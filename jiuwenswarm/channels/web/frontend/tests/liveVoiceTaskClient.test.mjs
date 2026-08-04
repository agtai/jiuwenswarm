import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createLiveVoiceTaskGateway,
  liveVoiceTaskExecutionContextKey,
  LIVE_VOICE_TASK_CLIENT_PIPELINE,
  normalizeLiveVoiceTaskExecutionContext,
  resolveLiveVoiceTaskExecutionContext,
} from '../node_modules/.cache/live-voice-task-client/liveVoiceTaskClient.mjs';

const executionContext = {
  projectDir: 'D:\\work\\live-voice',
  projectId: 'project-live-voice',
};

function makeClient(sessionId = 'session-real-1') {
  const calls = [];
  const response = { task_id: 'task-real-1', status: 'running' };
  const gateway = createLiveVoiceTaskGateway({
    sessionId,
    executionContext,
    request: async (method, params) => {
      calls.push({ method, params });
      return response;
    },
  });
  return { gateway, calls, response };
}

test('run pins the persisted session, AutoHarness mode, and reviewed pipeline', async () => {
  const { gateway, calls, response } = makeClient();

  const result = await gateway.run({
    query: '改进日志路由',
    pipeline: LIVE_VOICE_TASK_CLIENT_PIPELINE,
    commandId: 'command-stable-1',
  });

  assert.equal(result, response);
  assert.deepEqual(gateway.owner, {
    sessionId: 'session-real-1',
    projectDir: 'D:\\work\\live-voice',
    projectId: 'project-live-voice',
    channelId: 'web',
    appId: '',
  });
  assert.deepEqual(calls, [
    {
      method: 'schedule.run',
      params: {
        session_id: 'session-real-1',
        mode: 'auto_harness',
        project_dir: 'D:\\work\\live-voice',
        project_id: 'project-live-voice',
        query: '改进日志路由',
        pipeline: 'extended_evolve_pipeline',
        origin_namespace: 'live_voice',
        idempotency_key: 'command-stable-1',
      },
    },
  ]);
});

test('status and cancel target exactly the supplied real task id', async () => {
  const { gateway, calls } = makeClient(' session-real-2 ');

  await gateway.status('task-a');
  await gateway.cancel('task-a');

  assert.deepEqual(calls, [
    {
      method: 'schedule.status',
      params: {
        session_id: 'session-real-2',
        mode: 'auto_harness',
        project_dir: 'D:\\work\\live-voice',
        project_id: 'project-live-voice',
        task_id: 'task-a',
      },
    },
    {
      method: 'schedule.cancel',
      params: {
        session_id: 'session-real-2',
        mode: 'auto_harness',
        project_dir: 'D:\\work\\live-voice',
        project_id: 'project-live-voice',
        task_id: 'task-a',
      },
    },
  ]);
});

for (const invalidSessionId of ['', '   ', 'new', ' new ']) {
  test(`session ${JSON.stringify(invalidSessionId)} cannot dispatch a task request`, async () => {
    const calls = [];
    assert.throws(
      () =>
        createLiveVoiceTaskGateway({
          sessionId: invalidSessionId,
          executionContext,
          request: async (method, params) => {
            calls.push({ method, params });
            return { task_id: 'must-not-exist', status: 'running' };
          },
        }),
      /persisted session_id/
    );
    assert.deepEqual(calls, []);
  });
}

test('transport payloads, including business errors, pass through unchanged', async () => {
  const payload = {
    error: '启动失败',
    task_id: 'failed-real-id',
    status: 'failed',
  };
  const gateway = createLiveVoiceTaskGateway({
    sessionId: 'session-real-3',
    executionContext,
    request: async () => payload,
  });

  assert.equal(
    await gateway.run({
      query: '会失败的请求',
      pipeline: LIVE_VOICE_TASK_CLIENT_PIPELINE,
      commandId: 'failed-command',
    }),
    payload
  );
});

test('execution context accepts explicit absolute Windows, UNC, and POSIX paths without inferring an ID', () => {
  assert.deepEqual(normalizeLiveVoiceTaskExecutionContext(' D:\\repo ', ' project-a '), {
    projectDir: 'D:\\repo',
    projectId: 'project-a',
  });
  assert.deepEqual(normalizeLiveVoiceTaskExecutionContext('\\\\server\\share\\repo', ''), {
    projectDir: '\\\\server\\share\\repo',
    projectId: null,
  });
  assert.deepEqual(normalizeLiveVoiceTaskExecutionContext('/srv/repo', null), {
    projectDir: '/srv/repo',
    projectId: null,
  });
  assert.equal(liveVoiceTaskExecutionContextKey({ projectDir: '/srv/repo', projectId: null }), '["/srv/repo",null]');
});

test('target resolution accepts only the active persisted session and its exact registered project', () => {
  const session = { sessionId: 'session-a', projectDir: '', projectId: 'default' };
  assert.deepEqual(
    resolveLiveVoiceTaskExecutionContext('session-a', session, {
      projectDir: 'D:\\stable-default',
      projectId: 'default',
    }),
    { projectDir: 'D:\\stable-default', projectId: 'default' }
  );
  assert.equal(
    resolveLiveVoiceTaskExecutionContext('session-a', session, {
      projectDir: 'D:\\another-project',
      projectId: 'other',
    }),
    null
  );
  assert.equal(resolveLiveVoiceTaskExecutionContext('session-b', session, null), null);
  assert.equal(resolveLiveVoiceTaskExecutionContext('new', session, null), null);
});

for (const projectDir of ['', '   ', 'relative/repo', '.', undefined]) {
  test(`untrusted project path ${JSON.stringify(projectDir)} fails closed before transport`, async () => {
    const calls = [];
    const gateway = createLiveVoiceTaskGateway({
      sessionId: 'session-real-target',
      executionContext: { projectDir: projectDir ?? '', projectId: 'project-a' },
      request: async (method, params) => {
        calls.push({ method, params });
        return { task_id: 'must-not-exist', status: 'running' };
      },
    });

    await assert.rejects(
      async () => gateway.run({ query: '不得执行', pipeline: LIVE_VOICE_TASK_CLIENT_PIPELINE, commandId: 'invalid-target-command' }),
      /absolute persisted-session project_dir/
    );
    assert.deepEqual(calls, []);
  });
}

test('all task operations carry the immutable persisted-session target and omit an unknown project id', async () => {
  const calls = [];
  const mutableContext = { projectDir: '/srv/original', projectId: null };
  const gateway = createLiveVoiceTaskGateway({
    sessionId: 'session-target',
    executionContext: mutableContext,
    request: async (method, params) => {
      calls.push({ method, params });
      return { task_id: 'task-target', status: 'running' };
    },
  });
  mutableContext.projectDir = '/srv/changed-after-construction';

  await gateway.run({ query: '目标', pipeline: LIVE_VOICE_TASK_CLIENT_PIPELINE, commandId: 'command-target' });
  await gateway.listByCommand('command-target');
  await gateway.status('task-target');
  await gateway.cancel('task-target');

  assert.equal(calls.length, 4);
  for (const call of calls) {
    assert.equal(call.params.project_dir, '/srv/original');
    assert.equal(call.params.project_id, undefined);
    assert.equal(call.params.session_id, 'session-target');
  }
  assert.deepEqual(calls[0].params, {
    session_id: 'session-target',
    mode: 'auto_harness',
    project_dir: '/srv/original',
    query: '目标',
    pipeline: 'extended_evolve_pipeline',
    origin_namespace: 'live_voice',
    idempotency_key: 'command-target',
  });
  assert.deepEqual(calls[1], {
    method: 'schedule.list',
    params: {
      session_id: 'session-target',
      mode: 'auto_harness',
      project_dir: '/srv/original',
      origin_namespace: 'live_voice',
      idempotency_key: 'command-target',
    },
  });
});

test('exact-key reconciliation is scoped by session, target, namespace, and the stable command id', async () => {
  const { gateway, calls } = makeClient('session-reconcile');

  await gateway.listByCommand('command-reconcile');

  assert.deepEqual(calls, [
    {
      method: 'schedule.list',
      params: {
        session_id: 'session-reconcile',
        mode: 'auto_harness',
        project_dir: 'D:\\work\\live-voice',
        project_id: 'project-live-voice',
        origin_namespace: 'live_voice',
        idempotency_key: 'command-reconcile',
      },
    },
  ]);
});

test('read operations propagate AbortSignal without changing run or cancel calls', async () => {
  const calls = [];
  const gateway = createLiveVoiceTaskGateway({
    sessionId: 'session-signal',
    executionContext,
    request: async (method, params, options) => {
      calls.push({ method, params, options });
      return method === 'schedule.list' ? { tasks: [] } : { task_id: 'task-signal', status: 'running' };
    },
  });
  const controller = new AbortController();

  await gateway.status('task-signal', { signal: controller.signal });
  await gateway.listByCommand('command-signal', { signal: controller.signal });
  await gateway.run({ query: '目标', pipeline: LIVE_VOICE_TASK_CLIENT_PIPELINE, commandId: 'command-signal' });
  await gateway.cancel('task-signal');

  assert.equal(calls[0].options.signal, controller.signal);
  assert.equal(calls[1].options.signal, controller.signal);
  assert.equal(calls[2].options, undefined);
  assert.equal(calls[3].options, undefined);
});
