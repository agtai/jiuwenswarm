export const PRODUCT_P3_TASK_INTENT_METHOD = 'live_voice.composition.p3.intent' as const;
export const PRODUCT_P3_TASK_INTENT_STATUS_METHOD = 'live_voice.composition.p3.intent.status' as const;

export type FormalTaskIntentOperation =
  | 'task.create'
  | 'task.status'
  | 'task.cancel'
  | 'task.provide_input'
  | 'task.update_constraints';
export type FormalTaskIntentSource = 'text' | 'voice';
export type FormalTaskIntentDisposition = 'dispatched' | 'clarification' | 'rejected';

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
  formal_task_result: Readonly<Record<string, unknown>> | null;
}>;

export type FormalTaskIntentOwnerSnapshot = Readonly<{
  status: 'disabled' | 'idle' | 'submitting' | 'clarification' | 'dispatched' | 'rejected' | 'failed' | 'closed';
  pending_confirmation: Readonly<{
    source: FormalTaskIntentSource;
    session_id: string;
    correlation_id: string;
    interaction_id: string;
    operation: Exclude<FormalTaskIntentOperation, 'task.status'>;
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
  requestId: string
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
  phase: 'resolving' | 'clarification' | 'awaiting_confirmation';
  owner_id: string;
  generation: number;
  request_id: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  source: FormalTaskIntentSource;
  operation: FormalTaskIntentOperation;
  task_id: string | null;
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

function parseRecoveryCheckpoint(value: unknown): FormalTaskIntentRecoveryCheckpoint {
  const raw = objectValue(value);
  if (
    raw === null ||
    Object.keys(raw).sort().join(',') !==
      'correlation_id,generation,interaction_id,operation,owner_id,phase,request_id,revision,schema,session_id,source,task_id' ||
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
    (operation !== 'task.create' &&
      operation !== 'task.status' &&
      operation !== 'task.cancel' &&
      operation !== 'task.provide_input' &&
      operation !== 'task.update_constraints') ||
    (phase !== 'resolving' && phase !== 'clarification' && phase !== 'awaiting_confirmation') ||
    !Number.isSafeInteger(raw.generation) ||
    (raw.generation as number) <= 0
  ) {
    throw new Error('formal task intent recovery checkpoint is invalid');
  }
  const taskId = optionalTaskId(raw.task_id);
  if ((operation === 'task.create') !== (taskId === null)) {
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
  });
}

type RecoveryBucket = Readonly<{
  schema: typeof RECOVERY_BUCKET_SCHEMA;
  revision: 2;
  entries: readonly FormalTaskIntentRecoveryCheckpoint[];
}>;

function sameRecoveryCheckpoint(
  left: FormalTaskIntentRecoveryCheckpoint,
  right: FormalTaskIntentRecoveryCheckpoint
): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function parseRecoveryBucket(encoded: string | null): RecoveryBucket {
  if (encoded === null) return Object.freeze({ schema: RECOVERY_BUCKET_SCHEMA, revision: 2, entries: Object.freeze([]) });
  if (
    encoded.length > RECOVERY_BUCKET_MAX_BYTES ||
    new TextEncoder().encode(encoded).byteLength > RECOVERY_BUCKET_MAX_BYTES
  ) {
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

export function createSessionFormalTaskIntentRecoveryJournal(
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
): FormalTaskIntentRecoveryJournal {
  if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function' || typeof storage.removeItem !== 'function') {
    throw new Error('formal task intent recovery storage is unavailable');
  }
  const read = (): RecoveryBucket => parseRecoveryBucket(storage.getItem(RECOVERY_STORAGE_KEY));
  const write = (entries: readonly FormalTaskIntentRecoveryCheckpoint[]): void => {
    if (entries.length > RECOVERY_CAPACITY) throw new Error('formal task intent recovery capacity is full');
    if (
      entries.some(entry => {
        const encodedEntry = JSON.stringify(entry);
        return (
          encodedEntry.length > RECOVERY_CHECKPOINT_MAX_BYTES ||
          new TextEncoder().encode(encodedEntry).byteLength > RECOVERY_CHECKPOINT_MAX_BYTES
        );
      })
    ) {
      throw new Error('formal task intent recovery checkpoint is oversized');
    }
    const bucket = { schema: RECOVERY_BUCKET_SCHEMA, revision: 2, entries };
    const encoded = JSON.stringify(bucket);
    if (
      encoded.length > RECOVERY_BUCKET_MAX_BYTES ||
      new TextEncoder().encode(encoded).byteLength > RECOVERY_BUCKET_MAX_BYTES
    ) {
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
      if (
        encoded.length > RECOVERY_CHECKPOINT_MAX_BYTES ||
        new TextEncoder().encode(encoded).byteLength > RECOVERY_CHECKPOINT_MAX_BYTES
      ) {
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
      if (
        clean.session_id !== expected.session_id ||
        clean.owner_id !== expected.owner_id ||
        clean.generation !== expected.generation + 1
      ) {
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
    interaction_id: input.source === 'voice' ? input.voice_origin?.interaction_id : pending?.interaction_id ?? null,
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
  }>
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
    result.resolver_implementation_class === undefined
      ? null
      : requiredText(result.resolver_implementation_class, 'resolver_implementation_class');
  if (
    disposition !== 'rejected' &&
    (resolutionId === null || commitSha256 === null || provider === null || implementation === null)
  ) {
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
  const token = result.confirmation_token === undefined || result.confirmation_token === null ? null : requiredText(result.confirmation_token, 'confirmation_token', 32);
  const form = result.confirmation_form === undefined || result.confirmation_form === null ? null : requiredText(result.confirmation_form, 'confirmation_form');
  if ((token === null) !== (form === null) || (token !== null && (!HEX_32.test(token) || form !== `confirm task request ${token}`))) {
    throw new Error('formal task intent confirmation binding is invalid');
  }
  if (
    token !== null &&
    (disposition !== 'clarification' ||
      (operation !== 'task.create' &&
        operation !== 'task.cancel' &&
        operation !== 'task.provide_input' &&
        operation !== 'task.update_constraints'))
  ) {
    throw new Error('formal task intent confirmation is not destructive and pending');
  }
  if (disposition === 'dispatched' && operation === null) throw new Error('dispatched task intent has no operation');
  if (disposition === 'clarification' && result.partial_command_count !== 0) throw new Error('clarification reported a partial command');
  const originId = result.origin_id === undefined || result.origin_id === null ? null : requiredText(result.origin_id, 'origin_id');
  const formalResult = result.formal_task_result === undefined || result.formal_task_result === null ? null : objectValue(result.formal_task_result);
  if (result.formal_task_result !== undefined && result.formal_task_result !== null && formalResult === null) {
    throw new Error('formal task result is invalid');
  }
  if (
    disposition === 'dispatched' &&
    (result.origin_kind !== expected.source ||
      originId === null ||
      formalResult === null ||
      (operation === 'task.create' && taskId === null))
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
    formal_task_result: formalResult === null ? null : Object.freeze({ ...formalResult }),
  });
}

function parseRecoveredIntentReceipt(
  value: unknown,
  statusRequestId: string,
  checkpoint: FormalTaskIntentRecoveryCheckpoint
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
    (result.phase !== 'clarification' &&
      result.phase !== 'awaiting_confirmation' &&
      result.phase !== 'final' &&
      result.phase !== 'expired') ||
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
    }
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
  readonly #taskRevisionEnabled: boolean;

  constructor(
    input: Readonly<{
      enabled: boolean;
      request: FormalTaskIntentRequest;
      recovery_journal?: FormalTaskIntentRecoveryJournal | null;
      task_revision_enabled?: boolean;
    }>
  ) {
    this.#enabled = input.enabled;
    this.#request = input.request;
    this.#recoveryJournal = input.recovery_journal ?? null;
    this.#taskRevisionEnabled = input.task_revision_enabled === true;
    this.#status = input.enabled ? 'idle' : 'disabled';
  }

  snapshot(): FormalTaskIntentOwnerSnapshot {
    return Object.freeze({
      status: this.#status,
      pending_confirmation: this.#pending,
      retained_transport: this.#retained !== null || this.#recovery !== null || this.#recoveryBlocked,
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

  submitText(input: Readonly<{ session_id: string; correlation_id: string; text: string; operation: FormalTaskIntentOperation; task_id?: string | null }>): Promise<FormalTaskIntentReceipt> {
    return this.#submit({ ...input, source: 'text', task_id: input.task_id ?? null });
  }

  submitVoice(input: Readonly<{ origin: FormalTaskIntentVoiceOrigin; operation: FormalTaskIntentOperation; task_id?: string | null }>): Promise<FormalTaskIntentReceipt> {
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
      statusRequestId
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
        } else {
          this.#clearOwnedCheckpoint(false);
        }
        this.#adoptReceipt(receipt, checkpoint, checkpoint.interaction_id);
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
    if (
      input.operation !== 'task.create' &&
      input.operation !== 'task.status' &&
      input.operation !== 'task.cancel' &&
      input.operation !== 'task.provide_input' &&
      input.operation !== 'task.update_constraints'
    ) {
      return Promise.reject(new Error('formal task intent operation is unsupported'));
    }
    const revisionOperation =
      input.operation === 'task.provide_input' || input.operation === 'task.update_constraints';
    if (revisionOperation && !this.#taskRevisionEnabled) {
      this.#status = 'rejected';
      this.#reason = 'TASK_REVISION_PRODUCT_ROUTE_DISABLED';
      return Promise.reject(new Error('formal task revision route is disabled'));
    }
    if (revisionOperation && input.source !== 'voice') {
      this.#status = 'rejected';
      this.#reason = 'TASK_REVISION_VOICE_ORIGIN_REQUIRED';
      return Promise.reject(new Error('formal task revision requires a committed voice origin'));
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
    interactionId?: string
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
        });
        if (receipt.disposition === 'clarification') {
          this.#advanceOwnedCheckpoint(receipt.confirmation_token === null ? 'clarification' : 'awaiting_confirmation');
        } else {
          this.#clearOwnedCheckpoint(false);
        }
        this.#retained = null;
        this.#adoptReceipt(receipt, retained.checkpoint, ownedInteraction);
        return receipt;
      })
      .catch(error => {
        if (this.#retained === retained) {
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
    interactionId: string
  ): void {
    this.#receipt = receipt;
    this.#reason = receipt.reason;
    if (receipt.confirmation_token !== null && receipt.confirmation_form !== null) {
      this.#pending = Object.freeze({
        source: binding.source,
        session_id: binding.session_id,
        correlation_id: binding.correlation_id,
        interaction_id: interactionId,
        operation: binding.operation as Exclude<FormalTaskIntentOperation, 'task.status'>,
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
