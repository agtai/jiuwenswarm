const PRODUCT_P3_PROGRESS_GENERATION_CONTRACT = 'live-voice.product-p3-progress-generation.v1' as const;
const PRODUCT_P3_PROGRESS_GENERATION_STORAGE_PREFIX = 'jiuwenswarm.live_voice.product_p3_progress_generation.v1:';
const PRODUCT_P3_PROGRESS_GENERATION_MAX_TEXT_CHARS = 256;
const PRODUCT_P3_PROGRESS_GENERATION_MAX_ENTRIES = 128;
const PRODUCT_P3_PROGRESS_GENERATION_MAX_SERIALIZED_CHARS = 262_144;

export type ProductP3ProgressGenerationJournalStore = Pick<Storage, 'getItem' | 'setItem'>;

export interface ProductP3ProgressGenerationLease {
  runExclusive<T>(name: string, operation: () => Promise<T>): Promise<T | null>;
}

export type ProductP3ProgressGenerationIdentity = Readonly<{
  session_id: string;
  task_id: string;
  correlation_id: string;
  origin_id: string;
  generation_id: string;
}>;

type StoredProgressGenerationEntry = ProductP3ProgressGenerationIdentity &
  Readonly<{
    last_generation: number;
  }>;

type StoredProgressGenerationJournal = Readonly<{
  contract_version: typeof PRODUCT_P3_PROGRESS_GENERATION_CONTRACT;
  revision: number;
  session_id: string;
  entries: readonly StoredProgressGenerationEntry[];
}>;

function requiredText(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new Error(`${field} is invalid`);
  const text = value.trim();
  if (!text || text !== value || text.length > PRODUCT_P3_PROGRESS_GENERATION_MAX_TEXT_CHARS) {
    throw new Error(`${field} is invalid`);
  }
  return text;
}

function safeInteger(value: unknown, field: string, options: Readonly<{ allowZero?: boolean }> = {}): number {
  if (!Number.isSafeInteger(value) || Number(value) < (options.allowZero === true ? 0 : 1)) {
    throw new Error(`${field} is invalid`);
  }
  return Number(value);
}

function exactObject(value: unknown, keys: readonly string[], field: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${field} is invalid`);
  }
  const record = value as Record<string, unknown>;
  const actual = Object.keys(record).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${field} shape is invalid`);
  }
  return record;
}

function freezeIdentity(value: unknown): ProductP3ProgressGenerationIdentity {
  const record = exactObject(value, ['session_id', 'task_id', 'correlation_id', 'origin_id', 'generation_id'], 'product P3 progress generation identity');
  return Object.freeze({
    session_id: requiredText(record.session_id, 'session_id'),
    task_id: requiredText(record.task_id, 'task_id'),
    correlation_id: requiredText(record.correlation_id, 'correlation_id'),
    origin_id: requiredText(record.origin_id, 'origin_id'),
    generation_id: requiredText(record.generation_id, 'generation_id'),
  });
}

function entryRouteKey(entry: ProductP3ProgressGenerationIdentity): string {
  return JSON.stringify([entry.task_id, entry.origin_id, entry.generation_id]);
}

function parseJournal(serialized: string, expectedSessionId: string): StoredProgressGenerationJournal {
  if (serialized.length > PRODUCT_P3_PROGRESS_GENERATION_MAX_SERIALIZED_CHARS) {
    throw new Error('product P3 progress generation journal is too large');
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(serialized);
  } catch {
    throw new Error('product P3 progress generation journal JSON is invalid');
  }
  const record = exactObject(decoded, ['contract_version', 'revision', 'session_id', 'entries'], 'product P3 progress generation journal');
  if (record.contract_version !== PRODUCT_P3_PROGRESS_GENERATION_CONTRACT) {
    throw new Error('product P3 progress generation journal contract is invalid');
  }
  const sessionId = requiredText(record.session_id, 'journal.session_id');
  if (sessionId !== expectedSessionId) throw new Error('product P3 progress generation journal scope is invalid');
  const revision = safeInteger(record.revision, 'journal.revision', { allowZero: true });
  if (!Array.isArray(record.entries) || record.entries.length > PRODUCT_P3_PROGRESS_GENERATION_MAX_ENTRIES) {
    throw new Error('product P3 progress generation journal entries are invalid');
  }
  const routeKeys = new Set<string>();
  const entries = record.entries.map((value, index) => {
    const entry = exactObject(value, ['session_id', 'task_id', 'correlation_id', 'origin_id', 'generation_id', 'last_generation'], `journal.entries[${index}]`);
    const identity = freezeIdentity({
      session_id: entry.session_id,
      task_id: entry.task_id,
      correlation_id: entry.correlation_id,
      origin_id: entry.origin_id,
      generation_id: entry.generation_id,
    });
    if (identity.session_id !== sessionId) throw new Error('product P3 progress generation entry scope is invalid');
    const routeKey = entryRouteKey(identity);
    if (routeKeys.has(routeKey)) throw new Error('product P3 progress generation route is duplicated');
    routeKeys.add(routeKey);
    return Object.freeze({
      ...identity,
      last_generation: safeInteger(entry.last_generation, `journal.entries[${index}].last_generation`),
    });
  });
  return Object.freeze({
    contract_version: PRODUCT_P3_PROGRESS_GENERATION_CONTRACT,
    revision,
    session_id: sessionId,
    entries: Object.freeze(entries),
  });
}

function storageKey(sessionId: string): string {
  return `${PRODUCT_P3_PROGRESS_GENERATION_STORAGE_PREFIX}${encodeURIComponent(requiredText(sessionId, 'session_id'))}`;
}

function browserStorage(): ProductP3ProgressGenerationJournalStore {
  if (typeof window === 'undefined') throw new Error('product P3 progress generation storage is unavailable');
  try {
    return window.sessionStorage;
  } catch {
    throw new Error('product P3 progress generation storage is unavailable');
  }
}

const nodeGenerationLocks = new Map<string, true>();

const defaultGenerationLease: ProductP3ProgressGenerationLease = {
  async runExclusive<T>(name: string, operation: () => Promise<T>): Promise<T | null> {
    if (typeof window !== 'undefined') {
      const locks = (
        globalThis.navigator as Navigator & {
          locks?: {
            request<R>(
              lockName: string,
              options: { mode: 'exclusive'; ifAvailable: true },
              callback: (lock: unknown | null) => Promise<R | null>,
            ): Promise<R | null>;
          };
        }
      ).locks;
      if (!locks) throw new Error('product P3 progress generation lease is unavailable');
      return locks.request(name, { mode: 'exclusive', ifAvailable: true }, lock => (lock === null ? Promise.resolve(null) : operation()));
    }
    if (nodeGenerationLocks.has(name)) return null;
    nodeGenerationLocks.set(name, true);
    try {
      return await operation();
    } finally {
      nodeGenerationLocks.delete(name);
    }
  },
};

/**
 * Claim one monotonic progress generation for an exact Task route. The claim is
 * persisted before any server effect and held under one same-session Web Lock,
 * so a page refresh cannot reset a live AgentServer generation to one. The
 * bounded journal never evicts a route because forgetting its high-water mark
 * could make a later revisit stale or ambiguous.
 */
export async function claimProductP3ProgressGeneration(
  input: ProductP3ProgressGenerationIdentity,
  options: Readonly<{
    storage?: ProductP3ProgressGenerationJournalStore;
    lease?: ProductP3ProgressGenerationLease;
  }> = {},
): Promise<number> {
  const identity = freezeIdentity(input);
  const store = options.storage ?? browserStorage();
  const key = storageKey(identity.session_id);
  const leaseName = `jiuwenswarm.liveVoice.productP3ProgressGeneration:${encodeURIComponent(identity.session_id)}`;
  const claimed = await (options.lease ?? defaultGenerationLease).runExclusive(leaseName, async () => {
    let stored: string | null;
    try {
      stored = store.getItem(key);
    } catch {
      throw new Error('product P3 progress generation journal cannot be read');
    }
    const journal: StoredProgressGenerationJournal =
      stored === null
        ? Object.freeze({
            contract_version: PRODUCT_P3_PROGRESS_GENERATION_CONTRACT,
            revision: 0,
            session_id: identity.session_id,
            entries: Object.freeze([]),
          })
        : parseJournal(stored, identity.session_id);
    const routeKey = entryRouteKey(identity);
    const existingIndex = journal.entries.findIndex(entry => entryRouteKey(entry) === routeKey);
    const existing = existingIndex < 0 ? null : journal.entries[existingIndex]!;
    if (existing !== null && existing.correlation_id !== identity.correlation_id) {
      throw new Error('product P3 progress generation correlation changed');
    }
    if (existing === null && journal.entries.length >= PRODUCT_P3_PROGRESS_GENERATION_MAX_ENTRIES) {
      throw new Error('product P3 progress generation journal capacity is exhausted');
    }
    const generation = existing === null ? 1 : safeInteger(existing.last_generation + 1, 'next progress generation');
    const nextEntry = Object.freeze({ ...identity, last_generation: generation });
    const entries = [...journal.entries];
    if (existingIndex < 0) entries.push(nextEntry);
    else entries[existingIndex] = nextEntry;
    const next: StoredProgressGenerationJournal = Object.freeze({
      contract_version: PRODUCT_P3_PROGRESS_GENERATION_CONTRACT,
      revision: safeInteger(journal.revision + 1, 'next journal revision'),
      session_id: identity.session_id,
      entries: Object.freeze(entries),
    });
    const serialized = JSON.stringify(next);
    if (serialized.length > PRODUCT_P3_PROGRESS_GENERATION_MAX_SERIALIZED_CHARS) {
      throw new Error('product P3 progress generation journal is too large');
    }
    try {
      store.setItem(key, serialized);
      if (store.getItem(key) !== serialized) throw new Error('product P3 progress generation journal write was replaced');
    } catch (error) {
      if (error instanceof Error && error.message === 'product P3 progress generation journal write was replaced') throw error;
      throw new Error('product P3 progress generation journal cannot be written');
    }
    parseJournal(serialized, identity.session_id);
    return generation;
  });
  if (claimed === null) throw new Error('product P3 progress generation lease is unavailable');
  return claimed;
}
