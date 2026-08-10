import type { ProductWebP2ActivationBinding } from './productWebActivation';

export const PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA = 'live-voice.product-p2-activation-journal.v1' as const;
export const PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED = 'P2_REFRESH_RECONCILIATION_REQUIRED' as const;
export const PRODUCT_P2_REFRESH_SERVER_STATE_LOST = 'P2_REFRESH_SERVER_STATE_LOST' as const;

export type ProductP2ActivationJournalPhase =
  'activating' | 'active' | 'reconciling' | 'reconciling_unconfirmed' | 'closing' | 'closing_unconfirmed' | 'closed' | 'result_unknown';

export type ProductP2ActivationJournalStore = Pick<Storage, 'getItem' | 'setItem'>;

export type ProductP2ActivationJournalSnapshot = Readonly<{
  schema: typeof PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA;
  client_instance_id: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  binding: ProductWebP2ActivationBinding | null;
  phase: ProductP2ActivationJournalPhase;
  last_generation: number;
}>;

type StoredJournal = {
  schema: typeof PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA;
  client_instance_id: string;
  session_id: string;
  correlation_id: string;
  interaction_id: string;
  binding: ProductWebP2ActivationBinding | null;
  phase: ProductP2ActivationJournalPhase;
  last_generation: number;
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
  'result_unknown',
]);
const MAX_ID_LENGTH = 512;

function requiredText(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim() || value.length > MAX_ID_LENGTH) {
    throw new Error(`${field} is invalid`);
  }
  return value;
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

function parseJournal(value: string, expectedSessionId: string): StoredJournal {
  let decoded: unknown;
  try {
    decoded = JSON.parse(value);
  } catch {
    throw new Error('product P2 activation journal JSON is invalid');
  }
  const record = exactObject(
    decoded,
    ['schema', 'client_instance_id', 'session_id', 'correlation_id', 'interaction_id', 'binding', 'phase', 'last_generation'],
    'product P2 activation journal'
  );
  if (record.schema !== PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA) {
    throw new Error('product P2 activation journal schema is unsupported');
  }
  const sessionId = requiredText(record.session_id, 'journal.session_id');
  if (sessionId !== expectedSessionId) {
    throw new Error('product P2 activation journal session mismatch');
  }
  const correlationId = requiredText(record.correlation_id, 'journal.correlation_id');
  const interactionId = requiredText(record.interaction_id, 'journal.interaction_id');
  if (typeof record.phase !== 'string' || !JOURNAL_PHASES.has(record.phase as ProductP2ActivationJournalPhase)) {
    throw new Error('product P2 activation journal phase is invalid');
  }
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
    client_instance_id: requiredText(record.client_instance_id, 'journal.client_instance_id'),
    session_id: sessionId,
    correlation_id: correlationId,
    interaction_id: interactionId,
    binding,
    phase: record.phase as ProductP2ActivationJournalPhase,
    last_generation: lastGeneration,
  };
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

function storageKey(sessionId: string): string {
  return `${JOURNAL_STORAGE_PREFIX}:${encodeURIComponent(sessionId)}`;
}

function browserStorage(): ProductP2ActivationJournalStore {
  if (typeof window === 'undefined') {
    throw new Error('browser session storage is unavailable');
  }
  try {
    return window.sessionStorage;
  } catch {
    throw new Error('browser session storage is unavailable');
  }
}

function frozenSnapshot(record: StoredJournal): ProductP2ActivationJournalSnapshot {
  return Object.freeze({
    ...record,
    binding: record.binding === null ? null : Object.freeze({ ...record.binding }),
  });
}

export class ProductP2ActivationJournal {
  readonly #store: ProductP2ActivationJournalStore;
  readonly #storageKey: string;
  #record: StoredJournal;

  private constructor(store: ProductP2ActivationJournalStore, key: string, record: StoredJournal) {
    this.#store = store;
    this.#storageKey = key;
    this.#record = record;
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
      return new ProductP2ActivationJournal(store, key, parseJournal(stored, sessionId));
    }
    const routeId = clientInstanceId.replace(/[^A-Za-z0-9_-]/g, '') || 'route';
    const record: StoredJournal = {
      schema: PRODUCT_P2_ACTIVATION_JOURNAL_SCHEMA,
      client_instance_id: clientInstanceId,
      session_id: sessionId,
      correlation_id: `integrated-web-${routeId}`,
      interaction_id: `web-interaction-${routeId}`,
      binding: null,
      phase: 'closed',
      last_generation: 0,
    };
    const journal = new ProductP2ActivationJournal(store, key, record);
    journal.#persist(record, null);
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
    if (stored === null) {
      throw new Error('product P2 activation journal disappeared');
    }
    const refreshed = parseJournal(stored, this.#record.session_id);
    if (
      refreshed.correlation_id !== this.#record.correlation_id ||
      refreshed.interaction_id !== this.#record.interaction_id ||
      refreshed.last_generation < this.#record.last_generation
    ) {
      throw new Error('product P2 activation journal scope regressed');
    }
    this.#record = refreshed;
    return this.snapshot();
  }

  predecessorForRecovery(): ProductWebP2ActivationBinding | null {
    // Unknown local results retain an exact binding so recovery can adopt the
    // server's active replay or closed-generation truth without a successor.
    if (this.#record.phase === 'closed') return null;
    if (this.#record.binding === null) {
      throw new Error('product P2 activation journal predecessor is missing');
    }
    return Object.freeze({ ...this.#record.binding });
  }

  prepareSuccessor(pageInstanceId: string): ProductWebP2ActivationBinding {
    if (this.#record.phase !== 'closed') {
      throw new Error(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED);
    }
    if (this.#record.last_generation >= Number.MAX_SAFE_INTEGER) {
      throw new Error('product P2 activation generation is exhausted');
    }
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

  markActive(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#replace(binding, 'active');
  }

  markReconciling(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#replace(
      binding,
      this.#record.phase === 'activating' || this.#record.phase === 'reconciling_unconfirmed' || this.#record.phase === 'closing_unconfirmed'
        ? 'reconciling_unconfirmed'
        : 'reconciling'
    );
  }

  markClosing(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#replace(
      binding,
      this.#record.phase === 'activating' || this.#record.phase === 'reconciling_unconfirmed' || this.#record.phase === 'closing_unconfirmed'
        ? 'closing_unconfirmed'
        : 'closing'
    );
  }

  markClosed(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#replace(binding, 'closed');
  }

  markResultUnknown(binding: Readonly<ProductWebP2ActivationBinding>): void {
    this.#replace(binding, 'result_unknown');
  }

  #replace(binding: Readonly<ProductWebP2ActivationBinding>, phase: ProductP2ActivationJournalPhase): void {
    if (this.#record.binding !== null && !sameBinding(this.#record.binding, binding) && phase !== 'activating') {
      throw new Error('product P2 activation journal binding mismatch');
    }
    if (phase === 'activating' && binding.activation_generation <= this.#record.last_generation) {
      throw new Error('product P2 activation successor is stale');
    }
    const next: StoredJournal = {
      ...this.#record,
      binding: Object.freeze({ ...binding }),
      phase,
      last_generation: binding.activation_generation,
    };
    this.#persist(next, this.#record);
    this.#record = next;
  }

  #persist(record: StoredJournal, expected: StoredJournal | null): void {
    try {
      const current = this.#store.getItem(this.#storageKey);
      const expectedValue = expected === null ? null : JSON.stringify(expected);
      if (current !== expectedValue) {
        throw new Error('product P2 activation journal ownership changed');
      }
      this.#store.setItem(this.#storageKey, JSON.stringify(record));
    } catch (error) {
      if (error instanceof Error && error.message === 'product P2 activation journal ownership changed') {
        throw error;
      }
      throw new Error('product P2 activation journal cannot be persisted');
    }
  }
}

export type ProductP2PredecessorRecoveryResult = Readonly<
  | { kind: 'ready' }
  | {
      kind: 'superseded';
      reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED;
    }
  | {
      kind: 'retry';
      reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED;
    }
  | {
      kind: 'blocked';
      reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED | typeof PRODUCT_P2_REFRESH_SERVER_STATE_LOST;
    }
>;

export async function reconcileProductP2Predecessor(
  input: Readonly<{
    journal: ProductP2ActivationJournal;
    activate_exact: (binding: Readonly<ProductWebP2ActivationBinding>) => Promise<Readonly<{ replayed: boolean }>>;
    close_exact: (binding: Readonly<ProductWebP2ActivationBinding>) => Promise<void>;
    error_reason: (error: unknown) => string | undefined;
    activation_retryable: (error: unknown) => boolean;
    is_current?: () => boolean;
  }>
): Promise<ProductP2PredecessorRecoveryResult> {
  const blocked = (
    reason: typeof PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED | typeof PRODUCT_P2_REFRESH_SERVER_STATE_LOST = PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED
  ): ProductP2PredecessorRecoveryResult => Object.freeze({ kind: 'blocked', reason });
  const ready = (): ProductP2PredecessorRecoveryResult => Object.freeze({ kind: 'ready' });
  const superseded = (): ProductP2PredecessorRecoveryResult =>
    Object.freeze({
      kind: 'superseded',
      reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
    });
  const retry = (): ProductP2PredecessorRecoveryResult =>
    Object.freeze({
      kind: 'retry',
      reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
    });
  const isCurrent = input.is_current ?? (() => true);
  const resolveCheckpointConflict = (predecessor: Readonly<ProductWebP2ActivationBinding>): ProductP2PredecessorRecoveryResult => {
    try {
      const refreshed = input.journal.refresh();
      if (refreshed.binding !== null && sameBinding(refreshed.binding, predecessor) && refreshed.phase === 'closed') {
        return ready();
      }
      // Another writer owns either this exact in-flight checkpoint or a newer
      // generation. This invocation must never adopt or close that writer's
      // binding; its recovery remains bound to the predecessor captured below.
      return superseded();
    } catch {
      return blocked();
    }
  };
  const resolveCheckpointFailure = (error: unknown, predecessor: Readonly<ProductWebP2ActivationBinding>): ProductP2PredecessorRecoveryResult =>
    error instanceof Error && error.message === 'product P2 activation journal ownership changed' ? resolveCheckpointConflict(predecessor) : blocked();
  let predecessor: ProductWebP2ActivationBinding | null;
  let predecessorPhase: ProductP2ActivationJournalPhase;
  try {
    predecessor = input.journal.predecessorForRecovery();
    predecessorPhase = input.journal.snapshot().phase;
  } catch {
    return blocked();
  }
  if (predecessor === null) return ready();
  if (!isCurrent()) return superseded();
  try {
    input.journal.markReconciling(predecessor);
  } catch (error) {
    return resolveCheckpointFailure(error, predecessor);
  }
  if (!isCurrent()) return superseded();
  let activation: Readonly<{ replayed: boolean }>;
  try {
    activation = await input.activate_exact(predecessor);
  } catch (error) {
    if (!isCurrent()) return superseded();
    if (input.error_reason(error) === 'ACTIVATION_GENERATION_STALE') {
      try {
        input.journal.markClosed(predecessor);
        return ready();
      } catch (checkpointError) {
        return resolveCheckpointFailure(checkpointError, predecessor);
      }
    }
    if (input.activation_retryable(error)) return retry();
    try {
      input.journal.markResultUnknown(predecessor);
    } catch (checkpointError) {
      return resolveCheckpointFailure(checkpointError, predecessor);
    }
    return blocked();
  }
  if (!isCurrent()) return superseded();
  try {
    input.journal.markClosing(predecessor);
  } catch (error) {
    return resolveCheckpointFailure(error, predecessor);
  }
  if (!isCurrent()) return superseded();
  try {
    await input.close_exact(predecessor);
  } catch {
    return isCurrent() ? retry() : superseded();
  }
  if (!isCurrent()) return superseded();
  if (!activation.replayed) {
    if (predecessorPhase === 'activating' || predecessorPhase === 'reconciling_unconfirmed' || predecessorPhase === 'closing_unconfirmed') {
      try {
        input.journal.markClosed(predecessor);
        return ready();
      } catch (error) {
        return resolveCheckpointFailure(error, predecessor);
      }
    }
    try {
      input.journal.markResultUnknown(predecessor);
    } catch (error) {
      return resolveCheckpointFailure(error, predecessor);
    }
    return blocked(PRODUCT_P2_REFRESH_SERVER_STATE_LOST);
  }
  try {
    input.journal.markClosed(predecessor);
    return ready();
  } catch (error) {
    return resolveCheckpointFailure(error, predecessor);
  }
}
