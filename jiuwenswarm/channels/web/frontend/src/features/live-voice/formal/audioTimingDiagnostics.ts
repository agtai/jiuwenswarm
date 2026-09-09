/** Passive numeric observations. Energy != speech; output estimates != hearing. */
export interface TimingAudioContext {
  readonly currentTime: number;
  readonly sampleRate: number;
  readonly state: string;
  readonly baseLatency?: number;
  readonly outputLatency?: number;
  getOutputTimestamp?(): { contextTime?: number; performanceTime?: number };
}

type NumericFacts = Record<string, number | string | boolean | null>;
const INPUT_WINDOW_MS = 10;
const INPUT_DBFS = -45;
const LOW_INPUT_DBFS = -55;
const OUTPUT_WINDOW_MS = 5;
const OUTPUT_DBFS = -50;

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** No PCM is retained, logged, or used to control capture/turns. */
export class CaptureTimingDiagnostics {
  #capture: string | null = null;
  #generation: number | null = null;
  #tail: NumericFacts = {};
  #lowTail: number | null = null;
  #last: NumericFacts = {};

  observe(
    frame: {
      capture: { capture_id: string; capture_generation: number };
      seq: number;
      sample_cursor: number;
      context_time_s: number;
      samples: Float32Array;
      format: { sample_rate_hz: number };
    },
    context: TimingAudioContext,
    nowMs: number,
  ): void {
    try {
      if (frame.capture.capture_id !== this.#capture || frame.capture.capture_generation !== this.#generation) {
        this.#capture = frame.capture.capture_id;
        this.#generation = frame.capture.capture_generation;
        this.#tail = {};
        this.#lowTail = null;
        this.#last = {};
      }
      const rate = frame.format.sample_rate_hz;
      if (!finite(nowMs) || !finite(context.currentTime) || context.state !== 'running' || rate <= 0) return;
      const mapping = nowMs - context.currentTime * 1000;
      const step = Math.max(1, Math.round((rate * INPUT_WINDOW_MS) / 1000));
      let firstWindowDbfs: number | null = null;
      let lastWindowDbfs: number | null = null;
      for (let start = 0; start < frame.samples.length; start += step) {
        const end = Math.min(start + step, frame.samples.length);
        let energy = 0;
        for (let i = start; i < end; i += 1) energy += frame.samples[i] ** 2;
        const power = energy / (end - start);
        lastWindowDbfs = power > 0 && finite(power) ? 10 * Math.log10(power) : null;
        if (start === 0) firstWindowDbfs = lastWindowDbfs;
        const contextEnd = (frame.context_time_s + end / rate) * 1000;
        if (power >= 10 ** (LOW_INPUT_DBFS / 10)) this.#lowTail = mapping + contextEnd;
        if (power >= 10 ** (INPUT_DBFS / 10))
          this.#tail = {
            input_tail_estimate_ms: mapping + contextEnd,
            input_tail_context_ms: contextEnd,
            input_tail_sample_end: frame.sample_cursor + end,
            input_tail_frame_seq: frame.seq,
          };
      }
      this.#last = {
        capture_first_window_dbfs: firstWindowDbfs,
        capture_last_window_dbfs: lastWindowDbfs,
        capture_callback_ms: nowMs,
        capture_context_ms: context.currentTime * 1000,
        capture_frame_end_context_ms: (frame.context_time_s + frame.samples.length / rate) * 1000,
        capture_frame_sample_end: frame.sample_cursor + frame.samples.length,
        frame_seq: frame.seq,
        sample_rate_hz: rate,
      };
    } catch {
      /* Diagnostic observation cannot reject a capture frame. */
    }
  }

  snapshot(captureId: string | null): NumericFacts {
    if (captureId === null || captureId !== this.#capture) return {};
    return {
      ...this.#last,
      input_tail_estimate_ms: null,
      ...this.#tail,
      input_tail_low_estimate_ms: this.#lowTail,
      input_threshold_dbfs: INPUT_DBFS,
      input_low_threshold_dbfs: LOW_INPUT_DBFS,
      input_window_ms: INPUT_WINDOW_MS,
      input_time_method: 'processed_energy_render_clock_estimate',
      acoustic_measured: false,
    };
  }
}

/** First 5ms energy window, including leading silence. Never an audibility claim. */
export function firstSignalOffset(samples: Float32Array, rate: number, offsetSeconds = 0): number | null {
  if (!Number.isSafeInteger(rate) || rate <= 0 || !finite(offsetSeconds) || offsetSeconds < 0) return null;
  const step = Math.max(1, Math.round((rate * OUTPUT_WINDOW_MS) / 1000));
  for (let start = Math.ceil(offsetSeconds * rate); start < samples.length; start += step) {
    const end = Math.min(start + step, samples.length);
    let energy = 0;
    for (let i = start; i < end; i += 1) energy += samples[i] ** 2;
    if (energy / (end - start) >= 10 ** (OUTPUT_DBFS / 10)) return start / rate;
  }
  return null;
}

export function outputTimingFacts(context: TimingAudioContext, signalContextSeconds: number, nowMs: number): NumericFacts {
  const facts: NumericFacts = {
    signal_context_ms: signalContextSeconds * 1000,
    output_signal_window_ms: OUTPUT_WINDOW_MS,
    output_signal_threshold_dbfs: OUTPUT_DBFS,
    output_estimate_ms: null,
    output_time_method: 'unavailable',
    acoustic_measured: false,
  };
  try {
    if (!finite(signalContextSeconds) || !finite(nowMs) || context.state !== 'running') return facts;
    facts.render_estimate_ms = nowMs + (signalContextSeconds - context.currentTime) * 1000;
    facts.output_context_ms = context.currentTime * 1000;
    facts.sample_rate_hz = context.sampleRate;
    if (finite(context.baseLatency) && context.baseLatency >= 0) facts.base_latency_ms = context.baseLatency * 1000;
    if (finite(context.outputLatency) && context.outputLatency >= 0) facts.output_latency_ms = context.outputLatency * 1000;
    const stamp = context.getOutputTimestamp?.();
    if (stamp && finite(stamp.contextTime) && stamp.contextTime > 0 && finite(stamp.performanceTime) && stamp.performanceTime > 0) {
      facts.output_timestamp_context_ms = stamp.contextTime * 1000;
      facts.output_timestamp_performance_ms = stamp.performanceTime;
      facts.output_timestamp_age_ms = nowMs - stamp.performanceTime;
      // Zero, future or stale timestamps are not replaced with invented latency.
      if (stamp.performanceTime <= nowMs && nowMs - stamp.performanceTime <= 1000 && stamp.contextTime <= context.currentTime) {
        facts.output_estimate_ms = stamp.performanceTime + (signalContextSeconds - stamp.contextTime) * 1000;
        facts.output_time_method = 'get_output_timestamp_estimate';
      }
    }
  } catch {
    /* Output clock support is optional. */
  }
  return facts;
}
