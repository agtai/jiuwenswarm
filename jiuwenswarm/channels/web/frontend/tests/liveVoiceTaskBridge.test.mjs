import assert from 'node:assert/strict';
import test from 'node:test';

import {
  LIVE_VOICE_AUTO_HARNESS_DEMO_DISCLOSURE,
  LIVE_VOICE_AUTO_HARNESS_PIPELINE,
  LiveVoiceTaskBridge,
  isLiveVoiceTaskCommand,
  normalizeLiveVoiceTaskStatus,
  shouldFenceLiveVoiceTaskMonitor,
} from '../node_modules/.cache/live-voice-task-bridge/features/live-voice/liveVoiceTaskBridge.js';

test('the parse-only probe distinguishes fixed task commands from ordinary chat', () => {
  assert.equal(isLiveVoiceTaskCommand('检查进度'), false);
  assert.equal(isLiveVoiceTaskCommand('检查后台任务进度'), true);
  assert.equal(isLiveVoiceTaskCommand('检查后台任务进度。'), true);
  assert.equal(isLiveVoiceTaskCommand('检查后台代码优化任务进度'), true);
  assert.equal(isLiveVoiceTaskCommand('检查后台演进任务进度'), true);
  assert.equal(isLiveVoiceTaskCommand('确认取消后台代码优化任务！'), true);
  assert.equal(isLiveVoiceTaskCommand('确认取消后台演进任务！'), true);
  assert.equal(isLiveVoiceTaskCommand('请分析代码优化方案'), false);
  assert.equal(isLiveVoiceTaskCommand('帮我分析当前仓库'), false);
});

test('only a status or confirmed control command fences the active monitor', () => {
  assert.equal(shouldFenceLiveVoiceTaskMonitor('确认启动后台演进任务：检查日志'), false);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('检查后台任务进度'), true);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('检查后台代码优化任务进度'), true);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('取消后台代码优化任务'), false);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('确认取消后台代码优化任务'), true);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('替换后台代码优化任务目标是修复测试'), false);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('确认替换后台代码优化任务目标是修复测试'), true);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('取消后台演进任务'), false);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('确认取消后台演进任务'), true);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('替换后台演进任务：修复测试'), false);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('确认替换后台演进任务：修复测试'), true);
  assert.equal(shouldFenceLiveVoiceTaskMonitor('普通聊天'), false);
});

function finalInput(text, captureKey = 'capture-1') {
  return {
    captureKey,
    text,
    transcriptKind: 'final',
    committed: true,
  };
}

function makeGateway(overrides = {}) {
  const calls = [];
  let nextId = 1;
  const gateway = {
    owner: overrides.owner,
    async run(request) {
      calls.push({ method: 'run', request });
      if (overrides.run) return overrides.run(request, calls);
      const taskId = `task-${nextId}`;
      nextId += 1;
      return { task_id: taskId, status: 'running' };
    },
    async listByCommand(commandId) {
      calls.push({ method: 'list', commandId });
      if (overrides.listByCommand) return overrides.listByCommand(commandId, calls);
      return { tasks: [] };
    },
    async status(taskId) {
      calls.push({ method: 'status', taskId });
      if (overrides.status) return overrides.status(taskId, calls);
      return { task_id: taskId, status: 'running' };
    },
    async cancel(taskId) {
      calls.push({ method: 'cancel', taskId });
      if (overrides.cancel) return overrides.cancel(taskId, calls);
      return { task_id: taskId, status: 'cancelled' };
    },
  };
  return { gateway, calls };
}

const executionTarget = {
  project_dir: 'D:\\work\\live-voice',
  project_id: 'project-live-voice',
  origin_session_id: 'session-live-voice',
  origin_channel_id: 'channel-web',
};

const executionContract = {
  effective_execution_root: 'D:\\work\\live-voice',
  artifact_kind: 'git_visible_project_change',
  executor: 'jiuwenswarm_code_agent',
  pipeline: 'project_code_pipeline',
  effect_policy: {
    git_commit: 'forbidden',
    git_push: 'forbidden',
    tests: 'forbidden',
    shell: 'forbidden',
  },
};

async function startTask(bridge, query = '改进工具路由', captureKey = 'start') {
  return bridge.handle(finalInput(`确认启动后台演进任务：${query}`, captureKey));
}

test('ordinary committed text is not intercepted and never reaches the task gateway', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);

  const result = await bridge.handle(finalInput('帮我分析当前仓库'));

  assert.deepEqual(result, { handled: false, outcome: 'not-handled' });
  assert.deepEqual(calls, []);
});

test('only the exact Chinese command grammar is recognized', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);

  for (const [index, text] of [
    '请检查进度',
    '确认启动后台代码优化任务目标',
    '确认启动后台代码优化任务：',
    '确认启动后台演进任务目标',
    '确认启动后台演进任务：',
    '确认取消后台任务',
  ].entries()) {
    const result = await bridge.handle(finalInput(text, `strict-${index}`));
    assert.equal(result.handled, false);
  }

  assert.deepEqual(calls, []);
});

test('spoken create separators preserve a narrow confirmed code-optimization command and the query', async () => {
  for (const [index, separator] of [
    '：',
    ':',
    '，',
    ',',
    ' ',
    '冒号',
    '冒号，',
    '任务内容是',
    '任务内容为',
    '，任务内容是',
    '任务内容是：',
    '目标是',
    '目标为',
    '，目标是',
  ].entries()) {
    const { gateway, calls } = makeGateway();
    const bridge = new LiveVoiceTaskBridge(gateway);

    const result = await bridge.handle(finalInput(`确认启动后台代码优化任务${separator}生成测试。`, `separator-${index}`));

    assert.equal(result.outcome, 'started');
    assert.equal(calls[0].request.query, '生成测试');
  }
});

test('an interim command is blocked but does not consume its capture before committed final', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);
  const text = '确认启动后台演进任务：改进日志';

  const interim = await bridge.handle({
    captureKey: 'same-capture',
    text,
    transcriptKind: 'interim',
    committed: false,
  });
  assert.equal(interim.outcome, 'ignored-not-committed');
  assert.deepEqual(calls, []);

  const committed = await bridge.handle(finalInput(text, 'same-capture'));
  assert.equal(committed.outcome, 'started');
  assert.equal(calls.length, 1);
});

test('a final transcript that is not committed cannot dispatch', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);

  const result = await bridge.handle({
    ...finalInput('检查后台任务进度'),
    committed: false,
  });

  assert.equal(result.outcome, 'ignored-not-committed');
  assert.deepEqual(calls, []);
});

test('unconfirmed create, replace, and cancel commands require confirmation with zero gateway calls', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);
  const commands = ['启动后台演进任务：目标 A', '替换后台演进任务：目标 B', '取消后台演进任务'];

  for (const [index, text] of commands.entries()) {
    const result = await bridge.handle(finalInput(text, `confirm-${index}`));
    assert.equal(result.outcome, 'confirmation-required');
    assert.equal(result.feedback.code, 'explicit-confirmation-required');
  }
  assert.deepEqual(calls, []);
});

test('unconfirmed code-optimization commands require confirmation with zero gateway calls', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);
  const commands = [
    '启动后台代码优化任务任务内容是目标 A',
    '替换后台代码优化任务目标是目标 B',
    '取消后台代码优化任务',
  ];

  for (const [index, text] of commands.entries()) {
    const result = await bridge.handle(finalInput(text, `code-optimization-confirm-${index}`));
    assert.equal(result.outcome, 'confirmation-required');
    assert.equal(result.feedback.code, 'explicit-confirmation-required');
  }
  assert.deepEqual(calls, []);
});

test('confirmed code-optimization aliases use the existing create, status, replace, and cancel controls', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);

  const started = await bridge.handle(finalInput('确认启动后台代码优化任务目标是目标 A', 'code-optimization-create'));
  const status = await bridge.handle(finalInput('检查后台代码优化任务进度', 'code-optimization-status'));
  const replaced = await bridge.handle(finalInput('确认替换后台代码优化任务任务内容是目标 B', 'code-optimization-replace'));
  const cancelled = await bridge.handle(finalInput('确认取消后台代码优化任务', 'code-optimization-cancel'));

  assert.equal(started.outcome, 'started');
  assert.equal(status.outcome, 'status');
  assert.equal(replaced.outcome, 'replaced');
  assert.equal(cancelled.outcome, 'cancelled');
  assert.deepEqual(
    calls.map(call => call.method),
    ['run', 'status', 'cancel', 'run', 'cancel']
  );
  assert.equal(calls[0].request.query, '目标 A');
  assert.equal(calls[3].request.query, '目标 B');
});

test('confirmed create uses the fixed side-effecting pipeline and saves the real task id', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ task_id: 'real-task-42', status: 'running', execution_target: executionTarget }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-real-42' });

  const result = await startTask(bridge, '生成一个更好的 Harness');

  assert.equal(result.outcome, 'started');
  assert.equal(result.task.taskId, 'real-task-42');
  assert.equal(result.task.status.kind, 'running');
  assert.deepEqual(result.task.executionTarget, {
    projectDir: 'D:\\work\\live-voice',
    projectId: 'project-live-voice',
    originSessionId: 'session-live-voice',
    originChannelId: 'channel-web',
  });
  assert.equal(result.disclosure.hasCodeSideEffects, true);
  assert.equal(result.disclosure, LIVE_VOICE_AUTO_HARNESS_DEMO_DISCLOSURE);
  assert.deepEqual(calls, [
    {
      method: 'run',
      request: {
        query: '生成一个更好的 Harness',
        pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
        commandId: 'command-real-42',
      },
    },
  ]);
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'real-task-42');
  assert.notEqual(bridge.getSnapshot().lastVisibleTask.executionTarget, result.task.executionTarget);
});

test('missing and legacy unknown execution target fields remain explicitly unknown', async () => {
  const { gateway } = makeGateway({
    run: async () => ({
      task_id: 'legacy-task',
      status: 'running',
      execution_target: {
        project_dir: 'unknown',
        project_id: ' ',
        origin_session_id: null,
      },
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);

  const result = await startTask(bridge, 'legacy target', 'legacy-target');

  assert.deepEqual(result.task.executionTarget, {
    projectDir: null,
    projectId: null,
    originSessionId: null,
    originChannelId: null,
  });
});

test('status rejects conflicting target provenance without changing the remembered task', async () => {
  const statusTarget = {
    ...executionTarget,
    origin_channel_id: 'channel-status',
  };
  const { gateway } = makeGateway({
    run: async () => ({ task_id: 'target-task', status: 'running', execution_target: executionTarget }),
    status: async taskId => ({ task_id: taskId, status: 'completed', execution_target: statusTarget }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge, 'target status', 'target-status-create');

  const result = await bridge.handle(finalInput('检查后台任务进度', 'target-status-read'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'execution-target-conflict');
  assert.equal(result.task.executionTarget.originChannelId, 'channel-web');
  assert.equal(bridge.getSnapshot().lastVisibleTask.executionTarget.projectDir, 'D:\\work\\live-voice');
});

test('a run response without a task id uses one bounded same-key retry, then latches the command for reconciliation', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ task_id: '   ', status: 'running' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);

  const result = await startTask(bridge);
  const retry = await startTask(bridge, '不要重复', 'missing-id-retry');
  const status = await bridge.handle(finalInput('检查后台任务进度', 'missing-id-status'));
  const cancel = await bridge.handle(finalInput('确认取消后台演进任务', 'missing-id-cancel'));

  assert.equal(result.outcome, 'mutation-unknown');
  assert.equal(result.feedback.code, 'mutation-outcome-unknown');
  assert.match(result.feedback.detail, /不会盲目创建重复任务/);
  assert.equal(retry.outcome, 'mutation-unknown');
  assert.equal(status.outcome, 'mutation-unknown');
  assert.equal(cancel.outcome, 'mutation-unknown');
  assert.match(cancel.feedback.detail, /后台任务列表/);
  assert.equal(bridge.getSnapshot().mutationUnknown, true);
  assert.equal(bridge.getSnapshot().lastVisibleTask, null);
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
  assert.equal(new Set(calls.filter(call => call.method === 'run').map(call => call.request.commandId)).size, 1);
});

test('a resolved run payload containing error is a failure while its real task_id remains visible', async () => {
  const { gateway } = makeGateway({
    run: async () => ({
      error: '一次性任务启动失败',
      task_id: 'failed-task-id',
      status: 'failed',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);

  const result = await startTask(bridge);

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'gateway-business-error');
  assert.equal(result.task.taskId, 'failed-task-id');
  assert.equal(result.task.status.kind, 'failed');
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'failed-task-id');
});

test('the same committed capture can produce at most one command', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);
  const input = finalInput('确认启动后台演进任务：任务 A', 'dedupe-key');

  assert.equal((await bridge.handle(input)).outcome, 'started');
  assert.equal((await bridge.handle(input)).outcome, 'duplicate-capture');
  assert.equal(calls.filter(call => call.method === 'run').length, 1);
});

test('a second create is refused while the last visible status is non-terminal or unknown', async () => {
  const { gateway, calls } = makeGateway({
    run: async (_request, allCalls) => ({
      task_id: `task-${allCalls.length}`,
      status: allCalls.length === 1 ? 'running' : 'queued',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);

  await startTask(bridge, '任务 A', 'create-a');
  const result = await startTask(bridge, '任务 B', 'create-b');

  assert.equal(result.outcome, 'active-task-exists');
  assert.equal(result.task.taskId, 'task-1');
  assert.equal(calls.filter(call => call.method === 'run').length, 1);
});

test('both narrow status aliases and cancel without a saved task id make zero requests', async () => {
  const { gateway, calls } = makeGateway();
  const bridge = new LiveVoiceTaskBridge(gateway);

  const status = await bridge.handle(finalInput('检查后台任务进度', 'status-none'));
  const statusAlias = await bridge.handle(finalInput('检查后台演进任务进度', 'status-alias-none'));
  const cancel = await bridge.handle(finalInput('确认取消后台演进任务', 'cancel-none'));

  assert.equal(status.outcome, 'no-visible-task');
  assert.equal(statusAlias.outcome, 'no-visible-task');
  assert.equal(cancel.outcome, 'no-visible-task');
  assert.deepEqual(calls, []);
});

test('status normalization is tolerant and preserves unknown backend values', async () => {
  assert.deepEqual(normalizeLiveVoiceTaskStatus('IN-PROGRESS'), {
    kind: 'running',
    raw: 'IN-PROGRESS',
    terminal: false,
  });
  assert.deepEqual(normalizeLiveVoiceTaskStatus('waiting_for_magic'), {
    kind: 'unknown',
    raw: 'waiting_for_magic',
    terminal: false,
  });
  assert.deepEqual(normalizeLiveVoiceTaskStatus('completed_without_pr'), {
    kind: 'success',
    raw: 'completed_without_pr',
    terminal: true,
  });
  assert.deepEqual(normalizeLiveVoiceTaskStatus('needs_human'), {
    kind: 'unknown',
    raw: 'needs_human',
    terminal: true,
  });

  const { gateway } = makeGateway({
    status: async taskId => ({
      task_id: taskId,
      status: 'waiting_for_magic',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('检查后台任务进度', 'status-unknown'));

  assert.equal(result.outcome, 'status');
  assert.equal(result.task.status.kind, 'unknown');
  assert.equal(result.task.status.raw, 'waiting_for_magic');
  assert.match(result.feedback.detail, /unknown\/waiting_for_magic/);
});

test('a status response for another task id is rejected without changing the visible task', async () => {
  const { gateway } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    status: async () => ({ task_id: 'task-b', status: 'completed' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('检查后台任务进度', 'status-mismatch'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'task-id-mismatch');
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'task-a');
  assert.equal(bridge.getSnapshot().lastVisibleTask.status.kind, 'running');
});

test('a resolved status payload with error is treated as an error', async () => {
  const { gateway } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    status: async taskId => ({ error: '任务不存在', task_id: taskId }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('检查后台任务进度', 'status-error'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'gateway-business-error');
  assert.match(result.feedback.detail, /任务不存在/);
});

test('a run transport error performs one same-key retry before remaining mutation-unknown', async () => {
  const { gateway } = makeGateway({
    run: async () => {
      throw new Error('transport unavailable');
    },
  });
  const bridge = new LiveVoiceTaskBridge(gateway);

  const result = await startTask(bridge);

  assert.equal(result.outcome, 'mutation-unknown');
  assert.equal(result.feedback.code, 'mutation-outcome-unknown');
  assert.equal(bridge.getSnapshot().mutationUnknown, true);
  assert.match(result.feedback.detail, /transport unavailable/);
});

test('every backend terminal task status is not cancelled again', async () => {
  for (const [index, terminalStatus] of [
    'success',
    'FAILED',
    'cancelled',
    'pr_created',
    'completed',
    'completed_without_pr',
    'skipped',
    'needs_human',
  ].entries()) {
    const { gateway, calls } = makeGateway({
      run: async () => ({
        task_id: `terminal-${index}`,
        status: terminalStatus,
      }),
    });
    const bridge = new LiveVoiceTaskBridge(gateway);
    await startTask(bridge, '短任务', `terminal-start-${index}`);

    const result = await bridge.handle(finalInput('确认取消后台演进任务', `terminal-cancel-${index}`));

    assert.equal(result.outcome, 'already-terminal');
    assert.equal(calls.filter(call => call.method === 'cancel').length, 0);
  }
});

test('confirmed cancel targets the saved id and requires a real cancelled status', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ task_id: 'task-cancel-me', status: 'running' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认取消后台演进任务', 'cancel-real'));

  assert.equal(result.outcome, 'cancelled');
  assert.equal(result.task.status.kind, 'cancelled');
  assert.deepEqual(calls.at(-1), {
    method: 'cancel',
    taskId: 'task-cancel-me',
  });
});

test('cancel does not invent success when the backend returns a non-cancelled status', async () => {
  const { gateway } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    cancel: async taskId => ({ task_id: taskId, status: 'still_running' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认取消后台演进任务', 'cancel-unknown'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'cancel-not-confirmed');
  assert.equal(result.task.status.kind, 'unknown');
  assert.equal(result.task.status.raw, 'still_running');
});

test('cancel response task id mismatch is an error', async () => {
  const { gateway } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    cancel: async () => ({ task_id: 'task-b', status: 'cancelled' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认取消后台演进任务', 'cancel-mismatch'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'task-id-mismatch');
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'task-a');
});

test('a terminal cancel business error still updates the remembered real status', async () => {
  let runCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => {
      runCount += 1;
      return { task_id: `task-${runCount}`, status: 'running' };
    },
    cancel: async taskId => ({
      error: '任务已结束，无法取消',
      task_id: taskId,
      status: 'success',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const cancelled = await bridge.handle(finalInput('确认取消后台演进任务', 'cancel-finished'));
  const next = await startTask(bridge, '明确的新任务', 'after-finished');

  assert.equal(cancelled.outcome, 'failed');
  assert.equal(cancelled.feedback.code, 'gateway-business-error');
  assert.equal(cancelled.task.status.kind, 'success');
  assert.equal(next.outcome, 'started');
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'task-2');
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
});

test('replace cancels A before creating B and exposes both real task ids', async () => {
  const { gateway, calls } = makeGateway({
    run: async (_request, allCalls) => ({
      task_id: allCalls.filter(call => call.method === 'run').length === 1 ? 'task-a' : 'task-b',
      status: 'running',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge, '目标 A', 'replace-start');

  const result = await bridge.handle(finalInput('确认替换后台演进任务：目标 B', 'replace'));

  assert.equal(result.outcome, 'replaced');
  assert.equal(result.predecessorTaskId, 'task-a');
  assert.equal(result.successorTaskId, 'task-b');
  assert.equal(result.predecessorCancelled, true);
  assert.deepEqual(
    calls.slice(1).map(call => call.method),
    ['cancel', 'run']
  );
  assert.equal(calls[1].taskId, 'task-a');
  assert.equal(calls[2].request.query, '目标 B');
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'task-b');
});

test('replace never creates B when cancellation of A fails', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    cancel: async taskId => ({
      error: '执行器拒绝取消',
      task_id: taskId,
      status: 'running',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认替换后台演进任务：目标 B', 'replace-cancel-fail'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.predecessorCancelled, false);
  assert.equal(result.feedback.code, 'gateway-business-error');
  assert.equal(calls.filter(call => call.method === 'run').length, 1);
});

test('replace preserves a terminal predecessor status returned with a cancel error', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    cancel: async taskId => ({
      error: '任务已结束，无法取消',
      task_id: taskId,
      status: 'completed',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认替换后台演进任务：目标 B', 'replace-finished'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.predecessorCancelled, false);
  assert.equal(result.task.status.kind, 'success');
  assert.equal(bridge.getSnapshot().lastVisibleTask.status.kind, 'success');
  assert.equal(calls.filter(call => call.method === 'run').length, 1);
});

test('replace truthfully reports A cancelled when creation of B fails', async () => {
  let runCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => {
      runCount += 1;
      if (runCount === 1) return { task_id: 'task-a', status: 'running' };
      return {
        error: '新任务启动失败',
        task_id: 'task-b-failed',
        status: 'failed',
      };
    },
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认替换后台演进任务：目标 B', 'replace-create-fail'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.predecessorTaskId, 'task-a');
  assert.equal(result.predecessorCancelled, true);
  assert.equal(result.successorTaskId, 'task-b-failed');
  assert.equal(result.task.status.kind, 'failed');
  assert.match(result.feedback.title, /前任务已取消/);
  assert.deepEqual(
    calls.map(call => call.method),
    ['run', 'cancel', 'run']
  );
});

test('a new create is allowed after a terminal needs_human task', async () => {
  let runCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => {
      runCount += 1;
      return {
        task_id: `task-${runCount}`,
        status: runCount === 1 ? 'needs_human' : 'running',
      };
    },
  });
  const bridge = new LiveVoiceTaskBridge(gateway);

  assert.equal((await startTask(bridge, '短任务', 'terminal-a')).outcome, 'started');
  const second = await startTask(bridge, '新任务', 'terminal-b');

  assert.equal(second.outcome, 'started');
  assert.equal(second.task.taskId, 'task-2');
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
});

test('in-flight commands are serialized and both duplicate and distinct captures are rejected', async () => {
  let resolveRun;
  const pendingRun = new Promise(resolve => {
    resolveRun = resolve;
  });
  const { gateway, calls } = makeGateway({ run: async () => pendingRun });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-in-flight' });
  const firstInput = finalInput('确认启动后台演进任务：慢任务', 'inflight-a');

  const firstResultPromise = bridge.handle(firstInput);
  assert.equal(bridge.getSnapshot().inFlight, true);
  assert.equal(bridge.getSnapshot().pendingCommandId, 'command-in-flight');

  const duplicate = await bridge.handle(firstInput);
  const distinct = await bridge.handle(finalInput('检查后台任务进度', 'inflight-b'));
  assert.equal(duplicate.outcome, 'duplicate-capture');
  assert.equal(distinct.outcome, 'busy');
  assert.equal(calls.length, 1);

  resolveRun({ task_id: 'slow-task', status: 'running' });
  const first = await firstResultPromise;
  assert.equal(first.outcome, 'started');
  assert.equal(bridge.getSnapshot().inFlight, false);
  assert.equal(bridge.getSnapshot().pendingCommandId, null);

  const distinctRetry = await bridge.handle(finalInput('检查后台任务进度', 'inflight-b'));
  assert.equal(distinctRetry.outcome, 'duplicate-capture');
  assert.equal(calls.length, 1);
});

test('a successful status response without task_id is rejected', async () => {
  const { gateway } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
    status: async () => ({ status: 'completed' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('检查后台任务进度', 'status-no-id'));

  assert.equal(result.outcome, 'failed');
  assert.equal(result.feedback.code, 'task-id-mismatch');
  assert.equal(bridge.getSnapshot().lastVisibleTask.status.kind, 'running');
});

test('an ambiguous successor id latches a recovery conflict and blocks another create', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ task_id: 'task-a', status: 'running' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway);
  await startTask(bridge);

  const result = await bridge.handle(finalInput('确认替换后台演进任务：新目标', 'same-id'));
  const retry = await startTask(bridge, '再次尝试', 'same-id-retry');

  assert.equal(result.outcome, 'recovery-conflict');
  assert.equal(result.feedback.code, 'recovery-conflict');
  assert.equal(result.predecessorCancelled, true);
  assert.equal(result.successorTaskId, undefined);
  assert.equal(result.conflictingTaskId, 'task-a');
  assert.equal(retry.outcome, 'mutation-unknown');
  assert.equal(bridge.getSnapshot().mutationUnknown, true);
  assert.equal(bridge.getSnapshot().lastVisibleTask.status.kind, 'cancelled');
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
}, { timeout: 1000 });

test('a transport-unknown create reuses one stable command id for bounded retry and reports recovery provenance', async () => {
  let runCount = 0;
  const { gateway, calls } = makeGateway({
    owner: {
      sessionId: 'session-live-voice',
      projectDir: 'D:\\work\\live-voice',
      projectId: 'project-live-voice',
    },
    run: async () => {
      runCount += 1;
      if (runCount === 1) throw new Error('response lost');
      return {
        task_id: 'task-retried',
        status: 'running',
        execution_target: executionTarget,
        execution_contract: executionContract,
      };
    },
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-stable' });

  const result = await startTask(bridge, '稳定重试', 'stable-retry');

  assert.equal(result.outcome, 'recovered');
  assert.equal(result.commandId, 'command-stable');
  assert.equal(result.task.resultSource, 'same-key-retry');
  assert.equal(result.task.recoveryStatus, 'recovered');
  assert.deepEqual(
    calls.filter(call => call.method === 'run').map(call => call.request.commandId),
    ['command-stable', 'command-stable']
  );
  assert.deepEqual(
    calls.filter(call => call.method === 'list').map(call => call.commandId),
    ['command-stable']
  );
});

test('an unknown create is reconciled by exact key on the repeated same intent without another run', async () => {
  let listCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => ({ status: 'running' }),
    listByCommand: async commandId => {
      listCount += 1;
      if (listCount < 3) return { tasks: [] };
      return {
        tasks: [
          {
            task_id: 'task-reconciled',
            status: 'running',
            query: '精确核对',
            pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
            origin_namespace: 'live_voice',
            idempotency_key: commandId,
          },
        ],
      };
    },
  });
  let factoryCalls = 0;
  const bridge = new LiveVoiceTaskBridge(gateway, {
    commandIdFactory: () => {
      factoryCalls += 1;
      return 'command-reconcile';
    },
  });

  const unknown = await startTask(bridge, '精确核对', 'reconcile-first');
  const recovered = await startTask(bridge, '精确核对', 'reconcile-repeat');

  assert.equal(unknown.outcome, 'mutation-unknown');
  assert.equal(recovered.outcome, 'recovered');
  assert.equal(recovered.task.taskId, 'task-reconciled');
  assert.equal(recovered.task.source, 'schedule.list');
  assert.equal(recovered.task.resultSource, 'exact-key-reconciliation');
  assert.equal(factoryCalls, 1);
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
  assert.equal(calls.filter(call => call.method === 'list').length, 3);
  assert.equal(new Set(calls.filter(call => call.method !== 'status' && call.method !== 'cancel').map(call => call.request?.commandId ?? call.commandId)).size, 1);
});

test('a distinct committed create after a terminal task receives a new command id', async () => {
  const commandIds = ['command-a', 'command-b'];
  const { gateway, calls } = makeGateway({
    run: async (_request, allCalls) => ({
      task_id: `task-${allCalls.filter(call => call.method === 'run').length}`,
      status: 'completed',
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => commandIds.shift() });

  await startTask(bridge, '意图 A', 'new-id-a');
  await startTask(bridge, '意图 B', 'new-id-b');

  assert.deepEqual(
    calls.filter(call => call.method === 'run').map(call => call.request.commandId),
    ['command-a', 'command-b']
  );
});

test('an exact-key record with a different intent becomes a recovery conflict and is never remembered', async () => {
  let listCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => ({ status: 'running' }),
    listByCommand: async commandId => {
      listCount += 1;
      if (listCount < 3) return { tasks: [] };
      return {
        tasks: [
          {
            task_id: 'wrong-intent-task',
            status: 'running',
            query: '另一个意图',
            pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
            origin_namespace: 'live_voice',
            idempotency_key: commandId,
          },
        ],
      };
    },
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-conflict' });
  await startTask(bridge, '原始意图', 'intent-conflict-first');

  const result = await startTask(bridge, '原始意图', 'intent-conflict-repeat');

  assert.equal(result.outcome, 'recovery-conflict');
  assert.equal(result.recoveryStatus, 'conflict');
  assert.equal(bridge.getSnapshot().lastVisibleTask, null);
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
});

test('exact-key reconciliation rejects missing or conflicting key, namespace, pipeline, query, target, and error fields', async () => {
  const cases = [
    ['missing key', record => ({ ...record, idempotency_key: undefined })],
    ['missing namespace', record => ({ ...record, origin_namespace: undefined })],
    ['missing pipeline', record => ({ ...record, pipeline: undefined })],
    ['missing query', record => ({ ...record, query: undefined })],
    ['business error', record => ({ ...record, error: 'record is not usable' })],
    [
      'wrong target',
      record => ({ ...record, execution_target: { ...record.execution_target, project_dir: 'D:\\other' } }),
    ],
  ];

  for (const [index, [label, mutate]] of cases.entries()) {
    let listCount = 0;
    const { gateway, calls } = makeGateway({
      owner: {
        sessionId: 'session-live-voice',
        projectDir: 'D:\\work\\live-voice',
        projectId: 'project-live-voice',
      },
      run: async () => ({ status: 'running' }),
      listByCommand: async commandId => {
        listCount += 1;
        if (listCount < 3) return { tasks: [] };
        const exact = {
          task_id: `strict-task-${index}`,
          status: 'running',
          query: '严格核对',
          pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
          origin_namespace: 'live_voice',
          idempotency_key: commandId,
          execution_target: executionTarget,
        };
        return { tasks: [mutate(exact)] };
      },
    });
    const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => `strict-command-${index}` });

    await startTask(bridge, '严格核对', `strict-first-${index}`);
    const result = await startTask(bridge, '严格核对', `strict-repeat-${index}`);

    assert.equal(result.outcome, 'recovery-conflict', label);
    assert.equal(bridge.getSnapshot().lastVisibleTask, null, label);
    assert.equal(calls.filter(call => call.method === 'run').length, 2, label);
  }
});

test('exact-key reconciliation never accepts tasks from a top-level list business error', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ status: 'running' }),
    listByCommand: async commandId => ({
      error: 'scope rejected',
      tasks: [
        {
          task_id: 'task-from-error-response',
          status: 'running',
          query: 'strict top-level error',
          pipeline: LIVE_VOICE_AUTO_HARNESS_PIPELINE,
          origin_namespace: 'live_voice',
          idempotency_key: commandId,
          execution_target: executionTarget,
        },
      ],
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'top-level-error-command' });
  const result = await startTask(bridge, 'strict top-level error', 'top-level-error');
  assert.equal(result.outcome, 'mutation-unknown');
  assert.equal(bridge.getSnapshot().lastVisibleTask, null);
  assert.equal(bridge.getSnapshot().pendingCommandId, 'top-level-error-command');
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
});

test('status and cancel prioritize an unresolved newer mutation and never operate on the old visible task', async () => {
  let runCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => {
      runCount += 1;
      return runCount === 1 ? { task_id: 'old-task', status: 'completed' } : { status: 'running' };
    },
  });
  const bridge = new LiveVoiceTaskBridge(gateway, {
    commandIdFactory: (() => {
      const ids = ['old-command', 'pending-command'];
      return () => ids.shift();
    })(),
  });

  await startTask(bridge, '旧任务', 'old-create');
  const unknown = await startTask(bridge, '未决新任务', 'pending-create');
  const status = await bridge.handle(finalInput('检查后台任务进度', 'pending-status'));
  const cancel = await bridge.handle(finalInput('确认取消后台演进任务', 'pending-cancel'));

  assert.equal(unknown.outcome, 'mutation-unknown');
  assert.equal(status.outcome, 'mutation-unknown');
  assert.equal(cancel.outcome, 'mutation-unknown');
  assert.equal(status.commandId, 'pending-command');
  assert.equal(cancel.commandId, 'pending-command');
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'old-task');
  assert.equal(calls.filter(call => call.method === 'status').length, 0);
  assert.equal(calls.filter(call => call.method === 'cancel').length, 0);
  assert.equal(calls.filter(call => call.method === 'run').length, 3);
});

test('a deleted tombstone is terminal and does not block a later create with a new command id', async () => {
  let runCount = 0;
  const { gateway, calls } = makeGateway({
    run: async () => {
      runCount += 1;
      return { task_id: `task-${runCount}`, status: runCount === 1 ? 'deleted' : 'running' };
    },
  });
  const commandIds = ['deleted-command', 'new-command'];
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => commandIds.shift() });

  const tombstone = await startTask(bridge, '已删除任务', 'deleted-create');
  const next = await startTask(bridge, '替代任务', 'after-deleted');

  assert.equal(tombstone.task.status.raw, 'deleted');
  assert.equal(tombstone.task.status.terminal, true);
  assert.equal(next.outcome, 'started');
  assert.equal(next.task.commandId, 'new-command');
  assert.equal(calls.filter(call => call.method === 'run').length, 2);
});

test('a task observed outside the captured owner target fails closed and is not remembered', async () => {
  const { gateway, calls } = makeGateway({
    owner: {
      sessionId: 'session-live-voice',
      projectDir: 'D:\\work\\live-voice',
      projectId: 'project-live-voice',
    },
    run: async () => ({
      task_id: 'wrong-target-task',
      status: 'running',
      execution_target: { ...executionTarget, project_dir: 'D:\\other\\repo' },
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-wrong-target' });

  const result = await startTask(bridge, '不能串项目', 'wrong-target');

  assert.equal(result.outcome, 'recovery-conflict');
  assert.equal(result.feedback.code, 'recovery-conflict');
  assert.equal(result.task.taskId, 'wrong-target-task');
  assert.equal(bridge.getSnapshot().lastVisibleTask, null);
  assert.deepEqual(calls.map(call => call.method), ['run']);
});

test('a new owner-bound task without an execution contract fails closed', async () => {
  const { gateway } = makeGateway({
    owner: {
      sessionId: 'session-live-voice',
      projectDir: 'D:\\work\\live-voice',
      projectId: 'project-live-voice',
    },
    run: async () => ({
      task_id: 'missing-contract-task',
      status: 'running',
      execution_target: executionTarget,
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'missing-contract-command' });

  const result = await startTask(bridge, 'missing contract', 'missing-contract-create');

  assert.equal(result.outcome, 'recovery-conflict');
  assert.equal(bridge.getSnapshot().lastVisibleTask, null);
});

test('status and cancel observations preserve known command and target provenance when fields are omitted', async () => {
  const { gateway } = makeGateway({
    owner: {
      sessionId: 'session-live-voice',
      projectDir: 'D:\\work\\live-voice',
      projectId: 'project-live-voice',
    },
    run: async () => ({
      task_id: 'provenance-task',
      status: 'running',
      execution_target: executionTarget,
      execution_contract: executionContract,
    }),
    status: async taskId => ({ task_id: taskId, status: 'running' }),
    cancel: async taskId => ({ task_id: taskId, status: 'cancelled' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-provenance' });
  await startTask(bridge, '保留来源', 'provenance-create');

  const status = await bridge.handle(finalInput('检查后台任务进度', 'provenance-status'));
  const cancelled = await bridge.handle(finalInput('确认取消后台演进任务', 'provenance-cancel'));

  for (const result of [status, cancelled]) {
    assert.equal(result.task.commandId, 'command-provenance');
    assert.deepEqual(result.task.executionTarget, {
      projectDir: 'D:\\work\\live-voice',
      projectId: 'project-live-voice',
      originSessionId: 'session-live-voice',
      originChannelId: 'channel-web',
    });
    assert.equal(result.task.executionContract.executor, 'jiuwenswarm_code_agent');
  }
  assert.equal(status.task.resultSource, 'status-observation');
  assert.equal(cancelled.task.resultSource, 'cancel-observation');
});

test('status and cancel remain available for a tracked legacy task with no execution contract', async () => {
  const { gateway } = makeGateway({
    run: async () => ({
      task_id: 'legacy-task',
      status: 'running',
      execution_target: executionTarget,
    }),
    status: async taskId => ({ task_id: taskId, status: 'running' }),
    cancel: async taskId => ({ task_id: taskId, status: 'cancelled' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'legacy-command' });
  await startTask(bridge, 'legacy task', 'legacy-create');
  gateway.owner = {
    sessionId: 'session-live-voice',
    projectDir: 'D:\\work\\live-voice',
    projectId: 'project-live-voice',
  };

  const status = await bridge.handle(finalInput('检查后台任务进度', 'legacy-status'));
  const cancelled = await bridge.handle(finalInput('确认取消后台演进任务', 'legacy-cancel'));

  assert.equal(status.outcome, 'status');
  assert.equal(status.task.executionContract.executor, null);
  assert.equal(cancelled.outcome, 'cancelled');
  assert.equal(cancelled.task.executionContract.executor, null);
});

test('a server idempotency conflict exposes only an audit id and never labels it as a successor', async () => {
  const { gateway, calls } = makeGateway({
    run: async () => ({ code: 'IDEMPOTENCY_CONFLICT', error: 'same key, different intent', existing_task_id: 'existing-task' }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-server-conflict' });

  const result = await startTask(bridge, '冲突意图', 'server-conflict');

  assert.equal(result.outcome, 'recovery-conflict');
  assert.equal(result.recoveryStatus, 'conflict');
  assert.equal(result.successorTaskId, undefined);
  assert.equal(result.conflictingTaskId, 'existing-task');
  assert.deepEqual(calls.map(call => call.method), ['run']);
});

test('a monitor observation updates the Bridge only for the exact current task and target', async () => {
  const { gateway } = makeGateway({
    owner: {
      sessionId: 'session-live-voice',
      projectDir: 'D:\\work\\live-voice',
      projectId: 'project-live-voice',
    },
    run: async () => ({
      task_id: 'task-monitor',
      status: 'running',
      execution_target: executionTarget,
      execution_contract: executionContract,
    }),
  });
  const bridge = new LiveVoiceTaskBridge(gateway, { commandIdFactory: () => 'command-monitor' });
  const started = await startTask(bridge, '监控目标', 'monitor-create');
  const terminal = {
    ...started.task,
    status: { kind: 'success', raw: 'completed', terminal: true },
    source: 'schedule.status',
    resultSource: 'status-observation',
  };

  assert.equal(bridge.applyMonitorObservation(terminal), true);
  assert.equal(bridge.getSnapshot().lastVisibleTask.status.raw, 'completed');
  assert.equal(bridge.applyMonitorObservation({ ...terminal, taskId: 'task-foreign' }), false);
  assert.equal(
    bridge.applyMonitorObservation({
      ...terminal,
      executionTarget: { ...terminal.executionTarget, projectDir: 'D:\\other' },
    }),
    false
  );
  assert.equal(bridge.getSnapshot().lastVisibleTask.taskId, 'task-monitor');
});
