import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FORMAL_P3_TASK_METHODS,
  FormalP3TaskExperienceOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/tasks/formalP3TaskExperience.js';

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
          ['adjust.task-checkpoint', 'v1'],
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
    causation_id: seq === 0 ? `${task.task_id}:cause:${seq}` : `${task.task_id}:source:${seq}`,
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

function terminalProgress(task) {
  const sourceId = `${task.task_id}:event:2`;
  return {
    session_id: sessionId, project_id: scope.project_id, correlation_id: task.correlation_id,
    task_id: task.task_id, attempt_id: task.attempt_id, state: 'terminal',
    source_event: { event_id: sourceId, seq: 2, event_type: 'task.terminal',
      payload: { state: 'terminal', outcome: 'completed' },
      raw: { extensions: { 'jiuwenswarm.task_progress_return': { persistent_event_producer: 'task_core' } } } },
    progress_event: { event_id: `${task.task_id}:progress:2`, causation_id: sourceId,
      payload: { state: 'terminal', outcome: 'completed' } },
  };
}

function terminalHistory(task, id, afterSeq = -1) {
  return envelope(id, { task_id: task.task_id, after_seq: afterSeq, head_seq: 2,
    events: [event(task, 0, 'task.accepted', 'accepted'), event(task, 1, 'task.running', 'running'),
      event(task, 2, 'task.terminal', 'terminal', 'completed')], has_more: false, next_after_seq: null });
}

test('shared progress advances background B without selecting it and withdraws unproved operations/results', async () => {
  const fixture = authoritativeFixture();
  let terminal = false;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
    request: (method, params, id) => terminal && method === FORMAL_P3_TASK_METHODS.events && params.task_id === 'task-b'
      ? Promise.resolve(terminalHistory(fixture.taskB, id)) : fixture.request(method, params, id) });
  await owner.refresh(sessionId);
  await owner.readTaskFacts(sessionId, 'task-b');
  terminal = true;
  await owner.reconcileProgress(terminalProgress(fixture.taskB), () => true);
  const snapshot = owner.snapshot();
  assert.equal(snapshot.selected_task_id, 'task-a');
  assert.equal(owner.taskObservation(sessionId, 'task-b').tasks[0].state, 'terminal');
  const taskB = snapshot.tasks.find(task => task.task_id === 'task-b');
  assert.equal(taskB.outcome, 'completed');
  assert.deepEqual(taskB.available_operations, []);
  assert.equal(taskB.result_availability, null);
  assert.equal(taskB.result_text, null);
  assert.equal(fixture.store.getItem(`jiuwenswarm.live_voice.formal_p3_selection.v1:${encodeURIComponent(sessionId)}`), 'task-a');
  assert.equal(fixture.calls.filter(call => [FORMAL_P3_TASK_METHODS.intent, FORMAL_P3_TASK_METHODS.confirmation, FORMAL_P3_TASK_METHODS.mutate].includes(call.method)).length, 0);
});

for (const fault of ['producer', 'scope', 'same-head', 'retired-consumer']) {
  test(`shared progress ${fault} rejects without changing Task facts, selection or receipts`, async () => {
    const fixture = authoritativeFixture();
    let corrupt = false;
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
      request: async (method, params, id) => {
        const reply = await fixture.request(method, params, id);
        if (corrupt && method === FORMAL_P3_TASK_METHODS.events && params.task_id === 'task-b') {
          reply.result.events[1].event_id = 'forged-same-head-event';
        }
        return reply;
      } });
    await owner.refresh(sessionId);
    await owner.readTaskFacts(sessionId, 'task-b');
    const before = owner.taskObservation(sessionId, 'task-b');
    const beforeUi = owner.snapshot();
    const delivery = terminalProgress(fixture.taskB);
    if (fault === 'producer') delivery.source_event.raw.extensions['jiuwenswarm.task_progress_return'].persistent_event_producer = 'forged';
    if (fault === 'scope') delivery.project_id = 'other-project';
    corrupt = fault === 'same-head';
    if (corrupt) {
      delivery.state = 'running';
      Object.assign(delivery.source_event, { event_id: 'forged-same-head-event', seq: 1, event_type: 'task.running',
        payload: { state: 'running', outcome: null } });
      Object.assign(delivery.progress_event, { causation_id: 'forged-same-head-event', payload: { state: 'running', outcome: null } });
    }
    await assert.rejects(owner.reconcileProgress(delivery, () => fault !== 'retired-consumer'));
    assert.deepEqual(owner.taskObservation(sessionId, 'task-b'), before);
    assert.equal(owner.snapshot(), beforeUi);
    assert.equal(owner.taskObservation(sessionId, 'task-b').connected, true);
    assert.equal(fixture.calls.filter(call => /ack|mutate|intent/.test(call.method)).length, 0);
  });
}

test('result arriving after a shared progress commit cannot restore the old Task revision', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  let holdResult = false;
  let terminal = false;
  let release;
  const resultStarted = new Promise(resolve => { release = resolve; });
  let finishResult;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
    request: async (method, params, id) => {
      if (terminal && method === FORMAL_P3_TASK_METHODS.events) return terminalHistory(fixture.taskB, id);
      const reply = await fixture.request(method, params, id);
      if (holdResult && method === FORMAL_P3_TASK_METHODS.result) {
        release();
        return new Promise(resolve => { finishResult = () => resolve(reply); });
      }
      return reply;
    } });
  await owner.refresh(sessionId);
  holdResult = true;
  const selection = owner.select('task-b');
  const rejectedSelection = assert.rejects(selection, /result revision became stale/);
  await resultStarted;
  terminal = true;
  await owner.reconcileProgress(terminalProgress(fixture.taskB), () => true);
  finishResult();
  await rejectedSelection;
  assert.equal(owner.taskObservation(sessionId, 'task-b').tasks[0].outcome, 'completed');
  assert.equal(owner.snapshot().tasks.find(task => task.task_id === 'task-b').outcome, 'completed');
  assert.deepEqual(owner.snapshot().tasks.find(task => task.task_id === 'task-b').available_operations, []);
});

for (const delayed of ['result', 'list']) {
  test(`late A ${delayed} preserves B progress and cannot restore B operations`, async () => {
    const fixture = authoritativeFixture();
    let hold = false;
    let terminal = false;
    let started;
    const waiting = new Promise(resolve => { started = resolve; });
    let finish;
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
      request: async (method, params, id) => {
        if (terminal && method === FORMAL_P3_TASK_METHODS.events && params.task_id === 'task-b') return terminalHistory(fixture.taskB, id);
        const reply = await fixture.request(method, params, id);
        if (hold && method === FORMAL_P3_TASK_METHODS[delayed]) {
          hold = false;
          const old = structuredClone(reply);
          started();
          return new Promise(resolve => { finish = () => resolve(old); });
        }
        return reply;
      } });
    await owner.refresh(sessionId);
    await owner.readTaskFacts(sessionId, 'task-b');
    hold = true;
    const flight = delayed === 'list' ? owner.refresh(sessionId) : owner.select('task-a');
    await waiting;
    terminal = true;
    await owner.reconcileProgress(terminalProgress(fixture.taskB), () => true);
    finish();
    await flight;
    const b = owner.snapshot().tasks.find(task => task.task_id === 'task-b');
    assert.equal(owner.snapshot().selected_task_id, 'task-a');
    assert.equal(b.outcome, 'completed');
    assert.equal(b.event_head, 2);
    assert.deepEqual(b.available_operations, []);
    assert.equal(b.result_text, null);
  });
}

for (const fault of ['receipt-reuse', 'causation']) {
  test(`progress ${fault} cannot partially commit history before rejecting its receipt`, async () => {
    const fixture = authoritativeFixture({ selectedHint: 'task-b' });
    let terminal = false;
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
      request: (method, params, id) => terminal && method === FORMAL_P3_TASK_METHODS.events
        ? Promise.resolve(terminalHistory(fixture.taskB, id)) : fixture.request(method, params, id) });
    await owner.refresh(sessionId);
    const delivery = terminalProgress(fixture.taskB);
    if (fault === 'receipt-reuse') {
      const running = structuredClone(delivery);
      running.state = 'running';
      Object.assign(running.source_event, { seq: 1, event_id: 'task-b:event:1', event_type: 'task.running', payload: { state: 'running', outcome: null } });
      Object.assign(running.progress_event, { causation_id: 'task-b:event:1', payload: { state: 'running', outcome: null } });
      await owner.reconcileProgress(running, () => true);
    } else delivery.progress_event.causation_id = 'wrong-source';
    const before = owner.taskObservation(sessionId, 'task-b');
    const ui = owner.snapshot();
    terminal = true;
    await assert.rejects(owner.reconcileProgress(delivery, () => true), /receipt conflicts|origin binding mismatch/);
    assert.deepEqual(owner.taskObservation(sessionId, 'task-b'), before);
    assert.equal(owner.snapshot(), ui);
  });
}

test('historical scope hint is checked before any event read or shared fact adoption', async () => {
  const fixture = authoritativeFixture();
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await assert.rejects(owner.readTaskFacts(sessionId, 'task-b', () => true, {
    ...scope, correlation_id: 'wrong-correlation', generation: 7,
  }), /task-control binding mismatch/);
  assert.equal(owner.taskObservation(sessionId, 'task-b'), null);
  assert.equal(fixture.calls.length, 1);
  assert.equal(fixture.calls[0].method, FORMAL_P3_TASK_METHODS.status);
});

test('the shared reader retains a server dirty-worktree retry rejection without manufacturing eligibility', async () => {
  const fixture = authoritativeFixture();
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
    request: async (method, params, id) => {
      const reply = await fixture.request(method, params, id);
      if (method === FORMAL_P3_TASK_METHODS.status) {
        reply.result.retry_admission = { eligible: false, reason: 'TASK_CONTEXT_WORKTREE_DIRTY',
          task_id: params.task_id, attempt_id: null, attempt_number: null };
      }
      return reply;
    } });
  const facts = await owner.readTaskFacts(sessionId, 'task-a');
  assert.equal(facts.status_response.result.retry_admission.eligible, false);
  assert.equal(facts.status_response.result.retry_admission.reason, 'TASK_CONTEXT_WORKTREE_DIRTY');
  assert.equal(owner.taskObservation(sessionId, 'task-a').tasks[0].outcome, 'completed');
  assert.equal(fixture.calls.filter(call => /intent|mutate/.test(call.method)).length, 0);
});

for (const retirement of [null, 'voice', 'session']) {
  test(`per-Task updates serialize without blocking A selection; retirement=${retirement}`, async () => {
    const fixture = authoritativeFixture();
    let holding = false;
    let started;
    const statusStarted = new Promise(resolve => { started = resolve; });
    let finishStatus;
    let laterHistoryCalls = 0;
    let voiceCurrent = true;
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
      request: async (method, params, id) => {
        const reply = await fixture.request(method, params, id);
        if (holding && params.task_id === 'task-b') {
          if (method === FORMAL_P3_TASK_METHODS.status) {
            started();
            return new Promise(resolve => { finishStatus = () => resolve(reply); });
          }
          if (method === FORMAL_P3_TASK_METHODS.events && ++laterHistoryCalls === 2) return terminalHistory(fixture.taskB, id);
        }
        return reply;
      } });
    await owner.refresh(sessionId);
    await owner.readTaskFacts(sessionId, 'task-b');
    holding = true;
    const reading = owner.readTaskFacts(sessionId, 'task-b');
    await statusStarted;
    const reconciling = owner.reconcileProgress(terminalProgress(fixture.taskB), () => voiceCurrent);
    const readOutcome = retirement === 'session' ? assert.rejects(reading, /stale/) : reading;
    const progressOutcome = retirement === null ? reconciling : assert.rejects(reconciling, /stale/);
    await owner.select('task-a');
    assert.equal(owner.snapshot().selected_task_id, 'task-a');
    assert.equal(laterHistoryCalls, 0);
    if (retirement === 'voice') voiceCurrent = false;
    if (retirement === 'session') owner.disconnect();
    finishStatus();
    await readOutcome;
    await progressOutcome;
    if (retirement === 'session') {
      assert.equal(owner.taskObservation(sessionId, 'task-b'), null);
      assert.equal(laterHistoryCalls, 0);
    } else {
      assert.equal(owner.taskObservation(sessionId, 'task-b').connected, true);
      assert.equal(owner.taskObservation(sessionId, 'task-b').tasks[0].state, retirement === null ? 'terminal' : 'running');
      assert.equal(laterHistoryCalls, retirement === null ? 2 : 1);
    }
  });
}

test('same-head status/history disagreement leaves no shared Task observation', async () => {
  const fixture = authoritativeFixture();
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
    request: async (method, params, id) => {
      const reply = await fixture.request(method, params, id);
      if (method === FORMAL_P3_TASK_METHODS.events) reply.result.events[1].outcome = 'cancelled';
      return reply;
    } });
  await assert.rejects(owner.readTaskFacts(sessionId, 'task-a'), /current Attempt mismatch/);
  assert.equal(owner.taskObservation(sessionId, 'task-a'), null);
  assert.equal(owner.snapshot().selected_task_id, null);
  assert.equal(fixture.calls.filter(call => /result|intent|mutate/.test(call.method)).length, 0);
});

test('shared Task history preserves the existing paginated UI capacity beyond 256 events', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  fixture.taskB.event_head = 300;
  const history = Array.from({ length: 301 }, (_, seq) => event(fixture.taskB, seq,
    seq === 0 ? 'task.accepted' : 'task.running', seq === 0 ? 'accepted' : 'running'));
  const cursors = [];
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
    request: async (method, params, id) => {
      if (method !== FORMAL_P3_TASK_METHODS.events) return fixture.request(method, params, id);
      cursors.push(params.after_seq);
      const page = history.slice(params.after_seq + 1, params.after_seq + 151);
      const next = page.at(-1).seq < 300 ? page.at(-1).seq : null;
      return envelope(id, { task_id: 'task-b', after_seq: params.after_seq, head_seq: 300,
        events: page, has_more: next !== null, next_after_seq: next });
    } });
  await owner.refresh(sessionId);
  assert.deepEqual(cursors, [-1, 149, 299]);
  assert.equal(owner.taskObservation(sessionId, 'task-b').tasks[0].last_event_seq, 300);
  assert.equal(owner.snapshot().tasks.find(task => task.task_id === 'task-b').replay_event_count, 301);
});

test('background Task reads share one flight without selecting or invalidating another Task', async () => {
  const fixture = authoritativeFixture();
  let release;
  let pause = false;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store, request: async (...args) => {
    const result = await fixture.request(...args);
    if (pause && args[0] === FORMAL_P3_TASK_METHODS.status && args[1].task_id === 'task-a') {
      await new Promise(resolve => { release = resolve; });
    }
    return result;
  } });
  await owner.refresh(sessionId);
  pause = true;
  const before = fixture.calls.length;
  let voiceCurrent = true;
  const retired = owner.readTaskFacts(sessionId, 'task-a', () => voiceCurrent);
  const retained = owner.readTaskFacts(sessionId, 'task-a');
  const rejected = assert.rejects(retired, /stale/);
  await owner.select('task-b');
  const snapshot = owner.snapshot();
  const storage = [...fixture.store.values];
  voiceCurrent = false;
  release();
  await rejected;
  const facts = await retained;
  assert.equal(facts.task.task_id, 'task-a');
  assert.equal(facts.task.replay_event_count, 2);
  assert.equal(owner.snapshot(), snapshot);
  assert.deepEqual([...fixture.store.values], storage);
  assert.equal(snapshot.selected_task_id, 'task-b');
  const reads = fixture.calls.slice(before).filter(call => call.params.task_id === 'task-a');
  assert.deepEqual(reads.map(call => call.method), [FORMAL_P3_TASK_METHODS.status, FORMAL_P3_TASK_METHODS.events]);
});

test('Task advancement between status and history requires a fresh read without publishing mixed facts', async () => {
  const fixture = authoritativeFixture();
  let advance = false;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store, request: async (...args) => {
    const response = await fixture.request(...args);
    if (advance && args[0] === FORMAL_P3_TASK_METHODS.events) {
      advance = false;
      return { ...response, result: { ...response.result, head_seq: response.result.head_seq + 1 } };
    }
    return response;
  } });
  await owner.refresh(sessionId);
  const snapshot = owner.snapshot();
  const before = fixture.calls.length;
  advance = true;
  await assert.rejects(owner.readTaskFacts(sessionId, 'task-b'), error => error.reason === 'PRODUCTION_TASK_AUTHORITY_PROJECTION_MISMATCH');
  assert.equal(owner.snapshot(), snapshot);
  assert.equal((await owner.readTaskFacts(sessionId, 'task-b')).task.task_id, 'task-b');
  assert.deepEqual(fixture.calls.slice(before).map(call => call.method), [
    FORMAL_P3_TASK_METHODS.status, FORMAL_P3_TASK_METHODS.events,
    FORMAL_P3_TASK_METHODS.status, FORMAL_P3_TASK_METHODS.events,
  ]);
});

for (const retirement of ['caller', 'disconnect', 'session']) test(`background Task read stops before history after ${retirement} retirement`, async () => {
  const fixture = authoritativeFixture();
  let release;
  let pause = false;
  let current = true;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store, request: async (...args) => {
    if (args[1].session_id !== sessionId) return envelope(args[2], { tasks: [], has_more: false, next_cursor: null });
    const result = await fixture.request(...args);
    if (pause && args[0] === FORMAL_P3_TASK_METHODS.status) await new Promise(resolve => { release = resolve; });
    return result;
  } });
  await owner.refresh(sessionId);
  pause = true;
  const before = fixture.calls.length;
  const reading = owner.readTaskFacts(sessionId, 'task-b', () => current);
  const rejected = assert.rejects(reading, /stale/);
  await Promise.resolve();
  if (retirement === 'caller') current = false;
  else if (retirement === 'disconnect') owner.disconnect();
  else await owner.refresh('other-session');
  release();
  await rejected;
  assert.deepEqual(fixture.calls.slice(before).map(call => call.method), [FORMAL_P3_TASK_METHODS.status]);
});

test('live Task refresh converges without a voice notification and stops reading when all Tasks are terminal', async () => {
  const fixture = authoritativeFixture();
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await owner.refresh(sessionId);
  assert.equal(owner.snapshot().tasks.find(task => task.task_id === 'task-b').canonical_state, 'running');
  fixture.taskB.state = 'terminal';
  fixture.taskB.outcome = 'completed';
  const settled = await owner.refreshLiveTasks(sessionId);
  assert.equal(settled.tasks.find(task => task.task_id === 'task-b').display_state, 'completed');
  assert.equal(settled.selected_task_id, 'task-a');
  const readCount = fixture.calls.length;
  await owner.refreshLiveTasks(sessionId);
  assert.equal(fixture.calls.length, readCount);
  assert.equal(fixture.calls.some(call => [FORMAL_P3_TASK_METHODS.intent, FORMAL_P3_TASK_METHODS.confirmation, FORMAL_P3_TASK_METHODS.mutate].includes(call.method)), false);
});

test('live Task refresh retries a read failure without losing the need to settle its formerly running Task', async () => {
  const fixture = authoritativeFixture();
  let fail = false;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store, request: async (...args) => {
    if (fail) throw new Error('read unavailable');
    return fixture.request(...args);
  } });
  await owner.refresh(sessionId);
  fail = true;
  await assert.rejects(owner.refreshLiveTasks(sessionId), /read unavailable/);
  assert.equal(owner.snapshot().status, 'failed');
  fail = false;
  fixture.taskB.state = 'terminal';
  fixture.taskB.outcome = 'completed';
  const recovered = await owner.refreshLiveTasks(sessionId);
  assert.equal(recovered.status, 'ready');
  assert.equal(recovered.tasks.find(task => task.task_id === 'task-b').outcome, 'completed');
});

test('live Task fallback cannot cross Session, closed/disconnected ownership or an unresolved command', async () => {
  for (const condition of ['wrong-session', 'stale', 'closed', 'disconnected', 'confirmation']) {
    const fixture = authoritativeFixture();
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
    await owner.refresh(sessionId);
    if (condition === 'closed') owner.close();
    if (condition === 'disconnected') owner.disconnect();
    if (condition === 'confirmation') {
      await owner.select('task-b');
      await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'Keep the afternoon free' });
    }
    const before = owner.snapshot();
    const readCount = fixture.calls.length;
    await owner.refreshLiveTasks(condition === 'wrong-session' ? 'another-session' : sessionId, () => condition !== 'stale');
    assert.equal(fixture.calls.length, readCount, condition);
    assert.equal(owner.snapshot(), before, condition);
  }
});

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

test('definitive confirmation rejection is exact and unlocks later Task controls', async () => {
  const fixture = authoritativeFixture({
    selectedHint: 'task-b',
    taskBOperations: ['task.adjust', 'task.cancel', 'task.status'],
  });
  let intentCalls = 0;
  const request = async (method, params, id) => {
    if (method !== FORMAL_P3_TASK_METHODS.intent) return fixture.request(method, params, id);
    intentCalls += 1;
    if (intentCalls === 1) return fixture.request(method, params, id);
    if (intentCalls === 2) {
      throw Object.assign(new Error('production Task intent failed closed'), {
        requestId: id,
        code: 'CONFLICT',
        retriable: false,
        reason: 'TASK_AUTHORITY_CHANGED',
        payload: { error: { reason: 'TASK_AUTHORITY_CHANGED' } },
      });
    }
    return envelope(id, {
      status: 'clarification',
      reason: 'TASK_CONFIRMATION_REQUIRED',
      operation: 'task.cancel',
      task_id: 'task-b',
      confirmation_token: 'confirmation-cancel-after-rejection',
      confirmation_form: 'confirm task request confirmation-cancel-after-rejection',
      partial_command_count: 0,
    });
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });

  await assert.rejects(owner.confirm(), /TASK_AUTHORITY_CHANGED/);
  const rejected = owner.snapshot();
  assert.equal(rejected.status, 'ready');
  assert.equal(rejected.command.phase, 'rejected');
  assert.equal(rejected.command.accepted, false);
  assert.equal(rejected.command.applied, false);
  assert.equal(rejected.command.reason, 'TASK_AUTHORITY_CHANGED');

  const next = await owner.issue({ operation: 'task.cancel', task_id: 'task-b' });
  assert.equal(next.command.phase, 'confirmation_required');
});

test('transport-unknown confirmation outcome remains locked for safe recovery', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  let intentCalls = 0;
  const request = async (method, params, id) => {
    if (method !== FORMAL_P3_TASK_METHODS.intent) return fixture.request(method, params, id);
    intentCalls += 1;
    if (intentCalls === 1) return fixture.request(method, params, id);
    throw Object.assign(new Error('request timed out'), {
      requestId: id,
      retriable: true,
    });
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });

  await assert.rejects(owner.confirm(), /request timed out/);
  assert.equal(owner.snapshot().command.phase, 'unknown');
  const count = fixture.calls.length;
  await assert.rejects(owner.issue({ operation: 'task.cancel', task_id: 'task-b' }), /unavailable/);
  assert.equal(fixture.calls.length, count);
});

for (const lostStage of ['issue', 'confirm']) {
  test(`structured ${lostStage} response loss recovers the identical RPC with one effect`, async () => {
    const fixture = authoritativeFixture({ selectedHint: 'task-b' });
    const wire = [];
    const replies = new Map();
    let lost = false;
    const request = async (method, params, id) => {
      wire.push({ method, params: structuredClone(params), id });
      if (replies.has(id)) return replies.get(id);
      const reply = await fixture.request(method, params, id);
      if (method === FORMAL_P3_TASK_METHODS.intent) {
        replies.set(id, reply);
        if (!lost && Boolean(params.continuation_id) === (lostStage === 'confirm')) {
          lost = true;
          throw new Error('response lost after server effect');
        }
      }
      return reply;
    };
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
    await owner.refresh(sessionId);
    const issue = () => owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
    if (lostStage === 'issue') await assert.rejects(issue(), /response lost/);
    else { await issue(); await assert.rejects(owner.confirm(), /response lost/); }
    assert.equal(owner.snapshot().command.phase, 'unknown');
    const before = wire.length;
    await assert.rejects(owner.issue({ operation: 'task.cancel', task_id: 'task-b' }), /unavailable/);
    assert.equal(wire.length, before);
    owner.disconnect();
    await owner.refresh(sessionId);
    const replay = await owner.confirm();
    assert.equal(replay.command.phase, lostStage === 'issue' ? 'confirmation_required' : 'applied');
    const intents = wire.filter(item => item.method === FORMAL_P3_TASK_METHODS.intent);
    assert.deepEqual(intents.at(-1), intents.at(-2));
    if (lostStage === 'issue') await owner.confirm();
    assert.equal(fixture.calls.filter(item => item.method === FORMAL_P3_TASK_METHODS.intent).length, 2);
  });
}

for (const malformedReason of [false, true]) {
test(`malformed mutation receipt remains unknown and cannot unlock another issue (reason=${malformedReason})`, async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  let original;
  const wire = [];
  const request = async (method, params, id) => {
    wire.push({ method, params, id });
    if (method === FORMAL_P3_TASK_METHODS.intent && params.continuation_id) {
      if (original) { assert.equal(id, original.request_id); return original; }
      original = await fixture.request(method, params, id);
      return malformedReason
        ? { ...original, result: { ...original.result, formal_task_result: { ...original.result.formal_task_result, reason: {} } } }
        : envelope(id, { status: 'dispatched', operation: 'task.adjust', task_id: 'task-b' });
    }
    return fixture.request(method, params, id);
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  await assert.rejects(owner.confirm(), malformedReason ? /invalid/ : /missing/);
  const count = wire.length;
  await assert.rejects(owner.issue({ operation: 'task.cancel', task_id: 'task-b' }), /unavailable/);
  assert.equal(wire.length, count);
  assert.equal((await owner.confirm()).command.phase, 'applied');
});
}

test('late same-session selection preserves a newly issued confirmation', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  let releaseIssue, enteredIssue, releaseSelection, enteredSelection;
  const issueGate = new Promise(resolve => { releaseIssue = resolve; });
  const issueStarted = new Promise(resolve => { enteredIssue = resolve; });
  const selectionGate = new Promise(resolve => { releaseSelection = resolve; });
  const selectionStarted = new Promise(resolve => { enteredSelection = resolve; });
  let holdSelection = false;
  const request = async (method, params, id) => {
    const reply = await fixture.request(method, params, id);
    if (method === FORMAL_P3_TASK_METHODS.intent && !params.continuation_id) {
      holdSelection = true; enteredIssue(); await issueGate;
    }
    if (method === FORMAL_P3_TASK_METHODS.result && holdSelection) {
      holdSelection = false; enteredSelection(); await selectionGate;
    }
    return reply;
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  const issue = owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  await issueStarted;
  const select = owner.select('task-b');
  await selectionStarted;
  releaseIssue(); await issue;
  assert.equal(owner.snapshot().command.phase, 'confirmation_required');
  releaseSelection(); await select;
  assert.equal(owner.snapshot().command.phase, 'confirmation_required');
  await owner.confirm();
  assert.equal(owner.snapshot().command.phase, 'applied');
  assert.equal(fixture.calls.filter(item => item.method === FORMAL_P3_TASK_METHODS.intent).length, 2);
});

test('unknown retry recovers original RPC even after the real Attempt has advanced', async () => {
  const fixture = authoritativeFixture();
  const mutations = [];
  let reply;
  const request = async (method, params, id) => {
    if (method === FORMAL_P3_TASK_METHODS.confirmation) return envelope(id, {
      status: 'confirmation_issued', confirmation_id: 'retry-bound-confirmation',
      operation: 'task.retry', command_id: params.command_id, target_task_id: 'task-a',
    });
    if (method === FORMAL_P3_TASK_METHODS.mutate) {
      mutations.push({ params: structuredClone(params), id });
      if (reply) return reply;
      fixture.taskA.attempt_id = 'attempt-a-new';
      reply = envelope(id, { status: 'mutation_processed', operation: 'task.retry',
        command_id: params.command_id, target_task_id: 'task-a', formal_task_result: {
          task_id: 'task-a', attempt_id: 'attempt-a-new', state: 'accepted',
        } });
      throw new Error('retry response lost');
    }
    return fixture.request(method, params, id);
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.retry', task_id: 'task-a' });
  await assert.rejects(owner.confirm(), /response lost/);
  owner.disconnect(); await owner.refresh(sessionId);
  await owner.confirm();
  assert.deepEqual(mutations[1], mutations[0]);
  assert.equal(owner.snapshot().command.accepted, true);
  assert.equal(owner.snapshot().tasks.find(task => task.task_id === 'task-a').attempt_id, 'attempt-a-new');
});

test('RESULT_UNKNOWN error envelope is not a definitive rejection even with retriable false', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const request = async (method, params, id) => {
    if (method === FORMAL_P3_TASK_METHODS.intent && params.continuation_id) {
      return { request_id: id, ok: false, result: null,
        error: { code: 'RESULT_UNKNOWN', reason: 'TASK_RESULT_UNKNOWN', retriable: false } };
    }
    return fixture.request(method, params, id);
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  await assert.rejects(owner.confirm(), /TASK_RESULT_UNKNOWN/);
  assert.equal(owner.snapshot().command.phase, 'unknown');
  const count = fixture.calls.length;
  await assert.rejects(owner.issue({ operation: 'task.cancel', task_id: 'task-b' }), /unavailable/);
  assert.equal(fixture.calls.length, count);
});

test('late disconnected confirmation never projects a result or queries until exact recovery', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  let release, entered;
  const started = new Promise(resolve => { entered = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  let saved;
  const request = async (method, params, id) => {
    if (method === FORMAL_P3_TASK_METHODS.intent && params.continuation_id) {
      if (saved) { assert.equal(saved.request_id, id); return saved; }
      saved = await fixture.request(method, params, id);
      entered();
      await gate;
      return saved;
    }
    return fixture.request(method, params, id);
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  const pending = owner.confirm();
  await started;
  owner.disconnect();
  await owner.refresh(sessionId);
  const before = fixture.calls.length;
  release();
  await assert.rejects(pending, /stale/);
  assert.equal(fixture.calls.length, before);
  assert.equal(owner.snapshot().command.phase, 'unknown');
  assert.equal((await owner.confirm()).command.phase, 'applied');
});

for (const definitive of [false, true]) {
test(`known mutation followed by failed detail query recovers reads only (definitive=${definitive})`, async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  let effect = false, failed = false;
  const request = async (method, params, id) => {
    if (method === FORMAL_P3_TASK_METHODS.list && effect && !failed) {
      failed = true;
      if (definitive) return envelope(id, { reason: 'TASK_READ_PERMISSION_CHANGED' }, false);
      throw new Error('detail unavailable');
    }
    const reply = await fixture.request(method, params, id);
    if (method === FORMAL_P3_TASK_METHODS.intent && params.continuation_id) effect = true;
    return reply;
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  await assert.rejects(owner.confirm(), definitive ? /TASK_READ_PERMISSION_CHANGED/ : /detail unavailable/);
  assert.equal(owner.snapshot().command.accepted, true);
  assert.equal(owner.snapshot().command.phase, 'applied');
  await owner.confirm();
  assert.equal(owner.snapshot().status, 'ready');
  assert.equal(fixture.calls.filter(item => item.method === FORMAL_P3_TASK_METHODS.intent).length, 2);
});
}

test('concurrent issue is fenced before any query and duplicate confirm joins one RPC', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request: fixture.request, store: fixture.store });
  await owner.refresh(sessionId);
  const first = owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  await assert.rejects(owner.issue({ operation: 'task.cancel', task_id: 'task-b' }), /unavailable/);
  await first;
  const confirm = owner.confirm();
  assert.equal(owner.confirm(), confirm);
  await confirm;
  assert.equal(fixture.calls.filter(item => item.method === FORMAL_P3_TASK_METHODS.intent).length, 2);
});

test('ordinary event advancement does not invalidate exact confirmation', async () => {
  const fixture = authoritativeFixture({ selectedHint: 'task-b' });
  const request = async (method, params, id) => {
    const reply = await fixture.request(method, params, id);
    if (method === FORMAL_P3_TASK_METHODS.events && params.task_id === 'task-b' && fixture.taskB.event_head === 2) {
      reply.result.events.push(event(fixture.taskB, 2, 'task.running', 'running', null, { progress: 'next checkpoint' }));
    }
    return reply;
  };
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
  await owner.refresh(sessionId);
  await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
  fixture.taskB.event_head = 2;
  assert.equal((await owner.confirm()).command.phase, 'applied');
});

for (const field of ['attempt_id', 'revision']) {
  test(`first confirmation rejects changed ${field} before mutation`, async () => {
    const fixture = authoritativeFixture({ selectedHint: 'task-b' });
    const predecessor = { ...fixture.taskB };
    const request = async (method, params, id) => {
      const reply = await fixture.request(method, params, id);
      if (params.task_id === 'task-b' && fixture.taskB.attempt_id === 'attempt-successor') {
        if (method === FORMAL_P3_TASK_METHODS.status) reply.result.attempt.attempt_number = 2;
        if (method === FORMAL_P3_TASK_METHODS.events) reply.result.events = [
          event(predecessor, 0, 'task.accepted', 'accepted'),
          event(predecessor, 1, 'task.running', 'running'),
          event(predecessor, 2, 'task.terminal', 'terminal', 'completed'),
          { ...event(fixture.taskB, 3, 'task.retry_accepted', 'accepted'), source_event_id: null,
            causation_id: 'retry-b', details: { command_id: 'retry-b', retry_of_attempt_id: predecessor.attempt_id,
              previous_outcome: 'completed', attempt_number: 2 } },
          event(fixture.taskB, 4, 'task.running', 'running'),
        ];
      }
      return reply;
    };
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
    await owner.refresh(sessionId);
    await owner.issue({ operation: 'task.adjust', task_id: 'task-b', adjustment: 'advance checkpoint' });
    if (field === 'attempt_id') {
      fixture.taskB.attempt_id = 'attempt-successor';
      fixture.taskB.admission.attempt_id = 'attempt-successor';
      fixture.taskB.event_head = 4;
    }
    else fixture.taskB.revision.number += 1;
    await assert.rejects(owner.confirm(), /CONFIRMATION_STALE/);
    assert.equal(owner.snapshot().command.phase, 'rejected');
    assert.equal(fixture.calls.filter(item => item.method === FORMAL_P3_TASK_METHODS.intent).length, 1);
  });
}

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

for (const stage of ['issue', 'confirm']) for (const field of ['operation', 'command_id', 'target_task_id']) {
  test(`shared retry rejects a forged ${stage} ${field} and retains only its exact RPC`, async () => {
    const fixture = authoritativeFixture();
    const mutationCalls = [];
    const request = async (method, params, id) => {
      if (![FORMAL_P3_TASK_METHODS.confirmation, FORMAL_P3_TASK_METHODS.mutate].includes(method)) return fixture.request(method, params, id);
      mutationCalls.push({ method, params, id });
      const issuing = method === FORMAL_P3_TASK_METHODS.confirmation;
      const result = {
        status: issuing ? 'confirmation_issued' : 'mutation_processed',
        operation: 'task.retry', command_id: params.command_id, target_task_id: 'task-a',
        confirmation_id: 'exact-retry',
        formal_task_result: { task_id: 'task-a', attempt_id: 'attempt-next', state: 'accepted', outbox_id: 'retry-outbox' },
      };
      if (issuing === (stage === 'issue')) result[field] = 'foreign-binding';
      return envelope(id, result);
    };
    const owner = new FormalP3TaskExperienceOwner({ enabled: true, request, store: fixture.store });
    await owner.refresh(sessionId);
    if (stage === 'issue') await assert.rejects(owner.issue({ operation: 'task.retry', task_id: 'task-a' }), /binding mismatch/);
    else {
      await owner.issue({ operation: 'task.retry', task_id: 'task-a' });
      await assert.rejects(owner.confirm(), /binding mismatch/);
    }
    assert.equal(owner.snapshot().command.phase, 'unknown');
    const last = mutationCalls.at(-1);
    await assert.rejects(owner.issue({ operation: 'task.cancel', task_id: 'task-b' }), /unavailable/);
    await assert.rejects(owner.confirm(), /binding mismatch/);
    assert.deepEqual(mutationCalls.at(-1), last);
    assert.equal(mutationCalls.filter(call => call.method === FORMAL_P3_TASK_METHODS.mutate).length, stage === 'issue' ? 0 : 2);
    assert.equal(owner.snapshot().command.accepted, false);
    assert.equal(owner.snapshot().tasks.find(task => task.task_id === 'task-a').attempt_id, 'attempt-a');
  });
}

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
    if (method !== FORMAL_P3_TASK_METHODS.events || params.task_id !== 'task-b') {
      const reply = await fixture.request(method, params, id);
      if (method === FORMAL_P3_TASK_METHODS.status && params.task_id === 'task-b') reply.result.attempt.attempt_number = 2;
      return reply;
    }
    fixture.calls.push({ method, params, requestId: id });
    return envelope(id, {
      task_id: 'task-b',
      after_seq: -1,
      events: [
        event(oldAttempt, 0, 'task.accepted', 'accepted', null, { progress: 'previous Attempt 1/2' }),
        event(oldAttempt, 1, 'task.terminal', 'terminal', 'completed', { progress: 'previous Attempt 2/2' }),
        { ...event(fixture.taskB, 2, 'task.retry_accepted', 'accepted'), source_event_id: null,
          causation_id: 'retry-b', details: { command_id: 'retry-b', retry_of_attempt_id: oldAttempt.attempt_id,
            previous_outcome: 'completed', attempt_number: 2 } },
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
  assert.deepEqual(selected.replay_event_types, ['task.accepted', 'task.terminal', 'task.retry_accepted', 'task.running']);
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


for (const suspended of ['list', 'status', 'events', 'result']) test(`retired activation during Task ${suspended} cannot publish, persist selection, or continue reads`, async () => {
  const fixture = authoritativeFixture();
  const calls = [], snapshots = [];
  let current = true, release;
  const owner = new FormalP3TaskExperienceOwner({ enabled: true, store: fixture.store,
    on_snapshot: snapshot => snapshots.push(snapshot),
    request: async (method, params, id) => {
      calls.push(method);
      if (method === FORMAL_P3_TASK_METHODS[suspended])
        return new Promise(resolve => { release = () => resolve(fixture.request(method, params, id)); });
      return fixture.request(method, params, id);
    } });
  const pending = owner.refresh(sessionId, () => current);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof release, 'function');
  current = false;
  const published = snapshots.length, requests = calls.length;
  const hint = JSON.stringify([...fixture.store.values]);
  release();
  await assert.rejects(pending, /became stale/);
  assert.equal(snapshots.length, published);
  assert.equal(calls.length, requests);
  assert.equal(JSON.stringify([...fixture.store.values]), hint);
  assert.equal(calls.some(method => /mutate|intent|confirmation/.test(method)), false);
});
