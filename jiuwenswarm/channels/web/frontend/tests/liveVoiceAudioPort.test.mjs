import assert from 'node:assert/strict';
import test from 'node:test';

import { AudioPort, AudioPortViolation, createAudioRenderPlan } from '../node_modules/.cache/live-voice-audio-port/features/live-voice/formal/audioPort.js';

const first = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 });
const second = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-2', response_generation: 1 });
const formal = Object.freeze({ provider_id: 'formal-tts', implementation_class: 'formal', fallback_from: null });

function chunk(response, seq, overrides = {}) {
  return {
    response,
    unit_id: 'unit-1',
    seq,
    audio: new Uint8Array([seq + 1]),
    provider: formal,
    ...overrides,
  };
}

test('current response queues ordered audio and acknowledgements drain it', () => {
  const port = new AudioPort();
  port.begin(first);
  assert.equal(port.enqueue(chunk(first, 0)), true);
  assert.equal(port.enqueue(chunk(first, 1)), true);
  assert.deepEqual(
    port.pending(first).map(item => item.seq),
    [0, 1]
  );
  assert.equal(port.acknowledge(first, 'unit-1', 0), 1);
  assert.deepEqual(
    port.pending(first).map(item => item.seq),
    [1]
  );
});

test('verified EOF requires the exact full accepted manifest even after some PCM rendered', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  port.enqueue(chunk(first, 1));
  port.enqueue(chunk(first, 0, { unit_id: 'unit-2' }));
  port.acknowledge(first, 'unit-1', 0);
  const exact = [{ unit_id: 'unit-1', contiguous_through_seq: 1 }, { unit_id: 'unit-2', contiguous_through_seq: 0 }];
  for (const invalid of [[], exact.slice(0, 1), [exact[0], exact[0]], [exact[0], { ...exact[1], contiguous_through_seq: 1 }],
    [exact[0], { ...exact[1], extra: true }], [exact[0], { ...exact[1], contiguous_through_seq: true }]]) {
    assert.throws(() => port.sealExact(first, invalid), error => error.reason === 'INVALID_AUDIO_FINAL_CURSOR');
  }
  assert.equal(port.sealExact(second, exact), null);
  const frozen = port.sealExact(first, exact);
  assert.equal(frozen.completion_kind, 'verified_eof');
  assert.deepEqual(frozen.accepted_cutoff, exact);
  assert.equal(Object.isFrozen(frozen.accepted_cutoff[0]), true);
  assert.equal(port.enqueue(chunk(first, 2)), false);
  assert.equal(port.sealExact(first, [...exact].reverse()), frozen);
  assert.equal(port.acknowledge(first, 'unit-1', 1), 1);
  assert.equal(port.acknowledge(first, 'unit-2', 0), 1);
  assert.deepEqual(port.pending(first), []);
});

test('unknown EOF freezes only the accepted prefix and cannot upgrade to completed speech', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  const frozen = port.freezeAcceptedPrefix(first);
  assert.deepEqual(frozen.accepted_cutoff, [{ unit_id: 'unit-1', contiguous_through_seq: 0 }]);
  assert.equal(port.freezeAcceptedPrefix(first), frozen);
  assert.equal(port.enqueue(chunk(first, 1)), false);
  assert.throws(() => port.sealExact(first, frozen.accepted_cutoff), error => error.reason === 'AUDIO_COMPLETION_KIND_CONFLICT');
  assert.equal(port.acknowledge(first, 'unit-1', 0), 1);
  assert.equal(port.stopLocal(first), true);
  assert.equal(port.freezeAcceptedPrefix(first), null);
  port.begin(second);
  assert.equal(port.freezeAcceptedPrefix(first), null);
  assert.deepEqual(port.freezeAcceptedPrefix(second).accepted_cutoff, []);
  assert.equal(port.businessCancelCount(), 0);
});

test('replacement and wrong response chunks have zero playback effect', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  port.begin(second);
  assert.equal(port.enqueue(chunk(first, 1)), false);
  assert.equal(port.enqueue(chunk({ ...second, response_generation: 9 }, 0)), false);
  assert.deepEqual(port.pending(first), []);
  assert.deepEqual(port.pending(second), []);
});

test('local stop does not escalate to a business cancellation', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  assert.equal(port.stopLocal(first), true);
  assert.deepEqual(port.pending(first), []);
  assert.equal(port.businessCancelCount(), 0);
  assert.equal(port.enqueue(chunk(first, 1)), false);
});

test('sequence gaps and response reuse reject without queued audio', () => {
  const port = new AudioPort();
  port.begin(first);
  assert.throws(
    () => port.enqueue(chunk(first, 1)),
    error => error instanceof AudioPortViolation && error.reason === 'NON_CONTIGUOUS_AUDIO_SEQUENCE'
  );
  assert.deepEqual(port.pending(first), []);
  assert.throws(
    () => port.begin(first),
    error => error instanceof AudioPortViolation && error.reason === 'RESPONSE_ID_REUSED'
  );
});

test('fallback provenance remains visible and cannot be omitted', () => {
  const port = new AudioPort();
  port.begin(first);
  const fallback = { provider_id: 'browser-tts', implementation_class: 'fallback', fallback_from: 'formal-tts' };
  assert.equal(port.enqueue(chunk(first, 0, { provider: fallback })), true);
  assert.equal(port.pending(first)[0].provider.fallback_from, 'formal-tts');
  assert.throws(
    () => port.enqueue(chunk(first, 1, { provider: { ...fallback, fallback_from: null } })),
    error => error instanceof AudioPortViolation && error.reason === 'FALLBACK_PROVENANCE_REQUIRED'
  );
});

test('render plan preserves display text and explicit transform spans', () => {
  const plan = createAudioRenderPlan('WHO update', 'World Health Organization update', [
    { transform: 'expand.abbreviation', source_start: 0, source_end: 3, rendered_text: 'World Health Organization' },
  ]);
  assert.equal(plan.display_text, 'WHO update');
  assert.equal(plan.spoken_text, 'World Health Organization update');
  assert.equal(plan.transforms[0].source_end, 3);
  assert.equal(Object.isFrozen(plan), true);
  assert.equal(Object.isFrozen(plan.transforms), true);
});

test('ack beyond delivery and invalid provider class reject without draining audio', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  assert.throws(
    () => port.acknowledge(first, 'unit-1', 1),
    error => error instanceof AudioPortViolation && error.reason === 'INVALID_AUDIO_ACK'
  );
  assert.deepEqual(
    port.pending(first).map(item => item.seq),
    [0]
  );
  assert.throws(
    () => port.enqueue(chunk(first, 1, { provider: { ...formal, implementation_class: 'hidden' } })),
    error => error instanceof AudioPortViolation && error.reason === 'INVALID_IMPLEMENTATION_CLASS'
  );
  assert.deepEqual(
    port.pending(first).map(item => item.seq),
    [0]
  );
});

test('unsupported provider and false fallback provenance cannot enqueue', () => {
  const port = new AudioPort();
  port.begin(first);
  assert.throws(
    () =>
      port.enqueue(
        chunk(first, 0, {
          provider: { provider_id: 'none', implementation_class: 'unsupported', fallback_from: null },
        })
      ),
    error => error instanceof AudioPortViolation && error.reason === 'AUDIO_PROVIDER_UNSUPPORTED'
  );
  assert.throws(
    () => port.enqueue(chunk(first, 0, { provider: { ...formal, fallback_from: 'other' } })),
    error => error instanceof AudioPortViolation && error.reason === 'UNEXPECTED_FALLBACK_PROVENANCE'
  );
  assert.deepEqual(port.pending(first), []);
});
