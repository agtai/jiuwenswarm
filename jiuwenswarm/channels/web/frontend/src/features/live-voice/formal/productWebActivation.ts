import { canonicalJson, canonicalJsonBytes } from './liveVoiceContractV2.js';

export const PRODUCT_P2_ACTIVATE_METHOD = 'live_voice.composition.p2.activate' as const;
export const PRODUCT_P2_CLOSE_METHOD = 'live_voice.composition.p2.close' as const;
export const PRODUCT_P2_SUBMIT_METHOD = 'live_voice.composition.p2.submit' as const;
export const PRODUCT_P2_NOTIFICATION_NEXT_METHOD = 'live_voice.composition.p2.notification.next' as const;
export const PRODUCT_P2_PRESENTATION_ACK_METHOD = 'live_voice.composition.p2.presentation.ack' as const;
export const PRODUCT_P2_PRESENTATION_FAILED_METHOD = 'live_voice.composition.p2.presentation.failed' as const;
export const PRODUCT_P2_BARGE_IN_METHOD = 'live_voice.composition.p2.barge_in' as const;
export const PRODUCT_P2_INTERRUPT_GENERATION_METHOD = 'live_voice.composition.p2.interrupt_generation' as const;
export const PRODUCT_P3_CONFIRMATION_ISSUE_METHOD = 'live_voice.composition.p3.confirmation.issue' as const;
export const PRODUCT_P3_MUTATE_METHOD = 'live_voice.composition.p3.mutate' as const;
export const PRODUCT_P3_TASK_LIST_METHOD = 'live_voice.task.list' as const;
export const PRODUCT_P3_TASK_STATUS_METHOD = 'live_voice.task.status' as const;
export const PRODUCT_P3_TASK_EVENTS_METHOD = 'live_voice.task.events' as const;
export const PRODUCT_P3_PROGRESS_ACTIVATE_METHOD = 'live_voice.composition.p3.progress.activate' as const;
export const PRODUCT_P3_PROGRESS_CLOSE_METHOD = 'live_voice.composition.p3.progress.close' as const;

type JsonObject = Readonly<Record<string, unknown>>;

export type ProductWebP2ActivationStatus = 'disabled' | 'idle' | 'activating' | 'active' | 'unavailable' | 'cleanup_pending' | 'closed';

export interface ProductWebP2ActivationBinding {
  readonly session_id: string;
  readonly correlation_id: string;
  readonly interaction_id: string;
  readonly activation_id: string;
  readonly activation_generation: number;
}

export interface ProductWebP2ActivationSnapshot {
  readonly status: ProductWebP2ActivationStatus;
  readonly binding: ProductWebP2ActivationBinding | null;
  readonly reason: string | null;
}

export interface ProductWebP3ProgressBinding {
  readonly session_id: string;
  readonly task_id: string;
  readonly correlation_id: string;
  readonly origin_id: string;
  readonly generation_id: string;
  readonly generation: number;
}

export interface ProductWebP3ProgressSnapshot {
  readonly status: ProductWebP2ActivationStatus;
  readonly binding: ProductWebP3ProgressBinding | null;
  readonly reason: string | null;
  readonly requested_origin_kind: 'text' | 'voice' | null;
  readonly effective_origin_kind: 'text' | 'voice' | null;
  readonly voice_progress: 'available' | 'unavailable' | null;
  readonly voice_reason: string | null;
  readonly fallback_reason: string | null;
}

type ProductWebCloseRetryObserver<TSnapshot> = (snapshot: Readonly<TSnapshot>, attempt: number) => void;

export interface ProductWebCloseRetryOptions<TSnapshot> {
  readonly max_attempts?: number;
  readonly retry_delay_ms?: number;
  readonly on_retry?: ProductWebCloseRetryObserver<TSnapshot>;
}

type ProductWebAmbiguousActivationError = Error & {
  readonly product_activation_cleanup_required: true;
};

const AMBIGUOUS_ACTIVATION_TRANSPORT_CODES = new Set(['REQUEST_TIMEOUT', 'WS_DISCONNECTED', 'WS_CLOSED']);
const RETAINED_OPERATION_RETRY_DELAYS_MS = Object.freeze([250, 750]);
const PRODUCT_OPERATION_CAPACITY = 128;

class ProductReplayFence {
  private readonly bits = new Uint8Array(8192);

  private indices(value: string): readonly number[] {
    return [0x811c9dc5, 0x9e3779b1, 0x85ebca6b, 0xc2b2ae35].map(seed => {
      let hash = seed;
      for (let index = 0; index < value.length; index += 1) {
        hash = Math.imul(hash ^ value.charCodeAt(index), 0x01000193);
      }
      return (hash >>> 0) % (this.bits.length * 8);
    });
  }

  add(value: string): void {
    for (const index of this.indices(value)) this.bits[index >> 3] |= 1 << (index & 7);
  }

  has(value: string): boolean {
    return this.indices(value).every(index => (this.bits[index >> 3] & (1 << (index & 7))) !== 0);
  }
}

function completedProductOperationFingerprint<T>(ledger: Map<string, { requestId: string; result?: T; promise?: Promise<T> }>): string | null {
  for (const [fingerprint, entry] of ledger) {
    if (entry.result !== undefined) return fingerprint;
  }
  return null;
}
let productRequestSequence = 0;

function allocateProductRequestId(prefix: string): string {
  productRequestSequence += 1;
  const random = globalThis.crypto?.randomUUID?.();
  return `${prefix}-${random ?? `${Date.now()}-${productRequestSequence}`}`;
}

export type ProductWebRequest = (method: string, params: Record<string, unknown>, request_id?: string) => Promise<unknown>;

export type ProductP2DurableOperationMethod =
  | typeof PRODUCT_P2_SUBMIT_METHOD
  | typeof PRODUCT_P2_PRESENTATION_ACK_METHOD
  | typeof PRODUCT_P2_BARGE_IN_METHOD
  | typeof PRODUCT_P2_INTERRUPT_GENERATION_METHOD;

export type ProductP2DurableOperation = Readonly<{
  method: ProductP2DurableOperationMethod;
  request_id: string;
  params: Readonly<Record<string, unknown>>;
}>;

export interface ProductP2DurableOperationJournal {
  checkpointOperation(operation: Readonly<ProductP2DurableOperation>): void;
  settleOperation(operation: Readonly<ProductP2DurableOperation>): void;
}

const PRODUCT_P2_DURABLE_OPERATION_MAX_BYTES = 131_072;
const PRODUCT_P2_DURABLE_TEXT_MAX_BYTES = 100_000;
const PRODUCT_P2_SUBMIT_PREFLIGHT_REQUEST_ID = 'live-voice-p2-submit-00000000-0000-4000-8000-000000000000';

function exactRecord(value: unknown, keys: readonly string[], field: string): Record<string, unknown> {
  const record = objectValue(value);
  if (record === null || Object.getOwnPropertySymbols(record).length !== 0) throw new Error(`${field} is invalid`);
  const actual = Object.keys(record).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${field} has unexpected fields`);
  }
  return record;
}

function exactDurableText(value: unknown, field: string, maxLength = 256): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maxLength) throw new Error(`${field} is invalid`);
  return value;
}

function exactDurableCommittedText(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${field} is invalid`);
  try {
    canonicalJsonBytes(value);
  } catch {
    throw new Error(`${field} is invalid`);
  }
  if (new TextEncoder().encode(value).byteLength > PRODUCT_P2_DURABLE_TEXT_MAX_BYTES) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function exactDurableGeneration(value: unknown, field: string, allowZero = false): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < (allowZero ? 0 : 1)) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function durableOperationParamKeys(method: ProductP2DurableOperationMethod, params: Record<string, unknown>): readonly string[] {
  const binding = ['session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation'];
  if (method === PRODUCT_P2_SUBMIT_METHOD) {
    const keys = [...binding, 'commit_id', 'turn_id', 'committed_at', 'text', 'dispatch_target'];
    if (params.dispatch_target === 'agent') keys.push('response_id');
    if (Object.prototype.hasOwnProperty.call(params, 'voice_commit_receipt')) keys.push('voice_commit_receipt');
    if (Object.prototype.hasOwnProperty.call(params, 'critical_confirmation')) keys.push('critical_confirmation');
    return keys;
  }
  if (method === PRODUCT_P2_PRESENTATION_ACK_METHOD) {
    return [...binding, 'response_id', 'response_generation', 'surface', 'unit_id', 'contiguous_cursor', 'presented_at'];
  }
  // A generation interruption carries no cancellation-scope key at all, so a
  // persisted operation can never be replayed as a wider cancellation.
  if (method === PRODUCT_P2_INTERRUPT_GENERATION_METHOD) {
    return [...binding, 'action_id', 'response_id', 'response_generation'];
  }
  return [...binding, 'action_id', 'response_id', 'response_generation', 'cancel_response'];
}

/** Strictly parse one bounded, secret-free request envelope before transport or persistence. */
export function validateProductP2DurableOperation(value: unknown, expectedBinding?: Readonly<ProductWebP2ActivationBinding>): ProductP2DurableOperation {
  const operation = exactRecord(value, ['method', 'request_id', 'params'], 'durable product operation');
  if (
    operation.method !== PRODUCT_P2_SUBMIT_METHOD &&
    operation.method !== PRODUCT_P2_PRESENTATION_ACK_METHOD &&
    operation.method !== PRODUCT_P2_BARGE_IN_METHOD &&
    operation.method !== PRODUCT_P2_INTERRUPT_GENERATION_METHOD
  ) {
    throw new Error('durable product operation method is invalid');
  }
  const method = operation.method;
  const looseParams = objectValue(operation.params);
  if (looseParams === null) throw new Error('durable product operation params are invalid');
  const params = exactRecord(looseParams, durableOperationParamKeys(method, looseParams), 'durable product operation params');
  const binding = freezeBinding({
    session_id: exactDurableText(params.session_id, 'session_id'),
    correlation_id: exactDurableText(params.correlation_id, 'correlation_id'),
    interaction_id: exactDurableText(params.interaction_id, 'interaction_id'),
    activation_id: exactDurableText(params.activation_id, 'activation_id'),
    activation_generation: exactDurableGeneration(params.activation_generation, 'activation_generation'),
  });
  if (expectedBinding !== undefined && !sameBinding(binding, expectedBinding)) {
    throw new Error('durable product operation binding mismatch');
  }
  if (method === PRODUCT_P2_SUBMIT_METHOD) {
    exactDurableText(params.commit_id, 'commit_id');
    exactDurableText(params.turn_id, 'turn_id');
    exactDurableText(params.committed_at, 'committed_at');
    exactDurableCommittedText(params.text, 'text');
    if (params.dispatch_target !== 'agent' && params.dispatch_target !== 'task') {
      throw new Error('durable product submission target is invalid');
    }
    if (params.dispatch_target === 'agent') exactDurableText(params.response_id, 'response_id');
    if (params.voice_commit_receipt !== undefined) exactDurableText(params.voice_commit_receipt, 'voice_commit_receipt');
    if (params.critical_confirmation !== undefined && params.critical_confirmation !== true) {
      throw new Error('durable product critical confirmation is invalid');
    }
    if (params.dispatch_target === 'task' && typeof params.voice_commit_receipt !== 'string') {
      throw new Error('durable product task receipt is missing');
    }
  } else if (method === PRODUCT_P2_PRESENTATION_ACK_METHOD) {
    exactDurableText(params.response_id, 'response_id');
    exactDurableGeneration(params.response_generation, 'response_generation', true);
    if (params.surface !== 'text' && params.surface !== 'audio') throw new Error('durable product ACK surface is invalid');
    exactDurableText(params.unit_id, 'unit_id');
    exactDurableGeneration(params.contiguous_cursor, 'contiguous_cursor', true);
    exactDurableText(params.presented_at, 'presented_at');
  } else if (method === PRODUCT_P2_INTERRUPT_GENERATION_METHOD) {
    exactDurableText(params.action_id, 'action_id');
    exactDurableText(params.response_id, 'response_id');
    exactDurableGeneration(params.response_generation, 'response_generation', true);
  } else {
    exactDurableText(params.action_id, 'action_id');
    exactDurableText(params.response_id, 'response_id');
    exactDurableGeneration(params.response_generation, 'response_generation', true);
    if (typeof params.cancel_response !== 'boolean') throw new Error('durable product barge-in policy is invalid');
  }
  let serialized: Uint8Array;
  try {
    serialized = canonicalJsonBytes(value);
  } catch {
    throw new Error('durable product operation cannot be serialized');
  }
  if (serialized.byteLength > PRODUCT_P2_DURABLE_OPERATION_MAX_BYTES) {
    throw new Error('durable product operation exceeds its bound');
  }
  return Object.freeze({
    method,
    request_id: exactDurableText(operation.request_id, 'request_id'),
    params: Object.freeze({ ...params }),
  });
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function isRetriableProductOperationError(error: unknown): boolean {
  const candidate = objectValue(error);
  return Boolean(
    candidate?.retriable === true ||
    (typeof candidate?.code === 'string' &&
      (AMBIGUOUS_ACTIVATION_TRANSPORT_CODES.has(candidate.code) || candidate.code === 'WS_NOT_READY' || candidate.code === 'UNAVAILABLE')),
  );
}

const DEFINITIVE_PRODUCT_FAILURE_CODES = new Set([
  'INVALID_ARGUMENT',
  'UNAUTHENTICATED',
  'PERMISSION_DENIED',
  'NOT_FOUND',
  'CONFLICT',
  'STALE',
  'UNSUPPORTED',
  'CAPABILITY_UNAVAILABLE',
]);
const DEFINITIVE_PRODUCT_FAILURE_REASONS = new Set([
  'PRODUCT_OPERATION_LEDGER_FULL',
  'PRODUCT_COMPOSITION_STOPPED',
  'PRODUCT_P2_NOTIFICATION_FAILED',
  'NOTIFICATION_STREAM_CLOSED',
  'P3_CONFIRMATION_ISSUER_UNAVAILABLE',
]);

export function isDefinitiveProductOperationError(error: unknown): boolean {
  const candidate = objectValue(error);
  return Boolean(
    (typeof candidate?.code === 'string' && DEFINITIVE_PRODUCT_FAILURE_CODES.has(candidate.code)) ||
    (typeof candidate?.reason === 'string' && DEFINITIVE_PRODUCT_FAILURE_REASONS.has(candidate.reason)),
  );
}

/** Retry one retained request without changing its caller-owned request ID. */
export async function retryRetainedProductOperation<T>(input: {
  operation: () => Promise<T>;
  is_current: () => boolean;
  retry_delays_ms?: readonly number[];
}): Promise<T> {
  const delays = input.retry_delays_ms ?? RETAINED_OPERATION_RETRY_DELAYS_MS;
  let failure: unknown;
  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    if (!input.is_current()) {
      throw failure instanceof Error ? failure : new Error('retained product operation is no longer current');
    }
    try {
      return await input.operation();
    } catch (error) {
      failure = error;
      if (isDefinitiveProductOperationError(error) || !isRetriableProductOperationError(error) || attempt === delays.length) throw error;
      const delay = delays[attempt];
      if (!Number.isSafeInteger(delay) || delay < 0) {
        throw new Error('retained product retry delay is invalid');
      }
      await new Promise(resolve => globalThis.setTimeout(resolve, delay));
    }
  }
  throw failure;
}

function requiredText(value: string, field: string): string {
  const text = value.trim();
  if (!text || text.length > 256) throw new Error(`${field} is invalid`);
  return text;
}

export type ProductWebP3MutationInput = Readonly<
  | {
      operation: 'task.create';
      session_id: string;
      command_id: string;
      issued_at: string;
      correlation_id: string;
      source: 'structured' | 'voice';
      interaction_id?: string;
      turn_id?: string;
      commit_id?: string;
      name: string;
      instruction: string;
      model_intent?: string;
    }
  | {
      operation: 'task.cancel';
      session_id: string;
      command_id: string;
      issued_at: string;
      correlation_id: string;
      source: 'structured';
      task_id: string;
    }
  | {
      operation: 'task.retry';
      session_id: string;
      command_id: string;
      issued_at: string;
      correlation_id: string;
      task_id: string;
    }
>;

export interface ProductWebP3ConfirmationReceipt {
  readonly confirmation_id: string;
  readonly expires_at: string;
  readonly operation: 'task.create' | 'task.cancel' | 'task.retry';
  readonly command_id: string;
  readonly target_task_id: string | null;
  readonly task_control_binding: ProductWebP3TaskControlBinding;
}

export interface ProductWebP3TaskControlBinding {
  readonly subject_id: string;
  readonly session_id: string;
  readonly project_id: string;
  readonly correlation_id: string;
  readonly generation: number;
}

function requiredContent(value: string, field: string): string {
  if (!value.trim() || value.length > 100_000) throw new Error(`${field} is invalid`);
  return value;
}

function requiredCommittedText(value: string, field: string): string {
  return exactDurableCommittedText(value, field);
}

function freezeBinding(input: Readonly<ProductWebP2ActivationBinding>): ProductWebP2ActivationBinding {
  if (!Number.isSafeInteger(input.activation_generation) || input.activation_generation <= 0) {
    throw new Error('activation_generation is invalid');
  }
  return Object.freeze({
    session_id: requiredText(input.session_id, 'session_id'),
    correlation_id: requiredText(input.correlation_id, 'correlation_id'),
    interaction_id: requiredText(input.interaction_id, 'interaction_id'),
    activation_id: requiredText(input.activation_id, 'activation_id'),
    activation_generation: input.activation_generation,
  });
}

function freezeDurableOperation(
  method: ProductP2DurableOperationMethod,
  requestId: string,
  params: Readonly<Record<string, unknown>>,
): ProductP2DurableOperation {
  return validateProductP2DurableOperation({ method, request_id: requestId, params });
}

function sameBinding(left: Readonly<ProductWebP2ActivationBinding>, right: Readonly<ProductWebP2ActivationBinding>): boolean {
  return (
    left.session_id === right.session_id &&
    left.correlation_id === right.correlation_id &&
    left.interaction_id === right.interaction_id &&
    left.activation_id === right.activation_id &&
    left.activation_generation === right.activation_generation
  );
}

function requireResult(value: unknown, expectedStatus: 'active' | 'closed', binding: Readonly<ProductWebP2ActivationBinding>): JsonObject {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (payload?.ok !== true || result?.status !== expectedStatus) {
    throw new Error(`product P2 ${expectedStatus} response is unavailable`);
  }
  if (expectedStatus === 'active') {
    if (
      result.session_id !== binding.session_id ||
      result.correlation_id !== binding.correlation_id ||
      result.interaction_id !== binding.interaction_id ||
      result.activation_id !== binding.activation_id ||
      result.activation_generation !== binding.activation_generation
    ) {
      throw new Error('product P2 activation binding mismatch');
    }
  } else if (
    result.session_id !== binding.session_id ||
    result.correlation_id !== binding.correlation_id ||
    result.interaction_id !== binding.interaction_id ||
    result.activation_id !== binding.activation_id ||
    result.activation_generation !== binding.activation_generation
  ) {
    throw new Error('product P2 close binding mismatch');
  }
  return Object.freeze({ ...result });
}

function requireP2BoundOperationResult(
  value: unknown,
  expectedStatus:
    | 'round_accepted'
    | 'task_origin_accepted'
    | 'notification'
    | 'presentation_acknowledged'
    | 'presentation_failed_fallback_text'
    | 'barge_in_applied'
    | 'generation_interrupted',
  binding: Readonly<ProductWebP2ActivationBinding>,
): JsonObject {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (
    payload?.ok !== true ||
    result?.status !== expectedStatus ||
    result.session_id !== binding.session_id ||
    result.correlation_id !== binding.correlation_id ||
    result.interaction_id !== binding.interaction_id ||
    result.activation_id !== binding.activation_id ||
    result.activation_generation !== binding.activation_generation
  ) {
    throw new Error(`product P2 ${expectedStatus} binding mismatch`);
  }
  return Object.freeze({ ...result });
}

const PRODUCT_P2_NOTIFICATION_BATCH_MAX = 16;
const PRODUCT_P2_NOTIFICATION_BATCH_KEYS = Object.freeze([
  'status',
  'notifications',
  'session_id',
  'correlation_id',
  'interaction_id',
  'activation_id',
  'activation_generation',
] as const);
const PRODUCT_P2_NOTIFICATION_ITEM_KEYS = Object.freeze([
  'status',
  'kind',
  'request_id',
  'round_id',
  'response',
  'agent_event',
  'source_event',
  'progress_event',
  'presentation_unit',
  'error_reason',
  'publish_seq',
  'session_id',
  'correlation_id',
  'interaction_id',
  'activation_id',
  'activation_generation',
] as const);

function isP2BatchObserver(notification: Readonly<Record<string, unknown>>): boolean {
  const agentEvent = objectValue(notification.agent_event);
  return (
    agentEvent !== null &&
    (agentEvent.event_type === 'chat.delta' || agentEvent.event_type === 'chat.reasoning') &&
    agentEvent.error_reason === null &&
    notification.source_event === null &&
    notification.progress_event === null &&
    notification.presentation_unit === null &&
    notification.error_reason === null
  );
}

function requireP2NotificationResult(
  value: unknown,
  binding: Readonly<ProductWebP2ActivationBinding>,
  batchSize: number,
  priorBatchPublishSeq: number | null,
): readonly JsonObject[] {
  const payload = objectValue(value);
  const looseResult = objectValue(payload?.result);
  if (payload?.ok !== true || looseResult === null) {
    throw new Error('product P2 notification response is unavailable');
  }
  if (looseResult.status === 'notification') {
    return Object.freeze([requireP2BoundOperationResult(value, 'notification', binding)]);
  }
  let result: Record<string, unknown>;
  try {
    result = exactRecord(looseResult, PRODUCT_P2_NOTIFICATION_BATCH_KEYS, 'product P2 notification batch');
  } catch {
    throw new Error('product P2 notification batch is invalid');
  }
  if (
    result.status !== 'notification_batch' ||
    result.session_id !== binding.session_id ||
    result.correlation_id !== binding.correlation_id ||
    result.interaction_id !== binding.interaction_id ||
    result.activation_id !== binding.activation_id ||
    result.activation_generation !== binding.activation_generation ||
    !Array.isArray(result.notifications) ||
    result.notifications.length < 1 ||
    result.notifications.length > batchSize ||
    result.notifications.length > PRODUCT_P2_NOTIFICATION_BATCH_MAX
  ) {
    throw new Error('product P2 notification batch binding is invalid');
  }
  const notifications: JsonObject[] = [];
  let priorPublishSeq = priorBatchPublishSeq;
  for (let index = 0; index < result.notifications.length; index += 1) {
    let notification: Record<string, unknown>;
    try {
      notification = exactRecord(result.notifications[index], PRODUCT_P2_NOTIFICATION_ITEM_KEYS, 'product P2 notification batch item');
    } catch {
      throw new Error('product P2 notification batch item is invalid');
    }
    if (
      notification.status !== 'notification' ||
      notification.session_id !== binding.session_id ||
      notification.correlation_id !== binding.correlation_id ||
      notification.interaction_id !== binding.interaction_id ||
      notification.activation_id !== binding.activation_id ||
      notification.activation_generation !== binding.activation_generation
    ) {
      throw new Error('product P2 notification batch item binding is invalid');
    }
    const publishSeq = notification.publish_seq;
    if (publishSeq !== null && (!Number.isSafeInteger(publishSeq) || (publishSeq as number) < 0)) {
      throw new Error('product P2 notification batch order is invalid');
    }
    if (publishSeq === null) {
      if (result.notifications.length !== 1) throw new Error('product P2 notification batch order is invalid');
    } else {
      if (priorPublishSeq !== null && (publishSeq as number) <= priorPublishSeq) {
        throw new Error('product P2 notification batch order is invalid');
      }
      priorPublishSeq = publishSeq as number;
    }
    if (index < result.notifications.length - 1 && !isP2BatchObserver(notification)) {
      throw new Error('product P2 notification batch barrier is invalid');
    }
    notifications.push(Object.freeze({ ...notification }));
  }
  return Object.freeze(notifications);
}

function requireDurableP2Envelope(operation: Readonly<ProductP2DurableOperation>, value: unknown): JsonObject {
  const payload = objectValue(value);
  if (payload?.request_id !== operation.request_id || payload.ok !== true || payload.error !== null) {
    throw new Error('durable product operation response envelope is unavailable');
  }
  return payload;
}

function requireDurableP2OperationResult(operation: Readonly<ProductP2DurableOperation>, value: unknown): JsonObject {
  const payload = requireDurableP2Envelope(operation, value);
  const params = operation.params;
  if (
    typeof params.session_id !== 'string' ||
    typeof params.correlation_id !== 'string' ||
    typeof params.interaction_id !== 'string' ||
    typeof params.activation_id !== 'string'
  ) {
    throw new Error('durable product operation binding is invalid');
  }
  const binding = freezeBinding({
    session_id: params.session_id,
    correlation_id: params.correlation_id,
    interaction_id: params.interaction_id,
    activation_id: params.activation_id,
    activation_generation: params.activation_generation as number,
  });
  if (operation.method === PRODUCT_P2_SUBMIT_METHOD) {
    const dispatchTarget = params.dispatch_target;
    if (dispatchTarget !== 'agent' && dispatchTarget !== 'task') {
      throw new Error('durable product submission target is invalid');
    }
    const result = requireP2BoundOperationResult(payload, dispatchTarget === 'task' ? 'task_origin_accepted' : 'round_accepted', binding);
    const response = objectValue(result.response);
    if (
      result.turn_id !== params.turn_id ||
      result.commit_id !== params.commit_id ||
      response?.interaction_id !== binding.interaction_id ||
      typeof response.response_id !== 'string' ||
      !response.response_id.trim() ||
      (dispatchTarget === 'agent' && response.response_id !== params.response_id) ||
      !Number.isSafeInteger(response.response_generation) ||
      (response.response_generation as number) < 0
    ) {
      throw new Error(`product P2 ${dispatchTarget === 'task' ? 'task_origin_accepted' : 'round_accepted'} response binding mismatch`);
    }
    return result;
  }
  if (operation.method === PRODUCT_P2_PRESENTATION_ACK_METHOD) {
    const result = requireP2BoundOperationResult(payload, 'presentation_acknowledged', binding);
    if (
      typeof result.accepted !== 'boolean' ||
      typeof result.replayed !== 'boolean' ||
      !Number.isSafeInteger(result.history_records_written) ||
      (result.history_records_written as number) < 0 ||
      typeof result.history_pending !== 'boolean' ||
      (result.accepted === false && (result.history_records_written !== 0 || result.history_pending !== false)) ||
      (result.history_pending === true && result.history_records_written !== 0)
    ) {
      throw new Error('product P2 presentation ACK result binding is invalid');
    }
    return result;
  }
  if (operation.method === PRODUCT_P2_INTERRUPT_GENERATION_METHOD) {
    const interrupted = requireP2BoundOperationResult(payload, 'generation_interrupted', binding);
    if (
      interrupted.action_id !== params.action_id ||
      interrupted.response_id !== params.response_id ||
      interrupted.response_generation !== params.response_generation ||
      // The server owns this fact and the browser refuses anything wider than
      // a round cancellation, so a widened scope fails closed here as well.
      interrupted.cancel_scope !== 'round.cancel' ||
      (interrupted.fence_status !== 'fenced' && interrupted.fence_status !== 'already_settled') ||
      typeof interrupted.applied !== 'boolean' ||
      typeof interrupted.replayed !== 'boolean' ||
      !Array.isArray(interrupted.effect_ids) ||
      interrupted.effect_ids.some(item => typeof item !== 'string' || !item)
    ) {
      throw new Error('generation interruption response binding is invalid');
    }
    return interrupted;
  }
  const result = requireP2BoundOperationResult(payload, 'barge_in_applied', binding);
  if (
    result.action_id !== params.action_id ||
    result.response_id !== params.response_id ||
    result.response_generation !== params.response_generation ||
    result.cancel_response !== params.cancel_response ||
    typeof result.applied !== 'boolean' ||
    typeof result.replayed !== 'boolean' ||
    !Array.isArray(result.effect_ids) ||
    result.effect_ids.some(item => typeof item !== 'string' || !item)
  ) {
    throw new Error('barge-in response binding is invalid');
  }
  return result;
}

/** Replay one persisted business operation with its original request identity. */
export async function replayProductP2DurableOperation(input: {
  operation: Readonly<ProductP2DurableOperation>;
  request: ProductWebRequest;
}): Promise<JsonObject> {
  const operation = validateProductP2DurableOperation(input.operation);
  const value = await input.request(operation.method, { ...operation.params }, operation.request_id);
  return requireDurableP2OperationResult(operation, value);
}

function freezeP3MutationInput(input: ProductWebP3MutationInput): ProductWebP3MutationInput {
  const common = {
    session_id: requiredText(input.session_id, 'session_id'),
    command_id: requiredText(input.command_id, 'command_id'),
    issued_at: requiredText(input.issued_at, 'issued_at'),
    correlation_id: requiredText(input.correlation_id, 'correlation_id'),
  } as const;
  if (input.operation === 'task.cancel') {
    const source = (input as { source?: unknown }).source;
    if (source !== undefined && source !== 'structured') {
      throw new Error(`${input.operation} source is invalid`);
    }
    return Object.freeze({
      operation: input.operation,
      ...common,
      source: 'structured' as const,
      task_id: requiredText(input.task_id, 'task_id'),
    });
  }
  if (input.operation === 'task.retry') {
    const inputKeys = Object.keys(input).sort();
    const expectedKeys = ['command_id', 'correlation_id', 'issued_at', 'operation', 'session_id', 'task_id'];
    if (inputKeys.length !== expectedKeys.length || inputKeys.some((key, index) => key !== expectedKeys[index])) {
      throw new Error('task.retry input must contain only task_id and confirmation-bound request facts');
    }
    return Object.freeze({
      operation: 'task.retry' as const,
      ...common,
      task_id: requiredText(input.task_id, 'task_id'),
    });
  }
  const source = input.source ?? 'structured';
  if (source !== 'structured' && source !== 'voice') {
    throw new Error('task.create source is invalid');
  }
  if (
    (source === 'voice' && (!input.interaction_id || !input.turn_id || !input.commit_id)) ||
    (source === 'structured' && (input.interaction_id !== undefined || input.turn_id !== undefined || input.commit_id !== undefined))
  ) {
    throw new Error('task.create committed origin is invalid');
  }
  return Object.freeze({
    operation: 'task.create' as const,
    ...common,
    source,
    ...(source === 'voice'
      ? {
          interaction_id: requiredText(input.interaction_id ?? '', 'interaction_id'),
          turn_id: requiredText(input.turn_id ?? '', 'turn_id'),
          commit_id: requiredText(input.commit_id ?? '', 'commit_id'),
        }
      : {}),
    name: requiredContent(input.name, 'name'),
    instruction: requiredContent(input.instruction, 'instruction'),
    ...(input.model_intent === undefined ? {} : { model_intent: requiredText(input.model_intent, 'model_intent') }),
  });
}

function requireP3TaskControlBinding(value: unknown, mutation: ProductWebP3MutationInput): ProductWebP3TaskControlBinding {
  const binding = objectValue(value);
  if (
    binding === null ||
    Object.keys(binding).sort().join(',') !== 'correlation_id,generation,project_id,session_id,subject_id' ||
    binding.session_id !== mutation.session_id ||
    binding.correlation_id !== mutation.correlation_id ||
    !Number.isSafeInteger(binding.generation) ||
    Number(binding.generation) <= 0
  ) {
    throw new Error('product P3 task-control binding is unavailable');
  }
  return Object.freeze({
    subject_id: requiredText(String(binding.subject_id ?? ''), 'subject_id'),
    session_id: requiredText(String(binding.session_id), 'session_id'),
    project_id: requiredText(String(binding.project_id ?? ''), 'project_id'),
    correlation_id: requiredText(String(binding.correlation_id), 'correlation_id'),
    generation: Number(binding.generation),
  });
}

function selectSingleActiveTask(value: unknown): string {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  const tasks = result?.tasks;
  if (payload?.ok !== true || !Array.isArray(tasks)) {
    throw new Error('formal task list is unavailable');
  }
  const active: string[] = [];
  for (const item of tasks) {
    const task = objectValue(item);
    if (!task || typeof task.task_id !== 'string' || typeof task.state !== 'string') {
      throw new Error('formal task list binding is invalid');
    }
    const taskId = requiredText(task.task_id, 'task_id');
    const state = requiredText(task.state, 'task.state');
    if (state !== 'terminal') active.push(taskId);
  }
  if (active.length !== 1) {
    throw new Error('formal text progress requires exactly one active task');
  }
  return active[0]!;
}

function freezeP3Binding(input: Readonly<ProductWebP3ProgressBinding>): ProductWebP3ProgressBinding {
  if (!Number.isSafeInteger(input.generation) || input.generation <= 0) {
    throw new Error('generation is invalid');
  }
  return Object.freeze({
    session_id: requiredText(input.session_id, 'session_id'),
    task_id: requiredText(input.task_id, 'task_id'),
    correlation_id: requiredText(input.correlation_id, 'correlation_id'),
    origin_id: requiredText(input.origin_id, 'origin_id'),
    generation_id: requiredText(input.generation_id, 'generation_id'),
    generation: input.generation,
  });
}

function requireP3Result(value: unknown, expectedStatus: 'active' | 'closed', binding: Readonly<ProductWebP3ProgressBinding>): JsonObject {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (
    payload?.ok !== true ||
    result?.status !== expectedStatus ||
    result.session_id !== binding.session_id ||
    result.task_id !== binding.task_id ||
    result.correlation_id !== binding.correlation_id ||
    result.origin_id !== binding.origin_id ||
    result.generation_id !== binding.generation_id ||
    result.generation !== binding.generation
  ) {
    throw new Error(`product P3 progress ${expectedStatus} binding mismatch`);
  }
  return Object.freeze({ ...result });
}

function parseP3ActivationDelivery(
  result: JsonObject,
): Pick<ProductWebP3ProgressSnapshot, 'requested_origin_kind' | 'effective_origin_kind' | 'voice_progress' | 'voice_reason' | 'fallback_reason'> {
  const requested = result.requested_origin_kind;
  const effective = result.origin_kind;
  const voiceProgress = result.voice_progress;
  const fallbackReason = result.fallback_reason === null ? null : requiredText(String(result.fallback_reason ?? ''), 'fallback_reason');
  const voiceReason = result.voice_reason === null ? null : requiredText(String(result.voice_reason ?? ''), 'voice_reason');
  if (
    (requested !== 'text' && requested !== 'voice') ||
    (effective !== 'text' && effective !== 'voice') ||
    (voiceProgress !== 'available' && voiceProgress !== 'unavailable') ||
    (effective === 'voice') !== (voiceProgress === 'available') ||
    (effective === 'voice' && (requested !== 'voice' || fallbackReason !== null || voiceReason !== null)) ||
    (requested === 'voice' && effective === 'text' && (fallbackReason === null || voiceReason !== fallbackReason)) ||
    (requested === 'text' && (effective !== 'text' || fallbackReason !== null))
  ) {
    throw new Error('product P3 progress activation delivery is invalid');
  }
  return Object.freeze({
    requested_origin_kind: requested,
    effective_origin_kind: effective,
    voice_progress: voiceProgress,
    voice_reason: voiceReason,
    fallback_reason: fallbackReason,
  });
}

function ambiguousActivationResponse(error: unknown): ProductWebAmbiguousActivationError {
  const message = error instanceof Error ? error.message : 'product activation response binding is unavailable';
  const wrapped = new Error(message) as ProductWebAmbiguousActivationError;
  wrapped.name = 'ProductWebAmbiguousActivationError';
  Object.defineProperty(wrapped, 'product_activation_cleanup_required', {
    value: true,
    enumerable: true,
  });
  return wrapped;
}

/** True only when the request may have opened a route without a usable reply. */
export function requiresProductActivationCleanup(error: unknown): boolean {
  const candidate = objectValue(error);
  return (
    candidate?.product_activation_cleanup_required === true || (typeof candidate?.code === 'string' && AMBIGUOUS_ACTIVATION_TRANSPORT_CODES.has(candidate.code))
  );
}

function closeWithBoundedRetry<TSnapshot>(input: {
  close: () => Promise<TSnapshot>;
  snapshot: () => TSnapshot;
  options: ProductWebCloseRetryOptions<TSnapshot>;
}): Promise<TSnapshot> {
  const maxAttempts = input.options.max_attempts ?? 3;
  const retryDelayMs = input.options.retry_delay_ms ?? 100;
  if (!Number.isSafeInteger(maxAttempts) || maxAttempts <= 0) {
    return Promise.reject(new Error('cleanup retry attempts are invalid'));
  }
  if (!Number.isSafeInteger(retryDelayMs) || retryDelayMs < 0) {
    return Promise.reject(new Error('cleanup retry delay is invalid'));
  }
  const run = async (): Promise<TSnapshot> => {
    let lastError: unknown = new Error('product cleanup unavailable');
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        return await input.close();
      } catch (error) {
        lastError = error;
        input.options.on_retry?.(input.snapshot(), attempt);
        if (attempt < maxAttempts && retryDelayMs > 0) {
          await new Promise(resolve => setTimeout(resolve, retryDelayMs));
        }
      }
    }
    throw lastError;
  };
  return run();
}

/**
 * Stock-Web owner for one exact P2 activation lease.
 *
 * The owner deliberately has no bearer-token field. The default-off Gateway
 * credential bridge injects the bounded Alpha bearer server-side. An ambiguous
 * response-lost activation retains enough exact binding to attempt cleanup;
 * an authoritative rejection remains unavailable without fake ownership.
 */
export class ProductWebP2ActivationOwner {
  private readonly enabled: boolean;
  private readonly request: ProductWebRequest;
  private readonly durableOperationJournal?: ProductP2DurableOperationJournal;
  private readonly onSnapshot?: (snapshot: ProductWebP2ActivationSnapshot) => void;
  private readonly notificationBatchSize: number;
  private binding: ProductWebP2ActivationBinding | null = null;
  private status: ProductWebP2ActivationStatus;
  private reason: string | null = null;
  private activationAttempted = false;
  private activationReplayed: boolean | null = null;
  private cleanupRequired = false;
  private closing = false;
  private activationPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private mediaAuthorityRefreshPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private mediaStartReservation: Readonly<{ cancel: () => Promise<void> }> | null = null;
  private closePromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private closeRetryPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private readonly closeRetryObservers = new Set<ProductWebCloseRetryObserver<ProductWebP2ActivationSnapshot>>();
  private readonly submissions = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly presentationAcks = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly presentationFailures = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly bargeIns = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly generationInterrupts = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly submissionReplayFence = new ProductReplayFence();
  private readonly presentationAckReplayFence = new ProductReplayFence();
  private readonly presentationFailureReplayFence = new ProductReplayFence();
  private readonly bargeInReplayFence = new ProductReplayFence();
  private readonly generationInterruptReplayFence = new ProductReplayFence();
  private notificationRequestId: string | null = null;
  private notificationPromise: Promise<JsonObject> | null = null;
  private notificationSequence = 0;
  private notificationQueue: JsonObject[] = [];
  private lastNotificationPublishSeq: number | null = null;

  constructor(input: {
    enabled: boolean;
    request: ProductWebRequest;
    on_snapshot?: (snapshot: ProductWebP2ActivationSnapshot) => void;
    durable_operation_journal?: ProductP2DurableOperationJournal;
    notification_batch_size?: number;
  }) {
    if (typeof input.request !== 'function') throw new Error('product request owner is required');
    const notificationBatchSize = input.notification_batch_size ?? 1;
    if (!Number.isSafeInteger(notificationBatchSize) || notificationBatchSize < 1 || notificationBatchSize > PRODUCT_P2_NOTIFICATION_BATCH_MAX) {
      throw new Error('product notification batch size is invalid');
    }
    this.enabled = input.enabled;
    this.request = input.request;
    this.notificationBatchSize = notificationBatchSize;
    this.durableOperationJournal = input.durable_operation_journal;
    this.onSnapshot = input.on_snapshot;
    this.status = input.enabled ? 'idle' : 'disabled';
    this.publish();
  }

  snapshot(): ProductWebP2ActivationSnapshot {
    return Object.freeze({ status: this.status, binding: this.binding, reason: this.reason });
  }

  retirementStarted(): boolean {
    return this.closing;
  }

  needsCleanup(): boolean {
    return this.activationPromise !== null || this.mediaAuthorityRefreshPromise !== null || this.mediaStartReservation !== null || this.cleanupRequired;
  }

  activationWasReplayed(): boolean | null {
    return this.activationReplayed;
  }

  start(input: Readonly<ProductWebP2ActivationBinding>): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) return Promise.resolve(this.snapshot());
    if (this.closing || this.closePromise) return Promise.reject(new Error('product P2 activation is closing'));
    const binding = freezeBinding(input);
    if (this.binding && !sameBinding(this.binding, binding)) {
      return Promise.reject(new Error('a different product P2 activation is already owned'));
    }
    if (this.activationPromise) return this.activationPromise;
    if (this.status === 'active') return Promise.resolve(this.snapshot());
    this.binding = binding;
    this.activationAttempted = true;
    this.activationReplayed = null;
    this.cleanupRequired = false;
    this.status = 'activating';
    this.reason = null;
    this.publish();
    this.activationPromise = this.request(PRODUCT_P2_ACTIVATE_METHOD, { ...binding })
      .then(value => {
        try {
          const result = requireResult(value, 'active', binding);
          this.activationReplayed = result.replayed === true ? true : result.replayed === false ? false : null;
        } catch (error) {
          throw ambiguousActivationResponse(error);
        }
        this.cleanupRequired = true;
        this.status = 'active';
        this.reason = null;
        return this.publish();
      })
      .catch(error => {
        this.cleanupRequired = requiresProductActivationCleanup(error);
        this.status = 'unavailable';
        this.reason = error instanceof Error ? error.message : 'product P2 activation unavailable';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.activationPromise = null;
      });
    return this.activationPromise;
  }

  /**
   * Revalidate the exact active P2 lease before an explicit media start.
   *
   * Gateway media authority is intentionally short-lived. The browser owner
   * can outlive that TTL, so an `active` client snapshot alone is not proof
   * that a new microphone route is still trusted. Replaying the exact P2
   * activation renews server-observed authority without auto-starting capture.
   */
  refreshMediaAuthority(): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) return Promise.resolve(this.snapshot());
    if (this.closing || this.closePromise) return Promise.reject(new Error('product P2 activation is closing'));
    if (this.mediaAuthorityRefreshPromise) return this.mediaAuthorityRefreshPromise;
    let binding: ProductWebP2ActivationBinding;
    try {
      binding = this.requireActiveBinding();
    } catch (error) {
      return Promise.reject(error);
    }
    let retained: Promise<ProductWebP2ActivationSnapshot>;
    retained = this.request(PRODUCT_P2_ACTIVATE_METHOD, { ...binding })
      .then(value => {
        let result: JsonObject;
        try {
          result = requireResult(value, 'active', binding);
        } catch (error) {
          throw ambiguousActivationResponse(error);
        }
        if (result.replayed !== true) {
          throw new Error('product P2 media authority refresh did not replay the active binding');
        }
        if (this.closing || this.binding === null || !sameBinding(this.binding, binding)) {
          throw new Error('product P2 activation changed during media authority refresh');
        }
        this.activationReplayed = true;
        this.cleanupRequired = true;
        this.status = 'active';
        this.reason = null;
        return this.publish();
      })
      .catch(error => {
        this.cleanupRequired = true;
        this.status = 'unavailable';
        this.reason = error instanceof Error ? error.message : 'product P2 media authority unavailable';
        this.publish();
        throw error;
      })
      .finally(() => {
        if (this.mediaAuthorityRefreshPromise === retained) this.mediaAuthorityRefreshPromise = null;
      });
    this.mediaAuthorityRefreshPromise = retained;
    return retained;
  }

  /** Synchronous final fence immediately before an explicit media effect. */
  authorizesMediaStart(input: Readonly<ProductWebP2ActivationBinding>): boolean {
    return !this.closing && this.status === 'active' && this.binding !== null && sameBinding(this.binding, input);
  }

  /**
   * Atomically order one explicit media start before or after P2 teardown.
   *
   * Start is invoked synchronously after the reservation is published. A
   * later close fences new reservations and awaits the caller-owned local
   * cancellation before revoking remote authority; it does not wait forever
   * on a browser permission promise that may remain pending.
   */
  runAuthorizedMediaStart<T>(
    input: Readonly<ProductWebP2ActivationBinding>,
    operation: Readonly<{ start: () => Promise<T>; cancel: () => Promise<void> }>,
  ): Promise<T> {
    if (typeof operation.start !== 'function' || typeof operation.cancel !== 'function') {
      return Promise.reject(new Error('product P2 media start operation is invalid'));
    }
    if (!this.authorizesMediaStart(input)) return Promise.reject(new Error('product P2 media authority is not current'));
    if (this.mediaStartReservation !== null) return Promise.reject(new Error('a product P2 media start is already pending'));
    const reservation = Object.freeze({ cancel: operation.cancel });
    this.mediaStartReservation = reservation;
    let pending: Promise<T>;
    try {
      pending = Promise.resolve(operation.start());
    } catch (error) {
      if (this.mediaStartReservation === reservation) this.mediaStartReservation = null;
      return Promise.reject(error);
    }
    return pending.finally(() => {
      if (this.mediaStartReservation === reservation) this.mediaStartReservation = null;
    });
  }

  hasPendingSubmission(): boolean {
    return [...this.submissions.values()].some(entry => entry.result === undefined);
  }

  hasPendingNotification(): boolean {
    return this.notificationRequestId !== null;
  }

  hasPendingPresentationAck(): boolean {
    return [...this.presentationAcks.values()].some(entry => entry.result === undefined);
  }

  hasPendingPresentationFailure(): boolean {
    return [...this.presentationFailures.values()].some(entry => entry.result === undefined);
  }

  hasPendingBargeIn(): boolean {
    return [...this.bargeIns.values()].some(entry => entry.result === undefined);
  }

  hasPendingGenerationInterrupt(): boolean {
    return [...this.generationInterrupts.values()].some(entry => entry.result === undefined);
  }

  async submitText(input: {
    commit_id: string;
    turn_id: string;
    response_id?: string;
    committed_at: string;
    text: string;
    dispatch_target?: 'agent' | 'task';
    voice_commit_receipt?: string;
    critical_confirmation?: true;
  }): Promise<JsonObject> {
    const binding = this.requireActiveBinding();
    const dispatchTarget = input.dispatch_target ?? 'agent';
    if (dispatchTarget !== 'agent' && dispatchTarget !== 'task') {
      throw new Error('product turn dispatch target is invalid');
    }
    if (dispatchTarget === 'task' && !input.voice_commit_receipt) {
      throw new Error('voice task origin requires a formal speech receipt');
    }
    if (dispatchTarget === 'task' && input.response_id !== undefined) {
      throw new Error('voice task origin cannot declare a canonical response_id');
    }
    if (dispatchTarget === 'agent' && input.response_id === undefined) {
      throw new Error('response_id is required');
    }
    const responseId = dispatchTarget === 'agent' ? requiredText(input.response_id!, 'response_id') : null;
    const params = {
      ...binding,
      commit_id: requiredText(input.commit_id, 'commit_id'),
      turn_id: requiredText(input.turn_id, 'turn_id'),
      ...(responseId === null ? {} : { response_id: responseId }),
      committed_at: requiredText(input.committed_at, 'committed_at'),
      text: requiredCommittedText(input.text, 'text'),
      dispatch_target: dispatchTarget,
      ...(input.voice_commit_receipt ? { voice_commit_receipt: requiredText(input.voice_commit_receipt, 'voice_commit_receipt') } : {}),
      ...(input.critical_confirmation === true ? { critical_confirmation: true } : {}),
    };
    validateProductP2DurableOperation({
      method: PRODUCT_P2_SUBMIT_METHOD,
      request_id: PRODUCT_P2_SUBMIT_PREFLIGHT_REQUEST_ID,
      params,
    });
    const fingerprint = canonicalJson(params);
    let retained = this.submissions.get(fingerprint);
    if (retained?.result) return Promise.resolve(retained.result);
    if (retained?.promise) return retained.promise;
    let operation: ProductP2DurableOperation;
    if (!retained) {
      if (this.submissionReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed product submission replay has expired'));
      }
      if (this.hasPendingSubmission() || this.hasPendingPresentationAck()) {
        return Promise.reject(new Error('a previous product turn is still unresolved'));
      }
      const completed = this.submissions.size >= PRODUCT_OPERATION_CAPACITY ? completedProductOperationFingerprint(this.submissions) : null;
      if (this.submissions.size >= PRODUCT_OPERATION_CAPACITY && completed === null) {
        return Promise.reject(new Error('bounded product submission ledger is full'));
      }
      const candidate = { requestId: allocateProductRequestId('live-voice-p2-submit') };
      operation = freezeDurableOperation(PRODUCT_P2_SUBMIT_METHOD, candidate.requestId, params);
      this.durableOperationJournal?.checkpointOperation(operation);
      if (completed !== null) {
        this.submissions.delete(completed);
        this.submissionReplayFence.add(completed);
      }
      retained = candidate;
      this.submissions.set(fingerprint, retained);
    } else {
      operation = freezeDurableOperation(PRODUCT_P2_SUBMIT_METHOD, retained.requestId, params);
      this.durableOperationJournal?.checkpointOperation(operation);
    }
    const entry = retained;
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_SUBMIT_METHOD, params, entry.requestId)
      .then(value => {
        const result = requireDurableP2OperationResult(operation, value);
        this.durableOperationJournal?.settleOperation(operation);
        entry.result = result;
        return result;
      })
      .catch(error => {
        if (isDefinitiveProductOperationError(error)) {
          this.durableOperationJournal?.settleOperation(operation);
          this.submissions.delete(fingerprint);
        }
        throw error;
      })
      .finally(() => {
        if (entry.promise === promise) entry.promise = undefined;
      });
    entry.promise = promise;
    return promise;
  }

  async nextNotification(): Promise<JsonObject> {
    const binding = this.requireActiveBinding();
    const queued = this.notificationQueue.shift();
    if (queued !== undefined) return queued;
    if (this.notificationPromise) return this.notificationPromise;
    if (this.notificationRequestId === null) {
      this.notificationRequestId = allocateProductRequestId('live-voice-p2-notification');
      this.notificationSequence += 1;
    }
    const requestId = this.notificationRequestId;
    const params = {
      ...binding,
      notification_sequence: this.notificationSequence,
      ...(this.notificationBatchSize > 1 ? { max_notifications: this.notificationBatchSize } : {}),
    };
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_NOTIFICATION_NEXT_METHOD, params, requestId)
      .then(value => {
        if (this.closing || this.binding === null || !sameBinding(this.binding, binding)) {
          throw new Error('product P2 notification owner is no longer current');
        }
        const notifications = requireP2NotificationResult(value, binding, this.notificationBatchSize, this.lastNotificationPublishSeq);
        const [result, ...tail] = notifications;
        if (result === undefined) throw new Error('product P2 notification batch is empty');
        for (let index = notifications.length - 1; index >= 0; index -= 1) {
          const publishSeq = notifications[index].publish_seq;
          if (typeof publishSeq === 'number') {
            this.lastNotificationPublishSeq = publishSeq;
            break;
          }
        }
        this.notificationQueue.push(...tail);
        this.notificationRequestId = null;
        return result;
      })
      .catch(error => {
        if (isDefinitiveProductOperationError(error)) this.notificationRequestId = null;
        throw error;
      })
      .finally(() => {
        if (this.notificationPromise === promise) this.notificationPromise = null;
      });
    this.notificationPromise = promise;
    return promise;
  }

  async bargeIn(input: { action_id: string; response_id: string; response_generation: number; cancel_response: boolean }): Promise<JsonObject> {
    const binding = this.requireActiveBinding();
    if (!Number.isSafeInteger(input.response_generation) || input.response_generation < 0 || typeof input.cancel_response !== 'boolean') {
      return Promise.reject(new Error('barge-in binding is invalid'));
    }
    const params = {
      ...binding,
      action_id: requiredText(input.action_id, 'action_id'),
      response_id: requiredText(input.response_id, 'response_id'),
      response_generation: input.response_generation,
      cancel_response: input.cancel_response,
    };
    const fingerprint = JSON.stringify(params);
    let retained = this.bargeIns.get(fingerprint);
    if (retained?.result) return Promise.resolve(retained.result);
    if (retained?.promise) return retained.promise;
    let operation: ProductP2DurableOperation;
    if (!retained) {
      if (this.bargeInReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed barge-in replay has expired'));
      }
      const completed = this.bargeIns.size >= PRODUCT_OPERATION_CAPACITY ? completedProductOperationFingerprint(this.bargeIns) : null;
      if (this.bargeIns.size >= PRODUCT_OPERATION_CAPACITY && completed === null) {
        return Promise.reject(new Error('bounded barge-in ledger is full'));
      }
      const candidate = { requestId: allocateProductRequestId('live-voice-p2-barge') };
      operation = freezeDurableOperation(PRODUCT_P2_BARGE_IN_METHOD, candidate.requestId, params);
      this.durableOperationJournal?.checkpointOperation(operation);
      if (completed !== null) {
        this.bargeIns.delete(completed);
        this.bargeInReplayFence.add(completed);
      }
      retained = candidate;
      this.bargeIns.set(fingerprint, retained);
    } else {
      operation = freezeDurableOperation(PRODUCT_P2_BARGE_IN_METHOD, retained.requestId, params);
      this.durableOperationJournal?.checkpointOperation(operation);
    }
    const entry = retained;
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_BARGE_IN_METHOD, params, entry.requestId)
      .then(value => {
        const result = requireDurableP2OperationResult(operation, value);
        this.durableOperationJournal?.settleOperation(operation);
        entry.result = result;
        return result;
      })
      .catch(error => {
        if (isDefinitiveProductOperationError(error)) {
          this.durableOperationJournal?.settleOperation(operation);
          this.bargeIns.delete(fingerprint);
        }
        throw error;
      })
      .finally(() => {
        if (entry.promise === promise) entry.promise = undefined;
      });
    entry.promise = promise;
    return promise;
  }

  /**
   * Fence one exact unfinished response so newer committed speech can own it.
   *
   * There is deliberately no cancellation-scope argument: the server always
   * limits itself to the conversational round, so a spoken interruption can
   * never grow into a background Task cancellation from the browser side.
   */
  async interruptGeneration(input: { action_id: string; response_id: string; response_generation: number }): Promise<JsonObject> {
    const binding = this.requireActiveBinding();
    if (!Number.isSafeInteger(input.response_generation) || input.response_generation < 0) {
      return Promise.reject(new Error('generation interruption binding is invalid'));
    }
    const params = {
      ...binding,
      action_id: requiredText(input.action_id, 'action_id'),
      response_id: requiredText(input.response_id, 'response_id'),
      response_generation: input.response_generation,
    };
    const fingerprint = JSON.stringify(params);
    let retained = this.generationInterrupts.get(fingerprint);
    if (retained?.result) return Promise.resolve(retained.result);
    if (retained?.promise) return retained.promise;
    if (!retained) {
      if (this.generationInterruptReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed generation interruption replay has expired'));
      }
      const completed = this.generationInterrupts.size >= PRODUCT_OPERATION_CAPACITY
        ? completedProductOperationFingerprint(this.generationInterrupts)
        : null;
      if (this.generationInterrupts.size >= PRODUCT_OPERATION_CAPACITY && completed === null) {
        return Promise.reject(new Error('bounded generation interruption ledger is full'));
      }
      retained = { requestId: allocateProductRequestId('live-voice-p2-generation-interrupt') };
      if (completed !== null) {
        this.generationInterrupts.delete(completed);
        this.generationInterruptReplayFence.add(completed);
      }
      this.generationInterrupts.set(fingerprint, retained);
    }
    const entry = retained;
    // The exact request/response shape is still validated here, but this
    // operation deliberately stays out of the single-slot durable journal.
    // Barge-in must be recoverable because it settles output the user already
    // saw or heard; a generation interruption happens before any output exists,
    // and reserving the slot would collide with the presentation ACK of the
    // very answer it is fencing. Replay safety comes from the server-side
    // action_id ledger instead.
    const operation = freezeDurableOperation(PRODUCT_P2_INTERRUPT_GENERATION_METHOD, entry.requestId, params);
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_INTERRUPT_GENERATION_METHOD, params, entry.requestId)
      .then(value => {
        let result: JsonObject;
        try {
          result = requireDurableP2OperationResult(operation, value);
        } catch (error) {
          // A response was received, so a binding/schema failure is
          // deterministic rather than ambiguous transport loss. Retaining it
          // would make every recovery poll replay the same invalid response
          // forever. Release only this exact entry and fail closed instead.
          if (this.generationInterrupts.get(fingerprint) === entry) {
            this.generationInterrupts.delete(fingerprint);
          }
          throw error;
        }
        entry.result = result;
        return result;
      })
      .catch(error => {
        if (isDefinitiveProductOperationError(error)) {
          this.generationInterrupts.delete(fingerprint);
        }
        throw error;
      })
      .finally(() => {
        if (entry.promise === promise) entry.promise = undefined;
      });
    entry.promise = promise;
    return promise;
  }

  async acknowledgePresentation(input: {
    response_id: string;
    response_generation: number;
    surface: 'text' | 'audio';
    unit_id: string;
    contiguous_cursor: number;
    presented_at: string;
  }): Promise<JsonObject> {
    const binding = this.requireActiveBinding();
    if (
      !Number.isSafeInteger(input.response_generation) ||
      input.response_generation < 0 ||
      !Number.isSafeInteger(input.contiguous_cursor) ||
      input.contiguous_cursor < 0 ||
      (input.surface !== 'text' && input.surface !== 'audio')
    ) {
      return Promise.reject(new Error('presentation ACK binding is invalid'));
    }
    const params = {
      ...binding,
      response_id: requiredText(input.response_id, 'response_id'),
      response_generation: input.response_generation,
      surface: input.surface,
      unit_id: requiredText(input.unit_id, 'unit_id'),
      contiguous_cursor: input.contiguous_cursor,
      presented_at: requiredText(input.presented_at, 'presented_at'),
    };
    const fingerprint = JSON.stringify(params);
    let retained = this.presentationAcks.get(fingerprint);
    if (retained?.result) return Promise.resolve(retained.result);
    if (retained?.promise) return retained.promise;
    let operation: ProductP2DurableOperation;
    if (!retained) {
      if (this.presentationAckReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed presentation ACK replay has expired'));
      }
      if (this.hasPendingPresentationAck() || this.hasPendingPresentationFailure()) {
        return Promise.reject(new Error('a previous presentation ACK is still unresolved'));
      }
      const completed = this.presentationAcks.size >= PRODUCT_OPERATION_CAPACITY ? completedProductOperationFingerprint(this.presentationAcks) : null;
      if (this.presentationAcks.size >= PRODUCT_OPERATION_CAPACITY && completed === null) {
        return Promise.reject(new Error('bounded presentation ACK ledger is full'));
      }
      const candidate = { requestId: allocateProductRequestId('live-voice-p2-ack') };
      operation = freezeDurableOperation(PRODUCT_P2_PRESENTATION_ACK_METHOD, candidate.requestId, params);
      this.durableOperationJournal?.checkpointOperation(operation);
      if (completed !== null) {
        this.presentationAcks.delete(completed);
        this.presentationAckReplayFence.add(completed);
      }
      retained = candidate;
      this.presentationAcks.set(fingerprint, retained);
    } else {
      operation = freezeDurableOperation(PRODUCT_P2_PRESENTATION_ACK_METHOD, retained.requestId, params);
      this.durableOperationJournal?.checkpointOperation(operation);
    }
    const entry = retained;
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_PRESENTATION_ACK_METHOD, params, entry.requestId)
      .then(value => {
        const result = requireDurableP2OperationResult(operation, value);
        this.durableOperationJournal?.settleOperation(operation);
        entry.result = result;
        return result;
      })
      .catch(error => {
        if (isDefinitiveProductOperationError(error)) {
          this.durableOperationJournal?.settleOperation(operation);
          this.presentationAcks.delete(fingerprint);
        }
        throw error;
      })
      .finally(() => {
        if (entry.promise === promise) entry.promise = undefined;
      });
    entry.promise = promise;
    return promise;
  }

  async failTaskPresentation(input: {
    response_id: string;
    response_generation: number;
    surface: 'audio';
    unit_id: string;
    failure_reason: 'task_audio_playout_failed' | 'task_audio_owner_unavailable';
  }): Promise<JsonObject> {
    const binding = this.requireActiveBinding();
    if (
      !Number.isSafeInteger(input.response_generation) ||
      input.response_generation < 0 ||
      input.surface !== 'audio' ||
      (input.failure_reason !== 'task_audio_playout_failed' && input.failure_reason !== 'task_audio_owner_unavailable')
    ) {
      return Promise.reject(new Error('presentation failure binding is invalid'));
    }
    const params = {
      ...binding,
      response_id: requiredText(input.response_id, 'response_id'),
      response_generation: input.response_generation,
      surface: input.surface,
      unit_id: requiredText(input.unit_id, 'unit_id'),
      failure_reason: input.failure_reason,
    };
    const fingerprint = JSON.stringify(params);
    let retained = this.presentationFailures.get(fingerprint);
    if (retained?.result) return Promise.resolve(retained.result);
    if (retained?.promise) return retained.promise;
    if (!retained) {
      if (this.presentationFailureReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed presentation failure replay has expired'));
      }
      if (this.hasPendingPresentationAck() || this.hasPendingPresentationFailure()) {
        return Promise.reject(new Error('a previous presentation settlement is still unresolved'));
      }
      const completed =
        this.presentationFailures.size >= PRODUCT_OPERATION_CAPACITY
          ? completedProductOperationFingerprint(this.presentationFailures)
          : null;
      if (this.presentationFailures.size >= PRODUCT_OPERATION_CAPACITY && completed === null) {
        return Promise.reject(new Error('bounded presentation failure ledger is full'));
      }
      retained = { requestId: allocateProductRequestId('live-voice-p2-presentation-failed') };
      if (completed !== null) {
        this.presentationFailures.delete(completed);
        this.presentationFailureReplayFence.add(completed);
      }
      this.presentationFailures.set(fingerprint, retained);
    }
    const entry = retained;
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_PRESENTATION_FAILED_METHOD, params, entry.requestId)
      .then(value => {
        const result = requireP2BoundOperationResult(value, 'presentation_failed_fallback_text', binding);
        if (
          result.response_id !== params.response_id ||
          result.response_generation !== params.response_generation ||
          result.surface !== 'audio' ||
          result.unit_id !== params.unit_id ||
          result.failure_reason !== params.failure_reason ||
          result.fallback !== 'text' ||
          typeof result.replayed !== 'boolean'
        ) {
          throw new Error('product P2 presentation failure result binding is invalid');
        }
        entry.result = result;
        return result;
      })
      .catch(error => {
        if (isDefinitiveProductOperationError(error)) this.presentationFailures.delete(fingerprint);
        throw error;
      })
      .finally(() => {
        if (entry.promise === promise) entry.promise = undefined;
      });
    entry.promise = promise;
    return promise;
  }

  close(): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) {
      this.notificationQueue = [];
      this.lastNotificationPublishSeq = null;
      this.status = 'disabled';
      return Promise.resolve(this.publish());
    }
    this.notificationQueue = [];
    this.lastNotificationPublishSeq = null;
    this.notificationRequestId = null;
    if (this.closePromise) return this.closePromise;
    // Publish the lifecycle fence synchronously. Awaited activation/authority
    // work may settle later, but no continuation may start a new media effect.
    this.closing = true;
    const pendingActivation = this.activationPromise ? this.activationPromise.catch(() => this.snapshot()) : Promise.resolve(this.snapshot());
    const pendingMediaAuthority = this.mediaAuthorityRefreshPromise
      ? this.mediaAuthorityRefreshPromise.catch(() => this.snapshot())
      : Promise.resolve(this.snapshot());
    const mediaStartReservation = this.mediaStartReservation;
    let pendingMediaStart: Promise<void>;
    try {
      pendingMediaStart = mediaStartReservation ? Promise.resolve(mediaStartReservation.cancel()) : Promise.resolve();
    } catch (error) {
      pendingMediaStart = Promise.reject(error);
    }
    const waitForActivation = Promise.all([pendingActivation, pendingMediaAuthority, pendingMediaStart]).then(() => this.snapshot());
    this.closePromise = waitForActivation
      .then(async () => {
        const binding = this.binding;
        if (!binding || !this.activationAttempted || !this.cleanupRequired) {
          this.status = 'closed';
          this.reason = null;
          this.binding = null;
          this.activationAttempted = false;
          this.cleanupRequired = false;
          return this.publish();
        }
        const value = await this.request(PRODUCT_P2_CLOSE_METHOD, { ...binding });
        requireResult(value, 'closed', binding);
        this.status = 'closed';
        this.reason = null;
        this.binding = null;
        this.activationAttempted = false;
        this.cleanupRequired = false;
        return this.publish();
      })
      .catch(error => {
        this.status = 'cleanup_pending';
        this.reason = error instanceof Error ? error.message : 'product P2 cleanup pending';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.closePromise = null;
      });
    return this.closePromise;
  }

  closeWithRetry(options: ProductWebCloseRetryOptions<ProductWebP2ActivationSnapshot> = {}): Promise<ProductWebP2ActivationSnapshot> {
    if (options.on_retry) {
      this.closeRetryObservers.add(options.on_retry);
      if (this.closeRetryPromise && this.status === 'cleanup_pending') {
        try {
          options.on_retry(this.snapshot(), 0);
        } catch {
          // A diagnostic observer must never interrupt exact cleanup.
        }
      }
    }
    if (this.closeRetryPromise) return this.closeRetryPromise;
    let retained: Promise<ProductWebP2ActivationSnapshot>;
    retained = closeWithBoundedRetry({
      close: () => this.close(),
      snapshot: () => this.snapshot(),
      options: {
        ...options,
        on_retry: (snapshot, attempt) => {
          for (const observer of this.closeRetryObservers) {
            try {
              observer(snapshot, attempt);
            } catch {
              // A diagnostic observer must never interrupt exact cleanup.
            }
          }
        },
      },
    }).finally(() => {
      if (this.closeRetryPromise === retained) {
        this.closeRetryPromise = null;
        this.closeRetryObservers.clear();
      }
    });
    this.closeRetryPromise = retained;
    return retained;
  }

  private publish(): ProductWebP2ActivationSnapshot {
    const snapshot = this.snapshot();
    this.onSnapshot?.(snapshot);
    return snapshot;
  }

  private requireActiveBinding(): ProductWebP2ActivationBinding {
    if (this.closing || this.status !== 'active' || this.binding === null) {
      throw new Error('product P2 activation is not active');
    }
    return this.binding;
  }
}

export type ProductP2PollRecoveryResult<TSuccessor> =
  { readonly kind: 'notification'; readonly notification: JsonObject } | { readonly kind: 'recovered'; readonly successor: TSuccessor | null };

/**
 * Poll one retained P2 notification and own the exact closed-route handoff.
 *
 * Ambiguous failures remain retained because `settle_retained_operations`
 * throws.  An authoritative closed stream clears the retained poll, closes
 * the exact old activation, and only then permits a new generation.
 */
export async function pollProductP2RouteWithRecovery<TSuccessor>(input: {
  owner: ProductWebP2ActivationOwner;
  is_current: () => boolean;
  settle_retained_operations: () => Promise<void>;
  can_activate_successor: () => boolean;
  activate_successor: () => Promise<TSuccessor>;
}): Promise<ProductP2PollRecoveryResult<TSuccessor>> {
  try {
    const notification = await retryRetainedProductOperation({
      operation: () => input.owner.nextNotification(),
      is_current: input.is_current,
    });
    return { kind: 'notification', notification };
  } catch {
    await input.settle_retained_operations();
    await input.owner.closeWithRetry();
    if (!input.can_activate_successor()) {
      return { kind: 'recovered', successor: null };
    }
    return {
      kind: 'recovered',
      successor: await input.activate_successor(),
    };
  }
}

/** Credential-free Web owner for one exact server-issued P3 mutation confirmation. */
export class ProductWebP3MutationOwner {
  private readonly enabled: boolean;
  private readonly request: ProductWebRequest;
  private pending: {
    fingerprint: string;
    input: ProductWebP3MutationInput;
    issueRequestId: string;
    receipt?: ProductWebP3ConfirmationReceipt;
    issuePromise?: Promise<ProductWebP3ConfirmationReceipt>;
    mutationRequestId?: string;
    mutationPromise?: Promise<JsonObject>;
  } | null = null;

  constructor(input: { enabled: boolean; request: ProductWebRequest }) {
    if (typeof input.request !== 'function') throw new Error('product request owner is required');
    this.enabled = input.enabled;
    this.request = input.request;
  }

  hasPendingMutation(): boolean {
    return this.pending !== null;
  }

  async issue(input: ProductWebP3MutationInput): Promise<ProductWebP3ConfirmationReceipt> {
    if (!this.enabled) throw new Error('product P3 mutation is disabled');
    const frozen = freezeP3MutationInput(input);
    const fingerprint = JSON.stringify(frozen);
    let pending = this.pending;
    if (pending !== null) {
      if (pending.fingerprint !== fingerprint) {
        throw new Error('a different product P3 confirmation is already owned');
      }
      if (pending.receipt) return pending.receipt;
      if (pending.issuePromise) return pending.issuePromise;
    } else {
      pending = {
        fingerprint,
        input: frozen,
        issueRequestId: allocateProductRequestId('live-voice-p3-confirmation'),
      };
      this.pending = pending;
    }
    const retained = pending;
    let issuePromise: Promise<ProductWebP3ConfirmationReceipt>;
    issuePromise = this.request(PRODUCT_P3_CONFIRMATION_ISSUE_METHOD, { ...frozen }, retained.issueRequestId)
      .then(value => {
        const payload = objectValue(value);
        const result = objectValue(payload?.result);
        const targetTaskId = frozen.operation === 'task.create' ? null : frozen.task_id;
        if (
          payload?.ok !== true ||
          result?.status !== 'confirmation_issued' ||
          result.operation !== frozen.operation ||
          result.command_id !== frozen.command_id ||
          result.target_task_id !== targetTaskId ||
          typeof result.confirmation_id !== 'string' ||
          typeof result.expires_at !== 'string'
        ) {
          throw new Error('product P3 confirmation response is unavailable');
        }
        const receipt = Object.freeze({
          confirmation_id: requiredText(result.confirmation_id, 'confirmation_id'),
          expires_at: requiredText(result.expires_at, 'expires_at'),
          operation: frozen.operation,
          command_id: frozen.command_id,
          target_task_id: targetTaskId,
          task_control_binding: requireP3TaskControlBinding(result.task_control_binding, frozen),
        });
        if (this.pending === retained) retained.receipt = receipt;
        return receipt;
      })
      .catch(error => {
        if (this.pending === retained && isDefinitiveProductOperationError(error)) {
          this.pending = null;
        }
        throw error;
      })
      .finally(() => {
        if (this.pending === retained && retained.issuePromise === issuePromise) {
          retained.issuePromise = undefined;
        }
      });
    retained.issuePromise = issuePromise;
    return issuePromise;
  }

  async mutate(input: ProductWebP3MutationInput): Promise<JsonObject> {
    if (!this.enabled) throw new Error('product P3 mutation is disabled');
    const frozen = freezeP3MutationInput(input);
    const pending = this.pending;
    if (pending === null || pending.fingerprint !== JSON.stringify(frozen)) {
      throw new Error('exact product P3 confirmation is required');
    }
    if (!pending.receipt) throw new Error('exact product P3 confirmation is required');
    if (pending.mutationPromise) return pending.mutationPromise;
    pending.mutationRequestId ??= allocateProductRequestId('live-voice-p3-mutation');
    const retained = pending;
    let mutationPromise: Promise<JsonObject>;
    mutationPromise = this.request(
      PRODUCT_P3_MUTATE_METHOD,
      {
        ...frozen,
        confirmation_id: pending.receipt.confirmation_id,
      },
      pending.mutationRequestId,
    )
      .then(value => {
        const payload = objectValue(value);
        const result = objectValue(payload?.result);
        const targetTaskId = frozen.operation === 'task.create' ? null : frozen.task_id;
        if (
          payload?.ok !== true ||
          result?.status !== 'mutation_processed' ||
          result.operation !== frozen.operation ||
          result.command_id !== frozen.command_id ||
          result.target_task_id !== targetTaskId ||
          objectValue(result.formal_task_result) === null
        ) {
          throw new Error('product P3 mutation response is unavailable');
        }
        const frozenResult = Object.freeze({ ...result });
        if (this.pending === retained) this.pending = null;
        return frozenResult;
      })
      .catch(error => {
        if (this.pending === retained && isDefinitiveProductOperationError(error)) {
          this.pending = null;
        }
        throw error;
      })
      .finally(() => {
        if (this.pending === retained && retained.mutationPromise === mutationPromise) {
          retained.mutationPromise = undefined;
        }
      });
    retained.mutationPromise = mutationPromise;
    return mutationPromise;
  }
}

/** Retained stock-Web owner for one query-selected formal text-progress route. */
export class ProductWebP3ProgressOwner {
  private readonly enabled: boolean;
  private readonly request: ProductWebRequest;
  private readonly onSnapshot?: (snapshot: ProductWebP3ProgressSnapshot) => void;
  private binding: ProductWebP3ProgressBinding | null = null;
  private status: ProductWebP2ActivationStatus;
  private reason: string | null = null;
  private requestedOriginKind: 'text' | 'voice' | null = null;
  private effectiveOriginKind: 'text' | 'voice' | null = null;
  private voiceProgress: 'available' | 'unavailable' | null = null;
  private voiceReason: string | null = null;
  private fallbackReason: string | null = null;
  private activationAttempted = false;
  private cleanupRequired = false;
  private startPromise: Promise<ProductWebP3ProgressSnapshot> | null = null;
  private closePromise: Promise<ProductWebP3ProgressSnapshot> | null = null;
  private closeRetryPromise: Promise<ProductWebP3ProgressSnapshot> | null = null;
  private readonly closeRetryObservers = new Set<ProductWebCloseRetryObserver<ProductWebP3ProgressSnapshot>>();

  constructor(input: { enabled: boolean; request: ProductWebRequest; on_snapshot?: (snapshot: ProductWebP3ProgressSnapshot) => void }) {
    if (typeof input.request !== 'function') throw new Error('product request owner is required');
    this.enabled = input.enabled;
    this.request = input.request;
    this.onSnapshot = input.on_snapshot;
    this.status = input.enabled ? 'idle' : 'disabled';
    this.publish();
  }

  snapshot(): ProductWebP3ProgressSnapshot {
    return Object.freeze({
      status: this.status,
      binding: this.binding,
      reason: this.reason,
      requested_origin_kind: this.requestedOriginKind,
      effective_origin_kind: this.effectiveOriginKind,
      voice_progress: this.voiceProgress,
      voice_reason: this.voiceReason,
      fallback_reason: this.fallbackReason,
    });
  }

  needsCleanup(): boolean {
    return this.startPromise !== null || this.cleanupRequired;
  }

  start(input: {
    session_id: string;
    correlation_id: string;
    origin_id: string;
    generation_id: string;
    generation: number | ((task_id: string) => Promise<number>);
    task_id?: string;
  }): Promise<ProductWebP3ProgressSnapshot> {
    if (!this.enabled) return Promise.resolve(this.snapshot());
    if (this.startPromise) return this.startPromise;
    if (this.status === 'active') return Promise.resolve(this.snapshot());
    const sessionId = requiredText(input.session_id, 'session_id');
    const base = {
      session_id: sessionId,
      correlation_id: requiredText(input.correlation_id, 'correlation_id'),
      origin_id: requiredText(input.origin_id, 'origin_id'),
      generation_id: requiredText(input.generation_id, 'generation_id'),
    };
    if (typeof input.generation !== 'function' && (!Number.isSafeInteger(input.generation) || input.generation <= 0)) {
      return Promise.reject(new Error('generation is invalid'));
    }
    const exactTaskId = input.task_id === undefined ? null : requiredText(input.task_id, 'task_id');
    this.cleanupRequired = false;
    this.status = 'activating';
    this.reason = null;
    this.requestedOriginKind = null;
    this.effectiveOriginKind = null;
    this.voiceProgress = null;
    this.voiceReason = null;
    this.fallbackReason = null;
    this.publish();
    const selectedTask =
      exactTaskId === null ? this.request(PRODUCT_P3_TASK_LIST_METHOD, { session_id: sessionId }).then(selectSingleActiveTask) : Promise.resolve(exactTaskId);
    this.startPromise = selectedTask
      .then(async taskId => {
        const generation = typeof input.generation === 'function' ? await input.generation(taskId) : input.generation;
        const binding = freezeP3Binding({ ...base, task_id: taskId, generation });
        this.binding = binding;
        this.activationAttempted = true;
        return this.request(PRODUCT_P3_PROGRESS_ACTIVATE_METHOD, { ...binding }).then(response => {
          let result: JsonObject;
          try {
            result = requireP3Result(response, 'active', binding);
            const delivery = parseP3ActivationDelivery(result);
            this.requestedOriginKind = delivery.requested_origin_kind;
            this.effectiveOriginKind = delivery.effective_origin_kind;
            this.voiceProgress = delivery.voice_progress;
            this.voiceReason = delivery.voice_reason;
            this.fallbackReason = delivery.fallback_reason;
          } catch (error) {
            throw ambiguousActivationResponse(error);
          }
          this.cleanupRequired = true;
          this.status = 'active';
          this.reason = null;
          return this.publish();
        });
      })
      .catch(error => {
        this.cleanupRequired = this.binding !== null && requiresProductActivationCleanup(error);
        this.status = 'unavailable';
        this.reason = error instanceof Error ? error.message : 'product P3 progress unavailable';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.startPromise = null;
      });
    return this.startPromise;
  }

  close(): Promise<ProductWebP3ProgressSnapshot> {
    if (!this.enabled) {
      this.status = 'disabled';
      return Promise.resolve(this.publish());
    }
    if (this.closePromise) return this.closePromise;
    const waitForStart = this.startPromise ? this.startPromise.catch(() => this.snapshot()) : Promise.resolve(this.snapshot());
    this.closePromise = waitForStart
      .then(async () => {
        const binding = this.binding;
        if (!binding || !this.activationAttempted || !this.cleanupRequired) {
          this.status = 'closed';
          this.reason = null;
          this.binding = null;
          this.activationAttempted = false;
          this.cleanupRequired = false;
          this.requestedOriginKind = null;
          this.effectiveOriginKind = null;
          this.voiceProgress = null;
          this.voiceReason = null;
          this.fallbackReason = null;
          return this.publish();
        }
        const value = await this.request(PRODUCT_P3_PROGRESS_CLOSE_METHOD, {
          ...binding,
        });
        requireP3Result(value, 'closed', binding);
        this.status = 'closed';
        this.reason = null;
        this.binding = null;
        this.activationAttempted = false;
        this.cleanupRequired = false;
        this.requestedOriginKind = null;
        this.effectiveOriginKind = null;
        this.voiceProgress = null;
        this.voiceReason = null;
        this.fallbackReason = null;
        return this.publish();
      })
      .catch(error => {
        this.status = 'cleanup_pending';
        this.reason = error instanceof Error ? error.message : 'product P3 cleanup pending';
        this.publish();
        throw error;
      })
      .finally(() => {
        this.closePromise = null;
      });
    return this.closePromise;
  }

  closeWithRetry(options: ProductWebCloseRetryOptions<ProductWebP3ProgressSnapshot> = {}): Promise<ProductWebP3ProgressSnapshot> {
    if (options.on_retry) {
      this.closeRetryObservers.add(options.on_retry);
      if (this.closeRetryPromise && this.status === 'cleanup_pending') {
        try {
          options.on_retry(this.snapshot(), 0);
        } catch {
          // A diagnostic observer must never interrupt exact cleanup.
        }
      }
    }
    if (this.closeRetryPromise) return this.closeRetryPromise;
    let retained: Promise<ProductWebP3ProgressSnapshot>;
    retained = closeWithBoundedRetry({
      close: () => this.close(),
      snapshot: () => this.snapshot(),
      options: {
        ...options,
        on_retry: (snapshot, attempt) => {
          for (const observer of this.closeRetryObservers) {
            try {
              observer(snapshot, attempt);
            } catch {
              // A diagnostic observer must never interrupt exact cleanup.
            }
          }
        },
      },
    }).finally(() => {
      if (this.closeRetryPromise === retained) {
        this.closeRetryPromise = null;
        this.closeRetryObservers.clear();
      }
    });
    this.closeRetryPromise = retained;
    return retained;
  }

  private publish(): ProductWebP3ProgressSnapshot {
    const snapshot = this.snapshot();
    this.onSnapshot?.(snapshot);
    return snapshot;
  }
}
