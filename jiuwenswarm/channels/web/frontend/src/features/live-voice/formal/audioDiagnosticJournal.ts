/** Bounded same-tab diagnostic journal. No network, payloads or product state. */
const PREFIX = 'live-voice-diagnostics-v1:';
const PAGE_COUNT = 128;
const PAGE_SIZE = 32;
const MAX_PAGE_CHARS = 48_000;
let pending: unknown[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let storageFailures = 0;

export function flushAudioDiagnosticJournal(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  if (!pending.length) return;
  const batch = pending;
  pending = [];
  try {
    const storage = window.sessionStorage;
    const raw = Number(storage.getItem(`${PREFIX}next`) ?? '0');
    let next = Number.isSafeInteger(raw) && raw >= 0 ? raw : 0;
    const retained = storage.getItem(`${PREFIX}${next % PAGE_COUNT}`);
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
        storage.setItem(`${PREFIX}${next % PAGE_COUNT}`, JSON.stringify(page));
        next += 1;
        page = [];
      }
      page.push(record);
    }
    storage.setItem(`${PREFIX}${next % PAGE_COUNT}`, JSON.stringify(page));
    storage.setItem(`${PREFIX}next`, String(next));
  } catch {
    storageFailures += batch.length;
  }
}

export function appendAudioDiagnosticJournal(record: unknown): void {
  if (typeof window === 'undefined') return;
  pending.push(record);
  if (pending.length >= PAGE_SIZE) flushAudioDiagnosticJournal();
  else if (timer === null) timer = setTimeout(flushAudioDiagnosticJournal, 1000);
}

export function readAudioDiagnosticJournal(): { records: unknown[]; overwritten_pages: number; storage_failures: number } {
  flushAudioDiagnosticJournal();
  const records: unknown[] = [];
  let overwritten = 0;
  try {
    const storage = window.sessionStorage;
    const raw = Number(storage.getItem(`${PREFIX}next`) ?? '0');
    const next = Number.isSafeInteger(raw) && raw >= 0 ? raw : 0;
    overwritten = Math.max(0, next - PAGE_COUNT + 1);
    for (let index = Math.max(0, next - PAGE_COUNT + 1); index <= next; index += 1) {
      const text = storage.getItem(`${PREFIX}${index % PAGE_COUNT}`);
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
  return { records, overwritten_pages: overwritten, storage_failures: storageFailures };
}

export function clearAudioDiagnosticJournal(): void {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  pending = [];
  storageFailures = 0;
  try {
    for (let index = 0; index < PAGE_COUNT; index += 1) window.sessionStorage.removeItem(`${PREFIX}${index}`);
    window.sessionStorage.removeItem(`${PREFIX}next`);
  } catch {
    /* Storage is optional; capture never depends on it. */
  }
}
