import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
  PRODUCT_P1_MEDIA_CLOSE_METHOD,
  PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD,
  ProductP1VoiceRouteOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP1VoiceRoute.js';
import {
  encodeAudioFrame,
  serializeMediaControl,
} from '../node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs';

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
}

class FakeNode {
  connect(destination) { return destination; }
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

  async resume() { this.state = 'running'; }
  async close() { this.state = 'closed'; }
  createMediaStreamSource() { return new FakeNode(); }
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
        context.peakSources = Math.max(context.peakSources, context.activeSources);
        queueMicrotask(() => {
          context.activeSources -= 1;
          source.onended?.();
        });
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

  stop() { this.readyState = 'ended'; }
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

  send(value) {
    this.sent.push(value);
    if (typeof value !== 'string' && this.binding !== null) {
      queueMicrotask(() => this.onmessage?.({
        data: JSON.stringify({
          type: 'media.ack',
          lease_id: this.binding.lease_id,
          generation: this.binding.generation.value,
          through_seq: 0,
        }),
      }));
    }
  }
  close() { this.readyState = 3; }
  open(binding) {
    this.binding = binding;
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
  mediaDevices.getUserMedia = async () => {
    const track = new FakeTrack();
    environment.track = track;
    return {
      getAudioTracks: () => [track],
      getTracks: () => [track],
    };
  };
  mediaDevices.enumerateDevices = async () => [{ kind: 'audioinput' }];
  const environment = {
    isSecureContext: true,
    document,
    mediaDevices,
    createAudioContext: () => {
      const context = new FakeAudioContext();
      environment.contexts.push(context);
      return context;
    },
    createAudioWorkletNode: () => {
      const node = new FakeNode();
      node.port = { onmessage: null, close() {} };
      node.onprocessorerror = null;
      environment.worklet = node;
      return node;
    },
    createId,
    worklet: null,
    track: null,
    contexts: [],
  };
  return environment;
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

test('formal P1 binds media activation to the exact product P2 activation', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: audioEnvironment(),
    socket_factory: (url, protocols) => {
      assert.equal(url, 'wss://voice.example.test/ws/live-voice/media/private-ticket');
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
        endpoint_path: '/ws/live-voice/media/private-ticket',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding,
        privacy: {
          raw_audio_persisted: false,
          raw_audio_logged: false,
          memory_only: true,
        },
      };
    },
  });

  await owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
  });

  assert.equal(owner.status().status, 'capturing');
  assert.deepEqual(calls, [[PRODUCT_P1_MEDIA_ACTIVATE_METHOD, {
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
  }]]);
  await owner.close();
  assert.equal(owner.status().status, 'closed');
  assert.equal(calls[1][0], PRODUCT_P1_MEDIA_CLOSE_METHOD);
});

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
          endpoint_path: '/ws/live-voice/media/private-ticket',
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
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

  await owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 7,
    locale: 'zh-CN',
  });
  environment.worklet.port.onmessage({ data: {
    kind: 'frame',
    capture_generation: 1,
    seq: 0,
    sample_rate_hz: 48_000,
    sample_cursor: 0,
    context_time_s: 0,
    samples: new Float32Array(960).fill(0.25),
  } });
  const recognition = await owner.stopAndRecognize();
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
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
    'live_voice.speech.recognize_batch',
    'live_voice.speech.synthesize_batch',
    PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD,
  ]);
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
          endpoint_path: `/ws/live-voice/media/ticket-${params.activation_generation}`,
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
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
              provider_id: 'provider-test', implementation_class: 'formal',
              fallback_from: null, model: 'stt-test',
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
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 1,
  };
  await owner.startCapture(first);
  environment.worklet.port.onmessage({ data: {
    kind: 'frame', capture_generation: 1, seq: 0, sample_rate_hz: 48_000,
    sample_cursor: 0, context_time_s: 0, samples: new Float32Array(960),
  } });
  await owner.stopAndRecognize();
  await owner.startCapture({
    session_id: 'session-1', interaction_id: 'interaction-2', correlation_id: 'correlation-2',
    activation_id: 'activation-2', activation_generation: 2,
  });

  assert.deepEqual(calls.slice(0, 4).map(([method]) => method), [
    PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
    'live_voice.speech.recognize_batch',
    PRODUCT_P1_MEDIA_CLOSE_METHOD,
    PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
  ]);
  assert.deepEqual(calls[2][1], {
    session_id: 'session-1', subject_id: 'media-subject-1', correlation_id: 'correlation-1',
    interaction_id: 'interaction-1', activation_id: 'activation-1', activation_generation: 1,
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
          disconnect() { sourceDisconnectCalls += 1; },
          start() {
            lateEnded = source.onended;
            throw new Error('injected source startup failure');
          },
          stop() { sourceStopCalls += 1; },
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
          status: 'active', reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: 'media-subject-1', endpoint_path: '/ws/live-voice/media/private-ticket',
          subprotocol: 'live-voice.media.v1', ticket_ttl_ms: 30_000, binding,
          privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
        };
      }
      if (method === 'live_voice.speech.recognize_batch') {
        return {
          contract_version: 'live-voice.contract.v2', request_id: params.request_id,
          operation_id: params.operation_id, ok: true, error: null,
          result: {
            operation: 'speech.recognize.batch',
            voice_commit_receipt: 'voice-receipt-3',
            capture: params.capture,
            event: {
              session_id: params.capture.capture_id,
              generation: params.capture.capture_generation, seq: 0, kind: 'final',
              commits_turn: false,
              hypothesis: {
                alternatives: [{ raw_text: 'formal text', display_text: 'formal text', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'provider-test', implementation_class: 'formal',
              fallback_from: null, model: 'stt-test',
            },
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
        return {
          contract_version: 'live-voice.contract.v2', request_id: params.request_id,
          operation_id: params.operation_id, ok: true, error: null,
          result: {
            operation: 'speech.synthesize.batch', response: params.response,
            unit_id: params.unit_id,
            audio: {
              format: 'wav_pcm16_mono', sample_rate_hz: 48_000, channel_count: 1,
              data_base64: wavBase64(),
            },
            provider: {
              provider_id: 'provider-test', implementation_class: 'formal',
              fallback_from: null, model: 'tts-test', voice: 'voice-test',
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

  await owner.startCapture({
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 1,
  });
  environment.worklet.port.onmessage({ data: {
    kind: 'frame', capture_generation: 1, seq: 0, sample_rate_hz: 48_000,
    sample_cursor: 0, context_time_s: 0, samples: new Float32Array(960),
  } });
  await owner.stopAndRecognize();
  await assert.rejects(owner.playAgentText({
    response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 },
    unit_id: 'unit-1', text: 'formal Agent response',
  }), /browser playout source setup failed/);

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
    request: async () => { requests += 1; },
  });

  await assert.rejects(owner.startCapture({
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 1,
  }), /browser audio operation failed/);

  assert.deepEqual(owner.status(), { status: 'failed', reason: 'CAPTURE_START_FAILED' });
  assert.equal(requests, 0);
  assert.equal(environment.contexts.every(context => context.state === 'closed'), true);
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
        status: 'active', reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'media-subject-1', endpoint_path: '/ws/live-voice/media/private-ticket',
        subprotocol: 'live-voice.media.v1', ticket_ttl_ms: 30_000, binding,
        privacy: { raw_audio_persisted: true, raw_audio_logged: false, memory_only: true },
      };
    },
  });

  await assert.rejects(owner.startCapture({
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 1,
  }), /privacy boundary/);

  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P1_MEDIA_ACTIVATE_METHOD,
    PRODUCT_P1_MEDIA_CLOSE_METHOD,
  ]);
  assert.equal(environment.track.readyState, 'ended');
  assert.equal(environment.contexts.every(context => context.state === 'closed'), true);
  assert.equal(owner.status().status, 'failed');
});

test('Agent output during capture cannot hide the reachable stop control or start TTS', async () => {
  const calls = [];
  const binding = serverBinding();
  const socket = new FakeSocket();
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: audioEnvironment(),
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
        endpoint_path: '/ws/live-voice/media/private-ticket',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });
  await owner.startCapture({
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 7,
  });

  await assert.rejects(owner.playAgentText({
    response: { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 },
    unit_id: 'unit-1', text: 'must remain text-only while capture is active',
  }), /capture must settle/);
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
    socket_factory: () => { throw new Error('socket must not be allocated'); },
    request: async () => { calls += 1; },
  });

  await assert.rejects(owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 0,
  }), /activation_generation/);

  assert.equal(owner.status().status, 'idle');
  assert.equal(calls, 0);
  await owner.close();
});

test('formal P1 fences successor capture while retained close is in flight', async () => {
  const binding = serverBinding();
  const socket = new FakeSocket();
  let releaseClose;
  let markCloseStarted;
  const closeGate = new Promise(resolve => { releaseClose = resolve; });
  const closeStarted = new Promise(resolve => { markCloseStarted = resolve; });
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: audioEnvironment(),
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
        endpoint_path: '/ws/live-voice/media/private-ticket',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    },
  });
  const capture = {
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 7,
  };
  await owner.startCapture(capture);

  const closing = owner.close();
  await closeStarted;
  assert.equal(owner.status().status, 'cleanup_pending');
  await assert.rejects(owner.startCapture(capture), /cleanup is in progress/);
  releaseClose();
  await closing;
  assert.equal(owner.status().status, 'closed');
});

test('formal P1 dedicated downlink overlaps the next real capture and ACKs only rendered audio', async () => {
  const calls = [];
  const bindingsByPath = new Map();
  const sockets = [];
  let activationCount = 0;
  const environment = audioEnvironment((() => {
    let value = 0;
    return () => `capture-${++value}`;
  })());
  const response = {
    interaction_id: 'interaction-1',
    response_id: 'response-duplex-1',
    response_generation: 1,
  };
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
    constructor(binding) {
      super();
      this.serverBinding = binding;
    }
    send(value) {
      this.sent.push(value);
      if (this.serverBinding.direction === 'uplink' && typeof value !== 'string') {
        queueMicrotask(() => this.onmessage?.({
          data: serializeMediaControl({
            type: 'media.ack',
            lease_id: this.serverBinding.lease_id,
            generation: this.serverBinding.generation.value,
            through_seq: 0,
          }),
        }));
      } else if (this.serverBinding.direction === 'downlink' && typeof value === 'string') {
        const control = JSON.parse(value);
        if (control.type === 'media.ack') {
          queueMicrotask(() => this.onmessage?.({
            data: serializeMediaControl({
              type: 'media.detach',
              lease_id: this.serverBinding.lease_id,
              generation: this.serverBinding.generation.value,
              reason_id: 'MEDIA_LOCAL_CLOSE',
              through_seq: control.through_seq,
              business_cancel_count_delta: 0,
            }),
          }));
        }
      }
    }
  }

  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: environment,
    socket_factory: url => {
      const binding = bindingsByPath.get(new URL(url).pathname);
      assert.ok(binding);
      const socket = new DuplexSocket(binding);
      sockets.push(socket);
      queueMicrotask(() => {
        socket.open(binding);
        if (binding.direction === 'downlink') {
          socket.onmessage?.({
            data: encodeAudioFrame(binding, {
              seq: 0,
              sample_cursor: 0,
              samples: new Float32Array(960).fill(0.125),
            }),
          });
        }
      });
      return socket;
    },
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P1_MEDIA_ACTIVATE_METHOD) {
        activationCount += 1;
        const binding = makeUplinkBinding(params, activationCount);
        const path = `/ws/live-voice/media/uplink-${activationCount}`;
        bindingsByPath.set(path, binding);
        return {
          status: 'active',
          reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
          subject_id: `media-subject-${activationCount}`,
          endpoint_path: path,
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
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
                alternatives: [{ raw_text: 'duplex text', display_text: 'duplex text', confidence: null }],
                selected_index: 0,
              },
            },
            provider: {
              provider_id: 'provider-test', implementation_class: 'formal',
              fallback_from: null, model: 'stt-test',
            },
            voice_commit_receipt: 'voice-receipt-duplex-1',
          },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
        const path = '/ws/live-voice/media/downlink-1';
        bindingsByPath.set(path, downlinkBinding);
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
              endpoint_path: path,
              subprotocol: 'live-voice.media.v1',
              ticket_ttl_ms: 30_000,
              binding: downlinkBinding,
              max_pending_frames: 8,
              max_pending_bytes: 131_072,
            },
            provider: {
              provider_id: 'provider-test', implementation_class: 'formal',
              fallback_from: null, model: 'tts-test', voice: 'voice-test',
            },
            presented: false,
          },
        };
      }
      if (method === PRODUCT_P1_MEDIA_PLAYOUT_RECEIPT_METHOD) {
        assert.equal(params.subject_id, 'media-subject-1');
        assert.equal(params.rendered_chunks, 1);
        return {
          status: 'media_playout_acknowledged',
          reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
          receipt_id: 'media-playout-duplex-1',
          duplex_media_observed: true,
          ...params,
        };
      }
      if (method === PRODUCT_P1_MEDIA_CLOSE_METHOD) {
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      throw new Error(`unexpected method ${method}`);
    },
  });

  await owner.startCapture({
    session_id: 'session-1', interaction_id: 'interaction-1', correlation_id: 'correlation-1',
    activation_id: 'activation-1', activation_generation: 7, locale: 'zh-CN',
  });
  environment.worklet.port.onmessage({ data: {
    kind: 'frame', capture_generation: 1, seq: 0, sample_rate_hz: 48_000,
    sample_cursor: 0, context_time_s: 0, samples: new Float32Array(960).fill(0.25),
  } });
  await owner.stopAndRecognize();
  await owner.playAgentText({ response, unit_id: 'unit-duplex-1', text: 'duplex Agent response' });

  assert.equal(owner.status().status, 'capturing');
  assert.equal(activationCount, 2);
  const downlinkSocket = sockets.find(socket => socket.serverBinding.direction === 'downlink');
  assert.ok(downlinkSocket);
  const downlinkControls = downlinkSocket.sent.filter(value => typeof value === 'string').map(JSON.parse);
  assert.equal(downlinkControls.filter(control => control.type === 'media.ack').length, 1);
  assert.ok(calls.some(([method, params]) => (
    method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-1'
  )));
  await owner.close();
  assert.ok(calls.some(([method, params]) => (
    method === PRODUCT_P1_MEDIA_CLOSE_METHOD && params.subject_id === 'media-subject-2'
  )));
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

    await assert.rejects(owner.startCapture({
      session_id: 'session-1',
      interaction_id: 'interaction-1',
      correlation_id: 'correlation-1',
      activation_id: 'activation-1',
      activation_generation: 1,
    }), error => error.reason_id === reason);
    assert.deepEqual(owner.status(), { status: 'failed', reason });
    await owner.close();
  });
}

test('formal P1 never publishes a private transport error message', async () => {
  const owner = new ProductP1VoiceRouteOwner({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    audio_environment: audioEnvironment(),
    socket_factory: () => { throw new Error('socket must not be allocated'); },
    request: async () => { throw new Error('api_key=private-provider-value'); },
  });

  await assert.rejects(owner.startCapture({
    session_id: 'session-1',
    interaction_id: 'interaction-1',
    correlation_id: 'correlation-1',
    activation_id: 'activation-1',
    activation_generation: 1,
  }), /private-provider-value/);

  assert.deepEqual(owner.status(), {
    status: 'failed',
    reason: 'FORMAL_P1_ROUTE_FAILED',
  });
  assert.doesNotMatch(JSON.stringify(owner.status()), /private-provider-value|api_key/);
  await assert.rejects(owner.playAgentText({
    response: {
      interaction_id: 'interaction-1',
      response_id: 'response-1',
      response_generation: 0,
    },
    unit_id: 'unit-1',
    text: 'must not retain failed Speech authority',
  }), /synthesis authority is unavailable/);
  await owner.close();
});
