import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ProductTtsContinuationOwner,
  ProductTtsContinuationViolation,
} from '../node_modules/.cache/live-voice-tts-continuation/productTtsContinuationOwner.mjs';

const RESPONSE = Object.freeze({
  interaction_id: 'interaction-1',
  response_id: 'response-1',
  response_generation: 0,
});

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

function unit(seq, start = (seq - 1) * 100, end = seq * 100) {
  return Object.freeze({
    response: RESPONSE,
    unitId: `unit-${seq}`,
    seq,
    sourceStartUtf8: start,
    sourceEndUtf8: end,
    text: `text-${seq}`,
  });
}

function setup() {
  const preparations = new Map();
  const signals = new Map();
  const owner = new ProductTtsContinuationOwner({
    maxActivePreparations: 1,
    maxPreparedSuccessors: 1,
    maximumUnits: 4,
    prepare: (item, signal) => {
      const pending = deferred();
      preparations.set(item.unitId, pending);
      signals.set(item.unitId, signal);
      return pending.promise;
    },
  });
  return { owner, preparations, signals };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('owner prepares the next successor on release and renders it in order', async () => {
  const { owner, preparations } = setup();
  owner.enqueue(unit(1));
  owner.enqueue(unit(2));
  assert.deepEqual([...preparations.keys()], ['unit-1']);

  preparations.get('unit-1').resolve('audio-1');
  await settle();
  assert.deepEqual(owner.takeReleasable(), {
    unit: unit(1),
    prepared: 'audio-1',
  });
  assert.equal(owner.takeReleasable(), null);
  assert.equal(preparations.has('unit-2'), true);
  owner.markRendered('unit-1');
  preparations.get('unit-2').resolve('audio-2');
  await settle();
  assert.deepEqual(owner.takeReleasable(), {
    unit: unit(2),
    prepared: 'audio-2',
  });
});

test('owner keeps only one successor ahead and never starts over two preparations', async () => {
  const { owner, preparations } = setup();
  for (let seq = 1; seq <= 4; seq += 1) owner.enqueue(unit(seq));
  assert.deepEqual([...preparations.keys()], ['unit-1']);

  preparations.get('unit-1').resolve('audio-1');
  await settle();
  owner.takeReleasable();
  assert.equal(preparations.has('unit-3'), false);
  owner.markRendered('unit-1');
  assert.equal(preparations.has('unit-2'), true);
  assert.equal(preparations.has('unit-3'), false);
  assert.equal(preparations.has('unit-4'), false);
});

test('owner prepares one exact successor while the released predecessor plays', async () => {
  const { owner, preparations } = setup();
  for (let seq = 1; seq <= 3; seq += 1) owner.enqueue(unit(seq));

  preparations.get('unit-1').resolve('audio-1');
  await settle();
  assert.equal(owner.takeReleasable()?.unit.unitId, 'unit-1');

  assert.equal(preparations.has('unit-2'), true);
  assert.equal(preparations.has('unit-3'), false);
  assert.equal(owner.takeReleasable(), null);
  assert.equal(owner.snapshot().active_count, 1);

  preparations.get('unit-2').resolve('audio-2');
  await settle();
  assert.equal(owner.takeReleasable(), null);

  owner.markRendered('unit-1');
  assert.equal(owner.takeReleasable()?.unit.unitId, 'unit-2');
  assert.equal(preparations.has('unit-3'), true);
});

test('server ACK settlement is not a continuation scheduler input', () => {
  const { owner } = setup();
  assert.equal('acknowledge' in owner, false);
  assert.equal(typeof owner.markRendered, 'function');
});

test('foreign response span gap duplicate and fifth unit fail before preparation', () => {
  const cases = [
    [unit(1), unit(1)],
    [unit(1), { ...unit(2), sourceStartUtf8: 101 }],
    [unit(1), { ...unit(2), response: { ...RESPONSE, response_id: 'other' } }],
  ];
  for (const items of cases) {
    const { owner, preparations } = setup();
    owner.enqueue(items[0]);
    assert.throws(
      () => owner.enqueue(items[1]),
      error => error instanceof ProductTtsContinuationViolation,
    );
    assert.equal(preparations.size, 1);
  }

  const { owner } = setup();
  for (let seq = 1; seq <= 4; seq += 1) owner.enqueue(unit(seq));
  assert.throws(() => owner.enqueue(unit(5)), ProductTtsContinuationViolation);
});

test('preparation failure cancels all active work with zero retry', async () => {
  const { owner, preparations, signals } = setup();
  owner.enqueue(unit(1));
  owner.enqueue(unit(2));
  preparations.get('unit-1').reject(new Error('provider failed'));
  await settle();

  assert.equal(signals.get('unit-1').aborted, true);
  assert.equal(signals.has('unit-2'), false);
  assert.equal(owner.takeReleasable(), null);
  assert.deepEqual(owner.snapshot(), {
    phase: 'cancelled',
    queued_count: 2,
    active_count: 0,
    prepared_count: 0,
    released_count: 0,
    rendered_count: 0,
    cancelled_count: 2,
    wasted_prefetch_count: 0,
    retry_count: 0,
    reason: 'TTS_PREPARATION_FAILED',
  });
});

test('barge-in cancellation aborts preparation and discards buffered successor', async () => {
  const { owner, preparations, signals } = setup();
  owner.enqueue(unit(1));
  owner.enqueue(unit(2));
  owner.cancel('BARGE_IN');

  assert.equal(signals.get('unit-1').aborted, true);
  assert.equal(signals.has('unit-2'), false);
  assert.equal(owner.takeReleasable(), null);
  assert.equal(owner.snapshot().reason, 'BARGE_IN');
  assert.equal(owner.snapshot().wasted_prefetch_count, 0);
  assert.equal(owner.snapshot().retry_count, 0);
});
