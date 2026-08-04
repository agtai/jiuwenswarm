import type { AudioProviderRef } from '../audioPort.js';

export interface BrowserRecognitionCapability {
  readonly available: boolean;
  readonly batch: true;
  readonly streaming: false;
  readonly hypothesis_cursor: false;
  readonly provider_final_is_turn_commit: false;
  readonly provider: Readonly<AudioProviderRef>;
}

export interface BrowserRecognitionCapture {
  readonly session_id: string;
  readonly generation: number;
}

export interface BrowserRecognitionObservation {
  readonly session: Readonly<BrowserRecognitionCapture>;
  readonly seq: number;
  readonly kind: 'partial' | 'final';
  readonly raw_text: string;
  readonly display_text: string;
  readonly confidence: null;
  readonly commits_turn: false;
  readonly provider: Readonly<AudioProviderRef>;
}

export class BrowserSpeechRecognitionAdapterViolation extends Error {
  constructor(
    readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'BrowserSpeechRecognitionAdapterViolation';
  }
}

function requiredText(value: string, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new BrowserSpeechRecognitionAdapterViolation('INVALID_REQUIRED_TEXT', `${field} must be non-empty`);
  }
  return value;
}

function captureKey(capture: Readonly<BrowserRecognitionCapture>): string {
  return `${capture.session_id}\u0000${capture.generation}`;
}

export class BrowserSpeechRecognitionAdapter {
  readonly capability: Readonly<BrowserRecognitionCapability>;
  readonly #lastGeneration = new Map<string, number>();
  readonly #active = new Map<string, { capture: Readonly<BrowserRecognitionCapture>; nextSeq: number }>();

  constructor(options: Readonly<{ available?: boolean }> = {}) {
    const available = options.available ?? true;
    if (typeof available !== 'boolean') {
      throw new BrowserSpeechRecognitionAdapterViolation('INVALID_BOOLEAN', 'available must be boolean');
    }
    this.capability = Object.freeze({
      available,
      batch: true,
      streaming: false,
      hypothesis_cursor: false,
      provider_final_is_turn_commit: false,
      provider: Object.freeze({
        provider_id: 'browser-speech-recognition',
        implementation_class: available ? 'fallback' : 'unsupported',
        fallback_from: available ? 'formal-speech-recognition-port' : null,
      }),
    });
  }

  begin(sessionId: string): Readonly<BrowserRecognitionCapture> {
    if (!this.capability.available) {
      throw new BrowserSpeechRecognitionAdapterViolation('BROWSER_RECOGNITION_UNAVAILABLE', 'browser recognition is unavailable');
    }
    const normalizedSessionId = requiredText(sessionId, 'session_id');
    const generation = (this.#lastGeneration.get(normalizedSessionId) ?? -1) + 1;
    const capture = Object.freeze({ session_id: normalizedSessionId, generation });
    this.#lastGeneration.set(normalizedSessionId, generation);
    this.#active.set(normalizedSessionId, { capture, nextSeq: 0 });
    return capture;
  }

  observe(capture: Readonly<BrowserRecognitionCapture>, transcript: string, isFinal: boolean): Readonly<BrowserRecognitionObservation> | null {
    if (typeof isFinal !== 'boolean') {
      throw new BrowserSpeechRecognitionAdapterViolation('INVALID_BOOLEAN', 'isFinal must be boolean');
    }
    const active = this.#active.get(capture.session_id);
    if (active === undefined || captureKey(active.capture) !== captureKey(capture)) return null;
    if (typeof transcript === 'string' && transcript.trim().length === 0) return null;
    const text = requiredText(transcript, 'transcript');
    const observation = Object.freeze({
      session: active.capture,
      seq: active.nextSeq,
      kind: isFinal ? ('final' as const) : ('partial' as const),
      raw_text: text,
      display_text: text,
      confidence: null,
      commits_turn: false as const,
      provider: this.capability.provider,
    });
    active.nextSeq += 1;
    return observation;
  }

  finish(capture: Readonly<BrowserRecognitionCapture>): boolean {
    const active = this.#active.get(capture.session_id);
    if (active === undefined || captureKey(active.capture) !== captureKey(capture)) return false;
    this.#active.delete(capture.session_id);
    return true;
  }

  cancel(capture: Readonly<BrowserRecognitionCapture>): boolean {
    return this.finish(capture);
  }
}
