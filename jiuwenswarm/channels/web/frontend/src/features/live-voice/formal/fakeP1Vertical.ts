import { AudioPort, AudioPortViolation, createAudioRenderPlan, type AudioResponseRef } from './audioPort.js';
import {
  CONTRACT_VERSION,
  createRouteTelemetryLedger,
  createRouteTelemetryRecord,
  type RouteTelemetryLedger,
  type RouteTelemetryRecord,
} from './liveVoiceRouteTelemetry.js';

export type FakeP1CommitState = 'partial' | 'uncommitted' | 'committed';

export interface FakeP1VerticalInput {
  readonly state: FakeP1CommitState;
  readonly response: Readonly<AudioResponseRef>;
  readonly display_text: string;
  readonly spoken_text: string;
  readonly audio: Uint8Array;
  readonly correlation_id: string;
  readonly observed_at: string;
}

export interface FakeP1VerticalResult {
  readonly committed: boolean;
  readonly available: boolean;
  readonly queued_audio: number;
  readonly route: Readonly<RouteTelemetryRecord> | null;
}

export class FakeP1VerticalViolation extends Error {
  constructor(
    readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'FakeP1VerticalViolation';
  }
}

export class FakeP1Vertical {
  readonly #enabled: boolean;
  readonly #audio = new AudioPort();
  readonly #routes: RouteTelemetryLedger;

  constructor(options: Readonly<{ enabled?: boolean }> = {}) {
    this.#enabled = options.enabled ?? true;
    if (typeof this.#enabled !== 'boolean') {
      throw new FakeP1VerticalViolation('INVALID_BOOLEAN', 'enabled must be boolean');
    }
    this.#routes = createRouteTelemetryLedger();
  }

  run(input: Readonly<FakeP1VerticalInput>): Readonly<FakeP1VerticalResult> {
    if (!(['partial', 'uncommitted', 'committed'] as const).includes(input.state)) {
      throw new FakeP1VerticalViolation('INVALID_COMMIT_STATE', 'input state is invalid');
    }
    if (input.state !== 'committed') {
      return Object.freeze({ committed: false, available: this.#enabled, queued_audio: 0, route: null });
    }
    const route = createRouteTelemetryRecord({
      segment_id: 'p1.fake_vertical',
      implementation_class: this.#enabled ? 'demo_substitute' : 'unsupported',
      owner_module: 'formal.fakeP1Vertical',
      capability_provider: this.#enabled ? 'deterministic-speech-fake' : null,
      contract_version: CONTRACT_VERSION,
      correlation_id: input.correlation_id,
      observed_at: input.observed_at,
      safe_reason: this.#enabled ? 'DETERMINISTIC_FAKE_ONLY' : 'TRACK_UNAVAILABLE',
    });
    if (!this.#enabled) {
      this.#routes.add(route);
      return Object.freeze({ committed: true, available: false, queued_audio: 0, route });
    }
    createAudioRenderPlan(input.display_text, input.spoken_text);
    if (!(input.audio instanceof Uint8Array) || input.audio.byteLength === 0) {
      throw new AudioPortViolation('INVALID_AUDIO_CHUNK', 'audio must be non-empty bytes');
    }
    this.#audio.begin(input.response);
    const queued = this.#audio.enqueue({
      response: input.response,
      unit_id: 'unit-1',
      seq: 0,
      audio: input.audio,
      provider: Object.freeze({
        provider_id: 'deterministic-speech-fake',
        implementation_class: 'demo_substitute',
        fallback_from: null,
      }),
    });
    this.#routes.add(route);
    return Object.freeze({ committed: true, available: true, queued_audio: queued ? 1 : 0, route });
  }

  pending(response: Readonly<AudioResponseRef>) {
    return this.#audio.pending(response);
  }

  routes(): readonly Readonly<RouteTelemetryRecord>[] {
    return this.#routes.list();
  }
}
