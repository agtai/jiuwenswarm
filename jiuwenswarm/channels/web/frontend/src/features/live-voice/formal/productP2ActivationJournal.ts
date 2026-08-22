import type {
  ProductP2DurableOperation,
  ProductP2DurableOperationJournal,
  ProductP2DurableOperationMethod,
  ProductWebP2ActivationBinding,
} from './productWebActivation';

const P2_SUBMIT_METHOD: ProductP2DurableOperationMethod = 'live_voice.composition.p2.submit';
const P2_PRESENTATION_ACK_METHOD: ProductP2DurableOperationMethod = 'live_voice.composition.p2.presentation.ack';
const P2_BARGE_IN_METHOD: ProductP2DurableOperationMethod = 'live_voice.composition.p2.barge_in';

export const PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA = 'live-voice.product-p2-activation-journal.v2' as const;
export const PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED = 'P2_REFRESH_RECONCILIATION_REQUIRED' as const;
export const PRODUCT_P2_REFRESH_SERVER_STATE_LOST = 'P2_REFRESH_SERVER_STATE_LOST' as const;

const LEGACY_JOURNAL_SCHEMA = 'live-voice.product-p2-activation-journal.v1' as const;

export type ProductP2ActivationJournalPhase =
  | 'activating'
  | 'active'
  | 'reconciling'
  | 'reconciling_unconfirmed'
  | 'closing'
  | 'closing_unconfirmed'
  | 'closed'
  | 'activation_result_unknown'
  | 'operation_result_unknown'
  | 'operation_reconciling'
  | 'result_unknown';

export type ProductP2ActivationJournalStore = Pick<Storage, 'getItem' | 'setItem'>;

export type ProductP2RecoveryClaim = Readonly<{
  owner_id: string;
  token: string;
  epoch: number;
}>;

/**
 * Recovery ownership covers one sessionStorage lineage in one top-level tab,
 * including owners recreated by refresh. Other top-level tabs have isolated
 * sessionStorage journals; exact server request/binding authority remains the
 * final protection between those independently recovered lineages.
 */
export interface ProductP2RecoveryLease {
  runExclusive<T>(name: string, operation: () => Promise<T>): Promise<T | null>;
}

export type ProductP2ActivationJournalSnapshot = Readonly<{
  schema: typeof PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA;
  revision: number;
  client_instance_id: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  binding: ProductWebP2ActivationBinding | null;
  phase: ProductP2ActivationJournalPhase;
  last_generation: number;
  pending_operation: ProductP2DurableOperation | null;
  recovery_owner_id: string | null;
  recovery_token: string | null;
  recovery_epoch: number;
}>;

type StoredJournal = {
  schema: typeof PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA;
  revision: number;
  client_instance_id: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  binding: ProductWebP2ActivationBinding | null;
  phase: ProductP2ActivationJournalPhase;
  last_generation: number;
  pending_operation: ProductP2DurableOperation | null;
  recovery_owner_id: string | null;
  recovery_token: string | null;
  recovery_epoch: number;
};

const JOURNAL_STORAGE_PREFIX = 'jiuwenswarm.liveVoice.productP2ActivationJournal.v1';
const JOURNAL_PHASES = new Set<ProductP2ActivationJournalPhase>([
  'activating',
  'active',
  'reconciling',
  'reconciling_unconfirmed',
  'closing',
  'closing_unconfirmed',
  'closed',
  'activation_result_unknown',
  'operation_result_unknown',
  'operation_reconciling',
  'result_unknown',
]);
const OPERATION_PHASES = new Set<ProductP2ActivationJournalPhase>(['operation_result_unknown', 'operation_reconciling']);
const MAX_ID_LENGTH = 512;
const MAX_CONTENT_LENGTH = 100_000;
const MAX_DURABLE_OPERATION_BYTES = 131_072;
let recoveryTokenSequence = 0;
let routeIdentitySequence = 0;

function requiredText(value: unknown, field: string, maxLength = MAX_ID_LENGTH): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maxLength) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function optionalText(value: unknown, field: string): string | null {
  return value === null ? null : requiredText(value, field);
}

function safeGeneration(value: unknown, field: string, allowZero = false): number {
  if (!Number.isSafeInteger(value) || typeof value !== 'number' || value < (allowZero ? 0 : 1)) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function exactObject(value: unknown, keys: readonly string[], field: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${field} is invalid`);
  }
  const record = value as Record<string, unknown>;
  const actual = Object.keys(record).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${field} has unexpected fields`);
  }
  return record;
}

function parseBinding(value: unknown, sessionId: string, correlationId: string, interactionId: string): ProductWebP2ActivationBinding | null {
  if (value === null) return null;
  const record = exactObject(value, ['session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation'], 'binding');
  const binding = Object.freeze({
    session_id: requiredText(record.session_id, 'binding.session_id'),
    correlation_id: requiredText(record.correlation_id, 'binding.correlation_id'),
    interaction_id: requiredText(record.interaction_id, 'binding.interaction_id'),
    activation_id: requiredText(record.activation_id, 'binding.activation_id'),
    activation_generation: safeGeneration(record.activation_generation, 'binding.activation_generation'),
  });
  if (binding.session_id !== sessionId || binding.correlation_id !== correlationId || binding.interaction_id !== interactionId) {
    throw new Error('binding scope does not match its journal');
  }
  return binding;
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

function operationParamsKeys(method: ProductP2DurableOperationMethod, record: Record<string, unknown>): readonly string[] {
  const bindingKeys = ['session_id', 'correlation_id', 'interaction_id', 'activation_id', 'activation_generation'];
  if (method === P2_SUBMIT_METHOD) {
    const keys = [...bindingKeys, 'commit_id', 'turn_id', 'committed_at', 'text', 'dispatch_target'];
    if (record.dispatch_target === 'agent') keys.push('response_id');
    if (Object.prototype.hasOwnProperty.call(record, 'voice_commit_receipt')) keys.push('voice_commit_receipt');
    if (Object.prototype.hasOwnProperty.call(record, 'critical_confirmation')) keys.push('critical_confirmation');
    return keys;
  }
  if (method === P2_PRESENTATION_ACK_METHOD) {
    return [...bindingKeys, 'response_id', 'response_generation', 'surface', 'unit_id', 'contiguous_cursor', 'presented_at'];
  }
  return [...bindingKeys, 'action_id', 'response_id', 'response_generation', 'cancel_response'];
}

function parseOperation(value: unknown, binding: ProductWebP2ActivationBinding | null): ProductP2DurableOperation | null {
  if (value === null) return null;
  let serialized: string;
  try {
    serialized = JSON.stringify(value);
  } catch {
    throw new Error('pending operation cannot be serialized');
  }
  if (!serialized || new TextEncoder().encode(serialized).byteLength > MAX_DURABLE_OPERATION_BYTES) {
    throw new Error('pending operation exceeds its durable bound');
  }
  const record = exactObject(value, ['method', 'request_id', 'params'], 'pending operation');
  if (record.method !== P2_SUBMIT_METHOD && record.method !== P2_PRESENTATION_ACK_METHOD && record.method !== P2_BARGE_IN_METHOD) {
    throw new Error('pending operation method is invalid');
  }
  const method = record.method as ProductP2DurableOperationMethod;
  const looseParams = record.params;
  if (looseParams === null || typeof looseParams !== 'object' || Array.isArray(looseParams)) {
    throw new Error('pending operation params are invalid');
  }
  const paramsRecord = looseParams as Record<string, unknown>;
  const params = exactObject(paramsRecord, operationParamsKeys(method, paramsRecord), 'pending operation params');
  const operationBinding = parseBinding(
    {
      session_id: params.session_id,
      correlation_id: params.correlation_id,
      interaction_id: params.interaction_id,
      activation_id: params.activation_id,
      activation_generation: params.activation_generation,
    },
    requiredText(params.session_id, 'pending operation session_id'),
    requiredText(params.correlation_id, 'pending operation correlation_id'),
    requiredText(params.interaction_id, 'pending operation interaction_id')
  );
  if (binding === null || operationBinding === null || !sameBinding(binding, operationBinding)) {
    throw new Error('pending operation binding does not match its journal');
  }
  if (method === P2_SUBMIT_METHOD) {
    requiredText(params.commit_id, 'pending operation commit_id');
    requiredText(params.turn_id, 'pending operation turn_id');
    requiredText(params.committed_at, 'pending operation committed_at');
    requiredText(params.text, 'pending operation text', MAX_CONTENT_LENGTH);
    if (params.dispatch_target !== 'agent' && params.dispatch_target !== 'task') {
      throw new Error('pending operation dispatch target is invalid');
    }
    if (params.dispatch_target === 'agent') requiredText(params.response_id, 'pending operation response_id');
    if (params.voice_commit_receipt !== undefined) requiredText(params.voice_commit_receipt, 'pending operation voice receipt');
    if (params.critical_confirmation !== undefined && params.critical_confirmation !== true) {
      throw new Error('pending operation critical confirmation is invalid');
    }
    if (params.dispatch_target === 'task' && typeof params.voice_commit_receipt !== 'string') {
      throw new Error('pending task operation voice receipt is missing');
    }
  } else if (method === P2_PRESENTATION_ACK_METHOD) {
    requiredText(params.response_id, 'pending ACK response_id');
    safeGeneration(params.response_generation, 'pending ACK response_generation', true);
    if (params.surface !== 'text' && params.surface !== 'audio') throw new Error('pending ACK surface is invalid');
    requiredText(params.unit_id, 'pending ACK unit_id');
    safeGeneration(params.contiguous_cursor, 'pending ACK contiguous_cursor', true);
    requiredText(params.presented_at, 'pending ACK presented_at');
  } else {
    requiredText(params.action_id, 'pending barge-in action_id');
    requiredText(params.response_id, 'pending barge-in response_id');
    safeGeneration(params.response_generation, 'pending barge-in response_generation', true);
    if (typeof params.cancel_response !== 'boolean') throw new Error('pending barge-in policy is invalid');
  }
  return Object.freeze({
    method,
    request_id: requiredText(record.request_id, 'pending operation request_id'),
    params: Object.freeze({ ...params }),
  });
}

function sameOperation(left: Readonly<ProductP2DurableOperation>, right: Readonly<ProductP2DurableOperation>): boolean {
  const canonical = (operation: Readonly<ProductP2DurableOperation>) =>
    JSON.stringify({
      method: operation.method,
      request_id: operation.request_id,
      params: Object.fromEntries(Object.entries(operation.params).sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))),
    });
  return canonical(left) === canonical(right);
}

function parseV2Journal(decoded: unknown, expectedSessionId: string): StoredJournal {
  const record = exactObject(
    decoded,
    [
      'schema',
      'revision',
      'client_instance_id',
      'session_id',
      'correlation_id',
      'interaction_id',
      'binding',
      'phase',
      'last_generation',
      'pending_operation',
      'recovery_owner_id',
      'recovery_token',
      'recovery_epoch',
    ],
    'product P2 activation journal'
  );
  if (record.schema !== PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA) {
    throw new Error('product P2 activation journal schema is unsupported');
  }
  const sessionId = requiredText(record.session_id, 'journal.session_id');
  if (sessionId !== expectedSessionId) throw new Error('product P2 activation journal session mismatch');
  const correlationId = requiredText(record.correlation_id, 'journal.correlation_id');
  const interactionId = requiredText(record.interaction_id, 'journal.interaction_id');
  if (typeof record.phase !== 'string' || !JOURNAL_PHASES.has(record.phase as ProductP2ActivationJournalPhase)) {
    throw new Error('product P2 activation journal phase is invalid');
  }
  const phase = record.phase as ProductP2ActivationJournalPhase;
  const lastGeneration = safeGeneration(record.last_generation, 'journal.last_generation', true);
  const binding = parseBinding(record.binding, sessionId, correlationId, interactionId);
  const pendingOperation = parseOperation(record.pending_operation, binding);
  const recoveryOwner = optionalText(record.recovery_owner_id, 'journal.recovery_owner_id');
  const recoveryToken = optionalText(record.recovery_token, 'journal.recovery_token');
  if (
    (binding === null && lastGeneration !== 0) ||
    (binding !== null && binding.activation_generation !== lastGeneration) ||
    (binding === null && phase !== 'closed') ||
    OPERATION_PHASES.has(phase) !== (pendingOperation !== null) ||
    (recoveryOwner === null) !== (recoveryToken === null)
  ) {
    throw new Error('product P2 activation journal state is inconsistent');
  }
  return {
    schema: PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA,
    revision: safeGeneration(record.revision, 'journal.revision', true),
    client_instance_id: requiredText(record.client_instance_id, 'journal.client_instance_id'),
    session_id: sessionId,
    correlation_id: correlationId,
    interaction_id: interactionId,
    binding,
    phase,
    last_generation: lastGeneration,
    pending_operation: pendingOperation,
    recovery_owner_id: recoveryOwner,
    recovery_token: recoveryToken,
    recovery_epoch: safeGeneration(record.recovery_epoch, 'journal.recovery_epoch', true),
  };
}

function parseLegacyJournal(decoded: unknown, expectedSessionId: string): StoredJournal {
  const record = exactObject(
    decoded,
    ['schema', 'client_instance_id', 'session_id', 'correlation_id', 'interaction_id', 'binding', 'phase', 'last_generation'],
    'legacy product P2 activation journal'
  );
  if (record.schema !== LEGACY_JOURNAL_SCHEMA) throw new Error('product P2 activation journal schema is unsupported');
  const sessionId = requiredText(record.session_id, 'journal.session_id');
  if (sessionId !== expectedSessionId) throw new Error('product P2 activation journal session mismatch');
  const correlationId = requiredText(record.correlation_id, 'journal.correlation_id');
  const interactionId = requiredText(record.interaction_id, 'journal.interaction_id');
  const legacyPhases = new Set([
    'activating',
    'active',
    'reconciling',
    'reconciling_unconfirmed',
    'closing',
    'closing_unconfirmed',
    'closed',
    'result_unknown',
  ]);
  if (typeof record.phase !== 'string' || !legacyPhases.has(record.phase)) throw new Error('product P2 activation journal phase is invalid');
  const lastGeneration = safeGeneration(record.last_generation, 'journal.last_generation', true);
  const binding = parseBinding(record.binding, sessionId, correlationId, interactionId);
  if (
    (binding === null && lastGeneration !== 0) ||
    (binding !== null && binding.activation_generation !== lastGeneration) ||
    (binding === null && record.phase !== 'closed')
  ) {
    throw new Error('product P2 activation journal state is inconsistent');
  }
  return {
    schema: PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA,
    revision: 0,
    client_instance_id: requiredText(record.client_instance_id, 'journal.client_instance_id'),
    session_id: sessionId,
    correlation_id: correlationId,
    interaction_id: interactionId,
    binding,
    phase: record.phase as ProductP2ActivationJournalPhase,
    last_generation: lastGeneration,
    pending_operation: null,
    recovery_owner_id: null,
    recovery_token: null,
    recovery_epoch: 0,
  };
}

function decodeJournal(value: string, expectedSessionId: string): { record: StoredJournal; legacy: boolean } {
  let decoded: unknown;
  try {
    decoded = JSON.parse(value);
  } catch {
    throw new Error('product P2 activation journal JSON is invalid');
  }
  const schema = decoded !== null && typeof decoded === 'object' && !Array.isArray(decoded) ? (decoded as Record<string, unknown>).schema : null;
  if (schema === LEGACY_JOURNAL_SCHEMA) return { record: parseLegacyJournal(decoded, expectedSessionId), legacy: true };
  return { record: parseV2Journal(decoded, expectedSessionId), legacy: false };
}

function storageKey(sessionId: string): string {
  return `${JOURNAL_STORAGE_PREFIX}:${encodeURIComponent(sessionId)}`;
}

function browserStorage(): ProductP2ActivationJournalStore {
  if (typeof window === 'undefined') throw new Error('browser session storage is unavailable');
  try {
    return window.sessionStorage;
  } catch {
    throw new Error('browser session storage is unavailable');
  }
}

function frozenOperation(operation: ProductP2DurableOperation | null): ProductP2DurableOperation | null {
  return operation === null ? null : Object.freeze({ ...operation, params: Object.freeze({ ...operation.params }) });
}

function frozenSnapshot(record: StoredJournal): ProductP2ActivationJournalSnapshot {
  return Object.freeze({
    ...record,
    binding: record.binding === null ? null : Object.freeze({ ...record.binding }),
    pending_operation: frozenOperation(record.pending_operation),
  });
}

function allocateRecoveryToken(ownerId: string): string {
  recoveryTokenSequence += 1;
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${recoveryTokenSequence}`;
  return `p2-recovery-${ownerId.replace(/[^A-Za-z0-9_-]/g, '')}-${random}`.slice(0, MAX_ID_LENGTH);
}

function allocateSessionRouteIdentity(sessionId: string, clientInstanceId: string): string {
  routeIdentitySequence += 1;
  const session = sessionId.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 48) || 'session';
  const client = clientInstanceId.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 48) || 'client';
  const nonce = (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${routeIdentitySequence}`).replace(/[^A-Za-z0-9_-]/g, '');
  return `${client}-${session}-${nonce}`.slice(0, 192);
}

const nodeRecoveryLocks = new Map<string, true>();

/** Browser Web Locks hold one same-sessionStorage refresh recovery across every await. */
const defaultRecoveryLease: ProductP2RecoveryLease = {
  async runExclusive<T>(name: string, operation: () => Promise<T>): Promise<T | null> {
    if (typeof window !== 'undefined') {
      const locks = (
        globalThis.navigator as Navigator & {
          locks?: {
            request<R>(
              name: string,
              options: { mode: 'exclusive'; ifAvailable: true },
              callback: (lock: unknown | null) => Promise<R | null>
            ): Promise<R | null>;
          };
        }
      ).locks;
      if (!locks) throw new Error('browser recovery lease is unavailable');
      return locks.request(name, { mode: 'exclusive', ifAvailable: true }, lock => (lock === null ? Promise.resolve(null) : operation()));
    }
    if (nodeRecoveryLocks.has(name)) return null;
    nodeRecoveryLocks.set(name, true);
    try {
      return await operation();
    } finally {
      nodeRecoveryLocks.delete(name);
    }
  },
};

export class ProductP2ActivationJournal implements ProductP2DurableOperationJournal {
  readonly #store: ProductP2ActivationJournalStore;
  readonly #storageKey: string;
  readonly #localClientInstanceId: string;
  #record: StoredJournal;
  #serialized: string;

  private constructor(store: ProductP2ActivationJournalStore, key: string, localClientInstanceId: string, record: StoredJournal, serialized: string) {
    this.#store = store;
    this.#storageKey = key;
    this.#localClientInstanceId = localClientInstanceId;
    this.#record = record;
    this.#serialized = serialized;
  }

  static open(
    input: Readonly<{
      session_id: string;
      client_instance_id: string;
      storage?: ProductP2ActivationJournalStore;
    }>
  ): ProductP2ActivationJournal {
    const sessionId = requiredText(input.session_id, 'session_id');
    const clientInstanceId = requiredText(input.client_instance_id, 'client_instance_id');
    const store = input.storage ?? browserStorage();
    const key = storageKey(sessionId);
    let stored: string | null;
    try {
      stored = store.getItem(key);
    } catch {
      throw new Error('product P2 activation journal cannot be read');
    }
    if (stored !== null) {
      const decoded = decodeJournal(stored, sessionId);
      const journal = new ProductP2ActivationJournal(store, key, clientInstanceId, decoded.record, stored);
      if (decoded.legacy) journal.#write({ ...decoded.record, revision: decoded.record.revision + 1 });
      return journal;
    }
    // A React page instance survives same-tab Session switches.  A fresh
    // per-Session journal therefore needs its own durable route identity;
    // reusing only client_instance_id would reset response generations under
    // the same interaction/correlation in the Gateway synthesis owner.
    const routeId = allocateSessionRouteIdentity(sessionId, clientInstanceId);
    const record: StoredJournal = {
      schema: PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA,
      revision: 0,
      client_instance_id: clientInstanceId,
      session_id: sessionId,
      correlation_id: `integrated-web-${routeId}`,
      interaction_id: `web-interaction-${routeId}`,
      binding: null,
      phase: 'closed',
      last_generation: 0,
      pending_operation: null,
      recovery_owner_id: null,
      recovery_token: null,
      recovery_epoch: 0,
    };
    const journal = new ProductP2ActivationJournal(store, key, clientInstanceId, record, '');
    journal.#write(record, null);
    return journal;
  }

  snapshot(): ProductP2ActivationJournalSnapshot {
    return frozenSnapshot(this.#record);
  }

  refresh(): ProductP2ActivationJournalSnapshot {
    let stored: string | null;
    try {
      stored = this.#store.getItem(this.#storageKey);
    } catch {
      throw new Error('product P2 activation journal cannot be read');
    }
    if (stored === null) throw new Error('product P2 activation journal disappeared');
    const refreshed = decodeJournal(stored, this.#record.session_id).record;
    if (
      refreshed.correlation_id !== this.#record.correlation_id ||
      refreshed.interaction_id !== this.#record.interaction_id ||
      refreshed.last_generation < this.#record.last_generation ||
      refreshed.revision < this.#record.revision
    ) {
      throw new Error('product P2 activation journal scope regressed');
    }
    this.#record = refreshed;
    this.#serialized = stored;
    return this.snapshot();
  }

  recoveryLockName(): string {
    return `jiuwenswarm.liveVoice.productP2Recovery:${encodeURIComponent(this.#record.session_id)}`;
  }

  beginRecovery(): ProductP2RecoveryClaim {
    this.refresh();
    const epoch = this.#record.recovery_epoch + 1;
    if (!Number.isSafeInteger(epoch)) throw new Error('product P2 recovery epoch is exhausted');
    const ownerId = this.#localClientInstanceId;
    const token = allocateRecoveryToken(ownerId);
    this.#write({
      ...this.#record,
      revision: this.#record.revision + 1,
      recovery_owner_id: ownerId,
      recovery_token: token,
      recovery_epoch: epoch,
    });
    return Object.freeze({ owner_id: ownerId, token, epoch });
  }

  assertRecovery(claim: Readonly<ProductP2RecoveryClaim>): ProductP2ActivationJournalSnapshot {
    const refreshed = this.refresh();
    if (refreshed.recovery_owner_id !== claim.owner_id || refreshed.recovery_token !== claim.token || refreshed.recovery_epoch !== claim.epoch) {
      throw new Error('product P2 activation journal recovery ownership changed');
    }
    return refreshed;
  }

  endRecovery(claim: Readonly<ProductP2RecoveryClaim>): void {
    this.assertRecovery(claim);
    this.#write({
      ...this.#record,
      revision: this.#record.revision + 1,
      recovery_owner_id: null,
      recovery_token: null,
    });
  }

  predecessorForRecovery(): ProductWebP2ActivationBinding | null {
    if (this.#record.phase === 'closed') return null;
    if (this.#record.phase === 'result_unknown') throw new Error(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED);
    if (this.#record.binding === null) throw new Error('product P2 activation journal predecessor is missing');
    return Object.freeze({ ...this.#record.binding });
  }

  prepareSuccessor(pageInstanceId: string): ProductWebP2ActivationBinding {
    this.#requireNoRecoveryOwner();
    if (this.#record.phase !== 'closed' || this.#record.pending_operation !== null) {
      throw new Error(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED);
    }
    if (this.#record.last_generation >= Number.MAX_SAFE_INTEGER) throw new Error('product P2 activation generation is exhausted');
    const pageId = requiredText(pageInstanceId, 'page_instance_id').replace(/[^A-Za-z0-9_-]/g, '') || 'page';
    const generation = this.#record.last_generation + 1;
    const binding = Object.freeze({
      session_id: this.#record.session_id,
      correlation_id: this.#record.correlation_id,
      interaction_id: this.#record.interaction_id,
      activation_id: `web-activation-${pageId}-${generation}`,
      activation_generation: generation,
    });
    this.#replace(binding, 'activating');
    return binding;
  }

  markActive(binding: Readonly<ProductWebP2ActivationBinding>, recovery?: Readonly<ProductP2RecoveryClaim>): void {
    this.#replace(binding, 'active', recovery);
  }

  markReconciling(binding: Readonly<ProductWebP2ActivationBinding>, recovery?: Readonly<ProductP2RecoveryClaim>): void {
    this.#replace(
      binding,
      this.#record.phase === 'activating' ||
        this.#record.phase === 'activation_result_unknown' ||
        this.#record.phase === 'reconciling_unconfirmed' ||
        this.#record.phase === 'closing_unconfirmed'
        ? 'reconciling_unconfirmed'
        : 'reconciling',
      recovery
    );
  }

  markClosing(binding: Readonly<ProductWebP2ActivationBinding>, recovery?: Readonly<ProductP2RecoveryClaim>): void {
    this.#replace(
      binding,
      this.#record.phase === 'activating' ||
        this.#record.phase === 'activation_result_unknown' ||
        this.#record.phase === 'reconciling_unconfirmed' ||
        this.#record.phase === 'closing_unconfirmed'
        ? 'closing_unconfirmed'
        : 'closing',
      recovery
    );
  }

  markClosed(binding: Readonly<ProductWebP2ActivationBinding>, recovery?: Readonly<ProductP2RecoveryClaim>): void {
    this.#replace(binding, 'closed', recovery);
  }

  markActivationResultUnknown(binding: Readonly<ProductWebP2ActivationBinding>, recovery?: Readonly<ProductP2RecoveryClaim>): void {
    this.#replace(binding, 'activation_result_unknown', recovery);
  }

  /** Compatibility constructor for a v1/generic unknown barrier. */
  markResultUnknown(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#replace(binding, 'result_unknown');
  }

  /**
   * An explicit user retry may abandon an unclassified legacy outcome only by
   * promoting it to exact activation reconciliation.  The recovery owner must
   * still replay/close this same binding before a successor can be allocated;
   * this transition never declares a submit, ACK, barge-in or activation
   * successful and never clears a durable pending operation.
   */
  requestResultUnknownRecovery(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#requireNoRecoveryOwner();
    if (this.#record.phase !== 'result_unknown' || this.#record.pending_operation !== null) {
      throw new Error('product P2 result-unknown recovery is unavailable');
    }
    this.#replace(binding, 'activation_result_unknown');
  }

  checkpointOperation(operation: Readonly<ProductP2DurableOperation>): void {
    this.#requireNoRecoveryOwner();
    const parsed = parseOperation(operation, this.#record.binding);
    if (parsed === null || this.#record.binding === null) throw new Error('pending product P2 operation is invalid');
    if (this.#record.pending_operation !== null && !sameOperation(this.#record.pending_operation, parsed)) {
      throw new Error('a different product P2 operation is already unresolved');
    }
    if (this.#record.phase !== 'active' && !OPERATION_PHASES.has(this.#record.phase)) {
      throw new Error('product P2 operation cannot be checkpointed in this phase');
    }
    this.#write({
      ...this.#record,
      revision: this.#record.revision + 1,
      phase: 'operation_result_unknown',
      pending_operation: parsed,
    });
  }

  settleOperation(operation: Readonly<ProductP2DurableOperation>): void {
    this.#requireNoRecoveryOwner();
    this.#settleOperation(operation);
  }

  markOperationReconciling(operation: Readonly<ProductP2DurableOperation>, recovery: Readonly<ProductP2RecoveryClaim>): void {
    this.#requireRecovery(recovery);
    if (this.#record.pending_operation === null || !sameOperation(this.#record.pending_operation, operation)) {
      throw new Error('pending product P2 operation changed');
    }
    this.#write({ ...this.#record, revision: this.#record.revision + 1, phase: 'operation_reconciling' });
  }

  settleRecoveredOperation(operation: Readonly<ProductP2DurableOperation>, recovery: Readonly<ProductP2RecoveryClaim>): void {
    this.#requireRecovery(recovery);
    this.#settleOperation(operation);
  }

  #settleOperation(operation: Readonly<ProductP2DurableOperation>): void {
    const parsed = parseOperation(operation, this.#record.binding);
    if (parsed === null || this.#record.pending_operation === null || !sameOperation(this.#record.pending_operation, parsed)) {
      throw new Error('pending product P2 operation changed');
    }
    this.#write({
      ...this.#record,
      revision: this.#record.revision + 1,
      phase: 'active',
      pending_operation: null,
    });
  }

  #replace(binding: Readonly<ProductWebP2ActivationBinding>, phase: ProductP2ActivationJournalPhase, recovery?: Readonly<ProductP2RecoveryClaim>): void {
    if (recovery) this.#requireRecovery(recovery);
    else this.#requireNoRecoveryOwner();
    if (this.#record.pending_operation !== null) throw new Error('pending product P2 operation must settle first');
    if (
      binding.session_id !== this.#record.session_id ||
      binding.correlation_id !== this.#record.correlation_id ||
      binding.interaction_id !== this.#record.interaction_id
    ) {
      throw new Error('product P2 activation journal binding scope mismatch');
    }
    if (this.#record.binding !== null && !sameBinding(this.#record.binding, binding) && phase !== 'activating') {
      throw new Error('product P2 activation journal binding mismatch');
    }
    if (phase === 'activating' && binding.activation_generation <= this.#record.last_generation) {
      throw new Error('product P2 activation successor is stale');
    }
    this.#write({
      ...this.#record,
      revision: this.#record.revision + 1,
      binding: Object.freeze({ ...binding }),
      phase,
      last_generation: binding.activation_generation,
    });
  }

  #requireNoRecoveryOwner(): void {
    if (this.#record.recovery_token !== null) throw new Error('product P2 activation journal recovery is in progress');
  }

  #requireRecovery(claim: Readonly<ProductP2RecoveryClaim>): void {
    if (this.#record.recovery_owner_id !== claim.owner_id || this.#record.recovery_token !== claim.token || this.#record.recovery_epoch !== claim.epoch) {
      throw new Error('product P2 activation journal recovery ownership changed');
    }
  }

  #write(record: StoredJournal, expected: string | null = this.#serialized): void {
    try {
      const current = this.#store.getItem(this.#storageKey);
      if (current !== expected) throw new Error('product P2 activation journal ownership changed');
      const serialized = JSON.stringify(record);
      this.#store.setItem(this.#storageKey, serialized);
      this.#record = record;
      this.#serialized = serialized;
    } catch (error) {
      if (error instanceof Error && error.message === 'product P2 activation journal ownership changed') throw error;
      throw new Error('product P2 activation journal cannot be persisted');
    }
  }
}

export type ProductP2PredecessorRecoveryResult = Readonly<
  | { kind: 'ready' }
  | { kind: 'superseded'; reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED }
  | { kind: 'retry'; reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED }
  | {
      kind: 'blocked';
      reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED | typeof PRODUCT_P2_REFRESH_SERVER_STATE_LOST;
    }
>;

export async function reconcileProductP2Predecessor(
  input: Readonly<{
    journal: ProductP2ActivationJournal;
    replay_operation?: (operation: Readonly<ProductP2DurableOperation>) => Promise<unknown>;
    on_operation_recovered?: (operation: Readonly<ProductP2DurableOperation>, result: unknown) => void;
    activate_exact: (binding: Readonly<ProductWebP2ActivationBinding>) => Promise<Readonly<{ replayed: boolean }>>;
    close_exact: (binding: Readonly<ProductWebP2ActivationBinding>) => Promise<void>;
    error_reason: (error: unknown) => string | undefined;
    activation_retryable: (error: unknown) => boolean;
    operation_retryable?: (error: unknown) => boolean;
    is_current?: () => boolean;
    recovery_lease?: ProductP2RecoveryLease;
  }>
): Promise<ProductP2PredecessorRecoveryResult> {
  const blocked = (
    reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED | typeof PRODUCT_P2_REFRESH_SERVER_STATE_LOST = PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED
  ): ProductP2PredecessorRecoveryResult => Object.freeze({ kind: 'blocked', reason });
  const ready = (): ProductP2PredecessorRecoveryResult => Object.freeze({ kind: 'ready' });
  const superseded = (): ProductP2PredecessorRecoveryResult => Object.freeze({ kind: 'superseded', reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED });
  const retry = (): ProductP2PredecessorRecoveryResult => Object.freeze({ kind: 'retry', reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED });
  const isCurrent = input.is_current ?? (() => true);
  const lease = input.recovery_lease ?? defaultRecoveryLease;

  let leased: ProductP2PredecessorRecoveryResult | null;
  try {
    leased = await lease.runExclusive(input.journal.recoveryLockName(), async () => {
      let claim: ProductP2RecoveryClaim;
      try {
        claim = input.journal.beginRecovery();
      } catch {
        return blocked();
      }
      let outcome: ProductP2PredecessorRecoveryResult = blocked();
      const checkpoint = (): boolean => {
        if (!isCurrent()) return false;
        try {
          input.journal.assertRecovery(claim);
          return true;
        } catch {
          return false;
        }
      };
      const resolveCheckpointFailure = (error: unknown, predecessor: Readonly<ProductWebP2ActivationBinding>): ProductP2PredecessorRecoveryResult => {
        if (
          error instanceof Error &&
          (error.message === 'product P2 activation journal ownership changed' || error.message === 'product P2 activation journal recovery ownership changed')
        ) {
          try {
            const refreshed = input.journal.refresh();
            if (refreshed.binding !== null && sameBinding(refreshed.binding, predecessor) && refreshed.phase === 'closed') return ready();
            return superseded();
          } catch {
            return blocked();
          }
        }
        return blocked();
      };
      try {
        let snapshot = input.journal.assertRecovery(claim);
        if (snapshot.phase === 'result_unknown') {
          outcome = blocked();
          return outcome;
        }
        if (OPERATION_PHASES.has(snapshot.phase)) {
          const pending = snapshot.pending_operation;
          if (pending === null || input.replay_operation === undefined) {
            outcome = blocked();
            return outcome;
          }
          try {
            input.journal.markOperationReconciling(pending, claim);
          } catch (error) {
            outcome = snapshot.binding === null ? blocked() : resolveCheckpointFailure(error, snapshot.binding);
            return outcome;
          }
          if (!checkpoint()) {
            outcome = superseded();
            return outcome;
          }
          let operationResult: unknown;
          try {
            operationResult = await input.replay_operation(pending);
          } catch (error) {
            if (!checkpoint()) {
              outcome = superseded();
              return outcome;
            }
            // An exact presentation ACK can outlive its P2 route when the page
            // refreshes across an AgentServer restart.  The authoritative
            // route-not-found result proves that neither the ACK nor the old
            // activation can still complete, so retaining either checkpoint
            // would only replay the same impossible ACK on every remount.
            if (
              pending.method === P2_PRESENTATION_ACK_METHOD &&
              ['PRODUCT_P2_ROUTE_NOT_FOUND', 'STALE_RESPONSE_OUTPUT', 'UNKNOWN_AGENT_RESPONSE'].includes(
                input.error_reason(error) ?? '',
              )
            ) {
              try {
                input.journal.settleRecoveredOperation(pending, claim);
                snapshot = input.journal.assertRecovery(claim);
                if (snapshot.binding === null) {
                  outcome = blocked();
                  return outcome;
                }
                input.journal.markClosed(snapshot.binding, claim);
                outcome = ready();
              } catch (checkpointError) {
                outcome = snapshot.binding === null ? blocked() : resolveCheckpointFailure(checkpointError, snapshot.binding);
              }
              return outcome;
            }
            outcome = input.operation_retryable?.(error) === true ? retry() : blocked();
            return outcome;
          }
          if (!checkpoint()) {
            outcome = superseded();
            return outcome;
          }
          try {
            input.on_operation_recovered?.(pending, operationResult);
          } catch {
            outcome = blocked();
            return outcome;
          }
          if (!checkpoint()) {
            outcome = superseded();
            return outcome;
          }
          try {
            input.journal.settleRecoveredOperation(pending, claim);
            snapshot = input.journal.assertRecovery(claim);
          } catch (error) {
            outcome = snapshot.binding === null ? blocked() : resolveCheckpointFailure(error, snapshot.binding);
            return outcome;
          }
        }

        let predecessor: ProductWebP2ActivationBinding | null;
        let predecessorPhase: ProductP2ActivationJournalPhase;
        try {
          predecessor = input.journal.predecessorForRecovery();
          predecessorPhase = input.journal.snapshot().phase;
        } catch {
          outcome = blocked();
          return outcome;
        }
        if (predecessor === null) {
          outcome = ready();
          return outcome;
        }
        if (!checkpoint()) {
          outcome = superseded();
          return outcome;
        }
        try {
          input.journal.markReconciling(predecessor, claim);
        } catch (error) {
          outcome = resolveCheckpointFailure(error, predecessor);
          return outcome;
        }
        if (!checkpoint()) {
          outcome = superseded();
          return outcome;
        }
        let activation: Readonly<{ replayed: boolean }>;
        try {
          activation = await input.activate_exact(predecessor);
        } catch (error) {
          if (!checkpoint()) {
            outcome = superseded();
            return outcome;
          }
          if (input.error_reason(error) === 'ACTIVATION_GENERATION_STALE') {
            try {
              input.journal.markClosed(predecessor, claim);
              outcome = ready();
            } catch (checkpointError) {
              outcome = resolveCheckpointFailure(checkpointError, predecessor);
            }
            return outcome;
          }
          if (input.activation_retryable(error)) {
            outcome = retry();
            return outcome;
          }
          try {
            input.journal.markActivationResultUnknown(predecessor, claim);
          } catch (checkpointError) {
            outcome = resolveCheckpointFailure(checkpointError, predecessor);
            return outcome;
          }
          outcome = blocked();
          return outcome;
        }
        if (!checkpoint()) {
          outcome = superseded();
          return outcome;
        }
        try {
          input.journal.markClosing(predecessor, claim);
        } catch (error) {
          outcome = resolveCheckpointFailure(error, predecessor);
          return outcome;
        }
        if (!checkpoint()) {
          outcome = superseded();
          return outcome;
        }
        try {
          await input.close_exact(predecessor);
        } catch {
          outcome = checkpoint() ? retry() : superseded();
          return outcome;
        }
        if (!checkpoint()) {
          outcome = superseded();
          return outcome;
        }
        if (!activation.replayed) {
          if (
            predecessorPhase === 'activating' ||
            predecessorPhase === 'activation_result_unknown' ||
            predecessorPhase === 'reconciling_unconfirmed' ||
            predecessorPhase === 'closing_unconfirmed'
          ) {
            try {
              input.journal.markClosed(predecessor, claim);
              outcome = ready();
            } catch (error) {
              outcome = resolveCheckpointFailure(error, predecessor);
            }
            return outcome;
          }
          try {
            input.journal.markActivationResultUnknown(predecessor, claim);
          } catch (error) {
            outcome = resolveCheckpointFailure(error, predecessor);
            return outcome;
          }
          outcome = blocked(PRODUCT_P2_REFRESH_SERVER_STATE_LOST);
          return outcome;
        }
        try {
          input.journal.markClosed(predecessor, claim);
          outcome = ready();
        } catch (error) {
          outcome = resolveCheckpointFailure(error, predecessor);
        }
        return outcome;
      } finally {
        try {
          input.journal.endRecovery(claim);
        } catch {
          throw new Error('product P2 recovery release checkpoint failed');
        }
      }
    });
  } catch {
    return blocked();
  }
  return leased ?? superseded();
}
