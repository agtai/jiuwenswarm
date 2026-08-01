import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isLiveVoiceTaskResultCurrentContext,
  projectLiveVoiceTaskActivity,
  selectLiveVoiceTaskContextInvalidation,
  selectLiveVoiceTaskFeedbackDrainAction,
  selectLiveVoiceTaskSafetyDisclosure,
  selectLiveVoiceTaskTranscriptRoute,
} from '../node_modules/.cache/live-voice-task-adapter/liveVoiceTaskAdapter.mjs';

const confirmedTaskCommand = '确认启动后台演进任务：检查任务适配器';
const executionTargetKey = '["D:\\\\repo","project-a"]';

const visibleTask = {
  taskId: 'task-a',
  commandId: 'command-a',
  query: '目标 A',
  status: { kind: 'cancelled', raw: 'cancelled', terminal: true },
  source: 'schedule.cancel',
  resultSource: 'cancel-observation',
  recoveryStatus: 'not-needed',
  pipeline: 'extended_evolve_pipeline',
  executionTarget: {
    projectDir: 'D:\\repo',
    projectId: 'project-a',
    originSessionId: 'session-a',
    originChannelId: 'channel-web',
  },
};

const feedback = {
  level: 'error',
  code: 'test',
  title: '测试记录',
  detail: '测试详情',
  speakableText: '测试详情',
};

test('flag-off leaves even an exact task command on the normal Chat/Agent path', () => {
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: false,
      transcript: confirmedTaskCommand,
      captureSessionId: 'session-a',
      currentSessionId: 'session-a',
      captureExecutionTargetKey: null,
      currentExecutionTargetKey: null,
    }),
    'chat'
  );
});

test('flag-on still leaves ordinary committed speech on the normal Chat/Agent path', () => {
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: true,
      transcript: '调用终端查看当前分支',
      captureSessionId: 'session-a',
      currentSessionId: 'session-a',
      captureExecutionTargetKey: null,
      currentExecutionTargetKey: null,
    }),
    'chat'
  );
});

test('only an exact task command in the same persisted session reaches dispatch', () => {
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: true,
      transcript: confirmedTaskCommand,
      captureSessionId: 'session-a',
      currentSessionId: 'session-a',
      captureExecutionTargetKey: executionTargetKey,
      currentExecutionTargetKey: executionTargetKey,
    }),
    'dispatch-task'
  );
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: true,
      transcript: confirmedTaskCommand,
      captureSessionId: 'session-a',
      currentSessionId: 'session-b',
      captureExecutionTargetKey: executionTargetKey,
      currentExecutionTargetKey: executionTargetKey,
    }),
    'session-changed'
  );
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: true,
      transcript: confirmedTaskCommand,
      captureSessionId: 'new',
      currentSessionId: 'new',
      captureExecutionTargetKey: null,
      currentExecutionTargetKey: null,
    }),
    'requires-persisted-session'
  );
});

test('an exact task command fails closed when the persisted session has no trusted project target', () => {
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: true,
      transcript: confirmedTaskCommand,
      captureSessionId: 'session-a',
      currentSessionId: 'session-a',
      captureExecutionTargetKey: null,
      currentExecutionTargetKey: null,
    }),
    'requires-execution-target'
  );
});

test('a project target change during capture rejects the task command', () => {
  assert.equal(
    selectLiveVoiceTaskTranscriptRoute({
      taskDemoEnabled: true,
      transcript: confirmedTaskCommand,
      captureSessionId: 'session-a',
      currentSessionId: 'session-a',
      captureExecutionTargetKey: '["D:\\\\repo-a","project-a"]',
      currentExecutionTargetKey: '["D:\\\\repo-b","project-b"]',
    }),
    'execution-target-changed'
  );
});

test('task safety disclosure is absent flag-off and present before flag-on dispatch', () => {
  assert.equal(selectLiveVoiceTaskSafetyDisclosure(false, 'side effects'), undefined);
  assert.equal(selectLiveVoiceTaskSafetyDisclosure(true, 'side effects'), 'side effects');
});

test('context drift isolates an in-flight or mutation-unknown command instead of orphaning its identity', () => {
  const base = {
    rememberedCaptureCount: 1,
    lastVisibleTask: null,
  };

  assert.deepEqual(
    selectLiveVoiceTaskContextInvalidation({
      ...base,
      inFlight: true,
      mutationUnknown: false,
      pendingCommandId: 'command-in-flight',
    }),
    { action: 'isolate', commandId: 'command-in-flight' }
  );
  assert.deepEqual(
    selectLiveVoiceTaskContextInvalidation({
      ...base,
      inFlight: false,
      mutationUnknown: true,
      pendingCommandId: 'command-unknown',
    }),
    { action: 'isolate', commandId: 'command-unknown' }
  );
  assert.deepEqual(
    selectLiveVoiceTaskContextInvalidation({
      ...base,
      inFlight: false,
      mutationUnknown: false,
      pendingCommandId: null,
    }),
    { action: 'clear', commandId: null }
  );
});

test('replace activity keeps attempted command, predecessor, successor, conflict, and record provenance separate', () => {
  const predecessor = projectLiveVoiceTaskActivity({
    handled: true,
    outcome: 'recovery-conflict',
    command: 'replace',
    commandId: 'command-b',
    recoveryStatus: 'conflict',
    predecessorTaskId: 'task-a',
    successorTaskId: 'task-b',
    conflictingTaskId: 'task-conflict',
    predecessorCancelled: true,
    task: visibleTask,
    feedback,
  });

  assert.equal(predecessor.commandId, 'command-b');
  assert.equal(predecessor.predecessorTaskId, 'task-a');
  assert.equal(predecessor.successorTaskId, 'task-b');
  assert.equal(predecessor.conflictingTaskId, 'task-conflict');
  assert.equal(predecessor.record.role, 'predecessor');
  assert.equal(predecessor.record.taskId, 'task-a');
  assert.equal(predecessor.record.commandId, 'command-a');
  assert.equal(predecessor.record.source, 'schedule.cancel');

  const successor = projectLiveVoiceTaskActivity({
    handled: true,
    outcome: 'replaced',
    command: 'replace',
    commandId: 'command-b',
    predecessorTaskId: 'task-a',
    successorTaskId: 'task-b',
    predecessorCancelled: true,
    task: { ...visibleTask, taskId: 'task-b', commandId: 'command-b' },
    feedback: { ...feedback, level: 'info' },
  });
  assert.equal(successor.record.role, 'successor');
});

test('activity never guesses a conflicting task id from a generic predecessor record', () => {
  const activity = projectLiveVoiceTaskActivity({
    handled: true,
    outcome: 'recovery-conflict',
    command: 'replace',
    commandId: 'command-b',
    predecessorTaskId: 'task-a',
    predecessorCancelled: true,
    task: visibleTask,
    feedback,
  });

  assert.equal(activity.conflictingTaskId, undefined);
  assert.equal(activity.record.role, 'predecessor');
});

test('an asynchronous task result cannot update feedback after session navigation', () => {
  const originContext = {};
  assert.equal(isLiveVoiceTaskResultCurrentContext('session-a', 'session-a', originContext, originContext), true);
  assert.equal(isLiveVoiceTaskResultCurrentContext('session-a', 'session-b', originContext, originContext), false);
  assert.equal(isLiveVoiceTaskResultCurrentContext('session-a', null, originContext, originContext), false);
});

test('an asynchronous result stays stale after navigating away and back to the same session', () => {
  assert.equal(isLiveVoiceTaskResultCurrentContext('session-a', 'session-a', {}, {}), false);
});

test('an asynchronous result is stale when the persisted project target changes', () => {
  const bridge = {};
  assert.equal(
    isLiveVoiceTaskResultCurrentContext('session-a', 'session-a', bridge, bridge, 'target-a', 'target-a'),
    true
  );
  assert.equal(
    isLiveVoiceTaskResultCurrentContext('session-a', 'session-a', bridge, bridge, 'target-a', 'target-b'),
    false
  );
});

test('drained task feedback may reopen capture while an unrelated Agent is processing', () => {
  assert.equal(
    selectLiveVoiceTaskFeedbackDrainAction({
      taskFeedbackOwnsResume: true,
      resumeRequested: true,
      responseInProgress: true,
      status: 'idle',
      pendingSpeechCount: 0,
      activeSpeechKey: null,
    }),
    'begin-capture'
  );
});

test('task feedback cannot reopen capture before its own speech drains or without ownership', () => {
  assert.equal(
    selectLiveVoiceTaskFeedbackDrainAction({
      taskFeedbackOwnsResume: true,
      resumeRequested: true,
      responseInProgress: true,
      status: 'idle',
      pendingSpeechCount: 0,
      activeSpeechKey: 'task-feedback:still-playing',
    }),
    'none'
  );
  assert.equal(
    selectLiveVoiceTaskFeedbackDrainAction({
      taskFeedbackOwnsResume: false,
      resumeRequested: true,
      responseInProgress: false,
      status: 'idle',
      pendingSpeechCount: 0,
      activeSpeechKey: null,
    }),
    'none'
  );
});
