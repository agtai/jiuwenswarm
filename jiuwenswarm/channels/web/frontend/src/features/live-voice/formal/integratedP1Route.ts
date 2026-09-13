import type { LiveVoiceSpeechPlayer } from '../liveVoiceCore.js';
import {
  BrowserSpeechRecognitionAdapter,
  type BrowserRecognitionCapture,
  type BrowserRecognitionObservation,
} from './adapters/browserSpeechRecognitionAdapter.js';
import { BrowserSpeechSynthesisAdapter, type BrowserSynthesisEnvironment } from './adapters/browserSpeechSynthesisAdapter.js';
import { CONTRACT_VERSION, createRouteTelemetryRecord, type RouteTelemetryRecord } from './liveVoiceRouteTelemetry.js';

export { BrowserSpeechRecognitionAdapter, BrowserSpeechRecognitionAdapterViolation } from './adapters/browserSpeechRecognitionAdapter.js';
export { BrowserSpeechSynthesisAdapter, BrowserSpeechSynthesisAdapterViolation } from './adapters/browserSpeechSynthesisAdapter.js';

export interface IntegratedP1Route {
  readonly routeLabel: string;
  readonly speechPlayer: LiveVoiceSpeechPlayer;
  beginRecognition(): void;
  observeRecognition(transcript: string, isFinal: boolean): Readonly<BrowserRecognitionObservation> | null;
  finishRecognition(): boolean;
  cancelRecognition(): boolean;
  routeTelemetry(): readonly Readonly<RouteTelemetryRecord>[];
  capabilities(): Readonly<{
    recognition_streaming: false;
    recognition_hypothesis_cursor: false;
    synthesis_streaming: false;
    synthesis_audio_chunk_cursor: false;
  }>;
}

export interface IntegratedP1RouteOptions {
  readonly correlationId: string;
  readonly observedAt?: string;
  readonly recognitionAvailable?: boolean;
  readonly synthesisEnvironment?: BrowserSynthesisEnvironment;
}

function browserRecognitionAvailable(): boolean {
  const browserWindow =
    typeof window === 'undefined'
      ? null
      : (window as Window & {
          SpeechRecognition?: unknown;
          webkitSpeechRecognition?: unknown;
        });
  return browserWindow !== null && (typeof browserWindow.SpeechRecognition === 'function' || typeof browserWindow.webkitSpeechRecognition === 'function');
}

export function createIntegratedP1Route(options: Readonly<IntegratedP1RouteOptions>): IntegratedP1Route {
  const recognition = new BrowserSpeechRecognitionAdapter({
    available: options.recognitionAvailable ?? browserRecognitionAvailable(),
  });
  const synthesis = new BrowserSpeechSynthesisAdapter(options.synthesisEnvironment);
  const routes: RouteTelemetryRecord[] = [];
  let activeCapture: Readonly<BrowserRecognitionCapture> | null = null;
  let playbackGeneration = 0;

  const recordRecognitionRoute = () => {
    routes.push(
      createRouteTelemetryRecord({
        segment_id: 'p1.browser_recognition',
        implementation_class: recognition.capability.available ? 'fallback' : 'unsupported',
        owner_module: 'formal.adapters.browserSpeechRecognitionAdapter',
        capability_provider: recognition.capability.available ? recognition.capability.provider.provider_id : null,
        contract_version: CONTRACT_VERSION,
        correlation_id: options.correlationId,
        observed_at: options.observedAt ?? new Date().toISOString(),
        safe_reason: recognition.capability.available ? 'BROWSER_SPEECH_COMPATIBILITY_ADAPTER' : 'BROWSER_RECOGNITION_UNAVAILABLE',
      })
    );
  };
  const recordSynthesisRoute = () => {
    routes.push(
      createRouteTelemetryRecord({
        segment_id: 'p1.browser_synthesis',
        implementation_class: synthesis.capability.available ? 'fallback' : 'unsupported',
        owner_module: 'formal.adapters.browserSpeechSynthesisAdapter',
        capability_provider: synthesis.capability.available ? synthesis.capability.provider.provider_id : null,
        contract_version: CONTRACT_VERSION,
        correlation_id: options.correlationId,
        observed_at: options.observedAt ?? new Date().toISOString(),
        safe_reason: synthesis.capability.available ? 'BROWSER_SPEECH_COMPATIBILITY_ADAPTER' : 'BROWSER_SYNTHESIS_UNAVAILABLE',
      })
    );
  };

  const speechPlayer: LiveVoiceSpeechPlayer = {
    play(text, callbacks): void {
      const generation = playbackGeneration;
      playbackGeneration += 1;
      try {
        synthesis.play(
          {
            response: Object.freeze({
              interaction_id: 'browser-p1-playback',
              response_id: `browser-p1-response-${generation}`,
              response_generation: generation,
            }),
            spoken_text: text,
          },
          callbacks
        );
        recordSynthesisRoute();
      } catch (error) {
        if (!synthesis.capability.available) recordSynthesisRoute();
        throw error;
      }
    },
    stop(): void {
      synthesis.stop();
    },
  };

  const allAvailable = recognition.capability.available && synthesis.capability.available;
  return {
    routeLabel: allAvailable ? 'P1 · Browser Speech · fallback' : 'P1 · Browser Speech · unsupported',
    speechPlayer,
    beginRecognition(): void {
      if (activeCapture !== null) recognition.cancel(activeCapture);
      try {
        activeCapture = recognition.begin('browser-live-voice');
        recordRecognitionRoute();
      } catch (error) {
        if (!recognition.capability.available) recordRecognitionRoute();
        throw error;
      }
    },
    observeRecognition(transcript: string, isFinal: boolean): Readonly<BrowserRecognitionObservation> | null {
      return activeCapture === null ? null : recognition.observe(activeCapture, transcript, isFinal);
    },
    finishRecognition(): boolean {
      if (activeCapture === null) return false;
      const capture = activeCapture;
      activeCapture = null;
      return recognition.finish(capture);
    },
    cancelRecognition(): boolean {
      if (activeCapture === null) return false;
      const capture = activeCapture;
      activeCapture = null;
      return recognition.cancel(capture);
    },
    routeTelemetry: () => routes.slice(),
    capabilities: () =>
      Object.freeze({
        recognition_streaming: false,
        recognition_hypothesis_cursor: false,
        synthesis_streaming: false,
        synthesis_audio_chunk_cursor: false,
      }),
  };
}
