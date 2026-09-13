import assert from 'node:assert/strict';
import test from 'node:test';

import { claimProductP3ProgressGeneration } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP3ProgressGenerationJournal.js';

function memoryStorage(initial = new Map()) {
  return {
    values: initial,
    getItem(key) {
      return this.values.get(key) ?? null;
    },
    setItem(key, value) {
      this.values.set(key, value);
    },
  };
}

function identity(overrides = {}) {
  return {
    session_id: 'session-a',
    task_id: 'task-a',
    correlation_id: 'correlation-a',
    origin_id: 'origin-a',
    generation_id: 'generation-a',
    ...overrides,
  };
}

function journalKey(sessionId = 'session-a') {
  return `jiuwenswarm.live_voice.product_p3_progress_generation.v1:${encodeURIComponent(sessionId)}`;
}

test('P3 progress generation journal advances the exact task route across refresh and target switches', async () => {
  const storage = memoryStorage();
  assert.equal(await claimProductP3ProgressGeneration(identity(), { storage }), 1);
  assert.equal(await claimProductP3ProgressGeneration(identity(), { storage }), 2);
  assert.equal(await claimProductP3ProgressGeneration(identity({ task_id: 'task-b' }), { storage }), 1);
  assert.equal(await claimProductP3ProgressGeneration(identity(), { storage }), 3);

  const stored = JSON.parse(storage.getItem(journalKey()));
  assert.equal(stored.contract_version, 'live-voice.product-p3-progress-generation.v1');
  assert.equal(stored.revision, 4);
  assert.deepEqual(
    stored.entries.map(entry => [entry.task_id, entry.correlation_id, entry.last_generation]),
    [
      ['task-a', 'correlation-a', 3],
      ['task-b', 'correlation-a', 1],
    ],
  );
});

test('P3 progress generation journal rejects changed correlation, corruption and exhausted counters without mutation', async () => {
  const storage = memoryStorage();
  await claimProductP3ProgressGeneration(identity(), { storage });
  const stable = storage.getItem(journalKey());

  await assert.rejects(claimProductP3ProgressGeneration(identity({ correlation_id: 'correlation-b' }), { storage }), /correlation changed/);
  assert.equal(storage.getItem(journalKey()), stable);

  const corrupted = JSON.parse(stable);
  corrupted.extra = 'forbidden';
  storage.setItem(journalKey(), JSON.stringify(corrupted));
  const corruptedSerialized = storage.getItem(journalKey());
  await assert.rejects(claimProductP3ProgressGeneration(identity(), { storage }), /shape is invalid/);
  assert.equal(storage.getItem(journalKey()), corruptedSerialized);

  const exhausted = JSON.parse(stable);
  exhausted.entries[0].last_generation = Number.MAX_SAFE_INTEGER;
  storage.setItem(journalKey(), JSON.stringify(exhausted));
  const exhaustedSerialized = storage.getItem(journalKey());
  await assert.rejects(claimProductP3ProgressGeneration(identity(), { storage }), /next progress generation is invalid/);
  assert.equal(storage.getItem(journalKey()), exhaustedSerialized);
});

test('P3 progress generation journal is bounded and never evicts a remembered high-water route', async () => {
  const storage = memoryStorage();
  for (let index = 0; index < 128; index += 1) {
    assert.equal(await claimProductP3ProgressGeneration(identity({ task_id: `task-${index}` }), { storage }), 1);
  }
  const full = storage.getItem(journalKey());
  await assert.rejects(claimProductP3ProgressGeneration(identity({ task_id: 'task-over-capacity' }), { storage }), /capacity is exhausted/);
  assert.equal(storage.getItem(journalKey()), full);
  assert.equal(await claimProductP3ProgressGeneration(identity({ task_id: 'task-0' }), { storage }), 2);
});

test('P3 progress generation journal fails closed on unavailable lease, storage or replaced writes', async () => {
  const storage = memoryStorage();
  await assert.rejects(
    claimProductP3ProgressGeneration(identity(), {
      storage,
      lease: { runExclusive: async () => null },
    }),
    /lease is unavailable/,
  );
  assert.equal(storage.values.size, 0);

  const unavailable = {
    getItem() {
      throw new Error('unavailable');
    },
    setItem() {
      throw new Error('unavailable');
    },
  };
  await assert.rejects(claimProductP3ProgressGeneration(identity(), { storage: unavailable }), /cannot be read/);

  const replaced = memoryStorage();
  replaced.setItem = function setItem(key) {
    this.values.set(key, '{"replaced":true}');
  };
  await assert.rejects(claimProductP3ProgressGeneration(identity(), { storage: replaced }), /write was replaced/);
  assert.equal(replaced.getItem(journalKey()), '{"replaced":true}');
});
