import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ProductTtsPresentationAckOwner,
} from '../node_modules/.cache/live-voice-tts-presentation-ack/productTtsPresentationAckOwner.mjs';

const RESPONSE = Object.freeze({
  interaction_id: 'interaction-1',
  response_id: 'response-1',
  response_generation: 0,
});

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((accept, fail) => {
    resolve = accept;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function attempt(seq, response = RESPONSE) {
  return Object.freeze({ response, unitId: `unit-${seq}`, seq, attempt: { unitId: `unit-${seq}` } });
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('ACK owner serializes exact units without gating enqueue', async () => {
  const calls = [];
  const first = deferred();
  const second = deferred();
  const owner = new ProductTtsPresentationAckOwner({
    firstUnitSeq: 0,
    lastUnitSeq: 4,
    settle: value => {
      calls.push(value.unitId);
      return value.unitId === 'unit-0' ? first.promise : second.promise;
    },
    onFailure: () => assert.fail('unexpected ACK failure'),
  });

  owner.enqueue(attempt(0));
  owner.enqueue(attempt(1));
  assert.deepEqual(calls, ['unit-0']);
  first.resolve();
  await settle();
  assert.deepEqual(calls, ['unit-0', 'unit-1']);
  second.resolve();
  await owner.whenIdle();
  assert.equal(owner.snapshot().settled_count, 2);
});

test('ACK owner rejects foreign duplicate gapped and overflow units before settlement', () => {
  const calls = [];
  const owner = new ProductTtsPresentationAckOwner({
    firstUnitSeq: 1,
    lastUnitSeq: 4,
    settle: async value => calls.push(value.unitId),
    onFailure: () => assert.fail('unexpected ACK failure'),
  });
  assert.throws(() => owner.enqueue(attempt(2)), /sequence/);
  owner.enqueue(attempt(1));
  assert.throws(() => owner.enqueue(attempt(1)), /sequence|duplicate/);
  assert.throws(
    () => owner.enqueue(attempt(2, { ...RESPONSE, response_id: 'foreign' })),
    /response/,
  );
  owner.enqueue(attempt(2));
  owner.enqueue(attempt(3));
  owner.enqueue(attempt(4));
  assert.throws(() => owner.enqueue(attempt(5)), /bound|sequence/);
});

test('ACK owner rejects one unit identity reused at a later sequence', () => {
  const owner = new ProductTtsPresentationAckOwner({
    firstUnitSeq: 0,
    lastUnitSeq: 4,
    settle: async () => undefined,
    onFailure: () => assert.fail('unexpected ACK failure'),
  });
  owner.enqueue(attempt(0));
  assert.throws(
    () => owner.enqueue({ ...attempt(1), unitId: 'unit-0' }),
    /unit.*reused|duplicate/i,
  );
});

test('terminal ACK failure drops queued successors and reports once', async () => {
  const failure = deferred();
  const failures = [];
  const calls = [];
  const owner = new ProductTtsPresentationAckOwner({
    firstUnitSeq: 0,
    lastUnitSeq: 4,
    settle: value => {
      calls.push(value.unitId);
      return failure.promise;
    },
    onFailure: error => failures.push(error.message),
  });
  owner.enqueue(attempt(0));
  owner.enqueue(attempt(1));
  failure.reject(new Error('ACK terminal'));
  await owner.whenIdle();
  assert.deepEqual(calls, ['unit-0']);
  assert.deepEqual(failures, ['ACK terminal']);
  assert.deepEqual(owner.snapshot(), {
    phase: 'failed',
    queued_count: 0,
    in_flight: false,
    settled_count: 0,
    cancelled_count: 1,
    reason: 'TTS_PRESENTATION_ACK_FAILED',
  });
});

test('cancel fences an in-flight late success and queued successor', async () => {
  const pending = deferred();
  const calls = [];
  const owner = new ProductTtsPresentationAckOwner({
    firstUnitSeq: 0,
    lastUnitSeq: 4,
    settle: value => {
      calls.push(value.unitId);
      return pending.promise;
    },
    onFailure: () => assert.fail('cancel is not failure'),
  });
  owner.enqueue(attempt(0));
  owner.enqueue(attempt(1));
  owner.cancel('BARGE_IN');
  pending.resolve();
  await owner.whenIdle();
  assert.deepEqual(calls, ['unit-0']);
  assert.equal(owner.snapshot().phase, 'cancelled');
  assert.equal(owner.snapshot().settled_count, 0);
  assert.equal(owner.snapshot().cancelled_count, 2);
});
