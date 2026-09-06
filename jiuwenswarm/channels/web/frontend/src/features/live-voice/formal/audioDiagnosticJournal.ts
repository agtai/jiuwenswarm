/** Bounded same-tab diagnostic journal. No network, payloads or product state. */
const PREFIX = 'live-voice-diagnostics-v1:';
const MILESTONE_PREFIX = 'live-voice-diagnostics-milestones-v1:';
const PAGE_COUNT = 128;
const MILESTONE_PAGE_COUNT = 16;
const PAGE_SIZE = 32;
const MAX_PAGE_CHARS = 48_000;
let pending: unknown[] = [];
let pendingMilestones: unknown[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let storageFailures = 0;

export function flushAudioDiagnosticJournal(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  const batch = pending;
  const milestones = pendingMilestones;
  pending = [];
  pendingMilestones = [];
  flushLane(batch, PREFIX, PAGE_COUNT);
  flushLane(milestones, MILESTONE_PREFIX, MILESTONE_PAGE_COUNT);
}

function flushLane(batch: unknown[], prefix: string, pageCount: number): void {
  if (!batch.length) return;
  try {
    const storage = window.sessionStorage;
    const raw = Number(storage.getItem(`${prefix}next`) ?? '0');
    let next = Number.isSafeInteger(raw) && raw >= 0 ? raw : 0;
    const retained = storage.getItem(`${prefix}${next % pageCount}`);
    let page: unknown[] = [];
    if (retained !== null && retained.length <= MAX_PAGE_CHARS) {
      try {
        const value: unknown = JSON.parse(retained);
        if (Array.isArray(value)) page = value.slice(0, PAGE_SIZE);
      } catch {
        storageFailures += 1;
      }
    }
    for (const record of batch) {
      if (page.length >= PAGE_SIZE || JSON.stringify([...page, record]).length > MAX_PAGE_CHARS) {
        storage.setItem(`${prefix}${next % pageCount}`, JSON.stringify(page));
        next += 1;
        page = [];
      }
      page.push(record);
    }
    storage.setItem(`${prefix}${next % pageCount}`, JSON.stringify(page));
    storage.setItem(`${prefix}next`, String(next));
  } catch {
    storageFailures += batch.length;
  }
}

export function appendAudioDiagnosticJournal(record: unknown, milestone = false): void {
  if (typeof window === 'undefined') return;
  pending.push(record);
  if (milestone) pendingMilestones.push(record);
  if (pending.length >= PAGE_SIZE) flushAudioDiagnosticJournal();
  else if (timer === null) timer = setTimeout(flushAudioDiagnosticJournal, 1000);
}

export function readAudioDiagnosticJournal(): { records: unknown[]; overwritten_pages: number; milestone_overwritten_pages: number; storage_failures: number } {
  flushAudioDiagnosticJournal();
  const regular = readLane(PREFIX, PAGE_COUNT);
  const milestones = readLane(MILESTONE_PREFIX, MILESTONE_PAGE_COUNT);
  return { records: [...regular.records, ...milestones.records], overwritten_pages: regular.overwritten,
    milestone_overwritten_pages: milestones.overwritten, storage_failures: storageFailures };
}

function readLane(prefix: string, pageCount: number): { records: unknown[]; overwritten: number } {
  const records: unknown[] = [];
  let overwritten = 0;
  try {
    const storage = window.sessionStorage;
    const raw = Number(storage.getItem(`${prefix}next`) ?? '0');
    const next = Number.isSafeInteger(raw) && raw >= 0 ? raw : 0;
    overwritten = Math.max(0, next - pageCount + 1);
    for (let index = Math.max(0, next - pageCount + 1); index <= next; index += 1) {
      const text = storage.getItem(`${prefix}${index % pageCount}`);
      if (text === null || text.length > MAX_PAGE_CHARS) continue;
      try {
        const page: unknown = JSON.parse(text);
        if (Array.isArray(page)) records.push(...page.slice(0, PAGE_SIZE));
      } catch {
        storageFailures += 1;
      }
    }
  } catch {
    storageFailures += 1;
  }
  return { records, overwritten };
}

export function clearAudioDiagnosticJournal(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  pending = [];
  pendingMilestones = [];
  storageFailures = 0;
  try {
    for (let index = 0; index < PAGE_COUNT; index += 1) window.sessionStorage.removeItem(`${PREFIX}${index}`);
    window.sessionStorage.removeItem(`${PREFIX}next`);
    for (let index = 0; index < MILESTONE_PAGE_COUNT; index += 1) window.sessionStorage.removeItem(`${MILESTONE_PREFIX}${index}`);
    window.sessionStorage.removeItem(`${MILESTONE_PREFIX}next`);
  } catch {
    /* Storage is optional; capture never depends on it. */
  }
}
