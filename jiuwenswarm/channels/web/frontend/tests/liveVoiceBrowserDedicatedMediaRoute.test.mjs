import assert from 'node:assert/strict';
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
  const generation = overrides.generation ?? (direction === 'downlink'
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

function active({
  exactBinding = binding(),
  socket = new FakeSocket(),
  effects,
  maxPendingFrames,
  maxPendingBytes,
  highWater,
} = {}) {
  const counters = effects ?? { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 };
  const factoryCalls = [];
  const activation = createBrowserDedicatedMediaRoute({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    endpoint_url: 'wss://voice.example.test/live-voice/media',
    binding: exactBinding,
    provider_available: true,
    transport_available: true,
    socket_factory: (url, protocols) => {
      factoryCalls.push({ url, protocols });
      return socket;
    },
    on_audio_frame: () => { counters.audio += 1; },
    max_pending_frames: maxPendingFrames,
    max_pending_bytes: maxPendingBytes,
    socket_high_water_bytes: highWater,
  });
  assert.equal(activation.active, true);
  return { activation, socket, effects: counters, factoryCalls };
}

function attach(route) {
  route.socket.open();
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
    confirmed_cursor_before_stop: Object.freeze(
      [...cursors].map(cursor => Object.freeze({ ...cursor })),
    ),
    browser_sources: Object.freeze({
      ...sources,
      stop_request: Object.freeze({ ...sources.stop_request }),
      disconnect: Object.freeze({ ...sources.disconnect }),
    }),
    timing: Object.freeze({ ...timing }),
  });
}

function frozenWithout(value, omittedField) {
  return Object.freeze(Object.fromEntries(
    Object.entries(value).filter(([field]) => field !== omittedField),
  ));
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
    confirmed_cursor_before_stop: [{
      unit_id: 'unit-01',
      contiguous_through_seq: confirmedThroughSeq,
    }],
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

test('uplink requires server attach then sends bounded LVM1 frames retained through ACK', () => {
  const route = active({ maxPendingFrames: 1 });
  assert.equal(route.socket.binaryType, 'arraybuffer');
  assert.deepEqual(route.factoryCalls, [{
    url: 'wss://voice.example.test/live-voice/media',
    protocols: [DEDICATED_MEDIA_SUBPROTOCOL],
  }]);
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

  route.socket.message(serializeMediaControl({
    type: 'media.ack',
    lease_id: route.activation.binding.lease_id,
    generation: route.activation.binding.generation.value,
    through_seq: 0,
  }));
  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame(1)).accepted, true);
  assert.equal(decodeAudioFrame(route.activation.binding, route.socket.sent[1]).seq, 1);
  assert.equal(route.effects.audio, 0);
  assert.equal(route.activation.capability.registered_route_observed, false);
  assert.equal(route.activation.capability.route_to_disk_zero_persistence_observed, false);
  assert.equal(route.activation.capability.formal_route_ready, false);
});

test('socket leaf cannot bypass the same-origin activation factory', () => {
  assert.throws(
    () => new BrowserDedicatedMediaSocketLeaf({}, new FakeSocket(), 1024),
    /require the same-origin factory/,
  );
});

test('socket bufferedAmount and bounded owner apply backpressure without retry or drop', () => {
  const route = active({ maxPendingFrames: 1, highWater: 1024 });
  attach(route);
  route.socket.bufferedAmount = 1024;

  assert.equal(route.activation.leaf.sendCaptureFrame(capturedFrame()).accepted, true);
  assert.equal(route.socket.sent.length, 0);
  assert.deepEqual(route.activation.leaf.sendCaptureFrame(capturedFrame(1)), {
    accepted: false,
    reason_id: 'MEDIA_BACKPRESSURE_LIMIT',
  });

  route.socket.bufferedAmount = 0;
  assert.equal(route.activation.leaf.flush().sent_frames, 1);
  assert.equal(route.socket.sent.length, 1);
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

test('wrong attach, stale capture, cursor gap, and malformed control terminally fence the leaf', () => {
  const cases = [
    (route) => {
      route.socket.open();
      route.socket.message(serializeMediaControl({
        type: 'media.attach', binding: binding({ session_id: 'wrong-session' }),
      }));
    },
    (route) => {
      attach(route);
      route.activation.leaf.sendCaptureFrame(capturedFrame(0, {
        capture: { capture_generation: 8 },
      }));
    },
    (route) => {
      attach(route);
      route.activation.leaf.sendCaptureFrame(capturedFrame(0, { sample_cursor: 160 }));
    },
    (route) => {
      route.socket.open();
      route.socket.message('{"not":"closed-control"}');
    },
  ];
  const reasons = [
    'MEDIA_BINDING_MISMATCH',
    'MEDIA_STALE_GENERATION',
    'MEDIA_INVALID_FRAME',
    'MEDIA_TRANSPORT_PROTOCOL_ERROR',
  ];

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
  const controls = route.socket.sent
    .filter(item => typeof item === 'string')
    .map(item => deserializeMediaControl(item));
  assert.deepEqual(controls.find(item => item.type === 'media.playback_stop_receipt'), control);
  assert.equal(controls.at(-1).type, 'media.detach');
  assert.equal(controls.at(-1).business_cancel_count_delta, 0);
  assert.equal(route.activation.leaf.closed, true);
  assert.throws(
    () => route.activation.leaf.sendLocalPlaybackStop(closedLocalStopReceipt(localReceipt, { business_cancel_count_delta: 1 })),
    /cannot carry business cancellation/,
  );
  assert.throws(
    () => route.activation.leaf.sendLocalPlaybackStop(closedLocalStopReceipt(localReceipt, {
      confirmed_cursor_before_stop: [{ unit_id: 'unit-01', contiguous_through_seq: 5 }],
    })),
    /cannot confirm an unreceived media frame/,
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
    ...Object.keys(trusted.response).map(field => closedLocalStopReceipt(trusted, {
      response: frozenWithout(trusted.response, field),
    })),
    ...Object.keys(trusted.browser_sources.stop_request).map(field => closedLocalStopReceipt(trusted, {
      browser_sources: {
        ...trusted.browser_sources,
        stop_request: frozenWithout(trusted.browser_sources.stop_request, field),
      },
    })),
    ...Object.keys(trusted.browser_sources.disconnect).map(field => closedLocalStopReceipt(trusted, {
      browser_sources: {
        ...trusted.browser_sources,
        disconnect: frozenWithout(trusted.browser_sources.disconnect, field),
      },
    })),
    ...Object.keys(trusted.timing).map(field => closedLocalStopReceipt(trusted, {
      timing: frozenWithout(trusted.timing, field),
    })),
    ...Object.keys(trusted.confirmed_cursor_before_stop[0]).map(field => closedLocalStopReceipt(trusted, {
      confirmed_cursor_before_stop: [frozenWithout(trusted.confirmed_cursor_before_stop[0], field)],
    })),
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
  const controls = route.socket.sent
    .filter(item => typeof item === 'string')
    .map(item => deserializeMediaControl(item));
  assert.equal(controls.some(item => item.type === 'media.playback_stop_receipt'), false);
  assert.equal(controls.some(item => item.type === 'media.detach'), false);
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
      error => error?.reasonId === 'MEDIA_STOP_NOT_DELIVERED',
    );
    const retained = route.activation.leaf.close();
    const controls = route.socket.sent
      .filter(item => typeof item === 'string')
      .map(item => deserializeMediaControl(item));
    assert.equal(returnedReceipt, false);
    assert.equal(controls.some(item => item.type === 'media.playback_stop_receipt'), false);
    assert.equal(retained.reason_id, expectedClose);
    assert.equal(retained.business_cancel_count_delta, 0);
    assert.deepEqual(route.effects, { audio: 0, agent: 0, tool: 0, task: 0, history: 0, persistence: 0 });
  }
});

test('flag-off and rejected origin allocate no socket and expose no effects', () => {
  let socketAllocations = 0;
  const disabled = createBrowserDedicatedMediaRoute({
    enabled: false,
    get expected_origin() { throw new Error('must not inspect origin'); },
    get endpoint_url() { throw new Error('must not inspect endpoint'); },
    get binding() { throw new Error('must not inspect authority'); },
    get provider_available() { throw new Error('must not inspect Provider'); },
    get transport_available() { throw new Error('must not inspect transport'); },
    get socket_factory() { throw new Error('must not inspect factory'); },
    get on_audio_frame() { throw new Error('must not inspect consumer'); },
  });
  const rejected = createBrowserDedicatedMediaRoute({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    endpoint_url: 'wss://other.example.test/live-voice/media',
    binding: binding(),
    provider_available: true,
    transport_available: true,
    socket_factory: () => { socketAllocations += 1; return new FakeSocket(); },
    on_audio_frame: () => { throw new Error('must not consume'); },
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
  ];

  for (const limits of invalidLimits) {
    let socketAllocations = 0;
    let audioEffects = 0;
    assert.throws(
      () => createBrowserDedicatedMediaRoute({
        enabled: true,
        expected_origin: 'https://voice.example.test',
        endpoint_url: 'wss://voice.example.test/live-voice/media',
        binding: binding(),
        provider_available: true,
        transport_available: true,
        socket_factory: () => { socketAllocations += 1; return new FakeSocket(); },
        on_audio_frame: () => { audioEffects += 1; },
        ...limits,
      }),
      /must be a positive safe integer no greater than/,
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
    () => createBrowserDedicatedMediaRoute({
      enabled: true,
      expected_origin: 'https://voice.example.test',
      endpoint_url: 'wss://voice.example.test/live-voice/media',
      binding: binding(),
      provider_available: true,
      transport_available: true,
      socket_factory: () => reused,
      on_audio_frame: () => {},
    }),
    /must return a new connecting socket/,
  );
  assert.equal(reused.closes.length, 1);
});

test('transport loss closes once and performs no implicit retry', () => {
  let allocations = 0;
  const socket = new FakeSocket();
  const route = createBrowserDedicatedMediaRoute({
    enabled: true,
    expected_origin: 'https://voice.example.test',
    endpoint_url: 'wss://voice.example.test/live-voice/media',
    binding: binding(),
    provider_available: true,
    transport_available: true,
    socket_factory: () => { allocations += 1; return socket; },
    on_audio_frame: () => {},
  });
  assert.equal(route.active, true);
  attach({ activation: route, socket });

  socket.transportClose();
  const repeated = route.leaf.close();

  assert.equal(route.leaf.closed, true);
  assert.equal(repeated.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(repeated.business_cancel_count_delta, 0);
  assert.equal(allocations, 1);
});
