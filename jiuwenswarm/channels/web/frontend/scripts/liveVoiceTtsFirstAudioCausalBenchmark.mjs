import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

import {
  PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
  PRODUCT_P1_MEDIA_CLOSE_METHOD,
  PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD,
  ProductP1VoiceRouteOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP1VoiceRoute.js';
import {
  decodeAudioFrame,
  encodeAudioFrame,
  serializeMediaControl,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/adapters/browserDedicatedMediaRoute.js';

const SCHEMA_VERSION = 'live-voice.tts-first-audio-causal-report.v0';
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const GIT_COMMIT = /^[0-9a-f]{40}$/;
const SUCCESSOR_ACK_DELAYS_MS = Object.freeze([0, 250, 750, 1100]);
const ALLOWED_ACK_DELAYS_MS = new Set(SUCCESSOR_ACK_DELAYS_MS);
const FORBIDDEN_EFFECTS = Object.freeze({ agent: 0, tool: 0, task: 0, history: 0 });
const MANUAL_EOT_FALLBACK = Object.freeze({
  status: 'fallback',
  requested_capability: 'media.end_of_turn.v1',
  reason_id: 'MEDIA_END_OF_TURN_FEATURE_OFF',
  fallback: 'manual',
  visible: true,
});

function fail(code) {
  throw new Error(code);
}

function canonicalInteger(value, minimum, maximum) {
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) && value >= minimum && value <= maximum ? value : null;
  }
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

class FakeEventTarget {
  listeners = new Map();

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener();
  }
}

class FakeAudioNode {
  connect(destination) {
    return destination;
  }

  disconnect() {}
}

class FakeTrack extends FakeEventTarget {
  constructor(id) {
    super();
    this.id = id;
    this.kind = 'audio';
    this.readyState = 'live';
    this.muted = false;
  }

  stop() {
    this.readyState = 'ended';
  }

  getSettings() {
    return {
      sampleRate: 48_000,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    };
  }
}

class FakeAudioContext {
  constructor(onSourceScheduled, schedulePlayout, playoutDurationMs) {
    this.sampleRate = 48_000;
    this.currentTime = 0;
    this.destination = Object.freeze({ kind: 'destination' });
    this.state = 'suspended';
    this.onstatechange = null;
    this.audioWorklet = { addModule: async () => undefined };
    this.onSourceScheduled = onSourceScheduled;
    this.schedulePlayout = schedulePlayout;
    this.playoutDurationMs = playoutDurationMs;
  }

  async resume() {
    this.state = 'running';
  }

  async close() {
    this.state = 'closed';
  }

  createMediaStreamSource() {
    return new FakeAudioNode();
  }

  createBuffer(_channels, length, sampleRate) {
    return { length, sampleRate, copyToChannel() {} };
  }

  createBufferSource() {
    const context = this;
    const source = {
      buffer: null,
      onended: null,
      connect() {},
      disconnect() {},
      start() {
        context.onSourceScheduled();
        context.schedulePlayout(context.playoutDurationMs, () => source.onended?.());
      },
      stop() {},
    };
    return source;
  }
}

function bindingForCapture(params, index) {
  return {
    lease_id: `tts-benchmark-uplink-lease-${index}`,
    authority_evidence_id: `tts-benchmark-uplink-authority-${index}`,
    connection_id: 'tts-benchmark-connection',
    connection_epoch: 0,
    session_id: params.session_id,
    media_session_id: `tts-benchmark-uplink-session-${index}`,
    interaction_id: params.interaction_id,
    track_id: params.track_id,
    correlation_id: params.correlation_id,
    direction: 'uplink',
    generation: {
      kind: 'capture',
      id: params.capture_id,
      value: params.capture_generation,
    },
    frame_format: {
      sample_rate_hz: 48_000,
      samples_per_channel: 960,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
    playout: null,
  };
}

function downlinkBinding(response, identity) {
  return {
    lease_id: 'tts-benchmark-downlink-lease',
    authority_evidence_id: 'tts-benchmark-downlink-authority',
    connection_id: 'tts-benchmark-connection',
    connection_epoch: 0,
    session_id: identity.session_id,
    media_session_id: 'tts-benchmark-downlink-session',
    interaction_id: response.interaction_id,
    track_id: 'tts-benchmark-playout-track',
    correlation_id: identity.correlation_id,
    direction: 'downlink',
    generation: {
      kind: 'response',
      id: response.response_id,
      value: response.response_generation,
    },
    frame_format: {
      sample_rate_hz: 48_000,
      samples_per_channel: 960,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
    playout: {
      response_id: response.response_id,
      response_generation: response.response_generation,
      unit_id: identity.unit_id,
    },
  };
}

function rounded(value) {
  return Math.round(value * 1_000) / 1_000;
}

function stableReason(error) {
  if (error && typeof error === 'object') {
    for (const key of ['reason', 'reason_id', 'code']) {
      const value = error[key];
      if (typeof value === 'string' && value) return value;
    }
  }
  return 'TTS_FIRST_AUDIO_ATTEMPT_FAILED';
}

function nearestRank(values, percentile) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return rounded(sorted[Math.ceil((percentile / 100) * sorted.length) - 1]);
}

function makeLatencyProbe(points, elapsed, measurementOrigin, onPoint) {
  let roundIndex = 0;
  const pointMap = new Map([
    ['browser.presentation_received', 'presentation_received_ms'],
    ['browser.tts_request_started', 'tts_request_started_ms'],
    ['browser.successor_capture_requested', 'successor_capture_requested_ms'],
    ['browser.successor_capture_ready', 'successor_first_ack_ms'],
    ['browser.downlink_attach_started', 'downlink_opened_ms'],
    ['browser.downlink_first_frame_received', 'downlink_first_frame_received_ms'],
    ['browser.playout_first_frame_scheduled', 'first_source_scheduled_ms'],
    ['browser.playout_ack_received', 'playout_receipt_accepted_ms'],
  ]);
  return {
    beginRound() {
      const index = roundIndex++;
      let finished = false;
      let committed = false;
      return {
        context: Object.freeze({
          schema_version: 'live-voice.latency-probe-context.v1',
          run_id: 'tts-causal-local',
          profile: 'dialogue_no_tool',
          input_case: 'tts-first-audio',
          round_index: index,
        }),
        mark(point, _identity, observation) {
          if (finished) return false;
          const target = pointMap.get(point);
          let pointElapsed = elapsed();
          if (target !== undefined && points[target] === null) {
            const observed = observation?.monotonic_ms;
            pointElapsed = rounded(typeof observed === 'number' && Number.isFinite(observed) ? Math.max(0, observed - measurementOrigin()) : elapsed());
            points[target] = pointElapsed;
          }
          onPoint?.(point, pointElapsed);
          return true;
        },
        commit() {
          if (finished || committed) return false;
          committed = true;
          return true;
        },
        finish(outcome) {
          if (finished || !committed) return null;
          finished = true;
          return Object.freeze({ round_index: index, terminal_outcome: outcome, marks: [] });
        },
        abandon() {
          finished = true;
        },
      };
    },
    async exportBatch() {},
  };
}

function makeAudioEnvironment(points, elapsed, timing) {
  const document = new FakeEventTarget();
  document.visibilityState = 'visible';
  const mediaDevices = new FakeEventTarget();
  let trackIndex = 0;
  mediaDevices.getUserMedia = async () => {
    const track = new FakeTrack(`tts-benchmark-track-${++trackIndex}`);
    return {
      getAudioTracks: () => [track],
      getTracks: () => [track],
    };
  };
  mediaDevices.enumerateDevices = async () => [{ kind: 'audioinput' }];
  let captureIndex = 0;
  const environment = {
    isSecureContext: true,
    document,
    mediaDevices,
    permissions: null,
    createAudioContext: () =>
      new FakeAudioContext(
        () => {
          if (points.first_source_scheduled_ms === null) {
            points.first_source_scheduled_ms = rounded(elapsed());
          }
        },
        timing.schedulePlayout,
        timing.playoutDurationMs,
      ),
    createAudioWorkletNode: (_context, _name, options) => {
      const node = new FakeAudioNode();
      node.captureGeneration = options.processorOptions.captureGeneration;
      let onmessage = null;
      node.port = { close() {} };
      Object.defineProperty(node.port, 'onmessage', {
        get: () => onmessage,
        set: handler => {
          onmessage = handler;
          if (typeof handler !== 'function') return;
          setImmediate(() => {
            handler({
              data: {
                kind: 'frame',
                capture_generation: node.captureGeneration,
                seq: 0,
                sample_rate_hz: 48_000,
                sample_cursor: 0,
                context_time_s: 0,
                samples: new Float32Array(960).fill(0.125),
              },
            });
          });
        },
      });
      node.onprocessorerror = null;
      return node;
    },
    createId: () => `tts-benchmark-capture-${++captureIndex}`,
    outputDeviceSelection: false,
  };
  return environment;
}

class BenchmarkMediaSocket {
  constructor({ ackDelayMs, points, elapsed, scheduleAck }) {
    this.ackDelayMs = ackDelayMs;
    this.points = points;
    this.elapsed = elapsed;
    this.scheduleAck = scheduleAck;
    this.readyState = 0;
    this.bufferedAmount = 0;
    this.protocol = '';
    this.binaryType = 'blob';
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.onclose = null;
    this.binding = null;
  }

  send(value) {
    if (typeof value === 'string') {
      const control = JSON.parse(value);
      if (control.type === 'media.auth') {
        this.binding = control.binding;
        return;
      }
      if (this.binding?.direction === 'uplink' && control.type === 'media.detach') {
        queueMicrotask(() => this.onmessage?.({ data: value }));
        return;
      }
      if (this.binding?.direction === 'downlink' && control.type === 'media.ack') {
        queueMicrotask(() => {
          this.onmessage?.({
            data: serializeMediaControl({
              type: 'media.detach',
              lease_id: this.binding.lease_id,
              generation: this.binding.generation.value,
              reason_id: 'MEDIA_LOCAL_CLOSE',
              through_seq: control.through_seq,
              business_cancel_count_delta: 0,
            }),
          });
        });
      }
      return;
    }
    if (this.binding?.direction !== 'uplink') return;
    const throughSeq = decodeAudioFrame(this.binding, value).seq;
    const successor = this.binding.generation.id === 'tts-benchmark-capture-2';
    const delay = successor ? this.ackDelayMs : 0;
    this.scheduleAck(delay, () => {
      if (this.readyState !== 1) return;
      if (successor && this.points.successor_first_ack_ms === null) {
        this.points.successor_first_ack_ms = rounded(this.elapsed());
      }
      this.onmessage?.({
        data: serializeMediaControl({
          type: 'media.ack',
          lease_id: this.binding.lease_id,
          generation: this.binding.generation.value,
          through_seq: throughSeq,
        }),
      });
      if (!successor && throughSeq === 0) {
        this.onmessage?.({
          data: serializeMediaControl({
            type: 'media.speech_start',
            capability_version: 'media.end_of_turn.v1',
            lease_id: this.binding.lease_id,
            generation: this.binding.generation.value,
            detector: 'server_vad',
            provider_start_ms: 0,
            timing_basis: 'provider_time',
            timing_provenance: 'adapter_derived',
            create_response: false,
            interrupt_response: false,
            business_cancel_count_delta: 0,
          }),
        });
        this.onmessage?.({
          data: serializeMediaControl({
            type: 'media.end_of_turn',
            capability_version: 'media.end_of_turn.v1',
            lease_id: this.binding.lease_id,
            generation: this.binding.generation.value,
            detector: 'server_vad',
            speech_started_observed: true,
            provider_start_ms: 0,
            provider_end_ms: 20,
            timing_basis: 'provider_time',
            timing_provenance: 'adapter_derived',
            create_response: false,
            interrupt_response: false,
            business_cancel_count_delta: 0,
          }),
        });
      }
    });
  }

  open() {
    this.protocol = 'live-voice.media.v1';
    this.readyState = 1;
    this.onopen?.({});
    const binding = this.binding;
    if (binding === null) fail('TTS_FIRST_AUDIO_SOCKET_BINDING_MISSING');
    this.onmessage?.({
      data: serializeMediaControl({ type: 'media.attach', binding }),
    });
    if (binding.direction === 'downlink') {
      queueMicrotask(() => {
        if (this.readyState !== 1) return;
        this.onmessage?.({
          data: encodeAudioFrame(binding, {
            seq: 0,
            sample_cursor: 0,
            samples: new Float32Array(960).fill(0.125),
          }),
        });
      });
    }
  }

  close() {
    this.readyState = 3;
  }
}

function defaultTiming() {
  return Object.freeze({
    now: () => performance.now(),
    scheduleAck: (delayMs, callback) => setTimeout(callback, delayMs),
    schedulePlayout: (_delayMs, callback) => queueMicrotask(callback),
    playoutDurationMs: 0,
    onPoint: null,
  });
}

async function runAttempt(ackDelayMs, attemptIndex, timing, identity) {
  let measurementOrigin = null;
  const elapsed = () => (measurementOrigin === null ? 0 : Math.max(0, timing.now() - measurementOrigin));
  const points = {
    presentation_received_ms: null,
    tts_request_started_ms: null,
    tts_descriptor_ready_ms: null,
    successor_capture_requested_ms: null,
    successor_first_ack_ms: null,
    downlink_opened_ms: null,
    downlink_first_frame_received_ms: null,
    first_source_scheduled_ms: null,
    playout_receipt_accepted_ms: null,
  };
  const response = Object.freeze({
    interaction_id: identity.interaction_id,
    response_id: identity.response_id,
    response_generation: identity.response_generation,
  });
  const downlink = downlinkBinding(response, identity);
  const environment = makeAudioEnvironment(points, elapsed, timing);
  const latencyProbe = makeLatencyProbe(points, elapsed, () => measurementOrigin ?? timing.now(), timing.onPoint);
  let activationCount = 0;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    latency_probe: latencyProbe,
    latency_monotonic_ms: timing.now,
    audio_environment: environment,
    socket_factory: () => {
      const socket = new BenchmarkMediaSocket({ ackDelayMs, points, elapsed, scheduleAck: timing.scheduleAck });
      queueMicrotask(() => socket.open());
      return socket;
    },
    request: async (method, params) => {
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        activationCount += 1;
        const binding = bindingForCapture(params, activationCount);
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: `tts-benchmark-subject-${activationCount}`,
          endpoint_path: '/ws/live-voice/media',
          media_ticket: `${String(activationCount).padStart(32, 'U')}VVVVVVVVVVV`,
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn:
            activationCount === 1
              ? {
                  status: 'active',
                  capability_version: 'media.end_of_turn.v1',
                  detector: 'server_vad',
                  create_response: false,
                  interrupt_response: false,
                }
              : MANUAL_EOT_FALLBACK,
          binding,
          privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
        };
      }
      if (method === 'live_voice.speech.recognize_batch') {
        return {
          contract_version: 'live-voice.contract.v2',
          request_id: params.request_id,
          operation_id: params.operation_id,
          ok: true,
          error: null,
          result: {
            operation: 'speech.recognize.batch',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation,
              seq: 0,
              kind: 'final',
              commits_turn: false,
              hypothesis: {
                alternatives: [{ raw_text: 'benchmark input', display_text: 'benchmark input', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'tts-benchmark-provider',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'stt-benchmark',
            },
            voice_commit_receipt: 'tts-benchmark-voice-receipt',
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
        measurementOrigin ??= timing.now();
        points.tts_request_started_ms = 0;
        points.tts_descriptor_ready_ms = rounded(elapsed());
        return {
          contract_version: 'live-voice.contract.v2',
          request_id: params.request_id,
          operation_id: params.operation_id,
          ok: true,
          error: null,
          result: {
            operation: 'speech.synthesize.batch',
            response: params.response,
            unit_id: params.unit_id,
            audio: {
              format: 'pcm_f32_mono_20ms',
              sample_rate_hz: 48_000,
              channel_count: 1,
              frame_count: 1,
              delivery: 'dedicated_media_downlink',
              endpoint_path: '/ws/live-voice/media',
              media_ticket: 'D'.repeat(43),
              subprotocol: 'live-voice.media.v1',
              ticket_ttl_ms: 30_000,
              binding: downlink,
              max_pending_frames: 8,
              max_pending_bytes: 131_072,
              streaming: false,
              degradation_reason: null,
            },
            provider: {
              provider_id: 'tts-benchmark-provider',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-benchmark',
              voice: 'tts-benchmark-voice',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD) {
        points.playout_receipt_accepted_ms = rounded(elapsed());
        return {
          status: 'media_playout_acknowledged',
          reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
          receipt_id: `tts-benchmark-receipt-${ackDelayMs}-${attemptIndex}`,
          duplex_media_observed: true,
          ...params,
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      if (
        method.startsWith('live_voice.composition.p2') ||
        method.startsWith('live_voice.composition.p3') ||
        method.startsWith('live_voice.task.') ||
        method.startsWith('agent.') ||
        method.startsWith('tool.') ||
        method.startsWith('history.')
      ) {
        fail('TTS_FIRST_AUDIO_FORBIDDEN_EFFECT');
      }
      fail('TTS_FIRST_AUDIO_UNEXPECTED_METHOD');
    },
  });

  let outcome = 'unknown';
  let reason = null;
  try {
    await owner.startCapture({
      session_id: identity.session_id,
      interaction_id: response.interaction_id,
      correlation_id: identity.correlation_id,
      activation_id: identity.activation_id,
      activation_generation: 1,
      locale: 'en-US',
    });
    await owner.stopAndRecognize();
    const context = owner.prepareUnifiedSubmitLatency(identity.turn_id);
    if (context === null || !owner.bindUnifiedSubmitLatency(response, null)) {
      fail('TTS_FIRST_AUDIO_RESPONSE_BINDING_FAILED');
    }
    points.presentation_received_ms = 0;
    if (!owner.observeForegroundPresentationLatency(response, null)) {
      fail('TTS_FIRST_AUDIO_PRESENTATION_BINDING_FAILED');
    }
    await owner.playAgentText({
      response,
      unit_id: identity.unit_id,
      text: 'Content-free deterministic benchmark response.',
    });
    const terminal = owner.status();
    if (terminal.status === 'recognized' && terminal.reason !== null) {
      outcome = 'degraded_interruption';
      reason = terminal.reason;
    } else {
      outcome = 'completed';
    }
  } catch (error) {
    outcome = 'failed';
    reason = stableReason(error);
  } finally {
    try {
      await owner.close();
    } catch {
      if (outcome === 'completed') {
        outcome = 'unknown';
        reason = 'TTS_FIRST_AUDIO_CLEANUP_FAILED';
      }
    }
  }
  return Object.freeze({
    attempt: attemptIndex,
    outcome,
    reason,
    interaction_id: identity.interaction_id,
    response_id: identity.response_id,
    unit_id: identity.unit_id,
    ...points,
  });
}

function validateRunInput(input) {
  const delays = Array.isArray(input?.successorAckDelaysMs) ? [...input.successorAckDelaysMs] : [...SUCCESSOR_ACK_DELAYS_MS];
  const timing = input?.timing ?? defaultTiming();
  const identity =
    input?.identity ??
    Object.freeze({
      session_id: 'tts-benchmark-session',
      correlation_id: 'tts-benchmark-correlation',
      interaction_id: 'tts-benchmark-interaction',
      activation_id: 'tts-benchmark-activation',
      turn_id: 'tts-benchmark-turn',
      response_id: 'tts-benchmark-response',
      response_generation: 1,
      unit_id: 'tts-benchmark-unit',
    });
  if (
    !RUN_ID.test(input?.runId ?? '') ||
    !GIT_COMMIT.test(input?.gitCommit ?? '') ||
    canonicalInteger(input?.samples, 1, 30) === null ||
    delays.length === 0 ||
    delays.some(delay => !ALLOWED_ACK_DELAYS_MS.has(delay)) ||
    new Set(delays).size !== delays.length ||
    timing === null ||
    typeof timing !== 'object' ||
    typeof timing.now !== 'function' ||
    typeof timing.scheduleAck !== 'function' ||
    typeof timing.schedulePlayout !== 'function' ||
    (timing.onPoint !== null && typeof timing.onPoint !== 'function') ||
    canonicalInteger(timing.playoutDurationMs, 0, 10_000) === null ||
    identity === null ||
    typeof identity !== 'object' ||
    !['session_id', 'correlation_id', 'interaction_id', 'activation_id', 'turn_id', 'response_id', 'unit_id'].every(
      key => typeof identity[key] === 'string' && RUN_ID.test(identity[key]),
    ) ||
    canonicalInteger(identity.response_generation, 0, 1_000_000) === null
  ) {
    fail('TTS_FIRST_AUDIO_INPUT_INVALID');
  }
  return Object.freeze({
    runId: input.runId,
    gitCommit: input.gitCommit,
    samples: input.samples,
    delays: Object.freeze(delays),
    timing: Object.freeze({ ...timing }),
    identity: Object.freeze({ ...identity }),
  });
}

export async function runTtsFirstAudioCausalBenchmark(input) {
  const config = validateRunInput(input);
  const populations = [];
  for (const delay of config.delays) {
    const attempts = [];
    for (let attempt = 0; attempt < config.samples; attempt += 1) {
      attempts.push(await runAttempt(delay, attempt, config.timing, config.identity));
    }
    populations.push(
      Object.freeze({
        successor_ack_delay_ms: delay,
        attempts: Object.freeze(attempts),
      }),
    );
  }
  const summaries = populations.map(population => {
    const successful = population.attempts.filter(attempt => ['completed', 'degraded_interruption'].includes(attempt.outcome));
    const samples = successful.map(attempt => attempt.first_source_scheduled_ms).filter(value => typeof value === 'number');
    return Object.freeze({
      successor_ack_delay_ms: population.successor_ack_delay_ms,
      attempts: population.attempts.length,
      completed: population.attempts.filter(attempt => attempt.outcome === 'completed').length,
      degraded_interruption: population.attempts.filter(attempt => attempt.outcome === 'degraded_interruption').length,
      failed: population.attempts.filter(attempt => attempt.outcome === 'failed').length,
      p50_first_source_scheduled_ms: nearestRank(samples, 50),
      p95_first_source_scheduled_ms: nearestRank(samples, 95),
    });
  });
  const zero = summaries.find(summary => summary.successor_ack_delay_ms === 0);
  const timeoutPopulation = populations.find(population => population.successor_ack_delay_ms === 1100);
  const timeoutReproduced =
    timeoutPopulation !== undefined &&
    timeoutPopulation.attempts.length === config.samples &&
    timeoutPopulation.attempts.every(
      attempt =>
        attempt.outcome === 'failed' &&
        attempt.reason === 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED' &&
        attempt.downlink_opened_ms === null &&
        attempt.first_source_scheduled_ms === null &&
        attempt.playout_receipt_accepted_ms === null,
    );
  const materialDelayedPopulation = summaries.some(summary => {
    if (![250, 750].includes(summary.successor_ack_delay_ms)) return false;
    if (summary.completed !== config.samples || zero?.p50_first_source_scheduled_ms === null) return false;
    const population = populations.find(value => value.successor_ack_delay_ms === summary.successor_ack_delay_ms);
    if (
      population === undefined ||
      !population.attempts.every(
        attempt =>
          typeof attempt.successor_first_ack_ms === 'number' &&
          typeof attempt.downlink_opened_ms === 'number' &&
          attempt.downlink_opened_ms >= attempt.successor_first_ack_ms,
      )
    ) {
      return false;
    }
    const delta = summary.p50_first_source_scheduled_ms - zero.p50_first_source_scheduled_ms;
    return delta >= 200 && delta >= zero.p50_first_source_scheduled_ms * 0.15;
  });
  const eligible = timeoutReproduced && materialDelayedPopulation;
  const candidateMode = populations.some(population =>
    population.attempts.some(
      attempt =>
        population.successor_ack_delay_ms > 0 &&
        typeof attempt.downlink_opened_ms === 'number' &&
        (attempt.successor_first_ack_ms === null || attempt.downlink_opened_ms < attempt.successor_first_ack_ms),
    ),
  )
    ? 'successor_ack_decoupled'
    : 'legacy_sequential';
  return Object.freeze({
    schema_version: SCHEMA_VERSION,
    run_id: config.runId,
    git_commit: config.gitCommit,
    source_clean: true,
    candidate_mode: candidateMode,
    samples: config.samples,
    populations: Object.freeze(populations),
    summaries: Object.freeze(summaries),
    decision: eligible ? 'SUCCESSOR_ACK_DECOUPLING_ELIGIBLE' : 'NO_MATERIAL_SUCCESSOR_ACK_GAP',
    forbidden_effects: FORBIDDEN_EFFECTS,
  });
}

export function parseTtsFirstAudioBenchmarkArgs(argv) {
  if (!Array.isArray(argv) || argv.length % 2 !== 0) fail('TTS_FIRST_AUDIO_ARGUMENT_INVALID');
  const allowed = new Set(['--output', '--git-commit', '--run-id', '--samples']);
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!allowed.has(key) || values.has(key) || typeof value !== 'string' || value === '') {
      fail('TTS_FIRST_AUDIO_ARGUMENT_INVALID');
    }
    values.set(key, value);
  }
  const output = values.get('--output');
  const gitCommit = values.get('--git-commit');
  const runId = values.get('--run-id');
  const samples = canonicalInteger(values.get('--samples'), 1, 30);
  if (
    values.size !== allowed.size ||
    typeof output !== 'string' ||
    !path.isAbsolute(output) ||
    output.includes('\n') ||
    output.includes('\r') ||
    !GIT_COMMIT.test(gitCommit ?? '') ||
    !RUN_ID.test(runId ?? '') ||
    samples === null
  ) {
    fail('TTS_FIRST_AUDIO_ARGUMENT_INVALID');
  }
  return Object.freeze({
    output,
    gitCommit,
    runId,
    samples,
    successorAckDelaysMs: SUCCESSOR_ACK_DELAYS_MS,
  });
}

export async function writeTtsFirstAudioCausalReport(output, report) {
  let handle = null;
  let created = false;
  try {
    const serialized = `${JSON.stringify(report)}\n`;
    handle = await fs.open(output, 'wx', 0o600);
    created = true;
    await handle.writeFile(serialized, 'utf8');
    await handle.close();
    handle = null;
  } catch (error) {
    if (handle !== null) await handle.close().catch(() => undefined);
    if (created) await fs.unlink(output).catch(() => undefined);
    if (error?.code === 'EEXIST') fail('TTS_FIRST_AUDIO_OUTPUT_EXISTS');
    throw error;
  }
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseTtsFirstAudioBenchmarkArgs(argv);
  const actualCommit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { encoding: 'utf8' });
  if (actualCommit !== args.gitCommit || status !== '') fail('TTS_FIRST_AUDIO_SOURCE_NOT_CLEAN');
  const report = await runTtsFirstAudioCausalBenchmark({
    runId: args.runId,
    gitCommit: args.gitCommit,
    samples: args.samples,
    successorAckDelaysMs: args.successorAckDelaysMs,
  });
  await writeTtsFirstAudioCausalReport(args.output, report);
  process.stdout.write(`${JSON.stringify({ run_id: args.runId, decision: report.decision })}\n`);
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  main().catch(() => {
    process.stderr.write('TTS_FIRST_AUDIO_BENCHMARK_FAILED\n');
    process.exitCode = 1;
  });
}

export { SCHEMA_VERSION, SUCCESSOR_ACK_DELAYS_MS };
