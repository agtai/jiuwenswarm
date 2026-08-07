import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  FEATURE_LIVE_VOICE_INTEGRATED_WEB,
  FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION,
  FEATURE_LIVE_VOICE_TASK_DEMO,
} from '../../featureFlags';
import {
  IntegratedWebRouteShell,
  createCurrentIntegratedWebRouteSelection,
  type IntegratedWebRouteManifest,
  type IntegratedWebRouteSelection,
} from '../../features/live-voice/formal/integratedWebRouteShell';
import {
  PRODUCT_TEXT_PROGRESS_EVENT,
  ProductTextProgressAckOwner,
  adoptProductTextProgressEvent,
  parseProductTextProgressEvent,
  type ProductTextProgressEvent,
} from '../../features/live-voice/formal/productTextProgress';
import {
  ProductWebP2ActivationOwner,
  ProductWebP3MutationOwner,
  ProductWebP3ProgressOwner,
  pollProductP2RouteWithRecovery,
  requiresProductActivationCleanup,
  retryRetainedProductOperation,
  type ProductWebP2ActivationSnapshot,
  type ProductWebP3ProgressBinding,
  type ProductWebP3ProgressSnapshot,
  type ProductWebP3MutationInput,
} from '../../features/live-voice/formal/productWebActivation';
import { WebPlatformDiagnosticsMonitor, type WebPlatformDiagnosticsSnapshot } from '../../features/live-voice/formal/webPlatformDiagnostics';
import { extractWebErrorReason, webClient } from '../../services/webClient';
import './LiveVoiceIntegratedRoutePanel.css';

export { extractWebErrorReason };

export interface LiveVoiceIntegratedRoutePanelProps {
  activeSessionId: string | null;
  isConnected: boolean;
  agentRouteAvailable: boolean;
  taskCompatibilityAvailable: boolean;
  routeSelection?: Readonly<IntegratedWebRouteSelection>;
}

export type ProductPresentationAckInput = {
  response_id: string;
  response_generation: number;
  surface: 'text' | 'audio';
  unit_id: string;
  contiguous_cursor: number;
};

type ProductTurnInput = {
  commit_id: string;
  turn_id: string;
  response_id: string;
  committed_at: string;
  text: string;
};

export type ProductP2NotificationDisposition =
  | { readonly kind: 'continue' }
  | { readonly kind: 'failed'; readonly reason: string }
  | {
      readonly kind: 'presentation';
      readonly text: string;
      readonly response_id: string;
      readonly ack: ProductPresentationAckInput;
    };

function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function classifyProductP2Notification(
  notification: Readonly<Record<string, unknown>>,
  hasPresentedOutput = false
): ProductP2NotificationDisposition {
  const event = recordValue(notification.agent_event);
  const unit = recordValue(notification.presentation_unit);
  const response = recordValue(notification.response);
  const errorReason =
    typeof notification.error_reason === 'string'
      ? notification.error_reason
      : typeof event?.error_reason === 'string'
        ? event.error_reason
        : null;
  if (
    notification.kind === 'agent.error' ||
    errorReason !== null ||
    (typeof event?.event_type === 'string' && /(?:error|failed|blocked)$/.test(event.event_type))
  ) {
    return { kind: 'failed', reason: errorReason ?? 'PRODUCT_AGENT_OUTPUT_FAILED' };
  }
  if (
    notification.kind === 'agent.output' &&
    typeof event?.text === 'string' &&
    unit?.surface === 'text' &&
    typeof unit.unit_id === 'string' &&
    Number.isSafeInteger(unit.seq) &&
    typeof response?.response_id === 'string' &&
    Number.isSafeInteger(response.response_generation)
  ) {
    return {
      kind: 'presentation',
      text: event.text,
      response_id: response.response_id,
      ack: {
        response_id: response.response_id,
        response_generation: response.response_generation as number,
        surface: 'text',
        unit_id: unit.unit_id,
        contiguous_cursor: unit.seq as number,
      },
    };
  }
  const progressEvent = recordValue(notification.progress_event);
  const progressPayload = recordValue(progressEvent?.payload);
  if (notification.kind === 'work.progress' && progressPayload?.state === 'terminal') {
    return hasPresentedOutput
      ? { kind: 'continue' }
      : {
          kind: 'failed',
          reason:
            typeof progressPayload.outcome === 'string'
              ? `PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL:${progressPayload.outcome}`
              : 'PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL',
        };
  }
  return { kind: 'continue' };
}

export function retainBoundedPresentedProductResponse(
  responses: Map<string, true>,
  responseId: string,
  capacity = 128
): void {
  if (!Number.isSafeInteger(capacity) || capacity <= 0) {
    throw new Error('presented response capacity is invalid');
  }
  if (!responses.has(responseId) && responses.size >= capacity) {
    const oldest = responses.keys().next().value;
    if (typeof oldest === 'string') responses.delete(oldest);
  }
  responses.set(responseId, true);
}

function browserSpeechCompatibilityAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  const browserWindow = window as Window & {
    SpeechRecognition?: unknown;
    webkitSpeechRecognition?: unknown;
  };
  const recognition = typeof browserWindow.SpeechRecognition === 'function' || typeof browserWindow.webkitSpeechRecognition === 'function';
  return recognition && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
}

function createManifest(input: Readonly<LiveVoiceIntegratedRoutePanelProps>, correlationId: string, observedAt: string): IntegratedWebRouteManifest {
  const selection =
    input.routeSelection ??
    createCurrentIntegratedWebRouteSelection({
      p1_browser_speech_available: browserSpeechCompatibilityAvailable(),
      p2_text_chat_available: input.isConnected && input.agentRouteAvailable,
      p3_task_compatibility_enabled: FEATURE_LIVE_VOICE_TASK_DEMO,
      p3_task_compatibility_available: input.taskCompatibilityAvailable,
    });
  return new IntegratedWebRouteShell({
    enabled: FEATURE_LIVE_VOICE_INTEGRATED_WEB,
    registry: selection.registry,
    policy: selection.policy,
    context: {
      session_id: input.activeSessionId,
      correlation_id: correlationId,
      observed_at: observedAt,
    },
  }).preview();
}

function DiagnosticsFact({ label, value }: { label: string; value: string }) {
  return (
    <span className="live-voice-integrated__fact">
      <span>{label}</span>
      <code>{value}</code>
    </span>
  );
}

export function LiveVoiceIntegratedRoutePanel(props: LiveVoiceIntegratedRoutePanelProps) {
  const reactId = useId();
  const correlationId = useMemo(() => `integrated-web-${reactId.replace(/[^A-Za-z0-9_-]/g, '') || 'route'}`, [reactId]);
  const [platform, setPlatform] = useState<Readonly<WebPlatformDiagnosticsSnapshot> | null>(null);
  const [progress, setProgress] = useState<Readonly<ProductTextProgressEvent> | null>(null);
  const [progressAck, setProgressAck] = useState<'idle' | 'pending' | 'acknowledged' | 'failed'>('idle');
  const [p2Activation, setP2Activation] = useState<Readonly<ProductWebP2ActivationSnapshot>>({
    status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
    binding: null,
    reason: null,
  });
  const [p2RecoveryEpoch, setP2RecoveryEpoch] = useState(0);
  const [p3Activation, setP3Activation] = useState<Readonly<ProductWebP3ProgressSnapshot>>({
    status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
    binding: null,
    reason: null,
  });
  const [productInput, setProductInput] = useState('');
  const [productOutput, setProductOutput] = useState<string | null>(null);
  const [productTextStatus, setProductTextStatus] = useState<
    'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed'
  >('idle');
  const [pendingPresentationAck, setPendingPresentationAck] = useState<
    ProductPresentationAckInput | null
  >(null);
  const [p3MutationOperation, setP3MutationOperation] = useState<'task.create' | 'task.cancel'>('task.create');
  const [p3TaskName, setP3TaskName] = useState('');
  const [p3TaskInstruction, setP3TaskInstruction] = useState('');
  const [p3TargetTaskId, setP3TargetTaskId] = useState('');
  const [p3MutationStatus, setP3MutationStatus] = useState<
    'idle' | 'issuing' | 'confirmed' | 'mutating' | 'accepted' | 'failed'
  >('idle');
  const monitorRef = useRef<WebPlatformDiagnosticsMonitor | null>(null);
  const progressRef = useRef<Readonly<ProductTextProgressEvent> | null>(null);
  const pendingOwnedProgressRef = useRef(
    new Map<string, Readonly<ProductTextProgressEvent>>()
  );
  const progressConsumerRef = useRef<
    ((event: Readonly<ProductTextProgressEvent>) => void) | null
  >(null);
  const progressAckOwnerRef = useRef<ProductTextProgressAckOwner | null>(null);
  const activationOwnerRef = useRef<ProductWebP2ActivationOwner | null>(null);
  const pendingProductTurnRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductTurnInput;
  } | null>(null);
  const pendingPresentationAttemptRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductPresentationAckInput & { presented_at: string };
  } | null>(null);
  const presentedProductResponsesRef = useRef(new Map<string, true>());
  const progressActivationOwnerRef = useRef<ProductWebP3ProgressOwner | null>(null);
  const p3MutationOwnerRef = useRef<ProductWebP3MutationOwner | null>(null);
  const pendingP3MutationRef = useRef<ProductWebP3MutationInput | null>(null);
  const activeSessionRef = useRef<string | null>(props.activeSessionId);
  const progressOwnerEpochRef = useRef(0);
  const activationGenerationRef = useRef(0);
  const progressGenerationRef = useRef(0);
  const productTurnSequenceRef = useRef(0);
  const p3MutationSequenceRef = useRef(0);
  activeSessionRef.current = props.activeSessionId;
  const manifest = useMemo(
    () => createManifest(props, correlationId, new Date().toISOString()),
    [correlationId, props.activeSessionId, props.agentRouteAvailable, props.isConnected, props.routeSelection, props.taskCompatibilityAvailable]
  );

  const adoptProductP2Notification = (
    owner: ProductWebP2ActivationOwner,
    notification: Readonly<Record<string, unknown>>
  ) => {
    const response = recordValue(notification.response);
    const responseId =
      typeof response?.response_id === 'string' ? response.response_id : null;
    const disposition = classifyProductP2Notification(
      notification,
      responseId !== null && presentedProductResponsesRef.current.has(responseId)
    );
    if (disposition.kind === 'failed') {
      setProductTextStatus('failed');
      return;
    }
    if (disposition.kind !== 'presentation') return;
    const pending = pendingPresentationAttemptRef.current;
    if (
      pending !== null &&
      (pending.owner !== owner || pending.input.response_id !== disposition.response_id)
    ) {
      throw new Error('a previous presentation ACK is still unresolved');
    }
    retainBoundedPresentedProductResponse(
      presentedProductResponsesRef.current,
      disposition.response_id
    );
    setProductOutput(disposition.text);
    setProductTextStatus('presented');
    setPendingPresentationAck(disposition.ack);
    if (pending === null) {
      pendingPresentationAttemptRef.current = {
        owner,
        input: {
          ...disposition.ack,
          presented_at: new Date().toISOString(),
        },
      };
    }
  };

  const settleRetainedP2Operations = async (owner: ProductWebP2ActivationOwner) => {
    const ownerSession = owner.snapshot().binding?.session_id;
    const isCurrent = () =>
      activationOwnerRef.current === owner &&
      ownerSession !== undefined &&
      activeSessionRef.current === ownerSession;
    const pendingTurn = pendingProductTurnRef.current;
    if (pendingTurn?.owner === owner) {
      try {
        await retryRetainedProductOperation({
          operation: () => owner.submitText(pendingTurn.input),
          is_current: isCurrent,
        });
        if (pendingProductTurnRef.current === pendingTurn) {
          pendingProductTurnRef.current = null;
          setProductInput('');
          setProductTextStatus('waiting');
        }
      } catch (error) {
        if (owner.hasPendingSubmission()) throw error;
        if (pendingProductTurnRef.current === pendingTurn) {
          pendingProductTurnRef.current = null;
          setProductTextStatus('failed');
        }
      }
    }
    if (owner.hasPendingNotification()) {
      try {
        const notification = await retryRetainedProductOperation({
          operation: () => owner.nextNotification(),
          is_current: isCurrent,
        });
        adoptProductP2Notification(owner, notification);
      } catch (error) {
        if (owner.hasPendingNotification()) throw error;
        setProductTextStatus('failed');
      }
    }
    const pendingPresentation = pendingPresentationAttemptRef.current;
    if (pendingPresentation?.owner === owner) {
      try {
        await retryRetainedProductOperation({
          operation: () => owner.acknowledgePresentation(pendingPresentation.input),
          is_current: isCurrent,
        });
        if (pendingPresentationAttemptRef.current === pendingPresentation) {
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          setProductTextStatus('acknowledged');
        }
      } catch (error) {
        if (owner.hasPendingPresentationAck()) throw error;
        if (pendingPresentationAttemptRef.current === pendingPresentation) {
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          setProductTextStatus('failed');
        }
      }
    }
  };

  useEffect(() => {
    const monitor = new WebPlatformDiagnosticsMonitor({
      enabled: FEATURE_LIVE_VOICE_INTEGRATED_WEB,
      on_snapshot: setPlatform,
    });
    monitorRef.current = monitor;
    monitor.start();
    return () => {
      monitor.stop();
      if (monitorRef.current === monitor) monitorRef.current = null;
    };
  }, []);

  useEffect(() => {
    setProgress(null);
    progressRef.current = null;
    pendingOwnedProgressRef.current.clear();
    if (!FEATURE_LIVE_VOICE_INTEGRATED_WEB || !props.activeSessionId) return;
    const ownedSessionId = props.activeSessionId;
    const owner = new ProductTextProgressAckOwner({
      enabled: true,
      request: (method, params) => webClient.request(method, { ...params }),
      on_snapshot: snapshot => {
        if (
          activeSessionRef.current === ownedSessionId &&
          progressAckOwnerRef.current === owner &&
          progressRef.current?.delivery_id === snapshot.delivery_id
        ) {
          setProgressAck(snapshot.status);
        }
      },
    });
    owner.setConnected(props.isConnected);
    progressAckOwnerRef.current = owner;
    const consume = (parsed: Readonly<ProductTextProgressEvent>) => {
      if (
        activeSessionRef.current !== ownedSessionId ||
        parsed.session_id !== ownedSessionId ||
        progressAckOwnerRef.current !== owner
      ) {
        return;
      }
      const adopted = adoptProductTextProgressEvent(
        progressRef.current,
        parsed,
        ownedSessionId
      );
      if (adopted !== progressRef.current) {
        progressRef.current = adopted;
        setProgress(adopted);
      }
      owner.retain(parsed);
    };
    progressConsumerRef.current = consume;
    const unsubscribe = webClient.on(PRODUCT_TEXT_PROGRESS_EVENT, ({ payload }) => {
      const parsed = parseProductTextProgressEvent(payload);
      if (!parsed) return;
      if (
        activeSessionRef.current !== ownedSessionId ||
        parsed.session_id !== ownedSessionId ||
        progressAckOwnerRef.current !== owner
      ) {
        return;
      }
      const activation = progressActivationOwnerRef.current?.snapshot();
      if (
        !activation?.binding ||
        !progressMatchesOwnedBinding(parsed, activation.binding, ownedSessionId)
      ) {
        return;
      }
      if (activation.status !== 'active') {
        if (activation.status === 'activating') {
          pendingOwnedProgressRef.current.set(parsed.delivery_id, parsed);
        }
        return;
      }
      consume(parsed);
    });
    return () => {
      unsubscribe();
      owner.close();
      pendingOwnedProgressRef.current.clear();
      if (progressConsumerRef.current === consume) progressConsumerRef.current = null;
      if (progressAckOwnerRef.current === owner) progressAckOwnerRef.current = null;
    };
  }, [props.activeSessionId]);

  useEffect(() => {
    progressAckOwnerRef.current?.setConnected(props.isConnected);
  }, [props.isConnected]);

  useEffect(() => {
    pendingProductTurnRef.current = null;
    pendingPresentationAttemptRef.current = null;
    presentedProductResponsesRef.current.clear();
    setPendingPresentationAck(null);
    setProductOutput(null);
    setProductTextStatus('idle');
  }, [props.activeSessionId]);

  useEffect(() => {
    let cancelled = false;
    let recoveryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
    const scheduleRecovery = () => {
      if (cancelled || recoveryTimer !== null) return;
      recoveryTimer = globalThis.setTimeout(
        () => setP2RecoveryEpoch(epoch => epoch + 1),
        1000
      );
    };
    const ownedSessionId = props.activeSessionId;
    const run = async () => {
      const routeEligible = Boolean(
        FEATURE_LIVE_VOICE_INTEGRATED_WEB &&
        ownedSessionId &&
        props.agentRouteAvailable
      );
      const previous = activationOwnerRef.current;
      if (previous) {
        const snapshot = previous.snapshot();
        const sameSession = snapshot.binding?.session_id === ownedSessionId;
        if (routeEligible && sameSession && snapshot.status === 'active') {
          if (!props.isConnected) {
            setP2Activation(snapshot);
            return;
          }
          try {
            await settleRetainedP2Operations(previous);
            await previous.closeWithRetry();
          } catch {
            scheduleRecovery();
            return;
          }
          if (activationOwnerRef.current === previous) {
            activationOwnerRef.current = null;
          }
        }
        if (
          routeEligible &&
          sameSession &&
          snapshot.status === 'activating' &&
          snapshot.binding
        ) {
          try {
            const settled = await previous.start(snapshot.binding);
            if (!cancelled && activationOwnerRef.current === previous) {
              setP2Activation(settled);
            }
          } catch {
            // The exact ambiguous activation is reconciled below on the next run.
            if (previous.needsCleanup()) scheduleRecovery();
          }
          return;
        }
        if (previous.needsCleanup()) {
          try {
            await previous.closeWithRetry({
              on_retry: snapshot => {
                if (!cancelled && activationOwnerRef.current === previous) {
                  setP2Activation(snapshot);
                }
              },
            });
          } catch {
            scheduleRecovery();
            return;
          }
        }
        if (activationOwnerRef.current === previous) activationOwnerRef.current = null;
      }
      if (
        cancelled ||
        !routeEligible ||
        !props.isConnected ||
        !ownedSessionId
      ) {
        if (!cancelled) {
          setP2Activation({
            status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
            binding: null,
            reason: null,
          });
        }
        return;
      }
      activationGenerationRef.current += 1;
      const generation = activationGenerationRef.current;
      const routeId = correlationId.replace(/[^A-Za-z0-9_-]/g, '') || 'route';
      let owner: ProductWebP2ActivationOwner | null = null;
      owner = new ProductWebP2ActivationOwner({
        enabled: true,
        request: (method, params, requestId) =>
          webClient.request(method, params, { requestId }),
        on_snapshot: snapshot => {
          if (
            !cancelled &&
            activeSessionRef.current === ownedSessionId &&
            activationOwnerRef.current === owner
          ) {
            setP2Activation(snapshot);
          }
        },
      });
      activationOwnerRef.current = owner;
      try {
        await owner.start({
          session_id: ownedSessionId,
          correlation_id: correlationId,
          interaction_id: `web-interaction-${routeId}`,
          activation_id: `web-activation-${routeId}-${generation}`,
          activation_generation: generation,
        });
      } catch (error) {
        // An activation response may have been lost after the route opened.
        // Reconcile the exact binding now; a later effect will retry the same
        // retained owner if the bounded cleanup remains pending.
        if (requiresProductActivationCleanup(error)) {
          try {
            await owner.closeWithRetry();
            if (!cancelled && activationOwnerRef.current === owner) {
              activationOwnerRef.current = null;
              setP2RecoveryEpoch(epoch => epoch + 1);
            }
          } catch {
            // Keep the exact cleanup owner and schedule another bounded pass.
            if (!cancelled && activationOwnerRef.current === owner) {
              scheduleRecovery();
            }
          }
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
      if (recoveryTimer !== null) globalThis.clearTimeout(recoveryTimer);
    };
  }, [correlationId, p2RecoveryEpoch, props.activeSessionId, props.agentRouteAvailable, props.isConnected]);

  useEffect(() => {
    return () => {
      const closing = activationOwnerRef.current;
      if (!closing) return;
      if (!closing.needsCleanup()) {
        if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
        return;
      }
      void closing
        .closeWithRetry()
        .then(() => {
          if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
        })
        .catch(() => undefined);
    };
  }, [correlationId, props.activeSessionId, props.agentRouteAvailable]);

  useEffect(() => {
    const owner = activationOwnerRef.current;
    const binding = p2Activation.binding;
    if (
      !props.isConnected ||
      p2Activation.status !== 'active' ||
      !binding ||
      !owner ||
      pendingPresentationAck !== null
    ) return;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled && activationOwnerRef.current === owner) {
        try {
          const outcome = await pollProductP2RouteWithRecovery({
            owner,
            is_current: () =>
              !cancelled &&
              activationOwnerRef.current === owner &&
              activeSessionRef.current === binding.session_id,
            settle_retained_operations: () => settleRetainedP2Operations(owner),
            can_activate_successor: () =>
              !cancelled &&
              activationOwnerRef.current === owner &&
              activeSessionRef.current === binding.session_id &&
              props.isConnected,
            activate_successor: async () => {
              if (activationOwnerRef.current === owner) {
                activationOwnerRef.current = null;
              }
              activationGenerationRef.current += 1;
              const generation = activationGenerationRef.current;
              const routeId =
                correlationId.replace(/[^A-Za-z0-9_-]/g, '') || 'route';
              let successor: ProductWebP2ActivationOwner | null = null;
              successor = new ProductWebP2ActivationOwner({
                enabled: true,
                request: (method, params, requestId) =>
                  webClient.request(method, params, { requestId }),
                on_snapshot: snapshot => {
                  if (
                    activeSessionRef.current === binding.session_id &&
                    activationOwnerRef.current === successor
                  ) {
                    setP2Activation(snapshot);
                  }
                },
              });
              activationOwnerRef.current = successor;
              await successor.start({
                session_id: binding.session_id,
                correlation_id: binding.correlation_id,
                interaction_id: binding.interaction_id,
                activation_id: `web-activation-${routeId}-${generation}`,
                activation_generation: generation,
              });
              return successor;
            },
          });
          if (outcome.kind === 'recovered') return;
          if (cancelled || activationOwnerRef.current !== owner) return;
          adoptProductP2Notification(owner, outcome.notification);
          if (pendingPresentationAttemptRef.current?.owner === owner) return;
        } catch {
          const retained = activationOwnerRef.current;
          if (!cancelled && retained?.needsCleanup()) {
            setP2RecoveryEpoch(epoch => epoch + 1);
          }
          if (!cancelled) {
            setProductTextStatus('failed');
          }
          return;
        }
      }
    };
    void poll();
    return () => {
      cancelled = true;
    };
  }, [correlationId, p2Activation.binding, p2Activation.status, pendingPresentationAck, props.isConnected]);

  useEffect(() => {
    const ack = pendingPresentationAck;
    const owner = activationOwnerRef.current;
    if (!ack || !owner || productOutput === null || !props.isConnected) return;
    let retained = pendingPresentationAttemptRef.current;
    if (retained !== null && retained.owner !== owner) {
      setProductTextStatus('failed');
      return;
    }
    if (retained === null) {
      retained = {
        owner,
        input: {
          ...ack,
          presented_at: new Date().toISOString(),
        },
      };
      pendingPresentationAttemptRef.current = retained;
    }
    let cancelled = false;
    void retryRetainedProductOperation({
      operation: () => owner.acknowledgePresentation(retained.input),
      is_current: () =>
        !cancelled &&
        activationOwnerRef.current === owner &&
        activeSessionRef.current === p2Activation.binding?.session_id,
    })
      .then(() => {
        if (
          !cancelled &&
          activationOwnerRef.current === owner &&
          pendingPresentationAttemptRef.current === retained
        ) {
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          setProductTextStatus('acknowledged');
        }
      })
      .catch(() => {
        if (!cancelled && activationOwnerRef.current === owner) {
          setProductTextStatus('failed');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [pendingPresentationAck, productOutput, props.isConnected]);

  useEffect(() => {
    pendingP3MutationRef.current = null;
    setP3MutationStatus('idle');
    if (
      !FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ||
      !props.activeSessionId
    ) {
      p3MutationOwnerRef.current = null;
      return;
    }
    const owner = new ProductWebP3MutationOwner({
      enabled: true,
      request: (method, params, requestId) =>
        webClient.request(method, params, { requestId }),
    });
    p3MutationOwnerRef.current = owner;
    return () => {
      if (p3MutationOwnerRef.current === owner) p3MutationOwnerRef.current = null;
    };
  }, [props.activeSessionId]);

  const submitProductText = async () => {
    const owner = activationOwnerRef.current;
    if (!owner || p2Activation.status !== 'active' || !productInput.trim()) return;
    let retained = pendingProductTurnRef.current;
    if (retained !== null && retained.owner !== owner) {
      setProductTextStatus('failed');
      return;
    }
    if (retained === null) {
      if (
        pendingPresentationAck !== null ||
        pendingPresentationAttemptRef.current !== null ||
        owner.hasPendingSubmission() ||
        owner.hasPendingPresentationAck()
      ) {
        setProductTextStatus('failed');
        return;
      }
      productTurnSequenceRef.current += 1;
      const identity = `${Date.now()}-${productTurnSequenceRef.current}`;
      retained = {
        owner,
        input: {
          commit_id: `web-commit-${identity}`,
          turn_id: `web-turn-${identity}`,
          response_id: `web-response-${identity}`,
          committed_at: new Date().toISOString(),
          text: productInput,
        },
      };
      pendingProductTurnRef.current = retained;
      setProductOutput(null);
    }
    setProductTextStatus('submitting');
    try {
      await retryRetainedProductOperation({
        operation: () => owner.submitText(retained.input),
        is_current: () =>
          props.isConnected &&
          activationOwnerRef.current === owner &&
          activeSessionRef.current === p2Activation.binding?.session_id,
      });
      if (
        activationOwnerRef.current === owner &&
        pendingProductTurnRef.current === retained
      ) {
        pendingProductTurnRef.current = null;
        setProductInput('');
        setProductTextStatus('waiting');
      }
    } catch {
      if (activationOwnerRef.current === owner) {
        if (!owner.hasPendingSubmission()) pendingProductTurnRef.current = null;
        setProductTextStatus('failed');
      }
    }
  };

  const buildP3Mutation = (): ProductWebP3MutationInput | null => {
    const sessionId = props.activeSessionId;
    if (!sessionId) return null;
    p3MutationSequenceRef.current += 1;
    const identity = `${Date.now()}-${p3MutationSequenceRef.current}`;
    const common = {
      session_id: sessionId,
      command_id: `web-task-command-${identity}`,
      issued_at: new Date().toISOString(),
      correlation_id: `${correlationId}-task-${identity}`,
    };
    if (p3MutationOperation === 'task.cancel') {
      if (!p3TargetTaskId.trim()) return null;
      return { operation: 'task.cancel', ...common, task_id: p3TargetTaskId };
    }
    if (!p3TaskName.trim() || !p3TaskInstruction.trim()) return null;
    return {
      operation: 'task.create',
      ...common,
      name: p3TaskName,
      instruction: p3TaskInstruction,
    };
  };

  const issueP3MutationConfirmation = async () => {
    const owner = p3MutationOwnerRef.current;
    const mutation = pendingP3MutationRef.current ?? buildP3Mutation();
    if (!owner || !mutation) return;
    pendingP3MutationRef.current = mutation;
    setP3MutationStatus('issuing');
    try {
      await owner.issue(mutation);
      if (p3MutationOwnerRef.current === owner) {
        setP3MutationStatus('confirmed');
      }
    } catch {
      if (p3MutationOwnerRef.current === owner) {
        if (!owner.hasPendingMutation()) pendingP3MutationRef.current = null;
        setP3MutationStatus('failed');
      }
    }
  };

  const executeP3Mutation = async () => {
    const owner = p3MutationOwnerRef.current;
    const mutation = pendingP3MutationRef.current;
    if (!owner || !mutation) return;
    setP3MutationStatus('mutating');
    try {
      await owner.mutate(mutation);
      if (p3MutationOwnerRef.current === owner) {
        pendingP3MutationRef.current = null;
        setP3MutationStatus('accepted');
      }
    } catch {
      if (p3MutationOwnerRef.current === owner) {
        if (!owner.hasPendingMutation()) pendingP3MutationRef.current = null;
        setP3MutationStatus('failed');
      }
    }
  };

  useEffect(() => {
    let cancelled = false;
    let owner: ProductWebP3ProgressOwner | null = null;
    const ownedSessionId = props.activeSessionId;
    const ownerEpoch = progressOwnerEpochRef.current + 1;
    progressOwnerEpochRef.current = ownerEpoch;
    const run = async () => {
      const previous = progressActivationOwnerRef.current;
      if (previous) {
        if (previous.needsCleanup()) {
          try {
            await previous.closeWithRetry({
              on_retry: snapshot => {
                if (!cancelled && progressActivationOwnerRef.current === previous) {
                  setP3Activation(snapshot);
                }
              },
            });
          } catch {
            return;
          }
        }
        if (progressActivationOwnerRef.current === previous) {
          progressActivationOwnerRef.current = null;
        }
      }
      if (
        cancelled ||
        !FEATURE_LIVE_VOICE_INTEGRATED_WEB ||
        !props.activeSessionId ||
        !props.isConnected
      ) {
        if (!cancelled) {
          setP3Activation({
            status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
            binding: null,
            reason: null,
          });
        }
        return;
      }
      progressGenerationRef.current += 1;
      const generation = progressGenerationRef.current;
      const routeId = correlationId.replace(/[^A-Za-z0-9_-]/g, '') || 'route';
      owner = new ProductWebP3ProgressOwner({
        enabled: true,
        request: (method, params) => webClient.request(method, params),
        on_snapshot: snapshot => {
          if (!isCurrentProgressOwner({
            cancelled,
            owner_epoch: ownerEpoch,
            current_owner_epoch: progressOwnerEpochRef.current,
            owner_session_id: ownedSessionId,
            active_session_id: activeSessionRef.current,
            is_current_owner: progressActivationOwnerRef.current === owner,
          })) {
            return;
          }
          setP3Activation(snapshot);
          if (snapshot.status === 'active' && snapshot.binding) {
            const pending = [...pendingOwnedProgressRef.current.values()];
            pendingOwnedProgressRef.current.clear();
            for (const event of pending) {
              if (
                progressMatchesOwnedBinding(
                  event,
                  snapshot.binding,
                  ownedSessionId
                )
              ) {
                progressConsumerRef.current?.(event);
              }
            }
          }
        },
      });
      progressActivationOwnerRef.current = owner;
      try {
        await owner.start({
          session_id: props.activeSessionId,
          correlation_id: correlationId,
          origin_id: `web-progress-${routeId}`,
          generation_id: `web-progress-generation-${routeId}`,
          generation,
        });
      } catch (error) {
        // Reconcile a possibly response-lost activation before any successor
        // route can be created. The exact owner is retained on retry failure.
        if (
          owner.snapshot().binding &&
          requiresProductActivationCleanup(error)
        ) {
          try {
            await owner.closeWithRetry();
          } catch {
            // The exact cleanup_pending owner remains retained in the ref.
          }
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
      if (progressOwnerEpochRef.current === ownerEpoch) {
        progressOwnerEpochRef.current += 1;
      }
      const closing = owner;
      if (!closing) return;
      if (!closing.needsCleanup()) {
        if (progressActivationOwnerRef.current === closing) {
          progressActivationOwnerRef.current = null;
        }
        return;
      }
      void closing
        .closeWithRetry()
        .then(() => {
          if (progressActivationOwnerRef.current === closing) {
            progressActivationOwnerRef.current = null;
          }
        })
        .catch(() => undefined);
    };
  }, [correlationId, props.activeSessionId, props.isConnected]);

  return (
    <LiveVoiceIntegratedRoutePanelView
      manifest={manifest}
      platform={platform}
      progress={progress}
      progressAck={progressAck}
      p2Activation={props.isConnected ? p2Activation : null}
      p3Activation={p3Activation}
      productInput={productInput}
      productOutput={productOutput}
      productTextStatus={productTextStatus}
      productOperationRetained={Boolean(
          pendingProductTurnRef.current ||
          pendingPresentationAttemptRef.current ||
          activationOwnerRef.current?.hasPendingSubmission() ||
          activationOwnerRef.current?.hasPendingPresentationAck()
      )}
      onProductInput={value => {
        const owner = activationOwnerRef.current;
        if (
          pendingProductTurnRef.current ||
          pendingPresentationAttemptRef.current ||
          owner?.hasPendingSubmission() ||
          owner?.hasPendingPresentationAck()
        ) return;
        setProductTextStatus('idle');
        setProductInput(value);
      }}
      onProductSubmit={() => void submitProductText()}
      p3MutationEnabled={FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION && props.isConnected}
      p3MutationOperation={p3MutationOperation}
      p3TaskName={p3TaskName}
      p3TaskInstruction={p3TaskInstruction}
      p3TargetTaskId={p3TargetTaskId}
      p3MutationStatus={p3MutationStatus}
      p3MutationRetained={p3MutationOwnerRef.current?.hasPendingMutation() ?? false}
      onP3MutationOperation={value => {
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3MutationOperation(value);
      }}
      onP3TaskName={value => {
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3TaskName(value);
      }}
      onP3TaskInstruction={value => {
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3TaskInstruction(value);
      }}
      onP3TargetTaskId={value => {
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3TargetTaskId(value);
      }}
      onP3Issue={() => void issueP3MutationConfirmation()}
      onP3Execute={() => void executeP3Mutation()}
      onRefresh={() => void monitorRef.current?.refresh()}
    />
  );
}

export function progressMatchesOwnedBinding(
  event: Readonly<ProductTextProgressEvent>,
  binding: Readonly<ProductWebP3ProgressBinding>,
  activeSessionId: string | null
): boolean {
  return (
    activeSessionId !== null &&
    event.session_id === activeSessionId &&
    binding.session_id === activeSessionId &&
    event.task_id === binding.task_id &&
    event.correlation_id === binding.correlation_id &&
    event.origin_id === binding.origin_id &&
    event.generation_id === binding.generation_id &&
    event.generation === binding.generation
  );
}

export function isCurrentProgressOwner(input: {
  cancelled: boolean;
  owner_epoch: number;
  current_owner_epoch: number;
  owner_session_id: string | null;
  active_session_id: string | null;
  is_current_owner: boolean;
}): boolean {
  return (
    !input.cancelled &&
    input.is_current_owner &&
    input.owner_epoch === input.current_owner_epoch &&
    input.owner_session_id !== null &&
    input.owner_session_id === input.active_session_id
  );
}

export interface LiveVoiceIntegratedRoutePanelViewProps {
  manifest: Readonly<IntegratedWebRouteManifest>;
  platform: Readonly<WebPlatformDiagnosticsSnapshot> | null;
  progress?: Readonly<ProductTextProgressEvent> | null;
  progressAck?: 'idle' | 'pending' | 'acknowledged' | 'failed';
  p2Activation?: Readonly<ProductWebP2ActivationSnapshot> | null;
  p3Activation?: Readonly<ProductWebP3ProgressSnapshot> | null;
  productInput?: string;
  productOutput?: string | null;
  productTextStatus?: 'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed';
  productOperationRetained?: boolean;
  onProductInput?: (value: string) => void;
  onProductSubmit?: () => void;
  p3MutationEnabled?: boolean;
  p3MutationOperation?: 'task.create' | 'task.cancel';
  p3TaskName?: string;
  p3TaskInstruction?: string;
  p3TargetTaskId?: string;
  p3MutationStatus?: 'idle' | 'issuing' | 'confirmed' | 'mutating' | 'accepted' | 'failed';
  p3MutationRetained?: boolean;
  onP3MutationOperation?: (value: 'task.create' | 'task.cancel') => void;
  onP3TaskName?: (value: string) => void;
  onP3TaskInstruction?: (value: string) => void;
  onP3TargetTaskId?: (value: string) => void;
  onP3Issue?: () => void;
  onP3Execute?: () => void;
  onRefresh: () => void;
}

export function LiveVoiceIntegratedRoutePanelView({
  manifest,
  platform,
  progress = null,
  progressAck = 'idle',
  p2Activation = null,
  p3Activation = null,
  productInput = '',
  productOutput = null,
  productTextStatus = 'idle',
  productOperationRetained = false,
  onProductInput,
  onProductSubmit,
  p3MutationEnabled = false,
  p3MutationOperation = 'task.create',
  p3TaskName = '',
  p3TaskInstruction = '',
  p3TargetTaskId = '',
  p3MutationStatus = 'idle',
  p3MutationRetained = false,
  onP3MutationOperation,
  onP3TaskName,
  onP3TaskInstruction,
  onP3TargetTaskId,
  onP3Issue,
  onP3Execute,
  onRefresh,
}: LiveVoiceIntegratedRoutePanelViewProps) {
  const { t } = useTranslation();

  const compositionLabel = t(`liveVoice.integrated.composition.${manifest.composition_state}`);
  const browserEvidence = platform?.browser_version
    ? `${platform.browser_family} ${platform.browser_version}`
    : (platform?.browser_family ?? t('liveVoice.integrated.diagnostics.pending'));
  const p3MutationLocked =
    ['issuing', 'confirmed', 'mutating'].includes(p3MutationStatus) ||
    (p3MutationStatus === 'failed' && p3MutationRetained);
  const productTextLocked =
    ['submitting', 'waiting', 'presented'].includes(productTextStatus) ||
    productOperationRetained;

  return (
    <details className="live-voice-integrated" data-composition={manifest.composition_state} data-testid="live-voice-integrated-route">
      <summary className="live-voice-integrated__summary">
        <Activity size={16} strokeWidth={2} aria-hidden="true" />
        <span>{t('liveVoice.integrated.title')}</span>
        <code>{compositionLabel}</code>
      </summary>
      <div className="live-voice-integrated__body">
        <div className="live-voice-integrated__warning" role="note">
          <ShieldAlert size={16} strokeWidth={2} aria-hidden="true" />
          <span>{t('liveVoice.integrated.shellOnly')}</span>
        </div>

        <div className="live-voice-integrated__section" aria-label={t('liveVoice.integrated.routes')}>
          <strong>{t('liveVoice.integrated.routes')}</strong>
          <div className="live-voice-integrated__facts">
            <DiagnosticsFact label={t('liveVoice.integrated.session')} value={manifest.session_id ?? 'null'} />
            <DiagnosticsFact label={t('liveVoice.integrated.correlation')} value={manifest.correlation_id} />
            <DiagnosticsFact label={t('liveVoice.integrated.observedAt')} value={manifest.observed_at} />
          </div>
          <div className="live-voice-integrated__routes">
            {manifest.segments.map(route => (
              <div
                className="live-voice-integrated__route"
                data-implementation-class={route.implementation_class}
                data-testid={`live-voice-integrated-${route.segment_id}`}
                key={route.segment_id}
              >
                <span className="live-voice-integrated__route-heading">
                  <code>{route.segment_id}</code>
                  <span className="live-voice-integrated__class">{route.implementation_class}</span>
                </span>
                <DiagnosticsFact label={t('liveVoice.integrated.requested')} value={route.requested_class} />
                <DiagnosticsFact label={t('liveVoice.integrated.owner')} value={route.owner_module ?? 'unknown'} />
                <DiagnosticsFact label={t('liveVoice.integrated.adapter')} value={route.adapter_id ?? 'null'} />
                <DiagnosticsFact label={t('liveVoice.integrated.provider')} value={route.capability_provider ?? 'null'} />
                <DiagnosticsFact label={t('liveVoice.integrated.contract')} value={route.contract_version ?? 'null'} />
                <DiagnosticsFact label={t('liveVoice.integrated.wiring')} value={route.wiring_state} />
                {route.safe_reason && <DiagnosticsFact label={t('liveVoice.integrated.reason')} value={route.safe_reason} />}
              </div>
            ))}
          </div>
          {p2Activation && (
            <div className="live-voice-integrated__facts" data-testid="live-voice-integrated-p2-activation">
              <DiagnosticsFact label={t('liveVoice.integrated.activation.status')} value={p2Activation.status} />
              <DiagnosticsFact
                label={t('liveVoice.integrated.activation.scope')}
                value={p2Activation.binding ? `${p2Activation.binding.interaction_id}:${p2Activation.binding.activation_generation}` : 'null'}
              />
            </div>
          )}
          {p3Activation && (
            <div className="live-voice-integrated__facts" data-testid="live-voice-integrated-p3-activation">
              <DiagnosticsFact label={t('liveVoice.integrated.activation.status')} value={`p3:${p3Activation.status}`} />
              <DiagnosticsFact
                label={t('liveVoice.integrated.activation.scope')}
                value={p3Activation.binding ? `${p3Activation.binding.task_id}:${p3Activation.binding.generation}` : 'null'}
              />
            </div>
          )}
          {p2Activation?.status === 'active' && onProductInput && onProductSubmit && (
            <form
              className="live-voice-integrated__text-route"
              data-testid="live-voice-integrated-product-text"
              onSubmit={event => {
                event.preventDefault();
                onProductSubmit();
              }}
            >
              <label htmlFor="live-voice-product-text">
                {t('liveVoice.integrated.textRoute.label')}
              </label>
              <textarea
                id="live-voice-product-text"
                value={productInput}
                disabled={productTextLocked}
                onChange={event => onProductInput(event.target.value)}
                placeholder={t('liveVoice.integrated.textRoute.placeholder')}
                maxLength={100000}
              />
              <button
                type="submit"
                disabled={!productInput.trim() || productTextLocked}
              >
                {t('liveVoice.integrated.textRoute.submit')}
              </button>
              <DiagnosticsFact
                label={t('liveVoice.integrated.textRoute.status')}
                value={productTextStatus}
              />
              {productOutput !== null && (
                <output aria-live="polite">{productOutput}</output>
              )}
            </form>
          )}
          {p3MutationEnabled &&
            onP3MutationOperation &&
            onP3TaskName &&
            onP3TaskInstruction &&
            onP3TargetTaskId &&
            onP3Issue &&
            onP3Execute && (
              <div
                className="live-voice-integrated__text-route"
                data-testid="live-voice-integrated-p3-mutation"
              >
                <strong>{t('liveVoice.integrated.taskControl.title')}</strong>
                <span className="live-voice-integrated__progress-note">
                  {t('liveVoice.integrated.taskControl.disclosure')}
                </span>
                <select
                  value={p3MutationOperation}
                  disabled={p3MutationLocked}
                  onChange={event =>
                    onP3MutationOperation(
                      event.target.value === 'task.cancel'
                        ? 'task.cancel'
                        : 'task.create'
                    )
                  }
                >
                  <option value="task.create">
                    {t('liveVoice.integrated.taskControl.create')}
                  </option>
                  <option value="task.cancel">
                    {t('liveVoice.integrated.taskControl.cancel')}
                  </option>
                </select>
                {p3MutationOperation === 'task.create' ? (
                  <>
                    <input
                      value={p3TaskName}
                      disabled={p3MutationLocked}
                      onChange={event => onP3TaskName(event.target.value)}
                      placeholder={t('liveVoice.integrated.taskControl.name')}
                    />
                    <textarea
                      value={p3TaskInstruction}
                      disabled={p3MutationLocked}
                      onChange={event => onP3TaskInstruction(event.target.value)}
                      placeholder={t('liveVoice.integrated.taskControl.instruction')}
                      maxLength={100000}
                    />
                  </>
                ) : (
                  <input
                    value={p3TargetTaskId}
                    disabled={p3MutationLocked}
                    onChange={event => onP3TargetTaskId(event.target.value)}
                    placeholder={t('liveVoice.integrated.taskControl.taskId')}
                  />
                )}
                {p3MutationStatus === 'confirmed' ? (
                  <button type="button" onClick={onP3Execute}>
                    {t('liveVoice.integrated.taskControl.execute')}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={onP3Issue}
                    disabled={p3MutationStatus === 'issuing' || p3MutationStatus === 'mutating'}
                  >
                    {t('liveVoice.integrated.taskControl.confirm')}
                  </button>
                )}
                <DiagnosticsFact
                  label={t('liveVoice.integrated.taskControl.status')}
                  value={p3MutationStatus}
                />
              </div>
            )}
        </div>

        {progress && (
          <div
            className="live-voice-integrated__section"
            aria-label={t('liveVoice.integrated.progress.title')}
            data-testid="live-voice-integrated-product-progress"
          >
            <strong>{t('liveVoice.integrated.progress.title')}</strong>
            <span className="live-voice-integrated__progress-note">
              {t('liveVoice.integrated.progress.disclosure')}
            </span>
            <div className="live-voice-integrated__facts" aria-live="polite">
              <DiagnosticsFact label={t('liveVoice.integrated.progress.task')} value={progress.task_id} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.state')} value={progress.state} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.correlation')} value={progress.correlation_id} />
              <DiagnosticsFact
                label={t('liveVoice.integrated.progress.generation')}
                value={`${progress.generation_kind}:${progress.generation_id}:${progress.generation}`}
              />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.sequence')} value={String(progress.source_event.seq)} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.evidence')} value={progress.evidence_id} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.delivery')} value={progress.delivery_id} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.ack')} value={progressAck} />
            </div>
          </div>
        )}

        <div className="live-voice-integrated__section" aria-label={t('liveVoice.integrated.platform')}>
          <span className="live-voice-integrated__section-heading">
            <strong>{t('liveVoice.integrated.platform')}</strong>
            <button
              type="button"
              className="live-voice-integrated__refresh"
              onClick={onRefresh}
              aria-label={t('liveVoice.integrated.refresh')}
              title={t('liveVoice.integrated.refresh')}
            >
              <RefreshCw size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </span>
          <div className="live-voice-integrated__facts" aria-live="polite">
            <DiagnosticsFact label={t('liveVoice.integrated.diagnostics.browser')} value={browserEvidence} />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.browserScope')}
              value={platform?.alpha_browser_scope ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.platform')}
              value={platform?.reported_platform ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.origin')}
              value={
                platform
                  ? `scope:${platform.origin_scope}; transport:${platform.transport_security}; secure_context:${platform.secure_context}`
                  : t('liveVoice.integrated.diagnostics.pending')
              }
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.permission')}
              value={platform?.microphone_permission ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.devices')}
              value={platform ? `input:${platform.audio_input}; output:${platform.audio_output}` : t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.activation')}
              value={platform?.user_activation ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.page')}
              value={
                platform
                  ? `visibility:${platform.page_visibility}; discarded:${platform.page_was_discarded ?? 'unknown'}`
                  : t('liveVoice.integrated.diagnostics.pending')
              }
            />
            <DiagnosticsFact label={t('liveVoice.integrated.diagnostics.network')} value={platform?.network ?? t('liveVoice.integrated.diagnostics.pending')} />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.aio')}
              value={
                platform
                  ? `capture:${platform.aio_capability.capture_pcm_f32}; playout:${platform.aio_capability.playout_pcm_f32}; wired:false`
                  : t('liveVoice.integrated.diagnostics.pending')
              }
            />
          </div>
          {platform && platform.diagnostic_errors.length > 0 && (
            <span className="live-voice-integrated__diagnostic-error" role="status">
              {t('liveVoice.integrated.diagnostics.errors')}: <code>{platform.diagnostic_errors.join(', ')}</code>
            </span>
          )}
        </div>
      </div>
    </details>
  );
}
