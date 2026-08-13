import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_P3_TASK_INTENT_METHOD,
  PRODUCT_P3_TASK_INTENT_STATUS_METHOD,
  ProductFormalTaskIntentOwner,
  createSessionFormalTaskIntentRecoveryJournal,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/formalTaskIntentRoute.js';

const resolution = 'a'.repeat(64);
const commitDigest = 'b'.repeat(64);
const token = resolution.slice(0, 32);

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
    values,
  };
}

function envelope(requestId, result, ok = true) {
  return {
    request_id: requestId,
    ok,
    result,
    error: ok ? null : { code: 'INVALID_ARGUMENT', reason: result.reason, message: 'rejected' },
    product_composition: {},
  };
}

function clarification(operation, taskId = null) {
  return {
    status: 'clarification',
    reason: 'TASK_CONFIRMATION_REQUIRED',
    resolver_provider: 'local.closed_schema',
    resolver_implementation_class: 'bounded_deterministic_alpha_v1',
    resolution_id: resolution,
    commit_sha256: commitDigest,
    operation,
    task_id: taskId,
    source_span: { start: 13, end: 24 },
    target_span: operation === 'task.cancel' ? { start: 12, end: 24 } : null,
    confirmation_token: token,
    confirmation_form: `confirm task request ${token}`,
    partial_command_count: 0,
  };
}

function dispatched(operation, taskId, originId, originKind = 'text') {
  return {
    status: 'dispatched',
    reason: 'TASK_INTENT_DISPATCHED',
    resolver_provider: 'local.closed_schema',
    resolver_implementation_class: 'bounded_deterministic_alpha_v1',
    resolution_id: resolution,
    commit_sha256: commitDigest,
    operation,
    task_id: taskId,
    source_span: { start: 13, end: 24 },
    target_span: operation === 'task.cancel' || operation === 'task.status' ? { start: 13, end: 24 } : null,
    origin_kind: originKind,
    origin_id: originId,
    confirmation_commit_id: 'confirm-commit',
    formal_task_result: { task_id: taskId, state: 'accepted' },
  };
}

test('text create requires a later content-bearing commit on the same exact interaction', async () => {
  const calls = [];
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push({ method, params, requestId });
      return calls.length === 1
        ? envelope(requestId, clarification('task.create'))
        : envelope(requestId, dispatched('task.create', 'task-created-1', params.interaction_id));
    },
  });

  const first = await owner.submitText({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    operation: 'task.create',
    text: 'create task: inspect the repository',
  });
  assert.equal(first.disposition, 'clarification');
  assert.equal(owner.snapshot().pending_confirmation?.form, `confirm task request ${token}`);

  const confirmed = await owner.submitText({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    operation: 'task.create',
    text: `confirm task request ${token}`,
  });

  assert.equal(confirmed.disposition, 'dispatched');
  assert.equal(confirmed.task_id, 'task-created-1');
  assert.equal(calls.length, 2);
  assert.equal(calls[0].method, PRODUCT_P3_TASK_INTENT_METHOD);
  assert.equal(calls[0].params.interaction_id, calls[1].params.interaction_id);
  assert.notEqual(calls[0].params.turn_id, calls[1].params.turn_id);
  assert.notEqual(calls[0].params.commit_id, calls[1].params.commit_id);
  assert.equal('confirmed' in calls[0].params, false);
  assert.equal('confirmed' in calls[1].params, false);
});

test('an idle pending clarification can be cancelled without a phantom transport lock', async () => {
  const storage = memoryStorage();
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: createSessionFormalTaskIntentRecoveryJournal(storage),
    request: async (_method, _params, requestId) => envelope(requestId, clarification('task.create')),
  });

  await owner.submitText({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    operation: 'task.create',
    text: 'create task: inspect the repository',
  });
  const cancelled = owner.cancelPendingConfirmation();

  assert.equal(cancelled.status, 'idle');
  assert.equal(cancelled.pending_confirmation, null);
  assert.equal(cancelled.retained_transport, false);
  assert.equal(storage.values.size, 0, 'explicit abandonment must clear the retained pending phase');
});

test('voice cancel forwards only the accepted TurnCommit identity and binds a later voice commit', async () => {
  const calls = [];
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async (_method, params, requestId) => {
      calls.push(params);
      return calls.length === 1
        ? envelope(requestId, clarification('task.cancel', 'task-abc_123'))
        : envelope(requestId, dispatched('task.cancel', 'task-abc_123', 'interaction-voice', 'voice'));
    },
  });
  const origin = {
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-voice',
    turn_id: 'turn-1',
    commit_id: 'commit-1',
  };

  await owner.submitVoice({ origin, operation: 'task.cancel', task_id: 'task-abc_123' });
  await owner.submitVoice({
    origin: { ...origin, turn_id: 'turn-2', commit_id: 'commit-2' },
    operation: 'task.cancel',
    task_id: 'task-abc_123',
  });

  assert.equal(calls.length, 2);
  assert.equal(calls[0].source, 'voice');
  assert.equal('text' in calls[0], false);
  assert.equal('committed_at' in calls[0], false);
  assert.equal(calls[1].interaction_id, calls[0].interaction_id);
  assert.notEqual(calls[1].commit_id, calls[0].commit_id);
});

test('S8.5 revision is separately gated, voice-only and confirmation-bound', async () => {
  const origin = {
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    interaction_id: 'interaction-revision',
    turn_id: 'turn-revision-1',
    commit_id: 'commit-revision-1',
  };
  let disabledCalls = 0;
  const disabled = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async () => {
      disabledCalls += 1;
      throw new Error('must not dispatch');
    },
  });
  await assert.rejects(
    disabled.submitVoice({ origin, operation: 'task.provide_input', task_id: 'task-abc_123' }),
    /revision route is disabled/
  );
  assert.equal(disabledCalls, 0);
  assert.equal(disabled.snapshot().reason, 'TASK_REVISION_PRODUCT_ROUTE_DISABLED');

  const calls = [];
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    task_revision_enabled: true,
    request: async (_method, params, requestId) => {
      calls.push(params);
      return calls.length === 1
        ? envelope(requestId, {
            ...clarification('task.provide_input', 'task-abc_123'),
            reason: 'TASK_REVISION_CONFIRMATION_REQUIRED',
          })
        : envelope(
            requestId,
            {
              ...dispatched('task.provide_input', 'task-abc_123', 'interaction-revision', 'voice'),
              reason: 'TASK_REVISION_ACCEPTED',
            }
          );
    },
  });
  await assert.rejects(
    owner.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.provide_input',
      task_id: 'task-abc_123',
      text: 'provide task input: preserve negative inputs',
    }),
    /committed voice origin/
  );
  assert.equal(owner.snapshot().reason, 'TASK_REVISION_VOICE_ORIGIN_REQUIRED');
  const first = await owner.submitVoice({
    origin,
    operation: 'task.provide_input',
    task_id: 'task-abc_123',
  });
  assert.equal(first.reason, 'TASK_REVISION_CONFIRMATION_REQUIRED');
  assert.equal(owner.snapshot().pending_confirmation?.operation, 'task.provide_input');
  const confirmed = await owner.submitVoice({
    origin: { ...origin, turn_id: 'turn-revision-2', commit_id: 'commit-revision-2' },
    operation: 'task.provide_input',
    task_id: 'task-abc_123',
  });
  assert.equal(confirmed.disposition, 'dispatched');
  assert.equal(confirmed.reason, 'TASK_REVISION_ACCEPTED');
  assert.equal(calls.length, 2);
});

test('pending confirmation cannot change task, operation, source or scope and sends zero request', async () => {
  let calls = 0;
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async (_method, _params, requestId) => {
      calls += 1;
      return envelope(requestId, clarification('task.cancel', 'task-abc_123'));
    },
  });
  await owner.submitText({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    operation: 'task.cancel',
    task_id: 'task-abc_123',
    text: 'cancel task task-abc_123',
  });

  await assert.rejects(
    owner.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.cancel',
      task_id: 'task-other',
      text: `confirm task request ${token}`,
    }),
    /cannot change/
  );
  assert.equal(calls, 1);
});

test('transport retry preserves the exact request and commit while changed input is fenced', async () => {
  const calls = [];
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async (_method, params, requestId) => {
      calls.push({ params, requestId });
      if (calls.length === 1) throw new Error('response lost');
      return envelope(requestId, dispatched('task.status', 'task-abc_123', params.interaction_id));
    },
  });
  const input = {
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    operation: 'task.status',
    task_id: 'task-abc_123',
    text: 'task status task-abc_123',
  };
  await assert.rejects(owner.submitText(input), /response lost/);
  await assert.rejects(owner.submitText({ ...input, text: 'status task task-abc_123' }), /another formal task intent/);
  const replay = await owner.submitText(input);

  assert.equal(replay.disposition, 'dispatched');
  assert.equal(calls.length, 2);
  assert.equal(calls[0].requestId, calls[1].requestId);
  assert.deepEqual(calls[0].params, calls[1].params);
});

test('disconnect close fences a late response and clears pending destructive authority', async () => {
  let settle;
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: (_method, _params, requestId) =>
      new Promise(resolve => {
        settle = () => resolve(envelope(requestId, clarification('task.create')));
      }),
  });

  const pending = owner.submitText({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    operation: 'task.create',
    text: 'create task: inspect the repository',
  });
  const closed = owner.close();
  settle();

  assert.equal(closed.status, 'closed');
  assert.equal(closed.pending_confirmation, null);
  assert.equal(closed.retained_transport, false);
  await assert.rejects(pending, /stale/);
  assert.equal(owner.snapshot().status, 'closed');
  assert.equal(owner.snapshot().pending_confirmation, null);
  assert.equal(owner.snapshot().retained_transport, false);
});

test('response loss reconnect recovers one exact side effect from a content-free checkpoint', async () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  const calls = [];
  let sideEffects = 0;
  const request = async (method, params, requestId) => {
    calls.push({ method, params, requestId });
    if (method === PRODUCT_P3_TASK_INTENT_METHOD) {
      sideEffects += 1;
      throw new Error('response lost');
    }
    assert.equal(method, PRODUCT_P3_TASK_INTENT_STATUS_METHOD);
    const original = calls[0];
    return envelope(requestId, {
      status: 'settled',
      phase: 'final',
      intent_request_id: original.requestId,
      source: 'text',
      intent: dispatched('task.create', 'task-recovered-1', original.params.interaction_id),
    });
  };
  const first = new ProductFormalTaskIntentOwner({ enabled: true, request, recovery_journal: journal });
  await assert.rejects(
    first.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.create',
      text: 'create task: SENTINEL_PRIVATE_INSTRUCTION',
    }),
    /response lost/
  );
  const encoded = [...storage.values.values()][0];
  assert.equal(typeof encoded, 'string');
  assert.equal(encoded.includes('SENTINEL_PRIVATE_INSTRUCTION'), false);
  assert.equal(encoded.includes('text'), true, 'source kind is an allowed control binding');
  assert.equal(encoded.includes('turn_id'), false);
  assert.equal(encoded.includes('commit_id'), false);
  first.close();

  const successor = new ProductFormalTaskIntentOwner({ enabled: true, request, recovery_journal: journal });
  const recovered = await successor.recoverPending({ session_id: 'session-1', correlation_id: 'correlation-1' });

  assert.equal(recovered?.disposition, 'dispatched');
  assert.equal(recovered?.task_id, 'task-recovered-1');
  assert.equal(sideEffects, 1);
  assert.equal(calls.length, 2);
  assert.deepEqual(Object.keys(calls[1].params).sort(), ['correlation_id', 'intent_request_id', 'session_id']);
  assert.equal(storage.values.size, 0);
});

test('response-lost clarification remounts as the same pending confirmation without replaying a mutation', async () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  const calls = [];
  let mutations = 0;
  const request = async (method, params, requestId) => {
    calls.push({ method, params, requestId });
    if (method === PRODUCT_P3_TASK_INTENT_STATUS_METHOD) {
      return envelope(requestId, {
        status: 'pending',
        phase: 'awaiting_confirmation',
        intent_request_id: calls[0].requestId,
        source: 'text',
        intent: clarification('task.create'),
      });
    }
    if (calls.filter(call => call.method === PRODUCT_P3_TASK_INTENT_METHOD).length === 1) {
      throw new Error('clarification response lost');
    }
    mutations += 1;
    return envelope(requestId, dispatched('task.create', 'task-confirmed-1', params.interaction_id));
  };
  const first = new ProductFormalTaskIntentOwner({ enabled: true, request, recovery_journal: journal });
  await assert.rejects(
    first.submitText({
      session_id: 'session-pending',
      correlation_id: 'correlation-pending',
      operation: 'task.create',
      text: 'create task: SENTINEL_PENDING_INSTRUCTION',
    }),
    /response lost/
  );
  first.close();

  const successor = new ProductFormalTaskIntentOwner({ enabled: true, request, recovery_journal: journal });
  const recovered = await successor.recoverPending({
    session_id: 'session-pending',
    correlation_id: 'correlation-pending',
  });
  assert.equal(recovered?.disposition, 'clarification');
  assert.equal(successor.snapshot().pending_confirmation?.token, token);
  assert.equal(mutations, 0);
  const retained = [...storage.values.values()][0];
  assert.equal(retained.includes('awaiting_confirmation'), true);
  assert.equal(retained.includes('SENTINEL_PENDING_INSTRUCTION'), false);
  assert.equal(retained.includes(token), false);

  const final = await successor.submitText({
    session_id: 'session-pending',
    correlation_id: 'correlation-pending',
    operation: 'task.create',
    text: `confirm task request ${token}`,
  });
  assert.equal(final.disposition, 'dispatched');
  assert.equal(mutations, 1);
  assert.equal(storage.values.size, 0);
  assert.equal(calls.filter(call => call.method === PRODUCT_P3_TASK_INTENT_STATUS_METHOD).length, 1);
});

test('content-free clarification without a destructive token survives remount until explicit scope abandonment', async () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  const calls = [];
  const unclear = {
    ...clarification('task.status', 'task-abc_123'),
    operation: null,
    task_id: null,
    source_span: null,
    target_span: null,
    confirmation_token: null,
    confirmation_form: null,
  };
  const request = async (method, params, requestId) => {
    calls.push({ method, params, requestId });
    if (method === PRODUCT_P3_TASK_INTENT_METHOD) throw new Error('clarification response lost');
    return envelope(requestId, {
      status: 'pending',
      phase: 'clarification',
      intent_request_id: calls[0].requestId,
      source: 'text',
      intent: unclear,
    });
  };
  const first = new ProductFormalTaskIntentOwner({ enabled: true, request, recovery_journal: journal });
  await assert.rejects(
    first.submitText({
      session_id: 'session-clarification',
      correlation_id: 'correlation-clarification',
      operation: 'task.status',
      task_id: 'task-abc_123',
      text: 'what is its task status',
    }),
    /response lost/
  );
  first.close();

  const successor = new ProductFormalTaskIntentOwner({ enabled: true, request, recovery_journal: journal });
  const recovered = await successor.recoverPending({
    session_id: 'session-clarification',
    correlation_id: 'correlation-clarification',
  });
  assert.equal(recovered?.disposition, 'clarification');
  assert.equal(recovered?.confirmation_token, null);
  assert.equal(successor.snapshot().status, 'clarification');
  assert.equal(storage.values.size, 1);
  assert.equal(calls.filter(call => call.method === PRODUCT_P3_TASK_INTENT_METHOD).length, 1);
  successor.close({ abandon_scope: true });
  assert.equal(storage.values.size, 0);
});

test('expired confirmation recovery clears the exact CAS-owned checkpoint without replaying mutation', async () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  let mutationCalls = 0;
  const first = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: journal,
    request: async method => {
      assert.equal(method, PRODUCT_P3_TASK_INTENT_METHOD);
      mutationCalls += 1;
      throw new Error('response lost');
    },
  });
  await assert.rejects(
    first.submitText({
      session_id: 'session-expired',
      correlation_id: 'correlation-expired',
      operation: 'task.create',
      text: 'create task: bounded expiry proof',
    }),
    /response lost/
  );
  first.close();

  const successor = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: journal,
    request: async (method, params, requestId) => {
      assert.equal(method, PRODUCT_P3_TASK_INTENT_STATUS_METHOD);
      return envelope(requestId, {
        status: 'expired',
        phase: 'expired',
        intent_request_id: params.intent_request_id,
        source: 'text',
        intent: null,
      });
    },
  });
  assert.equal(
    await successor.recoverPending({ session_id: 'session-expired', correlation_id: 'correlation-expired' }),
    null
  );
  assert.equal(successor.snapshot().status, 'rejected');
  assert.equal(successor.snapshot().reason, 'TASK_INTENT_CONFIRMATION_EXPIRED');
  assert.equal(mutationCalls, 1);
  assert.equal(storage.values.size, 0);
});

test('clarification phase CAS failure is a stable failed state and never creates a second request', async () => {
  let calls = 0;
  const journal = {
    load: () => null,
    save: () => {},
    claim: checkpoint => checkpoint,
    replace: () => {
      throw new Error('stale owner');
    },
    clear: () => {},
  };
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: journal,
    request: async (_method, _params, requestId) => {
      calls += 1;
      return envelope(requestId, clarification('task.create'));
    },
  });
  await assert.rejects(
    owner.submitText({
      session_id: 'session-cas-failed',
      correlation_id: 'correlation-cas-failed',
      operation: 'task.create',
      text: 'create task: bounded CAS proof',
    }),
    /stale owner/
  );
  assert.equal(owner.snapshot().status, 'failed');
  assert.equal(owner.snapshot().reason, 'FORMAL_TASK_INTENT_REQUEST_FAILED');
  assert.equal(calls, 1);
});

test('content-free recovery journals isolate sessions and use a distinct product namespace', () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  const checkpoint = sessionId => ({
    schema: 'live-voice.formal-task-intent-recovery.v2',
    revision: 2,
    phase: 'resolving',
    owner_id: `owner-${sessionId}`,
    generation: 1,
    request_id: `request-${sessionId}`,
    session_id: sessionId,
    correlation_id: `correlation-${sessionId}`,
    interaction_id: `interaction-${sessionId}`,
    source: 'text',
    operation: 'task.create',
    task_id: null,
  });
  journal.save(checkpoint('session-1'));
  journal.save(checkpoint('session-2'));

  assert.equal(storage.values.size, 1);
  assert.deepEqual([...storage.values.keys()], ['jiuwenswarm.liveVoice.formalTaskIntentRecovery.v2']);
  assert.equal([...storage.values.keys()].some(key => key.includes('productP2ActivationJournal')), false);
  assert.equal(journal.load('session-1').request_id, 'request-session-1');
  assert.equal(journal.load('session-2').request_id, 'request-session-2');
  journal.clear(journal.load('session-1'));
  assert.equal(journal.load('session-1'), null);
  assert.equal(journal.load('session-2').request_id, 'request-session-2');
});

test('recovery journal uses exact owner CAS and a fixed bounded key capacity', () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  const checkpoint = index => ({
    schema: 'live-voice.formal-task-intent-recovery.v2',
    revision: 2,
    phase: 'resolving',
    owner_id: `owner-${index}`,
    generation: 1,
    request_id: `request-${index}`,
    session_id: `session-${index}`,
    correlation_id: `correlation-${index}`,
    interaction_id: `interaction-${index}`,
    source: 'text',
    operation: 'task.create',
    task_id: null,
  });
  const stale = checkpoint(0);
  journal.save(stale);
  const claimed = journal.claim(stale, 'owner-successor');
  assert.equal(claimed.generation, 2);
  assert.throws(() => journal.clear(stale), /ownership changed/);
  assert.equal(journal.load('session-0').owner_id, 'owner-successor');
  for (let index = 1; index < 16; index += 1) journal.save(checkpoint(index));
  assert.equal(storage.values.size, 1);
  assert.throws(() => journal.save(checkpoint(16)), /capacity is full/);

  const unicodeStorage = memoryStorage();
  const unicodeJournal = createSessionFormalTaskIntentRecoveryJournal(unicodeStorage);
  assert.throws(
    () =>
      unicodeJournal.save({
        ...checkpoint(20),
        owner_id: '界'.repeat(128),
        request_id: '界'.repeat(256),
        session_id: '界'.repeat(256),
        correlation_id: '界'.repeat(256),
        interaction_id: '界'.repeat(256),
      }),
    /checkpoint is oversized/
  );
  assert.equal(unicodeStorage.values.size, 0);
});

test('checkpoint failure blocks the committed intent before network effects', async () => {
  let calls = 0;
  const journal = createSessionFormalTaskIntentRecoveryJournal({
    getItem: () => null,
    setItem: () => {
      throw new Error('private storage failure');
    },
    removeItem: () => {},
  });
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: journal,
    request: async () => {
      calls += 1;
      throw new Error('must not send');
    },
  });

  await assert.rejects(
    owner.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.status',
      task_id: 'task-abc_123',
      text: 'task status task-abc_123',
    }),
    /checkpoint failed/
  );
  assert.equal(calls, 0);
});

test('corrupt recovery checkpoint fails closed before status transport', async () => {
  const storage = memoryStorage();
  storage.values.set(
    'jiuwenswarm.liveVoice.formalTaskIntentRecovery.v2',
    '{"instruction":"SENTINEL_CORRUPT_CHECKPOINT"}'
  );
  let calls = 0;
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: createSessionFormalTaskIntentRecoveryJournal(storage),
    request: async () => {
      calls += 1;
      throw new Error('must not query status');
    },
  });

  await assert.rejects(
    owner.recoverPending({ session_id: 'session-1', correlation_id: 'correlation-1' }),
    /checkpoint is invalid/
  );
  assert.equal(calls, 0);
  assert.equal(owner.snapshot().reason, 'FORMAL_TASK_INTENT_RECOVERY_CHECKPOINT_INVALID');
  assert.equal(owner.snapshot().retained_transport, true);
  assert.equal(JSON.stringify(owner.snapshot()).includes('SENTINEL_CORRUPT_CHECKPOINT'), false);
  await assert.rejects(
    owner.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.create',
      text: 'create task: must stay blocked',
    }),
    /recovery is active/
  );
  assert.equal(calls, 0);
});

test('recovery binding mismatch is a retained zero-network barrier', async () => {
  const storage = memoryStorage();
  const journal = createSessionFormalTaskIntentRecoveryJournal(storage);
  journal.save({
    schema: 'live-voice.formal-task-intent-recovery.v2',
    revision: 2,
    phase: 'resolving',
    owner_id: 'owner-pending',
    generation: 1,
    request_id: 'request-pending',
    session_id: 'session-1',
    correlation_id: 'correlation-original',
    interaction_id: 'interaction-original',
    source: 'text',
    operation: 'task.create',
    task_id: null,
  });
  let calls = 0;
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    recovery_journal: journal,
    request: async () => {
      calls += 1;
      throw new Error('must not query a foreign binding');
    },
  });

  await assert.rejects(
    owner.recoverPending({ session_id: 'session-1', correlation_id: 'correlation-successor' }),
    /binding mismatch/
  );
  assert.equal(calls, 0);
  assert.equal(owner.snapshot().retained_transport, true);
  assert.equal(owner.snapshot().reason, 'FORMAL_TASK_INTENT_RECOVERY_BINDING_MISMATCH');
});

test('transport exception content is never retained in the UI-facing owner snapshot', async () => {
  const sentinel = 'SENTINEL_PROVIDER_SECRET_TRANSCRIPT';
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async () => {
      throw new Error(sentinel);
    },
  });

  await assert.rejects(
    owner.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.create',
      text: 'create task: bounded request',
    }),
    new RegExp(sentinel)
  );
  const snapshot = owner.snapshot();
  assert.equal(snapshot.status, 'failed');
  assert.equal(snapshot.reason, 'FORMAL_TASK_INTENT_REQUEST_FAILED');
  assert.equal(JSON.stringify(snapshot).includes(sentinel), false);
});

test('forged target response and flag-off both fail closed', async () => {
  let calls = 0;
  const owner = new ProductFormalTaskIntentOwner({
    enabled: true,
    request: async (_method, params, requestId) => {
      calls += 1;
      return envelope(requestId, dispatched('task.status', 'task-foreign', params.interaction_id));
    },
  });
  await assert.rejects(
    owner.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.status',
      task_id: 'task-abc_123',
      text: 'task status task-abc_123',
    }),
    /target binding mismatch/
  );
  assert.equal(calls, 1);

  const disabled = new ProductFormalTaskIntentOwner({
    enabled: false,
    request: async () => {
      calls += 1;
      throw new Error('must not be called');
    },
  });
  await assert.rejects(
    disabled.submitText({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      operation: 'task.create',
      text: 'create task: inspect the repository',
    }),
    /disabled/
  );
  assert.equal(calls, 1);
});
