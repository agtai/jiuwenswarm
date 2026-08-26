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

function closeInteraction(port, response) {
  return port.closeInteraction?.(response) ?? false;
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

test('local stop drops queued audio and fences later chunks', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  assert.equal(port.stopLocal(first), true);
  assert.deepEqual(port.pending(first), []);
  assert.equal(port.enqueue(chunk(first, 1)), false);
});

test('exact interaction close releases stopped state and permanently fences revival', () => {
  const port = new AudioPort();
  port.begin(first);
  port.enqueue(chunk(first, 0));
  assert.equal(port.stopLocal(first), true);
  const closed = closeInteraction(port, first);

  let revivalRejected = false;
  try {
    port.begin(second);
  } catch (error) {
    revivalRejected = error instanceof AudioPortViolation && error.reason === 'RESPONSE_GENERATION_NOT_INCREASING';
  }
  assert.equal(revivalRejected, true);
  assert.equal(closed, true);
  assert.deepEqual(port.pending(first), []);
  assert.equal(port.enqueue(chunk(first, 1)), false);
  assert.equal(closeInteraction(port, first), false);
});

test('stale interaction close cannot retire a newer response generation', () => {
  const port = new AudioPort();
  port.begin(first);
  port.begin(second);
  assert.equal(closeInteraction(port, first), false);
  assert.equal(port.enqueue(chunk(second, 0)), true);
  const closed = closeInteraction(port, second);

  let revivalRejected = false;
  try {
    port.begin({ interaction_id: second.interaction_id, response_id: 'response-3', response_generation: 2 });
  } catch (error) {
    revivalRejected = error instanceof AudioPortViolation && error.reason === 'RESPONSE_GENERATION_NOT_INCREASING';
  }
  assert.equal(revivalRejected, true);
  assert.equal(closed, true);
  assert.equal(port.enqueue(chunk(second, 1)), false);
});

test('audio replay ownership uses distinct bounded response and terminal-interaction fences', () => {
  const port = new AudioPort();
  let closedCount = 0;
  for (let index = 0; index < 2_000; index += 1) {
    const response = Object.freeze({
      interaction_id: `closed-interaction-${index}`,
      response_id: `audio-response-${index}`,
      response_generation: 0,
    });
    port.begin(response);
    if (closeInteraction(port, response)) closedCount += 1;
  }

  assert.throws(
    () =>
      port.begin({
        interaction_id: 'retired-response-replay',
        response_id: 'audio-response-0',
        response_generation: 0,
      }),
    error => error instanceof AudioPortViolation && error.reason === 'RESPONSE_ID_REUSED'
  );

  // This unused response ID becomes a four-hash false positive only when
  // audio-response-1871 retires at the exact 128-entry response-ID boundary.
  // The old unbounded Set, or a 129-entry exact ledger, admits it.
  assert.throws(
    () =>
      port.begin({
        interaction_id: 'response-fence-recovery-owner',
        response_id: 'unused-audio-boundary-4053973',
        response_generation: 0,
      }),
    error => error instanceof AudioPortViolation && error.reason === 'RESPONSE_ID_REUSED'
  );
  const responseRecovery = Object.freeze({
    interaction_id: 'response-fence-recovery-owner',
    response_id: 'fresh-audio-recovery',
    response_generation: 0,
  });
  port.begin(responseRecovery);
  assert.equal(closeInteraction(port, responseRecovery), true);

  assert.throws(
    () =>
      port.begin({
        interaction_id: 'closed-interaction-0',
        response_id: 'revival-response',
        response_generation: 1,
      }),
    error => error instanceof AudioPortViolation && error.reason === 'RESPONSE_GENERATION_NOT_INCREASING'
  );

  // Unlike response IDs, retired interactions do not keep a second 128-entry
  // exact ledger: every terminal identity enters its own conservative tombstone.
  assert.throws(
    () =>
      port.begin({
        interaction_id: 'unused-interaction-candidate-9808',
        response_id: 'interaction-candidate-response',
        response_generation: 0,
      }),
    error => error instanceof AudioPortViolation && error.reason === 'RESPONSE_GENERATION_NOT_INCREASING'
  );
  const interactionRecovery = Object.freeze({
    interaction_id: 'fresh-interaction-recovery',
    response_id: 'fresh-interaction-response',
    response_generation: 0,
  });
  port.begin(interactionRecovery);
  assert.equal(closeInteraction(port, interactionRecovery), true);

  const replacementOwner = new AudioPort();
  replacementOwner.begin({
    interaction_id: 'unused-interaction-candidate-9808',
    response_id: 'unused-audio-boundary-4053973',
    response_generation: 0,
  });
  assert.equal(closedCount, 2_000);
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
