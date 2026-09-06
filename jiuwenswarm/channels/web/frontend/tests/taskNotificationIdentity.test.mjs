import assert from 'node:assert/strict';
import test from 'node:test';
import { taskNotificationBindingKey, taskNotificationSourceKey } from '../node_modules/.cache/task-notification-identity/taskNotificationIdentity.js';

test('Task display identity survives transports and isolates immutable scope, attempt and event', () => {
  const scope = { subject_id: 'subject', project_id: 'project', session_id: 'session', assurance: 'authenticated' };
  const binding = { scope, task_id: 'task', attempt_id: 'attempt', event_id: 'event' };
  const source = { scope, stream_ref: { kind: 'task', id: 'task' }, event_id: 'event',
    extensions: { 'jiuwenswarm.task_progress_return': { persistent_attempt_id: 'attempt' } } };
  const key = taskNotificationBindingKey(binding, 'session');
  assert.ok(key);
  assert.equal(taskNotificationSourceKey(source, 'session'), key);
  for (const field of ['task_id', 'attempt_id', 'event_id']) assert.notEqual(taskNotificationBindingKey({ ...binding, [field]: 'other' }, 'session'), key);
  for (const field of ['subject_id', 'project_id']) assert.notEqual(taskNotificationBindingKey({ ...binding, scope: { ...scope, [field]: 'other' } }, 'session'), key);
  assert.equal(taskNotificationBindingKey(binding, 'foreign'), null);
  assert.equal(taskNotificationBindingKey({ ...binding, attempt_id: '' }, 'session'), null);
  assert.equal(taskNotificationBindingKey({ ...binding, extra: 'untrusted' }, 'session'), null);
  assert.equal(taskNotificationBindingKey({ ...binding, scope: { ...scope, assurance: 'legacy' } }, 'session'), null);
  assert.equal(taskNotificationSourceKey({ ...source, extensions: {} }, 'session'), null);
  assert.equal(taskNotificationSourceKey(null, 'session'), null);
});
