import assert from 'node:assert/strict';
import test from 'node:test';

import {
  persistProductP3TaskTarget,
  readProductP3TaskTarget,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP3TaskTargetJournal.js';

function memoryStorage() {
  const values = new Map();
  return {
    values,
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

function target(overrides = {}) {
  return {
    session_id: 'session-a',
    correlation_id: 'correlation-a',
    task_id: 'task-a',
    task_control_binding: {
      subject_id: 'subject-a',
      session_id: 'session-a',
      project_id: 'project-a',
      correlation_id: 'correlation-a',
      generation: 1,
    },
    ...overrides,
  };
}

test('P3 task target journal round-trips one exact credential-free Session binding', () => {
  const storage = memoryStorage();
  assert.equal(persistProductP3TaskTarget(target(), storage), true);
  assert.deepEqual(
    readProductP3TaskTarget({ session_id: 'session-a' }, storage),
    { contract_version: 'live-voice.product-p3-task-target.v1', ...target() }
  );
});

test('P3 task target journal retains its exact task correlation across P2 successors', () => {
  const storage = memoryStorage();
  const historical = target({
    correlation_id: 'historical-task-correlation',
    task_control_binding: { ...target().task_control_binding, correlation_id: 'historical-task-correlation' },
  });
  assert.equal(persistProductP3TaskTarget(historical, storage), true);
  assert.deepEqual(readProductP3TaskTarget({ session_id: 'session-a' }, storage), {
    contract_version: 'live-voice.product-p3-task-target.v1',
    ...historical,
  });
});

test('P3 task target journal rejects cross-correlation, cross-scope, malformed and extra authority', () => {
  const storage = memoryStorage();
  assert.equal(
    persistProductP3TaskTarget(
      target({ task_control_binding: { ...target().task_control_binding, session_id: 'session-b' } }),
      storage
    ),
    false
  );

  assert.equal(persistProductP3TaskTarget(target(), storage), true);
  const [key] = storage.values.keys();
  storage.values.set(
    key,
    JSON.stringify({ ...target(), contract_version: 'live-voice.product-p3-task-target.v1', correlation_id: 'correlation-b' })
  );
  assert.equal(readProductP3TaskTarget({ session_id: 'session-a' }, storage), null);
  storage.values.set(key, JSON.stringify({ ...target(), contract_version: 'live-voice.product-p3-task-target.v1', credential: 'forbidden' }));
  assert.equal(readProductP3TaskTarget({ session_id: 'session-a' }, storage), null);
  storage.values.set(key, '{');
  assert.equal(readProductP3TaskTarget({ session_id: 'session-a' }, storage), null);
  storage.values.set(key, 'x'.repeat(32_769));
  assert.equal(readProductP3TaskTarget({ session_id: 'session-a' }, storage), null);
  assert.equal(readProductP3TaskTarget({ session_id: 'session-b' }, storage), null);
});

test('P3 task target journal degrades without turning a completed mutation into a false failure', () => {
  const unavailable = {
    getItem() {
      throw new Error('storage unavailable');
    },
    setItem() {
      throw new Error('storage unavailable');
    },
  };
  assert.equal(persistProductP3TaskTarget(target(), unavailable), false);
  assert.equal(readProductP3TaskTarget({ session_id: 'session-a' }, unavailable), null);
});
