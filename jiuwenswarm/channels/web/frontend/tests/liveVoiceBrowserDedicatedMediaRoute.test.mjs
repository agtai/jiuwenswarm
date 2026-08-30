import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

import {
  BrowserDedicatedMediaSocketLeaf,
  DEDICATED_MEDIA_SUBPROTOCOL,
  createBrowserDedicatedMediaRoute,
} from '../node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs';
import {
  decodeAudioFrame,
  deserializeMediaControl,
  encodeAudioFrame,
  serializeMediaControl,
} from '../node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs';

function binding(overrides = {}) {
  const direction = overrides.direction ?? 'uplink';
  const generationValue = overrides.generation?.value ?? 7;
  const generation =
    overrides.generation ??
    (direction === 'downlink'
      ? { kind: 'response', id: 'response-01', value: generationValue }
      : { kind: 'capture', id: 'capture-01', value: generationValue });
  const playout = Object.hasOwn(overrides, 'playout')
    ? overrides.playout
    : direction === 'downlink'
      ? { response_id: 'response-01', response_generation: generationValue, unit_id: 'unit-01' }
      : null;
  return {
    lease_id: 'lease-dedicated-01',
    authority_evidence_id: 'authority-dedicated-01',
    connection_id: 'connection-dedicated-01',
    connection_epoch: 3,
    session_id: 'session-dedicated-01',
    media_session_id: 'media-session-dedicated-01',
    interaction_id: 'interaction-dedicated-01',
    track_id: 'track-dedicated-01',
    correlation_id: 'correlation-dedicated-01',
    direction,
    generation,
    frame_format: {
      sample_rate_hz: 8_000,
      samples_per_channel: 160,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
    playout,
    ...overrides,
    generation,
    playout,
  };
}

function mediaFrame(seq = 0, sampleCursor = seq * 160) {
  return {
    seq,
    sample_cursor: sampleCursor,
    samples: Float32Array.from({ length: 160 }, (_, index) => Math.sin(index / 13) * 0.2),
  };
}

function capturedFrame(seq = 0, overrides = {}) {
  const { capture: captureOverrides = {}, format: formatOverrides = {}, ...frameOverrides } = overrides;
  return {
    capture: {
      capture_id: 'capture-01',
      capture_generation: 7,
      track_id: 'track-dedicated-01',
      ...captureOverrides,
    },
    seq,
    sample_cursor: seq * 160,
    context_time_s: seq * 0.02,
    format: {
      encoding: 'pcm_f32',
      sample_rate_hz: 8_000,
      channel_count: 1,
      frame_duration_ms: 20,
      samples_per_channel: 160,
      ...formatOverrides,
    },
    samples: new Float32Array(160).fill(0.125),
    ...frameOverrides,
  };
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
  closes = [];
  throwOnSend = false;

  send(data) {
    if (this.throwOnSend) throw new Error('private socket send failure');
    if (this.readyState !== 1) throw new Error('socket not open');
    this.sent.push(typeof data === 'string' ? data : new Uint8Array(data.buffer, data.byteOffset, data.byteLength).slice());
  }

  close(code, reason) {
    this.closes.push({ code, reason });
    this.readyState = 3;
  }

  open(protocol = DEDICATED_MEDIA_SUBPROTOCOL) {
    this.protocol = protocol;
    this.readyState = 1;
    this.onopen?.({});
  }

  message(data) {
    this.onmessage?.({ data });
  }

  transportClose() {
    this.readyState = 3;
    this.onclose?.({});
  }
}

class FakeDrainScheduler {
  #nextHandle = 1;
  callbacks = new Map();
  cancelled = [];
  delays = [];

  schedule = (callback, delayMs) => {
    const handle = this.#nextHandle++;
    this.callbacks.set(handle, callback);
    this.delays.push(delayMs);
    return handle;
  };

  cancel = handle => {
    this.cancelled.push(handle);
  };

  run(handle = Math.min(...this.callbacks.keys())) {
    const callback = this.callbacks.get(handle);
    assert.equal(typeof callback, 'function');
    callback();
    return handle;
  }
}

function active({
  exactBinding = binding(),
  socket = new FakeSocket(),
  effects,
  maxPendingFrames,
  maxPendingBytes,
  highWater,
  deferDownlinkAck,
  onTerminal,
  onUplinkFrameSent,
  drainRetryDelayMs,
  maxDrainStallRetries,
  drainScheduler,
  endOfTurnCapability,
  continuousEndOfTurn,
  onSpeechStart,
  onEndOfTurn,
  onAudioFrame,
} = {}) {
  const counters = effects ?? { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 };
  const factoryCalls = [];
  const activation = createBrowserDedicatedMediaRoute({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    endpoint_url: 'wss://voice.example.test/ws/live-voice/media',
    media_ticket: 'A'.repeat(43),
    binding: exactBinding,
    provider_available: true,
    transport_available: true,
    socket_factory: (url, protocols) => {
      factoryCalls.push({ url, protocols });
      return socket;
    },
    on_audio_frame: onAudioFrame ?? (() => {
      counters.audio += 1;
    }),
    max_pending_frames: maxPendingFrames,
    max_pending_bytes: maxPendingBytes,
    socket_high_water_bytes: highWater,
    defer_downlink_ack: deferDownlinkAck,
    on_terminal: onTerminal,
    on_uplink_frame_sent: onUplinkFrameSent,
    drain_retry_delay_ms: drainRetryDelayMs,
    max_drain_stall_retries: maxDrainStallRetries,
    schedule_drain_retry: drainScheduler?.schedule,
    cancel_drain_retry: drainScheduler?.cancel,
    end_of_turn_capability: endOfTurnCapability,
    continuous_end_of_turn: continuousEndOfTurn,
    on_speech_start: onSpeechStart,
    on_end_of_turn: onEndOfTurn,
  });
  assert.equal(activation.active, true);
  return { activation, socket, effects: counters, factoryCalls };
}

function attach(route) {
  route.socket.open();
  const auth = JSON.parse(route.socket.sent.shift());
  assert.equal(auth.type, 'media.auth');
  assert.equal(auth.contract_version, 'live-voice.media-auth.v1');
  assert.match(auth.media_ticket, /^[A-Za-z0-9_-]{32,128}$/);
  assert.deepEqual(auth.binding, JSON.parse(serializeMediaControl({ type: 'media.attach', binding: route.activation.binding })).binding);
  route.socket.message(serializeMediaControl({ type: 'media.attach', binding: route.activation.binding }));
  assert.equal(route.activation.leaf.attached, true);
}

function closedLocalStopReceipt(receipt, overrides = {}) {
  const selected = { ...receipt, ...overrides };
  const response = selected.response;
  const cursors = selected.confirmed_cursor_before_stop;
  const sources = selected.browser_sources;
  const timing = selected.timing;
  return Object.freeze({
    ...selected,
    response: Object.freeze({ ...response }),
    confirmed_cursor_before_stop: Object.freeze([...cursors].map(cursor => Object.freeze({ ...cursor }))),
    browser_sources: Object.freeze({
      ...sources,
      stop_request: Object.freeze({ ...sources.stop_request }),
      disconnect: Object.freeze({ ...sources.disconnect }),
    }),
    timing: Object.freeze({ ...timing }),
  });
}

function frozenWithout(value, omittedField) {
  return Object.freeze(Object.fromEntries(Object.entries(value).filter(([field]) => field !== omittedField)));
}

function localStopReceipt(route, confirmedThroughSeq = null) {
  return closedLocalStopReceipt({
    kind: 'browser_audio.local_stop.v1',
    outcome: 'local_fence_established',
    response: {
      interaction_id: route.activation.binding.interaction_id,
      response_id: 'response-01',
      response_generation: 7,
    },
    reason: 'interrupted',
    local_fence_established: true,
    confirmed_cursor_before_stop: [
      {
        unit_id: 'unit-01',
        contiguous_through_seq: confirmedThroughSeq,
      },
    ],
    browser_sources: {
      source_count: 1,
      stop_request: { status: 'completed', attempted_count: 1, completed_count: 1, failed_count: 0 },
      disconnect: { status: 'completed', attempted_count: 1, completed_count: 1, failed_count: 0 },
    },
    timing: { status: 'confirmed', requested_at_monotonic_ms: 1, confirmed_at_monotonic_ms: 2, duration_ms: 1 },
    physical_heard: 'unproven',
    physical_silence: 'unproven',
    business_cancel_count_before: 0,
    business_cancel_count_after: 0,
    business_cancel_count_delta: 0,
  });
}

test('EOT cross-language fixture round trips without cursor, item, transcript, or business authority', () => {
  const fixture = JSON.parse(readFileSync(resolve(process.cwd(), '../../../../tests/fixtures/live_voice_media_transport_v1/end_of_turn.json'), 'utf8'));
  const decoded = deserializeMediaControl(JSON.stringify(fixture.control));
  assert.deepEqual(decoded, Object.fromEntries(Object.entries(fixture.control).filter(([key]) => key !== 'contract_version')));
  assert.deepEqual(deserializeMediaControl(serializeMediaControl(decoded)), decoded);
  assert.equal(Object.hasOwn(decoded, 'audio_cursor'), false);
  assert.equal(Object.hasOwn(decoded, 'item_id'), false);
  assert.equal(Object.hasOwn(decoded, 'transcript'), false);
  assert.equal(decoded.create_response, false);
  assert.equal(decoded.interrupt_response, false);
  assert.equal(decoded.business_cancel_count_delta, 0);
});

test('uplink requires server attach then sends bounded LVM1 frames retained through ACK', () => {
  const route = active({ maxPendingFrames: 1 });
  assert.equal(route.socket.binaryType, 'arraybuffer');
  assert.deepEqual(route.factoryCalls, [
    {
      url: 'wss://voice.example.test/ws/live-voice/media',
      protocols: [DEDICATED_MEDIA_SUBPROTOCOL],
    },
  ]);
  assert.deepEqual(route.activation.leaf.sendCaptureFrame(capturedFrame()), {
    accepted: false,
    reason_id: 'MEDIA_NOT_ATTACHED',
  });

  attach(route);
  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame()).accepted, true);
  assert.equal(route.socket.sent.length, 1);
  assert.equal(new TextDecoder().decode(route.socket.sent[0].subarray(0, 4)), 'LVM1');
  assert.equal(decodeAudioFrame(route.activation.binding, route.socket.sent[0]).seq, 0);
  assert.deepEqual(route.activation.leaf.sendCaptureFrame(capturedFrame(1)), {
    accepted: false,
    reason_id: 'MEDIA_BACKPRESSURE_LIMIT',
  });

  route.socket.message(
    serializeMediaControl({
      type: 'media.ack',
      lease_id: route.activation.binding.lease_id,
      generation: route.activation.binding.generation.value,
      through_seq: 0,
    })
  );
  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame(1)).accepted, true);
  assert.equal(decodeAudioFrame(route.activation.binding, route.socket.sent[1]).seq, 1);
  assert.equal(route.effects.audio, 0);
  assert.equal(route.activation.capability.registered_route_observed, false);
  assert.equal(route.activation.capability.route_to_disk_zero_persistence_observed, false);
  assert.equal(route.activation.capability.formal_route_ready, false);
});

test('socket leaf cannot bypass the same-origin activation factory', () => {
  assert.throws(() => new BrowserDedicatedMediaSocketLeaf({}, new FakeSocket(), 1024), /require the same-origin factory/);
});

test('socket bufferedAmount backpressure autonomously drains without retrying or dropping a frame', () => {
  const drainScheduler = new FakeDrainScheduler();
  const sentSequences = [];
  const route = active({
    maxPendingFrames: 1,
    highWater: 1024,
    drainScheduler,
    drainRetryDelayMs: 7,
    onUplinkFrameSent: seq => sentSequences.push(seq),
  });
  attach(route);
  route.socket.bufferedAmount = 1024;

  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame()).accepted, true);
  assert.equal(route.socket.sent.length, 0);
  assert.deepEqual(sentSequences, []);
  assert.deepEqual(route.activation.leaf.sendCaptureFrame(capturedFrame(1)), {
    accepted: false,
    reason_id: 'MEDIA_BACKPRESSURE_LIMIT',
  });

  assert.deepEqual(drainScheduler.delays, [7]);
  const scheduledHandle = drainScheduler.run();
  assert.equal(route.socket.sent.length, 0);
  assert.equal(drainScheduler.callbacks.size, 2);

  route.socket.bufferedAmount = 0;
  drainScheduler.run(2);
  assert.equal(route.socket.sent.length, 1);
  assert.deepEqual(sentSequences, [0]);
  assert.equal(decodeAudioFrame(route.activation.binding, route.socket.sent[0]).seq, 0);

  route.socket.message(
    serializeMediaControl({
      type: 'media.ack',
      lease_id: route.activation.binding.lease_id,
      generation: route.activation.binding.generation.value,
      through_seq: 0,
    })
  );
  assert.ok(drainScheduler.cancelled.includes(3));
  drainScheduler.run(scheduledHandle);
  assert.equal(route.socket.sent.length, 1);
  assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
});

test('persistent socket backpressure fails closed after the bounded stall window', () => {
  const drainScheduler = new FakeDrainScheduler();
  const terminal = [];
  const route = active({
    maxPendingFrames: 1,
    highWater: 1024,
    drainScheduler,
    drainRetryDelayMs: 5,
    maxDrainStallRetries: 2,
    onTerminal: event => terminal.push(event),
  });
  attach(route);
  route.socket.bufferedAmount = 1024;

  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame()).accepted, true);
  drainScheduler.run(1);
  drainScheduler.run(2);

  assert.equal(route.activation.leaf.closed, true);
  assert.deepEqual(terminal, [
    {
      reason_id: 'MEDIA_TRANSPORT_SEND_FAILED',
      source: 'transport_close',
      direction: 'uplink',
      attached_before_close: true,
    },
  ]);
  assert.deepEqual(route.activation.leaf.sendCaptureFrame(capturedFrame(1)), {
    accepted: false,
    reason_id: 'MEDIA_TRANSPORT_SEND_FAILED',
  });
  const detach = route.socket.sent.map(value => (typeof value === 'string' ? deserializeMediaControl(value) : null)).find(Boolean);
  assert.equal(detach.reason_id, 'MEDIA_TRANSPORT_SEND_FAILED');
  assert.equal(detach.business_cancel_count_delta, 0);
  assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
});

test('drain scheduler failure fails closed and cancelled-generation callbacks stay inert', () => {
  for (const schedule of [
    () => {
      throw new Error('private scheduler failure');
    },
    callback => {
      callback();
      return 1;
    },
  ]) {
    const terminal = [];
    const route = active({
      maxPendingFrames: 1,
      highWater: 1024,
      drainScheduler: { schedule, cancel: () => {} },
      onTerminal: event => terminal.push(event),
    });
    attach(route);
    route.socket.bufferedAmount = 1024;
    route.activation.leaf.sendCaptureFrame(capturedFrame());
    assert.equal(route.activation.leaf.closed, true);
    assert.deepEqual(terminal, [
      {
        reason_id: 'MEDIA_TRANSPORT_SEND_FAILED',
        source: 'internal_failure',
        direction: 'uplink',
        attached_before_close: true,
      },
    ]);
    assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
  }

  const drainScheduler = new FakeDrainScheduler();
  drainScheduler.cancel = handle => {
    drainScheduler.cancelled.push(handle);
    throw new Error('private cancellation failure');
  };
  const terminal = [];
  const route = active({
    maxPendingFrames: 1,
    highWater: 1024,
    drainScheduler,
    onTerminal: event => terminal.push(event),
  });
  attach(route);
  route.socket.bufferedAmount = 1024;
  route.activation.leaf.sendCaptureFrame(capturedFrame());
  route.activation.leaf.close('MEDIA_LOCAL_CLOSE');
  drainScheduler.run(1);
  assert.equal(route.socket.sent.filter(value => typeof value !== 'string').length, 0);
  assert.equal(terminal.length, 1);
  assert.equal(terminal[0].source, 'local_close');
  assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });

  const peerScheduler = new FakeDrainScheduler();
  const peer = active({ maxPendingFrames: 1, highWater: 1024, drainScheduler: peerScheduler });
  attach(peer);
  peer.socket.bufferedAmount = 1024;
  peer.activation.leaf.sendCaptureFrame(capturedFrame());
  peer.socket.message(
    serializeMediaControl({
      type: 'media.detach',
      lease_id: peer.activation.binding.lease_id,
      generation: peer.activation.binding.generation.value,
      reason_id: 'MEDIA_PEER_CLOSE',
      through_seq: null,
      business_cancel_count_delta: 0,
    })
  );
  assert.deepEqual(peerScheduler.cancelled, [1]);
  peerScheduler.run(1);
  assert.equal(peer.socket.sent.filter(value => typeof value !== 'string').length, 0);
  assert.equal(peer.activation.leaf.closed, true);
});

test('downlink accepts exact binary sequence, invokes audio once, and returns typed ACK', () => {
  const effects = { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 };
  const route = active({ exactBinding: binding({ direction: 'downlink' }), effects });
  attach(route);

  route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame()));

  assert.equal(effects.audio, 1);
  assert.equal(route.socket.sent.length, 1);
  assert.deepEqual(deserializeMediaControl(route.socket.sent[0]), {
    type: 'media.ack',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    through_seq: 0,
  });
  assert.deepEqual(effects, { audio: 1, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
});

test('downlink reports a bounded browser consumer reason without changing the wire detach', () => {
  const terminal = [];
  const route = active({
    exactBinding: binding({ direction: 'downlink' }),
    onAudioFrame: () => {
      throw Object.assign(new Error('private browser output detail'), {
        reason: 'PLAYOUT_SAMPLE_RATE_MISMATCH',
        output_device_id: 'speaker-secret',
      });
    },
    onTerminal: event => terminal.push(event),
  });
  attach(route);

  route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame()));

  assert.deepEqual(deserializeMediaControl(route.socket.sent[0]), {
    type: 'media.detach',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    reason_id: 'MEDIA_CONSUMER_FAILED',
    through_seq: null,
    business_cancel_count_delta: 0,
  });
  assert.deepEqual(terminal, [{
    reason_id: 'MEDIA_CONSUMER_FAILED',
    consumer_reason_id: 'PLAYOUT_SAMPLE_RATE_MISMATCH',
    source: 'internal_failure',
    direction: 'downlink',
    attached_before_close: true,
  }]);
  assert.equal(JSON.stringify(terminal).includes('speaker-secret'), false);
  assert.equal(JSON.stringify(terminal).includes('private browser output detail'), false);
});

test('downlink can defer its bounded ACK until browser rendering confirms the frame', () => {
  const effects = { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 };
  const route = active({
    exactBinding: binding({ direction: 'downlink' }),
    effects,
    deferDownlinkAck: true,
  });
  attach(route);

  route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame(0)));
  route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame(1)));
  assert.equal(effects.audio, 2);
  assert.equal(route.socket.sent.length, 0);
  assert.throws(
    () => route.activation.leaf.acknowledgeDownlinkThrough(2),
    error => error?.reasonId === 'MEDIA_ACK_UNSENT'
  );
  assert.throws(
    () => route.activation.leaf.acknowledgeDownlinkThrough(1),
    error => error?.reasonId === 'MEDIA_ACK_OUT_OF_ORDER'
  );

  route.activation.leaf.acknowledgeDownlinkThrough(0);
  route.activation.leaf.acknowledgeDownlinkThrough(1);
  assert.deepEqual(route.socket.sent.map(deserializeMediaControl), [
    {
      type: 'media.ack',
      lease_id: route.activation.binding.lease_id,
      generation: route.activation.binding.generation.value,
      through_seq: 0,
    },
    {
      type: 'media.ack',
      lease_id: route.activation.binding.lease_id,
      generation: route.activation.binding.generation.value,
      through_seq: 1,
    },
  ]);
});

test('deferred downlink rejects a peer that exceeds the advertised unrendered window', () => {
  const effects = { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 };
  const route = active({
    exactBinding: binding({ direction: 'downlink' }),
    effects,
    deferDownlinkAck: true,
    maxPendingFrames: 1,
  });
  attach(route);
  route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame(0)));
  route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame(1)));

  assert.equal(effects.audio, 1);
  assert.equal(route.activation.leaf.closed, true);
  assert.equal(deserializeMediaControl(route.socket.sent[0]).reason_id, 'MEDIA_TRANSPORT_PROTOCOL_ERROR');
});

test('wrong attach, stale capture, cursor gap, and malformed control terminally fence the leaf', () => {
  const cases = [
    route => {
      route.socket.open();
      route.socket.message(
        serializeMediaControl({
          type: 'media.attach',
          binding: binding({ session_id: 'wrong-session' }),
        })
      );
    },
    route => {
      attach(route);
      route.activation.leaf.sendCaptureFrame(
        capturedFrame(0, {
          capture: { capture_generation: 8 },
        })
      );
    },
    route => {
      attach(route);
      route.activation.leaf.sendCaptureFrame(capturedFrame(0, { sample_cursor: 160 }));
    },
    route => {
      route.socket.open();
      route.socket.message('{"not":"closed-control"}');
    },
  ];
  const reasons = ['MEDIA_BINDING_MISMATCH', 'MEDIA_STALE_GENERATION', 'MEDIA_INVALID_FRAME', 'MEDIA_TRANSPORT_PROTOCOL_ERROR'];

  for (let index = 0; index < cases.length; index += 1) {
    const route = active();
    cases[index](route);
    assert.equal(route.activation.leaf.closed, true);
    assert.equal(route.socket.closes.length, 1);
    const lastControl = route.socket.sent.filter(item => typeof item === 'string').at(-1);
    assert.equal(typeof lastControl, 'string', `case ${index} did not send terminal detach`);
    const detach = deserializeMediaControl(lastControl);
    assert.equal(detach.type, 'media.detach');
    assert.equal(detach.reason_id, reasons[index]);
    assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
  }
});

test('local playback stop maps the exact confirmed unit and never escalates business cancel', () => {
  const route = active({ exactBinding: binding({ direction: 'downlink' }) });
  attach(route);
  for (let seq = 0; seq <= 4; seq += 1) {
    route.socket.message(encodeAudioFrame(route.activation.binding, mediaFrame(seq)));
  }
  const localReceipt = localStopReceipt(route, 4);

  const control = route.activation.leaf.sendLocalPlaybackStop(localReceipt);

  assert.equal(control.confirmed_through_seq, 4);
  assert.equal(control.business_cancel_count_delta, 0);
  const controls = route.socket.sent.filter(item => typeof item === 'string').map(item => deserializeMediaControl(item));
  assert.deepEqual(
    controls.find(item => item.type === 'media.playback_stop_receipt'),
    control
  );
  assert.equal(controls.at(-1).type, 'media.detach');
  assert.equal(controls.at(-1).business_cancel_count_delta, 0);
  assert.equal(route.activation.leaf.closed, true);
  assert.throws(
    () => route.activation.leaf.sendLocalPlaybackStop(closedLocalStopReceipt(localReceipt, { business_cancel_count_delta: 1 })),
    /cannot carry business cancellation/
  );
  assert.throws(
    () =>
      route.activation.leaf.sendLocalPlaybackStop(
        closedLocalStopReceipt(localReceipt, {
          confirmed_cursor_before_stop: [{ unit_id: 'unit-01', contiguous_through_seq: 5 }],
        })
      ),
    /cannot confirm an unreceived media frame/
  );
});

test('active leaf rejects forged or contradictory BrowserAudio stop truth before socket and state effects', () => {
  const route = active({ exactBinding: binding({ direction: 'downlink' }) });
  attach(route);
  const trusted = localStopReceipt(route);
  const notAttempted = Object.freeze({
    status: 'not_attempted',
    attempted_count: 0,
    completed_count: 0,
    failed_count: 0,
  });
  const invalidReceipts = [
    ...Object.keys(trusted).map(field => frozenWithout(trusted, field)),
    ...Object.keys(trusted.response).map(field =>
      closedLocalStopReceipt(trusted, {
        response: frozenWithout(trusted.response, field),
      })
    ),
    ...Object.keys(trusted.browser_sources.stop_request).map(field =>
      closedLocalStopReceipt(trusted, {
        browser_sources: {
          ...trusted.browser_sources,
          stop_request: frozenWithout(trusted.browser_sources.stop_request, field),
        },
      })
    ),
    ...Object.keys(trusted.browser_sources.disconnect).map(field =>
      closedLocalStopReceipt(trusted, {
        browser_sources: {
          ...trusted.browser_sources,
          disconnect: frozenWithout(trusted.browser_sources.disconnect, field),
        },
      })
    ),
    ...Object.keys(trusted.timing).map(field =>
      closedLocalStopReceipt(trusted, {
        timing: frozenWithout(trusted.timing, field),
      })
    ),
    ...Object.keys(trusted.confirmed_cursor_before_stop[0]).map(field =>
      closedLocalStopReceipt(trusted, {
        confirmed_cursor_before_stop: [frozenWithout(trusted.confirmed_cursor_before_stop[0], field)],
      })
    ),
    closedLocalStopReceipt(trusted, { kind: 'browser_audio.local_stop.v0' }),
    closedLocalStopReceipt(trusted, { local_fence_established: false }),
    closedLocalStopReceipt(trusted, {
      business_cancel_count_before: 900,
      business_cancel_count_after: 1,
      business_cancel_count_delta: 0,
    }),
    closedLocalStopReceipt(trusted, {
      browser_sources: {
        ...trusted.browser_sources,
        disconnect: notAttempted,
      },
    }),
    closedLocalStopReceipt(trusted, {
      timing: {
        ...trusted.timing,
        duration_ms: 99,
      },
    }),
    closedLocalStopReceipt(trusted, { physical_silence: 'confirmed' }),
    Object.freeze({ ...trusted, unexpected_private_fact: 'forged' }),
    closedLocalStopReceipt(trusted, {
      outcome: 'target_mismatch',
      local_fence_established: false,
      confirmed_cursor_before_stop: [],
      browser_sources: {
        source_count: 0,
        stop_request: notAttempted,
        disconnect: notAttempted,
      },
    }),
  ];

  for (const receipt of invalidReceipts) {
    const sentBefore = route.socket.sent.length;
    const closesBefore = route.socket.closes.length;
    assert.throws(() => route.activation.leaf.sendLocalPlaybackStop(receipt), TypeError);
    assert.equal(route.socket.sent.length, sentBefore);
    assert.equal(route.socket.closes.length, closesBefore);
    assert.equal(route.activation.leaf.closed, false);
    assert.equal(route.activation.leaf.attached, true);
  }
  const controls = route.socket.sent.filter(item => typeof item === 'string').map(item => deserializeMediaControl(item));
  assert.equal(
    controls.some(item => item.type === 'media.playback_stop_receipt'),
    false
  );
  assert.equal(
    controls.some(item => item.type === 'media.detach'),
    false
  );
  assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
});

test('source-cleanup unknown receipt preserves the local fence without claiming physical silence', () => {
  const route = active({ exactBinding: binding({ direction: 'downlink' }) });
  attach(route);
  const base = localStopReceipt(route);
  const receipt = closedLocalStopReceipt(base, {
    outcome: 'local_fence_established_source_unknown',
    browser_sources: {
      source_count: 1,
      stop_request: {
        status: 'unknown',
        attempted_count: 1,
        completed_count: 0,
        failed_count: 1,
      },
      disconnect: base.browser_sources.disconnect,
    },
  });

  const control = route.activation.leaf.sendLocalPlaybackStop(receipt);

  assert.equal(control.outcome, 'local_fence_established_source_unknown');
  assert.equal(control.business_cancel_count_delta, 0);
  assert.equal(route.activation.leaf.closed, true);
  assert.equal(route.socket.closes.length, 1);
});

test('unattached, closed, and send-failed stop paths return no false delivery receipt', () => {
  const cases = [];

  const unattached = active({ exactBinding: binding({ direction: 'downlink' }) });
  unattached.socket.open();
  cases.push({ route: unattached, expectedClose: 'MEDIA_LOCAL_CLOSE' });

  const lost = active({ exactBinding: binding({ direction: 'downlink' }) });
  attach(lost);
  lost.socket.transportClose();
  cases.push({ route: lost, expectedClose: 'MEDIA_TRANSPORT_CLOSED' });

  const sendFailed = active({ exactBinding: binding({ direction: 'downlink' }) });
  attach(sendFailed);
  sendFailed.socket.throwOnSend = true;
  cases.push({ route: sendFailed, expectedClose: 'MEDIA_TRANSPORT_SEND_FAILED' });

  for (const { route, expectedClose } of cases) {
    let returnedReceipt = false;
    assert.throws(
      () => {
        route.activation.leaf.sendLocalPlaybackStop(localStopReceipt(route));
        returnedReceipt = true;
      },
      error => error?.reasonId === 'MEDIA_STOP_NOT_DELIVERED'
    );
    const retained = route.activation.leaf.close();
    const controls = route.socket.sent
      .filter(item => typeof item === 'string' && JSON.parse(item).type !== 'media.auth')
      .map(item => deserializeMediaControl(item));
    assert.equal(returnedReceipt, false);
    assert.equal(
      controls.some(item => item.type === 'media.playback_stop_receipt'),
      false
    );
    assert.equal(retained.reason_id, expectedClose);
    assert.equal(retained.business_cancel_count_delta, 0);
    assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
  }
});

test('uplink completion waits for the exact server detach receipt before physical close', async () => {
  const terminal = [];
  let route;
  route = active({
    onTerminal: event => terminal.push({ event, closed: route.activation.leaf.closed, attached: route.activation.leaf.attached }),
  });
  attach(route);
  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame()).accepted, true);
  route.socket.message(
    serializeMediaControl({
      type: 'media.ack',
      lease_id: route.activation.binding.lease_id,
      generation: route.activation.binding.generation.value,
      through_seq: 0,
    })
  );

  const completion = route.activation.leaf.completeUplink('MEDIA_LOCAL_CLOSE');
  const detach = deserializeMediaControl(route.socket.sent.at(-1));
  assert.equal(detach.type, 'media.detach');
  assert.equal(route.socket.closes.length, 0);

  route.socket.message(serializeMediaControl(detach));
  const closed = await completion;

  assert.equal(closed.reason_id, 'MEDIA_LOCAL_CLOSE');
  assert.equal(closed.business_cancel_count_delta, 0);
  assert.equal(route.activation.leaf.closed, true);
  assert.equal(route.socket.closes.length, 1);
  assert.deepEqual(terminal, [
    {
      event: {
        reason_id: 'MEDIA_LOCAL_CLOSE',
        source: 'expected_completion',
        direction: 'uplink',
        attached_before_close: true,
      },
      closed: true,
      attached: false,
    },
  ]);
});

test('negotiated EOT is content-free, one-shot, and preserves pending uplink completion', async () => {
  const observedStarts = [];
  const observedEnds = [];
  const route = active({
    endOfTurnCapability: 'media.end_of_turn.v1',
    onSpeechStart: event => observedStarts.push(event),
    onEndOfTurn: event => observedEnds.push(event),
  });
  attach(route);
  const completion = route.activation.leaf.completeUplink('MEDIA_LOCAL_CLOSE');
  const detach = deserializeMediaControl(route.socket.sent.at(-1));
  const speechStart = {
    type: 'media.speech_start',
    capability_version: 'media.end_of_turn.v1',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    detector: 'server_vad',
    provider_start_ms: 320,
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  };
  const endOfTurn = {
    type: 'media.end_of_turn',
    capability_version: 'media.end_of_turn.v1',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    detector: 'server_vad',
    speech_started_observed: true,
    provider_start_ms: 320,
    provider_end_ms: 1840,
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  };
  route.socket.message(serializeMediaControl(speechStart));
  assert.deepEqual(observedStarts, [speechStart]);
  assert.deepEqual(observedEnds, []);
  assert.equal(route.socket.closes.length, 0);
  route.socket.message(serializeMediaControl(endOfTurn));
  assert.deepEqual(observedEnds, [endOfTurn]);
  assert.equal(route.socket.closes.length, 0);
  assert.deepEqual(route.effects, {
    audio: 0,
    agent: 0,
    tool: 0,
    task: 0,
    history: 0,
    persistence: 0,
  });
  route.socket.message(serializeMediaControl(detach));
  assert.equal((await completion).reason_id, 'MEDIA_LOCAL_CLOSE');
});

test('speech boundary consumer failures retain a bounded internal stage and keep the wire detach generic', () => {
  const controlFor = (route, type) => ({
    type,
    capability_version: 'media.end_of_turn.v1',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    detector: 'server_vad',
    ...(type === 'media.speech_start'
      ? { provider_start_ms: 320 }
      : {
          speech_started_observed: true,
          provider_start_ms: 320,
          provider_end_ms: 1840,
        }),
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  });
  const scenarios = [
    {
      expected: 'ADAPTER_SPEECH_START_CALLBACK_FAILED',
      configure: terminal => active({
        endOfTurnCapability: 'media.end_of_turn.v1',
        onSpeechStart: () => {
          throw new Error('private speech-start callback detail');
        },
        onEndOfTurn: () => undefined,
        onTerminal: event => terminal.push(event),
      }),
      deliver: route => route.socket.message(serializeMediaControl(controlFor(route, 'media.speech_start'))),
    },
    {
      expected: 'ADAPTER_END_OF_TURN_CALLBACK_FAILED',
      configure: terminal => active({
        endOfTurnCapability: 'media.end_of_turn.v1',
        onSpeechStart: () => undefined,
        onEndOfTurn: () => {
          throw Object.assign(new Error('private end-of-turn callback detail'), { device_id: 'microphone-secret' });
        },
        onTerminal: event => terminal.push(event),
      }),
      deliver: route => {
        route.socket.message(serializeMediaControl(controlFor(route, 'media.speech_start')));
        route.socket.message(serializeMediaControl(controlFor(route, 'media.end_of_turn')));
      },
    },
  ];

  for (const scenario of scenarios) {
    const terminal = [];
    const route = scenario.configure(terminal);
    attach(route);
    scenario.deliver(route);

    assert.equal(route.activation.leaf.closed, true);
    assert.equal(deserializeMediaControl(route.socket.sent.at(-1)).reason_id, 'MEDIA_CONSUMER_FAILED');
    assert.deepEqual(terminal, [{
      reason_id: 'MEDIA_CONSUMER_FAILED',
      consumer_reason_id: scenario.expected,
      source: 'internal_failure',
      direction: 'uplink',
      attached_before_close: true,
    }]);
    assert.equal(JSON.stringify(terminal).includes('private'), false);
    assert.equal(JSON.stringify(terminal).includes('microphone-secret'), false);
    assert.deepEqual(route.effects, {
      audio: 0,
      agent: 0,
      tool: 0,
      task: 0,
      history: 0,
      persistence: 0,
    });
  }
});

test('Native continuous EOT admits prefix-overlapped Provider speech cycles and rejects a stale replay', () => {
  const observedStarts = [];
  const observedEnds = [];
  const route = active({
    endOfTurnCapability: 'media.end_of_turn.v1',
    continuousEndOfTurn: true,
    onSpeechStart: event => observedStarts.push(event.provider_start_ms),
    onEndOfTurn: event => observedEnds.push(event.provider_end_ms),
  });
  attach(route);
  const boundary = (type, start, end = null) => ({
    type,
    capability_version: 'media.end_of_turn.v1',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    detector: 'server_vad',
    ...(type === 'media.speech_start'
      ? {
          provider_start_ms: start,
        }
      : {
          speech_started_observed: true,
          provider_start_ms: start,
          provider_end_ms: end,
        }),
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  });

  route.socket.message(serializeMediaControl(boundary('media.speech_start', 100)));
  route.socket.message(serializeMediaControl(boundary('media.end_of_turn', 100, 700)));
  // Realtime VAD includes leading audio in speech_start and trailing audio in
  // speech_stopped, so consecutive provider intervals may legitimately
  // overlap. This reproduces the observed 512 ms semantic-VAD overlap.
  route.socket.message(serializeMediaControl(boundary('media.speech_start', 188)));
  route.socket.message(serializeMediaControl(boundary('media.end_of_turn', 188, 1400)));

  assert.deepEqual(observedStarts, [100, 188]);
  assert.deepEqual(observedEnds, [700, 1400]);
  assert.equal(route.activation.leaf.closed, false);

  route.socket.message(serializeMediaControl(boundary('media.speech_start', 100)));
  assert.equal(route.activation.leaf.closed, true);
  assert.deepEqual(route.effects, {
    audio: 0,
    agent: 0,
    tool: 0,
    task: 0,
    history: 0,
    persistence: 0,
  });
});

test('unnegotiated, duplicate, stale, or out-of-order speech boundaries fail closed with zero business effects', () => {
  const exact = active();
  attach(exact);
  const speechStart = {
    type: 'media.speech_start',
    capability_version: 'media.end_of_turn.v1',
    lease_id: exact.activation.binding.lease_id,
    generation: exact.activation.binding.generation.value,
    detector: 'server_vad',
    provider_start_ms: 10,
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  };
  exact.socket.message(serializeMediaControl(speechStart));
  assert.equal(exact.activation.leaf.closed, true);
  assert.deepEqual(exact.effects, {
    audio: 0,
    agent: 0,
    tool: 0,
    task: 0,
    history: 0,
    persistence: 0,
  });

  const observed = [];
  const duplicate = active({
    endOfTurnCapability: 'media.end_of_turn.v1',
    onSpeechStart: event => observed.push(event),
    onEndOfTurn: () => undefined,
  });
  attach(duplicate);
  const duplicateControl = {
    ...speechStart,
    lease_id: duplicate.activation.binding.lease_id,
    generation: duplicate.activation.binding.generation.value,
  };
  duplicate.socket.message(serializeMediaControl(duplicateControl));
  duplicate.socket.message(serializeMediaControl(duplicateControl));
  assert.equal(observed.length, 1);
  assert.equal(duplicate.activation.leaf.closed, true);
  assert.deepEqual(duplicate.effects, exact.effects);

  const outOfOrder = active({
    endOfTurnCapability: 'media.end_of_turn.v1',
    onSpeechStart: () => undefined,
    onEndOfTurn: () => undefined,
  });
  attach(outOfOrder);
  outOfOrder.socket.message(serializeMediaControl({
    type: 'media.end_of_turn',
    capability_version: 'media.end_of_turn.v1',
    lease_id: outOfOrder.activation.binding.lease_id,
    generation: outOfOrder.activation.binding.generation.value,
    detector: 'server_vad',
    speech_started_observed: true,
    provider_start_ms: 10,
    provider_end_ms: 20,
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  }));
  assert.equal(outOfOrder.activation.leaf.closed, true);
  assert.deepEqual(outOfOrder.effects, exact.effects);
});

test('a fully rendered downlink exact detach is expected completion while an early detach is peer-owned', () => {
  const completedEvents = [];
  const completed = active({
    exactBinding: binding({ direction: 'downlink' }),
    deferDownlinkAck: true,
    onTerminal: event => completedEvents.push(event),
  });
  attach(completed);
  completed.socket.message(encodeAudioFrame(completed.activation.binding, mediaFrame(0)));
  completed.activation.leaf.acknowledgeDownlinkThrough(0);
  completed.socket.message(
    serializeMediaControl({
      type: 'media.detach',
      lease_id: completed.activation.binding.lease_id,
      generation: completed.activation.binding.generation.value,
      reason_id: 'MEDIA_LOCAL_CLOSE',
      through_seq: 0,
      business_cancel_count_delta: 0,
    })
  );
  assert.deepEqual(completedEvents, [
    {
      reason_id: 'MEDIA_LOCAL_CLOSE',
      source: 'expected_completion',
      direction: 'downlink',
      attached_before_close: true,
    },
  ]);

  const peerEvents = [];
  const peer = active({
    exactBinding: binding({ direction: 'downlink' }),
    deferDownlinkAck: true,
    onTerminal: event => peerEvents.push(event),
  });
  attach(peer);
  peer.socket.message(
    serializeMediaControl({
      type: 'media.detach',
      lease_id: peer.activation.binding.lease_id,
      generation: peer.activation.binding.generation.value,
      reason_id: 'MEDIA_LOCAL_CLOSE',
      through_seq: null,
      business_cancel_count_delta: 0,
    })
  );
  assert.deepEqual(peerEvents, [
    {
      reason_id: 'MEDIA_LOCAL_CLOSE',
      source: 'peer_detach',
      direction: 'downlink',
      attached_before_close: true,
    },
  ]);
});

test('uplink completion rejects missing or foreign server receipts without business effects', async () => {
  const cases = [
    detach => ({ ...detach, lease_id: 'foreign-lease' }),
    detach => ({ ...detach, generation: detach.generation + 1 }),
    detach => ({ ...detach, reason_id: 'MEDIA_PEER_CLOSE' }),
    detach => ({ ...detach, through_seq: 1 }),
  ];

  for (const mutate of cases) {
    const route = active();
    attach(route);
    const completion = route.activation.leaf.completeUplink('MEDIA_LOCAL_CLOSE');
    const detach = deserializeMediaControl(route.socket.sent.at(-1));
    route.socket.message(serializeMediaControl(mutate(detach)));
    await assert.rejects(completion, error => error?.reasonId === 'MEDIA_TRANSPORT_PROTOCOL_ERROR');
    assert.equal(route.activation.leaf.closed, true);
    assert.equal(route.socket.closes.length, 1);
    assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
  }

  const lost = active();
  attach(lost);
  const completion = lost.activation.leaf.completeUplink('MEDIA_LOCAL_CLOSE');
  lost.socket.transportClose();
  await assert.rejects(completion, error => error?.reasonId === 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(lost.activation.leaf.closed, true);
  assert.equal(lost.socket.closes.length, 0);
});

test('Alpha socket uses a fixed URL and sends one exact first-frame ticket without retaining it in route snapshots', () => {
  const route = active();

  assert.deepEqual(route.factoryCalls, [
    {
      url: 'wss://voice.example.test/ws/live-voice/media',
      protocols: ['live-voice.media.v1'],
    },
  ]);
  assert.equal(JSON.stringify(route.activation).includes('A'.repeat(43)), false);

  route.socket.open();
  assert.equal(route.socket.sent.length, 1);
  const auth = JSON.parse(route.socket.sent[0]);
  assert.deepEqual(auth, {
    type: 'media.auth',
    contract_version: 'live-voice.media-auth.v1',
    media_ticket: 'A'.repeat(43),
    binding: JSON.parse(serializeMediaControl({ type: 'media.attach', binding: route.activation.binding })).binding,
  });
  assert.equal(JSON.stringify(route.activation).includes('A'.repeat(43)), false);

  route.activation.leaf.close();
  assert.equal(JSON.stringify(route.activation).includes('A'.repeat(43)), false);
});

test('Alpha auth send failure is terminal before attach with zero media or business effects', () => {
  const socket = new FakeSocket();
  socket.throwOnSend = true;
  const terminal = [];
  const route = active({ socket, onTerminal: event => terminal.push(event) });

  socket.open();

  assert.equal(route.activation.leaf.closed, true);
  assert.equal(route.activation.leaf.attached, false);
  assert.equal(socket.sent.length, 0);
  assert.deepEqual(terminal, [
    {
      reason_id: 'MEDIA_TRANSPORT_SEND_FAILED',
      source: 'internal_failure',
      direction: 'uplink',
      attached_before_close: false,
    },
  ]);
  assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
  assert.equal(JSON.stringify(route.activation).includes('A'.repeat(43)), false);
});

test('ticket-in-path routing is permanently rejected without socket or business effects', () => {
  let allocations = 0;
  const effects = { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 };
  const shared = {
    enabled: true,
    expected_origin: 'https://voice.example.test',
    binding: binding(),
    provider_available: true,
    transport_available: true,
    socket_factory: () => {
      allocations += 1;
      return new FakeSocket();
    },
    on_audio_frame: () => {
      effects.audio += 1;
    },
  };
  const missingTicket = createBrowserDedicatedMediaRoute({
    ...shared,
    endpoint_url: 'wss://voice.example.test/ws/live-voice/media',
  });
  const legacyByDefault = createBrowserDedicatedMediaRoute({
    ...shared,
    endpoint_url: 'wss://voice.example.test/ws/live-voice/media/private-ticket',
    media_ticket: 'A'.repeat(43),
  });

  assert.equal(missingTicket.active, false);
  assert.equal(missingTicket.reason_id, 'MEDIA_AUTHORITY_UNAVAILABLE');
  assert.equal(legacyByDefault.active, false);
  assert.equal(legacyByDefault.reason_id, 'MEDIA_ORIGIN_REJECTED');
  assert.equal(allocations, 0);
  assert.deepEqual(effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
});

test('flag-off and rejected origin allocate no socket and expose no effects', () => {
  let socketAllocations = 0;
  const disabled = createBrowserDedicatedMediaRoute({
    enabled: false,
    get expected_origin() {
      throw new Error('must not inspect origin');
    },
    get endpoint_url() {
      throw new Error('must not inspect endpoint');
    },
    get media_ticket() {
      throw new Error('must not inspect ticket');
    },
    get binding() {
      throw new Error('must not inspect authority');
    },
    get provider_available() {
      throw new Error('must not inspect Provider');
    },
    get transport_available() {
      throw new Error('must not inspect transport');
    },
    get socket_factory() {
      throw new Error('must not inspect factory');
    },
    get on_audio_frame() {
      throw new Error('must not inspect consumer');
    },
    get schedule_drain_retry() {
      throw new Error('must not inspect retry scheduler');
    },
    get cancel_drain_retry() {
      throw new Error('must not inspect retry canceller');
    },
  });
  const rejected = createBrowserDedicatedMediaRoute({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    endpoint_url: 'wss://other.example.test/live-voice/media',
    binding: binding(),
    provider_available: true,
    transport_available: true,
    socket_factory: () => {
      socketAllocations += 1;
      return new FakeSocket();
    },
    on_audio_frame: () => {
      throw new Error('must not consume');
    },
  });

  assert.equal(disabled.reason_id, 'MEDIA_FEATURE_DISABLED');
  assert.equal(rejected.reason_id, 'MEDIA_ORIGIN_REJECTED');
  assert.equal(socketAllocations, 0);
  assert.equal(disabled.capability.socket_allocated, false);
  assert.equal(rejected.capability.formal_route_ready, false);
});

test('public queue and socket limits are practical safe integers before allocation', () => {
  const invalidLimits = [
    { max_pending_frames: 257 },
    { max_pending_frames: 1.5 },
    { max_pending_frames: Number.MAX_SAFE_INTEGER + 1 },
    { max_pending_bytes: 8 * 1024 * 1024 + 1 },
    { max_pending_bytes: 1.5 },
    { max_pending_bytes: Number.MAX_SAFE_INTEGER + 1 },
    { socket_high_water_bytes: 8 * 1024 * 1024 + 1 },
    { socket_high_water_bytes: 1.5 },
    { socket_high_water_bytes: Number.MAX_SAFE_INTEGER + 1 },
    { drain_retry_delay_ms: 0 },
    { drain_retry_delay_ms: 1_001 },
    { max_drain_stall_retries: 0 },
    { max_drain_stall_retries: 10_001 },
  ];

  for (const limits of invalidLimits) {
    let socketAllocations = 0;
    let audioEffects = 0;
    assert.throws(
      () =>
        createBrowserDedicatedMediaRoute({
          enabled: true,
          expected_origin: 'https://voice.example.test',
          endpoint_url: 'wss://voice.example.test/ws/live-voice/media',
          media_ticket: 'B'.repeat(43),
          binding: binding(),
          provider_available: true,
          transport_available: true,
          socket_factory: () => {
            socketAllocations += 1;
            return new FakeSocket();
          },
          on_audio_frame: () => {
            audioEffects += 1;
          },
          ...limits,
        }),
      /must be a positive safe integer no greater than/
    );
    assert.equal(socketAllocations, 0);
    assert.equal(audioEffects, 0);
  }

  const accepted = active({
    maxPendingFrames: 256,
    maxPendingBytes: 8 * 1024 * 1024,
    highWater: 8 * 1024 * 1024,
  });
  assert.equal(accepted.factoryCalls.length, 1);
  assert.equal(accepted.effects.audio, 0);
  accepted.activation.leaf.close();

  assert.throws(
    () =>
      createBrowserDedicatedMediaRoute({
        enabled: true,
        expected_origin: 'https://voice.example.test',
        endpoint_url: 'wss://voice.example.test/ws/live-voice/media',
        media_ticket: 'C'.repeat(43),
        binding: binding(),
        provider_available: true,
        transport_available: true,
        socket_factory: () => new FakeSocket(),
        on_audio_frame: () => {},
        schedule_drain_retry: () => 1,
      }),
    /requires both schedule and cancel/
  );
});

test('subprotocol mismatch and reused socket fail closed without sending media controls', () => {
  const mismatch = active();
  mismatch.socket.open('wrong.media.protocol');
  const retained = mismatch.activation.leaf.close();
  assert.equal(retained.reason_id, 'MEDIA_TRANSPORT_PROTOCOL_ERROR');
  assert.equal(mismatch.socket.sent.length, 0);
  assert.equal(mismatch.socket.closes.length, 1);

  const reused = new FakeSocket();
  reused.readyState = 1;
  reused.protocol = DEDICATED_MEDIA_SUBPROTOCOL;
  assert.throws(
    () =>
      createBrowserDedicatedMediaRoute({
        enabled: true,
        expected_origin: 'https://voice.example.test',
        endpoint_url: 'wss://voice.example.test/ws/live-voice/media',
        media_ticket: 'D'.repeat(43),
        binding: binding(),
        provider_available: true,
        transport_available: true,
        socket_factory: () => reused,
        on_audio_frame: () => {},
      }),
    /must return a new connecting socket/
  );
  assert.equal(reused.closes.length, 1);
});

test('transport loss closes once, reports exact terminal provenance, and performs no implicit retry', () => {
  let allocations = 0;
  const terminal = [];
  const socket = new FakeSocket();
  const route = createBrowserDedicatedMediaRoute({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    endpoint_url: 'wss://voice.example.test/ws/live-voice/media',
    media_ticket: 'E'.repeat(43),
    binding: binding(),
    provider_available: true,
    transport_available: true,
    socket_factory: () => {
      allocations += 1;
      return socket;
    },
    on_audio_frame: () => {},
    on_terminal: event => terminal.push(event),
  });
  assert.equal(route.active, true);
  attach({ activation: route, socket });

  socket.transportClose();
  const repeated = route.leaf.close();

  assert.equal(route.leaf.closed, true);
  assert.equal(repeated.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(repeated.business_cancel_count_delta, 0);
  assert.equal(allocations, 1);
  assert.deepEqual(terminal, [
    {
      reason_id: 'MEDIA_TRANSPORT_CLOSED',
      source: 'transport_close',
      direction: 'uplink',
      attached_before_close: true,
    },
  ]);
  socket.onerror?.({});
  assert.equal(terminal.length, 1);
});

test('local terminal provenance is one-shot and observer failure cannot alter the retained fence', () => {
  let observations = 0;
  let terminal = null;
  const route = active({
    onTerminal: event => {
      observations += 1;
      terminal = event;
      throw new Error('observer failure');
    },
  });
  attach(route);

  const closed = route.activation.leaf.close('MEDIA_LOCAL_CLOSE');
  route.socket.transportClose();

  assert.equal(closed.reason_id, 'MEDIA_LOCAL_CLOSE');
  assert.equal(closed.business_cancel_count_delta, 0);
  assert.equal(route.activation.leaf.closed, true);
  assert.equal(observations, 1);
  assert.deepEqual(terminal, {
    reason_id: 'MEDIA_LOCAL_CLOSE',
    source: 'local_close',
    direction: 'uplink',
    attached_before_close: true,
  });
  assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
});
