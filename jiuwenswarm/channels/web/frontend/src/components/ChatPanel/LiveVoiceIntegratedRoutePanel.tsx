import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Activity, RefreshCw, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
export { productTaskProgressTranslationKey } from './productTaskProgressPresentation';
import {
  FEATURE_LIVE_VOICE_INTEGRATED_WEB,
  FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION,
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
  ProductTextProgressDomAdoptionOwner,
  adoptParsedProductTextProgressEvent,
  parseProductTextProgressEvent,
  productTextProgressPresentationBinding,
  type ProductTextProgressEvent,
} from '../../features/live-voice/formal/productTextProgress';
import {
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_PRESENTATION_ACK_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
  PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
  PRODUCT_P3_TASK_EVENTS_METHOD,
  PRODUCT_P3_TASK_STATUS_METHOD,
  ProductWebP2ActivationOwner,
  ProductWebP3MutationOwner,
  ProductWebP3ProgressOwner,
  isDefinitiveProductOperationError,
  isRetriableProductOperationError,
  pollProductP2RouteWithRecovery,
  replayProductP2DurableOperation,
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
  PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
  ProductP2ActivationJournal,
  reconcileProductP2Predecessor,
  reconcileRetiredProductP2PresentationAcks,
} from '../../features/live-voice/formal/productP2ActivationJournal';
import { inspectProductP3TaskTarget, persistProductP3TaskTarget } from '../../features/live-voice/formal/productP3TaskTargetJournal';
import { claimProductP3ProgressGeneration } from '../../features/live-voice/formal/productP3ProgressGenerationJournal';
import {
  FormalTaskControlLeaf,
  isFormalTaskRetryEligible,
  prepareFormalTaskMutation,
  type FormalTaskControlBinding,
  type FormalTaskControlRecord,
  type FormalTaskState,
  type PreparedFormalTaskMutation,
} from '../../features/live-voice/formal/formalTaskControlLeaf';
import {
  ProductFormalTaskIntentOwner,
  createSessionFormalTaskIntentRecoveryJournal,
  type FormalTaskIntentOperation,
  type FormalTaskIntentOwnerSnapshot,
  type FormalTaskIntentReceipt,
  type FormalTaskIntentTaskControlBinding,
} from '../../features/live-voice/formal/formalTaskIntentRoute';
import {
  FormalP3TaskExperienceOwner,
  type FormalP3TaskExperienceSnapshot,
  type FormalP3TaskMutationInput,
} from '../../features/live-voice/formal/formalP3TaskExperience';
import { WebPlatformDiagnosticsMonitor, type WebPlatformDiagnosticsSnapshot } from '../../features/live-voice/formal/webPlatformDiagnostics';
import {
  BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  BrowserAudioDeviceSelectionOwner,
  type BrowserAudioDeviceSelectionSnapshot,
} from '../../features/live-voice/formal/browserAudioDeviceSelection';
import {
  ProductUnifiedCommittedInputOwner,
  type UnifiedAuthoritativeFinal,
} from '../../features/live-voice/formal/unifiedCommittedInputOwner';
import { extractWebErrorReason, webClient, webReconnectDelayMs } from '../../services/webClient';
import type { WebRequestOptions } from '../../types';
import './LiveVoiceIntegratedRoutePanel.css';

export { extractWebErrorReason, webReconnectDelayMs };

type ProductP2ActivationOwnerInput = Omit<
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

export interface LiveVoiceIntegratedRoutePanelProps {
  activeSessionId: string | null;
  isConnected: boolean;
  agentRouteAvailable: boolean;
  taskCompatibilityAvailable: boolean;
  routeSelection?: Readonly<IntegratedWebRouteSelection>;
  request?: (method: string, params?: Record<string, unknown>, options?: WebRequestOptions) => Promise<unknown>;
  progressSubscribe?: (listener: (payload: unknown) => void) => () => void;
  progressAckCapacity?: number;
  p3RetryInspectionWait?: (delayMs: number, signal: AbortSignal) => Promise<void>;
  productVoiceControlRef?: { current: ProductLiveVoiceSurfaceControl | null };
  onProductVoiceStateChange?: (state: Readonly<ProductLiveVoiceSurfaceState>) => void;
  onProductVoiceMessage?: (event: Readonly<ProductLiveVoiceMessageEvent>) => void;
}

export type ProductLiveVoiceMessageEvent = Readonly<{
  session_id: string;
  message: Readonly<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
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
  interruption_degraded_reason: string | null;
  input: string;
  output: string | null;
  text_status: 'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed';
  text_reason: string | null;
  confirmation_phase: 'confirming' | 'dispatching' | null;
  operation_retained: boolean;
  command_route: 'agent' | 'task';
  task_available: boolean;
  task_operation: FormalTaskIntentOperation;
  task_id: string;
  task_status: FormalTaskIntentOwnerSnapshot['status'];
  task_reason: string | null;
  task_confirmation_form: string | null;
  task_result: string | null;
  task_progress_task_id: string | null;
  task_progress_state: string | null;
  task_progress_delivery_mode: ProductTextProgressEvent['delivery_mode'] | null;
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
  task_controls_locked: boolean;
  task_experience: FormalP3TaskExperienceSnapshot;
}>;

export interface ProductLiveVoiceSurfaceControl {
  start(): Promise<void>;
  stop(): Promise<void>;
  closeSession(sessionId: string): Promise<void>;
  updateInput(value: string): void;
  submit(): void;
  submitCommand(): void;
  setCommandRoute(route: 'agent' | 'task'): void;
  setTaskOperation(operation: FormalTaskIntentOperation): void;
  setTaskId(taskId: string): void;
  cancelTaskConfirmation(): void;
  confirm(): Promise<void>;
  cancelConfirmation(): void;
  refreshTasks(): Promise<void>;
  selectTask(taskId: string): Promise<void>;
  issueTaskMutation(input: FormalP3TaskMutationInput): Promise<void>;
  confirmTaskMutation(): Promise<void>;
  close(): Promise<void>;
}

const defaultProductRequest = (method: string, params?: Record<string, unknown>, options?: WebRequestOptions): Promise<unknown> =>
  webClient.request(method, params, options);

const PRODUCT_P3_RETRY_INSPECTION_DELAYS_MS = Object.freeze([250, 500, 1_000, 2_000, 4_000, 8_000, 16_000, 30_000]);
export const PRODUCT_P3_CREATED_TASK_BOOTSTRAP_DELAYS_MS = Object.freeze([250, 500, 1_000]);
const PRODUCT_P3_PROGRESS_BUFFER_CAPACITY = 128;
export const PRODUCT_P3_PROGRESS_EXHAUSTED_CAPACITY = 128;
const PRODUCT_P3_PROGRESS_RECONCILIATION_RETRY_MS = 250;
const PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS = 4;
const PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED = 'PRODUCT_P3_PROGRESS_ACK_RETENTION_FAILED';
export const PRODUCT_P2_NOTIFICATION_PENDING_BACKOFF_MS = 500;

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

type ProductTaskPresentationFailureReason = 'task_audio_playout_failed' | 'task_audio_owner_unavailable';

function sameProductPresentation(
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

function durablePresentationAckMatches(
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

/** True when playout stood down for a live speaker rather than failing. */
function playoutDeferredToSpeaker(value: unknown): boolean {
  return (
    value !== null &&
    typeof value === 'object' &&
    (value as { reason?: unknown }).reason === PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER
  );
}

function stableProductTextReason(value: unknown, fallback: string): string {
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

function isStaleProductResponseError(value: unknown): boolean {
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

function isHarmlessCompletedBargeInError(value: unknown): boolean {
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
  task_route?: 'structured' | 'natural';
  phase: 'confirming' | 'dispatching';
  session_id: string;
  text: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
}>;

type ProductVoiceDraftBinding = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
}>;

type EditedVoiceDraftConfirmation = ProductVoiceDraftBinding &
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

type ProductWebRequest = NonNullable<LiveVoiceIntegratedRoutePanelProps['request']>;

function sameFormalTaskControlBinding(left: Readonly<FormalTaskControlBinding>, right: Readonly<FormalTaskControlBinding>): boolean {
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
    expected_binding?: FormalTaskIntentTaskControlBinding;
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
  };
}

export function productTextBlockedByP1Status(status: ProductP1VoiceStatus): boolean {
  return ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(status);
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

function recognizedVoiceMatchesProductBinding(
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

function recognizedSpeechConfirmationAuthorityMatches(
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
  | { readonly kind: 'continue' }
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
      readonly ack: ProductPresentationAckInput;
      readonly replayed: boolean;
      readonly task_notification: boolean;
      readonly adjustment_notification: boolean;
    };

type PendingForegroundPresentationFence = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  activation_id: string;
  activation_generation: number;
  response_id: string;
  response_generation: number;
}>;

type ProductP2NotificationAdmission = Readonly<{
  voice_loop_generation: number;
  foreground_presentation: PendingForegroundPresentationFence | null;
}>;

function foregroundPresentationFenceMatchesResponse(
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

export function shouldYieldProductP2PollToVoiceCapture(
  input: Readonly<{
    voice_loop_enabled: boolean;
    terminal_notification_check_required: boolean;
    foreground_response_waiting: boolean;
  }>,
): boolean {
  return input.voice_loop_enabled && input.terminal_notification_check_required && !input.foreground_response_waiting;
}

export function productP2NotificationRepollDelayMs(
  input: Readonly<{
    disposition: ProductP2NotificationDisposition;
    terminal_notification_check_required: boolean;
    foreground_response_waiting: boolean;
  }>,
): number {
  if (input.disposition.kind !== 'continue' || !input.terminal_notification_check_required) return 0;
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

function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function formalTaskIntentResultSummary(receipt: FormalTaskIntentReceipt | null | undefined): string | null {
  if (receipt?.disposition !== 'dispatched' || receipt.operation === null || receipt.formal_task_result === null) return null;
  const result = receipt.formal_task_result;
  const task = recordValue(result.task) ?? result;
  const taskId = typeof task.task_id === 'string' && task.task_id.trim() ? task.task_id.trim() : receipt.task_id;
  const state = typeof task.state === 'string' && task.state.trim() ? task.state.trim() : null;
  const outcome = typeof task.outcome === 'string' && task.outcome.trim() ? task.outcome.trim() : null;
  if (taskId !== null && state !== null) {
    return `${taskId} | ${state}${outcome === null ? '' : `/${outcome}`}`;
  }
  if (taskId !== null) return `${receipt.operation} | ${taskId}`;
  const status = typeof result.status === 'string' && result.status.trim() ? result.status.trim() : null;
  return status === null ? receipt.operation : `${receipt.operation} | ${status}`;
}

const PRODUCT_P3_RETRY_INSPECTION_FAILED_REASON = 'PRODUCT_P3_RETRY_INSPECTION_FAILED';
const PRODUCT_P3_STABLE_REASON_PATTERN = /^[A-Z][A-Z0-9_]{0,127}$/;

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

const PRODUCT_P3_TERMINAL_STATUSES = Object.freeze(['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const);

const PRODUCT_P3_PROGRESS_EVENT_TYPES: Readonly<Record<FormalTaskState, readonly string[]>> = Object.freeze({
  accepted: Object.freeze(['task.accepted', 'task.retry_accepted']),
  running: Object.freeze(['task.running']),
  blocked: Object.freeze(['task.blocked']),
  decision_required: Object.freeze(['task.decision_required']),
  terminal: Object.freeze(['task.terminal']),
});

function productP3ProgressState(value: unknown): FormalTaskState {
  if (!(['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const).includes(value as FormalTaskState)) {
    throw new Error('product P3 progress state is outside the formal lifecycle');
  }
  return value as FormalTaskState;
}

function productP3ProgressOutcome(value: unknown): ProductP3TerminalStatus | null {
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

const PRODUCT_P3_PROGRESS_QUARANTINABLE_FAILURES = new Set([
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
  const event = recordValue(notification.agent_event);
  const unit = recordValue(notification.presentation_unit);
  const response = recordValue(notification.response);
  const taskNotification = event?.source_provenance === 'server.task_notification';
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
      task_notification: taskNotification,
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
    return hasPresentedOutput
      ? { kind: 'continue' }
      : responseBinding === null
        ? {
          kind: 'failed',
          reason:
            typeof progressPayload.outcome === 'string'
              ? `PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL:${progressPayload.outcome}`
              : 'PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL',
          }
        : {
            kind: 'failed',
            reason:
              typeof progressPayload.outcome === 'string'
                ? `PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL:${progressPayload.outcome}`
                : 'PRODUCT_AGENT_TERMINAL_WITHOUT_FINAL',
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
  }>,
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
  const [retiredPresentationAckRecoveryEpoch, setRetiredPresentationAckRecoveryEpoch] = useState(0);
  const [p2NotificationWakeEpoch, setP2NotificationWakeEpoch] = useState(0);
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
  const [adjustmentNotification, setAdjustmentNotification] = useState<string | null>(null);
  const [productTextStatus, setProductTextStatus] = useState<
    'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed'
  >('idle');
  const [productTextReason, setProductTextReason] = useState<string | null>(null);
  const [recoveryDiagnostic, setRecoveryDiagnostic] = useState<ProductLiveVoiceRecoveryDiagnostic | null>(null);
  const [p1VoiceStatus, setP1VoiceStatus] = useState<ProductP1VoiceStatus>(FEATURE_LIVE_VOICE_INTEGRATED_P1 ? 'idle' : 'closed');
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
  const [taskIntentOperation, setTaskIntentOperation] = useState<FormalTaskIntentOperation>('task.create');
  const [taskIntentText, setTaskIntentText] = useState('');
  const [taskIntentTaskId, setTaskIntentTaskId] = useState('');
  const [productCommandRoute, setProductCommandRoute] = useState<'agent' | 'task'>('agent');
  const [taskIntentSnapshot, setTaskIntentSnapshot] = useState<FormalTaskIntentOwnerSnapshot>({
    status: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ? 'idle' : 'disabled',
    pending_confirmation: null,
    retained_transport: false,
    receipt: null,
    reason: null,
  });
  const [taskExperience, setTaskExperience] = useState<FormalP3TaskExperienceSnapshot>({
    status: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ? 'idle' : 'disabled',
    session_id: null,
    tasks: Object.freeze([]),
    selected_task_id: null,
    collection_operations: Object.freeze([]),
    command: null,
    reason: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ? null : 'FORMAL_P3_TASK_EXPERIENCE_DISABLED',
  });
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
  const activationOwnerRef = useRef<ProductWebP2ActivationOwner | null>(null);
  const p2ActivationJournalRef = useRef<ProductP2ActivationJournal | null>(null);
  const retiredPresentationAckInFlightRef = useRef(new Set<string>());
  const retiredPresentationAckOwnerRequestRef = useRef(new Map<ProductWebP2ActivationOwner, string>());
  const retiredPresentationAckDrainIdentityRef = useRef(0);
  const p1VoiceOwnerRef = useRef<ProductP1VoiceRouteOwner | null>(null);
  const p1VoiceOwnerSessionRef = useRef<string | null>(null);
  const unifiedInputOwnerRef = useRef<ProductUnifiedCommittedInputOwner | null>(null);
  const deviceSelectionOwnerRef = useRef<BrowserAudioDeviceSelectionOwner | null>(null);
  const pendingP1VoiceStartRef = useRef<Readonly<{ generation: number; promise: Promise<void> }> | null>(null);
  const pendingP1VoiceStopRef = useRef<Promise<void> | null>(null);
  const stopP1VoiceHandlerRef = useRef<() => Promise<void>>(async () => undefined);
  const startP1VoiceHandlerRef = useRef<() => Promise<void>>(async () => undefined);
  const voiceLoopEnabledRef = useRef(false);
  const voiceLoopGenerationRef = useRef(0);
  const voiceLoopCaptureTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | null>(null);
  const voiceLoopP2RefreshAfterGenerationRef = useRef<number | null>(null);
  const voiceLoopP2RefreshInFlightRef = useRef(false);
  const terminalNotificationCheckRequiredRef = useRef(false);
  terminalNotificationCheckRequiredRef.current = Boolean(
    createdProgressTaskId !== null &&
      createdProgressOrigin?.kind === 'voice' &&
      terminalNotificationTaskIdRef.current !== createdProgressTaskId,
  );
  const submittedVoiceFinalsRef = useRef(
    new Map<string, Readonly<{ fingerprint: string; operation: Promise<void> }>>(),
  );
  const pendingUnifiedFinalRef = useRef<Readonly<{
    receipt: string;
    input: UnifiedAuthoritativeFinal;
  }> | null>(null);
  const pendingForegroundPresentationRef = useRef<PendingForegroundPresentationFence | null>(null);
  const pendingProductTurnRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductTurnInput;
  } | null>(null);
  const pendingPresentationAttemptRef = useRef<{
    owner: ProductWebP2ActivationOwner;
    input: ProductPresentationAckInput & { presented_at: string };
    response: Readonly<{
      interaction_id: string;
      response_id: string;
      response_generation: number;
    }>;
    playoutSettlement: Promise<void>;
    markPlayoutSettled: () => void;
    task_notification: {
      task_id: string;
      disposition: Extract<ProductP2NotificationDisposition, { readonly kind: 'presentation' }>;
      retry_count: number;
      retry_pending: boolean;
    } | null;
    failure_reason?: ProductTaskPresentationFailureReason;
    settlement?: Promise<void>;
    /**
     * Set when playout yielded to a live speaker. The announcement is retained
     * exactly as delivered and replayed once that speaker settles; it is not a
     * playout failure and must not rebuild the P1 route.
     */
    deferred_to_speaker?: boolean;
  } | null>(null);
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
  const progressActivationOwnerRef = useRef<ProductWebP3ProgressOwner | null>(null);
  const p3MutationOwnerRef = useRef<ProductWebP3MutationOwner | null>(null);
  const taskIntentOwnerRef = useRef<ProductFormalTaskIntentOwner | null>(null);
  const taskExperienceOwnerRef = useRef<FormalP3TaskExperienceOwner | null>(null);
  const pendingNaturalCreateHandoffRef = useRef<Readonly<{
    owner: ProductFormalTaskIntentOwner;
    session_id: string;
    correlation_id: string;
    task_id: string;
    origin: Readonly<{ kind: 'text' | 'voice'; id: string }>;
    task_control_binding: FormalTaskIntentTaskControlBinding;
  }> | null>(null);
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
    const retained = generationCaptureRef.current;
    if (retained === null) return false;
    if (matches !== undefined && !matches(retained)) return false;
    generationCaptureRef.current = null;
    return true;
  };
  const generationInterruptSequenceRef = useRef(0);
  // Responses this route has interrupted. A fenced answer can still be in
  // flight from the server, so identity, not timing, is what refuses it.
  const interruptedProductResponsesRef = useRef(new Map<string, true>());
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
    terminalAnnouncementStateRef.current = state;
    if (taskId !== undefined) terminalAnnouncementTaskIdRef.current = taskId;
    setTerminalAnnouncementState(state);
  };
  const queueTerminalAnnouncement = (taskId: string) => {
    const route = createdProgressRouteRef.current;
    if (route?.task_id !== taskId || route.origin?.kind !== 'voice' || terminalNotificationTaskIdRef.current === taskId) {
      return;
    }
    const currentTaskId = terminalAnnouncementTaskIdRef.current;
    if (currentTaskId !== null && currentTaskId !== taskId && terminalAnnouncementStateRef.current !== 'idle') return;
    if (terminalAnnouncementStateRef.current === 'idle') updateTerminalAnnouncementState('queued', taskId);
  };
  const adoptCreatedProgressRoute = (route: typeof createdProgressRoute) => {
    const previousTaskId = createdProgressRouteRef.current?.task_id ?? null;
    const nextTaskId = route?.task_id ?? null;
    if (nextTaskId !== null && nextTaskId !== previousTaskId) {
      terminalNotificationTaskIdRef.current = null;
      updateTerminalAnnouncementState('idle', null);
      terminalAnnouncementSpeechOwnerRef.current = null;
      setTerminalNotification(null);
      setAdjustmentNotification(null);
    }
    createdProgressRouteRef.current = route;
    terminalNotificationCheckRequiredRef.current = Boolean(
      nextTaskId !== null && route?.origin?.kind === 'voice' && terminalNotificationTaskIdRef.current !== nextTaskId,
    );
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
    recoveryDiagnosticRef.current = diagnostic;
    setRecoveryDiagnostic(diagnostic);
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
    recoveryDiagnosticRef.current = null;
    setRecoveryDiagnostic(null);
  };
  activeSessionRef.current = props.activeSessionId;
  isConnectedRef.current = props.isConnected;

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
        pendingUnifiedFinalRef.current === null &&
        pendingForegroundPresentationRef.current === null &&
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

  const resumeVoiceLoopAfterP2Successor = (binding: NonNullable<ProductWebP2ActivationSnapshot['binding']>) => {
    const predecessorGeneration = voiceLoopP2RefreshAfterGenerationRef.current;
    if (predecessorGeneration === null || binding.activation_generation <= predecessorGeneration) return;
    voiceLoopP2RefreshAfterGenerationRef.current = null;
    voiceLoopP2RefreshInFlightRef.current = false;
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
                setProductTextReason(reason);
                setProductTextStatus('failed');
                publishProductRecoveryDiagnostic({
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
        if (activeVoiceResponseRef.current?.response_id === retained.response.response_id) {
          activeVoiceResponseRef.current = null;
        }
        pendingPresentationAttemptRef.current = null;
        setPendingPresentationAck(null);
        if (taskNotification.task_id) {
          terminalNotificationTaskIdRef.current = taskNotification.task_id;
          terminalNotificationCheckRequiredRef.current = false;
        }
        terminalAnnouncementSpeechOwnerRef.current = null;
        updateTerminalAnnouncementState('idle', null);
        clearProductRecoveryDiagnostic({
          seam: 'tts',
          binding: owner.snapshot().binding,
          response: retained.response,
        });
        if (!continuePendingVoiceLoopP2Refresh()) scheduleProductVoiceLoopCapture();
      })
      .catch(error => {
        if (!isCurrentOwner()) return;
        const reason = stableProductTextReason(error, 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED');
        if (!owner.hasPendingPresentationFailure()) {
          if (activeVoiceResponseRef.current?.response_id === retained.response.response_id) {
            activeVoiceResponseRef.current = null;
          }
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          terminalAnnouncementSpeechOwnerRef.current = null;
          updateTerminalAnnouncementState('idle', null);
          if (isStaleProductResponseError(error)) {
            setProductTextReason(null);
            setProductTextStatus(pendingForegroundPresentationRef.current !== null ? 'waiting' : 'acknowledged');
            clearProductRecoveryDiagnostic({
              seam: 'tts',
              binding: owner.snapshot().binding,
              response: retained.response,
            });
          } else {
            setProductTextReason(reason);
            setProductTextStatus('failed');
            publishProductRecoveryDiagnostic({
              seam: 'tts',
              disposition: 'terminal',
              reason,
              binding: owner.snapshot().binding,
              response: retained.response,
            });
          }
          if (!continuePendingVoiceLoopP2Refresh()) scheduleProductVoiceLoopCapture();
          return;
        }
        setProductTextReason(reason);
        setProductTextStatus('failed');
        publishProductRecoveryDiagnostic({
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

  const settleProductPresentationAck = (retained: NonNullable<typeof pendingPresentationAttemptRef.current>): Promise<void> => {
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
              setProductTextReason(reason);
              setProductTextStatus('failed');
              publishProductRecoveryDiagnostic({
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
        const currentPresentation = pendingPresentationAttemptRef.current;
        if (
          isCurrentPresentationOwner() &&
          currentPresentation === retained &&
          sameProductPresentation(currentPresentation.input, retained.input)
        ) {
          const mayMutateUi = canMutateCurrentPresentationUi();
          pendingPresentationAttemptRef.current = null;
          setPendingPresentationAck(null);
          if (!mayMutateUi) return;
          const terminal = retained.task_notification;
          if (terminal !== null) {
            retainBoundedPresentedProductResponse(presentedProductResponsesRef.current, retained.input.response_id);
            terminalNotificationTaskIdRef.current = terminal.task_id;
            terminalNotificationCheckRequiredRef.current = false;
            terminalAnnouncementSpeechOwnerRef.current = null;
            updateTerminalAnnouncementState('idle', null);
          }
          setProductTextReason(null);
          setProductTextStatus('acknowledged');
          clearProductRecoveryDiagnostic({
            seam: 'presentation_ack',
            binding: owner.snapshot().binding,
            response: retained.input,
          });
          if (!continuePendingVoiceLoopP2Refresh()) scheduleProductVoiceLoopCapture();
        }
      })
      .catch(error => {
        if (isCurrentPresentationOwner()) {
          const mayMutateUi = canMutateCurrentPresentationUi();
          const reason = stableProductTextReason(error, 'PRODUCT_PRESENTATION_ACK_RECOVERY_REQUIRED');
          if (!owner.hasPendingPresentationAck()) {
            pendingPresentationAttemptRef.current = null;
            setPendingPresentationAck(null);
            if (!mayMutateUi) return;
            if (isStaleProductResponseError(error)) {
              // A newer committed utterance already owns the response lane.
              // The predecessor ACK is definitively obsolete, not a voice
              // recovery failure; keep polling for the newer presentation.
              const terminal = retained.task_notification;
              if (terminal !== null) {
                // Playout already completed before this ACK.  Remember that
                // exact current-Task announcement locally so a server replay
                // cannot speak or ACK it twice, then release the foreground
                // response lane from the predecessor's `acking` state.
                retainBoundedPresentedProductResponse(presentedProductResponsesRef.current, retained.input.response_id);
                terminalNotificationTaskIdRef.current = terminal.task_id;
                terminalNotificationCheckRequiredRef.current = false;
                terminalAnnouncementSpeechOwnerRef.current = null;
                updateTerminalAnnouncementState('idle', null);
              }
              setProductTextReason(null);
              setProductTextStatus(pendingForegroundPresentationRef.current !== null ? 'waiting' : 'acknowledged');
              clearProductRecoveryDiagnostic({
                seam: 'presentation_ack',
                binding: owner.snapshot().binding,
                response: retained.input,
              });
              if (!continuePendingVoiceLoopP2Refresh() && pendingForegroundPresentationRef.current === null) {
                scheduleProductVoiceLoopCapture();
              }
            } else {
              setProductTextReason(reason);
              setProductTextStatus('failed');
              publishProductRecoveryDiagnostic({
                seam: 'presentation_ack',
                disposition: 'terminal',
                reason,
                binding: owner.snapshot().binding,
                response: retained.response,
              });
            }
          } else if (mayMutateUi) {
            setProductTextReason(reason);
            setProductTextStatus('failed');
            publishProductRecoveryDiagnostic({
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

  useEffect(() => {
    const sessionId = props.activeSessionId;
    clearScheduledProductVoiceLoopCapture();
    voiceLoopEnabledRef.current = false;
    voiceLoopGenerationRef.current += 1;
    voiceLoopP2RefreshAfterGenerationRef.current = null;
    voiceLoopP2RefreshInFlightRef.current = false;
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
      props.taskCompatibilityAvailable,
    ],
  );

  const adoptProductP2Notification = (
    owner: ProductWebP2ActivationOwner,
    notification: Readonly<Record<string, unknown>>,
    admission: ProductP2NotificationAdmission | null = null,
  ) => {
    const response = recordValue(notification.response);
    const responseId = typeof response?.response_id === 'string' ? response.response_id : null;
    const disposition = classifyProductP2Notification(notification, responseId !== null && presentedProductResponsesRef.current.has(responseId));
    const presentationBinding = owner.snapshot().binding;
    if (
      admission !== null &&
      (voiceLoopGenerationRef.current !== admission.voice_loop_generation ||
        voiceLoopP2RefreshAfterGenerationRef.current !== null)
    ) {
      // Exit and P2 refresh retire the entire poll admission before any UI,
      // history, TTS or ACK effect. The durable route may replay the
      // notification to the exact successor owner after cleanup completes.
      return disposition;
    }
    if (disposition.kind === 'failed') {
      if (
        foregroundPresentationFenceMatchesResponse(
          pendingForegroundPresentationRef.current,
          presentationBinding,
          disposition.response ?? null,
        )
      ) {
        pendingForegroundPresentationRef.current = null;
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
      scheduleProductVoiceLoopCapture();
      return disposition;
    }
    if (disposition.kind !== 'presentation') {
      if (
        shouldYieldProductP2PollToVoiceCapture({
          voice_loop_enabled: voiceLoopEnabledRef.current,
          terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
          foreground_response_waiting: pendingForegroundPresentationRef.current !== null,
        })
      ) {
        scheduleProductVoiceLoopCapture();
      }
      return disposition;
    }
    if (!disposition.task_notification && interruptedProductResponsesRef.current.has(disposition.response_id)) {
      // The speaker already interrupted this exact answer. It must not render,
      // speak, acknowledge or reach history, whether it arrives before or after
      // the server-side fence settles.
      return disposition;
    }
    if (!disposition.task_notification && terminalAnnouncementStateRef.current === 'fetching' && terminalAnnouncementTaskIdRef.current !== null) {
      updateTerminalAnnouncementState('queued');
    }
    const pending = pendingPresentationAttemptRef.current;
    if (pending !== null && (pending.owner !== owner || pending.input.response_id !== disposition.response_id)) {
      throw new Error('a previous presentation ACK is still unresolved');
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
      if (ownsForegroundPresentation) pendingForegroundPresentationRef.current = null;
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
        playoutSettlement,
        markPlayoutSettled,
        task_notification: disposition.task_notification
          ? {
              task_id: createdProgressRouteRef.current?.task_id ?? terminalAnnouncementTaskIdRef.current ?? '',
              disposition,
              retry_count: 0,
              retry_pending: false,
            }
          : null,
      };
    }
    const presentationAttempt = pendingPresentationAttemptRef.current;
    if (presentationAttempt === null) throw new Error('presentation ACK owner was not retained');
    const playoutLoopGeneration = voiceLoopGenerationRef.current;
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
      voiceLoopGenerationRef.current === playoutLoopGeneration;
    const retainAck = (playoutFailed = false) => {
      presentationAttempt.markPlayoutSettled();
      if (!isCurrentPresentationAttempt()) return;
      if (playoutFailed) setProductTextStatus('failed');
      if (presentationAttempt.task_notification != null) updateTerminalAnnouncementState('acking');
      setPendingPresentationAck(disposition.ack);
      void settleProductPresentationAck(presentationAttempt);
    };
    const voiceOwner = p1VoiceOwnerRef.current;
    if (voiceOwner !== null && (!disposition.replayed || disposition.task_notification)) {
      if (disposition.task_notification) updateTerminalAnnouncementState('playing');
      // Clear a silent listening window before playout, and yield entirely to a
      // speaker who is mid-utterance instead of failing the route on them.
      void settleCaptureBeforePlayout()
        .then(readiness => {
          if (readiness !== 'ready') {
            throw Object.assign(new Error('playout yielded to an active speaker'), {
              reason: PRODUCT_PLAYOUT_DEFERRED_TO_SPEAKER,
            });
          }
          return voiceOwner.playAgentText({
            response: disposition.response,
            unit_id: disposition.unit_id,
            text: disposition.text,
          });
        })
        .then(() => {
          if (!isCurrentVoicePlayout()) {
            presentationAttempt.markPlayoutSettled();
            if (isCurrentPresentationAttempt()) retainAck();
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
          if (disposition.task_notification && playoutDeferredToSpeaker(error)) {
            // Standing down is not a playout failure and must be decided before
            // anything settles: settling the playout here would let cleanup
            // acknowledge an announcement that was never spoken. The retained
            // attempt is the only identity that matters here -- media start
            // authority is not required to *not* play something.
            if (pendingPresentationAttemptRef.current !== presentationAttempt) return;
            // Release the active-response claim: while it stands the route
            // counts as foreground-busy, and the arbitration that has to replay
            // this announcement would defer forever.
            if (activeVoiceResponseRef.current?.response_id === disposition.response_id) {
              activeVoiceResponseRef.current = null;
            }
            presentationAttempt.deferred_to_speaker = true;
            terminalAnnouncementSpeechOwnerRef.current = voiceOwner;
            updateTerminalAnnouncementState('queued');
            return;
          }
          presentationAttempt.markPlayoutSettled();
          if (disposition.task_notification && disposition.ack.surface === 'audio') {
            if (!isCurrentPresentationAttempt()) return;
            if (activeVoiceResponseRef.current?.response_id === disposition.response_id) activeVoiceResponseRef.current = null;
            const reason = stableProductTextReason(error, 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED');
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
            if (isCurrentPresentationAttempt()) retainAck();
            return;
          }
          if (activeVoiceResponseRef.current?.response_id === disposition.response_id) activeVoiceResponseRef.current = null;
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

  const settleRetainedP2Operations = async (
    owner: ProductWebP2ActivationOwner,
    options: Readonly<{ abandon_pending_notification?: boolean }> = {},
  ) => {
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
            const ownerCorrelation = owner.snapshot().binding?.correlation_id;
            if (!ownerCorrelation) throw new Error('recovered voice Task origin lost its correlation');
            voiceTaskOriginRef.current = bindProductVoiceTaskOrigin(pendingTurn.input, result, ownerSession, interactionId, ownerCorrelation);
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
      await pendingPresentation.playoutSettlement;
      // Normal playout settlement and P2 recovery share one exact retained
      // operation. A failed Task AUDIO playout reports failure; it must never
      // be converted into an accepted Presentation ACK during recovery.
      if (pendingPresentation.failure_reason !== undefined) {
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
        if (voiceOwner !== null && !['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(voiceOwner.status().status)) {
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
          const activation = progressActivationOwnerRef.current?.snapshot();
          const leaf = formalTaskControlLeafRef.current;
          if (activation?.status !== 'active' || activation.binding === null || leaf === null) return;
          for (const [deliveryId, event] of pendingOwnedProgressRef.current) {
            if (!progressMatchesOwnedBinding(event, activation.binding, ownedSessionId)) {
              pendingOwnedProgressRef.current.delete(deliveryId);
              reconciliationFailures.delete(deliveryId);
            }
          }
          for (const deliveryId of reconciliationFailures.keys()) {
            if (!pendingOwnedProgressRef.current.has(deliveryId)) reconciliationFailures.delete(deliveryId);
          }
          const parsed = [...pendingOwnedProgressRef.current.values()]
            .filter(event => progressMatchesOwnedBinding(event, activation.binding!, ownedSessionId))
            .sort(
              (left, right) =>
                left.source_event.seq - right.source_event.seq || left.delivery_id.localeCompare(right.delivery_id),
            )[0];
          if (parsed === undefined) return;
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
            const currentActivation = progressActivationOwnerRef.current?.snapshot();
            return (
              mountedRef.current &&
              activeSessionRef.current === ownedSessionId &&
              progressAckOwnerRef.current === owner &&
              formalTaskControlLeafRef.current === leaf &&
              p3ProgressReconciliationGenerationRef.current === reconciliationGeneration &&
              progressOwnerEpochRef.current === ownerEpoch &&
              (progressTaskTargetRef.current === null || progressTaskTargetRef.current === parsed.task_id) &&
              currentActivation?.status === 'active' &&
              currentActivation.binding !== null &&
              progressMatchesOwnedBinding(parsed, currentActivation.binding, ownedSessionId)
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
            pendingOwnedProgressRef.current.delete(parsed.delivery_id);
            reconciliationFailures.delete(parsed.delivery_id);
            const adopted = adoptParsedProductTextProgressEvent(progressRef.current, parsed, ownedSessionId);
            if (adopted !== progressRef.current) {
              progressRef.current = adopted;
              setProgress(adopted);
            }
            const terminalStatus = productP3TerminalStatus(record);
            if (terminalStatus !== null) {
              setP3MutationStatus(terminalStatus);
              queueTerminalAnnouncement(parsed.task_id);
            }
            // The layout effect owns the first ACK only after React commits the
            // exact delivery into the connected DOM.
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
        (progressTaskTargetRef.current !== null && progressTaskTargetRef.current !== parsed.task_id)
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

  useLayoutEffect(() => {
    if (progress === null) return;
    const adoptionOwner = progressDomAdoptionOwnerRef.current;
    const node = progressDomRef.current;
    if (adoptionOwner === null || node === null) return;
    try {
      const retained = adoptionOwner.adopt(progress, node);
      if (retained === null) return;
      setProgressAck(retained.status);
      // The reconciliation coroutine clears its in-flight guard in `finally`.
      // A task turn therefore starts the next prefix item only after both that
      // guard and this committed-DOM adoption have settled.
      globalThis.setTimeout(() => progressDrainRef.current?.(), 0);
    } catch {
      setProgressAck('failed');
    }
  }, [progress]);

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
      setProductTextStatus('idle');
    }
    p1VoiceCaptureBindingRef.current = null;
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
    const pending = recognizedSpeechConfirmationRef.current;
    if (pending === null) return;
    const displayedText = pending.intent === 'agent' ? productInput : pending.task_route === 'natural' ? taskIntentText : p3TaskInstruction;
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
    taskIntentText,
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
    updateRecognizedSpeechConfirmation(null);
    recognizedVoiceRef.current = null;
    voiceDraftBindingRef.current = null;
    p1VoiceCaptureBindingRef.current = null;
    presentedProductResponsesRef.current.clear();
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
  }, [props.activeSessionId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearScheduledProductVoiceLoopCapture();
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
            await previous.closeWithRetry();
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
              if (settled.status === 'active') {
                clearProductRecoveryDiagnostic({
                  seam: 'activation',
                  binding: settled.binding,
                });
              }
            }
          } catch {
            // The exact ambiguous activation is reconciled below on the next run.
            if (previous.needsCleanup()) scheduleRecovery();
          }
          return;
        }
        if (previous.needsCleanup()) {
          try {
            if (snapshot.binding && journalReady && sameSession) {
              journal!.markClosing(snapshot.binding);
            }
            await previous.closeWithRetry({
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
      const recoveredBinding = recovery.owner?.snapshot().binding ?? journal.snapshot().binding;
      recovery.owner = null;
      if (!isCurrentRun()) return;
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
            scheduleRecovery();
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
              scheduleRecovery();
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
      if (recoveryTimer !== null) globalThis.clearTimeout(recoveryTimer);
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
      if (!isCurrent() || result.kind !== 'retry') return;
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
  }, [p1VoiceStatus, p2Activation.status, productTextStatus, props.isConnected, terminalAnnouncementState]);

  useEffect(() => {
    const owner = activationOwnerRef.current;
    const binding = p2Activation.binding;
    const journal = p2ActivationJournalRef.current;
    if (
      !props.isConnected ||
      p2Activation.status !== 'active' ||
      !binding ||
      !owner ||
      !journal ||
      pendingPresentationAck !== null ||
      pendingPresentationAttemptRef.current !== null ||
      activeVoiceResponseRef.current !== null ||
      voiceLoopP2RefreshAfterGenerationRef.current !== null ||
      (!['idle', 'fetching'].includes(terminalAnnouncementState) && !(terminalAnnouncementState === 'queued' && productTextStatus === 'waiting')) ||
      (terminalAnnouncementState === 'fetching' && !voiceLoopEnabledRef.current) ||
      (['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus) &&
        !admitsGenerationListeningPoll(p1VoiceStatus))
    )
      return;
    const notificationAdmission: ProductP2NotificationAdmission = Object.freeze({
      voice_loop_generation: voiceLoopGenerationRef.current,
      foreground_presentation: pendingForegroundPresentationRef.current,
    });
    let cancelled = false;
    const poll = async () => {
      while (!cancelled && activationOwnerRef.current === owner) {
        const liveStatus = p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus;
        if (
          activeVoiceResponseRef.current !== null ||
          (['starting', 'capturing', 'recognizing', 'playing'].includes(liveStatus) &&
            !admitsGenerationListeningPoll(liveStatus))
        )
          return;
        try {
          const outcome = await pollProductP2RouteWithRecovery({
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
                if (successorSnapshot.binding !== null) resumeVoiceLoopAfterP2Successor(successorSnapshot.binding);
              }
              return successor;
            },
          });
          if (outcome.kind === 'recovered') {
            await pendingP1VoiceStartRef.current?.promise.catch(() => undefined);
            scheduleProductVoiceLoopCapture();
            return;
          }
          if (
            cancelled ||
            activationOwnerRef.current !== owner ||
            voiceLoopGenerationRef.current !== notificationAdmission.voice_loop_generation ||
            voiceLoopP2RefreshAfterGenerationRef.current !== null
          ) {
            return;
          }
          const disposition = adoptProductP2Notification(owner, outcome.notification, notificationAdmission);
          // A presentation owns the P2 lane until its TEXT ACK settles.  Do
          // not let an immediately rejected TTS attempt race a successor
          // notification long-poll and strand that ACK behind it.
          if (disposition.kind === 'presentation' || pendingPresentationAttemptRef.current?.owner === owner) return;
          // A hands-free capture is admitted only after this exact poll has
          // settled. A committed foreground response keeps the P2 lane until
          // its presentation arrives; the queued Task terminal check cannot
          // starve that response after an idle keepalive.
          if (
            shouldYieldProductP2PollToVoiceCapture({
              voice_loop_enabled: voiceLoopEnabledRef.current,
              terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
              foreground_response_waiting: pendingForegroundPresentationRef.current !== null,
            })
          ) {
            return;
          }
          const repollDelayMs = productP2NotificationRepollDelayMs({
            disposition,
            terminal_notification_check_required: terminalNotificationCheckRequiredRef.current,
            foreground_response_waiting: pendingForegroundPresentationRef.current !== null,
          });
          if (repollDelayMs > 0) {
            await new Promise<void>(resolve => globalThis.setTimeout(resolve, repollDelayMs));
            if (cancelled || activationOwnerRef.current !== owner) return;
          }
        } catch (error) {
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
    if (typeof window !== 'undefined') {
      try {
        const retainedIntent = createSessionFormalTaskIntentRecoveryJournal(window.sessionStorage).load(sessionId);
        if (retainedIntent?.phase === 'post_create_binding') return;
      } catch {
        // A corrupt/unavailable intent journal is an authority barrier. The
        // task-intent owner reports the stable recovery error; do not race it
        // with the less-specific historical target recovery.
        return;
      }
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
    taskIntentOwnerRef.current?.close();
    taskIntentOwnerRef.current = null;
    pendingNaturalCreateHandoffRef.current = null;
    setProductCommandRoute('agent');
    setTaskIntentOperation('task.create');
    setTaskIntentText('');
    setTaskIntentTaskId('');
    if (!FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION || !props.activeSessionId || !props.isConnected) {
      setTaskIntentSnapshot({
        status: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION ? 'idle' : 'disabled',
        pending_confirmation: null,
        retained_transport: false,
        receipt: null,
        reason: null,
      });
      return;
    }
    let recoveryJournal: ReturnType<typeof createSessionFormalTaskIntentRecoveryJournal> | null = null;
    try {
      recoveryJournal = typeof window === 'undefined' ? null : createSessionFormalTaskIntentRecoveryJournal(window.sessionStorage);
    } catch {
      setTaskIntentSnapshot({
        status: 'failed',
        pending_confirmation: null,
        retained_transport: false,
        receipt: null,
        reason: 'TASK_INTENT_RECOVERY_STORAGE_UNAVAILABLE',
      });
      return;
    }
    const owner = new ProductFormalTaskIntentOwner({
      enabled: true,
      request: (method, params, requestId) => productRequest(method, { ...params }, { requestId }),
      recovery_journal: recoveryJournal,
    });
    taskIntentOwnerRef.current = owner;
    setTaskIntentSnapshot(owner.snapshot());
    void owner
      .recoverPending({ session_id: props.activeSessionId, correlation_id: correlationId })
      .then(receipt => {
        if (taskIntentOwnerRef.current !== owner || receipt === null) return;
        adoptFormalTaskIntentReceipt(receipt);
        setTaskIntentSnapshot(owner.snapshot());
      })
      .catch(() => {
        if (taskIntentOwnerRef.current === owner) setTaskIntentSnapshot(owner.snapshot());
      });
    return () => {
      owner.close({ abandon_scope: activeSessionRef.current !== props.activeSessionId });
      if (taskIntentOwnerRef.current === owner) taskIntentOwnerRef.current = null;
      if (pendingNaturalCreateHandoffRef.current?.owner === owner) pendingNaturalCreateHandoffRef.current = null;
    };
  }, [correlationId, props.activeSessionId, props.isConnected]);

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
    if (!props.isConnected) {
      if (taskExperienceValidatedSessionRef.current === sessionId) {
        taskExperienceRevalidationPendingSessionRef.current = sessionId;
      }
      // A route is a connection-local activation hint, not reconnect authority.
      // The durable Task target journal remains available for the fresh
      // list/status/events/result recovery owned below.
      adoptCreatedProgressRoute(null);
      setTaskExperience(previous => ({
        ...previous,
        status: 'disconnected',
        session_id: sessionId,
        command: null,
        reason: 'FORMAL_P3_TASK_RECONNECT_REQUIRED',
      }));
      return;
    }
    const owner = new FormalP3TaskExperienceOwner({
      enabled: true,
      request: (method, params, requestId) => productRequest(method, params, { requestId }),
      on_snapshot: snapshot => {
        if (taskExperienceOwnerRef.current !== owner || activeSessionRef.current !== sessionId) return;
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
        }
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
      },
    });
    taskExperienceOwnerRef.current = owner;
    setTaskExperience(owner.snapshot());
    void owner.refresh(sessionId).catch(() => {
      // The owner publishes a fail-closed snapshot with no retained controls.
    });
    return () => {
      owner.close();
      if (taskExperienceOwnerRef.current === owner) taskExperienceOwnerRef.current = null;
    };
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

  const submitProductText = async (overrideText?: string, source: 'structured' | 'voice' = 'structured'): Promise<ProductTurnInput | null> => {
    const owner = activationOwnerRef.current;
    const ownerBinding = currentProductP2Binding();
    const turnText = overrideText ?? productInput;
    if (!owner || p2Activation.status !== 'active' || ownerBinding === null || !turnText.trim()) return null;
    const liveP1Status = p1VoiceOwnerRef.current?.status().status ?? p1VoiceStatus;
    if (productTextBlockedByP1Status(liveP1Status)) return null;
    if (source === 'structured') voiceTaskOriginRef.current = null;
    const recognized = recognizedVoiceRef.current;
    if (
      source === 'voice' &&
      (recognized === null ||
        recognized.session_id !== props.activeSessionId ||
        recognized.text !== turnText ||
        !recognizedVoiceMatchesProductBinding(recognized, ownerBinding))
    )
      return null;
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
        ownerHasUnsettledGenerationInterrupt(owner) ||
        owner.hasPendingSubmission() ||
        owner.hasPendingPresentationAck() ||
        owner.hasPendingPresentationFailure() ||
        owner.hasPendingBargeIn() ||
        owner.hasPendingGenerationInterrupt()
      ) {
        setProductTextStatus('failed');
        return null;
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
    try {
      await retryRetainedProductOperation({
        operation: () => owner.submitText(retained.input),
        is_current: () => props.isConnected && activationOwnerRef.current === owner && activeSessionRef.current === p2Activation.binding?.session_id,
      });
      if (activationOwnerRef.current === owner && pendingProductTurnRef.current === retained) {
        pendingProductTurnRef.current = null;
        setProductInput('');
        setProductTextStatus('waiting');
        // A previous notification.next may already have yielded after the
        // route became idle. Changing a ref (or setting waiting to the same
        // value) does not schedule this effect, so explicitly wake it for the
        // newly accepted foreground presentation.
        setP2NotificationWakeEpoch(epoch => epoch + 1);
        if (source === 'voice' && recognizedVoiceRef.current === recognized) {
          recognizedVoiceRef.current = null;
          voiceDraftBindingRef.current = null;
        }
        return retained.input;
      }
      return null;
    } catch {
      if (activationOwnerRef.current === owner) {
        if (!owner.hasPendingSubmission()) {
          pendingProductTurnRef.current = null;
        }
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
    if (selectionOwner === null || ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus)) return;
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

  const bootstrapCreatedP3ProgressRoute = async (
    taskId: string,
    binding: Readonly<NonNullable<ProductWebP2ActivationSnapshot['binding']>>,
  ): Promise<boolean> => {
    const isCurrentSession = () => mountedRef.current && activeSessionRef.current === binding.session_id;
    if (!isCurrentSession()) return false;
    if (progressTaskTargetRef.current !== taskId) {
      progressRef.current = null;
      pendingOwnedProgressRef.current.clear();
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
          return true;
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
      });
      setProductOutput(null);
      setProductTextReason(null);
      setProductTextStatus('submitting');
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
        });
        const retainsCurrentSession = mountedRef.current && activeSessionRef.current === binding.session_id;
        const retainsOriginVoiceLoop =
          retainsCurrentSession &&
          voiceLoopEnabledRef.current &&
          voiceLoopGenerationRef.current === originVoiceLoopGeneration;
        if (retainsOriginVoiceLoop) pendingForegroundPresentationRef.current = presentationFence;
        if (pendingUnifiedFinalRef.current?.input === input) {
          pendingUnifiedFinalRef.current = null;
        }
        if (recognizedVoiceRef.current === recognized) recognizedVoiceRef.current = null;
        if (!retainsCurrentSession) return;
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
          // Unified voice create already mutated Task authority.  Bootstrap
          // the exact task.status/task.events leaf before activation so replayed
          // accepted/running/terminal pushes always have an authority replica
          // to reconcile against, including tasks that finish very quickly.
          const bootstrapped = await bootstrapCreatedP3ProgressRoute(createdTaskId, binding);
          if (!bootstrapped) {
            if (pendingForegroundPresentationRef.current === presentationFence) {
              pendingForegroundPresentationRef.current = null;
            }
            return;
          }
        }
        if (!retainsOriginVoiceLoop) return;
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
        if (settledWithoutPresentation) scheduleProductVoiceLoopCapture();
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
    const hasCaptureAuthorityBarrier = () =>
      pendingProductTurnRef.current !== null ||
      pendingUnifiedFinalRef.current !== null ||
      (pendingForegroundPresentationRef.current !== null && !admitsGenerationCapture()) ||
      (pendingPresentationAttemptRef.current !== null && !retainedTerminalRecovery) ||
      pendingBargeInRef.current !== null ||
      Boolean(activationOwnerRef.current?.hasPendingSubmission()) ||
      Boolean(terminalNotificationCheckRequiredRef.current && activationOwnerRef.current?.hasPendingNotification()) ||
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
      console.warn(`live_voice_media_authority_refresh_failure reason=${reason} fallback=text visible=true`);
      if (activationOwnerRef.current === activationOwner && mountedRef.current && activeSessionRef.current === binding.session_id) {
        // Persist the state-loss barrier before cleanup so a reload cannot
        // reinterpret a later stale/closed tombstone as permission to prepare
        // a successor after the stable response-generation owner was lost.
        let barrierPersisted = false;
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
              journal.markResultUnknown(binding);
              barrierPersisted = true;
            }
          } catch {
            // Journal ownership/storage failure remains a local hard barrier;
            // exact server cleanup is still attempted below.
          }
        }
        // Close the possibly renewed/new server route now, but never mark the
        // predecessor closed or prepare a successor from unknown continuity.
        try {
          await activationOwner.closeWithRetry();
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
        request: productRequest,
        on_status: (status, reason) => {
          if (callbackOwner !== null && p1VoiceOwnerRef.current === callbackOwner) {
            if (status !== 'capturing' && terminalAnnouncementSpeechOwnerRef.current === callbackOwner) {
              terminalAnnouncementSpeechOwnerRef.current = null;
            }
            if (status === 'recognized' && terminalAnnouncementStateRef.current === 'suspending_capture') {
              p1VoiceCaptureBindingRef.current = null;
              updateTerminalAnnouncementState('fetching');
            }
            setP1VoiceStatus(status);
            setP1VoiceReason(reason);
            const diagnostics = callbackOwner.captureDiagnostics();
            setInterruptionDegradedReason(
              ['playing', 'recognized'].includes(status)
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
              const activeResponse = activeVoiceResponseRef.current;
              const response =
                activeResponse?.interaction_id === binding.interaction_id
                  ? activeResponse
                  : null;
              const seam: ProductLiveVoiceRecoveryDiagnostic['seam'] = response === null ? 'activation' : 'tts';
              if (status === 'cleanup_pending' && reason !== 'FORMAL_P1_CLEANUP_IN_PROGRESS') {
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
                if (!retainsExactTerminalTruth) {
                  publishProductRecoveryDiagnostic({
                    seam,
                    disposition: 'retrying',
                    reason: stableProductTextReason(reason, 'FORMAL_P1_CLEANUP_PENDING'),
                    binding,
                    response,
                  });
                }
              } else if (status === 'failed') {
                publishProductRecoveryDiagnostic({
                  seam,
                  disposition: 'terminal',
                  reason: stableProductTextReason(reason, 'PRODUCT_P1_ROUTE_FAILED'),
                  binding,
                  response,
                });
              } else if (['idle', 'capturing', 'recognized', 'closed'].includes(status)) {
                clearProductRecoveryDiagnostic({ seam: 'activation', binding });
              }
            }
          }
        },
        on_concurrent_capture_started: () => {
          if (
            voiceLoopEnabledRef.current &&
            voiceLoopGenerationRef.current === loopGeneration &&
            p1VoiceOwnerRef.current === owner
          ) {
            // The overlap uplink is already authoritative even while the
            // answer is still playing. Retain its P2 binding now so an EOT
            // racing the final playout frame can still stop, recognize, and
            // submit the captured utterance as the next turn.
            const binding = currentProductP2Binding();
            if (binding !== null) p1VoiceCaptureBindingRef.current = binding;
          }
        },
        on_barge_in_speech_start: () => {
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
      await startProductVoiceCaptureOwned();
    }).finally(() => {
      if (pendingP1VoiceStartRef.current?.promise === retained) pendingP1VoiceStartRef.current = null;
    });
    pendingP1VoiceStartRef.current = Object.freeze({ generation, promise: retained });
    return retained;
  };
  startP1VoiceHandlerRef.current = startProductVoiceCapture;

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
      const pauseOutcome = await retryOwner.pauseIdleCaptureForNotification();
      if (pauseOutcome === 'speech_active') {
        terminal.retry_pending = false;
        terminalAnnouncementSpeechOwnerRef.current = retryOwner;
        updateTerminalAnnouncementState('queued');
        return;
      }
      p1VoiceCaptureBindingRef.current = null;
      updateTerminalAnnouncementState('playing');
      activeVoiceResponseRef.current = terminal.disposition.response;
      await retryOwner.playAgentText({
        response: terminal.disposition.response,
        unit_id: terminal.disposition.unit_id,
        text: terminal.disposition.text,
      });
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
    void (async () => {
      const readiness = await settleCaptureBeforePlayout();
      if (
        !mountedRef.current ||
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
      p1VoiceCaptureBindingRef.current = null;
      updateTerminalAnnouncementState('playing');
      activeVoiceResponseRef.current = terminal.disposition.response;
      await voiceOwner.playAgentText({
        response: terminal.disposition.response,
        unit_id: terminal.disposition.unit_id,
        text: terminal.disposition.text,
      });
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
        // A real playout failure now: fall back to the ordinary recovery path.
        const reason = stableProductTextReason(error, 'PRODUCT_TERMINAL_ANNOUNCEMENT_AUDIO_FAILED');
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
        setTaskIntentText(recognition.text);
        p1VoiceCaptureBindingRef.current = null;
        await submitUnifiedRecognizedVoice(recognized, captureBinding);
      } else if (!isCurrentBinding()) {
        await owner.close().catch(() => undefined);
        if (p1VoiceOwnerRef.current === owner) p1VoiceOwnerRef.current = null;
      }
    } catch {
      // The owner publishes a content-free reason and retains cleanup.
    }
  };

  const stopProductVoiceCapture = (): Promise<void> => {
    const pending = pendingP1VoiceStopRef.current;
    if (pending !== null) return pending;
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
    if (p2Owner === null || p1Owner === null || response === null || p1Owner.status().status !== 'playing') return;
    bargeInSequenceRef.current += 1;
    const actionId = `product-barge-${bargeInSequenceRef.current}`;
    const locallyStopped = p1Owner.stopAgentPlayout(response);
    if (!locallyStopped) return;
    activeVoiceResponseRef.current = null;
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
        await pendingPresentation.playoutSettlement;
        await settleProductPresentationAck(pendingPresentation);
      }
      await p2Owner.bargeIn(retained.input);
      if (pendingBargeInRef.current === retained) {
        pendingBargeInRef.current = null;
      }
    } catch (error) {
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
    retainBoundedPresentedProductResponse(interruptedProductResponsesRef.current, input.response_id);
    const withdrawOptimisticRefusal = () => {
      interruptedProductResponsesRef.current.delete(input.response_id);
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
        // The fenced answer is gone and the replacement utterance is still
        // being captured, so the route is waiting for input again, not for a
        // response that can no longer arrive.
        setProductOutput(null);
        setProductTextStatus('idle');
        setProductTextReason(null);
      }
    } catch (error) {
      if (isDefinitiveProductOperationError(error)) {
        // The server definitively refused, so it fenced nothing: the answer is
        // still live and must not be silently dropped by our optimistic guess.
        withdrawOptimisticRefusal();
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

  function adoptFormalTaskIntentReceipt(receipt: FormalTaskIntentReceipt) {
    if (receipt.operation !== null) {
      setTaskIntentOperation(receipt.operation);
      setTaskIntentTaskId(receipt.task_id ?? '');
    }
    if (receipt.disposition !== 'dispatched' || receipt.operation === null) return;
    if (receipt.operation === 'task.create') {
      if (receipt.task_id === null || receipt.origin_id === null || receipt.task_control_binding === null) {
        throw new Error('formal natural-language task.create lost its exact task origin');
      }
      setTaskIntentTaskId(receipt.task_id);
      const owner = taskIntentOwnerRef.current;
      const sessionId = activeSessionRef.current;
      if (owner === null || sessionId === null) {
        throw new Error('formal natural-language task.create lost its post-create owner');
      }
      const handoff = Object.freeze({
        owner,
        session_id: sessionId,
        correlation_id: correlationId,
        task_id: receipt.task_id,
        origin: Object.freeze({ kind: receipt.source, id: receipt.origin_id }),
        task_control_binding: receipt.task_control_binding,
      });
      pendingNaturalCreateHandoffRef.current = handoff;
      // A natural-language create has already performed the Task mutation. Do
      // not activate its progress route until task.status + task.events have
      // established an exact FormalTaskControlLeaf for the returned task. The
      // progress producer replays the authoritative prefix after activation,
      // so even a fast terminal task remains visible and controllable.
      void inspectP3RetryEligibility({
        task_id: receipt.task_id,
        progress_origin: handoff.origin,
        replace_leaf: true,
        expected_task_control_binding: handoff.task_control_binding,
      });
    }
  }

  const submitFormalTaskIntent = async (source: 'text' | 'voice'): Promise<FormalTaskIntentReceipt | null> => {
    const owner = taskIntentOwnerRef.current;
    const sessionId = props.activeSessionId;
    if (
      owner === null ||
      sessionId === null ||
      !props.isConnected ||
      p3MutationOwnerRef.current?.hasPendingMutation() === true ||
      pendingFormalP3MutationRef.current !== null ||
      ['issuing', 'confirmed', 'mutating'].includes(p3MutationStatus) ||
      !taskIntentText.trim() ||
      (taskIntentOperation !== 'task.create' && !taskIntentTaskId.trim())
    ) {
      return null;
    }
    try {
      let pending: Promise<FormalTaskIntentReceipt>;
      if (source === 'voice') {
        const recognized = recognizedVoiceRef.current;
        const binding = currentProductP2Binding();
        if (recognized === null || binding === null || recognized.text !== taskIntentText || !recognizedVoiceMatchesProductBinding(recognized, binding)) {
          return null;
        }
        if (p3TaskInstruction !== recognized.text) setP3TaskInstruction(recognized.text);
        const origin = await commitRecognizedVoiceTaskOrigin();
        if (origin === null || origin.correlation_id !== binding.correlation_id) return null;
        pending = owner.submitVoice({
          origin: {
            session_id: origin.session_id,
            correlation_id: origin.correlation_id,
            interaction_id: origin.interaction_id,
            turn_id: origin.turn_id,
            commit_id: origin.commit_id,
          },
          operation: taskIntentOperation,
          task_id: taskIntentOperation === 'task.create' ? null : taskIntentTaskId.trim(),
        });
      } else {
        pending = owner.submitText({
          session_id: sessionId,
          correlation_id: correlationId,
          text: taskIntentText,
          operation: taskIntentOperation,
          task_id: taskIntentOperation === 'task.create' ? null : taskIntentTaskId.trim(),
        });
      }
      setTaskIntentSnapshot(owner.snapshot());
      const receipt = await pending;
      if (taskIntentOwnerRef.current !== owner || activeSessionRef.current !== sessionId) return null;
      adoptFormalTaskIntentReceipt(receipt);
      setTaskIntentSnapshot(owner.snapshot());
      return receipt;
    } catch {
      if (taskIntentOwnerRef.current === owner) setTaskIntentSnapshot(owner.snapshot());
      return null;
    }
  };

  async function inspectP3RetryEligibility(
    input: Readonly<{
      task_id?: string;
      follow_nonterminal?: boolean;
      progress_origin?: Readonly<{ kind: 'text' | 'voice'; id: string }> | null;
      replace_leaf?: boolean;
      expected_task_control_binding?: FormalTaskIntentTaskControlBinding;
      throw_on_failure?: boolean;
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
          pendingOwnedProgressRef.current.clear();
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
    const taskIntentAuthority = taskIntentOwnerRef.current?.snapshot() ?? null;
    if (
      (taskIntentAuthority !== null && (taskIntentAuthority.pending_confirmation !== null || taskIntentAuthority.retained_transport)) ||
      pendingNaturalCreateHandoffRef.current !== null ||
      (currentSpeechConfirmation !== null && currentSpeechConfirmation !== recognizedSpeechDispatch) ||
      (recognizedSpeechDispatch !== null &&
        (recognizedSpeechDispatch.intent !== 'task' ||
          recognizedSpeechDispatch.task_route === 'natural' ||
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
    const displayedText = pending.intent === 'agent' ? productInput : pending.task_route === 'natural' ? taskIntentText : p3TaskInstruction;
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
      if (pending.task_route === 'natural') {
        await submitFormalTaskIntent('voice');
      } else {
        await issueP3MutationConfirmation(dispatching);
      }
    } finally {
      if (recognizedSpeechConfirmationRef.current === dispatching) {
        updateRecognizedSpeechConfirmation(null);
      }
    }
  };

  const executeP3Mutation = async () => {
    const taskIntentAuthority = taskIntentOwnerRef.current?.snapshot() ?? null;
    if (
      (taskIntentAuthority !== null && (taskIntentAuthority.pending_confirmation !== null || taskIntentAuthority.retained_transport)) ||
      pendingNaturalCreateHandoffRef.current !== null
    )
      return;
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
        const activationSnapshot = await owner.start({
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
        const handoff = pendingNaturalCreateHandoffRef.current;
        if (
          activationSnapshot.status === 'active' &&
          activationSnapshot.binding !== null &&
          handoff !== null &&
          handoff.owner === taskIntentOwnerRef.current &&
          handoff.session_id === ownedSessionId &&
          handoff.session_id === activationSnapshot.binding.session_id &&
          handoff.correlation_id === activationSnapshot.binding.correlation_id &&
          handoff.task_id === createdProgressTaskId &&
          handoff.task_id === activationSnapshot.binding.task_id &&
          handoff.origin.kind === ownedProgressOrigin?.kind &&
          handoff.origin.id === ownedProgressOrigin?.id &&
          handoff.origin.id === activationSnapshot.binding.origin_id
        ) {
          try {
            const settled = handoff.owner.completePostCreateBinding({
              session_id: handoff.session_id,
              correlation_id: handoff.correlation_id,
              task_id: handoff.task_id,
              origin_id: handoff.origin.id,
            });
            if (pendingNaturalCreateHandoffRef.current === handoff) {
              pendingNaturalCreateHandoffRef.current = null;
              setTaskIntentSnapshot(settled);
            }
          } catch {
            if (taskIntentOwnerRef.current === handoff.owner) {
              setTaskIntentSnapshot(handoff.owner.snapshot());
            }
          }
        }
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
  }, [correlationId, createdProgressRoute, props.activeSessionId, props.isConnected]);

  const productTextTransportRetained = Boolean(
    pendingProductTurnRef.current ||
    pendingUnifiedFinalRef.current ||
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
      owner?.hasPendingGenerationInterrupt() ||
      taskIntentSnapshot.retained_transport
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
    setTaskIntentText(value);
    setP3TaskInstruction(value);
  };

  const setProductCommandRouteSafely = (route: 'agent' | 'task') => {
    if (
      (route === 'task' && !FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION) ||
      taskIntentSnapshot.pending_confirmation !== null ||
      taskIntentSnapshot.retained_transport ||
      pendingNaturalCreateHandoffRef.current !== null ||
      productOperationRetained
    )
      return;
    setProductCommandRoute(route);
  };

  const setProductTaskOperationSafely = (operation: FormalTaskIntentOperation) => {
    if (taskIntentSnapshot.pending_confirmation !== null || taskIntentSnapshot.retained_transport || pendingNaturalCreateHandoffRef.current !== null) return;
    setTaskIntentOperation(operation);
    setTaskIntentSnapshot(taskIntentOwnerRef.current?.cancelPendingConfirmation() ?? taskIntentSnapshot);
    if (operation !== 'task.create' && !taskIntentTaskId.trim()) {
      const latestTaskId = progress?.task_id ?? taskIntentSnapshot.receipt?.task_id ?? p3TargetTaskId.trim();
      if (latestTaskId) setTaskIntentTaskId(latestTaskId);
    }
  };

  const setProductTaskIdSafely = (taskId: string) => {
    if (taskIntentSnapshot.pending_confirmation !== null || taskIntentSnapshot.retained_transport || pendingNaturalCreateHandoffRef.current !== null) return;
    setTaskIntentTaskId(taskId);
  };

  const cancelProductTaskConfirmation = () => {
    const owner = taskIntentOwnerRef.current;
    if (owner === null || taskIntentSnapshot.retained_transport) return;
    setTaskIntentSnapshot(owner.cancelPendingConfirmation());
    setProductInput('');
    setTaskIntentText('');
  };

  const submitProductCommand = async () => {
    const recognized = recognizedVoiceRef.current;
    const binding = currentProductP2Binding();
    const exactVoiceDraft =
      recognized !== null &&
      recognized.session_id === props.activeSessionId &&
      recognized.text === productInput &&
      recognizedVoiceMatchesProductBinding(recognized, binding);
    if (productCommandRoute === 'agent') {
      await submitProductText(undefined, exactVoiceDraft ? 'voice' : 'structured');
      return;
    }
    if (!FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION || taskIntentSnapshot.retained_transport || !taskIntentText.trim()) return;
    const receipt = await submitFormalTaskIntent(exactVoiceDraft ? 'voice' : 'text');
    if (receipt !== null) {
      setProductInput('');
      setTaskIntentText('');
    }
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
    clearScheduledProductVoiceLoopCapture();
    voiceLoopEnabledRef.current = false;
    voiceLoopGenerationRef.current += 1;
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
    if (!voiceLoopEnabledRef.current) {
      voiceLoopGenerationRef.current += 1;
      voiceLoopEnabledRef.current = true;
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

  useEffect(() => {
    const taskControlsLocked =
      taskIntentSnapshot.pending_confirmation !== null || taskIntentSnapshot.retained_transport || pendingNaturalCreateHandoffRef.current !== null;
    props.onProductVoiceStateChange?.(
      Object.freeze({
        available: productVoiceAvailable,
        p1_status: p1VoiceStatus,
        p1_reason: p1VoiceReason,
        interruption_degraded_reason: interruptionDegradedReason,
        input: productInput,
        output: productOutput,
        text_status: productTextStatus,
        text_reason: productTextReason,
        confirmation_phase: recognizedSpeechConfirmation?.phase ?? editedVoiceDraftConfirmation?.phase ?? null,
        operation_retained: productOperationRetained,
        command_route: productCommandRoute,
        task_available: FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION && props.isConnected,
        task_operation: taskIntentOperation,
        task_id: taskIntentTaskId,
        task_status: taskIntentSnapshot.status,
        task_reason: taskIntentSnapshot.reason,
        task_confirmation_form: taskIntentSnapshot.pending_confirmation?.form ?? null,
        task_result: formalTaskIntentResultSummary(taskIntentSnapshot.receipt),
        task_progress_task_id: progress?.task_id ?? null,
        task_progress_state: progress?.state ?? null,
        task_progress_delivery_mode: progress?.delivery_mode ?? null,
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
        task_controls_locked: taskControlsLocked,
        task_experience: taskExperience,
      }),
    );
  }, [
    p1VoiceReason,
    p1VoiceStatus,
    interruptionDegradedReason,
    productInput,
    productOperationRetained,
    productOutput,
    productTextReason,
    productTextStatus,
    productVoiceAvailable,
    productCommandRoute,
    progress?.delivery_mode,
    progress?.attempt_id,
    progress?.source_event.event_id,
    progress?.source_event.seq,
    progress?.state,
    progress?.task_id,
    progressAck,
    props.onProductVoiceStateChange,
    props.isConnected,
    editedVoiceDraftConfirmation?.phase,
    recognizedSpeechConfirmation?.phase,
    recoveryDiagnostic,
    taskIntentOperation,
    taskIntentSnapshot,
    taskIntentTaskId,
    adjustmentNotification,
    terminalAnnouncementState,
    terminalNotification,
    taskExperience,
  ]);

  useEffect(() => {
    const control = Object.freeze<ProductLiveVoiceSurfaceControl>({
      start: startProductVoiceLoop,
      stop: () => (p1VoiceOwnerRef.current?.status().status === 'playing' ? stopProductVoicePlayout() : stopProductVoiceCapture()),
      closeSession: closeProductVoiceSession,
      updateInput: handleProductCommandInput,
      submit: handleProductSubmit,
      submitCommand: () => void submitProductCommand(),
      setCommandRoute: setProductCommandRouteSafely,
      setTaskOperation: setProductTaskOperationSafely,
      setTaskId: setProductTaskIdSafely,
      cancelTaskConfirmation: cancelProductTaskConfirmation,
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
      progressDomRef={progressDomRef}
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
      taskIntentEnabled={FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION && props.isConnected}
      taskIntentOperation={taskIntentOperation}
      taskIntentText={taskIntentText}
      taskIntentTaskId={taskIntentTaskId}
      taskIntentSnapshot={taskIntentSnapshot}
      onTaskIntentOperation={operation => {
        if (taskIntentSnapshot.pending_confirmation !== null || taskIntentSnapshot.retained_transport) return;
        updateRecognizedSpeechConfirmation(null);
        setTaskIntentOperation(operation);
        setTaskIntentSnapshot(taskIntentOwnerRef.current?.cancelPendingConfirmation() ?? taskIntentSnapshot);
      }}
      onTaskIntentText={value => {
        if (taskIntentSnapshot.retained_transport) return;
        updateRecognizedSpeechConfirmation(null);
        if (value !== recognizedVoiceRef.current?.text) recognizedVoiceRef.current = null;
        setTaskIntentText(value);
      }}
      onTaskIntentTaskId={value => {
        if (taskIntentSnapshot.pending_confirmation !== null || taskIntentSnapshot.retained_transport) return;
        updateRecognizedSpeechConfirmation(null);
        setTaskIntentTaskId(value);
      }}
      onTaskIntentSubmit={() => {
        const recognized = recognizedVoiceRef.current;
        const binding = currentProductP2Binding();
        if (
          recognized !== null &&
          recognized.text === taskIntentText &&
          recognized.session_id === props.activeSessionId &&
          binding !== null &&
          recognizedVoiceMatchesProductBinding(recognized, binding)
        ) {
          updateRecognizedSpeechConfirmation(
            Object.freeze({
              intent: 'task',
              task_route: 'natural',
              phase: 'confirming',
              session_id: recognized.session_id,
              text: recognized.text,
              correlation_id: binding.correlation_id,
              interaction_id: binding.interaction_id,
              activation_id: binding.activation_id,
              activation_generation: binding.activation_generation,
            }),
          );
          return;
        }
        void submitFormalTaskIntent('text');
      }}
      onTaskIntentCancelPending={() => {
        const owner = taskIntentOwnerRef.current;
        if (owner !== null) setTaskIntentSnapshot(owner.cancelPendingConfirmation());
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

export interface LiveVoiceIntegratedRoutePanelViewProps {
  manifest: Readonly<IntegratedWebRouteManifest>;
  platform: Readonly<WebPlatformDiagnosticsSnapshot> | null;
  progress?: Readonly<ProductTextProgressEvent> | null;
  progressAck?: 'idle' | 'pending' | 'acknowledged' | 'failed';
  progressDomRef?: RefObject<HTMLDivElement>;
  p2Activation?: Readonly<ProductWebP2ActivationSnapshot> | null;
  p3Activation?: Readonly<ProductWebP3ProgressSnapshot> | null;
  productInput?: string;
  productOutput?: string | null;
  productTextStatus?: 'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed';
  p1VoiceEnabled?: boolean;
  p1VoiceStatus?: ProductP1VoiceStatus;
  p1VoiceReason?: string | null;
  deviceSelection?: Readonly<BrowserAudioDeviceSelectionSnapshot> | null;
  draftInputDeviceToken?: string;
  draftOutputDeviceToken?: string;
  onLoadAudioDevices?: () => void;
  onDraftInputDevice?: (token: string) => void;
  onDraftOutputDevice?: (token: string) => void;
  onApplyAudioDevices?: () => void;
  onP1VoiceStart?: () => void;
  onP1VoiceStop?: () => void;
  productOperationRetained?: boolean;
  productTextTransportRetained?: boolean;
  onProductInput?: (value: string) => void;
  onProductSubmit?: () => void;
  recognizedSpeechConfirmation?: 'agent' | 'task' | null;
  recognizedSpeechDispatching?: boolean;
  onRecognizedSpeechConfirm?: () => void;
  onRecognizedSpeechCancel?: () => void;
  taskIntentEnabled?: boolean;
  taskIntentOperation?: FormalTaskIntentOperation;
  taskIntentText?: string;
  taskIntentTaskId?: string;
  taskIntentSnapshot?: FormalTaskIntentOwnerSnapshot | null;
  onTaskIntentOperation?: (value: FormalTaskIntentOperation) => void;
  onTaskIntentText?: (value: string) => void;
  onTaskIntentTaskId?: (value: string) => void;
  onTaskIntentSubmit?: () => void;
  onTaskIntentCancelPending?: () => void;
  p3MutationEnabled?: boolean;
  p3MutationOperation?: 'task.create' | 'task.cancel' | 'task.retry';
  p3TaskName?: string;
  p3TaskInstruction?: string;
  p3TargetTaskId?: string;
  p3MutationStatus?: ProductP3MutationStatus;
  p3MutationReason?: string | null;
  p3MutationRetained?: boolean;
  p3RetryEligible?: boolean;
  p3RetryAttemptNumber?: number | null;
  p3RetryInspectionStatus?: 'idle' | 'checking' | 'eligible' | 'ineligible' | 'failed';
  p3RetryInspectionReason?: string | null;
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
  progressDomRef,
  p2Activation = null,
  p3Activation = null,
  productInput = '',
  productOutput = null,
  productTextStatus = 'idle',
  p1VoiceEnabled = false,
  p1VoiceStatus = 'closed',
  p1VoiceReason = null,
  deviceSelection = null,
  draftInputDeviceToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  draftOutputDeviceToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  onLoadAudioDevices,
  onDraftInputDevice,
  onDraftOutputDevice,
  onApplyAudioDevices,
  onP1VoiceStart,
  onP1VoiceStop,
  productOperationRetained = false,
  productTextTransportRetained,
  onProductInput,
  onProductSubmit,
  recognizedSpeechConfirmation = null,
  recognizedSpeechDispatching = false,
  onRecognizedSpeechConfirm,
  onRecognizedSpeechCancel,
  taskIntentEnabled = false,
  taskIntentOperation = 'task.create',
  taskIntentText = '',
  taskIntentTaskId = '',
  taskIntentSnapshot = null,
  onTaskIntentOperation,
  onTaskIntentText,
  onTaskIntentTaskId,
  onTaskIntentSubmit,
  onTaskIntentCancelPending,
  p3MutationEnabled = false,
  p3MutationOperation = 'task.create',
  p3TaskName = '',
  p3TaskInstruction = '',
  p3TargetTaskId = '',
  p3MutationStatus = 'idle',
  p3MutationReason = null,
  p3MutationRetained = false,
  p3RetryEligible = false,
  p3RetryAttemptNumber = null,
  p3RetryInspectionStatus = 'idle',
  p3RetryInspectionReason = null,
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
  const structuredP3MutationLocked =
    productOperationRetained ||
    recognizedSpeechConfirmation !== null ||
    ['issuing', 'confirmed', 'mutating'].includes(p3MutationStatus) ||
    p3RetryInspectionStatus === 'checking' ||
    (p3MutationStatus === 'failed' && p3MutationRetained);
  const p3MutationLocked = structuredP3MutationLocked || taskIntentSnapshot?.pending_confirmation != null || taskIntentSnapshot?.retained_transport === true;
  const resolvedProductTextTransportRetained = productTextTransportRetained ?? (productOperationRetained && recognizedSpeechConfirmation === null);
  const productTextLocked =
    recognizedSpeechDispatching ||
    ['submitting', 'waiting', 'presented'].includes(productTextStatus) ||
    resolvedProductTextTransportRetained ||
    ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus);
  const deviceSelectionLocked =
    productOperationRetained ||
    ['loading', 'refreshing'].includes(deviceSelection?.status ?? '') ||
    ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus);
  const taskIntentBindingLocked =
    structuredP3MutationLocked ||
    taskIntentSnapshot?.pending_confirmation != null ||
    (taskIntentSnapshot?.status === 'clarification' && taskIntentSnapshot.pending_confirmation == null) ||
    taskIntentSnapshot?.retained_transport === true ||
    taskIntentSnapshot?.status === 'submitting';
  const taskIntentTextLocked =
    structuredP3MutationLocked ||
    (taskIntentSnapshot?.status === 'clarification' && taskIntentSnapshot.pending_confirmation == null) ||
    taskIntentSnapshot?.retained_transport === true ||
    taskIntentSnapshot?.status === 'submitting';
  const taskIntentResultSummary = formalTaskIntentResultSummary(taskIntentSnapshot?.receipt);
  // Retain the established diagnostic harness behind the hidden/aria-hidden
  // owner surface so lifecycle regressions stay testable. The product bar is
  // the only visible Live Voice UI and never exposes these controls.
  const legacyManualControls = true;

  return (
    <details
      className="live-voice-integrated"
      data-composition={manifest.composition_state}
      data-testid="live-voice-integrated-route"
      aria-hidden="true"
      hidden
    >
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
              {p3Activation.requested_origin_kind && p3Activation.effective_origin_kind && (
                <DiagnosticsFact
                  label="Task progress activation origin"
                  value={`${p3Activation.requested_origin_kind}->${p3Activation.effective_origin_kind}`}
                />
              )}
              {p3Activation.voice_progress && <DiagnosticsFact label="Task progress voice status" value={p3Activation.voice_progress} />}
              {p3Activation.fallback_reason && <DiagnosticsFact label="Task progress activation fallback" value={p3Activation.fallback_reason} />}
            </div>
          )}
          {legacyManualControls && p1VoiceEnabled && onP1VoiceStart && onP1VoiceStop && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-product-voice">
              <strong>Formal P1 voice</strong>
              {deviceSelection && onLoadAudioDevices && onDraftInputDevice && onDraftOutputDevice && onApplyAudioDevices && (
                <fieldset className="live-voice-integrated__device-selection" data-testid="live-voice-integrated-device-selection">
                  <legend>{t('liveVoice.integrated.audioDevices.title')}</legend>
                  <span className="live-voice-integrated__progress-note">{t('liveVoice.integrated.audioDevices.memoryOnly')}</span>
                  <button type="button" onClick={onLoadAudioDevices} disabled={deviceSelectionLocked || deviceSelection.status === 'loading'}>
                    {deviceSelection.status === 'loading'
                      ? t('liveVoice.integrated.audioDevices.loading')
                      : deviceSelection.status === 'refreshing'
                        ? t('liveVoice.integrated.audioDevices.refreshing')
                        : t('liveVoice.integrated.audioDevices.load')}
                  </button>
                  <label>
                    {t('liveVoice.integrated.audioDevices.input')}
                    <select value={draftInputDeviceToken} onChange={event => onDraftInputDevice(event.target.value)} disabled={deviceSelectionLocked}>
                      <option value={BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN}>{t('liveVoice.integrated.audioDevices.systemDefault')}</option>
                      {deviceSelection.inputs.map(option => (
                        <option value={option.token} key={option.token}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t('liveVoice.integrated.audioDevices.output')}
                    <select value={draftOutputDeviceToken} onChange={event => onDraftOutputDevice(event.target.value)} disabled={deviceSelectionLocked}>
                      <option value={BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN}>{t('liveVoice.integrated.audioDevices.systemDefault')}</option>
                      {deviceSelection.outputs.map(option => (
                        <option value={option.token} key={option.token}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" onClick={onApplyAudioDevices} disabled={deviceSelectionLocked || deviceSelection.status !== 'ready'}>
                    {t('liveVoice.integrated.audioDevices.apply')}
                  </button>
                  <DiagnosticsFact label={t('liveVoice.integrated.audioDevices.status')} value={deviceSelection.status} />
                  {deviceSelection.reason !== null && <DiagnosticsFact label={t('liveVoice.integrated.audioDevices.reason')} value={deviceSelection.reason} />}
                </fieldset>
              )}
              <span className="live-voice-integrated__progress-note">
                Dedicated same-origin PCM route → Gateway batch Speech → committed Agent text → Gateway synthesis.
              </span>
              <span className="live-voice-integrated__progress-note">
                One spoken utterance retains at most {PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 1000} seconds of captured audio, measured from the recognized start
                of speech. Silent listening and overlapping playback rotate the capture automatically and do not count toward the limit. Speak and press Stop
                and recognize before the limit.
              </span>
              {p1VoiceStatus === 'capturing' || p1VoiceStatus === 'playing' ? (
                <button type="button" onClick={onP1VoiceStop}>
                  {p1VoiceStatus === 'playing' ? 'Stop playback' : 'Stop and recognize'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onP1VoiceStart}
                  disabled={
                    productOperationRetained ||
                    ['loading', 'refreshing'].includes(deviceSelection?.status ?? '') ||
                    !['idle', 'recognized'].includes(p1VoiceStatus)
                  }
                >
                  Start formal voice turn
                </button>
              )}
              <DiagnosticsFact label="P1 status" value={p1VoiceStatus} />
              {p1VoiceReason !== null && <DiagnosticsFact label="P1 reason" value={p1VoiceReason} />}
              {p1VoiceReason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON && (
                <span className="live-voice-integrated__progress-note">
                  The utterance exceeded its 30-second budget; the expired capture was discarded without a new Speech or Agent submission. Refresh to start
                  again.
                </span>
              )}
            </div>
          )}
          {legacyManualControls && p2Activation?.status === 'active' && onProductInput && onProductSubmit && (
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
              <button type="submit" disabled={!productInput.trim() || productTextLocked || recognizedSpeechConfirmation !== null}>
                {t('liveVoice.integrated.textRoute.submit')}
              </button>
              <DiagnosticsFact label={t('liveVoice.integrated.textRoute.status')} value={productTextStatus} />
              {productOutput !== null && <output aria-live="polite">{productOutput}</output>}
            </form>
          )}
          {legacyManualControls && recognizedSpeechConfirmation !== null && onRecognizedSpeechConfirm && onRecognizedSpeechCancel && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-recognized-confirmation" role="note">
              <strong>{t('liveVoice.integrated.recognizedConfirmation.title')}</strong>
              <span className="live-voice-integrated__progress-note">{t(`liveVoice.integrated.recognizedConfirmation.${recognizedSpeechConfirmation}`)}</span>
              <button type="button" onClick={onRecognizedSpeechConfirm}>
                {t('liveVoice.integrated.recognizedConfirmation.confirm')}
              </button>
              <button type="button" onClick={onRecognizedSpeechCancel}>
                {t('liveVoice.integrated.recognizedConfirmation.cancel')}
              </button>
            </div>
          )}
          {legacyManualControls && taskIntentEnabled && onTaskIntentOperation && onTaskIntentText && onTaskIntentTaskId && onTaskIntentSubmit && (
            <form
              className="live-voice-integrated__text-route"
              data-testid="live-voice-integrated-formal-task-intent"
              onSubmit={event => {
                event.preventDefault();
                onTaskIntentSubmit();
              }}
            >
              <strong>Bounded natural-language Task route</strong>
              <span className="live-voice-integrated__progress-note">
                Exact English/Chinese create, status and cancel forms only. Ambiguous language issues no Task command.
              </span>
              <select
                aria-label="Task intent operation hint"
                value={taskIntentOperation}
                disabled={taskIntentBindingLocked}
                onChange={event => {
                  const value = event.target.value;
                  onTaskIntentOperation(value === 'task.status' || value === 'task.cancel' ? value : 'task.create');
                }}
              >
                <option value="task.create">task.create</option>
                <option value="task.status">task.status</option>
                <option value="task.cancel">task.cancel</option>
              </select>
              {taskIntentOperation !== 'task.create' && (
                <input
                  aria-label="Exact Task intent target"
                  value={taskIntentTaskId}
                  disabled={taskIntentBindingLocked}
                  onChange={event => onTaskIntentTaskId(event.target.value)}
                  placeholder="task-abc_123"
                  maxLength={128}
                />
              )}
              <textarea
                aria-label="Committed natural-language Task intent"
                value={taskIntentText}
                disabled={taskIntentTextLocked}
                onChange={event => onTaskIntentText(event.target.value)}
                placeholder={
                  taskIntentOperation === 'task.create'
                    ? 'create task: inspect the repository'
                    : taskIntentOperation === 'task.status'
                      ? 'task status task-abc_123'
                      : 'cancel task task-abc_123'
                }
                maxLength={8192}
              />
              {taskIntentSnapshot?.pending_confirmation && (
                <div role="note" data-testid="live-voice-integrated-task-intent-confirmation">
                  <span className="live-voice-integrated__progress-note">
                    A destructive request is pending. Type or speak the following as a new committed turn; this notice is not confirmation authority.
                  </span>
                  <code>{taskIntentSnapshot.pending_confirmation.form}</code>
                  {onTaskIntentCancelPending && (
                    <button type="button" onClick={onTaskIntentCancelPending} disabled={taskIntentSnapshot.retained_transport}>
                      Abandon pending request
                    </button>
                  )}
                </div>
              )}
              {taskIntentSnapshot?.status === 'clarification' && taskIntentSnapshot.pending_confirmation === null && (
                <div role="note" data-testid="live-voice-integrated-task-intent-clarification">
                  <span className="live-voice-integrated__progress-note">
                    This committed turn needs a new, unambiguous request. Abandon it before entering the replacement turn.
                  </span>
                  {onTaskIntentCancelPending && (
                    <button type="button" onClick={onTaskIntentCancelPending} disabled={taskIntentSnapshot.retained_transport}>
                      Abandon clarification
                    </button>
                  )}
                </div>
              )}
              <button
                type="submit"
                disabled={taskIntentTextLocked || !taskIntentText.trim() || (taskIntentOperation !== 'task.create' && !taskIntentTaskId.trim())}
              >
                Submit committed Task turn
              </button>
              <DiagnosticsFact label="Task intent status" value={taskIntentSnapshot?.status ?? 'idle'} />
              {taskIntentSnapshot?.reason && <DiagnosticsFact label="Task intent reason" value={taskIntentSnapshot.reason} />}
              {taskIntentResultSummary !== null && <DiagnosticsFact label="Task intent result" value={taskIntentResultSummary} />}
            </form>
          )}
          {legacyManualControls && p3MutationEnabled && onP3MutationOperation && onP3TaskName && onP3TaskInstruction && onP3TargetTaskId && onP3Issue && onP3Execute && (
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
                <button type="button" onClick={onP3InspectRetry} disabled={!p3TargetTaskId.trim() || p3MutationLocked}>
                  {t('liveVoice.integrated.taskControl.inspectRetry')}
                </button>
              )}
              <DiagnosticsFact
                label={t('liveVoice.integrated.taskControl.retryStatus')}
                value={p3RetryEligible && p3RetryAttemptNumber !== null ? `eligible:${p3RetryAttemptNumber}/3` : p3RetryInspectionStatus}
              />
              {p3RetryInspectionReason !== null && (
                <DiagnosticsFact label={t('liveVoice.integrated.taskControl.retryReason')} value={p3RetryInspectionReason} />
              )}
              {p3MutationStatus === 'confirmed' ? (
                <button type="button" onClick={onP3Execute}>
                  {t('liveVoice.integrated.taskControl.execute')}
                </button>
              ) : (
                <button type="button" onClick={onP3Issue} disabled={p3MutationLocked || (p3MutationOperation === 'task.retry' && !p3RetryEligible)}>
                  {t('liveVoice.integrated.taskControl.confirm')}
                </button>
              )}
              <DiagnosticsFact label={t('liveVoice.integrated.taskControl.status')} value={p3MutationStatus} />
              {p3MutationReason !== null && <DiagnosticsFact label={t('liveVoice.integrated.taskControl.reason')} value={p3MutationReason} />}
            </div>
          )}
        </div>

        {progress && (
          <div
            key={progress.delivery_id}
            ref={progressDomRef}
            className="live-voice-integrated__section"
            aria-label={t('liveVoice.integrated.progress.title')}
            data-testid="live-voice-integrated-product-progress"
            data-delivery-id={progress.delivery_id}
            data-presentation-binding={
              progress.consumption_mode === 'presentation' ? productTextProgressPresentationBinding(progress) : undefined
            }
            data-session-id={progress.session_id}
            data-subject-id={progress.source_event.scope.subject_id}
            data-project-id={progress.project_id}
            data-task-id={progress.task_id}
            data-attempt-id={progress.attempt_id}
            data-event-id={progress.source_event.event_id}
            data-event-seq={String(progress.source_event.seq)}
            data-generation-id={progress.generation_id}
            data-generation={String(progress.generation)}
            data-presentation-class={progress.presentation_class ?? undefined}
            data-response-interaction-id={progress.response_ref?.interaction_id}
            data-response-id={progress.response_ref?.response_id}
            data-response-generation={progress.response_ref ? String(progress.response_ref.response_generation) : undefined}
            data-unit-id={progress.unit_id ?? undefined}
            data-expected-event-head={progress.expected_event_head === null ? undefined : String(progress.expected_event_head)}
            data-result-source-event-id={progress.consumption_mode === 'presentation' ? progress.result_source_event_id ?? '' : undefined}
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
              <DiagnosticsFact label="Task progress origin" value={`${progress.requested_origin_kind}->${progress.effective_origin_kind}`} />
              <DiagnosticsFact label="Task progress delivery mode" value={progress.delivery_mode} />
              {progress.fallback_reason && <DiagnosticsFact label="Task progress fallback" value={progress.fallback_reason} />}
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
                  ? `capture:${platform.aio_capability.capture_pcm_f32}; playout:${platform.aio_capability.playout_pcm_f32}; output_selection:${platform.aio_capability.output_device_selection}; wired:false`
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
