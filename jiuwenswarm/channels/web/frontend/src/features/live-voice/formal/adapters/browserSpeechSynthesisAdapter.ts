import type { AudioProviderRef, AudioResponseRef } from '../audioPort.js';

export interface BrowserSynthesisCapability {
  readonly available: boolean;
  readonly batch: true;
  readonly streaming: false;
  readonly audio_chunk_cursor: false;
  readonly provider: Readonly<AudioProviderRef>;
}

export interface BrowserSynthesisEnvironment {
  readonly available: boolean;
  createUtterance(text: string): SpeechSynthesisUtterance;
  getVoices(): readonly SpeechSynthesisVoice[];
  speak(utterance: SpeechSynthesisUtterance): void;
  cancel(): void;
}

export interface BrowserSynthesisRequest {
  readonly response: Readonly<AudioResponseRef>;
  readonly spoken_text: string;
}

export interface BrowserSynthesisCallbacks {
  onStart(): void;
  onEnd(): void;
  onError(error: Error): void;
}

export class BrowserSpeechSynthesisAdapterViolation extends Error {
  constructor(
    readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'BrowserSpeechSynthesisAdapterViolation';
  }
}

function defaultEnvironment(): BrowserSynthesisEnvironment {
  const available = typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
  return {
    available,
    createUtterance(text: string): SpeechSynthesisUtterance {
      if (!available) {
        throw new BrowserSpeechSynthesisAdapterViolation('BROWSER_SYNTHESIS_UNAVAILABLE', 'browser synthesis is unavailable');
      }
      return new SpeechSynthesisUtterance(text);
    },
    getVoices: () => (available ? window.speechSynthesis.getVoices() : []),
    speak(utterance): void {
      if (!available) {
        throw new BrowserSpeechSynthesisAdapterViolation('BROWSER_SYNTHESIS_UNAVAILABLE', 'browser synthesis is unavailable');
      }
      window.speechSynthesis.speak(utterance);
    },
    cancel(): void {
      if (available) window.speechSynthesis.cancel();
    },
  };
}

function requiredText(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new BrowserSpeechSynthesisAdapterViolation('INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function normalizeResponse(response: Readonly<AudioResponseRef>): Readonly<AudioResponseRef> {
  if (!Number.isSafeInteger(response.response_generation) || response.response_generation < 0) {
    throw new BrowserSpeechSynthesisAdapterViolation('INVALID_RESPONSE_GENERATION', 'response_generation must be a non-negative safe integer');
  }
  return Object.freeze({
    interaction_id: requiredText(response.interaction_id, 'interaction_id'),
    response_id: requiredText(response.response_id, 'response_id'),
    response_generation: response.response_generation,
  });
}

function responseKey(response: Readonly<AudioResponseRef>): string {
  return `${response.interaction_id}\u0000${response.response_id}\u0000${response.response_generation}`;
}

export class BrowserSpeechSynthesisAdapter {
  readonly capability: Readonly<BrowserSynthesisCapability>;
  readonly #environment: BrowserSynthesisEnvironment;
  readonly #seenResponseIds = new Set<string>();
  readonly #lastGeneration = new Map<string, number>();
  #active: { response: Readonly<AudioResponseRef>; utterance: SpeechSynthesisUtterance } | null = null;

  constructor(environment: BrowserSynthesisEnvironment = defaultEnvironment()) {
    if (typeof environment.available !== 'boolean') {
      throw new BrowserSpeechSynthesisAdapterViolation('INVALID_BOOLEAN', 'environment.available must be boolean');
    }
    this.#environment = environment;
    this.capability = Object.freeze({
      available: environment.available,
      batch: true,
      streaming: false,
      audio_chunk_cursor: false,
      provider: Object.freeze({
        provider_id: 'browser-speech-synthesis',
        implementation_class: environment.available ? 'fallback' : 'unsupported',
        fallback_from: environment.available ? 'formal-speech-synthesis-port' : null,
      }),
    });
  }

  play(request: Readonly<BrowserSynthesisRequest>, callbacks: Readonly<BrowserSynthesisCallbacks>): void {
    if (!this.capability.available) {
      throw new BrowserSpeechSynthesisAdapterViolation('BROWSER_SYNTHESIS_UNAVAILABLE', 'browser synthesis is unavailable');
    }
    const response = normalizeResponse(request.response);
    const spokenText = requiredText(request.spoken_text, 'spoken_text');
    if (this.#seenResponseIds.has(response.response_id)) {
      throw new BrowserSpeechSynthesisAdapterViolation('RESPONSE_ID_REUSED', 'response identifiers cannot be reused');
    }
    const lastGeneration = this.#lastGeneration.get(response.interaction_id) ?? -1;
    if (response.response_generation <= lastGeneration) {
      throw new BrowserSpeechSynthesisAdapterViolation('RESPONSE_GENERATION_NOT_INCREASING', 'response generation must increase');
    }
    this.#clearActive(true);
    const utterance = this.#environment.createUtterance(spokenText);
    utterance.lang = 'zh-CN';
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    utterance.voice = this.#environment.getVoices().find(voice => /^zh(?:-|_)/i.test(voice.lang)) ?? null;
    utterance.onstart = () => {
      if (this.isCurrent(response)) callbacks.onStart();
    };
    utterance.onend = () => {
      if (!this.isCurrent(response)) return;
      this.#active = null;
      callbacks.onEnd();
    };
    utterance.onerror = event => {
      if (!this.isCurrent(response)) return;
      this.#active = null;
      callbacks.onError(new Error(`Speech playback failed: ${event.error}`));
    };
    this.#seenResponseIds.add(response.response_id);
    this.#lastGeneration.set(response.interaction_id, response.response_generation);
    this.#active = { response, utterance };
    try {
      this.#environment.speak(utterance);
    } catch (error) {
      if (this.isCurrent(response)) this.#active = null;
      utterance.onstart = null;
      utterance.onend = null;
      utterance.onerror = null;
      throw error;
    }
  }

  isCurrent(response: Readonly<AudioResponseRef>): boolean {
    return this.#active !== null && responseKey(this.#active.response) === responseKey(response);
  }

  stop(response?: Readonly<AudioResponseRef>): boolean {
    if (this.#active === null) return false;
    if (response !== undefined && !this.isCurrent(response)) return false;
    this.#clearActive(true);
    return true;
  }

  #clearActive(cancelBrowser: boolean): void {
    const active = this.#active;
    this.#active = null;
    if (active !== null) {
      active.utterance.onstart = null;
      active.utterance.onend = null;
      active.utterance.onerror = null;
    }
    if (cancelBrowser && active !== null) this.#environment.cancel();
  }
}
