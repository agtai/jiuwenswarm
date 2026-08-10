import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  FEATURE_LIVE_VOICE_INTEGRATED_WEB,
  FEATURE_LIVE_VOICE_INTEGRATED_P1,
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
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P3_TASK_EVENTS_METHOD,
  PRODUCT_P3_TASK_STATUS_METHOD,
  ProductWebP2ActivationOwner,
  ProductWebP3MutationOwner,
  ProductWebP3ProgressOwner,
  isRetriableProductOperationError,
  pollProductP2RouteWithRecovery,
  requiresProductActivationCleanup,
  retryRetainedProductOperation,
  type ProductWebP2ActivationSnapshot,
  type ProductWebP3ProgressBinding,
  type ProductWebP3ProgressSnapshot,
  type ProductWebP3MutationInput,
} from '../../features/live-voice/formal/productWebActivation';
import {
  PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  PRODUCT_P1_CAPTURE_MAX_DURATION_MS,
  ProductP1VoiceRouteOwner,
  type ProductP1VoiceStatus,
} from '../../features/live-voice/formal/productP1VoiceRoute';
import {
  PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  ProductP2ActivationJournal,
  reconcileProductP2Predecessor,
} from '../../features/live-voice/formal/productP2ActivationJournal';
import {
  FormalTaskControlLeaf,
  isFormalTaskRetryEligible,
  prepareFormalTaskMutation,
  type FormalTaskControlRecord,
  type PreparedFormalTaskMutation,
} from '../../features/live-voice/formal/formalTaskControlLeaf';
import { WebPlatformDiagnosticsMonitor, type WebPlatformDiagnosticsSnapshot } from '../../features/live-voice/formal/webPlatformDiagnostics';
import { extractWebErrorReason, webClient } from '../../services/webClient';
import type { WebRequestOptions } from '../../types';
import './LiveVoiceIntegratedRoutePanel.css';

export { extractWebErrorReason };

export interface LiveVoiceIntegratedRoutePanelProps {
  activeSessionId: string | null;
  isConnected: boolean;
  agentRouteAvailable: boolean;
  taskCompatibilityAvailable: boolean;
  routeSelection?: Readonly<IntegratedWebRouteSelection>;
  request?: (method: string, params?: Record<string, unknown>, options?: WebRequestOptions) => Promise<unknown>;
  p3RetryInspectionWait?: (delayMs: number, signal: AbortSignal) => Promise<void>;
}

const defaultProductRequest = (method: string, params?: Record<string, unknown>, options?: WebRequestOptions): Promise<unknown> =>
  webClient.request(method, params, options);

const PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS = Object.freeze([250, 500, 1_000, 2_000, 4_000, 8_000, 16_000, 30_000]);

function defaultP3RetryInspectionWait(delayMs: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new Error('P3 retry inspection was cancelled'));
  return new Promise((resolve, reject) => {
    let settled = false;
    let timeoutId: ReturnType<typeof globalThis.setTimeout> | null = null;
    const finish = (error: Error | null) => {
      if (settled) return;
      settled = true;
      if (timeoutId !== null) globalThis.clearTimeout(timeoutId);
      signal.removeEventListener('abort', abort);
      if (error === null) resolve();
      else reject(error);
    };
    const abort = () => finish(new Error('P3 retry inspection was cancelled'));
    timeoutId = globalThis.setTimeout(() => finish(null), delayMs);
    signal.addEventListener('abort', abort, { once: true });
  });
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
  response_id?: string;
  committed_at: string;
  text: string;
  dispatch_target?: 'agent' | 'task';
  voice_commit_receipt?: string;
  critical_confirmation?: true;
};

type ProductRecognizedVoice = Readonly<{
  session_id: string;
  text: string;
  voice_commit_receipt: string;
}>;

export type ProductVoiceTaskOrigin = Readonly<{
  session_id: string;
  interaction_id: string;
  turn_id: string;
  commit_id: string;
  response_id: string;
  response_generation: number;
  instruction: string;
}>;

type ProductWebRequest = NonNullable<LiveVoiceIntegratedRoutePanelProps['request']>;

/**
 * Read and validate one exact retry candidate before publishing it to the live
 * leaf.  Status and full history are first reduced in an isolated probe; only
 * the already-validated event history may update the live replica, and only
 * while the caller's Session/target generation is still current.
 */
export async function inspectProductP3RetryCandidate(input: Readonly<{
  request: ProductWebRequest;
  leaf: FormalTaskControlLeaf;
  session_id: string;
  task_id: string;
  request_nonce: string;
  is_current: () => boolean;
}>): Promise<Readonly<FormalTaskControlRecord>> {
  const taskId = input.task_id.trim();
  if (!taskId || !input.session_id || !input.request_nonce || !input.is_current()) {
    throw new Error('formal task retry inspection is stale or incomplete');
  }
  const initialSnapshot = input.leaf.snapshot();
  if (!initialSnapshot.connected || initialSnapshot.binding.session_id !== input.session_id) {
    throw new Error('formal task retry inspection does not own the exact Session binding');
  }
  const ownedGeneration = initialSnapshot.connection_generation;
  const probe = new FormalTaskControlLeaf({ enabled: true, binding: initialSnapshot.binding });
  const stillCurrent = () => (
    input.is_current()
    && input.leaf.snapshot().connected
    && input.leaf.snapshot().connection_generation === ownedGeneration
  );
  const statusResponse = await input.request(
    PRODUCT_P3_TASK_STATUS_METHOD,
    { session_id: input.session_id, task_id: taskId },
    { requestId: `web-task-status-${input.request_nonce}` },
  );
  if (!stillCurrent()) throw new Error('formal task retry inspection became stale');
  probe.adopt('task.status', statusResponse, {
    connection_generation: probe.snapshot().connection_generation,
    command_id: null,
    target_task_id: taskId,
    events_query: null,
  });
  const eventsResponse = await input.request(
    PRODUCT_P3_TASK_EVENTS_METHOD,
    { session_id: input.session_id, task_id: taskId, after_seq: -1 },
    { requestId: `web-task-events-${input.request_nonce}` },
  );
  if (!stillCurrent()) throw new Error('formal task retry inspection became stale');
  probe.adopt('task.events', eventsResponse, {
    connection_generation: probe.snapshot().connection_generation,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: taskId, after_seq: -1 },
  });
  const selected = probe.snapshot().tasks.find(task => task.task_id === taskId) ?? null;
  if (selected === null) throw new Error('formal task retry inspection returned no exact task');
  input.leaf.adopt('task.events', eventsResponse, {
    connection_generation: ownedGeneration,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: taskId, after_seq: -1 },
  });
  const adopted = input.leaf.snapshot().tasks.find(task => task.task_id === taskId) ?? null;
  if (
    adopted === null
    || adopted.attempt_id !== selected.attempt_id
    || adopted.attempt_number !== selected.attempt_number
    || adopted.state !== selected.state
    || adopted.outcome !== selected.outcome
    || adopted.event_head !== selected.event_head
  ) {
    throw new Error('formal task retry inspection lost its exact task revision');
  }
  return adopted;
}

export function resolveProductTaskCreateOrigin(
  instruction: string,
  activeSessionId: string | null,
  origin: ProductVoiceTaskOrigin | null
): Readonly<{ source: 'structured' } | { source: 'voice'; interaction_id: string; turn_id: string; commit_id: string }> {
  if (origin !== null && activeSessionId === origin.session_id && instruction === origin.instruction) {
    return Object.freeze({
      source: 'voice' as const,
      interaction_id: origin.interaction_id,
      turn_id: origin.turn_id,
      commit_id: origin.commit_id,
    });
  }
  return Object.freeze({ source: 'structured' as const });
}

// Gateway retains a unary AgentServer request for at most 600 seconds. The
// browser must not abandon a notification poll first and replay its exact ID
// while that downstream owner is still active.
export const PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS = 610_000;

export function productP2WebRequestOptions(method: string, requestId?: string): WebRequestOptions {
  return {
    ...(requestId === undefined ? {} : { requestId }),
    ...(method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD ? { timeoutMs: PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS } : {}),
  };
}

export function productTextBlockedByP1Status(status: ProductP1VoiceStatus): boolean {
  return ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(status);
}

export function confirmRecognizedSpeechExact(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.confirm === 'function' &&
    window.confirm('Confirm that the recognized speech shown on screen is exact before dispatch.')
  );
}

export type ProductP2NotificationDisposition =
  | { readonly kind: 'continue' }
  | { readonly kind: 'failed'; readonly reason: string }
  | {
      readonly kind: 'presentation';
      readonly text: string;
      readonly response_id: string;
      readonly response: Readonly<{
        interaction_id: string;
        response_id: string;
        response_generation: number;
      }>;
      readonly unit_id: string;
      readonly ack: ProductPresentationAckInput;
    };

function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function bindProductVoiceTaskOrigin(
  input: Readonly<ProductTurnInput>,
  result: unknown,
  sessionId: string,
  interactionId: string
): ProductVoiceTaskOrigin {
  const body = recordValue(result);
  const response = recordValue(body?.response);
  if (
    input.dispatch_target !== 'task' ||
    body?.status !== 'task_origin_accepted' ||
    body.turn_id !== input.turn_id ||
    body.commit_id !== input.commit_id ||
    response?.interaction_id !== interactionId ||
    typeof response.response_id !== 'string' ||
    !response.response_id.trim() ||
    !Number.isSafeInteger(response.response_generation) ||
    (response.response_generation as number) < 0
  ) {
    throw new Error('product voice Task origin response binding mismatch');
  }
  return Object.freeze({
    session_id: sessionId,
    interaction_id: interactionId,
    turn_id: input.turn_id,
    commit_id: input.commit_id,
    response_id: response.response_id,
    response_generation: response.response_generation as number,
    instruction: input.text,
  });
}

export function classifyProductP2Notification(notification: Readonly<Record<string, unknown>>, hasPresentedOutput = false): ProductP2NotificationDisposition {
  const event = recordValue(notification.agent_event);
  const unit = recordValue(notification.presentation_unit);
  const response = recordValue(notification.response);
  const errorReason =
    typeof notification.error_reason === 'string' ? notification.error_reason : typeof event?.error_reason === 'string' ? event.error_reason : null;
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
    typeof response?.interaction_id === 'string' &&
    typeof response?.response_id === 'string' &&
    Number.isSafeInteger(response.response_generation)
  ) {
    return {
      kind: 'presentation',
      text: event.text,
      response_id: response.response_id,
      response: {
        interaction_id: response.interaction_id,
        response_id: response.response_id,
        response_generation: response.response_generation as number,
      },
      unit_id: unit.unit_id,
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

export function retainBoundedPresentedProductResponse(responses: Map<string, true>, responseId: string, capacity = 128): void {
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

function createManifest(
  input: Readonly<LiveVoiceIntegratedRoutePanelProps>,
  correlationId: string,
  observedAt: string,
  formal: Readonly<{
    p1_available: boolean;
    p2_available: boolean;
    p3_available: boolean;
  }>
): IntegratedWebRouteManifest {
  const selection =
    input.routeSelection ??
    createCurrentIntegratedWebRouteSelection({
      p1_browser_speech_available: browserSpeechCompatibilityAvailable(),
      p2_text_chat_available: input.isConnected && input.agentRouteAvailable,
      p3_task_compatibility_enabled: FEATURE_LIVE_VOICE_TASK_DEMO,
      p3_task_compatibility_available: input.taskCompatibilityAvailable,
      p1_formal_enabled: FEATURE_LIVE_VOICE_INTEGRATED_P1,
      p1_formal_available: formal.p1_available,
      p2_formal_enabled: FEATURE_LIVE_VOICE_INTEGRATED_WEB,
      p2_formal_available: formal.p2_available,
      p3_formal_enabled: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION,
      p3_formal_available: formal.p3_available,
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
  const productRequest = props.request ?? defaultProductRequest;
  const reactId = useId();
  const fallbackCorrelationId = useMemo(() => `integrated-web-${reactId.replace(/[^A-Za-z0-9_-]/g, '') || 'route'}`, [reactId]);
  const pageInstanceIdRef = useRef<string | null>(null);
  if (pageInstanceIdRef.current === null) {
    pageInstanceIdRef.current = globalThis.crypto?.randomUUID?.() ?? `page-${reactId.replace(/[^A-Za-z0-9_-]/g, '') || 'route'}-${Date.now()}`;
  }
  const [p2JournalState, setP2JournalState] = useState<Readonly<{
    session_id: string;
    correlation_id: string;
    status: 'ready' | 'failed';
    reason: string | null;
  }> | null>(null);
  const correlationId = p2JournalState?.session_id === props.activeSessionId ? p2JournalState.correlation_id : fallbackCorrelationId;
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
  const [productTextStatus, setProductTextStatus] = useState<'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed'>('idle');
  const [p1VoiceStatus, setP1VoiceStatus] = useState<ProductP1VoiceStatus>(FEATURE_LIVE_VOICE_INTEGRATED_P1 ? 'idle' : 'closed');
  const [p1VoiceReason, setP1VoiceReason] = useState<string | null>(null);
  const [pendingPresentationAck, setPendingPresentationAck] = useState<ProductPresentationAckInput | null>(null);
  const [p3MutationOperation, setP3MutationOperation] = useState<'task.create' | 'task.cancel' | 'task.retry'>('task.create');
  const [p3TaskName, setP3TaskName] = useState('');
  const [p3TaskInstruction, setP3TaskInstruction] = useState('');
  const [p3TargetTaskId, setP3TargetTaskId] = useState('');
  const [p3MutationStatus, setP3MutationStatus] = useState<'idle' | 'issuing' | 'confirmed' | 'mutating' | 'accepted' | 'failed'>('idle');
  const [p3RetryInspectionStatus, setP3RetryInspectionStatus] = useState<'idle' | 'checking' | 'eligible' | 'ineligible' | 'failed'>('idle');
  const [p3RetryEligibility, setP3RetryEligibility] = useState<Readonly<FormalTaskControlRecord> | null>(null);
  const p3RetryInspectionGenerationRef = useRef(0);
  const p3RetryInspectionAbortRef = useRef<AbortController | null>(null);
  const [createdProgressTaskId, setCreatedProgressTaskId] = useState<string | null>(null);
  const monitorRef = useRef<WebPlatformDiagnosticsMonitor | null>(null);
  const progressRef = useRef<Readonly<ProductTextProgressEvent> | null>(null);
  const pendingOwnedProgressRef = useRef(new Map<string, Readonly<ProductTextProgressEvent>>());
  const progressConsumerRef = useRef<((event: Readonly<ProductTextProgressEvent>) => void) | null>(null);
  const progressAckOwnerRef = useRef<ProductTextProgressAckOwner | null>(null);
  const activationOwnerRef = useRef<ProductWebP2ActivationOwner | null>(null);
  const p2ActivationJournalRef = useRef<ProductP2ActivationJournal | null>(null);
  const p1VoiceOwnerRef = useRef<ProductP1VoiceRouteOwner | null>(null);
  const pendingP1VoiceStartRef = useRef<Promise<void> | null>(null);
  const pendingProductTurnRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductTurnInput;
  } | null>(null);
  const pendingPresentationAttemptRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductPresentationAckInput & { presented_at: string };
  } | null>(null);
  const pendingBargeInRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: {
      action_id: string;
      response_id: string;
      response_generation: number;
      cancel_response: boolean;
    };
  } | null>(null);
  const activeVoiceResponseRef = useRef<Readonly<{
    interaction_id: string;
    response_id: string;
    response_generation: number;
  }> | null>(null);
  const presentedProductResponsesRef = useRef(new Map<string, true>());
  const progressActivationOwnerRef = useRef<ProductWebP3ProgressOwner | null>(null);
  const p3MutationOwnerRef = useRef<ProductWebP3MutationOwner | null>(null);
  const pendingP3MutationRef = useRef<ProductWebP3MutationInput | null>(null);
  const voiceTaskOriginRef = useRef<ProductVoiceTaskOrigin | null>(null);
  const recognizedVoiceRef = useRef<ProductRecognizedVoice | null>(null);
  const formalTaskControlLeafRef = useRef<FormalTaskControlLeaf | null>(null);
  const pendingFormalP3MutationRef = useRef<PreparedFormalTaskMutation | null>(null);
  const activeSessionRef = useRef<string | null>(props.activeSessionId);
  const isConnectedRef = useRef(props.isConnected);
  const mountedRef = useRef(true);
  const progressOwnerEpochRef = useRef(0);
  const activationGenerationRef = useRef(0);
  const progressGenerationRef = useRef(0);
  const productTurnSequenceRef = useRef(0);
  const bargeInSequenceRef = useRef(0);
  const p3MutationSequenceRef = useRef(0);
  const cancelP3RetryInspection = () => {
    p3RetryInspectionGenerationRef.current += 1;
    p3RetryInspectionAbortRef.current?.abort();
    p3RetryInspectionAbortRef.current = null;
  };
  activeSessionRef.current = props.activeSessionId;
  isConnectedRef.current = props.isConnected;

  useEffect(() => {
    const sessionId = props.activeSessionId;
    p2ActivationJournalRef.current = null;
    if (!FEATURE_LIVE_VOICE_INTEGRATED_WEB || sessionId === null) {
      setP2JournalState(null);
      return;
    }
    try {
      const journal = ProductP2ActivationJournal.open({
        session_id: sessionId,
        client_instance_id: pageInstanceIdRef.current!,
      });
      const snapshot = journal.snapshot();
      p2ActivationJournalRef.current = journal;
      activationGenerationRef.current = snapshot.last_generation;
      setP2JournalState(
        Object.freeze({
          session_id: sessionId,
          correlation_id: snapshot.correlation_id,
          status: 'ready',
          reason: null,
        })
      );
    } catch {
      setP2JournalState(
        Object.freeze({
          session_id: sessionId,
          correlation_id: fallbackCorrelationId,
          status: 'failed',
          reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
        })
      );
      setP2Activation({
        status: 'unavailable',
        binding: null,
        reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
      });
    }
  }, [fallbackCorrelationId, props.activeSessionId]);

  const manifest = useMemo(
    () =>
      createManifest(props, correlationId, new Date().toISOString(), {
        p1_available: ['capturing', 'recognizing', 'recognized', 'playing'].includes(p1VoiceStatus),
        p2_available: p2Activation.status === 'active',
        p3_available: p3Activation.status === 'active' || ['confirmed', 'mutating', 'accepted'].includes(p3MutationStatus),
      }),
    [
      correlationId,
      p1VoiceStatus,
      p2Activation.status,
      p3Activation.status,
      p3MutationStatus,
      props.activeSessionId,
      props.agentRouteAvailable,
      props.isConnected,
      props.routeSelection,
      props.taskCompatibilityAvailable,
    ]
  );

  const adoptProductP2Notification = (owner: ProductWebP2ActivationOwner, notification: Readonly<Record<string, unknown>>) => {
    const response = recordValue(notification.response);
    const responseId = typeof response?.response_id === 'string' ? response.response_id : null;
    const disposition = classifyProductP2Notification(notification, responseId !== null && presentedProductResponsesRef.current.has(responseId));
    if (disposition.kind === 'failed') {
      setProductTextStatus('failed');
      return;
    }
    if (disposition.kind !== 'presentation') return;
    const pending = pendingPresentationAttemptRef.current;
    if (pending !== null && (pending.owner !== owner || pending.input.response_id !== disposition.response_id)) {
      throw new Error('a previous presentation ACK is still unresolved');
    }
    retainBoundedPresentedProductResponse(presentedProductResponsesRef.current, disposition.response_id);
    setProductOutput(disposition.text);
    setProductTextStatus('presented');
    setPendingPresentationAck(disposition.ack);
    activeVoiceResponseRef.current = disposition.response;
    const voiceOwner = p1VoiceOwnerRef.current;
    if (voiceOwner !== null) {
      void voiceOwner
        .playAgentText({
          response: disposition.response,
          unit_id: disposition.unit_id,
          text: disposition.text,
        })
        .catch(() => undefined);
    }
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

  const p2JournalBinding = (
    owner: ProductWebP2ActivationOwner
  ): Readonly<{
    journal: ProductP2ActivationJournal;
    binding: NonNullable<ProductWebP2ActivationSnapshot['binding']>;
  }> | null => {
    const journal = p2ActivationJournalRef.current;
    const binding = owner.snapshot().binding;
    if (journal === null || binding === null) return null;
    const snapshot = journal.snapshot();
    if (
      snapshot.session_id !== binding.session_id ||
      snapshot.correlation_id !== binding.correlation_id ||
      snapshot.interaction_id !== binding.interaction_id ||
      snapshot.binding === null ||
      snapshot.binding.activation_id !== binding.activation_id ||
      snapshot.binding.activation_generation !== binding.activation_generation
    )
      return null;
    return Object.freeze({ journal, binding });
  };

  const markP2OperationUnknown = (owner: ProductWebP2ActivationOwner): boolean => {
    const owned = p2JournalBinding(owner);
    if (owned === null) return false;
    try {
      owned.journal.markResultUnknown(owned.binding);
      return true;
    } catch {
      return false;
    }
  };

  const markP2OperationSettled = (owner: ProductWebP2ActivationOwner): boolean => {
    if (owner.hasPendingSubmission() || owner.hasPendingPresentationAck() || owner.hasPendingBargeIn()) return false;
    const owned = p2JournalBinding(owner);
    if (owned === null) return false;
    try {
      owned.journal.markActive(owned.binding);
      return true;
    } catch {
      return false;
    }
  };

  const settleRetainedP2Operations = async (owner: ProductWebP2ActivationOwner) => {
    const ownerSession = owner.snapshot().binding?.session_id;
    const isCurrent = () => activationOwnerRef.current === owner && ownerSession !== undefined && activeSessionRef.current === ownerSession;
    const pendingTurn = pendingProductTurnRef.current;
    if (pendingTurn?.owner === owner) {
      try {
        const result = await retryRetainedProductOperation({
          operation: () => owner.submitText(pendingTurn.input),
          is_current: isCurrent,
        });
        if (pendingProductTurnRef.current === pendingTurn) {
          if (pendingTurn.input.dispatch_target === 'task' && ownerSession) {
            const interactionId = owner.snapshot().binding?.interaction_id;
            if (!interactionId) throw new Error('recovered voice Task origin lost its interaction');
            voiceTaskOriginRef.current = bindProductVoiceTaskOrigin(
              pendingTurn.input,
              result,
              ownerSession,
              interactionId
            );
          }
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
    const pendingBargeIn = pendingBargeInRef.current;
    if (pendingBargeIn?.owner === owner) {
      try {
        await retryRetainedProductOperation({
          operation: () => owner.bargeIn(pendingBargeIn.input),
          is_current: isCurrent,
        });
        if (pendingBargeInRef.current === pendingBargeIn) {
          pendingBargeInRef.current = null;
        }
      } catch (error) {
        if (owner.hasPendingBargeIn()) throw error;
        if (pendingBargeInRef.current === pendingBargeIn) {
          pendingBargeInRef.current = null;
        }
      }
    }
    if (!owner.hasPendingSubmission() && !owner.hasPendingPresentationAck() && !owner.hasPendingBargeIn()) {
      markP2OperationSettled(owner);
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
      request: (method, params) => productRequest(method, { ...params }),
      on_snapshot: snapshot => {
        if (activeSessionRef.current === ownedSessionId && progressAckOwnerRef.current === owner && progressRef.current?.delivery_id === snapshot.delivery_id) {
          setProgressAck(snapshot.status);
        }
      },
    });
    owner.setConnected(props.isConnected);
    progressAckOwnerRef.current = owner;
    const consume = (parsed: Readonly<ProductTextProgressEvent>) => {
      if (activeSessionRef.current !== ownedSessionId || parsed.session_id !== ownedSessionId || progressAckOwnerRef.current !== owner) {
        return;
      }
      const adopted = adoptProductTextProgressEvent(progressRef.current, parsed, ownedSessionId);
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
      if (activeSessionRef.current !== ownedSessionId || parsed.session_id !== ownedSessionId || progressAckOwnerRef.current !== owner) {
        return;
      }
      const activation = progressActivationOwnerRef.current?.snapshot();
      if (!activation?.binding || !progressMatchesOwnedBinding(parsed, activation.binding, ownedSessionId)) {
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
    if (props.isConnected) return;
    const voiceOwner = p1VoiceOwnerRef.current;
    if (voiceOwner === null) return;
    void voiceOwner
      .close()
      .then(() => {
        if (p1VoiceOwnerRef.current === voiceOwner) {
          p1VoiceOwnerRef.current = null;
        }
      })
      .catch(() => {
        // The owner remains retained with cleanup_pending truth for retry on
        // session teardown or the next explicit start attempt.
      });
  }, [props.isConnected]);

  useEffect(() => {
    const voiceOwner = p1VoiceOwnerRef.current;
    if (voiceOwner !== null) {
      void voiceOwner
        .close()
        .then(() => {
          if (p1VoiceOwnerRef.current === voiceOwner) {
            p1VoiceOwnerRef.current = null;
          }
        })
        .catch(() => {
          // Retain cleanup_pending ownership. A successor Session cannot replace
          // it until the next explicit start retries the exact close.
        });
    }
    setP1VoiceStatus(FEATURE_LIVE_VOICE_INTEGRATED_P1 ? 'idle' : 'closed');
    setP1VoiceReason(null);
    pendingProductTurnRef.current = null;
    pendingPresentationAttemptRef.current = null;
    pendingBargeInRef.current = null;
    presentedProductResponsesRef.current.clear();
    setPendingPresentationAck(null);
    setProductOutput(null);
    setProductTextStatus('idle');
  }, [props.activeSessionId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cancelP3RetryInspection();
      const voiceOwner = p1VoiceOwnerRef.current;
      if (voiceOwner !== null) {
        // Local microphone/playout closes before remote authority revocation.
        // Retry the retained remote close without constructing a successor.
        void (async () => {
          for (let attempt = 0; attempt < 3; attempt += 1) {
            try {
              await voiceOwner.close();
              return;
            } catch {
              // Bounded teardown retry; the page owns no successor route.
            }
          }
        })();
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let recoveryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
    const scheduleRecovery = () => {
      if (cancelled || recoveryTimer !== null) return;
      recoveryTimer = globalThis.setTimeout(() => setP2RecoveryEpoch(epoch => epoch + 1), 1000);
    };
    const ownedSessionId = props.activeSessionId;
    const run = async () => {
      const journal = p2ActivationJournalRef.current;
      const journalReady = Boolean(
        journal &&
        ownedSessionId &&
        p2JournalState?.session_id === ownedSessionId &&
        p2JournalState.status === 'ready' &&
        journal.snapshot().correlation_id === correlationId
      );
      const routeEligible = Boolean(FEATURE_LIVE_VOICE_INTEGRATED_WEB && ownedSessionId && props.agentRouteAvailable && journalReady);
      const isCurrentRun = () =>
        Boolean(
          !cancelled &&
          ownedSessionId &&
          activeSessionRef.current === ownedSessionId &&
          p2ActivationJournalRef.current === journal &&
          props.agentRouteAvailable &&
          props.isConnected
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
          let operationsSettled = false;
          try {
            await settleRetainedP2Operations(previous);
            operationsSettled = true;
            if (snapshot.binding && journalReady) {
              journal!.markClosing(snapshot.binding);
            }
            await previous.closeWithRetry();
            if (snapshot.binding && journalReady) {
              journal!.markClosed(snapshot.binding);
            }
          } catch {
            if (!operationsSettled && snapshot.binding && journalReady) {
              try {
                journal!.markResultUnknown(snapshot.binding);
              } catch {
                // The route remains fail-closed when its checkpoint is unavailable.
              }
            }
            if (operationsSettled && activationOwnerRef.current === previous) {
              activationOwnerRef.current = null;
            }
            scheduleRecovery();
            return;
          }
          if (activationOwnerRef.current === previous) {
            activationOwnerRef.current = null;
          }
        }
        if (routeEligible && sameSession && snapshot.status === 'activating' && snapshot.binding) {
          try {
            const settled = await previous.start(snapshot.binding);
            if (!cancelled && activationOwnerRef.current === previous) {
              if (journalReady && settled.status === 'active') {
                journal!.markActive(snapshot.binding);
              }
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
            if (snapshot.binding && journalReady) {
              journal!.markClosing(snapshot.binding);
            }
            await previous.closeWithRetry({
              on_retry: snapshot => {
                if (!cancelled && activationOwnerRef.current === previous) {
                  setP2Activation(snapshot);
                }
              },
            });
            if (snapshot.binding && journalReady) {
              journal!.markClosed(snapshot.binding);
            }
          } catch {
            if (journalReady && journal!.snapshot().phase !== 'result_unknown' && activationOwnerRef.current === previous) {
              activationOwnerRef.current = null;
            }
            scheduleRecovery();
            return;
          }
        }
        if (activationOwnerRef.current === previous) activationOwnerRef.current = null;
      }
      if (cancelled || !routeEligible || !props.isConnected || !ownedSessionId || !journal) {
        if (!cancelled) {
          setP2Activation({
            status: p2JournalState?.status === 'failed' ? 'unavailable' : FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
            binding: null,
            reason: p2JournalState?.reason ?? null,
          });
        }
        return;
      }
      setP2Activation({
        status: 'activating',
        binding: null,
        reason: 'P2_REFRESH_RECONCILING',
      });
      const recovery = {
        owner: null as ProductWebP2ActivationOwner | null,
      };
      const recovered = await reconcileProductP2Predecessor({
        journal,
        activate_exact: async binding => {
          recovery.owner = new ProductWebP2ActivationOwner({
            enabled: true,
            request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
          });
          await recovery.owner.start(binding);
          const replayed = recovery.owner.activationWasReplayed();
          if (replayed === null) {
            throw new Error('product P2 activation replay truth is unavailable');
          }
          return Object.freeze({ replayed });
        },
        close_exact: async () => {
          if (recovery.owner === null) {
            throw new Error('product P2 recovery owner is unavailable');
          }
          await recovery.owner.closeWithRetry();
        },
        error_reason: extractWebErrorReason,
        activation_retryable: error => requiresProductActivationCleanup(error) || isRetriableProductOperationError(error),
        is_current: isCurrentRun,
      });
      if (!isCurrentRun()) {
        const staleOwner = recovery.owner;
        const staleBinding = staleOwner?.snapshot().binding ?? null;
        if (staleOwner?.needsCleanup()) {
          void (async () => {
            if (staleBinding) {
              try {
                journal.markClosing(staleBinding);
              } catch {
                // A newer exact journal owner may already have advanced.
              }
            }
            try {
              await staleOwner.closeWithRetry();
              if (staleBinding) {
                try {
                  journal.markClosed(staleBinding);
                } catch {
                  // A newer exact journal owner may already have advanced.
                }
              }
            } catch {
              // The stale run never allocates a successor.
            }
          })();
        }
        return;
      }
      if (recovered.kind !== 'ready') {
        const unresolvedOwner = recovery.owner;
        const unresolvedBinding = unresolvedOwner?.snapshot().binding ?? null;
        if (unresolvedOwner?.needsCleanup() && unresolvedBinding) {
          try {
            journal.markClosing(unresolvedBinding);
          } catch {
            // Exact cleanup still runs; journal ownership is re-read below.
          }
          try {
            await unresolvedOwner.closeWithRetry();
            try {
              journal.markClosed(unresolvedBinding);
            } catch {
              // A concurrent journal owner remains authoritative.
            }
            recovery.owner = null;
            if (isCurrentRun()) setP2RecoveryEpoch(epoch => epoch + 1);
            return;
          } catch {
            if (isCurrentRun()) {
              activationOwnerRef.current = unresolvedOwner;
              setP2Activation({
                status: 'unavailable',
                binding: null,
                reason: recovered.reason,
              });
              scheduleRecovery();
            }
            return;
          }
        }
        recovery.owner = null;
        if (!cancelled) {
          setP2Activation({
            status: 'unavailable',
            binding: null,
            reason: recovered.reason,
          });
        }
        if (recovered.kind === 'retry') scheduleRecovery();
        return;
      }
      recovery.owner = null;
      if (!isCurrentRun()) return;
      let binding: NonNullable<ProductWebP2ActivationSnapshot['binding']>;
      try {
        binding = journal.prepareSuccessor(pageInstanceIdRef.current!);
      } catch {
        if (isCurrentRun()) {
          setP2Activation({
            status: 'unavailable',
            binding: null,
            reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
          });
        }
        return;
      }
      activationGenerationRef.current = binding.activation_generation;
      let owner: ProductWebP2ActivationOwner | null = null;
      owner = new ProductWebP2ActivationOwner({
        enabled: true,
        request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
        on_snapshot: snapshot => {
          if (!cancelled && activeSessionRef.current === ownedSessionId && activationOwnerRef.current === owner && snapshot.status !== 'active') {
            setP2Activation(snapshot);
          }
        },
      });
      activationOwnerRef.current = owner;
      try {
        const activated = await owner.start(binding);
        if (!isCurrentRun() || activationOwnerRef.current !== owner) {
          try {
            journal.markClosing(binding);
          } catch {
            // Continue exact cleanup when the stale journal was superseded.
          }
          try {
            await owner.closeWithRetry();
            try {
              journal.markClosed(binding);
            } catch {
              // A current run may already own the journal.
            }
          } catch {
            // A stale run is never allowed to allocate another successor.
          }
          return;
        }
        journal.markActive(binding);
        if (!cancelled && activationOwnerRef.current === owner) {
          setP2Activation(activated);
        }
      } catch (error) {
        if (owner.snapshot().status === 'active') {
          try {
            journal.markClosing(binding);
          } catch {
            // Continue exact cleanup even if the browser checkpoint failed.
          }
          try {
            await owner.closeWithRetry();
          } catch {
            // The exact owner remains retained and P1 stays unavailable.
          }
          if (!cancelled) {
            setP2Activation({
              status: 'unavailable',
              binding: null,
              reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
            });
          }
          return;
        }
        // An activation response may have been lost after the route opened.
        // Reconcile the exact binding now; a later effect will retry the same
        // retained owner if the bounded cleanup remains pending.
        const cleanupRequired = requiresProductActivationCleanup(error);
        if (!cleanupRequired && isRetriableProductOperationError(error)) {
          // The request may have reached the registry. Keep the write-ahead
          // activating checkpoint and replay this exact binding next epoch.
          if (!cancelled && activationOwnerRef.current === owner) {
            scheduleRecovery();
          }
        } else if (cleanupRequired) {
          try {
            journal.markClosing(binding);
            await owner.closeWithRetry();
            journal.markClosed(binding);
            if (!cancelled && activationOwnerRef.current === owner) {
              activationOwnerRef.current = null;
              setP2RecoveryEpoch(epoch => epoch + 1);
            }
          } catch {
            // Keep the exact cleanup owner and schedule another bounded pass.
            if (!cancelled && activationOwnerRef.current === owner) {
              activationOwnerRef.current = null;
              scheduleRecovery();
            }
          }
        } else {
          const reason = extractWebErrorReason(error);
          try {
            if (reason === 'ACTIVATION_BINDING_CONFLICT' || reason === 'ACTIVATION_BINDING_MISMATCH' || reason === 'ACTIVATION_GENERATION_STALE') {
              journal.markResultUnknown(binding);
            } else {
              journal.markClosed(binding);
            }
          } catch {
            // The route remains fail-closed when its checkpoint is unavailable.
          }
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
      if (recoveryTimer !== null) globalThis.clearTimeout(recoveryTimer);
    };
  }, [correlationId, p2JournalState, p2RecoveryEpoch, props.activeSessionId, props.agentRouteAvailable, props.isConnected]);

  useEffect(() => {
    const journal = p2ActivationJournalRef.current;
    return () => {
      const closing = activationOwnerRef.current;
      if (!closing) return;
      if (!closing.needsCleanup()) {
        if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
        return;
      }
      const binding = closing.snapshot().binding;
      const resultUnknown = Boolean(
        journal?.snapshot().phase === 'result_unknown' ||
        pendingProductTurnRef.current?.owner === closing ||
        pendingPresentationAttemptRef.current?.owner === closing ||
        pendingBargeInRef.current?.owner === closing ||
        closing.hasPendingSubmission() ||
        closing.hasPendingPresentationAck() ||
        closing.hasPendingBargeIn()
      );
      if (binding && journal) {
        try {
          if (resultUnknown) journal.markResultUnknown(binding);
          else journal.markClosing(binding);
        } catch {
          // Cleanup still runs, but no successor may rely on a missing journal write.
        }
      }
      void closing
        .closeWithRetry()
        .then(() => {
          if (binding && journal && !resultUnknown) {
            try {
              journal.markClosed(binding);
            } catch {
              // The next page remains fail-closed if the journal cannot settle.
            }
          }
          if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
        })
        .catch(() => undefined);
    };
  }, [correlationId, p2JournalState, props.activeSessionId, props.agentRouteAvailable]);

  useEffect(() => {
    const owner = activationOwnerRef.current;
    const binding = p2Activation.binding;
    const journal = p2ActivationJournalRef.current;
    if (!props.isConnected || p2Activation.status !== 'active' || !binding || !owner || !journal || pendingPresentationAck !== null) return;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled && activationOwnerRef.current === owner) {
        try {
          const outcome = await pollProductP2RouteWithRecovery({
            owner,
            is_current: () => !cancelled && activationOwnerRef.current === owner && activeSessionRef.current === binding.session_id,
            settle_retained_operations: async () => {
              await settleRetainedP2Operations(owner);
              journal.markClosing(binding);
            },
            can_activate_successor: () =>
              !cancelled &&
              activationOwnerRef.current === owner &&
              activeSessionRef.current === binding.session_id &&
              p2ActivationJournalRef.current === journal &&
              props.isConnected,
            activate_successor: async () => {
              if (
                cancelled ||
                activationOwnerRef.current !== owner ||
                activeSessionRef.current !== binding.session_id ||
                p2ActivationJournalRef.current !== journal ||
                !props.isConnected
              ) {
                throw new Error(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED);
              }
              if (activationOwnerRef.current === owner) {
                activationOwnerRef.current = null;
              }
              journal.markClosed(binding);
              const successorBinding = journal.prepareSuccessor(pageInstanceIdRef.current!);
              activationGenerationRef.current = successorBinding.activation_generation;
              let successor: ProductWebP2ActivationOwner | null = null;
              successor = new ProductWebP2ActivationOwner({
                enabled: true,
                request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
                on_snapshot: snapshot => {
                  if (activeSessionRef.current === binding.session_id && activationOwnerRef.current === successor && snapshot.status !== 'active') {
                    setP2Activation(snapshot);
                  }
                },
              });
              activationOwnerRef.current = successor;
              const successorSnapshot = await successor.start(successorBinding);
              journal.markActive(successorBinding);
              if (activeSessionRef.current === binding.session_id && activationOwnerRef.current === successor) {
                setP2Activation(successorSnapshot);
              }
              return successor;
            },
          });
          if (outcome.kind === 'recovered') return;
          if (cancelled || activationOwnerRef.current !== owner) return;
          adoptProductP2Notification(owner, outcome.notification);
          if (pendingPresentationAttemptRef.current?.owner === owner) return;
        } catch {
          const retained = activationOwnerRef.current;
          if (
            !cancelled &&
            retained?.needsCleanup() &&
            journal.snapshot().phase !== 'result_unknown' &&
            !retained.hasPendingSubmission() &&
            !retained.hasPendingPresentationAck() &&
            !retained.hasPendingBargeIn()
          ) {
            if (activationOwnerRef.current === retained) {
              activationOwnerRef.current = null;
            }
          }
          if (!cancelled && retained?.needsCleanup()) {
            setP2RecoveryEpoch(epoch => epoch + 1);
          }
          if (!cancelled) {
            setProductTextStatus('failed');
            setP2Activation({
              status: 'unavailable',
              binding: null,
              reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
            });
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
    if (!markP2OperationUnknown(owner)) {
      setProductTextStatus('failed');
      return;
    }
    let cancelled = false;
    void retryRetainedProductOperation({
      operation: () => owner.acknowledgePresentation(retained.input),
      is_current: () => !cancelled && activationOwnerRef.current === owner && activeSessionRef.current === p2Activation.binding?.session_id,
    })
      .then(() => {
        if (!cancelled && activationOwnerRef.current === owner && pendingPresentationAttemptRef.current === retained) {
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          setProductTextStatus('acknowledged');
          markP2OperationSettled(owner);
        }
      })
      .catch(() => {
        if (!cancelled && activationOwnerRef.current === owner) {
          if (!owner.hasPendingPresentationAck()) markP2OperationSettled(owner);
          setProductTextStatus('failed');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [pendingPresentationAck, productOutput, props.isConnected]);

  useEffect(() => {
    cancelP3RetryInspection();
    pendingP3MutationRef.current = null;
    voiceTaskOriginRef.current = null;
    recognizedVoiceRef.current = null;
    activeVoiceResponseRef.current = null;
    pendingFormalP3MutationRef.current = null;
    formalTaskControlLeafRef.current?.disconnect();
    formalTaskControlLeafRef.current = null;
    setP3MutationOperation('task.create');
    setP3TargetTaskId('');
    setP3MutationStatus('idle');
    setP3RetryInspectionStatus('idle');
    setP3RetryEligibility(null);
    setCreatedProgressTaskId(null);
    if (!FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION || !props.activeSessionId) {
      p3MutationOwnerRef.current = null;
      return;
    }
    const owner = new ProductWebP3MutationOwner({
      enabled: true,
      request: (method, params, requestId) => productRequest(method, params, { requestId }),
    });
    p3MutationOwnerRef.current = owner;
    return () => {
      cancelP3RetryInspection();
      formalTaskControlLeafRef.current?.disconnect();
      if (p3MutationOwnerRef.current === owner) p3MutationOwnerRef.current = null;
    };
  }, [props.activeSessionId]);

  useEffect(() => {
    if (!props.isConnected) {
      cancelP3RetryInspection();
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('idle');
      formalTaskControlLeafRef.current?.disconnect();
      return;
    }
    const leaf = formalTaskControlLeafRef.current;
    if (leaf !== null && !leaf.snapshot().connected) {
      leaf.reconnect(leaf.snapshot().binding);
    }
  }, [props.isConnected]);

  const submitProductText = async (overrideText?: string, source: 'structured' | 'voice' = 'structured'): Promise<ProductTurnInput | null> => {
    const owner = activationOwnerRef.current;
    const turnText = overrideText ?? productInput;
    if (!owner || p2Activation.status !== 'active' || !turnText.trim()) return null;
    const liveP1Status = p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus;
    if (productTextBlockedByP1Status(liveP1Status)) return null;
    if (source === 'structured') voiceTaskOriginRef.current = null;
    const recognized = recognizedVoiceRef.current;
    if (source === 'voice' && (recognized === null || recognized.session_id !== props.activeSessionId || recognized.text !== turnText)) return null;
    let retained = pendingProductTurnRef.current;
    if (retained !== null && retained.owner !== owner) {
      setProductTextStatus('failed');
      return null;
    }
    if (retained === null) {
      if (
        pendingPresentationAck !== null ||
        pendingPresentationAttemptRef.current !== null ||
        pendingBargeInRef.current !== null ||
        owner.hasPendingSubmission() ||
        owner.hasPendingPresentationAck() ||
        owner.hasPendingBargeIn()
      ) {
        setProductTextStatus('failed');
        return null;
      }
      if (source === 'voice' && !confirmRecognizedSpeechExact()) return null;
      productTurnSequenceRef.current += 1;
      const identity = `${Date.now()}-${productTurnSequenceRef.current}`;
      retained = {
        owner,
        input: {
          commit_id: `web-commit-${identity}`,
          turn_id: `web-turn-${identity}`,
          response_id: `web-response-${identity}`,
          committed_at: new Date().toISOString(),
          text: turnText,
          dispatch_target: 'agent',
          ...(source === 'voice'
            ? {
                voice_commit_receipt: recognized!.voice_commit_receipt,
                critical_confirmation: true as const,
              }
            : {}),
        },
      };
      pendingProductTurnRef.current = retained;
      setProductOutput(null);
    }
    setProductTextStatus('submitting');
    if (!markP2OperationUnknown(owner)) {
      setProductTextStatus('failed');
      return null;
    }
    try {
      await retryRetainedProductOperation({
        operation: () => owner.submitText(retained.input),
        is_current: () => props.isConnected && activationOwnerRef.current === owner && activeSessionRef.current === p2Activation.binding?.session_id,
      });
      if (activationOwnerRef.current === owner && pendingProductTurnRef.current === retained) {
        pendingProductTurnRef.current = null;
        markP2OperationSettled(owner);
        setProductInput('');
        setProductTextStatus('waiting');
        if (source === 'voice' && recognizedVoiceRef.current === recognized) {
          recognizedVoiceRef.current = null;
        }
        return retained.input;
      }
      return null;
    } catch {
      if (activationOwnerRef.current === owner) {
        if (!owner.hasPendingSubmission()) {
          pendingProductTurnRef.current = null;
          markP2OperationSettled(owner);
        }
        setProductTextStatus('failed');
      }
      return null;
    }
  };

  const startProductVoiceCaptureOwned = async () => {
    const binding = p2Activation.binding;
    const isCurrentBinding = () => {
      const activation = activationOwnerRef.current?.snapshot();
      const current = activation?.binding;
      return (
        mountedRef.current &&
        isConnectedRef.current &&
        activeSessionRef.current === binding?.session_id &&
        activation?.status === 'active' &&
        current != null &&
        binding !== null &&
        current.session_id === binding.session_id &&
        current.correlation_id === binding.correlation_id &&
        current.interaction_id === binding.interaction_id &&
        current.activation_id === binding.activation_id &&
        current.activation_generation === binding.activation_generation
      );
    };
    if (
      !FEATURE_LIVE_VOICE_INTEGRATED_P1 ||
      !isCurrentBinding() ||
      p2Activation.status !== 'active' ||
      binding === null ||
      typeof window === 'undefined' ||
      pendingProductTurnRef.current !== null ||
      pendingPresentationAttemptRef.current !== null ||
      pendingBargeInRef.current !== null ||
      activationOwnerRef.current?.hasPendingSubmission() ||
      activationOwnerRef.current?.hasPendingPresentationAck() ||
      activationOwnerRef.current?.hasPendingBargeIn()
    )
      return;
    let owner = p1VoiceOwnerRef.current;
    if (owner && ['failed', 'cleanup_pending'].includes(owner.status().status)) {
      await owner.close();
      if (p1VoiceOwnerRef.current === owner) p1VoiceOwnerRef.current = null;
      owner = null;
    }
    if (!isCurrentBinding()) return;
    if (owner === null || owner.status().status === 'closed') {
      owner = new ProductP1VoiceRouteOwner({
        enabled: true,
        expected_origin: window.location.origin,
        request: (method, params) => productRequest(method, params),
        on_status: (status, reason) => {
          if (p1VoiceOwnerRef.current === owner) {
            setP1VoiceStatus(status);
            setP1VoiceReason(reason);
          }
        },
      });
      p1VoiceOwnerRef.current = owner;
    }
    try {
      await owner.startCapture({
        session_id: binding.session_id,
        interaction_id: binding.interaction_id,
        correlation_id: binding.correlation_id,
        activation_id: binding.activation_id,
        activation_generation: binding.activation_generation,
        locale: 'zh-CN',
      });
    } catch {
      // The owner publishes a content-free reason and retains cleanup.
    }
  };

  const startProductVoiceCapture = (): Promise<void> => {
    const pending = pendingP1VoiceStartRef.current;
    if (pending !== null) return pending;
    const retained = startProductVoiceCaptureOwned().finally(() => {
      if (pendingP1VoiceStartRef.current === retained) pendingP1VoiceStartRef.current = null;
    });
    pendingP1VoiceStartRef.current = retained;
    return retained;
  };

  const stopProductVoiceCapture = async () => {
    const owner = p1VoiceOwnerRef.current;
    if (owner === null || owner.status().status !== 'capturing') return;
    try {
      const recognition = await owner.stopAndRecognize();
      if (props.activeSessionId !== null) {
        recognizedVoiceRef.current = Object.freeze({
          session_id: props.activeSessionId,
          text: recognition.text,
          voice_commit_receipt: recognition.voice_commit_receipt,
        });
        voiceTaskOriginRef.current = null;
        setProductInput(recognition.text);
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3MutationOperation('task.create');
        setP3TaskName('Voice task');
        setP3TaskInstruction(recognition.text);
      }
    } catch {
      // The owner publishes a content-free reason and retains cleanup.
    }
  };

  const stopProductVoicePlayout = async () => {
    const p2Owner = activationOwnerRef.current;
    const p1Owner = p1VoiceOwnerRef.current;
    const response = activeVoiceResponseRef.current;
    if (p2Owner === null || p1Owner === null || response === null || p1Owner.status().status !== 'playing') return;
    bargeInSequenceRef.current += 1;
    const actionId = `product-barge-${bargeInSequenceRef.current}`;
    const locallyStopped = p1Owner.stopAgentPlayout(response);
    if (!locallyStopped) return;
    activeVoiceResponseRef.current = null;
    if (!markP2OperationUnknown(p2Owner)) {
      setProductTextStatus('failed');
      return;
    }
    let retained = pendingBargeInRef.current;
    if (retained !== null && retained.owner !== p2Owner) {
      setProductTextStatus('failed');
      return;
    }
    if (retained === null) {
      retained = {
        owner: p2Owner,
        input: {
          action_id: actionId,
          response_id: response.response_id,
          response_generation: response.response_generation,
          cancel_response: true,
        },
      };
      pendingBargeInRef.current = retained;
    }
    try {
      await p2Owner.bargeIn(retained.input);
      if (pendingBargeInRef.current === retained) {
        pendingBargeInRef.current = null;
      }
      markP2OperationSettled(p2Owner);
    } catch {
      if (!p2Owner.hasPendingBargeIn() && pendingBargeInRef.current === retained) {
        pendingBargeInRef.current = null;
        markP2OperationSettled(p2Owner);
      }
      setProductTextStatus('failed');
    }
  };

  const commitRecognizedVoiceTaskOrigin = async (): Promise<ProductVoiceTaskOrigin | null> => {
    const owner = activationOwnerRef.current;
    const recognized = recognizedVoiceRef.current;
    if (
      owner === null ||
      recognized === null ||
      props.activeSessionId === null ||
      recognized.session_id !== props.activeSessionId ||
      recognized.text !== p3TaskInstruction ||
      p2Activation.status !== 'active' ||
      p2Activation.binding === null ||
      pendingProductTurnRef.current !== null ||
      pendingBargeInRef.current !== null ||
      owner.hasPendingSubmission() ||
      owner.hasPendingPresentationAck() ||
      owner.hasPendingBargeIn()
    )
      return null;
    if (!confirmRecognizedSpeechExact()) return null;
    const activationBinding = p2Activation.binding;
    productTurnSequenceRef.current += 1;
    const identity = `${Date.now()}-${productTurnSequenceRef.current}`;
    const input: ProductTurnInput = {
      commit_id: `web-commit-${identity}`,
      turn_id: `web-turn-${identity}`,
      committed_at: new Date().toISOString(),
      text: recognized.text,
      dispatch_target: 'task',
      voice_commit_receipt: recognized.voice_commit_receipt,
      critical_confirmation: true,
    };
    const retained = { owner, input };
    pendingProductTurnRef.current = retained;
    if (!markP2OperationUnknown(owner)) {
      pendingProductTurnRef.current = null;
      return null;
    }
    try {
      const result = await retryRetainedProductOperation({
        operation: () => owner.submitText(input),
        is_current: () => props.isConnected && activationOwnerRef.current === owner && activeSessionRef.current === recognized.session_id,
      });
      if (pendingProductTurnRef.current !== retained) return null;
      pendingProductTurnRef.current = null;
      markP2OperationSettled(owner);
      const origin = bindProductVoiceTaskOrigin(
        input,
        result,
        recognized.session_id,
        activationBinding.interaction_id
      );
      voiceTaskOriginRef.current = origin;
      recognizedVoiceRef.current = null;
      return origin;
    } catch {
      if (activationOwnerRef.current === owner && !owner.hasPendingSubmission()) {
        pendingProductTurnRef.current = null;
        markP2OperationSettled(owner);
      }
      return null;
    }
  };

  const inspectP3RetryEligibility = async (input: Readonly<{
    task_id?: string;
    follow_nonterminal?: boolean;
  }> = {}): Promise<Readonly<FormalTaskControlRecord> | null> => {
    const sessionId = props.activeSessionId;
    const taskId = (input.task_id ?? p3TargetTaskId).trim();
    const leaf = formalTaskControlLeafRef.current;
    if (!sessionId || !taskId || !leaf || p3MutationOwnerRef.current?.hasPendingMutation()) {
      cancelP3RetryInspection();
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('ineligible');
      return null;
    }
    cancelP3RetryInspection();
    const inspectionGeneration = p3RetryInspectionGenerationRef.current;
    const abortController = new AbortController();
    p3RetryInspectionAbortRef.current = abortController;
    const waitForRetry = props.p3RetryInspectionWait ?? defaultP3RetryInspectionWait;
    const isCurrent = () => (
      !abortController.signal.aborted
      && mountedRef.current
      && formalTaskControlLeafRef.current === leaf
      && activeSessionRef.current === sessionId
      && p3RetryInspectionGenerationRef.current === inspectionGeneration
      && p3RetryInspectionAbortRef.current === abortController
    );
    setP3RetryEligibility(null);
    setP3RetryInspectionStatus('checking');
    try {
      for (let attempt = 0; ; attempt += 1) {
        const selected = await inspectProductP3RetryCandidate({
          request: productRequest,
          leaf,
          session_id: sessionId,
          task_id: taskId,
          request_nonce: `${Date.now()}-${inspectionGeneration}-${attempt}`,
          is_current: isCurrent,
        });
        if (!isCurrent()) return null;
        if (isFormalTaskRetryEligible(selected)) {
          setP3RetryEligibility(selected);
          setP3RetryInspectionStatus('eligible');
          setP3MutationOperation('task.retry');
          return selected;
        }
        if (
          selected.state === 'terminal'
          || input.follow_nonterminal !== true
          || attempt >= PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS.length
        ) {
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('ineligible');
          return null;
        }
        await waitForRetry(PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS[attempt]!, abortController.signal);
        if (!isCurrent()) return null;
      }
    } catch {
      if (isCurrent()) {
        setP3RetryEligibility(null);
        setP3RetryInspectionStatus('failed');
      }
      return null;
    } finally {
      if (p3RetryInspectionAbortRef.current === abortController) {
        p3RetryInspectionAbortRef.current = null;
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
      correlation_id: correlationId,
    };
    if (p3MutationOperation === 'task.cancel' || p3MutationOperation === 'task.retry') {
      if (!p3TargetTaskId.trim()) return null;
      if (
        p3MutationOperation === 'task.retry'
        && (
          p3RetryEligibility?.task_id !== p3TargetTaskId.trim()
          || !isFormalTaskRetryEligible(p3RetryEligibility)
        )
      ) return null;
      return p3MutationOperation === 'task.cancel'
        ? {
            operation: 'task.cancel',
            ...common,
            source: 'structured',
            task_id: p3TargetTaskId,
          }
        : {
            operation: 'task.retry',
            ...common,
            task_id: p3TargetTaskId,
          };
    }
    if (!p3TaskName.trim() || !p3TaskInstruction.trim()) return null;
    return {
      operation: 'task.create',
      ...common,
      ...resolveProductTaskCreateOrigin(p3TaskInstruction, props.activeSessionId, voiceTaskOriginRef.current),
      name: p3TaskName,
      instruction: p3TaskInstruction,
    };
  };

  const issueP3MutationConfirmation = async () => {
    const inspectionWasChecking = p3RetryInspectionStatus === 'checking';
    cancelP3RetryInspection();
    if (inspectionWasChecking) {
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('idle');
      return;
    }
    const owner = p3MutationOwnerRef.current;
    let mutation = pendingP3MutationRef.current;
    if (
      mutation === null &&
      p3MutationOperation === 'task.create' &&
      voiceTaskOriginRef.current === null &&
      recognizedVoiceRef.current?.session_id === props.activeSessionId &&
      recognizedVoiceRef.current?.text === p3TaskInstruction
    ) {
      const origin = await commitRecognizedVoiceTaskOrigin();
      if (origin === null) {
        setP3MutationStatus('failed');
        return;
      }
    }
    mutation = mutation ?? buildP3Mutation();
    if (!owner || !mutation) return;
    pendingP3MutationRef.current = mutation;
    setP3MutationStatus('issuing');
    try {
      const receipt = await owner.issue(mutation);
      let leaf = formalTaskControlLeafRef.current;
      if (leaf === null) {
        leaf = new FormalTaskControlLeaf({
          enabled: true,
          binding: receipt.task_control_binding,
        });
        formalTaskControlLeafRef.current = leaf;
      } else {
        leaf.reconnect(receipt.task_control_binding);
      }
      pendingFormalP3MutationRef.current = prepareFormalTaskMutation(
        receipt.task_control_binding,
        {
          operation: mutation.operation,
          command_id: mutation.command_id,
          task_id: mutation.operation === 'task.create' ? null : mutation.task_id,
        },
        receipt
      );
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
    const leaf = formalTaskControlLeafRef.current;
    const prepared = pendingFormalP3MutationRef.current;
    if (!owner || !mutation || !leaf || !prepared) return;
    setP3MutationStatus('mutating');
    try {
      const result = await leaf.submitMutation(prepared, () => owner.mutate(mutation));
      leaf.adopt(mutation.operation, result, {
        connection_generation: leaf.snapshot().connection_generation,
        command_id: mutation.command_id,
        target_task_id: null,
        events_query: null,
      });
      if (p3MutationOwnerRef.current === owner) {
        if (mutation.operation === 'task.create') {
          const formalResult = recordValue(result.formal_task_result);
          const createdTaskId = formalResult?.task_id;
          if (typeof createdTaskId !== 'string' || !createdTaskId.trim()) {
            throw new Error('formal task.create result did not return an exact task');
          }
          setCreatedProgressTaskId(createdTaskId);
          cancelP3RetryInspection();
          setP3TargetTaskId(createdTaskId);
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('idle');
          setP3MutationOperation('task.cancel');
        } else if (mutation.operation === 'task.retry') {
          cancelP3RetryInspection();
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('ineligible');
          setP3MutationOperation('task.cancel');
        }
        pendingP3MutationRef.current = null;
        pendingFormalP3MutationRef.current = null;
        setP3MutationStatus('accepted');
        if (mutation.operation === 'task.cancel') {
          void inspectP3RetryEligibility({ task_id: mutation.task_id, follow_nonterminal: true });
        }
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
      if (cancelled || !FEATURE_LIVE_VOICE_INTEGRATED_WEB || !props.activeSessionId || !props.isConnected) {
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
        request: (method, params) => productRequest(method, params),
        on_snapshot: snapshot => {
          if (
            !isCurrentProgressOwner({
              cancelled,
              owner_epoch: ownerEpoch,
              current_owner_epoch: progressOwnerEpochRef.current,
              owner_session_id: ownedSessionId,
              active_session_id: activeSessionRef.current,
              is_current_owner: progressActivationOwnerRef.current === owner,
            })
          ) {
            return;
          }
          setP3Activation(snapshot);
          if (snapshot.status === 'active' && snapshot.binding) {
            const pending = [...pendingOwnedProgressRef.current.values()];
            pendingOwnedProgressRef.current.clear();
            for (const event of pending) {
              if (progressMatchesOwnedBinding(event, snapshot.binding, ownedSessionId)) {
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
          ...(createdProgressTaskId === null ? {} : { task_id: createdProgressTaskId }),
        });
      } catch (error) {
        // Reconcile a possibly response-lost activation before any successor
        // route can be created. The exact owner is retained on retry failure.
        if (owner.snapshot().binding && requiresProductActivationCleanup(error)) {
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
  }, [correlationId, createdProgressTaskId, props.activeSessionId, props.isConnected]);

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
      p1VoiceEnabled={FEATURE_LIVE_VOICE_INTEGRATED_P1 && props.isConnected && p2Activation.status === 'active'}
      p1VoiceStatus={p1VoiceStatus}
      p1VoiceReason={p1VoiceReason}
      onP1VoiceStart={() => void startProductVoiceCapture()}
      onP1VoiceStop={() => void (p1VoiceStatus === 'playing' ? stopProductVoicePlayout() : stopProductVoiceCapture())}
      productOperationRetained={Boolean(
        pendingProductTurnRef.current ||
        pendingPresentationAttemptRef.current ||
        pendingBargeInRef.current ||
        activationOwnerRef.current?.hasPendingSubmission() ||
        activationOwnerRef.current?.hasPendingPresentationAck() ||
        activationOwnerRef.current?.hasPendingBargeIn()
      )}
      onProductInput={value => {
        const owner = activationOwnerRef.current;
        if (
          pendingProductTurnRef.current ||
          pendingPresentationAttemptRef.current ||
          pendingBargeInRef.current ||
          owner?.hasPendingSubmission() ||
          owner?.hasPendingPresentationAck() ||
          owner?.hasPendingBargeIn()
        )
          return;
        setProductTextStatus('idle');
        if (value !== recognizedVoiceRef.current?.text) {
          recognizedVoiceRef.current = null;
        }
        setProductInput(value);
      }}
      onProductSubmit={() => {
        const recognized = recognizedVoiceRef.current;
        void submitProductText(
          undefined,
          recognized !== null && recognized.session_id === props.activeSessionId && recognized.text === productInput ? 'voice' : 'structured'
        );
      }}
      p3MutationEnabled={FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION && props.isConnected}
      p3MutationOperation={p3MutationOperation}
      p3TaskName={p3TaskName}
      p3TaskInstruction={p3TaskInstruction}
      p3TargetTaskId={p3TargetTaskId}
      p3MutationStatus={p3MutationStatus}
      p3MutationRetained={p3MutationOwnerRef.current?.hasPendingMutation() ?? false}
      p3RetryEligible={isFormalTaskRetryEligible(p3RetryEligibility)}
      p3RetryAttemptNumber={p3RetryEligibility?.attempt_number ?? null}
      p3RetryInspectionStatus={p3RetryInspectionStatus}
      onP3MutationOperation={value => {
        cancelP3RetryInspection();
        pendingP3MutationRef.current = null;
        voiceTaskOriginRef.current = null;
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
        if (value !== voiceTaskOriginRef.current?.instruction) {
          voiceTaskOriginRef.current = null;
        }
        if (value !== recognizedVoiceRef.current?.text) {
          recognizedVoiceRef.current = null;
        }
        setP3MutationStatus('idle');
        setP3TaskInstruction(value);
      }}
      onP3TargetTaskId={value => {
        pendingP3MutationRef.current = null;
        cancelP3RetryInspection();
        setP3RetryEligibility(null);
        setP3RetryInspectionStatus('idle');
        if (p3MutationOperation === 'task.retry') setP3MutationOperation('task.cancel');
        setP3MutationStatus('idle');
        setP3TargetTaskId(value);
      }}
      onP3InspectRetry={() => void inspectP3RetryEligibility({ follow_nonterminal: true })}
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
  p1VoiceEnabled?: boolean;
  p1VoiceStatus?: ProductP1VoiceStatus;
  p1VoiceReason?: string | null;
  onP1VoiceStart?: () => void;
  onP1VoiceStop?: () => void;
  productOperationRetained?: boolean;
  onProductInput?: (value: string) => void;
  onProductSubmit?: () => void;
  p3MutationEnabled?: boolean;
  p3MutationOperation?: 'task.create' | 'task.cancel' | 'task.retry';
  p3TaskName?: string;
  p3TaskInstruction?: string;
  p3TargetTaskId?: string;
  p3MutationStatus?: 'idle' | 'issuing' | 'confirmed' | 'mutating' | 'accepted' | 'failed';
  p3MutationRetained?: boolean;
  p3RetryEligible?: boolean;
  p3RetryAttemptNumber?: number | null;
  p3RetryInspectionStatus?: 'idle' | 'checking' | 'eligible' | 'ineligible' | 'failed';
  onP3MutationOperation?: (value: 'task.create' | 'task.cancel' | 'task.retry') => void;
  onP3TaskName?: (value: string) => void;
  onP3TaskInstruction?: (value: string) => void;
  onP3TargetTaskId?: (value: string) => void;
  onP3InspectRetry?: () => void;
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
  p1VoiceEnabled = false,
  p1VoiceStatus = 'closed',
  p1VoiceReason = null,
  onP1VoiceStart,
  onP1VoiceStop,
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
  p3RetryEligible = false,
  p3RetryAttemptNumber = null,
  p3RetryInspectionStatus = 'idle',
  onP3MutationOperation,
  onP3TaskName,
  onP3TaskInstruction,
  onP3TargetTaskId,
  onP3InspectRetry,
  onP3Issue,
  onP3Execute,
  onRefresh,
}: LiveVoiceIntegratedRoutePanelViewProps) {
  const { t } = useTranslation();

  const compositionLabel = t(`liveVoice.integrated.composition.${manifest.composition_state}`);
  const browserEvidence = platform?.browser_version
    ? `${platform.browser_family} ${platform.browser_version}`
    : (platform?.browser_family ?? t('liveVoice.integrated.diagnostics.pending'));
  const p3MutationLocked = ['issuing', 'confirmed', 'mutating'].includes(p3MutationStatus)
    || p3RetryInspectionStatus === 'checking'
    || (p3MutationStatus === 'failed' && p3MutationRetained);
  const productTextLocked =
    ['submitting', 'waiting', 'presented'].includes(productTextStatus) ||
    productOperationRetained ||
    ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus);

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
          {p1VoiceEnabled && onP1VoiceStart && onP1VoiceStop && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-product-voice">
              <strong>Formal P1 voice</strong>
              <span className="live-voice-integrated__progress-note">
                Dedicated same-origin PCM route → Gateway batch Speech → committed Agent text → Gateway synthesis.
              </span>
              <span className="live-voice-integrated__progress-note">
                This turn retains at most {PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 1000} seconds of captured audio. During continuous capture this is approximately{' '}
                {PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 1000} seconds; audio captured during overlapping playback counts toward the limit. Speak and press Stop
                and recognize before the limit.
              </span>
              {p1VoiceStatus === 'capturing' || p1VoiceStatus === 'playing' ? (
                <button type="button" onClick={onP1VoiceStop}>
                  {p1VoiceStatus === 'playing' ? 'Stop playback' : 'Stop and recognize'}
                </button>
              ) : (
                <button type="button" onClick={onP1VoiceStart} disabled={productOperationRetained || !['idle', 'recognized'].includes(p1VoiceStatus)}>
                  Start formal voice turn
                </button>
              )}
              <DiagnosticsFact label="P1 status" value={p1VoiceStatus} />
              {p1VoiceReason !== null && <DiagnosticsFact label="P1 reason" value={p1VoiceReason} />}
              {p1VoiceReason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON && (
                <span className="live-voice-integrated__progress-note">
                  The expired capture was discarded without a new Speech or Agent submission. Refresh to start again.
                </span>
              )}
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
              <label htmlFor="live-voice-product-text">{t('liveVoice.integrated.textRoute.label')}</label>
              <textarea
                id="live-voice-product-text"
                value={productInput}
                disabled={productTextLocked}
                onChange={event => onProductInput(event.target.value)}
                placeholder={t('liveVoice.integrated.textRoute.placeholder')}
                maxLength={100000}
              />
              <button type="submit" disabled={!productInput.trim() || productTextLocked}>
                {t('liveVoice.integrated.textRoute.submit')}
              </button>
              <DiagnosticsFact label={t('liveVoice.integrated.textRoute.status')} value={productTextStatus} />
              {productOutput !== null && <output aria-live="polite">{productOutput}</output>}
            </form>
          )}
          {p3MutationEnabled && onP3MutationOperation && onP3TaskName && onP3TaskInstruction && onP3TargetTaskId && onP3Issue && onP3Execute && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-p3-mutation">
              <strong>{t('liveVoice.integrated.taskControl.title')}</strong>
              <span className="live-voice-integrated__progress-note">{t('liveVoice.integrated.taskControl.disclosure')}</span>
              <select
                value={p3MutationOperation}
                disabled={p3MutationLocked}
                onChange={event => {
                  const operation = event.target.value;
                  onP3MutationOperation(operation === 'task.cancel' || operation === 'task.retry' ? operation : 'task.create');
                }}
              >
                <option value="task.create">{t('liveVoice.integrated.taskControl.create')}</option>
                <option value="task.cancel">{t('liveVoice.integrated.taskControl.cancel')}</option>
                {p3RetryEligible && <option value="task.retry">{t('liveVoice.integrated.taskControl.retry')}</option>}
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
              {p3MutationOperation !== 'task.create' && onP3InspectRetry && (
                <button
                  type="button"
                  onClick={onP3InspectRetry}
                  disabled={!p3TargetTaskId.trim() || p3MutationLocked}
                >
                  {t('liveVoice.integrated.taskControl.inspectRetry')}
                </button>
              )}
              <DiagnosticsFact
                label={t('liveVoice.integrated.taskControl.retryStatus')}
                value={p3RetryEligible && p3RetryAttemptNumber !== null
                  ? `eligible:${p3RetryAttemptNumber}/3`
                  : p3RetryInspectionStatus}
              />
              {p3MutationStatus === 'confirmed' ? (
                <button type="button" onClick={onP3Execute}>
                  {t('liveVoice.integrated.taskControl.execute')}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onP3Issue}
                  disabled={
                    p3MutationLocked
                    || (p3MutationOperation === 'task.retry' && !p3RetryEligible)
                  }
                >
                  {t('liveVoice.integrated.taskControl.confirm')}
                </button>
              )}
              <DiagnosticsFact label={t('liveVoice.integrated.taskControl.status')} value={p3MutationStatus} />
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
            <span className="live-voice-integrated__progress-note">{t('liveVoice.integrated.progress.disclosure')}</span>
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
