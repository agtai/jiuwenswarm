import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { FEATURE_LIVE_VOICE_INTEGRATED_WEB, FEATURE_LIVE_VOICE_TASK_DEMO } from '../../featureFlags';
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
  ProductWebP3ProgressOwner,
  requiresProductActivationCleanup,
  type ProductWebP2ActivationSnapshot,
  type ProductWebP3ProgressBinding,
  type ProductWebP3ProgressSnapshot,
} from '../../features/live-voice/formal/productWebActivation';
import { WebPlatformDiagnosticsMonitor, type WebPlatformDiagnosticsSnapshot } from '../../features/live-voice/formal/webPlatformDiagnostics';
import { webClient } from '../../services/webClient';
import './LiveVoiceIntegratedRoutePanel.css';

export interface LiveVoiceIntegratedRoutePanelProps {
  activeSessionId: string | null;
  isConnected: boolean;
  agentRouteAvailable: boolean;
  taskCompatibilityAvailable: boolean;
  routeSelection?: Readonly<IntegratedWebRouteSelection>;
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
  const [p3Activation, setP3Activation] = useState<Readonly<ProductWebP3ProgressSnapshot>>({
    status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
    binding: null,
    reason: null,
  });
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
  const progressActivationOwnerRef = useRef<ProductWebP3ProgressOwner | null>(null);
  const activeSessionRef = useRef<string | null>(props.activeSessionId);
  const progressOwnerEpochRef = useRef(0);
  const activationGenerationRef = useRef(0);
  const progressGenerationRef = useRef(0);
  activeSessionRef.current = props.activeSessionId;
  const manifest = useMemo(
    () => createManifest(props, correlationId, new Date().toISOString()),
    [correlationId, props.activeSessionId, props.agentRouteAvailable, props.isConnected, props.routeSelection, props.taskCompatibilityAvailable]
  );

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
    let cancelled = false;
    let owner: ProductWebP2ActivationOwner | null = null;
    const ownedSessionId = props.activeSessionId;
    const run = async () => {
      const previous = activationOwnerRef.current;
      if (previous) {
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
            return;
          }
        }
        if (activationOwnerRef.current === previous) activationOwnerRef.current = null;
      }
      if (
        cancelled ||
        !FEATURE_LIVE_VOICE_INTEGRATED_WEB ||
        !props.activeSessionId ||
        !props.isConnected ||
        !props.agentRouteAvailable
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
      owner = new ProductWebP2ActivationOwner({
        enabled: true,
        request: (method, params) => webClient.request(method, params),
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
          session_id: props.activeSessionId,
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
          } catch {
            // The exact cleanup_pending owner remains retained in the ref.
          }
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
      const closing = owner;
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
  }, [correlationId, props.activeSessionId, props.agentRouteAvailable, props.isConnected]);

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
      p2Activation={p2Activation}
      p3Activation={p3Activation}
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
  onRefresh: () => void;
}

export function LiveVoiceIntegratedRoutePanelView({
  manifest,
  platform,
  progress = null,
  progressAck = 'idle',
  p2Activation = null,
  p3Activation = null,
  onRefresh,
}: LiveVoiceIntegratedRoutePanelViewProps) {
  const { t } = useTranslation();

  const compositionLabel = t(`liveVoice.integrated.composition.${manifest.composition_state}`);
  const browserEvidence = platform?.browser_version
    ? `${platform.browser_family} ${platform.browser_version}`
    : (platform?.browser_family ?? t('liveVoice.integrated.diagnostics.pending'));

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
