export interface AudioResponseRef {
  readonly interaction_id: string;
  readonly response_id: string;
  readonly response_generation: number;
}

export interface AudioProviderRef {
  readonly provider_id: string;
  readonly implementation_class: 'formal' | 'fallback' | 'demo_substitute' | 'unsupported';
  readonly fallback_from: string | null;
}

export interface AudioChunk {
  readonly response: Readonly<AudioResponseRef>;
  readonly unit_id: string;
  readonly seq: number;
  readonly audio: Uint8Array;
  readonly provider: Readonly<AudioProviderRef>;
}

export const LIVE_VOICE_AUDIO_FRAME_DURATION_MS = 20;

export interface AudioCaptureRef {
  readonly capture_id: string;
  readonly capture_generation: number;
  readonly track_id: string;
}

export interface AudioFrameFormat {
  readonly encoding: 'pcm_f32';
  readonly sample_rate_hz: number;
  readonly channel_count: 1;
  readonly frame_duration_ms: typeof LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
  readonly samples_per_channel: number;
}

export interface CapturedAudioFrame {
  readonly capture: Readonly<AudioCaptureRef>;
  readonly seq: number;
  readonly sample_cursor: number;
  readonly context_time_s: number;
  readonly format: Readonly<AudioFrameFormat>;
  readonly samples: Float32Array;
}

export interface AudioRenderTransform {
  readonly transform: string;
  readonly source_start: number;
  readonly source_end: number;
  readonly rendered_text: string;
}

export interface AudioRenderPlan {
  readonly display_text: string;
  readonly spoken_text: string;
  readonly transforms: readonly Readonly<AudioRenderTransform>[];
}

export class AudioPortViolation extends Error {
  constructor(
    readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'AudioPortViolation';
  }
}

function requiredText(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new AudioPortViolation('INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function normalizeRef(ref: Readonly<AudioResponseRef>): Readonly<AudioResponseRef> {
  if (!Number.isSafeInteger(ref.response_generation) || ref.response_generation < 0) {
    throw new AudioPortViolation('INVALID_RESPONSE_GENERATION', 'response_generation must be a non-negative safe integer');
  }
  return Object.freeze({
    interaction_id: requiredText(ref.interaction_id, 'interaction_id'),
    response_id: requiredText(ref.response_id, 'response_id'),
    response_generation: ref.response_generation,
  });
}

function nonNegativeSafeInteger(value: number, field: string): number {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new AudioPortViolation('INVALID_AUDIO_INTEGER', `${field} must be a non-negative safe integer`);
  }
  return value;
}

export function audioFrameSamples(sampleRateHz: number): number {
  if (!Number.isSafeInteger(sampleRateHz) || sampleRateHz <= 0) {
    throw new AudioPortViolation('INVALID_SAMPLE_RATE', 'sample_rate_hz must be a positive safe integer');
  }
  const frameSampleNumerator = sampleRateHz * LIVE_VOICE_AUDIO_FRAME_DURATION_MS;
  if (!Number.isSafeInteger(frameSampleNumerator) || frameSampleNumerator % 1000 !== 0) {
    throw new AudioPortViolation('NON_INTEGRAL_AUDIO_FRAME', 'sample_rate_hz must produce an exact 20ms frame');
  }
  return frameSampleNumerator / 1000;
}

export function createCapturedAudioFrame(input: Readonly<CapturedAudioFrame>): Readonly<CapturedAudioFrame> {
  const generation = nonNegativeSafeInteger(input.capture.capture_generation, 'capture_generation');
  const seq = nonNegativeSafeInteger(input.seq, 'seq');
  const sampleCursor = nonNegativeSafeInteger(input.sample_cursor, 'sample_cursor');
  const expectedSamples = audioFrameSamples(input.format.sample_rate_hz);
  if (
    input.format.encoding !== 'pcm_f32' ||
    input.format.channel_count !== 1 ||
    input.format.frame_duration_ms !== LIVE_VOICE_AUDIO_FRAME_DURATION_MS ||
    input.format.samples_per_channel !== expectedSamples
  ) {
    throw new AudioPortViolation('INVALID_AUDIO_FRAME_FORMAT', 'capture frame format does not match the frozen AIO-B contract');
  }
  if (!(input.samples instanceof Float32Array) || input.samples.length !== expectedSamples) {
    throw new AudioPortViolation('INVALID_AUDIO_FRAME_SAMPLES', 'capture frame samples do not match the declared format');
  }
  for (const sample of input.samples) {
    if (!Number.isFinite(sample)) {
      throw new AudioPortViolation('INVALID_AUDIO_FRAME_SAMPLES', 'capture frame samples must be finite');
    }
  }
  if (!Number.isFinite(input.context_time_s) || input.context_time_s < 0) {
    throw new AudioPortViolation('INVALID_AUDIO_TIMESTAMP', 'context_time_s must be a non-negative finite number');
  }
  if (sampleCursor !== seq * expectedSamples) {
    throw new AudioPortViolation('INVALID_AUDIO_CURSOR', 'sample_cursor must be contiguous with the frame sequence');
  }
  return Object.freeze({
    capture: Object.freeze({
      capture_id: requiredText(input.capture.capture_id, 'capture_id'),
      capture_generation: generation,
      track_id: requiredText(input.capture.track_id, 'track_id'),
    }),
    seq,
    sample_cursor: sampleCursor,
    context_time_s: input.context_time_s,
    format: Object.freeze({
      encoding: 'pcm_f32',
      sample_rate_hz: input.format.sample_rate_hz,
      channel_count: 1,
      frame_duration_ms: LIVE_VOICE_AUDIO_FRAME_DURATION_MS,
      samples_per_channel: expectedSamples,
    }),
    samples: input.samples.slice(),
  });
}

function refKey(ref: Readonly<AudioResponseRef>): string {
  return `${ref.interaction_id}\u0000${ref.response_id}\u0000${ref.response_generation}`;
}

export function createAudioRenderPlan(
  displayText: string,
  spokenText: string,
  transforms: readonly Readonly<AudioRenderTransform>[] = []
): Readonly<AudioRenderPlan> {
  requiredText(displayText, 'display_text');
  requiredText(spokenText, 'spoken_text');
  const normalized = transforms.map(item => {
    requiredText(item.transform, 'transform');
    requiredText(item.rendered_text, 'rendered_text');
    if (
      !Number.isSafeInteger(item.source_start) ||
      !Number.isSafeInteger(item.source_end) ||
      item.source_start < 0 ||
      item.source_end < item.source_start ||
      item.source_end > displayText.length
    ) {
      throw new AudioPortViolation('INVALID_RENDER_SPAN', 'render transform span is invalid');
    }
    return Object.freeze({ ...item });
  });
  return Object.freeze({ display_text: displayText, spoken_text: spokenText, transforms: Object.freeze(normalized) });
}

interface PlaybackState {
  readonly ref: Readonly<AudioResponseRef>;
  readonly chunks: AudioChunk[];
  readonly nextSeq: Map<string, number>;
  readonly acknowledgedSeq: Map<string, number>;
  stopped: boolean;
}

const EXACT_RESPONSE_ID_CAPACITY = 128;

class ConservativeIdentityFence {
  readonly #bits = new Uint8Array(8192);

  #indices(value: string): readonly number[] {
    return [0x811c9dc5, 0x9e3779b1, 0x85ebca6b, 0xc2b2ae35].map(seed => {
      let hash = seed;
      for (let index = 0; index < value.length; index += 1) {
        hash = Math.imul(hash ^ value.charCodeAt(index), 0x01000193);
      }
      return (hash >>> 0) % (this.#bits.length * 8);
    });
  }

  add(value: string): void {
    for (const index of this.#indices(value)) this.#bits[index >> 3] |= 1 << (index & 7);
  }

  has(value: string): boolean {
    return this.#indices(value).every(index => (this.#bits[index >> 3] & (1 << (index & 7))) !== 0);
  }
}

export class AudioPort {
  readonly #byInteraction = new Map<string, PlaybackState>();
  readonly #seenResponseIds = new Set<string>();
  readonly #retiredResponseIds = new ConservativeIdentityFence();
  // This exact map contains only interactions that have not reached the
  // authoritative close seam. stopLocal releases playback state but preserves
  // the exact high-water needed for a later replacement or terminal close.
  readonly #latestResponseByInteraction = new Map<string, Readonly<AudioResponseRef>>();
  readonly #closedInteractions = new ConservativeIdentityFence();

  begin(input: Readonly<AudioResponseRef>): void {
    const ref = normalizeRef(input);
    if (this.#closedInteractions.has(ref.interaction_id)) {
      throw new AudioPortViolation('RESPONSE_GENERATION_NOT_INCREASING', 'a terminal interaction cannot be revived');
    }
    if (this.#seenResponseIds.has(ref.response_id) || this.#retiredResponseIds.has(ref.response_id)) {
      throw new AudioPortViolation('RESPONSE_ID_REUSED', 'response identifiers cannot be reused');
    }
    const last = this.#latestResponseByInteraction.get(ref.interaction_id)?.response_generation ?? -1;
    if (ref.response_generation <= last) {
      throw new AudioPortViolation('RESPONSE_GENERATION_NOT_INCREASING', 'response generation must increase');
    }
    const prior = this.#byInteraction.get(ref.interaction_id);
    if (prior !== undefined) {
      prior.stopped = true;
      prior.chunks.length = 0;
    }
    this.#retainResponseId(ref.response_id);
    this.#latestResponseByInteraction.set(ref.interaction_id, ref);
    this.#byInteraction.set(ref.interaction_id, {
      ref,
      chunks: [],
      nextSeq: new Map(),
      acknowledgedSeq: new Map(),
      stopped: false,
    });
  }

  enqueue(input: Readonly<AudioChunk>): boolean {
    const ref = normalizeRef(input.response);
    const state = this.#byInteraction.get(ref.interaction_id);
    if (state === undefined || refKey(state.ref) !== refKey(ref) || state.stopped) return false;
    requiredText(input.unit_id, 'unit_id');
    const expected = state.nextSeq.get(input.unit_id) ?? 0;
    if (!Number.isSafeInteger(input.seq) || input.seq !== expected) {
      throw new AudioPortViolation('NON_CONTIGUOUS_AUDIO_SEQUENCE', `expected audio sequence ${expected}`);
    }
    if (!(input.audio instanceof Uint8Array) || input.audio.byteLength === 0) {
      throw new AudioPortViolation('INVALID_AUDIO_CHUNK', 'audio must be non-empty bytes');
    }
    const provider = Object.freeze({
      provider_id: requiredText(input.provider.provider_id, 'provider_id'),
      implementation_class: input.provider.implementation_class,
      fallback_from: input.provider.fallback_from,
    });
    if (!(['formal', 'fallback', 'demo_substitute', 'unsupported'] as const).includes(provider.implementation_class)) {
      throw new AudioPortViolation('INVALID_IMPLEMENTATION_CLASS', 'audio implementation class is invalid');
    }
    if (provider.implementation_class === 'fallback' && !provider.fallback_from) {
      throw new AudioPortViolation('FALLBACK_PROVENANCE_REQUIRED', 'fallback audio must identify its source');
    }
    if (provider.implementation_class !== 'fallback' && provider.fallback_from !== null) {
      throw new AudioPortViolation('UNEXPECTED_FALLBACK_PROVENANCE', 'only fallback audio may identify a replaced provider');
    }
    if (provider.implementation_class === 'unsupported') {
      throw new AudioPortViolation('AUDIO_PROVIDER_UNSUPPORTED', 'an unsupported provider cannot enqueue audio');
    }
    const chunk = Object.freeze({ ...input, response: ref, audio: input.audio.slice(), provider });
    state.chunks.push(chunk);
    state.nextSeq.set(input.unit_id, expected + 1);
    return true;
  }

  pending(input: Readonly<AudioResponseRef>): readonly Readonly<AudioChunk>[] {
    const ref = normalizeRef(input);
    const state = this.#byInteraction.get(ref.interaction_id);
    if (state === undefined || refKey(state.ref) !== refKey(ref) || state.stopped) return Object.freeze([]);
    return Object.freeze(state.chunks.map(chunk => Object.freeze({ ...chunk, audio: chunk.audio.slice() })));
  }

  acknowledge(input: Readonly<AudioResponseRef>, unitId: string, throughSeq: number): number {
    const ref = normalizeRef(input);
    const state = this.#byInteraction.get(ref.interaction_id);
    if (state === undefined || refKey(state.ref) !== refKey(ref) || state.stopped) return 0;
    requiredText(unitId, 'unit_id');
    if (!Number.isSafeInteger(throughSeq) || throughSeq < 0) {
      throw new AudioPortViolation('INVALID_AUDIO_ACK', 'audio acknowledgement must be non-negative');
    }
    const delivered = (state.nextSeq.get(unitId) ?? 0) - 1;
    const prior = state.acknowledgedSeq.get(unitId) ?? -1;
    if (throughSeq > delivered || throughSeq < prior) {
      throw new AudioPortViolation('INVALID_AUDIO_ACK', 'audio acknowledgement is stale or beyond delivery');
    }
    const before = state.chunks.length;
    state.chunks.splice(0, state.chunks.length, ...state.chunks.filter(chunk => chunk.unit_id !== unitId || chunk.seq > throughSeq));
    state.acknowledgedSeq.set(unitId, throughSeq);
    return before - state.chunks.length;
  }

  stopLocal(input: Readonly<AudioResponseRef>): boolean {
    const ref = normalizeRef(input);
    const state = this.#byInteraction.get(ref.interaction_id);
    if (state === undefined || refKey(state.ref) !== refKey(ref) || state.stopped) return false;
    state.stopped = true;
    state.chunks.length = 0;
    this.#byInteraction.delete(ref.interaction_id);
    return true;
  }

  closeInteraction(input: Readonly<AudioResponseRef>): boolean {
    const ref = normalizeRef(input);
    const latest = this.#latestResponseByInteraction.get(ref.interaction_id);
    if (latest === undefined || refKey(latest) !== refKey(ref)) return false;
    const active = this.#byInteraction.get(ref.interaction_id);
    if (active !== undefined && refKey(active.ref) !== refKey(ref)) return false;
    this.#closedInteractions.add(ref.interaction_id);
    if (active !== undefined) {
      active.stopped = true;
      active.chunks.length = 0;
      this.#byInteraction.delete(ref.interaction_id);
    }
    this.#latestResponseByInteraction.delete(ref.interaction_id);
    return true;
  }

  #retainResponseId(responseId: string): void {
    if (this.#seenResponseIds.size >= EXACT_RESPONSE_ID_CAPACITY) {
      const oldest = this.#seenResponseIds.values().next().value;
      if (oldest !== undefined) {
        this.#retiredResponseIds.add(oldest);
        this.#seenResponseIds.delete(oldest);
      }
    }
    this.#seenResponseIds.add(responseId);
  }
}
