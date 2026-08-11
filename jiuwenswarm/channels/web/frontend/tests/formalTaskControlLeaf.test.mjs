import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FORMAL_TASK_CONTROL_LIMITS,
  FormalTaskControlLeaf,
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
    correlation_id: overrides.correlation_id ?? binding.correlation_id,
    attempt_id: overrides.attempt_id ?? 'attempt-1',
    attempt_number: overrides.attempt_number ?? 1,
    state: overrides.state ?? 'running',
    outcome: overrides.outcome ?? null,
    event_head: overrides.event_head ?? 1,
  };
}

function event(seq, overrides = {}) {
  const eventType = overrides.event_type ?? (seq === 0 ? 'task.accepted' : 'task.running');
  const sourceEventId = Object.hasOwn(overrides, 'source_event_id')
    ? overrides.source_event_id
    : seq === 0
      ? null
      : `executor-source-${seq}`;
  return {
    event_id: overrides.event_id ?? `task-1:event:${seq}`,
    task_id: overrides.task_id ?? 'task-1',
    attempt_id: overrides.attempt_id ?? 'attempt-1',
    scope: overrides.scope ?? { ...scope },
    seq,
    event_type: eventType,
    state: overrides.state ?? (seq === 0 ? 'accepted' : 'running'),
    outcome: overrides.outcome ?? null,
    producer: overrides.producer ?? 'task_core',
    source_event_id: sourceEventId,
    causation_id: overrides.causation_id ?? (sourceEventId ?? `cause-${seq}`),
    correlation_id: overrides.correlation_id ?? binding.correlation_id,
    occurred_at: '2026-08-07T12:00:00Z',
    details: overrides.details ?? {},
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

function adoption(leaf, { command_id = null, target_task_id = null, events_query = null, connection_generation } = {}) {
  return {
    connection_generation: connection_generation ?? leaf.snapshot().connection_generation,
    command_id,
    target_task_id,
    events_query,
  };
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
    command_id: 'command-1',
    target_task_id: null,
    formal_task_result: {
      task_id: 'task-1',
      attempt_id: 'attempt-1',
      state: 'accepted',
      outbox_id: 'outbox-1',
    },
  }, adoption(leaf, { command_id: 'command-1' }));
  assert.equal(leaf.snapshot().tasks[0].state, 'accepted');

  leaf.adopt('task.get', {
    ok: true,
    result: { task: task(), attempt: { task_id: 'task-1', attempt_id: 'attempt-1', attempt_number: 1 } },
  }, adoption(leaf, { target_task_id: 'task-1' }));
  leaf.adopt('task.status', {
    ok: true,
    result: { task: task(), attempt: { task_id: 'task-1', attempt_id: 'attempt-1', attempt_number: 1 } },
  }, adoption(leaf, { target_task_id: 'task-1' }));
  leaf.adopt('task.list', { ok: true, result: { tasks: [task()] } }, adoption(leaf));
  leaf.adopt(
    'task.events',
    {
      ok: true,
      result: eventsResult([event(0), event(1)], 1, 'task-1', -1),
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
    command_id: 'command-cancel',
    target_task_id: 'task-1',
    formal_task_result: {
      task_id: 'task-1',
      attempt_id: 'attempt-1',
      cancel_acknowledged: true,
      applied: true,
      state: 'running',
      outbox_id: 'outbox-cancel',
    },
  }, adoption(leaf, { command_id: 'command-cancel' }));

  assert.equal(calls, 1);
  assert.equal(leaf.snapshot().tasks.length, 1);
  assert.equal(leaf.snapshot().tasks[0].last_event_id, 'task-1:event:1');
  assert.deepEqual(leaf.snapshot().mutation_receipts, ['command-1', 'command-cancel']);
  await assert.rejects(
    leaf.submitMutation(prepared, async () => {}),
    /already acknowledged/
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

test('bounded retry advances exact A/B/C lineage without client-supplied predecessor facts', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const aTerminal = event(1, {
    event_type: 'task.terminal',
    state: 'terminal',
    outcome: 'cancelled',
    attempt_id: 'attempt-a',
  });
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult([event(0, { attempt_id: 'attempt-a' }), aTerminal], 1, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  const retryB = prepareFormalTaskMutation(
    binding,
    { operation: 'task.retry', command_id: 'retry-b', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-retry-b',
      operation: 'task.retry',
      command_id: 'retry-b',
      target_task_id: 'task-1',
    }),
  );
  let sentB;
  await leaf.submitMutation(retryB, async prepared => {
    sentB = prepared;
    return { ok: true };
  });
  assert.deepEqual(sentB.mutation, {
    operation: 'task.retry',
    command_id: 'retry-b',
    task_id: 'task-1',
  });
  const retryBResponse = {
    status: 'mutation_processed',
    operation: 'task.retry',
    command_id: 'retry-b',
    target_task_id: 'task-1',
    formal_task_result: {
      task_id: 'task-1',
      previous_attempt_id: 'attempt-a',
      attempt_id: 'attempt-b',
      attempt_number: 2,
      applied: true,
      state: 'accepted',
      outbox_id: 'outbox-b',
    },
  };
  leaf.adopt('task.retry', retryBResponse, adoption(leaf, { command_id: 'retry-b' }));
  assert.deepEqual(
    {
      attempt_id: leaf.snapshot().tasks[0].attempt_id,
      attempt_number: leaf.snapshot().tasks[0].attempt_number,
      last_event_seq: leaf.snapshot().tasks[0].last_event_seq,
    },
    { attempt_id: 'attempt-b', attempt_number: 2, last_event_seq: null },
  );
  const afterRetryB = leaf.snapshot();
  assert.deepEqual(
    leaf.adopt('task.retry', retryBResponse, adoption(leaf, { command_id: 'retry-b' })),
    afterRetryB,
    'an exact command-ledger replay is a zero-effect receipt',
  );

  const historyThroughB = [
    event(0, { attempt_id: 'attempt-a' }),
    aTerminal,
    event(2, {
      attempt_id: 'attempt-b',
      event_type: 'task.retry_accepted',
      state: 'accepted',
      source_event_id: null,
      causation_id: 'retry-b',
      details: {
        command_id: 'retry-b',
        retry_of_attempt_id: 'attempt-a',
        previous_outcome: 'cancelled',
        attempt_number: 2,
      },
    }),
    event(3, {
      attempt_id: 'attempt-b',
      event_type: 'task.terminal',
      state: 'terminal',
      outcome: 'completed',
      producer: 'task_core.delivery',
    }),
  ];
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(historyThroughB, 3, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  const retryC = prepareFormalTaskMutation(
    binding,
    { operation: 'task.retry', command_id: 'retry-c', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-retry-c',
      operation: 'task.retry',
      command_id: 'retry-c',
      target_task_id: 'task-1',
    }),
  );
  await leaf.submitMutation(retryC, async () => ({ ok: true }));
  leaf.adopt('task.retry', {
    status: 'mutation_processed',
    operation: 'task.retry',
    command_id: 'retry-c',
    target_task_id: 'task-1',
    formal_task_result: {
      task_id: 'task-1',
      previous_attempt_id: 'attempt-b',
      attempt_id: 'attempt-c',
      attempt_number: 3,
      applied: true,
      state: 'accepted',
      outbox_id: 'outbox-c',
    },
  }, adoption(leaf, { command_id: 'retry-c' }));
  assert.equal(leaf.snapshot().tasks[0].attempt_id, 'attempt-c');
  assert.equal(leaf.snapshot().tasks[0].attempt_number, 3);
  const afterRetryC = leaf.snapshot();
  assert.deepEqual(
    leaf.adopt('task.retry', retryBResponse, adoption(leaf, { command_id: 'retry-b' })),
    afterRetryC,
    'a historical exact replay cannot roll the current attempt back',
  );

  let calls = 0;
  const exhausted = prepareFormalTaskMutation(
    binding,
    { operation: 'task.retry', command_id: 'retry-d', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-retry-d',
      operation: 'task.retry',
      command_id: 'retry-d',
      target_task_id: 'task-1',
    }),
  );
  await assert.rejects(leaf.submitMutation(exhausted, async () => { calls += 1; }), /eligible/);
  assert.equal(calls, 0);
});

test('forged retry boundaries and response lineage have zero task-replica effect', async () => {
  const baseEvents = [
    event(0, { attempt_id: 'attempt-a' }),
    event(1, {
      attempt_id: 'attempt-a',
      event_type: 'task.terminal',
      state: 'terminal',
      outcome: 'cancelled',
    }),
  ];
  for (const retryOverride of [
    { details: { command_id: 'retry-b', retry_of_attempt_id: 'attempt-extra', previous_outcome: 'cancelled', attempt_number: 2 } },
    { details: { command_id: 'retry-b', retry_of_attempt_id: 'attempt-a', previous_outcome: 'completed', attempt_number: 2 } },
    { attempt_id: 'attempt-a', details: { command_id: 'retry-b', retry_of_attempt_id: 'attempt-a', previous_outcome: 'cancelled', attempt_number: 2 } },
    { details: { command_id: 'retry-b', retry_of_attempt_id: 'attempt-a', previous_outcome: 'cancelled', attempt_number: 3 } },
  ]) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    leaf.adopt('task.events', { ok: true, result: eventsResult(baseEvents, 1, 'task-1', -1) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }));
    const before = leaf.snapshot();
    const forged = event(2, {
      attempt_id: 'attempt-b',
      event_type: 'task.retry_accepted',
      state: 'accepted',
      source_event_id: null,
      causation_id: 'retry-b',
      details: { command_id: 'retry-b', retry_of_attempt_id: 'attempt-a', previous_outcome: 'cancelled', attempt_number: 2 },
      ...retryOverride,
    });
    assert.throws(
      () => leaf.adopt('task.events', { ok: true, result: eventsResult([...baseEvents, forged], 2, 'task-1', -1) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })),
      /retry|attempt|lineage/,
    );
    assert.deepEqual(leaf.snapshot(), before);
  }

  const responseLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  responseLeaf.adopt('task.events', { ok: true, result: eventsResult(baseEvents, 1, 'task-1', -1) }, adoption(responseLeaf, { events_query: { task_id: 'task-1', after_seq: -1 } }));
  const prepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.retry', command_id: 'retry-forged', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-retry-forged',
      operation: 'task.retry',
      command_id: 'retry-forged',
      target_task_id: 'task-1',
    }),
  );
  await responseLeaf.submitMutation(prepared, async () => ({ ok: true }));
  const beforeResponse = responseLeaf.snapshot();
  assert.throws(
    () => responseLeaf.adopt('task.retry', {
      status: 'mutation_processed',
      operation: 'task.retry',
      command_id: 'retry-forged',
      target_task_id: 'task-1',
      formal_task_result: {
        task_id: 'task-1',
        previous_attempt_id: 'attempt-foreign',
        attempt_id: 'attempt-b',
        attempt_number: 2,
        applied: true,
        state: 'accepted',
        outbox_id: 'outbox-b',
      },
    }, adoption(responseLeaf, { command_id: 'retry-forged' })),
    /lineage|binding/,
  );
  assert.deepEqual(responseLeaf.snapshot(), beforeResponse);
});

test('canonical task blocked and decision_required history remains consumable', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const history = [
    event(0),
    event(1),
    event(2, { event_type: 'task.blocked', state: 'blocked' }),
    event(3, { event_type: 'task.decision_required', state: 'decision_required' }),
    event(4, { event_type: 'task.running', state: 'running' }),
    event(5, {
      event_type: 'task.terminal',
      state: 'terminal',
      outcome: 'completed',
      producer: 'task_core.delivery',
    }),
  ];
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(history, 5, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  assert.equal(leaf.snapshot().tasks[0].state, 'terminal');
  assert.equal(leaf.snapshot().tasks[0].outcome, 'completed');
});

test('canonical delivery-owned failed terminal history remains consumable', () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const history = [
    event(0),
    event(1, {
      event_type: 'attempt.terminal',
      state: 'terminal',
      outcome: 'failed',
      producer: 'task_core.delivery',
      source_event_id: null,
      causation_id: 'outbox-dispatch-1',
      details: { reason: 'EXECUTOR_CAPABILITY_UNAVAILABLE' },
    }),
    event(2, {
      event_type: 'task.terminal',
      state: 'terminal',
      outcome: 'failed',
      producer: 'task_core.delivery',
      source_event_id: null,
      causation_id: 'outbox-dispatch-1',
      details: { reason: 'EXECUTOR_CAPABILITY_UNAVAILABLE' },
    }),
  ];
  leaf.adopt(
    'task.events',
    { ok: true, result: eventsResult(history, 2, 'task-1', -1) },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  assert.deepEqual(
    {
      attempt_id: leaf.snapshot().tasks[0].attempt_id,
      attempt_number: leaf.snapshot().tasks[0].attempt_number,
      state: leaf.snapshot().tasks[0].state,
      outcome: leaf.snapshot().tasks[0].outcome,
    },
    { attempt_id: 'attempt-1', attempt_number: 1, state: 'terminal', outcome: 'failed' },
  );
});

test('internal attempt producers cannot forge accepted, running, or sourced terminal history', () => {
  for (const forged of [
    event(1, {
      event_type: 'attempt.accepted',
      state: 'accepted',
      producer: 'task_core.delivery',
      source_event_id: null,
      causation_id: 'outbox-dispatch-1',
    }),
    event(1, {
      event_type: 'attempt.running',
      state: 'running',
      producer: 'task_core.reconciliation',
      source_event_id: null,
      causation_id: 'reconciliation:attempt-1',
    }),
    event(1, {
      event_type: 'attempt.terminal',
      state: 'terminal',
      outcome: 'failed',
      producer: 'task_core.delivery',
      source_event_id: 'forged-source',
      causation_id: 'forged-source',
    }),
    event(1, {
      event_type: 'attempt.terminal',
      state: 'terminal',
      outcome: 'failed',
      producer: 'task_core.control',
      source_event_id: null,
      causation_id: 'outbox-dispatch-1',
    }),
  ]) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    assert.throws(
      () => leaf.adopt(
        'task.events',
        { ok: true, result: eventsResult([event(0), forged], 1, 'task-1', -1) },
        adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
      ),
      /producer|source/,
    );
    assert.deepEqual(leaf.snapshot().tasks, []);
  }
});

test('status target binding and equal-head event truth fail closed', () => {
  const foreign = new FormalTaskControlLeaf({ enabled: true, binding });
  assert.throws(
    () => foreign.adopt(
      'task.status',
      {
        ok: true,
        result: {
          task: task({ task_id: 'task-foreign', attempt_id: 'attempt-foreign' }),
          attempt: { task_id: 'task-foreign', attempt_id: 'attempt-foreign', attempt_number: 1 },
        },
      },
      adoption(foreign, { target_task_id: 'task-1' }),
    ),
    /binding mismatch/,
  );
  assert.deepEqual(foreign.snapshot().tasks, []);

  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt(
    'task.status',
    {
      ok: true,
      result: {
        task: task({ attempt_id: 'attempt-c', state: 'accepted', outcome: null, event_head: 4 }),
        attempt: { task_id: 'task-1', attempt_id: 'attempt-c', attempt_number: 3 },
      },
    },
    adoption(leaf, { target_task_id: 'task-1' }),
  );
  const beforeConflict = leaf.snapshot();
  const staleB = [
    event(0, { attempt_id: 'attempt-a' }),
    event(1, { attempt_id: 'attempt-a', event_type: 'task.terminal', state: 'terminal', outcome: 'cancelled' }),
    event(2, {
      attempt_id: 'attempt-b',
      event_type: 'task.retry_accepted',
      state: 'accepted',
      source_event_id: null,
      causation_id: 'retry-b',
      details: {
        command_id: 'retry-b',
        retry_of_attempt_id: 'attempt-a',
        previous_outcome: 'cancelled',
        attempt_number: 2,
      },
    }),
    event(3, { attempt_id: 'attempt-b' }),
    event(4, { attempt_id: 'attempt-b', event_type: 'task.terminal', state: 'terminal', outcome: 'completed' }),
  ];
  assert.throws(
    () => leaf.adopt(
      'task.events',
      { ok: true, result: eventsResult(staleB, 4, 'task-1', -1) },
      adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } }),
    ),
    /replay conflicts/,
  );
  assert.deepEqual(leaf.snapshot(), beforeConflict);

  const newer = new FormalTaskControlLeaf({ enabled: true, binding });
  newer.adopt(
    'task.status',
    {
      ok: true,
      result: {
        task: task({ attempt_id: 'attempt-b', state: 'running', outcome: null, event_head: 3 }),
        attempt: { task_id: 'task-1', attempt_id: 'attempt-b', attempt_number: 2 },
      },
    },
    adoption(newer, { target_task_id: 'task-1' }),
  );
  newer.adopt(
    'task.events',
    { ok: true, result: eventsResult(staleB, 4, 'task-1', -1) },
    adoption(newer, { events_query: { task_id: 'task-1', after_seq: -1 } }),
  );
  assert.equal(newer.snapshot().tasks[0].outcome, 'completed');
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
      result: eventsResult([event(0), event(1)], 1, 'task-1', -1),
    },
    adoption(leaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  const progress = {
    task_id: 'task-1',
    correlation_id: binding.correlation_id,
    source_event_id: 'task-1:event:1',
    source_event_seq: 1,
    progress_event_id: 'progress-1',
    progress_causation_id: 'task-1:event:1',
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
    { ok: true, result: { tasks: [task({ correlation_id: 'foreign-correlation' })] } },
    {
      ok: true,
      result: {
        task: task(),
        attempt: { task_id: 'task-1', attempt_id: 'attempt-other', attempt_number: 1 },
      },
    },
  ]) {
    const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
    const operation = 'tasks' in response.result ? 'task.list' : 'task.get';
    assert.throws(
      () => leaf.adopt(operation, response, adoption(leaf, { target_task_id: operation === 'task.get' ? 'task-1' : null })),
      /mismatch/,
    );
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
  leaf.adopt('task.events', { ok: true, result: eventsResult([event(1)], 1, 'task-1', 0) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 0 } }));
  const afterSuffix = leaf.snapshot().tasks[0];
  assert.equal(afterSuffix.last_event_seq, 1);
  assert.equal(afterSuffix.event_head, 1);
  leaf.adopt('task.events', { ok: true, result: eventsResult([], 1, 'task-1', 1) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 1 } }));
  assert.deepEqual(leaf.snapshot().tasks[0], afterSuffix);
  assert.throws(() => leaf.adopt('task.events', { ok: true, result: eventsResult([], 2, 'task-1', 1) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 1 } })), /omits events/);
  assert.throws(
    () => leaf.adopt('task.events', { ok: true, result: eventsResult([event(2)], 2, 'task-foreign', 1) }, adoption(leaf, { events_query: { task_id: 'task-foreign', after_seq: 1 } })),
    /cursor does not bind|origin binding mismatch/
  );
  assert.throws(() => leaf.adopt('task.events', { ok: true, result: eventsResult([], 1, 'task-1', 2) }, adoption(leaf, { events_query: { task_id: 'task-1', after_seq: 2 } })), /cursor exceeds/);
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
        command_id: 'command-b',
        target_task_id: null,
        formal_task_result: {
          task_id: 'task-b',
          attempt_id: 'attempt-b',
          state: 'accepted',
          outbox_id: 'outbox-b',
        },
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
        command_id: `command-${suffix}`,
        target_task_id: null,
        formal_task_result: {
          task_id: `task-${suffix}`,
          attempt_id: `attempt-${suffix}`,
          state: 'accepted',
          outbox_id: `outbox-${suffix}`,
        },
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
  for (const response of [
    {
      status: 'mutation_processed',
      operation: 'task.cancel',
      command_id: 'command-cancel-a',
      target_task_id: 'task-b',
      formal_task_result: {
        task_id: 'task-a',
        attempt_id: 'attempt-a',
        cancel_acknowledged: true,
        applied: true,
        state: 'accepted',
        outbox_id: 'outbox-cancel-a',
      },
    },
    {
      status: 'mutation_processed',
      operation: 'task.cancel',
      command_id: 'command-cancel-a',
      target_task_id: 'task-a',
      formal_task_result: {
        task_id: 'task-b',
        attempt_id: 'attempt-b',
        cancel_acknowledged: true,
        applied: true,
        state: 'accepted',
        outbox_id: 'outbox-cancel-a',
      },
    },
    {
      status: 'mutation_processed',
      operation: 'task.cancel',
      command_id: 'command-cancel-a',
      target_task_id: 'task-a',
      formal_task_result: {
        task_id: 'task-a',
        attempt_id: 'attempt-b',
        cancel_acknowledged: true,
        applied: true,
        state: 'accepted',
        outbox_id: 'outbox-cancel-a',
      },
    },
  ]) {
    assert.throws(
      () => leaf.adopt(
        'task.cancel',
        response,
        adoption(leaf, { command_id: 'command-cancel-a' })
      ),
      /target binding mismatch|attempt binding mismatch/
    );
    assert.deepEqual(leaf.snapshot(), beforeWrongTarget);
  }
});

test('cancel result acknowledgement, application, and durable outbox stay fail closed', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  leaf.adopt('task.list', { ok: true, result: { tasks: [task()] } }, adoption(leaf));
  const prepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.cancel', command_id: 'command-cancel-repeat', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-cancel-repeat',
      operation: 'task.cancel',
      command_id: 'command-cancel-repeat',
      target_task_id: 'task-1',
    })
  );
  await leaf.submitMutation(prepared, async () => ({ ok: true }));
  const repeatedCancelResult = {
    task_id: 'task-1',
    attempt_id: 'attempt-1',
    cancel_acknowledged: true,
    applied: false,
    state: 'running',
  };
  const repeatedCancelResponse = {
    status: 'mutation_processed',
    operation: 'task.cancel',
    command_id: 'command-cancel-repeat',
    target_task_id: 'task-1',
    formal_task_result: repeatedCancelResult,
  };
  const invalidResponses = [
    [{ ...repeatedCancelResponse, formal_task_result: { ...repeatedCancelResult, cancel_acknowledged: false } }, /not acknowledged/],
    [{ ...repeatedCancelResponse, formal_task_result: { ...repeatedCancelResult, applied: 'false' } }, /applied result is invalid/],
    [{ ...repeatedCancelResponse, formal_task_result: { ...repeatedCancelResult, outbox_id: 'outbox-forged' } }, /cannot own an outbox/],
    [{ ...repeatedCancelResponse, formal_task_result: { ...repeatedCancelResult, applied: true } }, /invalid durable outbox/],
    [{
      ...repeatedCancelResponse,
      formal_task_result: {
        ...repeatedCancelResult,
        applied: true,
        state: 'terminal',
        outbox_id: 'outbox-forged',
      },
    }, /invalid durable outbox/],
  ];
  const beforeInvalidResponses = leaf.snapshot();

  for (const [response, error] of invalidResponses) {
    assert.throws(
      () => leaf.adopt('task.cancel', response, adoption(leaf, { command_id: 'command-cancel-repeat' })),
      error
    );
    assert.deepEqual(leaf.snapshot(), beforeInvalidResponses);
  }

  const repeated = leaf.adopt(
    'task.cancel',
    repeatedCancelResponse,
    adoption(leaf, { command_id: 'command-cancel-repeat' })
  );
  assert.deepEqual(repeated, beforeInvalidResponses);
  assert.deepEqual(
    leaf.adopt(
      'task.cancel',
      { ...repeatedCancelResponse, formal_task_result: { ...repeatedCancelResult, outbox_id: null } },
      adoption(leaf, { command_id: 'command-cancel-repeat' })
    ),
    repeated
  );

  const terminalLeaf = new FormalTaskControlLeaf({ enabled: true, binding });
  terminalLeaf.adopt('task.list', { ok: true, result: { tasks: [task()] } }, adoption(terminalLeaf));
  const terminalPrepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.cancel', command_id: 'command-cancel-terminal', task_id: 'task-1' },
    confirmation({
      confirmation_id: 'confirmation-cancel-terminal',
      operation: 'task.cancel',
      command_id: 'command-cancel-terminal',
      target_task_id: 'task-1',
    })
  );
  await terminalLeaf.submitMutation(terminalPrepared, async () => ({ ok: true }));
  terminalLeaf.adopt(
    'task.cancel',
    {
      status: 'mutation_processed',
      operation: 'task.cancel',
      command_id: 'command-cancel-terminal',
      target_task_id: 'task-1',
      formal_task_result: {
        task_id: 'task-1',
        attempt_id: 'attempt-1',
        cancel_acknowledged: true,
        applied: true,
        state: 'terminal',
        outbox_id: null,
      },
    },
    adoption(terminalLeaf, { command_id: 'command-cancel-terminal' })
  );
  assert.deepEqual(terminalLeaf.snapshot().tasks, leaf.snapshot().tasks);
});

test('product mutation wrapper rejects misplaced authority and invalid formal result fields', async () => {
  const leaf = new FormalTaskControlLeaf({ enabled: true, binding });
  const prepared = prepareFormalTaskMutation(
    binding,
    { operation: 'task.create', command_id: 'command-create', task_id: null },
    confirmation({ confirmation_id: 'confirmation-create', command_id: 'command-create' })
  );
  await leaf.submitMutation(prepared, async () => ({ ok: true }));
  const validFormalResult = {
      task_id: 'task-created',
      attempt_id: 'attempt-created',
      attempt_number: 1,
    state: 'accepted',
    outbox_id: 'outbox-created',
  };
  const validResponse = {
    status: 'mutation_processed',
    operation: 'task.create',
    command_id: 'command-create',
    target_task_id: null,
    formal_task_result: validFormalResult,
  };
  const invalidResponses = [
    [{ ...validResponse, operation: 'task.cancel' }, /operation binding mismatch/],
    [{ ...validResponse, command_id: 'command-forged' }, /command binding mismatch/],
    [{ ...validResponse, target_task_id: 'task-forged' }, /target binding mismatch/],
    [{ ...validResponse, formal_task_result: { ...validFormalResult, command_id: 'command-create' } }, /misplaced authority/],
    [{ ...validResponse, formal_task_result: { ...validFormalResult, task_id: '' } }, /result.task_id is invalid/],
    [{ ...validResponse, formal_task_result: { ...validFormalResult, attempt_id: null } }, /result.attempt_id is invalid/],
    [{ ...validResponse, formal_task_result: { ...validFormalResult, state: 'running' } }, /not an accepted durable task/],
    [{ ...validResponse, formal_task_result: { ...validFormalResult, outbox_id: null } }, /not an accepted durable task/],
  ];
  const beforeInvalidResponses = leaf.snapshot();

  for (const [response, error] of invalidResponses) {
    assert.throws(
      () => leaf.adopt('task.create', response, adoption(leaf, { command_id: 'command-create' })),
      error
    );
    assert.deepEqual(leaf.snapshot(), beforeInvalidResponses);
  }

  const adopted = leaf.adopt(
    'task.create',
    validResponse,
    adoption(leaf, { command_id: 'command-create' })
  );
  assert.deepEqual(adopted.tasks, [{
    task_id: 'task-created',
    attempt_id: 'attempt-created',
    attempt_number: 1,
    state: 'accepted',
    outcome: null,
    event_head: null,
    last_event_id: null,
    last_event_seq: null,
  }]);
  assert.deepEqual(
    leaf.adopt('task.create', validResponse, adoption(leaf, { command_id: 'command-create' })),
    adopted
  );
  assert.throws(
    () => leaf.adopt(
      'task.create',
      {
        ...validResponse,
        formal_task_result: { ...validFormalResult, outbox_id: 'outbox-forged' },
      },
      adoption(leaf, { command_id: 'command-create' })
    ),
    /replay conflicts/
  );
  assert.deepEqual(leaf.snapshot(), adopted);
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
    /self-contradictory/
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
    { ok: true, result: eventsResult([event(0), event(1)], 1, 'task-1', -1) },
    adoption(progressLeaf, { events_query: { task_id: 'task-1', after_seq: -1 } })
  );
  const progressGeneration = progressLeaf.snapshot().connection_generation;
  for (let index = 0; index < FORMAL_TASK_CONTROL_LIMITS.max_progress_receipts; index += 1) {
    progressLeaf.adoptProgress({
      task_id: 'task-1',
      correlation_id: binding.correlation_id,
      source_event_id: 'task-1:event:1',
      source_event_seq: 1,
      progress_event_id: `progress-${index}`,
      progress_causation_id: 'task-1:event:1',
      state: 'running',
      outcome: null,
    }, progressGeneration);
  }
  const progressBoundary = progressLeaf.snapshot();
  assert.throws(
    () => progressLeaf.adoptProgress({
      task_id: 'task-1',
      correlation_id: binding.correlation_id,
      source_event_id: 'task-1:event:1',
      source_event_seq: 1,
      progress_event_id: 'progress-overflow',
      progress_causation_id: 'task-1:event:1',
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
