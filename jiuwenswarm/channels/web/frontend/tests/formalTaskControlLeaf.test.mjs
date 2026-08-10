import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FORMAL_TASK_CONTROL_LIMITS,
  FormalTaskControlLeaf,
  deriveFormalTaskQueryBinding,
  mapFormalTaskCancel,
  prepareFormalTaskMutation,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/formalTaskControlLeaf.js';

const binding = Object.freeze({
  subject_id: 'principal-1',
  session_id: 'session-1',
  project_id: 'project-1',
  correlation_id: 'correlation-1',
  generation: 1,
});

const scope = Object.freeze({
  subject_id: binding.subject_id,
  session_id: binding.session_id,
  project_id: binding.project_id,
  assurance: 'authenticated',
});

function task(overrides = {}) {
  return {
    task_id: overrides.task_id ?? 'task-1',
    scope: overrides.scope ?? { ...scope },
    attempt_id: overrides.attempt_id ?? 'attempt-1',
    correlation_id: overrides.correlation_id ?? binding.correlation_id,
    state: overrides.state ?? 'running',
    outcome: overrides.outcome ?? null,
    event_head: overrides.event_head ?? 1,
  };
}

function event(seq, overrides = {}) {
  const eventType = overrides.event_type ?? (
    seq === 0 ? 'task.accepted' : seq === 1 ? 'attempt.running' : seq === 2 ? 'task.running' : 'task.cancel_requested'
  );
  const sourceEventId = Object.hasOwn(overrides, 'source_event_id')
    ? overrides.source_event_id
    : seq === 0
      ? null
      : seq <= 2
        ? 'executor-source-1'
        : null;
  return {
    event_id: overrides.event_id ?? `task-1:event:${seq}`,
    task_id: overrides.task_id ?? 'task-1',
    attempt_id: overrides.attempt_id ?? 'attempt-1',
    scope: overrides.scope ?? { ...scope },
    seq,
    event_type: eventType,
    state: overrides.state ?? (seq === 0 ? 'accepted' : 'running'),
    outcome: overrides.outcome ?? null,
    producer: overrides.producer ?? (seq === 1 ? 'jiuwenswarm_code_agent.project_code' : seq >= 3 ? 'task_core.control' : 'task_core'),
    source_event_id: sourceEventId,
    causation_id: overrides.causation_id ?? (sourceEventId ?? `cause-${seq}`),
    correlation_id: overrides.correlation_id ?? binding.correlation_id,
    occurred_at: '2026-08-07T12:00:00Z',
    details: {},
  };
}

function confirmation(overrides = {}) {
  return {
    confirmation_id: overrides.confirmation_id ?? 'confirmation-1',
    operation: overrides.operation ?? 'task.create',
    command_id: overrides.command_id ?? 'command-1',
    target_task_id: overrides.target_task_id ?? null,
    expires_at: '2100-01-01T00:00:00Z',
  };
}

function adoption(leaf, { command_id = null, query_task_id = null, events_query = null, connection_generation } = {}) {
  return {
    connection_generation: connection_generation ?? leaf.snapshot().connection_generation,
    command_id,
    query_task_id,
    events_query,
  };
}

function runningPrefix() {
  return [event(0), event(1), event(2)];
}

function terminalEvents(outcome = 'completed') {
  return [
    ...runningPrefix(),
    event(3, {
      event_type: 'attempt.terminal', state: 'terminal', outcome,
      producer: 'jiuwenswarm_code_agent.project_code', source_event_id: 'executor-source-3', causation_id: 'executor-source-3',
    }),
    event(4, {
      event_type: 'task.terminal', state: 'terminal', outcome,
      producer: 'task_core', source_event_id: 'executor-source-3', causation_id: 'executor-source-3',
    }),
  ];
}

function eventsResult(events, headSeq, taskId, afterSeq) {
  return {
    events,
    head_seq: headSeq,
    task_id: taskId,
    after_seq: afterSeq,
  };
}

test('confirmation is exact and feature-off allocates zero mutation calls', async () => {
  const prepared = prepareFormalTaskMutation(binding, { operation: 'task.create', command_id: 'command-1', task_id: null }, confirmation());
  let calls = 0;
  const disabled = new FormalTaskControlLeaf({ enabled: false, binding });

  await assert.rejects(
    disabled.submitMutation(prepared, async () => {
      calls += 1;
    }),
    /disabled/
  );
  assert.equal(calls, 0);
  assert.throws(
    () =>
      prepareFormalTaskMutation(binding, { operation: 'task.create', command_id: 'command-1', task_id: null }, confirmation({ command_id: 'wrong-command' })),
    /confirmation binding mismatch/
  );
});

test('create get list status cancel and events retain authoritative task truth', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const prepared = prepareFormalTaskMutation(binding, { operation: 'task.create', command_id: 'command-1', task_id: null }, confirmation());
  let calls = 0;
  await leaf.submitMutation(prepared, async value => {
    calls += 1;
    assert.equal(value.confirmation.confirmation_id, 'confirmation-1');
    return { ok: true };
  });
  leaf.adopt('task.create', {
    status: 'mutation_processed',
    operation: 'task.create',
    formal_task_result: { command_id: 'command-1', task_id: 'task-1', attempt_id: 'attempt-1' },
  }, adoption(leaf, { command_id: 'command-1' }));
  assert.equal(leaf.snapshot().tasks[0].state, null);

  leaf.adopt('task.get', {
    ok: true,
    result: { task: task(), attempt: { task_id: 'task-1', attempt_id: 'attempt-1' } },
  }, adoption(leaf, { query_task_id: 'task-1' }));
  leaf.adopt('task.status', {
    ok: true,
    result: { task: task(), attempt: { task_id: 'task-1', attempt_id: 'attempt-1' } },
  }, adoption(leaf, { query_task_id: 'task-1' }));
  leaf.adopt('task.list', { ok: true, result: { tasks: [task()] } }, adoption(leaf));
  leaf.adopt(
    'task.events',
    {
      ok: true,
      result: eventsResult(runningPrefix(), 2, 'task-1', -1),
    },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  const cancelPrepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.cancel', command_id: 'command-cancel', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-cancel',
      operation: 'task.cancel',
      command_id: 'command-cancel',
      target_task_id: 'task-1',
    })
  );
  await leaf.submitMutation(cancelPrepared, async () => ({ ok: true }));
  leaf.adopt('task.cancel', {
    status: 'mutation_processed',
    operation: 'task.cancel',
    formal_task_result: { command_id: 'command-cancel', task_id: 'task-1', attempt_id: 'attempt-1' },
  }, adoption(leaf, { command_id: 'command-cancel' }));

  assert.equal(calls, 1);
  assert.equal(leaf.snapshot().tasks.length, 1);
  assert.equal(leaf.snapshot().tasks[0].last_event_id, 'task-1:event:2');
  assert.deepEqual(leaf.snapshot().mutation_receipts, ['command-1', 'command-cancel']);
  await assert.rejects(
    leaf.submitMutation(prepared, async () => {}),
    /already acknowledged/
  );
});

test('a created task takes its correlation from Task Core, never from the control binding', async () => {
  // Task Core owns the Task correlation and a mutation result does not echo
  // it. Inferring it from the local control binding made every later query
  // throw as soon as the two disagreed, and because task.list is all-or-
  // nothing that permanently broke the whole scope's list view.
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const prepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.create', command_id: 'command-1', task_id: null },
    confirmation()
  );
  await leaf.submitMutation(prepared, async () => ({ ok: true }));
  leaf.adopt('task.create', {
    status: 'mutation_processed',
    operation: 'task.create',
    formal_task_result: { command_id: 'command-1', task_id: 'task-1', attempt_id: 'attempt-1' },
  }, adoption(leaf, { command_id: 'command-1' }));
  assert.equal(leaf.snapshot().tasks[0].correlation_id, null);

  // An authoritative correlation that differs from the control binding is
  // adopted rather than rejected.
  const authoritative = task({ correlation_id: 'task-core-correlation-9' });
  const adopted = leaf.adopt('task.get', {
    ok: true,
    result: { task: authoritative, attempt: { task_id: 'task-1', attempt_id: 'attempt-1' } },
  }, adoption(leaf, { query_task_id: 'task-1' }));
  assert.equal(adopted.tasks[0].correlation_id, 'task-core-correlation-9');

  // Once confirmed it is immutable.
  assert.throws(
    () => leaf.adopt('task.get', {
      ok: true,
      result: {
        task: task({ correlation_id: 'task-core-correlation-10' }),
        attempt: { task_id: 'task-1', attempt_id: 'attempt-1' },
      },
    }, adoption(leaf, { query_task_id: 'task-1' })),
    /retained task identity/
  );
});

test('response and round cancellation never widen into formal task cancellation', () => {
  assert.equal(mapFormalTaskCancel('playback.stop', 'task-1'), null);
  assert.equal(mapFormalTaskCancel('response.cancel', 'task-1'), null);
  assert.equal(mapFormalTaskCancel('round.cancel', 'task-1'), null);
  assert.deepEqual(mapFormalTaskCancel('task.cancel', 'task-1'), {
    operation: 'task.cancel',
    task_id: 'task-1',
  });
  assert.throws(() => mapFormalTaskCancel('task.cancel', null), /task_id is invalid/);
});

test('concurrent mutation replay and confirmation reuse allocate one call', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const prepared = prepareFormalTaskMutation(binding, { operation: 'task.create', command_id: 'command-1', task_id: null }, confirmation());
  let release;
  const gate = new Promise(resolve => {
    release = resolve;
  });
  let calls = 0;
  const first = leaf.submitMutation(prepared, async () => {
    calls += 1;
    await gate;
    return { ok: true };
  });

  await assert.rejects(
    leaf.submitMutation(prepared, async () => {}),
    /already in flight/
  );
  assert.equal(calls, 1);
  release();
  await first;
  const reusedConfirmation = prepareFormalTaskMutation(
    binding,
    { operation: 'task.create', command_id: 'command-2', task_id: null },
    confirmation({ command_id: 'command-2' })
  );
  await assert.rejects(
    leaf.submitMutation(reusedConfirmation, async () => {
      calls += 1;
    }),
    /already acknowledged/
  );
  assert.equal(calls, 1);
});

test('voice or Web disconnect preserves formal task truth and blocks mutation', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt('task.list', { ok: true, result: { tasks: [task()] } }, adoption(leaf));
  const disconnected = leaf.disconnect();
  const prepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.cancel', command_id: 'command-cancel', task_id: 'task-1' },
    confirmation({
      operation: 'task.cancel',
      command_id: 'command-cancel',
      target_task_id: 'task-1',
    })
  );
  let calls = 0;

  assert.equal(disconnected.tasks[0].task_id, 'task-1');
  await assert.rejects(
    leaf.submitMutation(prepared, async () => {
      calls += 1;
    }),
    /disconnected/
  );
  assert.equal(calls, 0);
  assert.equal(leaf.reconnect(binding).tasks[0].task_id, 'task-1');
  assert.throws(() => leaf.reconnect({ ...binding, session_id: 'session-2' }), /cannot cross scope/);
});

test('progress adoption requires exact TaskEvent causation and result origin', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt(
    'task.events',
    {
      ok: true,
      result: eventsResult(runningPrefix(), 2, 'task-1', -1),
    },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  const progress = {
    task_id: 'task-1',
    correlation_id: binding.correlation_id,
    source_event_id: 'task-1:event:2',
    source_event_seq: 2,
    progress_event_id: 'progress-1',
    progress_causation_id: 'task-1:event:2',
    state: 'running',
    outcome: null,
  };

  leaf.adoptProgress(progress, leaf.snapshot().connection_generation);
  assert.deepEqual(leaf.snapshot().progress_receipts, ['progress-1']);
  assert.throws(() => leaf.adoptProgress({ ...progress, progress_event_id: 'bad', progress_causation_id: 'wrong' }, leaf.snapshot().connection_generation), /origin binding mismatch/);
  assert.throws(() => leaf.adoptProgress({ ...progress, progress_event_id: 'bad-state', state: 'terminal', outcome: 'completed' }, leaf.snapshot().connection_generation), /origin binding mismatch/);
  assert.deepEqual(leaf.snapshot().progress_receipts, ['progress-1']);
});

test('foreign scope, correlation, event gaps, and task-attempt mismatch fail closed', () => {
  for (const response of [
    { ok: true, result: { tasks: [task({ scope: { ...scope, project_id: 'foreign' } })] } },
    {
      ok: true,
      result: {
        task: task(),
        attempt: { task_id: 'task-1', attempt_id: 'attempt-other' },
      },
    },
  ]) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    assert.throws(() => leaf.adopt(
      'tasks' in response.result ? 'task.list' : 'task.get',
      response,
      adoption(leaf, { query_task_id: 'tasks' in response.result ? null : 'task-1' }),
    ), /mismatch/);
    assert.equal(leaf.snapshot().tasks.length, 0);
  }

  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  assert.throws(
    () =>
      leaf.adopt(
        'task.events',
        {
          ok: true,
          result: eventsResult([event(0), event(2, { correlation_id: 'foreign' })], 2, 'task-1', -1),
        },
        adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
      ),
    /sequence or origin binding mismatch/
  );
  assert.equal(leaf.snapshot().tasks.length, 0);
});

test('event suffix and empty cursor replay preserve exact observed truth', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt('task.events', { ok: true, result: eventsResult([event(0)], 0, 'task-1', -1) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }));
  leaf.adopt('task.events', { ok: true, result: eventsResult([event(1), event(2)], 2, 'task-1', 0) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 0 } }));
  const afterSuffix = leaf.snapshot().tasks[0];
  assert.equal(afterSuffix.last_event_seq, 2);
  assert.equal(afterSuffix.event_head, 2);
  leaf.adopt('task.events', { ok: true, result: eventsResult([], 2, 'task-1', 2) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 2 } }));
  assert.deepEqual(leaf.snapshot().tasks[0], afterSuffix);
  assert.throws(() => leaf.adopt('task.events', { ok: true, result: eventsResult([], 3, 'task-1', 2) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 2 } })), /omits events/);
  assert.throws(
    () => leaf.adopt('task.events', { ok: true, result: eventsResult([event(3)], 3, 'task-foreign', 2) }, adoption(leaf, { events_query: { task_id: 'task-foreign', after_seq: 2 } })),
    /cursor does not bind|origin binding mismatch/
  );
  assert.throws(() => leaf.adopt('task.events', { ok: true, result: eventsResult([], 2, 'task-1', 3) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 3 } })), /cursor exceeds/);
  assert.throws(
    () => leaf.adopt('task.events', { ok: true, result: eventsResult([event(0)], 0, 'task-1', -1) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })),
    /head cannot move backwards/
  );
});

test('mutation adoption binds the exact submitted command, operation, target, and attempt', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  for (const suffix of ['a', 'b']) {
    const prepared = prepareFormalTaskMutation(
      binding,
      { operation: 'task.create', command_id: `command-${suffix}`, task_id: null },
      confirmation({ confirmation_id: `confirmation-${suffix}`, command_id: `command-${suffix}` })
    );
    await leaf.submitMutation(prepared, async () => ({ ok: true }));
  }

  const beforeSwap = leaf.snapshot();
  assert.throws(
    () => leaf.adopt(
      'task.create',
      {
        status: 'mutation_processed',
        operation: 'task.create',
        formal_task_result: { command_id: 'command-b', task_id: 'task-b', attempt_id: 'attempt-b' },
      },
      adoption(leaf, { command_id: 'command-a' })
    ),
    /command binding mismatch/
  );
  assert.deepEqual(leaf.snapshot(), beforeSwap);

  for (const suffix of ['a', 'b']) {
    leaf.adopt(
      'task.create',
      {
        status: 'mutation_processed',
        operation: 'task.create',
        formal_task_result: { command_id: `command-${suffix}`, task_id: `task-${suffix}`, attempt_id: `attempt-${suffix}` },
      },
      adoption(leaf, { command_id: `command-${suffix}` })
    );
  }
  const cancel = prepareFormalTaskMutation(
    binding,
    { operation: 'task.cancel', command_id: 'command-cancel-a', task_id: 'task-a' },
    confirmation({
      confirmation_id: 'confirmation-cancel-a',
      operation: 'task.cancel',
      command_id: 'command-cancel-a',
      target_task_id: 'task-a',
    })
  );
  await leaf.submitMutation(cancel, async () => ({ ok: true }));
  const beforeWrongTarget = leaf.snapshot();
  for (const result of [
    { command_id: 'command-cancel-a', task_id: 'task-b', attempt_id: 'attempt-b' },
    { command_id: 'command-cancel-a', task_id: 'task-a', attempt_id: 'attempt-b' },
  ]) {
    assert.throws(
      () => leaf.adopt(
        'task.cancel',
        { status: 'mutation_processed', operation: 'task.cancel', formal_task_result: result },
        adoption(leaf, { command_id: 'command-cancel-a' })
      ),
      /attempt binding mismatch/
    );
    assert.deepEqual(leaf.snapshot(), beforeWrongTarget);
  }
});

test('disconnect fences direct adoption, progress, and every late in-flight mutation response', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const connectedGeneration = leaf.snapshot().connection_generation;
  leaf.adopt('task.list', { ok: true, result: { tasks: [task()] } }, adoption(leaf));
  const retainedTask = leaf.snapshot().tasks[0];
  leaf.disconnect();

  assert.throws(
    () => leaf.adopt('task.list', { ok: true, result: { tasks: [] } }, adoption(leaf, { connection_generation: connectedGeneration })),
    /disconnected/
  );
  assert.throws(
    () => leaf.adoptProgress({
      task_id: 'task-1',
      correlation_id: binding.correlation_id,
      source_event_id: 'event-1',
      source_event_seq: 1,
      progress_event_id: 'progress-late',
      progress_causation_id: 'event-1',
      state: 'running',
      outcome: null,
    }, connectedGeneration),
    /disconnected/
  );
  leaf.reconnect(binding);
  assert.throws(
    () => leaf.adopt('task.list', { ok: true, result: { tasks: [] } }, adoption(leaf, { connection_generation: connectedGeneration })),
    /stale connection/
  );
  assert.deepEqual(leaf.snapshot().tasks, [retainedTask]);

  const lateLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const prepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.create', command_id: 'command-late', task_id: null },
    confirmation({ confirmation_id: 'confirmation-late', command_id: 'command-late' })
  );
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let calls = 0;
  const pending = lateLeaf.submitMutation(prepared, async () => {
    calls += 1;
    await gate;
    return { ok: true };
  });
  lateLeaf.disconnect();
  lateLeaf.reconnect(binding);
  release();
  await assert.rejects(pending, /stale after disconnect/);
  assert.equal(calls, 1);
  assert.deepEqual(lateLeaf.snapshot().mutation_receipts, []);
  assert.deepEqual(lateLeaf.snapshot().tasks, []);
});

test('task.events echoes the exact task and cursor even for an empty response', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult([event(0)], 0, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  const before = leaf.snapshot();
  for (const result of [
    eventsResult([], 0, 'task-swapped', 0),
    eventsResult([], 0, 'task-1', -1),
  ]) {
    assert.throws(
      () => leaf.adopt(
        'task.events',
        { ok: true, result },
        adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 0 } })
      ),
      /response query binding mismatch/
    );
    assert.deepEqual(leaf.snapshot(), before);
  }
});

test('foreign and self-contradictory event provenance or lifecycle has zero replica effect', () => {
  const invalidEvents = [
    event(0, { producer: 'foreign' }),
    event(0, { event_type: 'task.running', state: 'accepted' }),
    event(0, { source_event_id: 'foreign-source', causation_id: 'foreign-source' }),
    event(0, { causation_id: '' }),
  ];
  for (const invalid of invalidEvents) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    assert.throws(
      () => leaf.adopt(
        'task.events',
        { ok: true, result: eventsResult([invalid], 0, 'task-1', -1) },
        adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
      ),
      /event|invalid/
    );
    assert.deepEqual(leaf.snapshot().tasks, []);
  }

  const terminal = event(1, {
    event_type: 'task.terminal',
    state: 'terminal',
    outcome: 'completed',
  });
  const conflicting = event(2, {
    event_type: 'task.terminal',
    state: 'terminal',
    outcome: 'failed',
  });
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  assert.throws(
    () => leaf.adopt(
      'task.events',
      { ok: true, result: eventsResult([event(0), terminal, conflicting], 2, 'task-1', -1) },
      adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
    ),
    /self-contradictory|authoritative/
  );
  assert.deepEqual(leaf.snapshot().tasks, []);
});

test('closed practical limits accept their boundary and reject overflow before state or transport effects', async () => {
  const exactText = 'x'.repeat(FORMAL_TASK_CONTROL_LIMITS.max_text_chars);
  assert.equal(mapFormalTaskCancel('task.cancel', exactText).task_id, exactText);
  assert.throws(
    () => mapFormalTaskCancel('task.cancel', `${exactText}x`),
    /invalid/
  );

  const taskLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const boundaryTasks = Array.from({ length: FORMAL_TASK_CONTROL_LIMITS.max_tasks }, (_, index) => task({
    task_id: `task-${index}`,
    attempt_id: `attempt-${index}`,
  }));
  taskLeaf.adopt('task.list', { ok: true, result: { tasks: boundaryTasks } }, adoption(taskLeaf));
  const taskBoundary = taskLeaf.snapshot();
  assert.equal(taskBoundary.tasks.length, FORMAL_TASK_CONTROL_LIMITS.max_tasks);
  assert.throws(
    () => taskLeaf.adopt('task.list', { ok: true, result: { tasks: [...boundaryTasks, task({ task_id: 'overflow', attempt_id: 'overflow' })] } }, adoption(taskLeaf)),
    /exceeds the formal task capacity/
  );
  assert.deepEqual(taskLeaf.snapshot(), taskBoundary);

  const eventLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const boundaryEvents = Array.from({ length: FORMAL_TASK_CONTROL_LIMITS.max_events_per_response }, (_, index) => event(index));
  eventLeaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(boundaryEvents, boundaryEvents.length - 1, 'task-1', -1) },
    adoption(eventLeaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  assert.equal(eventLeaf.snapshot().tasks[0].last_event_seq, boundaryEvents.length - 1);
  const eventOverflowLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  assert.throws(
    () => eventOverflowLeaf.adopt(
      'task.events',
      { ok: true, result: eventsResult([...boundaryEvents, event(boundaryEvents.length)], boundaryEvents.length, 'task-1', -1) },
      adoption(eventOverflowLeaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
    ),
    /formal event capacity/
  );
  assert.deepEqual(eventOverflowLeaf.snapshot().tasks, []);

  const progressLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  progressLeaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(runningPrefix(), 2, 'task-1', -1) },
    adoption(progressLeaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  const progressGeneration = progressLeaf.snapshot().connection_generation;
  for (let index = 0; index < FORMAL_TASK_CONTROL_LIMITS.max_progress_receipts; index += 1) {
    progressLeaf.adoptProgress({
      task_id: 'task-1',
      correlation_id: binding.correlation_id,
      source_event_id: 'task-1:event:2',
      source_event_seq: 2,
      progress_event_id: `progress-${index}`,
      progress_causation_id: 'task-1:event:2',
      state: 'running',
      outcome: null,
    }, progressGeneration);
  }
  const progressBoundary = progressLeaf.snapshot();
  assert.throws(
    () => progressLeaf.adoptProgress({
      task_id: 'task-1',
      correlation_id: binding.correlation_id,
      source_event_id: 'task-1:event:2',
      source_event_seq: 2,
      progress_event_id: 'progress-overflow',
      progress_causation_id: 'task-1:event:2',
      state: 'running',
      outcome: null,
    }, progressGeneration),
    /progress receipt capacity/
  );
  assert.deepEqual(progressLeaf.snapshot(), progressBoundary);

  const receiptLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  let receiptCalls = 0;
  for (let index = 0; index < FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts; index += 1) {
    const commandId = `receipt-command-${index}`;
    await receiptLeaf.submitMutation(
      prepareFormalTaskMutation(
        binding,
        { operation: 'task.create', command_id: commandId, task_id: null },
        confirmation({ confirmation_id: `receipt-confirmation-${index}`, command_id: commandId })
      ),
      async () => { receiptCalls += 1; }
    );
  }
  await assert.rejects(
    receiptLeaf.submitMutation(
      prepareFormalTaskMutation(
        binding,
        { operation: 'task.create', command_id: 'receipt-overflow', task_id: null },
        confirmation({ confirmation_id: 'receipt-confirmation-overflow', command_id: 'receipt-overflow' })
      ),
      async () => { receiptCalls += 1; }
    ),
    /receipt capacity/
  );
  assert.equal(receiptCalls, FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts);

  const pendingLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  let pendingCalls = 0;
  let releasePending;
  const pendingGate = new Promise(resolve => { releasePending = resolve; });
  const pending = [];
  for (let index = 0; index < FORMAL_TASK_CONTROL_LIMITS.max_pending_mutations; index += 1) {
    const commandId = `pending-command-${index}`;
    pending.push(pendingLeaf.submitMutation(
      prepareFormalTaskMutation(
        binding,
        { operation: 'task.create', command_id: commandId, task_id: null },
        confirmation({ confirmation_id: `pending-confirmation-${index}`, command_id: commandId })
      ),
      async () => { pendingCalls += 1; await pendingGate; }
    ));
  }
  await assert.rejects(
    pendingLeaf.submitMutation(
      prepareFormalTaskMutation(
        binding,
        { operation: 'task.create', command_id: 'pending-overflow', task_id: null },
        confirmation({ confirmation_id: 'pending-confirmation-overflow', command_id: 'pending-overflow' })
      ),
      async () => { pendingCalls += 1; }
    ),
    /pending capacity/
  );
  assert.equal(pendingCalls, FORMAL_TASK_CONTROL_LIMITS.max_pending_mutations);
  releasePending();
  await Promise.all(pending);
});

test('an exact retained server result can be adopted after its confirmation expires', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const retained = {
    binding,
    mutation: { operation: 'task.create', command_id: 'retained-command', task_id: null },
    confirmation: {
      confirmation_id: 'retained-confirmation',
      operation: 'task.create',
      command_id: 'retained-command',
      target_task_id: null,
      expires_at: '2026-08-07T10:00:00Z',
    },
  };
  const response = {
    status: 'mutation_processed',
    operation: 'task.create',
    command_id: 'retained-command',
    target_task_id: null,
    formal_task_result: {
      command_id: 'retained-command', task_id: 'retained-task', attempt_id: 'retained-attempt',
    },
  };

  leaf.adoptRetainedMutationResult(retained, response, leaf.snapshot().connection_generation);

  assert.equal(leaf.snapshot().tasks[0].task_id, 'retained-task');
  assert.deepEqual(leaf.snapshot().mutation_receipts, ['retained-command']);
  assert.throws(() => leaf.adoptRetainedMutationResult(
    { ...retained, confirmation: { ...retained.confirmation, expires_at: 'not-a-date' } },
    response,
    leaf.snapshot().connection_generation,
  ), /confirmation binding mismatch/);
});

test('terminal outcomes are a closed vocabulary at every query event and progress boundary', () => {
  const queryCases = [
    ['task.list', { ok: true, result: { tasks: [task({ state: 'terminal', outcome: 'forged-success' })] } }, {}],
    ['task.get', { ok: true, result: { task: task({ state: 'terminal', outcome: 'forged-success' }), attempt: { task_id: 'task-1', attempt_id: 'attempt-1' } } }, { query_task_id: 'task-1' }],
    ['task.status', { ok: true, result: { task: task({ state: 'terminal', outcome: 'forged-success' }), attempt: { task_id: 'task-1', attempt_id: 'attempt-1' } } }, { query_task_id: 'task-1' }],
    ['task.events', { ok: true, result: eventsResult([
      event(0),
      event(1, { event_type: 'task.terminal', state: 'terminal', outcome: 'forged-success' }),
    ], 1, 'task-1', -1) }, { events_query: { task_id: 'task-1', after_seq: -1 } }],
  ];
  for (const [operation, response, context] of queryCases) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    const before = leaf.snapshot();
    assert.throws(() => leaf.adopt(operation, response, adoption(leaf, context)), /terminal outcome vocabulary/);
    assert.deepEqual(leaf.snapshot(), before);
  }

  const progressLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  progressLeaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(terminalEvents(), 4, 'task-1', -1) },
    adoption(progressLeaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  const beforeProgress = progressLeaf.snapshot();
  assert.throws(() => progressLeaf.adoptProgress({
    task_id: 'task-1',
    correlation_id: binding.correlation_id,
    source_event_id: 'task-1:event:4',
    source_event_seq: 4,
    progress_event_id: 'progress-forged',
    progress_causation_id: 'task-1:event:4',
    state: 'terminal',
    outcome: 'forged-success',
  }, beforeProgress.connection_generation), /terminal outcome vocabulary/);
  assert.deepEqual(progressLeaf.snapshot(), beforeProgress);
});

test('event identities remain unique across exact cursor suffixes', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(runningPrefix(), 2, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  const before = leaf.snapshot();
  assert.throws(() => leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult([
      event(3, { event_id: 'task-1:event:0', event_type: 'task.blocked', state: 'blocked', producer: 'task_core' }),
    ], 3, 'task-1', 2) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 2 } }),
  ), /event_id was reused/);
  assert.deepEqual(leaf.snapshot(), before);
});

test('full event replay rejects reused sequence with a replacement event identity', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(runningPrefix(), 2, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  const before = leaf.snapshot();
  const replaced = runningPrefix();
  replaced[1] = event(1, { event_id: 'replacement-event-1', details: { replacement: true } });
  assert.throws(() => leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(replaced, 2, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  ), /sequence was reused/);
  assert.deepEqual(leaf.snapshot(), before);
});

test('delivery failures and blocked decision transitions preserve separate task and attempt truth', () => {
  const delivery = new FormalTaskControlLeaf({ enabled: true, binding });
  delivery.adopt(
    'task.events',
    { ok: true, result: eventsResult([
      event(0),
      event(1, {
        event_type: 'attempt.terminal', state: 'terminal', outcome: 'failed',
        producer: 'task_core.delivery', source_event_id: null, causation_id: 'outbox-1',
      }),
      event(2, {
        event_type: 'task.terminal', state: 'terminal', outcome: 'failed',
        producer: 'task_core.delivery', source_event_id: null, causation_id: 'outbox-1',
      }),
    ], 2, 'task-1', -1) },
    adoption(delivery, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  assert.equal(delivery.snapshot().tasks[0].outcome, 'failed');

  const lifecycle = new FormalTaskControlLeaf({ enabled: true, binding });
  lifecycle.adopt(
    'task.events',
    { ok: true, result: eventsResult([
      ...runningPrefix(),
      event(3, { event_type: 'task.blocked', state: 'blocked', producer: 'task_core' }),
      event(4, { event_type: 'task.decision_required', state: 'decision_required', producer: 'task_core' }),
      event(5, { event_type: 'task.running', state: 'running', producer: 'task_core' }),
    ], 5, 'task-1', -1) },
    adoption(lifecycle, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  assert.equal(lifecycle.snapshot().tasks[0].state, 'running');
});

test('attempt terminal requires its consecutive authoritative task terminal', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const uncoupled = terminalEvents().slice(0, -1);
  assert.throws(() => leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(uncoupled, 3, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  ), /consecutive task lifecycle/);
  assert.deepEqual(leaf.snapshot().tasks, []);
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(terminalEvents(), 4, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  assert.equal(leaf.snapshot().tasks[0].outcome, 'completed');
  const terminal = leaf.snapshot();
  assert.throws(() => leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult([
      event(5, { event_type: 'task.terminal', state: 'terminal', outcome: 'completed', producer: 'task_core' }),
    ], 5, 'task-1', 4) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 4 } }),
  ), /lifecycle/);
  assert.deepEqual(leaf.snapshot(), terminal);
});

test('canonical terminal truth rejects every later control event', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(terminalEvents(), 4, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  const terminal = leaf.snapshot();
  const lateCancel = event(5, {
    event_type: 'task.cancel_requested', state: 'terminal', outcome: 'completed',
    producer: 'task_core.control', source_event_id: null, causation_id: 'late-cancel',
  });
  assert.throws(() => leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult([lateCancel], 5, 'task-1', 4) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 4 } }),
  ), /lifecycle/);
  assert.deepEqual(leaf.snapshot(), terminal);

  const replay = new FormalTaskControlLeaf({ enabled: true, binding });
  assert.throws(() => replay.adopt(
    'task.events',
    { ok: true, result: eventsResult([...terminalEvents(), lateCancel], 5, 'task-1', -1) },
    adoption(replay, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  ), /lifecycle/);
  assert.deepEqual(replay.snapshot().tasks, []);
});

test('task queries cannot roll back or retarget retained task truth', () => {
  for (const operation of ['task.get', 'task.status', 'task.list']) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    leaf.adopt('task.list', { ok: true, result: { tasks: [task({ event_head: 5 })] } }, adoption(leaf));
    const before = leaf.snapshot();
    const response = operation === 'task.list'
      ? { ok: true, result: { tasks: [task({ state: 'accepted', event_head: 0 })] } }
      : { ok: true, result: { task: task({ state: 'accepted', event_head: 0 }), attempt: { task_id: 'task-1', attempt_id: 'attempt-1' } } };
    assert.throws(() => leaf.adopt(
      operation,
      response,
      adoption(leaf, { query_task_id: operation === 'task.list' ? null : 'task-1' }),
    ), /retained/);
    assert.deepEqual(leaf.snapshot(), before);
  }

  const swapped = new FormalTaskControlLeaf({ enabled: true, binding });
  swapped.adopt('task.list', { ok: true, result: { tasks: [task({ event_head: 5 })] } }, adoption(swapped));
  const beforeSwap = swapped.snapshot();
  assert.throws(() => swapped.adopt('task.status', {
    ok: true,
    result: {
      task: task({ attempt_id: 'attempt-forged', event_head: 6 }),
      attempt: { task_id: 'task-1', attempt_id: 'attempt-forged' },
    },
  }, adoption(swapped, { query_task_id: 'task-1' })), /retained task identity/);
  assert.deepEqual(swapped.snapshot(), beforeSwap);

  const target = new FormalTaskControlLeaf({ enabled: true, binding });
  assert.throws(() => target.adopt('task.get', {
    ok: true,
    result: {
      task: task({ task_id: 'task-B' }),
      attempt: { task_id: 'task-B', attempt_id: 'attempt-1' },
    },
  }, adoption(target, { query_task_id: 'task-A' })), /binding mismatch/);
  assert.deepEqual(target.snapshot().tasks, []);
});

test('query binding is derived only from exact authenticated Task Core scope and correlation', () => {
  const response = {
    ok: true,
    result: {
      tasks: [task({ task_id: 'task-1' }), task({ task_id: 'task-2', correlation_id: 'correlation-2' })],
    },
  };
  assert.deepEqual(
    deriveFormalTaskQueryBinding({
      operation: 'task.list',
      response,
      expected_session_id: 'session-1',
      generation: 7,
    }),
    {
      ...binding,
      generation: 7,
    },
  );
  assert.throws(
    () =>
      deriveFormalTaskQueryBinding({
        operation: 'task.list',
        response,
        expected_session_id: 'session-other',
        generation: 7,
      }),
    /scope binding mismatch/,
  );
  assert.equal(
    deriveFormalTaskQueryBinding({
      operation: 'task.list',
      response: { ok: true, result: { tasks: [] } },
      expected_session_id: 'session-1',
      generation: 7,
    }),
    null,
  );
});

test('a confirmed mutation rebind transfers only the exact observed task attempt', () => {
  const source = new FormalTaskControlLeaf({ enabled: true, binding });
  source.adopt(
    'task.list',
    {
      ok: true,
      result: {
        tasks: [task({ task_id: 'task-1' }), task({ task_id: 'task-2', correlation_id: 'correlation-2' })],
      },
    },
    adoption(source),
  );
  const nextBinding = { ...binding, correlation_id: 'cancel-correlation', generation: 2 };
  const rebound = source.rebindConfirmedMutation(nextBinding, 'task-2');

  assert.equal(source.snapshot().connected, false);
  assert.deepEqual(rebound.snapshot().binding, nextBinding);
  assert.deepEqual(
    rebound.snapshot().tasks.map(record => record.task_id),
    ['task-2'],
  );
  assert.throws(() => rebound.rebindConfirmedMutation({ ...nextBinding, project_id: 'foreign-project' }, 'task-2'), /cannot cross scope/);
  assert.throws(() => rebound.rebindConfirmedMutation(nextBinding, 'task-unobserved'), /observed exact task attempt/);
  rebound.disconnect();
  assert.throws(() => rebound.rebindConfirmedMutation(nextBinding, 'task-2'), /connected observed replica/);
});
