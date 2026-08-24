import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FORMAL_P3_TASK_METHODS,
  FormalP3TaskExperienceOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/formalP3TaskExperience.js';

const sessionId = 'session-p3-7';
const scope = Object.freeze({
  subject_id: 'subject-p3-7',
  session_id: sessionId,
  project_id: 'project-p3-7',
  assurance: 'authenticated',
});

function envelope(requestId, result, ok = true) {
  return {
    request_id: requestId,
    ok,
    result,
    error: ok ? null : { code: 'CONFLICT', reason: result.reason, message: 'rejected' },
    product_composition: {},
  };
}

function taskRecord({
  taskId,
  attemptId,
  state,
  outcome = null,
  eventHead,
  revision = 1,
  predecessorTaskId = null,
  queued = false,
  retainedAdmission = false,
  name = taskId,
}) {
  return {
    task_id: taskId,
    scope: { ...scope },
    spec: {
      name,
      instruction: `${name} instruction`,
      origin: {},
      context: {},
      executor_id: 'executor-p3-7',
      required_capabilities: [],
      side_effect_class: 'project_mutation',
      constraints: [],
      attributes: {},
    },
    state,
    attempt_id: attemptId,
    correlation_id: `correlation-${taskId}`,
    cancel_requested: false,
    dispatch_fenced: false,
    outcome,
    reconciliation: null,
    revision: {
      number: revision,
      predecessor_task_id: predecessorTaskId,
      create_command_id: `create-${taskId}`,
    },
    event_head: eventHead,
    queued,
    admission: queued || retainedAdmission
      ? {
          task_id: taskId,
          attempt_id: attemptId,
          queued,
          priority: 'high',
          reason: null,
          attempt_count: 0,
          next_eligible_at: '2026-08-21T00:00:00Z',
          deadline_at: '2026-08-21T01:00:00Z',
          enqueued_at: '2026-08-21T00:00:00Z',
          reconciliation_required: false,
          reconciliation_reason: null,
          manual_action: null,
        }
      : null,
  };
}

function attempt(task, { number = 1, executorRef = 'executor-ref' } = {}) {
  return {
    task_id: task.task_id,
    attempt_id: task.attempt_id,
    attempt_number: number,
    executor_id: 'executor-p3-7',
    executor_ref: executorRef,
    state: task.state === 'terminal' ? 'terminal' : task.state === 'accepted' ? 'accepted' : 'running',
    outcome: task.outcome,
    source_seq: executorRef === null ? -1 : task.event_head,
    executor_selection: {
      adapter_id: 'live-voice.direct-project-code',
      capability_profile: {
        operation_versions: [
          ['adjust.demo-itinerary-checkpoint', 'v1'],
          ['cancel', 'v1'],
          ['dispatch', 'v1'],
          ['status', 'v1'],
        ],
      },
      capability_profile_digest: 'a'.repeat(64),
      execution_requirements: {},
      admission_priority: 'normal',
    },
  };
}

function event(task, seq, eventType, state, outcome = null, details = {}) {
  return {
    event_id: `${task.task_id}:event:${seq}`,
    task_id: task.task_id,
    attempt_id: task.attempt_id,
    scope: { ...scope },
    seq,
    event_type: eventType,
    state,
    outcome,
    producer: 'task_core',
    source_event_id: seq === 0 ? null : `${task.task_id}:source:${seq}`,
    causation_id: `${task.task_id}:cause:${seq}`,
    correlation_id: task.correlation_id,
    occurred_at: '2026-08-21T00:00:00Z',
    details,
  };
}

function memoryStorage(selectedTaskId = null) {
  const values = new Map();
  if (selectedTaskId !== null) {
    values.set(`jiuwenswarm.live_voice.formal_p3_selection.v1:${encodeURIComponent(sessionId)}`, selectedTaskId);
  }
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
    values,
  };
}

function authoritativeFixture({
  selectedHint = 'task-a',
  collectionOperations = ['task.create'],
  taskAOperations = ['task.create_successor', 'task.retry', 'task.status'],
  taskBOperations = ['task.adjust', 'task.cancel', 'task.events', 'task.result', 'task.status'],
  resultSourceEventId = 'task-a:source:1',
} = {}) {
  const taskA = taskRecord({
    taskId: 'task-a',
    attemptId: 'attempt-a',
    state: 'terminal',
    outcome: 'completed',
    eventHead: 1,
    name: 'Completed predecessor',
  });
  const taskB = taskRecord({
    taskId: 'task-b',
    attemptId: 'attempt-b',
    state: 'running',
    eventHead: 1,
    revision: 2,
    predecessorTaskId: 'task-a',
    retainedAdmission: true,
    name: 'Running successor',
  });
  const calls = [];
  let structuredCalls = 0;
  const request = async (method, params, requestId) => {
    calls.push({ method, params, requestId });
    if (method === FORMAL_P3_TASK_METHODS.list) {
      return envelope(requestId, { tasks: [taskB, taskA], cursor: null, next_cursor: null, has_more: false, limit: 100, supported_operations: collectionOperations });
    }
    const task = params.task_id === taskA.task_id ? taskA : taskB;
    if (method === FORMAL_P3_TASK_METHODS.status) {
      return envelope(requestId, {
        task,
        attempt: attempt(task),
        admission: task.admission,
        retry_admission: {
          eligible: task.task_id === taskA.task_id,
          reason: task.task_id === taskA.task_id ? 'TASK_RETRY_ELIGIBLE' : 'TASK_RETRY_STATE_CONFLICT',
          task_id: task.task_id,
          attempt_id: task.task_id === taskA.task_id ? task.attempt_id : null,
          attempt_number: task.task_id === taskA.task_id ? 2 : null,
        },
        supported_operations: task.task_id === taskA.task_id ? taskAOperations : taskBOperations,
      });
    }
    if (method === FORMAL_P3_TASK_METHODS.events) {
      const events = task.task_id === taskA.task_id
        ? [event(taskA, 0, 'task.accepted', 'accepted'), event(taskA, 1, 'task.terminal', 'terminal', 'completed')]
        : [event(taskB, 0, 'task.accepted', 'accepted'), event(taskB, 1, 'task.running', 'running', null, { progress: 'checkpoint 1/3' })];
      return envelope(requestId, {
        task_id: task.task_id,
        after_seq: params.after_seq,
        events,
        head_seq: task.event_head,
        next_after_seq: null,
        has_more: false,
        limit: 500,
        truncated: false,
        cursor_replay_supported: true,
      });
    }
    if (method === FORMAL_P3_TASK_METHODS.result) {
      return envelope(requestId, task.task_id === taskA.task_id
        ? {
            task_id: task.task_id,
            availability: 'available',
            reason: 'TASK_RESULT_AVAILABLE',
            task_result: {
              task_id: task.task_id,
              attempt_id: task.attempt_id,
              source_event_id: resultSourceEventId,
              result_text: 'immutable predecessor result',
              artifacts: [{ relative_path: 'result.txt', sha256: 'b'.repeat(64) }],
              completed_at: '2026-08-21T00:00:00Z',
            },
          }
        : { task_id: task.task_id, availability: 'not_ready', reason: 'TASK_RESULT_NOT_READY', task_result: null });
    }
    if (method === FORMAL_P3_TASK_METHODS.intent) {
      structuredCalls += 1;
      if (structuredCalls === 1) {
        return envelope(requestId, {
          status: 'clarification',
          reason: 'TASK_CONFIRMATION_REQUIRED',
          operation: 'task.adjust',
          task_id: taskB.task_id,
          confirmation_token: 'confirmation-adjust-1',
          confirmation_form: 'confirm task request confirmation-adjust-1',
          partial_command_count: 0,
        });
      }
      return envelope(requestId, {
        status: 'dispatched',
        reason: 'TASK_INTENT_DISPATCHED',
        operation: 'task.adjust',
        task_id: taskB.task_id,
        formal_task_result: {
          task_id: taskB.task_id,
          attempt_id: taskB.attempt_id,
          state: 'running',
          applied: true,
          reason: 'TASK_ADJUST_APPLIED',
        },
      });
    }
    throw new Error(`unexpected method ${method}`);
  };
  return { taskA, taskB, calls, request, store: memoryStorage(selectedHint) };
}

test('refresh exposes two exact Tasks, hint-only selection, lineage, replay and immutable result truth without inventing unread state', async () => {
  const fixture = authoritativeFixture();
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });

  const snapshot = await owner.refresh(sessionId);

  assert.equal(snapshot.status, 'ready');
  assert.equal(snapshot.tasks.length, 2);
  assert.equal(snapshot.selected_task_id, 'task-a');
  const predecessor = snapshot.tasks.find(task => task.task_id === 'task-a');
  const successor = snapshot.tasks.find(task => task.task_id === 'task-b');
  assert.equal(predecessor.successor_task_id, 'task-b');
  assert.equal(predecessor.result_text, 'immutable predecessor result');
  assert.equal(predecessor.replay_event_count, 2);
  assert.equal(successor.predecessor_task_id, 'task-a');
  assert.equal('unread_event_count' in predecessor, false);
  assert.equal('unread_event_count' in successor, false);
  assert.deepEqual(snapshot.collection_operations, ['task.create']);
  assert.deepEqual(
    fixture.calls.filter(call => [FORMAL_P3_TASK_METHODS.intent, FORMAL_P3_TASK_METHODS.confirmation, FORMAL_P3_TASK_METHODS.mutate].includes(call.method)),
    [],
  );
});

test('available TaskResult binds to the terminal source event and rejects the TaskEvent record id with zero mutation', async () => {
  const acceptedFixture = authoritativeFixture();
  const acceptedOwner = new FormalP3TaskExperienceOwner({
    enabled: true,
    request: acceptedFixture.request,
    store: acceptedFixture.store,
  });

  const accepted = await acceptedOwner.refresh(sessionId);

  assert.equal(accepted.status, 'ready');
  assert.equal(accepted.tasks.find(task => task.task_id === 'task-a').result_text, 'immutable predecessor result');

  const rejectedFixture = authoritativeFixture({ resultSourceEventId: 'task-a:event:1' });
  const rejectedOwner = new FormalP3TaskExperienceOwner({
    enabled: true,
    request: rejectedFixture.request,
    store: rejectedFixture.store,
  });

  await assert.rejects(rejectedOwner.refresh(sessionId), /TaskResult identity mismatch/);
  assert.equal(rejectedOwner.snapshot().status, 'failed');
  assert.deepEqual(rejectedOwner.snapshot().tasks, []);
  assert.equal(
    rejectedFixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent).length,
    0,
  );
});

test('selection performs an exact fresh status/events/result reread and rejects foreign ids before transport', async () => {
  const fixture = authoritativeFixture();
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await owner.refresh(sessionId);
  const before = fixture.calls.length;

  await assert.rejects(owner.select('task-foreign'), /not authoritative/);
  assert.equal(fixture.calls.length, before);

  const selected = await owner.select('task-b');
  const task = selected.tasks.find(item => item.task_id === 'task-b');
  assert.equal(task.display_state, 'running');
  assert.equal(task.progress, 'checkpoint 1/3');
  assert.equal(task.result_availability, 'not_ready');
  assert.ok(task.available_operations.includes('task.adjust'));
});

test('retained admission rejects queued truth outside accepted lifecycle or contradicting its Task projection', async () => {
  const invalidTasks = [
    taskRecord({ taskId: 'task-running-queued', attemptId: 'attempt-running-queued', state: 'running', eventHead: 1, queued: true }),
    taskRecord({ taskId: 'task-flag-mismatch', attemptId: 'attempt-flag-mismatch', state: 'accepted', eventHead: 0, queued: true }),
  ];
  invalidTasks[1].admission.queued = false;
  for (const invalidTask of invalidTasks) {
    const calls = [];
    const owner = new FormalP3TaskExperienceOwner({
      enabled: true,
      store: memoryStorage(),
      request: async (method, _params, requestId) => {
        calls.push(method);
        return envelope(requestId, {
          tasks: [invalidTask],
          cursor: null,
          next_cursor: null,
          has_more: false,
          limit: 100,
          supported_operations: ['task.create'],
        });
      },
    });
    await assert.rejects(owner.refresh(sessionId), /admission binding mismatch/);
    assert.deepEqual(calls, [FORMAL_P3_TASK_METHODS.list]);
  }
});

test('unsupported controls are stable and produce zero query, mutation, Agent, Tool, audio or history effects', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await owner.refresh(sessionId);
  const before = fixture.calls.length;

  for (const operation of ['task.provide_input', 'task.pause', 'task.resume']) {
    const snapshot = await owner.issue({ operation, task_id: 'task-b' });
    assert.equal(snapshot.command.phase, 'rejected');
    assert.equal(snapshot.command.reason, 'TASK_CONTROL_UNSUPPORTED');
  }

  assert.equal(fixture.calls.length, before);
});

test('structured adjustment separates confirmation, accepted/applied and terminal outcome with a second authority reread', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await owner.refresh(sessionId);

  const pending = await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  assert.equal(pending.command.phase, 'confirmation_required');
  assert.equal(pending.command.accepted, false);
  assert.equal(pending.command.applied, false);
  assert.equal(pending.command.terminal_outcome, null);

  const settled = await owner.confirm();
  assert.equal(settled.command.phase, 'applied');
  assert.equal(settled.command.accepted, true);
  assert.equal(settled.command.applied, true);
  assert.equal(settled.command.terminal_outcome, null);
  assert.match(settled.command.command_id, /^formal-p3-command-/);
  assert.notEqual(settled.command.command_id, settled.command.request_id);
  const intents = fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent);
  assert.equal(intents.length, 2);
  assert.equal(intents[1].params.continuation_id, 'confirmation-adjust-1');
  assert.ok(fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.status).length >= 3);
});

test('five production structured controls preserve their exact closed operation target and arguments', async () => {
  const cases = [
    {
      input: { operation: 'task.create', name: 'Create task', instruction: 'Create instruction' },
      target: null,
      arguments: { name: 'Create task', instruction: 'Create instruction' },
    },
    {
      input: { operation: 'task.update', task_id: 'task-b', instruction: 'Updated instruction' },
      target: 'task-b',
      arguments: { instruction: 'Updated instruction' },
    },
    {
      input: { operation: 'task.reprioritize', task_id: 'task-b', priority: 'urgent' },
      target: 'task-b',
      arguments: { priority: 'urgent' },
    },
    {
      input: { operation: 'task.cancel', task_id: 'task-b' },
      target: 'task-b',
      arguments: {},
    },
    {
      input: { operation: 'task.create_successor', task_id: 'task-a', name: 'Successor', instruction: 'Successor instruction' },
      target: 'task-a',
      arguments: { name: 'Successor', instruction: 'Successor instruction' },
    },
  ];
  for (const item of cases) {
    const fixture = authoritativeFixture({
      taskBOperations: ['task.update', 'task.reprioritize', 'task.cancel'],
    });
    const request = async (method, params, id) => {
      if (method !== FORMAL_P3_TASK_METHODS.intent) return fixture.request(method, params, id);
      fixture.calls.push({ method, params, requestId: id });
      return envelope(id, {
        status: 'clarification',
        reason: 'TASK_CONFIRMATION_REQUIRED',
        operation: item.input.operation,
        task_id: item.target,
        confirmation_token: `confirmation-${item.input.operation}`,
        confirmation_form: `confirm task request confirmation-${item.input.operation}`,
        partial_command_count: 0,
      });
    };
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
    await owner.refresh(sessionId);
    const pending = await owner.issue(item.input);
    assert.equal(pending.command.phase, 'confirmation_required');
    const call = fixture.calls.find(call => call.method === FORMAL_P3_TASK_METHODS.intent);
    assert.deepEqual(call.params.structured_intent, {
      operation: item.input.operation,
      target: item.target,
      arguments: item.arguments,
    });
    assert.equal(call.params.source, 'structured');
    assert.equal(call.params.operation_hint, item.input.operation);
    assert.equal(call.params.task_id_hint ?? null, item.target);
  }
});

test('retry uses only its exact target through the existing confirmation primitive', async () => {
  const fixture = authoritativeFixture();
  const request = async (method, params, id) => {
    if (method !== FORMAL_P3_TASK_METHODS.confirmation) return fixture.request(method, params, id);
    fixture.calls.push({ method, params, requestId: id });
    return envelope(id, {
      status: 'confirmation_issued',
      confirmation_id: 'confirmation-retry',
      expires_at: '2026-08-21T01:00:00Z',
      replayed: false,
      operation: 'task.retry',
      command_id: params.command_id,
      target_task_id: 'task-a',
      task_control_binding: {},
    });
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  const pending = await owner.issue({ operation: 'task.retry', task_id: 'task-a' });
  assert.equal(pending.command.phase, 'confirmation_required');
  const call = fixture.calls.find(item => item.method === FORMAL_P3_TASK_METHODS.confirmation);
  assert.deepEqual(Object.keys(call.params).sort(), [
    'command_id',
    'correlation_id',
    'issued_at',
    'operation',
    'session_id',
    'task_id',
  ]);
  assert.equal(call.params.task_id, 'task-a');
});

test('ready and progress-route adoption eligibility occur only after list, status, replay and result all succeed', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const snapshots = [];
  let resultSucceeded = false;
  const owner = new FormalP3TaskExperienceOwner({
    enabled: true,
    store: fixture.store,
    request: async (method, params, id) => {
      const value = await fixture.request(method, params, id);
      if (method === FORMAL_P3_TASK_METHODS.result) resultSucceeded = true;
      return value;
    },
    on_snapshot: snapshot => snapshots.push({ status: snapshot.status, selected: snapshot.selected_task_id, resultSucceeded }),
  });

  await owner.refresh(sessionId);
  assert.deepEqual(
    fixture.calls
      .filter(call => call.params.task_id === 'task-b')
      .map(call => call.method),
    [
      FORMAL_P3_TASK_METHODS.status,
      FORMAL_P3_TASK_METHODS.events,
      FORMAL_P3_TASK_METHODS.result,
    ],
  );
  const ready = snapshots.filter(snapshot => snapshot.status === 'ready');
  assert.equal(ready.length, 1);
  assert.equal(ready[0].resultSucceeded, true);
  assert.equal(ready[0].selected, 'task-b');
  assert.ok(snapshots.slice(0, -1).every(snapshot => snapshot.status === 'loading' && snapshot.selected === null));
});

test('selection revalidation failure withdraws old selection and every executable control', async () => {
  const fixture = authoritativeFixture();
  let failSelection = false;
  const owner = new FormalP3TaskExperienceOwner({
    enabled: true,
    store: fixture.store,
    request: async (method, params, id) => {
      if (failSelection && method === FORMAL_P3_TASK_METHODS.status && params.task_id === 'task-b') {
        return envelope(`${id}-ambiguous`, { task: fixture.taskB });
      }
      return fixture.request(method, params, id);
    },
  });
  await owner.refresh(sessionId);
  failSelection = true;
  const beforeMutations = fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent).length;

  await assert.rejects(owner.select('task-b'), /response result is invalid|REQUEST_REJECTED/);
  const failed = owner.snapshot();
  assert.equal(failed.status, 'failed');
  assert.equal(failed.selected_task_id, null);
  assert.deepEqual(failed.tasks, []);
  assert.deepEqual(failed.collection_operations, []);
  assert.equal(fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent).length, beforeMutations);
});

test('Task-wide replay keeps previous Attempt history but projects progress only from the current Attempt', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  fixture.taskB.event_head = 3;
  const oldAttempt = { ...fixture.taskB, attempt_id: 'attempt-b-old' };
  const request = async (method, params, id) => {
    if (method !== FORMAL_P3_TASK_METHODS.events || params.task_id !== 'task-b') return fixture.request(method, params, id);
    fixture.calls.push({ method, params, requestId: id });
    return envelope(id, {
      task_id: 'task-b',
      after_seq: -1,
      events: [
        event(oldAttempt, 0, 'task.running', 'running', null, { progress: 'previous Attempt 1/2' }),
        event(fixture.taskB, 1, 'task.accepted', 'accepted'),
        event(oldAttempt, 2, 'task.running', 'running', null, { progress: 'late previous Attempt 2/2' }),
        event(fixture.taskB, 3, 'task.running', 'running', null, { progress: 'current Attempt 1/3' }),
      ],
      head_seq: 3,
      next_after_seq: null,
      has_more: false,
      limit: 500,
      truncated: false,
      cursor_replay_supported: true,
    });
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });

  const snapshot = await owner.refresh(sessionId);
  const selected = snapshot.tasks.find(task => task.task_id === 'task-b');
  assert.equal(selected.progress, 'current Attempt 1/3');
  assert.equal(selected.replay_event_count, 4);
  assert.deepEqual(selected.replay_event_types, ['task.running', 'task.accepted', 'task.running', 'task.running']);
});

test('concurrent refreshes fence a late predecessor without overwriting the newer authority', async () => {
  const fixture = authoritativeFixture();
  let firstListResolve;
  let listCalls = 0;
  const owner = new FormalP3TaskExperienceOwner({
    enabled: true,
    store: fixture.store,
    request: async (method, params, id) => {
      if (method === FORMAL_P3_TASK_METHODS.list && ++listCalls === 1) {
        return new Promise(resolve => { firstListResolve = () => resolve(fixture.request(method, params, id)); });
      }
      return fixture.request(method, params, id);
    },
  });
  const predecessor = owner.refresh(sessionId);
  await new Promise(resolve => setImmediate(resolve));
  const successor = owner.refresh(sessionId);
  await successor;
  firstListResolve();
  await assert.rejects(predecessor, /became stale/);
  assert.equal(owner.snapshot().status, 'ready');
  assert.equal(owner.snapshot().selected_task_id, 'task-a');
});

test('status-only collection authority exposes no create or targeted controls and produces zero mutation', async () => {
  const fixture = authoritativeFixture({
    collectionOperations: [],
    taskAOperations: [],
    taskBOperations: [],
  });
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  const snapshot = await owner.refresh(sessionId);
  assert.deepEqual(snapshot.collection_operations, []);
  assert.deepEqual(snapshot.tasks.find(task => task.task_id === snapshot.selected_task_id).available_operations, []);
  const beforeMutations = fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent).length;
  const rejected = await owner.issue({ operation: 'task.create', name: 'denied', instruction: 'denied' });
  assert.equal(rejected.command.reason, 'TASK_CONTROL_UNSUPPORTED');
  assert.equal(fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent).length, beforeMutations);
});

test('disconnect and reconnect preserve Task truth but never replay a command or create a Task', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await owner.refresh(sessionId);
  owner.disconnect();
  assert.equal(owner.snapshot().status, 'disconnected');
  assert.equal(owner.snapshot().command, null);

  const reconnected = await owner.refresh(sessionId);
  assert.equal(reconnected.selected_task_id, 'task-b');
  assert.equal(reconnected.tasks.length, 2);
  assert.equal(fixture.calls.filter(call => call.method === FORMAL_P3_TASK_METHODS.intent).length, 0);
});

test('wrong-session authority fails closed before control and leaves the prior snapshot without false Task truth', async () => {
  const fixture = authoritativeFixture();
  let calls = 0;
  const owner = new FormalP3TaskExperienceOwner({
    enabled: true,
    store: fixture.store,
    request: async (_method, _params, requestId) => {
      calls += 1;
      return envelope(requestId, {
        tasks: [{ ...fixture.taskA, scope: { ...scope, session_id: 'session-foreign' } }],
        cursor: null,
        next_cursor: null,
        has_more: false,
        limit: 100,
      });
    },
  });

  await assert.rejects(owner.refresh(sessionId), /Session binding mismatch/);
  assert.equal(owner.snapshot().status, 'failed');
  assert.equal(owner.snapshot().tasks.length, 0);
  assert.equal(calls, 1);
});

test('feature-off rejects refresh and allocates zero transport or business effects', async () => {
  let calls = 0;
  const owner = new FormalP3TaskExperienceOwner({
    enabled: false,
    request: async () => {
      calls += 1;
      throw new Error('must not run');
    },
  });
  await assert.rejects(owner.refresh(sessionId), /disabled/);
  assert.equal(owner.snapshot().status, 'disabled');
  assert.equal(calls, 0);
});
