import type {
  BrowserAudioContextLike,
  BrowserAudioEnvironment,
  BrowserAudioWorkletNodeLike,
  BrowserMediaDeviceInfoLike,
  BrowserMediaStreamLike,
} from '../formal/adapters/browserAudioIOAdapter.js';

const MAX_WAV_BYTES = 4 * 1024 * 1024;
const MIN_START_DELAY_MS = 250;
const MAX_START_DELAY_MS = 5_000;
const CONTEXT_RESUME_TIMEOUT_MS = 2_000;

export interface FixedAudioCaptureFixture {
  readonly input_case_id: string;
  readonly wav_bytes: ArrayBuffer;
  readonly expected_sample_rate_hz: number;
  readonly start_delay_ms: number;
}

export interface FixedAudioCapturePlatform {
  readonly isSecureContext?: boolean;
  readonly document?: BrowserAudioEnvironment['document'];
  createAudioContext(): FixedAudioContext;
  createAudioWorkletNode?(context: BrowserAudioContextLike, name: string, options: Readonly<Record<string, unknown>>): BrowserAudioWorkletNodeLike;
  createId?(): string;
}

export interface FixedAudioCaptureOwner {
  readonly environment: BrowserAudioEnvironment;
  readonly input_case_id: string;
  close(): Promise<void>;
}

interface FixedAudioContext extends BrowserAudioContextLike {
  createMediaStreamDestination(): Readonly<{ stream: BrowserMediaStreamLike }>;
}

interface DecodedWav {
  readonly sampleRate: number;
  readonly samples: Float32Array;
}

function violation(reason: string): Error {
  return new Error(`FIXED_AUDIO_${reason}`);
}

function fourCc(view: DataView, offset: number): string {
  return String.fromCharCode(view.getUint8(offset), view.getUint8(offset + 1), view.getUint8(offset + 2), view.getUint8(offset + 3));
}

function decodePcm16MonoWav(bytes: ArrayBuffer, expectedSampleRate: number): DecodedWav {
  if (!(bytes instanceof ArrayBuffer) || bytes.byteLength > MAX_WAV_BYTES || bytes.byteLength < 44) throw violation('WAV_INVALID');
  const view = new DataView(bytes);
  if (fourCc(view, 0) !== 'RIFF' || fourCc(view, 8) !== 'WAVE') throw violation('WAV_INVALID');
  if (view.getUint32(4, true) + 8 !== bytes.byteLength) throw violation('WAV_INVALID');

  let format: Readonly<{ channels: number; sampleRate: number; bitsPerSample: number }> | null = null;
  let dataOffset = -1;
  let dataLength = -1;
  for (let offset = 12; offset + 8 <= bytes.byteLength;) {
    const chunkLength = view.getUint32(offset + 4, true);
    const payloadOffset = offset + 8;
    const nextOffset = payloadOffset + chunkLength + (chunkLength % 2);
    if (nextOffset > bytes.byteLength) throw violation('WAV_INVALID');
    const kind = fourCc(view, offset);
    if (kind === 'fmt ') {
      if (chunkLength < 16 || format !== null) throw violation('WAV_INVALID');
      if (view.getUint16(payloadOffset, true) !== 1) throw violation('WAV_PCM16_REQUIRED');
      format = Object.freeze({
        channels: view.getUint16(payloadOffset + 2, true),
        sampleRate: view.getUint32(payloadOffset + 4, true),
        bitsPerSample: view.getUint16(payloadOffset + 14, true),
      });
    } else if (kind === 'data') {
      if (dataOffset !== -1) throw violation('WAV_INVALID');
      dataOffset = payloadOffset;
      dataLength = chunkLength;
    }
    offset = nextOffset;
  }
  if (format === null || dataOffset < 0 || dataLength <= 0 || dataLength % 2 !== 0) throw violation('WAV_INVALID');
  if (format.channels !== 1) throw violation('WAV_MONO_REQUIRED');
  if (format.bitsPerSample !== 16) throw violation('WAV_PCM16_REQUIRED');
  if (!Number.isInteger(expectedSampleRate) || expectedSampleRate <= 0 || format.sampleRate !== expectedSampleRate) {
    throw violation('WAV_SAMPLE_RATE_MISMATCH');
  }
  const samples = new Float32Array(dataLength / 2);
  for (let index = 0; index < samples.length; index += 1) samples[index] = view.getInt16(dataOffset + index * 2, true) / 32768;
  return Object.freeze({ sampleRate: format.sampleRate, samples });
}

function defaultPlatform(): FixedAudioCapturePlatform {
  if (typeof window === 'undefined' || typeof document === 'undefined' || typeof AudioContext === 'undefined') throw violation('PLATFORM_UNAVAILABLE');
  const audioWorkletNode = (window as Window & { AudioWorkletNode?: typeof AudioWorkletNode }).AudioWorkletNode;
  return Object.freeze({
    isSecureContext: window.isSecureContext,
    document: document as unknown as BrowserAudioEnvironment['document'],
    createAudioContext: () => new AudioContext() as unknown as FixedAudioContext,
    createAudioWorkletNode: audioWorkletNode
      ? (context: BrowserAudioContextLike, name: string, options: Readonly<Record<string, unknown>>) =>
          new audioWorkletNode(context as unknown as BaseAudioContext, name, options as AudioWorkletNodeOptions) as unknown as BrowserAudioWorkletNodeLike
      : undefined,
    createId: typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? () => crypto.randomUUID() : undefined,
  });
}

async function requireRunningContext(context: FixedAudioContext): Promise<void> {
  if (context.state === 'running') return;
  let timeout: ReturnType<typeof globalThis.setTimeout> | null = null;
  try {
    await Promise.race([
      context.resume(),
      new Promise<never>((_resolve, reject) => {
        timeout = globalThis.setTimeout(() => reject(violation('CONTEXT_NOT_RUNNING')), CONTEXT_RESUME_TIMEOUT_MS);
      }),
    ]);
  } catch {
    throw violation('CONTEXT_NOT_RUNNING');
  } finally {
    if (timeout !== null) globalThis.clearTimeout(timeout);
  }
  if (context.state !== 'running') throw violation('CONTEXT_NOT_RUNNING');
}

export function createFixedAudioCaptureOwner(
  fixture: FixedAudioCaptureFixture,
  platform: FixedAudioCapturePlatform = defaultPlatform(),
): FixedAudioCaptureOwner {
  if (fixture === null || typeof fixture !== 'object' || typeof fixture.input_case_id !== 'string' || fixture.input_case_id.length === 0) {
    throw violation('FIXTURE_INVALID');
  }
  const inputCaseId = fixture.input_case_id;
  const startDelayMs = fixture.start_delay_ms;
  const expectedSampleRateHz = fixture.expected_sample_rate_hz;
  const wavBytes = fixture.wav_bytes;
  if (!Number.isInteger(startDelayMs) || startDelayMs < MIN_START_DELAY_MS || startDelayMs > MAX_START_DELAY_MS) {
    throw violation('START_DELAY_INVALID');
  }
  const decoded = decodePcm16MonoWav(wavBytes, expectedSampleRateHz);
  const sampleRate = decoded.sampleRate;
  let sourceBytes: Float32Array | null = decoded.samples;
  let fixtureContext: FixedAudioContext;
  let destination: Readonly<{ stream: BrowserMediaStreamLike }>;
  try {
    fixtureContext = platform.createAudioContext();
    if (fixtureContext.sampleRate !== sampleRate) throw violation('CONTEXT_SAMPLE_RATE_MISMATCH');
    destination = fixtureContext.createMediaStreamDestination();
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('FIXED_AUDIO_')) throw error;
    throw violation('CONTEXT_CREATE_FAILED');
  }

  let closed = false;
  let streamClaims = 0;
  let started = false;
  let source: ReturnType<FixedAudioContext['createBufferSource']> | null = null;
  const destinations: Array<Readonly<{ stream: BrowserMediaStreamLike }>> = [destination];

  const close = async (): Promise<void> => {
    if (closed) return;
    closed = true;
    try {
      source?.stop();
    } catch {
      // Cleanup is best-effort and must not expose platform exceptions.
    }
    try {
      source?.disconnect();
    } catch {
      // Cleanup is best-effort and must not expose platform exceptions.
    }
    for (const ownedDestination of destinations) {
      for (const track of ownedDestination.stream.getTracks()) {
        try {
          track.stop();
        } catch {
          // A stopped fixture track is already terminal.
        }
      }
    }
    source = null;
    sourceBytes = null;
    try {
      await fixtureContext.close();
    } catch {
      // The owner is closed even if the browser has already torn its context down.
    }
  };

  const getUserMedia = async (): Promise<BrowserMediaStreamLike> => {
    if (closed) throw violation('OWNER_CLOSED');
    if (streamClaims >= 2) throw violation('STREAM_ALREADY_CLAIMED');
    streamClaims += 1;
    if (streamClaims === 2) {
      try {
        await requireRunningContext(fixtureContext);
        const successor = fixtureContext.createMediaStreamDestination();
        destinations.push(successor);
        return successor.stream;
      } catch {
        await close();
        throw violation('SUCCESSOR_STREAM_FAILED');
      }
    }
    try {
      await requireRunningContext(fixtureContext);
      const values = sourceBytes;
      if (values === null) throw violation('OWNER_CLOSED');
      const buffer = fixtureContext.createBuffer(1, values.length, sampleRate);
      buffer.copyToChannel(values, 0);
      source = fixtureContext.createBufferSource();
      source.buffer = buffer;
      source.connect(destination);
      source.start(fixtureContext.currentTime + startDelayMs / 1000);
      started = true;
      return destination.stream;
    } catch (error) {
      await close();
      if (error instanceof Error && error.message.startsWith('FIXED_AUDIO_')) throw error;
      throw violation('SOURCE_START_FAILED');
    }
  };

  const environment: BrowserAudioEnvironment = Object.freeze({
    isSecureContext: platform.isSecureContext ?? true,
    document: platform.document ?? null,
    mediaDevices: Object.freeze({
      getUserMedia,
      enumerateDevices: async (): Promise<BrowserMediaDeviceInfoLike[]> => [],
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
    permissions: Object.freeze({
      query: async () => Object.freeze({ state: 'granted', addEventListener: () => undefined, removeEventListener: () => undefined }),
    }),
    createAudioContext: () => platform.createAudioContext(),
    createAudioWorkletNode: platform.createAudioWorkletNode ?? null,
    createId: platform.createId ?? null,
  });
  void started;
  return Object.freeze({ environment, input_case_id: inputCaseId, close });
}
