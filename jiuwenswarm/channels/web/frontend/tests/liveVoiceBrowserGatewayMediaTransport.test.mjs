import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

import {
  BoundedMediaSender,
  BrowserGatewayMediaRegistrationOwner,
  MediaTransportViolation,
  StrictMediaReceiver,
  createBrowserGatewayMediaActivation,
  createPlaybackStopReceipt,
  decodeAudioFrame,
  deserializeMediaControl,
  encodeAudioFrame,
  serializeMediaControl,
  validatePlaybackStopReceipt,
} from '../node_modules/.cache/live-voice-browser-gateway-media/browserGatewayMediaTransport.mjs';

test('registration owner cannot be constructed outside the activation factory', () => {
  assert.throws(
    () => new BrowserGatewayMediaRegistrationOwner(binding(), 2, 2048, () => {}),
    (error) => error instanceof MediaTransportViolation
      && error.reasonId === 'MEDIA_ACTIVATION_FACTORY_REQUIRED',
  );
});

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
    lease_id: 'lease-opaque-01',
    authority_evidence_id: 'authority-evidence-01',
    connection_id: 'connection-01',
    connection_epoch: 3,
    session_id: 'session-01',
    media_session_id: 'media-session-01',
    interaction_id: 'interaction-01',
    track_id: 'capture-track-01',
    correlation_id: 'correlation-01',
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

function frame(seq = 0, sampleCursor = 0) {
  return {
    seq,
    sample_cursor: sampleCursor,
    samples: Float32Array.from({ length: 160 }, (_, index) => Math.sin(index / 11) * 0.25),
  };
}

function active({ exactBinding = binding(), maxPendingFrames, maxPendingBytes, effects } = {}) {
  const counters = effects ?? { audio: 0 };
  const result = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: exactBinding,
    provider_available: true,
    transport_available: true,
    on_audio_frame: () => { counters.audio += 1; },
    max_pending_frames: maxPendingFrames,
    max_pending_bytes: maxPendingBytes,
  });
  assert.equal(result.active, true);
  return result;
}

function assertZeroDownstream(effects) {
  assert.deepEqual(effects, { audio: 0, agent: 0, task: 0 });
}

test('LVM1 frame and typed control round trip preserve exact codec facts', () => {
  const exactBinding = binding();
  const source = frame();
  const binary = encodeAudioFrame(exactBinding, source);
  const decoded = decodeAudioFrame(exactBinding, binary);
  const attach = { type: 'media.attach', binding: exactBinding };
  const decodedControl = deserializeMediaControl(serializeMediaControl(attach));

  assert.equal(new TextDecoder().decode(binary.subarray(0, 4)), 'LVM1');
  assert.equal(decoded.seq, 0);
  assert.equal(decoded.sample_cursor, 0);
  assert.equal(decoded.samples.length, 160);
  assert.ok(Math.abs(decoded.samples[37] - source.samples[37]) < 1e-7);
  assert.deepEqual(decodedControl, attach);
});

test('speech-start control round trip is exact and missing bindings fail closed', () => {
  const speechStart = {
    type: 'media.speech_start',
    capability_version: 'media.end_of_turn.v1',
    lease_id: 'lease-opaque-01',
    generation: 7,
    detector: 'server_vad',
    provider_start_ms: 320,
    timing_basis: 'provider_time',
    timing_provenance: 'adapter_derived',
    create_response: false,
    interrupt_response: false,
    business_cancel_count_delta: 0,
  };

  assert.deepEqual(deserializeMediaControl(serializeMediaControl(speechStart)), speechStart);
  for (const omitted of ['lease_id', 'generation', 'provider_start_ms']) {
    const malformed = JSON.parse(serializeMediaControl(speechStart));
    delete malformed[omitted];
    assert.throws(
      () => deserializeMediaControl(JSON.stringify(malformed)),
      (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_MALFORMED_CONTROL',
    );
  }
});

test('actual AudioContext rate is preserved without resampling', () => {
  const exactBinding = binding({
    frame_format: {
      sample_rate_hz: 48_000,
      samples_per_channel: 960,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
  });
  const source = {
    seq: 0,
    sample_cursor: 0,
    samples: Float32Array.from({ length: 960 }, (_, index) => (index % 31) / 64),
  };

  const decoded = decodeAudioFrame(exactBinding, encodeAudioFrame(exactBinding, source));

  assert.equal(exactBinding.frame_format.sample_rate_hz, 48_000);
  assert.equal(exactBinding.frame_format.samples_per_channel, 960);
  assert.equal(decoded.samples.length, 960);
  assert.deepEqual(decoded.samples, source.samples);
});

test('LVM1 cross-language fixture is byte exact', () => {
  const fixture = JSON.parse(readFileSync(resolve(
    process.cwd(),
    '../../../../tests/fixtures/live_voice_media_transport_v1/roundtrip.json',
  ), 'utf8'));
  const samples = Float32Array.from([
    ...fixture.frame.sample_prefix,
    ...Array(fixture.frame.trailing_zero_samples).fill(0),
  ]);

  const binary = encodeAudioFrame(fixture.binding, {
    seq: fixture.frame.seq,
    sample_cursor: fixture.frame.sample_cursor,
    samples,
  });

  assert.equal(binary.byteLength, fixture.expected_binary_bytes);
  assert.equal(createHash('sha256').update(binary).digest('hex'), fixture.expected_sha256);
});

for (const [field, value] of [
  ['session_id', 'wrong-session'],
  ['track_id', 'wrong-track'],
  ['lease_id', 'wrong-lease'],
]) {
  test(`attach rejects wrong ${field} with zero downstream effects`, () => {
    const effects = { audio: 0, agent: 0, task: 0 };
    const activation = active({ effects });

    const result = activation.owner.attach({
      type: 'media.attach',
      binding: binding({ [field]: value }),
    });

    assert.equal(result.reason_id, 'MEDIA_BINDING_MISMATCH');
    assert.equal(activation.owner.closed, true);
    assertZeroDownstream(effects);
  });
}

test('malformed, oversized, stale generation, and non-finite frames detach before consumption', () => {
  const cases = [
    {
      reason: 'MEDIA_MALFORMED_FRAME',
      mutate: (binary) => binary.subarray(0, 10),
    },
    {
      reason: 'MEDIA_MALFORMED_FRAME',
      mutate: (binary) => {
        const changed = new Uint8Array(binary);
        changed[0] = 0;
        return changed;
      },
    },
    {
      reason: 'MEDIA_OVERSIZED_FRAME',
      mutate: (binary) => {
        const changed = new Uint8Array(binary.byteLength + 20_000);
        changed.set(binary);
        return changed;
      },
    },
    {
      reason: 'MEDIA_STALE_GENERATION',
      mutate: (binary) => {
        const changed = new Uint8Array(binary);
        new DataView(changed.buffer).setUint32(8, 999, true);
        return changed;
      },
    },
    {
      reason: 'MEDIA_NONFINITE_AUDIO',
      mutate: (binary) => {
        const changed = new Uint8Array(binary);
        const payloadOffset = 36 + new TextEncoder().encode('lease-opaque-01').length;
        new DataView(changed.buffer).setFloat32(payloadOffset, Number.NaN, true);
        return changed;
      },
    },
  ];

  for (const { reason, mutate } of cases) {
    const effects = { audio: 0, agent: 0, task: 0 };
    const activation = active({ effects });
    activation.owner.attach({ type: 'media.attach', binding: activation.binding });
    const result = activation.owner.acceptBinary(mutate(encodeAudioFrame(activation.binding, frame())));
    assert.equal(result.reason_id, reason);
    assertZeroDownstream(effects);
  }
});

for (const scenario of [
  { first: [1, 160], second: null, reason: 'MEDIA_SEQUENCE_GAP', audio: 0 },
  { first: [0, 0], second: [0, 0], reason: 'MEDIA_DUPLICATE_OR_OUT_OF_ORDER', audio: 1 },
  { first: [0, 0], second: [2, 320], reason: 'MEDIA_SEQUENCE_GAP', audio: 1 },
  { first: [0, 0], second: [1, 161], reason: 'MEDIA_CURSOR_MISMATCH', audio: 1 },
]) {
  test(`ordering policy terminally detaches ${scenario.reason}`, () => {
    const effects = { audio: 0, agent: 0, task: 0 };
    const activation = active({ effects });
    activation.owner.attach({ type: 'media.attach', binding: activation.binding });
    let result = activation.owner.acceptBinary(
      encodeAudioFrame(activation.binding, frame(...scenario.first)),
    );
    if (scenario.second !== null && result.type !== 'media.detach') {
      result = activation.owner.acceptBinary(
        encodeAudioFrame(activation.binding, frame(...scenario.second)),
      );
    }
    assert.equal(result.reason_id, scenario.reason);
    assert.deepEqual(effects, { audio: scenario.audio, agent: 0, task: 0 });
  });
}

test('sender enforces bounded pressure and retains sent frames until ACK', () => {
  let activation = active({ maxPendingFrames: 1 });
  let owner = activation.owner;
  assert.equal(owner.enqueue(frame()).accepted, true);
  assert.deepEqual(owner.enqueue(frame(1, 160)), {
    accepted: false,
    reason_id: 'MEDIA_BACKPRESSURE_LIMIT',
  });
  assert.equal(owner.drain(() => 'backpressured').sent_frames, 0);
  assert.equal(owner.lifecycleSnapshot().sender_pending_frames, 1);
  assert.equal(owner.acknowledge({
    type: 'media.ack', lease_id: activation.binding.lease_id, generation: 7, through_seq: 0,
  }).reason_id, 'MEDIA_ACK_UNSENT');

  activation = active({ maxPendingFrames: 1 });
  owner = activation.owner;
  owner.enqueue(frame());
  const sentSequences = [];
  assert.equal(owner.drain(() => 'sent', seq => sentSequences.push(seq)).sent_frames, 1);
  assert.deepEqual(sentSequences, [0]);
  assert.equal(owner.acknowledge({
    type: 'media.ack', lease_id: activation.binding.lease_id, generation: 7, through_seq: 0,
  }), null);
  assert.equal(owner.lifecycleSnapshot().sender_pending_frames, 0);
  assert.equal(owner.lifecycleSnapshot().sender_pending_bytes, 0);
  assert.equal(owner.enqueue(frame(1, 160)).accepted, true);
});

test('sender retains copied immutable metadata and bytes across caller mutation', () => {
  const activation = active();
  const source = frame();
  const originalFirstSample = source.samples[0];
  assert.equal(activation.owner.enqueue(source).accepted, true);
  source.seq = 99;
  source.sample_cursor = 99;
  source.samples[0] = 0.75;
  let sent = null;

  const drained = activation.owner.drain((binary) => {
    sent = binary;
    return 'sent';
  });
  const ack = activation.owner.acknowledge({
    type: 'media.ack',
    lease_id: activation.binding.lease_id,
    generation: activation.binding.generation.value,
    through_seq: 0,
  });
  const decoded = decodeAudioFrame(activation.binding, sent);

  assert.equal(drained.sent_frames, 1);
  assert.equal(ack, null);
  assert.equal(decoded.seq, 0);
  assert.equal(decoded.sample_cursor, 0);
  assert.equal(decoded.samples[0], originalFirstSample);
  assert.equal(activation.owner.lifecycleSnapshot().sender_pending_frames, 0);
});

test('semantic detach and close fence the lease without downstream effects', () => {
  const effects = { audio: 0, agent: 0, task: 0 };
  const activation = active({ effects });
  assert.equal(activation.owner.attach({ type: 'media.attach', binding: activation.binding }), null);
  const detached = activation.owner.acceptDetach({
    type: 'media.detach',
    lease_id: activation.binding.lease_id,
    generation: activation.binding.generation.value,
    reason_id: 'MEDIA_LOCAL_CLOSE',
    through_seq: null,
    business_cancel_count_delta: 0,
  });

  const late = activation.owner.acceptBinary(encodeAudioFrame(activation.binding, frame()));
  const repeated = activation.owner.close();

  assert.equal(detached.was_active, true);
  assert.equal(detached.reason_id, 'MEDIA_LOCAL_CLOSE');
  assert.equal(detached.business_cancel_count_delta, 0);
  assert.equal(late.reason_id, 'MEDIA_LOCAL_CLOSE');
  assert.equal(repeated, detached);
  assertZeroDownstream(effects);
});

test('injected transport failure closes without implicit retry', () => {
  const activation = active();
  activation.owner.enqueue(frame());

  const result = activation.owner.drain(() => { throw new Error('private transport detail'); });

  assert.equal(result.sent_frames, 0);
  assert.equal(result.reason_id, 'MEDIA_TRANSPORT_SEND_FAILED');
  assert.equal(activation.owner.closed, true);
});

test('sender and receiver are injected seams and never open sockets themselves', () => {
  const exactBinding = binding();
  const sender = new BoundedMediaSender(exactBinding, 1, 1024);
  const receiver = new StrictMediaReceiver(exactBinding, () => {});
  assert.equal(sender.pending_frames, 0);
  assert.equal(receiver.attached, false);
  assert.equal('socket' in sender, false);
  assert.equal('socket' in receiver, false);
});

for (const scenario of [
  { enabled: false, exactBinding: binding(), provider: true, transport: true, reason: 'MEDIA_FEATURE_DISABLED' },
  { enabled: true, exactBinding: null, provider: true, transport: true, reason: 'MEDIA_AUTHORITY_UNAVAILABLE' },
  { enabled: true, exactBinding: binding(), provider: false, transport: true, reason: 'MEDIA_PROVIDER_UNAVAILABLE' },
  { enabled: true, exactBinding: binding(), provider: true, transport: false, reason: 'MEDIA_TRANSPORT_UNAVAILABLE' },
]) {
  test(`inactive gate ${scenario.reason} exposes no media effects`, () => {
    const effects = { audio: 0, agent: 0, task: 0 };
    const activation = createBrowserGatewayMediaActivation({
      enabled: scenario.enabled,
      binding: scenario.exactBinding,
      provider_available: scenario.provider,
      transport_available: scenario.transport,
      on_audio_frame: () => { effects.audio += 1; },
    });
    assert.equal(activation.active, false);
    assert.equal(activation.reason_id, scenario.reason);
    assert.equal('sender' in activation, false);
    assert.equal('receiver' in activation, false);
    assert.equal(activation.capability.real_transport_observed, false);
    assert.equal(activation.capability.formal_route_ready, false);
    assert.equal(activation.capability.evidence_scope, 'contract_only');
    assert.equal(activation.capability.registration_evidence_id, null);
    assert.equal(activation.capability.runtime_evidence_id, null);
    assertZeroDownstream(effects);
  });
}

test('downlink stop receipt is exact and never escalates cancellation', () => {
  const exactBinding = binding({ direction: 'downlink' });
  const receipt = createPlaybackStopReceipt(exactBinding, 'local_fence_established', 4);
  assert.deepEqual(deserializeMediaControl(serializeMediaControl(receipt)), receipt);
  assert.equal(receipt.response_id, exactBinding.playout.response_id);
  assert.equal(receipt.response_generation, exactBinding.playout.response_generation);
  assert.equal(receipt.unit_id, exactBinding.playout.unit_id);
  assert.equal(receipt.business_cancel_count_delta, 0);
  assert.throws(
    () => validatePlaybackStopReceipt(exactBinding, { ...receipt, unit_id: 'wrong-unit' }),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_STOP_BINDING_MISMATCH',
  );
  assert.throws(
    () => createPlaybackStopReceipt(binding(), 'local_fence_established'),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_STOP_BINDING_MISMATCH',
  );
});

test('activation freezes trusted binding and malformed control claims fail closed', () => {
  const source = binding();
  const activation = active({ exactBinding: source });
  assert.equal(Object.isFrozen(activation.binding), true);
  assert.equal(Object.isFrozen(activation.binding.generation), true);
  source.session_id = 'mutated-client-claim';
  assert.equal(activation.binding.session_id, 'session-01');

  assert.throws(
    () => deserializeMediaControl(JSON.stringify({
      type: 'media.ack',
      contract_version: 'live-voice.media.v1',
      lease_id: 'lease',
      generation: 1,
      through_seq: 0,
      session_id: 'client-claim',
    })),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_MALFORMED_CONTROL',
  );

  const noncanonicalFormat = JSON.parse(serializeMediaControl({
    type: 'media.attach', binding: activation.binding,
  }));
  noncanonicalFormat.binding.frame_format.channel_count = true;
  assert.throws(
    () => deserializeMediaControl(JSON.stringify(noncanonicalFormat)),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_INVALID_FORMAT',
  );
});

test('arbitrary detach reason is rejected before receiver state change', () => {
  const effects = { audio: 0, agent: 0, task: 0 };
  const activation = active({ effects });
  assert.equal(activation.owner.attach({ type: 'media.attach', binding: activation.binding }), null);
  const raw = JSON.parse(serializeMediaControl({
    type: 'media.detach',
    lease_id: activation.binding.lease_id,
    generation: activation.binding.generation.value,
    reason_id: 'MEDIA_PEER_CLOSE',
    through_seq: null,
    business_cancel_count_delta: 0,
  }));
  raw.reason_id = 'private-content\nnot-a-stable-reason';

  assert.throws(
    () => deserializeMediaControl(JSON.stringify(raw)),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_MALFORMED_CONTROL',
  );
  assert.throws(
    () => activation.owner.acceptDetach(raw),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_INVALID_CONTROL',
  );
  assert.equal(activation.owner.lifecycleSnapshot().receiver_attached, true);
  assert.equal(activation.owner.lifecycleSnapshot().receiver_closed, false);
  assertZeroDownstream(effects);

  const local = active().owner.close('private-content\nnot-a-stable-reason');
  assert.equal(local.reason_id, 'MEDIA_LOCAL_CLOSE');
  assert.equal(local.sender_detach.reason_id, 'MEDIA_LOCAL_CLOSE');
});

test('business cancel delta rejects boolean false before receiver state change', () => {
  const effects = { audio: 0, agent: 0, task: 0 };
  const activation = active({ effects });
  assert.equal(activation.owner.attach({ type: 'media.attach', binding: activation.binding }), null);
  const detach = JSON.parse(serializeMediaControl({
    type: 'media.detach',
    lease_id: activation.binding.lease_id,
    generation: activation.binding.generation.value,
    reason_id: 'MEDIA_PEER_CLOSE',
    through_seq: null,
    business_cancel_count_delta: 0,
  }));
  detach.business_cancel_count_delta = false;
  const downlink = binding({ direction: 'downlink' });
  const stop = JSON.parse(serializeMediaControl(
    createPlaybackStopReceipt(downlink, 'local_fence_established'),
  ));
  stop.business_cancel_count_delta = false;

  assert.throws(
    () => deserializeMediaControl(JSON.stringify(detach)),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_MALFORMED_CONTROL',
  );
  assert.throws(
    () => activation.owner.acceptDetach(detach),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_INVALID_CONTROL',
  );
  assert.throws(
    () => deserializeMediaControl(JSON.stringify(stop)),
    (error) => error instanceof MediaTransportViolation && error.reasonId === 'MEDIA_MALFORMED_CONTROL',
  );
  assert.equal(activation.owner.lifecycleSnapshot().receiver_attached, true);
  assert.equal(activation.owner.lifecycleSnapshot().receiver_closed, false);
  assertZeroDownstream(effects);
});

test('registration owner runs attach-frame-ACK-close with payload-free non-formal facts', () => {
  const facts = [];
  const effects = { audio: 0, agent: 0, task: 0 };
  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: binding(),
    provider_available: true,
    transport_available: true,
    on_audio_frame: () => { effects.audio += 1; },
    on_lifecycle_fact: (fact) => { facts.push(fact); },
  });
  assert.equal(activation.active, true);
  const owner = activation.owner;
  assert.equal(owner.attach({ type: 'media.attach', binding: activation.binding }), null);
  assert.deepEqual(owner.enqueue(frame()), { accepted: true, reason_id: 'MEDIA_ENQUEUED' });
  let binary = null;
  assert.equal(owner.drain((value) => { binary = value; return 'sent'; }).sent_frames, 1);
  const ack = owner.acceptBinary(binary);
  assert.equal(ack.type, 'media.ack');
  assert.equal(owner.acknowledge(ack), null);
  const firstClose = owner.close();
  const replayClose = owner.close();

  assert.equal(replayClose, firstClose);
  assert.equal(firstClose.business_cancel_count_delta, 0);
  assert.deepEqual(effects, { audio: 1, agent: 0, task: 0 });
  assert.deepEqual(facts, []);
  assert.equal(owner.pending_lifecycle_facts, 7);
  assert.equal(owner.drainLifecycleFacts(32), 7);
  assert.deepEqual(facts.map(fact => fact.event), [
    'activation.ready',
    'receiver.attach',
    'sender.enqueue',
    'sender.drain',
    'receiver.accept_binary',
    'sender.acknowledge',
    'activation.closed',
  ]);
  const final = facts.at(-1);
  assert.equal(Object.isFrozen(final), true);
  assert.equal(final.owner_closed, true);
  assert.equal(final.connection_epoch, 3);
  assert.equal(final.track_id, 'capture-track-01');
  assert.equal(final.correlation_id, 'correlation-01');
  assert.equal(final.generation_id, 'capture-01');
  assert.equal(final.fact_contains_raw_payload, false);
  assert.equal(final.registered_route_observed, false);
  assert.equal(final.formal_route_ready, false);
  assert.equal(final.route_to_disk_zero_persistence_observed, false);
  assert.equal(final.business_cancel_count_delta, 0);
  assert.equal(JSON.stringify(facts).includes('samples'), false);
  assert.equal(JSON.stringify(facts).includes(String(frame().samples[17])), false);
});

test('feature-off returns before inspecting binding, dependencies, consumers, or audit hook', () => {
  const inspected = [];
  const request = {
    enabled: false,
    get binding() { inspected.push('binding'); throw new Error('must not inspect binding'); },
    get provider_available() { inspected.push('provider'); throw new Error('must not inspect provider'); },
    get transport_available() { inspected.push('transport'); throw new Error('must not inspect transport'); },
    get on_audio_frame() { inspected.push('audio'); throw new Error('must not inspect consumer'); },
    get on_lifecycle_fact() { inspected.push('audit'); throw new Error('must not inspect audit'); },
    get lifecycle_fact_capacity() { inspected.push('audit-capacity'); throw new Error('must not allocate lane'); },
  };

  const activation = createBrowserGatewayMediaActivation(request);

  assert.equal(activation.active, false);
  assert.equal(activation.reason_id, 'MEDIA_FEATURE_DISABLED');
  assert.deepEqual(inspected, []);
  assert.equal('owner' in activation, false);
  assert.equal(activation.capability.formal_route_ready, false);
  assert.equal(activation.capability.real_transport_observed, false);
});

for (const scenario of [
  { provider: false, transport: true, reason: 'MEDIA_PROVIDER_UNAVAILABLE', inspected: [] },
  { provider: true, transport: false, reason: 'MEDIA_TRANSPORT_UNAVAILABLE', inspected: [] },
]) {
  test(`${scenario.reason} returns before consumer and audit allocation`, () => {
    const inspected = [];
    const request = {
      enabled: true,
      binding: binding(),
      provider_available: scenario.provider,
      transport_available: scenario.transport,
      get on_audio_frame() { inspected.push('audio'); throw new Error('must not inspect consumer'); },
      get on_lifecycle_fact() { inspected.push('audit'); throw new Error('must not inspect audit'); },
      get lifecycle_fact_capacity() { inspected.push('audit-capacity'); throw new Error('must not allocate lane'); },
    };

    const activation = createBrowserGatewayMediaActivation(request);

    assert.equal(activation.active, false);
    assert.equal(activation.reason_id, scenario.reason);
    assert.deepEqual(inspected, scenario.inspected);
    assert.equal('owner' in activation, false);
  });
}

test('registration owner fences exact downlink correlation, generation, response, and unit binding', () => {
  const exact = binding({ direction: 'downlink' });
  const effects = { audio: 0, agent: 0, task: 0 };
  for (const changed of [
    { correlation_id: 'wrong-correlation' },
    { connection_epoch: 4 },
    { track_id: 'wrong-track' },
    { generation: { ...exact.generation, value: 8 }, playout: { ...exact.playout, response_generation: 8 } },
    { generation: { ...exact.generation, id: 'wrong-response' }, playout: { ...exact.playout, response_id: 'wrong-response' } },
    { playout: { ...exact.playout, unit_id: 'wrong-unit' } },
  ]) {
    const activation = active({ exactBinding: exact, effects });
    const detach = activation.owner.attach({
      type: 'media.attach',
      binding: binding({ direction: 'downlink', ...changed }),
    });
    assert.equal(detach.reason_id, 'MEDIA_BINDING_MISMATCH');
    assert.equal(activation.owner.closed, true);
    assert.equal(activation.owner.close().business_cancel_count_delta, 0);
  }
  assertZeroDownstream(effects);
});

test('registration owner retains terminal cleanup and fences every late effect', () => {
  const effects = { audio: 0, agent: 0, task: 0 };
  const activation = active({ effects });
  const owner = activation.owner;
  assert.equal(owner.attach({ type: 'media.attach', binding: activation.binding }), null);
  const first = owner.close('MEDIA_TRANSPORT_CLOSED');
  const lateBinary = owner.acceptBinary(encodeAudioFrame(activation.binding, frame()));
  const lateEnqueue = owner.enqueue(frame());
  const lateDrain = owner.drain(() => { throw new Error('late transport call'); });
  const replay = owner.close('MEDIA_LOCAL_CLOSE');

  assert.equal(replay, first);
  assert.equal(first.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(first.business_cancel_count_delta, 0);
  assert.equal(lateBinary.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.deepEqual(lateEnqueue, { accepted: false, reason_id: 'MEDIA_TRANSPORT_CLOSED' });
  assert.equal(lateDrain.sent_frames, 0);
  assert.equal(lateDrain.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assertZeroDownstream(effects);
});

test('audit callback runs only during an explicit bounded drain', () => {
  let callbackCalls = 0;
  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: binding(),
    provider_available: true,
    transport_available: true,
    on_audio_frame: () => {},
    on_lifecycle_fact: () => { callbackCalls += 1; throw new Error('private audit failure'); },
  });
  assert.equal(activation.active, true);
  activation.owner.attach({ type: 'media.attach', binding: activation.binding });
  activation.owner.close();
  let snapshot = activation.owner.lifecycleSnapshot();

  assert.equal(callbackCalls, 0);
  assert.equal(activation.owner.audit_delivery_failures, 0);
  assert.equal(snapshot.pending_lifecycle_facts, 3);
  assert.equal(activation.owner.drainLifecycleFacts(2), 2);
  snapshot = activation.owner.lifecycleSnapshot();
  assert.equal(callbackCalls, 2);
  assert.equal(activation.owner.audit_delivery_failures, 2);
  assert.equal(snapshot.pending_lifecycle_facts, 1);
  assert.equal(activation.owner.drainLifecycleFacts(2), 1);
  snapshot = activation.owner.lifecycleSnapshot();
  assert.equal(callbackCalls, 3);
  assert.equal(activation.owner.audit_delivery_failures, 3);
  assert.equal(snapshot.audit_delivery_failures, 3);
  assert.equal(snapshot.formal_route_ready, false);
  assert.equal(snapshot.registered_route_observed, false);
  assert.equal(snapshot.route_to_disk_zero_persistence_observed, false);
  assert.equal(snapshot.business_cancel_count_delta, 0);
});

test('lifecycle facts are fixed-capacity and a poison consumer cannot freeze Media cleanup', () => {
  let callbackCalls = 0;
  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: binding(),
    provider_available: true,
    transport_available: true,
    lifecycle_fact_capacity: 2,
    on_audio_frame: () => {},
    on_lifecycle_fact: () => {
      callbackCalls += 1;
      throw new Error('observer sink is unavailable');
    },
  });
  assert.equal(activation.active, true);
  const owner = activation.owner;
  assert.equal(owner.attach({ type: 'media.attach', binding: activation.binding }), null);
  assert.equal(owner.enqueue(frame()).accepted, true);
  const firstClose = owner.close('MEDIA_TRANSPORT_CLOSED');
  const replayClose = owner.close('MEDIA_LOCAL_CLOSE');
  const snapshot = owner.lifecycleSnapshot();

  assert.equal(replayClose, firstClose);
  assert.equal(firstClose.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(callbackCalls, 0);
  assert.equal(owner.pending_lifecycle_facts, 2);
  assert.equal(owner.dropped_lifecycle_facts, 2);
  assert.equal(snapshot.pending_lifecycle_facts, 2);
  assert.equal(snapshot.dropped_lifecycle_facts, 2);
  assert.equal(snapshot.formal_route_ready, false);
  assert.equal(snapshot.registered_route_observed, false);
  assert.equal(snapshot.route_to_disk_zero_persistence_observed, false);
  assert.equal(snapshot.business_cancel_count_delta, 0);
});

test('explicit lifecycle drain can reenter retained cleanup without splitting terminal state', () => {
  let owner = null;
  let callbackClose = null;
  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: binding(),
    provider_available: true,
    transport_available: true,
    on_audio_frame: () => {},
    on_lifecycle_fact: () => {
      callbackClose = owner.close('MEDIA_TRANSPORT_CLOSED');
    },
  });
  assert.equal(activation.active, true);
  owner = activation.owner;

  assert.equal(owner.drainLifecycleFacts(1), 1);
  assert.equal(owner.closed, true);
  assert.equal(callbackClose.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(owner.close('MEDIA_LOCAL_CLOSE'), callbackClose);
  assert.equal(owner.pending_lifecycle_facts, 1);
});

test('active activation exposes no raw sender or receiver bypass and retains one terminal reason', () => {
  const activation = active();
  assert.equal('sender' in activation, false);
  assert.equal('receiver' in activation, false);
  assert.equal('sender' in activation.owner, false);
  assert.equal('receiver' in activation.owner, false);

  const terminal = activation.owner.attach({
    type: 'media.attach',
    binding: binding({ session_id: 'wrong-session' }),
  });
  const replay = activation.owner.close('MEDIA_LOCAL_CLOSE');
  const lateFrame = activation.owner.acceptBinary(encodeAudioFrame(activation.binding, frame()));

  assert.equal(terminal.reason_id, 'MEDIA_BINDING_MISMATCH');
  assert.equal(replay.reason_id, 'MEDIA_BINDING_MISMATCH');
  assert.equal(lateFrame.reason_id, 'MEDIA_BINDING_MISMATCH');
  assert.equal(replay, activation.owner.close('MEDIA_TRANSPORT_CLOSED'));
});

test('reentrant audio consumer close returns retained detach with zero post-close ACK or cursor effect', () => {
  const facts = [];
  let owner = null;
  let audioCalls = 0;
  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: binding(),
    provider_available: true,
    transport_available: true,
    on_audio_frame: () => {
      audioCalls += 1;
      owner.close('MEDIA_TRANSPORT_CLOSED');
    },
    on_lifecycle_fact: (fact) => { facts.push(fact); },
  });
  assert.equal(activation.active, true);
  owner = activation.owner;
  assert.equal(owner.attach({ type: 'media.attach', binding: activation.binding }), null);

  const result = owner.acceptBinary(encodeAudioFrame(activation.binding, frame()));
  const late = owner.acceptBinary(encodeAudioFrame(activation.binding, frame()));
  const retained = owner.close('MEDIA_LOCAL_CLOSE');
  const snapshot = owner.lifecycleSnapshot();

  assert.equal(result.type, 'media.detach');
  assert.equal(result.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(result.through_seq, null);
  assert.equal(result, retained.receiver_detach);
  assert.equal(late, result);
  assert.equal(audioCalls, 1);
  assert.equal(snapshot.receiver_next_seq, 0);
  assert.equal(snapshot.receiver_next_cursor, 0);
  assert.equal(snapshot.receiver_last_ack, null);
  assert.deepEqual(facts, []);
  assert.equal(owner.drainLifecycleFacts(10), 3);
  assert.deepEqual(facts.map(fact => fact.event), [
    'activation.ready',
    'receiver.attach',
    'activation.closed',
  ]);
});

test('reentrant transport close returns retained reason with zero post-close sent or lifecycle effect', () => {
  const facts = [];
  let owner = null;
  let transportCalls = 0;
  let callbackClose = null;
  const activation = createBrowserGatewayMediaActivation({
    enabled: true,
    binding: binding(),
    provider_available: true,
    transport_available: true,
    on_audio_frame: () => {},
    on_lifecycle_fact: (fact) => { facts.push(fact); },
  });
  assert.equal(activation.active, true);
  owner = activation.owner;
  assert.equal(owner.enqueue(frame()).accepted, true);

  const result = owner.drain(() => {
    transportCalls += 1;
    callbackClose = owner.close('MEDIA_TRANSPORT_CLOSED');
    return 'sent';
  });
  const lateDrain = owner.drain(() => { throw new Error('late transport callback'); });
  const lateAck = owner.acknowledge({
    type: 'media.ack',
    lease_id: activation.binding.lease_id,
    generation: activation.binding.generation.value,
    through_seq: 0,
  });
  const snapshot = owner.lifecycleSnapshot();

  assert.equal(result.sent_frames, 0);
  assert.equal(result.pending_frames, 0);
  assert.equal(result.pending_bytes, 0);
  assert.equal(result.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(lateDrain.sent_frames, 0);
  assert.equal(lateDrain.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(lateAck.reason_id, 'MEDIA_TRANSPORT_CLOSED');
  assert.equal(lateAck.through_seq, null);
  assert.equal(transportCalls, 1);
  assert.equal(snapshot.sender_pending_frames, 0);
  assert.equal(snapshot.sender_pending_bytes, 0);
  assert.equal(owner.close('MEDIA_LOCAL_CLOSE'), callbackClose);
  assert.deepEqual(facts, []);
  assert.equal(owner.drainLifecycleFacts(10), 3);
  assert.deepEqual(facts.map(fact => fact.event), [
    'activation.ready',
    'sender.enqueue',
    'activation.closed',
  ]);
});
