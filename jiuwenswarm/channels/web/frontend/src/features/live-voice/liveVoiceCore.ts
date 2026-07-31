/**
 * Demo-only Live Voice lifecycle and speech queue.
 *
 * This module intentionally has no React or browser dependencies. UI code owns
 * speech recognition and Agent transport, while a small injected player owns
 * browser TTS. Keeping the lifecycle pure makes the two most important Demo
 * guarantees deterministic and testable:
 *
 * - one listening cycle can submit at most one complete final transcript;
 * - callbacks and queued speech from an older response epoch are ignored.
 */

export type LiveVoiceStatus = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'error';

export interface LiveVoiceError {
  code: string;
  message: string;
}

export interface LiveVoiceSnapshot {
  status: LiveVoiceStatus;
  captureId: number;
  responseEpoch: number;
  interimTranscript: string;
  finalTranscript: string;
  pendingSpeechCount: number;
  activeSpeechKey: string | null;
  error: LiveVoiceError | null;
}

export interface LiveVoiceSpeechCallbacks {
  onStart: () => void;
  onEnd: () => void;
  onError: (error: unknown) => void;
}

export interface LiveVoiceSpeechPlayer {
  play: (text: string, callbacks: LiveVoiceSpeechCallbacks) => void;
  stop: () => void;
}

export type FinalTranscriptRejection = 'empty' | 'not-listening' | 'already-committed' | 'disposed';

export type FinalTranscriptResult =
  | {
      accepted: true;
      captureId: number;
      responseEpoch: number;
      transcript: string;
    }
  | {
      accepted: false;
      reason: FinalTranscriptRejection;
    };

export type SpeechEnqueueRejection = 'empty' | 'stale-epoch' | 'duplicate' | 'error' | 'disposed';

export type SpeechEnqueueResult =
  | {
      accepted: true;
      key: string;
    }
  | {
      accepted: false;
      reason: SpeechEnqueueRejection;
    };

export interface LiveVoiceCoreOptions {
  player: LiveVoiceSpeechPlayer;
  normalizeTranscript?: (transcript: string) => string;
}

export interface LiveVoiceCore {
  getSnapshot: () => LiveVoiceSnapshot;
  subscribe: (listener: (snapshot: LiveVoiceSnapshot) => void) => () => void;
  beginListening: () => number;
  setInterimTranscript: (transcript: string) => boolean;
  commitFinalTranscript: (transcript: string) => FinalTranscriptResult;
  markThinking: (responseEpoch: number) => boolean;
  enqueueSpeech: (text: string, responseEpoch: number, key?: string) => SpeechEnqueueResult;
  interrupt: () => number;
  exit: () => void;
  fail: (code: string, message: string) => void;
  clearError: () => void;
  isCurrentResponseEpoch: (responseEpoch: number) => boolean;
  dispose: () => void;
}

interface SpeechQueueEntry {
  key: string;
  text: string;
  responseEpoch: number;
}

interface ActiveSpeech {
  entry: SpeechQueueEntry;
  playbackToken: number;
}

interface MutableState {
  status: LiveVoiceStatus;
  captureId: number;
  responseEpoch: number;
  interimTranscript: string;
  finalTranscript: string;
  error: LiveVoiceError | null;
}

const normalizeWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();

class DefaultLiveVoiceCore implements LiveVoiceCore {
  private readonly player: LiveVoiceSpeechPlayer;
  private readonly normalizeTranscript: (transcript: string) => string;
  private readonly listeners = new Set<(snapshot: LiveVoiceSnapshot) => void>();
  private readonly queuedSpeechKeys = new Set<string>();
  private readonly speechQueue: SpeechQueueEntry[] = [];

  private state: MutableState = {
    status: 'idle',
    captureId: 0,
    responseEpoch: 0,
    interimTranscript: '',
    finalTranscript: '',
    error: null,
  };
  private activeSpeech: ActiveSpeech | null = null;
  private captureCommitted = false;
  private playbackToken = 0;
  private disposed = false;

  constructor(options: LiveVoiceCoreOptions) {
    this.player = options.player;
    this.normalizeTranscript = options.normalizeTranscript ?? normalizeWhitespace;
  }

  getSnapshot = (): LiveVoiceSnapshot => ({
    ...this.state,
    pendingSpeechCount: this.speechQueue.length + (this.activeSpeech === null ? 0 : 1),
    activeSpeechKey: this.activeSpeech?.entry.key ?? null,
    error: this.state.error ? { ...this.state.error } : null,
  });

  subscribe = (listener: (snapshot: LiveVoiceSnapshot) => void): (() => void) => {
    if (this.disposed) {
      return () => {};
    }

    this.listeners.add(listener);
    listener(this.getSnapshot());
    return () => this.listeners.delete(listener);
  };

  beginListening = (): number => {
    if (this.disposed) {
      return this.state.captureId;
    }
    if (this.state.status === 'listening') {
      return this.state.captureId;
    }

    const isInterruptingResponse =
      this.state.status === 'thinking' || this.state.status === 'speaking' || this.activeSpeech !== null || this.speechQueue.length > 0;
    // A new capture is also a hard response boundary after the previous FIFO
    // drained back to idle. Without this, a late integration callback holding
    // the previous epoch could enqueue speech while the microphone is open.
    if (this.state.responseEpoch > 0) {
      this.advanceResponseEpoch();
    }
    if (isInterruptingResponse) {
      this.state.status = 'interrupted';
      this.state.interimTranscript = '';
      this.emit();
    }

    this.state.captureId += 1;
    this.captureCommitted = false;
    this.state.status = 'listening';
    this.state.interimTranscript = '';
    this.state.finalTranscript = '';
    this.state.error = null;
    this.emit();
    return this.state.captureId;
  };

  setInterimTranscript = (transcript: string): boolean => {
    if (this.disposed || this.state.status !== 'listening') {
      return false;
    }

    this.state.interimTranscript = transcript;
    this.emit();
    return true;
  };

  commitFinalTranscript = (transcript: string): FinalTranscriptResult => {
    if (this.disposed) {
      return { accepted: false, reason: 'disposed' };
    }
    if (this.captureCommitted) {
      return { accepted: false, reason: 'already-committed' };
    }
    if (this.state.status !== 'listening') {
      return { accepted: false, reason: 'not-listening' };
    }

    const normalized = this.normalizeTranscript(transcript);
    if (!normalized) {
      return { accepted: false, reason: 'empty' };
    }

    this.captureCommitted = true;
    const responseEpoch = this.advanceResponseEpoch();
    this.state.status = 'thinking';
    this.state.interimTranscript = '';
    this.state.finalTranscript = normalized;
    this.state.error = null;
    this.emit();

    return {
      accepted: true,
      captureId: this.state.captureId,
      responseEpoch,
      transcript: normalized,
    };
  };

  markThinking = (responseEpoch: number): boolean => {
    if (this.disposed || this.state.error !== null || this.activeSpeech !== null || !this.isCurrentResponseEpoch(responseEpoch)) {
      return false;
    }

    this.state.status = 'thinking';
    this.emit();
    return true;
  };

  enqueueSpeech = (text: string, responseEpoch: number, key?: string): SpeechEnqueueResult => {
    if (this.disposed) {
      return { accepted: false, reason: 'disposed' };
    }
    if (this.state.error !== null) {
      return { accepted: false, reason: 'error' };
    }
    if (!this.isCurrentResponseEpoch(responseEpoch)) {
      return { accepted: false, reason: 'stale-epoch' };
    }

    const normalizedText = text.trim();
    if (!normalizedText) {
      return { accepted: false, reason: 'empty' };
    }

    const speechKey = (key ?? normalizedText).trim();
    if (!speechKey) {
      return { accepted: false, reason: 'empty' };
    }
    if (this.queuedSpeechKeys.has(speechKey)) {
      return { accepted: false, reason: 'duplicate' };
    }

    this.queuedSpeechKeys.add(speechKey);
    this.speechQueue.push({
      key: speechKey,
      text: normalizedText,
      responseEpoch,
    });
    this.emit();
    this.playNextSpeech();
    return { accepted: true, key: speechKey };
  };

  interrupt = (): number => {
    if (this.disposed) {
      return this.state.responseEpoch;
    }

    const responseEpoch = this.advanceResponseEpoch();
    this.state.status = 'interrupted';
    this.state.interimTranscript = '';
    this.state.error = null;
    this.emit();
    return responseEpoch;
  };

  exit = (): void => {
    if (this.disposed) {
      return;
    }

    this.advanceResponseEpoch();
    this.captureCommitted = false;
    this.state.status = 'idle';
    this.state.interimTranscript = '';
    this.state.finalTranscript = '';
    this.state.error = null;
    this.emit();
  };

  fail = (code: string, message: string): void => {
    if (this.disposed) {
      return;
    }

    this.advanceResponseEpoch();
    this.state.status = 'error';
    this.state.interimTranscript = '';
    this.state.error = { code, message };
    this.emit();
  };

  clearError = (): void => {
    if (this.disposed || this.state.error === null) {
      return;
    }

    this.state.status = 'idle';
    this.state.error = null;
    this.emit();
  };

  isCurrentResponseEpoch = (responseEpoch: number): boolean => !this.disposed && responseEpoch > 0 && responseEpoch === this.state.responseEpoch;

  dispose = (): void => {
    if (this.disposed) {
      return;
    }

    this.advanceResponseEpoch();
    this.disposed = true;
    this.listeners.clear();
  };

  private advanceResponseEpoch(): number {
    this.state.responseEpoch += 1;
    this.cancelSpeech();
    return this.state.responseEpoch;
  }

  private cancelSpeech(): void {
    this.playbackToken += 1;
    this.activeSpeech = null;
    this.speechQueue.length = 0;
    this.queuedSpeechKeys.clear();
    try {
      this.player.stop();
    } catch {
      // State invalidation already happened; a browser adapter may report the
      // playback failure separately without reviving the stale callbacks.
    }
  }

  private playNextSpeech(): void {
    if (this.disposed || this.activeSpeech !== null) {
      return;
    }

    let entry = this.speechQueue.shift();
    while (entry && !this.isCurrentResponseEpoch(entry.responseEpoch)) {
      entry = this.speechQueue.shift();
    }
    if (!entry) {
      if (this.state.status === 'speaking') {
        this.state.status = 'idle';
      }
      this.emit();
      return;
    }

    const playbackToken = ++this.playbackToken;
    this.activeSpeech = { entry, playbackToken };
    this.emit();

    try {
      this.player.play(entry.text, {
        onStart: () => this.handleSpeechStart(playbackToken),
        onEnd: () => this.handleSpeechEnd(playbackToken),
        onError: error => this.handleSpeechError(playbackToken, error),
      });
    } catch (error) {
      this.handleSpeechError(playbackToken, error);
    }
  }

  private handleSpeechStart(playbackToken: number): void {
    if (!this.isActivePlayback(playbackToken)) {
      return;
    }

    this.state.status = 'speaking';
    this.emit();
  }

  private handleSpeechEnd(playbackToken: number): void {
    if (!this.isActivePlayback(playbackToken)) {
      return;
    }

    this.activeSpeech = null;

    if (this.speechQueue.length === 0) {
      if (this.state.status === 'speaking') {
        this.state.status = 'idle';
      }
      this.emit();
      return;
    }

    this.emit();
    this.playNextSpeech();
  }

  private handleSpeechError(playbackToken: number, error: unknown): void {
    if (!this.isActivePlayback(playbackToken)) {
      return;
    }

    const message = error instanceof Error && error.message ? error.message : 'Speech playback failed';
    this.cancelSpeech();
    this.state.status = 'error';
    this.state.error = {
      code: 'speech-playback',
      message,
    };
    this.emit();
  }

  private isActivePlayback(playbackToken: number): boolean {
    return !this.disposed && this.activeSpeech?.playbackToken === playbackToken && this.isCurrentResponseEpoch(this.activeSpeech.entry.responseEpoch);
  }

  private emit(): void {
    if (this.disposed) {
      return;
    }

    const snapshot = this.getSnapshot();
    for (const listener of [...this.listeners]) {
      listener(snapshot);
    }
  }
}

export function createLiveVoiceCore(options: LiveVoiceCoreOptions): LiveVoiceCore {
  return new DefaultLiveVoiceCore(options);
}
