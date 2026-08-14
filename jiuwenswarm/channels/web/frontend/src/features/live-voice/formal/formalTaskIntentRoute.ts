export const PRODUCT_P3_TASK_INTENT_METHOD = 'live_voice.composition.p3.intent' as const;
export const PRODUCT_P3_TASK_INTENT_STATUS_METHOD = 'live_voice.composition.p3.intent.status' as const;

export type FormalTaskIntentOperation = 'task.create' | 'task.status' | 'task.cancel';
export type FormalTaskIntentSource = 'text' | 'voice';
export type FormalTaskIntentDisposition = 'dispatched' | 'clarification' | 'rejected';

export type FormalTaskIntentTaskControlBinding = Readonly<{
  subject_id: string;
  session_id: string;
  project_id: string;
  correlation_id: string;
  generation: number;
}>;

export type FormalTaskIntentVoiceOrigin = Readonly<{
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  turn_id: string;
  commit_id: string;
}>;

export type FormalTaskIntentReceipt = Readonly<{
  disposition: FormalTaskIntentDisposition;
  reason: string;
  source: FormalTaskIntentSource;
  operation: FormalTaskIntentOperation | null;
  task_id: string | null;
  resolver_provider: string | null;
  resolver_implementation_class: string | null;
  resolution_id: string | null;
  commit_sha256: string | null;
  confirmation_token: string | null;
  confirmation_form: string | null;
  origin_id: string | null;
  task_control_binding: FormalTaskIntentTaskControlBinding | null;
  formal_task_result: Readonly<Record<string, unknown>> | null;
}>;

export type FormalTaskIntentOwnerSnapshot = Readonly<{
  status: 'disabled' | 'idle' | 'submitting' | 'clarification' | 'dispatched' | 'rejected' | 'failed' | 'closed';
  pending_confirmation: Readonly<{
    source: FormalTaskIntentSource;
    session_id: string;
    correlation_id: string;
    interaction_id: string;
    operation: 'task.create' | 'task.cancel';
    task_id: string | null;
    token: string;
    form: string;
  }> | null;
  retained_transport: boolean;
  receipt: FormalTaskIntentReceipt | null;
  reason: string | null;
}>;

export type FormalTaskIntentRequest = (
  method: typeof PRODUCT_P3_TASK_INTENT_METHOD | typeof PRODUCT_P3_TASK_INTENT_STATUS_METHOD,
  params: Readonly<Record<string, unknown>>,
  requestId: string,
) => Promise<unknown>;

type SubmitInput = Readonly<{
  source: FormalTaskIntentSource;
  session_id: string;
  correlation_id: string;
  operation: FormalTaskIntentOperation;
  task_id: string | null;
  text?: string;
  voice_origin?: FormalTaskIntentVoiceOrigin;
}>;

type PendingConfirmation = NonNullable<FormalTaskIntentOwnerSnapshot['pending_confirmation']>;

export type FormalTaskIntentRecoveryCheckpoint = Readonly<{
  schema: 'live-voice.formal-task-intent-recovery.v2';
  revision: 2;
  phase: 'resolving' | 'clarification' | 'awaiting_confirmation' | 'post_create_binding';
  owner_id: string;
  generation: number;
  request_id: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  source: FormalTaskIntentSource;
  operation: FormalTaskIntentOperation;
  task_id: string | null;
  origin_id: string | null;
  result_reason: string | null;
  task_control_binding: FormalTaskIntentTaskControlBinding | null;
}>;

export interface FormalTaskIntentRecoveryJournal {
  load(sessionId: string): FormalTaskIntentRecoveryCheckpoint | null;
  save(checkpoint: FormalTaskIntentRecoveryCheckpoint): void;
  claim(checkpoint: FormalTaskIntentRecoveryCheckpoint, ownerId: string): FormalTaskIntentRecoveryCheckpoint;
  replace(checkpoint: FormalTaskIntentRecoveryCheckpoint, next: FormalTaskIntentRecoveryCheckpoint): void;
  clear(checkpoint: FormalTaskIntentRecoveryCheckpoint): void;
}

type RetainedOperation = {
  readonly fingerprint: string;
  readonly request_id: string;
  readonly params: Readonly<Record<string, unknown>>;
  readonly checkpoint: FormalTaskIntentRecoveryCheckpoint;
  promise: Promise<FormalTaskIntentReceipt> | null;
};

const TASK_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/;
const HEX_32 = /^[0-9a-f]{32}$/;
const HEX_64 = /^[0-9a-f]{64}$/;
const MAX_TEXT = 8_192;
const RECOVERY_SCHEMA = 'live-voice.formal-task-intent-recovery.v2' as const;
const RECOVERY_STORAGE_KEY = 'jiuwenswarm.liveVoice.formalTaskIntentRecovery.v2';
const RECOVERY_BUCKET_SCHEMA = 'live-voice.formal-task-intent-recovery-bucket.v2' as const;
const RECOVERY_CAPACITY = 16;
const RECOVERY_CHECKPOINT_MAX_BYTES = 2_048;
const RECOVERY_BUCKET_MAX_BYTES = 32_768;
let fallbackSequence = 0;

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function requiredText(value: unknown, field: string, maximum = 256): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) throw new Error(`${field} is invalid`);
  return value;
}

function optionalTaskId(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || !TASK_ID.test(value)) throw new Error('task intent target is invalid');
  return value;
}

function parseTaskControlBinding(value: unknown, expected: Readonly<{ session_id: unknown; correlation_id: unknown }>): FormalTaskIntentTaskControlBinding {
  const raw = objectValue(value);
  if (
    raw === null ||
    Object.keys(raw).sort().join(',') !== 'correlation_id,generation,project_id,session_id,subject_id' ||
    !Number.isSafeInteger(raw.generation) ||
    (raw.generation as number) <= 0
  ) {
    throw new Error('formal task intent task-control binding is invalid');
  }
  const binding = Object.freeze({
    subject_id: requiredText(raw.subject_id, 'task-control subject_id'),
    session_id: requiredText(raw.session_id, 'task-control session_id'),
    project_id: requiredText(raw.project_id, 'task-control project_id'),
    correlation_id: requiredText(raw.correlation_id, 'task-control correlation_id'),
    generation: raw.generation as number,
  });
  if (
    binding.session_id !== requiredText(expected.session_id, 'expected task-control session_id') ||
    binding.correlation_id !== requiredText(expected.correlation_id, 'expected task-control correlation_id')
  ) {
    throw new Error('formal task intent task-control binding mismatch');
  }
  return binding;
}

function parseRecoveryCheckpoint(value: unknown): FormalTaskIntentRecoveryCheckpoint {
  const raw = objectValue(value);
  const keys = raw === null ? '' : Object.keys(raw).sort().join(',');
  if (
    raw === null ||
    (keys !== 'correlation_id,generation,interaction_id,operation,owner_id,phase,request_id,revision,schema,session_id,source,task_id' &&
      keys !==
        'correlation_id,generation,interaction_id,operation,origin_id,owner_id,phase,request_id,result_reason,revision,schema,session_id,source,task_control_binding,task_id') ||
    raw.schema !== RECOVERY_SCHEMA ||
    raw.revision !== 2
  ) {
    throw new Error('formal task intent recovery checkpoint is invalid');
  }
  const source = raw.source;
  const operation = raw.operation;
  const phase = raw.phase;
  if (
    (source !== 'text' && source !== 'voice') ||
    (operation !== 'task.create' && operation !== 'task.status' && operation !== 'task.cancel') ||
    (phase !== 'resolving' && phase !== 'clarification' && phase !== 'awaiting_confirmation' && phase !== 'post_create_binding') ||
    !Number.isSafeInteger(raw.generation) ||
    (raw.generation as number) <= 0
  ) {
    throw new Error('formal task intent recovery checkpoint is invalid');
  }
  const taskId = optionalTaskId(raw.task_id);
  const originId = raw.origin_id === undefined || raw.origin_id === null ? null : requiredText(raw.origin_id, 'recovery origin_id');
  const resultReason = raw.result_reason === undefined || raw.result_reason === null ? null : requiredText(raw.result_reason, 'recovery result_reason');
  const taskControlBinding =
    raw.task_control_binding === undefined || raw.task_control_binding === null
      ? null
      : parseTaskControlBinding(raw.task_control_binding, {
          session_id: raw.session_id,
          correlation_id: raw.correlation_id,
        });
  if (
    (phase === 'post_create_binding' &&
      (operation !== 'task.create' || taskId === null || originId === null || resultReason === null || taskControlBinding === null)) ||
    (phase !== 'post_create_binding' &&
      ((operation === 'task.create') !== (taskId === null) || originId !== null || resultReason !== null || taskControlBinding !== null))
  ) {
    throw new Error('formal task intent recovery target is invalid');
  }
  return Object.freeze({
    schema: RECOVERY_SCHEMA,
    revision: 2,
    phase,
    owner_id: requiredText(raw.owner_id, 'recovery owner_id', 128),
    generation: raw.generation as number,
    request_id: requiredText(raw.request_id, 'recovery request_id'),
    session_id: requiredText(raw.session_id, 'recovery session_id'),
    correlation_id: requiredText(raw.correlation_id, 'recovery correlation_id'),
    interaction_id: requiredText(raw.interaction_id, 'recovery interaction_id'),
    source,
    operation,
    task_id: taskId,
    origin_id: originId,
    result_reason: resultReason,
    task_control_binding: taskControlBinding,
  });
}

type RecoveryBucket = Readonly<{
  schema: typeof RECOVERY_BUCKET_SCHEMA;
  revision: 2;
  entries: readonly FormalTaskIntentRecoveryCheckpoint[];
}>;

function sameRecoveryCheckpoint(left: FormalTaskIntentRecoveryCheckpoint, right: FormalTaskIntentRecoveryCheckpoint): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function parseRecoveryBucket(encoded: string | null): RecoveryBucket {
  if (encoded === null) return Object.freeze({ schema: RECOVERY_BUCKET_SCHEMA, revision: 2, entries: Object.freeze([]) });
  if (encoded.length > RECOVERY_BUCKET_MAX_BYTES || new TextEncoder().encode(encoded).byteLength > RECOVERY_BUCKET_MAX_BYTES) {
    throw new Error('formal task intent recovery bucket is oversized');
  }
  let value: unknown;
  try {
    value = JSON.parse(encoded);
  } catch {
    throw new Error('formal task intent recovery bucket is invalid');
  }
  const raw = objectValue(value);
  if (
    raw === null ||
    Object.keys(raw).sort().join(',') !== 'entries,revision,schema' ||
    raw.schema !== RECOVERY_BUCKET_SCHEMA ||
    raw.revision !== 2 ||
    !Array.isArray(raw.entries) ||
    raw.entries.length > RECOVERY_CAPACITY
  ) {
    throw new Error('formal task intent recovery bucket is invalid');
  }
  const entries = raw.entries.map(parseRecoveryCheckpoint);
  if (new Set(entries.map(entry => entry.session_id)).size !== entries.length) {
    throw new Error('formal task intent recovery bucket contains duplicate sessions');
  }
  return Object.freeze({ schema: RECOVERY_BUCKET_SCHEMA, revision: 2, entries: Object.freeze(entries) });
}

export function createSessionFormalTaskIntentRecoveryJournal(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>): FormalTaskIntentRecoveryJournal {
  if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function' || typeof storage.removeItem !== 'function') {
    throw new Error('formal task intent recovery storage is unavailable');
  }
  const read = (): RecoveryBucket => parseRecoveryBucket(storage.getItem(RECOVERY_STORAGE_KEY));
  const write = (entries: readonly FormalTaskIntentRecoveryCheckpoint[]): void => {
    if (entries.length > RECOVERY_CAPACITY) throw new Error('formal task intent recovery capacity is full');
    if (
      entries.some(entry => {
        const encodedEntry = JSON.stringify(entry);
        return encodedEntry.length > RECOVERY_CHECKPOINT_MAX_BYTES || new TextEncoder().encode(encodedEntry).byteLength > RECOVERY_CHECKPOINT_MAX_BYTES;
      })
    ) {
      throw new Error('formal task intent recovery checkpoint is oversized');
    }
    const bucket = { schema: RECOVERY_BUCKET_SCHEMA, revision: 2, entries };
    const encoded = JSON.stringify(bucket);
    if (encoded.length > RECOVERY_BUCKET_MAX_BYTES || new TextEncoder().encode(encoded).byteLength > RECOVERY_BUCKET_MAX_BYTES) {
      throw new Error('formal task intent recovery bucket is oversized');
    }
    storage.setItem(RECOVERY_STORAGE_KEY, encoded);
  };
  const load = (sessionId: string): FormalTaskIntentRecoveryCheckpoint | null => {
    const exactSession = requiredText(sessionId, 'recovery session_id');
    return read().entries.find(entry => entry.session_id === exactSession) ?? null;
  };
  return Object.freeze({
    load,
    save(checkpoint: FormalTaskIntentRecoveryCheckpoint) {
      const clean = parseRecoveryCheckpoint(checkpoint);
      const encoded = JSON.stringify(clean);
      if (encoded.length > RECOVERY_CHECKPOINT_MAX_BYTES || new TextEncoder().encode(encoded).byteLength > RECOVERY_CHECKPOINT_MAX_BYTES) {
        throw new Error('formal task intent recovery checkpoint is oversized');
      }
      const bucket = read();
      if (bucket.entries.some(entry => entry.session_id === clean.session_id)) {
        throw new Error('formal task intent recovery session is already retained');
      }
      if (bucket.entries.length >= RECOVERY_CAPACITY) throw new Error('formal task intent recovery capacity is full');
      write([...bucket.entries, clean]);
    },
    claim(checkpoint: FormalTaskIntentRecoveryCheckpoint, ownerId: string) {
      const expected = parseRecoveryCheckpoint(checkpoint);
      const bucket = read();
      const index = bucket.entries.findIndex(entry => entry.session_id === expected.session_id);
      if (index < 0 || !sameRecoveryCheckpoint(bucket.entries[index]!, expected)) {
        throw new Error('formal task intent recovery ownership changed');
      }
      if (expected.generation >= Number.MAX_SAFE_INTEGER) throw new Error('formal task intent recovery generation is exhausted');
      const claimed = parseRecoveryCheckpoint({
        ...expected,
        owner_id: requiredText(ownerId, 'recovery owner_id', 128),
        generation: expected.generation + 1,
      });
      const entries = [...bucket.entries];
      entries[index] = claimed;
      write(entries);
      return claimed;
    },
    replace(checkpoint: FormalTaskIntentRecoveryCheckpoint, next: FormalTaskIntentRecoveryCheckpoint) {
      const expected = parseRecoveryCheckpoint(checkpoint);
      const clean = parseRecoveryCheckpoint(next);
      if (clean.session_id !== expected.session_id || clean.owner_id !== expected.owner_id || clean.generation !== expected.generation + 1) {
        throw new Error('formal task intent recovery successor is invalid');
      }
      const bucket = read();
      const index = bucket.entries.findIndex(entry => entry.session_id === expected.session_id);
      if (index < 0 || !sameRecoveryCheckpoint(bucket.entries[index]!, expected)) {
        throw new Error('formal task intent recovery ownership changed');
      }
      const entries = [...bucket.entries];
      entries[index] = clean;
      write(entries);
    },
    clear(checkpoint: FormalTaskIntentRecoveryCheckpoint) {
      const expected = parseRecoveryCheckpoint(checkpoint);
      const bucket = read();
      const index = bucket.entries.findIndex(entry => entry.session_id === expected.session_id);
      if (index < 0 || !sameRecoveryCheckpoint(bucket.entries[index]!, expected)) {
        throw new Error('formal task intent recovery ownership changed');
      }
      const entries = bucket.entries.filter((_entry, entryIndex) => entryIndex !== index);
      if (entries.length === 0) storage.removeItem(RECOVERY_STORAGE_KEY);
      else write(entries);
    },
  });
}

function identifier(prefix: string): string {
  fallbackSequence += 1;
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${fallbackSequence}`;
  return `${prefix}-${random}`;
}

function canonicalSemanticInput(input: SubmitInput, pending: PendingConfirmation | null): string {
  return JSON.stringify({
    source: input.source,
    session_id: input.session_id,
    correlation_id: input.correlation_id,
    interaction_id: input.source === 'voice' ? input.voice_origin?.interaction_id : (pending?.interaction_id ?? null),
    turn_id: input.source === 'voice' ? input.voice_origin?.turn_id : null,
    commit_id: input.source === 'voice' ? input.voice_origin?.commit_id : null,
    operation: input.operation,
    task_id: input.task_id,
    text: input.source === 'text' ? input.text : null,
  });
}

function parseSpan(value: unknown): Readonly<{ start: number; end: number }> | null {
  if (value === null) return null;
  const span = objectValue(value);
  if (
    span === null ||
    Object.keys(span).sort().join(',') !== 'end,start' ||
    !Number.isSafeInteger(span.start) ||
    !Number.isSafeInteger(span.end) ||
    (span.start as number) < 0 ||
    (span.end as number) <= (span.start as number)
  ) {
    throw new Error('task intent source span is invalid');
  }
  return Object.freeze({ start: span.start as number, end: span.end as number });
}

function parseIntentReceipt(
  value: unknown,
  expected: Readonly<{
    request_id: string;
    source: FormalTaskIntentSource;
    operation: FormalTaskIntentOperation;
    task_id: string | null;
    session_id: string;
    correlation_id: string;
  }>,
): FormalTaskIntentReceipt {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (payload?.request_id !== expected.request_id || result === null) throw new Error('formal task intent response is invalid');
  const disposition = result.status;
  if (disposition !== 'dispatched' && disposition !== 'clarification' && disposition !== 'rejected') {
    throw new Error('formal task intent disposition is invalid');
  }
  if ((payload.ok === true) !== (disposition !== 'rejected')) throw new Error('formal task intent response contradicts its disposition');
  const reason = requiredText(result.reason, 'task intent reason');
  const operation = result.operation === null || result.operation === undefined ? null : requiredText(result.operation, 'task intent operation', 32);
  if (operation !== null && operation !== expected.operation) throw new Error('formal task intent operation binding mismatch');
  const taskId = result.task_id === undefined || result.task_id === null ? null : optionalTaskId(result.task_id);
  if (expected.operation !== 'task.create' && operation !== null && taskId !== expected.task_id) {
    throw new Error('formal task intent target binding mismatch');
  }
  const resolutionId = result.resolution_id === undefined ? null : requiredText(result.resolution_id, 'resolution_id', 64);
  const commitSha256 = result.commit_sha256 === undefined ? null : requiredText(result.commit_sha256, 'commit_sha256', 64);
  if ((resolutionId !== null && !HEX_64.test(resolutionId)) || (commitSha256 !== null && !HEX_64.test(commitSha256))) {
    throw new Error('formal task intent digest is invalid');
  }
  const provider = result.resolver_provider === undefined ? null : requiredText(result.resolver_provider, 'resolver_provider');
  const implementation =
    result.resolver_implementation_class === undefined ? null : requiredText(result.resolver_implementation_class, 'resolver_implementation_class');
  if (disposition !== 'rejected' && (resolutionId === null || commitSha256 === null || provider === null || implementation === null)) {
    throw new Error('successful task intent omitted its content-bound resolver identity');
  }
  const sourceSpan = result.source_span === undefined ? null : parseSpan(result.source_span);
  const targetSpan = result.target_span === undefined ? null : parseSpan(result.target_span);
  if (
    (sourceSpan === null) !== (operation === null) ||
    (operation === 'task.create' && targetSpan !== null) ||
    ((operation === 'task.status' || operation === 'task.cancel') && targetSpan === null)
  ) {
    throw new Error('formal task intent span binding is invalid');
  }
  const token =
    result.confirmation_token === undefined || result.confirmation_token === null ? null : requiredText(result.confirmation_token, 'confirmation_token', 32);
  const form = result.confirmation_form === undefined || result.confirmation_form === null ? null : requiredText(result.confirmation_form, 'confirmation_form');
  if ((token === null) !== (form === null) || (token !== null && (!HEX_32.test(token) || form !== `confirm task request ${token}`))) {
    throw new Error('formal task intent confirmation binding is invalid');
  }
  if (token !== null && (disposition !== 'clarification' || (operation !== 'task.create' && operation !== 'task.cancel'))) {
    throw new Error('formal task intent confirmation is not destructive and pending');
  }
  if (disposition === 'dispatched' && operation === null) throw new Error('dispatched task intent has no operation');
  if (disposition === 'clarification' && result.partial_command_count !== 0) throw new Error('clarification reported a partial command');
  const originId = result.origin_id === undefined || result.origin_id === null ? null : requiredText(result.origin_id, 'origin_id');
  const taskControlBinding =
    result.task_control_binding === undefined || result.task_control_binding === null ? null : parseTaskControlBinding(result.task_control_binding, expected);
  const formalResult = result.formal_task_result === undefined || result.formal_task_result === null ? null : objectValue(result.formal_task_result);
  if (result.formal_task_result !== undefined && result.formal_task_result !== null && formalResult === null) {
    throw new Error('formal task result is invalid');
  }
  if (
    disposition === 'dispatched' &&
    (result.origin_kind !== expected.source ||
      originId === null ||
      formalResult === null ||
      (operation === 'task.create' && (taskId === null || taskControlBinding === null)))
  ) {
    throw new Error('dispatched task intent omitted its exact origin or formal result');
  }
  return Object.freeze({
    disposition,
    reason,
    source: expected.source,
    operation: operation as FormalTaskIntentOperation | null,
    task_id: taskId,
    resolver_provider: provider,
    resolver_implementation_class: implementation,
    resolution_id: resolutionId,
    commit_sha256: commitSha256,
    confirmation_token: token,
    confirmation_form: form,
    origin_id: originId,
    task_control_binding: taskControlBinding,
    formal_task_result: formalResult === null ? null : Object.freeze({ ...formalResult }),
  });
}

function parseRecoveredIntentReceipt(
  value: unknown,
  statusRequestId: string,
  checkpoint: FormalTaskIntentRecoveryCheckpoint,
): Readonly<{
  status: 'pending' | 'settled' | 'expired';
  phase: 'clarification' | 'awaiting_confirmation' | 'final' | 'expired';
  receipt: FormalTaskIntentReceipt | null;
}> {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  const intent = objectValue(result?.intent);
  if (
    payload?.request_id !== statusRequestId ||
    payload.ok !== true ||
    (result?.status !== 'pending' && result?.status !== 'settled' && result?.status !== 'expired') ||
    (result.phase !== 'clarification' && result.phase !== 'awaiting_confirmation' && result.phase !== 'final' && result.phase !== 'expired') ||
    result.intent_request_id !== checkpoint.request_id ||
    result.source !== checkpoint.source
  ) {
    throw new Error('formal task intent recovery response is invalid');
  }
  if (result.status === 'expired') {
    if (result.phase !== 'expired' || intent !== null) throw new Error('formal task intent expired response is invalid');
    return Object.freeze({ status: 'expired', phase: 'expired', receipt: null });
  }
  if (
    intent === null ||
    (result.status === 'pending' && result.phase !== 'clarification' && result.phase !== 'awaiting_confirmation') ||
    (result.status === 'settled' && result.phase !== 'final')
  ) {
    throw new Error('formal task intent recovery phase is invalid');
  }
  const receipt = parseIntentReceipt(
    {
      request_id: checkpoint.request_id,
      ok: intent.status !== 'rejected',
      result: intent,
    },
    {
      request_id: checkpoint.request_id,
      source: checkpoint.source,
      operation: checkpoint.operation,
      task_id: checkpoint.task_id,
      session_id: checkpoint.session_id,
      correlation_id: checkpoint.correlation_id,
    },
  );
  if (
    (result.status === 'pending' && receipt.disposition !== 'clarification') ||
    (result.phase === 'awaiting_confirmation') !== (receipt.confirmation_token !== null) ||
    (result.phase === 'clarification' && receipt.confirmation_token !== null) ||
    (result.status === 'settled' && receipt.disposition === 'clarification')
  ) {
    throw new Error('formal task intent recovery disposition is invalid');
  }
  return Object.freeze({ status: result.status, phase: result.phase, receipt });
}

export class ProductFormalTaskIntentOwner {
  readonly #enabled: boolean;
  readonly #request: FormalTaskIntentRequest;
  readonly #recoveryJournal: FormalTaskIntentRecoveryJournal | null;
  readonly #ownerId = identifier('web-task-intent-owner');
  #status: FormalTaskIntentOwnerSnapshot['status'];
  #pending: PendingConfirmation | null = null;
  #retained: RetainedOperation | null = null;
  #receipt: FormalTaskIntentReceipt | null = null;
  #reason: string | null = null;
  #recovery: Promise<FormalTaskIntentReceipt | null> | null = null;
  #ownedCheckpoint: FormalTaskIntentRecoveryCheckpoint | null = null;
  #recoveryBlocked = false;
  #closed = false;

  constructor(
    input: Readonly<{
      enabled: boolean;
      request: FormalTaskIntentRequest;
      recovery_journal?: FormalTaskIntentRecoveryJournal | null;
    }>,
  ) {
    this.#enabled = input.enabled;
    this.#request = input.request;
    this.#recoveryJournal = input.recovery_journal ?? null;
    this.#status = input.enabled ? 'idle' : 'disabled';
  }

  snapshot(): FormalTaskIntentOwnerSnapshot {
    return Object.freeze({
      status: this.#status,
      pending_confirmation: this.#pending,
      retained_transport: this.#retained !== null || this.#recovery !== null || this.#recoveryBlocked || this.#ownedCheckpoint?.phase === 'post_create_binding',
      receipt: this.#receipt,
      reason: this.#reason,
    });
  }

  close(options: Readonly<{ abandon_scope?: boolean }> = {}): FormalTaskIntentOwnerSnapshot {
    this.#closed = true;
    if (options.abandon_scope === true) this.#clearOwnedCheckpoint(false);
    this.#pending = null;
    this.#retained = null;
    this.#recovery = null;
    this.#ownedCheckpoint = null;
    this.#recoveryBlocked = false;
    this.#receipt = null;
    this.#reason = null;
    this.#status = this.#enabled ? 'closed' : 'disabled';
    return this.snapshot();
  }

  cancelPendingConfirmation(): FormalTaskIntentOwnerSnapshot {
    if (this.#retained !== null || this.#recovery !== null || this.#recoveryBlocked) {
      throw new Error('formal task intent outcome is unresolved');
    }
    this.#clearOwnedCheckpoint(true);
    this.#pending = null;
    this.#receipt = null;
    this.#reason = null;
    this.#status = this.#enabled ? 'idle' : 'disabled';
    return this.snapshot();
  }

  completePostCreateBinding(
    input: Readonly<{ session_id: string; correlation_id: string; task_id: string; origin_id: string }>,
  ): FormalTaskIntentOwnerSnapshot {
    if (!this.#enabled || this.#closed) throw new Error('formal task intent route is disabled');
    const checkpoint = this.#ownedCheckpoint;
    if (
      checkpoint === null ||
      checkpoint.phase !== 'post_create_binding' ||
      checkpoint.session_id !== requiredText(input.session_id, 'session_id') ||
      checkpoint.correlation_id !== requiredText(input.correlation_id, 'correlation_id') ||
      checkpoint.task_id !== optionalTaskId(input.task_id) ||
      checkpoint.origin_id !== requiredText(input.origin_id, 'origin_id')
    ) {
      throw new Error('formal task post-create binding ownership changed');
    }
    this.#clearOwnedCheckpoint(true);
    return this.snapshot();
  }

  submitText(
    input: Readonly<{ session_id: string; correlation_id: string; text: string; operation: FormalTaskIntentOperation; task_id?: string | null }>,
  ): Promise<FormalTaskIntentReceipt> {
    return this.#submit({ ...input, source: 'text', task_id: input.task_id ?? null });
  }

  submitVoice(
    input: Readonly<{ origin: FormalTaskIntentVoiceOrigin; operation: FormalTaskIntentOperation; task_id?: string | null }>,
  ): Promise<FormalTaskIntentReceipt> {
    return this.#submit({
      source: 'voice',
      session_id: input.origin.session_id,
      correlation_id: input.origin.correlation_id,
      operation: input.operation,
      task_id: input.task_id ?? null,
      voice_origin: input.origin,
    });
  }

  recoverPending(input: Readonly<{ session_id: string; correlation_id: string }>): Promise<FormalTaskIntentReceipt | null> {
    if (!this.#enabled || this.#closed) return Promise.reject(new Error('formal task intent route is disabled'));
    if (this.#retained !== null) return Promise.reject(new Error('formal task intent transport is active'));
    if (this.#recovery !== null) return this.#recovery;
    const sessionId = requiredText(input.session_id, 'session_id');
    const correlationId = requiredText(input.correlation_id, 'correlation_id');
    let checkpoint: FormalTaskIntentRecoveryCheckpoint | null;
    try {
      checkpoint = this.#recoveryJournal?.load(sessionId) ?? null;
    } catch {
      this.#status = 'failed';
      this.#reason = 'FORMAL_TASK_INTENT_RECOVERY_CHECKPOINT_INVALID';
      this.#recoveryBlocked = true;
      return Promise.reject(new Error('formal task intent recovery checkpoint is invalid'));
    }
    if (checkpoint === null) {
      this.#recoveryBlocked = false;
      return Promise.resolve(null);
    }
    if (checkpoint.session_id !== sessionId || checkpoint.correlation_id !== correlationId) {
      this.#status = 'failed';
      this.#reason = 'FORMAL_TASK_INTENT_RECOVERY_BINDING_MISMATCH';
      this.#recoveryBlocked = true;
      return Promise.reject(new Error('formal task intent recovery binding mismatch'));
    }
    try {
      checkpoint = this.#recoveryJournal?.claim(checkpoint, this.#ownerId) ?? checkpoint;
    } catch {
      this.#status = 'failed';
      this.#reason = 'FORMAL_TASK_INTENT_RECOVERY_OWNERSHIP_CHANGED';
      this.#recoveryBlocked = true;
      return Promise.reject(new Error('formal task intent recovery ownership changed'));
    }
    this.#ownedCheckpoint = checkpoint;
    this.#recoveryBlocked = false;
    if (checkpoint.phase === 'post_create_binding') {
      const receipt: FormalTaskIntentReceipt = Object.freeze({
        disposition: 'dispatched',
        reason: requiredText(checkpoint.result_reason, 'recovery result_reason'),
        source: checkpoint.source,
        operation: 'task.create',
        task_id: optionalTaskId(checkpoint.task_id),
        resolver_provider: null,
        resolver_implementation_class: null,
        resolution_id: null,
        commit_sha256: null,
        confirmation_token: null,
        confirmation_form: null,
        origin_id: requiredText(checkpoint.origin_id, 'recovery origin_id'),
        task_control_binding: checkpoint.task_control_binding,
        formal_task_result: null,
      });
      this.#adoptReceipt(receipt, checkpoint, checkpoint.interaction_id);
      return Promise.resolve(receipt);
    }
    const statusRequestId = identifier('web-task-intent-status');
    this.#status = 'submitting';
    this.#reason = null;
    const recovery = this.#request(
      PRODUCT_P3_TASK_INTENT_STATUS_METHOD,
      {
        session_id: sessionId,
        correlation_id: correlationId,
        intent_request_id: checkpoint.request_id,
      },
      statusRequestId,
    )
      .then(value => {
        if (this.#recovery !== recovery || this.#closed) throw new Error('formal task intent recovery response is stale');
        const recovered = parseRecoveredIntentReceipt(value, statusRequestId, checkpoint);
        if (recovered.status === 'expired') {
          this.#clearOwnedCheckpoint(true);
          this.#pending = null;
          this.#receipt = null;
          this.#status = 'rejected';
          this.#reason = 'TASK_INTENT_CONFIRMATION_EXPIRED';
          this.#recoveryBlocked = false;
          return null;
        }
        const receipt = recovered.receipt;
        if (receipt === null) throw new Error('formal task intent recovery receipt is unavailable');
        if (recovered.status === 'pending') {
          this.#advanceOwnedCheckpoint(recovered.phase as 'clarification' | 'awaiting_confirmation');
        } else if (receipt.disposition === 'dispatched' && receipt.operation === 'task.create') {
          this.#promotePostCreateBinding(receipt);
        } else {
          this.#clearOwnedCheckpoint(false);
        }
        this.#adoptReceipt(receipt, this.#ownedCheckpoint ?? checkpoint, checkpoint.interaction_id);
        this.#recoveryBlocked = false;
        return receipt;
      })
      .catch(error => {
        if (this.#recovery === recovery && !this.#closed) {
          this.#status = 'failed';
          this.#reason = 'FORMAL_TASK_INTENT_RECOVERY_FAILED';
          this.#recoveryBlocked = true;
        }
        throw error;
      })
      .finally(() => {
        if (this.#recovery === recovery) this.#recovery = null;
      });
    this.#recovery = recovery;
    return recovery;
  }

  #submit(input: SubmitInput): Promise<FormalTaskIntentReceipt> {
    if (!this.#enabled || this.#closed) return Promise.reject(new Error('formal task intent route is disabled'));
    const sessionId = requiredText(input.session_id, 'session_id');
    const correlationId = requiredText(input.correlation_id, 'correlation_id');
    if (input.operation !== 'task.create' && input.operation !== 'task.status' && input.operation !== 'task.cancel') {
      return Promise.reject(new Error('formal task intent operation is unsupported'));
    }
    const taskId = input.operation === 'task.create' ? null : optionalTaskId(input.task_id);
    if ((input.operation === 'task.create') !== (taskId === null)) return Promise.reject(new Error('formal task intent target is invalid'));
    const pending = this.#pending;
    if (
      pending !== null &&
      (pending.source !== input.source ||
        pending.session_id !== sessionId ||
        pending.correlation_id !== correlationId ||
        pending.operation !== input.operation ||
        pending.task_id !== taskId ||
        (input.source === 'voice' && pending.interaction_id !== input.voice_origin?.interaction_id))
    ) {
      return Promise.reject(new Error('formal task confirmation cannot change source, scope, operation or target'));
    }
    const semantic = canonicalSemanticInput({ ...input, session_id: sessionId, correlation_id: correlationId, task_id: taskId }, pending);
    if (this.#recovery !== null || this.#recoveryBlocked) {
      return Promise.reject(new Error('formal task intent recovery is active'));
    }
    if (this.#ownedCheckpoint?.phase === 'post_create_binding') {
      return Promise.reject(new Error('formal task post-create binding is unresolved'));
    }
    if (this.#retained !== null) {
      if (this.#retained.fingerprint !== semantic) return Promise.reject(new Error('another formal task intent outcome is unresolved'));
      if (this.#retained.promise !== null) return this.#retained.promise;
      return this.#dispatchRetained(this.#retained, input.source, input.operation, taskId);
    }
    const requestId = identifier('web-task-intent-request');
    let interactionId: string;
    let params: Record<string, unknown>;
    if (input.source === 'voice') {
      const origin = input.voice_origin;
      if (
        origin === undefined ||
        origin.session_id !== sessionId ||
        origin.correlation_id !== correlationId ||
        !requiredText(origin.interaction_id, 'interaction_id') ||
        !requiredText(origin.turn_id, 'turn_id') ||
        !requiredText(origin.commit_id, 'commit_id')
      ) {
        return Promise.reject(new Error('formal voice task origin is invalid'));
      }
      interactionId = origin.interaction_id;
      params = {
        session_id: sessionId,
        correlation_id: correlationId,
        source: 'voice',
        operation_hint: input.operation,
        task_id_hint: taskId,
        interaction_id: origin.interaction_id,
        turn_id: origin.turn_id,
        commit_id: origin.commit_id,
      };
    } else {
      const text = requiredText(input.text, 'task intent text', MAX_TEXT);
      interactionId = pending?.interaction_id ?? identifier('web-task-intent-interaction');
      params = {
        session_id: sessionId,
        correlation_id: correlationId,
        source: 'text',
        operation_hint: input.operation,
        task_id_hint: taskId,
        interaction_id: interactionId,
        turn_id: identifier('web-task-intent-turn'),
        commit_id: identifier('web-task-intent-commit'),
        committed_at: new Date().toISOString(),
        text,
      };
    }
    const retained: RetainedOperation = {
      fingerprint: semantic,
      request_id: requestId,
      params: Object.freeze(params),
      checkpoint: Object.freeze({
        schema: RECOVERY_SCHEMA,
        revision: 2,
        phase: 'resolving',
        owner_id: this.#ownerId,
        generation: (this.#ownedCheckpoint?.generation ?? 0) + 1,
        request_id: requestId,
        session_id: sessionId,
        correlation_id: correlationId,
        interaction_id: interactionId,
        source: input.source,
        operation: input.operation,
        task_id: taskId,
        origin_id: null,
        result_reason: null,
        task_control_binding: null,
      }),
      promise: null,
    };
    try {
      if (this.#ownedCheckpoint === null) this.#recoveryJournal?.save(retained.checkpoint);
      else this.#recoveryJournal?.replace(this.#ownedCheckpoint, retained.checkpoint);
    } catch {
      return Promise.reject(new Error('formal task intent recovery checkpoint failed'));
    }
    this.#ownedCheckpoint = retained.checkpoint;
    this.#retained = retained;
    this.#status = 'submitting';
    this.#reason = null;
    return this.#dispatchRetained(retained, input.source, input.operation, taskId, interactionId);
  }

  #dispatchRetained(
    retained: RetainedOperation,
    source: FormalTaskIntentSource,
    operation: FormalTaskIntentOperation,
    taskId: string | null,
    interactionId?: string,
  ): Promise<FormalTaskIntentReceipt> {
    const ownedInteraction = interactionId ?? requiredText(retained.params.interaction_id, 'interaction_id');
    const promise = this.#request(PRODUCT_P3_TASK_INTENT_METHOD, retained.params, retained.request_id)
      .then(value => {
        if (this.#retained !== retained || this.#closed) throw new Error('formal task intent response is stale');
        const receipt = parseIntentReceipt(value, {
          request_id: retained.request_id,
          source,
          operation,
          task_id: taskId,
          session_id: retained.checkpoint.session_id,
          correlation_id: retained.checkpoint.correlation_id,
        });
        if (receipt.disposition === 'clarification') {
          this.#advanceOwnedCheckpoint(receipt.confirmation_token === null ? 'clarification' : 'awaiting_confirmation');
        } else if (receipt.disposition === 'dispatched' && receipt.operation === 'task.create') {
          this.#promotePostCreateBinding(receipt);
        } else {
          this.#clearOwnedCheckpoint(false);
        }
        this.#retained = null;
        this.#adoptReceipt(receipt, retained.checkpoint, ownedInteraction);
        return receipt;
      })
      .catch(error => {
        if (this.#retained === retained) {
          const errorRecord = objectValue(error);
          try {
            const rejected = parseIntentReceipt(errorRecord?.payload, {
              request_id: retained.request_id,
              source,
              operation,
              task_id: taskId,
              session_id: retained.checkpoint.session_id,
              correlation_id: retained.checkpoint.correlation_id,
            });
            if (rejected.disposition === 'rejected') {
              this.#clearOwnedCheckpoint(false);
              this.#retained = null;
              this.#adoptReceipt(rejected, retained.checkpoint, ownedInteraction);
              return rejected;
            }
          } catch {
            // A transport failure or malformed error payload remains retained
            // for exact status reconciliation. Only a fully parsed server-owned
            // rejected receipt can unlock the current form without a reload.
          }
          retained.promise = null;
          this.#status = 'failed';
          this.#reason = 'FORMAL_TASK_INTENT_REQUEST_FAILED';
        }
        throw error;
      });
    retained.promise = promise;
    return promise;
  }

  #advanceOwnedCheckpoint(phase: 'clarification' | 'awaiting_confirmation'): void {
    const current = this.#ownedCheckpoint;
    if (current === null || current.phase === phase) return;
    const next = Object.freeze({ ...current, phase, generation: current.generation + 1 });
    this.#recoveryJournal?.replace(current, next);
    this.#ownedCheckpoint = next;
  }

  #promotePostCreateBinding(receipt: FormalTaskIntentReceipt): void {
    const current = this.#ownedCheckpoint;
    if (
      current === null ||
      current.operation !== 'task.create' ||
      receipt.disposition !== 'dispatched' ||
      receipt.operation !== 'task.create' ||
      receipt.source !== current.source ||
      receipt.task_id === null ||
      receipt.origin_id === null ||
      receipt.task_control_binding === null
    ) {
      throw new Error('formal task post-create binding receipt is invalid');
    }
    const next = parseRecoveryCheckpoint({
      ...current,
      phase: 'post_create_binding',
      generation: current.generation + 1,
      task_id: receipt.task_id,
      origin_id: receipt.origin_id,
      result_reason: receipt.reason,
      task_control_binding: receipt.task_control_binding,
    });
    this.#recoveryJournal?.replace(current, next);
    this.#ownedCheckpoint = next;
  }

  #clearOwnedCheckpoint(required: boolean): void {
    const current = this.#ownedCheckpoint;
    if (current === null) return;
    try {
      this.#recoveryJournal?.clear(current);
      this.#ownedCheckpoint = null;
    } catch (error) {
      if (required) {
        this.#status = 'failed';
        this.#reason = 'FORMAL_TASK_INTENT_RECOVERY_CLEAR_FAILED';
        this.#recoveryBlocked = true;
        throw error;
      }
    }
  }

  #adoptReceipt(
    receipt: FormalTaskIntentReceipt,
    binding: Pick<FormalTaskIntentRecoveryCheckpoint, 'source' | 'session_id' | 'correlation_id' | 'operation' | 'task_id'>,
    interactionId: string,
  ): void {
    this.#receipt = receipt;
    this.#reason = receipt.reason;
    if (receipt.confirmation_token !== null && receipt.confirmation_form !== null) {
      this.#pending = Object.freeze({
        source: binding.source,
        session_id: binding.session_id,
        correlation_id: binding.correlation_id,
        interaction_id: interactionId,
        operation: binding.operation as 'task.create' | 'task.cancel',
        task_id: binding.task_id,
        token: receipt.confirmation_token,
        form: receipt.confirmation_form,
      });
    } else {
      this.#pending = null;
    }
    this.#status = receipt.disposition;
  }
}
