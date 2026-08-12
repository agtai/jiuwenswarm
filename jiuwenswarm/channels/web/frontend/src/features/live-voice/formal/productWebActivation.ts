export const PRODUCT_P2_ACTIVATE_METHOD = 'live_voice.composition.p2.activate' as const;
export const PRODUCT_P2_CLOSE_METHOD = 'live_voice.composition.p2.close' as const;
export const PRODUCT_P2_SUBMIT_METHOD = 'live_voice.composition.p2.submit' as const;
export const PRODUCT_P2_NOTIFICATION_NEXT_METHOD = 'live_voice.composition.p2.notification.next' as const;
export const PRODUCT_P2_PRESENTATION_ACK_METHOD = 'live_voice.composition.p2.presentation.ack' as const;
export const PRODUCT_P2_BARGE_IN_METHOD = 'live_voice.composition.p2.barge_in' as const;
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

function evictCompletedProductOperation<T>(
  ledger: Map<string, { requestId: string; result?: T; promise?: Promise<T> }>,
  replayFence: ProductReplayFence
): boolean {
  for (const [fingerprint, entry] of ledger) {
    if (entry.result === undefined) continue;
    ledger.delete(fingerprint);
    replayFence.add(fingerprint);
    return true;
  }
  return false;
}
let productRequestSequence = 0;

function allocateProductRequestId(prefix: string): string {
  productRequestSequence += 1;
  const random = globalThis.crypto?.randomUUID?.();
  return `${prefix}-${random ?? `${Date.now()}-${productRequestSequence}`}`;
}

export type ProductWebRequest = (method: string, params: Record<string, unknown>, request_id?: string) => Promise<unknown>;

export type ProductP2DurableOperationMethod = typeof PRODUCT_P2_SUBMIT_METHOD | typeof PRODUCT_P2_PRESENTATION_ACK_METHOD | typeof PRODUCT_P2_BARGE_IN_METHOD;

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
const PRODUCT_P2_DURABLE_TEXT_MAX_LENGTH = 100_000;

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
  return [...binding, 'action_id', 'response_id', 'response_generation', 'cancel_response'];
}

/** Strictly parse one bounded, secret-free request envelope before transport or persistence. */
export function validateProductP2DurableOperation(value: unknown, expectedBinding?: Readonly<ProductWebP2ActivationBinding>): ProductP2DurableOperation {
  let serialized: string;
  try {
    serialized = JSON.stringify(value);
  } catch {
    throw new Error('durable product operation cannot be serialized');
  }
  if (!serialized || new TextEncoder().encode(serialized).byteLength > PRODUCT_P2_DURABLE_OPERATION_MAX_BYTES) {
    throw new Error('durable product operation exceeds its bound');
  }
  const operation = exactRecord(value, ['method', 'request_id', 'params'], 'durable product operation');
  if (
    operation.method !== PRODUCT_P2_SUBMIT_METHOD &&
    operation.method !== PRODUCT_P2_PRESENTATION_ACK_METHOD &&
    operation.method !== PRODUCT_P2_BARGE_IN_METHOD
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
    exactDurableText(params.text, 'text', PRODUCT_P2_DURABLE_TEXT_MAX_LENGTH);
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
  } else {
    exactDurableText(params.action_id, 'action_id');
    exactDurableText(params.response_id, 'response_id');
    exactDurableGeneration(params.response_generation, 'response_generation', true);
    if (typeof params.cancel_response !== 'boolean') throw new Error('durable product barge-in policy is invalid');
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
      (AMBIGUOUS_ACTIVATION_TRANSPORT_CODES.has(candidate.code) || candidate.code === 'WS_NOT_READY' || candidate.code === 'UNAVAILABLE'))
  );
}

const DEFINITIVE_PRODUCT_FAILURE_CODES = new Set([
  'INVALID_ARGUMENT',
  'UNAUTHENTICATED',
  'PERMISSION_DENIED',
  'NOT_FOUND',
  'CONFLICT',
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
    (typeof candidate?.reason === 'string' && DEFINITIVE_PRODUCT_FAILURE_REASONS.has(candidate.reason))
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
  params: Readonly<Record<string, unknown>>
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
  expectedStatus: 'round_accepted' | 'task_origin_accepted' | 'notification' | 'presentation_acknowledged' | 'barge_in_applied',
  binding: Readonly<ProductWebP2ActivationBinding>
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

function parseP3ActivationDelivery(result: JsonObject): Pick<
  ProductWebP3ProgressSnapshot,
  'requested_origin_kind' | 'effective_origin_kind' | 'voice_progress' | 'voice_reason' | 'fallback_reason'
> {
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
  private binding: ProductWebP2ActivationBinding | null = null;
  private status: ProductWebP2ActivationStatus;
  private reason: string | null = null;
  private activationAttempted = false;
  private activationReplayed: boolean | null = null;
  private cleanupRequired = false;
  private activationPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private closePromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private closeRetryPromise: Promise<ProductWebP2ActivationSnapshot> | null = null;
  private readonly closeRetryObservers = new Set<ProductWebCloseRetryObserver<ProductWebP2ActivationSnapshot>>();
  private readonly submissions = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly presentationAcks = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly bargeIns = new Map<string, { requestId: string; result?: JsonObject; promise?: Promise<JsonObject> }>();
  private readonly submissionReplayFence = new ProductReplayFence();
  private readonly presentationAckReplayFence = new ProductReplayFence();
  private readonly bargeInReplayFence = new ProductReplayFence();
  private notificationRequestId: string | null = null;
  private notificationPromise: Promise<JsonObject> | null = null;
  private notificationSequence = 0;

  constructor(input: {
    enabled: boolean;
    request: ProductWebRequest;
    on_snapshot?: (snapshot: ProductWebP2ActivationSnapshot) => void;
    durable_operation_journal?: ProductP2DurableOperationJournal;
  }) {
    if (typeof input.request !== 'function') throw new Error('product request owner is required');
    this.enabled = input.enabled;
    this.request = input.request;
    this.durableOperationJournal = input.durable_operation_journal;
    this.onSnapshot = input.on_snapshot;
    this.status = input.enabled ? 'idle' : 'disabled';
    this.publish();
  }

  snapshot(): ProductWebP2ActivationSnapshot {
    return Object.freeze({ status: this.status, binding: this.binding, reason: this.reason });
  }

  needsCleanup(): boolean {
    return this.activationPromise !== null || this.cleanupRequired;
  }

  activationWasReplayed(): boolean | null {
    return this.activationReplayed;
  }

  start(input: Readonly<ProductWebP2ActivationBinding>): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) return Promise.resolve(this.snapshot());
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

  hasPendingSubmission(): boolean {
    return [...this.submissions.values()].some(entry => entry.result === undefined);
  }

  hasPendingNotification(): boolean {
    return this.notificationRequestId !== null;
  }

  hasPendingPresentationAck(): boolean {
    return [...this.presentationAcks.values()].some(entry => entry.result === undefined);
  }

  hasPendingBargeIn(): boolean {
    return [...this.bargeIns.values()].some(entry => entry.result === undefined);
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
      text: requiredContent(input.text, 'text'),
      dispatch_target: dispatchTarget,
      ...(input.voice_commit_receipt ? { voice_commit_receipt: requiredText(input.voice_commit_receipt, 'voice_commit_receipt') } : {}),
      ...(input.critical_confirmation === true ? { critical_confirmation: true } : {}),
    };
    const fingerprint = JSON.stringify(params);
    let retained = this.submissions.get(fingerprint);
    if (retained?.result) return Promise.resolve(retained.result);
    if (retained?.promise) return retained.promise;
    if (!retained) {
      if (this.submissionReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed product submission replay has expired'));
      }
      if (this.hasPendingSubmission() || this.hasPendingPresentationAck()) {
        return Promise.reject(new Error('a previous product turn is still unresolved'));
      }
      if (this.submissions.size >= PRODUCT_OPERATION_CAPACITY && !evictCompletedProductOperation(this.submissions, this.submissionReplayFence)) {
        return Promise.reject(new Error('bounded product submission ledger is full'));
      }
      retained = { requestId: allocateProductRequestId('live-voice-p2-submit') };
      this.submissions.set(fingerprint, retained);
    }
    const entry = retained;
    const operation = freezeDurableOperation(PRODUCT_P2_SUBMIT_METHOD, entry.requestId, params);
    this.durableOperationJournal?.checkpointOperation(operation);
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
    if (this.notificationPromise) return this.notificationPromise;
    if (this.notificationRequestId === null) {
      this.notificationRequestId = allocateProductRequestId('live-voice-p2-notification');
      this.notificationSequence += 1;
    }
    const requestId = this.notificationRequestId;
    let promise: Promise<JsonObject>;
    promise = this.request(PRODUCT_P2_NOTIFICATION_NEXT_METHOD, { ...binding, notification_sequence: this.notificationSequence }, requestId)
      .then(value => {
        const result = requireP2BoundOperationResult(value, 'notification', binding);
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
    if (!retained) {
      if (this.bargeInReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed barge-in replay has expired'));
      }
      if (this.bargeIns.size >= PRODUCT_OPERATION_CAPACITY && !evictCompletedProductOperation(this.bargeIns, this.bargeInReplayFence)) {
        return Promise.reject(new Error('bounded barge-in ledger is full'));
      }
      retained = { requestId: allocateProductRequestId('live-voice-p2-barge') };
      this.bargeIns.set(fingerprint, retained);
    }
    const entry = retained;
    const operation = freezeDurableOperation(PRODUCT_P2_BARGE_IN_METHOD, entry.requestId, params);
    this.durableOperationJournal?.checkpointOperation(operation);
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
    if (!retained) {
      if (this.presentationAckReplayFence.has(fingerprint)) {
        return Promise.reject(new Error('completed presentation ACK replay has expired'));
      }
      if (this.hasPendingPresentationAck()) {
        return Promise.reject(new Error('a previous presentation ACK is still unresolved'));
      }
      if (this.presentationAcks.size >= PRODUCT_OPERATION_CAPACITY && !evictCompletedProductOperation(this.presentationAcks, this.presentationAckReplayFence)) {
        return Promise.reject(new Error('bounded presentation ACK ledger is full'));
      }
      retained = { requestId: allocateProductRequestId('live-voice-p2-ack') };
      this.presentationAcks.set(fingerprint, retained);
    }
    const entry = retained;
    const operation = freezeDurableOperation(PRODUCT_P2_PRESENTATION_ACK_METHOD, entry.requestId, params);
    this.durableOperationJournal?.checkpointOperation(operation);
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

  close(): Promise<ProductWebP2ActivationSnapshot> {
    if (!this.enabled) {
      this.status = 'disabled';
      return Promise.resolve(this.publish());
    }
    if (this.closePromise) return this.closePromise;
    const waitForActivation = this.activationPromise ? this.activationPromise.catch(() => this.snapshot()) : Promise.resolve(this.snapshot());
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
    if (this.status !== 'active' || this.binding === null) {
      throw new Error('product P2 activation is not active');
    }
    return this.binding;
  }
}

export type ProductP2PollRecoveryResult<TSuccessor> =
  | { readonly kind: 'notification'; readonly notification: JsonObject }
  | { readonly kind: 'recovered'; readonly successor: TSuccessor | null };

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
      pending.mutationRequestId
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
    generation: number;
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
      generation: input.generation,
    };
    if (!Number.isSafeInteger(base.generation) || base.generation <= 0) {
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
      .then(taskId => {
        const binding = freezeP3Binding({ ...base, task_id: taskId });
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
