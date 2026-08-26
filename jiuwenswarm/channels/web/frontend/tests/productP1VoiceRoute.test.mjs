import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

import {
  PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  PRODUCT_P1_CAPTURE_MAX_DURATION_MS,
  PRODUCT_P1_EMPTY_TRANSCRIPT_REASON,
  PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
  PRODUCT_P1_MEDIA_CLOSE_METHOD,
  PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD,
  ProductP1VoiceRouteOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP1VoiceRoute.js';
import {
  decodeAudioFrame,
  encodeAudioFrame,
  serializeMediaControl,
} from '../node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs';

const captureProcessorSource = readFileSync(new URL('../src/features/live-voice/formal/adapters/liveVoiceCaptureProcessor.js', import.meta.url), 'utf8');
const productP1VoiceRouteSource = readFileSync(
  new URL('../src/features/live-voice/formal/productP1VoiceRoute.ts', import.meta.url),
  'utf8',
);
const MANUAL_EOT_FALLBACK = Object.freeze({
  status: 'fallback',
  requested_capability: 'media.end_of_turn.v1',
  reason_id: 'MEDIA_END_OF_TURN_FEATURE_OFF',
  fallback: 'manual',
  visible: true,
});

test('formal P1 forwards the configured playout startup lead to browser audio', () => {
  assert.match(productP1VoiceRouteSource, /playout_startup_lead_ms\?: number/);
  assert.match(
    productP1VoiceRouteSource,
    /new BrowserAudioIOAdapter\(\{[\s\S]*?playoutStartupLeadMs: input\.playout_startup_lead_ms/,
  );
});

function attachRealCaptureProcessor(worklet, sampleRate = 48_000) {
  let Processor = null;
  class FakeAudioWorkletProcessor {
    constructor() {
      this.port = {
        postMessage: message => worklet.port.onmessage?.({ data: message }),
      };
    }
  }
  const sandbox = {
    AudioWorkletProcessor: FakeAudioWorkletProcessor,
    Float32Array,
    Math,
    currentFrame: 0,
    sampleRate,
    registerProcessor(_name, constructor) {
      Processor = constructor;
    },
  };
  vm.runInNewContext(captureProcessorSource, sandbox, {
    filename: 'liveVoiceCaptureProcessor.js',
  });
  assert.notEqual(Processor, null);
  const processor = new Processor({
    processorOptions: {
      captureGeneration: worklet.captureGeneration,
      frameDurationMs: 20,
    },
  });
  const quantum = (value = 0.25) => [[new Float32Array(128).fill(value)]];
  return { processor, quantum, sandbox };
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

  listenerCount(type) {
    return this.listeners.get(type)?.size ?? 0;
  }
}

class FakePermissionStatus extends FakeEventTarget {
  constructor(state = 'granted') {
    super();
    this.state = state;
  }

  change(state) {
    this.state = state;
    this.emit('change');
  }
}

class FakeNode {
  connect(destination) {
    return destination;
  }
  disconnect() {}
}

class FakeAudioContext {
  sampleRate = 48_000;
  currentTime = 0;
  destination = Object.freeze({ kind: 'destination' });
  state = 'suspended';
  onstatechange = null;
  audioWorklet = { addModule: async () => undefined };
  activeSources = 0;
  peakSources = 0;
  sourceStartCount = 0;
  sourceEndCount = 0;
  onSourceEnded = null;
  deferSourceEnds = false;
  pendingSourceEnds = [];
  sinkIds = [];

  releaseSourceEnds() {
    for (const finish of this.pendingSourceEnds.splice(0)) finish();
  }

  async resume() {
    this.state = 'running';
  }
  async setSinkId(deviceId) {
    this.sinkIds.push(deviceId);
  }
  async close() {
    this.state = 'closed';
  }
  createMediaStreamSource() {
    return new FakeNode();
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
        context.activeSources += 1;
        context.sourceStartCount += 1;
        context.peakSources = Math.max(context.peakSources, context.activeSources);
        const finish = () => {
          context.activeSources -= 1;
          context.sourceEndCount += 1;
          context.onSourceEnded?.({
            sourceStartCount: context.sourceStartCount,
            sourceEndCount: context.sourceEndCount,
          });
          source.onended?.();
        };
        if (context.deferSourceEnds) context.pendingSourceEnds.push(finish);
        else queueMicrotask(finish);
      },
      stop() {
        if (context.activeSources > 0) context.activeSources -= 1;
      },
    };
    return source;
  }
}

class FakeTrack extends FakeEventTarget {
  id = 'track-1';
  kind = 'audio';
  readyState = 'live';
  muted = false;

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

class FakeSocket {
  readyState = 0;
  bufferedAmount = 0;
  protocol = '';
  binaryType = 'blob';
  onopen = null;
  onmessage = null;
  onerror = null;
  onclose = null;
  sent = [];
  binding = null;
  closeOnFirstBinary = false;
  acknowledgeBinary = true;
  binarySendCount = 0;
  deferDetachReceipt = false;
  pendingDetachReceipt = null;

  send(value) {
    this.sent.push(value);
    if (typeof value === 'string') {
      let control = null;
      try {
        control = JSON.parse(value);
      } catch {
        control = null;
      }
      if (control?.type === 'media.detach') {
        this.pendingDetachReceipt = value;
        if (!this.deferDetachReceipt) {
          queueMicrotask(() => this.releaseDetachReceipt());
        }
      }
    }
    if (typeof value !== 'string' && this.binding !== null && this.acknowledgeBinary) {
      const throughSeq = this.binarySendCount;
      this.binarySendCount += 1;
      queueMicrotask(() =>
        this.onmessage?.({
          data: JSON.stringify({
            type: 'media.ack',
            contract_version: 'live-voice.media.v1',
            lease_id: this.binding.lease_id,
            generation: this.binding.generation.value,
            through_seq: throughSeq,
          }),
        })
      );
      if (this.closeOnFirstBinary) {
        this.closeOnFirstBinary = false;
        queueMicrotask(() => {
          this.readyState = 3;
          this.onclose?.({});
        });
      }
    }
  }
  close() {
    this.readyState = 3;
  }
  releaseDetachReceipt(overrides = {}) {
    if (this.pendingDetachReceipt === null) return;
    const control = { ...JSON.parse(this.pendingDetachReceipt), ...overrides };
    this.pendingDetachReceipt = null;
    this.onmessage?.({ data: JSON.stringify(control) });
  }
  open(binding) {
    this.binding = binding;
    this.binarySendCount = 0;
    this.protocol = 'live-voice.media.v1';
    this.readyState = 1;
    this.onopen?.({});
    this.onmessage?.({
      data: JSON.stringify({
        type: 'media.attach',
        contract_version: 'live-voice.media.v1',
        binding,
      }),
    });
  }
}

function audioEnvironment(createId = () => 'capture-1') {
  const document = new FakeEventTarget();
  document.visibilityState = 'visible';
  const mediaDevices = new FakeEventTarget();
  mediaDevices.constraints = [];
  mediaDevices.getUserMedia = async constraints => {
    mediaDevices.constraints.push(constraints);
    const track = new FakeTrack();
    track.muted = environment.initialTrackMuted;
    environment.track = track;
    return {
      getAudioTracks: () => [track],
      getTracks: () => [track],
    };
  };
  mediaDevices.enumerateDevices = async () => environment.devices;
  const environment = {
    isSecureContext: true,
    document,
    mediaDevices,
    permissions: null,
    createAudioContext: () => {
      const context = new FakeAudioContext();
      context.deferSourceEnds = environment.deferSourceEnds;
      environment.contexts.push(context);
      return context;
    },
    createAudioWorkletNode: (_context, _name, options) => {
      const node = new FakeNode();
      let onmessage = null;
      node.port = { close() {} };
      Object.defineProperty(node.port, 'onmessage', {
        get: () => onmessage,
        set: handler => {
          onmessage = handler;
          const samples = environment.nextWorkletFirstFrameSamples;
          if (typeof handler !== 'function' || samples === null) return;
          environment.nextWorkletFirstFrameSamples = null;
          environment.autoFirstFrameScheduled += 1;
          setTimeout(() => {
            environment.autoFirstFrameDelivered += 1;
            handler({
              data: {
                kind: 'frame',
                capture_generation: node.captureGeneration,
                seq: 0,
                sample_rate_hz: 48_000,
                sample_cursor: 0,
                context_time_s: 0,
                samples,
              },
            });
          }, 250);
        },
      });
      node.onprocessorerror = null;
      node.captureGeneration = options.processorOptions.captureGeneration;
      environment.worklet = node;
      return node;
    },
    createId,
    outputDeviceSelection: false,
    worklet: null,
    track: null,
    contexts: [],
    devices: [{ kind: 'audioinput' }],
    initialTrackMuted: false,
    deferSourceEnds: false,
    nextWorkletFirstFrameSamples: null,
    autoFirstFrameScheduled: 0,
    autoFirstFrameDelivered: 0,
  };
  return environment;
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolveValue, rejectValue) => {
    resolve = resolveValue;
    reject = rejectValue;
  });
  return { promise, resolve, reject };
}

async function outcomeWithin(operation, timeoutMessage) {
  let timeoutHandle = null;
  try {
    return await Promise.race([
      operation.then(
        () => null,
        error => error
      ),
      new Promise(resolve => {
        timeoutHandle = setTimeout(() => resolve(timeoutMessage), 100);
      }),
    ]);
  } finally {
    if (timeoutHandle !== null) clearTimeout(timeoutHandle);
  }
}

async function startCaptureWithFirstFrame(owner, environment, input, overrides = {}) {
  const starting = owner.startCapture(input);
  for (let turn = 0; turn < 100 && typeof environment.worklet?.port.onmessage !== 'function'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(typeof environment.worklet?.port.onmessage, 'function');
  // Installing the handler precedes the adapter's atomic session handoff.
  // Wait one task so the frame cannot race that assignment in this fake.
  await new Promise(resolve => setImmediate(resolve));
  environment.worklet.port.onmessage({
    data: {
      kind: 'frame',
      capture_generation: environment.worklet.captureGeneration,
      seq: 0,
      sample_rate_hz: 48_000,
      sample_cursor: 0,
      context_time_s: 0,
      samples: new Float32Array(960).fill(0.25),
      ...overrides,
    },
  });
  await starting;
}

async function sendFirstFrameToNextWorklet(environment, priorWorklet, overrides = {}) {
  for (let turn = 0; turn < 100 && (environment.worklet === priorWorklet || typeof environment.worklet?.port.onmessage !== 'function'); turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.notEqual(environment.worklet, priorWorklet);
  assert.equal(typeof environment.worklet?.port.onmessage, 'function');
  await new Promise(resolve => setImmediate(resolve));
  environment.worklet.port.onmessage({
    data: {
      kind: 'frame',
      capture_generation: environment.worklet.captureGeneration,
      seq: 0,
      sample_rate_hz: 48_000,
      sample_cursor: 0,
      context_time_s: 0,
      samples: new Float32Array(960).fill(0.25),
      ...overrides,
    },
  });
}

function sendNextFrameFromCurrentWorklet(environment, seq = 1) {
  const worklet = environment.worklet;
  const handler = worklet?.port.onmessage;
  assert.equal(typeof handler, 'function');
  handler({
    data: {
      kind: 'frame',
      capture_generation: worklet.captureGeneration,
      seq,
      sample_rate_hz: 48_000,
      sample_cursor: seq * 960,
      context_time_s: seq * 0.02,
      samples: new Float32Array(960).fill(0.25),
    },
  });
}

async function sendCaptureToDurationBoundary(
  environment,
  samples,
  { exceed = false, extraFrames = 0, afterBoundary = null } = {},
) {
  const worklet = environment.worklet;
  const handler = worklet?.port.onmessage;
  assert.equal(typeof handler, 'function');
  const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
  for (let seq = 1; seq < frameCount; seq += 1) {
    handler({
      data: {
        kind: 'frame',
        capture_generation: worklet.captureGeneration,
        seq,
        sample_rate_hz: 48_000,
        sample_cursor: seq * 960,
        context_time_s: seq * 0.02,
        samples,
      },
    });
    if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
  }
  afterBoundary?.(worklet);
  if (exceed) {
    for (let offset = 0; offset <= extraFrames; offset += 1) {
      handler({
        data: {
          kind: 'frame',
          capture_generation: worklet.captureGeneration,
          seq: frameCount + offset,
          sample_rate_hz: 48_000,
          sample_cursor: (frameCount + offset) * 960,
          context_time_s: (frameCount + offset) * 0.02,
          samples,
        },
      });
    }
  }
  return worklet;
}

function wavBase64(sampleRate = 48_000, sampleCount = 960) {
  const bytes = new Uint8Array(44 + sampleCount * 2);
  const view = new DataView(bytes.buffer);
  const ascii = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  ascii(0, 'RIFF');
  view.setUint32(4, bytes.length - 8, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, 'data');
  view.setUint32(40, sampleCount * 2, true);
  return Buffer.from(bytes).toString('base64');
}

function serverBinding() {
  return {
    lease_id: 'media-lease-1',
    authority_evidence_id: 'media-authority-1',
    connection_id: 'connection-1',
    connection_epoch: 0,
    session_id: 'session-1',
    media_session_id: 'media-session-1',
    interaction_id: 'interaction-1',
    track_id: 'track-1',
    correlation_id: 'correlation-1',
    direction: 'uplink',
    generation: { kind: 'capture', id: 'capture-1', value: 1 },
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

function streamingMediaActivation(binding, degradation = null, endOfTurn = MANUAL_EOT_FALLBACK) {
  return {
    status: 'active',
    reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
    subject_id: 'media-subject-1',
    endpoint_path: '/ws/live-voice/media',
    media_ticket: 'P'.repeat(43),
    subprotocol: 'live-voice.media.v1',
    ticket_ttl_ms: 30_000,
    streaming_recognition: degradation === null,
    streaming_degradation: degradation,
    end_of_turn: endOfTurn,
    binding,
    privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
  };
}

function streamingRecognitionResult(params, text = 'streaming text') {
  return {
    status: 'completed',
    operation: 'speech.recognize.stream',
    capture: {
      capture_id: params.capture_id,
      capture_generation: params.capture_generation,
      track_id: params.track_id,
      final: true,
    },
    final_text: text,
    raw_text: text,
    commits_turn: false,
    voice_commit_receipt: 'streaming-voice-receipt-1',
    provider: {
      provider_id: 'openai-streaming-speech',
      implementation_class: 'formal',
      fallback_from: null,
    },
    degradation: null,
  };
}

function streamingFallbackResult(params, fallbackTier, reasonId) {
  const routeAborted = reasonId === 'STREAMING_SPEECH_ROUTE_ABORTED';
  return {
    status: 'fallback',
    operation: 'speech.recognize.stream',
    capture: {
      capture_id: params.capture_id,
      capture_generation: params.capture_generation,
      track_id: params.track_id,
      final: true,
    },
    fallback_tier: fallbackTier,
    reason_id: reasonId,
    visible: true,
    x_obs_event: routeAborted ? 'degradation.activated' : 'failure.observed',
    x_obs_metric: routeAborted ? 'live_voice.degradation_total' : 'live_voice.failure_total',
  };
}

function batchRecognitionResult(params, text = 'batch text') {
  return {
    contract_version: 'live-voice.contract.v2',
    request_id: params.request_id,
    operation_id: params.operation_id,
    ok: true,
    error: null,
    result: {
      operation: 'speech.recognize.batch',
      voice_commit_receipt: 'batch-voice-receipt-1',
      capture: params.capture,
      event: {
        session_id: params.capture.capture_id,
        generation: params.capture.capture_generation,
        seq: 0,
        kind: 'final',
        commits_turn: false,
        hypothesis: {
          alternatives: [{ raw_text: text, display_text: text, confidence: null }],
          selected_index: 0,
        },
      },
      provider: {
        provider_id: 'provider-test',
        implementation_class: 'formal',
        fallback_from: null,
        model: 'stt-test',
      },
    },
  };
}

test('formal P1 binds media activation to the exact product P2 activation', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  environment.outputDeviceSelection = true;
  environment.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1' },
    { kind: 'audiooutput', deviceId: 'private-output-1' },
  ];
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: (url, protocols) => {
      assert.equal(url, 'wss://voice.example.test/ws/live-voice/media');
      assert.deepEqual(protocols, ['live-voice.media.v1']);
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      if (method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD) {
        return {
          status: 'media_playout_acknowledged',
          reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
          receipt_id: 'media-playout-receipt-1',
          duplex_media_observed: false,
          ...params,
        };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: {
          raw_audio_persisted: false,
          raw_audio_logged: false,
          memory_only: true,
        },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
    device_selection: {
      selection_generation: 2,
      input_device_id: 'private-input-1',
      output_device_id: 'private-output-1',
    },
  });

  assert.equal(owner.status().status, 'capturing');
  assert.deepEqual(environment.contexts[0].sinkIds, ['private-output-1']);
  assert.equal(environment.mediaDevices.constraints[0].audio.deviceId.exact, 'private-input-1');
  assert.deepEqual(calls, [
    [
      PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
      {
        session_id: 'session-1',
        interaction_id: 'interaction-1',
        correlation_id: 'correlation-1',
        activation_id: 'activation-1',
        activation_generation: 7,
        capture_id: 'capture-1',
        capture_generation: 1,
        track_id: 'track-1',
        sample_rate_hz: 48_000,
        locale: 'zh-CN',
        end_of_turn_capability: 'media.end_of_turn.v1',
      },
    ],
  ]);
  await owner.close();
  assert.equal(owner.status().status, 'closed');
  assert.equal(calls[1][0], PRODUCT_P1_MEDIA_CLOSE_METHOD);
});

test('formal P1 requires one real AIO frame before publishing capture readiness', async () => {
  const calls = [];
  const statuses = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    on_status: status => statuses.push(status),
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    }),
    error => error?.reason === 'AUDIO_CAPTURE_NO_FRAMES'
  );

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_CAPTURE_NO_FRAMES' });
  assert.equal(statuses.includes('capturing'), false);
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 remains starting until a delayed first frame is accepted', async () => {
  const statuses = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    on_status: status => statuses.push(status),
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  for (let turn = 0; turn < 100 && typeof environment.worklet?.port.onmessage !== 'function'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(owner.status(), { status: 'starting', reason: null });
  assert.equal(statuses.includes('capturing'), false);
  environment.worklet.port.onmessage({
    data: {
      kind: 'frame',
      capture_generation: environment.worklet.captureGeneration,
      seq: 0,
      sample_rate_hz: 48_000,
      sample_cursor: 0,
      context_time_s: 0,
      samples: new Float32Array(960),
    },
  });
  await starting;
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  assert.equal(statuses.filter(status => status === 'capturing').length, 1);
  await owner.close();
});

test('formal P1 drains capture accumulated before media attach through bounded ACK backpressure', async () => {
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  let releaseActivation;
  const activationGate = new Promise(resolve => {
    releaseActivation = resolve;
  });
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      await activationGate;
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  for (let turn = 0; turn < 100 && typeof environment.worklet?.port.onmessage !== 'function'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(typeof environment.worklet?.port.onmessage, 'function');
  await new Promise(resolve => setImmediate(resolve));
  for (let seq = 0; seq < 12; seq += 1) {
    environment.worklet.port.onmessage({
      data: {
        kind: 'frame',
        capture_generation: environment.worklet.captureGeneration,
        seq,
        sample_rate_hz: 48_000,
        sample_cursor: seq * 960,
        context_time_s: seq * 0.02,
        samples: new Float32Array(960).fill(0.25),
      },
    });
  }
  releaseActivation();

  await starting;
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  const binaries = socket.sent.filter(value => typeof value !== 'string');
  assert.equal(binaries.length, 12);
  assert.deepEqual(
    binaries.map(value => decodeAudioFrame(binding, value).seq),
    Array.from({ length: 12 }, (_value, seq) => seq)
  );
  await owner.close();
});
test('formal P1 rejects a media leaf that closes in the first-frame readiness window', async () => {
  const calls = [];
  const statuses = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  socket.closeOnFirstBinary = true;
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    on_status: status => statuses.push(status),
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await assert.rejects(
    startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    }),
    error => error?.reason === 'AUDIO_CAPTURE_MEDIA_ROUTE_CLOSED'
  );

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_CAPTURE_MEDIA_ROUTE_CLOSED' });
  assert.equal(statuses.includes('capturing'), false);
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 rejects a first frame that the Gateway never acknowledges', async () => {
  const calls = [];
  const statuses = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  socket.acknowledgeBinary = false;
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    on_status: status => statuses.push(status),
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await assert.rejects(
    startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    }),
    error => error?.reason === 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED'
  );

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED' });
  assert.equal(statuses.includes('capturing'), false);
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 rejects an initially muted input before media or Speech effects', async () => {
  const calls = [];
  const environment = audioEnvironment();
  environment.initialTrackMuted = true;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      throw new Error('socket must not be allocated');
    },
    request: async method => {
      calls.push(method);
      throw new Error('request must not be called');
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    }),
    error => error?.reason === 'AUDIO_INPUT_MUTED'
  );

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_INPUT_MUTED' });
  assert.deepEqual(calls, []);
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 latches a starting-window track end and revokes issued media authority', async () => {
  const calls = [];
  const binding = serverBinding();
  const environment = audioEnvironment();
  let socketAllocations = 0;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      socketAllocations += 1;
      throw new Error('socket must not be allocated');
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      environment.track.readyState = 'ended';
      environment.track.emit('ended');
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    }),
    error => error?.reason === 'AUDIO_TRACK_ENDED'
  );

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_TRACK_ENDED' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(socketAllocations, 0);
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 releases local audio while media activation remains pending, then compensates authority', async () => {
  const calls = [];
  const binding = serverBinding();
  const environment = audioEnvironment();
  let socketAllocations = 0;
  let resolveActivation;
  let markActivationRequested;
  const activationGate = new Promise(resolve => {
    resolveActivation = resolve;
  });
  const activationRequested = new Promise(resolve => {
    markActivationRequested = resolve;
  });
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      socketAllocations += 1;
      throw new Error('socket must not be allocated');
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      markActivationRequested();
      return activationGate;
    },
  });

  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  await activationRequested;
  environment.track.muted = true;
  environment.track.emit('mute');
  assert.deepEqual(owner.status(), { status: 'cleanup_pending', reason: 'AUDIO_INPUT_MUTED' });
  await assert.rejects(owner.stopAndRecognize(), /capture is not active/);
  for (let turn = 0; turn < 100 && !environment.contexts.every(context => context.state === 'closed'); turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD]
  );
  assert.equal(socketAllocations, 0);

  resolveActivation({
    status: 'active',
    reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
    subject_id: 'media-subject-1',
    endpoint_path: '/ws/live-voice/media',
    media_ticket: 'P'.repeat(43),
    subprotocol: 'live-voice.media.v1',
    ticket_ttl_ms: 30_000,
    end_of_turn: MANUAL_EOT_FALLBACK,
    binding,
    privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
  });
  await assert.rejects(starting, error => error?.reason === 'AUDIO_INPUT_MUTED');
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_INPUT_MUTED' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    calls.some(([method]) => method === 'live_voice.speech.recognize_batch'),
    false
  );
  assert.equal(socketAllocations, 0);
});

test('formal P1 close waits for pending activation registration and revokes the late exact authority', async () => {
  const calls = [];
  const binding = serverBinding();
  const environment = audioEnvironment();
  let socketAllocations = 0;
  let resolveActivation;
  let markActivationRequested;
  const activationGate = new Promise(resolve => {
    resolveActivation = resolve;
  });
  const activationRequested = new Promise(resolve => {
    markActivationRequested = resolve;
  });
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      socketAllocations += 1;
      throw new Error('socket must not be allocated');
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      markActivationRequested();
      return activationGate;
    },
  });

  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  await activationRequested;
  let closeSettled = false;
  const closing = owner.close().then(() => {
    closeSettled = true;
  });
  for (let turn = 0; turn < 100 && !environment.contexts.every(context => context.state === 'closed'); turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.deepEqual(owner.status(), {
    status: 'cleanup_pending',
    reason: 'FORMAL_P1_CLEANUP_IN_PROGRESS',
  });
  assert.equal(closeSettled, false);
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.equal(socketAllocations, 0);

  resolveActivation({
    status: 'active',
    reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
    subject_id: 'media-subject-late',
    endpoint_path: '/ws/live-voice/media',
    media_ticket: 'P'.repeat(43),
    subprotocol: 'live-voice.media.v1',
    ticket_ttl_ms: 30_000,
    end_of_turn: MANUAL_EOT_FALLBACK,
    binding,
    privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
  });
  const [startResult, closeResult] = await Promise.allSettled([starting, closing]);
  assert.equal(startResult.status, 'rejected');
  assert.equal(closeResult.status, 'fulfilled');
  assert.deepEqual(owner.status(), { status: 'closed', reason: null });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(calls[1][1].subject_id, 'media-subject-late');
  assert.equal(socketAllocations, 0);
});

test('formal P1 runtime mute closes exact capture and fences stale Worklet frames', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  const staleFrame = environment.worklet.port.onmessage;
  environment.track.muted = true;
  environment.track.emit('mute');
  assert.deepEqual(owner.status(), { status: 'cleanup_pending', reason: 'AUDIO_INPUT_MUTED' });
  await assert.rejects(owner.stopAndRecognize(), /capture is not active/);
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_INPUT_MUTED' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    calls.some(([method]) => method === 'live_voice.speech.recognize_batch'),
    false
  );
  const failed = owner.status();
  staleFrame({
    data: {
      kind: 'frame',
      capture_generation: 1,
      seq: 1,
      sample_rate_hz: 48_000,
      sample_cursor: 960,
      context_time_s: 0.02,
      samples: new Float32Array(960),
    },
  });
  await Promise.resolve();
  assert.deepEqual(owner.status(), failed);
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 unexpected track end closes exact capture and fences stale Worklet frames', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  const staleFrame = environment.worklet.port.onmessage;
  environment.track.readyState = 'ended';
  environment.track.emit('ended');
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_TRACK_ENDED' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  const failed = owner.status();
  staleFrame({
    data: {
      kind: 'frame',
      capture_generation: 1,
      seq: 1,
      sample_rate_hz: 48_000,
      sample_cursor: 960,
      context_time_s: 0.02,
      samples: new Float32Array(960),
    },
  });
  await Promise.resolve();
  assert.deepEqual(owner.status(), failed);
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 AudioContext loss closes exact capture without Speech or business effects', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  const captureContext = environment.contexts.at(-1);
  captureContext.state = 'suspended';
  captureContext.onstatechange?.({});
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_CONTEXT_NOT_RUNNING' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 fails the current capture when every browser audio input disappears', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  environment.devices = [];
  environment.mediaDevices.emit('devicechange');
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_INPUT_UNAVAILABLE' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    calls.some(([method]) => method === 'live_voice.speech.recognize_batch'),
    false
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 fails closed when its exact input disappears while another microphone remains', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  environment.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1' },
    { kind: 'audioinput', deviceId: 'private-input-2' },
  ];
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    device_selection: {
      selection_generation: 2,
      input_device_id: 'private-input-1',
    },
  });
  environment.devices = [{ kind: 'audioinput', deviceId: 'private-input-2' }];
  environment.mediaDevices.emit('devicechange');
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_INPUT_SELECTION_LOST' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(calls.some(([method]) => method === 'live_voice.speech.recognize_batch'), false);
  assert.equal(environment.track.readyState, 'ended');
});

test('formal P1 fails closed when its exact output disappears and never switches to an alternate', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  environment.outputDeviceSelection = true;
  environment.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1' },
    { kind: 'audiooutput', deviceId: 'private-output-1' },
    { kind: 'audiooutput', deviceId: 'private-output-2' },
  ];
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    device_selection: {
      selection_generation: 2,
      input_device_id: 'private-input-1',
      output_device_id: 'private-output-1',
    },
  });
  environment.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1' },
    { kind: 'audiooutput', deviceId: 'private-output-2' },
  ];
  environment.mediaDevices.emit('devicechange');
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_OUTPUT_SELECTION_LOST' });
  assert.deepEqual(environment.contexts[0].sinkIds, ['private-output-1']);
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(calls.some(([method]) => method === 'live_voice.speech.recognize_batch'), false);
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(environment.mediaDevices.listenerCount('devicechange'), 0);
});

test('formal P1 preserves exact output loss while microphone startup is still pending', async () => {
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const mediaGrant = deferred();
  const track = new FakeTrack();
  environment.outputDeviceSelection = true;
  environment.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1' },
    { kind: 'audiooutput', deviceId: 'private-output-1' },
    { kind: 'audiooutput', deviceId: 'private-output-2' },
  ];
  environment.mediaDevices.getUserMedia = async constraints => {
    environment.mediaDevices.constraints.push(constraints);
    const stream = await mediaGrant.promise;
    environment.track = track;
    return stream;
  };
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async () => {
      throw new Error('remote activation must not begin');
    },
  });

  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    device_selection: {
      selection_generation: 2,
      input_device_id: 'private-input-1',
      output_device_id: 'private-output-1',
    },
  });
  for (let turn = 0; turn < 100 && environment.mediaDevices.constraints.length === 0; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(environment.mediaDevices.constraints.length, 1);
  environment.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1' },
    { kind: 'audiooutput', deviceId: 'private-output-2' },
  ];
  environment.mediaDevices.emit('devicechange');
  await new Promise(resolve => setImmediate(resolve));
  mediaGrant.resolve({ getAudioTracks: () => [track], getTracks: () => [track] });

  const error = await starting.then(
    () => null,
    failure => failure
  );
  assert.equal(error?.reason, 'AUDIO_OUTPUT_SELECTION_LOST');
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_OUTPUT_SELECTION_LOST' });
  assert.equal(track.readyState, 'ended');
  assert.equal(environment.contexts.every(context => context.state === 'closed'), true);
  assert.equal(environment.mediaDevices.listenerCount('devicechange'), 0);
});

test('formal P1 maps active microphone permission revocation and forbids Speech or playout effects', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const permission = new FakePermissionStatus('denied');
  const environment = audioEnvironment();
  let resolvePermissionQuery;
  environment.permissions = {
    query: () => new Promise(resolve => (resolvePermissionQuery = resolve)),
  };
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  assert.equal(permission.listenerCount('change'), 0);
  resolvePermissionQuery(permission);
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'MICROPHONE_PERMISSION_REVOKED' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    calls.some(([method]) => method === 'live_voice.speech.recognize_batch'),
    false
  );
  assert.equal(
    calls.some(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD),
    false
  );
  assert.equal(permission.listenerCount('change'), 0);
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('formal P1 latches pending permission revocation while preserving initial-denial semantics and zero remote effects', async () => {
  const permission = new FakePermissionStatus('prompt');
  const environment = audioEnvironment();
  environment.permissions = { query: async () => permission };
  let resolveMedia;
  environment.mediaDevices.getUserMedia = () =>
    new Promise(resolve => {
      const track = new FakeTrack();
      environment.track = track;
      resolveMedia = () =>
        resolve({
          getAudioTracks: () => [track],
          getTracks: () => [track],
        });
    });
  let requests = 0;
  let socketAllocations = 0;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      socketAllocations += 1;
      throw new Error('socket must not be allocated');
    },
    request: async () => {
      requests += 1;
      throw new Error('request must not be called');
    },
  });

  const starting = owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  for (let turn = 0; turn < 100 && permission.listenerCount('change') === 0; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(permission.listenerCount('change'), 1);
  permission.change('denied');
  const outcome = await outcomeWithin(starting, 'permission revocation did not settle product capture');
  assert.equal(outcome?.reason, 'MICROPHONE_PERMISSION_REVOKED');

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'MICROPHONE_PERMISSION_REVOKED' });
  assert.equal(requests, 0);
  assert.equal(socketAllocations, 0);
  assert.equal(permission.listenerCount('change'), 0);
  resolveMedia();
  for (let turn = 0; turn < 100 && environment.track.readyState !== 'ended'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );

  const deniedPermission = new FakePermissionStatus('denied');
  const deniedEnvironment = audioEnvironment();
  deniedEnvironment.permissions = { query: async () => deniedPermission };
  deniedEnvironment.mediaDevices.getUserMedia = async () => {
    const error = new Error('initial microphone denial');
    error.name = 'NotAllowedError';
    throw error;
  };
  let deniedRequests = 0;
  const deniedOwner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: deniedEnvironment,
    request: async () => {
      deniedRequests += 1;
    },
  });
  await assert.rejects(
    deniedOwner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    }),
    error => error?.reason === 'MICROPHONE_PERMISSION_DENIED'
  );
  assert.deepEqual(deniedOwner.status(), { status: 'failed', reason: 'MICROPHONE_PERMISSION_DENIED' });
  assert.equal(deniedRequests, 0);
  assert.equal(deniedPermission.listenerCount('change'), 0);
});

test('formal P1 fails immediately when the current dedicated media transport closes', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  socket.readyState = 3;
  socket.onclose?.({});
  for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'MEDIA_TRANSPORT_CLOSED' });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(
    calls.some(([method]) => method === 'live_voice.speech.recognize_batch'),
    false
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

for (const [name, trigger, expectedReason] of [
  [
    'page hide',
    environment => {
      environment.document.visibilityState = 'hidden';
      environment.document.emit('visibilitychange');
    },
    'PAGE_HIDDEN',
  ],
  ['AudioWorklet processor failure', environment => environment.worklet.onprocessorerror?.({}), 'AUDIO_PROCESSOR_ERROR'],
]) {
  test(`formal P1 preserves the stable ${name} reason and forbids Speech effects`, async () => {
    const calls = [];
    const binding = serverBinding();
    const socket = new FakeSocket();
    const environment = audioEnvironment();
    const owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      audio_environment: environment,
      socket_factory: () => {
        queueMicrotask(() => socket.open(binding));
        return socket;
      },
      request: async (method, params) => {
        calls.push([method, params]);
        if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
          return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
        }
        assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1',
          endpoint_path: '/ws/live-voice/media',
          media_ticket: 'P'.repeat(43),
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
          binding,
          privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
        };
      },
    });

    await startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    });
    trigger(environment);
    for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
      await new Promise(resolve => setImmediate(resolve));
    }

    assert.deepEqual(owner.status(), { status: 'failed', reason: expectedReason });
    assert.deepEqual(
      calls.map(([method]) => method),
      [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
    );
    assert.equal(
      environment.contexts.every(context => context.state === 'closed'),
      true
    );
  });
}

test('formal P1 completes capture, STT, authoritative TTS, and browser playout', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1',
          endpoint_path: '/ws/live-voice/media',
          media_ticket: 'P'.repeat(43),
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
          binding,
          privacy: {
            raw_audio_persisted: false,
            raw_audio_logged: false,
            memory_only: true,
          },
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
            voice_commit_receipt: 'voice-receipt-1',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation,
              seq: 0,
              kind: 'final',
              commits_turn: false,
              hypothesis: {
                alternatives: [{ raw_text: 'formal text', display_text: 'formal text', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'stt-test',
            },
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
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
              format: 'wav_pcm16_mono',
              sample_rate_hz: 48_000,
              channel_count: 1,
              data_base64: wavBase64(48_000, 960 * 300),
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-test',
              voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD) {
        return {
          status: 'media_playout_acknowledged',
          reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
          receipt_id: 'media-playout-receipt-1',
          duplex_media_observed: false,
          ...params,
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
  });
  socket.deferDetachReceipt = true;
  const pendingRecognition = owner.stopAndRecognize();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 0);
  assert.notEqual(socket.pendingDetachReceipt, null);
  socket.releaseDetachReceipt();
  const recognition = await pendingRecognition;
  assert.deepEqual(recognition, {
    text: 'formal text',
    voice_commit_receipt: 'voice-receipt-1',
  });
  await owner.playAgentText({
    response: {
      interaction_id: 'interaction-1',
      response_id: 'response-1',
      response_generation: 0,
    },
    unit_id: 'unit-1',
    text: 'formal Agent response',
  });

  assert.equal(owner.status().status, 'recognized');
  assert.equal(Math.max(...environment.contexts.map(context => context.peakSources)), 256);
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, 'live_voice.speech.recognize_batch', 'live_voice.speech.synthesize_batch', PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD]
  );
  await owner.close();
  assert.equal(calls.at(-1)[0], PRODUCT_P1_MEDIA_CLOSE_METHOD);
});

test('formal P1 consumes the streaming STT final without replaying batch audio', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params, options) => {
      calls.push([method, params, options]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) return streamingMediaActivation(binding);
      if (method === 'live_voice.speech.recognize_streaming_result') {
        return streamingRecognitionResult(params);
      }
      if (method === 'live_voice.speech.recognize_batch') {
        throw new Error('batch replay is forbidden after streaming success');
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  const recognition = await owner.stopAndRecognize();

  assert.deepEqual(recognition, {
    text: 'streaming text',
    voice_commit_receipt: 'streaming-voice-receipt-1',
  });
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, 'live_voice.speech.recognize_streaming_result']
  );
  assert.deepEqual(calls[1][2], { timeoutMs: 38_000, signal: undefined });
  assert.deepEqual(owner.status(), { status: 'recognized', reason: null });
});

test('formal P1 auto and manual EOT retain one stop and recognition operation', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return streamingMediaActivation(binding, null, {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        });
      }
      if (method === 'live_voice.speech.recognize_streaming_result') {
        return streamingRecognitionResult(params, 'automatic EOT text');
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected EOT method ${method}`);
    },
  });
  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  let automatic = null;
  let automaticCalls = 0;
  assert.equal(
    owner.armEndOfTurn(() => {
      automaticCalls += 1;
      automatic = owner.stopAndRecognize();
    }),
    true
  );
  socket.onmessage?.({
    data: serializeMediaControl({
      type: 'media.speech_start',
      capability_version: 'media.end_of_turn.v1',
      lease_id: binding.lease_id,
      generation: binding.generation.value,
      detector: 'server_vad',
      provider_start_ms: 100,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  socket.onmessage?.({
    data: serializeMediaControl({
      type: 'media.end_of_turn',
      capability_version: 'media.end_of_turn.v1',
      lease_id: binding.lease_id,
      generation: binding.generation.value,
      detector: 'server_vad',
      speech_started_observed: true,
      provider_start_ms: 100,
      provider_end_ms: 700,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  await Promise.resolve();
  assert.equal(automaticCalls, 1);
  assert.notEqual(automatic, null);
  const manual = owner.stopAndRecognize();
  assert.equal(manual, automatic);
  const recognition = await manual;
  assert.deepEqual(recognition, {
    text: 'automatic EOT text',
    voice_commit_receipt: 'streaming-voice-receipt-1',
  });
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_streaming_result').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('agent') || method.includes('task')),
    false
  );
  await owner.close();
});

test('formal P1 manual stop wins the queued EOT callback without a late second stop', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return streamingMediaActivation(binding, null, {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        });
      }
      if (method === 'live_voice.speech.recognize_streaming_result') {
        return streamingRecognitionResult(params, 'manual race text');
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected EOT method ${method}`);
    },
  });
  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  let automaticCalls = 0;
  assert.equal(
    owner.armEndOfTurn(() => {
      automaticCalls += 1;
      void owner.stopAndRecognize();
    }),
    true
  );
  socket.onmessage?.({
    data: serializeMediaControl({
      type: 'media.speech_start',
      capability_version: 'media.end_of_turn.v1',
      lease_id: binding.lease_id,
      generation: binding.generation.value,
      detector: 'server_vad',
      provider_start_ms: 100,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  socket.onmessage?.({
    data: serializeMediaControl({
      type: 'media.end_of_turn',
      capability_version: 'media.end_of_turn.v1',
      lease_id: binding.lease_id,
      generation: binding.generation.value,
      detector: 'server_vad',
      speech_started_observed: true,
      provider_start_ms: 100,
      provider_end_ms: 700,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  const manual = owner.stopAndRecognize();
  await Promise.resolve();
  assert.equal(automaticCalls, 0);
  assert.deepEqual(await manual, {
    text: 'manual race text',
    voice_commit_receipt: 'streaming-voice-receipt-1',
  });
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_streaming_result').length, 1);
  await owner.close();
});

test('formal P1 performs exactly one visible batch fallback after a sealed streaming failure', async () => {
  const calls = [];
  const warnings = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const originalWarn = console.warn;
  console.warn = message => warnings.push(String(message));
  try {
    const owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      audio_environment: environment,
      socket_factory: () => {
        queueMicrotask(() => socket.open(binding));
        return socket;
      },
      request: async (method, params) => {
        calls.push([method, params]);
        if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) return streamingMediaActivation(binding);
        if (method === 'live_voice.speech.recognize_streaming_result') {
          return streamingFallbackResult(params, 'batch', 'STREAMING_SPEECH_PROVIDER_TIMEOUT');
        }
        if (method === 'live_voice.speech.recognize_batch') {
          return batchRecognitionResult(params);
        }
        throw new Error(`unexpected method ${method}`);
      },
    });

    await startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    });
    const recognition = await owner.stopAndRecognize();

    assert.equal(recognition.text, 'batch text');
    assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
    assert.equal(
      warnings.some(message => message === 'live_voice_speech_degradation reason=STREAMING_SPEECH_PROVIDER_TIMEOUT target=batch visible=true'),
      true
    );
    assert.deepEqual(owner.status(), {
      status: 'recognized',
      reason: 'STREAMING_SPEECH_PROVIDER_TIMEOUT',
    });
  } finally {
    console.warn = originalWarn;
  }
});

test('formal P1 discloses startup streaming unavailability before using batch', async () => {
  const calls = [];
  const warnings = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const originalWarn = console.warn;
  console.warn = message => warnings.push(String(message));
  try {
    const owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      audio_environment: environment,
      socket_factory: () => {
        queueMicrotask(() => socket.open(binding));
        return socket;
      },
      request: async (method, params) => {
        calls.push([method, params]);
        if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
          return streamingMediaActivation(binding, {
            reason_id: 'STREAMING_SPEECH_FEATURE_OFF',
            fallback_tier: 'batch',
            visible: true,
            x_obs_event: null,
            x_obs_metric: null,
          });
        }
        if (method === 'live_voice.speech.recognize_batch') {
          return batchRecognitionResult(params);
        }
        throw new Error(`unexpected method ${method}`);
      },
    });

    await startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    });
    const recognition = await owner.stopAndRecognize();

    assert.equal(recognition.text, 'batch text');
    assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_streaming_result').length, 0);
    assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
    assert.equal(warnings.includes('live_voice_speech_degradation reason=STREAMING_SPEECH_FEATURE_OFF target=batch visible=true'), true);
    assert.deepEqual(owner.status(), {
      status: 'recognized',
      reason: 'STREAMING_SPEECH_FEATURE_OFF',
    });
  } finally {
    console.warn = originalWarn;
  }
});

test('formal P1 honors a startup text fallback without replaying batch audio', async () => {
  const calls = [];
  const warnings = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const originalWarn = console.warn;
  console.warn = message => warnings.push(String(message));
  try {
    const owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      audio_environment: environment,
      socket_factory: () => {
        queueMicrotask(() => socket.open(binding));
        return socket;
      },
      request: async (method, params) => {
        calls.push([method, params]);
        if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
          return streamingMediaActivation(binding, {
            reason_id: 'STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE',
            fallback_tier: 'text',
            visible: true,
            x_obs_event: null,
            x_obs_metric: null,
          });
        }
        if (method === 'live_voice.speech.recognize_batch') {
          throw new Error('batch replay is forbidden for startup text fallback');
        }
        if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
          return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
        }
        throw new Error(`unexpected method ${method}`);
      },
    });

    await startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    });
    await assert.rejects(
      owner.stopAndRecognize(),
      error => error?.reason_id === 'STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE'
    );

    assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_streaming_result').length, 0);
    assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 0);
    assert.equal(
      warnings.includes(
        'live_voice_speech_degradation reason=STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE target=text visible=true'
      ),
      true
    );
    assert.deepEqual(owner.status(), {
      status: 'failed',
      reason: 'STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE',
    });
  } finally {
    console.warn = originalWarn;
  }
});

test('formal P1 text fallback never replays batch audio or hides the failure', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) return streamingMediaActivation(binding);
      if (method === 'live_voice.speech.recognize_streaming_result') {
        return streamingFallbackResult(params, 'text', 'STREAMING_SPEECH_ROUTE_ABORTED');
      }
      if (method === 'live_voice.speech.recognize_batch') {
        throw new Error('batch replay is forbidden for text fallback');
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  await assert.rejects(owner.stopAndRecognize(), error => error?.reason_id === 'STREAMING_SPEECH_ROUTE_ABORTED');

  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 0);
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'STREAMING_SPEECH_ROUTE_ABORTED',
  });
});

test('formal P1 rejects private streaming fallback reasons without logging or batch replay', async () => {
  const calls = [];
  const warnings = [];
  const privateReason = 'PRIVATE_PROVIDER_TRACE';
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const originalWarn = console.warn;
  console.warn = message => warnings.push(String(message));
  try {
    const owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      audio_environment: environment,
      socket_factory: () => {
        queueMicrotask(() => socket.open(binding));
        return socket;
      },
      request: async (method, params) => {
        calls.push([method, params]);
        if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) return streamingMediaActivation(binding);
        if (method === 'live_voice.speech.recognize_streaming_result') {
          return streamingFallbackResult(params, 'batch', privateReason);
        }
        if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
          return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
        }
        throw new Error(`unexpected method ${method}`);
      },
    });

    await startCaptureWithFirstFrame(owner, environment, {
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 7,
    });
    await assert.rejects(owner.stopAndRecognize(), error => error?.reason === 'INVALID_STREAMING_RECOGNITION_FALLBACK');

    assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 0);
    assert.equal(warnings.join('\n').includes(privateReason), false);
    assert.equal(JSON.stringify(owner.status()).includes(privateReason), false);
  } finally {
    console.warn = originalWarn;
  }
});

test('formal P1 page-hidden playout fences browser sources without receipt or business effects', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  let heldSource = null;
  environment.createAudioContext = () => {
    const context = new FakeAudioContext();
    context.createBufferSource = () => {
      const source = {
        buffer: null,
        onended: null,
        stopCount: 0,
        disconnectCount: 0,
        connect() {},
        disconnect() {
          source.disconnectCount += 1;
        },
        start() {
          heldSource = source;
        },
        stop() {
          source.stopCount += 1;
        },
      };
      return source;
    };
    environment.contexts.push(context);
    return context;
  };
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1',
          endpoint_path: '/ws/live-voice/media',
          media_ticket: 'P'.repeat(43),
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
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
            voice_commit_receipt: 'voice-receipt-1',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation,
              seq: 0,
              kind: 'final',
              commits_turn: false,
              hypothesis: { alternatives: [{ raw_text: 'formal text', display_text: 'formal text', confidence: null }], selected_index: 0 },
            },
            provider: { provider_id: 'provider-test', implementation_class: 'formal', fallback_from: null, model: 'stt-test' },
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
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
            audio: { format: 'wav_pcm16_mono', sample_rate_hz: 48_000, channel_count: 1, data_base64: wavBase64() },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-test',
              voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  await owner.stopAndRecognize();
  const playing = owner.playAgentText({
    response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 },
    unit_id: 'unit-1',
    text: 'formal Agent response',
  });
  for (let turn = 0; turn < 100 && heldSource === null; turn += 1) await new Promise(resolve => setImmediate(resolve));
  assert.notEqual(heldSource, null);
  const lateEnded = heldSource.onended;

  environment.document.visibilityState = 'hidden';
  environment.document.emit('visibilitychange');
  const outcome = await outcomeWithin(playing, 'page-hidden playout remained pending');

  assert.equal(outcome?.reason, 'PAGE_HIDDEN_PLAYOUT_FENCED');
  assert.equal(heldSource.stopCount, 1);
  assert.equal(heldSource.disconnectCount, 1);
  assert.equal(
    calls.some(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD),
    false
  );
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, 'live_voice.speech.recognize_batch', 'live_voice.speech.synthesize_batch', PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'PAGE_HIDDEN_PLAYOUT_FENCED' });
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  const callsAfterFence = calls.length;
  lateEnded();
  await Promise.resolve();
  assert.equal(calls.length, callsAfterFence);
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'PAGE_HIDDEN_PLAYOUT_FENCED' });
});

test('formal P1 page-hidden transition fences a TTS result before browser playout begins', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  let releaseSynthesis = null;
  const synthesisGate = new Promise(resolve => {
    releaseSynthesis = resolve;
  });
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1',
          endpoint_path: '/ws/live-voice/media',
          media_ticket: 'P'.repeat(43),
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
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
            voice_commit_receipt: 'voice-receipt-1',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation,
              seq: 0,
              kind: 'final',
              commits_turn: false,
              hypothesis: { alternatives: [{ raw_text: 'formal text', display_text: 'formal text', confidence: null }], selected_index: 0 },
            },
            provider: { provider_id: 'provider-test', implementation_class: 'formal', fallback_from: null, model: 'stt-test' },
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
        await synthesisGate;
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
            audio: { format: 'wav_pcm16_mono', sample_rate_hz: 48_000, channel_count: 1, data_base64: wavBase64() },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-test',
              voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });
  await owner.stopAndRecognize();
  const playing = owner.playAgentText({
    response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 },
    unit_id: 'unit-1',
    text: 'formal Agent response',
  });
  for (let turn = 0; turn < 100 && calls.filter(([method]) => method === 'live_voice.speech.synthesize_batch').length === 0; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  environment.document.visibilityState = 'hidden';
  environment.document.emit('visibilitychange');
  releaseSynthesis();

  const outcome = await outcomeWithin(playing, 'page-hidden pre-playout result remained pending');
  assert.equal(outcome?.reason, 'PAGE_HIDDEN_PLAYOUT_FENCED');
  assert.equal(
    environment.contexts.every(context => context.sourceStartCount === 0),
    true
  );
  assert.equal(
    calls.some(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD),
    false
  );
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, 'live_voice.speech.recognize_batch', 'live_voice.speech.synthesize_batch', PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'PAGE_HIDDEN_PLAYOUT_FENCED' });
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('empty capture settles with zero commit while retaining authoritative P2 playout', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1',
          endpoint_path: '/ws/live-voice/media',
          media_ticket: 'P'.repeat(43),
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
          binding,
          privacy: {
            raw_audio_persisted: false,
            raw_audio_logged: false,
            memory_only: true,
          },
        };
      }
      if (method === 'live_voice.speech.recognize_batch') {
        throw Object.assign(new Error('provider returned no transcript'), {
          reason: PRODUCT_P1_EMPTY_TRANSCRIPT_REASON,
        });
      }
      if (method === 'live_voice.speech.synthesize_batch') {
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
              format: 'wav_pcm16_mono',
              sample_rate_hz: 48_000,
              channel_count: 1,
              data_base64: wavBase64(48_000, 960),
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-test',
              voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD) {
        return {
          status: 'media_playout_acknowledged',
          reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
          receipt_id: 'media-playout-receipt-1',
          duplex_media_observed: false,
          ...params,
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
  });
  await assert.rejects(
    owner.stopAndRecognize(),
    error => error?.reason === PRODUCT_P1_EMPTY_TRANSCRIPT_REASON
  );

  assert.deepEqual(owner.status(), {
    status: 'idle',
    reason: PRODUCT_P1_EMPTY_TRANSCRIPT_REASON,
  });
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD).length, 0);

  await owner.playAgentText({
    response: {
      interaction_id: 'interaction-1',
      response_id: 'response-p2-1',
      response_generation: 0,
    },
    unit_id: 'unit-p2-1',
    text: 'main',
  });

  assert.equal(owner.status().status, 'recognized');
  assert.deepEqual(
    calls.map(([method]) => method),
    [
      PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
      'live_voice.speech.recognize_batch',
      'live_voice.speech.synthesize_batch',
      PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD,
    ]
  );
  await owner.close();
  assert.equal(calls.at(-1)[0], PRODUCT_P1_MEDIA_CLOSE_METHOD);
});

test('a successor P1 turn revokes the exact prior media and Speech authority first', async () => {
  const calls = [];
  let captureIndex = 0;
  let activeBinding = null;
  const environment = audioEnvironment(() => `capture-${++captureIndex}`);
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      const socket = new FakeSocket();
      queueMicrotask(() => socket.open(activeBinding));
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        activeBinding = {
          ...serverBinding(),
          lease_id: `media-lease-${params.capture_generation}`,
          authority_evidence_id: `media-authority-${params.capture_generation}`,
          session_id: params.session_id,
          interaction_id: params.interaction_id,
          correlation_id: params.correlation_id,
          track_id: params.track_id,
          generation: {
            kind: 'capture',
            id: params.capture_id,
            value: params.capture_generation,
          },
        };
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: `media-subject-${params.activation_generation}`,
          endpoint_path: '/ws/live-voice/media',
          media_ticket: `${String(params.activation_generation).padStart(32, 'A')}BBBBBBBBBBB`,
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
          binding: activeBinding,
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
            voice_commit_receipt: 'voice-receipt-2',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation,
              seq: 0,
              kind: 'final',
              commits_turn: false,
              hypothesis: {
                alternatives: [{ raw_text: 'turn text', display_text: 'turn text', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'stt-test',
            },
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  const first = {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 1,
  };
  await startCaptureWithFirstFrame(owner, environment, first, { samples: new Float32Array(960) });
  await owner.stopAndRecognize();
  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-2',
    correlation_id: 'correlation-2',
    activation_id: 'activation-2',
    activation_generation: 2,
  });

  assert.deepEqual(
    calls.slice(0, 4).map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, 'live_voice.speech.recognize_batch', PRODUCT_P1_MEDIA_CLOSE_METHOD, PRODUCT_P1_MEDIA_ACTIVATE_METHOD]
  );
  assert.deepEqual(calls[2][1], {
    session_id: 'session-1',
    subject_id: 'media-subject-1',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-1',
    activation_id: 'activation-1',
    activation_generation: 1,
  });
  assert.equal(calls[3][1].correlation_id, 'correlation-2');
  await owner.close();
});

test('P1 playout source failure fences cleanup and every late source callback', async () => {
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  let contextCount = 0;
  let sourceStopCalls = 0;
  let sourceDisconnectCalls = 0;
  let lateEnded = null;
  let mediaCloseCalls = 0;
  environment.createAudioContext = () => {
    contextCount += 1;
    const context = new FakeAudioContext();
    if (contextCount === 1) {
      context.createBufferSource = () => {
        const source = {
          buffer: null,
          onended: null,
          connect() {},
          disconnect() {
            sourceDisconnectCalls += 1;
          },
          start() {
            lateEnded = source.onended;
            throw new Error('injected source startup failure');
          },
          stop() {
            sourceStopCalls += 1;
          },
        };
        return source;
      };
    }
    return context;
  };
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1',
          endpoint_path: '/ws/live-voice/media',
          media_ticket: 'P'.repeat(43),
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn: MANUAL_EOT_FALLBACK,
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
            voice_commit_receipt: 'voice-receipt-3',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation,
              seq: 0,
              kind: 'final',
              commits_turn: false,
              hypothesis: {
                alternatives: [{ raw_text: 'formal text', display_text: 'formal text', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'stt-test',
            },
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
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
              format: 'wav_pcm16_mono',
              sample_rate_hz: 48_000,
              channel_count: 1,
              data_base64: wavBase64(),
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-test',
              voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        mediaCloseCalls += 1;
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 1,
  });
  await owner.stopAndRecognize();
  await assert.rejects(
    owner.playAgentText({
      response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 },
      unit_id: 'unit-1',
      text: 'formal Agent response',
    }),
    /browser playout source setup failed/
  );

  assert.equal(sourceStopCalls, 1);
  assert.equal(sourceDisconnectCalls, 1);
  assert.equal(mediaCloseCalls, 1);
  assert.equal(owner.status().status, 'failed');
  const failedSnapshot = owner.status();
  assert.equal(typeof lateEnded, 'function');
  lateEnded();
  await Promise.resolve();
  assert.deepEqual(owner.status(), failedSnapshot);
  await owner.close();
  assert.equal(mediaCloseCalls, 1);
});

test('capture setup failure closes browser audio without an explicit owner close', async () => {
  const environment = audioEnvironment();
  environment.mediaDevices.getUserMedia = async () => {
    throw Object.assign(new Error('private microphone failure'), {
      reason: 'FORMAL_CAPTURE_FAILED',
    });
  };
  let requests = 0;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    request: async () => {
      requests += 1;
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 1,
    }),
    /browser audio operation failed/
  );

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'CAPTURE_START_FAILED' });
  assert.equal(requests, 0);
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
});

test('post-activation validation failure automatically revokes exact media authority', async () => {
  const environment = audioEnvironment();
  const binding = serverBinding();
  const calls = [];
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: true, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 1,
    }),
    /privacy boundary/
  );

  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P1_MEDIA_ACTIVATE_METHOD, PRODUCT_P1_MEDIA_CLOSE_METHOD]
  );
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.equal(owner.status().status, 'failed');
});

test('Agent output during capture cannot hide the reachable stop control or start TTS', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      calls.push(method);
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });
  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  });

  await assert.rejects(
    owner.playAgentText({
      response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 },
      unit_id: 'unit-1',
      text: 'must remain text-only while capture is active',
    }),
    /capture must settle/
  );
  assert.equal(owner.status().status, 'capturing');
  assert.deepEqual(calls, [PRODUCT_P1_MEDIA_ACTIVATE_METHOD]);
  await owner.close();
});

test('formal P1 rejects an invalid product activation generation before browser effects', async () => {
  let calls = 0;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: audioEnvironment(),
    socket_factory: () => {
      throw new Error('socket must not be allocated');
    },
    request: async () => {
      calls += 1;
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 0,
    }),
    /activation_generation/
  );

  assert.equal(owner.status().status, 'idle');
  assert.equal(calls, 0);
  await owner.close();
});

test('formal P1 fences successor capture while retained close is in flight', async () => {
  const binding = serverBinding();
  const socket = new FakeSocket();
  let releaseClose;
  let markCloseStarted;
  const closeGate = new Promise(resolve => {
    releaseClose = resolve;
  });
  const closeStarted = new Promise(resolve => {
    markCloseStarted = resolve;
  });
  const environment = audioEnvironment();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: () => {
      queueMicrotask(() => socket.open(binding));
      return socket;
    },
    request: async (method, params) => {
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        markCloseStarted();
        await closeGate;
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'P'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: MANUAL_EOT_FALLBACK,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });
  const capture = {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
  };
  await startCaptureWithFirstFrame(owner, environment, capture);

  const closing = owner.close();
  await closeStarted;
  assert.equal(owner.status().status, 'cleanup_pending');
  await assert.rejects(owner.startCapture(capture), /cleanup is in progress/);
  releaseClose();
  await closing;
  assert.equal(owner.status().status, 'closed');
});

async function runConcurrentCaptureJourney(options = {}) {
  const calls = [];
  const requestOptions = [];
  const statuses = [];
  const statusSnapshots = [];
  const sockets = [];
  const socketOpenTasks = [];
  let activationCount = 0;
  let concurrentFailureSnapshot = null;
  let concurrentAudioReleased = false;
  let concurrentClosePromise = null;
  let concurrentCloseSnapshot = null;
  let concurrentCloseAudioReleased = false;
  let realProcessorHarness = null;
  let finalPlayoutDuplicateSnapshot = null;
  let postReceiptStatusBeforeFailure = null;
  let postReceiptSourceStartsBeforeFailure = null;
  let postReceiptUplinkFramesBeforeFailure = null;
  let captureDurationBoundarySnapshot = null;
  let captureDurationBoundaryRecognition = null;
  let captureDurationLateFrameUplinkCount = null;
  let transportAckBeforeRenderSnapshot = null;
  let secondMediaCloseFailures = options.failSecondMediaCloseOnce === true ? 1 : 0;
  let activationCountAtFinalDownlinkAck = null;
  let concurrentCaptureStartedCalls = 0;
  let bargeInSpeechStartCalls = 0;
  let bargeInEotCalls = 0;
  let bargeInStopped = null;
  let captureRotationSnapshot = null;
  let overlapRotationRaceSnapshot = null;
  let staleSpeechStartSnapshot = null;
  let notificationPauseOutcome = null;
  let notificationPausedFrameHandler = null;
  let staleCaptureFrameHandler = null;
  let staleUplinkMessageHandler = null;
  let staleDownlinkMessageHandler = null;
  let socketFactory = null;
  let request = null;
  let receiptSubjectId = null;
  let finalDownlinkAckResolve;
  let pendingSecondCaptureFirstAck = null;
  let pendingSecondCaptureNextAck = null;
  let secondCaptureAckStillPendingAtReady = null;
  const finalDownlinkAckObserved = new Promise(resolve => {
    finalDownlinkAckResolve = resolve;
  });
  const environment = audioEnvironment(
    (() => {
      let value = 0;
      return () => `capture-${++value}`;
    })(),
  );
  environment.deferSourceEnds = options.deferSourceEndsUntilTransportAck === true;
  const response = {
    interaction_id: 'interaction-1',
    response_id: 'response-duplex-1',
    response_generation: 1,
  };
  const downlinkFrameCount = options.downlinkFrameCount ?? 1;
  const downlinkFramesToSend = options.downlinkFramesToSend ?? downlinkFrameCount;
  const makeUplinkBinding = (params, index) => ({
    ...serverBinding(),
    lease_id: `media-uplink-lease-${index}`,
    authority_evidence_id: `media-uplink-authority-${index}`,
    media_session_id: `media-uplink-session-${index}`,
    track_id: params.track_id,
    generation: {
      kind: 'capture',
      id: params.capture_id,
      value: params.capture_generation,
    },
  });
  const downlinkBinding = {
    ...serverBinding(),
    lease_id: 'media-downlink-lease-1',
    authority_evidence_id: 'media-downlink-authority-1',
    media_session_id: 'media-downlink-session-1',
    track_id: 'playout-track-1',
    direction: 'downlink',
    generation: { kind: 'response', id: response.response_id, value: response.response_generation },
    playout: {
      response_id: response.response_id,
      response_generation: response.response_generation,
      unit_id: 'unit-duplex-1',
    },
  };

  class DuplexSocket extends FakeSocket {
    constructor() {
      super();
      this.serverBinding = null;
      this.downlinkNextSeq = 0;
      this.downlinkAckedSeq = -1;
    }
    pumpDownlink() {
      const binding = this.serverBinding;
      if (binding?.direction !== 'downlink' || this.readyState !== 1) return;
      const maxPendingFrames = 8;
      while (
        this.downlinkNextSeq < downlinkFramesToSend
        && this.downlinkNextSeq <= this.downlinkAckedSeq + maxPendingFrames
      ) {
        const seq = this.downlinkNextSeq;
        this.downlinkNextSeq += 1;
        this.onmessage?.({
          data: encodeAudioFrame(binding, {
            seq,
            sample_cursor: seq * 960,
            samples: new Float32Array(960).fill(0.125),
          }),
        });
      }
    }
    send(value) {
      this.sent.push(value);
      if (typeof value === 'string') {
        const control = JSON.parse(value);
        if (control.type === 'media.auth') {
          this.serverBinding = control.binding;
          return;
        }
      }
      if (this.serverBinding.direction === 'uplink' && typeof value !== 'string') {
        if (options.ackSecondCapture !== false || this.serverBinding.generation.id !== 'capture-2') {
          const throughSeq = decodeAudioFrame(this.serverBinding, value).seq;
          const acknowledge = () => {
            if (this.serverBinding.generation.id === 'capture-2' && throughSeq === 0) {
              this.secondCaptureFramesInFlightAtFirstAck =
                this.sent.filter(sent => typeof sent !== 'string').length - 1;
            }
            this.onmessage?.({
              data: serializeMediaControl({
                type: 'media.ack',
                lease_id: this.serverBinding.lease_id,
                generation: this.serverBinding.generation.value,
                through_seq: throughSeq,
              }),
            });
          };
          if (
            options.holdSecondCaptureFirstAckUntilNextFrame === true
            && this.serverBinding.generation.id === 'capture-2'
          ) {
            if (throughSeq === 0) {
              pendingSecondCaptureFirstAck = acknowledge;
              return;
            }
            if (throughSeq === 1 && pendingSecondCaptureFirstAck !== null) {
              const releaseFirstAck = pendingSecondCaptureFirstAck;
              pendingSecondCaptureFirstAck = null;
              queueMicrotask(releaseFirstAck);
              pendingSecondCaptureNextAck = acknowledge;
              return;
            }
          }
          if (
            this.serverBinding.generation.id === 'capture-2'
            && Number.isFinite(options.secondCaptureAckDelayMs)
            && options.secondCaptureAckDelayMs > 0
          ) {
            setTimeout(acknowledge, options.secondCaptureAckDelayMs);
          } else {
            queueMicrotask(acknowledge);
          }
        }
      } else if (this.serverBinding.direction === 'uplink' && typeof value === 'string') {
        const control = JSON.parse(value);
        if (control.type === 'media.detach') {
          queueMicrotask(() => this.onmessage?.({ data: value }));
        }
      } else if (this.serverBinding.direction === 'downlink' && typeof value === 'string') {
        const control = JSON.parse(value);
        if (control.type !== 'media.ack') return;
        this.downlinkAckedSeq = Math.max(this.downlinkAckedSeq, control.through_seq);
        if (control.through_seq === options.earlyDownlinkDetachThroughSeq) {
          this.onmessage?.({
            data: serializeMediaControl({
              type: 'media.detach',
              lease_id: this.serverBinding.lease_id,
              generation: this.serverBinding.generation.value,
              reason_id: 'MEDIA_LOCAL_CLOSE',
              through_seq: control.through_seq,
              business_cancel_count_delta: 0,
            }),
          });
        } else if (control.through_seq === downlinkFrameCount - 1) {
          activationCountAtFinalDownlinkAck = activationCount;
          finalDownlinkAckResolve();
          if (options.holdDownlinkDetachAfterFinalRender !== true) {
            const completeDownlink = () =>
              this.onmessage?.({
                data: serializeMediaControl({
                  type: 'media.detach',
                  lease_id: this.serverBinding.lease_id,
                  generation: this.serverBinding.generation.value,
                  reason_id: 'MEDIA_LOCAL_CLOSE',
                  through_seq: control.through_seq,
                  business_cancel_count_delta: 0,
                }),
              });
            if (options.synchronousDownlinkDetachAfterFinalRender === true) completeDownlink();
            else queueMicrotask(completeDownlink);
          }
        } else {
          queueMicrotask(() => this.pumpDownlink());
        }
      }
    }
  }

  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    on_status: status => {
      statuses.push(status);
      statusSnapshots.push({
        status,
        source_start_count: environment.contexts[0]?.sourceStartCount ?? 0,
      });
    },
    on_concurrent_capture_started: () => {
      concurrentCaptureStartedCalls += 1;
      if (options.holdSecondCaptureFirstAckUntilNextFrame === true) {
        secondCaptureAckStillPendingAtReady = pendingSecondCaptureNextAck !== null;
        const releaseNextAck = pendingSecondCaptureNextAck;
        pendingSecondCaptureNextAck = null;
        if (releaseNextAck !== null) queueMicrotask(releaseNextAck);
      }
    },
    ...(options.triggerBargeInEot === true
      ? {
          on_barge_in_speech_start: event => {
            bargeInSpeechStartCalls += 1;
            assert.equal(event.detector, 'server_vad');
            assert.equal(event.business_cancel_count_delta, 0);
            bargeInStopped = owner.stopAgentPlayout(response);
          },
          on_barge_in_end_of_turn: event => {
            bargeInEotCalls += 1;
            assert.equal(event.speech_started_observed, true);
            assert.equal(event.business_cancel_count_delta, 0);
          },
        }
      : {}),
    audio_environment: environment,
    socket_factory: (socketFactory = url => {
      assert.equal(new URL(url).pathname, '/ws/live-voice/media');
      const socket = new DuplexSocket();
      sockets.push(socket);
      const openTask = Promise.resolve().then(async () => {
        socket.protocol = 'live-voice.media.v1';
        socket.readyState = 1;
        socket.onopen?.({});
        const binding = socket.serverBinding;
        // An immediate speech-start barge can close a just-created downlink
        // before this queued fake open runs. That is a valid cancelled route,
        // not a missing authority on an active route.
        if (binding === null) return;
        socket.onmessage?.({
          data: serializeMediaControl({ type: 'media.attach', binding }),
        });
        if (binding.direction === 'downlink') {
          if (options.useRealProcessorForSecondCapture === true) {
            for (let turn = 0; turn < 500 && realProcessorHarness === null; turn += 1) {
              await new Promise(resolve => setImmediate(resolve));
            }
            assert.notEqual(realProcessorHarness, null);
            for (let turn = 0; turn < 500 && concurrentCaptureStartedCalls === 0; turn += 1) {
              await new Promise(resolve => setTimeout(resolve, 1));
            }
            assert.equal(concurrentCaptureStartedCalls, 1);
          }
          if (
            options.exerciseRenderRegressionDuringDownlink === true
            || options.exerciseRenderStallDuringDownlink === true
          ) {
            socket.pumpDownlink();
            assert.equal(owner.status().status, 'playing');
          }
          if (options.exerciseDuplicateRenderFrameAtFinalPlayout === true) {
            assert.notEqual(realProcessorHarness, null);
            environment.contexts[0].onSourceEnded = ({ sourceStartCount, sourceEndCount }) => {
              if (sourceEndCount !== downlinkFrameCount || finalPlayoutDuplicateSnapshot !== null) return;
              const { processor, quantum, sandbox } = realProcessorHarness;
              const pendingLengthBefore = processor.pendingLength;
              const seqBefore = processor.seq;
              const sampleCursorBefore = processor.sampleCursor;
              sandbox.currentFrame = processor.lastRenderFrame;
              const accepted = processor.process(quantum(0.9));
              finalPlayoutDuplicateSnapshot = {
                accepted,
                sourceStartCount,
                sourceEndCount,
                duplicateRenderFrameCount: processor.duplicateRenderFrameCount,
                pendingLengthBefore,
                pendingLengthAfter: processor.pendingLength,
                seqBefore,
                seqAfter: processor.seq,
                sampleCursorBefore,
                sampleCursorAfter: processor.sampleCursor,
              };
            };
          }
          if (options.exerciseTransientGapDuringDownlink === true) {
            assert.notEqual(realProcessorHarness, null);
            const { processor, quantum, sandbox } = realProcessorHarness;
            sandbox.currentFrame = processor.expectedRenderFrame;
            assert.equal(processor.process([[]]), true);
            sandbox.currentFrame += 128;
            assert.equal(processor.process(quantum()), true);
          }
          if (options.exerciseMonotonicOverlapDuringDownlink === true) {
            assert.notEqual(realProcessorHarness, null);
            const { processor, quantum, sandbox } = realProcessorHarness;
            sandbox.currentFrame = processor.expectedRenderFrame - 64;
            assert.equal(processor.process(quantum()), true);
          }
          if (options.exerciseDuplicateRenderFrameDuringDownlink === true) {
            assert.notEqual(realProcessorHarness, null);
            const { processor, quantum, sandbox } = realProcessorHarness;
            sandbox.currentFrame = processor.lastRenderFrame;
            assert.equal(processor.process(quantum()), true);
          }
          if (options.exerciseRenderRegressionDuringDownlink === true) {
            assert.notEqual(realProcessorHarness, null);
            const { processor, quantum, sandbox } = realProcessorHarness;
            sandbox.currentFrame = processor.lastRenderFrame - 64;
            assert.equal(processor.process(quantum()), false);
            concurrentFailureSnapshot = owner.status();
          }
          if (options.exerciseRenderStallDuringDownlink === true) {
            assert.notEqual(realProcessorHarness, null);
            const { processor, quantum, sandbox } = realProcessorHarness;
            sandbox.currentFrame = processor.lastRenderFrame;
            for (let duplicate = 0; duplicate < 8; duplicate += 1) {
              assert.equal(processor.process(quantum()), true);
            }
            assert.equal(processor.process(quantum()), false);
            concurrentFailureSnapshot = owner.status();
          }
          socket.pumpDownlink();
        }
      });
      void openTask.catch(() => undefined);
      socketOpenTasks.push(openTask);
      return socket;
    }),
    request: (request = async (method, params, transportOptions) => {
      calls.push([method, params]);
      requestOptions.push([method, transportOptions]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        activationCount += 1;
        const binding = makeUplinkBinding(params, activationCount);
        const path = '/ws/live-voice/media';
        if (activationCount === 2 && options.failSecondCaptureWithMute === true) {
          environment.track.muted = true;
          environment.track.emit('mute');
          concurrentFailureSnapshot = owner.status();
          for (let turn = 0; turn < 100 && !environment.contexts.every(context => context.state === 'closed'); turn += 1) {
            await new Promise(resolve => setImmediate(resolve));
          }
          concurrentAudioReleased = environment.contexts.every(context => context.state === 'closed');
        }
        if (activationCount === 2 && options.closeSecondCaptureWhilePending === true) {
          concurrentClosePromise = owner.close();
          concurrentCloseSnapshot = owner.status();
          for (let turn = 0; turn < 100 && !environment.contexts.every(context => context.state === 'closed'); turn += 1) {
            await new Promise(resolve => setImmediate(resolve));
          }
          concurrentCloseAudioReleased = environment.contexts.every(context => context.state === 'closed');
        }
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: `media-subject-${activationCount}`,
          endpoint_path: path,
          media_ticket: `${String(activationCount).padStart(32, 'U')}VVVVVVVVVVV`,
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          end_of_turn:
            options.negotiatedEot === true
              ? {
                  status: 'active',
                  capability_version: 'media.end_of_turn.v1',
                  detector: 'server_vad',
                  create_response: false,
                  interrupt_response: false,
                }
              : MANUAL_EOT_FALLBACK,
          ...(options.streamingRecognition === true
            ? {
                streaming_recognition: true,
                streaming_degradation: null,
              }
            : {}),
          binding,
          privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
        };
      }
      if (method === 'live_voice.speech.recognize_streaming_result') {
        return streamingRecognitionResult(params, 'duplex streaming text');
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
                alternatives: [{ raw_text: 'duplex text', display_text: 'duplex text', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'stt-test',
            },
            voice_commit_receipt: 'voice-receipt-duplex-1',
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
        receiptSubjectId = `media-subject-${activationCount}`;
        const path = '/ws/live-voice/media';
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
              frame_count: options.streamingDownlink === true ? null : downlinkFrameCount,
              delivery: 'dedicated_media_downlink',
              endpoint_path: path,
              media_ticket: 'D'.repeat(43),
              subprotocol: 'live-voice.media.v1',
              ticket_ttl_ms: 30_000,
              binding: downlinkBinding,
              max_pending_frames: 8,
              max_pending_bytes: 131_072,
              streaming: options.streamingDownlink === true,
              degradation_reason: options.downlinkDegradationReason ?? null,
            },
            provider: {
              provider_id: 'provider-test',
              implementation_class: 'formal',
              fallback_from: null,
              model: 'tts-test',
              voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD) {
        assert.equal(params.subject_id, receiptSubjectId);
        assert.equal(params.rendered_chunks, downlinkFrameCount);
        return {
          status: 'media_playout_acknowledged',
          reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
          receipt_id: 'media-playout-duplex-1',
          duplex_media_observed: options.serverDuplexMediaObserved ?? true,
          ...params,
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        if (params.subject_id === 'media-subject-2' && secondMediaCloseFailures > 0) {
          secondMediaCloseFailures -= 1;
          throw { code: 'WS_NOT_READY' };
        }
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    }),
  });

  await startCaptureWithFirstFrame(owner, environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
  }, options.pauseForNotificationBeforePlayout === true
    ? { samples: new Float32Array(960) }
    : {});
  if (options.pauseForNotificationBeforePlayout === true) {
    notificationPausedFrameHandler = environment.worklet.port.onmessage;
    notificationPauseOutcome = await owner.pauseIdleCaptureForNotification();
  } else {
    await owner.stopAndRecognize();
  }
  const capturingBeforeConcurrent = statuses.filter(status => status === 'capturing').length;
  const priorWorklet = environment.worklet;
  const playing = owner.playAgentText({
    response,
    unit_id: 'unit-duplex-1',
    text: options.agentText ?? 'duplex Agent response',
    ...(options.captureDuringPlayout === false ? { capture_during_playout: false } : {}),
  });
  void playing.catch(() => undefined);
  if (options.sendSecondFrame !== false) {
    if (options.deferSuccessorCaptureUntilAfterPlayout === true) {
      await finalDownlinkAckObserved;
      // The browser route closes the downlink on a bounded detach retry before
      // Product P1 is allowed to create the deferred successor capture.
      await new Promise(resolve => setTimeout(resolve, 50));
      await sendFirstFrameToNextWorklet(environment, priorWorklet);
    } else if (options.useRealProcessorForSecondCapture === true) {
      for (let turn = 0; turn < 100 && (environment.worklet === priorWorklet || typeof environment.worklet?.port.onmessage !== 'function'); turn += 1) {
        await new Promise(resolve => setImmediate(resolve));
      }
      assert.notEqual(environment.worklet, priorWorklet);
      realProcessorHarness = attachRealCaptureProcessor(environment.worklet);
      const { processor, quantum, sandbox } = realProcessorHarness;
      assert.equal(processor.process(quantum()), true);
      sandbox.currentFrame = 128;
      assert.equal(processor.process([[]]), true);
      sandbox.currentFrame = 256;
      assert.equal(processor.process([[]]), true);
      sandbox.currentFrame = 384;
      assert.equal(processor.process(quantum()), true);
      for (let index = 0; index < 5; index += 1) {
        sandbox.currentFrame += 128;
        assert.equal(processor.process(quantum()), true);
      }
    } else {
      await sendFirstFrameToNextWorklet(
        environment,
        priorWorklet,
        options.silentSuccessorCapture === true
          ? { samples: new Float32Array(960) }
          : {},
      );
      if (options.holdSecondCaptureFirstAckUntilNextFrame === true) {
        sendNextFrameFromCurrentWorklet(environment);
      }
    }
  }
  const activeCaptureFailureReason =
    typeof options.failSecondCaptureDuringDownlinkReason === 'string'
      ? options.failSecondCaptureDuringDownlinkReason
      : options.failSecondCaptureDuringDownlink === true
        ? 'input_gap_exceeded'
        : null;
  if (activeCaptureFailureReason !== null) {
    for (let turn = 0; turn < 500 && concurrentCaptureStartedCalls === 0; turn += 1) {
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    assert.equal(concurrentCaptureStartedCalls, 1);
    environment.worklet.port.onmessage?.({
      data: { kind: 'error', reason: activeCaptureFailureReason },
    });
    concurrentFailureSnapshot = owner.status();
  }
  if (options.closeDuringActivePlayout === true) {
    for (let turn = 0; turn < 500; turn += 1) {
      const downlink = sockets.find(socket => socket.serverBinding?.direction === 'downlink');
      if (owner.status().status === 'playing' && downlink !== undefined && environment.contexts[0].sourceStartCount > 0) break;
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    const uplink = sockets.find(socket => socket.serverBinding?.generation?.id === 'capture-2');
    const downlink = sockets.find(socket => socket.serverBinding?.direction === 'downlink');
    assert.equal(owner.status().status, 'playing');
    assert.ok(uplink);
    assert.ok(downlink);
    staleCaptureFrameHandler = environment.worklet.port.onmessage;
    staleUplinkMessageHandler = uplink.onmessage;
    staleDownlinkMessageHandler = downlink.onmessage;
    concurrentClosePromise = owner.close();
    concurrentCloseSnapshot = owner.status();
  }
  if (options.triggerBargeInEot === true) {
    const uplinkSocket = sockets.find(socket => socket.serverBinding?.generation?.id === 'capture-2');
    assert.ok(uplinkSocket);
    uplinkSocket.onmessage?.({
      data: serializeMediaControl({
        type: 'media.speech_start',
        capability_version: 'media.end_of_turn.v1',
        lease_id: uplinkSocket.serverBinding.lease_id,
        generation: uplinkSocket.serverBinding.generation.value,
        detector: 'server_vad',
        provider_start_ms: 100,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      }),
    });
    for (let turn = 0; turn < 100 && bargeInSpeechStartCalls === 0; turn += 1) {
      await new Promise(resolve => setTimeout(resolve, 5));
    }
    assert.equal(bargeInSpeechStartCalls, 1);
    assert.equal(bargeInStopped, true);
    uplinkSocket.onmessage?.({
      data: serializeMediaControl({
        type: 'media.end_of_turn',
        capability_version: 'media.end_of_turn.v1',
        lease_id: uplinkSocket.serverBinding.lease_id,
        generation: uplinkSocket.serverBinding.generation.value,
        detector: 'server_vad',
        speech_started_observed: true,
        provider_start_ms: 100,
        provider_end_ms: 700,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      }),
    });
    await Promise.resolve();
  }
  if (options.signalProviderSpeechStartBeforeOverlapDuration === true) {
    const uplinkSocket = sockets.find(socket => socket.serverBinding?.generation?.id === 'capture-2');
    assert.ok(uplinkSocket);
    uplinkSocket.onmessage?.({
      data: serializeMediaControl({
        type: 'media.speech_start',
        capability_version: 'media.end_of_turn.v1',
        lease_id: uplinkSocket.serverBinding.lease_id,
        generation: uplinkSocket.serverBinding.generation.value,
        detector: 'server_vad',
        provider_start_ms: 100,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      }),
    });
    await Promise.resolve();
  }
  if (options.exerciseSilentCaptureRotationDuringActivePlayout === true) {
    for (let turn = 0; turn < 500 && concurrentCaptureStartedCalls === 0; turn += 1) {
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    assert.equal(concurrentCaptureStartedCalls, 1);
    const rotatingWorklet = environment.worklet;
    const retainedFrameHandler = rotatingWorklet.port.onmessage;
    assert.equal(typeof retainedFrameHandler, 'function');
    const samples = new Float32Array(960).fill(
      options.localEnergyDuringOverlapRotation === true ? 0.125 : 0,
    );
    const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
    environment.nextWorkletFirstFrameSamples = samples;
    retainedFrameHandler({
      data: {
        kind: 'frame',
        capture_generation: rotatingWorklet.captureGeneration,
        seq: 1,
        sample_rate_hz: 48_000,
        sample_cursor: 960,
        context_time_s: 0.02,
        samples,
      },
    });
    for (let turn = 0; turn < 500; turn += 1) {
      if (sockets.some(socket => socket.serverBinding?.direction === 'downlink')) break;
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    assert.equal(
      sockets.some(socket => socket.serverBinding?.direction === 'downlink'),
      true,
      `long playout did not establish its downlink before overlap rotation: status=${JSON.stringify(owner.status())} sockets=${sockets.map(socket => `${socket.serverBinding?.direction ?? 'none'}:${socket.sent.filter(value => typeof value !== 'string').length}`).join(',')} methods=${calls.map(([method]) => method).join(',')}`,
    );
    for (let seq = 2; seq < frameCount; seq += 1) {
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: rotatingWorklet.captureGeneration,
          seq,
          sample_rate_hz: 48_000,
          sample_cursor: seq * 960,
          context_time_s: seq * 0.02,
          samples,
        },
      });
      if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
    }
    const rotatedUplink = sockets.find(
      socket => socket.serverBinding?.generation?.id === 'capture-2',
    );
    assert.ok(rotatedUplink);
    if (options.signalProviderSpeechStartDuringOverlapRotation === true) {
      rotatedUplink.onmessage?.({
        data: serializeMediaControl({
          type: 'media.speech_start',
          capability_version: 'media.end_of_turn.v1',
          lease_id: rotatedUplink.serverBinding.lease_id,
          generation: rotatedUplink.serverBinding.generation.value,
          detector: 'server_vad',
          provider_start_ms: 250,
          timing_basis: 'provider_time',
          timing_provenance: 'adapter_derived',
          create_response: false,
          interrupt_response: false,
          business_cancel_count_delta: 0,
        }),
      });
      for (let turn = 0; turn < 500 && owner.status().status !== 'failed'; turn += 1) {
        await new Promise(resolve => setImmediate(resolve));
      }
      overlapRotationRaceSnapshot = {
        status: owner.status(),
        activation_count: activationCount,
      };
    } else {
    for (let turn = 0; turn < 3_500 && (activationCount !== 3 || environment.worklet === rotatingWorklet); turn += 1) {
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    assert.equal(
      activationCount,
      3,
      `silent overlap did not rotate: status=${JSON.stringify(owner.status())} methods=${calls.map(([method]) => method).join(',')}`,
    );
    for (let turn = 0; turn < 500; turn += 1) {
      if (
        calls.some(
          ([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD
            && params.subject_id === 'media-subject-2',
        )
      ) break;
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    captureRotationSnapshot = {
      old_frame_count: rotatedUplink.sent.filter(value => typeof value !== 'string').length,
      status: owner.status(),
      old_authority_closed: calls.some(
        ([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD
          && params.subject_id === 'media-subject-2',
      ),
    };
    if (options.signalStaleProviderSpeechStartAfterOverlapRotation === true) {
      const callsBefore = calls.length;
      const activationCountBefore = activationCount;
      rotatedUplink.onmessage?.({
        data: serializeMediaControl({
          type: 'media.speech_start',
          capability_version: 'media.end_of_turn.v1',
          lease_id: rotatedUplink.serverBinding.lease_id,
          generation: rotatedUplink.serverBinding.generation.value,
          detector: 'server_vad',
          provider_start_ms: 200,
          timing_basis: 'provider_time',
          timing_provenance: 'adapter_derived',
          create_response: false,
          interrupt_response: false,
          business_cancel_count_delta: 0,
        }),
      });
      await Promise.resolve();
      staleSpeechStartSnapshot = {
        status: owner.status(),
        calls_delta: calls.length - callsBefore,
        activation_count_delta: activationCount - activationCountBefore,
        barge_in_speech_start_calls: bargeInSpeechStartCalls,
      };
    }
    const downlinkSocket = sockets.find(
      socket => socket.serverBinding?.direction === 'downlink',
    );
    assert.ok(downlinkSocket);
    downlinkSocket.onmessage?.({
      data: serializeMediaControl({
        type: 'media.detach',
        lease_id: downlinkSocket.serverBinding.lease_id,
        generation: downlinkSocket.serverBinding.generation.value,
        reason_id: 'MEDIA_LOCAL_CLOSE',
        through_seq: downlinkFramesToSend - 1,
        business_cancel_count_delta: 0,
      }),
    });
    }
  }
  if (options.deferSourceEndsUntilTransportAck === true) {
    let downlinkSocket = null;
    for (let turn = 0; turn < 200; turn += 1) {
      downlinkSocket = sockets.find(socket => socket.serverBinding?.direction === 'downlink') ?? null;
      if ((downlinkSocket?.downlinkNextSeq ?? 0) >= Math.min(downlinkFrameCount, 8)) break;
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    await new Promise(resolve => setTimeout(resolve, 20));
    transportAckBeforeRenderSnapshot = {
      downlinkAckedSeq: downlinkSocket?.downlinkAckedSeq ?? null,
      downlinkNextSeq: downlinkSocket?.downlinkNextSeq ?? null,
      sourceStartCount: environment.contexts[0].sourceStartCount,
      sourceEndCount: environment.contexts[0].sourceEndCount,
    };
    environment.contexts[0].deferSourceEnds = false;
    environment.contexts[0].releaseSourceEnds();
  }
  if (options.exerciseCaptureDurationBeforeReceipt === true) {
    await finalDownlinkAckObserved;
    if (options.deferCaptureDurationUntilDetachWait === true) {
      // Let playAgentText consume the rendered Promise and enter its held
      // downlink-detach wait while the settling playout remains authoritative.
      await new Promise(resolve => setImmediate(resolve));
    }
    const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
    const samples = new Float32Array(960).fill(0.125);
    const retainedFrameHandler = environment.worklet.port.onmessage;
    assert.equal(typeof retainedFrameHandler, 'function');
    for (let seq = 1; seq < frameCount; seq += 1) {
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: environment.worklet.captureGeneration,
          seq,
          sample_rate_hz: 48_000,
          sample_cursor: seq * 960,
          context_time_s: seq * 0.02,
          samples,
        },
      });
    }
    captureDurationBoundarySnapshot = owner.status();
    // The 30-second budget now bounds the authoritative utterance from its
    // provider speech-start (successor frame index 1), not the lease age, so
    // the exact failure lands one frame past the former lease-age bound.
    let failedSeq = frameCount;
    for (; failedSeq <= frameCount + 2; failedSeq += 1) {
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: environment.worklet.captureGeneration,
          seq: failedSeq,
          sample_rate_hz: 48_000,
          sample_cursor: failedSeq * 960,
          context_time_s: failedSeq * 0.02,
          samples,
        },
      });
      if (owner.status().status !== 'playing') break;
    }
    concurrentFailureSnapshot = owner.status();
    const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
    captureDurationLateFrameUplinkCount = uplinkSocket.sent.filter(value => typeof value !== 'string').length;
    // Re-enter the retained callback in the same stack after #fail has latched
    // cleanup, then again after cleanup. Neither stale frame may reach uplink.
    retainedFrameHandler({
      data: {
        kind: 'frame',
        capture_generation: environment.worklet.captureGeneration,
        seq: failedSeq + 1,
        sample_rate_hz: 48_000,
        sample_cursor: (failedSeq + 1) * 960,
        context_time_s: (failedSeq + 1) * 0.02,
        samples,
      },
    });
    assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, captureDurationLateFrameUplinkCount);
    for (let turn = 0; turn < 100; turn += 1) {
      await new Promise(resolve => setImmediate(resolve));
      if (owner.status().status === 'failed') break;
    }
    retainedFrameHandler({
      data: {
        kind: 'frame',
        capture_generation: environment.worklet.captureGeneration,
        seq: failedSeq + 2,
        sample_rate_hz: 48_000,
        sample_cursor: (failedSeq + 2) * 960,
        context_time_s: (failedSeq + 2) * 0.02,
        samples,
      },
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, captureDurationLateFrameUplinkCount);
  }
  let playError = null;
  let playoutSettleTimer = null;
  try {
    await (options.requireBoundedPlayoutSettlement === true
      ? Promise.race([
          playing,
          new Promise((_resolve, reject) => {
            playoutSettleTimer = setTimeout(() => reject(new Error('formal P1 playout did not settle after an early downlink detach')), 500);
          }),
        ])
      : playing);
  } catch (error) {
    playError = error;
  } finally {
    if (playoutSettleTimer !== null) clearTimeout(playoutSettleTimer);
  }
  if (playError === null && options.exercisePostReceiptCaptureAdvance === true) {
    assert.notEqual(realProcessorHarness, null);
    const { processor, quantum, sandbox } = realProcessorHarness;
    for (let index = 0; index < 8; index += 1) {
      sandbox.currentFrame = processor.expectedRenderFrame;
      assert.equal(processor.process(quantum(0.625)), true);
    }
  }
  if (playError === null && options.exerciseRenderStallAfterReceipt === true) {
    assert.notEqual(realProcessorHarness, null);
    postReceiptStatusBeforeFailure = owner.status();
    const { processor, quantum, sandbox } = realProcessorHarness;
    const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
    postReceiptSourceStartsBeforeFailure = environment.contexts[0].sourceStartCount;
    sandbox.currentFrame = processor.expectedRenderFrame;
    assert.equal(processor.process(quantum()), true);
    assert.equal(processor.duplicateRenderFrameCount, 0);
    postReceiptUplinkFramesBeforeFailure = uplinkSocket.sent.filter(value => typeof value !== 'string').length;
    sandbox.currentFrame = processor.lastRenderFrame;
    for (let duplicate = 0; duplicate < 8; duplicate += 1) {
      assert.equal(processor.process(quantum()), true);
    }
    assert.equal(processor.process(quantum()), false);
    concurrentFailureSnapshot = owner.status();
    for (let turn = 0; turn < 100 && owner.status().status !== 'failed'; turn += 1) {
      await new Promise(resolve => setImmediate(resolve));
    }
  }
  if (playError === null && (options.exerciseCaptureDurationAfterReceipt === true || options.stopAtCaptureDurationBoundaryAfterReceipt === true)) {
    postReceiptStatusBeforeFailure = owner.status();
    const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
    const samples = new Float32Array(960).fill(0.125);
    const retainedFrameHandler = environment.worklet.port.onmessage;
    assert.equal(typeof retainedFrameHandler, 'function');
    if (options.exerciseCaptureDurationAfterReceipt === true) {
      // Without an authoritative utterance the successor lease now rotates
      // transparently, so anchor this duration-failure journey to a real
      // provider speech-start: the utterance budget expires one frame past
      // the former lease-age bound. Requires the negotiated EOT capability.
      const speechStartUplink = sockets.find(socket => socket.serverBinding?.generation?.id === 'capture-2');
      assert.ok(speechStartUplink);
      speechStartUplink.onmessage?.({
        data: serializeMediaControl({
          type: 'media.speech_start',
          capability_version: 'media.end_of_turn.v1',
          lease_id: speechStartUplink.serverBinding.lease_id,
          generation: speechStartUplink.serverBinding.generation.value,
          detector: 'server_vad',
          provider_start_ms: 150,
          timing_basis: 'provider_time',
          timing_provenance: 'adapter_derived',
          create_response: false,
          interrupt_response: false,
          business_cancel_count_delta: 0,
        }),
      });
      await Promise.resolve();
    }
    for (let seq = 1; seq < frameCount; seq += 1) {
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: environment.worklet.captureGeneration,
          seq,
          sample_rate_hz: 48_000,
          sample_cursor: seq * 960,
          context_time_s: seq * 0.02,
          samples,
        },
      });
    }
    captureDurationBoundarySnapshot = owner.status();
    if (options.stopAtCaptureDurationBoundaryAfterReceipt === true) {
      captureDurationBoundaryRecognition = await owner.stopAndRecognize();
    } else {
      let failedSeq = frameCount;
      for (; failedSeq <= frameCount + 2; failedSeq += 1) {
        retainedFrameHandler({
          data: {
            kind: 'frame',
            capture_generation: environment.worklet.captureGeneration,
            seq: failedSeq,
            sample_rate_hz: 48_000,
            sample_cursor: failedSeq * 960,
            context_time_s: failedSeq * 0.02,
            samples,
          },
        });
        if (owner.status().status !== 'capturing') break;
      }
      concurrentFailureSnapshot = owner.status();
      const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
      captureDurationLateFrameUplinkCount = uplinkSocket.sent.filter(value => typeof value !== 'string').length;
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: environment.worklet.captureGeneration,
          seq: failedSeq + 1,
          sample_rate_hz: 48_000,
          sample_cursor: (failedSeq + 1) * 960,
          context_time_s: (failedSeq + 1) * 0.02,
          samples,
        },
      });
      assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, captureDurationLateFrameUplinkCount);
      for (let turn = 0; turn < 100; turn += 1) {
        await new Promise(resolve => setImmediate(resolve));
        if (owner.status().status === 'failed') break;
      }
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: environment.worklet.captureGeneration,
          seq: failedSeq + 2,
          sample_rate_hz: 48_000,
          sample_cursor: (failedSeq + 2) * 960,
          context_time_s: (failedSeq + 2) * 0.02,
          samples,
        },
      });
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, captureDurationLateFrameUplinkCount);
    }
  }
  if (concurrentClosePromise !== null) await concurrentClosePromise;
  await Promise.all(socketOpenTasks);

  return {
    owner,
    calls,
    requestOptions,
    statuses,
    statusSnapshots,
    sockets,
    activationCount,
    playError,
    capturingBeforeConcurrent,
    concurrentFailureSnapshot,
    concurrentAudioReleased,
    concurrentCloseSnapshot,
    concurrentCloseAudioReleased,
    realProcessorHarness,
    finalPlayoutDuplicateSnapshot,
    postReceiptStatusBeforeFailure,
    postReceiptSourceStartsBeforeFailure,
    postReceiptUplinkFramesBeforeFailure,
    captureDurationBoundarySnapshot,
    captureDurationBoundaryRecognition,
    captureDurationLateFrameUplinkCount,
    activationCountAtFinalDownlinkAck,
    transportAckBeforeRenderSnapshot,
    concurrentCaptureStartedCalls,
    secondCaptureAckStillPendingAtReady,
    bargeInSpeechStartCalls,
    bargeInEotCalls,
    bargeInStopped,
    captureRotationSnapshot,
    overlapRotationRaceSnapshot,
    staleSpeechStartSnapshot,
    notificationPauseOutcome,
    notificationPausedFrameHandler,
    staleCaptureFrameHandler,
    staleUplinkMessageHandler,
    staleDownlinkMessageHandler,
    socketFactory,
    request,
    response,
    environment,
  };
}

async function runFirstRecoveredRetry(journey, afterCaptureStarted = async () => undefined) {
  const statuses = [];
  journey.environment.deferSourceEnds = false;
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    on_status: status => statuses.push(status),
    audio_environment: journey.environment,
    socket_factory: journey.socketFactory,
    request: journey.request,
  });
  const capture = {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-retry-1',
    activation_generation: 8,
    locale: 'zh-CN',
  };
  await startCaptureWithFirstFrame(owner, journey.environment, capture);
  await afterCaptureStarted(owner);
  const recognition = await owner.stopAndRecognize();
  const priorWorklet = journey.environment.worklet;
  const playing = owner.playAgentText({
    response: journey.response,
    unit_id: 'unit-duplex-1',
    text: 'first retry response',
  });
  void playing.catch(() => undefined);
  await sendFirstFrameToNextWorklet(journey.environment, priorWorklet);
  await playing;
  return { owner, recognition, statuses };
}

test('formal P1 Task announcement playout suppresses self-capturing overlap before a fresh resume', async () => {
  const journey = await runConcurrentCaptureJourney({
    pauseForNotificationBeforePlayout: true,
    captureDuringPlayout: false,
    sendSecondFrame: false,
  });

  assert.equal(journey.playError, null);
  assert.equal(journey.notificationPauseOutcome, 'paused');
  assert.equal(journey.concurrentCaptureStartedCalls, 0);
  assert.equal(journey.activationCount, 1);
  assert.deepEqual(journey.owner.status(), { status: 'recognized', reason: null });
  assert.equal(
    journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length,
    1,
  );
  const priorWorklet = journey.environment.worklet;
  const resumed = journey.owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
  });
  await sendFirstFrameToNextWorklet(journey.environment, priorWorklet);
  await resumed;
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length,
    2,
  );
  await journey.owner.close();
});

test('formal P1 preserves the streaming finalize budget for initial and successor captures', async () => {
  const journey = await runConcurrentCaptureJourney({ streamingRecognition: true });

  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  const successorRecognition = await journey.owner.stopAndRecognize();
  assert.deepEqual(successorRecognition, {
    text: 'duplex streaming text',
    voice_commit_receipt: 'streaming-voice-receipt-1',
  });
  assert.deepEqual(
    journey.requestOptions
      .filter(([method]) => method === 'live_voice.speech.recognize_streaming_result')
      .map(([, options]) => options),
    [
      { timeoutMs: 38_000, signal: undefined },
      { timeoutMs: 38_000, signal: undefined },
    ],
  );
  assert.equal(
    journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length,
    0,
  );
  await journey.owner.close();
});

test('formal P1 initial and successor Speech adapters forward the exact request options object', () => {
  const exactSpeechRequestAdapter =
    /request: async <T = unknown>\(\s*method: string,\s*params\?: Record<string, unknown>,\s*options\?: Readonly<\{ timeoutMs\?: number; signal\?: AbortSignal \}>,\s*\) => \(await this\.#request\(method, params \?\? \{\}, options\)\) as T,/g;

  assert.equal(
    [...productP1VoiceRouteSource.matchAll(exactSpeechRequestAdapter)].length,
    2,
    'initial and successor Gateway Speech adapters must pass the same timeout/signal options object unchanged',
  );
});

test('formal P1 L0 success waits for the authoritative playout receipt and retains render time', () => {
  assert.match(
    productP1VoiceRouteSource,
    /await this\.#acknowledgePlayout\(pendingPlayout\);[\s\S]*?this\.#l0Record\([\s\S]*?'playout_completed'[\s\S]*?'success'[\s\S]*?completed/s,
  );
  assert.doesNotMatch(
    productP1VoiceRouteSource,
    /#observePlayout\([\s\S]*?this\.#l0Record\('playout_completed'[\s\S]*?#observeBrowserFirstFrame/s,
  );
  assert.match(
    productP1VoiceRouteSource,
    /#stageL0PlayoutCompletion[\s\S]*?renderClock\?\.observedAt \?\? new Date\(\)\.toISOString\(\)[\s\S]*?monotonicMs[\s\S]*?elapsedMs/s,
  );
  assert.match(
    productP1VoiceRouteSource,
    /renderMonotonicMs = monotonicNowMs\(\);[\s\S]*?lastRenderedClock = Object\.freeze[\s\S]*?throughSeq: event\.through_seq[\s\S]*?#stageL0PlayoutCompletion\(pending\.response, renderClock\)/s,
  );
});

test('formal P1 L0 records the first exact browser route failure before cleanup', () => {
  assert.match(
    productP1VoiceRouteSource,
    /if \(this\.#failureCleanupPromise === null\) \{[\s\S]*?this\.#l0Record\('browser_failure', failureResponse, undefined, 'failure'\);[\s\S]*?this\.#failureCleanupReason = failureReason;/,
  );
});

test('formal P1 L0 records uplink send only after the dedicated socket drains it', () => {
  assert.equal(
    [...productP1VoiceRouteSource.matchAll(/on_uplink_frame_sent:/g)].length,
    2,
  );
  assert.match(
    productP1VoiceRouteSource,
    /#observeUplinkFrameSent\(.*?route !== this\.#route.*?#l0LastFrameSentClock = l0ClockNow\(\)/s,
  );
  assert.doesNotMatch(
    productP1VoiceRouteSource,
    /#mediaSentFrames \+= 1;\s*this\.#l0LastFrameSentClock/s,
  );
});

test('formal P1 installs measurement hot-path hooks only on an L0 opt-in page', () => {
  assert.match(
    productP1VoiceRouteSource,
    /#l0Available = browserL0Available\(\);/,
  );
  assert.match(
    productP1VoiceRouteSource,
    /\.\.\.\(this\.#l0Available[\s\S]*?onPlayoutScheduled:/,
  );
  assert.equal(
    [...productP1VoiceRouteSource.matchAll(/\.\.\.\(this\.#l0Available\s*\?\s*\{\s*on_uplink_frame_sent:/g)].length,
    2,
  );
  assert.match(
    productP1VoiceRouteSource,
    /#l0Binding\([\s\S]*?!this\.#l0Available[\s\S]*?return null;/,
  );
  assert.match(
    productP1VoiceRouteSource,
    /#stageL0PlayoutCompletion\([\s\S]*?if \(!this\.#l0Available\) return;/,
  );
  assert.match(
    productP1VoiceRouteSource,
    /if \(this\.#l0Available\) \{[\s\S]*?renderMonotonicMs = monotonicNowMs\(\);[\s\S]*?pending\.lastRenderedClock = Object\.freeze/,
  );
  assert.equal(
    [...productP1VoiceRouteSource.matchAll(/if \(this\.#l0Available && (?:frame|chunk)\.seq === 0\) \{\s*this\.#observeBrowserFirstFrame/g)].length,
    2,
  );
});

test('formal P1 L0 barge-in clocks bracket the exact local playout fence', () => {
  assert.match(
    productP1VoiceRouteSource,
    /requestedClock = this\.#l0Available \? l0ClockNow\(\) : null;.*?stopPlayoutExact\(.*?local_fence_established.*?if \(requestedClock !== null\).*?#l0Record\('barge_in'.*?#l0Record\(.*?'fence_cancel_completion'/s,
  );
});

test('formal P1 L0 confirms WebAudio start and retains the scheduled audio clock', () => {
  assert.match(
    productP1VoiceRouteSource,
    /confirmStarted[\s\S]*?event\.has_started\(\)[\s\S]*?scheduled_start_clock[\s\S]*?'webaudio_actually_started'/s,
  );
  assert.match(
    productP1VoiceRouteSource,
    /confirmStarted\(L0_WEBAUDIO_START_CONFIRMATION_RETRIES\)/,
  );
});

test('formal P1 timestamps successor readiness inside the actual ready transition', () => {
  assert.match(
    productP1VoiceRouteSource,
    /#successorCaptureReadiness = 'ready';[\s\S]*?#l0Record\('successor_capture_ready', response\);[\s\S]*?return Object\.freeze\(\{ ready: true/s,
  );
  assert.doesNotMatch(
    productP1VoiceRouteSource,
    /await capturePreparation;[\s\S]{0,240}#l0Record\('successor_capture_ready'/s,
  );
});

test('formal P1 dedicated downlink ACKs scheduled audio and receipts only rendered audio', async () => {
  const journey = await runConcurrentCaptureJourney({ synchronousDownlinkDetachAfterFinalRender: true });
  const { owner, calls, sockets, activationCount, playError, environment, statusSnapshots } = journey;

  assert.equal(playError, null);
  assert.equal(owner.status().status, 'capturing');
  assert.equal(journey.concurrentCaptureStartedCalls, 1);
  assert.equal(activationCount, 2);
  assert.equal(environment.contexts.length, 1);
  assert.equal(environment.contexts[0].state, 'running');
  assert.ok(statusSnapshots.find(snapshot => snapshot.status === 'playing')?.source_start_count > 0);
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  assert.ok(downlinkSocket);
  const downlinkControls = downlinkSocket.sent.filter(value => typeof value === 'string').map(JSON.parse);
  assert.equal(downlinkControls.filter(control => control.type === 'media.ack').length, 1);
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1'));
  await owner.close();
  assert.equal(environment.contexts[0].state, 'closed');
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
});

test('server speech-start/EOT during playout triggers barge-in without Task mutation', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    triggerBargeInEot: true,
    holdDownlinkDetachAfterFinalRender: true,
    deferSourceEndsUntilTransportAck: true,
  });
  assert.equal(journey.bargeInSpeechStartCalls, 1);
  assert.equal(journey.bargeInEotCalls, 0);
  assert.equal(journey.bargeInStopped, true);
  assert.equal(journey.playError, null);
  assert.equal(journey.owner.status().status, 'capturing');
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('task.cancel') || method.includes('task.mutate'),
    ),
    false,
  );
  const downlink = journey.sockets.find(socket => socket.serverBinding?.direction === 'downlink');
  if (downlink !== undefined) {
    const controls = downlink.sent.filter(value => typeof value === 'string').map(JSON.parse);
    const detach = controls.find(control => control.type === 'media.detach');
    if (detach !== undefined) assert.equal(detach.business_cancel_count_delta, 0);
  }
  await journey.owner.close();
});

test('server speech-start/EOT interrupts an answer estimated beyond twenty seconds without Task mutation', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    triggerBargeInEot: true,
    holdDownlinkDetachAfterFinalRender: true,
    deferSourceEndsUntilTransportAck: true,
    agentText:
      '实时语音系统会依次完成录音采集、前端处理、语音识别、Agent 推理、语音合成和浏览器播放。'.repeat(8),
  });
  assert.equal(journey.activationCount, 2);
  assert.equal(journey.bargeInSpeechStartCalls, 1);
  assert.equal(journey.bargeInEotCalls, 0);
  assert.equal(journey.bargeInStopped, true);
  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('task.cancel') || method.includes('task.mutate'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 advances the eight-frame downlink window before browser render completion', async () => {
  const journey = await runConcurrentCaptureJourney({
    downlinkFrameCount: 9,
    deferSourceEndsUntilTransportAck: true,
  });
  const { owner, playError, transportAckBeforeRenderSnapshot } = journey;

  assert.equal(playError, null);
  assert.deepEqual(transportAckBeforeRenderSnapshot, {
    downlinkAckedSeq: 8,
    downlinkNextSeq: 9,
    sourceStartCount: 9,
    sourceEndCount: 0,
  });
  await owner.close();
});

test('formal P1 starts one bounded successor capture without gating a long-answer downlink', async () => {
  const journey = await runConcurrentCaptureJourney({
    agentText:
      '实时语音系统会依次完成录音采集、前端处理、语音识别、Agent 推理、语音合成和浏览器播放。'.repeat(8),
    downlinkFrameCount: 3,
  });
  const { owner, calls, activationCount, activationCountAtFinalDownlinkAck, playError, environment } = journey;

  assert.equal(playError, null);
  assert.equal(activationCountAtFinalDownlinkAck, 1);
  assert.equal(activationCount, 2);
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON), false);
  assert.equal(environment.contexts[0].sourceEndCount, 3);
  await owner.close();
});

test('formal P1 rotates thirty seconds of silent overlap during active long playout without dropping the boundary frame', async () => {
  const journey = await runConcurrentCaptureJourney({
    agentText:
      '实时语音系统会持续朗读较长回答，同时保持受控监听并轮换静默的上行媒体租约。'.repeat(8),
    streamingDownlink: true,
    downlinkFrameCount: 16,
    downlinkFramesToSend: 16,
    deferSourceEndsUntilTransportAck: true,
    holdDownlinkDetachAfterFinalRender: true,
    silentSuccessorCapture: true,
    exerciseSilentCaptureRotationDuringActivePlayout: true,
  });

  assert.equal(journey.playError, null);
  assert.equal(journey.activationCount, 3);
  assert.deepEqual(journey.captureRotationSnapshot, {
    old_frame_count: PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20,
    status: { status: 'playing', reason: null },
    old_authority_closed: true,
  });
  assert.equal(
    journey.calls.some(
      ([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
    ),
    false,
  );
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  await journey.owner.close();
});

test('formal P1 rotates TTS echo energy without provider speech-start and fences a stale prior-lease speech-start', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    agentText:
      '实时语音系统会持续朗读较长回答，同时只以当前媒体租约的权威语音开始事件保护真实用户讲话。'.repeat(8),
    streamingDownlink: true,
    downlinkFrameCount: 16,
    downlinkFramesToSend: 16,
    deferSourceEndsUntilTransportAck: true,
    holdDownlinkDetachAfterFinalRender: true,
    localEnergyDuringOverlapRotation: true,
    exerciseSilentCaptureRotationDuringActivePlayout: true,
    signalStaleProviderSpeechStartAfterOverlapRotation: true,
  });

  assert.equal(journey.playError, null);
  assert.equal(journey.activationCount, 3);
  assert.deepEqual(journey.captureRotationSnapshot, {
    old_frame_count: PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20,
    status: { status: 'playing', reason: null },
    old_authority_closed: true,
  });
  assert.deepEqual(journey.staleSpeechStartSnapshot, {
    status: { status: 'playing', reason: null },
    calls_delta: 0,
    activation_count_delta: 0,
    barge_in_speech_start_calls: 0,
  });
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  await journey.owner.close();
});

test('formal P1 fails closed at the overlap duration bound after current provider speech-start', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    holdDownlinkDetachAfterFinalRender: true,
    deferCaptureDurationUntilDetachWait: true,
    signalProviderSpeechStartBeforeOverlapDuration: true,
    exerciseCaptureDurationBeforeReceipt: true,
  });

  assert.notEqual(journey.playError, null);
  assert.deepEqual(journey.captureDurationBoundarySnapshot, { status: 'playing', reason: null });
  assert.deepEqual(journey.concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.deepEqual(journey.owner.status(), {
    status: 'failed',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.equal(journey.activationCount, 2);
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 0);
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 ignores a closed owner provider speech-start with zero side effects', async () => {
  const journey = await runConcurrentCaptureJourney({ negotiatedEot: true });
  const closedUplink = journey.sockets.find(
    socket => socket.serverBinding?.generation?.id === 'capture-2',
  );
  assert.ok(closedUplink);
  await journey.owner.close();
  const callsBefore = journey.calls.length;

  closedUplink.onmessage?.({
    data: serializeMediaControl({
      type: 'media.speech_start',
      capability_version: 'media.end_of_turn.v1',
      lease_id: closedUplink.serverBinding.lease_id,
      generation: closedUplink.serverBinding.generation.value,
      detector: 'server_vad',
      provider_start_ms: 300,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  await Promise.resolve();

  assert.deepEqual(journey.owner.status(), { status: 'closed', reason: null });
  assert.equal(journey.calls.length, callsBefore);
  assert.equal(journey.bargeInSpeechStartCalls, 0);
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
});

test('formal P1 protects a current provider speech-start after playout and bounds its utterance', async () => {
  const journey = await runConcurrentCaptureJourney({ negotiatedEot: true });
  const uplink = journey.sockets.find(
    socket => socket.serverBinding?.generation?.id === 'capture-2',
  );
  assert.ok(uplink);
  uplink.onmessage?.({
    data: serializeMediaControl({
      type: 'media.speech_start',
      capability_version: 'media.end_of_turn.v1',
      lease_id: uplink.serverBinding.lease_id,
      generation: uplink.serverBinding.generation.value,
      detector: 'server_vad',
      provider_start_ms: 400,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  // The utterance budget starts at the provider speech-start (successor frame
  // index 1), so the exact failure lands just past the former lease-age bound.
  await sendCaptureToDurationBoundary(
    journey.environment,
    new Float32Array(960),
    { exceed: true, extraFrames: 2 },
  );
  for (let turn = 0; turn < 200 && journey.owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(journey.owner.status(), {
    status: 'failed',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.equal(journey.activationCount, 2);
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 does not carry short-playout echo energy into later idle rotation', async () => {
  const journey = await runConcurrentCaptureJourney();
  const priorWorklet = await sendCaptureToDurationBoundary(
    journey.environment,
    new Float32Array(960),
  );
  for (let turn = 0; turn < 3_500 && journey.environment.worklet === priorWorklet; turn += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.notEqual(journey.environment.worklet, priorWorklet);
  assert.equal(
    journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length,
    3,
  );
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    journey.calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  await journey.owner.close();
});

test('formal P1 decays one post-playout energy frame and rotates the silent lease boundary', async () => {
  const journey = await runConcurrentCaptureJourney();
  const { owner, calls, environment } = journey;
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  const priorWorklet = environment.worklet;
  const handler = priorWorklet.port.onmessage;
  assert.equal(typeof handler, 'function');
  const frameAt = (seq, samples) => ({
    data: {
      kind: 'frame',
      capture_generation: priorWorklet.captureGeneration,
      seq,
      sample_rate_hz: 48_000,
      sample_cursor: seq * 960,
      context_time_s: seq * 0.02,
      samples,
    },
  });
  // One post-playout frame crosses the local energy floor (a TTS tail, echo
  // or environmental sound); the room then stays silent through the 30-second
  // lease boundary. The lease must rotate transparently with no visible error
  // and zero forbidden Agent/Tool/Task/history effects.
  environment.nextWorkletFirstFrameSamples = new Float32Array(960);
  handler(frameAt(1, new Float32Array(960).fill(0.125)));
  const silent = new Float32Array(960);
  const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
  for (let seq = 2; seq <= frameCount + 2; seq += 1) {
    handler(frameAt(seq, silent));
    if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
  }
  for (let turn = 0; turn < 3_500 && environment.worklet === priorWorklet; turn += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.notEqual(environment.worklet, priorWorklet);
  assert.equal(
    calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length,
    3,
  );
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  assert.equal(
    calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  const rotationDiagnostics = owner.captureDiagnostics();
  assert.equal(rotationDiagnostics.provider_speech_start_observed, false);
  assert.equal(rotationDiagnostics.actual_processing?.echo_cancellation, true);
  assert.equal(rotationDiagnostics.actual_processing?.noise_suppression, true);
  assert.equal(rotationDiagnostics.actual_processing?.auto_gain_control, true);
  await owner.close();
});

test('formal P1 defers the boundary rotation for recent local energy and rotates when it decays', async () => {
  const journey = await runConcurrentCaptureJourney();
  const { owner, calls, environment } = journey;
  const priorWorklet = environment.worklet;
  const handler = priorWorklet.port.onmessage;
  assert.equal(typeof handler, 'function');
  const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
  const silent = new Float32Array(960);
  const energetic = new Float32Array(960).fill(0.125);
  environment.nextWorkletFirstFrameSamples = new Float32Array(960);
  // Local energy lands just before the boundary. The rotation defers inside
  // its bounded grace and fires as soon as the recency hint decays; it must
  // not fail the lease.
  for (let seq = 1; seq <= frameCount + 110; seq += 1) {
    // A real worklet stops producing once the rotation stops its capture;
    // stop driving as soon as the rotation dispatches.
    if (owner.captureDiagnostics().rotation_in_flight || environment.worklet !== priorWorklet) break;
    const samples = seq >= frameCount - 6 && seq <= frameCount - 5 ? energetic : silent;
    handler({
      data: {
        kind: 'frame',
        capture_generation: priorWorklet.captureGeneration,
        seq,
        sample_rate_hz: 48_000,
        sample_cursor: seq * 960,
        context_time_s: seq * 0.02,
        samples,
      },
    });
    if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
  }
  for (let turn = 0; turn < 3_500 && environment.worklet === priorWorklet; turn += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.notEqual(environment.worklet, priorWorklet);
  assert.equal(
    calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length,
    3,
  );
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  for (let turn = 0; turn < 500; turn += 1) {
    if (calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2')) break;
    await new Promise(resolve => setTimeout(resolve, 1));
  }
  for (let turn = 0; turn < 200 && owner.captureDiagnostics().last_rotation?.completed !== true; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  const deferredRotation = owner.captureDiagnostics().last_rotation;
  assert.equal(deferredRotation?.completed, true);
  assert.equal(deferredRotation?.trigger, 'silent_boundary');
  assert.equal(deferredRotation?.at_frame_count > frameCount, true);
  await owner.close();
});

test('formal P1 rotates a lease with sustained unconfirmed energy at the bounded grace end', async () => {
  const journey = await runConcurrentCaptureJourney();
  const { owner, calls, environment } = journey;
  const priorWorklet = environment.worklet;
  const handler = priorWorklet.port.onmessage;
  assert.equal(typeof handler, 'function');
  const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
  const energetic = new Float32Array(960).fill(0.125);
  environment.nextWorkletFirstFrameSamples = new Float32Array(960);
  // Every frame crosses the local floor but the Provider never confirms
  // speech. Sustained unconfirmed energy must rotate at the bounded grace end
  // instead of expiring the lease.
  for (let seq = 1; seq <= frameCount + 110; seq += 1) {
    // A real worklet stops producing once the rotation stops its capture;
    // stop driving as soon as the rotation dispatches.
    if (owner.captureDiagnostics().rotation_in_flight || environment.worklet !== priorWorklet) break;
    handler({
      data: {
        kind: 'frame',
        capture_generation: priorWorklet.captureGeneration,
        seq,
        sample_rate_hz: 48_000,
        sample_cursor: seq * 960,
        context_time_s: seq * 0.02,
        samples: energetic,
      },
    });
    if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
  }
  for (let turn = 0; turn < 3_500 && environment.worklet === priorWorklet; turn += 1) {
    await new Promise(resolve => setTimeout(resolve, 1));
  }

  assert.notEqual(environment.worklet, priorWorklet);
  assert.equal(
    calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length,
    3,
  );
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  for (let turn = 0; turn < 500; turn += 1) {
    if (calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2')) break;
    await new Promise(resolve => setTimeout(resolve, 1));
  }
  for (let turn = 0; turn < 200 && owner.captureDiagnostics().last_rotation?.completed !== true; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }
  const graceRotation = owner.captureDiagnostics().last_rotation;
  assert.equal(graceRotation?.completed, true);
  assert.equal(graceRotation?.trigger, 'local_activity_grace_elapsed');
  assert.equal(graceRotation?.at_frame_count > frameCount, true);
  await owner.close();
});

test('formal P1 keeps an authoritative utterance alive past the lease bound and recognizes it', async () => {
  const journey = await runConcurrentCaptureJourney({ negotiatedEot: true });
  const { owner, calls, environment, sockets } = journey;
  const priorWorklet = environment.worklet;
  const handler = priorWorklet.port.onmessage;
  assert.equal(typeof handler, 'function');
  const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
  const silent = new Float32Array(960);
  const sendSilent = seq => handler({
    data: {
      kind: 'frame',
      capture_generation: priorWorklet.captureGeneration,
      seq,
      sample_rate_hz: 48_000,
      sample_cursor: seq * 960,
      context_time_s: seq * 0.02,
      samples: silent,
    },
  });
  for (let seq = 1; seq <= 800; seq += 1) {
    sendSilent(seq);
    if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
  }
  const uplink = sockets.find(socket => socket.serverBinding?.generation?.id === 'capture-2');
  assert.ok(uplink);
  uplink.onmessage?.({
    data: serializeMediaControl({
      type: 'media.speech_start',
      capability_version: 'media.end_of_turn.v1',
      lease_id: uplink.serverBinding.lease_id,
      generation: uplink.serverBinding.generation.value,
      detector: 'server_vad',
      provider_start_ms: 16_000,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  await Promise.resolve();
  // The utterance began late in the lease; its own 30-second budget keeps the
  // capture alive past the former lease-age bound without rotation.
  for (let seq = 801; seq <= frameCount + 200; seq += 1) {
    sendSilent(seq);
    if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.activationCount, 2);
  assert.equal(
    calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  const recognition = await owner.stopAndRecognize();
  assert.deepEqual(recognition, {
    text: 'duplex text',
    voice_commit_receipt: 'voice-receipt-duplex-1',
  });
  assert.deepEqual(owner.status(), { status: 'recognized', reason: null });
  const recognitionCalls = calls.filter(([method]) => method === 'live_voice.speech.recognize_batch');
  assert.equal(recognitionCalls.length, 2);
  // Batch fallback uploads the complete lease audio (the Speech client
  // requires recognition input to start at the first captured frame), so the
  // extended lease produces a WAV longer than the former 30-second ceiling.
  assert.equal(
    Buffer.from(recognitionCalls[1][1].audio.data_base64, 'base64').length,
    44 + (frameCount + 201) * 960 * 2,
  );
  await owner.close();
});

test('formal P1 aborts an in-flight overlap rotation when current provider speech-start arrives', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    streamingDownlink: true,
    downlinkFrameCount: 16,
    downlinkFramesToSend: 16,
    holdDownlinkDetachAfterFinalRender: true,
    exerciseSilentCaptureRotationDuringActivePlayout: true,
    signalProviderSpeechStartDuringOverlapRotation: true,
  });

  assert.notEqual(journey.playError, null);
  assert.deepEqual(journey.overlapRotationRaceSnapshot, {
    status: {
      status: 'failed',
      reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
    },
    activation_count: 2,
  });
  assert.deepEqual(journey.owner.status(), {
    status: 'failed',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 rotates consecutive silent idle captures and pauses without recognition for a notification', async () => {
  const journey = await runConcurrentCaptureJourney({ silentSuccessorCapture: true });
  const { owner, calls, environment, sockets } = journey;
  const frameCount = PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20;
  const silentSamples = new Float32Array(960);

  for (let cycle = 0; cycle < 2; cycle += 1) {
    const priorWorklet = environment.worklet;
    const retainedFrameHandler = priorWorklet.port.onmessage;
    assert.equal(typeof retainedFrameHandler, 'function');
    environment.nextWorkletFirstFrameSamples = silentSamples;
    for (let seq = 1; seq < frameCount; seq += 1) {
      retainedFrameHandler({
        data: {
          kind: 'frame',
          capture_generation: priorWorklet.captureGeneration,
          seq,
          sample_rate_hz: 48_000,
          sample_cursor: seq * 960,
          context_time_s: seq * 0.02,
          samples: silentSamples,
        },
      });
      if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
    }
    for (let turn = 0; turn < 3_500 && environment.worklet === priorWorklet; turn += 1) {
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    assert.notEqual(
      environment.worklet,
      priorWorklet,
      `silent idle cycle ${cycle + 1} did not rotate; status=${JSON.stringify(owner.status())}; activations=${calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length}; uplinks=${sockets
        .filter(socket => socket.serverBinding?.direction === 'uplink')
        .map(socket => `${socket.serverBinding.generation.id}:${socket.sent.filter(value => typeof value !== 'string').length}`)
        .join(',')}`,
    );
    const rotatedSubject = `media-subject-${cycle + 2}`;
    for (let turn = 0; turn < 500; turn += 1) {
      if (calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === rotatedSubject)) {
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    assert.equal(
      calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === rotatedSubject),
      true,
    );
    for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(owner.status(), { status: 'capturing', reason: null }, `auto=${environment.autoFirstFrameScheduled}/${environment.autoFirstFrameDelivered}; current-generation=${environment.worklet?.captureGeneration}; uplinks=${sockets
      .filter(socket => socket.serverBinding?.direction === 'uplink')
      .map(socket => `${socket.serverBinding.generation.id}:${socket.sent.filter(value => typeof value !== 'string').length}`)
      .join(',')}`);
  }

  const recognitionCallsBeforePause = calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length;
  assert.equal(await owner.pauseIdleCaptureForNotification(), 'paused');
  assert.deepEqual(owner.status(), { status: 'recognized', reason: null });
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, recognitionCallsBeforePause);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length, 4);
  assert.equal(
    calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  await owner.close();
});

test('formal P1 notification pause preserves a capture after real speech energy', async () => {
  const journey = await runConcurrentCaptureJourney();
  const worklet = journey.environment.worklet;
  assert.equal(typeof worklet?.port.onmessage, 'function');
  worklet.port.onmessage({
    data: {
      kind: 'frame',
      capture_generation: worklet.captureGeneration,
      seq: 1,
      sample_rate_hz: 48_000,
      sample_cursor: 960,
      context_time_s: 0.02,
      samples: new Float32Array(960).fill(0.25),
    },
  });
  const recognitionCallsBeforePause = journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length;

  assert.equal(await journey.owner.pauseIdleCaptureForNotification(), 'speech_active');
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, recognitionCallsBeforePause);
  await journey.owner.close();
});

test('formal P1 notification pause preserves current provider speech-start without capture side effects', async () => {
  const journey = await runConcurrentCaptureJourney({ negotiatedEot: true });
  const uplink = journey.sockets.find(
    socket => socket.serverBinding?.generation?.id === 'capture-2',
  );
  assert.ok(uplink);
  uplink.onmessage?.({
    data: serializeMediaControl({
      type: 'media.speech_start',
      capability_version: 'media.end_of_turn.v1',
      lease_id: uplink.serverBinding.lease_id,
      generation: uplink.serverBinding.generation.value,
      detector: 'server_vad',
      provider_start_ms: 500,
      timing_basis: 'provider_time',
      timing_provenance: 'adapter_derived',
      create_response: false,
      interrupt_response: false,
      business_cancel_count_delta: 0,
    }),
  });
  const worklet = journey.environment.worklet;
  const handler = worklet.port.onmessage;
  const callsBefore = journey.calls.length;
  const recognitionCallsBefore = journey.calls.filter(
    ([method]) => method === 'live_voice.speech.recognize_batch',
  ).length;

  assert.equal(await journey.owner.pauseIdleCaptureForNotification(), 'speech_active');
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.environment.worklet, worklet);
  assert.equal(worklet.port.onmessage, handler);
  assert.equal(journey.calls.length, callsBefore);
  assert.equal(
    journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length,
    recognitionCallsBefore,
  );
  await journey.owner.close();
});

test('formal P1 terminal announcement settles the paused lease and fences its stale capture callback', async () => {
  const journey = await runConcurrentCaptureJourney({
    pauseForNotificationBeforePlayout: true,
  });

  assert.equal(journey.notificationPauseOutcome, 'paused');
  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length,
    0,
  );
  assert.equal(
    journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length,
    1,
  );
  assert.ok(
    journey.calls.some(
      ([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD
        && params.subject_id === 'media-subject-1',
    ),
  );

  const callsBeforeStaleCallback = journey.calls.length;
  const statusesBeforeStaleCallback = journey.statuses.length;
  journey.notificationPausedFrameHandler?.({
    data: { kind: 'error', reason: 'input_gap_exceeded' },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(journey.calls.length, callsBeforeStaleCallback);
  assert.equal(journey.statuses.length, statusesBeforeStaleCallback);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });

  await journey.owner.stopAndRecognize();
  await startCaptureWithFirstFrame(journey.owner, journey.environment, {
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-after-announcement-1',
    activation_generation: 8,
    locale: 'zh-CN',
  });
  journey.notificationPausedFrameHandler?.({
    data: {
      kind: 'frame',
      capture_generation: 1,
      seq: PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20,
      sample_rate_hz: 48_000,
      sample_cursor: PRODUCT_P1_CAPTURE_MAX_DURATION_MS * 48,
      context_time_s: PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 1_000,
      samples: new Float32Array(960).fill(0.75),
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(
    journey.calls.some(([, params]) => params?.reason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON),
    false,
  );
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 terminal announcement failure releases both leases and first retry recovers', async () => {
  const journey = await runConcurrentCaptureJourney({
    pauseForNotificationBeforePlayout: true,
    failSecondCaptureDuringDownlink: true,
    deferSourceEndsUntilTransportAck: true,
  });

  assert.equal(journey.notificationPauseOutcome, 'paused');
  assert.equal(journey.playError?.reason, 'AUDIO_INPUT_GAP_EXCEEDED');
  assert.deepEqual(journey.owner.status(), {
    status: 'failed',
    reason: 'AUDIO_INPUT_GAP_EXCEEDED',
  });
  assert.equal(
    journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length,
    0,
  );
  assert.ok(
    journey.calls.some(
      ([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD
        && params.subject_id === 'media-subject-1',
    ),
  );
  assert.ok(
    journey.calls.some(
      ([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD
        && params.subject_id === 'media-subject-2',
    ),
  );
  await journey.owner.close();

  const recovered = await runFirstRecoveredRetry(journey);
  assert.equal(recovered.recognition.text, 'duplex text');
  assert.deepEqual(recovered.owner.status(), { status: 'capturing', reason: null });
  assert.equal(recovered.statuses.includes('failed'), false);
  await recovered.owner.close();
});

test('formal P1 close during terminal announcement fences old audio and first successor recovers', async () => {
  const journey = await runConcurrentCaptureJourney({
    pauseForNotificationBeforePlayout: true,
    closeDuringActivePlayout: true,
    deferSourceEndsUntilTransportAck: true,
    downlinkFrameCount: 16,
    downlinkFramesToSend: 16,
  });

  assert.equal(journey.notificationPauseOutcome, 'paused');
  assert.deepEqual(journey.concurrentCloseSnapshot, {
    status: 'cleanup_pending',
    reason: 'FORMAL_P1_CLEANUP_IN_PROGRESS',
  });
  assert.equal(journey.playError?.reason, 'FORMAL_P1_CLOSED');
  assert.equal(journey.statuses.includes('failed'), false);
  assert.deepEqual(journey.owner.status(), { status: 'closed', reason: null });

  const oldUplink = journey.sockets.find(
    socket => socket.serverBinding?.generation?.id === 'capture-2',
  );
  const oldDownlink = journey.sockets.find(
    socket => socket.serverBinding?.direction === 'downlink',
  );
  assert.ok(oldUplink);
  assert.ok(oldDownlink);
  const recovered = await runFirstRecoveredRetry(journey, async recoveredOwner => {
    const callsBeforeStaleCallbacks = journey.calls.length;
    const successorContext = journey.environment.contexts.at(-1);
    const successorSourceStarts = successorContext.sourceStartCount;
    journey.staleCaptureFrameHandler?.({
      data: { kind: 'error', reason: 'input_gap_exceeded' },
    });
    journey.staleUplinkMessageHandler?.({
      data: serializeMediaControl({
        type: 'media.speech_start',
        capability_version: 'media.end_of_turn.v1',
        lease_id: oldUplink.serverBinding.lease_id,
        generation: oldUplink.serverBinding.generation.value,
        detector: 'server_vad',
        provider_start_ms: 100,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      }),
    });
    journey.staleDownlinkMessageHandler?.({
      data: serializeMediaControl({
        type: 'media.detach',
        lease_id: oldDownlink.serverBinding.lease_id,
        generation: oldDownlink.serverBinding.generation.value,
        reason_id: 'MEDIA_LOCAL_CLOSE',
        through_seq: 15,
        business_cancel_count_delta: 0,
      }),
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(journey.calls.length, callsBeforeStaleCallbacks);
    assert.equal(successorContext.sourceStartCount, successorSourceStarts);
    assert.deepEqual(recoveredOwner.status(), { status: 'capturing', reason: null });
    assert.deepEqual(journey.owner.status(), { status: 'closed', reason: null });
  });

  assert.equal(recovered.recognition.text, 'duplex text');
  assert.deepEqual(recovered.owner.status(), { status: 'capturing', reason: null });
  assert.equal(recovered.statuses.includes('failed'), false);
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await recovered.owner.close();
});

test('formal P1 aborts an in-flight idle rotation when current provider speech-start arrives', async () => {
  const journey = await runConcurrentCaptureJourney({ negotiatedEot: true });
  const uplink = journey.sockets.find(
    socket => socket.serverBinding?.generation?.id === 'capture-2',
  );
  assert.ok(uplink);
  const priorWorklet = journey.environment.worklet;

  await sendCaptureToDurationBoundary(
    journey.environment,
    new Float32Array(960),
    {
      afterBoundary: () => {
        uplink.onmessage?.({
          data: serializeMediaControl({
            type: 'media.speech_start',
            capability_version: 'media.end_of_turn.v1',
            lease_id: uplink.serverBinding.lease_id,
            generation: uplink.serverBinding.generation.value,
            detector: 'server_vad',
            provider_start_ms: 550,
            timing_basis: 'provider_time',
            timing_provenance: 'adapter_derived',
            create_response: false,
            interrupt_response: false,
            business_cancel_count_delta: 0,
          }),
        });
      },
    },
  );
  for (let turn = 0; turn < 500 && journey.owner.status().status !== 'failed'; turn += 1) {
    await new Promise(resolve => setImmediate(resolve));
  }

  assert.deepEqual(journey.owner.status(), {
    status: 'failed',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.equal(journey.environment.worklet, priorWorklet);
  assert.equal(journey.activationCount, 2);
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 streaming downlink derives its final rendered cursor only from expected completion', async () => {
  const journey = await runConcurrentCaptureJourney({
    streamingDownlink: true,
    downlinkFrameCount: 3,
  });
  const { owner, calls, sockets, playError } = journey;

  assert.equal(playError, null);
  assert.equal(owner.status().status, 'capturing');
  const receipt = calls.find(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD)?.[1];
  assert.ok(receipt);
  assert.equal(receipt.rendered_chunks, 3);
  assert.equal(receipt.rendered_through_seq, 2);
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  assert.ok(downlinkSocket);
  const controls = downlinkSocket.sent.filter(value => typeof value === 'string').map(JSON.parse);
  assert.deepEqual(
    controls.filter(control => control.type === 'media.ack').map(control => control.through_seq),
    [0, 1, 2]
  );
  assert.equal(
    calls.some(([method]) => method.includes('agent') || method.includes('task') || method.includes('history')),
    false
  );
  await owner.close();
});

test('formal P1 streaming downlink renders beyond the former 30-second frame ceiling', async () => {
  const journey = await runConcurrentCaptureJourney({
    streamingDownlink: true,
    downlinkFrameCount: 1_501,
    agentText:
      '实时语音系统需要连续朗读完整的长回复，不应在三十秒边界取消合成与播放。'.repeat(8),
  });
  const { owner, calls, playError, environment } = journey;

  assert.equal(playError, null);
  assert.equal(environment.contexts[0].sourceEndCount, 1_501);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD).length, 1);
  assert.deepEqual(owner.status(), { status: 'capturing', reason: null });
  await owner.close();
});

test('formal P1 batch fallback exposes its typed streaming degradation reason', async () => {
  const journey = await runConcurrentCaptureJourney({
    downlinkDegradationReason: 'STREAMING_SPEECH_PROVIDER_UNAVAILABLE',
  });
  const { owner, calls, playError } = journey;

  assert.equal(playError, null);
  assert.deepEqual(owner.status(), {
    status: 'capturing',
    reason: 'STREAMING_SPEECH_PROVIDER_UNAVAILABLE',
  });
  assert.equal(
    calls.some(([method]) => method.includes('agent') || method.includes('task') || method.includes('history')),
    false
  );
  await owner.close();
});

test('formal P1 rejects a prefix-only downlink completion without receipt or business effects', async () => {
  const journey = await runConcurrentCaptureJourney({
    downlinkFrameCount: 2,
    downlinkFramesToSend: 1,
    earlyDownlinkDetachThroughSeq: 0,
    requireBoundedPlayoutSettlement: true,
    sendSecondFrame: false,
  });
  const { owner, calls, sockets, playError, environment } = journey;

  assert.equal(playError?.reason, 'MEDIA_TRANSPORT_PROTOCOL_ERROR');
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'MEDIA_TRANSPORT_PROTOCOL_ERROR' });
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 0);
  assert.equal(
    calls.some(([method]) => method.includes('cancel') || method.includes('agent') || method.includes('task') || method.includes('history')),
    false
  );
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  const downlinkControls = downlinkSocket.sent.filter(value => typeof value === 'string').map(JSON.parse);
  assert.deepEqual(
    downlinkControls.filter(control => control.type === 'media.ack').map(control => control.through_seq),
    [0]
  );
  assert.equal(
    downlinkControls.every(control => control.business_cancel_count_delta === undefined || control.business_cancel_count_delta === 0),
    true
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  await owner.close();
});

test('formal P1 keeps duplex playout alive across bounded real-processor input gaps', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    exerciseTransientGapDuringDownlink: true,
  });
  const { owner, calls, sockets, playError, realProcessorHarness } = journey;

  assert.equal(playError, null);
  assert.equal(owner.status().status, 'capturing');
  assert.equal(realProcessorHarness.processor.failed, false);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  const acknowledgements = downlinkSocket.sent
    .filter(value => typeof value === 'string')
    .map(JSON.parse)
    .filter(control => control.type === 'media.ack');
  assert.equal(acknowledgements.length, 1);
  assert.equal(acknowledgements[0].through_seq, 0);
  await owner.close();
});

test('formal P1 keeps duplex playout alive across a monotonic overlap compatibility anomaly', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    exerciseMonotonicOverlapDuringDownlink: true,
  });
  const { owner, calls, sockets, playError, realProcessorHarness } = journey;

  assert.equal(playError, null);
  assert.equal(owner.status().status, 'capturing');
  assert.equal(realProcessorHarness.processor.failed, false);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  const acknowledgements = downlinkSocket.sent
    .filter(value => typeof value === 'string')
    .map(JSON.parse)
    .filter(control => control.type === 'media.ack');
  assert.equal(acknowledgements.length, 1);
  assert.equal(acknowledgements[0].through_seq, 0);
  await owner.close();
});

test('formal P1 preserves multi-frame playout, receipt, and successor PCM across a final-source duplicate callback', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    downlinkFrameCount: 3,
    exerciseDuplicateRenderFrameAtFinalPlayout: true,
    exercisePostReceiptCaptureAdvance: true,
  });
  const { owner, calls, sockets, playError, realProcessorHarness, finalPlayoutDuplicateSnapshot, environment } = journey;

  assert.equal(playError, null);
  assert.equal(owner.status().status, 'capturing');
  assert.equal(realProcessorHarness.processor.failed, false);
  assert.equal(realProcessorHarness.processor.duplicateRenderFrameCount, 0);
  assert.deepEqual(finalPlayoutDuplicateSnapshot, {
    accepted: true,
    sourceStartCount: 3,
    sourceEndCount: 3,
    duplicateRenderFrameCount: 1,
    pendingLengthBefore: 192,
    pendingLengthAfter: 192,
    seqBefore: 1,
    seqAfter: 1,
    sampleCursorBefore: 960,
    sampleCursorAfter: 960,
  });
  assert.equal(environment.contexts[0].sourceStartCount, 3);
  assert.equal(environment.contexts[0].sourceEndCount, 3);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  const receiptCall = calls.find(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD);
  assert.equal(receiptCall[1].rendered_chunks, 3);
  assert.equal(receiptCall[1].rendered_through_seq, 2);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  const acknowledgements = downlinkSocket.sent
    .filter(value => typeof value === 'string')
    .map(JSON.parse)
    .filter(control => control.type === 'media.ack');
  assert.deepEqual(
    acknowledgements.map(control => control.through_seq),
    [0, 1, 2]
  );
  const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
  const uplinkFrames = uplinkSocket.sent.filter(value => typeof value !== 'string').map(value => decodeAudioFrame(uplinkSocket.serverBinding, value));
  assert.deepEqual(
    uplinkFrames.map(frame => [frame.seq, frame.sample_cursor]),
    [
      [0, 0],
      [1, 960],
    ]
  );
  assert.equal(
    uplinkFrames[1].samples.slice(0, 192).every(sample => Math.abs(sample - 0.25) < 1e-6),
    true
  );
  assert.equal(
    uplinkFrames[1].samples.slice(192).every(sample => Math.abs(sample - 0.625) < 1e-6),
    true
  );
  await owner.close();
});

test('formal P1 fails only the retained capture when the render clock stalls after an accepted receipt', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    downlinkFrameCount: 3,
    exerciseDuplicateRenderFrameAtFinalPlayout: true,
    exerciseRenderStallAfterReceipt: true,
  });
  const {
    owner,
    calls,
    sockets,
    statuses,
    playError,
    concurrentFailureSnapshot,
    realProcessorHarness,
    finalPlayoutDuplicateSnapshot,
    postReceiptStatusBeforeFailure,
    postReceiptSourceStartsBeforeFailure,
    postReceiptUplinkFramesBeforeFailure,
    environment,
  } = journey;

  assert.equal(playError, null);
  assert.deepEqual(postReceiptStatusBeforeFailure, { status: 'capturing', reason: null });
  assert.equal(finalPlayoutDuplicateSnapshot.duplicateRenderFrameCount, 1);
  assert.equal(realProcessorHarness.processor.failed, true);
  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: 'AUDIO_RENDER_FRAME_NOT_ADVANCED',
  });
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'AUDIO_RENDER_FRAME_NOT_ADVANCED',
  });
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1').length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  assert.equal(environment.contexts[0].sourceStartCount, postReceiptSourceStartsBeforeFailure);
  assert.equal(environment.contexts[0].sourceStartCount, 3);
  assert.equal(environment.contexts[0].sourceEndCount, 3);
  const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
  assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, postReceiptUplinkFramesBeforeFailure);
  assert.equal(realProcessorHarness.processor.process(realProcessorHarness.quantum(0.75)), false);
  environment.worklet.port.onmessage?.({
    data: {
      kind: 'frame',
      capture_generation: environment.worklet.captureGeneration,
      seq: 99,
      sample_rate_hz: 48_000,
      sample_cursor: 99 * 960,
      context_time_s: 1.98,
      samples: new Float32Array(960).fill(0.75),
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, postReceiptUplinkFramesBeforeFailure);
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_RENDER_FRAME_NOT_ADVANCED' });
  assert.equal(statuses.at(-1), 'failed');
  await owner.close();
});

test('formal P1 duration expiry after final render is fenced before playout receipt dispatch', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    downlinkFrameCount: 3,
    holdDownlinkDetachAfterFinalRender: true,
    signalProviderSpeechStartBeforeOverlapDuration: true,
    exerciseCaptureDurationBeforeReceipt: true,
    deferCaptureDurationUntilDetachWait: true,
  });
  const { owner, calls, sockets, playError, concurrentFailureSnapshot, captureDurationBoundarySnapshot, captureDurationLateFrameUplinkCount, environment } =
    journey;

  assert.notEqual(playError, null);
  assert.deepEqual(captureDurationBoundarySnapshot, { status: 'playing', reason: null });
  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 0);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.synthesize_batch').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  const acknowledgements = downlinkSocket.sent
    .filter(value => typeof value === 'string')
    .map(JSON.parse)
    .filter(control => control.type === 'media.ack');
  assert.deepEqual(
    acknowledgements.map(control => control.through_seq),
    [0, 1, 2]
  );
  const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
  assert.equal(captureDurationLateFrameUplinkCount <= PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20 + 1, true);
  assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, captureDurationLateFrameUplinkCount);
  assert.equal(
    sockets.every(socket => socket.readyState === 3),
    true
  );
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  await owner.close();
});

test('formal P1 reports the exact 30-second successor-capture bound after preserving the accepted receipt', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    useRealProcessorForSecondCapture: true,
    downlinkFrameCount: 3,
    exerciseDuplicateRenderFrameAtFinalPlayout: true,
    exerciseCaptureDurationAfterReceipt: true,
  });
  const {
    owner,
    calls,
    sockets,
    statuses,
    playError,
    concurrentFailureSnapshot,
    captureDurationBoundarySnapshot,
    captureDurationLateFrameUplinkCount,
    environment,
    postReceiptStatusBeforeFailure,
  } = journey;

  assert.equal(playError, null);
  assert.deepEqual(postReceiptStatusBeforeFailure, { status: 'capturing', reason: null });
  assert.deepEqual(captureDurationBoundarySnapshot, { status: 'capturing', reason: null });
  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.synthesize_batch').length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1').length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  assert.equal(environment.contexts[0].sourceStartCount, 3);
  assert.equal(environment.contexts[0].sourceEndCount, 3);
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.equal(
    sockets.every(socket => socket.readyState === 3),
    true
  );
  const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
  const uplinkCountAfterFailure = uplinkSocket.sent.filter(value => typeof value !== 'string').length;
  assert.equal(captureDurationLateFrameUplinkCount > 0, true);
  assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, uplinkCountAfterFailure);
  assert.deepEqual(owner.status(), { status: 'failed', reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON });
  assert.equal(statuses.at(-1), 'failed');
  await owner.close();
});

test('formal P1 duration expiry releases local capture before an exact authority close retry', async () => {
  const journey = await runConcurrentCaptureJourney({
    negotiatedEot: true,
    downlinkFrameCount: 3,
    exerciseCaptureDurationAfterReceipt: true,
    failSecondMediaCloseOnce: true,
  });
  const { owner, calls, sockets, playError, concurrentFailureSnapshot, captureDurationLateFrameUplinkCount } = journey;

  assert.equal(playError, null);
  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  });
  assert.deepEqual(owner.status(), {
    status: 'cleanup_pending',
    reason: 'FORMAL_P1_CLEANUP_PENDING',
  });
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.synthesize_batch').length, 1);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  await assert.rejects(owner.stopAndRecognize(), /not active/);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
  assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, captureDurationLateFrameUplinkCount);
  await owner.close();
  assert.deepEqual(owner.status(), { status: 'closed', reason: null });
  const retriedCloses = calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2');
  assert.equal(retriedCloses.length, 2);
  assert.deepEqual(retriedCloses[1][1], retriedCloses[0][1]);
});

test('formal P1 accepts Stop and recognize at the exact 30-second capture boundary', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    downlinkFrameCount: 3,
    stopAtCaptureDurationBoundaryAfterReceipt: true,
  });
  const { owner, calls, playError, captureDurationBoundarySnapshot, captureDurationBoundaryRecognition } = journey;

  assert.equal(playError, null);
  assert.deepEqual(captureDurationBoundarySnapshot, { status: 'capturing', reason: null });
  assert.deepEqual(captureDurationBoundaryRecognition, {
    text: 'duplex text',
    voice_commit_receipt: 'voice-receipt-duplex-1',
  });
  assert.deepEqual(owner.status(), { status: 'recognized', reason: null });
  const recognitionCalls = calls.filter(([method]) => method === 'live_voice.speech.recognize_batch');
  assert.equal(recognitionCalls.length, 2);
  assert.equal(Buffer.from(recognitionCalls[1][1].audio.data_base64, 'base64').length, 44 + (PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 20) * 960 * 2);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  await owner.close();
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1').length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2').length, 1);
});

test('a real processor render-clock regression fails exact P1 playout with zero ACK or cancel', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    exerciseRenderRegressionDuringDownlink: true,
  });
  const { owner, calls, sockets, playError, concurrentFailureSnapshot, realProcessorHarness, environment } = journey;

  assert.equal(realProcessorHarness.processor.failed, true);
  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: 'AUDIO_RENDER_FRAME_REGRESSED',
  });
  assert.equal(playError?.reason, 'AUDIO_RENDER_FRAME_REGRESSED');
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'AUDIO_RENDER_FRAME_REGRESSED',
  });
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.equal(Math.max(...environment.contexts.map(context => context.peakSources)), 1);
  assert.equal(
    sockets.every(socket => socket.readyState === 3),
    true
  );
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 0);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  await owner.close();
});

test('formal P1 concurrent capture cannot publish readiness without a real frame', async () => {
  const journey = await runConcurrentCaptureJourney({ sendSecondFrame: false });
  const { owner, calls, statuses, playError, capturingBeforeConcurrent, environment } = journey;

  assert.equal(playError, null);
  assert.deepEqual(owner.status(), { status: 'recognized', reason: 'AUDIO_CAPTURE_NO_FRAMES' });
  assert.equal(environment.contexts[0].sourceStartCount, 1);
  assert.equal(statuses.filter(status => status === 'capturing').length, capturingBeforeConcurrent);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
  await owner.close();
});

test('formal P1 concurrent capture without a Gateway ACK degrades barge-in without discarding TTS', async () => {
  const journey = await runConcurrentCaptureJourney({ ackSecondCapture: false });
  const { owner, calls, statuses, playError, capturingBeforeConcurrent, environment } = journey;

  assert.equal(playError, null);
  assert.deepEqual(owner.status(), {
    status: 'recognized',
    reason: 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED',
  });
  assert.equal(environment.contexts[0].sourceStartCount, 1);
  assert.equal(statuses.filter(status => status === 'capturing').length, capturingBeforeConcurrent);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
  assert.equal(calls.some(([method]) => method.includes('task.') || method.includes('tool.')), false);
  assert.equal(owner.captureDiagnostics().successor_readiness, 'degraded');
  assert.equal(owner.captureDiagnostics().successor_readiness_reason, 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED');
  assert.ok(owner.captureDiagnostics().successor_readiness_elapsed_ms >= 1_000);
  await owner.close();
});

test('formal P1 restarts listening after degraded successor capture without replaying the response', async () => {
  const journey = await runConcurrentCaptureJourney({ ackSecondCapture: false });
  const priorWorklet = journey.environment.worklet;
  const restarting = journey.owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-restart-after-degradation',
    activation_generation: 8,
    locale: 'zh-CN',
  });
  await sendFirstFrameToNextWorklet(journey.environment, priorWorklet);
  await restarting;

  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD).length, 3);
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(journey.calls.filter(([method]) => method === 'live_voice.speech.synthesize_batch').length, 1);
  assert.equal(journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(journey.calls.some(([method]) => method.includes('task.') || method.includes('tool.')), false);
  await journey.owner.close();
});

test('formal P1 accepts a delayed successor ACK inside the readiness window', async () => {
  const journey = await runConcurrentCaptureJourney({ secondCaptureAckDelayMs: 500 });

  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.concurrentCaptureStartedCalls, 1);
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(journey.owner.captureDiagnostics().successor_readiness, 'ready');
  assert.equal(journey.owner.captureDiagnostics().successor_readiness_reason, null);
  assert.ok(journey.owner.captureDiagnostics().successor_readiness_elapsed_ms >= 450);
  assert.ok(journey.owner.captureDiagnostics().successor_readiness_elapsed_ms < 1_000);
  await journey.owner.close();
});

test('formal P1 accepts an acknowledged first successor frame while later live frames remain pending', async () => {
  const journey = await runConcurrentCaptureJourney({
    holdSecondCaptureFirstAckUntilNextFrame: true,
  });
  const successorSocket = journey.sockets.find(
    socket => socket.serverBinding?.generation?.id === 'capture-2',
  );

  assert.ok(successorSocket);
  assert.ok(successorSocket.secondCaptureFramesInFlightAtFirstAck > 0);
  assert.equal(journey.secondCaptureAckStillPendingAtReady, true);
  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.concurrentCaptureStartedCalls, 1);
  assert.equal(journey.owner.captureDiagnostics().successor_readiness, 'ready');
  assert.equal(journey.owner.captureDiagnostics().successor_readiness_reason, null);
  assert.equal(journey.calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(journey.calls.filter(([method]) => method === 'live_voice.speech.synthesize_batch').length, 1);
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(journey.environment.contexts[0].sourceStartCount, 1);
  assert.equal(
    journey.calls.some(
      ([method]) => method.includes('agent') || method.includes('tool') || method.includes('task') || method.includes('history'),
    ),
    false,
  );
  await journey.owner.close();
});

test('formal P1 keeps completed TTS when the Gateway reports no early duplex media', async () => {
  const journey = await runConcurrentCaptureJourney({
    secondCaptureAckDelayMs: 500,
    serverDuplexMediaObserved: false,
  });

  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), { status: 'capturing', reason: null });
  assert.equal(journey.environment.contexts[0].sourceStartCount, 1);
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.equal(
    journey.calls.some(([method]) => method.includes('agent') || method.includes('tool') || method.includes('task') || method.includes('history')),
    false,
  );
  await journey.owner.close();
});

test('formal P1 late successor ACK after the readiness window cannot cancel scheduled TTS', async () => {
  const journey = await runConcurrentCaptureJourney({ secondCaptureAckDelayMs: 1_100 });

  assert.equal(journey.playError, null);
  assert.deepEqual(journey.owner.status(), {
    status: 'recognized',
    reason: 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED',
  });
  assert.equal(journey.environment.contexts[0].sourceStartCount, 1);
  assert.equal(journey.concurrentCaptureStartedCalls, 0);
  assert.equal(journey.calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 1);
  assert.ok(journey.calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
  const callsBeforeLateAck = journey.calls.length;
  const sourceStartsBeforeLateAck = journey.environment.contexts[0].sourceStartCount;
  await new Promise(resolve => setTimeout(resolve, 150));
  assert.deepEqual(journey.owner.status(), {
    status: 'recognized',
    reason: 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED',
  });
  assert.equal(journey.calls.length, callsBeforeLateAck);
  assert.equal(journey.environment.contexts[0].sourceStartCount, sourceStartsBeforeLateAck);
  await journey.owner.close();
});

test('formal P1 concurrent playing-window mute releases audio and compensates exact authority', async () => {
  const journey = await runConcurrentCaptureJourney({
    sendSecondFrame: false,
    failSecondCaptureWithMute: true,
  });
  const { owner, calls, sockets, statuses, playError, capturingBeforeConcurrent, concurrentFailureSnapshot, concurrentAudioReleased } = journey;

  assert.deepEqual(concurrentFailureSnapshot, { status: 'playing', reason: 'AUDIO_INPUT_MUTED' });
  assert.equal(concurrentAudioReleased, false);
  assert.equal(playError, null);
  assert.deepEqual(owner.status(), { status: 'recognized', reason: 'AUDIO_INPUT_MUTED' });
  assert.equal(statuses.filter(status => status === 'capturing').length, capturingBeforeConcurrent);
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
  assert.equal(sockets.some(socket => socket.serverBinding?.direction === 'downlink'), true);
  await owner.close();
});

test('formal P1 persistent concurrent input gap stops playout with the exact stable reason', async () => {
  const journey = await runConcurrentCaptureJourney({
    failSecondCaptureDuringDownlink: true,
    deferSourceEndsUntilTransportAck: true,
  });
  const { owner, calls, sockets, statuses, playError, capturingBeforeConcurrent, concurrentFailureSnapshot, environment } = journey;

  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: 'AUDIO_INPUT_GAP_EXCEEDED',
  });
  assert.notEqual(playError, null);
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'AUDIO_INPUT_GAP_EXCEEDED',
  });
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.equal(
    sockets.every(socket => socket.readyState === 3),
    true
  );
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 0);
  assert.equal(statuses.filter(status => status === 'capturing').length, capturingBeforeConcurrent);
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1'));
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
  await owner.close();
});

test('formal P1 non-advancing concurrent render clock stops playout with the exact stable reason', async () => {
  const journey = await runConcurrentCaptureJourney({
    useRealProcessorForSecondCapture: true,
    exerciseRenderStallDuringDownlink: true,
  });
  const { owner, calls, sockets, statuses, playError, capturingBeforeConcurrent, concurrentFailureSnapshot, realProcessorHarness, environment } = journey;

  assert.equal(realProcessorHarness.processor.failed, true);
  assert.deepEqual(concurrentFailureSnapshot, {
    status: 'cleanup_pending',
    reason: 'AUDIO_RENDER_FRAME_NOT_ADVANCED',
  });
  assert.equal(playError?.reason, 'AUDIO_RENDER_FRAME_NOT_ADVANCED');
  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'AUDIO_RENDER_FRAME_NOT_ADVANCED',
  });
  assert.equal(
    environment.contexts.every(context => context.state === 'closed'),
    true
  );
  assert.equal(Math.max(...environment.contexts.map(context => context.peakSources)), 1);
  assert.equal(
    environment.contexts.reduce((count, context) => count + context.sourceStartCount, 0),
    1
  );
  assert.equal(
    sockets.every(socket => socket.readyState === 3),
    true
  );
  assert.equal(calls.filter(([method]) => method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD).length, 0);
  assert.equal(statuses.filter(status => status === 'capturing').length, capturingBeforeConcurrent);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1').length, 1);
  assert.equal(calls.filter(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2').length, 1);
  assert.equal(
    calls.some(([method]) => method.includes('cancel')),
    false
  );
  const uplinkSocket = sockets.find(socket => socket.serverBinding.generation.id === 'capture-2');
  const binaryCount = uplinkSocket.sent.filter(value => typeof value !== 'string').length;
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  const downlinkAckCount = downlinkSocket.sent
    .filter(value => typeof value === 'string')
    .map(JSON.parse)
    .filter(control => control.type === 'media.ack').length;
  environment.worklet.port.onmessage?.({
    data: {
      kind: 'frame',
      capture_generation: environment.worklet.captureGeneration,
      seq: 99,
      sample_rate_hz: 48_000,
      sample_cursor: 99 * 960,
      context_time_s: 1.98,
      samples: new Float32Array(960).fill(0.75),
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(uplinkSocket.sent.filter(value => typeof value !== 'string').length, binaryCount);
  assert.equal(
    downlinkSocket.sent
      .filter(value => typeof value === 'string')
      .map(JSON.parse)
      .filter(control => control.type === 'media.ack').length,
    downlinkAckCount
  );
  assert.equal(downlinkAckCount, 0);
  assert.deepEqual(owner.status(), { status: 'failed', reason: 'AUDIO_RENDER_FRAME_NOT_ADVANCED' });
  await owner.close();
});

test('formal P1 concurrent close waits for pending activation and revokes both exact authorities', async () => {
  const journey = await runConcurrentCaptureJourney({
    sendSecondFrame: false,
    closeSecondCaptureWhilePending: true,
  });
  const { owner, calls, statuses, sockets, playError, concurrentCloseSnapshot, concurrentCloseAudioReleased } = journey;

  assert.deepEqual(concurrentCloseSnapshot, {
    status: 'cleanup_pending',
    reason: 'FORMAL_P1_CLEANUP_IN_PROGRESS',
  });
  assert.equal(concurrentCloseAudioReleased, true);
  assert.equal(playError?.reason, 'FORMAL_P1_CLOSED');
  assert.equal(statuses.includes('failed'), false);
  assert.deepEqual(owner.status(), { status: 'closed', reason: null });
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1'));
  assert.ok(calls.some(([method, params]) => method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'));
  assert.equal(calls.filter(([method]) => method === 'live_voice.speech.recognize_batch').length, 1);
  assert.equal(
    sockets.some(socket => socket.serverBinding?.generation.id === 'capture-2'),
    false
  );
});

for (const [status, reason] of [
  ['disabled', 'MEDIA_FEATURE_DISABLED'],
  ['unavailable', 'MEDIA_PROVIDER_UNAVAILABLE'],
]) {
  test(`formal P1 preserves the stable ${status} media reason`, async () => {
    const environment = audioEnvironment();
    const owner = new ProductP1VoiceRouteOwner({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      audio_environment: environment,
      request: async method => {
        assert.equal(method, PRODUCT_P1_MEDIA_ACTIVATE_METHOD);
        return { status, reason_id: reason };
      },
    });

    await assert.rejects(
      owner.startCapture({
        session_id: 'session-1',
        interaction_id: 'interaction-1',
        correlation_id: 'correlation-1',
        activation_id: 'activation-1',
        activation_generation: 1,
      }),
      error => error.reason_id === reason
    );
    assert.deepEqual(owner.status(), { status: 'failed', reason });
    await owner.close();
  });
}

test('formal P1 never publishes a private transport error message', async () => {
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: audioEnvironment(),
    socket_factory: () => {
      throw new Error('socket must not be allocated');
    },
    request: async () => {
      throw new Error('api_key=private-provider-value');
    },
  });

  await assert.rejects(
    owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 1,
    }),
    /private-provider-value/
  );

  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'FORMAL_P1_ROUTE_FAILED',
  });
  assert.doesNotMatch(JSON.stringify(owner.status()), /private-provider-value|api_key/);
  await assert.rejects(
    owner.playAgentText({
      response: {
        interaction_id: 'interaction-1',
        response_id: 'response-1',
        response_generation: 0,
      },
      unit_id: 'unit-1',
      text: 'must not retain failed Speech authority',
    }),
    /synthesis authority is unavailable/
  );
  await owner.close();
});
