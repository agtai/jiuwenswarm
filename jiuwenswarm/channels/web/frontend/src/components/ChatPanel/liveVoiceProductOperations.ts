import {
  FEATURE_LIVE_VOICE_INTEGRATED_P1,
  FEATURE_LIVE_VOICE_INTEGRATED_WEB,
  FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION,
} from '../../featureFlags';
import type { BrowserAudioCaptureStreamFactory } from '../../features/live-voice/formal/adapters/browserAudioIOAdapter';
import { type FormalP3TaskExperienceSnapshot, type FormalP3TaskMutationInput } from '../../features/live-voice/formal/formalP3TaskExperience';
import {
  FormalTaskControlLeaf,
  isFormalTaskRetryEligible,
  type FormalTaskControlBinding,
  type FormalTaskControlRecord,
  type FormalTaskState,
} from '../../features/live-voice/formal/formalTaskControlLeaf';
import {
  IntegratedWebRouteShell,
  createCurrentIntegratedWebRouteSelection,
  type IntegratedWebRouteManifest,
  type IntegratedWebRouteSelection,
} from '../../features/live-voice/formal/integratedWebRouteShell';
import { parseEventEnvelope } from '../../features/live-voice/formal/liveVoiceContractV2';
import { type NativeGeneratedMessage } from '../../features/live-voice/formal/nativeGeneratedText';
import { parseNativeWorkStateNotification, type NativeWorkStateNotification, type NativeWorkStateSnapshot } from '../../features/live-voice/formal/nativeWorkState';
import { ProductP1VoiceRouteOwner, type ProductP1InteractionEngine, type ProductP1VoiceStatus } from '../../features/live-voice/formal/productP1VoiceRoute';
import { type ProductTextProgressEvent } from '../../features/live-voice/formal/productTextProgress';
import {
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_PRESENTATION_ACK_METHOD,
  PRODUCT_P3_TASK_EVENTS_METHOD,
  PRODUCT_P3_TASK_STATUS_METHOD,
  ProductWebP2ActivationOwner,
  type ProductWebP2ActivationBinding,
  type ProductWebP2ActivationSnapshot,
  type ProductWebP3ProgressBinding,
} from '../../features/live-voice/formal/productWebActivation';
import { taskNotificationSourceKey, type TaskNotificationDisplay } from '../../features/live-voice/formal/taskNotificationIdentity';
import { PRODUCT_SEMANTIC_CLIENT_TIMEOUT_MS, PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD } from '../../features/live-voice/formal/unifiedCommittedInputOwner';
import { extractWebErrorReason, webClient } from '../../services/webClient';
import type { WebRequestOptions } from '../../types';

export type ProductP2ActivationOwnerInput = Omit<
  ConstructorParameters<typeof ProductWebP2ActivationOwner>[0],
  'notification_batch_size'
> & { notification_batch_size?: 1 | 16 };


export function createProductP2ActivationOwner(input: ProductP2ActivationOwnerInput): ProductWebP2ActivationOwner {
  const { notification_batch_size = 16, ...ownerInput } = input;
  return new ProductWebP2ActivationOwner({
    ...ownerInput,
    notification_batch_size,
  });
}

export function sameProductP2ActivationBinding(
  left: Readonly<ProductWebP2ActivationBinding>,
  right: Readonly<ProductWebP2ActivationBinding>,
): boolean {
  return (
    left.session_id === right.session_id &&
    left.correlation_id === right.correlation_id &&
    left.interaction_id === right.interaction_id &&
    left.activation_id === right.activation_id &&
    left.activation_generation === right.activation_generation
  );
}


export function normalizeProductP1StatusForP2Retirement(
  status: ProductP1VoiceStatus,
  reason: string | null,
  p2RetirementStarted: boolean,
): Readonly<{ status: ProductP1VoiceStatus; reason: string | null }> {
  if (
    p2RetirementStarted
    && status === 'failed'
    && reason === 'STREAMING_SPEECH_ROUTE_ABORTED'
  ) {
    return Object.freeze({
      status: 'cleanup_pending',
      reason: 'FORMAL_P1_CLEANUP_IN_PROGRESS',
    });
  }
  return Object.freeze({ status, reason });
}


export interface LiveVoiceIntegratedRoutePanelProps {
  activeSessionId: string | null;
  isConnected: boolean;
  agentRouteAvailable: boolean;
  selectedAgentModelName?: string | null;
  routeSelection?: Readonly<IntegratedWebRouteSelection>;
  request?: (method: string, params?: Record<string, unknown>, options?: WebRequestOptions) => Promise<unknown>;
  progressSubscribe?: (listener: (payload: unknown) => void) => () => void;
  progressAckCapacity?: number;
  p3RetryInspectionWait?: (delayMs: number, signal: AbortSignal) => Promise<void>;
  taskNotificationPlayoutTimeoutMs?: number;
  productVoiceControlRef?: { current: ProductLiveVoiceSurfaceControl | null };
  onProductVoiceStateChange?: (state: Readonly<ProductLiveVoiceSurfaceState>) => void;
  onProductVoiceMessage?: (event: Readonly<ProductLiveVoiceMessageEvent>) => void;
  onNativeVoiceDisplayEnded?: (sessionId: string, responseKeys: readonly string[]) => void;
}


export type ProductLiveVoiceMessageEvent = Readonly<{
  session_id: string;
  message: Readonly<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    nativeVoice?: NativeGeneratedMessage['nativeVoice'];
    nativeTurnKey?: string;
    taskNotification?: TaskNotificationDisplay;
  }>;
}>;


export type ProductLiveVoiceRecoveryDiagnostic = Readonly<{
  seam: 'activation' | 'response_generation' | 'presentation_ack' | 'tts';
  disposition: 'retrying' | 'terminal';
  reason: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string | null;
  activation_id: string | null;
  activation_generation: number | null;
  response_id: string | null;
  response_generation: number | null;
}>;


export type ProductLiveVoiceSurfaceState = Readonly<{
  available: boolean;
  p1_status: ProductP1VoiceStatus;
  p1_reason: string | null;
  /** Local accepted PCM may still drain after the Provider transport failed. */
  p1_fault_tail_playing?: boolean;
  interruption_degraded_reason: string | null;
  input: string;
  output: string | null;
  text_status: 'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed';
  text_reason: string | null;
  replacement_recognition_failed?: boolean;
  confirmation_phase: 'confirming' | 'dispatching' | null;
  operation_retained: boolean;
  task_progress_task_id: string | null;
  task_progress_state: string | null;
  task_progress_delivery_mode: ProductTextProgressEvent['delivery_mode'] | null;
  task_progress_event: Readonly<ProductTextProgressEvent> | null;
  task_progress_node_ref: (node: HTMLDivElement | null) => void;
  task_unread_delivery: Readonly<{
    task_id: string;
    attempt_id: string;
    event_id: string;
    event_seq: number;
    acknowledgement: 'idle' | 'pending' | 'acknowledged' | 'failed';
  }> | null;
  terminal_announcement_state: TerminalAnnouncementState;
  recovery_diagnostic: ProductLiveVoiceRecoveryDiagnostic | null;
  terminal_notification: string | null;
  adjustment_notification: string | null;
  task_experience: FormalP3TaskExperienceSnapshot;
  native_work?: NativeWorkStateSnapshot | null;
}>;


export interface ProductLiveVoiceSurfaceControl {
  start(): Promise<void>;
  stop(): Promise<void>;
  setL0CaptureStreamFactory(factory: BrowserAudioCaptureStreamFactory | null): void;
  closeSession(sessionId: string): Promise<void>;
  updateInput(value: string): void;
  submit(): void;
  submitCommand(): void;
  confirm(): Promise<void>;
  cancelConfirmation(): void;
  refreshTasks(): Promise<void>;
  selectTask(taskId: string): Promise<void>;
  issueTaskMutation(input: FormalP3TaskMutationInput): Promise<void>;
  confirmTaskMutation(): Promise<void>;
  close(): Promise<void>;
}

export const defaultProductRequest = (method: string, params?: Record<string, unknown>, options?: WebRequestOptions): Promise<unknown> =>
  webClient.request(method, params, options);

export const PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS = Object.freeze([250, 500, 1_000, 2_000, 4_000, 8_000, 16_000, 30_000]);

export const PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS = Object.freeze([250, 500, 1_000]);

export const PRODUCT_P3_PROGRESS_BUFFER_CAPACITY = 128;

export const PRODUCT_P3_PROGRESS_EXHAUSTED_CAPACITY = 128;

export const PRODUCT_P3_PROGRESS_RECONCILIATION_RETRY_MS = 250;

export const PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS = 4;

export const PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED = 'PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED';

export const PRODUCT_P2_NOTIFICATION_PENDING_BACKOFF_MS = 500;

export const PRODUCT_TASK_NOTIFICATION_PLAYOUT_TIMEOUT_MS = 15_000;


export async function awaitProductTaskNotificationPlayout(
  operation: Promise<unknown>,
  onTimeout: () => void,
  timeoutMs = PRODUCT_TASK_NOTIFICATION_PLAYOUT_TIMEOUT_MS,
): Promise<void> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error('Task notification playout timeout must be positive');
  }
  let timeout: ReturnType<typeof globalThis.setTimeout> | null = null;
  const deadline = new Promise<void>((_resolve, reject) => {
    timeout = globalThis.setTimeout(() => {
      try {
        onTimeout();
      } finally {
        reject(
          Object.assign(new Error('Task notification playout did not settle'), {
            reason: 'PRODUCT_TASK_NOTIFICATION_PLAYOUT_TIMEOUT',
          }),
        );
      }
    }, timeoutMs);
  });
  try {
    await Promise.race([operation, deadline]);
  } finally {
    if (timeout !== null) globalThis.clearTimeout(timeout);
  }
}

export function defaultP3RetryInspectionWait(delayMs: number, signal: AbortSignal): Promise<void> {
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

export type ProductTaskPresentationFailureReason = 'task_audio_playout_failed' | 'task_audio_owner_unavailable';

export function sameProductPresentation(
  left: ProductPresentationAckInput,
  right: ProductPresentationAckInput,
): boolean {
  return (
    left.response_id === right.response_id &&
    left.response_generation === right.response_generation &&
    left.surface === right.surface &&
    left.unit_id === right.unit_id &&
    left.contiguous_cursor === right.contiguous_cursor
  );
}

export function durablePresentationAckMatches(
  operation: Readonly<{ method: string; params: Readonly<Record<string, unknown>> }>,
  input: ProductPresentationAckInput & { presented_at: string },
): boolean {
  return (
    operation.method === PRODUCT_P2_PRESENTATION_ACK_METHOD &&
    sameProductPresentation(operation.params as ProductPresentationAckInput, input) &&
    operation.params.presented_at === input.presented_at
  );
}


export const PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER = 'PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER';

export function playoutDeferredToSpeaker(value: unknown): boolean {
  return (
    value !== null &&
    typeof value === 'object' &&
    (value as { reason?: unknown }).reason === PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER
  );
}

export function stableProductTextReason(value: unknown, fallback: string): string {
  const candidate = typeof value === 'string' ? value : extractWebErrorReason(value);
  return typeof candidate === 'string' && /^[A-Z][A-Z0-9_]{0,127}$/.test(candidate) ? candidate : fallback;
}


export function productRecoveryDiagnosticMatchesClear(
  current: ProductLiveVoiceRecoveryDiagnostic,
  input: Readonly<{
    seam: ProductLiveVoiceRecoveryDiagnostic['seam'];
    binding: ProductWebP2ActivationSnapshot['binding'];
    response?: Readonly<{
      response_id: string;
      response_generation: number;
    }> | null;
  }>,
): boolean {
  if (current.seam !== input.seam) return false;
  if (input.binding !== null) {
    const activationScopeDiagnostic =
      current.seam === 'activation' &&
      current.interaction_id === null &&
      current.activation_id === null &&
      current.activation_generation === null &&
      current.response_id === null &&
      current.response_generation === null;
    if (
      current.session_id !== input.binding.session_id ||
      current.correlation_id !== input.binding.correlation_id ||
      (!activationScopeDiagnostic &&
        (current.interaction_id !== input.binding.interaction_id ||
          current.activation_id !== input.binding.activation_id ||
          current.activation_generation !== input.binding.activation_generation))
    ) {
      return false;
    }
  }
  if (
    input.response !== undefined &&
    input.response !== null &&
    (current.response_id !== input.response.response_id || current.response_generation !== input.response.response_generation)
  ) {
    return false;
  }
  return true;
}

export function isStaleProductResponseError(value: unknown): boolean {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const detail =
    candidate.error !== null && typeof candidate.error === 'object' && !Array.isArray(candidate.error)
      ? (candidate.error as Record<string, unknown>)
      : null;
  return (
    candidate.code === 'STALE' ||
    detail?.code === 'STALE' ||
    candidate.reason === 'STALE_RESPONSE_OUTPUT' ||
    detail?.reason === 'STALE_RESPONSE_OUTPUT'
  );
}

export function isHarmlessCompletedBargeInError(value: unknown): boolean {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const detail =
    candidate.error !== null && typeof candidate.error === 'object' && !Array.isArray(candidate.error)
      ? (candidate.error as Record<string, unknown>)
      : null;
  const reason = typeof candidate.reason === 'string' ? candidate.reason : detail?.reason;
  return (
    reason === 'RESPONSE_ALREADY_TERMINAL' ||
    reason === 'UNKNOWN_AGENT_RESPONSE' ||
    reason === 'STALE_RESPONSE_OUTPUT'
  );
}

export type ProductTurnInput = {
  commit_id: string;
  turn_id: string;
  response_id?: string;
  committed_at: string;
  text: string;
  dispatch_target?: 'agent' | 'task';
  voice_commit_receipt?: string;
  critical_confirmation?: true;
};


export type ProductRecognizedVoice = Readonly<{
  session_id: string;
  text: string;
  voice_commit_receipt: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
}>;


export type RecognizedSpeechConfirmation = Readonly<{
  intent: 'agent' | 'task';
  task_route?: 'structured';
  phase: 'confirming' | 'dispatching';
  session_id: string;
  text: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
}>;

export type ProductVoiceDraftBinding = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
}>;

export type EditedVoiceDraftConfirmation = ProductVoiceDraftBinding &
  Readonly<{
    phase: 'confirming' | 'dispatching';
    text: string;
  }>;


export function hasDurableProductVoiceSession(sessionId: string | null): sessionId is string {
  return sessionId !== null && sessionId.trim().length > 0 && sessionId !== 'new';
}


export function productVoiceDraftMatchesBinding(
  draft: ProductVoiceDraftBinding | null,
  activeSessionId: string | null,
  binding: ProductWebP2ActivationSnapshot['binding'],
): draft is ProductVoiceDraftBinding {
  return Boolean(
    draft !== null &&
    binding !== null &&
    activeSessionId !== null &&
    draft.session_id === activeSessionId &&
    binding.session_id === activeSessionId &&
    draft.correlation_id === binding.correlation_id &&
    draft.interaction_id === binding.interaction_id &&
    draft.activation_id === binding.activation_id &&
    draft.activation_generation === binding.activation_generation,
  );
}


export type ProductVoiceTaskOrigin = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  turn_id: string;
  commit_id: string;
  response_id: string;
  response_generation: number;
  instruction: string;
}>;

export type ProductWebRequest = NonNullable<LiveVoiceIntegratedRoutePanelProps['request']>;

export function sameFormalTaskControlBinding(left: Readonly<FormalTaskControlBinding>, right: Readonly<FormalTaskControlBinding>): boolean {
  return (
    left.subject_id === right.subject_id &&
    left.session_id === right.session_id &&
    left.project_id === right.project_id &&
    left.correlation_id === right.correlation_id &&
    left.generation === right.generation
  );
}


/**
 * Recover only enough local authority to validate an authenticated historical
 * task query.  The returned status is immediately adopted by the formal leaf,
 * so a forged scope, Session, correlation, target, or attempt still fails
 * closed before the caller can expose retry or mutation controls.
 */
export function bootstrapProductP3TaskInspectionLeaf(
  response: unknown,
  input: Readonly<{
    session_id: string;
    task_id: string;
    expected_binding?: FormalTaskControlBinding;
  }>,
): FormalTaskControlLeaf {
  const envelope = recordValue(response);
  const result = recordValue(envelope?.result);
  const task = recordValue(result?.task);
  const scope = recordValue(task?.scope);
  const required = (value: unknown, field: string): string => {
    if (typeof value !== 'string' || !value.trim()) throw new Error(`formal task inspection ${field} is invalid`);
    return value;
  };
  const observedBinding = Object.freeze({
    subject_id: required(scope?.subject_id, 'subject_id'),
    session_id: required(scope?.session_id, 'session_id'),
    project_id: required(scope?.project_id, 'project_id'),
    correlation_id: required(task?.correlation_id, 'correlation_id'),
  });
  if (observedBinding.session_id !== input.session_id) throw new Error('formal task inspection Session binding mismatch');
  const expectedBinding = input.expected_binding;
  if (
    expectedBinding !== undefined &&
    (observedBinding.subject_id !== required(expectedBinding.subject_id, 'expected subject_id') ||
      observedBinding.session_id !== required(expectedBinding.session_id, 'expected session_id') ||
      observedBinding.project_id !== required(expectedBinding.project_id, 'expected project_id') ||
      observedBinding.correlation_id !== required(expectedBinding.correlation_id, 'expected correlation_id') ||
      !Number.isSafeInteger(expectedBinding.generation) ||
      expectedBinding.generation <= 0)
  ) {
    throw new Error('formal task inspection task-control binding mismatch');
  }
  const binding = Object.freeze({
    ...observedBinding,
    generation: expectedBinding?.generation ?? 1,
  });
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt('task.status', response, {
    connection_generation: leaf.snapshot().connection_generation,
    command_id: null,
    target_task_id: input.task_id,
    events_query: null,
  });
  return leaf;
}


/**
 * Read and validate one exact retry candidate before publishing it to the live
 * leaf.  Status and full history are first reduced in an isolated probe; only
 * the already-validated event history may update the live replica, and only
 * while the caller's Session/target generation is still current.
 */
export async function inspectProductP3RetryCandidate(
  input: Readonly<{
    request: ProductWebRequest;
    leaf: FormalTaskControlLeaf;
    session_id: string;
    task_id: string;
    request_nonce: string;
    is_current: () => boolean;
  }>,
): Promise<ProductP3RetryInspection> {
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
  const stillCurrent = () => input.is_current() && input.leaf.snapshot().connected && input.leaf.snapshot().connection_generation === ownedGeneration;
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
  const admission = parseProductP3RetryAdmission(statusResponse, selected);
  const previouslyObserved = initialSnapshot.tasks.find(task => task.task_id === taskId) ?? null;
  if (
    previouslyObserved !== null &&
    previouslyObserved.attempt_id !== null &&
    previouslyObserved.attempt_number !== null &&
    (selected.attempt_id === null ||
      selected.attempt_number === null ||
      selected.attempt_number < previouslyObserved.attempt_number ||
      (selected.attempt_number === previouslyObserved.attempt_number && selected.attempt_id !== previouslyObserved.attempt_id) ||
      (selected.attempt_id === previouslyObserved.attempt_id &&
        previouslyObserved.last_event_seq !== null &&
        (selected.last_event_seq === null || selected.last_event_seq < previouslyObserved.last_event_seq)) ||
      (selected.attempt_id === previouslyObserved.attempt_id && previouslyObserved.state === 'terminal' && selected.state !== 'terminal') ||
      (selected.attempt_id === previouslyObserved.attempt_id &&
        previouslyObserved.state === 'terminal' &&
        selected.state === 'terminal' &&
        selected.outcome !== previouslyObserved.outcome))
  ) {
    throw new Error('formal task retry inspection cannot regress an observed successor');
  }
  input.leaf.adopt('task.events', eventsResponse, {
    connection_generation: ownedGeneration,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: taskId, after_seq: -1 },
  });
  const adopted = input.leaf.snapshot().tasks.find(task => task.task_id === taskId) ?? null;
  if (
    adopted === null ||
    adopted.attempt_id !== selected.attempt_id ||
    adopted.attempt_number !== selected.attempt_number ||
    adopted.state !== selected.state ||
    adopted.outcome !== selected.outcome ||
    adopted.event_head !== selected.event_head
  ) {
    throw new Error('formal task retry inspection lost its exact task revision');
  }
  return Object.freeze({ record: adopted, admission });
}


export function resolveProductTaskCreateOrigin(
  instruction: string,
  activeSessionId: string | null,
  origin: ProductVoiceTaskOrigin | null,
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
    ...(method === PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD ? { timeoutMs: PRODUCT_SEMANTIC_CLIENT_TIMEOUT_MS } : {}),
  };
}


export function productTextBlockedByP1Status(status: ProductP1VoiceStatus): boolean {
  return ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(status);
}


export function shouldBlockProductP2NotificationPoll(
  status: ProductP1VoiceStatus,
  interactionEngine: ProductP1InteractionEngine,
): boolean {
  return (
    ['starting', 'recognizing', 'playing', 'cleanup_pending'].includes(status) ||
    (status === 'capturing' && interactionEngine !== 'openai-realtime-native')
  );
}


export function recognizedSpeechConfirmationMatches(
  pending: RecognizedSpeechConfirmation | null,
  recognized: ProductRecognizedVoice | null,
  activeSessionId: string | null,
  displayedText: string,
  binding: Readonly<{
    session_id: string;
    correlation_id: string;
    interaction_id: string;
    activation_id: string;
    activation_generation: number;
  }> | null,
): boolean {
  return (
    pending !== null &&
    recognized !== null &&
    activeSessionId !== null &&
    binding !== null &&
    pending.session_id === activeSessionId &&
    recognized.session_id === activeSessionId &&
    pending.text === displayedText &&
    recognized.text === displayedText &&
    recognized.correlation_id === binding.correlation_id &&
    recognized.interaction_id === binding.interaction_id &&
    recognized.activation_id === binding.activation_id &&
    recognized.activation_generation === binding.activation_generation &&
    pending.session_id === binding.session_id &&
    pending.correlation_id === binding.correlation_id &&
    pending.interaction_id === binding.interaction_id &&
    pending.activation_id === binding.activation_id &&
    pending.activation_generation === binding.activation_generation
  );
}

export function recognizedVoiceMatchesProductBinding(
  recognized: ProductRecognizedVoice,
  binding: Readonly<{
    session_id: string;
    correlation_id: string;
    interaction_id: string;
    activation_id: string;
    activation_generation: number;
  }> | null,
): boolean {
  return (
    binding !== null &&
    recognized.session_id === binding.session_id &&
    recognized.correlation_id === binding.correlation_id &&
    recognized.interaction_id === binding.interaction_id &&
    recognized.activation_id === binding.activation_id &&
    recognized.activation_generation === binding.activation_generation
  );
}

export function recognizedSpeechConfirmationAuthorityMatches(
  pending: RecognizedSpeechConfirmation,
  activeSessionId: string | null,
  displayedText: string,
  binding: Readonly<{
    session_id: string;
    correlation_id: string;
    interaction_id: string;
    activation_id: string;
    activation_generation: number;
  }> | null,
): boolean {
  return (
    activeSessionId !== null &&
    binding !== null &&
    pending.session_id === activeSessionId &&
    pending.text === displayedText &&
    pending.session_id === binding.session_id &&
    pending.correlation_id === binding.correlation_id &&
    pending.interaction_id === binding.interaction_id &&
    pending.activation_id === binding.activation_id &&
    pending.activation_generation === binding.activation_generation
  );
}


export type ProductP2NotificationDisposition =
  | NativeWorkStateNotification
  | { readonly kind: 'continue' }
  | {
      readonly kind: 'native_task_association';
      readonly session_id: string;
      readonly correlation_id: string;
      readonly interaction_id: string;
      readonly activation_id: string;
      readonly activation_generation: number;
      readonly task_id: string;
      readonly turn_commit_id: string;
      readonly provider_call_id: string;
    }
  | {
      readonly kind: 'failed';
      readonly reason: string;
      readonly response?: Readonly<{
        interaction_id: string;
        response_id: string;
        response_generation: number;
      }>;
    }
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
      readonly history_message_id: string | null;
      readonly task_notification_event_key?: string | null;
      readonly task_notification_text_sha256?: string | null;
      readonly ack: ProductPresentationAckInput;
      readonly replayed: boolean;
      readonly task_notification: boolean;
      readonly task_id: string | null;
      readonly task_notification_terminal: boolean;
      readonly adjustment_notification: boolean;
    }
  | {
      readonly kind: 'native_audio';
      readonly response_id: string;
      readonly response: Readonly<{
        interaction_id: string;
        response_id: string;
        response_generation: number;
      }>;
      readonly unit_id: string;
      readonly presentation_unit: Readonly<Record<string, unknown>>;
      readonly audio: Readonly<Record<string, unknown>>;
    }
  | {
      readonly kind: 'native_user_transcript';
      readonly session_id: string;
      readonly correlation_id: string;
      readonly interaction_id: string;
      readonly activation_id: string;
      readonly activation_generation: number;
      readonly message: Readonly<{
        id: string;
        role: 'user';
        content: string;
        timestamp: string;
        nativeTurnKey: string;
      }>;
      readonly following_assistant: readonly Readonly<{
        id: string;
        role: 'assistant';
        content: string;
        timestamp: string;
      }>[];
    }
  | {
      readonly kind: 'native_request_state';
      readonly response: Readonly<{ interaction_id: string; response_id: string; response_generation: number }> | null;
      readonly session_id: string; readonly correlation_id: string; readonly interaction_id: string;
      readonly activation_id: string; readonly activation_generation: number;
      readonly turn_id: string; readonly sequence: number;
      readonly phase: 'processing' | 'interrupted' | 'failed'; readonly reason: string | null;
    };

export type PendingForegroundPresentationFence = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
  response_id: string;
  response_generation: number;
  playout_owner: ProductP1VoiceRouteOwner | null;
  voice_loop_generation: number;
}>;

export type ProductP2NotificationAdmission = Readonly<{
  voice_loop_generation: number;
  foreground_presentation: PendingForegroundPresentationFence | null;
}>;

export type DeferredProductTaskPresentation = Readonly<{
  owner: ProductWebP2ActivationOwner;
  disposition: Extract<ProductP2NotificationDisposition, { readonly kind: 'presentation' }>;
}>;

export type CapturedProductTaskNotification = Readonly<{
  owner: ProductWebP2ActivationOwner;
  capture_owner: ProductP1VoiceRouteOwner | null;
  media_replay: {
    owner: ProductP1VoiceRouteOwner | null;
    operation: Promise<void> | null;
  };
  notification: Readonly<Record<string, unknown>>;
  disposition: Extract<ProductP2NotificationDisposition, { readonly kind: 'presentation' }>;
  admission: ProductP2NotificationAdmission;
  task_id: string;
  response_id: string;
  response_generation: number;
}>;

export type PendingProductPresentationAttempt = {
  native_foreground_epoch: number;
  owner: ProductWebP2ActivationOwner;
  input: ProductPresentationAckInput & { presented_at: string };
  response: Readonly<{
    interaction_id: string;
    response_id: string;
    response_generation: number;
  }>;
  playoutSettlement: Promise<void>;
  markPlayoutSettled: () => void;
  release_notification_capture?: () => void;
  task_notification: {
    task_id: string;
    disposition: Extract<ProductP2NotificationDisposition, { readonly kind: 'presentation' }>;
    terminal: boolean;
    retry_count: number;
    retry_pending: boolean;
  } | null;
  notification_repoll_before_capture?: boolean;
  failure_reason?: ProductTaskPresentationFailureReason;
  /** Local unplayed foreground retirement is never evidence for an ACK. */
  unplayed_foreground_retired?: boolean;
  /** Retry only this failed presentation's exact P1 close and fence retirement. */
  close_unplayed_foreground?: () => Promise<void>;
  settlement?: Promise<void>;
  /**
   * Set when playout yielded to a live speaker. The announcement is retained
   * exactly as delivered and replayed once that speaker settles; it is not a
   * playout failure and must not rebuild the P1 route.
   */
  deferred_to_speaker?: boolean;
};

export function foregroundPresentationFenceMatchesResponse(
  fence: PendingForegroundPresentationFence | null,
  binding: ProductWebP2ActivationSnapshot['binding'],
  response: Readonly<{
    interaction_id: string;
    response_id: string;
    response_generation: number;
  }> | null,
): boolean {
  // Presentation authority never crosses an activation generation. Exit
  // invalidates an unpresented predecessor response; a successor must capture
  // and present only output produced by its own exact P2 binding.
  return (
    fence !== null &&
    binding !== null &&
    response !== null &&
    fence.session_id === binding.session_id &&
    fence.correlation_id === binding.correlation_id &&
    fence.interaction_id === binding.interaction_id &&
    fence.activation_id === binding.activation_id &&
    fence.activation_generation === binding.activation_generation &&
    fence.interaction_id === response.interaction_id &&
    fence.response_id === response.response_id &&
    fence.response_generation === response.response_generation
  );
}


export type TerminalAnnouncementState = 'idle' | 'queued' | 'suspending_capture' | 'fetching' | 'playing' | 'acking' | 'recovering';


export function productP2TaskNotificationCheckRequired(
  input: Readonly<{
    deferred_presentation: boolean;
    task_id: string | null;
    origin_kind: 'text' | 'voice' | null;
    terminal_task_id: string | null;
    announcement_task_id: string | null;
    announcement_state: TerminalAnnouncementState;
  }>,
): boolean {
  // A Task query refresh may temporarily withdraw the created route while the
  // pop-on-read P2 owner still owes running/terminal notifications.  The
  // retained announcement owner remains the receive authority until it settles.
  return Boolean(
    input.deferred_presentation ||
      (input.task_id !== null &&
        input.origin_kind === 'voice' &&
        input.terminal_task_id !== input.task_id) ||
      (input.announcement_task_id !== null && input.announcement_state !== 'idle'),
  );
}


export function terminalAnnouncementArbitrationAction(
  input: Readonly<{
    queued: boolean;
    voice_active: boolean;
    connected: boolean;
    page_visible: boolean;
    foreground_active: boolean;
    speech_active: boolean;
    p1_status: ProductP1VoiceStatus | null;
  }>,
): 'defer' | 'recover_owner' | 'suspend_capture' | 'fetch' {
  if (!input.queued || !input.voice_active || !input.connected || !input.page_visible || input.foreground_active) return 'defer';
  if (input.p1_status === null || ['failed', 'cleanup_pending', 'closed'].includes(input.p1_status)) return 'recover_owner';
  if (input.p1_status === 'capturing') return input.speech_active ? 'defer' : 'suspend_capture';
  if (['idle', 'recognized'].includes(input.p1_status)) return 'fetch';
  return 'defer';
}


export function productP2NotificationTransportBlockedByP1(
  input: Readonly<{
    p1_status: ProductP1VoiceStatus;
    terminal_notification_check_required: boolean;
  }>,
): boolean {
  if (productP2TaskNotificationRequiresCaptureArbitration(input)) return false;
  return ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(input.p1_status);
}


export function productP2TaskNotificationRequiresCaptureArbitration(
  input: Readonly<{
    p1_status: ProductP1VoiceStatus;
    terminal_notification_check_required: boolean;
  }>,
): boolean {
  return input.terminal_notification_check_required && ['starting', 'capturing'].includes(input.p1_status);
}


export function capturedTaskNotificationDeadlineAction(
  input: Readonly<{
    capture_settlement_requested: boolean;
    p1_status: ProductP1VoiceStatus | null;
    announcement_state: TerminalAnnouncementState;
    capture_binding_available: boolean;
    foreground_pending?: boolean;
  }>,
): 'settle_capture' | 'fallback_text' {
  return !input.foreground_pending && !input.capture_settlement_requested &&
    input.p1_status === 'capturing' &&
    input.announcement_state === 'queued' &&
    input.capture_binding_available
    ? 'settle_capture'
    : 'fallback_text';
}


export function capturedTaskNotificationRequiresAnnouncementRequeue(
  announcementState: TerminalAnnouncementState,
): boolean {
  return announcementState === 'fetching';
}


export function terminalTextFallbackCompletesVoiceAnnouncement(
  event: Readonly<ProductTextProgressEvent>,
  currentTaskId: string | null,
): boolean {
  return (
    currentTaskId !== null &&
    event.task_id === currentTaskId &&
    event.state === 'terminal' &&
    event.origin_kind === 'voice' &&
    event.requested_origin_kind === 'voice' &&
    event.delivery_mode === 'text_fallback' &&
    event.consumption_mode === 'presentation' &&
    event.presentation_class === 'text'
  );
}


export function terminalTextFallbackNotificationText(
  event: Readonly<ProductTextProgressEvent>,
  currentTaskId: string | null,
  chinese = false,
  taskName: string | null = null,
): string | null {
  if (!terminalTextFallbackCompletesVoiceAnnouncement(event, currentTaskId)) return null;
  // This is a display projection of the reconciled canonical terminal event,
  // not a new result or a client-authored P2 response/history record.
  const subject = taskName === null ? (chinese ? '后台任务' : 'The background task')
    : chinese ? `“${taskName}”` : `Task "${taskName}"`;
  if (chinese) {
    switch (event.source_event.payload.outcome) {
      case 'completed': return `${subject}已完成，结果已经生成。`;
      case 'cancelled': return `${subject}已取消。`;
      case 'failed': return `${subject}失败了。`;
      case 'interrupted': return `${subject}已中断。`;
      case 'unknown': return `${subject}已经结束，结果状态未知。`;
      default: return null;
    }
  }
  switch (event.source_event.payload.outcome) {
    case 'completed': return `${subject} is complete and its result is ready.`;
    case 'cancelled': return `${subject} was cancelled.`;
    case 'failed': return `${subject} failed.`;
    case 'interrupted': return `${subject} was interrupted.`;
    case 'unknown': return `${subject} ended with an unknown outcome.`;
    default: return null;
  }
}


export async function terminalTextFallbackMessage(
  event: Readonly<ProductTextProgressEvent>,
  currentTaskId: string | null,
  chinese = false,
  taskName: string | null = null,
): Promise<ProductLiveVoiceMessageEvent | null> {
  const text = terminalTextFallbackNotificationText(event, currentTaskId, chinese, taskName);
  const response = event.response_ref;
  if (text === null || response === null) return null;
  const digest = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
  const hash = Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
  return Object.freeze({
    session_id: event.session_id,
    message: Object.freeze({
      // Match SessionFormalHistoryWriter's existing TEXT record identity. The
      // exact P3 ACK persists this same cursor-0/unit-0 sentence on the server.
      id: `live-voice:${response.interaction_id}:${response.response_id}:${response.response_generation}:text:0:0:${hash}`,
      role: 'assistant',
      content: text,
      timestamp: new Date().toISOString(),
      ...(() => { const eventKey = taskNotificationSourceKey(event.source_event.raw, event.session_id);
        return eventKey ? { taskNotification: { eventKey, presentation: 'text' as const } } : {}; })(),
    }),
  });
}


export function productP2NotificationRepollDelayMs(
  input: Readonly<{
    disposition: ProductP2NotificationDisposition;
    terminal_notification_check_required: boolean;
    foreground_response_waiting: boolean;
    notification?: Readonly<Record<string, unknown>>;
  }>,
): number {
  const event = input.notification ? recordValue(input.notification.agent_event) : null;
  const streamObserver = event?.event_type === 'chat.delta' || event?.event_type === 'chat.reasoning';
  if (
    input.disposition.kind !== 'continue' ||
    streamObserver ||
    input.notification?.kind !== 'transport.keepalive' ||
    !input.terminal_notification_check_required ||
    !input.foreground_response_waiting
  )
    return 0;
  return PRODUCT_P2_NOTIFICATION_PENDING_BACKOFF_MS;
}


export function productP3ProgressReconciliationRetryDelayMs(failures: number): number | null {
  if (!Number.isSafeInteger(failures) || failures <= 0 || failures >= PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS) return null;
  return Math.min(PRODUCT_P3_PROGRESS_RECONCILIATION_RETRY_MS * 2 ** (failures - 1), 2_000);
}


export function rememberProductP3ProgressExhaustion(exhausted: Map<string, true>, deliveryId: string): void {
  if (exhausted.has(deliveryId)) return;
  while (exhausted.size >= PRODUCT_P3_PROGRESS_EXHAUSTED_CAPACITY) {
    const oldest = exhausted.keys().next().value;
    if (typeof oldest !== 'string') break;
    exhausted.delete(oldest);
  }
  exhausted.set(deliveryId, true);
}

export function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function hasExactFields(value: Readonly<Record<string, unknown>>, fields: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  return actual.length === expected.length && actual.every((field, index) => field === expected[index]);
}

export const PRODUCT_P3_RETRY_INSPECTION_FAILED_REASON = 'PRODUCT_P3_RETRY_INSPECTION_FAILED';

export const PRODUCT_P3_STABLE_REASON_PATTERN = /^[A-Z][A-Z0-9_]{0,127}$/;


export type ProductP3RetryAdmission = Readonly<{
  eligible: boolean;
  reason: string;
  task_id: string;
  attempt_id: string | null;
  attempt_number: number | null;
}>;


export type ProductP3RetryInspection = Readonly<{
  record: Readonly<FormalTaskControlRecord>;
  admission: ProductP3RetryAdmission;
}>;


export function parseProductP3RetryAdmission(response: unknown, record: Readonly<FormalTaskControlRecord>): ProductP3RetryAdmission {
  const envelope = recordValue(response);
  const result = recordValue(envelope?.result);
  const raw = recordValue(result?.retry_admission);
  if (
    envelope?.ok !== true ||
    raw === null ||
    Object.keys(raw).sort().join(',') !== 'attempt_id,attempt_number,eligible,reason,task_id' ||
    typeof raw.eligible !== 'boolean' ||
    typeof raw.reason !== 'string' ||
    !PRODUCT_P3_STABLE_REASON_PATTERN.test(raw.reason) ||
    raw.task_id !== record.task_id
  ) {
    throw new Error('formal task retry admission is missing or malformed');
  }
  if (raw.eligible) {
    if (
      raw.reason !== 'TASK_RETRY_ELIGIBLE' ||
      typeof raw.attempt_id !== 'string' ||
      raw.attempt_id !== record.attempt_id ||
      !Number.isSafeInteger(raw.attempt_number) ||
      raw.attempt_number !== (record.attempt_number ?? -1) + 1 ||
      !isFormalTaskRetryEligible(record)
    ) {
      throw new Error('formal task retry admission does not bind the exact current attempt');
    }
  } else if (raw.attempt_id !== null || raw.attempt_number !== null) {
    throw new Error('formal task retry rejection carries ambiguous attempt authority');
  }
  return Object.freeze({
    eligible: raw.eligible,
    reason: raw.reason,
    task_id: raw.task_id as string,
    attempt_id: raw.attempt_id as string | null,
    attempt_number: raw.attempt_number as number | null,
  });
}


export function productP3RetryInspectionFailureReason(error: unknown): string {
  const reason = extractWebErrorReason(error);
  return reason && PRODUCT_P3_STABLE_REASON_PATTERN.test(reason) ? reason : PRODUCT_P3_RETRY_INSPECTION_FAILED_REASON;
}


export type ProductP3TerminalStatus = 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown';


export type ProductP3MutationStatus = 'idle' | 'issuing' | 'confirmed' | 'mutating' | 'accepted' | ProductP3TerminalStatus;

export const PRODUCT_P3_TERMINAL_STATUSES = Object.freeze(['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const);

export const PRODUCT_P3_PROGRESS_EVENT_TYPES: Readonly<Record<FormalTaskState, readonly string[]>> = Object.freeze({
  accepted: Object.freeze(['task.accepted', 'task.retry_accepted']),
  running: Object.freeze(['task.running']),
  blocked: Object.freeze(['task.blocked']),
  decision_required: Object.freeze(['task.decision_required']),
  terminal: Object.freeze(['task.terminal']),
});

export function productP3ProgressState(value: unknown): FormalTaskState {
  if (!(['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const).includes(value as FormalTaskState)) {
    throw new Error('product P3 progress state is outside the formal lifecycle');
  }
  return value as FormalTaskState;
}

export function productP3ProgressOutcome(value: unknown): ProductP3TerminalStatus | null {
  if (value === null || value === undefined) return null;
  if (!PRODUCT_P3_TERMINAL_STATUSES.includes(value as ProductP3TerminalStatus)) {
    throw new Error('product P3 progress outcome is outside the formal lifecycle');
  }
  return value as ProductP3TerminalStatus;
}


export function productP3TerminalStatus(record: Readonly<FormalTaskControlRecord>): ProductP3TerminalStatus | null {
  if (record.state !== 'terminal') return null;
  return productP3ProgressOutcome(record.outcome);
}

export const PRODUCT_P3_PROGRESS_QUARANTINABLE_FAILURES = new Set([
  'formal product progress does not own the exact Session/task/attempt binding',
  'product P3 progress state is outside the formal lifecycle',
  'product P3 progress outcome is outside the formal lifecycle',
  'formal product progress source, state, outcome, or producer mismatch',
  'formal product progress task.events response is malformed',
  'formal product progress conflicts with authoritative task.events truth',
  'formal product progress conflicts with authoritative task.events head',
  'formal product progress lost its exact authoritative revision',
]);


export function productP3ProgressFailureIsQuarantinable(error: unknown): boolean {
  return error instanceof Error && PRODUCT_P3_PROGRESS_QUARANTINABLE_FAILURES.has(error.message);
}


/**
 * Rebuild the exact origin task from durable task.events before acknowledging
 * or displaying a product progress delivery.  The isolated probe prevents a
 * malformed response from partially updating the live replica.  Session,
 * connection, task, and attempt ownership are rechecked after the network
 * boundary so a predecessor or late response cannot update the current UI.
 */
export async function reconcileProductP3ProgressEvent(
  input: Readonly<{
    request: ProductWebRequest;
    leaf: FormalTaskControlLeaf;
    event: Readonly<ProductTextProgressEvent>;
    session_id: string;
    request_nonce: string;
    is_current: () => boolean;
    before_adopt?: (record: Readonly<FormalTaskControlRecord>) => void;
  }>,
): Promise<Readonly<FormalTaskControlRecord>> {
  const { event } = input;
  if (!input.session_id || !input.request_nonce || !input.is_current()) {
    throw new Error('formal product progress reconciliation is stale or incomplete');
  }
  const initialSnapshot = input.leaf.snapshot();
  const initialRecord = initialSnapshot.tasks.find(task => task.task_id === event.task_id) ?? null;
  if (
    !initialSnapshot.connected ||
    initialSnapshot.binding.session_id !== input.session_id ||
    event.session_id !== input.session_id ||
    event.project_id !== initialSnapshot.binding.project_id ||
    event.correlation_id !== initialSnapshot.binding.correlation_id ||
    initialRecord === null ||
    initialRecord.attempt_id !== event.attempt_id
  ) {
    throw new Error('formal product progress does not own the exact Session/task/attempt binding');
  }

  const state = productP3ProgressState(event.state);
  const sourceState = productP3ProgressState(event.source_event.payload.state);
  const progressState = productP3ProgressState(event.progress_event.payload.state);
  const sourceOutcome = productP3ProgressOutcome(event.source_event.payload.outcome);
  const progressOutcome = productP3ProgressOutcome(event.progress_event.payload.outcome);
  const expectedEventTypes = PRODUCT_P3_PROGRESS_EVENT_TYPES[state];
  const sourceExtensions = recordValue(event.source_event.raw.extensions);
  const progressReturn = recordValue(sourceExtensions?.['jiuwenswarm.task_progress_return']);
  const persistentProducer = progressReturn?.persistent_event_producer;
  const producerMatches =
    state === 'terminal'
      ? ['task_core', 'task_core.delivery', 'task_core.reconciliation'].includes(String(persistentProducer))
      : persistentProducer === 'task_core';
  if (
    state !== sourceState ||
    state !== progressState ||
    !expectedEventTypes.includes(event.source_event.event_type) ||
    !producerMatches ||
    sourceOutcome !== progressOutcome ||
    (state === 'terminal') !== (progressOutcome !== null)
  ) {
    throw new Error('formal product progress source, state, outcome, or producer mismatch');
  }

  const ownedConnectionGeneration = initialSnapshot.connection_generation;
  const expectedAttemptId = event.attempt_id;
  const stillCurrent = () => {
    if (!input.is_current()) return false;
    const snapshot = input.leaf.snapshot();
    const record = snapshot.tasks.find(task => task.task_id === event.task_id) ?? null;
    return (
      snapshot.connected &&
      snapshot.connection_generation === ownedConnectionGeneration &&
      snapshot.binding.session_id === input.session_id &&
      record?.attempt_id === expectedAttemptId
    );
  };
  const eventsResponse = await input.request(
    PRODUCT_P3_TASK_EVENTS_METHOD,
    { session_id: input.session_id, task_id: event.task_id, after_seq: -1 },
    { requestId: `web-task-progress-events-${input.request_nonce}` },
  );
  if (!stillCurrent()) throw new Error('formal product progress reconciliation became stale');

  const responseBody = recordValue(eventsResponse);
  const responseResult = recordValue(responseBody?.result);
  const responseEvents = Array.isArray(responseResult?.events) ? responseResult.events : null;
  if (responseBody === null || responseResult === null || responseEvents === null) {
    throw new Error('formal product progress task.events response is malformed');
  }
  const evidenceEvents = responseEvents.filter(candidate => {
    const raw = recordValue(candidate);
    return typeof raw?.seq === 'number' && Number.isSafeInteger(raw.seq) && raw.seq <= event.source_event.seq;
  });
  const evidenceResponse = Object.freeze({
    ...responseBody,
    result: Object.freeze({
      ...responseResult,
      head_seq: event.source_event.seq,
      events: Object.freeze(evidenceEvents),
    }),
  });
  const evidenceProbe = new FormalTaskControlLeaf({ enabled: true, binding: initialSnapshot.binding });
  evidenceProbe.adopt('task.events', evidenceResponse, {
    connection_generation: evidenceProbe.snapshot().connection_generation,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: event.task_id, after_seq: -1 },
  });
  const evidence = evidenceProbe.snapshot().tasks.find(task => task.task_id === event.task_id) ?? null;
  if (
    evidence === null ||
    evidence.attempt_id !== expectedAttemptId ||
    evidence.last_event_id !== event.source_event.event_id ||
    evidence.last_event_seq !== event.source_event.seq ||
    evidence.state !== state ||
    evidence.outcome !== progressOutcome
  ) {
    throw new Error('formal product progress conflicts with authoritative task.events truth');
  }

  const headProbe = new FormalTaskControlLeaf({ enabled: true, binding: initialSnapshot.binding });
  headProbe.adopt('task.events', eventsResponse, {
    connection_generation: headProbe.snapshot().connection_generation,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: event.task_id, after_seq: -1 },
  });
  const selected = headProbe.snapshot().tasks.find(task => task.task_id === event.task_id) ?? null;
  const selectedLastEventSeq = selected?.last_event_seq ?? null;
  if (
    selected === null ||
    selected.attempt_id !== expectedAttemptId ||
    selectedLastEventSeq === null ||
    selectedLastEventSeq < event.source_event.seq
  ) {
    throw new Error('formal product progress conflicts with authoritative task.events head');
  }
  if (!stillCurrent()) throw new Error('formal product progress reconciliation became stale');
  input.before_adopt?.(selected);
  if (!stillCurrent()) throw new Error('formal product progress reconciliation became stale');

  input.leaf.adopt('task.events', eventsResponse, {
    connection_generation: ownedConnectionGeneration,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: event.task_id, after_seq: -1 },
  });
  if (selectedLastEventSeq === event.source_event.seq) {
    input.leaf.adoptProgress(
      {
        task_id: event.task_id,
        correlation_id: event.correlation_id,
        source_event_id: event.source_event.event_id,
        source_event_seq: event.source_event.seq,
        progress_event_id: event.progress_event.event_id,
        progress_causation_id: event.progress_event.causation_id ?? '',
        state,
        outcome: progressOutcome,
      },
      ownedConnectionGeneration,
    );
  }
  const adopted = input.leaf.snapshot().tasks.find(task => task.task_id === event.task_id) ?? null;
  if (
    !stillCurrent() ||
    adopted === null ||
    adopted.attempt_id !== selected.attempt_id ||
    adopted.last_event_id !== selected.last_event_id ||
    adopted.last_event_seq !== selected.last_event_seq ||
    adopted.state !== selected.state ||
    adopted.outcome !== selected.outcome
  ) {
    throw new Error('formal product progress lost its exact authoritative revision');
  }
  return adopted;
}


export function bindProductVoiceTaskOrigin(
  input: Readonly<ProductTurnInput>,
  result: unknown,
  sessionId: string,
  interactionId: string,
  correlationId = 'legacy-product-voice-origin',
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
    correlation_id: correlationId,
    interaction_id: interactionId,
    turn_id: input.turn_id,
    commit_id: input.commit_id,
    response_id: response.response_id,
    response_generation: response.response_generation as number,
    instruction: input.text,
  });
}


export function classifyProductP2Notification(notification: Readonly<Record<string, unknown>>, hasPresentedOutput = false): ProductP2NotificationDisposition {
  if (notification.kind === 'native.work_state') {
    try { return parseNativeWorkStateNotification(notification); }
    catch { return { kind: 'continue' }; }
  }
  const event = recordValue(notification.agent_event);
  const unit = recordValue(notification.presentation_unit);
  const response = recordValue(notification.response);
  const taskNotification = event?.source_provenance === 'server.task_notification';
  let taskTerminal = false;
  let notificationTaskId: string | null = null;
  if (taskNotification && notification.source_event != null) {
    try {
      const source = parseEventEnvelope(notification.source_event);
      if (source.stream_ref.kind !== 'task' || source.scope.assurance !== 'authenticated' ||
          source.scope.session_id !== notification.session_id || source.scope.project_id === null) throw new Error('Task source binding mismatch');
      taskTerminal = source.payload.state === 'terminal';
      notificationTaskId = source.stream_ref.id;
    } catch {
      return { kind: 'failed', reason: 'PRODUCT_TASK_NOTIFICATION_SOURCE_INVALID' };
    }
  }
  const presentationSurface = unit?.surface === 'text' || (unit?.surface === 'audio' && taskNotification) ? unit.surface : null;
  const errorReason =
    typeof notification.error_reason === 'string' ? notification.error_reason : typeof event?.error_reason === 'string' ? event.error_reason : null;
  const responseBinding =
    typeof response?.interaction_id === 'string' &&
    typeof response.response_id === 'string' &&
    Number.isSafeInteger(response.response_generation)
      ? Object.freeze({
          interaction_id: response.interaction_id,
          response_id: response.response_id,
          response_generation: response.response_generation as number,
        })
      : null;
  if (notification.kind === 'native.request_state') {
    const state = recordValue(notification.request_state);
    const validId = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 256 && value.trim() === value && !/[\u0000-\u001f\u007f]/u.test(value);
    if (!hasExactFields(notification, ['status', 'kind', 'request_id', 'round_id', 'response', 'request_state',
      'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq',
      'session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect']) ||
      notification.status !== 'notification' || notification.sequence_effect !== 'neutral' ||
      !validId(notification.request_id) || !validId(notification.session_id) || !validId(notification.correlation_id) ||
      !validId(notification.interaction_id) || !validId(notification.activation_id) ||
      !Number.isSafeInteger(notification.activation_generation) || (notification.activation_generation as number) <= 0 ||
      state === null || !hasExactFields(state, ['turn_id', 'sequence', 'phase', 'reason']) || !validId(state.turn_id) ||
      !Number.isSafeInteger(state.sequence) || (state.sequence as number) <= 0 ||
      !['processing', 'interrupted', 'failed'].includes(String(state.phase)) ||
      (state.phase === 'failed' ? typeof state.reason !== 'string' || !/^[A-Z][A-Z0-9_]{1,119}$/u.test(state.reason) : state.reason !== null) ||
      (state.phase === 'interrupted' ? (response === null || !hasExactFields(response, ['interaction_id', 'response_id', 'response_generation']) ||
        responseBinding === null || responseBinding.interaction_id !== notification.interaction_id || !validId(responseBinding.response_id) || responseBinding.response_generation < 1) : notification.response !== null) ||
      ['round_id', 'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq'].some(key => notification[key] !== null)) {
      return { kind: 'failed', reason: 'PRODUCT_NATIVE_REQUEST_STATE_INVALID' };
    }
    return { kind: 'native_request_state', response: responseBinding, session_id: notification.session_id, correlation_id: notification.correlation_id,
      interaction_id: notification.interaction_id, activation_id: notification.activation_id,
      activation_generation: notification.activation_generation as number, turn_id: state.turn_id,
      sequence: state.sequence as number, phase: state.phase as 'processing' | 'interrupted' | 'failed', reason: state.reason as string | null };
  }
  if (notification.kind === 'native.task_association') {
    const association = recordValue(notification.task_association);
    const validId = (value: unknown): value is string => typeof value === 'string' && value.trim() === value && value.length > 0 &&
      new TextEncoder().encode(value).length <= 256 && !/[\u0000-\u001f\u007f]/u.test(value);
    if (
      !hasExactFields(notification, ['status', 'kind', 'request_id', 'round_id', 'response', 'task_association',
        'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq',
        'session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect']) ||
      notification.status !== 'notification' || notification.sequence_effect !== 'neutral' ||
      !validId(notification.request_id) || !validId(notification.session_id) || !validId(notification.correlation_id) ||
      !validId(notification.interaction_id) || !validId(notification.activation_id) ||
      !Number.isSafeInteger(notification.activation_generation) || (notification.activation_generation as number) <= 0 ||
      response === null || !hasExactFields(response, ['interaction_id', 'response_id', 'response_generation']) ||
      responseBinding === null || responseBinding.interaction_id !== notification.interaction_id ||
      !validId(responseBinding.response_id) || responseBinding.response_generation < 0 ||
      association === null || !hasExactFields(association, ['task_id', 'turn_commit_id', 'provider_call_id']) ||
      !validId(association.task_id) || !validId(association.turn_commit_id) || !validId(association.provider_call_id) ||
      ['round_id', 'agent_event', 'source_event', 'progress_event', 'presentation_unit', 'audio', 'error_reason', 'publish_seq']
        .some(field => notification[field] !== null)
    ) return { kind: 'failed', reason: 'PRODUCT_NATIVE_TASK_ASSOCIATION_INVALID' };
    return Object.freeze({ kind: 'native_task_association', session_id: notification.session_id,
      correlation_id: notification.correlation_id, interaction_id: notification.interaction_id,
      activation_id: notification.activation_id, activation_generation: notification.activation_generation as number,
      task_id: association.task_id, turn_commit_id: association.turn_commit_id, provider_call_id: association.provider_call_id });
  }
  if (notification.kind === 'native.user_transcript') {
    const message = recordValue(event?.message);
    const binding = recordValue(event?.binding);
    const scope = recordValue(binding?.scope);
    const timestamp = message?.timestamp;
    const followingAssistant = event?.following_assistant;
    const timestampDate =
      typeof timestamp === 'number' && Number.isFinite(timestamp) && timestamp >= 0
        ? new Date(timestamp * 1_000)
        : null;
    const valid =
      hasExactFields(notification, [
        'status', 'kind', 'request_id', 'round_id', 'response', 'agent_event',
        'source_event', 'progress_event', 'presentation_unit', 'audio',
        'error_reason', 'publish_seq', 'session_id', 'correlation_id',
        'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect',
      ]) &&
      notification.status === 'notification' &&
      notification.sequence_effect === 'neutral' &&
      typeof notification.request_id === 'string' && notification.request_id.trim().length > 0 &&
      notification.round_id === null &&
      notification.response === null &&
      notification.source_event === null &&
      notification.progress_event === null &&
      notification.presentation_unit === null &&
      notification.audio === null &&
      notification.error_reason === null &&
      notification.publish_seq === null &&
      typeof notification.session_id === 'string' && notification.session_id.trim().length > 0 &&
      typeof notification.correlation_id === 'string' && notification.correlation_id.trim().length > 0 &&
      typeof notification.interaction_id === 'string' && notification.interaction_id.trim().length > 0 &&
      typeof notification.activation_id === 'string' && notification.activation_id.trim().length > 0 &&
      Number.isSafeInteger(notification.activation_generation) &&
      (notification.activation_generation as number) > 0 &&
      event !== null &&
      (hasExactFields(event, ['event_type', 'message', 'binding']) ||
        hasExactFields(event, ['event_type', 'message', 'binding', 'following_assistant'])) &&
      event.event_type === 'chat.final' &&
      message !== null &&
      hasExactFields(message, ['id', 'role', 'content', 'timestamp']) &&
      typeof message.id === 'string' && message.id.trim().length > 0 &&
      message.role === 'user' &&
      typeof message.content === 'string' &&
      message.content.trim().length > 0 &&
      message.content === message.content.trim() &&
      timestampDate !== null &&
      Number.isFinite(timestampDate.getTime()) &&
      binding !== null &&
      hasExactFields(binding, [
        'scope', 'interaction_id', 'activation_id', 'activation_generation',
        'correlation_id', 'turn_id', 'commit_id', 'provider_session_id',
        'provider_item_id', 'provider_event_id',
      ]) &&
      scope !== null &&
      hasExactFields(scope, ['subject_id', 'project_id', 'session_id', 'assurance']) &&
      typeof scope.subject_id === 'string' && scope.subject_id.trim().length > 0 &&
      (scope.project_id === null || (typeof scope.project_id === 'string' && scope.project_id.trim().length > 0)) &&
      scope.session_id === notification.session_id &&
      (scope.assurance === 'request_asserted' || scope.assurance === 'authenticated') &&
      binding.interaction_id === notification.interaction_id &&
      binding.activation_id === notification.activation_id &&
      binding.activation_generation === notification.activation_generation &&
      binding.correlation_id === notification.correlation_id &&
      typeof binding.turn_id === 'string' && binding.turn_id.trim().length > 0 &&
      typeof binding.commit_id === 'string' && binding.commit_id.trim().length > 0 &&
      typeof binding.provider_session_id === 'string' && binding.provider_session_id.trim().length > 0 &&
      typeof binding.provider_item_id === 'string' && binding.provider_item_id.trim().length > 0 &&
      typeof binding.provider_event_id === 'string' && binding.provider_event_id.trim().length > 0 &&
      message.id === `live-voice:${binding.commit_id}:native-user` &&
      (followingAssistant === undefined || (Array.isArray(followingAssistant) && followingAssistant.length > 0));
    if (!valid) {
      return { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' };
    }
    const parsedFollowing: Array<Readonly<{
      id: string;
      role: 'assistant';
      content: string;
      timestamp: string;
    }>> = [];
    for (const candidate of (followingAssistant ?? []) as unknown[]) {
      const projection = recordValue(candidate);
      const assistantMessage = recordValue(projection?.message);
      const assistantBinding = recordValue(projection?.binding);
      const assistantResponse = recordValue(assistantBinding?.response);
      const assistantTimestamp = assistantMessage?.timestamp;
      const assistantTimestampDate =
        typeof assistantTimestamp === 'number' && Number.isFinite(assistantTimestamp) && assistantTimestamp >= 0
          ? new Date(assistantTimestamp * 1_000)
          : null;
      if (
        projection === null ||
        !hasExactFields(projection, ['message', 'binding']) ||
        assistantMessage === null ||
        !hasExactFields(assistantMessage, ['id', 'role', 'content', 'timestamp']) ||
        typeof assistantMessage.id !== 'string' || !assistantMessage.id.trim() ||
        assistantMessage.role !== 'assistant' ||
        typeof assistantMessage.content !== 'string' || !assistantMessage.content.trim() ||
        assistantMessage.content !== assistantMessage.content.trim() ||
        assistantTimestampDate === null || !Number.isFinite(assistantTimestampDate.getTime()) ||
        assistantBinding === null ||
        !hasExactFields(assistantBinding, ['turn_id', 'response', 'surface', 'presented_at']) ||
        assistantBinding.turn_id !== binding.turn_id ||
        assistantBinding.surface !== 'native_audio' ||
        typeof assistantBinding.presented_at !== 'string' ||
        !assistantBinding.presented_at.trim() ||
        !Number.isFinite(Date.parse(assistantBinding.presented_at)) ||
        assistantResponse === null ||
        !hasExactFields(assistantResponse, ['interaction_id', 'response_id', 'response_generation']) ||
        assistantResponse.interaction_id !== notification.interaction_id ||
        typeof assistantResponse.response_id !== 'string' || !assistantResponse.response_id.trim() ||
        !Number.isSafeInteger(assistantResponse.response_generation) ||
        (assistantResponse.response_generation as number) <= 0
      ) {
        return { kind: 'failed', reason: 'PRODUCT_NATIVE_USER_TRANSCRIPT_NOTIFICATION_INVALID' };
      }
      parsedFollowing.push(Object.freeze({
        id: assistantMessage.id,
        role: 'assistant',
        content: assistantMessage.content,
        timestamp: assistantTimestampDate.toISOString(),
      }));
    }
    return {
      kind: 'native_user_transcript',
      session_id: notification.session_id as string,
      correlation_id: notification.correlation_id as string,
      interaction_id: notification.interaction_id as string,
      activation_id: notification.activation_id as string,
      activation_generation: notification.activation_generation as number,
      message: Object.freeze({
        id: message.id as string,
        role: 'user',
        content: message.content as string,
        timestamp: timestampDate!.toISOString(),
        nativeTurnKey: JSON.stringify([notification.interaction_id, binding!.turn_id]),
      }),
      following_assistant: Object.freeze(parsedFollowing),
    };
  }
  if (notification.kind === 'native.audio') {
    const unitResponse = recordValue(unit?.response);
    const audio = recordValue(notification.audio);
    const valid =
      hasExactFields(notification, [
        'status', 'kind', 'request_id', 'round_id', 'response', 'agent_event',
        'source_event', 'progress_event', 'presentation_unit', 'audio',
        'error_reason', 'publish_seq', 'session_id', 'correlation_id',
        'interaction_id', 'activation_id', 'activation_generation', 'sequence_effect',
      ]) &&
      notification.status === 'notification' &&
      notification.sequence_effect === 'neutral' &&
      typeof notification.request_id === 'string' && notification.request_id.trim().length > 0 &&
      notification.round_id === null &&
      notification.agent_event === null &&
      notification.source_event === null &&
      notification.progress_event === null &&
      notification.error_reason === null &&
      notification.publish_seq === null &&
      typeof notification.session_id === 'string' && notification.session_id.trim().length > 0 &&
      typeof notification.correlation_id === 'string' && notification.correlation_id.trim().length > 0 &&
      typeof notification.interaction_id === 'string' &&
      typeof notification.activation_id === 'string' && notification.activation_id.trim().length > 0 &&
      Number.isSafeInteger(notification.activation_generation) &&
      (notification.activation_generation as number) > 0 &&
      responseBinding !== null &&
      responseBinding.interaction_id === notification.interaction_id &&
      responseBinding.response_generation > 0 &&
      unit !== null &&
      hasExactFields(unit, [
        'response', 'surface', 'unit_id', 'seq', 'source_start_utf8',
        'source_end_utf8', 'content_ref',
      ]) &&
      unitResponse !== null &&
      hasExactFields(unitResponse, ['interaction_id', 'response_id', 'response_generation']) &&
      unitResponse.interaction_id === responseBinding.interaction_id &&
      unitResponse.response_id === responseBinding.response_id &&
      unitResponse.response_generation === responseBinding.response_generation &&
      unit.surface === 'audio' &&
      typeof unit.unit_id === 'string' && unit.unit_id.trim().length > 0 &&
      Number.isSafeInteger(unit.seq) && (unit.seq as number) >= 0 &&
      Number.isSafeInteger(unit.source_start_utf8) && (unit.source_start_utf8 as number) >= 0 &&
      Number.isSafeInteger(unit.source_end_utf8) &&
      (unit.source_end_utf8 as number) >= (unit.source_start_utf8 as number) &&
      typeof unit.content_ref === 'string' && /^sha256:[0-9a-f]{64}$/.test(unit.content_ref) &&
      audio !== null;
    if (!valid) {
      return responseBinding === null
        ? { kind: 'failed', reason: 'PRODUCT_NATIVE_AUDIO_NOTIFICATION_INVALID' }
        : { kind: 'failed', reason: 'PRODUCT_NATIVE_AUDIO_NOTIFICATION_INVALID', response: responseBinding };
    }
    return {
      kind: 'native_audio',
      response_id: responseBinding.response_id,
      response: responseBinding,
      unit_id: unit.unit_id as string,
      presentation_unit: Object.freeze({ ...unit, response: Object.freeze({ ...unitResponse }) }),
      // This object is the one-use handoff into P1. P1 must remove the private
      // media ticket immediately after creating its ticket consumer, so freezing
      // the handoff here makes an otherwise valid Gateway descriptor unusable.
      audio: { ...audio },
    };
  }
  if (
    notification.kind === 'agent.error' ||
    errorReason !== null ||
    (typeof event?.event_type === 'string' && /(?:error|failed|blocked)$/.test(event.event_type))
  ) {
    const reason = errorReason ?? 'PRODUCT_AGENT_OUTPUT_FAILED';
    return responseBinding === null ? { kind: 'failed', reason } : { kind: 'failed', reason, response: responseBinding };
  }
  if (
    notification.kind === 'agent.output' &&
    typeof event?.text === 'string' &&
    presentationSurface !== null &&
    unit !== null &&
    typeof unit.unit_id === 'string' &&
    Number.isSafeInteger(unit.seq) &&
    typeof response?.interaction_id === 'string' &&
    typeof response?.response_id === 'string' &&
    Number.isSafeInteger(response.response_generation)
  ) {
    const contentRef = typeof unit.content_ref === 'string' ? unit.content_ref : '';
    const contentDigest = /^sha256:([0-9a-f]{64})$/.exec(contentRef)?.[1] ?? null;
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
      history_message_id:
        contentDigest === null
          ? null
          : `live-voice:${response.interaction_id}:${response.response_id}:${response.response_generation}:${presentationSurface}:${unit.seq}:${unit.seq}:${contentDigest}`,
      replayed: hasPresentedOutput,
      task_notification_event_key: taskNotification ? taskNotificationSourceKey(notification.source_event, String(notification.session_id)) : null,
      task_notification_text_sha256: taskNotification ? contentDigest : null,
      task_notification: taskNotification,
      task_id: notificationTaskId,
      task_notification_terminal: taskTerminal,
      adjustment_notification: event.source_provenance === 'server.background.adjustment',
      ack: {
        response_id: response.response_id,
        response_generation: response.response_generation as number,
        surface: presentationSurface,
        unit_id: unit.unit_id,
        contiguous_cursor: unit.seq as number,
      },
    };
  }
  const progressEvent = recordValue(notification.progress_event);
  const progressPayload = recordValue(progressEvent?.payload);
  if (notification.kind === 'work.progress' && progressPayload?.state === 'terminal') {
    const outcome = progressPayload.outcome;
    const reason = typeof outcome === 'string' && ['completed', 'failed', 'cancelled', 'unknown'].includes(outcome)
      ? `PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL_${outcome.toUpperCase()}`
      : 'PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL';
    return hasPresentedOutput
      ? { kind: 'continue' }
      : responseBinding === null
        ? {
          kind: 'failed',
          reason,
          }
        : {
            kind: 'failed',
            reason,
            response: responseBinding,
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

export function productResponseGenerationIdentity(response: Readonly<{
  response_id: string;
  response_generation: number;
}>): string {
  return `${response.response_generation}:${response.response_id}`;
}

export function productForegroundPresentationIdentity(
  binding: Readonly<ProductWebP2ActivationBinding>,
  response: Readonly<{ response_id: string; response_generation: number }>,
): string {
  return JSON.stringify([
    binding.session_id, binding.correlation_id, binding.interaction_id,
    binding.activation_id, binding.activation_generation,
    response.response_id, response.response_generation,
  ]);
}

export function browserSpeechCompatibilityAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  const browserWindow = window as Window & {
    SpeechRecognition?: unknown;
    webkitSpeechRecognition?: unknown;
  };
  const recognition = typeof browserWindow.SpeechRecognition === 'function' || typeof browserWindow.webkitSpeechRecognition === 'function';
  return recognition && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
}

export function createManifest(
  input: Readonly<LiveVoiceIntegratedRoutePanelProps>,
  correlationId: string,
  observedAt: string,
  formal: Readonly<{
    p1_available: boolean;
    p2_available: boolean;
    p3_available: boolean;
  }>,
): IntegratedWebRouteManifest {
  const selection =
    input.routeSelection ??
    createCurrentIntegratedWebRouteSelection({
      p1_browser_speech_available: browserSpeechCompatibilityAvailable(),
      p2_text_chat_available: input.isConnected && input.agentRouteAvailable,
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


export function progressMatchesOwnedBinding(
  event: Readonly<ProductTextProgressEvent>,
  binding: Readonly<ProductWebP3ProgressBinding>,
  activeSessionId: string | null,
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
