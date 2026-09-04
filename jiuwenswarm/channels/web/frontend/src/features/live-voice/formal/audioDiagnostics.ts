/** Passive, content-free local diagnostics. Never an input/stop authority. */
const LIMIT = 2048;
const ID_KEYS = new Set(['session_id', 'media_session_id', 'interaction_id', 'correlation_id', 'capture_id', 'response_id', 'lease_id']);
const LABEL_KEYS = new Set(['status', 'reason', 'direction', 'outcome', 'context_state']);
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
]);
export interface AudioDiagnostic {
  readonly event: string;
  readonly observed_at: string;
  readonly monotonic_ms: number;
  readonly fields: Readonly<Record<string, string | number | boolean | null>>;
}
const records: Readonly<AudioDiagnostic>[] = [];

export function audioDiagnosticSnapshot(): readonly Readonly<AudioDiagnostic>[] {
  return records.slice();
}

export function clearAudioDiagnostics(): void {
  records.length = 0;
}

/** Unknown keys/non-scalars are discarded; observer failures never escape. */
export function recordAudioDiagnostic(event: string, fields: Readonly<Record<string, unknown>>): void {
  try {
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(event)) return;
    const safe: Record<string, string | number | boolean | null> = {};
    for (const [key, value] of Object.entries(fields)) {
      if (ID_KEYS.has(key) || LABEL_KEYS.has(key)) {
        if (value === null) safe[key] = null;
        else if (typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,160}$/.test(value)) safe[key] = value;
      } else if (VALUE_KEYS.has(key)) {
        if (value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) safe[key] = value;
      }
    }
    const record = Object.freeze({
      event,
      observed_at: new Date().toISOString(),
      monotonic_ms: performance.now(),
      fields: Object.freeze(safe),
    });
    if (records.length >= LIMIT) records.shift();
    records.push(record);
    // Memory only: survives neither reload nor tab close, and performs no RPC.
    if (typeof window !== 'undefined' && !Object.prototype.hasOwnProperty.call(window, '__liveVoiceDiagnostics')) {
      Object.defineProperty(window, '__liveVoiceDiagnostics', {
        value: Object.freeze({ snapshot: audioDiagnosticSnapshot, clear: clearAudioDiagnostics }),
        configurable: true,
      });
    }
    console.info(`live_voice_audio_diagnostic ${JSON.stringify(record)}`);
  } catch {
    // Diagnostics must not change capture, playback, control or media ownership.
  }
}
