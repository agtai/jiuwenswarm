import assert from 'node:assert/strict';
import test from 'node:test';

import { LiveVoiceTaskMonitor, parseLiveVoiceTaskObservation } from '../node_modules/.cache/live-voice-task-monitor/liveVoiceTaskMonitor.mjs';

const owner = {
  sessionId: 'session-a',
  projectDir: 'D:\\repo',
  projectId: 'project-a',
  channelId: 'web',
  appId: '',
};

const task = {
  taskId: 'task-a',
  commandId: 'command-a',
  query: '改进日志路由',
  status: { kind: 'running', raw: 'running', terminal: false },
  source: 'schedule.run',
  resultSource: 'fresh',
  recoveryStatus: 'not-needed',
  pipeline: 'extended_evolve_pipeline',
  executionTarget: {
    projectDir: 'D:\\repo',
    projectId: 'project-a',
    originSessionId: 'session-a',
    originChannelId: null,
  },
};

function observation(status = 'running', overrides = {}) {
  return {
    task_id: 'task-a',
    status,
    query: '改进日志路由',
    pipeline: 'extended_evolve_pipeline',
    idempotency_key: 'command-a',
    execution_target: {
      project_dir: 'D:\\repo',
      project_id: 'project-a',
      origin_session_id: 'session-a',
      origin_channel_id: 'web',
    },
    provenance: {
      owner_scope: { channel_id: 'web', session_id: 'session-a', app_id: '' },
      origin_namespace: 'live_voice',
      idempotency_key: 'command-a',
      legacy_unscoped: false,
      access: 'authorized',
    },
    ...overrides,
  };
}

class FakeClock {
  nowValue = 0;
  nextId = 1;
  timers = new Map();

  now() {
    return this.nowValue;
  }

  setTimeout(callback, delayMs) {
    const id = this.nextId++;
    this.timers.set(id, { at: this.nowValue + delayMs, callback });
    return id;
  }

  clearTimeout(id) {
    this.timers.delete(id);
  }

  nextDelay() {
    if (this.timers.size === 0) return null;
    return Math.min(...[...this.timers.values()].map(timer => timer.at)) - this.nowValue;
  }

  advance(delayMs) {
    const target = this.nowValue + delayMs;
    for (;;) {
      const due = [...this.timers.entries()].filter(([, timer]) => timer.at <= target).sort((left, right) => left[1].at - right[1].at)[0];
      if (!due) break;
      this.nowValue = due[1].at;
      this.timers.delete(due[0]);
      due[1].callback();
    }
    this.nowValue = target;
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

function createHarness({ status, listByCommand, accepted = true } = {}) {
  const clock = new FakeClock();
  const statusCalls = [];
  const listCalls = [];
  const snapshots = [];
  const observations = [];
  const gateway = {
    owner,
    status: async (taskId, options) => {
      statusCalls.push({ taskId, options });
      return status ? status(taskId, options, statusCalls.length) : observation('running');
    },
    listByCommand: async (commandId, options) => {
      listCalls.push({ commandId, options });
      return listByCommand ? listByCommand(commandId, options, listCalls.length) : { tasks: [observation('running')] };
    },
  };
  const monitor = new LiveVoiceTaskMonitor({
    task,
    gateway,
    clock,
    onSnapshot: snapshot => snapshots.push(snapshot),
    onObservation: value => {
      observations.push(value);
      return accepted;
    },
  });
  return { clock, gateway, monitor, statusCalls, listCalls, snapshots, observations };
}

test('a connected monitor reads immediately, follows cadence, and stops irreversibly at terminal', async () => {
  const responses = [observation('queued'), observation('running'), observation('completed')];
  const harness = createHarness({ status: async () => responses.shift() });

  harness.monitor.start(true);
  await settle();
  assert.equal(harness.statusCalls.length, 1);
  assert.equal(harness.monitor.getSnapshot().phase, 'polling');
  assert.equal(harness.clock.nextDelay(), 1000);

  harness.clock.advance(1000);
  await settle();
  assert.equal(harness.statusCalls.length, 2);
  assert.equal(harness.clock.nextDelay(), 2000);

  harness.clock.advance(2000);
  await settle();
  assert.equal(harness.statusCalls.length, 3);
  assert.equal(harness.monitor.getSnapshot().phase, 'terminal');
  assert.equal(harness.clock.nextDelay(), null);
  harness.clock.advance(60000);
  await settle();
  assert.equal(harness.statusCalls.length, 3);
  assert.equal(harness.observations.length, 3);
});

test('a failed backend task replaces stale progress with terminal failure facts', async () => {
  const harness = createHarness({
    status: async () =>
      observation('failed', {
        progress: { summary: '2/4 已完成，正在 构建验证' },
        last_error: 'Permission denied: log.json',
      }),
  });

  harness.monitor.start(true);
  await settle();

  const snapshot = harness.monitor.getSnapshot();
  assert.equal(snapshot.phase, 'terminal');
  assert.deepEqual(snapshot.task.status, { kind: 'failed', raw: 'failed', terminal: true });
  assert.equal(snapshot.progressSummary, '2/4 已完成，正在 构建验证');
  assert.equal(snapshot.lastError, 'Permission denied: log.json');
  assert.equal(harness.clock.nextDelay(), null);
});

test('running cadence changes from two seconds to five seconds after thirty seconds', async () => {
  const harness = createHarness();
  harness.monitor.start(true);
  await settle();
  assert.equal(harness.clock.nextDelay(), 2000);
  harness.clock.advance(30000);
  await settle();
  assert.equal(harness.clock.nextDelay(), 5000);
});

test('unknown non-terminal status remains truthful and polls at five seconds', async () => {
  const harness = createHarness({ status: async () => observation('future_state') });
  harness.monitor.start(true);
  await settle();
  assert.deepEqual(harness.monitor.getSnapshot().task.status, { kind: 'unknown', raw: 'future_state', terminal: false });
  assert.equal(harness.clock.nextDelay(), 5000);
  assert.equal(harness.monitor.takeTerminalNotification(), null);
});

for (const [name, payload, code] of [
  ['non-object payload', null, 'invalid-task-payload'],
  ['wrong task id', observation('running', { task_id: 'task-foreign' }), 'task-id-mismatch'],
  ['missing status', observation('running', { status: '' }), 'invalid-task-status'],
  ['wrong target', observation('running', { execution_target: { ...observation().execution_target, project_dir: 'D:\\other' } }), 'task-scope-mismatch'],
  ['denied provenance', observation('running', { provenance: { ...observation().provenance, access: 'denied' } }), 'task-scope-mismatch'],
  [
    'wrong channel target and provenance',
    observation('running', {
      execution_target: { ...observation().execution_target, origin_channel_id: 'foreign-channel' },
      provenance: {
        ...observation().provenance,
        owner_scope: { ...observation().provenance.owner_scope, channel_id: 'foreign-channel' },
      },
    }),
    'task-scope-mismatch',
  ],
  [
    'wrong app provenance',
    observation('running', {
      provenance: {
        ...observation().provenance,
        owner_scope: { ...observation().provenance.owner_scope, app_id: 'foreign-app' },
      },
    }),
    'task-scope-mismatch',
  ],
  ['malformed progress', observation('running', { progress: 'halfway' }), 'invalid-task-progress'],
  ['malformed last error', observation('running', { last_error: 42 }), 'invalid-task-last-error'],
]) {
  test(`${name} stops without adopting foreign or malformed facts`, async () => {
    const harness = createHarness({ status: async () => payload });
    harness.monitor.start(true);
    await settle();
    assert.equal(harness.monitor.getSnapshot().phase, 'adapter-error');
    assert.equal(harness.monitor.getSnapshot().errorCode, code);
    assert.equal(harness.observations.length, 0);
    assert.equal(harness.clock.nextDelay(), null);
  });
}

test('stable missing and other business errors remain distinct and never update status', async () => {
  const missing = createHarness({ status: async () => ({ error: 'missing', code: 'TASK_NOT_FOUND', task_id: 'task-a' }) });
  missing.monitor.start(true);
  await settle();
  assert.equal(missing.monitor.getSnapshot().phase, 'missing');
  assert.equal(missing.observations.length, 0);

  const unavailable = createHarness({ status: async () => ({ error: 'unavailable', code: 'TASK_STORE_UNAVAILABLE', task_id: 'task-a' }) });
  unavailable.monitor.start(true);
  await settle();
  assert.equal(unavailable.monitor.getSnapshot().phase, 'adapter-error');
  assert.equal(unavailable.monitor.getSnapshot().errorCode, 'TASK_STORE_UNAVAILABLE');
  assert.equal(unavailable.observations.length, 0);

  unavailable.monitor.setConnected(false);
  unavailable.monitor.setConnected(true);
  await settle();
  assert.equal(unavailable.statusCalls.length, 1);
  assert.equal(unavailable.listCalls.length, 0);
  assert.equal(unavailable.monitor.getSnapshot().phase, 'adapter-error');
});

test('retriable reads back off at one, two, five, and capped ten seconds without changing identity', async () => {
  let failures = 0;
  const harness = createHarness({
    status: async () => {
      if (failures < 5) {
        failures += 1;
        throw { code: 'REQUEST_TIMEOUT', message: 'timeout', retriable: true };
      }
      return observation('running');
    },
  });
  harness.monitor.start(true);
  await settle();
  for (const delay of [1000, 2000, 5000, 10000, 10000]) {
    assert.equal(harness.clock.nextDelay(), delay);
    harness.clock.advance(delay);
    await settle();
  }
  assert.equal(harness.statusCalls.length, 6);
  assert.equal(harness.monitor.getSnapshot().retryCount, 0);
  assert.ok(harness.statusCalls.every(call => call.taskId === 'task-a'));
  assert.equal(harness.listCalls.length, 0);
});

test('disconnect aborts and fences an unresolved status before exact-key reconciliation', async () => {
  const pending = deferred();
  const harness = createHarness({ status: async () => pending.promise });
  harness.monitor.start(true);
  await settle();
  assert.equal(harness.statusCalls.length, 1);

  harness.monitor.setConnected(false);
  assert.equal(harness.statusCalls[0].options.signal.aborted, true);
  harness.monitor.setConnected(true);
  await settle();
  assert.equal(harness.listCalls.length, 0);

  pending.resolve(observation('failed'));
  await settle();
  assert.equal(harness.listCalls.length, 1);
  assert.deepEqual(harness.listCalls[0].commandId, 'command-a');
  assert.equal(harness.observations.length, 1);
  assert.equal(harness.observations[0].source, 'schedule.list');
  assert.equal(harness.monitor.getSnapshot().phase, 'polling');
});

test('empty and conflicting exact-key reconciliation stop without status, run, or cancel effects', async () => {
  const empty = createHarness({ listByCommand: async () => ({ tasks: [] }) });
  empty.monitor.start(false);
  empty.monitor.setConnected(true);
  await settle();
  assert.equal(empty.monitor.getSnapshot().phase, 'missing');
  assert.equal(empty.statusCalls.length, 0);
  assert.equal(empty.observations.length, 0);

  const conflict = createHarness({ listByCommand: async () => ({ tasks: [observation(), observation()] }) });
  conflict.monitor.start(false);
  conflict.monitor.setConnected(true);
  await settle();
  assert.equal(conflict.monitor.getSnapshot().phase, 'adapter-error');
  assert.equal(conflict.monitor.getSnapshot().errorCode, 'task-list-conflict');
  assert.equal(conflict.statusCalls.length, 0);
  assert.equal(conflict.observations.length, 0);
});

test('store-unavailable reconciliation is an adapter error rather than a missing task', async () => {
  const harness = createHarness({
    listByCommand: async () => ({
      error: 'unavailable',
      code: 'TASK_STORE_UNAVAILABLE',
    }),
  });
  harness.monitor.start(false);
  harness.monitor.setConnected(true);
  await settle();

  assert.equal(harness.monitor.getSnapshot().phase, 'adapter-error');
  assert.equal(harness.monitor.getSnapshot().errorCode, 'TASK_STORE_UNAVAILABLE');
  assert.equal(harness.statusCalls.length, 0);
  assert.equal(harness.observations.length, 0);
});

test('stop fences a late completion and clears all future reads', async () => {
  const pending = deferred();
  const harness = createHarness({ status: async () => pending.promise });
  harness.monitor.start(true);
  await settle();
  harness.monitor.stop();
  pending.resolve(observation('completed'));
  await settle();
  assert.equal(harness.monitor.getSnapshot().phase, 'stopped');
  assert.equal(harness.observations.length, 0);
  assert.equal(harness.clock.nextDelay(), null);
});

test('a Bridge rejection stops the monitor instead of creating UI-only truth', async () => {
  const harness = createHarness({ accepted: false });
  harness.monitor.start(true);
  await settle();
  assert.equal(harness.monitor.getSnapshot().phase, 'adapter-error');
  assert.equal(harness.monitor.getSnapshot().errorCode, 'bridge-observation-rejected');
  assert.equal(harness.clock.nextDelay(), null);
});

test('terminal notification is neutral and available at most once', async () => {
  const harness = createHarness({ status: async () => observation('needs_human') });
  harness.monitor.start(true);
  await settle();
  const first = harness.monitor.takeTerminalNotification();
  assert.match(first, /needs_human/);
  assert.match(first, /不代表成功/);
  assert.equal(harness.monitor.takeTerminalNotification(), null);
});

test('the strict parser preserves optional Unicode facts and ignores unknown fields', () => {
  const parsed = parseLiveVoiceTaskObservation(
    observation('running', {
      progress: { summary: '正在检查：语音路由' },
      last_error: '上一次连接失败',
      future_field: { any: true },
    }),
    task,
    owner,
    'schedule.status'
  );
  assert.equal(parsed.ok, true);
  assert.equal(parsed.observation.progressSummary, '正在检查：语音路由');
  assert.equal(parsed.observation.lastError, '上一次连接失败');
});
