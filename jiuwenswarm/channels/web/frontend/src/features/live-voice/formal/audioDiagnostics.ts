/** Passive, content-free local diagnostics. Never an input/stop authority. */
import {
  appendAudioDiagnosticJournal,
  clearAudioDiagnosticJournal,
  flushAudioDiagnosticJournal,
  readAudioDiagnosticJournal,
} from './audioDiagnosticJournal.js';
const LIMIT = 2048;
const ID_KEYS = new Set(['session_id', 'media_session_id', 'interaction_id', 'correlation_id', 'capture_id', 'response_id', 'lease_id']);
const LABEL_KEYS = new Set(['status', 'reason', 'direction', 'outcome', 'context_state']);
for (const key of ['request_id', 'operation_id', 'span_id', 'task_id', 'attempt_id', 'turn_id', 'commit_id', 'unit_id', 'activation_id']) ID_KEYS.add(key);
for (const key of ['stage', 'rpc_method', 'error_type', 'error_code', 'error_reason', 'milestone']) LABEL_KEYS.add(key);
const VALUE_KEYS = new Set([
  'generation',
  'operation_generation',
  'response_generation',
  'frame_count',
  'frames_sent',
  'frames_acked',
  'pending_frames',
  'pending_bytes',
  'socket_buffered_bytes',
  'frame_age_ms',
  'tick_delay_ms',
  'energy_frames',
  'rms_peak',
  'provider_speech_started',
  'eot_pending',
  'eot_delivered',
  'handler_present',
  'playout_pending',
  'rotation_in_flight',
  'attached',
  'closed',
  'provider_start_ms',
  'provider_end_ms',
  'seq',
  'startup_lead_ms',
  'buffer_ahead_ms',
  'schedule_gap_ms',
  'scheduled_sources',
  'stopped_sources',
  'failed_sources',
  'elapsed_ms',
  'callback_current',
  'capture_ready',
  'echo_cancellation',
  'noise_suppression',
  'auto_gain_control',
  'duration_ms',
  'timeout_ms',
  'source_line',
  'capture_generation',
  'activation_generation',
  'output_latency_ms',
  'base_latency_ms',
  'long_task_ms',
  'activity_threshold',
  'activity_run_frames',
  'activity_first_age_ms',
  'activity_observed_frames',
  'activity_above_floor_frames',
  'activity_rms_peak',
  'activity_floor_first_age_ms',
  'activity_floor_sustained_age_ms',
  'activity_strong_first_age_ms',
  'activity_strong_sustained_age_ms',
]);
export interface AudioDiagnostic {
  readonly event: string;
  readonly observed_at: string;
  readonly monotonic_ms: number;
  readonly clock_id?: string;
  readonly sequence?: number;
  readonly fields: Readonly<Record<string, string | number | boolean | null>>;
}
const records: Readonly<AudioDiagnostic>[] = [];
const clockId = `browser-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
let sequence = 0;
let spanSequence = 0;
const rpcRejections = new WeakSet<object>();

/** Passive provenance: the WebSocket response explicitly had ok=false. */
export function markAudioRpcRejection(error: unknown): void {
  try {
    if (error !== null && typeof error === 'object') rpcRejections.add(error);
  } catch {
    /* Never modify or replace the business error. */
  }
}

function rejectionFields(value: unknown): Record<string, unknown> {
  try {
    if (!value || typeof value !== 'object') return {};
    const outer = value as Record<string, unknown>;
    const carrier = outer.payload && typeof outer.payload === 'object' ? (outer.payload as Record<string, unknown>) : outer;
    const detail = carrier.error && typeof carrier.error === 'object' ? (carrier.error as Record<string, unknown>) : {};
    const safe = (token: unknown) => (typeof token === 'string' && /^[A-Z][A-Z0-9_]{1,119}$/.test(token) ? token : undefined);
    return { error_code: safe(outer.code ?? detail.code), error_reason: safe(outer.reason ?? detail.reason) };
  } catch {
    return {};
  }
}
let dropped = 0;
let installed = false;

export function audioDiagnosticSnapshot(): readonly Readonly<AudioDiagnostic>[] {
  return records.slice();
}

export function clearAudioDiagnostics(): void {
  records.length = 0;
  dropped = 0;
  clearAudioDiagnosticJournal();
}

function safeFields(fields: Readonly<Record<string, unknown>>): Record<string, string | number | boolean | null> {
  const safe: Record<string, string | number | boolean | null> = {};
  for (const [key, value] of Object.entries(fields)) {
    if (ID_KEYS.has(key) || LABEL_KEYS.has(key)) {
      if (value === null) safe[key] = null;
      else if (typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,160}$/.test(value)) safe[key] = value;
    } else if (VALUE_KEYS.has(key)) {
      if (value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) safe[key] = value;
    }
  }
  return safe;
}

export function audioDiagnosticBundle() {
  const journal = readAudioDiagnosticJournal();
  const unique = new Map<string, AudioDiagnostic>();
  for (const raw of [...journal.records, ...records]) {
    try {
      const value = raw as AudioDiagnostic;
      if (
        !value ||
        !/^[a-z][a-z0-9_]{0,63}$/.test(value.event) ||
        !Number.isFinite(value.monotonic_ms) ||
        !Number.isSafeInteger(value.sequence) ||
        !/^browser-[a-z0-9-]{1,80}$/.test(value.clock_id ?? '') ||
        !/^\d{4}-\d{2}-\d{2}T[0-9:.]+Z$/.test(value.observed_at)
      )
        continue;
      const record = {
        event: value.event,
        observed_at: value.observed_at,
        monotonic_ms: value.monotonic_ms,
        clock_id: value.clock_id,
        sequence: value.sequence,
        fields: safeFields(value.fields),
      };
      unique.set(`${record.clock_id}:${record.sequence}`, record);
    } catch {
      /* Imported storage is untrusted and never product input. */
    }
  }
  return {
    format: 'live-voice.diagnostics.v1',
    exported_at: new Date().toISOString(),
    clock_id: clockId,
    memory_overwrites: dropped,
    overwritten_pages: journal.overwritten_pages,
    storage_failures: journal.storage_failures,
    records: [...unique.values()].sort((a, b) => a.observed_at.localeCompare(b.observed_at)),
  };
}

export function downloadAudioDiagnostics(): boolean {
  try {
    const blob = new Blob([JSON.stringify(audioDiagnosticBundle())], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `live-voice-diagnostics-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    try {
      anchor.click();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    return true;
  } catch {
    return false;
  }
}

export function diagnosticIdentity(value: unknown): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  try {
    if (!value || typeof value !== 'object') return result;
    const source = value as Record<string, unknown>;
    for (const key of ID_KEYS) if (typeof source[key] === 'string') result[key] = source[key];
    for (const name of ['scope', 'binding', 'response_ref', 'response', 'capture']) {
      const child = source[name];
      if (child && typeof child === 'object')
        for (const key of ID_KEYS) {
          const field = (child as Record<string, unknown>)[key];
          if (typeof field === 'string') result[key] = field;
        }
    }
  } catch {
    /* Ignore faulty diagnostic inputs. */
  }
  return result;
}

export async function profileAudioOperation<T>(stage: string, fields: Record<string, unknown>, action: () => Promise<T>): Promise<T> {
  const now = () => {
    try {
      return performance.now();
    } catch {
      return null;
    }
  };
  const started = now();
  const duration = () => {
    const ended = now();
    return started === null || ended === null ? null : ended - started;
  };
  const spanId = `${clockId}-${++spanSequence}`;
  const metadata = () => {
    try {
      return { ...fields, stage, span_id: spanId };
    } catch {
      return { stage, span_id: spanId };
    }
  };
  recordAudioDiagnostic('profile_span_started', { ...metadata(), outcome: 'started' });
  try {
    const result = await action();
    let rejected = false;
    try {
      rejected = (result as { ok?: boolean } | null)?.ok === false;
    } catch {
      /* Passive. */
    }
    recordAudioDiagnostic('profile_span_settled', {
      ...metadata(),
      ...diagnosticIdentity(result),
      ...(rejected ? rejectionFields(result) : {}),
      duration_ms: duration(),
      outcome: rejected ? 'rejected' : 'returned',
    });
    return result;
  } catch (error) {
    let code: unknown;
    let kind: unknown;
    let rejected = false;
    try {
      code = (error as { code?: unknown })?.code;
      kind = (error as { name?: unknown })?.name;
      rejected = rpcRejections.has(error as object) || (error as { payload?: { ok?: boolean } })?.payload?.ok === false;
    } catch {
      /* No error text. */
    }
    recordAudioDiagnostic('profile_span_settled', {
      ...metadata(),
      duration_ms: duration(),
      error_code: code,
      error_type: kind,
      ...rejectionFields(error),
      outcome: rejected ? 'rejected' : code === 'REQUEST_TIMEOUT' ? 'timeout' : code === 'REQUEST_ABORTED' || kind === 'AbortError' ? 'cancelled' : 'failed',
    });
    throw error;
  }
}

/** Unknown keys/non-scalars are discarded; observer failures never escape. */
export function recordAudioDiagnostic(event: string, fields: Readonly<Record<string, unknown>>): void {
  try {
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(event)) return;
    const safe = safeFields(fields);
    const record = Object.freeze({
      event,
      observed_at: new Date().toISOString(),
      monotonic_ms: performance.now(),
      clock_id: clockId,
      sequence: ++sequence,
      fields: Object.freeze(safe),
    });
    if (records.length >= LIMIT) {
      records.shift();
      dropped += 1;
    }
    records.push(record);
    appendAudioDiagnosticJournal(record);
    if (typeof window !== 'undefined' && !installed) {
      installed = true;
      window.addEventListener('pagehide', flushAudioDiagnosticJournal);
      window.addEventListener('error', event => recordAudioDiagnostic('browser_error', { source_line: event.lineno, outcome: 'failed' }));
      window.addEventListener('unhandledrejection', () => recordAudioDiagnostic('browser_unhandled_rejection', { outcome: 'failed' }));
      try {
        const observer = new PerformanceObserver(list => {
          for (const entry of list.getEntries()) recordAudioDiagnostic('browser_long_task', { long_task_ms: entry.duration });
        });
        observer.observe({ entryTypes: ['longtask'] });
      } catch {
        /* Unsupported observers do not affect audio. */
      }
    }
    if (typeof window !== 'undefined' && !Object.prototype.hasOwnProperty.call(window, '__liveVoiceDiagnostics')) {
      Object.defineProperty(window, '__liveVoiceDiagnostics', {
        value: Object.freeze({
          snapshot: audioDiagnosticSnapshot,
          clear: clearAudioDiagnostics,
          export: audioDiagnosticBundle,
          download: downloadAudioDiagnostics,
        }),
        configurable: true,
      });
    }
    console.info(`live_voice_audio_diagnostic ${JSON.stringify(record)}`);
  } catch {
    // Diagnostics must not change capture, playback, control or media ownership.
  }
}
