import {
  BrowserAudioIOAdapter,
  inspectBrowserAudioPlatform,
  type BrowserAudioCaptureMetadata,
  type BrowserAudioCaptureStateEvent,
  type BrowserAudioDeviceEvent,
  type BrowserAudioPlayoutMetadata,
  type BrowserAudioPlayoutEvent,
} from '../../src/features/live-voice/formal/adapters/browserAudioIOAdapter.js';
import { audioFrameSamples } from '../../src/features/live-voice/formal/audioPort.js';

interface HarnessState {
  capability: ReturnType<typeof inspectBrowserAudioPlatform>;
  capture: BrowserAudioCaptureMetadata | null;
  playout: BrowserAudioPlayoutMetadata | null;
  capture_state: BrowserAudioCaptureStateEvent | null;
  device: BrowserAudioDeviceEvent | null;
  playout_state: BrowserAudioPlayoutEvent | null;
  frame_count: number;
  first_frame: { seq: number; sample_cursor: number; context_time_s: number; sample_count: number } | null;
  last_frame: { seq: number; sample_cursor: number; context_time_s: number; sample_count: number } | null;
  error: { name: string; reason: string | null; message: string } | null;
}

const state: HarnessState = {
  capability: inspectBrowserAudioPlatform(true),
  capture: null,
  playout: null,
  capture_state: null,
  device: null,
  playout_state: null,
  frame_count: 0,
  first_frame: null,
  last_frame: null,
  error: null,
};

const output = document.querySelector<HTMLPreElement>('#state');
if (output === null) throw new Error('state output is missing');

function render(): void {
  output.textContent = JSON.stringify(state, null, 2);
}

function safeError(error: unknown): HarnessState['error'] {
  if (error instanceof Error) {
    return {
      name: error.name,
      reason: 'reason' in error && typeof error.reason === 'string' ? error.reason : null,
      message: error.message,
    };
  }
  return { name: 'UnknownError', reason: null, message: 'unknown error' };
}

const adapter = new BrowserAudioIOAdapter({
  enabled: true,
  observer: {
    onCaptureFrame(frame) {
      const summary = {
        seq: frame.seq,
        sample_cursor: frame.sample_cursor,
        context_time_s: frame.context_time_s,
        sample_count: frame.samples.length,
      };
      state.frame_count += 1;
      state.first_frame ??= summary;
      state.last_frame = summary;
      if (state.frame_count === 1 || state.frame_count % 10 === 0) render();
    },
    onCaptureState(event) {
      state.capture_state = event;
      render();
    },
    onDeviceChange(event) {
      state.device = event;
      render();
    },
    onPlayoutState(event) {
      state.playout_state = event;
      render();
    },
  },
});
let playbackGeneration = 0;

async function startCapture(): Promise<void> {
  state.error = null;
  try {
    state.playout = await adapter.unlockPlayout();
    state.capture = await adapter.startCapture();
  } catch (error) {
    state.error = safeError(error);
  }
  render();
}

async function stopCapture(): Promise<void> {
  state.error = null;
  try {
    await adapter.stopCapture('harness_stop');
  } catch (error) {
    state.error = safeError(error);
  }
  render();
}

async function playSyntheticPcm(): Promise<void> {
  state.error = null;
  try {
    state.playout = await adapter.unlockPlayout();
    const response = Object.freeze({
      interaction_id: 'aio-harness-interaction',
      response_id: `aio-harness-response-${playbackGeneration}`,
      response_generation: playbackGeneration,
    });
    playbackGeneration += 1;
    adapter.beginPlayout(response);
    const sampleRate = state.playout.sample_rate_hz;
    const samplesPerChunk = audioFrameSamples(sampleRate);
    for (let seq = 0; seq < 10; seq += 1) {
      const samples = new Float32Array(samplesPerChunk);
      for (let index = 0; index < samples.length; index += 1) {
        const absoluteSample = seq * samples.length + index;
        samples[index] = Math.sin((2 * Math.PI * 440 * absoluteSample) / sampleRate) * 0.08;
      }
      adapter.enqueuePlayout({
        response,
        unit_id: 'synthetic-tone',
        seq,
        sample_rate_hz: sampleRate,
        channel_count: 1,
        samples,
        provider: Object.freeze({
          provider_id: 'aio-b-manual-synthetic-tone',
          implementation_class: 'demo_substitute',
          fallback_from: null,
        }),
      });
    }
  } catch (error) {
    state.error = safeError(error);
  }
  render();
}

async function closeAdapter(): Promise<void> {
  state.error = null;
  try {
    await adapter.close();
  } catch (error) {
    state.error = safeError(error);
  }
  render();
}

document.querySelector<HTMLButtonElement>('#start')?.addEventListener('click', () => void startCapture());
document.querySelector<HTMLButtonElement>('#stop')?.addEventListener('click', () => void stopCapture());
document.querySelector<HTMLButtonElement>('#play')?.addEventListener('click', () => void playSyntheticPcm());
document.querySelector<HTMLButtonElement>('#close')?.addEventListener('click', () => void closeAdapter());

Object.assign(window, {
  __LIVE_VOICE_AIO_HARNESS__: Object.freeze({
    state,
    startCapture,
    stopCapture,
    playSyntheticPcm,
    closeAdapter,
  }),
});
render();
