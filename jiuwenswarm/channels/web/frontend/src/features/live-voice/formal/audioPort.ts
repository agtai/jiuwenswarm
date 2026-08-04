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

export class AudioPort {
  readonly #byInteraction = new Map<string, PlaybackState>();
  readonly #seenResponseIds = new Set<string>();
  readonly #lastGeneration = new Map<string, number>();

  begin(input: Readonly<AudioResponseRef>): void {
    const ref = normalizeRef(input);
    if (this.#seenResponseIds.has(ref.response_id)) {
      throw new AudioPortViolation('RESPONSE_ID_REUSED', 'response identifiers cannot be reused');
    }
    const last = this.#lastGeneration.get(ref.interaction_id) ?? -1;
    if (ref.response_generation <= last) {
      throw new AudioPortViolation('RESPONSE_GENERATION_NOT_INCREASING', 'response generation must increase');
    }
    const prior = this.#byInteraction.get(ref.interaction_id);
    if (prior !== undefined) {
      prior.stopped = true;
      prior.chunks.length = 0;
    }
    this.#seenResponseIds.add(ref.response_id);
    this.#lastGeneration.set(ref.interaction_id, ref.response_generation);
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
    return true;
  }

  businessCancelCount(): number {
    return 0;
  }
}
