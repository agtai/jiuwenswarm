import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import {
  FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION,
  FEATURE_LIVE_VOICE_INTEGRATED_P1,
  FEATURE_LIVE_VOICE_INTEGRATED_WEB,
  FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION,
} from '../../featureFlags';
import type { BrowserAudioCaptureStreamFactory } from '../../features/live-voice/formal/adapters/browserAudioIOAdapter';
import { recordAudioDiagnostic } from '../../features/live-voice/formal/audioDiagnostics';
import {
  BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  BrowserAudioDeviceSelectionOwner,
  type BrowserAudioDeviceSelectionSnapshot,
} from '../../features/live-voice/formal/browserAudioDeviceSelection';
import { FormalP3TaskExperienceOwner, type FormalP3TaskExperienceSnapshot } from '../../features/live-voice/formal/formalP3TaskExperience';
import {
  FormalTaskControlLeaf,
  isFormalTaskRetryEligible,
  prepareFormalTaskMutation,
  type FormalTaskControlBinding,
  type FormalTaskControlRecord,
  type PreparedFormalTaskMutation,
} from '../../features/live-voice/formal/formalTaskControlLeaf';
import { parseNativeGeneratedText } from '../../features/live-voice/formal/nativeGeneratedText';
import { nativeWorkBindingMatches, nativeWorkSnapshotAdvances, type NativeWorkStateSnapshot } from '../../features/live-voice/formal/nativeWorkState';
import {
  PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  PRODUCT_P1_EMPTY_TRANSCRIPT_REASON,
  ProductP1VoiceRouteOwner,
  type ProductP1VoiceStatus,
} from '../../features/live-voice/formal/productP1VoiceRoute';
import {
  PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
  ProductP2ActivationJournal,
  reconcileProductP2Predecessor,
  reconcileRetiredProductP2PresentationAcks,
} from '../../features/live-voice/formal/productP2ActivationJournal';
import { claimProductP3ProgressGeneration } from '../../features/live-voice/formal/productP3ProgressGenerationJournal';
import { inspectProductP3TaskTarget, persistProductP3TaskTarget } from '../../features/live-voice/formal/productP3TaskTargetJournal';
import {
  PRODUCT_TEXT_PROGRESS_EVENT,
  ProductTextProgressAckOwner,
  ProductTextProgressDomAdoptionOwner,
  adoptParsedProductTextProgressEvent,
  parseProductTextProgressEvent,
  type ProductTextProgressEvent,
} from '../../features/live-voice/formal/productTextProgress';
import {
  AGENT_MODEL_SELECTION_VERSION,
  PRODUCT_P2_PRESENTATION_ACK_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
  PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
  PRODUCT_P3_TASK_STATUS_METHOD,
  ProductWebP2ActivationOwner,
  ProductWebP3MutationOwner,
  ProductWebP3ProgressOwner,
  isDefinitiveProductOperationError,
  isProductNotificationSequenceMismatch,
  isRetriableProductOperationError,
  pollProductP2RouteWithRecovery,
  replayProductP2DurableOperation,
  requiresProductActivationCleanup,
  retryRetainedProductOperation,
  type ProductP2CloseCause,
  type ProductWebP2ActivationBinding,
  type ProductWebP2ActivationSnapshot,
  type ProductWebP3MutationInput,
  type ProductWebP3ProgressSnapshot,
} from '../../features/live-voice/formal/productWebActivation';
import { ProductUnifiedCommittedInputOwner, type UnifiedAuthoritativeFinal } from '../../features/live-voice/formal/unifiedCommittedInputOwner';
import { WebPlatformDiagnosticsMonitor, type WebPlatformDiagnosticsSnapshot } from '../../features/live-voice/formal/webPlatformDiagnostics';
import { extractWebErrorReason, webClient, webReconnectDelayMs } from '../../services/webClient';
import { useLiveVoiceTaskStore } from '../../stores/liveVoiceTaskStore';
import './LiveVoiceIntegratedRoutePanel.css';
import { LiveVoiceIntegratedRoutePanelView } from './LiveVoiceIntegratedRoutePanelView';
import {
  PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS,
  PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED,
  PRODUCT_P3_PROGRESS_BUFFER_CAPACITY,
  PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS,
  PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS,
  PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER,
  PRODUCT_TASK_NOTIFICATION_PLAYOUT_TIMEOUT_MS,
  awaitProductTaskNotificationPlayout,
  bindProductVoiceTaskOrigin,
  bootstrapProductP3TaskInspectionLeaf,
  capturedTaskNotificationDeadlineAction,
  capturedTaskNotificationRequiresAnnouncementRequeue,
  classifyProductP2Notification,
  createManifest,
  createProductP2ActivationOwner,
  defaultP3RetryInspectionWait,
  defaultProductRequest,
  durablePresentationAckMatches,
  foregroundPresentationFenceMatchesResponse,
  hasDurableProductVoiceSession,
  inspectProductP3RetryCandidate,
  isCurrentProgressOwner,
  isHarmlessCompletedBargeInError,
  isStaleProductResponseError,
  normalizeProductP1StatusForP2Retirement,
  playoutDeferredToSpeaker,
  productForegroundPresentationIdentity,
  productP2NotificationRepollDelayMs,
  productP2NotificationTransportBlockedByP1,
  productP2TaskNotificationCheckRequired,
  productP2TaskNotificationRequiresCaptureArbitration,
  productP2WebRequestOptions,
  productP3ProgressFailureIsQuarantinable,
  productP3ProgressReconciliationRetryDelayMs,
  productP3RetryInspectionFailureReason,
  productP3TerminalStatus,
  productRecoveryDiagnosticMatchesClear,
  productResponseGenerationIdentity,
  productTextBlockedByP1Status,
  productVoiceDraftMatchesBinding,
  progressMatchesOwnedBinding,
  recognizedSpeechConfirmationAuthorityMatches,
  recognizedSpeechConfirmationMatches,
  recognizedVoiceMatchesProductBinding,
  reconcileProductP3ProgressEvent,
  recordValue,
  rememberProductP3ProgressExhaustion,
  resolveProductTaskCreateOrigin,
  retainBoundedPresentedProductResponse,
  sameFormalTaskControlBinding,
  sameProductP2ActivationBinding,
  sameProductPresentation,
  shouldBlockProductP2NotificationPoll,
  stableProductTextReason,
  terminalAnnouncementArbitrationAction,
  terminalTextFallbackMessage,
  type CapturedProductTaskNotification,
  type DeferredProductTaskPresentation,
  type EditedVoiceDraftConfirmation,
  type LiveVoiceIntegratedRoutePanelProps,
  type PendingForegroundPresentationFence,
  type PendingProductPresentationAttempt,
  type ProductLiveVoiceRecoveryDiagnostic,
  type ProductLiveVoiceSurfaceControl,
  type ProductP2NotificationAdmission,
  type ProductP2NotificationDisposition,
  type ProductP3MutationStatus,
  type ProductP3RetryInspection,
  type ProductPresentationAckInput,
  type ProductRecognizedVoice,
  type ProductTaskPresentationFailureReason,
  type ProductTurnInput,
  type ProductVoiceDraftBinding,
  type ProductVoiceTaskOrigin,
  type RecognizedSpeechConfirmation,
  type TerminalAnnouncementState,
} from './liveVoiceProductOperations';
export { productTaskProgressTranslationKey } from './productTaskProgressPresentation';
export { extractWebErrorReason, webReconnectDelayMs };
export { LiveVoiceIntegratedRoutePanelView, type LiveVoiceIntegratedRoutePanelViewProps } from './LiveVoiceIntegratedRoutePanelView';
export {
  PRODUCT_P2_NOTIFICATION_CLIENT_TIMEOUT_MS,
  PRODUCT_P2_NOTIFICATION_PENDING_BACKOFF_MS,
  PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS,
  PRODUCT_P3_PROGRESS_EXHAUSTED_CAPACITY,
  PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER,
  PRODUCT_TASK_NOTIFICATION_PLAYOUT_TIMEOUT_MS,
  awaitProductTaskNotificationPlayout,
  bindProductVoiceTaskOrigin,
  bootstrapProductP3TaskInspectionLeaf,
  capturedTaskNotificationDeadlineAction,
  capturedTaskNotificationRequiresAnnouncementRequeue,
  classifyProductP2Notification,
  createProductP2ActivationOwner,
  hasDurableProductVoiceSession,
  inspectProductP3RetryCandidate,
  isCurrentProgressOwner,
  normalizeProductP1StatusForP2Retirement,
  parseProductP3RetryAdmission,
  productP2NotificationRepollDelayMs,
  productP2NotificationTransportBlockedByP1,
  productP2TaskNotificationCheckRequired,
  productP2TaskNotificationRequiresCaptureArbitration,
  productP2WebRequestOptions,
  productP3ProgressFailureIsQuarantinable,
  productP3ProgressReconciliationRetryDelayMs,
  productP3RetryInspectionFailureReason,
  productP3TerminalStatus,
  productRecoveryDiagnosticMatchesClear,
  productTextBlockedByP1Status,
  productVoiceDraftMatchesBinding,
  progressMatchesOwnedBinding,
  recognizedSpeechConfirmationMatches,
  reconcileProductP3ProgressEvent,
  rememberProductP3ProgressExhaustion,
  resolveProductTaskCreateOrigin,
  retainBoundedPresentedProductResponse,
  shouldBlockProductP2NotificationPoll,
  terminalAnnouncementArbitrationAction,
  terminalTextFallbackCompletesVoiceAnnouncement,
  terminalTextFallbackMessage,
  terminalTextFallbackNotificationText,
  type LiveVoiceIntegratedRoutePanelProps,
  type ProductLiveVoiceMessageEvent,
  type ProductLiveVoiceRecoveryDiagnostic,
  type ProductLiveVoiceSurfaceControl,
  type ProductLiveVoiceSurfaceState,
  type ProductP2NotificationDisposition,
  type ProductP3MutationStatus,
  type ProductP3RetryAdmission,
  type ProductP3RetryInspection,
  type ProductP3TerminalStatus,
  type ProductPresentationAckInput,
  type ProductRecognizedVoice,
  type ProductVoiceTaskOrigin,
  type RecognizedSpeechConfirmation,
  type TerminalAnnouncementState,
} from './liveVoiceProductOperations';


export function LiveVoiceIntegratedRoutePanel(props: LiveVoiceIntegratedRoutePanelProps) {
  const { t } = useTranslation();
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
  const [retiredPresentationAckRecoveryEpoch, setRetiredPresentationAckRecoveryEpoch] = useState(0);
  const [p2NotificationWakeEpoch, setP2NotificationWakeEpoch] = useState(0);
  const [foregroundPresentationEpoch, setForegroundPresentationEpoch] = useState(0);
  const [p3Activation, setP3Activation] = useState<Readonly<ProductWebP3ProgressSnapshot>>({
    status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
    binding: null,
    reason: null,
    requested_origin_kind: null,
    effective_origin_kind: null,
    voice_progress: null,
    voice_reason: null,
    fallback_reason: null,
  });
  const [productInput, setProductInput] = useState('');
  const [productOutput, setProductOutput] = useState<string | null>(null);
  const [terminalNotification, setTerminalNotification] = useState<string | null>(null);
  const [terminalAnnouncementState, setTerminalAnnouncementState] = useState<TerminalAnnouncementState>('idle');
  const [terminalAnnouncementArbitrationEpoch, setTerminalAnnouncementArbitrationEpoch] = useState(0);
  const [adjustmentNotification, setAdjustmentNotification] = useState<string | null>(null);
  const [productTextStatus, setProductTextStatus] = useState<
    'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed'
  >('idle');
  const [productTextReason, setProductTextReason] = useState<string | null>(null);
  const nativeForegroundEpochRef = useRef(0);
  const nativePresentationQueueRef = useRef<{ key: string; owner: ProductWebP2ActivationOwner; notification: Readonly<Record<string, unknown>>; admission: ProductP2NotificationAdmission }[]>([]);
  const nativeRequestStateRef = useRef<{ binding: string; sequence: number; phase: string } | null>(null);
  const [nativeWorkState, setNativeWorkState] = useState<NativeWorkStateSnapshot | null>(null);
  const nativeWorkStateRef = useRef<NativeWorkStateSnapshot | null>(null);
  const nativeTextReadRef = useRef<{ owner: ProductWebP2ActivationOwner; voice: ProductP1VoiceRouteOwner;
    binding: string; sessionId: string; revision: number; visible: Set<string>; ended: boolean;
    onEnd: LiveVoiceIntegratedRoutePanelProps['onNativeVoiceDisplayEnded'] } | null>(null);
  const endNativeTextDisplay = useCallback(() => {
    const cursor = nativeTextReadRef.current;
    if (!cursor || cursor.ended) return;
    cursor.ended = true;
    cursor.onEnd?.(cursor.sessionId, [...cursor.visible]);
  }, []);
  const [replacementRecognitionFailure, setReplacementRecognitionFailure] = useState<{
    session_id: string; loop_generation: number;
  } | null>(null);
  const [recoveryDiagnostic, setRecoveryDiagnostic] = useState<ProductLiveVoiceRecoveryDiagnostic | null>(null);
  const [p1VoiceStatus, setP1VoiceStatus] = useState<ProductP1VoiceStatus>(FEATURE_LIVE_VOICE_INTEGRATED_P1 ? 'idle' : 'closed');
  const [p1FaultTailPlaying, setP1FaultTailPlaying] = useState(false);
  const [p1VoiceReason, setP1VoiceReason] = useState<string | null>(null);
  const [interruptionDegradedReason, setInterruptionDegradedReason] = useState<string | null>(null);
  const [deviceSelection, setDeviceSelection] = useState<Readonly<BrowserAudioDeviceSelectionSnapshot>>({
    status: FEATURE_LIVE_VOICE_INTEGRATED_P1 ? 'idle' : 'closed',
    reason: null,
    inventory_generation: 0,
    selection_generation: 1,
    inputs: Object.freeze([]),
    outputs: Object.freeze([]),
    applied_input_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
    applied_output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  });
  const [draftInputDeviceToken, setDraftInputDeviceToken] = useState(BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN);
  const [draftOutputDeviceToken, setDraftOutputDeviceToken] = useState(BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN);
  const [recognizedSpeechConfirmation, setRecognizedSpeechConfirmation] = useState<RecognizedSpeechConfirmation | null>(null);
  const [editedVoiceDraftConfirmation, setEditedVoiceDraftConfirmation] = useState<EditedVoiceDraftConfirmation | null>(null);
  const [pendingPresentationAck, setPendingPresentationAck] = useState<ProductPresentationAckInput | null>(null);
  const [p3MutationOperation, setP3MutationOperation] = useState<'task.create' | 'task.cancel' | 'task.retry'>('task.create');
  const [p3TaskName, setP3TaskName] = useState('');
  const [p3TaskInstruction, setP3TaskInstruction] = useState('');
  const [p3TargetTaskId, setP3TargetTaskId] = useState('');
  const [p3MutationStatus, setP3MutationStatus] = useState<ProductP3MutationStatus>('idle');
  const [p3MutationReason, setP3MutationReason] = useState<string | null>(null);
  const [taskExperience, setTaskExperience] = useState<FormalP3TaskExperienceSnapshot>({
    status: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ? 'idle' : 'disabled',
    session_id: null,
    tasks: Object.freeze([]),
    selected_task_id: null,
    collection_operations: Object.freeze([]),
    command: null,
    reason: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ? null : 'FORMAL_P3_TASK_EXPERIENCE_DISABLED',
  });
  useEffect(() => {
    if (p2Activation.status !== 'active' || !p2Activation.agent_model_selection) return;
    recordAudioDiagnostic('native_model_confirmed', { ...p2Activation.binding,
      model_id: p2Activation.agent_model_selection.model_identity,
      model_config_version: p2Activation.agent_model_selection.model_config_version });
  }, [p2Activation.status, p2Activation.binding?.activation_id,
    p2Activation.agent_model_selection?.model_identity, p2Activation.agent_model_selection?.model_config_version]);
  const selectedAgentModelNameRef = useRef(props.selectedAgentModelName ?? null);
  selectedAgentModelNameRef.current = props.selectedAgentModelName ?? null;
  const taskExperienceValidatedSessionRef = useRef<string | null>(null);
  const taskExperienceRevalidationPendingSessionRef = useRef<string | null>(null);
  const [p3RetryInspectionStatus, setP3RetryInspectionStatus] = useState<'idle' | 'checking' | 'eligible' | 'ineligible' | 'failed'>('idle');
  const [p3RetryInspectionReason, setP3RetryInspectionReason] = useState<string | null>(null);
  const [p3RetryEligibility, setP3RetryEligibility] = useState<Readonly<FormalTaskControlRecord> | null>(null);
  const p3RetryInspectionGenerationRef = useRef(0);
  const p3RetryInspectionAbortRef = useRef<AbortController | null>(null);
  const [createdProgressRoute, setCreatedProgressRoute] = useState<Readonly<{
    task_id: string;
    correlation_id: string;
    origin: Readonly<{ kind: 'text' | 'voice'; id: string }> | null;
  }> | null>(null);
  useEffect(() => {
    if (p3MutationStatus !== 'failed') setP3MutationReason(null);
  }, [p3MutationStatus]);
  const createdProgressTaskId = createdProgressRoute?.task_id ?? null;
  const createdProgressCorrelationId = createdProgressRoute?.correlation_id ?? null;
  const createdProgressOrigin = createdProgressRoute?.origin ?? null;
  const createdProgressRouteRef = useRef<typeof createdProgressRoute>(null);
  const desiredVoiceProgressRef = useRef(new Map<string, {
    binding: Readonly<ProductWebP2ActivationBinding>;
    voice_generation: number;
    retryable: boolean;
  }>());
  const voiceProgressOwnersRef = useRef(new Map<string, {
    binding: Readonly<ProductWebP2ActivationBinding>;
    owner: ProductWebP3ProgressOwner;
    leaf: FormalTaskControlLeaf | null;
    closed: boolean;
    terminal_presented: boolean;
    notification_chinese: boolean;
    notification_name: string | null;
    voice_generation: number;
    retry_abort: AbortController;
    ready: Promise<void>;
  }>());
  const terminalNotificationTaskIdRef = useRef<string | null>(null);
  const terminalAnnouncementStateRef = useRef<TerminalAnnouncementState>('idle');
  const terminalAnnouncementTaskIdRef = useRef<string | null>(null);
  const terminalAnnouncementSpeechOwnerRef = useRef<ProductP1VoiceRouteOwner | null>(null);
  const progressTaskTargetRef = useRef<string | null>(null);
  const recoveredP3TaskTargetRef = useRef<string | null>(null);
  const monitorRef = useRef<WebPlatformDiagnosticsMonitor | null>(null);
  const progressRef = useRef<Readonly<ProductTextProgressEvent> | null>(null);
  const pendingOwnedProgressRef = useRef(new Map<string, Readonly<ProductTextProgressEvent>>());
  const progressDrainRef = useRef<(() => void) | null>(null);
  const progressAckOwnerRef = useRef<ProductTextProgressAckOwner | null>(null);
  const progressDomAdoptionOwnerRef = useRef<ProductTextProgressDomAdoptionOwner | null>(null);
  const progressDomRef = useRef<HTMLDivElement | null>(null);
  const adoptVisibleProductTextProgressNode = useMemo(() => {
    const ownedProgress = progress;
    let ownedNode: HTMLDivElement | null = null;
    return (node: HTMLDivElement | null) => {
      if (node === null) {
        if (progressDomRef.current === ownedNode) progressDomRef.current = null;
        ownedNode = null;
        return;
      }
      ownedNode = node;
      progressDomRef.current = node;
      const adoptionOwner = progressDomAdoptionOwnerRef.current;
      if (ownedProgress === null || adoptionOwner === null) return;
      try {
        const retained = adoptionOwner.adopt(ownedProgress, node);
        if (retained === null) return;
        setProgressAck(retained.status);
        // The reconciliation coroutine clears its in-flight guard in `finally`.
        // Continue only after the user-visible product node owns this delivery.
        globalThis.setTimeout(() => progressDrainRef.current?.(), 0);
      } catch {
        setProgressAck('failed');
      }
    };
  }, [progress]);
  const activationOwnerRef = useRef<ProductWebP2ActivationOwner | null>(null);
  const p2ActivationJournalRef = useRef<ProductP2ActivationJournal | null>(null);
  const retiredPresentationAckInFlightRef = useRef(new Set<string>());
  const retiredPresentationAckOwnerRequestRef = useRef(new Map<ProductWebP2ActivationOwner, string>());
  const retiredPresentationAckDrainIdentityRef = useRef(0);
  const p1VoiceOwnerRef = useRef<ProductP1VoiceRouteOwner | null>(null);
  const l0CaptureStreamFactoryRef = useRef<BrowserAudioCaptureStreamFactory | null>(null);
  const p1VoiceOwnerSessionRef = useRef<string | null>(null);
  const unifiedInputOwnerRef = useRef<ProductUnifiedCommittedInputOwner | null>(null);
  const deviceSelectionOwnerRef = useRef<BrowserAudioDeviceSelectionOwner | null>(null);
  const pendingP1VoiceStartRef = useRef<Readonly<{ generation: number; promise: Promise<void> }> | null>(null);
  const pendingP1VoiceStopRef = useRef<Promise<void> | null>(null);
  const stopP1VoiceHandlerRef = useRef<() => Promise<void>>(async () => undefined);
  const startP1VoiceHandlerRef = useRef<() => Promise<void>>(async () => undefined);
  const captureRecoveryGenerationRef = useRef<number | null>(null);
  const voiceLoopEnabledRef = useRef(false);
  const voiceLoopGenerationRef = useRef(0);
  const voiceLoopCaptureTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null);
  const productP2RecoveryTimerRef = useRef<{
    timer: ReturnType<typeof globalThis.setTimeout>;
    session_id: string;
    binding: Readonly<ProductWebP2ActivationBinding>;
    journal: ProductP2ActivationJournal;
  } | null>(null);
  const voiceLoopP2RefreshAfterGenerationRef = useRef<number | null>(null);
  const voiceLoopP2RefreshCauseRef = useRef<ProductP2CloseCause>('active_recovery');
  const voiceLoopP2RefreshInFlightRef = useRef(false);
  const deferredTaskPresentationRef = useRef<DeferredProductTaskPresentation | null>(null);
  const capturedTaskNotificationRef = useRef<CapturedProductTaskNotification | null>(null);
  const capturedTaskNotificationDeadlineRef = useRef<Readonly<{
    timer: ReturnType<typeof globalThis.setTimeout>;
    notification: CapturedProductTaskNotification;
    capture_settlement_requested: boolean;
  }> | null>(null);
  const terminalNotificationCheckRequiredRef = useRef(false);
  const taskAudioRepollBeforeCaptureTaskIdRef = useRef<string | null>(null);
  terminalNotificationCheckRequiredRef.current = [...voiceProgressOwnersRef.current.values()].some(entry => !entry.closed && !entry.terminal_presented) || productP2TaskNotificationCheckRequired({
    deferred_presentation: deferredTaskPresentationRef.current !== null,
    task_id: createdProgressTaskId,
    origin_kind: createdProgressOrigin?.kind ?? null,
    terminal_task_id: terminalNotificationTaskIdRef.current,
    announcement_task_id: terminalAnnouncementTaskIdRef.current,
    announcement_state: terminalAnnouncementStateRef.current,
  });
  const submittedVoiceFinalsRef = useRef(
    new Map<string, Readonly<{ fingerprint: string; operation: Promise<void> }>>(),
  );
  const pendingUnifiedFinalRef = useRef<Readonly<{
    receipt: string;
    input: UnifiedAuthoritativeFinal;
    playout_owner: ProductP1VoiceRouteOwner | null;
    voice_loop_generation: number;
  }> | null>(null);
  const readPendingUnifiedFinal = () => pendingUnifiedFinalRef.current;
  const pendingForegroundPresentationRef = useRef<PendingForegroundPresentationFence | null>(null);
  const foregroundTextStatusAfterSettlement = () =>
    pendingUnifiedFinalRef.current !== null ? 'submitting' as const :
      pendingForegroundPresentationRef.current !== null ? 'waiting' as const : 'acknowledged' as const;
  const pendingProductTurnRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductTurnInput;
  } | null>(null);
  const pendingPresentationAttemptRef = useRef<PendingProductPresentationAttempt | null>(null);
  const retryTerminalAnnouncementHandlerRef = useRef<(retained: NonNullable<typeof pendingPresentationAttemptRef.current>) => void>(() => undefined);
  const resumeDeferredTaskAnnouncementRef = useRef<(retained: NonNullable<typeof pendingPresentationAttemptRef.current>) => void>(() => undefined);
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
  const recoveryDiagnosticRef = useRef<ProductLiveVoiceRecoveryDiagnostic | null>(null);
  const presentedProductResponsesRef = useRef(new Map<string, true>());
  const presentedNativeChatMessagesRef = useRef(new Map<string, true>());
  const discoveredNativeTasksRef = useRef(new Map<string, true>());
  const refreshedNativeTaskOperationsRef = useRef(new Map<string, true>());
  const nativeTaskDiscoveryRef = useRef<Promise<void>>(Promise.resolve());
  const progressActivationOwnerRef = useRef<ProductWebP3ProgressOwner | null>(null);
  const p3MutationOwnerRef = useRef<ProductWebP3MutationOwner | null>(null);
  const taskExperienceOwnerRef = useRef<FormalP3TaskExperienceOwner | null>(null);
  const pendingP3MutationRef = useRef<ProductWebP3MutationInput | null>(null);
  const p3AcceptedFollowTargetRef = useRef<Readonly<{ session_id: string; task_id: string }> | null>(null);
  const voiceTaskOriginRef = useRef<ProductVoiceTaskOrigin | null>(null);
  const recognizedVoiceRef = useRef<ProductRecognizedVoice | null>(null);
  const voiceDraftBindingRef = useRef<ProductVoiceDraftBinding | null>(null);
  const p3VoiceDraftBindingRef = useRef<ProductVoiceDraftBinding | null>(null);
  const p1VoiceCaptureBindingRef = useRef<Readonly<NonNullable<ProductWebP2ActivationSnapshot['binding']>> | null>(null);
  const recognizedSpeechConfirmationRef = useRef<RecognizedSpeechConfirmation | null>(null);
  const editedVoiceDraftConfirmationRef = useRef<EditedVoiceDraftConfirmation | null>(null);
  const formalTaskControlLeafRef = useRef<FormalTaskControlLeaf | null>(null);
  const pendingFormalP3MutationRef = useRef<PreparedFormalTaskMutation | null>(null);
  const activeSessionRef = useRef<string | null>(props.activeSessionId);
  const isConnectedRef = useRef(props.isConnected);
  const mountedRef = useRef(true);
  const progressOwnerEpochRef = useRef(0);
  const p3ProgressReconciliationGenerationRef = useRef(0);
  const activationGenerationRef = useRef(0);
  const productTurnSequenceRef = useRef(0);
  const bargeInSequenceRef = useRef(0);
  // The hands-free listening window that runs while an Agent answer is still
  // being generated. It is bound to the exact response it may replace, so a
  // late or reordered capture can never fence a newer answer.
  const generationCaptureRef = useRef<Readonly<{
    owner: ProductWebP2ActivationOwner;
    fence: PendingForegroundPresentationFence;
    loop_generation: number;
  }> | null>(null);
  // While submit is in flight there is no server response ID to interrupt.
  // Retain speech against the exact local final, then bind it on acceptance.
  const submissionCaptureRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: UnifiedAuthoritativeFinal;
    loop_generation: number;
    speech_started: boolean;
  } | null>(null);
  const pendingGenerationInterruptRef = useRef<Readonly<{
    owner: ProductWebP2ActivationOwner;
    input: { action_id: string; response_id: string; response_generation: number };
  }> | null>(null);
  /**
   * Whether this exact activation still owns an interruption that has not
   * settled. Five rounds of review turned this into the single question every
   * barrier here has to ask: an unsettled interruption closes its own owner's
   * capture, listening window, announcement arbitration and turn admission,
   * while a retired activation's handle must close nothing at all -- matching
   * on "any pending interruption" once fenced every later Session out of
   * generation-time listening for the life of the page.
   */
  const ownerHasUnsettledGenerationInterrupt = (
    candidate: ProductWebP2ActivationOwner | null,
  ): boolean => candidate !== null && pendingGenerationInterruptRef.current?.owner === candidate;
  /**
   * Retire the generation-time listening window.
   *
   * The window is the one capture allowed to keep the P2 notification poll
   * alive, and the next answer is refused a window of its own while one is
   * retained -- so a window left behind does not merely leak, it silently
   * disables the feature for the rest of the session. Four separate paths must
   * retire it, each found by a different review round: Session switch, Exit,
   * browser capture ownership surrender, and the exact response failing. They
   * all go through here so the complete set stays greppable from one name.
   *
   * `matches` narrows the retirement to a window this caller owns; omit it to
   * retire whatever is there.
   */
  const retireGenerationListening = (
    matches?: (retained: { fence: PendingForegroundPresentationFence }) => boolean,
  ): boolean => {
    if (matches === undefined) submissionCaptureRef.current = null;
    const retained = generationCaptureRef.current;
    if (retained === null) return false;
    if (matches !== undefined && !matches(retained)) return false;
    generationCaptureRef.current = null;
    return true;
  };
  const generationInterruptSequenceRef = useRef(0);
  const replacementRecognitionRef = useRef<{
    owner: NonNullable<typeof p1VoiceOwnerRef.current>;
    binding: NonNullable<typeof p1VoiceCaptureBindingRef.current>;
    loop_generation: number;
    fenced: boolean;
    failed: boolean;
  } | null>(null);
  const publishReplacementRecognitionFailure = () => {
    const replacement = replacementRecognitionRef.current;
    if (replacement === null || !replacement.fenced || !replacement.failed ||
      !mountedRef.current || !voiceLoopEnabledRef.current ||
      replacement.owner !== p1VoiceOwnerRef.current ||
      replacement.loop_generation !== voiceLoopGenerationRef.current ||
      replacement.binding.session_id !== activeSessionRef.current) return;
    setReplacementRecognitionFailure({
      session_id: replacement.binding.session_id,
      loop_generation: replacement.loop_generation,
    });
  };
  // Responses this route has interrupted. A fenced answer can still be in
  // flight from the server, so exact response id + generation, not timing, is
  // what refuses it.
  const interruptedProductResponsesRef = useRef(new Map<string, true>());
  const localRetiredForegroundPresentationsRef = useRef(new Map<string, true>());
  const interruptProductGenerationHandlerRef = useRef<() => Promise<void>>(async () => undefined);

  /**
   * Keep pulling P2 notifications while the generation-time window listens.
   *
   * Ordinary capture and waiting for an answer are mutually exclusive, so the
   * poll normally stands down for any open capture. Generation-time listening
   * is the one capture that runs *because* an answer is still outstanding: if
   * the poll stood down for it, that answer could not arrive until the user
   * stopped speaking, which is the exact latency this feature removes.
   */
  const admitsGenerationListeningPoll = (status: ProductP1VoiceStatus): boolean =>
    FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION &&
    generationCaptureRef.current !== null &&
    ['starting', 'capturing'].includes(status);
  const p3MutationSequenceRef = useRef(0);
  const updateTerminalAnnouncementState = (state: TerminalAnnouncementState, taskId?: string | null) => {
    if (state !== 'fetching') taskAudioRepollBeforeCaptureTaskIdRef.current = null;
    terminalAnnouncementStateRef.current = state;
    if (taskId !== undefined) terminalAnnouncementTaskIdRef.current = taskId;
    setTerminalAnnouncementState(state);
  };
  const clearCapturedTaskNotification = (expected?: CapturedProductTaskNotification) => {
    if (expected !== undefined && capturedTaskNotificationRef.current !== expected) return false;
    const deadline = capturedTaskNotificationDeadlineRef.current;
    if (deadline !== null && (expected === undefined || deadline.notification === expected)) {
      globalThis.clearTimeout(deadline.timer);
      capturedTaskNotificationDeadlineRef.current = null;
    }
    capturedTaskNotificationRef.current = null;
    return true;
  };
  const queueTerminalAnnouncement = (taskId: string) => {
    const route = createdProgressRouteRef.current;
    const ownedVoice = voiceProgressOwnersRef.current.get(taskId);
    if ((ownedVoice === undefined && (route?.task_id !== taskId || route.origin?.kind !== 'voice')) || terminalNotificationTaskIdRef.current === taskId) {
      return;
    }
    const currentTaskId = terminalAnnouncementTaskIdRef.current;
    if (currentTaskId !== null && currentTaskId !== taskId && terminalAnnouncementStateRef.current !== 'idle') return;
    if (terminalAnnouncementStateRef.current === 'idle') updateTerminalAnnouncementState('queued', taskId);
  };
  const adoptCreatedProgressRoute = (route: typeof createdProgressRoute) => {
    const previousTaskId = createdProgressRouteRef.current?.task_id ?? null;
    const nextTaskId = route?.task_id ?? null;
    if (nextTaskId !== null && nextTaskId !== previousTaskId && voiceProgressOwnersRef.current.size === 0) {
      clearCapturedTaskNotification();
      terminalNotificationTaskIdRef.current = null;
      updateTerminalAnnouncementState('idle', null);
      terminalAnnouncementSpeechOwnerRef.current = null;
      setTerminalNotification(null);
      setAdjustmentNotification(null);
    }
    createdProgressRouteRef.current = route;
    terminalNotificationCheckRequiredRef.current = [...voiceProgressOwnersRef.current.values()].some(entry => !entry.closed && !entry.terminal_presented) || productP2TaskNotificationCheckRequired({
      deferred_presentation: deferredTaskPresentationRef.current !== null,
      task_id: nextTaskId,
      origin_kind: route?.origin?.kind ?? null,
      terminal_task_id: terminalNotificationTaskIdRef.current,
      announcement_task_id: terminalAnnouncementTaskIdRef.current,
      announcement_state: terminalAnnouncementStateRef.current,
    });
    setCreatedProgressRoute(route);
  };
  const cancelP3RetryInspection = () => {
    p3RetryInspectionGenerationRef.current += 1;
    p3RetryInspectionAbortRef.current?.abort();
    p3RetryInspectionAbortRef.current = null;
  };
  const updateRecognizedSpeechConfirmation = (confirmation: RecognizedSpeechConfirmation | null) => {
    if (confirmation !== null || editedVoiceDraftConfirmationRef.current !== null) {
      editedVoiceDraftConfirmationRef.current = null;
      setEditedVoiceDraftConfirmation(null);
    }
    recognizedSpeechConfirmationRef.current = confirmation;
    setRecognizedSpeechConfirmation(confirmation);
  };
  const updateEditedVoiceDraftConfirmation = (confirmation: EditedVoiceDraftConfirmation | null) => {
    if (confirmation !== null || recognizedSpeechConfirmationRef.current !== null) {
      recognizedSpeechConfirmationRef.current = null;
      setRecognizedSpeechConfirmation(null);
    }
    editedVoiceDraftConfirmationRef.current = confirmation;
    setEditedVoiceDraftConfirmation(confirmation);
  };
  const currentProductP2Binding = (): ProductWebP2ActivationSnapshot['binding'] => {
    const snapshot = activationOwnerRef.current?.snapshot();
    return snapshot?.status === 'active' ? snapshot.binding : null;
  };
  const publishProductRecoveryDiagnostic = (input: Readonly<{
    seam: ProductLiveVoiceRecoveryDiagnostic['seam'];
    disposition: ProductLiveVoiceRecoveryDiagnostic['disposition'];
    reason: string;
    binding: ProductWebP2ActivationSnapshot['binding'];
    nativeTurnId?: string;
    response?: Readonly<{
      interaction_id: string;
      response_id: string;
      response_generation: number;
    }> | null;
  }>) => {
    const bindingSessionId = input.binding?.session_id ?? null;
    if (bindingSessionId !== null && bindingSessionId !== activeSessionRef.current) return;
    const sessionId = bindingSessionId ?? activeSessionRef.current;
    if (sessionId === null) return;
    const diagnostic = Object.freeze<ProductLiveVoiceRecoveryDiagnostic>({
      seam: input.seam,
      disposition: input.disposition,
      reason: input.reason,
      session_id: sessionId,
      correlation_id: input.binding?.correlation_id ?? correlationId,
      interaction_id: input.response?.interaction_id ?? input.binding?.interaction_id ?? null,
      activation_id: input.binding?.activation_id ?? null,
      activation_generation: input.binding?.activation_generation ?? null,
      response_id: input.response?.response_id ?? null,
      response_generation: input.response?.response_generation ?? null,
    });
    recordAudioDiagnostic('voice_recovery_state', { ...diagnostic, stage: diagnostic.seam, status: diagnostic.disposition });
    recoveryDiagnosticRef.current = diagnostic;
    setRecoveryDiagnostic(diagnostic);
    const isNative = p1VoiceOwnerRef.current?.interactionEngine() === 'openai-realtime-native' ||
      (input.binding != null && nativeRequestStateRef.current?.binding ===
        JSON.stringify([sessionId, input.binding.activation_id, input.binding.activation_generation]));
    if (!isNative && input.disposition === 'terminal' && input.seam === 'response_generation') {
      // Native failures belong to the status area. Its original generated row
      // retains the interruption state without inserting an assistant answer.
      const failureIdentity = input.nativeTurnId !== undefined
        ? `native:${diagnostic.activation_generation}:${input.nativeTurnId}`
        : `${diagnostic.response_id ?? diagnostic.reason}:${diagnostic.response_generation ?? 0}`;
      props.onProductVoiceMessage?.({ session_id: sessionId, message: {
        id: `live-voice-failure:${diagnostic.activation_id}:${failureIdentity}`,
        role: 'assistant', content: t('liveVoice.formal.requestFailed', { reason: input.reason }),
        timestamp: new Date().toISOString(),
      } });
    }
  };
  const clearProductRecoveryDiagnostic = (input?: Readonly<{
    seam: ProductLiveVoiceRecoveryDiagnostic['seam'];
    binding: ProductWebP2ActivationSnapshot['binding'];
    response?: Readonly<{
      response_id: string;
      response_generation: number;
    }> | null;
  }>) => {
    const current = recoveryDiagnosticRef.current;
    if (current === null) return;
    if (input !== undefined && !productRecoveryDiagnosticMatchesClear(current, input)) return;
    recordAudioDiagnostic('voice_recovery_cleared', { ...current, stage: current.seam, outcome: 'recovered' });
    recoveryDiagnosticRef.current = null;
    setRecoveryDiagnostic(null);
  };
  activeSessionRef.current = props.activeSessionId;
  isConnectedRef.current = props.isConnected;

  const hasExactNativeTerminalFailure = (binding: ProductWebP2ActivationSnapshot['binding']) => {
    const state = nativeRequestStateRef.current;
    const retained = recoveryDiagnosticRef.current;
    return binding !== null && state?.phase === 'failed' &&
      state.binding === JSON.stringify([binding.session_id, binding.activation_id, binding.activation_generation]) &&
      retained?.seam === 'response_generation' && retained.disposition === 'terminal' &&
      retained.session_id === binding.session_id && retained.correlation_id === binding.correlation_id &&
      retained.interaction_id === binding.interaction_id && retained.activation_id === binding.activation_id &&
      retained.activation_generation === binding.activation_generation;
  };

  const currentDeferredTaskPresentation = (owner = activationOwnerRef.current) =>
    owner !== null && deferredTaskPresentationRef.current?.owner === owner
      ? deferredTaskPresentationRef.current
      : null;

  const retainDeferredTaskPresentation = (
    owner: ProductWebP2ActivationOwner,
    disposition: Extract<ProductP2NotificationDisposition, { readonly kind: 'presentation' }>,
  ) => {
    let retained = deferredTaskPresentationRef.current;
    if (retained?.owner.snapshot().status === 'closed') {
      deferredTaskPresentationRef.current = null;
      retained = null;
    }
    if (
      retained?.owner === owner &&
      retained.disposition.response_id === disposition.response_id &&
      retained.disposition.response.response_generation === disposition.response.response_generation
    ) {
      return;
    }
    if (retained !== null) {
      throw new Error('a deferred Task presentation is still unresolved');
    }
    deferredTaskPresentationRef.current = Object.freeze({
      owner,
      disposition,
    });
  };

  const retireDeferredTaskPresentationForClosedOwner = (owner: ProductWebP2ActivationOwner) => {
    if (
      deferredTaskPresentationRef.current?.owner === owner &&
      owner.snapshot().status === 'closed'
    ) {
      deferredTaskPresentationRef.current = null;
    }
  };

  const retireCapturedTaskNotificationForClosedOwner = (owner: ProductWebP2ActivationOwner) => {
    if (
      capturedTaskNotificationRef.current?.owner === owner &&
      owner.snapshot().status === 'closed'
    ) {
      clearCapturedTaskNotification(capturedTaskNotificationRef.current);
    }
  };

  const retireDeferredTaskPresentationForClosedBinding = (
    binding: Readonly<ProductWebP2ActivationBinding>,
  ) => {
    const retained = deferredTaskPresentationRef.current;
    const retainedBinding = retained?.owner.snapshot().binding ?? null;
    if (
      retained !== null &&
      retainedBinding !== null &&
      sameProductP2ActivationBinding(retainedBinding, binding)
    ) {
      deferredTaskPresentationRef.current = null;
    }
  };

  const retireCapturedTaskNotificationForClosedBinding = (
    binding: Readonly<ProductWebP2ActivationBinding>,
  ) => {
    const retained = capturedTaskNotificationRef.current;
    const retainedBinding = retained?.owner.snapshot().binding ?? null;
    if (
      retained !== null &&
      retainedBinding !== null &&
      sameProductP2ActivationBinding(retainedBinding, binding)
    ) {
      clearCapturedTaskNotification(retained);
    }
  };

  const clearScheduledProductVoiceLoopCapture = () => {
    const timer = voiceLoopCaptureTimerRef.current;
    if (timer === null) return;
    globalThis.clearTimeout(timer);
    voiceLoopCaptureTimerRef.current = null;
  };

  const scheduleProductVoiceLoopCapture = () => {
    if (
      !voiceLoopEnabledRef.current ||
      pendingForegroundPresentationRef.current !== null ||
      deferredTaskPresentationRef.current !== null ||
      voiceLoopCaptureTimerRef.current !== null
    ) {
      return;
    }
    const loopGeneration = voiceLoopGenerationRef.current;
    voiceLoopCaptureTimerRef.current = globalThis.setTimeout(() => {
      voiceLoopCaptureTimerRef.current = null;
      const voiceOwner = p1VoiceOwnerRef.current;
      const terminalState = terminalAnnouncementStateRef.current;
      if (
        voiceLoopEnabledRef.current &&
        voiceLoopGenerationRef.current === loopGeneration &&
        (pendingUnifiedFinalRef.current === null || submissionCaptureRef.current?.input === pendingUnifiedFinalRef.current.input) &&
        pendingForegroundPresentationRef.current === null &&
        deferredTaskPresentationRef.current === null &&
        pendingProductTurnRef.current === null &&
        pendingPresentationAttemptRef.current === null &&
        pendingBargeInRef.current === null &&
        (terminalState === 'idle' || voiceOwner === null || ['failed', 'cleanup_pending', 'closed'].includes(voiceOwner.status().status)) &&
        (voiceOwner === null || ['idle', 'recognized', 'failed', 'cleanup_pending', 'closed'].includes(voiceOwner.status().status))
      ) {
        void startP1VoiceHandlerRef.current().catch(() => undefined);
      }
    }, 0);
  };

  useEffect(() => {
    // Presentation ACK can settle one render before Product P1 publishes its
    // final `playing -> recognized` transition. The first 0 ms capture wake is
    // then correctly fenced by the still-playing owner; replay that idempotent
    // wake only after both owners have authoritatively settled.
    if (
      p1VoiceStatus === 'recognized' &&
      productTextStatus === 'acknowledged' &&
      recognizedVoiceRef.current === null
    ) {
      scheduleProductVoiceLoopCapture();
    }
  }, [p1VoiceStatus, productTextStatus]);

  const resumeVoiceLoopAfterP2Successor = (binding: NonNullable<ProductWebP2ActivationSnapshot['binding']>) => {
    const predecessorGeneration = voiceLoopP2RefreshAfterGenerationRef.current;
    if (predecessorGeneration === null || binding.activation_generation <= predecessorGeneration) return;
    voiceLoopP2RefreshAfterGenerationRef.current = null;
    voiceLoopP2RefreshInFlightRef.current = false;
    voiceLoopP2RefreshCauseRef.current = 'active_recovery';
    // Clearing the refresh fence only mutates refs. Wake this bounded terminal
    // handoff so the Registry's successor-bound TEXT is polled immediately.
    if (['queued', 'fetching'].includes(terminalAnnouncementStateRef.current)) {
      setP2NotificationWakeEpoch(epoch => epoch + 1);
    }
    // Predecessor output is fenced at Exit. Successor capture is independent
    // of the shielded teardown of an already accepted Agent turn.
    scheduleProductVoiceLoopCapture();
  };

  const continuePendingVoiceLoopP2Refresh = () => {
    if (voiceLoopEnabledRef.current && voiceLoopP2RefreshAfterGenerationRef.current !== null) {
      setP2RecoveryEpoch(epoch => epoch + 1);
      return true;
    }
    return false;
  };

  const requestVoiceLoopP2Refresh = () => {
    if (voiceLoopP2RefreshAfterGenerationRef.current === null || voiceLoopP2RefreshInFlightRef.current) return;
    voiceLoopP2RefreshInFlightRef.current = true;
    setP2RecoveryEpoch(epoch => epoch + 1);
  };

  const settleTaskPresentationFailure = (
    retained: NonNullable<typeof pendingPresentationAttemptRef.current>,
    failureReason: ProductTaskPresentationFailureReason,
  ): Promise<void> => {
    const ownsForeground = () => retained.native_foreground_epoch === nativeForegroundEpochRef.current;
    const updateForegroundReason = (value: Parameters<typeof setProductTextReason>[0]) => { if (ownsForeground()) setProductTextReason(value); };
    const updateForegroundStatus = (value: Parameters<typeof setProductTextStatus>[0]) => { if (ownsForeground()) setProductTextStatus(value); };
    const publishForegroundDiagnostic = (value: Parameters<typeof publishProductRecoveryDiagnostic>[0]) => { if (ownsForeground()) publishProductRecoveryDiagnostic(value); };
    const taskNotification = retained.task_notification;
    if (taskNotification === null || retained.input.surface !== 'audio') {
      return Promise.reject(new Error('only Task AUDIO presentation can report playout failure'));
    }
    if (retained.failure_reason !== undefined && retained.failure_reason !== failureReason) {
      return Promise.reject(new Error('Task presentation failure reason cannot be rewritten'));
    }
    retained.failure_reason = failureReason;
    retained.markPlayoutSettled();
    if (retained.settlement) return retained.settlement;
    const owner = retained.owner;
    const ownerSession = owner.snapshot().binding?.session_id;
    const isCurrentOwner = () =>
      mountedRef.current &&
      activationOwnerRef.current === owner &&
      ownerSession !== undefined &&
      activeSessionRef.current === ownerSession &&
      pendingPresentationAttemptRef.current === retained;
    const continueAfterSettlement = () => {
      if (retained.notification_repoll_before_capture) {
        setP2NotificationWakeEpoch(epoch => epoch + 1);
        return;
      }
      if (!continuePendingVoiceLoopP2Refresh()) scheduleProductVoiceLoopCapture();
    };
    let settlement: Promise<void>;
    settlement = Promise.resolve()
      .then(() =>
        retryRetainedProductOperation({
          operation: async () => {
            try {
              return await owner.failTaskPresentation({
                response_id: retained.input.response_id,
                response_generation: retained.input.response_generation,
                surface: 'audio',
                unit_id: retained.input.unit_id,
                failure_reason: failureReason,
              });
            } catch (error) {
              if (isCurrentOwner() && isRetriableProductOperationError(error)) {
                const reason = stableProductTextReason(error, 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED');
                updateForegroundReason(reason);
                updateForegroundStatus('failed');
                publishForegroundDiagnostic({
                  seam: 'tts',
                  disposition: 'retrying',
                  reason,
                  binding: owner.snapshot().binding,
                  response: retained.response,
                });
              }
              throw error;
            }
          },
          is_current: isCurrentOwner,
        }),
      )
      .then(() => {
        if (!isCurrentOwner()) return;
        retained.release_notification_capture?.();
        if (activeVoiceResponseRef.current?.response_id === retained.response.response_id) {
          activeVoiceResponseRef.current = null;
        }
        pendingPresentationAttemptRef.current = null;
        setPendingPresentationAck(null);
        updateForegroundReason(null);
        updateForegroundStatus(foregroundTextStatusAfterSettlement());
        // presentation.failed only proves that AUDIO was not delivered. Even
        // for a terminal event, notification completion belongs exclusively to
        // the subsequently rendered and ACKed TEXT fallback.
        const repollBeforeCapture = Boolean(retained.notification_repoll_before_capture);
        taskAudioRepollBeforeCaptureTaskIdRef.current = repollBeforeCapture ? taskNotification.task_id : null;
        terminalAnnouncementSpeechOwnerRef.current = null;
        updateTerminalAnnouncementState(
          repollBeforeCapture ? 'fetching' : 'idle',
          repollBeforeCapture ? taskNotification.task_id : null,
        );
        clearProductRecoveryDiagnostic({
          seam: 'tts',
          binding: owner.snapshot().binding,
          response: retained.response,
        });
        continueAfterSettlement();
      })
      .catch(error => {
        if (!isCurrentOwner()) return;
        const reason = stableProductTextReason(error, 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED');
        if (!owner.hasPendingPresentationFailure()) {
          retained.release_notification_capture?.();
          if (activeVoiceResponseRef.current?.response_id === retained.response.response_id) {
            activeVoiceResponseRef.current = null;
          }
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          terminalAnnouncementSpeechOwnerRef.current = null;
          updateTerminalAnnouncementState('idle', null);
          if (isStaleProductResponseError(error)) {
            updateForegroundReason(null);
            updateForegroundStatus(foregroundTextStatusAfterSettlement());
            clearProductRecoveryDiagnostic({
              seam: 'tts',
              binding: owner.snapshot().binding,
              response: retained.response,
            });
          } else {
            updateForegroundReason(reason);
            updateForegroundStatus('failed');
            publishForegroundDiagnostic({
              seam: 'tts',
              disposition: 'terminal',
              reason,
              binding: owner.snapshot().binding,
              response: retained.response,
            });
          }
          continueAfterSettlement();
          return;
        }
        updateForegroundReason(reason);
        updateForegroundStatus('failed');
        publishForegroundDiagnostic({
          seam: 'tts',
          disposition: 'retrying',
          reason,
          binding: owner.snapshot().binding,
          response: retained.response,
        });
        setP2RecoveryEpoch(epoch => epoch + 1);
      })
      .finally(() => {
        if (retained.settlement === settlement) retained.settlement = undefined;
      });
    retained.settlement = settlement;
    return settlement;
  };

  const clearScheduledProductP2Recovery = () => {
    const scheduled = productP2RecoveryTimerRef.current;
    if (scheduled === null) return;
    globalThis.clearTimeout(scheduled.timer);
    productP2RecoveryTimerRef.current = null;
  };

  const scheduleProductP2Recovery = (
    sessionId: string,
    binding: Readonly<ProductWebP2ActivationBinding>,
    journal: ProductP2ActivationJournal,
  ) => {
    try {
      const snapshot = journal.refresh();
      if (
        snapshot.phase === 'active' ||
        snapshot.phase === 'closed' ||
        snapshot.binding === null ||
        !sameProductP2ActivationBinding(snapshot.binding, binding)
      ) {
        return;
      }
    } catch {
      return;
    }
    const scheduled = productP2RecoveryTimerRef.current;
    if (
      scheduled !== null &&
      scheduled.session_id === sessionId &&
      scheduled.journal === journal &&
      sameProductP2ActivationBinding(scheduled.binding, binding)
    ) {
      return;
    }
    clearScheduledProductP2Recovery();
    const timer = globalThis.setTimeout(() => {
      if (productP2RecoveryTimerRef.current?.timer === timer) {
        productP2RecoveryTimerRef.current = null;
      }
      if (
        !mountedRef.current ||
        activeSessionRef.current !== sessionId ||
        p2ActivationJournalRef.current !== journal
      ) {
        return;
      }
      try {
        const snapshot = journal.refresh();
        if (
          snapshot.phase === 'active' ||
          snapshot.phase === 'closed' ||
          snapshot.binding === null ||
          !sameProductP2ActivationBinding(snapshot.binding, binding)
        ) {
          return;
        }
      } catch {
        return;
      }
      setP2RecoveryEpoch(epoch => epoch + 1);
    }, 1000);
    productP2RecoveryTimerRef.current = { timer, session_id: sessionId, binding, journal };
  };

  const settleDeferredTaskPresentationFailure = (owner: ProductWebP2ActivationOwner) => {
    const retained = currentDeferredTaskPresentation(owner);
    if (retained === null || pendingPresentationAttemptRef.current !== null) return false;
    const disposition = retained.disposition;
    let markPlayoutSettled: () => void = () => undefined;
    const playoutSettlement = new Promise<void>(resolve => {
      markPlayoutSettled = resolve;
    });
    markPlayoutSettled();
    const failureAttempt: PendingProductPresentationAttempt = {
      owner,
      input: {
        ...disposition.ack,
        presented_at: new Date().toISOString(),
      },
      response: disposition.response,
      native_foreground_epoch: nativeForegroundEpochRef.current,
      playoutSettlement,
      markPlayoutSettled,
      task_notification: {
        task_id: disposition.task_id ?? '',
        disposition,
        terminal: disposition.task_notification_terminal,
        retry_count: 0,
        retry_pending: false,
      },
      notification_repoll_before_capture: true,
    };
    deferredTaskPresentationRef.current = null;
    pendingPresentationAttemptRef.current = failureAttempt;
    updateTerminalAnnouncementState('recovering');
    void settleTaskPresentationFailure(failureAttempt, 'task_audio_playout_failed');
    return true;
  };

  const scheduleCapturedTaskNotificationDeadline = (
    captured: CapturedProductTaskNotification,
    captureSettlementRequested = false,
  ) => {
    const previous = capturedTaskNotificationDeadlineRef.current;
    if (previous !== null) globalThis.clearTimeout(previous.timer);
    const timeoutMs = props.taskNotificationPlayoutTimeoutMs ?? PRODUCT_TASK_NOTIFICATION_PLAYOUT_TIMEOUT_MS;
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      throw new Error('Task notification capture deadline must be positive');
    }
    const timer = globalThis.setTimeout(() => {
      const deadline = capturedTaskNotificationDeadlineRef.current;
      if (deadline?.timer !== timer || deadline.notification !== captured) return;
      capturedTaskNotificationDeadlineRef.current = null;
      if (
        !mountedRef.current ||
        activationOwnerRef.current !== captured.owner ||
        captured.owner.snapshot().binding?.session_id !== activeSessionRef.current ||
        !ownsVoiceProgressTask(captured.task_id)
      ) {
        clearCapturedTaskNotification(captured);
        return;
      }
      const waitForCaptureSettlement = (operation: Promise<void>) => {
        void operation.catch(() => undefined).then(() => {
          if (
            mountedRef.current &&
            voiceLoopEnabledRef.current &&
            voiceLoopGenerationRef.current === captured.admission.voice_loop_generation &&
            capturedTaskNotificationRef.current === captured &&
            activationOwnerRef.current === captured.owner &&
            captured.owner.snapshot().binding?.session_id === activeSessionRef.current &&
            ownsVoiceProgressTask(captured.task_id)
          ) {
            scheduleCapturedTaskNotificationDeadline(captured, true);
            setTerminalAnnouncementArbitrationEpoch(epoch => epoch + 1);
          }
        });
      };
      if (
        p1VoiceOwnerRef.current === captured.capture_owner &&
        p1VoiceOwnerRef.current?.status().status === 'recognizing' &&
        pendingP1VoiceStopRef.current !== null
      ) {
        // EOT can start recognition before this timer requests settlement.
        // Join that same owned operation rather than fail its parked AUDIO.
        waitForCaptureSettlement(pendingP1VoiceStopRef.current);
        return;
      }
      const deadlineAction = capturedTaskNotificationDeadlineAction({
        capture_settlement_requested: deadline.capture_settlement_requested,
        p1_status: p1VoiceOwnerRef.current?.status().status ?? null,
        announcement_state: terminalAnnouncementStateRef.current,
        capture_binding_available: p1VoiceCaptureBindingRef.current !== null,
        // A notification deadline may fall back to durable text, but cannot
        // manufacture an EOT in the foreground user's listening window.
        foreground_pending: pendingUnifiedFinalRef.current !== null ||
          pendingForegroundPresentationRef.current !== null || generationCaptureRef.current !== null,
      });
      if (deadlineAction === 'settle_capture') {
        // A speech-marked capture may legitimately own a user utterance when a
        // Task AUDIO notification arrives.  Settle that utterance through the
        // existing recognition/submit path once before abandoning audio. Its
        // Provider final/batch fallback already owns bounded timeouts; starting
        // another 15-second acquisition clock concurrently misclassifies that
        // still-owned recognition as a Task playout failure. Start the second
        // acquisition window only after recognition/submit has settled.
        waitForCaptureSettlement(stopP1VoiceHandlerRef.current());
        return;
      }
      if (!clearCapturedTaskNotification(captured)) return;
      // notification.next is pop-on-read. A Task AUDIO delivery may therefore
      // not remain parked forever behind speech-active capture rotations: once
      // the capture has received one bounded settlement opportunity and the
      // second acquisition window expires, report the exact AUDIO failure so
      // the Registry can publish its durable TEXT fallback.
      retainDeferredTaskPresentation(captured.owner, captured.disposition);
      if (!settleDeferredTaskPresentationFailure(captured.owner)) {
        setP2NotificationWakeEpoch(epoch => epoch + 1);
      }
    }, timeoutMs);
    capturedTaskNotificationDeadlineRef.current = Object.freeze({
      timer,
      notification: captured,
      capture_settlement_requested: captureSettlementRequested,
    });
  };

  const settleProductPresentationAck = (retained: NonNullable<typeof pendingPresentationAttemptRef.current>): Promise<void> => {
    if (retained.unplayed_foreground_retired === true) return Promise.resolve();
    const ownsForeground = () => retained.native_foreground_epoch === nativeForegroundEpochRef.current;
    const updateForegroundReason = (value: Parameters<typeof setProductTextReason>[0]) => { if (ownsForeground()) setProductTextReason(value); };
    const updateForegroundStatus = (value: Parameters<typeof setProductTextStatus>[0]) => { if (ownsForeground()) setProductTextStatus(value); };
    const publishForegroundDiagnostic = (value: Parameters<typeof publishProductRecoveryDiagnostic>[0]) => { if (ownsForeground()) publishProductRecoveryDiagnostic(value); };
    if (retained.settlement) return retained.settlement;
    const owner = retained.owner;
    const ownerSession = owner.snapshot().binding?.session_id;
    const isCurrentOwner = () =>
      mountedRef.current &&
      activationOwnerRef.current === owner &&
      ownerSession !== undefined &&
      activeSessionRef.current === ownerSession;
    const isCurrentPresentationOwner = () =>
      isCurrentOwner() &&
      pendingPresentationAttemptRef.current === retained;
    const canMutateCurrentPresentationUi = () =>
      isCurrentPresentationOwner() && voiceLoopP2RefreshAfterGenerationRef.current === null;
    let ackAttemptStarted = false;
    const canAttemptPresentationAck = () =>
      retained.unplayed_foreground_retired !== true &&
      isCurrentPresentationOwner() &&
      (voiceLoopP2RefreshAfterGenerationRef.current === null || !ackAttemptStarted);
    let settlement: Promise<void>;
    settlement = Promise.resolve()
      .then(() => retryRetainedProductOperation({
        operation: async () => {
          ackAttemptStarted = true;
          try {
            return await owner.acknowledgePresentation(retained.input);
          } catch (error) {
            if (canMutateCurrentPresentationUi() && isRetriableProductOperationError(error)) {
              const reason = stableProductTextReason(error, 'PRODUCT_PRESENTATION_ACK_RECOVERY_REQUIRED');
              updateForegroundReason(reason);
              updateForegroundStatus('failed');
              publishForegroundDiagnostic({
                seam: 'presentation_ack',
                disposition: 'retrying',
                reason,
                binding: owner.snapshot().binding,
                response: retained.response,
              });
            }
            throw error;
          }
        },
        is_current: canAttemptPresentationAck,
      }))
      .then(() => {
        recordAudioDiagnostic('presentation_acknowledged', { ...owner.snapshot().binding, ...retained.response,
          task_id: retained.task_notification?.task_id ?? null, unit_id: retained.input.unit_id, outcome: 'acknowledged' });
        const currentPresentation = pendingPresentationAttemptRef.current;
        if (
          isCurrentPresentationOwner() &&
          currentPresentation === retained &&
          sameProductPresentation(currentPresentation.input, retained.input)
        ) {
          const mayMutateUi = canMutateCurrentPresentationUi();
          retained.release_notification_capture?.();
          pendingPresentationAttemptRef.current = null;
          const activeResponse = activeVoiceResponseRef.current;
          if (activeResponse?.interaction_id === retained.response.interaction_id &&
              activeResponse.response_id === retained.response.response_id &&
              activeResponse.response_generation === retained.response.response_generation) {
            activeVoiceResponseRef.current = null;
          }
          setPendingPresentationAck(null);
          if (!mayMutateUi) {
            continuePendingVoiceLoopP2Refresh();
            return;
          }
          const taskNotification = retained.task_notification;
          const repollBeforeCapture = Boolean(
            retained.notification_repoll_before_capture && taskNotification !== null && !taskNotification.terminal,
          );
          if (taskNotification !== null) {
            taskAudioRepollBeforeCaptureTaskIdRef.current = repollBeforeCapture ? taskNotification.task_id : null;
            retainBoundedPresentedProductResponse(presentedProductResponsesRef.current, retained.input.response_id);
            if (taskNotification.terminal) {
              terminalNotificationTaskIdRef.current = taskNotification.task_id;
              markVoiceTaskTerminalPresented(taskNotification.task_id);
            }
            terminalAnnouncementSpeechOwnerRef.current = null;
            updateTerminalAnnouncementState(
              repollBeforeCapture ? 'fetching' : 'idle',
              repollBeforeCapture ? taskNotification.task_id : null,
            );
          }
          if (
            foregroundPresentationFenceMatchesResponse(
              pendingForegroundPresentationRef.current,
              owner.snapshot().binding,
              retained.response,
            )
          ) {
            // The lease ends only after playAgentText has emitted its media
            // receipt and the exact P2 Presentation ACK has succeeded. Any
            // retained Task fallback is released/settled immediately below,
            // before the next capture can be scheduled.
            pendingForegroundPresentationRef.current = null;
            if (terminalAnnouncementStateRef.current === 'fetching' &&
                capturedTaskNotificationRef.current === null) {
              taskAudioRepollBeforeCaptureTaskIdRef.current = null;
              updateTerminalAnnouncementState('idle', null);
            }
          }
          updateForegroundReason(null);
          updateForegroundStatus(foregroundTextStatusAfterSettlement());
          clearProductRecoveryDiagnostic({
            seam: 'presentation_ack',
            binding: owner.snapshot().binding,
            response: retained.input,
          });
          if (
            !settleDeferredTaskPresentation(owner) &&
            !continuePendingVoiceLoopP2Refresh()
          ) {
            if (repollBeforeCapture) setP2NotificationWakeEpoch(epoch => epoch + 1);
            else scheduleProductVoiceLoopCapture();
          }
        }
      })
      .catch(error => {
        if (isCurrentPresentationOwner()) {
          const mayMutateUi = canMutateCurrentPresentationUi();
          const reason = stableProductTextReason(error, 'PRODUCT_PRESENTATION_ACK_RECOVERY_REQUIRED');
          if (!owner.hasPendingPresentationAck()) {
            retained.release_notification_capture?.();
            pendingPresentationAttemptRef.current = null;
            setPendingPresentationAck(null);
            if (!mayMutateUi) return;
            if (isStaleProductResponseError(error)) {
              // A newer committed utterance already owns the response lane.
              // The predecessor ACK is definitively obsolete, not a voice
              // recovery failure; keep polling for the newer presentation.
              const taskNotification = retained.task_notification;
              const repollBeforeCapture = Boolean(
                retained.notification_repoll_before_capture && taskNotification !== null && !taskNotification.terminal,
              );
              taskAudioRepollBeforeCaptureTaskIdRef.current = repollBeforeCapture ? taskNotification?.task_id ?? null : null;
              if (taskNotification !== null) {
                // Playout already completed before this ACK.  Remember that
                // exact current-Task announcement locally so a server replay
                // cannot speak or ACK it twice, then release the foreground
                // response lane from the predecessor's `acking` state.
                retainBoundedPresentedProductResponse(presentedProductResponsesRef.current, retained.input.response_id);
                if (taskNotification.terminal) {
                  terminalNotificationTaskIdRef.current = taskNotification.task_id;
                  markVoiceTaskTerminalPresented(taskNotification.task_id);
                }
                terminalAnnouncementSpeechOwnerRef.current = null;
                updateTerminalAnnouncementState(
                  repollBeforeCapture ? 'fetching' : 'idle',
                  repollBeforeCapture ? taskNotification.task_id : null,
                );
              }
              if (
                foregroundPresentationFenceMatchesResponse(
                  pendingForegroundPresentationRef.current,
                  owner.snapshot().binding,
                  retained.response,
                )
              ) {
                pendingForegroundPresentationRef.current = null;
              }
              updateForegroundReason(null);
              updateForegroundStatus(pendingForegroundPresentationRef.current !== null ? 'waiting' : 'acknowledged');
              clearProductRecoveryDiagnostic({
                seam: 'presentation_ack',
                binding: owner.snapshot().binding,
                response: retained.input,
              });
              if (!continuePendingVoiceLoopP2Refresh() && pendingForegroundPresentationRef.current === null) {
                if (repollBeforeCapture) setP2NotificationWakeEpoch(epoch => epoch + 1);
                else scheduleProductVoiceLoopCapture();
              }
            } else {
              updateForegroundReason(reason);
              updateForegroundStatus('failed');
              publishForegroundDiagnostic({
                seam: 'presentation_ack',
                disposition: 'terminal',
                reason,
                binding: owner.snapshot().binding,
                response: retained.response,
              });
            }
          } else if (mayMutateUi) {
            updateForegroundReason(reason);
            updateForegroundStatus('failed');
            publishForegroundDiagnostic({
              seam: 'presentation_ack',
              disposition: 'retrying',
              reason,
              binding: owner.snapshot().binding,
              response: retained.response,
            });
            setP2RecoveryEpoch(epoch => epoch + 1);
          }
        }
      })
      .finally(() => {
        if (retained.settlement === settlement) retained.settlement = undefined;
        const retiredRequestId = retiredPresentationAckOwnerRequestRef.current.get(owner);
        if (retiredRequestId !== undefined) {
          retiredPresentationAckOwnerRequestRef.current.delete(owner);
          retiredPresentationAckInFlightRef.current.delete(retiredRequestId);
          if (mountedRef.current) setRetiredPresentationAckRecoveryEpoch(epoch => epoch + 1);
        }
      });
    retained.settlement = settlement;
    return settlement;
  };

  const settleDeferredTaskPresentation = (owner: ProductWebP2ActivationOwner) => {
    const retained = currentDeferredTaskPresentation(owner);
    if (retained === null || pendingPresentationAttemptRef.current !== null) return false;
    if (retained.disposition.ack.surface === 'audio') {
      return settleDeferredTaskPresentationFailure(owner);
    }
    if (retained.disposition.ack.surface !== 'text') return false;
    const binding = owner.snapshot().binding;
    if (binding === null || !voiceLoopEnabledRef.current) return false;
    // notification.next is pop-on-read, so this TEXT response is older than
    // the foreground response that just settled. ACKing it here would claim a
    // presentation that never reached UI, history or TTS. Retire the exact P2
    // owner instead; the Registry keeps the unacknowledged terminal fact and
    // rebinds it to the successor response generation for normal presentation.
    deferredTaskPresentationRef.current = null;
    voiceLoopP2RefreshCauseRef.current = 'task_redelivery';
    voiceLoopP2RefreshAfterGenerationRef.current = Math.max(
      voiceLoopP2RefreshAfterGenerationRef.current ?? binding.activation_generation,
      binding.activation_generation,
    );
    voiceLoopP2RefreshInFlightRef.current = false;
    updateTerminalAnnouncementState('queued');
    requestVoiceLoopP2Refresh();
    return true;
  };

  useEffect(() => {
    const sessionId = props.activeSessionId;
    clearScheduledProductVoiceLoopCapture();
    voiceLoopEnabledRef.current = false;
    voiceLoopGenerationRef.current += 1;
    voiceLoopP2RefreshAfterGenerationRef.current = null;
    voiceLoopP2RefreshInFlightRef.current = false;
    deferredTaskPresentationRef.current = null;
    clearCapturedTaskNotification();
    unifiedInputOwnerRef.current = null;
    submittedVoiceFinalsRef.current.clear();
    pendingUnifiedFinalRef.current = null;
    pendingForegroundPresentationRef.current = null;
    retireGenerationListening();
    // The interruption handle is deliberately kept here: while its activation
    // is still open, it is the only way the exact owner that issued the request
    // can still settle it. Every consumer matches on that owner, so a retired
    // handle can neither bind a successor nor fence one out of its own work,
    // and `retireOwnerGenerationInterrupt` drops it once that activation
    // closes and no replay through it is possible any more.
    interruptedProductResponsesRef.current.clear();
    localRetiredForegroundPresentationsRef.current.clear();
    p2ActivationJournalRef.current = null;
    if (!FEATURE_LIVE_VOICE_INTEGRATED_WEB || !hasDurableProductVoiceSession(sessionId)) {
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
        }),
      );
    } catch {
      setP2JournalState(
        Object.freeze({
          session_id: sessionId,
          correlation_id: fallbackCorrelationId,
          status: 'failed',
          reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
        }),
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
    ],
  );

  const prepareTerminalTaskNotification = (owner: ProductWebP2ActivationOwner,
    disposition: ProductP2NotificationDisposition) => {
    const binding = owner.snapshot().binding;
    const voiceOwner = p1VoiceOwnerRef.current;
    if (!mountedRef.current || !voiceLoopEnabledRef.current || !isConnectedRef.current ||
        activationOwnerRef.current !== owner || binding === null || activeSessionRef.current !== binding.session_id ||
        voiceOwner?.interactionEngine() !== 'openai-realtime-native' || disposition.kind !== 'presentation' ||
        !disposition.task_notification || !disposition.task_notification_terminal || disposition.ack.surface !== 'audio' ||
        !disposition.task_notification_event_key || !disposition.task_notification_text_sha256) return;
    voiceOwner.prepareTaskNotification({ response: disposition.response, unit_id: disposition.unit_id,
      text: disposition.text, event_key: disposition.task_notification_event_key,
      text_sha256: disposition.task_notification_text_sha256 });
  };

  const adoptProductP2Notification = (
    owner: ProductWebP2ActivationOwner,
    notification: Readonly<Record<string, unknown>>,
    admission: ProductP2NotificationAdmission | null = null,
  ) => {
    const response = recordValue(notification.response);
    const responseId = typeof response?.response_id === 'string' ? response.response_id : null;
    const disposition = classifyProductP2Notification(notification, responseId !== null && presentedProductResponsesRef.current.has(responseId));
    const presentationBinding = owner.snapshot().binding;
    const isTaskNotification = disposition.kind === 'presentation' && disposition.task_notification;
    if (
      admission !== null &&
      (voiceLoopP2RefreshAfterGenerationRef.current !== null ||
        (voiceLoopGenerationRef.current !== admission.voice_loop_generation &&
          (!isTaskNotification || !voiceLoopEnabledRef.current)))
    ) {
      // Exit and P2 refresh retire the entire poll admission before any UI,
      // history, TTS or ACK effect. The durable route may replay the
      // notification to the exact successor owner after cleanup completes.
      // A trusted Task notification belongs to the current P2/task authority,
      // not to one microphone capture generation, so a normal idle-capture
      // rotation must not discard it while that owner remains current.
      return disposition;
    }
    const interruptedResponse =
      disposition.kind === 'failed'
        ? disposition.response ?? null
        : disposition.kind === 'native_audio' || (disposition.kind === 'presentation' && !disposition.task_notification)
          ? disposition.response
          : null;
    if (
      interruptedResponse !== null &&
      (interruptedProductResponsesRef.current.has(productResponseGenerationIdentity(interruptedResponse)) ||
        (presentationBinding !== null && localRetiredForegroundPresentationsRef.current.has(
          productForegroundPresentationIdentity(presentationBinding, interruptedResponse),
        )))
    ) {
      // The speaker already interrupted this exact answer. Its expected
      // cancellation terminal and any late output belong to the predecessor,
      // so neither may fail, render, speak, acknowledge or reach history in
      // the replacement turn. Ignored Native audio still releases the poll.
      if (disposition.kind === 'native_audio') setP2NotificationWakeEpoch(epoch => epoch + 1);
      return disposition;
    }
    if (disposition.kind === 'native_work_state') {
      if (p1VoiceOwnerRef.current?.interactionEngine() !== 'openai-realtime-native' ||
          activationOwnerRef.current !== owner || !voiceLoopEnabledRef.current || !mountedRef.current ||
          activeSessionRef.current !== disposition.session_id || !nativeWorkBindingMatches(disposition, presentationBinding) ||
          !nativeWorkSnapshotAdvances(nativeWorkStateRef.current, disposition)) return disposition;
      const prior = nativeWorkStateRef.current;
      nativeWorkStateRef.current = disposition;
      setNativeWorkState(disposition);
      for (const work of disposition.works) {
        if (prior !== null && nativeWorkBindingMatches(prior, disposition) &&
            prior.works.some(item => item.work_id === work.work_id && item.sequence === work.sequence)) continue;
        recordAudioDiagnostic('native_work_state', {
          ...presentationBinding, work_id: work.work_id, revision_number: work.revision, work_version: work.sequence,
          status: work.state, seq: disposition.sequence,
        });
      }
      return disposition;
    }
    if (disposition.kind === 'native_request_state') {
      if (p1VoiceOwnerRef.current?.interactionEngine() !== 'openai-realtime-native' ||
        presentationBinding === null || activationOwnerRef.current !== owner || !voiceLoopEnabledRef.current ||
        presentationBinding.session_id !== disposition.session_id || presentationBinding.correlation_id !== disposition.correlation_id ||
        presentationBinding.interaction_id !== disposition.interaction_id || presentationBinding.activation_id !== disposition.activation_id ||
        presentationBinding.activation_generation !== disposition.activation_generation) return disposition;
      const key = JSON.stringify([disposition.session_id, disposition.activation_id, disposition.activation_generation]);
      const prior = nativeRequestStateRef.current;
      if (prior?.binding === key && prior.sequence >= disposition.sequence) return disposition;
      nativeRequestStateRef.current = { binding: key, sequence: disposition.sequence, phase: disposition.phase };
      nativeForegroundEpochRef.current += 1;
      if (disposition.response !== null) retainBoundedPresentedProductResponse(interruptedProductResponsesRef.current, productResponseGenerationIdentity(disposition.response));
      recordAudioDiagnostic('native_request_state', { ...presentationBinding, turn_id: disposition.turn_id, status: disposition.phase,
        reason: disposition.reason, seq: disposition.sequence });
      if (disposition.phase === 'failed') {
        setProductTextReason(disposition.reason);
        setProductTextStatus('failed');
        publishProductRecoveryDiagnostic({ seam: 'response_generation', disposition: 'terminal',
          reason: disposition.reason!, binding: presentationBinding, nativeTurnId: disposition.turn_id });
      } else {
        clearProductRecoveryDiagnostic();
        setProductTextReason(null);
        setProductTextStatus(disposition.phase === 'processing' ? 'waiting' : 'acknowledged');
      }
      return disposition;
    }
    if (disposition.kind === 'native_task_association') {
      const isCurrent = () => {
        const current = owner.snapshot().binding;
        return mountedRef.current && activationOwnerRef.current === owner && voiceLoopEnabledRef.current &&
          current !== null && current.session_id === disposition.session_id &&
          current.correlation_id === disposition.correlation_id && current.interaction_id === disposition.interaction_id &&
          current.activation_id === disposition.activation_id && current.activation_generation === disposition.activation_generation;
      };
      if (presentationBinding === null || !isCurrent()) return disposition;
      const taskKey = JSON.stringify([disposition.session_id, disposition.activation_id, disposition.activation_generation, disposition.task_id]);
      const operationKey = JSON.stringify([taskKey, disposition.turn_commit_id, disposition.provider_call_id]);
      if (refreshedNativeTaskOperationsRef.current.has(operationKey)) return disposition;
      retainBoundedPresentedProductResponse(refreshedNativeTaskOperationsRef.current, operationKey);
      // Discovery and operation invalidation have separate identities. A later
      // confirmed operation always rereads canonical state, without replaying it
      // or moving the user's selected Task back to an already discovered Task.
      nativeTaskDiscoveryRef.current = nativeTaskDiscoveryRef.current.catch(() => undefined).then(async () => {
        if (!isCurrent()) return;
        const discovered = discoveredNativeTasksRef.current.has(taskKey);
        let refreshed = false;
        const waitForRetry = props.p3RetryInspectionWait ?? defaultP3RetryInspectionWait;
        const retryAbort = new AbortController();
        for (let attempt = 0; attempt <= PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS.length; attempt += 1) {
          if (!isCurrent()) return;
          try {
            await refreshUnifiedTaskProjection({ result: { task_id: disposition.task_id } }, disposition.session_id, isCurrent, !discovered);
            if (!isCurrent()) return;
            refreshed = true;
            break;
          } catch {
            if (!isCurrent()) return;
            if (attempt < PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS.length)
              await waitForRetry(PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS[attempt]!, retryAbort.signal);
          }
        }
        if (!isCurrent()) return;
        recordAudioDiagnostic('task_projection_refresh', { ...presentationBinding, task_id: disposition.task_id,
          turn_commit_id: disposition.turn_commit_id, provider_call_id: disposition.provider_call_id,
          outcome: refreshed ? 'refreshed' : 'failed' });
        // Progress discovery remains independent of a temporarily unavailable
        // collection; a failed collection key is retryable even if bootstrap succeeds.
        let bootstrapped = discovered;
        if (!discovered) {
          try {
            bootstrapped = await bootstrapCreatedP3ProgressRoute(disposition.task_id, presentationBinding, isCurrent);
            if (bootstrapped && isCurrent()) retainBoundedPresentedProductResponse(discoveredNativeTasksRef.current, taskKey);
          } catch { /* Bootstrap publishes its own bounded read failure. */ }
        }
        if (!refreshed || !bootstrapped) refreshedNativeTaskOperationsRef.current.delete(operationKey);
      });
      return disposition;
    }

    if (disposition.kind === 'native_user_transcript') {
      if (
        presentationBinding === null ||
        presentationBinding.session_id !== disposition.session_id ||
        presentationBinding.correlation_id !== disposition.correlation_id ||
        presentationBinding.interaction_id !== disposition.interaction_id ||
        presentationBinding.activation_id !== disposition.activation_id ||
        presentationBinding.activation_generation !== disposition.activation_generation
      ) {
        return disposition;
      }
      if (!presentedNativeChatMessagesRef.current.has(disposition.message.id)) {
        retainBoundedPresentedProductResponse(
          presentedNativeChatMessagesRef.current,
          disposition.message.id,
        );
        props.onProductVoiceMessage?.(
          Object.freeze({
            session_id: disposition.session_id,
            message: disposition.message,
          }),
        );
      }
      for (const assistant of disposition.following_assistant) {
        if (presentedNativeChatMessagesRef.current.has(assistant.id)) continue;
        retainBoundedPresentedProductResponse(
          presentedNativeChatMessagesRef.current,
          assistant.id,
        );
        props.onProductVoiceMessage?.(
          Object.freeze({
            session_id: disposition.session_id,
            message: assistant,
          }),
        );
      }
      setP2NotificationWakeEpoch(epoch => epoch + 1);
      return disposition;
    }
    if (disposition.kind === 'failed') {
      const settlesForegroundPresentation = foregroundPresentationFenceMatchesResponse(
        pendingForegroundPresentationRef.current,
        presentationBinding,
        disposition.response ?? null,
      );
      if (pendingForegroundPresentationRef.current !== null && disposition.response !== undefined &&
          !settlesForegroundPresentation) {
        // A current poll can also carry a delayed predecessor failure. Keep
        // the accepted foreground and release the poll for its own response.
        setP2NotificationWakeEpoch(epoch => epoch + 1);
        return disposition;
      }
      const deferredTaskSettlementStarted = settlesForegroundPresentation
        ? settleDeferredTaskPresentation(owner)
        : false;
      if (settlesForegroundPresentation) {
        pendingForegroundPresentationRef.current = null;
        // A failed foreground response ends a one-shot post-fallback drain,
        // just like a keepalive. It does not consume the Task notification:
        // the authorized Task poll remains live during resumed listening.
        if (terminalAnnouncementStateRef.current === 'fetching' &&
            pendingPresentationAttemptRef.current === null &&
            capturedTaskNotificationRef.current === null) {
          taskAudioRepollBeforeCaptureTaskIdRef.current = null;
          updateTerminalAnnouncementState('idle', null);
        }
      }
      // The generation-time listening window is bound to the exact response
      // that just failed. There is nothing left to interrupt or replace, so
      // leaving it behind would refuse the next answer its own window for the
      // rest of the session and keep a capture that answers to nothing holding
      // the notification-poll privilege.
      if (
        retireGenerationListening(listening =>
          foregroundPresentationFenceMatchesResponse(
            listening.fence,
            presentationBinding,
            disposition.response ?? null,
          ),
        )
      ) {
        void settleCaptureBeforePlayout().catch(() => undefined);
      }
      const reason = stableProductTextReason(disposition.reason, 'PRODUCT_AGENT_OUTPUT_FAILED');
      setProductTextReason(reason);
      setProductTextStatus('failed');
      publishProductRecoveryDiagnostic({
        seam: 'response_generation',
        disposition: 'terminal',
        reason,
        binding: presentationBinding,
        response: disposition.response ?? null,
      });
      if (!deferredTaskSettlementStarted && !continuePendingVoiceLoopP2Refresh()) {
        scheduleProductVoiceLoopCapture();
      }
      return disposition;
    }
    if (disposition.kind === 'native_audio') {
      const foregroundFence = pendingForegroundPresentationRef.current;
      const ownsForegroundResponse = foregroundPresentationFenceMatchesResponse(
        foregroundFence,
        presentationBinding,
        disposition.response,
      );
      const expectedForegroundResponse = admission?.foreground_presentation ?? null;
      if (
        (expectedForegroundResponse !== null || foregroundFence !== null) &&
        (foregroundFence !== expectedForegroundResponse || !ownsForegroundResponse)
      ) {
        return disposition;
      }
      if (ownsForegroundResponse) pendingForegroundPresentationRef.current = null;
      const voiceOwner = p1VoiceOwnerRef.current;
      const taskAttempt = pendingPresentationAttemptRef.current;
      if (voiceOwner !== null && voiceOwner.interactionEngine() === 'openai-realtime-native' &&
          taskAttempt?.task_notification && taskAttempt.owner === owner &&
          taskAttempt.input.surface === 'audio') {
        // The exact local stop establishes its audio fence synchronously.
        // Task failure/consumption settlement must not block the Native downlink.
        voiceOwner.yieldNativeTaskNotification(taskAttempt.response);
        if (!mountedRef.current || activationOwnerRef.current !== owner ||
            p1VoiceOwnerRef.current !== voiceOwner || activeSessionRef.current !== presentationBinding?.session_id) return disposition;
      }
      if (
        voiceOwner === null ||
        voiceOwner.interactionEngine() !== 'openai-realtime-native' ||
        voiceOwner.status().status !== 'capturing'
      ) {
        const reason = 'PRODUCT_NATIVE_AUDIO_OWNER_UNAVAILABLE';
        setProductTextReason(reason);
        setProductTextStatus('failed');
        publishProductRecoveryDiagnostic({
          seam: 'response_generation',
          disposition: 'terminal',
          reason,
          binding: presentationBinding,
          response: disposition.response,
        });
        setP2NotificationWakeEpoch(epoch => epoch + 1);
        return disposition;
      }
      nativeForegroundEpochRef.current += 1;
      const playoutLoopGeneration = voiceLoopGenerationRef.current;
      const isCurrentNativePlayout = () =>
        mountedRef.current &&
        activationOwnerRef.current === owner &&
        presentationBinding !== null &&
        activeSessionRef.current === presentationBinding.session_id &&
        voiceLoopGenerationRef.current === playoutLoopGeneration &&
        p1VoiceOwnerRef.current === voiceOwner &&
        !interruptedProductResponsesRef.current.has(productResponseGenerationIdentity(disposition.response)) &&
        !localRetiredForegroundPresentationsRef.current.has(
          productForegroundPresentationIdentity(presentationBinding, disposition.response),
        );
      activeVoiceResponseRef.current = disposition.response;
      setProductTextReason(null);
      setProductTextStatus('waiting');
      void voiceOwner.playNativeAudio({
        response: disposition.response,
        presentation_unit: disposition.presentation_unit,
        audio: disposition.audio,
      }).then(chatProjection => {
        if (activeVoiceResponseRef.current?.response_id === disposition.response_id) {
          activeVoiceResponseRef.current = null;
        }
        if (presentationBinding === null || !isCurrentNativePlayout()) return;
        if (
          chatProjection !== null &&
          !presentedNativeChatMessagesRef.current.has(chatProjection.id)
        ) {
          retainBoundedPresentedProductResponse(
            presentedNativeChatMessagesRef.current,
            chatProjection.id,
          );
          props.onProductVoiceMessage?.(
            Object.freeze({
              session_id: presentationBinding.session_id,
              message: chatProjection,
            }),
          );
        }
        setProductTextStatus('acknowledged');
        clearProductRecoveryDiagnostic({
          seam: 'response_generation',
          binding: presentationBinding,
          response: disposition.response,
        });
        setP2NotificationWakeEpoch(epoch => epoch + 1);
      }).catch(error => {
        if (activeVoiceResponseRef.current?.response_id === disposition.response_id) {
          activeVoiceResponseRef.current = null;
        }
        if (!isCurrentNativePlayout()) return;
        if (hasExactNativeTerminalFailure(presentationBinding)) {
          setP2NotificationWakeEpoch(epoch => epoch + 1);
          return;
        }
        const reason = stableProductTextReason(error, 'PRODUCT_NATIVE_AUDIO_PLAYOUT_FAILED');
        setProductTextReason(reason);
        setProductTextStatus('failed');
        publishProductRecoveryDiagnostic({
          seam: 'response_generation',
          disposition: 'terminal',
          reason,
          binding: presentationBinding,
          response: disposition.response,
        });
        setP2NotificationWakeEpoch(epoch => epoch + 1);
      });
      return disposition;
    }
    if (disposition.kind !== 'presentation') {
      if (
        voiceLoopEnabledRef.current &&
        terminalNotificationCheckRequiredRef.current &&
        pendingForegroundPresentationRef.current === null
      ) {
        scheduleProductVoiceLoopCapture();
      }
      return disposition;
    }
    prepareTerminalTaskNotification(owner, disposition);
    if (
      disposition.task_notification &&
      (pendingUnifiedFinalRef.current !== null ||
        (pendingForegroundPresentationRef.current !== null &&
          !foregroundPresentationFenceMatchesResponse(
            pendingForegroundPresentationRef.current,
            presentationBinding,
            disposition.response,
          )))
    ) {
      // This poll completed after a newer authoritative voice final took the
      // foreground, either while unified.submit was assigning its response or
      // after the exact response fence was retained. The P2 owner has already
      // dequeued this durable Task presentation, so retain its exact identity
      // locally without UI, TTS, ACK or history effects. AUDIO alone has the
      // immediate failure authority while the foreground is busy: the Registry
      // retains its safe TEXT fallback, and the authoritative foreground ACK
      // releases that one deferred server presentation. A legitimate Task
      // TEXT remains unacknowledged; foreground settlement retires this P2
      // owner so the Registry can rebind the terminal fact to a successor for
      // normal UI, TTS and ACK. In particular, Task fallback must not enter
      // playAgentText and fail the P1 owner leased by the foreground response.
      retainDeferredTaskPresentation(owner, disposition);
      if (disposition.ack.surface === 'audio' && !settleDeferredTaskPresentationFailure(owner)) {
        setP2NotificationWakeEpoch(epoch => epoch + 1);
      }
      return disposition;
    }
    if (!disposition.task_notification && terminalAnnouncementStateRef.current === 'fetching' && terminalAnnouncementTaskIdRef.current !== null) {
      updateTerminalAnnouncementState('queued');
    }
    const pending = pendingPresentationAttemptRef.current;
    if (pending !== null) {
      if (pending.owner !== owner || pending.input.response_id !== disposition.response_id) {
        throw new Error('a previous presentation ACK is still unresolved');
      }
      // Multiple effect continuations may share one pop-on-read notification
      // result. Once its exact attempt owns UI, TTS and ACK, a coalesced replay
      // must have zero duplicate projection, synthesis or settlement effects.
      return disposition;
    }
    const foregroundPresentationFence = pendingForegroundPresentationRef.current;
    const ownsForegroundPresentation = foregroundPresentationFenceMatchesResponse(
      foregroundPresentationFence,
      presentationBinding,
      disposition.response,
    );
    if (!disposition.task_notification) {
      const expectedForegroundPresentation = admission?.foreground_presentation ?? null;
      const requiresForegroundPresentation =
        expectedForegroundPresentation !== null || foregroundPresentationFence !== null;
      const exactForegroundPresentationRetained =
        expectedForegroundPresentation === null || foregroundPresentationFence === expectedForegroundPresentation;
      if (
        requiresForegroundPresentation &&
        (!exactForegroundPresentationRetained || !ownsForegroundPresentation)
      ) {
        // A foreground voice result is admitted only by the exact retained
        // response fence. Text-only P2 presentations have no such fence and
        // remain available while Live Voice is idle.
        return disposition;
      }
      retainBoundedPresentedProductResponse(presentedProductResponsesRef.current, disposition.response_id);
    }
    setProductOutput(disposition.text);
    const presentedAt = new Date().toISOString();
    if (presentationBinding !== null && disposition.history_message_id !== null) {
      props.onProductVoiceMessage?.(
        Object.freeze({
          session_id: presentationBinding.session_id,
          message: Object.freeze({
            id: disposition.history_message_id,
            role: 'assistant',
            content: disposition.text,
            timestamp: presentedAt,
            ...(disposition.task_notification_event_key ? { taskNotification: {
              eventKey: disposition.task_notification_event_key,
              presentation: disposition.ack.surface === 'text' ? 'text' as const : 'preview' as const,
            } } : {}),
          }),
        }),
      );
    }
    if (disposition.task_notification) {
      setTerminalNotification(disposition.text);
    }
    if (disposition.adjustment_notification) setAdjustmentNotification(disposition.text);
    setProductTextStatus('presented');
    setProductTextReason(null);
    clearProductRecoveryDiagnostic({
      seam: 'response_generation',
      binding: presentationBinding,
      response: disposition.response,
    });
    if (pendingPresentationAttemptRef.current === null) {
      let markPlayoutSettled: () => void = () => undefined;
      const playoutSettlement = new Promise<void>(resolve => {
        markPlayoutSettled = resolve;
      });
      pendingPresentationAttemptRef.current = {
        owner,
        input: {
          ...disposition.ack,
          presented_at: presentedAt,
        },
        response: disposition.response,
        native_foreground_epoch: nativeForegroundEpochRef.current,
        playoutSettlement,
        markPlayoutSettled,
        task_notification: disposition.task_notification
          ? {
              task_id: disposition.task_id ?? '',
              disposition,
              terminal: disposition.task_notification_terminal,
              retry_count: 0,
              retry_pending: false,
            }
          : null,
        notification_repoll_before_capture:
          disposition.task_notification &&
          !disposition.task_notification_terminal &&
          terminalAnnouncementStateRef.current === 'fetching',
      };
    }
    const presentationAttempt = pendingPresentationAttemptRef.current;
    if (presentationAttempt === null) throw new Error('presentation ACK owner was not retained');
    const foregroundPlayoutLease = ownsForegroundPresentation ? foregroundPresentationFence : null;
    const playoutLoopGeneration = foregroundPlayoutLease?.voice_loop_generation ?? voiceLoopGenerationRef.current;
    activeVoiceResponseRef.current = disposition.replayed && !disposition.task_notification ? null : disposition.response;
    const isCurrentPresentationAttempt = () =>
      mountedRef.current &&
      presentationBinding !== null &&
      activationOwnerRef.current === owner &&
      activeSessionRef.current === presentationBinding.session_id &&
      pendingPresentationAttemptRef.current === presentationAttempt &&
      presentationAttempt.owner === owner &&
      presentationAttempt.response.response_id === disposition.response_id &&
      presentationAttempt.response.response_generation === disposition.response.response_generation &&
      owner.authorizesMediaStart(presentationBinding);
    const isCurrentVoicePlayout = () =>
      isCurrentPresentationAttempt() &&
      voiceLoopEnabledRef.current &&
      voiceLoopGenerationRef.current === playoutLoopGeneration &&
      (foregroundPlayoutLease === null ||
        (pendingForegroundPresentationRef.current === foregroundPlayoutLease &&
          foregroundPlayoutLease.playout_owner !== null &&
          p1VoiceOwnerRef.current === foregroundPlayoutLease.playout_owner));
    const foregroundLeaseRetiredByExit = () =>
      foregroundPlayoutLease !== null &&
      pendingForegroundPresentationRef.current !== foregroundPlayoutLease &&
      (!voiceLoopEnabledRef.current || voiceLoopGenerationRef.current !== foregroundPlayoutLease.voice_loop_generation);
    const retainAck = (playoutFailed = false) => {
      presentationAttempt.markPlayoutSettled();
      if (!isCurrentPresentationAttempt()) return;
      if (playoutFailed) setProductTextStatus('failed');
      if (presentationAttempt.task_notification != null) updateTerminalAnnouncementState('acking');
      setPendingPresentationAck(disposition.ack);
      void settleProductPresentationAck(presentationAttempt);
    };
    if (disposition.task_notification && disposition.ack.surface === 'text') {
      // The Task fallback is already rendered in the transcript. It must not
      // depend on acquiring another audio owner, otherwise one failed running
      // announcement can still block every later terminal notification.
      if (activeVoiceResponseRef.current?.response_id === disposition.response_id) {
        activeVoiceResponseRef.current = null;
      }
      retainAck();
      return disposition;
    }
    const voiceOwner = foregroundPlayoutLease !== null
      ? foregroundPlayoutLease.playout_owner
      : p1VoiceOwnerRef.current;
    if (
      foregroundPlayoutLease !== null &&
      (voiceOwner === null ||
        p1VoiceOwnerRef.current !== voiceOwner ||
        voiceLoopGenerationRef.current !== foregroundPlayoutLease.voice_loop_generation)
    ) {
      presentationAttempt.unplayed_foreground_retired = true;
      if (presentationBinding !== null) retainBoundedPresentedProductResponse(
        localRetiredForegroundPresentationsRef.current,
        productForegroundPresentationIdentity(presentationBinding, disposition.response),
      );
      presentationAttempt.markPlayoutSettled();
      if (activeVoiceResponseRef.current?.response_id === disposition.response_id) {
        activeVoiceResponseRef.current = null;
      }
      const reason = 'PRODUCT_FOREGROUND_PLAYOUT_OWNER_LOST';
      setProductTextReason(reason);
      setProductTextStatus('failed');
      publishProductRecoveryDiagnostic({
        seam: 'tts',
        disposition: 'terminal',
        reason,
        binding: presentationBinding,
        response: disposition.response,
      });
      // The response remains deliberately unacknowledged. Only Exit/session
      // teardown may retire a genuinely lost foreground lease; text display is
      // not proof of the requested voice presentation.
      return disposition;
    }
    if (voiceOwner !== null && (!disposition.replayed || disposition.task_notification)) {
      if (disposition.task_notification) updateTerminalAnnouncementState('playing', disposition.task_id);
      // Clear a silent listening window before playout, and yield entirely to a
      // speaker who is mid-utterance instead of failing the route on them.
      const prepareCapture = async (): Promise<'ready' | 'speaker_active'> => {
        if (disposition.task_notification) {
          return prepareTaskNotificationCapture(voiceOwner, presentationAttempt);
        }
        return settleCaptureBeforePlayout();
      };
      void prepareCapture()
        .then(async readiness => {
          if (readiness !== 'ready') {
            throw Object.assign(new Error('playout yielded to an active speaker'), {
              reason: PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER,
            });
          }
          const playout = voiceOwner.playAgentText({
            response: disposition.response,
            unit_id: disposition.unit_id,
            text: disposition.text,
            // Task system audio must not start foreground overlap capture and
            // record its own announcement. Resume fresh listening after ACK.
            capture_during_playout: !disposition.task_notification,
          });
          // The playout deadline starts after capture settlement, never while
          // a possible user utterance or generation-listening start owns it.
          await (disposition.task_notification
            ? awaitProductTaskNotificationPlayout(
                playout,
                () => {
                  if (!isCurrentPresentationAttempt()) return;
                  void voiceOwner.close().catch(() => undefined);
                },
                props.taskNotificationPlayoutTimeoutMs,
              )
            : playout);
        })
        .then(() => {
          if (!isCurrentVoicePlayout()) {
            presentationAttempt.markPlayoutSettled();
            if (
              isCurrentPresentationAttempt() &&
              (foregroundPlayoutLease === null || foregroundLeaseRetiredByExit())
            ) retainAck();
            return;
          }
          if (activeVoiceResponseRef.current?.response_id === disposition.response_id) {
            activeVoiceResponseRef.current = null;
          }
          clearProductRecoveryDiagnostic({
            seam: 'tts',
            binding: presentationBinding,
            response: disposition.response,
          });
          retainAck();
        })
        .catch(error => {
          if (foregroundPlayoutLease !== null && playoutDeferredToSpeaker(error) &&
              isCurrentVoicePlayout() && presentationBinding !== null) {
            // A new utterance owns this capture. Retire only the unplayed old
            // answer before waking any settlement waiter, preserving that owner.
            presentationAttempt.unplayed_foreground_retired = true;
            retainBoundedPresentedProductResponse(localRetiredForegroundPresentationsRef.current,
              productForegroundPresentationIdentity(presentationBinding, disposition.response));
            if (pendingPresentationAttemptRef.current === presentationAttempt) pendingPresentationAttemptRef.current = null;
            if (pendingForegroundPresentationRef.current === foregroundPlayoutLease) pendingForegroundPresentationRef.current = null;
            if (activeVoiceResponseRef.current?.response_id === disposition.response_id &&
                activeVoiceResponseRef.current.response_generation === disposition.response.response_generation) {
              activeVoiceResponseRef.current = null;
            }
            setPendingPresentationAck(null);
            presentationAttempt.markPlayoutSettled();
            setProductTextReason(PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER);
            setProductTextStatus('presented');
            setP2NotificationWakeEpoch(epoch => epoch + 1);
            return;
          }
          if (disposition.task_notification && playoutDeferredToSpeaker(error)) {
            // Standing down is not a playout failure and must be decided before
            // anything settles: settling the playout here would let cleanup
            // acknowledge an announcement that was never spoken. The retained
            // attempt is the only identity that matters here -- media start
            // authority is not required to *not* play something.
            deferTaskAnnouncementToSpeaker(presentationAttempt, voiceOwner);
            return;
          }
          if (foregroundPlayoutLease !== null) {
            presentationAttempt.unplayed_foreground_retired = true;
            if (presentationBinding !== null) retainBoundedPresentedProductResponse(
              localRetiredForegroundPresentationsRef.current,
              productForegroundPresentationIdentity(presentationBinding, disposition.response),
            );
          }
          // Foreground failure keeps its settlement barrier until the exact P1
          // close has retired the foreground fence. Otherwise a concurrent P2
          // recovery can rotate owners first and strand that fence forever.
          if (foregroundPlayoutLease === null) presentationAttempt.markPlayoutSettled();
          if (disposition.task_notification && disposition.ack.surface === 'audio') {
            if (!isCurrentPresentationAttempt()) return;
            if (activeVoiceResponseRef.current?.response_id === disposition.response_id) activeVoiceResponseRef.current = null;
            const reason = stableProductTextReason(error, 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED');
            if (reason === 'FORMAL_PLAYOUT_BARGED') {
              void settleTaskPresentationFailure(presentationAttempt, 'task_audio_playout_failed');
              return;
            }
            setProductTextReason(reason);
            setProductTextStatus('failed');
            publishProductRecoveryDiagnostic({
              seam: 'tts',
              disposition: 'retrying',
              reason,
              binding: presentationBinding,
              response: disposition.response,
            });
            updateTerminalAnnouncementState('recovering');
            void settleTaskPresentationFailure(presentationAttempt, 'task_audio_playout_failed');
            return;
          }
          if (!isCurrentVoicePlayout()) {
            presentationAttempt.markPlayoutSettled();
            if (
              isCurrentPresentationAttempt() &&
              (foregroundPlayoutLease === null || foregroundLeaseRetiredByExit())
            ) retainAck();
            return;
          }
          if (activeVoiceResponseRef.current?.response_id === disposition.response_id) activeVoiceResponseRef.current = null;
          if (foregroundPlayoutLease !== null) {
            const reason = stableProductTextReason(error, 'PRODUCT_FOREGROUND_PLAYOUT_FAILED');
            setProductTextReason(reason);
            setProductTextStatus('failed');
            publishProductRecoveryDiagnostic({
              seam: 'tts',
              disposition: 'terminal',
              reason,
              binding: presentationBinding,
              response: disposition.response,
            });
            // Retire failed audio without inventing a presentation ACK. Close
            // the exact P1 owner before refreshing P2; the existing activation
            // recovery keeps detached Tasks and fences late predecessor audio.
            presentationAttempt.close_unplayed_foreground = async () => {
              await voiceOwner.close();
              if (!isCurrentVoicePlayout() || presentationBinding === null) {
                presentationAttempt.markPlayoutSettled();
                console.info(`live_voice_foreground_recovery_retired activation_current=${activationOwnerRef.current === owner} attempt_current=${pendingPresentationAttemptRef.current === presentationAttempt} foreground_current=${pendingForegroundPresentationRef.current === foregroundPlayoutLease} voice_current=${p1VoiceOwnerRef.current === voiceOwner} loop_current=${voiceLoopGenerationRef.current === playoutLoopGeneration} enabled=${voiceLoopEnabledRef.current}`);
                return;
              }
              voiceLoopP2RefreshCauseRef.current = 'active_recovery';
              voiceLoopP2RefreshAfterGenerationRef.current = presentationBinding.activation_generation;
              voiceLoopP2RefreshInFlightRef.current = false;
              pendingPresentationAttemptRef.current = null;
              pendingForegroundPresentationRef.current = null;
              if (p1VoiceOwnerRef.current === voiceOwner) p1VoiceOwnerRef.current = null;
              p1VoiceCaptureBindingRef.current = null;
              setPendingPresentationAck(null);
              presentationAttempt.markPlayoutSettled();
              requestVoiceLoopP2Refresh();
            };
            void presentationAttempt.close_unplayed_foreground().catch(() => {
              // Cleanup remains visibly failed; never acquire a successor
              // while the old media authority is unresolved.
            });
            return;
          }
          const reason = stableProductTextReason(
            error,
            disposition.task_notification
              ? 'PRODUCT_TERMINAL_ANNOUNCEMENT_RECOVERY_REQUIRED'
              : 'PRODUCT_TTS_PLAYBACK_FAILED',
          );
          publishProductRecoveryDiagnostic({
            seam: 'tts',
            disposition: disposition.task_notification ? 'retrying' : 'terminal',
            reason,
            binding: presentationBinding,
            response: disposition.response,
          });
          if (disposition.task_notification) {
            setProductTextReason(reason);
            setProductTextStatus('failed');
            updateTerminalAnnouncementState('recovering');
            retryTerminalAnnouncementHandlerRef.current(presentationAttempt);
          } else {
            setProductTextReason(reason);
            retainAck(true);
          }
        });
    } else if (disposition.task_notification && disposition.ack.surface === 'audio') {
      if (FEATURE_LIVE_VOICE_INTEGRATED_P1 && !voiceLoopEnabledRef.current) {
        // An AUDIO delivery observed while listening is off has not failed
        // playout. Retain its exact unconsumed owner until explicit Start can
        // reauthorize it against a real media owner. Exit still fences it.
        if (activeVoiceResponseRef.current?.response_id === disposition.response_id) activeVoiceResponseRef.current = null;
        updateTerminalAnnouncementState('recovering', disposition.task_id);
        return disposition;
      }
      const reason = 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED';
      presentationAttempt.markPlayoutSettled();
      setProductTextReason(reason);
      setProductTextStatus('failed');
      publishProductRecoveryDiagnostic({
        seam: 'tts',
        disposition: 'retrying',
        reason,
        binding: presentationBinding,
        response: disposition.response,
      });
      updateTerminalAnnouncementState('recovering');
      void settleTaskPresentationFailure(presentationAttempt, 'task_audio_owner_unavailable');
    } else if (disposition.task_notification) {
      const reason = 'PRODUCT_TERMINAL_ANNOUNCEMENT_RECOVERY_REQUIRED';
      setProductTextReason(reason);
      setProductTextStatus('failed');
      publishProductRecoveryDiagnostic({
        seam: 'tts',
        disposition: 'retrying',
        reason,
        binding: presentationBinding,
        response: disposition.response,
      });
      updateTerminalAnnouncementState('recovering');
      if (voiceLoopEnabledRef.current) retryTerminalAnnouncementHandlerRef.current(presentationAttempt);
    } else {
      retainAck();
    }
    return disposition;
  };

  const settleRetainedUnifiedInput = async (owner: ProductWebP2ActivationOwner) => {
    const ownerSession = owner.snapshot().binding?.session_id;
    const unified = unifiedInputOwnerRef.current;
    const isCurrent = () => activationOwnerRef.current === owner && ownerSession !== undefined &&
      activeSessionRef.current === ownerSession && unifiedInputOwnerRef.current === unified && isConnectedRef.current;
    const pendingTurn = pendingProductTurnRef.current;
    if (pendingTurn?.owner === owner) {
      try {
        const binding = owner.snapshot().binding;
        if (!binding || !unified) throw new Error('exact unified input owner unavailable');
        // A legacy synthetic Task origin is never translated into a new final.
        if (pendingTurn.input.dispatch_target === 'task') throw new Error('legacy Task origin is retired');
        const submitted = await retryRetainedProductOperation({
          operation: () => unified.submit(binding, {
            request_id: `unified-text-${pendingTurn.input.commit_id}`,
            commit_id: pendingTurn.input.commit_id, turn_id: pendingTurn.input.turn_id,
            committed_at: pendingTurn.input.committed_at, text: pendingTurn.input.text,
            input_kind: 'text',
          }),
          is_current: isCurrent,
        });
        if (!isCurrent()) return;
        if (pendingProductTurnRef.current === pendingTurn) {
          pendingProductTurnRef.current = null;
          setProductInput('');
          setProductTextStatus('waiting');
        }
        if (isCurrent()) await refreshUnifiedTaskProjection(submitted, binding.session_id, isCurrent);
      } catch (error) {
        if (!isCurrent()) return;
        if (unifiedInputOwnerRef.current?.hasPending() || owner.hasPendingSubmission() ||
            pendingTurn.input.dispatch_target === 'task') throw error;
        if (pendingProductTurnRef.current === pendingTurn) {
          pendingProductTurnRef.current = null;
          setProductTextStatus('failed');
        }
      }
    }
  };

  const settleRetainedP2Operations = async (
    owner: ProductWebP2ActivationOwner,
    options: Readonly<{ abandon_pending_notification?: boolean }> = {},
  ) => {
    const ownerSession = owner.snapshot().binding?.session_id;
    const isCurrent = () => activationOwnerRef.current === owner && ownerSession !== undefined && activeSessionRef.current === ownerSession;
    await settleRetainedUnifiedInput(owner);
    if (owner.hasPendingNotification() && options.abandon_pending_notification !== true) {
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
    if (pendingPresentation?.owner === owner && pendingPresentation.deferred_to_speaker === true) {
      // It stood down for a speaker and was never handed to TTS, so it has no
      // presentation to acknowledge. Retire it with this activation and let the
      // server-owned unread/redelivery path own it instead of inventing an ACK.
      pendingPresentation.markPlayoutSettled();
      pendingPresentationAttemptRef.current = null;
      setPendingPresentationAck(null);
      updateTerminalAnnouncementState('idle');
    } else if (pendingPresentation?.owner === owner) {
      if (pendingPresentation.unplayed_foreground_retired === true && pendingPresentation.close_unplayed_foreground) {
        await pendingPresentation.close_unplayed_foreground();
      }
      await pendingPresentation.playoutSettlement;
      // Normal playout settlement and P2 recovery share one exact retained
      // operation. A failed Task AUDIO playout reports failure; it must never
      // be converted into an accepted Presentation ACK during recovery.
      if (pendingPresentation.unplayed_foreground_retired === true) {
        if (pendingPresentationAttemptRef.current === pendingPresentation) pendingPresentationAttemptRef.current = null;
        setPendingPresentationAck(null);
      } else if (pendingPresentation.failure_reason !== undefined) {
        await settleTaskPresentationFailure(pendingPresentation, pendingPresentation.failure_reason);
        if (pendingPresentationAttemptRef.current === pendingPresentation && owner.hasPendingPresentationFailure()) {
          throw new Error('presentation failure result remains unknown');
        }
      } else {
        await settleProductPresentationAck(pendingPresentation);
        if (pendingPresentationAttemptRef.current === pendingPresentation && owner.hasPendingPresentationAck()) {
          throw new Error('presentation ACK result remains unknown');
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
    const pendingGenerationInterrupt = pendingGenerationInterruptRef.current;
    if (pendingGenerationInterrupt?.owner === owner) {
      // Settled through the exact owner that issued it. `is_current` keeps a
      // retired Session or activation from resurrecting it against a successor.
      try {
        await retryRetainedProductOperation({
          operation: () => owner.interruptGeneration(pendingGenerationInterrupt.input),
          is_current: isCurrent,
        });
        if (pendingGenerationInterruptRef.current === pendingGenerationInterrupt) {
          pendingGenerationInterruptRef.current = null;
        }
      } catch (error) {
        if (owner.hasPendingGenerationInterrupt()) throw error;
        if (pendingGenerationInterruptRef.current === pendingGenerationInterrupt) {
          pendingGenerationInterruptRef.current = null;
        }
      }
    }
  };

  /**
   * A closed activation can no longer issue anything: `interruptGeneration`
   * requires its active binding, so any generation interruption it still holds
   * is unreachable for replay. Idempotence of a retried interruption is owned
   * by the server-side `action_id` ledger, not by this handle. Dropping it
   * with the activation is what keeps a retired one from reporting a pending
   * interruption that no successor can ever settle.
   */
  const retireOwnerGenerationInterrupt = (retiring: ProductWebP2ActivationOwner) => {
    if (ownerHasUnsettledGenerationInterrupt(retiring)) {
      pendingGenerationInterruptRef.current = null;
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
    const owner = new BrowserAudioDeviceSelectionOwner({
      enabled: FEATURE_LIVE_VOICE_INTEGRATED_WEB && FEATURE_LIVE_VOICE_INTEGRATED_P1,
      on_snapshot: snapshot => {
        if (deviceSelectionOwnerRef.current !== owner) return;
        setDeviceSelection(snapshot);
        if (snapshot.status === 'ready') {
          setDraftInputDeviceToken(current =>
            current === BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN || snapshot.inputs.some(option => option.token === current) ? current : snapshot.applied_input_token,
          );
          setDraftOutputDeviceToken(current =>
            current === BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN || snapshot.outputs.some(option => option.token === current)
              ? current
              : snapshot.applied_output_token,
          );
        }
      },
      on_device_invalidated: reason => {
        console.warn(`live_voice_audio_device_selection_failure reason=${reason} fallback=text visible=true`);
        const voiceOwner = p1VoiceOwnerRef.current;
        const ownsForegroundPlayout =
          voiceOwner !== null &&
          (pendingUnifiedFinalRef.current?.playout_owner === voiceOwner ||
            pendingForegroundPresentationRef.current?.playout_owner === voiceOwner);
        if (
          voiceOwner !== null &&
          !ownsForegroundPlayout &&
          !['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(voiceOwner.status().status)
        ) {
          void voiceOwner
            .close()
            .then(() => {
              if (p1VoiceOwnerRef.current === voiceOwner) p1VoiceOwnerRef.current = null;
            })
            .catch(() => {
              console.warn('live_voice_audio_device_selection_failure reason=FORMAL_P1_DEVICE_INVALIDATION_CLOSE_FAILED fallback=text visible=true');
            });
        }
      },
    });
    deviceSelectionOwnerRef.current = owner;
    setDeviceSelection(owner.snapshot());
    return () => {
      if (deviceSelectionOwnerRef.current === owner) deviceSelectionOwnerRef.current = null;
      owner.close();
    };
  }, []);

  useEffect(() => {
    p3ProgressReconciliationGenerationRef.current += 1;
    setProgress(null);
    progressRef.current = null;
    pendingOwnedProgressRef.current.clear();
    if (!FEATURE_LIVE_VOICE_INTEGRATED_WEB || !props.activeSessionId) return;
    const ownedSessionId = props.activeSessionId;
    const owner = new ProductTextProgressAckOwner({
      enabled: true,
      request: (method, params) => productRequest(method, { ...params }),
      capacity: props.progressAckCapacity,
      on_snapshot: snapshot => {
        if (activeSessionRef.current === ownedSessionId && progressAckOwnerRef.current === owner && progressRef.current?.delivery_id === snapshot.delivery_id) {
          setProgressAck(snapshot.status);
        }
      },
    });
    owner.setConnected(props.isConnected);
    progressAckOwnerRef.current = owner;
    const domAdoptionOwner = new ProductTextProgressDomAdoptionOwner(owner);
    progressDomAdoptionOwnerRef.current = domAdoptionOwner;
    let drainInFlight = false;
    let drainRetryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
    let effectClosed = false;
    const reconciliationFailures = new Map<string, number>();
    const exhaustedDeliveries = new Map<string, true>();
    const scheduleDrain = () => {
      if (effectClosed || drainInFlight || drainRetryTimer !== null || progressAckOwnerRef.current !== owner) return;
      drainInFlight = true;
      let retryDelayMs: number | null = null;
      let resumeAfterPermanentFailure = false;
      void (async () => {
        while (!effectClosed && mountedRef.current && activeSessionRef.current === ownedSessionId && progressAckOwnerRef.current === owner) {
          const ownedProgress = (event: Readonly<ProductTextProgressEvent>) => {
            const voice = voiceProgressOwnersRef.current.get(event.task_id);
            if (voice !== undefined && voiceProgressIsCurrent(voice)) {
              const activation = voice.owner.snapshot();
              if (activation.status === 'active' && activation.binding !== null && voice.leaf !== null
                && progressMatchesOwnedBinding(event, activation.binding, ownedSessionId)) {
                return { activation, leaf: voice.leaf, voice };
              }
            }
            const activation = progressActivationOwnerRef.current?.snapshot();
            const leaf = formalTaskControlLeafRef.current;
            if (activation?.status === 'active' && activation.binding !== null && leaf !== null
              && progressMatchesOwnedBinding(event, activation.binding, ownedSessionId)) return { activation, leaf, voice: null };
            return null;
          };
          for (const deliveryId of reconciliationFailures.keys()) {
            if (!pendingOwnedProgressRef.current.has(deliveryId)) reconciliationFailures.delete(deliveryId);
          }
          const parsed = [...pendingOwnedProgressRef.current.values()]
            .filter(event => ownedProgress(event) !== null)
            .sort(
              (left, right) =>
                left.source_event.seq - right.source_event.seq || left.delivery_id.localeCompare(right.delivery_id),
            )[0];
          if (parsed === undefined) return;
          const owned = ownedProgress(parsed)!;
          const leaf = owned.leaf;
          const candidate = adoptParsedProductTextProgressEvent(progressRef.current, parsed, ownedSessionId);
          if (candidate === progressRef.current && progressRef.current?.delivery_id === parsed.delivery_id) {
            try {
              const retained = domAdoptionOwner.adopt(parsed, progressDomRef.current);
              if (retained === null) return;
              pendingOwnedProgressRef.current.delete(parsed.delivery_id);
              reconciliationFailures.delete(parsed.delivery_id);
              setProgressAck(retained.status);
              continue;
            } catch (error) {
              const reason = stableProductTextReason(error, PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED);
              console.warn(
                `live_voice_task_progress_reconciliation_failure delivery_id=${parsed.delivery_id} seq=${parsed.source_event.seq} reason=${reason}`,
              );
              setProgressAck('failed');
              const failures = (reconciliationFailures.get(parsed.delivery_id) ?? 0) + 1;
              reconciliationFailures.set(parsed.delivery_id, failures);
              if (failures >= PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS) {
                pendingOwnedProgressRef.current.delete(parsed.delivery_id);
                reconciliationFailures.delete(parsed.delivery_id);
                if (reason !== PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED) {
                  rememberProductP3ProgressExhaustion(exhaustedDeliveries, parsed.delivery_id);
                }
                resumeAfterPermanentFailure = true;
              } else {
                retryDelayMs = productP3ProgressReconciliationRetryDelayMs(failures);
              }
              return;
            }
          }
          const reconciliationGeneration = p3ProgressReconciliationGenerationRef.current;
          const ownerEpoch = progressOwnerEpochRef.current;
          const isCurrent = () => {
            const currentOwned = ownedProgress(parsed);
            return (
              mountedRef.current &&
              activeSessionRef.current === ownedSessionId &&
              progressAckOwnerRef.current === owner &&
              currentOwned?.leaf === leaf &&
              (owned.voice !== null || (
                p3ProgressReconciliationGenerationRef.current === reconciliationGeneration &&
                progressOwnerEpochRef.current === ownerEpoch &&
                (progressTaskTargetRef.current === null || progressTaskTargetRef.current === parsed.task_id)
              ))
            );
          };
          try {
            const record = await reconcileProductP3ProgressEvent({
              request: productRequest,
              leaf,
              event: parsed,
              session_id: ownedSessionId,
              request_nonce: `${Date.now()}-${reconciliationGeneration}-${parsed.source_event.seq}`,
              is_current: isCurrent,
            });
            if (!isCurrent()) return;
            const fallbackMessage = await terminalTextFallbackMessage(
              parsed,
              owned.voice !== null ? parsed.task_id : createdProgressRouteRef.current?.task_id ?? null,
              owned.voice?.notification_chinese ?? false,
              owned.voice?.notification_name ?? null,
            );
            if (!isCurrent()) return;
            if (fallbackMessage !== null) props.onProductVoiceMessage?.(fallbackMessage);
            pendingOwnedProgressRef.current.delete(parsed.delivery_id);
            reconciliationFailures.delete(parsed.delivery_id);
            const adopted = adoptParsedProductTextProgressEvent(progressRef.current, parsed, ownedSessionId);
            if (adopted !== progressRef.current) {
              progressRef.current = adopted;
              setProgress(adopted);
            }
            const terminalStatus = productP3TerminalStatus(record);
            if (terminalStatus !== null) {
              void taskExperienceOwnerRef.current?.refresh(ownedSessionId).catch(() => {});
              if (createdProgressRouteRef.current?.task_id === parsed.task_id) setP3MutationStatus(terminalStatus);
              const fallbackText = fallbackMessage?.message.content ?? null;
              if (fallbackText !== null) {
                // Registry has already converted this exact failed AUDIO route
                // into its durable terminal TEXT presentation. Re-queuing it as
                // a voice announcement recreates a fence that no AUDIO delivery
                // can settle and blocks the next healthy P1 capture.
                // The technical progress node alone is not an obvious user
                // notification. Commit the same authoritative terminal outcome
                // to the primary Live Voice output before its DOM-gated ACK.
                setProductOutput(fallbackText);
                setTerminalNotification(fallbackText);
                terminalNotificationTaskIdRef.current = parsed.task_id;
                markVoiceTaskTerminalPresented(parsed.task_id);
                terminalAnnouncementSpeechOwnerRef.current = null;
                updateTerminalAnnouncementState('idle', null);
                scheduleProductVoiceLoopCapture();
              } else {
                queueTerminalAnnouncement(parsed.task_id);
              }
            }
            // The visible product task notification owns the first ACK only
            // after React commits the exact delivery into its connected DOM.
            return;
          } catch (error) {
            if (!isCurrent()) return;
            const reason = stableProductTextReason(error, 'PRODUCT_P3_PROGRESS_RECONCILIATION_FAILED');
            console.warn(
              `live_voice_task_progress_reconciliation_failure delivery_id=${parsed.delivery_id} seq=${parsed.source_event.seq} reason=${reason}`,
            );
            setProgressAck('failed');
            const failures = (reconciliationFailures.get(parsed.delivery_id) ?? 0) + 1;
            reconciliationFailures.set(parsed.delivery_id, failures);
            if (failures >= PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS) {
              pendingOwnedProgressRef.current.delete(parsed.delivery_id);
              reconciliationFailures.delete(parsed.delivery_id);
              if (
                reason !== PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED &&
                productP3ProgressFailureIsQuarantinable(error)
              ) {
                rememberProductP3ProgressExhaustion(exhaustedDeliveries, parsed.delivery_id);
              }
              resumeAfterPermanentFailure = true;
            } else {
              retryDelayMs = productP3ProgressReconciliationRetryDelayMs(failures);
            }
            return;
          }
        }
      })().finally(() => {
        drainInFlight = false;
        if (!effectClosed && retryDelayMs !== null && progressAckOwnerRef.current === owner && drainRetryTimer === null) {
          drainRetryTimer = globalThis.setTimeout(() => {
            drainRetryTimer = null;
            scheduleDrain();
          }, retryDelayMs);
        } else if (!effectClosed && resumeAfterPermanentFailure && progressAckOwnerRef.current === owner) {
          globalThis.queueMicrotask(scheduleDrain);
        }
      });
    };
    progressDrainRef.current = scheduleDrain;
    const acceptProgressPayload = (payload: unknown) => {
      const parsed = parseProductTextProgressEvent(payload);
      if (!parsed) {
        console.warn('live_voice_task_progress_rejected reason=INVALID_PAYLOAD');
        return;
      }
      if (
        activeSessionRef.current !== ownedSessionId ||
        parsed.session_id !== ownedSessionId ||
        progressAckOwnerRef.current !== owner ||
        (progressTaskTargetRef.current !== null && progressTaskTargetRef.current !== parsed.task_id && !voiceProgressOwnersRef.current.has(parsed.task_id))
      ) {
        return;
      }
      if (pendingOwnedProgressRef.current.has(parsed.delivery_id)) {
        scheduleDrain();
        return;
      }
      if (exhaustedDeliveries.has(parsed.delivery_id)) {
        console.warn(`live_voice_task_progress_rejected reason=RECONCILIATION_RETRY_EXHAUSTED delivery_id=${parsed.delivery_id}`);
        return;
      }
      if (pendingOwnedProgressRef.current.size >= PRODUCT_P3_PROGRESS_BUFFER_CAPACITY) {
        console.warn('live_voice_task_progress_rejected reason=PROGRESS_BUFFER_CAPACITY_EXCEEDED');
        setProgressAck('failed');
        return;
      }
      // A server replay may arrive before the activation response has supplied
      // its full binding or before unified create has bootstrapped the exact
      // FormalTaskControlLeaf.  Retain it without ACK or UI mutation; the
      // serial drain rechecks every identity after both authorities are ready.
      pendingOwnedProgressRef.current.set(parsed.delivery_id, parsed);
      scheduleDrain();
    };
    const unsubscribe = props.progressSubscribe
      ? props.progressSubscribe(acceptProgressPayload)
      : webClient.on(PRODUCT_TEXT_PROGRESS_EVENT, ({ payload }) => acceptProgressPayload(payload));
    return () => {
      effectClosed = true;
      p3ProgressReconciliationGenerationRef.current += 1;
      unsubscribe();
      owner.close();
      if (drainRetryTimer !== null) {
        globalThis.clearTimeout(drainRetryTimer);
        drainRetryTimer = null;
      }
      pendingOwnedProgressRef.current.clear();
      if (progressDrainRef.current === scheduleDrain) progressDrainRef.current = null;
      if (progressAckOwnerRef.current === owner) progressAckOwnerRef.current = null;
      if (progressDomAdoptionOwnerRef.current === domAdoptionOwner) progressDomAdoptionOwnerRef.current = null;
    };
  }, [props.activeSessionId, props.progressAckCapacity, props.progressSubscribe]);

  useEffect(() => {
    progressAckOwnerRef.current?.setConnected(props.isConnected);
  }, [props.isConnected]);

  useEffect(() => {
    if (props.isConnected) return;
    const hadVoiceDraft = recognizedVoiceRef.current !== null || voiceDraftBindingRef.current !== null;
    updateRecognizedSpeechConfirmation(null);
    recognizedVoiceRef.current = null;
    voiceDraftBindingRef.current = null;
    if (hadVoiceDraft) {
      setProductInput('');
      setProductTextStatus(pendingForegroundPresentationRef.current !== null ? 'waiting' : 'idle');
    }
    p1VoiceCaptureBindingRef.current = null;
    const voiceOwner = p1VoiceOwnerRef.current;
    if (voiceOwner === null) return;
    void (async () => {
      const foreground = pendingForegroundPresentationRef.current;
      if (foreground?.playout_owner === voiceOwner &&
          foreground.voice_loop_generation === voiceLoopGenerationRef.current &&
          voiceLoopEnabledRef.current && voiceOwner.status().status === 'capturing') {
        // Stop an idle microphone on disconnect without destroying the local
        // speaker owner of an already accepted answer. A real speaker or a
        // failed release still takes the existing full cleanup path below.
        if (await voiceOwner.abandonCapture('formal_transport_disconnected')) return;
      }
      await voiceOwner.close();
      if (p1VoiceOwnerRef.current === voiceOwner) p1VoiceOwnerRef.current = null;
    })()
      .catch(() => {
        // The owner remains retained with cleanup_pending truth for retry on
        // session teardown or the next explicit start attempt.
      });
  }, [props.isConnected]);

  useEffect(() => {
    const pending = recognizedSpeechConfirmationRef.current;
    if (pending === null) return;
    const displayedText = pending.intent === 'agent' ? productInput : p3TaskInstruction;
    if (
      p2Activation.status !== 'active' ||
      !recognizedSpeechConfirmationAuthorityMatches(pending, props.activeSessionId, displayedText, p2Activation.binding)
    ) {
      updateRecognizedSpeechConfirmation(null);
    }
  }, [
    p2Activation.binding?.activation_generation,
    p2Activation.binding?.activation_id,
    p2Activation.binding?.correlation_id,
    p2Activation.binding?.interaction_id,
    p2Activation.binding?.session_id,
    p2Activation.status,
    p3TaskInstruction,
    productInput,
    props.activeSessionId,
  ]);

  useEffect(() => {
    const pending = editedVoiceDraftConfirmationRef.current;
    if (pending === null) return;
    if (
      p2Activation.status !== 'active' ||
      pending.session_id !== props.activeSessionId ||
      pending.text !== productInput ||
      !productVoiceDraftMatchesBinding(pending, props.activeSessionId, p2Activation.binding)
    ) {
      updateEditedVoiceDraftConfirmation(null);
    }
  }, [
    p2Activation.binding?.activation_generation,
    p2Activation.binding?.activation_id,
    p2Activation.binding?.correlation_id,
    p2Activation.binding?.interaction_id,
    p2Activation.binding?.session_id,
    p2Activation.status,
    productInput,
    props.activeSessionId,
  ]);

  useEffect(() => {
    clearScheduledProductP2Recovery();
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
    setP1FaultTailPlaying(false);
    setP1VoiceReason(null);
    pendingProductTurnRef.current = null;
    pendingPresentationAttemptRef.current = null;
    pendingBargeInRef.current = null;
    updateRecognizedSpeechConfirmation(null);
    recognizedVoiceRef.current = null;
    voiceDraftBindingRef.current = null;
    p1VoiceCaptureBindingRef.current = null;
    presentedProductResponsesRef.current.clear();
    clearCapturedTaskNotification();
    presentedNativeChatMessagesRef.current.clear();
    discoveredNativeTasksRef.current.clear();
    refreshedNativeTaskOperationsRef.current.clear();
    terminalNotificationTaskIdRef.current = null;
    terminalAnnouncementSpeechOwnerRef.current = null;
    updateTerminalAnnouncementState('idle', null);
    setPendingPresentationAck(null);
    setProductInput('');
    setProductOutput(null);
    setTerminalNotification(null);
    setAdjustmentNotification(null);
    setProductTextReason(null);
    setProductTextStatus('idle');
    recoveryDiagnosticRef.current = null;
    setRecoveryDiagnostic(null);
    replacementRecognitionRef.current = null;
    setReplacementRecognitionFailure(null);
  }, [props.activeSessionId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearScheduledProductVoiceLoopCapture();
      clearScheduledProductP2Recovery();
      clearCapturedTaskNotification();
      recognizedSpeechConfirmationRef.current = null;
      editedVoiceDraftConfirmationRef.current = null;
      voiceDraftBindingRef.current = null;
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
    const scheduleRecovery = (binding: Readonly<ProductWebP2ActivationBinding> | null) => {
      const journal = p2ActivationJournalRef.current;
      if (binding === null || journal === null || !ownedSessionId) return;
      scheduleProductP2Recovery(ownedSessionId, binding, journal);
    };
    const ownedSessionId = props.activeSessionId;
    const run = async () => {
      const journal = p2ActivationJournalRef.current;
      const journalReady = Boolean(
        journal &&
        ownedSessionId &&
        p2JournalState?.session_id === ownedSessionId &&
        p2JournalState.status === 'ready' &&
        journal.snapshot().correlation_id === correlationId,
      );
      const routeEligible = Boolean(
        FEATURE_LIVE_VOICE_INTEGRATED_WEB &&
        hasDurableProductVoiceSession(ownedSessionId) &&
        props.agentRouteAvailable &&
        journalReady,
      );
      const isCurrentRun = () =>
        Boolean(
          !cancelled &&
          ownedSessionId &&
          activeSessionRef.current === ownedSessionId &&
          p2ActivationJournalRef.current === journal &&
          props.agentRouteAvailable &&
          props.isConnected,
        );
      const previous = activationOwnerRef.current;
      if (previous) {
        const snapshot = previous.snapshot();
        const sameSession = snapshot.binding?.session_id === ownedSessionId;
        if (routeEligible && sameSession && snapshot.status === 'active') {
          const foreground = pendingForegroundPresentationRef.current;
          const ownedInput = submissionCaptureRef.current?.owner === previous || pendingProductTurnRef.current?.owner === previous;
          const retainedJournal = journal!.snapshot();
          if (
            voiceLoopP2RefreshAfterGenerationRef.current === null &&
            !previous.retirementStarted() &&
            snapshot.binding !== null && retainedJournal.binding !== null &&
            sameProductP2ActivationBinding(snapshot.binding, retainedJournal.binding) &&
            retainedJournal.phase === 'active' &&
            retainedJournal.recovery_token === null &&
            pendingPresentationAttemptRef.current?.owner !== previous &&
            !previous.hasPendingPresentationAck() && !previous.hasPendingPresentationFailure() &&
            !previous.hasPendingBargeIn() && !previous.hasPendingGenerationInterrupt() &&
            !ownerHasUnsettledGenerationInterrupt(previous) &&
            (ownedInput || (foreground !== null && sameProductP2ActivationBinding(foreground, snapshot.binding)))
          ) {
            if (pendingProductTurnRef.current?.owner === previous && unifiedInputOwnerRef.current?.hasPending()) {
              try {
                // The unified owner coalesces the exact retained request. Its
                // unknown outcome is not an accepted foreground and must replay.
                await settleRetainedUnifiedInput(previous);
              } catch {
                if (!isCurrentRun() || activationOwnerRef.current !== previous) return;
                publishProductRecoveryDiagnostic({ seam: 'activation', disposition: 'retrying',
                  reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED, binding: snapshot.binding });
                scheduleRecovery(snapshot.binding);
                return;
              }
              if (!isCurrentRun() || activationOwnerRef.current !== previous) return;
              setP2NotificationWakeEpoch(epoch => epoch + 1);
            }
            // Reconnecting the transport does not revoke the accepted answer.
            // Its exact notification/ACK owners settle it; ordinary recovery
            // must not consume its final and then close the route before audio.
            setP2Activation(snapshot);
            return;
          }
          const activePresentation = pendingPresentationAttemptRef.current;
          if (
            activePresentation?.owner === previous &&
            activePresentation.settlement !== undefined &&
            voiceLoopP2RefreshAfterGenerationRef.current === null
          ) {
            // A live-page ACK owns its own single-flight settlement. The
            // durable checkpoint may rerender this recovery effect, but it is
            // not evidence that the active route needs predecessor cleanup.
            // Explicit Exit/re-enable is different: its exact P2 refresh must
            // await this same ACK settlement and then continue closing the
            // predecessor instead of losing the refresh epoch here.
            setP2Activation(snapshot);
            return;
          }
          if (!props.isConnected) {
            setP2Activation(snapshot);
            return;
          }
          let operationsSettled = false;
          try {
            const pendingDurableOperation = journalReady ? journal!.snapshot().pending_operation : null;
            const retiresPresentationAck = Boolean(
              pendingDurableOperation?.method === PRODUCT_P2_PRESENTATION_ACK_METHOD &&
                voiceLoopP2RefreshAfterGenerationRef.current !== null,
            );
            if (retiresPresentationAck && pendingDurableOperation !== null && snapshot.binding !== null && journalReady) {
              const activePresentationMatchesRetiredAck = Boolean(
                activePresentation?.owner === previous &&
                  durablePresentationAckMatches(pendingDurableOperation, activePresentation.input),
              );
              const retainsOriginalInFlightRequest = Boolean(
                activePresentationMatchesRetiredAck && activePresentation?.settlement !== undefined,
              );
              const retired = journal!.retirePendingPresentationAck(snapshot.binding);
              if (retainsOriginalInFlightRequest) {
                retiredPresentationAckInFlightRef.current.add(retired.request_id);
                retiredPresentationAckOwnerRequestRef.current.set(previous, retired.request_id);
              }
              if (activePresentationMatchesRetiredAck && pendingPresentationAttemptRef.current === activePresentation) {
                pendingPresentationAttemptRef.current = null;
                setPendingPresentationAck(null);
              }
              setRetiredPresentationAckRecoveryEpoch(epoch => epoch + 1);
            } else {
              await settleRetainedP2Operations(previous, {
                abandon_pending_notification:
                  voiceLoopP2RefreshInFlightRef.current && voiceLoopP2RefreshAfterGenerationRef.current !== null,
              });
            }
            operationsSettled = true;
            if (snapshot.binding && journalReady && sameSession) {
              journal!.markClosing(snapshot.binding);
            }
            await previous.closeWithRetry({ cause: voiceLoopP2RefreshAfterGenerationRef.current !== null
              ? voiceLoopP2RefreshCauseRef.current : 'active_recovery' });
            retireDeferredTaskPresentationForClosedOwner(previous);
            retireCapturedTaskNotificationForClosedOwner(previous);
            if (snapshot.binding && journalReady && sameSession) {
              journal!.markClosed(snapshot.binding);
            }
            retireOwnerGenerationInterrupt(previous);
          } catch {
            if (!operationsSettled && snapshot.binding && journalReady && sameSession && journal!.snapshot().pending_operation === null) {
              try {
                journal!.markResultUnknown(snapshot.binding);
              } catch {
                // The route remains fail-closed when its checkpoint is unavailable.
              }
            }
            if (operationsSettled && activationOwnerRef.current === previous) {
              activationOwnerRef.current = null;
            }
            publishProductRecoveryDiagnostic({
              seam: 'activation',
              disposition: 'retrying',
              reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
              binding: snapshot.binding,
            });
            scheduleRecovery(snapshot.binding);
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
              if (settled.status === 'active') {
                clearProductRecoveryDiagnostic({
                  seam: 'activation',
                  binding: settled.binding,
                });
              }
            }
          } catch {
            // The exact ambiguous activation is reconciled below on the next run.
            if (previous.needsCleanup()) scheduleRecovery(snapshot.binding);
          }
          return;
        }
        if (previous.needsCleanup()) {
          try {
            if (snapshot.binding && journalReady && sameSession) {
              journal!.markClosing(snapshot.binding);
            }
            await previous.closeWithRetry({
              cause: sameSession ? 'route_unavailable' : 'session_change',
              on_retry: snapshot => {
                if (!cancelled && activationOwnerRef.current === previous) {
                  setP2Activation(snapshot);
                }
              },
            });
            if (snapshot.binding && journalReady && sameSession) {
              journal!.markClosed(snapshot.binding);
            }
            retireOwnerGenerationInterrupt(previous);
          } catch {
            if (
              journalReady &&
              journal!.snapshot().phase !== 'result_unknown' &&
              journal!.snapshot().pending_operation === null &&
              activationOwnerRef.current === previous
            ) {
              activationOwnerRef.current = null;
            }
            publishProductRecoveryDiagnostic({
              seam: 'activation',
              disposition: 'retrying',
              reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
              binding: snapshot.binding,
            });
            scheduleRecovery(snapshot.binding);
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
      const recoveryPredecessorSnapshot = journal.snapshot();
      const recoveryPredecessorBinding =
        recoveryPredecessorSnapshot.phase === 'closed' ? null : recoveryPredecessorSnapshot.binding;
      const recovered = await reconcileProductP2Predecessor({
        journal,
        replay_operation: operation =>
          replayProductP2DurableOperation({
            operation,
            request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
          }),
        on_operation_recovered: (operation, result) => {
          if (operation.method !== PRODUCT_P2_SUBMIT_METHOD || operation.params.dispatch_target !== 'task') return;
          const {
            session_id: sessionId,
            interaction_id: interactionId,
            turn_id: turnId,
            commit_id: commitId,
            committed_at: committedAt,
            text,
          } = operation.params;
          if (
            typeof sessionId !== 'string' ||
            typeof interactionId !== 'string' ||
            typeof turnId !== 'string' ||
            typeof commitId !== 'string' ||
            typeof committedAt !== 'string' ||
            typeof text !== 'string'
          ) {
            throw new Error('recovered task origin is invalid');
          }
          const recoveredInput: ProductTurnInput = {
            turn_id: turnId,
            commit_id: commitId,
            committed_at: committedAt,
            text,
            dispatch_target: 'task',
          };
          voiceTaskOriginRef.current = bindProductVoiceTaskOrigin(recoveredInput, result, sessionId, interactionId);
          recognizedVoiceRef.current = null;
          pendingProductTurnRef.current = null;
          pendingP3MutationRef.current = null;
          setP3MutationOperation('task.create');
          setP3TaskName('Voice task');
          setP3TaskInstruction(text);
          setP3MutationStatus('idle');
        },
        activate_exact: async binding => {
          recovery.owner = createProductP2ActivationOwner({
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
        operation_retryable: isRetriableProductOperationError,
        is_current: isCurrentRun,
      });
      if (isCurrentRun() && journal.snapshot().retired_presentation_acks.length > 0) {
        setRetiredPresentationAckRecoveryEpoch(epoch => epoch + 1);
      }
      if (!isCurrentRun()) {
        const staleOwner = recovery.owner;
        const staleBinding = staleOwner?.snapshot().binding ?? null;
        if (staleOwner?.needsCleanup()) {
          void (async () => {
            if (staleBinding) {
              try {
                const latest = journal.refresh();
                if (latest.pending_operation !== null || latest.recovery_token !== null) return;
                journal.markClosing(staleBinding);
              } catch {
                // A newer journal owner exclusively decides exact cleanup.
                return;
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
        publishProductRecoveryDiagnostic({
          seam: 'activation',
          disposition: recovered.kind === 'retry' ? 'retrying' : 'terminal',
          reason: recovered.reason,
          binding: unresolvedBinding,
        });
        if (unresolvedOwner?.needsCleanup() && unresolvedBinding) {
          try {
            const latest = journal.refresh();
            if (latest.pending_operation !== null || latest.recovery_token !== null) return;
            journal.markClosing(unresolvedBinding);
          } catch {
            // A newer journal owner exclusively decides exact cleanup.
            return;
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
              scheduleRecovery(unresolvedBinding);
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
        if (recovered.kind === 'retry') scheduleRecovery(journal.snapshot().binding);
        return;
      }
      const recoveredBinding = recovery.owner?.snapshot().binding ?? journal.snapshot().binding;
      recovery.owner = null;
      if (!isCurrentRun()) return;
      const recoveredJournalSnapshot = journal.snapshot();
      if (
        recoveryPredecessorBinding !== null &&
        recoveredJournalSnapshot.phase === 'closed' &&
        recoveredJournalSnapshot.binding !== null &&
        sameProductP2ActivationBinding(recoveredJournalSnapshot.binding, recoveryPredecessorBinding)
      ) {
        retireDeferredTaskPresentationForClosedBinding(recoveryPredecessorBinding);
        retireCapturedTaskNotificationForClosedBinding(recoveryPredecessorBinding);
      }
      if (recoveredBinding !== null) {
        clearProductRecoveryDiagnostic({
          seam: 'activation',
          binding: recoveredBinding,
        });
      }
      let binding: NonNullable<ProductWebP2ActivationSnapshot['binding']>;
      try {
        binding = journal.prepareSuccessor(pageInstanceIdRef.current!);
      } catch {
        if (isCurrentRun()) {
          publishProductRecoveryDiagnostic({
            seam: 'activation',
            disposition: 'terminal',
            reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
            binding: null,
          });
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
      owner = createProductP2ActivationOwner({
        ...(selectedAgentModelNameRef.current ? { agent_model_selection: { contract_version: AGENT_MODEL_SELECTION_VERSION, model_name: selectedAgentModelNameRef.current } } : {}),
        enabled: true,
        request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
        durable_operation_journal: journal,
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
            const latest = journal.refresh();
            if (latest.pending_operation !== null || latest.recovery_token !== null) return;
            journal.markClosing(binding);
          } catch {
            // A newer journal owner exclusively decides exact cleanup.
            return;
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
          setProductTextReason(null);
          clearProductRecoveryDiagnostic({
            seam: 'activation',
            binding: activated.binding,
          });
          if (activated.binding !== null) resumeVoiceLoopAfterP2Successor(activated.binding);
        }
      } catch (error) {
        const activationReason = stableProductTextReason(error, PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED);
        if (!isCurrentRun() || activationOwnerRef.current !== owner) {
          const staleBinding = owner.snapshot().binding ?? binding;
          if (owner.needsCleanup()) {
            try {
              const latest = journal.refresh();
              if (latest.pending_operation !== null || latest.recovery_token !== null) return;
              journal.markClosing(staleBinding);
            } catch {
              return;
            }
            try {
              await owner.closeWithRetry();
              try {
                journal.markClosed(staleBinding);
              } catch {
                // A current run may already own the exact journal checkpoint.
              }
            } catch {
              // A stale run never publishes recovery state into its successor.
            }
          }
          return;
        }
        if (owner.snapshot().status === 'active') {
          publishProductRecoveryDiagnostic({
            seam: 'activation',
            disposition: 'retrying',
            reason: activationReason,
            binding,
          });
          try {
            const latest = journal.refresh();
            if (latest.pending_operation !== null || latest.recovery_token !== null) return;
            journal.markClosing(binding);
          } catch {
            // A newer journal owner exclusively decides exact cleanup.
            return;
          }
          try {
            await owner.closeWithRetry();
          } catch {
            // The exact owner remains retained and P1 stays unavailable.
          }
          if (isCurrentRun() && activationOwnerRef.current === owner) {
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
          publishProductRecoveryDiagnostic({
            seam: 'activation',
            disposition: 'retrying',
            reason: activationReason,
            binding,
          });
          // The request may have reached the registry. Keep the write-ahead
          // activating checkpoint and replay this exact binding next epoch.
          if (isCurrentRun() && activationOwnerRef.current === owner) {
            scheduleRecovery(binding);
          }
        } else if (cleanupRequired) {
          publishProductRecoveryDiagnostic({
            seam: 'activation',
            disposition: 'retrying',
            reason: activationReason,
            binding,
          });
          try {
            journal.markClosing(binding);
            await owner.closeWithRetry();
            journal.markClosed(binding);
            if (isCurrentRun() && activationOwnerRef.current === owner) {
              activationOwnerRef.current = null;
              setP2RecoveryEpoch(epoch => epoch + 1);
            }
          } catch {
            // Keep the exact cleanup owner and schedule another bounded pass.
            if (isCurrentRun() && activationOwnerRef.current === owner) {
              activationOwnerRef.current = null;
              scheduleRecovery(binding);
            }
          }
        } else {
          const reason = extractWebErrorReason(error);
          publishProductRecoveryDiagnostic({
            seam: 'activation',
            disposition: 'terminal',
            reason: activationReason,
            binding,
          });
          try {
            if (reason === 'ACTIVATION_BINDING_CONFLICT' || reason === 'ACTIVATION_BINDING_MISMATCH' || reason === 'ACTIVATION_GENERATION_STALE') {
              journal.markActivationResultUnknown(binding);
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
    };
  }, [correlationId, p2JournalState, p2RecoveryEpoch, props.activeSessionId, props.agentRouteAvailable, props.isConnected]);

  useEffect(() => {
    const identity = retiredPresentationAckDrainIdentityRef.current + 1;
    retiredPresentationAckDrainIdentityRef.current = identity;
    return () => {
      if (retiredPresentationAckDrainIdentityRef.current === identity) {
        retiredPresentationAckDrainIdentityRef.current += 1;
      }
    };
  }, [p2JournalState, props.activeSessionId, props.agentRouteAvailable, props.isConnected]);

  useEffect(() => {
    let triggerSuperseded = false;
    let retryTimer: ReturnType<typeof globalThis.setTimeout> | null = null;
    const journal = p2ActivationJournalRef.current;
    const ownedSessionId = props.activeSessionId;
    const drainIdentity = retiredPresentationAckDrainIdentityRef.current;
    const isCurrent = () =>
      Boolean(
        mountedRef.current &&
          retiredPresentationAckDrainIdentityRef.current === drainIdentity &&
          ownedSessionId &&
          activeSessionRef.current === ownedSessionId &&
          p2ActivationJournalRef.current === journal &&
          props.agentRouteAvailable &&
          props.isConnected,
      );
    if (
      journal === null ||
      !ownedSessionId ||
      p2JournalState?.session_id !== ownedSessionId ||
      p2JournalState.status !== 'ready' ||
      !props.agentRouteAvailable ||
      !props.isConnected
    ) {
      return () => undefined;
    }
    void reconcileRetiredProductP2PresentationAcks({
      journal,
      replay_operation: operation =>
        replayProductP2DurableOperation({
          operation,
          request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
        }),
      operation_definitive: error =>
        isDefinitiveProductOperationError(error) ||
        ['PRODUCT_P2_ROUTE_NOT_FOUND', 'STALE_RESPONSE_OUTPUT', 'UNKNOWN_AGENT_RESPONSE'].includes(extractWebErrorReason(error) ?? ''),
      operation_in_flight: operation => retiredPresentationAckInFlightRef.current.has(operation.request_id),
      is_current: isCurrent,
    }).then(result => {
      if (!isCurrent() || (result.kind !== 'retry' && result.kind !== 'superseded')) return;
      // A trigger may race the preceding drain's still-held Web Lock. That
      // lock miss is not session supersession; retain a bounded wake instead
      // of stranding the exact retired ACK after the transport settles.
      if (result.kind === 'superseded' && journal.snapshot().retired_presentation_acks.length === 0) return;
      if (triggerSuperseded) {
        setRetiredPresentationAckRecoveryEpoch(epoch => epoch + 1);
        return;
      }
      retryTimer = globalThis.setTimeout(() => setRetiredPresentationAckRecoveryEpoch(epoch => epoch + 1), 1000);
    });
    return () => {
      triggerSuperseded = true;
      if (retryTimer !== null) globalThis.clearTimeout(retryTimer);
    };
  }, [
    p2JournalState,
    props.activeSessionId,
    props.agentRouteAvailable,
    props.isConnected,
    retiredPresentationAckRecoveryEpoch,
  ]);

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
      let journalSnapshot: ReturnType<ProductP2ActivationJournal['snapshot']> | undefined;
      try {
        journalSnapshot = journal?.refresh();
      } catch {
        if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
        return;
      }
      const recoveryBarrier = Boolean(
        journalSnapshot?.phase === 'result_unknown' ||
        journalSnapshot?.phase === 'activation_result_unknown' ||
        journalSnapshot?.pending_operation !== null ||
        journalSnapshot?.recovery_token !== null ||
        pendingProductTurnRef.current?.owner === closing ||
        pendingPresentationAttemptRef.current?.owner === closing ||
        pendingBargeInRef.current?.owner === closing ||
        ownerHasUnsettledGenerationInterrupt(closing) ||
        closing.hasPendingSubmission() ||
        closing.hasPendingPresentationAck() ||
        closing.hasPendingPresentationFailure() ||
        closing.hasPendingBargeIn() ||
        closing.hasPendingGenerationInterrupt(),
      );
      if (recoveryBarrier) {
        if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
        return;
      }
      if (binding && journal) {
        try {
          journal.markClosing(binding);
        } catch {
          if (activationOwnerRef.current === closing) activationOwnerRef.current = null;
          return;
        }
      }
      void closing
        .closeWithRetry()
        .then(() => {
          retireDeferredTaskPresentationForClosedOwner(closing);
          retireCapturedTaskNotificationForClosedOwner(closing);
          retireOwnerGenerationInterrupt(closing);
          if (binding && journal) {
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
    const owner = p1VoiceOwnerRef.current;
    const action = terminalAnnouncementArbitrationAction({
      queued: terminalAnnouncementState === 'queued',
      voice_active: voiceLoopEnabledRef.current && p2Activation.status === 'active',
      connected: props.isConnected,
      page_visible: typeof document === 'undefined' || document.visibilityState === 'visible',
      foreground_active: Boolean(
        pendingProductTurnRef.current !== null ||
        pendingUnifiedFinalRef.current !== null ||
        // An announcement that stood down for a speaker is waiting for exactly
        // this arbitration to replay it, so it must not report itself busy.
        (pendingPresentationAttemptRef.current !== null &&
          pendingPresentationAttemptRef.current.deferred_to_speaker !== true) ||
        pendingBargeInRef.current !== null ||
        // A generation-time listening window, and the interruption it issues,
        // are foreground work: a Task announcement must not take the
        // microphone away from a speaker who is replacing an answer.
        generationCaptureRef.current !== null ||
        // Matched on the current owner. A handle left behind by an activation
        // that has already retired belongs to no live foreground, and must not
        // report a successor busy forever.
        ownerHasUnsettledGenerationInterrupt(activationOwnerRef.current) ||
        activeVoiceResponseRef.current !== null ||
        productTextStatus === 'waiting' ||
        activationOwnerRef.current?.hasPendingSubmission() ||
        activationOwnerRef.current?.hasPendingPresentationAck() ||
        activationOwnerRef.current?.hasPendingPresentationFailure() ||
        activationOwnerRef.current?.hasPendingBargeIn(),
      ),
      speech_active: owner !== null && terminalAnnouncementSpeechOwnerRef.current === owner,
      p1_status: owner?.status().status ?? null,
    });
    if (action === 'defer') return;
    if (action === 'recover_owner') {
      void startP1VoiceHandlerRef.current().catch(() => undefined);
      return;
    }
    if (owner === null) return;
    if (owner.interactionEngine() === 'openai-realtime-native') {
      // The native session is the continuous listening authority. Fetching a
      // Task notice must never close it like a Cascade idle capture.
      const deferred = pendingPresentationAttemptRef.current;
      if (deferred?.deferred_to_speaker === true) resumeDeferredTaskAnnouncementRef.current(deferred);
      else {
        updateTerminalAnnouncementState('fetching');
        setP2NotificationWakeEpoch(epoch => epoch + 1);
      }
      return;
    }
    if (action === 'suspend_capture') {
      const taskId = terminalAnnouncementTaskIdRef.current;
      updateTerminalAnnouncementState('suspending_capture');
      void owner
        .pauseIdleCaptureForNotification()
        .then(outcome => {
          if (
            !mountedRef.current ||
            p1VoiceOwnerRef.current !== owner ||
            !voiceLoopEnabledRef.current ||
            terminalAnnouncementTaskIdRef.current !== taskId ||
            terminalAnnouncementStateRef.current !== 'suspending_capture'
          ) {
            return;
          }
          if (outcome === 'speech_active') {
            terminalAnnouncementSpeechOwnerRef.current = owner;
            updateTerminalAnnouncementState('queued');
            return;
          }
          terminalAnnouncementSpeechOwnerRef.current = null;
          p1VoiceCaptureBindingRef.current = null;
          updateTerminalAnnouncementState('fetching');
        })
        .catch(error => {
          if (terminalAnnouncementTaskIdRef.current !== taskId) return;
          terminalAnnouncementSpeechOwnerRef.current = null;
          setProductTextReason(stableProductTextReason(error, 'PRODUCT_TERMINAL_CAPTURE_SUSPEND_FAILED'));
          setProductTextStatus('failed');
          updateTerminalAnnouncementState('queued');
        });
      return;
    }
    if (action === 'fetch') {
      terminalAnnouncementSpeechOwnerRef.current = null;
      const deferred = pendingPresentationAttemptRef.current;
      if (deferred !== null && deferred.deferred_to_speaker === true) {
        // The speaker settled. Replay the exact announcement already delivered
        // instead of fetching a new one; nothing was consumed twice and the P1
        // route the speaker just used stays intact.
        resumeDeferredTaskAnnouncementRef.current(deferred);
        return;
      }
      updateTerminalAnnouncementState('fetching');
    }
  }, [
    p1VoiceStatus,
    p2Activation.status,
    productTextStatus,
    props.isConnected,
    terminalAnnouncementArbitrationEpoch,
    terminalAnnouncementState,
  ]);

  useEffect(() => () => endNativeTextDisplay(), [endNativeTextDisplay]);

  useEffect(() => {
    if (!props.isConnected || !voiceLoopEnabledRef.current || p2Activation.status !== 'active' ||
        !['capturing', 'playing'].includes(p1VoiceStatus)) endNativeTextDisplay();
  }, [props.isConnected, p2Activation, p1VoiceStatus, endNativeTextDisplay]);

  useEffect(() => {
    const owner = activationOwnerRef.current;
    const voice = p1VoiceOwnerRef.current;
    const binding = p2Activation.binding;
    if (!props.isConnected || !voiceLoopEnabledRef.current || p2Activation.status !== 'active' || !binding || !owner ||
        voice?.interactionEngine() !== 'openai-realtime-native' || !['capturing', 'playing'].includes(p1VoiceStatus)) return;
    let cancelled = false;
    const bindingKey = JSON.stringify([binding.session_id, binding.interaction_id, binding.activation_id, binding.activation_generation]);
    if (nativeTextReadRef.current?.owner !== owner || nativeTextReadRef.current?.voice !== voice ||
        nativeTextReadRef.current?.binding !== bindingKey || nativeTextReadRef.current.ended) {
      endNativeTextDisplay();
      nativeTextReadRef.current = { owner, voice, binding: bindingKey, sessionId: binding.session_id,
        revision: 0, visible: new Set(), ended: false, onEnd: props.onNativeVoiceDisplayEnded };
    }
    const cursor = nativeTextReadRef.current;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const current = () => !cancelled && !cursor.ended && mountedRef.current && activationOwnerRef.current === owner &&
      p1VoiceOwnerRef.current === voice && activeSessionRef.current === binding.session_id && voiceLoopEnabledRef.current;
    const poll = async () => {
      try {
        const result = await productRequest('live_voice.media.native_text', {
          session_id: binding.session_id, interaction_id: binding.interaction_id, correlation_id: binding.correlation_id,
          activation_id: binding.activation_id, activation_generation: binding.activation_generation, after_revision: cursor.revision,
        });
        if (!current()) return;
        const projection = parseNativeGeneratedText(result, binding, cursor.revision);
        cursor.revision = projection.revision;
        for (const message of projection.messages) {
          props.onProductVoiceMessage?.({ session_id: binding.session_id, message });
          const first = !cursor.visible.has(message.nativeVoice.responseKey);
          cursor.visible.add(message.nativeVoice.responseKey);
          if (cursor.visible.size > 64) cursor.visible.delete(cursor.visible.values().next().value!);
          recordAudioDiagnostic(first ? 'native_text_first_visible' : 'native_text_updated', {
            ...binding, response_id: message.nativeVoice.responseId, response_generation: message.nativeVoice.responseGeneration,
            status: message.nativeVoice.state,
            seq: message.nativeVoice.revision, output_chars: message.content.length });
        }
      } catch (error) {
        if (current()) recordAudioDiagnostic('native_text_read_failed', { ...binding,
          reason: stableProductTextReason(error, 'MEDIA_NATIVE_TEXT_READ_FAILED') });
      }
      if (current()) timer = setTimeout(() => void poll(), 200);
    };
    void poll();
    return () => { cancelled = true; if (timer !== null) clearTimeout(timer); };
  }, [props.isConnected, p2Activation, p1VoiceStatus, productRequest, endNativeTextDisplay]);

  useEffect(() => {
    const owner = activationOwnerRef.current;
    const binding = p2Activation.binding;
    const journal = p2ActivationJournalRef.current;
    const nativeTaskTransportOpen = () => p1VoiceOwnerRef.current?.interactionEngine() === 'openai-realtime-native' &&
      voiceLoopEnabledRef.current && pendingPresentationAttemptRef.current?.owner === owner &&
      pendingPresentationAttemptRef.current.task_notification !== null &&
      ['capturing', 'playing'].includes(p1VoiceOwnerRef.current.status().status);
    if (
      !props.isConnected ||
      p2Activation.status !== 'active' ||
      !binding ||
      !owner ||
      !journal ||
      // The server publishes the authoritative presentation before
      // unified.submit can return its exact response fence. Starting a
      // pop-on-read poll in that interval can consume the response without an
      // owner that is allowed to present or ACK it.
      readPendingUnifiedFinal() !== null ||
      (!nativeTaskTransportOpen() && (pendingPresentationAck !== null ||
      pendingPresentationAttemptRef.current !== null ||
      activeVoiceResponseRef.current !== null ||
      voiceLoopP2RefreshAfterGenerationRef.current !== null ||
      (!['idle', 'fetching'].includes(terminalAnnouncementState) && !(terminalAnnouncementState === 'queued' && productTextStatus === 'waiting')) ||
      (terminalAnnouncementState === 'fetching' && !voiceLoopEnabledRef.current))) ||
      (!nativeTaskTransportOpen() && productP2NotificationTransportBlockedByP1({
        p1_status: p1VoiceStatus,
        terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
      }) &&
        !admitsGenerationListeningPoll(p1VoiceStatus) &&
        shouldBlockProductP2NotificationPoll(
          p1VoiceStatus,
          p1VoiceOwnerRef.current?.interactionEngine() ?? 'cascade',
        ))
    )
      return;
    const notificationAdmission: ProductP2NotificationAdmission = Object.freeze({
      voice_loop_generation: voiceLoopGenerationRef.current,
      foreground_presentation: pendingForegroundPresentationRef.current,
    });
    let cancelled = false;
    const poll = async () => {
      while (!cancelled && activationOwnerRef.current === owner) {
        const capturedTaskNotification = capturedTaskNotificationRef.current;
        const currentP1Status = p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus;
        if (
          terminalAnnouncementStateRef.current === 'fetching' &&
          capturedTaskNotification?.owner === owner
        ) {
          if (
            terminalAnnouncementTaskIdRef.current !== capturedTaskNotification.task_id ||
            !ownsVoiceProgressTask(capturedTaskNotification.task_id)
          ) {
            clearCapturedTaskNotification(capturedTaskNotification);
            return;
          }
          const playoutOwner = p1VoiceOwnerRef.current;
          if (capturedTaskNotification.disposition.task_notification_terminal) {
            try {
              // The same P1 owner can start a new media route. A notification
              // observed during that startup may authorize only its predecessor,
              // so owner identity cannot prove synthesis authority. Once capture
              // arbitration settles, re-observe the exact P2 delivery on the
              // ready route (same request/response/unit), never fetch a new one.
              const replay = capturedTaskNotification.media_replay;
              // React can replace the polling effect during the same media
              // transition. Those continuations share one exact replay.
              if (replay.operation === null || replay.owner !== playoutOwner) {
                replay.owner = playoutOwner;
                replay.operation = owner.replayNotificationForMediaAuthorization({
                  ...capturedTaskNotification.disposition.response,
                  unit_id: capturedTaskNotification.disposition.unit_id,
                });
              }
              await replay.operation;
            } catch {
              if (
                !cancelled && activationOwnerRef.current === owner &&
                capturedTaskNotificationRef.current === capturedTaskNotification &&
                clearCapturedTaskNotification(capturedTaskNotification)
              ) {
                retainDeferredTaskPresentation(owner, capturedTaskNotification.disposition);
                if (!settleDeferredTaskPresentationFailure(owner)) setP2NotificationWakeEpoch(epoch => epoch + 1);
              }
              return;
            }
            if (
              cancelled || !voiceLoopEnabledRef.current ||
              voiceLoopGenerationRef.current !== capturedTaskNotification.admission.voice_loop_generation ||
              p1VoiceOwnerRef.current !== playoutOwner || activationOwnerRef.current !== owner
            ) return;
          }
          if (!clearCapturedTaskNotification(capturedTaskNotification)) return;
          adoptProductP2Notification(
            owner,
            capturedTaskNotification.notification,
            capturedTaskNotification.admission,
          );
          return;
        }
        if (
          readPendingUnifiedFinal() !== null ||
          (!nativeTaskTransportOpen() && activeVoiceResponseRef.current !== null) ||
          (!nativeTaskTransportOpen() && productP2NotificationTransportBlockedByP1({
            p1_status: currentP1Status,
            terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
          }) &&
            !admitsGenerationListeningPoll(currentP1Status) &&
            shouldBlockProductP2NotificationPoll(
              currentP1Status,
              p1VoiceOwnerRef.current?.interactionEngine() ?? 'cascade',
            ))
        )
          return;
        try {
          nativePresentationQueueRef.current = nativePresentationQueueRef.current.filter(item => item.owner === owner);
          const staged = pendingPresentationAttemptRef.current === null && activeVoiceResponseRef.current === null
            ? nativePresentationQueueRef.current.shift() : undefined;
          const outcome = staged ? { kind: 'notification' as const, notification: staged.notification } : await pollProductP2RouteWithRecovery({
            owner,
            is_current: () => !cancelled && activationOwnerRef.current === owner && activeSessionRef.current === binding.session_id,
            settle_retained_operations: async () => {
              await settleRetainedP2Operations(owner);
              journal.markClosing(binding);
            },
            can_activate_successor: () =>
              mountedRef.current &&
              activationOwnerRef.current === owner &&
              activeSessionRef.current === binding.session_id &&
              p2ActivationJournalRef.current === journal &&
              isConnectedRef.current,
            activate_successor: async () => {
              if (
                !mountedRef.current ||
                activationOwnerRef.current !== owner ||
                activeSessionRef.current !== binding.session_id ||
                p2ActivationJournalRef.current !== journal ||
                !isConnectedRef.current
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
              successor = createProductP2ActivationOwner({
                ...(selectedAgentModelNameRef.current ? { agent_model_selection: { contract_version: AGENT_MODEL_SELECTION_VERSION, model_name: selectedAgentModelNameRef.current } } : {}),
                enabled: true,
                request: (method, params, requestId) => productRequest(method, params, productP2WebRequestOptions(method, requestId)),
                durable_operation_journal: journal,
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
                setProductTextReason(null);
                clearProductRecoveryDiagnostic({ seam: 'activation', binding });
                if (successorSnapshot.binding !== null) resumeVoiceLoopAfterP2Successor(successorSnapshot.binding);
              }
              return successor;
            },
          });
          if (outcome.kind === 'recovered') {
            retireDeferredTaskPresentationForClosedOwner(owner);
            retireCapturedTaskNotificationForClosedOwner(owner);
            await pendingP1VoiceStartRef.current?.promise.catch(() => undefined);
            scheduleProductVoiceLoopCapture();
            return;
          }
          const previewResponse = recordValue(outcome.notification.response);
          const previewResponseId = typeof previewResponse?.response_id === 'string' ? previewResponse.response_id : null;
          const previewDisposition = classifyProductP2Notification(
            outcome.notification,
            previewResponseId !== null && presentedProductResponsesRef.current.has(previewResponseId),
          );
          prepareTerminalTaskNotification(owner, previewDisposition);
          const pendingUnified = readPendingUnifiedFinal();
          if (pendingUnified !== null) {
            if (previewDisposition.kind === 'presentation' && previewDisposition.task_notification) {
              if (activationOwnerRef.current === owner && activeSessionRef.current === binding.session_id) {
                adoptProductP2Notification(owner, outcome.notification, notificationAdmission);
              }
              return;
            }
            // notification.next is pop-on-read, while unified.submit publishes
            // before returning the exact response fence. Keep this delivery in
            // the current poll continuation until the already-retained submit
            // settles; do not present, ACK, or start another poll pre-fence.
            await submittedVoiceFinalsRef.current
              .get(pendingUnified.receipt)
              ?.operation.catch(() => undefined);
          }
          if (
            activationOwnerRef.current !== owner ||
            activeSessionRef.current !== binding.session_id
          ) {
            return;
          }
          const notificationP1Status = p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus;
          if (
            previewDisposition.kind === 'presentation' &&
            previewDisposition.task_notification &&
            previewDisposition.ack.surface === 'audio' &&
            p1VoiceOwnerRef.current?.interactionEngine() !== 'openai-realtime-native' &&
            productP2TaskNotificationRequiresCaptureArbitration({
              p1_status: notificationP1Status,
              terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
            }) &&
            previewDisposition.task_id !== null &&
            ownsVoiceProgressTask(previewDisposition.task_id) &&
            terminalNotificationTaskIdRef.current !== previewDisposition.task_id
          ) {
            const retained = capturedTaskNotificationRef.current;
            if (
              retained !== null &&
              (retained.owner !== owner ||
                retained.response_id !== previewDisposition.response_id ||
                retained.response_generation !== previewDisposition.response.response_generation)
            ) {
              throw new Error('a captured Task notification is still unresolved');
            }
            if (retained === null) {
              const captured = Object.freeze<CapturedProductTaskNotification>({
                owner,
                capture_owner: p1VoiceOwnerRef.current,
                media_replay: { owner: null, operation: null },
                notification: outcome.notification,
                disposition: previewDisposition,
                admission: notificationAdmission,
                task_id: previewDisposition.task_id,
                response_id: previewDisposition.response_id,
                response_generation: previewDisposition.response.response_generation,
              });
              capturedTaskNotificationRef.current = captured;
              scheduleCapturedTaskNotificationDeadline(captured);
            }
            if (
              capturedTaskNotificationRequiresAnnouncementRequeue(
                terminalAnnouncementStateRef.current,
              )
            ) {
              // A prior Task AUDIO presentation can leave its concurrent
              // successor capture active while the terminal poll is already
              // `fetching`. Capturing the next exact AUDIO delivery must
              // re-enter queued arbitration so that capture is paused and this
              // pop-on-read notification is adopted, rather than timing out.
              updateTerminalAnnouncementState('queued', previewDisposition.task_id);
            } else {
              queueTerminalAnnouncement(previewDisposition.task_id);
            }
            return;
          }
          if (previewDisposition.kind === 'presentation' && previewDisposition.task_notification) {
            const foregroundAttempt = pendingPresentationAttemptRef.current;
            if (
              foregroundAttempt?.owner === owner &&
              foregroundAttempt.task_notification === null
            ) {
              await foregroundAttempt.playoutSettlement;
              await settleProductPresentationAck(foregroundAttempt);
              if (
                activationOwnerRef.current !== owner ||
                activeSessionRef.current !== binding.session_id
              ) {
                return;
              }
            }
          }
          const exactForegroundDelivery =
            (
              previewDisposition.kind === 'presentation' &&
              !previewDisposition.task_notification
            ) || previewDisposition.kind === 'native_audio' || previewDisposition.kind === 'failed'
              ? foregroundPresentationFenceMatchesResponse(
                  pendingForegroundPresentationRef.current,
                  owner.snapshot().binding,
                  previewDisposition.response ?? null,
                )
              : false;
          if (readPendingUnifiedFinal() !== null && !exactForegroundDelivery) return;
          const exactNativeStateDelivery = (previewDisposition.kind === 'native_request_state' || previewDisposition.kind === 'native_work_state') &&
            activationOwnerRef.current === owner && activeSessionRef.current === binding.session_id &&
            voiceLoopGenerationRef.current === notificationAdmission.voice_loop_generation &&
            previewDisposition.session_id === binding.session_id && previewDisposition.correlation_id === binding.correlation_id &&
            previewDisposition.interaction_id === binding.interaction_id && previewDisposition.activation_id === binding.activation_id &&
            previewDisposition.activation_generation === binding.activation_generation;
          const exactTaskPresentationDelivery = previewDisposition.kind === 'presentation' && previewDisposition.task_notification &&
            mountedRef.current && isConnectedRef.current && voiceLoopEnabledRef.current &&
            activationOwnerRef.current === owner && activeSessionRef.current === binding.session_id &&
            voiceLoopP2RefreshAfterGenerationRef.current === null &&
            voiceLoopGenerationRef.current === notificationAdmission.voice_loop_generation &&
            outcome.notification.session_id === binding.session_id && outcome.notification.correlation_id === binding.correlation_id &&
            outcome.notification.interaction_id === binding.interaction_id && outcome.notification.activation_id === binding.activation_id &&
            outcome.notification.activation_generation === binding.activation_generation;
          if (cancelled && !exactForegroundDelivery && !exactNativeStateDelivery && !exactTaskPresentationDelivery) {
            // A poll opened before submit may finish with the interrupted old
            // answer. Its obsolete effect must release a wake for the current
            // foreground; otherwise the successor stays listening forever.
            if (voiceLoopGenerationRef.current === notificationAdmission.voice_loop_generation &&
                pendingForegroundPresentationRef.current !== null && readPendingUnifiedFinal() === null) {
              setP2NotificationWakeEpoch(epoch => epoch + 1);
            }
            return;
          }
          if (p1VoiceOwnerRef.current?.interactionEngine() === 'openai-realtime-native' &&
              previewDisposition.kind === 'presentation' &&
              (pendingPresentationAttemptRef.current !== null || activeVoiceResponseRef.current !== null)) {
            const queue = nativePresentationQueueRef.current;
            const key = JSON.stringify([previewDisposition.response, previewDisposition.ack.surface, previewDisposition.unit_id]);
            const same = (item: typeof queue[number]) => item.key === key;
            if (!queue.some(same)) {
              if (queue.length >= 32) throw new Error('PRODUCT_NATIVE_NOTIFICATION_BUFFER_FULL');
              queue.push({ key, owner, notification: outcome.notification, admission: staged?.admission ?? notificationAdmission });
            }
            continue;
          }
          const disposition = adoptProductP2Notification(owner, outcome.notification, staged?.admission ?? notificationAdmission);
          if (
            cancelled ||
            voiceLoopGenerationRef.current !== notificationAdmission.voice_loop_generation ||
            voiceLoopP2RefreshAfterGenerationRef.current !== null
          ) {
            return;
          }
          const currentP1StatusAfterNotification = p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus;
          if (
            disposition.kind === 'continue' &&
            terminalAnnouncementStateRef.current === 'fetching' &&
            pendingForegroundPresentationRef.current === null &&
            readPendingUnifiedFinal() === null &&
            pendingPresentationAttemptRef.current === null &&
            capturedTaskNotificationRef.current === null &&
            deferredTaskPresentationRef.current === null &&
            ['idle', 'recognized'].includes(currentP1StatusAfterNotification)
          ) {
            taskAudioRepollBeforeCaptureTaskIdRef.current = null;
            // This exact poll found no presentation to own capture. This also
            // covers a generic completion check with no single Task selected,
            // not just the special post-AUDIO repoll. Retained presentations,
            // ACKs and foreground inputs above must still settle first.
            // The outstanding voice Task still authorizes notification.next
            // while the fresh capture runs, so terminal delivery remains live.
            updateTerminalAnnouncementState('idle', null);
            scheduleProductVoiceLoopCapture();
            return;
          }
          // A presentation owns the P2 lane until its TEXT ACK settles.  Do
          // not let an immediately rejected TTS attempt race a successor
          // notification long-poll and strand that ACK behind it.
          if (
            !nativeTaskTransportOpen() && (disposition.kind === 'presentation' ||
            disposition.kind === 'native_audio' ||
            pendingPresentationAttemptRef.current?.owner === owner)
          ) return;
          // A hands-free capture is admitted only after this exact poll has
          // settled. A committed foreground response keeps the P2 lane until
          // its presentation arrives; the queued Task terminal check cannot
          // starve that response after an idle keepalive.
          const repollDelayMs = productP2NotificationRepollDelayMs({
            disposition,
            terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
            foreground_response_waiting: pendingForegroundPresentationRef.current !== null,
            notification: outcome.notification,
          });
          if (repollDelayMs > 0) {
            await new Promise<void>(resolve => globalThis.setTimeout(resolve, repollDelayMs));
            if (cancelled || activationOwnerRef.current !== owner) return;
          }
        } catch (error) {
          if (!cancelled && isProductNotificationSequenceMismatch(error)) {
            const reason = stableProductTextReason(error, 'PRODUCT_NOTIFICATION_SEQUENCE_MISMATCH');
            setProductTextReason(reason);
            setProductTextStatus('failed');
            return;
          }
          const retained = activationOwnerRef.current;
          if (
            !cancelled &&
            retained?.needsCleanup() &&
            journal.snapshot().phase !== 'result_unknown' &&
            journal.snapshot().pending_operation === null &&
            !retained.hasPendingSubmission() &&
            !retained.hasPendingPresentationAck() &&
            !retained.hasPendingPresentationFailure() &&
            !retained.hasPendingBargeIn() &&
            !retained.hasPendingGenerationInterrupt()
          ) {
            if (activationOwnerRef.current === retained) {
              activationOwnerRef.current = null;
            }
          }
          if (!cancelled && retained?.needsCleanup()) {
            setP2RecoveryEpoch(epoch => epoch + 1);
          }
          if (!cancelled) {
            const reason = stableProductTextReason(error, PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED);
            setProductTextReason(reason);
            setProductTextStatus('failed');
            setP2Activation({
              status: 'unavailable',
              binding: null,
              reason,
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
  }, [
    correlationId,
    p1VoiceStatus,
    p2Activation.binding,
    p2Activation.status,
    foregroundPresentationEpoch,
    p2NotificationWakeEpoch,
    pendingPresentationAck,
    props.isConnected,
    terminalAnnouncementState,
  ]);

  useEffect(() => {
    p3ProgressReconciliationGenerationRef.current += 1;
    cancelP3RetryInspection();
    pendingP3MutationRef.current = null;
    p3AcceptedFollowTargetRef.current = null;
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
    setP3RetryInspectionReason(null);
    setP3RetryEligibility(null);
    progressTaskTargetRef.current = null;
    recoveredP3TaskTargetRef.current = null;
    adoptCreatedProgressRoute(null);
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
    const sessionId = props.activeSessionId;
    if (
      !FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ||
      !props.isConnected ||
      sessionId === null ||
      p2JournalState?.status !== 'ready' ||
      p2JournalState.session_id !== sessionId
    ) {
      return;
    }
    const targetInspection = inspectProductP3TaskTarget({ session_id: sessionId });
    if (targetInspection.status === 'absent') return;
    if (targetInspection.status === 'invalid') {
      recoveredP3TaskTargetRef.current = `${sessionId}\u0000invalid`;
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('failed');
      setP3RetryInspectionReason('PRODUCT_P3_TASK_TARGET_RECOVERY_REQUIRED');
      return;
    }
    const recovered = targetInspection.record;
    const recoveryIdentity = `${sessionId}\u0000${recovered.task_control_binding.correlation_id}\u0000${recovered.task_id}`;
    if (recoveredP3TaskTargetRef.current === recoveryIdentity) return;
    recoveredP3TaskTargetRef.current = recoveryIdentity;
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding: recovered.task_control_binding });
    const recoveryGeneration = p3ProgressReconciliationGenerationRef.current + 1;
    p3ProgressReconciliationGenerationRef.current = recoveryGeneration;
    let cancelled = false;
    setP3RetryInspectionStatus('checking');
    setP3RetryInspectionReason(null);
    const isCurrent = () =>
      !cancelled &&
      mountedRef.current &&
      props.isConnected &&
      activeSessionRef.current === sessionId &&
      recoveredP3TaskTargetRef.current === recoveryIdentity &&
      p3ProgressReconciliationGenerationRef.current === recoveryGeneration;
    void inspectProductP3RetryCandidate({
      request: productRequest,
      leaf,
      session_id: sessionId,
      task_id: recovered.task_id,
      request_nonce: `web-task-refresh-${Date.now()}-${recoveryGeneration}`,
      is_current: isCurrent,
    })
      .then(inspection => {
        if (!isCurrent()) return;
        const { record, admission } = inspection;
        formalTaskControlLeafRef.current?.disconnect();
        formalTaskControlLeafRef.current = leaf;
        progressDrainRef.current?.();
        progressTaskTargetRef.current = recovered.task_id;
        adoptCreatedProgressRoute(Object.freeze({ task_id: recovered.task_id, correlation_id: recovered.correlation_id, origin: null }));
        setP3TargetTaskId(recovered.task_id);
        const terminalStatus = productP3TerminalStatus(record);
        setP3MutationStatus(terminalStatus ?? 'accepted');
        if (admission.eligible && isFormalTaskRetryEligible(record)) {
          setP3RetryEligibility(record);
          setP3RetryInspectionStatus('eligible');
          setP3RetryInspectionReason(null);
          setP3MutationOperation('task.retry');
        } else {
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('ineligible');
          setP3RetryInspectionReason(admission.reason);
          setP3MutationOperation('task.cancel');
        }
      })
      .catch(error => {
        if (!isCurrent()) return;
        leaf.disconnect();
        recoveredP3TaskTargetRef.current = null;
        setP3RetryEligibility(null);
        setP3RetryInspectionStatus('failed');
        setP3RetryInspectionReason(productP3RetryInspectionFailureReason(error));
      });
    return () => {
      cancelled = true;
      leaf.disconnect();
      if (formalTaskControlLeafRef.current === leaf) formalTaskControlLeafRef.current = null;
      if (recoveredP3TaskTargetRef.current === recoveryIdentity) recoveredP3TaskTargetRef.current = null;
    };
  }, [correlationId, p2JournalState, productRequest, props.activeSessionId, props.isConnected]);

  useEffect(() => {
    taskExperienceOwnerRef.current?.close();
    taskExperienceOwnerRef.current = null;
    const sessionId = props.activeSessionId;
    if (!FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION) {
      taskExperienceValidatedSessionRef.current = null;
      taskExperienceRevalidationPendingSessionRef.current = null;
      setTaskExperience({
        status: 'disabled',
        session_id: null,
        tasks: Object.freeze([]),
        selected_task_id: null,
        collection_operations: Object.freeze([]),
        command: null,
        reason: 'FORMAL_P3_TASK_EXPERIENCE_DISABLED',
      });
      return;
    }
    if (sessionId === null || !hasDurableProductVoiceSession(sessionId)) {
      taskExperienceValidatedSessionRef.current = null;
      taskExperienceRevalidationPendingSessionRef.current = null;
      setTaskExperience({ status: 'idle', session_id: null, tasks: Object.freeze([]), selected_task_id: null, collection_operations: Object.freeze([]), command: null, reason: null });
      return;
    }
    if (inspectProductP3TaskTarget({ session_id: sessionId }).status === 'invalid') {
      setTaskExperience({
        status: 'failed',
        session_id: sessionId,
        tasks: Object.freeze([]),
        selected_task_id: null,
        collection_operations: Object.freeze([]),
        command: null,
        reason: 'PRODUCT_P3_TASK_TARGET_RECOVERY_REQUIRED',
      });
      return;
    }
    const owner = new FormalP3TaskExperienceOwner({
      enabled: true,
      request: (method, params, requestId) => productRequest(method, params, { requestId }),
      on_snapshot: snapshot => {
        if (taskExperienceOwnerRef.current !== owner || activeSessionRef.current !== sessionId) return;
        useLiveVoiceTaskStore.getState().publish(sessionId, owner, snapshot);
        if (snapshot.status === 'loading' && taskExperienceValidatedSessionRef.current === sessionId) {
          taskExperienceRevalidationPendingSessionRef.current = sessionId;
        }
        setTaskExperience(snapshot);
        const selected = snapshot.status === 'ready'
          ? snapshot.tasks.find(task => task.task_id === snapshot.selected_task_id)
          : undefined;
        if (snapshot.status === 'ready') {
          taskExperienceValidatedSessionRef.current = sessionId;
          taskExperienceRevalidationPendingSessionRef.current = null;
          if (selected === undefined && createdProgressRouteRef.current !== null) {
            adoptCreatedProgressRoute(null);
          }
          if (selected !== undefined && createdProgressRouteRef.current?.task_id !== selected.task_id) {
            adoptCreatedProgressRoute(Object.freeze({
              task_id: selected.task_id,
              correlation_id: selected.correlation_id,
              origin: null,
            }));
          }
        }
      },
    });
    taskExperienceOwnerRef.current = owner;
    useLiveVoiceTaskStore.getState().bind(sessionId, owner);
    setTaskExperience(owner.snapshot());
    return () => {
      useLiveVoiceTaskStore.getState().release(sessionId, owner);
      owner.close();
      if (taskExperienceOwnerRef.current === owner) taskExperienceOwnerRef.current = null;
    };
  }, [productRequest, props.activeSessionId]);

  useEffect(() => {
    const owner = taskExperienceOwnerRef.current;
    const sessionId = props.activeSessionId;
    if (owner === null || sessionId === null) return;
    if (!props.isConnected) {
      if (taskExperienceValidatedSessionRef.current === sessionId) {
        taskExperienceRevalidationPendingSessionRef.current = sessionId;
      }
      adoptCreatedProgressRoute(null);
      owner.disconnect();
      return;
    }
    // Revalidate read authority without replacing the same-Session unresolved
    // operation. Recovery is explicit and replays only its original RPC.
    void owner.refresh(sessionId).catch(() => {});
  }, [productRequest, props.activeSessionId, props.isConnected]);

  useEffect(() => {
    if (!props.isConnected) {
      p3ProgressReconciliationGenerationRef.current += 1;
      cancelP3RetryInspection();
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('idle');
      setP3RetryInspectionReason(null);
      formalTaskControlLeafRef.current?.disconnect();
      return;
    }
    const leaf = formalTaskControlLeafRef.current;
    if (leaf !== null && !leaf.snapshot().connected) {
      leaf.reconnect(leaf.snapshot().binding);
    }
  }, [props.isConnected]);

  useEffect(() => {
    const owner = taskExperienceOwnerRef.current;
    const sessionId = props.activeSessionId;
    if (!props.isConnected || owner === null || sessionId === null) return;
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;
    const isCurrent = () => !closed && mountedRef.current && isConnectedRef.current
      && activeSessionRef.current === sessionId && taskExperienceOwnerRef.current === owner;
    const refresh = async () => {
      if (!isCurrent()) return;
      try { await owner.refreshLiveTasks(sessionId, isCurrent); } catch { /* Owner retains the authoritative read failure. */ }
      if (isCurrent()) timer = setTimeout(() => { void refresh(); }, owner.snapshot().status === 'failed' ? 15_000 : 5_000);
    };
    timer = setTimeout(() => { void refresh(); }, 5_000);
    return () => { closed = true; clearTimeout(timer); };
  }, [productRequest, props.activeSessionId, props.isConnected]);

  const refreshUnifiedTaskProjection = async (value: Readonly<Record<string, unknown>>, sessionId: string, isCurrentActivation: () => boolean = () => true, selectDiscoveredTask = true): Promise<void> => {
    const result = value.result;
    const taskId = result !== null && typeof result === 'object' && !Array.isArray(result)
      ? (result as Record<string, unknown>).task_id : undefined;
    if (typeof taskId !== 'string') return;
    const owner = taskExperienceOwnerRef.current;
    const isCurrent = () => owner !== null && taskExperienceOwnerRef.current === owner
      && activeSessionRef.current === sessionId && isConnectedRef.current && isCurrentActivation();
    if (!isCurrent() || owner === null) return;
    await owner.refresh(sessionId, isCurrent);
    if (!isCurrent()) return;
    if (!owner.snapshot().tasks.some(task => task.task_id === taskId)) {
      throw new Error('FORMAL_P3_UNIFIED_TASK_DISCOVERY_UNAVAILABLE');
    }
    if (selectDiscoveredTask && owner.snapshot().selected_task_id !== taskId) await owner.select(taskId, isCurrent);
  };

  const submitProductText = async (overrideText?: string, source: 'structured' | 'voice' = 'structured'): Promise<ProductTurnInput | null> => {
    const owner = activationOwnerRef.current;
    const binding = currentProductP2Binding();
    const text = overrideText ?? productInput;
    if (!owner || binding === null || p2Activation.status !== 'active' || !text.trim()) return null;
    if (productTextBlockedByP1Status(p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus)) return null;
    if (source === 'voice') {
      const recognized = recognizedVoiceRef.current;
      if (recognized === null || recognized.text !== text || !recognizedVoiceMatchesProductBinding(recognized, binding)) return null;
      await submitUnifiedRecognizedVoice(recognized, binding);
      return null;
    }
    if (pendingUnifiedFinalRef.current || pendingPresentationAttemptRef.current || pendingBargeInRef.current ||
        owner.hasPendingPresentationAck() || owner.hasPendingPresentationFailure() ||
        ownerHasUnsettledGenerationInterrupt(owner)) return null;
    let retained = pendingProductTurnRef.current;
    if (retained !== null && retained.owner !== owner) return null;
    if (retained === null) {
      const identity = `${Date.now()}-${++productTurnSequenceRef.current}`;
      retained = { owner, input: { commit_id: `web-commit-${identity}`, turn_id: `web-turn-${identity}`,
        committed_at: new Date().toISOString(), text } };
      pendingProductTurnRef.current = retained;
      setProductOutput(null);
    }
    let unified = unifiedInputOwnerRef.current;
    if (unified === null) {
      unified = new ProductUnifiedCommittedInputOwner((method, params, requestId) =>
        productRequest(method, params, productP2WebRequestOptions(method, requestId)));
      unifiedInputOwnerRef.current = unified;
    }
    const input = { request_id: `unified-text-${retained.input.commit_id}`, commit_id: retained.input.commit_id,
      turn_id: retained.input.turn_id, committed_at: retained.input.committed_at,
      text: retained.input.text, input_kind: 'text' as const };
    setProductTextStatus('submitting');
    setProductTextReason(null);
    try {
      const submitted = await retryRetainedProductOperation({
        operation: () => unified!.submit(binding, input),
        is_current: () => activationOwnerRef.current === owner && activeSessionRef.current === binding.session_id && isConnectedRef.current,
      });
      if (activationOwnerRef.current !== owner || pendingProductTurnRef.current !== retained) return null;
      pendingProductTurnRef.current = null;
      setProductInput('');
      setProductTextStatus('waiting');
      setP2NotificationWakeEpoch(epoch => epoch + 1);
      await refreshUnifiedTaskProjection(submitted, binding.session_id);
      return retained.input;
    } catch (error) {
      if (activationOwnerRef.current === owner) {
        // Keep exact input/request identity for unknown outcome recovery.
        if (!unified.hasPending()) pendingProductTurnRef.current = null;
        setProductTextReason(stableProductTextReason(error, 'UNIFIED_INPUT_FAILED'));
        setProductTextStatus('failed');
      }
      return null;
    }
  };

  const loadProductAudioDevices = async () => {
    const owner = deviceSelectionOwnerRef.current;
    if (owner === null) return;
    try {
      const snapshot = await owner.load();
      if (deviceSelectionOwnerRef.current !== owner) return;
      setDraftInputDeviceToken(snapshot.applied_input_token);
      setDraftOutputDeviceToken(snapshot.applied_output_token);
    } catch (error) {
      const reason = extractWebErrorReason(error) ?? 'AUDIO_DEVICE_SELECTION_FAILED';
      console.warn(`live_voice_audio_device_selection_failure reason=${reason} fallback=text visible=true`);
    }
  };

  const applyProductAudioDevices = async () => {
    const selectionOwner = deviceSelectionOwnerRef.current;
    if (
      selectionOwner === null ||
      pendingUnifiedFinalRef.current !== null ||
      pendingForegroundPresentationRef.current !== null ||
      pendingPresentationAttemptRef.current !== null ||
      ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus)
    ) return;
    const voiceOwner = p1VoiceOwnerRef.current;
    if (voiceOwner !== null) {
      try {
        await voiceOwner.close();
      } catch {
        console.warn('live_voice_audio_device_selection_failure reason=FORMAL_P1_DEVICE_CHANGE_CLOSE_FAILED fallback=text visible=true');
        return;
      }
      if (p1VoiceOwnerRef.current === voiceOwner) p1VoiceOwnerRef.current = null;
    }
    try {
      selectionOwner.apply({
        inventory_generation: deviceSelection.inventory_generation,
        input_token: draftInputDeviceToken,
        output_token: draftOutputDeviceToken,
      });
      setP1VoiceStatus('idle');
      setP1VoiceReason(null);
    } catch (error) {
      const reason = extractWebErrorReason(error) ?? 'AUDIO_DEVICE_SELECTION_FAILED';
      console.warn(`live_voice_audio_device_selection_failure reason=${reason} fallback=text visible=true`);
    }
  };

  const voiceProgressIsCurrent = (entry: NonNullable<ReturnType<typeof voiceProgressOwnersRef.current.get>>): boolean => {
    const current = currentProductP2Binding();
    return !entry.closed && voiceLoopEnabledRef.current && entry.voice_generation === voiceLoopGenerationRef.current
      && mountedRef.current && isConnectedRef.current
      && activeSessionRef.current === entry.binding.session_id
      && current?.activation_id === entry.binding.activation_id
      && current.activation_generation === entry.binding.activation_generation
      && current.interaction_id === entry.binding.interaction_id;
  };
  const desiredVoiceProgressIsCurrent = (taskId: string): boolean => {
    const desired = desiredVoiceProgressRef.current.get(taskId);
    const current = currentProductP2Binding();
    return desired !== undefined && voiceLoopEnabledRef.current && mountedRef.current && isConnectedRef.current
      && desired.voice_generation === voiceLoopGenerationRef.current
      && activeSessionRef.current === desired.binding.session_id
      && current?.activation_id === desired.binding.activation_id
      && current.activation_generation === desired.binding.activation_generation
      && current.interaction_id === desired.binding.interaction_id;
  };
  const ownsVoiceProgressTask = (taskId: string): boolean => {
    const entry = voiceProgressOwnersRef.current.get(taskId);
    return entry !== undefined ? voiceProgressIsCurrent(entry)
      : desiredVoiceProgressIsCurrent(taskId) || (createdProgressRouteRef.current?.task_id === taskId && createdProgressRouteRef.current.origin?.kind === 'voice');
  };
  const markVoiceTaskTerminalPresented = (taskId: string | null) => {
    const entry = taskId === null ? undefined : voiceProgressOwnersRef.current.get(taskId);
    if (entry !== undefined) entry.terminal_presented = true;
    // Settling B does not settle A's unread completion. Recompute immediately,
    // before scheduling capture/polls; a future React render is not a fence.
    terminalNotificationCheckRequiredRef.current = [...voiceProgressOwnersRef.current.values()]
      .some(candidate => !candidate.closed && !candidate.terminal_presented);
  };
  const closeVoiceProgress = (taskId: string, entry: NonNullable<ReturnType<typeof voiceProgressOwnersRef.current.get>>) => {
    entry.closed = true;
    entry.retry_abort.abort();
    entry.leaf?.disconnect();
    return entry.owner.closeWithRetry().then(() => {
      if (voiceProgressOwnersRef.current.get(taskId) === entry) voiceProgressOwnersRef.current.delete(taskId);
    });
  };
  const ensureVoiceTaskProgress = async (taskId: string, binding: Readonly<ProductWebP2ActivationBinding>): Promise<void> => {
    if (!desiredVoiceProgressIsCurrent(taskId)) {
      for (const id of desiredVoiceProgressRef.current.keys()) {
        if (!desiredVoiceProgressIsCurrent(id)) desiredVoiceProgressRef.current.delete(id);
      }
      if (desiredVoiceProgressRef.current.size >= 128) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_CAPACITY');
      desiredVoiceProgressRef.current.set(taskId, { binding, voice_generation: voiceLoopGenerationRef.current, retryable: true });
    }
    const previous = voiceProgressOwnersRef.current.get(taskId);
    if (previous !== undefined) {
      if (voiceProgressIsCurrent(previous)) return previous.ready;
      await closeVoiceProgress(taskId, previous);
      // Several recovery/selection callbacks can await the same exact close.
      // Join the successor created by the first continuation, never replace it.
      const successor = voiceProgressOwnersRef.current.get(taskId);
      if (successor !== undefined) {
        if (voiceProgressIsCurrent(successor)) return successor.ready;
        throw new Error('PRODUCT_VOICE_TASK_PROGRESS_CLEANUP_PENDING');
      }
    }
    if (voiceProgressOwnersRef.current.size >= 128) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_CAPACITY');
    let owner: ProductWebP3ProgressOwner;
    owner = new ProductWebP3ProgressOwner({
      enabled: true,
      request: (method, params) => productRequest(method,
        method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? { ...params, origin_kind: 'voice' } : params),
      on_snapshot: snapshot => {
        const current = voiceProgressOwnersRef.current.get(taskId);
        if (current === undefined || current.owner !== owner || !voiceProgressIsCurrent(current)) return;
        if (createdProgressRouteRef.current?.task_id === taskId) setP3Activation(snapshot);
        if (snapshot.status === 'active') progressDrainRef.current?.();
      },
    });
    const entry = { binding, owner, leaf: null as FormalTaskControlLeaf | null, closed: false, terminal_presented: false, notification_chinese: false,
      notification_name: null as string | null,
      voice_generation: voiceLoopGenerationRef.current, retry_abort: new AbortController(), ready: Promise.resolve() };
    voiceProgressOwnersRef.current.set(taskId, entry);
    const isCurrent = () => voiceProgressOwnersRef.current.get(taskId) === entry && voiceProgressIsCurrent(entry);
    entry.ready = (async () => {
      if (!isCurrent()) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_STALE');
      // Keep the exact voice owner while read-only initialization retries. A
      // transient read must not turn a newly created voice Task into a text route.
      for (let attempt = 0; ; attempt += 1) {
        try {
          const response = await productRequest(PRODUCT_P3_TASK_STATUS_METHOD, { session_id: binding.session_id, task_id: taskId });
          if (!isCurrent()) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_STALE');
          entry.leaf = bootstrapProductP3TaskInspectionLeaf(response, { session_id: binding.session_id, task_id: taskId });
          const task = recordValue(recordValue(recordValue(response)?.result)?.task);
          const instruction = recordValue(task?.spec)?.instruction;
          const name = recordValue(task?.spec)?.name;
          // Match the server's language projection from this validated exact Task,
          // including the content used by durable TEXT-fallback history IDs.
          entry.notification_chinese = typeof instruction === 'string' && /[\u4e00-\u9fff]/.test(instruction);
          entry.notification_name = typeof name === 'string' && name.trim() ? name : taskId;
          await inspectProductP3RetryCandidate({ request: productRequest, leaf: entry.leaf, session_id: binding.session_id,
            task_id: taskId, request_nonce: `voice-progress-${Date.now()}`, is_current: isCurrent });
          if (!isCurrent()) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_STALE');
          break;
        } catch (error) {
          const reason = extractWebErrorReason(error) ?? recordValue(error)?.code;
          if (!isCurrent() || attempt >= PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS.length
            || !['REQUEST_TIMEOUT', 'UNAVAILABLE', 'PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH'].includes(String(reason ?? ''))) throw error;
          entry.leaf?.disconnect();
          entry.leaf = null;
          await (props.p3RetryInspectionWait ?? defaultP3RetryInspectionWait)(
            PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS[attempt]!, entry.retry_abort.signal);
          if (!isCurrent()) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_STALE');
        }
      }
      const identity = { session_id: binding.session_id, correlation_id: binding.correlation_id,
        origin_id: binding.interaction_id, generation_id: `${binding.correlation_id}:voice-progress` };
      await owner.start({ ...identity, task_id: taskId,
        generation: id => claimProductP3ProgressGeneration({ ...identity, task_id: id }) });
      if (!isCurrent()) throw new Error('PRODUCT_VOICE_TASK_PROGRESS_STALE');
      progressDrainRef.current?.();
    })().catch(async error => {
      const desired = desiredVoiceProgressRef.current.get(taskId);
      if (desired?.binding === binding) {
        const reason = extractWebErrorReason(error) ?? recordValue(error)?.code;
        desired.retryable = ['REQUEST_TIMEOUT', 'UNAVAILABLE', 'PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH'].includes(String(reason ?? ''));
      }
      try { await closeVoiceProgress(taskId, entry); } catch { /* Retain the exact cleanup-pending owner. */ }
      throw error;
    });
    return entry.ready;
  };
  useEffect(() => {
    for (const taskId of desiredVoiceProgressRef.current.keys()) {
      if (!desiredVoiceProgressIsCurrent(taskId)) desiredVoiceProgressRef.current.delete(taskId);
    }
    for (const [taskId, entry] of voiceProgressOwnersRef.current) {
      if (!voiceProgressIsCurrent(entry)) void closeVoiceProgress(taskId, entry).catch(() => undefined);
    }
  }, [props.activeSessionId, props.isConnected, p2Activation.status, p2Activation.binding?.activation_id, p2Activation.binding?.activation_generation]);
  useEffect(() => () => {
    desiredVoiceProgressRef.current.clear();
    for (const [taskId, entry] of voiceProgressOwnersRef.current) void closeVoiceProgress(taskId, entry).catch(() => undefined);
  }, []);
  useEffect(() => {
    const owner = activationOwnerRef.current;
    const binding = currentProductP2Binding();
    if (!voiceLoopEnabledRef.current || owner === null || binding === null || !props.isConnected) return;
    const discovery = owner.voiceTaskDiscovery();
    if (discovery.reason !== null) setP3RetryInspectionReason(discovery.reason);
    let cancelled = false;
    void (async () => {
      const taskIds = new Set([...discovery.task_ids, ...[...desiredVoiceProgressRef.current]
        .filter(([id, desired]) => desired.retryable && desiredVoiceProgressIsCurrent(id)).map(([id]) => id)]);
      for (const taskId of taskIds) {
        if (cancelled || !voiceLoopEnabledRef.current || activationOwnerRef.current !== owner) return;
        try { await ensureVoiceTaskProgress(taskId, binding); }
        catch (error) {
          if (!cancelled) setP3RetryInspectionReason(stableProductTextReason(error, 'PRODUCT_VOICE_TASK_RECOVERY_FAILED'));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [props.activeSessionId, props.isConnected, p2Activation.status, p2Activation.binding?.activation_id, p1VoiceStatus]);

  const bootstrapCreatedP3ProgressRoute = async (
    taskId: string,
    binding: Readonly<NonNullable<ProductWebP2ActivationSnapshot['binding']>>,
    isCurrentActivation: () => boolean = () => true,
  ): Promise<boolean> => {
    const isCurrentSession = () => mountedRef.current && activeSessionRef.current === binding.session_id && isCurrentActivation();
    if (!isCurrentSession()) return false;
    if (progressTaskTargetRef.current !== taskId) {
      progressRef.current = null;
      if (voiceProgressOwnersRef.current.size === 0) pendingOwnedProgressRef.current.clear();
      setProgress(null);
      setProgressAck('idle');
    }
    // task.create has already succeeded.  Publish only that immutable identity
    // before any status/events recovery so a failed bootstrap can never cause
    // the retained unified input owner to replay the mutation.
    progressTaskTargetRef.current = taskId;
    setP3TargetTaskId(taskId);
    setP3MutationStatus('accepted');
    setP3MutationReason(null);
    const waitForRetry = props.p3RetryInspectionWait ?? defaultP3RetryInspectionWait;
    const retryWaitAbort = new AbortController();
    let lastFailure: unknown = new Error('PRODUCT_P3_CREATED_TASK_BOOTSTRAP_FAILED');
    for (let attempt = 0; attempt <= PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS.length; attempt += 1) {
      if (!isCurrentSession()) return false;
      try {
        await inspectP3RetryEligibility({
          task_id: taskId,
          progress_origin: Object.freeze({ kind: 'voice' as const, id: binding.interaction_id }),
          replace_leaf: true,
          throw_on_failure: true,
          is_current: isCurrentSession,
        });
        if (!isCurrentSession()) return false;
        const route = createdProgressRouteRef.current;
        const leafSnapshot = formalTaskControlLeafRef.current?.snapshot() ?? null;
        if (
          route?.task_id === taskId &&
          route.origin?.kind === 'voice' &&
          route.origin.id === binding.interaction_id &&
          leafSnapshot?.tasks.some(task => task.task_id === taskId)
        ) {
          await ensureVoiceTaskProgress(taskId, binding);
          return isCurrentSession();
        }
        lastFailure = new Error('PRODUCT_P3_CREATED_TASK_BOOTSTRAP_FAILED');
      } catch (error) {
        lastFailure = error;
      }
      if (attempt >= PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS.length) break;
      await waitForRetry(PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS[attempt]!, retryWaitAbort.signal);
    }
    if (!isCurrentSession()) return false;
    setP3RetryEligibility(null);
    setP3RetryInspectionStatus('failed');
    setP3RetryInspectionReason(stableProductTextReason(lastFailure, 'PRODUCT_P3_CREATED_TASK_BOOTSTRAP_FAILED'));
    throw new Error('PRODUCT_P3_CREATED_TASK_BOOTSTRAP_FAILED');
  };

  /**
   * Name the exact answer this committed final replaces, if one is still live.
   *
   * Speech-start normally fences that answer first and clears the foreground
   * fence. This is the atomic fallback for the race where the utterance ends
   * before that fence settled: the server then supersedes the exact response in
   * the same admission that accepts the replacement turn.
   */
  const supersededGenerationTarget = (
    binding: Readonly<NonNullable<ProductWebP2ActivationSnapshot['binding']>>,
  ): Readonly<{ response_id: string; response_generation: number }> | null => {
    const fence = pendingForegroundPresentationRef.current;
    if (
      !FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION ||
      fence === null ||
      fence.session_id !== binding.session_id ||
      fence.correlation_id !== binding.correlation_id ||
      fence.interaction_id !== binding.interaction_id ||
      fence.activation_id !== binding.activation_id ||
      fence.activation_generation !== binding.activation_generation
    ) {
      return null;
    }
    return Object.freeze({
      response_id: fence.response_id,
      response_generation: fence.response_generation,
    });
  };

  const submitUnifiedRecognizedVoice = (
    recognized: ProductRecognizedVoice,
    binding: Readonly<NonNullable<ProductWebP2ActivationSnapshot['binding']>>,
  ): Promise<void> => {
    const fingerprint = JSON.stringify({
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: binding.interaction_id,
      activation_id: binding.activation_id,
      activation_generation: binding.activation_generation,
      text: recognized.text,
    });
    const retained = submittedVoiceFinalsRef.current.get(recognized.voice_commit_receipt);
    if (retained !== undefined) {
      if (retained.fingerprint !== fingerprint) {
        return Promise.reject(new Error('voice final identity changed its committed content'));
      }
      return retained.operation;
    }
    productTurnSequenceRef.current += 1;
    const identity = `${Date.now()}-${productTurnSequenceRef.current}`;
    const input: UnifiedAuthoritativeFinal = Object.freeze({
      request_id: `live-voice-unified-${identity}`,
      commit_id: `web-commit-${identity}`,
      turn_id: `web-turn-${identity}`,
      committed_at: new Date().toISOString(),
      text: recognized.text,
      voice_commit_receipt: recognized.voice_commit_receipt,
    });
    const originVoiceLoopGeneration = voiceLoopGenerationRef.current;
    // The recognized capture owner is also the only P1 authority allowed to
    // synthesize and play the response to this committed final. Retain it
    // before unified.submit so a Task notification or an automatic successor
    // capture cannot rotate the foreground playout authority while the server
    // is assigning the exact response generation.
    const foregroundPlayoutOwner = p1VoiceOwnerRef.current;
    const operation = (async () => {
      let presentationFence: PendingForegroundPresentationFence | null = null;
      let owner = unifiedInputOwnerRef.current;
      if (owner === null) {
        owner = new ProductUnifiedCommittedInputOwner((method, params, requestId) =>
          productRequest(method, params, productP2WebRequestOptions(method, requestId)),
        );
        unifiedInputOwnerRef.current = owner;
      }
      pendingUnifiedFinalRef.current = Object.freeze({
        receipt: recognized.voice_commit_receipt,
        input,
        playout_owner: foregroundPlayoutOwner,
        voice_loop_generation: originVoiceLoopGeneration,
      });
      setProductOutput(null);
      setProductTextReason(null);
      setProductTextStatus('submitting');
      const submittingActivation = activationOwnerRef.current;
      const submittingBinding = submittingActivation?.snapshot().binding;
      if (FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION && voiceLoopEnabledRef.current &&
          submittingActivation !== null && submittingBinding != null && generationCaptureRef.current === null &&
          sameProductP2ActivationBinding(submittingBinding, binding)) {
        const capture = {
          owner: submittingActivation, input, loop_generation: originVoiceLoopGeneration, speech_started: false,
        };
        submissionCaptureRef.current = capture;
        void startP1VoiceHandlerRef.current().catch(() => {
          if (submissionCaptureRef.current === capture) submissionCaptureRef.current = null;
        });
      }
      try {
        const supersedes = supersededGenerationTarget(binding);
        const submitResult = await retryRetainedProductOperation({
          operation: () => owner!.submit(binding, input, supersedes),
          is_current: () =>
            activationOwnerRef.current?.snapshot().status === 'active' &&
            activeSessionRef.current === binding.session_id,
        });
        // Submission ownership is represented by pendingUnifiedFinalRef.
        // Presentation ownership begins only after the server has accepted
        // this exact final; the wake epoch below can then restart a poll that
        // yielded while the network request was in flight.
        const unifiedResult = (submitResult as Readonly<Record<string, unknown>>).result as
          | Readonly<Record<string, unknown>>
          | null
          | undefined;
        const acceptedResponse = recordValue(unifiedResult?.response);
        if (
          acceptedResponse?.interaction_id !== binding.interaction_id ||
          typeof acceptedResponse.response_id !== 'string' ||
          !Number.isSafeInteger(acceptedResponse.response_generation)
        ) {
          throw new Error('accepted unified response lost its presentation binding');
        }
        presentationFence = Object.freeze({
          session_id: binding.session_id,
          correlation_id: binding.correlation_id,
          interaction_id: binding.interaction_id,
          activation_id: binding.activation_id,
          activation_generation: binding.activation_generation,
          response_id: acceptedResponse.response_id,
          response_generation: acceptedResponse.response_generation as number,
          playout_owner: foregroundPlayoutOwner,
          voice_loop_generation: originVoiceLoopGeneration,
        });
        const retainsCurrentSession = mountedRef.current && activeSessionRef.current === binding.session_id;
        const retainsOriginVoiceLoop =
          retainsCurrentSession &&
          voiceLoopEnabledRef.current &&
          voiceLoopGenerationRef.current === originVoiceLoopGeneration;
        const currentActivation = activationOwnerRef.current?.snapshot();
        const retainsSubmittingActivation =
          retainsOriginVoiceLoop &&
          currentActivation?.status === 'active' &&
          currentActivation.binding !== null &&
          sameProductP2ActivationBinding(currentActivation.binding, binding);
        if (retainsSubmittingActivation) {
          pendingForegroundPresentationRef.current = presentationFence;
          // A retained Task presentation needs one post-fence poll admission.
          // Both the scheduler wake and its foreground fence belong to the
          // exact activation that submitted this final. A same-Session P2
          // successor must own its own continuation.
          if (deferredTaskPresentationRef.current?.owner === activationOwnerRef.current) {
            setForegroundPresentationEpoch(epoch => epoch + 1);
          }
        }
        if (pendingUnifiedFinalRef.current?.input === input) {
          pendingUnifiedFinalRef.current = null;
        }
        const submissionCapture = submissionCaptureRef.current;
        if (submissionCapture?.input === input) {
          submissionCaptureRef.current = null;
          if (retainsSubmittingActivation) {
            generationCaptureRef.current = Object.freeze({
              owner: submissionCapture.owner, fence: presentationFence,
              loop_generation: originVoiceLoopGeneration,
            });
            if (submissionCapture.speech_started) await interruptProductGenerationHandlerRef.current();
          }
        }
        if (recognizedVoiceRef.current === recognized) recognizedVoiceRef.current = null;
        if (!retainsCurrentSession || !mountedRef.current || activeSessionRef.current !== binding.session_id) return;
        props.onProductVoiceMessage?.(
          Object.freeze({
            session_id: binding.session_id,
            message: Object.freeze({
              id: `live-voice:${input.commit_id}:user`,
              role: 'user',
              content: input.text,
              timestamp: input.committed_at,
            }),
          }),
        );
        const createdTaskId =
          typeof unifiedResult?.task_id === 'string' && unifiedResult.task_id.trim()
            ? unifiedResult.task_id
            : null;
        if (createdTaskId !== null) {
          const reportDiscoveryFailure = (error: unknown) => {
            if (mountedRef.current && activeSessionRef.current === binding.session_id &&
                activationOwnerRef.current === submittingActivation) {
              setP3RetryInspectionStatus('failed');
              setP3RetryInspectionReason(stableProductTextReason(error, 'PRODUCT_P3_CREATED_TASK_BOOTSTRAP_FAILED'));
            }
          };
          const existing = voiceProgressOwnersRef.current.get(createdTaskId);
          if (existing === undefined || !voiceProgressIsCurrent(existing)) {
            // Register the exact Task owner synchronously before polling. Its
            // authoritative status/events bootstrap owns its own recovery, so
            // those reads cannot hold an already accepted spoken answer hostage.
            // Queries of an already watched Task need no second bootstrap.
            void ensureVoiceTaskProgress(createdTaskId, binding).catch(reportDiscoveryFailure);
          }
          // Use the same authoritative Task collection projection as typed
          // unified input. The old retry-inspection UI is not a speech barrier.
          void refreshUnifiedTaskProjection(submitResult, binding.session_id).catch(reportDiscoveryFailure);
        }
        if (!retainsSubmittingActivation) return;
        if (
          !mountedRef.current ||
          activeSessionRef.current !== binding.session_id ||
          pendingForegroundPresentationRef.current !== presentationFence
        ) {
          return;
        }
        setProductTextStatus('waiting');
        setP2NotificationWakeEpoch(epoch => epoch + 1);
        // Listen while the Agent generates. Nothing in this window can commit
        // by itself: only a provider speech-start fences this exact answer, and
        // only the later EOT submits what the user actually said.
        const generationOwner = activationOwnerRef.current;
        if (generationOwner !== null) scheduleGenerationTimeCapture(generationOwner, presentationFence);
      } catch (error) {
        if (submissionCaptureRef.current?.input === input) submissionCaptureRef.current = null;
        if (pendingForegroundPresentationRef.current === presentationFence) {
          pendingForegroundPresentationRef.current = null;
        }
        let settledWithoutPresentation = false;
        if (!owner.hasPending() && pendingUnifiedFinalRef.current?.input === input) {
          pendingUnifiedFinalRef.current = null;
          settledWithoutPresentation = true;
        }
        if (recognizedVoiceRef.current === recognized) recognizedVoiceRef.current = null;
        if (!mountedRef.current || activeSessionRef.current !== binding.session_id) return;
        setProductTextReason(stableProductTextReason(error, 'UNIFIED_INPUT_FAILED'));
        setProductTextStatus('failed');
        if (settledWithoutPresentation) {
          const activationOwner = activationOwnerRef.current;
          const deferredTaskSettlementStarted =
            activationOwner !== null && settleDeferredTaskPresentation(activationOwner);
          if (!deferredTaskSettlementStarted && !continuePendingVoiceLoopP2Refresh()) {
            scheduleProductVoiceLoopCapture();
          }
        }
      }
    })();
    if (submittedVoiceFinalsRef.current.size >= 128) {
      const oldest = submittedVoiceFinalsRef.current.keys().next().value;
      if (typeof oldest === 'string') submittedVoiceFinalsRef.current.delete(oldest);
    }
    submittedVoiceFinalsRef.current.set(
      recognized.voice_commit_receipt,
      Object.freeze({ fingerprint, operation }),
    );
    return operation;
  };

  const startProductVoiceCaptureOwned = async () => {
    const loopGeneration = voiceLoopGenerationRef.current;
    updateRecognizedSpeechConfirmation(null);
    p1VoiceCaptureBindingRef.current = null;
    const binding = currentProductP2Binding();
    const retainedTerminalRecovery =
      terminalAnnouncementStateRef.current === 'recovering' && pendingPresentationAttemptRef.current?.task_notification?.retry_pending === true;
    // Listening while an Agent answer is still being generated is admitted only
    // for the exact response that capture was bound to. Every other foreground
    // fence keeps its original barrier, so an unrelated in-flight turn, ACK or
    // barge-in still refuses a new capture.
    const admitsGenerationCapture = () => {
      const retained = generationCaptureRef.current;
      const fence = pendingForegroundPresentationRef.current;
      return (
        retained !== null &&
        fence !== null &&
        retained.fence === fence &&
        retained.loop_generation === loopGeneration &&
        retained.owner === activationOwnerRef.current
      );
    };
    const admitsSubmissionCapture = () => {
      const retained = submissionCaptureRef.current;
      return retained !== null && retained.input === pendingUnifiedFinalRef.current?.input &&
        retained.owner === activationOwnerRef.current && retained.loop_generation === loopGeneration;
    };
    const hasCaptureAuthorityBarrier = () =>
      pendingProductTurnRef.current !== null ||
      (pendingUnifiedFinalRef.current !== null && !admitsSubmissionCapture()) ||
      (pendingForegroundPresentationRef.current !== null && !admitsGenerationCapture()) ||
      deferredTaskPresentationRef.current !== null ||
      (pendingPresentationAttemptRef.current !== null && !retainedTerminalRecovery) ||
      pendingBargeInRef.current !== null ||
      Boolean(activationOwnerRef.current?.hasPendingSubmission()) ||
      Boolean(activationOwnerRef.current?.hasPendingPresentationAck()) ||
      Boolean(activationOwnerRef.current?.hasPendingPresentationFailure()) ||
      Boolean(activationOwnerRef.current?.hasPendingBargeIn()) ||
      ownerHasUnsettledGenerationInterrupt(activationOwnerRef.current) ||
      Boolean(activationOwnerRef.current?.hasPendingGenerationInterrupt());
    const isCurrentBinding = () => {
      const activation = activationOwnerRef.current?.snapshot();
      const current = activation?.binding;
      return (
        mountedRef.current &&
        isConnectedRef.current &&
        voiceLoopEnabledRef.current &&
        voiceLoopGenerationRef.current === loopGeneration &&
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
      binding === null ||
      typeof window === 'undefined' ||
      hasCaptureAuthorityBarrier()
    )
      return;
    let owner = p1VoiceOwnerRef.current;
    if (owner !== null && p1VoiceOwnerSessionRef.current !== binding.session_id) {
      await owner.close();
      if (p1VoiceOwnerRef.current === owner) {
        p1VoiceOwnerRef.current = null;
        p1VoiceOwnerSessionRef.current = null;
      }
      owner = null;
    }
    if (owner && ['failed', 'cleanup_pending'].includes(owner.status().status)) {
      await owner.close();
      if (p1VoiceOwnerRef.current === owner) {
        p1VoiceOwnerRef.current = null;
        p1VoiceOwnerSessionRef.current = null;
      }
      owner = null;
    }
    if (!isCurrentBinding()) return;
    const activationOwner = activationOwnerRef.current;
    if (activationOwner === null) return;
    try {
      await activationOwner.refreshMediaAuthority();
    } catch (error) {
      const reason = extractWebErrorReason(error) ?? 'MEDIA_PRODUCT_ACTIVATION_UNTRUSTED';
      const predecessorIsClosedNativeRuntime = reason === 'NATIVE_RUNTIME_CLOSED';
      console.warn(`live_voice_media_authority_refresh_failure reason=${reason} fallback=text visible=true`);
      if (activationOwnerRef.current === activationOwner && mountedRef.current && activeSessionRef.current === binding.session_id) {
        // Persist the state-loss barrier before cleanup so a reload cannot
        // reinterpret a later stale/closed tombstone as permission to prepare
        // a successor after the stable response-generation owner was lost.
        let barrierPersisted = false;
        let closedNativeRuntimeCheckpointed = false;
        const journal = p2ActivationJournalRef.current;
        if (journal !== null) {
          try {
            const journalSnapshot = journal.refresh();
            const journalBinding = journalSnapshot.binding;
            const bindingMatches =
              journalBinding !== null &&
              journalBinding.session_id === binding.session_id &&
              journalBinding.correlation_id === binding.correlation_id &&
              journalBinding.interaction_id === binding.interaction_id &&
              journalBinding.activation_id === binding.activation_id &&
              journalBinding.activation_generation === binding.activation_generation;
            if (journalSnapshot.phase === 'result_unknown' && bindingMatches) {
              barrierPersisted = true;
            }
            if (journalSnapshot.phase === 'active' && journalSnapshot.pending_operation === null && journalSnapshot.recovery_token === null && bindingMatches) {
              if (predecessorIsClosedNativeRuntime) {
                // The Provider has authoritatively declared this exact Native
                // predecessor closed.  Preserve the exact binding while local
                // teardown runs, then one Start may allocate its successor.
                journal.markClosing(binding);
                voiceLoopP2RefreshCauseRef.current = 'native_closed';
                closedNativeRuntimeCheckpointed = true;
                voiceLoopP2RefreshAfterGenerationRef.current = Math.max(
                  voiceLoopP2RefreshAfterGenerationRef.current ?? binding.activation_generation,
                  binding.activation_generation,
                );
                voiceLoopP2RefreshInFlightRef.current = false;
              } else {
                journal.markResultUnknown(binding);
                barrierPersisted = true;
              }
            }
          } catch {
            // Journal ownership/storage failure remains a local hard barrier;
            // exact server cleanup is still attempted below.
          }
        }
        // Close the possibly renewed/new server route now, but never mark the
        // predecessor closed or prepare a successor from unknown continuity.
        try {
          await activationOwner.closeWithRetry({ cause: predecessorIsClosedNativeRuntime ? 'native_closed' : 'media_authority_failure' });
          retireDeferredTaskPresentationForClosedOwner(activationOwner);
          retireCapturedTaskNotificationForClosedOwner(activationOwner);
          if (closedNativeRuntimeCheckpointed && journal !== null && mountedRef.current && activeSessionRef.current === binding.session_id) {
            let exactCloseCheckpointed = false;
            try {
              const latest = journal.refresh();
              const latestBinding = latest.binding;
              const exactBinding =
                latestBinding !== null &&
                latestBinding.session_id === binding.session_id &&
                latestBinding.correlation_id === binding.correlation_id &&
                latestBinding.interaction_id === binding.interaction_id &&
                latestBinding.activation_id === binding.activation_id &&
                latestBinding.activation_generation === binding.activation_generation;
              if (latest.phase === 'closed' && exactBinding) {
                exactCloseCheckpointed = true;
              } else if (latest.recovery_token === null && exactBinding) {
                journal.markClosed(binding);
                exactCloseCheckpointed = true;
              }
            } catch {
              // A concurrent recovery owner remains the only authority that
              // may close this checkpoint and allocate its successor.
            }
            if (exactCloseCheckpointed) {
              if (activationOwnerRef.current === activationOwner) activationOwnerRef.current = null;
              let successorBinding: ProductWebP2ActivationBinding;
              try {
                successorBinding = journal.prepareSuccessor(pageInstanceIdRef.current!);
              } catch {
                setP2Activation({
                  status: 'unavailable',
                  binding: null,
                  reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
                });
                return;
              }
              activationGenerationRef.current = successorBinding.activation_generation;
              let successorOwner: ProductWebP2ActivationOwner | null = null;
              successorOwner = createProductP2ActivationOwner({
                ...(selectedAgentModelNameRef.current ? { agent_model_selection: { contract_version: AGENT_MODEL_SELECTION_VERSION, model_name: selectedAgentModelNameRef.current } } : {}),
                enabled: true,
                request: (method, params, requestId) =>
                  productRequest(method, params, productP2WebRequestOptions(method, requestId)),
                durable_operation_journal: journal,
                on_snapshot: snapshot => {
                  if (
                    mountedRef.current &&
                    activeSessionRef.current === binding.session_id &&
                    activationOwnerRef.current === successorOwner &&
                    snapshot.status !== 'active'
                  ) {
                    setP2Activation(snapshot);
                  }
                },
              });
              activationOwnerRef.current = successorOwner;
              try {
                const activated = await successorOwner.start(successorBinding);
                if (
                  !mountedRef.current ||
                  activeSessionRef.current !== binding.session_id ||
                  activationOwnerRef.current !== successorOwner
                ) {
                  return;
                }
                journal.markActive(successorBinding);
                setP2Activation(activated);
                setProductTextReason(null);
                clearProductRecoveryDiagnostic({
                  seam: 'activation',
                  binding: activated.binding,
                });
                if (activated.binding !== null) resumeVoiceLoopAfterP2Successor(activated.binding);
              } catch (successorError) {
                if (
                  mountedRef.current &&
                  activeSessionRef.current === binding.session_id &&
                  activationOwnerRef.current === successorOwner
                ) {
                  const successorReason = stableProductTextReason(
                    successorError,
                    PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
                  );
                  publishProductRecoveryDiagnostic({
                    seam: 'activation',
                    disposition: 'retrying',
                    reason: successorReason,
                    binding: successorBinding,
                  });
                  setP2Activation({
                    status: 'unavailable',
                    binding: null,
                    reason: successorReason,
                  });
                  setP2RecoveryEpoch(epoch => epoch + 1);
                }
              }
              return;
            }
          }
          if (activationOwnerRef.current === activationOwner && mountedRef.current && activeSessionRef.current === binding.session_id) {
            if (barrierPersisted) activationOwnerRef.current = null;
            setP2Activation({
              status: 'unavailable',
              binding: null,
              reason: PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
            });
          }
        } catch {
          // The exact cleanup_pending owner remains retained for teardown; no
          // successor or media effect may be allocated on unknown close truth.
        }
      }
      return;
    }
    if (activationOwnerRef.current !== activationOwner || !isCurrentBinding() || hasCaptureAuthorityBarrier()) return;
    let appliedDeviceRoute: ReturnType<BrowserAudioDeviceSelectionOwner['appliedRoute']>;
    try {
      const selectionOwner = deviceSelectionOwnerRef.current;
      if (selectionOwner === null) return;
      // This read follows every awaited predecessor cleanup. A devicechange
      // refresh increments its generation before publishing `refreshing`, so a
      // product start can never retain a pre-refresh route across that await.
      appliedDeviceRoute = selectionOwner.appliedRoute();
    } catch (error) {
      const reason = extractWebErrorReason(error) ?? 'AUDIO_DEVICE_SELECTION_FAILED';
      setP1VoiceStatus('failed');
      setP1VoiceReason(reason);
      console.warn(`live_voice_audio_device_selection_failure reason=${reason} fallback=text visible=true`);
      return;
    }
    if (owner === null || owner.status().status === 'closed') {
      if (!isCurrentBinding() || hasCaptureAuthorityBarrier()) return;
      let callbackOwner: ProductP1VoiceRouteOwner | null = null;
      const nextOwner = new ProductP1VoiceRouteOwner({
        enabled: true,
        expected_origin: window.location.origin,
        native_agent_model_confirmed: () => activationOwner.requestedAgentModelName() === null ||
          (isCurrentBinding() && activationOwner.snapshot().agent_model_selection?.model_name === activationOwner.requestedAgentModelName()),
        request: productRequest,
        ...(l0CaptureStreamFactoryRef.current === null
          ? {}
          : { capture_stream_factory: l0CaptureStreamFactoryRef.current }),
        on_status: (status, reason) => {
          if (callbackOwner !== null && p1VoiceOwnerRef.current === callbackOwner) {
            // Revoking an old P2 activation also aborts its streaming Speech
            // leaf. That terminal is expected once retirement has started; it
            // remains cleanup truth, not a user-visible route failure. The
            // same reason on the current activation still fails normally.
            const normalized = normalizeProductP1StatusForP2Retirement(
              status,
              reason,
              activationOwner.retirementStarted() || activationOwnerRef.current !== activationOwner,
            );
            const publishedStatus = normalized.status;
            const publishedReason = normalized.reason;
            if (publishedStatus !== 'capturing' && terminalAnnouncementSpeechOwnerRef.current === callbackOwner) {
              terminalAnnouncementSpeechOwnerRef.current = null;
            }
            if (publishedStatus === 'recognized' && terminalAnnouncementStateRef.current === 'suspending_capture') {
              p1VoiceCaptureBindingRef.current = null;
              updateTerminalAnnouncementState('fetching');
            }
            setP1VoiceStatus(publishedStatus);
            setP1VoiceReason(publishedReason);
            setP1FaultTailPlaying(callbackOwner.frozenFaultTailResponse() !== null);
            const replacement = replacementRecognitionRef.current;
            if (replacement?.owner === callbackOwner &&
              replacement.loop_generation === loopGeneration &&
              (publishedStatus === 'failed' || publishedReason === PRODUCT_P1_EMPTY_TRANSCRIPT_REASON)) {
              replacement.failed = true;
              publishReplacementRecognitionFailure();
            }
            const diagnostics = callbackOwner.captureDiagnostics();
            setInterruptionDegradedReason(
              ['playing', 'recognized'].includes(publishedStatus)
              && diagnostics.successor_readiness === 'degraded'
                ? diagnostics.successor_readiness_reason
                : null,
            );
            const diagnosticBinding = activationOwnerRef.current?.snapshot().binding ?? null;
            const ownsCurrentDiagnosticBinding =
              mountedRef.current &&
              voiceLoopEnabledRef.current &&
              voiceLoopGenerationRef.current === loopGeneration &&
              activeSessionRef.current === binding.session_id &&
              diagnosticBinding !== null &&
              diagnosticBinding.session_id === binding.session_id &&
              diagnosticBinding.correlation_id === binding.correlation_id &&
              diagnosticBinding.interaction_id === binding.interaction_id &&
              diagnosticBinding.activation_id === binding.activation_id &&
              diagnosticBinding.activation_generation === binding.activation_generation;
            if (ownsCurrentDiagnosticBinding) {
              const retiredFailure = recoveryDiagnosticRef.current;
              if (publishedStatus === 'capturing' && (retiredFailure?.seam === 'tts' || retiredFailure?.seam === 'response_generation') &&
                  retiredFailure.session_id === binding.session_id &&
                  retiredFailure.correlation_id === binding.correlation_id &&
                  retiredFailure.activation_generation !== null &&
                  retiredFailure.activation_generation < binding.activation_generation &&
                  pendingForegroundPresentationRef.current === null && pendingUnifiedFinalRef.current === null) {
                // Actual successor capture proves recovery. Retire the old
                // status diagnostic from this now-listening successor.
                clearProductRecoveryDiagnostic();
                setProductTextReason(null);
                setProductTextStatus('idle');
              }
              const activeResponse = activeVoiceResponseRef.current;
              const response =
                activeResponse?.interaction_id === binding.interaction_id
                  ? activeResponse
                  : null;
              const nativeState = nativeRequestStateRef.current;
              const ownsNativeTurn = nativeState?.binding === JSON.stringify([binding.session_id, binding.activation_id, binding.activation_generation]);
              const seam: ProductLiveVoiceRecoveryDiagnostic['seam'] = response !== null ? 'tts'
                : ownsNativeTurn && ['processing', 'failed'].includes(nativeState.phase) ? 'response_generation' : 'activation';
              if (publishedStatus === 'cleanup_pending' && publishedReason !== 'FORMAL_P1_CLEANUP_IN_PROGRESS') {
                const retainedDiagnostic = recoveryDiagnosticRef.current;
                const retainsExactTerminalTruth =
                  retainedDiagnostic?.disposition === 'terminal' &&
                  retainedDiagnostic.session_id === binding.session_id &&
                  retainedDiagnostic.correlation_id === binding.correlation_id &&
                  retainedDiagnostic.interaction_id === binding.interaction_id &&
                  retainedDiagnostic.activation_id === binding.activation_id &&
                  retainedDiagnostic.activation_generation === binding.activation_generation &&
                  (response === null ||
                    (retainedDiagnostic.response_id === response.response_id &&
                      retainedDiagnostic.response_generation === response.response_generation));
                if (!retainsExactTerminalTruth && !hasExactNativeTerminalFailure(binding)) {
                  publishProductRecoveryDiagnostic({
                    seam,
                    disposition: 'retrying',
                    reason: stableProductTextReason(publishedReason, 'FORMAL_P1_CLEANUP_PENDING'),
                    binding,
                    response,
                  });
                }
              } else if (publishedStatus === 'failed') {
                if (!hasExactNativeTerminalFailure(binding)) publishProductRecoveryDiagnostic({
                    seam, disposition: 'terminal',
                    reason: stableProductTextReason(publishedReason, 'PRODUCT_P1_ROUTE_FAILED'), binding, response,
                  });
              } else if (['idle', 'capturing', 'recognized', 'closed'].includes(publishedStatus)) {
                clearProductRecoveryDiagnostic({ seam: 'activation', binding });
              }
            }
          }
        },
        on_concurrent_capture_started: () => {
          const ownsCurrentCapture =
            callbackOwner !== null &&
            mountedRef.current &&
            voiceLoopEnabledRef.current &&
            voiceLoopGenerationRef.current === loopGeneration &&
            p1VoiceOwnerRef.current === callbackOwner;
          if (ownsCurrentCapture && terminalAnnouncementSpeechOwnerRef.current === callbackOwner) {
            // `speech_active` protects only the capture generation that
            // observed it. Idle/overlap rotation reuses the same P1 owner, so
            // owner identity alone would permanently defer a queued Task
            // announcement after the new capture becomes authoritative.
            terminalAnnouncementSpeechOwnerRef.current = null;
            setTerminalAnnouncementArbitrationEpoch(epoch => epoch + 1);
          }
          if (ownsCurrentCapture) {
            // The overlap uplink is already authoritative even while the
            // answer is still playing. Retain its P2 binding now so an EOT
            // racing the final playout frame can still stop, recognize, and
            // submit the captured utterance as the next turn.
            const binding = currentProductP2Binding();
            if (binding !== null) p1VoiceCaptureBindingRef.current = binding;
          }
        },
        on_capture_activity_settled: () => {
          if (mountedRef.current && voiceLoopEnabledRef.current && p1VoiceOwnerRef.current === callbackOwner) {
            terminalAnnouncementSpeechOwnerRef.current = null;
            setTerminalAnnouncementArbitrationEpoch(epoch => epoch + 1);
          }
        },
        on_barge_in_speech_start: () => {
          recordAudioDiagnostic('barge_in_ui_received', {
            session_id: binding.session_id, interaction_id: binding.interaction_id,
            callback_current: voiceLoopEnabledRef.current && voiceLoopGenerationRef.current === loopGeneration && p1VoiceOwnerRef.current === owner,
          });
          if (
            voiceLoopEnabledRef.current &&
            voiceLoopGenerationRef.current === loopGeneration &&
            p1VoiceOwnerRef.current === owner
          ) {
            // Stop local playout at the provider's speech-start boundary. The
            // later EOT remains the sole recognition/final-submit boundary.
            const binding = currentProductP2Binding();
            if (binding !== null) p1VoiceCaptureBindingRef.current = binding;
            void stopProductVoicePlayout();
          }
        },
        on_barge_in_end_of_turn: () => {
          if (
            voiceLoopEnabledRef.current &&
            voiceLoopGenerationRef.current === loopGeneration &&
            p1VoiceOwnerRef.current === owner
          ) {
            // Keep the exact successor binding for the already-retained EOT
            // handler. Playout was stopped by speech-start, not by EOT.
            const binding = currentProductP2Binding();
            if (binding !== null) p1VoiceCaptureBindingRef.current = binding;
          }
        },
        on_generation_speech_start: () => {
          if (
            voiceLoopEnabledRef.current &&
            voiceLoopGenerationRef.current === loopGeneration &&
            p1VoiceOwnerRef.current === owner
          ) {
            // The user started speaking while the Agent was still generating.
            // Fence that answer now, at the provider speech-start boundary, so
            // none of it can be produced, spoken, acknowledged or written to
            // history. The later EOT stays the sole submit boundary.
            const binding = currentProductP2Binding();
            if (binding !== null) p1VoiceCaptureBindingRef.current = binding;
            const submissionCapture = submissionCaptureRef.current;
            if (submissionCapture !== null && submissionCapture.owner === activationOwnerRef.current &&
                submissionCapture.input === pendingUnifiedFinalRef.current?.input &&
                submissionCapture.loop_generation === loopGeneration) {
              submissionCapture.speech_started = true;
              return;
            }
            void interruptProductGenerationHandlerRef.current();
          }
        },
      });
      callbackOwner = nextOwner;
      owner = nextOwner;
      p1VoiceOwnerRef.current = nextOwner;
      p1VoiceOwnerSessionRef.current = binding.session_id;
    }
    const startingOwner = owner;
    if (!isCurrentBinding() || hasCaptureAuthorityBarrier()) {
      if (p1VoiceOwnerRef.current === startingOwner) {
        await startingOwner.close().catch(() => undefined);
        if (p1VoiceOwnerRef.current === startingOwner) p1VoiceOwnerRef.current = null;
      }
      return;
    }
    try {
      await activationOwner.runAuthorizedMediaStart(binding, {
        start: () =>
          startingOwner.startCapture({
            session_id: binding.session_id,
            interaction_id: binding.interaction_id,
            correlation_id: binding.correlation_id,
            activation_id: binding.activation_id,
            activation_generation: binding.activation_generation,
            locale: 'zh-CN',
            device_selection: appliedDeviceRoute,
          }),
        cancel: () => startingOwner.close(),
      });
      if (isCurrentBinding() && owner.status().status === 'capturing') {
        p1VoiceCaptureBindingRef.current = binding;
        owner.armEndOfTurn(() => {
          void stopP1VoiceHandlerRef.current();
        });
      }
    } catch {
      // The owner publishes a content-free reason and retains cleanup.
      const reason = owner.status().reason;
      if ((appliedDeviceRoute.input_device_id !== undefined || appliedDeviceRoute.output_device_id !== undefined) && reason !== null) {
        console.warn(`live_voice_audio_device_selection_failure reason=${reason} fallback=text visible=true`);
      }
    }
  };

  const startProductVoiceCapture = (): Promise<void> => {
    const pending = pendingP1VoiceStartRef.current;
    const generation = voiceLoopGenerationRef.current;
    if (pending !== null && pending.generation === generation) return pending.promise;
    const predecessor = pending?.promise.catch(() => undefined) ?? Promise.resolve();
    const retained = predecessor.then(async () => {
      if (!voiceLoopEnabledRef.current || voiceLoopGenerationRef.current !== generation) return;
      const activationOwner = activationOwnerRef.current;
      const binding = activationOwner?.snapshot().binding ?? null;
      await startProductVoiceCaptureOwned();
      const failedOwner = p1VoiceOwnerRef.current;
      const currentBinding = activationOwnerRef.current?.snapshot().binding ?? null;
      if (
        failedOwner?.status().status !== 'failed' ||
        failedOwner.status().reason !== 'AUDIO_CAPTURE_MEDIA_ROUTE_NOT_ATTACHED' ||
        !mountedRef.current || !isConnectedRef.current ||
        !voiceLoopEnabledRef.current || voiceLoopGenerationRef.current !== generation ||
        binding === null || currentBinding === null ||
        activeSessionRef.current !== binding.session_id ||
        activationOwnerRef.current !== activationOwner ||
        !sameProductP2ActivationBinding(binding, currentBinding)
      ) return;
      publishProductRecoveryDiagnostic({
        seam: 'activation', disposition: 'retrying',
        reason: 'AUDIO_CAPTURE_MEDIA_ROUTE_NOT_ATTACHED', binding,
      });
      // One fresh capture after exact predecessor cleanup. This retries only
      // listening, never the committed utterance, Agent request or Task command.
      // The owned start rechecks Exit/session/activation fences after cleanup;
      // a second failure stays visible instead of starting a retry loop.
      await startProductVoiceCaptureOwned();
    }).finally(() => {
      if (pendingP1VoiceStartRef.current?.promise === retained) pendingP1VoiceStartRef.current = null;
    });
    pendingP1VoiceStartRef.current = Object.freeze({ generation, promise: retained });
    return retained;
  };
  startP1VoiceHandlerRef.current = startProductVoiceCapture;

  useEffect(() => {
    const reason = p1VoiceReason;
    const generation = voiceLoopGenerationRef.current;
    const binding = currentProductP2Binding();
    if (p1VoiceStatus !== 'failed' || !voiceLoopEnabledRef.current || !props.isConnected ||
        binding === null || captureRecoveryGenerationRef.current === generation ||
        !['SPEECH_RECOGNITION_STREAM_FAILED', PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON].includes(reason ?? '') ||
        pendingPresentationAttemptRef.current !== null || pendingBargeInRef.current !== null) return;
    captureRecoveryGenerationRef.current = generation;
    publishProductRecoveryDiagnostic({ seam: 'activation', disposition: 'retrying', reason: reason!, binding });
    console.warn(`live_voice_capture_recovery reason=${reason} generation=${generation} retry=1 committed_input_replayed=false`);
    void startP1VoiceHandlerRef.current().then(() => {
      const currentBinding = currentProductP2Binding();
      if (!mountedRef.current || !voiceLoopEnabledRef.current ||
          voiceLoopGenerationRef.current !== generation || activeSessionRef.current !== binding.session_id ||
          currentBinding === null || !sameProductP2ActivationBinding(binding, currentBinding) ||
          p1VoiceOwnerRef.current?.status().status !== 'capturing') return;
      if (recoveryDiagnosticRef.current?.reason === reason) clearProductRecoveryDiagnostic();
    }).catch(() => undefined);
  }, [p1VoiceStatus, p1VoiceReason, props.isConnected]);

  retryTerminalAnnouncementHandlerRef.current = retained => {
    const terminal = retained.task_notification;
    if (terminal === null || pendingPresentationAttemptRef.current !== retained || terminal.retry_pending || terminal.retry_count >= 1) {
      return;
    }
    if (retained.failure_reason !== undefined) {
      void settleTaskPresentationFailure(retained, retained.failure_reason);
      return;
    }
    if (
      !mountedRef.current ||
      !voiceLoopEnabledRef.current ||
      !isConnectedRef.current ||
      activationOwnerRef.current !== retained.owner ||
      (typeof document !== 'undefined' && document.visibilityState !== 'visible')
    ) {
      return;
    }
    terminal.retry_count += 1;
    terminal.retry_pending = true;
    const activationOwner = retained.owner;
    void (async () => {
      const failedOwner = p1VoiceOwnerRef.current;
      if (failedOwner !== null) {
        try {
          await failedOwner.close();
        } catch (error) {
          throw Object.assign(new Error('terminal announcement P1 cleanup is incomplete'), {
            reason: stableProductTextReason(error, 'PRODUCT_TERMINAL_ANNOUNCEMENT_RECOVERY_REQUIRED'),
          });
        }
        if (p1VoiceOwnerRef.current === failedOwner) p1VoiceOwnerRef.current = null;
      }
      if (
        !mountedRef.current ||
        !voiceLoopEnabledRef.current ||
        !isConnectedRef.current ||
        activationOwnerRef.current !== activationOwner ||
        pendingPresentationAttemptRef.current !== retained
      ) {
        terminal.retry_pending = false;
        return;
      }
      await startP1VoiceHandlerRef.current();
      const retryOwner = p1VoiceOwnerRef.current;
      if (retryOwner === null || retryOwner.status().status !== 'capturing') {
        throw Object.assign(new Error('terminal announcement P1 recovery did not restore capture authority'), {
          reason: 'PRODUCT_TERMINAL_ANNOUNCEMENT_RECOVERY_REQUIRED',
        });
      }
      await activationOwner.replayNotificationForMediaAuthorization({
        ...terminal.disposition.response,
        unit_id: terminal.disposition.unit_id,
      });
      if (activationOwnerRef.current !== activationOwner || pendingPresentationAttemptRef.current !== retained ||
          p1VoiceOwnerRef.current !== retryOwner || !voiceLoopEnabledRef.current) return;
      prepareTerminalTaskNotification(activationOwner, terminal.disposition);
      const pauseOutcome = await prepareTaskNotificationCapture(retryOwner, retained, true);
      if (pauseOutcome === 'speaker_active') {
        terminal.retry_pending = false;
        terminalAnnouncementSpeechOwnerRef.current = retryOwner;
        updateTerminalAnnouncementState('queued');
        return;
      }
      if (retryOwner.interactionEngine() !== 'openai-realtime-native') p1VoiceCaptureBindingRef.current = null;
      updateTerminalAnnouncementState('playing');
      activeVoiceResponseRef.current = terminal.disposition.response;
      await awaitProductTaskNotificationPlayout(
        retryOwner.playAgentText({
          response: terminal.disposition.response,
          unit_id: terminal.disposition.unit_id,
          text: terminal.disposition.text,
          capture_during_playout: false,
        }),
        () => {
          if (pendingPresentationAttemptRef.current !== retained) return;
          void retryOwner.close().catch(() => undefined);
        },
        props.taskNotificationPlayoutTimeoutMs,
      );
      if (activationOwnerRef.current !== activationOwner || pendingPresentationAttemptRef.current !== retained) {
        return;
      }
      if (activeVoiceResponseRef.current?.response_id === terminal.disposition.response_id) {
        activeVoiceResponseRef.current = null;
      }
      clearProductRecoveryDiagnostic({
        seam: 'tts',
        binding: activationOwner.snapshot().binding,
        response: terminal.disposition.response,
      });
      terminal.retry_pending = false;
      retained.markPlayoutSettled();
      updateTerminalAnnouncementState('acking');
      setPendingPresentationAck(terminal.disposition.ack);
      void settleProductPresentationAck(retained);
    })().catch(error => {
      terminal.retry_pending = false;
      if (activeVoiceResponseRef.current?.response_id === terminal.disposition.response_id) {
        activeVoiceResponseRef.current = null;
      }
      if (pendingPresentationAttemptRef.current === retained) {
        const reason = stableProductTextReason(error, 'PRODUCT_TERMINAL_ANNOUNCEMENT_AUDIO_FAILED');
        if (playoutDeferredToSpeaker(error)) {
          deferTaskAnnouncementToSpeaker(retained, p1VoiceOwnerRef.current);
          return;
        }
        if (reason === 'FORMAL_PLAYOUT_BARGED') {
          void settleTaskPresentationFailure(retained, 'task_audio_playout_failed');
          return;
        }
        setProductTextReason(reason);
        setProductTextStatus('failed');
        publishProductRecoveryDiagnostic({
          seam: 'tts',
          disposition: 'terminal',
          reason,
          binding: activationOwner.snapshot().binding,
          response: terminal.disposition.response,
        });
        updateTerminalAnnouncementState('recovering');
      }
    });
  };

  /**
   * Replay an announcement that stood down for a live speaker.
   *
   * Unlike the recovery retry, this never closes or rebuilds the P1 route: the
   * route is healthy and has just finished carrying the utterance that made the
   * announcement stand down. Nothing was consumed twice -- the exact delivered
   * announcement is still retained -- so there is no fetch either.
   */
  resumeDeferredTaskAnnouncementRef.current = retained => {
    const terminal = retained.task_notification;
    if (
      terminal === null ||
      retained.deferred_to_speaker !== true ||
      terminal.retry_pending ||
      pendingPresentationAttemptRef.current !== retained
    ) {
      return;
    }
    const activationOwner = retained.owner;
    if (
      !mountedRef.current ||
      !voiceLoopEnabledRef.current ||
      !isConnectedRef.current ||
      activationOwnerRef.current !== activationOwner
    ) {
      return;
    }
    terminal.retry_pending = true;
    const playoutLoopGeneration = voiceLoopGenerationRef.current;
    void (async () => {
      const currentOwner = p1VoiceOwnerRef.current;
      const readiness = currentOwner === null ? 'speaker_active' : await prepareTaskNotificationCapture(currentOwner, retained);
      if (
        !mountedRef.current ||
        !voiceLoopEnabledRef.current ||
        voiceLoopGenerationRef.current !== playoutLoopGeneration ||
        activationOwnerRef.current !== activationOwner ||
        pendingPresentationAttemptRef.current !== retained
      ) {
        terminal.retry_pending = false;
        return;
      }
      const voiceOwner = p1VoiceOwnerRef.current;
      if (readiness !== 'ready' || voiceOwner === null) {
        // Still speaking. Stay queued without spending the recovery budget.
        terminal.retry_pending = false;
        terminalAnnouncementSpeechOwnerRef.current = voiceOwner;
        updateTerminalAnnouncementState('queued');
        return;
      }
      retained.deferred_to_speaker = false;
      terminalAnnouncementSpeechOwnerRef.current = null;
      if (voiceOwner.interactionEngine() !== 'openai-realtime-native') p1VoiceCaptureBindingRef.current = null;
      updateTerminalAnnouncementState('playing');
      activeVoiceResponseRef.current = terminal.disposition.response;
      prepareTerminalTaskNotification(activationOwner, terminal.disposition);
      await awaitProductTaskNotificationPlayout(
        voiceOwner.playAgentText({
          response: terminal.disposition.response,
          unit_id: terminal.disposition.unit_id,
          text: terminal.disposition.text,
          capture_during_playout: false,
        }),
        () => {
          if (pendingPresentationAttemptRef.current !== retained) return;
          void voiceOwner.close().catch(() => undefined);
        },
        props.taskNotificationPlayoutTimeoutMs,
      );
      if (activationOwnerRef.current !== activationOwner || pendingPresentationAttemptRef.current !== retained) {
        terminal.retry_pending = false;
        return;
      }
      if (activeVoiceResponseRef.current?.response_id === terminal.disposition.response_id) {
        activeVoiceResponseRef.current = null;
      }
      clearProductRecoveryDiagnostic({
        seam: 'tts',
        binding: activationOwner.snapshot().binding,
        response: terminal.disposition.response,
      });
      terminal.retry_pending = false;
      retained.markPlayoutSettled();
      updateTerminalAnnouncementState('acking');
      setPendingPresentationAck(terminal.disposition.ack);
      void settleProductPresentationAck(retained);
    })().catch(error => {
      terminal.retry_pending = false;
      retained.deferred_to_speaker = false;
      if (activeVoiceResponseRef.current?.response_id === terminal.disposition.response_id) {
        activeVoiceResponseRef.current = null;
      }
      if (pendingPresentationAttemptRef.current === retained) {
        if (playoutDeferredToSpeaker(error)) {
          deferTaskAnnouncementToSpeaker(retained, p1VoiceOwnerRef.current);
          return;
        }
        // A resumed AUDIO failure uses the same Registry TEXT fallback as an
        // initial Task playout failure, not the retired local TTS retry path.
        const reason = stableProductTextReason(error, 'PRODUCT_TERMINAL_ANNOUNCEMENT_AUDIO_FAILED');
        if (reason === 'FORMAL_PLAYOUT_BARGED') {
          void settleTaskPresentationFailure(retained, 'task_audio_playout_failed');
          return;
        }
        setProductTextReason(reason);
        setProductTextStatus('failed');
        publishProductRecoveryDiagnostic({
          seam: 'tts',
          disposition: 'terminal',
          reason,
          binding: activationOwner.snapshot().binding,
          response: terminal.disposition.response,
        });
        updateTerminalAnnouncementState('recovering');
        retained.markPlayoutSettled();
        void settleTaskPresentationFailure(retained, 'task_audio_playout_failed');
      }
    });
  };

  const stopProductVoiceCaptureOwned = async () => {
    const owner = p1VoiceOwnerRef.current;
    const captureBinding = p1VoiceCaptureBindingRef.current;
    const loopGeneration = voiceLoopGenerationRef.current;
    if (owner === null || owner.status().status !== 'capturing' || captureBinding === null) return;
    const isCurrentBinding = () =>
      p1VoiceOwnerRef.current === owner &&
      p1VoiceCaptureBindingRef.current === captureBinding &&
      voiceLoopEnabledRef.current &&
      voiceLoopGenerationRef.current === loopGeneration;
    try {
      const recognition = await owner.stopAndRecognize();
      if (
        props.activeSessionId !== null &&
        voiceLoopEnabledRef.current &&
        voiceLoopGenerationRef.current === loopGeneration
      ) {
        replacementRecognitionRef.current = null;
        setReplacementRecognitionFailure(null);
        updateRecognizedSpeechConfirmation(null);
        const recognized = Object.freeze({
          session_id: props.activeSessionId,
          text: recognition.text,
          voice_commit_receipt: recognition.voice_commit_receipt,
          correlation_id: captureBinding.correlation_id,
          interaction_id: captureBinding.interaction_id,
          activation_id: captureBinding.activation_id,
          activation_generation: captureBinding.activation_generation,
        });
        recognizedVoiceRef.current = recognized;
        voiceDraftBindingRef.current = Object.freeze({
          session_id: props.activeSessionId,
          correlation_id: captureBinding.correlation_id,
          interaction_id: captureBinding.interaction_id,
          activation_id: captureBinding.activation_id,
          activation_generation: captureBinding.activation_generation,
        });
        p3VoiceDraftBindingRef.current = voiceDraftBindingRef.current;
        voiceTaskOriginRef.current = null;
        setProductInput(recognition.text);
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3MutationOperation('task.create');
        setP3TaskName('Voice task');
        setP3TaskInstruction(recognition.text);
        p1VoiceCaptureBindingRef.current = null;
        await submitUnifiedRecognizedVoice(recognized, captureBinding);
      } else if (!isCurrentBinding()) {
        await owner.close().catch(() => undefined);
        if (p1VoiceOwnerRef.current === owner) p1VoiceOwnerRef.current = null;
      }
    } catch {
      // The owner publishes a content-free reason and retains cleanup.
      const status = owner.status();
      const replacement = replacementRecognitionRef.current;
      if (replacement?.owner === owner && replacement.binding === captureBinding && isCurrentBinding()) {
        replacement.failed = true;
        publishReplacementRecognitionFailure();
      }
      if (
        isCurrentBinding() &&
        status.status === 'idle' &&
        status.reason === PRODUCT_P1_EMPTY_TRANSCRIPT_REASON
      ) {
        p1VoiceCaptureBindingRef.current = null;
        scheduleProductVoiceLoopCapture();
      }
    }
  };

  const stopProductVoiceCapture = (): Promise<void> => {
    const pending = pendingP1VoiceStopRef.current;
    if (pending !== null) {
      const captureOwner = p1VoiceOwnerRef.current;
      const captureBinding = p1VoiceCaptureBindingRef.current;
      const generation = voiceLoopGenerationRef.current;
      if (captureOwner?.status().status !== 'capturing' || captureBinding === null) return pending;
      // An EOT from the successor capture can arrive before the previous final
      // receives its response binding. Preserve that EOT and serialize commits.
      return pending.then(() => {
        if (voiceLoopEnabledRef.current && voiceLoopGenerationRef.current === generation &&
            p1VoiceOwnerRef.current === captureOwner && p1VoiceCaptureBindingRef.current === captureBinding &&
            captureOwner.status().status === 'capturing') return stopProductVoiceCapture();
      });
    }
    const retained = stopProductVoiceCaptureOwned().finally(() => {
      if (pendingP1VoiceStopRef.current === retained) pendingP1VoiceStopRef.current = null;
    });
    pendingP1VoiceStopRef.current = retained;
    return retained;
  };
  stopP1VoiceHandlerRef.current = stopProductVoiceCapture;

  const stopProductVoicePlayout = async () => {
    const p2Owner = activationOwnerRef.current;
    const p1Owner = p1VoiceOwnerRef.current;
    const response = activeVoiceResponseRef.current;
    recordAudioDiagnostic('barge_in_ui_stop_gate', {
      ...response, callback_current: p2Owner !== null && p1Owner !== null && response !== null && p1Owner.status().status === 'playing',
      status: p1Owner?.status().status ?? null,
    });
    if (p2Owner === null || p1Owner === null || response === null || p1Owner.status().status !== 'playing') return;
    bargeInSequenceRef.current += 1;
    const actionId = `product-barge-${bargeInSequenceRef.current}`;
    const locallyStopped = p1Owner.stopAgentPlayout(response);
    if (!locallyStopped) return;
    activeVoiceResponseRef.current = null;
    if (p1Owner.interactionEngine() === 'openai-realtime-native') return;
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
      // 先结算尚未完成的旧 presentation ACK。journal 单槽要求 ACK 先 settle,
      // 否则插话 barge-in 的 checkpoint 会因 pending ACK 冲突抛 'different
      // operation unresolved',并被误判为需重建整条 P2 路由。有意插话的旧 ACK
      // 应作为预期 stale 状态结算,而不是触发路由重建。
      const pendingPresentation = pendingPresentationAttemptRef.current;
      if (pendingPresentation !== null && pendingPresentation.owner === p2Owner) {
        recordAudioDiagnostic('barge_in_wait_presentation', { ...response });
        await pendingPresentation.playoutSettlement;
        await settleProductPresentationAck(pendingPresentation);
      }
      recordAudioDiagnostic('barge_in_rpc_requested', { ...response });
      await p2Owner.bargeIn(retained.input);
      recordAudioDiagnostic('barge_in_rpc_settled', { ...response, outcome: 'completed' });
      if (pendingBargeInRef.current === retained) {
        pendingBargeInRef.current = null;
      }
    } catch (error) {
      recordAudioDiagnostic('barge_in_rpc_settled', { ...response, outcome: 'failed_or_unknown' });
      if (!p2Owner.hasPendingBargeIn() && pendingBargeInRef.current === retained) {
        pendingBargeInRef.current = null;
      }
      if (!p2Owner.hasPendingBargeIn() && isHarmlessCompletedBargeInError(error)) {
        // The response finished between local stop and the remote barge-in.
        // Local playout is already stopped, so this is successful convergence
        // rather than a voice recovery failure.
        setProductTextReason(null);
        return;
      }
      setProductTextReason(stableProductTextReason(error, 'PRODUCT_BARGE_IN_RECOVERY_REQUIRED'));
      setProductTextStatus('failed');
      if (p2Owner.hasPendingBargeIn()) setP2RecoveryEpoch(epoch => epoch + 1);
    }
  };

  /**
   * Fence the answer that is still being generated, at speech-start.
   *
   * This issues only the server-side generation interruption, whose exact
   * cancellation scope is the conversational round. A background Task started
   * by that round keeps running and keeps reporting through Task notification.
   */
  const interruptProductGeneration = async () => {
    const retained = generationCaptureRef.current;
    const p2Owner = activationOwnerRef.current;
    const fence = pendingForegroundPresentationRef.current;
    if (
      retained === null ||
      p2Owner === null ||
      retained.owner !== p2Owner ||
      fence === null ||
      retained.fence !== fence ||
      retained.loop_generation !== voiceLoopGenerationRef.current ||
      ownerHasUnsettledGenerationInterrupt(p2Owner)
    ) {
      return;
    }
    generationInterruptSequenceRef.current += 1;
    const input = Object.freeze({
      action_id: `product-generation-interrupt-${generationInterruptSequenceRef.current}`,
      response_id: fence.response_id,
      response_generation: fence.response_generation,
    });
    const pending = Object.freeze({ owner: p2Owner, input });
    const loopGeneration = retained.loop_generation;
    const captureOwner = p1VoiceOwnerRef.current;
    const captureBinding = p1VoiceCaptureBindingRef.current;
    if (captureOwner === null || captureBinding === null ||
      captureBinding.session_id !== fence.session_id ||
      captureBinding.interaction_id !== fence.interaction_id) return;
    const replacement = {
      owner: captureOwner, binding: captureBinding, loop_generation: loopGeneration,
      fenced: false, failed: false,
    };
    replacementRecognitionRef.current = replacement;
    // An interruption can settle long after the route that issued it stopped
    // owning the foreground: the user can Exit, switch Session or hand the
    // microphone to another tab while it is still on the wire. Its outcome may
    // therefore only touch UI state that still belongs to that exact activation,
    // Session and voice loop; a successor must never inherit it.
    const ownsInterruptionOutcome = () =>
      mountedRef.current &&
      activationOwnerRef.current === p2Owner &&
      activeSessionRef.current === fence.session_id &&
      voiceLoopEnabledRef.current &&
      voiceLoopGenerationRef.current === loopGeneration;
    pendingGenerationInterruptRef.current = pending;
    // Optimistic: recorded before the request leaves so an answer that crosses
    // it on the wire is refused by identity. It is only a guess that the server
    // will fence anything, and it is withdrawn below whenever the server says
    // it did not -- an answer the server left intact is a legitimate answer.
    const interruptedResponseIdentity = productResponseGenerationIdentity(input);
    retainBoundedPresentedProductResponse(interruptedProductResponsesRef.current, interruptedResponseIdentity);
    const withdrawOptimisticRefusal = () => {
      interruptedProductResponsesRef.current.delete(interruptedResponseIdentity);
    };
    try {
      const outcome = await p2Owner.interruptGeneration(input);
      if (recordValue(outcome)?.fence_status !== 'fenced') {
        // ALREADY_SETTLED: the target finished or was replaced on its own, so
        // nothing was fenced and nothing was cancelled. Its presentation is
        // still valid, so withdraw the optimistic refusal and leave the
        // foreground exactly as it was -- that answer is still coming and the
        // route must stay able to receive, speak and acknowledge it.
        withdrawOptimisticRefusal();
        if (replacementRecognitionRef.current === replacement) replacementRecognitionRef.current = null;
        return;
      }
      // The fenced answer can no longer render, speak, be acknowledged or be
      // written to history, so it stops owning the foreground. The utterance
      // still being captured becomes an ordinary next turn at EOT.
      if (pendingForegroundPresentationRef.current === fence) {
        pendingForegroundPresentationRef.current = null;
      }
      if (generationCaptureRef.current === retained) generationCaptureRef.current = null;
      if (ownsInterruptionOutcome()) {
        replacement.fenced = true;
        publishReplacementRecognitionFailure();
        // The fenced answer is gone and the replacement utterance is still
        // being captured, so the route is waiting for input again, not for a
        // response that can no longer arrive.
        setProductOutput(null);
        setProductTextStatus('idle');
        setProductTextReason(null);
        if (replacement.failed && captureOwner.status().status === 'idle') {
          // Recognition may have failed before the fence response arrived.
          // Its earlier wake was blocked by the old foreground; retry only
          // after that exact foreground has now been authoritatively fenced.
          scheduleProductVoiceLoopCapture();
        }
      }
    } catch (error) {
      if (isDefinitiveProductOperationError(error)) {
        // The server definitively refused, so it fenced nothing: the answer is
        // still live and must not be silently dropped by our optimistic guess.
        withdrawOptimisticRefusal();
        if (replacementRecognitionRef.current === replacement) replacementRecognitionRef.current = null;
      }
      if (ownsInterruptionOutcome()) {
        setProductTextReason(stableProductTextReason(error, 'PRODUCT_GENERATION_INTERRUPT_RECOVERY_REQUIRED'));
        setProductTextStatus('failed');
      }
    } finally {
      // A retriable transport failure leaves the request unresolved inside the
      // owner. Clearing the ref here would strand it: only this ref lets
      // settleRetainedP2Operations replay it through the exact owner that
      // issued it, and cleanup refuses to retire an owner that still has one.
      if (
        pendingGenerationInterruptRef.current === pending &&
        !p2Owner.hasPendingGenerationInterrupt()
      ) {
        pendingGenerationInterruptRef.current = null;
      }
    }
  };
  interruptProductGenerationHandlerRef.current = interruptProductGeneration;

  /** Open the listening window that runs while the Agent is still generating. */
  const scheduleGenerationTimeCapture = (
    owner: ProductWebP2ActivationOwner,
    fence: PendingForegroundPresentationFence,
  ) => {
    if (
      !FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION ||
      !FEATURE_LIVE_VOICE_INTEGRATED_P1 ||
      !voiceLoopEnabledRef.current ||
      generationCaptureRef.current !== null ||
      pendingForegroundPresentationRef.current !== fence ||
      activationOwnerRef.current !== owner ||
      pendingPresentationAttemptRef.current !== null ||
      pendingBargeInRef.current !== null ||
      // Only this owner's own unsettled interruption closes its listening
      // window. A retired activation's handle cannot reach this foreground,
      // so letting it match here would block every successor Session forever.
      ownerHasUnsettledGenerationInterrupt(owner) ||
      terminalAnnouncementStateRef.current !== 'idle'
    ) {
      return;
    }
    const retained = Object.freeze({
      owner,
      fence,
      loop_generation: voiceLoopGenerationRef.current,
    });
    generationCaptureRef.current = retained;
    void startP1VoiceHandlerRef.current().catch(() => {
      if (generationCaptureRef.current === retained) generationCaptureRef.current = null;
    });
  };

  useEffect(() => {
    // A pending Task ACK/fallback can temporarily refuse a listening start.
    // Retaining the window is not proof that the microphone actually opened;
    // resume it once the presentation owner has settled its barrier.
    if (!voiceLoopEnabledRef.current || !['idle', 'recognized'].includes(p1VoiceStatus)) return;
    const owner = activationOwnerRef.current;
    const generation = generationCaptureRef.current;
    const submission = submissionCaptureRef.current;
    const current = generation?.owner === owner && generation?.fence === pendingForegroundPresentationRef.current &&
      generation?.loop_generation === voiceLoopGenerationRef.current;
    const submitting = submission?.owner === owner && submission?.input === pendingUnifiedFinalRef.current?.input &&
      submission?.loop_generation === voiceLoopGenerationRef.current;
    if (current || submitting) void startP1VoiceHandlerRef.current().catch(() => undefined);
  }, [p1VoiceStatus, productTextStatus, terminalAnnouncementState, pendingPresentationAck, p2Activation.status, props.isConnected]);

  /**
   * Decide whether an answer may be spoken right now, and clear the way if so.
   *
   * A silent generation-time listening window is released, because nobody is
   * speaking into it. A capture that already observed provider speech-start is
   * never discarded: it owns a real utterance. In that case the answer is not
   * handed to P1 at all -- asking P1 to play over a live capture fails the whole
   * route and would throw away the words the user is in the middle of saying.
   * The caller treats `speaker_active` as an ordinary unplayed presentation, so
   * Task notifications keep their existing retained-recovery path.
   */
  const deferTaskAnnouncementToSpeaker = (
    attempt: PendingProductPresentationAttempt, voiceOwner: ProductP1VoiceRouteOwner | null,
  ): void => {
    if (pendingPresentationAttemptRef.current !== attempt) return;
    if (activeVoiceResponseRef.current?.response_id === attempt.response.response_id &&
        activeVoiceResponseRef.current.response_generation === attempt.response.response_generation) {
      activeVoiceResponseRef.current = null;
    }
    attempt.release_notification_capture?.();
    attempt.release_notification_capture = undefined;
    attempt.deferred_to_speaker = true;
    const capture = voiceOwner?.captureDiagnostics();
    terminalAnnouncementSpeechOwnerRef.current = voiceOwner?.interactionEngine() === 'openai-realtime-native' &&
      !capture?.provider_speech_start_observed && (capture?.local_activity_recency_frames ?? 0) === 0 ? null : voiceOwner;
    updateTerminalAnnouncementState('queued');
    setTerminalAnnouncementArbitrationEpoch(epoch => epoch + 1);
  };

  const prepareTaskNotificationCapture = async (
    owner: ProductP1VoiceRouteOwner, attempt: PendingProductPresentationAttempt, recovering = false,
  ): Promise<'ready' | 'speaker_active'> => {
    const prepared = owner.prepareNativeTaskNotification(attempt.response);
    if (prepared.status === 'speaker_active') return 'speaker_active';
    if (prepared.status === 'ready') {
      attempt.release_notification_capture = prepared.release;
      return 'ready';
    }
    if (recovering) return (await owner.pauseIdleCaptureForNotification()) === 'paused' ? 'ready' : 'speaker_active';
    return settleCaptureBeforePlayout();
  };

  const settleCaptureBeforePlayout = async (): Promise<'ready' | 'speaker_active'> => {
    const retained = generationCaptureRef.current;
    if (retained !== null) {
      // An answer can arrive while that window is still being opened. Join the
      // exact start first, otherwise a half-started capture would stay open.
      const startInFlight = pendingP1VoiceStartRef.current?.promise;
      if (startInFlight !== undefined) await startInFlight.catch(() => undefined);
      if (generationCaptureRef.current === retained) generationCaptureRef.current = null;
    }
    const owner = p1VoiceOwnerRef.current;
    if (owner === null) return 'ready';
    if (owner.status().status !== 'capturing') {
      return ['starting', 'recognizing'].includes(owner.status().status) ? 'speaker_active' : 'ready';
    }
    if (owner.captureDiagnostics().provider_speech_start_observed) return 'speaker_active';
    try {
      await owner.abandonCapture('formal_generation_listening_released');
    } catch {
      // The owner publishes a content-free reason and retains cleanup.
    }
    if (owner.status().status === 'capturing') return 'speaker_active';
    if (p1VoiceCaptureBindingRef.current !== null) p1VoiceCaptureBindingRef.current = null;
    return 'ready';
  };

  const commitRecognizedVoiceTaskOrigin = async (): Promise<ProductVoiceTaskOrigin | null> => {
    const owner = activationOwnerRef.current;
    const recognized = recognizedVoiceRef.current;
    const activationBinding = currentProductP2Binding();
    if (
      owner === null ||
      recognized === null ||
      props.activeSessionId === null ||
      recognized.session_id !== props.activeSessionId ||
      recognized.text !== p3TaskInstruction ||
      !recognizedVoiceMatchesProductBinding(recognized, activationBinding) ||
      p2Activation.status !== 'active' ||
      activationBinding === null ||
      pendingProductTurnRef.current !== null ||
      pendingBargeInRef.current !== null ||
      ownerHasUnsettledGenerationInterrupt(owner) ||
      owner.hasPendingSubmission() ||
      owner.hasPendingPresentationAck() ||
      owner.hasPendingPresentationFailure() ||
      owner.hasPendingBargeIn() ||
      owner.hasPendingGenerationInterrupt()
    )
      return null;
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
    try {
      const result = await retryRetainedProductOperation({
        operation: () => owner.submitText(input),
        is_current: () => props.isConnected && activationOwnerRef.current === owner && activeSessionRef.current === recognized.session_id,
      });
      if (pendingProductTurnRef.current !== retained) return null;
      pendingProductTurnRef.current = null;
      const origin = bindProductVoiceTaskOrigin(input, result, recognized.session_id, activationBinding.interaction_id, activationBinding.correlation_id);
      voiceTaskOriginRef.current = origin;
      recognizedVoiceRef.current = null;
      return origin;
    } catch {
      if (activationOwnerRef.current === owner && !owner.hasPendingSubmission()) {
        pendingProductTurnRef.current = null;
      }
      return null;
    }
  };

  async function inspectP3RetryEligibility(
    input: Readonly<{
      task_id?: string;
      follow_nonterminal?: boolean;
      progress_origin?: Readonly<{ kind: 'text' | 'voice'; id: string }> | null;
      replace_leaf?: boolean;
      expected_task_control_binding?: FormalTaskControlBinding;
      throw_on_failure?: boolean;
      is_current?: () => boolean;
    }> = {},
  ): Promise<Readonly<FormalTaskControlRecord> | null> {
    const sessionId = props.activeSessionId;
    const taskId = (input.task_id ?? p3TargetTaskId).trim();
    if (!sessionId || !taskId || p3MutationOwnerRef.current?.hasPendingMutation()) {
      cancelP3RetryInspection();
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('ineligible');
      setP3RetryInspectionReason(null);
      return null;
    }
    cancelP3RetryInspection();
    const inspectionGeneration = p3RetryInspectionGenerationRef.current;
    const abortController = new AbortController();
    p3RetryInspectionAbortRef.current = abortController;
    const waitForRetry = props.p3RetryInspectionWait ?? defaultP3RetryInspectionWait;
    const previousLeaf = formalTaskControlLeafRef.current;
    const previousSnapshot = previousLeaf?.snapshot() ?? null;
    const replaceLeaf =
      input.replace_leaf === true || previousSnapshot === null || !previousSnapshot.connected || !previousSnapshot.tasks.some(task => task.task_id === taskId);
    let leaf = replaceLeaf ? null : previousLeaf;
    let replacementAdopted = false;
    const requestIsCurrent = () =>
      !abortController.signal.aborted &&
      (input.is_current?.() ?? true) &&
      mountedRef.current &&
      activeSessionRef.current === sessionId &&
      p3RetryInspectionGenerationRef.current === inspectionGeneration &&
      p3RetryInspectionAbortRef.current === abortController;
    const isCurrent = () =>
      requestIsCurrent() &&
      (replaceLeaf
        ? formalTaskControlLeafRef.current === previousLeaf || formalTaskControlLeafRef.current === leaf
        : formalTaskControlLeafRef.current === leaf);
    setP3RetryEligibility(null);
    setP3RetryInspectionStatus('checking');
    setP3RetryInspectionReason(null);
    try {
      if (leaf === null) {
        const bootstrapResponse = await productRequest(
          PRODUCT_P3_TASK_STATUS_METHOD,
          { session_id: sessionId, task_id: taskId },
          { requestId: `web-task-status-bootstrap-${Date.now()}-${inspectionGeneration}` },
        );
        if (!requestIsCurrent()) return null;
        leaf = bootstrapProductP3TaskInspectionLeaf(bootstrapResponse, {
          session_id: sessionId,
          task_id: taskId,
          expected_binding: input.expected_task_control_binding,
        });
        if (!replaceLeaf) {
          formalTaskControlLeafRef.current = leaf;
          progressDrainRef.current?.();
        }
      }
      for (let attempt = 0; ; attempt += 1) {
        let inspection: ProductP3RetryInspection;
        try {
          inspection = await inspectProductP3RetryCandidate({
            request: productRequest,
            leaf,
            session_id: sessionId,
            task_id: taskId,
            request_nonce: `${Date.now()}-${inspectionGeneration}-${attempt}`,
            is_current: isCurrent,
          });
        } catch (error) {
          if (
            input.follow_nonterminal === true &&
            attempt < PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS.length &&
            error instanceof Error &&
            error.message === 'formal task retry inspection cannot regress an observed successor'
          ) {
            await waitForRetry(PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS[attempt]!, abortController.signal);
            if (!isCurrent()) return null;
            continue;
          }
          throw error;
        }
        if (!isCurrent()) return null;
        const { record: selected, admission } = inspection;
        const taskControlBinding = leaf.snapshot().binding;
        const taskTargetPersisted = persistProductP3TaskTarget({
          session_id: taskControlBinding.session_id,
          correlation_id: taskControlBinding.correlation_id,
          task_id: taskId,
          task_control_binding: taskControlBinding,
        });
        if (replaceLeaf && !taskTargetPersisted) {
          throw new Error('formal task target persistence failed');
        }
        if (!isCurrent()) return null;
        if (replaceLeaf) {
          formalTaskControlLeafRef.current = leaf;
          progressDrainRef.current?.();
          replacementAdopted = true;
          previousLeaf?.disconnect();
        }
        recoveredP3TaskTargetRef.current = `${taskControlBinding.session_id}\u0000${taskControlBinding.correlation_id}\u0000${taskId}`;
        if (progressTaskTargetRef.current !== taskId) {
          progressRef.current = null;
          if (voiceProgressOwnersRef.current.size === 0) pendingOwnedProgressRef.current.clear();
          setProgress(null);
          setProgressAck('idle');
        }
        progressTaskTargetRef.current = taskId;
        adoptCreatedProgressRoute(Object.freeze({ task_id: taskId, correlation_id: taskControlBinding.correlation_id, origin: input.progress_origin ?? null }));
        setP3TargetTaskId(taskId);
        const terminalStatus = productP3TerminalStatus(selected);
        if (replaceLeaf) {
          setP3MutationStatus(terminalStatus ?? 'accepted');
          setP3MutationReason(null);
        }
        if (terminalStatus !== null) {
          const followTarget = p3AcceptedFollowTargetRef.current;
          if (followTarget?.session_id === sessionId && followTarget.task_id === taskId) {
            p3AcceptedFollowTargetRef.current = null;
          }
          setP3MutationStatus(terminalStatus);
        }
        if (admission.eligible && isFormalTaskRetryEligible(selected)) {
          setP3RetryEligibility(selected);
          setP3RetryInspectionStatus('eligible');
          setP3RetryInspectionReason(null);
          setP3MutationOperation('task.retry');
          return selected;
        }
        if (selected.state === 'terminal' || input.follow_nonterminal !== true || attempt >= PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS.length) {
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('ineligible');
          setP3RetryInspectionReason(admission.reason);
          return null;
        }
        await waitForRetry(PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS[attempt]!, abortController.signal);
        if (!isCurrent()) return null;
      }
    } catch (error) {
      if (isCurrent()) {
        setP3RetryEligibility(null);
        setP3RetryInspectionStatus('failed');
        setP3RetryInspectionReason(productP3RetryInspectionFailureReason(error));
      }
      if (input.throw_on_failure === true) throw error;
      return null;
    } finally {
      if (p3RetryInspectionAbortRef.current === abortController) {
        p3RetryInspectionAbortRef.current = null;
      }
      if (replaceLeaf && leaf !== null && !replacementAdopted) leaf.disconnect();
    }
  }

  const buildP3Mutation = (): ProductWebP3MutationInput | null => {
    const sessionId = props.activeSessionId;
    if (!sessionId) return null;
    p3MutationSequenceRef.current += 1;
    const identity = `${Date.now()}-${p3MutationSequenceRef.current}`;
    const taskControlSnapshot = formalTaskControlLeafRef.current?.snapshot() ?? null;
    const observedTarget = taskControlSnapshot?.tasks.find(task => task.task_id === p3TargetTaskId.trim());
    const mutationCorrelationId =
      p3MutationOperation !== 'task.create' && taskControlSnapshot !== null && observedTarget !== undefined
        ? taskControlSnapshot.binding.correlation_id
        : correlationId;
    const common = {
      session_id: sessionId,
      command_id: `web-task-command-${identity}`,
      issued_at: new Date().toISOString(),
      correlation_id: mutationCorrelationId,
    };
    if (p3MutationOperation === 'task.cancel' || p3MutationOperation === 'task.retry') {
      if (!p3TargetTaskId.trim()) return null;
      if (p3MutationOperation === 'task.retry' && (p3RetryEligibility?.task_id !== p3TargetTaskId.trim() || !isFormalTaskRetryEligible(p3RetryEligibility)))
        return null;
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
    const p3VoiceDraftBinding = p3VoiceDraftBindingRef.current;
    if (
      p3VoiceDraftBinding !== null &&
      (voiceTaskOriginRef.current === null || !productVoiceDraftMatchesBinding(p3VoiceDraftBinding, props.activeSessionId, currentProductP2Binding()))
    )
      return null;
    if (!p3TaskName.trim() || !p3TaskInstruction.trim()) return null;
    return {
      operation: 'task.create',
      ...common,
      ...resolveProductTaskCreateOrigin(p3TaskInstruction, props.activeSessionId, voiceTaskOriginRef.current),
      name: p3TaskName,
      instruction: p3TaskInstruction,
    };
  };

  const issueP3MutationConfirmation = async (recognizedSpeechDispatch: RecognizedSpeechConfirmation | null = null) => {
    const currentSpeechConfirmation = recognizedSpeechConfirmationRef.current;
    if (
      (currentSpeechConfirmation !== null && currentSpeechConfirmation !== recognizedSpeechDispatch) ||
      (recognizedSpeechDispatch !== null &&
        (recognizedSpeechDispatch.intent !== 'task' ||
          recognizedSpeechDispatch.task_route !== 'structured' ||
          recognizedSpeechDispatch.phase !== 'dispatching' ||
          !recognizedSpeechConfirmationAuthorityMatches(recognizedSpeechDispatch, props.activeSessionId, p3TaskInstruction, p2Activation.binding)))
    ) {
      return;
    }
    const inspectionWasChecking = p3RetryInspectionStatus === 'checking';
    cancelP3RetryInspection();
    if (inspectionWasChecking) {
      setP3RetryEligibility(null);
      setP3RetryInspectionStatus('idle');
      setP3RetryInspectionReason(null);
      return;
    }
    const owner = p3MutationOwnerRef.current;
    setP3MutationReason(null);
    let mutation = pendingP3MutationRef.current;
    if (
      mutation === null &&
      p3MutationOperation === 'task.create' &&
      voiceTaskOriginRef.current === null &&
      recognizedVoiceRef.current?.session_id === props.activeSessionId &&
      recognizedVoiceRef.current?.text === p3TaskInstruction
    ) {
      const recognized = recognizedVoiceRef.current;
      const binding = currentProductP2Binding();
      if (recognized === null || !recognizedVoiceMatchesProductBinding(recognized, binding)) {
        setP3MutationStatus('failed');
        return;
      }
      if (recognizedSpeechDispatch === null) {
        if (recognizedSpeechConfirmationRef.current === null && binding !== null) {
          updateRecognizedSpeechConfirmation(
            Object.freeze({
              intent: 'task',
              task_route: 'structured',
              phase: 'confirming',
              session_id: recognized.session_id,
              text: recognized.text,
              correlation_id: binding.correlation_id,
              interaction_id: binding.interaction_id,
              activation_id: binding.activation_id,
              activation_generation: binding.activation_generation,
            }),
          );
        }
        return;
      }
      const origin = await commitRecognizedVoiceTaskOrigin();
      const retainedOrigin = voiceTaskOriginRef.current as ProductVoiceTaskOrigin | null;
      const originIsCurrent =
        origin !== null &&
        recognizedSpeechConfirmationRef.current === recognizedSpeechDispatch &&
        p3MutationOperation === 'task.create' &&
        retainedOrigin === origin &&
        origin.session_id === recognizedSpeechDispatch.session_id &&
        origin.interaction_id === recognizedSpeechDispatch.interaction_id &&
        origin.instruction === recognizedSpeechDispatch.text &&
        recognizedSpeechConfirmationAuthorityMatches(
          recognizedSpeechDispatch,
          props.activeSessionId,
          p3TaskInstruction,
          activationOwnerRef.current?.snapshot().binding ?? null,
        );
      if (!originIsCurrent) {
        if (origin !== null && voiceTaskOriginRef.current === origin) voiceTaskOriginRef.current = null;
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
      const currentBinding = leaf?.snapshot().binding ?? null;
      let receiptLeaf = leaf;
      if (currentBinding === null || !sameFormalTaskControlBinding(currentBinding, receipt.task_control_binding)) {
        receiptLeaf = new FormalTaskControlLeaf({
          enabled: true,
          binding: receipt.task_control_binding,
        });
      } else {
        if (leaf === null) throw new Error('formal task control leaf missing for matching binding');
        leaf.reconnect(receipt.task_control_binding);
      }
      if (mutation.operation !== 'task.create') {
        if (receiptLeaf === null) throw new Error('formal task control receipt leaf is missing');
        const refreshed = await inspectProductP3RetryCandidate({
          request: productRequest,
          leaf: receiptLeaf,
          session_id: mutation.session_id,
          task_id: mutation.task_id,
          request_nonce: `confirmed-${mutation.command_id}`,
          is_current: () =>
            mountedRef.current &&
            p3MutationOwnerRef.current === owner &&
            pendingP3MutationRef.current === mutation &&
            activeSessionRef.current === mutation.session_id,
        });
        if (mutation.operation === 'task.retry' && (!refreshed.admission.eligible || !isFormalTaskRetryEligible(refreshed.record))) {
          if (p3MutationOwnerRef.current !== owner || pendingP3MutationRef.current !== mutation || activeSessionRef.current !== mutation.session_id) {
            return;
          }
          if (receiptLeaf !== leaf) receiptLeaf.disconnect();
          // The confirmation was issued, but no mutation request exists yet.
          // A fully parsed authoritative rejection can therefore release only
          // this local receipt and return to inspection. Transport/malformed
          // uncertainty still takes the catch path and retains the exact owner.
          p3MutationOwnerRef.current = new ProductWebP3MutationOwner({
            enabled: true,
            request: (method, params, requestId) => productRequest(method, params, { requestId }),
          });
          pendingP3MutationRef.current = null;
          pendingFormalP3MutationRef.current = null;
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('ineligible');
          setP3RetryInspectionReason(refreshed.admission.reason);
          setP3MutationStatus('failed');
          setP3MutationReason(refreshed.admission.reason);
          return;
        }
        if (mutation.operation === 'task.retry') setP3RetryEligibility(refreshed.record);
      }
      if (receiptLeaf !== leaf) {
        leaf?.disconnect();
        leaf = receiptLeaf;
        formalTaskControlLeafRef.current = receiptLeaf;
        progressDrainRef.current?.();
      }
      pendingFormalP3MutationRef.current = prepareFormalTaskMutation(
        receipt.task_control_binding,
        {
          operation: mutation.operation,
          command_id: mutation.command_id,
          task_id: mutation.operation === 'task.create' ? null : mutation.task_id,
        },
        receipt,
      );
      if (p3MutationOwnerRef.current === owner) {
        setP3MutationStatus('confirmed');
      }
    } catch (error) {
      if (p3MutationOwnerRef.current === owner) {
        if (!owner.hasPendingMutation()) pendingP3MutationRef.current = null;
        setP3MutationStatus('failed');
        setP3MutationReason(extractWebErrorReason(error) ?? 'PRODUCT_P3_CONFIRMATION_ISSUE_FAILED');
      }
    }
  };

  const acceptRecognizedSpeechConfirmation = async () => {
    const pending = recognizedSpeechConfirmationRef.current;
    if (pending === null) {
      const editedPending = editedVoiceDraftConfirmationRef.current;
      const binding = currentProductP2Binding();
      if (
        editedPending === null ||
        editedPending.phase !== 'confirming' ||
        editedPending.text !== productInput ||
        !productVoiceDraftMatchesBinding(editedPending, props.activeSessionId, binding) ||
        !productVoiceDraftMatchesBinding(voiceDraftBindingRef.current, props.activeSessionId, binding) ||
        p2Activation.status !== 'active'
      ) {
        updateEditedVoiceDraftConfirmation(null);
        return;
      }
      const dispatching = Object.freeze({ ...editedPending, phase: 'dispatching' as const });
      updateEditedVoiceDraftConfirmation(dispatching);
      try {
        const submitted = await submitProductText(undefined, 'structured');
        if (submitted !== null && productVoiceDraftMatchesBinding(voiceDraftBindingRef.current, editedPending.session_id, binding)) {
          voiceDraftBindingRef.current = null;
        }
      } finally {
        if (editedVoiceDraftConfirmationRef.current === dispatching) {
          updateEditedVoiceDraftConfirmation(null);
        }
      }
      return;
    }
    if (pending.phase !== 'confirming') return;
    const displayedText = pending.intent === 'agent' ? productInput : p3TaskInstruction;
    if (!recognizedSpeechConfirmationMatches(pending, recognizedVoiceRef.current, props.activeSessionId, displayedText, currentProductP2Binding())) {
      updateRecognizedSpeechConfirmation(null);
      return;
    }
    const dispatching = Object.freeze({ ...pending, phase: 'dispatching' as const });
    updateRecognizedSpeechConfirmation(dispatching);
    try {
      if (pending.intent === 'agent') {
        await submitProductText(undefined, 'voice');
        return;
      }
      await issueP3MutationConfirmation(dispatching);
    } finally {
      if (recognizedSpeechConfirmationRef.current === dispatching) {
        updateRecognizedSpeechConfirmation(null);
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
    setP3MutationReason(null);
    try {
      const result = await leaf.submitMutation(prepared, () => owner.mutate(mutation));
      leaf.adopt(mutation.operation, result, {
        connection_generation: leaf.snapshot().connection_generation,
        command_id: mutation.command_id,
        target_task_id: null,
        events_query: null,
      });
      p3ProgressReconciliationGenerationRef.current += 1;
      if (p3MutationOwnerRef.current === owner) {
        if (mutation.operation === 'task.create') {
          const formalResult = recordValue(result.formal_task_result);
          const createdTaskId = formalResult?.task_id;
          if (typeof createdTaskId !== 'string' || !createdTaskId.trim()) {
            throw new Error('formal task.create result did not return an exact task');
          }
          const taskControlBinding = leaf.snapshot().binding;
          persistProductP3TaskTarget({
            session_id: taskControlBinding.session_id,
            correlation_id: taskControlBinding.correlation_id,
            task_id: createdTaskId,
            task_control_binding: taskControlBinding,
          });
          recoveredP3TaskTargetRef.current = `${taskControlBinding.session_id}\u0000${taskControlBinding.correlation_id}\u0000${createdTaskId}`;
          progressTaskTargetRef.current = createdTaskId;
          progressRef.current = null;
          pendingOwnedProgressRef.current.clear();
          setProgress(null);
          setProgressAck('idle');
          const progressOrigin =
            mutation.source === 'voice' && typeof mutation.interaction_id === 'string' && mutation.interaction_id.trim()
              ? Object.freeze({ kind: 'voice' as const, id: mutation.interaction_id })
              : null;
          if (mutation.source === 'voice' && progressOrigin === null) {
            throw new Error('formal voice task.create lost its exact interaction origin');
          }
          adoptCreatedProgressRoute(
            Object.freeze({
              task_id: createdTaskId,
              correlation_id: taskControlBinding.correlation_id,
              origin: progressOrigin,
            }),
          );
          cancelP3RetryInspection();
          setP3TargetTaskId(createdTaskId);
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('idle');
          setP3RetryInspectionReason(null);
          setP3MutationOperation('task.cancel');
        } else if (mutation.operation === 'task.retry') {
          cancelP3RetryInspection();
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('ineligible');
          setP3RetryInspectionReason(null);
          setP3MutationOperation('task.cancel');
        }
        pendingP3MutationRef.current = null;
        pendingFormalP3MutationRef.current = null;
        p3AcceptedFollowTargetRef.current =
          mutation.operation === 'task.create' ? null : Object.freeze({ session_id: mutation.session_id, task_id: mutation.task_id });
        setP3MutationStatus('accepted');
        setP3MutationReason(null);
        if (mutation.operation !== 'task.create') {
          void inspectP3RetryEligibility({ task_id: mutation.task_id, follow_nonterminal: true });
        }
      }
    } catch (error) {
      if (p3MutationOwnerRef.current === owner) {
        if (isDefinitiveProductOperationError(error) && !owner.hasPendingMutation()) {
          pendingP3MutationRef.current = null;
          pendingFormalP3MutationRef.current = null;
        }
        setP3MutationStatus('failed');
        setP3MutationReason(extractWebErrorReason(error) ?? 'PRODUCT_P3_MUTATION_FAILED');
      }
    }
  };

  useEffect(() => {
    const followTarget = p3AcceptedFollowTargetRef.current;
    if (!props.isConnected || followTarget === null || followTarget.session_id !== props.activeSessionId) return;
    void inspectP3RetryEligibility({ task_id: followTarget.task_id, follow_nonterminal: true });
  }, [props.activeSessionId, props.isConnected]);

  useEffect(() => {
    let cancelled = false;
    let owner: ProductWebP3ProgressOwner | null = null;
    const ownedSessionId = props.activeSessionId;
    const ownedProgressRoute = createdProgressRoute;
    const ownedProgressCorrelationId = createdProgressCorrelationId ?? correlationId;
    const ownedProgressOrigin = createdProgressOrigin;
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
      if (cancelled || !FEATURE_LIVE_VOICE_INTEGRATED_WEB || !hasDurableProductVoiceSession(props.activeSessionId) || !props.isConnected) {
        if (!cancelled) {
          setP3Activation({
            status: FEATURE_LIVE_VOICE_INTEGRATED_WEB ? 'idle' : 'disabled',
            binding: null,
            reason: null,
            requested_origin_kind: null,
            effective_origin_kind: null,
            voice_progress: null,
            voice_reason: null,
            fallback_reason: null,
          });
        }
        return;
      }
      // A restored selection does not change the notification's voice origin.
      // Wait for authenticated P2 discovery before choosing a TEXT subscription;
      // otherwise remount can allocate an unconsumed TEXT prefix in the same
      // Runtime lane before Start restores the independent voice owner.
      const recoveryOwner = activationOwnerRef.current;
      const recoveryDiscovery = FEATURE_LIVE_VOICE_INTEGRATED_P1 ? recoveryOwner?.voiceTaskDiscovery() : null;
      if (FEATURE_LIVE_VOICE_INTEGRATED_P1 &&
          (recoveryOwner?.snapshot().status !== 'active' || recoveryDiscovery?.reason !== null)) return;
      const recoveredVoiceTasks = recoveryDiscovery?.task_ids ?? [];
      if (recoveredVoiceTasks.length > 0 && ownedProgressRoute === null) return;
      const recoveredVoiceSelection = ownedProgressRoute !== null && recoveredVoiceTasks.includes(ownedProgressRoute.task_id);
      if (recoveredVoiceSelection && !voiceLoopEnabledRef.current) return;
      // Voice subscriptions own independent, freshly authenticated inspection
      // leaves. Selecting B must not retire A's future terminal delivery.
      if (ownedProgressRoute !== null) {
        const retainedVoice = voiceProgressOwnersRef.current.get(ownedProgressRoute.task_id);
        const p2Binding = currentProductP2Binding();
        if (retainedVoice !== undefined && voiceProgressIsCurrent(retainedVoice)) {
          setP3Activation(retainedVoice.owner.snapshot());
          return;
        }
        if (p2Binding !== null && (recoveredVoiceSelection || desiredVoiceProgressIsCurrent(ownedProgressRoute.task_id)
          || (ownedProgressOrigin?.kind === 'voice' && p2Binding.interaction_id === ownedProgressOrigin.id))) {
          try { await ensureVoiceTaskProgress(ownedProgressRoute.task_id, p2Binding); } catch { /* Exact owner retains cleanup/retry state. */ }
          return;
        }
      }
      // A loading Task-experience snapshot clears the ref synchronously, but
      // this effect can still hold the previous render's route. Fence that old
      // closure before it can reactivate or ACK. Once the formal collection has
      // supplied authority, reconnect and later refreshes stay blocked until a
      // complete fresh list/status/events/result read publishes its selection.
      // Legacy P3 progress remains independently owned until that first formal
      // collection read succeeds, preserving the accepted P3-5B boundary.
      const routeIsCurrent = ownedProgressRoute === createdProgressRouteRef.current;
      const formalRevalidationPending = taskExperienceRevalidationPendingSessionRef.current === ownedSessionId;
      const formalCollectionOwnsSession = taskExperienceValidatedSessionRef.current === ownedSessionId;
      if (
        !routeIsCurrent
        || formalRevalidationPending
        || (formalCollectionOwnsSession && ownedProgressRoute === null)
      ) {
        setP3Activation({
          status: 'idle',
          binding: null,
          reason: null,
          requested_origin_kind: null,
          effective_origin_kind: null,
          voice_progress: null,
          voice_reason: null,
          fallback_reason: null,
        });
        return;
      }
      const taskTargetInspection = createdProgressRoute === null ? inspectProductP3TaskTarget({ session_id: props.activeSessionId }) : null;
      const hasPendingExactTaskRecovery =
        createdProgressRoute === null &&
        (recoveredP3TaskTargetRef.current !== null || (taskTargetInspection !== null && taskTargetInspection.status !== 'absent'));
      if (hasPendingExactTaskRecovery) {
        setP3Activation({
          status: taskTargetInspection?.status === 'invalid' ? 'unavailable' : 'idle',
          binding: null,
          reason: taskTargetInspection?.status === 'invalid' ? 'PRODUCT_P3_TASK_TARGET_RECOVERY_REQUIRED' : null,
          requested_origin_kind: null,
          effective_origin_kind: null,
          voice_progress: null,
          voice_reason: null,
          fallback_reason: null,
        });
        return;
      }
      let progressOriginId: string;
      let progressGenerationId: string;
      if (createdProgressTaskId === null) {
        const routeId = correlationId.replace(/[^A-Za-z0-9_-]/g, '') || 'route';
        progressOriginId = ownedProgressOrigin?.id ?? `web-progress-${routeId}`;
        progressGenerationId = `web-progress-generation-${routeId}`;
      } else {
        progressOriginId = ownedProgressOrigin?.id ?? ownedProgressCorrelationId;
        progressGenerationId = ownedProgressCorrelationId;
      }
      owner = new ProductWebP3ProgressOwner({
        enabled: true,
        request: (method, params) =>
          productRequest(method, method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? { ...params, origin_kind: ownedProgressOrigin?.kind ?? 'text' } : params),
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
            progressDrainRef.current?.();
          }
        },
      });
      progressActivationOwnerRef.current = owner;
      try {
        await owner.start({
          session_id: props.activeSessionId,
          correlation_id: ownedProgressCorrelationId,
          origin_id: progressOriginId,
          generation_id: progressGenerationId,
          generation: taskId =>
            claimProductP3ProgressGeneration({
              session_id: props.activeSessionId!,
              task_id: taskId,
              correlation_id: ownedProgressCorrelationId,
              origin_id: progressOriginId,
              generation_id: progressGenerationId,
            }),
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
  }, [correlationId, createdProgressRoute, props.activeSessionId, props.isConnected,
    FEATURE_LIVE_VOICE_INTEGRATED_P1 ? p2Activation.status : null,
    FEATURE_LIVE_VOICE_INTEGRATED_P1 ? p2Activation.binding?.activation_id : null]);

  const productTextTransportRetained = Boolean(
    pendingProductTurnRef.current ||
    pendingUnifiedFinalRef.current ||
    deferredTaskPresentationRef.current ||
    unifiedInputOwnerRef.current?.hasPending() ||
    pendingPresentationAttemptRef.current ||
    pendingBargeInRef.current ||
    ownerHasUnsettledGenerationInterrupt(activationOwnerRef.current) ||
    activationOwnerRef.current?.hasPendingSubmission() ||
    activationOwnerRef.current?.hasPendingPresentationAck() ||
    activationOwnerRef.current?.hasPendingPresentationFailure() ||
    activationOwnerRef.current?.hasPendingBargeIn() ||
    activationOwnerRef.current?.hasPendingGenerationInterrupt(),
  );
  const productOperationRetained = Boolean(recognizedSpeechConfirmation || editedVoiceDraftConfirmation || productTextTransportRetained);
  const productVoiceAvailable = FEATURE_LIVE_VOICE_INTEGRATED_P1 && props.isConnected && p2Activation.status === 'active';

  const handleProductInput = (value: string) => {
    const owner = activationOwnerRef.current;
    if (
      pendingProductTurnRef.current ||
      pendingPresentationAttemptRef.current ||
      pendingBargeInRef.current ||
      ownerHasUnsettledGenerationInterrupt(owner) ||
      owner?.hasPendingSubmission() ||
      owner?.hasPendingPresentationAck() ||
      owner?.hasPendingPresentationFailure() ||
      owner?.hasPendingBargeIn() ||
      owner?.hasPendingGenerationInterrupt()
    )
      return;
    updateRecognizedSpeechConfirmation(null);
    setProductTextStatus('idle');
    if (value !== recognizedVoiceRef.current?.text) {
      recognizedVoiceRef.current = null;
    }
    setProductInput(value);
  };

  const handleProductCommandInput = (value: string) => {
    const owner = activationOwnerRef.current;
    if (
      pendingProductTurnRef.current ||
      pendingPresentationAttemptRef.current ||
      pendingBargeInRef.current ||
      ownerHasUnsettledGenerationInterrupt(owner) ||
      owner?.hasPendingSubmission() ||
      owner?.hasPendingPresentationAck() ||
      owner?.hasPendingPresentationFailure() ||
      owner?.hasPendingBargeIn() ||
      owner?.hasPendingGenerationInterrupt()
    )
      return;
    updateRecognizedSpeechConfirmation(null);
    updateEditedVoiceDraftConfirmation(null);
    setProductTextStatus('idle');
    if (value !== recognizedVoiceRef.current?.text) {
      recognizedVoiceRef.current = null;
      voiceDraftBindingRef.current = null;
      p3VoiceDraftBindingRef.current = null;
      voiceTaskOriginRef.current = null;
    }
    setProductInput(value);
    setP3TaskInstruction(value);
  };

  const submitProductCommand = async () => {
    const recognized = recognizedVoiceRef.current;
    const binding = currentProductP2Binding();
    const exactVoiceDraft =
      recognized !== null &&
      recognized.session_id === props.activeSessionId &&
      recognized.text === productInput &&
      recognizedVoiceMatchesProductBinding(recognized, binding);
    await submitProductText(undefined, exactVoiceDraft ? 'voice' : 'structured');
  };

  const handleProductSubmit = () => {
    const recognized = recognizedVoiceRef.current;
    if (recognized !== null && recognized.session_id === props.activeSessionId && recognized.text === productInput) {
      const binding = currentProductP2Binding();
      if (
        recognizedSpeechConfirmationRef.current === null &&
        p2Activation.status === 'active' &&
        binding !== null &&
        recognizedVoiceMatchesProductBinding(recognized, binding)
      ) {
        updateRecognizedSpeechConfirmation(
          Object.freeze({
            intent: 'agent',
            phase: 'confirming',
            session_id: recognized.session_id,
            text: recognized.text,
            correlation_id: binding.correlation_id,
            interaction_id: binding.interaction_id,
            activation_id: binding.activation_id,
            activation_generation: binding.activation_generation,
          }),
        );
      } else if (binding === null || !recognizedVoiceMatchesProductBinding(recognized, binding)) {
        const staleVoiceTaskDraft = p3MutationOperation === 'task.create' && voiceTaskOriginRef.current === null && p3TaskInstruction === recognized.text;
        recognizedVoiceRef.current = null;
        voiceDraftBindingRef.current = null;
        setProductInput('');
        setProductTextStatus('idle');
        if (staleVoiceTaskDraft) {
          pendingP3MutationRef.current = null;
          setP3TaskName('');
          setP3TaskInstruction('');
          setP3MutationStatus('idle');
        }
      }
      return;
    }
    const voiceDraftBinding = voiceDraftBindingRef.current;
    const binding = currentProductP2Binding();
    if (voiceDraftBinding !== null) {
      if (!productVoiceDraftMatchesBinding(voiceDraftBinding, props.activeSessionId, binding) || !productInput.trim()) {
        voiceDraftBindingRef.current = null;
        setProductInput('');
        setProductTextStatus('idle');
        return;
      }
      if (editedVoiceDraftConfirmationRef.current === null && p2Activation.status === 'active' && binding !== null) {
        updateEditedVoiceDraftConfirmation(
          Object.freeze({
            phase: 'confirming',
            session_id: voiceDraftBinding.session_id,
            text: productInput,
            correlation_id: voiceDraftBinding.correlation_id,
            interaction_id: voiceDraftBinding.interaction_id,
            activation_id: voiceDraftBinding.activation_id,
            activation_generation: voiceDraftBinding.activation_generation,
          }),
        );
      }
      return;
    }
    void submitProductText(undefined, 'structured');
  };

  const closeProductVoice = async () => {
    voiceLoopP2RefreshCauseRef.current = 'user_exit';
    clearScheduledProductVoiceLoopCapture();
    voiceLoopEnabledRef.current = false;
    voiceLoopGenerationRef.current += 1;
    // Fence every Task consumer before the first await, even when microphone
    // teardown is delayed or fails. Remote cleanup retains its exact owner.
    for (const [taskId, entry] of voiceProgressOwnersRef.current) void closeVoiceProgress(taskId, entry).catch(() => undefined);
    clearCapturedTaskNotification();
    // Exit is the authoritative local presentation fence. An accepted Agent
    // execution may finish under retained server teardown, but its unpresented
    // response cannot block, text-present, ACK or play in the next loop.
    pendingForegroundPresentationRef.current = null;
    // The listening window belongs to the response Exit just fenced. Leaving it
    // behind is not merely untidy: the next loop refuses to open a new window
    // while one is retained, so generation-time interruption would be silently
    // dead for the rest of the session.
    retireGenerationListening();
    setProductOutput(null);
    setProductTextReason(null);
    setProductTextStatus('idle');
    const activeBinding = activationOwnerRef.current?.snapshot().binding ?? null;
    const refreshAfterGeneration = activeBinding?.activation_generation ?? activationGenerationRef.current;
    voiceLoopP2RefreshAfterGenerationRef.current = Math.max(
      voiceLoopP2RefreshAfterGenerationRef.current ?? refreshAfterGeneration,
      refreshAfterGeneration,
    );
    voiceLoopP2RefreshInFlightRef.current = false;
    const hadVoiceDraft = recognizedVoiceRef.current !== null || voiceDraftBindingRef.current !== null;
    updateRecognizedSpeechConfirmation(null);
    recognizedVoiceRef.current = null;
    voiceDraftBindingRef.current = null;
    if (hadVoiceDraft) {
      setProductInput('');
      setProductTextStatus('idle');
    }
    p1VoiceCaptureBindingRef.current = null;
    activeVoiceResponseRef.current = null;
    const owner = p1VoiceOwnerRef.current;
    if (owner === null) {
      setP1VoiceStatus('closed');
      setP1VoiceReason(null);
      requestVoiceLoopP2Refresh();
      return;
    }
    try {
      await owner.close();
      if (p1VoiceOwnerRef.current === owner) {
        p1VoiceOwnerRef.current = null;
      }
    } catch {
      // Retain the exact cleanup_pending owner. A later explicit start retries
      // cleanup before it can construct a successor route.
      throw new Error('FORMAL_P1_CLEANUP_PENDING');
    }
    requestVoiceLoopP2Refresh();
  };

  const closeProductVoiceSession = async (sessionId: string) => {
    voiceLoopP2RefreshCauseRef.current = 'session_change';
    for (const [taskId, entry] of voiceProgressOwnersRef.current) {
      if (entry.binding.session_id === sessionId) void closeVoiceProgress(taskId, entry).catch(() => undefined);
    }
    const owner = p1VoiceOwnerRef.current;
    if (owner === null || p1VoiceOwnerSessionRef.current !== sessionId) return;
    try {
      await owner.close();
    } catch {
      // Keep the exact old-Session owner retained. Browser capture ownership
      // cannot move until a later attempt settles this same cleanup.
      throw new Error('FORMAL_P1_CLEANUP_PENDING');
    }
    if (p1VoiceOwnerRef.current === owner) {
      p1VoiceOwnerRef.current = null;
      p1VoiceOwnerSessionRef.current = null;
      if (p1VoiceCaptureBindingRef.current?.session_id === sessionId) {
        p1VoiceCaptureBindingRef.current = null;
      }
      // Browser capture ownership just moved away. The generation-time
      // listening window belonged to the capture that was surrendered, and it
      // is the one thing that lets the notification poll run during a capture;
      // leaving it behind would grant that privilege to whatever starts next.
      retireGenerationListening(listening => listening.fence.session_id === sessionId);
    }
  };

  const startProductVoiceLoop = async () => {
    recordAudioDiagnostic('voice_listening_start', {
      session_id: activeSessionRef.current,
      status: p1VoiceOwnerRef.current?.status().status ?? 'idle',
      reason: recoveryDiagnosticRef.current?.reason ?? null,
    });
    if (p1VoiceOwnerRef.current?.status().status === 'capturing'
        && recoveryDiagnosticRef.current?.seam === 'response_generation') {
      // Input is already available. Retry clears the status diagnostic without
      // replaying the failed business request.
      clearProductRecoveryDiagnostic();
      setProductTextReason(null);
      setProductTextStatus('idle');
      return;
    }
    if (!voiceLoopEnabledRef.current) {
      voiceLoopGenerationRef.current += 1;
      voiceLoopEnabledRef.current = true;
    }
    const activationOwner = activationOwnerRef.current;
    const activationBinding = activationOwner?.snapshot().binding;
    const captureStatus = p1VoiceOwnerRef.current?.status().status ?? 'closed';
    if (activationOwner?.snapshot().status === 'active' && activationBinding &&
        ['idle', 'closed', 'failed'].includes(captureStatus) &&
        activationOwner.requestedAgentModelName() !== selectedAgentModelNameRef.current) {
      // Selection changes start a new immutable activation. Accepted work keeps
      // the predecessor's server-confirmed model and is never resubmitted here.
      voiceLoopP2RefreshAfterGenerationRef.current = activationBinding.activation_generation;
      voiceLoopP2RefreshCauseRef.current = 'active_recovery';
    }

    if (
      p2Activation.status === 'unavailable' &&
      (p2Activation.reason === PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED ||
        p2Activation.reason === PRODUCT_P2_REFRESH_SERVER_STATE_LOST)
    ) {
      const journal = p2ActivationJournalRef.current;
      if (journal === null) return;
      try {
        const snapshot = journal.refresh();
        const predecessorGeneration = snapshot.binding?.activation_generation ?? snapshot.last_generation;
        voiceLoopP2RefreshAfterGenerationRef.current = Math.max(
          voiceLoopP2RefreshAfterGenerationRef.current ?? predecessorGeneration,
          predecessorGeneration,
        );
        voiceLoopP2RefreshInFlightRef.current = false;
        if (snapshot.phase === 'result_unknown') {
          if (snapshot.binding === null) return;
          // A user-visible retry abandons no durable operation. It promotes the
          // generic hard barrier only to exact activation cleanup; the recovery
          // effect must still replay/close this predecessor before allocating a
          // successor generation.
          journal.requestResultUnknownRecovery(snapshot.binding);
        }
      } catch {
        return;
      }
      setP2RecoveryEpoch(epoch => epoch + 1);
      return;
    }
    const retainedTerminal = pendingPresentationAttemptRef.current;
    if (retainedTerminal?.task_notification != null && terminalAnnouncementStateRef.current === 'recovering') {
      retryTerminalAnnouncementHandlerRef.current(retainedTerminal);
      return;
    }
    const retainedP1 = p1VoiceOwnerRef.current;
    if (voiceLoopP2RefreshAfterGenerationRef.current !== null) {
      if (voiceLoopP2RefreshInFlightRef.current) return;
      if (retainedP1 !== null && retainedP1.status().status !== 'closed') {
        try {
          await retainedP1.close();
        } catch {
          return;
        }
        if (p1VoiceOwnerRef.current === retainedP1) p1VoiceOwnerRef.current = null;
      }
      requestVoiceLoopP2Refresh();
      return;
    }
    await startProductVoiceCapture();
  };

  const currentNativeWorkState = nativeWorkState !== null && props.isConnected && voiceLoopEnabledRef.current &&
    p2Activation.status === 'active' && props.activeSessionId === nativeWorkState.session_id &&
    nativeWorkBindingMatches(nativeWorkState, p2Activation.binding) ? nativeWorkState : null;
  useEffect(() => {
    if (currentNativeWorkState === null && nativeWorkStateRef.current !== null) {
      nativeWorkStateRef.current = null;
      setNativeWorkState(null);
    }
  }, [currentNativeWorkState]);

  useEffect(() => {
    props.onProductVoiceStateChange?.(
      Object.freeze({
        available: productVoiceAvailable,
        p1_status: p1VoiceStatus,
        p1_reason: p1VoiceReason,
        p1_fault_tail_playing: p1FaultTailPlaying,
        interruption_degraded_reason: interruptionDegradedReason,
        input: productInput,
        output: productOutput,
        text_status: productTextStatus,
        text_reason: productTextReason,
        replacement_recognition_failed: replacementRecognitionFailure !== null &&
          replacementRecognitionFailure.session_id === props.activeSessionId &&
          replacementRecognitionFailure.loop_generation === voiceLoopGenerationRef.current &&
          voiceLoopEnabledRef.current,
        confirmation_phase: recognizedSpeechConfirmation?.phase ?? editedVoiceDraftConfirmation?.phase ?? null,
        operation_retained: productOperationRetained,
        task_progress_task_id: progress?.task_id ?? null,
        task_progress_state: progress?.state ?? null,
        task_progress_delivery_mode: progress?.delivery_mode ?? null,
        task_progress_event: progress,
        task_progress_node_ref: adoptVisibleProductTextProgressNode,
        task_unread_delivery: progress === null ? null : Object.freeze({
          task_id: progress.task_id,
          attempt_id: progress.attempt_id,
          event_id: progress.source_event.event_id,
          event_seq: progress.source_event.seq,
          acknowledgement: progressAck,
        }),
        terminal_announcement_state: terminalAnnouncementState,
        recovery_diagnostic: recoveryDiagnostic,
        terminal_notification: terminalNotification,
        adjustment_notification: adjustmentNotification,
        task_experience: taskExperience,
        native_work: currentNativeWorkState,
      }),
    );
  }, [
    p1VoiceReason,
    p1VoiceStatus,
    p1FaultTailPlaying,
    interruptionDegradedReason,
    productInput,
    productOperationRetained,
    productOutput,
    productTextReason,
    replacementRecognitionFailure,
    productTextStatus,
    productVoiceAvailable,
    adoptVisibleProductTextProgressNode,
    progress?.delivery_mode,
    progress?.attempt_id,
    progress?.source_event.event_id,
    progress?.source_event.seq,
    progress?.state,
    progress?.task_id,
    progressAck,
    props.onProductVoiceStateChange,
    currentNativeWorkState,
    props.isConnected,
    editedVoiceDraftConfirmation?.phase,
    recognizedSpeechConfirmation?.phase,
    recoveryDiagnostic,
    adjustmentNotification,
    terminalAnnouncementState,
    terminalNotification,
    taskExperience,
  ]);

  useEffect(() => {
    const control = Object.freeze<ProductLiveVoiceSurfaceControl>({
      start: startProductVoiceLoop,
      stop: () => {
        const owner = p1VoiceOwnerRef.current;
        const faultTail = owner?.frozenFaultTailResponse() ?? null;
        if (owner !== null && faultTail !== null) {
          // Cleanup already owns remote retirement. This local exact STOP must
          // remain available without capture, an active P2 route or a new RPC.
          owner.stopAgentPlayout(faultTail);
          return Promise.resolve();
        }
        return owner?.status().status === 'playing' ? stopProductVoicePlayout() : stopProductVoiceCapture();
      },
      setL0CaptureStreamFactory: factory => {
        l0CaptureStreamFactoryRef.current = factory;
      },
      closeSession: closeProductVoiceSession,
      updateInput: handleProductCommandInput,
      submit: handleProductSubmit,
      submitCommand: () => void submitProductCommand(),
      confirm: acceptRecognizedSpeechConfirmation,
      cancelConfirmation: () => {
        updateRecognizedSpeechConfirmation(null);
        updateEditedVoiceDraftConfirmation(null);
      },
      refreshTasks: async () => {
        const owner = taskExperienceOwnerRef.current;
        const sessionId = activeSessionRef.current;
        if (owner === null || sessionId === null || !isConnectedRef.current) throw new Error('formal P3 Task experience is unavailable');
        await owner.refresh(sessionId);
      },
      selectTask: async taskId => {
        const owner = taskExperienceOwnerRef.current;
        if (owner === null || !isConnectedRef.current) throw new Error('formal P3 Task experience is unavailable');
        await owner.select(taskId);
      },
      issueTaskMutation: async input => {
        const owner = taskExperienceOwnerRef.current;
        if (owner === null || !isConnectedRef.current) throw new Error('formal P3 Task experience is unavailable');
        await owner.issue(input);
      },
      confirmTaskMutation: async () => {
        const owner = taskExperienceOwnerRef.current;
        if (owner === null || !isConnectedRef.current) throw new Error('formal P3 Task experience is unavailable');
        await owner.confirm();
      },
      close: closeProductVoice,
    });
    if (props.productVoiceControlRef) props.productVoiceControlRef.current = control;
    return () => {
      if (props.productVoiceControlRef?.current === control) props.productVoiceControlRef.current = null;
    };
  });

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
      p1VoiceEnabled={productVoiceAvailable}
      p1VoiceStatus={p1VoiceStatus}
      p1VoiceReason={p1VoiceReason}
      deviceSelection={deviceSelection}
      draftInputDeviceToken={draftInputDeviceToken}
      draftOutputDeviceToken={draftOutputDeviceToken}
      onLoadAudioDevices={() => void loadProductAudioDevices()}
      onDraftInputDevice={setDraftInputDeviceToken}
      onDraftOutputDevice={setDraftOutputDeviceToken}
      onApplyAudioDevices={() => void applyProductAudioDevices()}
      onP1VoiceStart={() => void startProductVoiceLoop()}
      onP1VoiceStop={() => void (p1VoiceStatus === 'playing' ? stopProductVoicePlayout() : stopProductVoiceCapture())}
      productOperationRetained={productOperationRetained}
      productTextTransportRetained={productTextTransportRetained}
      onProductInput={handleProductInput}
      onProductSubmit={handleProductSubmit}
      recognizedSpeechConfirmation={
        recognizedSpeechConfirmation?.phase === 'confirming'
          ? recognizedSpeechConfirmation.intent
          : editedVoiceDraftConfirmation?.phase === 'confirming'
            ? 'agent'
            : null
      }
      recognizedSpeechDispatching={recognizedSpeechConfirmation?.phase === 'dispatching' || editedVoiceDraftConfirmation?.phase === 'dispatching'}
      onRecognizedSpeechConfirm={() => void acceptRecognizedSpeechConfirmation()}
      onRecognizedSpeechCancel={() => {
        updateRecognizedSpeechConfirmation(null);
        updateEditedVoiceDraftConfirmation(null);
      }}
      p3MutationEnabled={FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION && props.isConnected}
      p3MutationOperation={p3MutationOperation}
      p3TaskName={p3TaskName}
      p3TaskInstruction={p3TaskInstruction}
      p3TargetTaskId={p3TargetTaskId}
      p3MutationStatus={p3MutationStatus}
      p3MutationReason={p3MutationReason}
      p3MutationRetained={
        p3MutationOwnerRef.current?.hasPendingMutation() === true || pendingP3MutationRef.current !== null || pendingFormalP3MutationRef.current !== null
      }
      p3RetryEligible={isFormalTaskRetryEligible(p3RetryEligibility)}
      p3RetryAttemptNumber={p3RetryEligibility?.attempt_number ?? null}
      p3RetryInspectionStatus={p3RetryInspectionStatus}
      p3RetryInspectionReason={p3RetryInspectionReason}
      onP3MutationOperation={value => {
        updateRecognizedSpeechConfirmation(null);
        cancelP3RetryInspection();
        pendingP3MutationRef.current = null;
        p3AcceptedFollowTargetRef.current = null;
        voiceTaskOriginRef.current = null;
        p3VoiceDraftBindingRef.current = null;
        if (value === 'task.create') {
          setP3RetryEligibility(null);
          setP3RetryInspectionStatus('idle');
          setP3RetryInspectionReason(null);
        }
        setP3MutationStatus('idle');
        setP3MutationReason(null);
        setP3MutationOperation(value);
      }}
      onP3TaskName={value => {
        updateRecognizedSpeechConfirmation(null);
        pendingP3MutationRef.current = null;
        setP3MutationStatus('idle');
        setP3MutationReason(null);
        setP3TaskName(value);
      }}
      onP3TaskInstruction={value => {
        updateRecognizedSpeechConfirmation(null);
        pendingP3MutationRef.current = null;
        if (value !== voiceTaskOriginRef.current?.instruction) {
          voiceTaskOriginRef.current = null;
        }
        if (value !== recognizedVoiceRef.current?.text) {
          recognizedVoiceRef.current = null;
          p3VoiceDraftBindingRef.current = null;
        }
        setP3MutationStatus('idle');
        setP3MutationReason(null);
        setP3TaskInstruction(value);
      }}
      onP3TargetTaskId={value => {
        p3ProgressReconciliationGenerationRef.current += 1;
        updateRecognizedSpeechConfirmation(null);
        pendingP3MutationRef.current = null;
        p3AcceptedFollowTargetRef.current = null;
        cancelP3RetryInspection();
        setP3RetryEligibility(null);
        setP3RetryInspectionStatus('idle');
        setP3RetryInspectionReason(null);
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
