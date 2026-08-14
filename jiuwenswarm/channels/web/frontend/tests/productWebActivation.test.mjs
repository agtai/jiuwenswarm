import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_P2_ACTIVATE_METHOD,
  PRODUCT_P2_CLOSE_METHOD,
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_PRESENTATION_ACK_METHOD,
  PRODUCT_P2_BARGE_IN_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
  PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
  PRODUCT_P3_PROGRESS_CLOSE_METHOD,
  PRODUCT_P3_TASK_LIST_METHOD,
  PRODUCT_P3_CONFIRMATION_ISSUE_METHOD,
  PRODUCT_P3_MUTATE_METHOD,
  ProductWebP2ActivationOwner,
  ProductWebP3MutationOwner,
  ProductWebP3ProgressOwner,
  pollProductP2RouteWithRecovery,
  replayProductP2DurableOperation,
  retryRetainedProductOperation,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';

function p3TaskControlBinding() {
  return {
    subject_id: 'subject-1',
    session_id: 'session-1',
    project_id: 'project-1',
    correlation_id: 'correlation-1',
    generation: 1,
  };
}

function p3ConfirmationResult(confirmationId = 'confirmation-1') {
  return {
    status: 'confirmation_issued',
    operation: 'task.cancel',
    command_id: 'command-1',
    target_task_id: 'task-1',
    confirmation_id: confirmationId,
    expires_at: '2026-08-07T10:02:00Z',
    task_control_binding: p3TaskControlBinding(),
  };
}

function p3MutationResult() {
  return {
    status: 'mutation_processed',
    operation: 'task.cancel',
    command_id: 'command-1',
    target_task_id: 'task-1',
    formal_task_result: {
      task_id: 'task-1',
      attempt_id: 'attempt-1',
      cancel_acknowledged: true,
      applied: true,
      state: 'running',
      outbox_id: 'outbox-cancel-1',
    },
  };
}

function p3ProgressResult(status, binding, overrides = {}) {
  return {
    status,
    ...binding,
    ...(status === 'active'
      ? {
          requested_origin_kind: 'text',
          origin_kind: 'text',
          voice_progress: 'unavailable',
          voice_reason: 'TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE',
          fallback_reason: null,
        }
      : {}),
    ...overrides,
  };
}

test('retained product retries reuse the exact operation after transport loss', async () => {
  let calls = 0;
  const result = await retryRetainedProductOperation({
    operation: async () => {
      calls += 1;
      if (calls < 3) {
        const error = new Error('response lost');
        error.code = 'REQUEST_TIMEOUT';
        error.retriable = true;
        throw error;
      }
      return 'replayed';
    },
    is_current: () => true,
    retry_delays_ms: [0, 0],
  });

  assert.equal(result, 'replayed');
  assert.equal(calls, 3);
});

test('retained product retries stop on authoritative failure or stale ownership', async () => {
  let authoritativeCalls = 0;
  await assert.rejects(
    retryRetainedProductOperation({
      operation: async () => {
        authoritativeCalls += 1;
        throw new Error('denied');
      },
      is_current: () => true,
      retry_delays_ms: [0, 0],
    }),
    /denied/
  );

  let current = true;
  let transportCalls = 0;
  await assert.rejects(
    retryRetainedProductOperation({
      operation: async () => {
        transportCalls += 1;
        current = false;
        const error = new Error('response lost');
        error.code = 'REQUEST_TIMEOUT';
        error.retriable = true;
        throw error;
      },
      is_current: () => current,
      retry_delays_ms: [0, 0],
    }),
    /response lost/
  );

  assert.equal(authoritativeCalls, 1);
  assert.equal(transportCalls, 1);
});

test('closed P2 notification settles definitively so reconnect can reactivate', async () => {
  let calls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      calls += 1;
      const error = webError('notification stream closed', 'UNAVAILABLE');
      error.reason = 'NOTIFICATION_STREAM_CLOSED';
      throw error;
    },
  });
  await owner.start(binding);

  await assert.rejects(
    retryRetainedProductOperation({
      operation: () => owner.nextNotification(),
      is_current: () => true,
      retry_delays_ms: [0, 0],
    }),
    /notification stream closed/
  );

  assert.equal(calls, 1);
  assert.equal(owner.hasPendingNotification(), false);
});

test('panel recovery coordinator closes an idle poll before activating the next generation', async () => {
  const calls = [];
  const request = async (method, params, requestId) => {
    calls.push([method, params, requestId]);
    if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active', params);
    if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
      const error = webError('notification stream closed', 'UNAVAILABLE');
      error.reason = 'NOTIFICATION_STREAM_CLOSED';
      throw error;
    }
    if (method === PRODUCT_P2_CLOSE_METHOD) return response('closed', params);
    throw new Error(`forbidden product effect: ${method}`);
  };
  const firstBinding = { ...binding, activation_id: 'activation-g1', activation_generation: 1 };
  const secondBinding = { ...binding, activation_id: 'activation-g2', activation_generation: 2 };
  const first = new ProductWebP2ActivationOwner({ enabled: true, request });
  await first.start(firstBinding);
  let current = first;

  const outcome = await pollProductP2RouteWithRecovery({
    owner: first,
    is_current: () => current === first,
    settle_retained_operations: async () => {
      if (first.hasPendingNotification()) await first.nextNotification();
    },
    can_activate_successor: () => current === first,
    activate_successor: async () => {
      const second = new ProductWebP2ActivationOwner({ enabled: true, request });
      current = second;
      await second.start(secondBinding);
      return second;
    },
  });

  assert.equal(outcome.kind, 'recovered');
  assert.equal(outcome.successor, current);
  assert.deepEqual(
    calls.map(([method, params]) => [method, params.activation_generation]),
    [
      [PRODUCT_P2_ACTIVATE_METHOD, 1],
      [PRODUCT_P2_NOTIFICATION_NEXT_METHOD, 1],
      [PRODUCT_P2_CLOSE_METHOD, 1],
      [PRODUCT_P2_ACTIVATE_METHOD, 2],
    ]
  );
  const notificationCalls = calls.filter(([method]) => method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD);
  assert.equal(notificationCalls.length, 1);
  assert.match(notificationCalls[0][2], /^live-voice-p2-notification-/);
  assert.equal(new Set(notificationCalls.map(([, , requestId]) => requestId)).size, 1);
  for (const forbidden of [PRODUCT_P2_SUBMIT_METHOD, PRODUCT_P2_PRESENTATION_ACK_METHOD, PRODUCT_P3_CONFIRMATION_ISSUE_METHOD, PRODUCT_P3_MUTATE_METHOD]) {
    assert.equal(calls.filter(([method]) => method === forbidden).length, 0, forbidden);
  }
});

const binding = Object.freeze({
  session_id: 'session-1',
  correlation_id: 'correlation-1',
  interaction_id: 'interaction-1',
  activation_id: 'activation-1',
  activation_generation: 1,
});

function response(status, changes = {}) {
  return {
    ok: true,
    result: {
      status,
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: binding.interaction_id,
      activation_id: binding.activation_id,
      activation_generation: binding.activation_generation,
      ...changes,
    },
  };
}

function durableResponse(requestId, status, changes = {}) {
  return {
    request_id: requestId,
    ok: true,
    result: {
      status,
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: binding.interaction_id,
      activation_id: binding.activation_id,
      activation_generation: binding.activation_generation,
      ...changes,
    },
    error: null,
  };
}

function agentSubmitResponse(requestId, params, changes = {}) {
  return durableResponse(requestId, 'round_accepted', {
    turn_id: params.turn_id,
    commit_id: params.commit_id,
    round_id: 'round-1',
    response: {
      interaction_id: params.interaction_id,
      response_id: params.response_id,
      response_generation: 0,
    },
    ...changes,
  });
}

function presentationAckResponse(requestId, changes = {}) {
  return durableResponse(requestId, 'presentation_acknowledged', {
    accepted: true,
    replayed: false,
    history_records_written: 1,
    history_pending: false,
    ...changes,
  });
}

function webError(message, code, retriable = false) {
  return Object.assign(new Error(message), { code, retriable });
}

test('feature-off owner allocates and calls nothing', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: false,
    request: async (...args) => calls.push(args),
  });

  assert.equal((await owner.start(binding)).status, 'disabled');
  assert.equal((await owner.close()).status, 'disabled');
  assert.deepEqual(calls, []);
});

test('stock Web activates and closes one exact credential-free binding', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return response(method === PRODUCT_P2_ACTIVATE_METHOD ? 'active' : 'closed');
    },
  });

  assert.equal((await owner.start(binding)).status, 'active');
  assert.equal((await owner.close()).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
  for (const [, params] of calls) {
    assert.deepEqual(params, binding);
    assert.equal('auth_token' in params, false);
  }
});

test('stock Web exposes authoritative activation replay truth for refresh recovery', async () => {
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method =>
      response(method === PRODUCT_P2_ACTIVATE_METHOD ? 'active' : 'closed', method === PRODUCT_P2_ACTIVATE_METHOD ? { replayed: true } : {}),
  });

  assert.equal(owner.activationWasReplayed(), null);
  await owner.start(binding);
  assert.equal(owner.activationWasReplayed(), true);
  await owner.close();
});

test('explicit media start refreshes one exact active P2 authority with singleflight', async () => {
  const calls = [];
  let resolveRefresh;
  const refresh = new Promise(resolve => {
    resolveRefresh = resolve;
  });
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD && calls.length === 2) return refresh;
      return response(method === PRODUCT_P2_CLOSE_METHOD ? 'closed' : 'active', {
        ...(method === PRODUCT_P2_ACTIVATE_METHOD ? { replayed: false } : {}),
      });
    },
  });

  await owner.start(binding);
  const first = owner.refreshMediaAuthority();
  const second = owner.refreshMediaAuthority();
  assert.equal(first, second);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1], [PRODUCT_P2_ACTIVATE_METHOD, binding]);
  resolveRefresh(response('active', { replayed: true }));

  assert.equal((await first).status, 'active');
  assert.equal(owner.activationWasReplayed(), true);
  await owner.close();
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
});

test('media authority refresh fails closed on a mismatched response and retains cleanup', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD && calls.length === 2) {
        return response('active', { interaction_id: 'other-interaction', replayed: true });
      }
      return response(method === PRODUCT_P2_CLOSE_METHOD ? 'closed' : 'active');
    },
  });

  await owner.start(binding);
  await assert.rejects(owner.refreshMediaAuthority(), /binding mismatch/);
  assert.equal(owner.snapshot().status, 'unavailable');
  assert.equal(owner.needsCleanup(), true);
  assert.equal((await owner.close()).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
});

test('media authority refresh rejects a newly allocated route instead of accepting it as a replay', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) {
        return response('active', { replayed: false });
      }
      return response('closed');
    },
  });

  await owner.start(binding);
  await assert.rejects(owner.refreshMediaAuthority(), /did not replay/);
  assert.equal(owner.snapshot().status, 'unavailable');
  assert.equal(owner.authorizesMediaStart(binding), false);
  assert.equal((await owner.close()).status, 'closed');
});

test('P2 close synchronously fences an in-flight media authority refresh before exact cleanup', async () => {
  const calls = [];
  let resolveRefresh;
  const refresh = new Promise(resolve => {
    resolveRefresh = resolve;
  });
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD && calls.length === 2) return refresh;
      return response(method === PRODUCT_P2_CLOSE_METHOD ? 'closed' : 'active');
    },
  });

  await owner.start(binding);
  const refreshing = owner.refreshMediaAuthority();
  const closing = owner.close();
  assert.equal(owner.authorizesMediaStart(binding), false);
  await Promise.resolve();
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD]
  );

  resolveRefresh(response('active', { replayed: true }));
  await assert.rejects(refreshing, /changed during media authority refresh/);
  assert.equal((await closing).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
});

test('P2 close cancels an atomically reserved media start before revoking exact authority', async () => {
  const calls = [];
  let rejectMediaStart;
  const mediaStart = new Promise((_resolve, reject) => {
    rejectMediaStart = reject;
  });
  let resolveCancellation;
  const cancellation = new Promise(resolve => {
    resolveCancellation = resolve;
  });
  let cancellationCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return response(method === PRODUCT_P2_CLOSE_METHOD ? 'closed' : 'active', {
        ...(method === PRODUCT_P2_ACTIVATE_METHOD ? { replayed: calls.length > 1 } : {}),
      });
    },
  });

  await owner.start(binding);
  await owner.refreshMediaAuthority();
  const starting = owner.runAuthorizedMediaStart(binding, {
    start: () => mediaStart,
    cancel: async () => {
      cancellationCalls += 1;
      rejectMediaStart(new Error('local media start cancelled'));
      await cancellation;
    },
  });
  const startOutcome = starting.catch(error => error);
  const closing = owner.close();
  assert.equal(cancellationCalls, 1);
  assert.equal(owner.authorizesMediaStart(binding), false);
  await assert.rejects(
    owner.runAuthorizedMediaStart(binding, { start: async () => undefined, cancel: async () => undefined }),
    /not current/
  );
  await Promise.resolve();
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD]
  );

  resolveCancellation();
  assert.match((await startOutcome).message, /local media start cancelled/);
  assert.equal((await closing).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
});

test('P2 owner publishes its construction snapshot without route allocation', () => {
  const snapshots = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async () => {
      throw new Error('construction must not allocate a route');
    },
    on_snapshot: snapshot => snapshots.push(snapshot),
  });

  assert.equal(owner.snapshot().status, 'idle');
  assert.deepEqual(
    snapshots.map(snapshot => snapshot.status),
    ['idle']
  );
});

test('active stock Web owner submits text, polls output, and ACKs exact presentation', async () => {
  const calls = [];
  const bound = (status, extra = {}) => ({
    ok: true,
    result: { status, ...binding, ...extra },
  });
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      if (method === PRODUCT_P2_SUBMIT_METHOD) {
        return agentSubmitResponse(requestId, params);
      }
      if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
        return bound('notification', { kind: 'agent.output' });
      }
      if (method === PRODUCT_P2_PRESENTATION_ACK_METHOD) {
        return presentationAckResponse(requestId);
      }
      return response('closed');
    },
  });
  await owner.start(binding);

  assert.equal(
    (
      await owner.submitText({
        commit_id: 'commit-1',
        turn_id: 'turn-1',
        response_id: 'response-1',
        committed_at: '2026-08-07T10:00:00Z',
        text: '  preserve exact text  ',
      })
    ).status,
    'round_accepted'
  );
  assert.equal((await owner.nextNotification()).kind, 'agent.output');
  assert.equal(
    (
      await owner.acknowledgePresentation({
        response_id: 'response-1',
        response_generation: 0,
        surface: 'text',
        unit_id: 'unit-1',
        contiguous_cursor: 0,
        presented_at: '2026-08-07T10:00:01Z',
      })
    ).accepted,
    true
  );

  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_SUBMIT_METHOD, PRODUCT_P2_NOTIFICATION_NEXT_METHOD, PRODUCT_P2_PRESENTATION_ACK_METHOD]
  );
  assert.equal(calls[1][1].text, '  preserve exact text  ');
  assert.equal(calls[2][1].notification_sequence, 1);
  for (const [, params] of calls) assert.equal('auth_token' in params, false);
});

test('durable submit ACK and barge-in checkpoint before transport and settle only after exact validation', async () => {
  const effects = [];
  const journal = {
    checkpointOperation: operation => effects.push(['checkpoint', operation]),
    settleOperation: operation => effects.push(['settle', operation]),
  };
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    durable_operation_journal: journal,
    request: async (method, params, requestId) => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      effects.push(['request', { method, request_id: requestId, params }]);
      if (method === PRODUCT_P2_SUBMIT_METHOD) return agentSubmitResponse(requestId, params);
      if (method === PRODUCT_P2_PRESENTATION_ACK_METHOD) return presentationAckResponse(requestId);
      if (method === PRODUCT_P2_BARGE_IN_METHOD) {
        return durableResponse(requestId, 'barge_in_applied', {
          action_id: params.action_id,
          response_id: params.response_id,
          response_generation: params.response_generation,
          cancel_response: params.cancel_response,
          applied: true,
          replayed: false,
          effect_ids: ['effect-1'],
        });
      }
      throw new Error(`unexpected ${method}`);
    },
  });
  await owner.start(binding);

  await owner.submitText({
    commit_id: 'commit-durable',
    turn_id: 'turn-durable',
    response_id: 'response-durable',
    committed_at: '2026-08-10T00:00:00Z',
    text: 'durable turn',
  });
  await owner.acknowledgePresentation({
    response_id: 'response-durable',
    response_generation: 0,
    surface: 'text',
    unit_id: 'unit-durable',
    contiguous_cursor: 12,
    presented_at: '2026-08-10T00:00:01Z',
  });
  await owner.bargeIn({
    action_id: 'barge-durable',
    response_id: 'response-durable',
    response_generation: 0,
    cancel_response: true,
  });

  assert.deepEqual(
    effects.map(([kind, operation]) => [kind, operation.method]),
    [
      ['checkpoint', PRODUCT_P2_SUBMIT_METHOD],
      ['request', PRODUCT_P2_SUBMIT_METHOD],
      ['settle', PRODUCT_P2_SUBMIT_METHOD],
      ['checkpoint', PRODUCT_P2_PRESENTATION_ACK_METHOD],
      ['request', PRODUCT_P2_PRESENTATION_ACK_METHOD],
      ['settle', PRODUCT_P2_PRESENTATION_ACK_METHOD],
      ['checkpoint', PRODUCT_P2_BARGE_IN_METHOD],
      ['request', PRODUCT_P2_BARGE_IN_METHOD],
      ['settle', PRODUCT_P2_BARGE_IN_METHOD],
    ]
  );
  for (let index = 0; index < effects.length; index += 3) {
    assert.deepEqual(effects[index][1], effects[index + 1][1]);
    assert.deepEqual(effects[index][1], effects[index + 2][1]);
  }
});

test('durable checkpoint failure creates zero submit ACK or barge-in transport effect', async () => {
  const operations = [
    owner =>
      owner.submitText({
        commit_id: 'commit-blocked',
        turn_id: 'turn-blocked',
        response_id: 'response-blocked',
        committed_at: '2026-08-10T00:00:00Z',
        text: 'blocked turn',
      }),
    owner =>
      owner.acknowledgePresentation({
        response_id: 'response-blocked',
        response_generation: 0,
        surface: 'text',
        unit_id: 'unit-blocked',
        contiguous_cursor: 0,
        presented_at: '2026-08-10T00:00:01Z',
      }),
    owner =>
      owner.bargeIn({
        action_id: 'barge-blocked',
        response_id: 'response-blocked',
        response_generation: 0,
        cancel_response: true,
      }),
  ];

  for (const invoke of operations) {
    let businessCalls = 0;
    const owner = new ProductWebP2ActivationOwner({
      enabled: true,
      durable_operation_journal: {
        checkpointOperation: () => {
          throw new Error('checkpoint unavailable');
        },
        settleOperation: () => {
          throw new Error('settle must not run');
        },
      },
      request: async method => {
        if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
        businessCalls += 1;
        throw new Error('business request must not run');
      },
    });
    await owner.start(binding);
    await assert.rejects(invoke(owner), /checkpoint unavailable/);
    assert.equal(businessCalls, 0);
  }
});

test('direct durable replay reuses the exact request and accepts a server-owned task response', async () => {
  const operation = {
    method: PRODUCT_P2_SUBMIT_METHOD,
    request_id: 'request-task-replay',
    params: {
      ...binding,
      commit_id: 'commit-task-replay',
      turn_id: 'turn-task-replay',
      committed_at: '2026-08-10T00:00:00Z',
      text: 'create from voice',
      dispatch_target: 'task',
      voice_commit_receipt: 'r'.repeat(32),
      critical_confirmation: true,
    },
  };
  const calls = [];
  const result = await replayProductP2DurableOperation({
    operation,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      return durableResponse(requestId, 'task_origin_accepted', {
        turn_id: operation.params.turn_id,
        commit_id: operation.params.commit_id,
        response: {
          interaction_id: binding.interaction_id,
          response_id: 'server-response-task-replay',
          response_generation: 0,
        },
      });
    },
  });

  assert.equal(result.response.response_id, 'server-response-task-replay');
  assert.deepEqual(calls, [[operation.method, operation.params, operation.request_id]]);
});

test('direct durable replay rejects malformed or secret-bearing envelopes before transport', async () => {
  const valid = {
    method: PRODUCT_P2_SUBMIT_METHOD,
    request_id: 'request-task-replay-invalid',
    params: {
      ...binding,
      commit_id: 'commit-task-replay-invalid',
      turn_id: 'turn-task-replay-invalid',
      committed_at: '2026-08-10T00:00:00Z',
      text: 'create from voice',
      dispatch_target: 'task',
      voice_commit_receipt: 'r'.repeat(32),
      critical_confirmation: true,
    },
  };
  const malformed = [
    { ...valid, method: PRODUCT_P2_NOTIFICATION_NEXT_METHOD },
    { ...valid, auth_token: 'secret' },
    { ...valid, params: { ...valid.params, raw_audio: 'secret-audio' } },
    { ...valid, params: { ...valid.params, activation_generation: 0 } },
    { ...valid, params: { ...valid.params, session_id: '' } },
  ];
  let calls = 0;

  for (const operation of malformed) {
    await assert.rejects(
      replayProductP2DurableOperation({
        operation,
        request: async () => {
          calls += 1;
          throw new Error('transport must not run');
        },
      }),
      /durable product|activation_generation|session_id/
    );
  }

  assert.equal(calls, 0);
});

test('direct durable replay rejects foreign envelopes and forged canonical operation results', async () => {
  const agentOperation = {
    method: PRODUCT_P2_SUBMIT_METHOD,
    request_id: 'request-agent-result-binding',
    params: {
      ...binding,
      commit_id: 'commit-agent-result-binding',
      turn_id: 'turn-agent-result-binding',
      response_id: 'response-agent-result-binding',
      committed_at: '2026-08-10T00:00:00Z',
      text: 'agent result binding',
      dispatch_target: 'agent',
    },
  };
  const validAgentResult = {
    turn_id: agentOperation.params.turn_id,
    commit_id: agentOperation.params.commit_id,
    round_id: 'round-agent-result-binding',
    response: {
      interaction_id: binding.interaction_id,
      response_id: agentOperation.params.response_id,
      response_generation: 0,
    },
  };
  const invalidAgentEnvelopes = [
    durableResponse('foreign-request', 'round_accepted', validAgentResult),
    { ...durableResponse(agentOperation.request_id, 'round_accepted', validAgentResult), ok: 1 },
    { ...durableResponse(agentOperation.request_id, 'round_accepted', validAgentResult), error: {} },
    durableResponse(agentOperation.request_id, 'round_accepted', { ...validAgentResult, turn_id: 'foreign-turn' }),
    durableResponse(agentOperation.request_id, 'round_accepted', { ...validAgentResult, response: undefined }),
    durableResponse(agentOperation.request_id, 'round_accepted', {
      ...validAgentResult,
      response: { ...validAgentResult.response, response_id: 'foreign-response' },
    }),
  ];

  for (const envelope of invalidAgentEnvelopes) {
    await assert.rejects(
      replayProductP2DurableOperation({
        operation: agentOperation,
        request: async () => envelope,
      }),
      /request|response|binding|unavailable/
    );
  }

  const ackOperation = {
    method: PRODUCT_P2_PRESENTATION_ACK_METHOD,
    request_id: 'request-ack-result-binding',
    params: {
      ...binding,
      response_id: 'response-ack-result-binding',
      response_generation: 0,
      surface: 'text',
      unit_id: 'unit-ack-result-binding',
      contiguous_cursor: 0,
      presented_at: '2026-08-10T00:00:01Z',
    },
  };
  for (const changes of [
    { accepted: true },
    { accepted: true, replayed: false, history_records_written: -1, history_pending: false },
    { accepted: false, replayed: false, history_records_written: 1, history_pending: false },
    { accepted: true, replayed: false, history_records_written: 1, history_pending: true },
    { accepted: true, replayed: 'false', history_records_written: 1, history_pending: false },
  ]) {
    await assert.rejects(
      replayProductP2DurableOperation({
        operation: ackOperation,
        request: async () => durableResponse(ackOperation.request_id, 'presentation_acknowledged', changes),
      }),
      /ACK|binding/
    );
  }
});

test('task submit rejects a client response id and UTF-8 overflow before transport', async () => {
  const valid = {
    method: PRODUCT_P2_SUBMIT_METHOD,
    request_id: 'request-task-strict-envelope',
    params: {
      ...binding,
      commit_id: 'commit-task-strict-envelope',
      turn_id: 'turn-task-strict-envelope',
      committed_at: '2026-08-10T00:00:00Z',
      text: 'create from voice',
      dispatch_target: 'task',
      voice_commit_receipt: 'r'.repeat(32),
      critical_confirmation: true,
    },
  };
  let calls = 0;
  for (const operation of [
    { ...valid, params: { ...valid.params, response_id: 'client-forged-response' } },
    { ...valid, params: { ...valid.params, text: '你'.repeat(45_000) } },
  ]) {
    await assert.rejects(
      replayProductP2DurableOperation({
        operation,
        request: async () => {
          calls += 1;
          return durableResponse(operation.request_id, 'task_origin_accepted', {
            turn_id: operation.params.turn_id,
            commit_id: operation.params.commit_id,
            response: {
              interaction_id: binding.interaction_id,
              response_id: 'server-owned-response',
              response_generation: 0,
            },
          });
        },
      }),
      /unexpected fields|bound/
    );
  }
  assert.equal(calls, 0);
});

test('task-origin submit requires the exact canonical CR response binding', async () => {
  const turn = {
    commit_id: 'commit-task-origin',
    turn_id: 'turn-task-origin',
    committed_at: '2026-08-07T10:00:00Z',
    text: 'create the task from this voice turn',
    dispatch_target: 'task',
    voice_commit_receipt: 'receipt-task-origin',
  };
  const makeOwner = submitResult =>
    new ProductWebP2ActivationOwner({
      enabled: true,
      request: async (method, params, requestId) => {
        if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
        assert.equal('response_id' in params, false);
        return durableResponse(requestId, 'task_origin_accepted', {
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          ...submitResult,
        });
      },
    });

  const missingResponse = makeOwner({});
  await missingResponse.start(binding);
  await assert.rejects(missingResponse.submitText(turn), /task_origin_accepted response binding mismatch/);

  const conflictingResponse = makeOwner({
    response: {
      interaction_id: 'interaction-foreign',
      response_id: 'server-owned-response',
      response_generation: 0,
    },
  });
  await conflictingResponse.start(binding);
  await assert.rejects(conflictingResponse.submitText(turn), /task_origin_accepted response binding mismatch/);

  const serverOwnedResponse = makeOwner({
    response: {
      interaction_id: binding.interaction_id,
      response_id: 'server-owned-response',
      response_generation: 0,
    },
  });
  await serverOwnedResponse.start(binding);
  const serverAccepted = await serverOwnedResponse.submitText(turn);
  assert.equal(serverAccepted.response.response_id, 'server-owned-response');
  assert.equal(serverAccepted.response.response_generation, 0);
  assert.notEqual(serverAccepted.response.response_generation, serverAccepted.activation_generation);
});

test('agent submit still requires a client response id before transport', async () => {
  let submitCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      submitCalls += 1;
      throw new Error('submit transport must not run');
    },
  });
  await owner.start(binding);

  await assert.rejects(
    owner.submitText({
      commit_id: 'commit-agent-missing-response',
      turn_id: 'turn-agent-missing-response',
      committed_at: '2026-08-10T00:00:00Z',
      text: 'agent submission',
    }),
    /response_id is required/
  );
  assert.equal(submitCalls, 0);
});

test('agent submit requires exact server-owned turn and commit binding', async () => {
  const turn = {
    commit_id: 'commit-agent-binding',
    turn_id: 'turn-agent-binding',
    response_id: 'response-agent-binding',
    committed_at: '2026-08-07T10:00:00Z',
    text: 'bind the agent round to this committed turn',
  };
  const makeOwner = resultBinding => {
    let submitCalls = 0;
    const owner = new ProductWebP2ActivationOwner({
      enabled: true,
      request: async (method, params, requestId) => {
        if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
        submitCalls += 1;
        return agentSubmitResponse(requestId, params, {
          round_id: 'round-agent-binding',
          ...resultBinding,
        });
      },
    });
    return { owner, submitCalls: () => submitCalls };
  };

  for (const resultBinding of [
    { turn_id: undefined, commit_id: undefined },
    { turn_id: 'turn-foreign', commit_id: turn.commit_id },
    { turn_id: turn.turn_id, commit_id: 'commit-foreign' },
  ]) {
    const { owner } = makeOwner(resultBinding);
    await owner.start(binding);
    await assert.rejects(owner.submitText(turn), /round_accepted response binding mismatch/);
  }

  const exact = makeOwner({
    turn_id: turn.turn_id,
    commit_id: turn.commit_id,
  });
  await exact.owner.start(binding);
  const accepted = await exact.owner.submitText(turn);
  const replayed = await exact.owner.submitText(turn);
  assert.deepEqual(replayed, accepted);
  assert.equal(accepted.turn_id, turn.turn_id);
  assert.equal(accepted.commit_id, turn.commit_id);
  assert.equal(exact.submitCalls(), 1);
});

test('active stock Web owner replays exact P2 operations after response loss', async () => {
  const calls = [];
  const attempts = new Map();
  const bound = (status, extra = {}) => ({
    ok: true,
    result: { status, ...binding, ...extra },
  });
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      const attempt = (attempts.get(method) ?? 0) + 1;
      attempts.set(method, attempt);
      if (attempt === 1) throw webError(`${method} response lost`, 'REQUEST_TIMEOUT', true);
      if (method === PRODUCT_P2_SUBMIT_METHOD) {
        return agentSubmitResponse(requestId, params);
      }
      if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
        return bound('notification', { kind: 'agent.output' });
      }
      return presentationAckResponse(requestId);
    },
  });
  await owner.start(binding);
  const turn = {
    commit_id: 'commit-1',
    turn_id: 'turn-1',
    response_id: 'response-1',
    committed_at: '2026-08-07T10:00:00Z',
    text: 'hello',
  };
  const ack = {
    response_id: 'response-1',
    response_generation: 0,
    surface: 'text',
    unit_id: 'unit-1',
    contiguous_cursor: 0,
    presented_at: '2026-08-07T10:00:01Z',
  };

  await assert.rejects(owner.submitText(turn), /response lost/);
  await owner.submitText(turn);
  await assert.rejects(owner.nextNotification(), /response lost/);
  await owner.nextNotification();
  await assert.rejects(owner.acknowledgePresentation(ack), /response lost/);
  await owner.acknowledgePresentation(ack);

  for (const method of [PRODUCT_P2_SUBMIT_METHOD, PRODUCT_P2_NOTIFICATION_NEXT_METHOD, PRODUCT_P2_PRESENTATION_ACK_METHOD]) {
    const operationCalls = calls.filter(([called]) => called === method);
    assert.equal(operationCalls.length, 2);
    assert.equal(operationCalls[0][2], operationCalls[1][2]);
    assert.match(operationCalls[0][2], /^live-voice-p2-/);
  }
  const notificationCalls = calls.filter(([method]) => method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD);
  assert.equal(notificationCalls[0][1].notification_sequence, 1);
  assert.equal(notificationCalls[1][1].notification_sequence, 1);
});

test('unknown P2 submit locks semantic changes but exact retry stays stable', async () => {
  const calls = [];
  let unavailable = true;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      if (unavailable) throw webError('submit outcome unknown', 'UNAVAILABLE');
      return agentSubmitResponse(requestId, params);
    },
  });
  await owner.start(binding);
  const first = {
    commit_id: 'commit-unknown-1',
    turn_id: 'turn-unknown-1',
    response_id: 'response-unknown-1',
    committed_at: '2026-08-07T10:00:00Z',
    text: 'first semantic turn',
  };

  await assert.rejects(owner.submitText(first), /outcome unknown/);
  assert.equal(owner.hasPendingSubmission(), true);
  await assert.rejects(owner.submitText({ ...first, commit_id: 'commit-unknown-2', text: 'changed turn' }), /previous product turn is still unresolved/);
  unavailable = false;
  await owner.submitText(first);

  const submits = calls.filter(([method]) => method === PRODUCT_P2_SUBMIT_METHOD);
  assert.equal(submits.length, 2);
  assert.equal(submits[0][2], submits[1][2]);
  assert.equal(owner.hasPendingSubmission(), false);
});

test('unresolved presentation ACK blocks a second turn and preserves exact retry', async () => {
  const calls = [];
  let ackUnavailable = true;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      if (method === PRODUCT_P2_PRESENTATION_ACK_METHOD && ackUnavailable) {
        throw webError('ACK outcome unknown', 'UNAVAILABLE');
      }
      if (method === PRODUCT_P2_PRESENTATION_ACK_METHOD) {
        return presentationAckResponse(requestId);
      }
      return agentSubmitResponse(requestId, params, { round_id: 'round-2' });
    },
  });
  await owner.start(binding);
  const ack = {
    response_id: 'response-1',
    response_generation: 0,
    surface: 'text',
    unit_id: 'unit-1',
    contiguous_cursor: 0,
    presented_at: '2026-08-07T10:00:01Z',
  };

  await assert.rejects(owner.acknowledgePresentation(ack), /outcome unknown/);
  assert.equal(owner.hasPendingPresentationAck(), true);
  await assert.rejects(
    owner.submitText({
      commit_id: 'commit-2',
      turn_id: 'turn-2',
      response_id: 'response-2',
      committed_at: '2026-08-07T10:00:02Z',
      text: 'must wait for ACK',
    }),
    /previous product turn is still unresolved/
  );
  ackUnavailable = false;
  await owner.acknowledgePresentation(ack);

  const acks = calls.filter(([method]) => method === PRODUCT_P2_PRESENTATION_ACK_METHOD);
  assert.equal(acks.length, 2);
  assert.equal(acks[0][2], acks[1][2]);
  assert.equal(owner.hasPendingPresentationAck(), false);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P2_SUBMIT_METHOD).length, 0);
});

test('completed Web submission capacity recovers and old replay fails closed', async () => {
  let submissionCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      submissionCalls += 1;
      return agentSubmitResponse(requestId, params, { round_id: `round-${submissionCalls}` });
    },
  });
  await owner.start(binding);
  const first = {
    commit_id: 'commit-capacity-0',
    turn_id: 'turn-capacity-0',
    response_id: 'response-capacity-0',
    committed_at: '2026-08-07T10:00:00Z',
    text: 'capacity 0',
  };
  for (let index = 0; index < 129; index += 1) {
    await owner.submitText({
      commit_id: `commit-capacity-${index}`,
      turn_id: `turn-capacity-${index}`,
      response_id: `response-capacity-${index}`,
      committed_at: '2026-08-07T10:00:00Z',
      text: `capacity ${index}`,
    });
  }

  await assert.rejects(owner.submitText(first), /replay has expired/);
  assert.equal(submissionCalls, 129);
});

test('P2 operations fail before transport unless the exact activation is active', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (...args) => calls.push(args),
  });

  await assert.rejects(
    owner.submitText({
      commit_id: 'commit-1',
      turn_id: 'turn-1',
      response_id: 'response-1',
      committed_at: '2026-08-07T10:00:00Z',
      text: 'hello',
    }),
    /not active/
  );
  await assert.rejects(owner.nextNotification(), /not active/);
  assert.deepEqual(calls, []);
});

test('stock Web P3 owner forwards one exact credential-free confirmed mutation', async () => {
  const calls = [];
  const owner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P3_CONFIRMATION_ISSUE_METHOD) {
        return {
          ok: true,
          result: p3ConfirmationResult(),
        };
      }
      return {
        ok: true,
        result: p3MutationResult(),
      };
    },
  });
  const mutation = Object.freeze({
    operation: 'task.cancel',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  });

  const first = await owner.issue(mutation);
  const replay = await owner.issue(mutation);
  assert.equal(first, replay);
  assert.equal((await owner.mutate(mutation)).status, 'mutation_processed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P3_CONFIRMATION_ISSUE_METHOD, PRODUCT_P3_MUTATE_METHOD]
  );
  assert.equal(calls[1][1].confirmation_id, 'confirmation-1');
  for (const [, params] of calls) assert.equal('auth_token' in params, false);
});

test('stock Web task.retry sends only the exact task target through two-step confirmation', async () => {
  const calls = [];
  const owner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P3_CONFIRMATION_ISSUE_METHOD) {
        return {
          ok: true,
          result: {
            ...p3ConfirmationResult('confirmation-retry'),
            operation: 'task.retry',
          },
        };
      }
      return {
        ok: true,
        result: {
          ...p3MutationResult(),
          operation: 'task.retry',
          formal_task_result: {
            task_id: 'task-1',
            previous_attempt_id: 'attempt-a',
            attempt_id: 'attempt-b',
            attempt_number: 2,
            applied: true,
            state: 'accepted',
            outbox_id: 'outbox-b',
          },
        },
      };
    },
  });
  const retry = Object.freeze({
    operation: 'task.retry',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  });
  await owner.issue(retry);
  await owner.mutate(retry);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0][1], retry);
  assert.deepEqual(calls[1][1], { ...retry, confirmation_id: 'confirmation-retry' });
  assert.equal(
    calls.some(([, params]) => 'previous_attempt_id' in params || 'attempt_number' in params || 'context' in params),
    false
  );
  assert.notEqual(calls[0][2], calls[1][2]);
});

test('task.retry rejects client-declared lineage and changed targets before network effects', async () => {
  let calls = 0;
  const owner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async () => {
      calls += 1;
      throw new Error('transport must not be reached');
    },
  });
  const retry = {
    operation: 'task.retry',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  };
  for (const forged of [
    { previous_attempt_id: 'attempt-a' },
    { previous_outcome: 'cancelled' },
    { attempt_number: 2 },
    { context: { revision: 'client-forged' } },
  ]) {
    await assert.rejects(owner.issue({ ...retry, ...forged }), /only task_id/);
  }
  assert.equal(calls, 0);
});

test('stock Web owner retains one exact playback-scoped barge-in', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      if (method === PRODUCT_P2_BARGE_IN_METHOD) {
        return durableResponse(requestId, 'barge_in_applied', {
          action_id: params.action_id,
          response_id: params.response_id,
          response_generation: params.response_generation,
          cancel_response: params.cancel_response,
          applied: true,
          replayed: false,
          effect_ids: ['effect-playback-stop'],
        });
      }
      return response('closed');
    },
  });
  await owner.start(binding);
  const input = {
    action_id: 'barge-action-1',
    response_id: 'response-1',
    response_generation: 0,
    cancel_response: false,
  };

  assert.equal(owner.hasPendingBargeIn(), false);
  const first = await owner.bargeIn(input);
  assert.equal(owner.hasPendingBargeIn(), false);
  const replay = await owner.bargeIn(input);

  assert.equal(first.status, 'barge_in_applied');
  assert.deepEqual(replay, first);
  assert.equal(calls.filter(([method]) => method === PRODUCT_P2_BARGE_IN_METHOD).length, 1);
  assert.equal(calls[1][1].cancel_response, false);
  assert.match(calls[1][2], /^live-voice-p2-barge-/);
  await assert.rejects(owner.bargeIn({ ...input, response_generation: -1 }), /barge-in binding/);
});

test('barge-in response loss stays pending until the exact input is replayed', async () => {
  let bargeCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      if (method === PRODUCT_P2_BARGE_IN_METHOD) {
        bargeCalls += 1;
        if (bargeCalls === 1) {
          const error = new Error('response lost');
          error.code = 'REQUEST_TIMEOUT';
          error.retriable = true;
          throw error;
        }
        return durableResponse(requestId, 'barge_in_applied', {
          action_id: params.action_id,
          response_id: params.response_id,
          response_generation: params.response_generation,
          cancel_response: params.cancel_response,
          applied: true,
          replayed: true,
          effect_ids: ['effect-playback-stop'],
        });
      }
      return response('closed');
    },
  });
  const input = {
    action_id: 'barge-action-loss',
    response_id: 'response-loss',
    response_generation: 1,
    cancel_response: true,
  };
  await owner.start(binding);

  await assert.rejects(owner.bargeIn(input), /response lost/);
  assert.equal(owner.hasPendingBargeIn(), true);
  assert.equal((await owner.bargeIn(input)).replayed, true);
  assert.equal(owner.hasPendingBargeIn(), false);
  assert.equal(bargeCalls, 2);
});

test('stock Web P3 owner binds exact committed voice origin and rejects borrowing', async () => {
  const calls = [];
  const owner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return {
        ok: true,
        result:
          method === PRODUCT_P3_CONFIRMATION_ISSUE_METHOD
            ? {
                ...p3ConfirmationResult(),
                operation: 'task.create',
                target_task_id: null,
              }
            : {
                ...p3MutationResult(),
                operation: 'task.create',
                target_task_id: null,
              },
      };
    },
  });
  const voice = Object.freeze({
    operation: 'task.create',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    source: 'voice',
    interaction_id: 'interaction-voice-1',
    turn_id: 'turn-voice-1',
    commit_id: 'commit-voice-1',
    name: 'Voice task',
    instruction: 'Create one bounded task.',
  });

  await owner.issue(voice);
  await owner.mutate(voice);
  for (const [, params] of calls) {
    assert.equal(params.source, 'voice');
    assert.equal(params.interaction_id, 'interaction-voice-1');
    assert.equal(params.turn_id, 'turn-voice-1');
    assert.equal(params.commit_id, 'commit-voice-1');
  }

  const rejecting = new ProductWebP3MutationOwner({
    enabled: true,
    request: async () => {
      throw new Error('transport must not be reached');
    },
  });
  await assert.rejects(rejecting.issue({ ...voice, source: 'structured' }), /committed origin/);
  await assert.rejects(rejecting.issue({ ...voice, interaction_id: undefined }), /committed origin/);
  await assert.rejects(rejecting.issue({ ...voice, turn_id: undefined }), /committed origin/);
});

test('stock Web P3 owner rejects forged confirmation echoes and closed bindings', async () => {
  const mutation = Object.freeze({
    operation: 'task.cancel',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  });
  const forgedResults = [
    { ...p3ConfirmationResult(), command_id: 'command-forged' },
    { ...p3ConfirmationResult(), target_task_id: 'task-forged' },
    {
      ...p3ConfirmationResult(),
      task_control_binding: {
        ...p3TaskControlBinding(),
        correlation_id: 'correlation-forged',
      },
    },
    {
      ...p3ConfirmationResult(),
      task_control_binding: {
        ...p3TaskControlBinding(),
        unexpected_grant: 'task.cancel',
      },
    },
  ];

  for (const forgedResult of forgedResults) {
    const calls = [];
    const owner = new ProductWebP3MutationOwner({
      enabled: true,
      request: async (method, params) => {
        calls.push([method, params]);
        return { ok: true, result: forgedResult };
      },
    });

    await assert.rejects(owner.issue(mutation), /response|binding/);
    await assert.rejects(owner.mutate(mutation), /confirmation/);
    assert.deepEqual(
      calls.map(([method]) => method),
      [PRODUCT_P3_CONFIRMATION_ISSUE_METHOD]
    );
  }
});

test('stock Web P3 owner rejects forged mutation echoes and missing formal result', async () => {
  const mutation = Object.freeze({
    operation: 'task.cancel',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  });
  const forgedResults = [
    { ...p3MutationResult(), command_id: 'command-forged' },
    { ...p3MutationResult(), target_task_id: 'task-forged' },
    { ...p3MutationResult(), formal_task_result: null },
  ];

  for (const forgedResult of forgedResults) {
    let mutationCalls = 0;
    const owner = new ProductWebP3MutationOwner({
      enabled: true,
      request: async method => {
        if (method === PRODUCT_P3_CONFIRMATION_ISSUE_METHOD) {
          return { ok: true, result: p3ConfirmationResult() };
        }
        mutationCalls += 1;
        return { ok: true, result: forgedResult };
      },
    });

    await owner.issue(mutation);
    await assert.rejects(owner.mutate(mutation), /mutation response/);
    assert.equal(owner.hasPendingMutation(), true);
    assert.equal(mutationCalls, 1);
  }
});

test('stock Web P3 owner reuses stable request IDs after response loss', async () => {
  const calls = [];
  let issueAttempts = 0;
  let mutationAttempts = 0;
  const owner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (method, params, requestId) => {
      calls.push([method, params, requestId]);
      if (method === PRODUCT_P3_CONFIRMATION_ISSUE_METHOD) {
        issueAttempts += 1;
        if (issueAttempts === 1) throw webError('issue response lost', 'REQUEST_TIMEOUT', true);
        return {
          ok: true,
          result: p3ConfirmationResult(),
        };
      }
      mutationAttempts += 1;
      if (mutationAttempts === 1) throw webError('mutation response lost', 'WS_DISCONNECTED', true);
      return {
        ok: true,
        result: p3MutationResult(),
      };
    },
  });
  const mutation = Object.freeze({
    operation: 'task.cancel',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  });

  await assert.rejects(owner.issue(mutation), /response lost/);
  await owner.issue(mutation);
  await assert.rejects(owner.mutate(mutation), /response lost/);
  await owner.mutate(mutation);

  assert.equal(calls[0][2], calls[1][2]);
  assert.equal(calls[2][2], calls[3][2]);
  assert.notEqual(calls[0][2], calls[2][2]);
  for (const call of calls) assert.match(call[2], /^live-voice-p3-/);
});

test('stock Web P3 owner releases definitive rejects but retains unknown outcomes', async () => {
  const mutation = Object.freeze({
    operation: 'task.cancel',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  });
  const deniedIds = [];
  let denied = true;
  const definitiveOwner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (_method, _params, requestId) => {
      deniedIds.push(requestId);
      if (denied) {
        denied = false;
        throw webError('permission revoked', 'PERMISSION_DENIED');
      }
      return {
        ok: true,
        result: p3ConfirmationResult('confirmation-2'),
      };
    },
  });

  await assert.rejects(definitiveOwner.issue(mutation), /permission revoked/);
  assert.equal(definitiveOwner.hasPendingMutation(), false);
  await definitiveOwner.issue(mutation);
  assert.notEqual(deniedIds[0], deniedIds[1]);

  const unknownIds = [];
  let unavailable = true;
  const retainedOwner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (_method, _params, requestId) => {
      unknownIds.push(requestId);
      if (unavailable) {
        unavailable = false;
        throw webError('result unknown', 'UNAVAILABLE');
      }
      return {
        ok: true,
        result: p3ConfirmationResult('confirmation-3'),
      };
    },
  });

  await assert.rejects(retainedOwner.issue(mutation), /result unknown/);
  assert.equal(retainedOwner.hasPendingMutation(), true);
  await retainedOwner.issue(mutation);
  assert.equal(unknownIds[0], unknownIds[1]);
});

test('stock Web P3 owner rejects mutation changes and feature-off effects', async () => {
  const calls = [];
  const disabled = new ProductWebP3MutationOwner({
    enabled: false,
    request: async (...args) => calls.push(args),
  });
  const mutation = {
    operation: 'task.cancel',
    session_id: 'session-1',
    command_id: 'command-1',
    issued_at: '2026-08-07T10:00:00Z',
    correlation_id: 'correlation-1',
    task_id: 'task-1',
  };
  await assert.rejects(disabled.issue(mutation), /disabled/);
  assert.deepEqual(calls, []);

  const owner = new ProductWebP3MutationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return {
        ok: true,
        result: p3ConfirmationResult(),
      };
    },
  });
  await owner.issue(mutation);
  await assert.rejects(owner.mutate({ ...mutation, task_id: 'task-other' }), /exact/);
  assert.equal(calls.length, 1);
});

test('close waits for an in-flight activation and still performs retained cleanup', async () => {
  const calls = [];
  let release;
  const activation = new Promise(resolve => {
    release = resolve;
  });
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return activation;
      return response('closed');
    },
  });

  const started = owner.start(binding);
  const closed = owner.close();
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD]
  );
  release(response('active'));

  assert.equal((await started).status, 'active');
  assert.equal((await closed).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
});

test('binding mismatch fails closed and cleanup remains attempted', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return method === PRODUCT_P2_ACTIVATE_METHOD ? response('active', { activation_id: 'wrong-activation' }) : response('closed');
    },
  });

  await assert.rejects(owner.start(binding), /binding mismatch/);
  assert.equal(owner.snapshot().status, 'unavailable');
  assert.equal((await owner.close()).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]
  );
});

test('P2 transport-loss activation retains exact cleanup ownership', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      calls.push(method);
      if (method === PRODUCT_P2_ACTIVATE_METHOD) {
        throw webError('activation response timed out', 'REQUEST_TIMEOUT', true);
      }
      return response('closed');
    },
  });

  await assert.rejects(owner.start(binding), /timed out/);
  assert.equal(owner.needsCleanup(), true);
  assert.equal((await owner.closeWithRetry({ retry_delay_ms: 0 })).status, 'closed');
  assert.deepEqual(calls, [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD]);
});

test('P2 pending activation disconnect cleans the exact route before reconnect recovery', async () => {
  const calls = [];
  let disconnected = true;
  const createOwner = () =>
    new ProductWebP2ActivationOwner({
      enabled: true,
      request: async (method, params) => {
        calls.push([method, params]);
        if (method === PRODUCT_P2_ACTIVATE_METHOD && disconnected) {
          throw webError('connection closed after send', 'WS_CLOSED');
        }
        return response(method === PRODUCT_P2_ACTIVATE_METHOD ? 'active' : 'closed');
      },
    });

  const disconnectedOwner = createOwner();
  await assert.rejects(disconnectedOwner.start(binding), /closed after send/);
  assert.equal(disconnectedOwner.needsCleanup(), true);
  assert.equal((await disconnectedOwner.closeWithRetry({ retry_delay_ms: 0 })).status, 'closed');

  disconnected = false;
  const reconnectedOwner = createOwner();
  assert.equal((await reconnectedOwner.start(binding)).status, 'active');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_CLOSE_METHOD, PRODUCT_P2_ACTIVATE_METHOD]
  );
  assert.deepEqual(calls[1][1], binding);
  await reconnectedOwner.close();
});

test('P2 authoritative activation denial stays unavailable and does not block recovery', async () => {
  const calls = [];
  const denied = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      calls.push(method);
      throw webError('authority denied', 'PERMISSION_DENIED');
    },
  });

  await assert.rejects(denied.start(binding), /authority denied/);
  assert.equal(denied.snapshot().status, 'unavailable');
  assert.equal(denied.needsCleanup(), false);

  const recovered = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      calls.push(method);
      return response(method === PRODUCT_P2_ACTIVATE_METHOD ? 'active' : 'closed');
    },
  });
  assert.equal((await recovered.start(binding)).status, 'active');
  assert.deepEqual(calls, [PRODUCT_P2_ACTIVATE_METHOD, PRODUCT_P2_ACTIVATE_METHOD]);
  await recovered.close();
});

test('failed close remains cleanup_pending and an exact retry can close', async () => {
  let closeCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      closeCalls += 1;
      if (closeCalls === 1) throw new Error('cleanup pending');
      return response('closed');
    },
  });

  await owner.start(binding);
  await assert.rejects(owner.close(), /cleanup pending/);
  assert.equal(owner.snapshot().status, 'cleanup_pending');
  assert.equal((await owner.close()).status, 'closed');
  assert.equal(closeCalls, 2);
});

test('P2 cleanup and next-session reconciliation share one bounded close retry', async () => {
  let closeCalls = 0;
  const reconciliationSnapshots = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      closeCalls += 1;
      if (closeCalls === 1) throw new Error('close response lost');
      return response('closed');
    },
  });
  await owner.start(binding);

  const cleanup = owner.closeWithRetry({ retry_delay_ms: 0 });
  const reconciliation = owner.closeWithRetry({
    retry_delay_ms: 0,
    on_retry: snapshot => reconciliationSnapshots.push(snapshot),
  });

  assert.equal(cleanup, reconciliation);
  assert.equal((await reconciliation).status, 'closed');
  assert.equal(closeCalls, 2);
  assert.equal(
    reconciliationSnapshots.some(snapshot => snapshot.status === 'cleanup_pending'),
    true
  );
});

test('P2 cleanup retry stops at its explicit bound and retains exact ownership', async () => {
  let closeCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      closeCalls += 1;
      throw webError('cleanup still unavailable', 'REQUEST_TIMEOUT', true);
    },
  });
  await owner.start(binding);

  await assert.rejects(owner.closeWithRetry({ max_attempts: 3, retry_delay_ms: 0 }), /cleanup still unavailable/);

  assert.equal(closeCalls, 3);
  assert.equal(owner.snapshot().status, 'cleanup_pending');
  assert.equal(owner.needsCleanup(), true);
});

test('close response binding mismatch stays cleanup_pending and retryable', async () => {
  let closeCalls = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return response('active');
      closeCalls += 1;
      if (closeCalls === 1) {
        return response('closed', { activation_id: 'other-activation' });
      }
      return response('closed');
    },
  });
  await owner.start(binding);

  await assert.rejects(owner.close(), /close binding mismatch/);
  assert.equal(owner.snapshot().status, 'cleanup_pending');
  assert.equal(owner.snapshot().binding?.interaction_id, 'interaction-1');
  assert.equal((await owner.close()).status, 'closed');
  assert.equal(closeCalls, 2);
});

test('stock Web queries one formal task then owns exact P3 progress activate and close', async () => {
  const calls = [];
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P3_TASK_LIST_METHOD) {
        return { ok: true, result: { tasks: [{ task_id: 'task-1', state: 'running' }] } };
      }
      return {
        ok: true,
        result: p3ProgressResult(method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed', {
          session_id: 'session-1',
          task_id: 'task-1',
          correlation_id: 'correlation-1',
          origin_id: 'origin-1',
          generation_id: 'generation-1',
          generation: 1,
        }),
      };
    },
  });

  const active = await owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  });
  assert.equal(active.status, 'active');
  assert.equal(active.binding?.task_id, 'task-1');
  assert.equal((await owner.close()).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P3_TASK_LIST_METHOD, PRODUCT_P3_PROGRESS_ACTIVATE_METHOD, PRODUCT_P3_PROGRESS_CLOSE_METHOD]
  );
  for (const [, params] of calls) assert.equal('auth_token' in params, false);
});

test('P3 progress snapshot publishes the server-declared voice to text fallback before any event', async () => {
  const snapshots = [];
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    on_snapshot: snapshot => snapshots.push(snapshot),
    request: async (method, params) => ({
      ok: true,
      result: p3ProgressResult(method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed', params, {
        requested_origin_kind: 'voice',
        origin_kind: 'text',
        voice_progress: 'unavailable',
        voice_reason: 'TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE',
        fallback_reason: 'TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE',
      }),
    }),
  });

  const active = await owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    task_id: 'task-voice-1',
    origin_id: 'interaction-voice-1',
    generation_id: 'generation-voice-1',
    generation: 1,
  });
  assert.equal(active.status, 'active');
  assert.equal(active.requested_origin_kind, 'voice');
  assert.equal(active.effective_origin_kind, 'text');
  assert.equal(active.voice_progress, 'unavailable');
  assert.equal(active.fallback_reason, 'TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE');
  assert.equal(snapshots.at(-1).fallback_reason, 'TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE');
  await owner.close();
});

test('fresh task.create binds progress directly to the exact accepted task', async () => {
  const calls = [];
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P3_TASK_LIST_METHOD) {
        throw new Error('fresh task progress must not query a task list');
      }
      return {
        ok: true,
        result: p3ProgressResult(method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed', params),
      };
    },
  });

  await owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    task_id: 'task-created-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  });
  await owner.close();

  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P3_PROGRESS_ACTIVATE_METHOD, PRODUCT_P3_PROGRESS_CLOSE_METHOD]
  );
  assert.equal(calls[0][1].task_id, 'task-created-1');
});

test('P3 close waits for in-flight task selection and cleans the resulting activation', async () => {
  const calls = [];
  let releaseTaskList;
  const taskList = new Promise(resolve => {
    releaseTaskList = resolve;
  });
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P3_TASK_LIST_METHOD) return taskList;
      return {
        ok: true,
        result: p3ProgressResult(method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed', {
          session_id: 'session-1',
          task_id: 'task-1',
          correlation_id: 'correlation-1',
          origin_id: 'origin-1',
          generation_id: 'generation-1',
          generation: 1,
        }),
      };
    },
  });

  const started = owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  });
  const closed = owner.close();
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P3_TASK_LIST_METHOD]
  );
  releaseTaskList({
    ok: true,
    result: { tasks: [{ task_id: 'task-1', state: 'running' }] },
  });

  assert.equal((await started).status, 'active');
  assert.equal((await closed).status, 'closed');
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P3_TASK_LIST_METHOD, PRODUCT_P3_PROGRESS_ACTIVATE_METHOD, PRODUCT_P3_PROGRESS_CLOSE_METHOD]
  );
});

test('P3 progress refuses ambiguous active task selection without activation', async () => {
  const calls = [];
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return {
        ok: true,
        result: {
          tasks: [
            { task_id: 'task-1', state: 'running' },
            { task_id: 'task-2', state: 'accepted' },
          ],
        },
      };
    },
  });

  await assert.rejects(
    owner.start({
      session_id: 'session-1',
      correlation_id: 'correlation-1',
      origin_id: 'origin-1',
      generation_id: 'generation-1',
      generation: 1,
    }),
    /exactly one active task/
  );
  assert.deepEqual(
    calls.map(([method]) => method),
    [PRODUCT_P3_TASK_LIST_METHOD]
  );
  assert.equal(owner.snapshot().binding, null);
  assert.equal((await owner.close()).status, 'closed');
});

test('P3 authoritative activation unavailability stays unavailable and permits recovery', async () => {
  const calls = [];
  let dependencyAvailable = false;
  const createOwner = () =>
    new ProductWebP3ProgressOwner({
      enabled: true,
      request: async method => {
        calls.push(method);
        if (method === PRODUCT_P3_TASK_LIST_METHOD) {
          return { ok: true, result: { tasks: [{ task_id: 'task-1', state: 'running' }] } };
        }
        if (method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD && !dependencyAvailable) {
          throw webError('subscription unavailable', 'UNAVAILABLE');
        }
        return {
          ok: true,
          result: p3ProgressResult(method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed', {
            session_id: 'session-1',
            task_id: 'task-1',
            correlation_id: 'correlation-1',
            origin_id: 'origin-1',
            generation_id: 'generation-1',
            generation: 1,
          }),
        };
      },
    });
  const input = {
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  };

  const unavailable = createOwner();
  await assert.rejects(unavailable.start(input), /subscription unavailable/);
  assert.equal(unavailable.snapshot().status, 'unavailable');
  assert.equal(unavailable.snapshot().binding?.task_id, 'task-1');
  assert.equal(unavailable.needsCleanup(), false);

  dependencyAvailable = true;
  const recovered = createOwner();
  assert.equal((await recovered.start(input)).status, 'active');
  assert.deepEqual(calls, [PRODUCT_P3_TASK_LIST_METHOD, PRODUCT_P3_PROGRESS_ACTIVATE_METHOD, PRODUCT_P3_TASK_LIST_METHOD, PRODUCT_P3_PROGRESS_ACTIVATE_METHOD]);
  await recovered.close();
});

test('P3 progress exact close remains retryable after response loss', async () => {
  let closeCalls = 0;
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P3_TASK_LIST_METHOD) {
        return { ok: true, result: { tasks: [{ task_id: 'task-1', state: 'running' }] } };
      }
      const result = {
        session_id: 'session-1',
        task_id: 'task-1',
        correlation_id: 'correlation-1',
        origin_id: 'origin-1',
        generation_id: 'generation-1',
        generation: 1,
      };
      if (method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD) {
        return { ok: true, result: p3ProgressResult('active', result) };
      }
      closeCalls += 1;
      if (closeCalls === 1) throw new Error('close response lost');
      return { ok: true, result: { ...result, status: 'closed', replayed: true } };
    },
  });
  await owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  });

  await assert.rejects(owner.close(), /response lost/);
  assert.equal(owner.snapshot().status, 'cleanup_pending');
  assert.equal((await owner.close()).status, 'closed');
  assert.equal(closeCalls, 2);
});

test('P3 cleanup and next-session reconciliation share one bounded close retry', async () => {
  let closeCalls = 0;
  const reconciliationSnapshots = [];
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P3_TASK_LIST_METHOD) {
        return { ok: true, result: { tasks: [{ task_id: 'task-1', state: 'running' }] } };
      }
      const result = {
        session_id: 'session-1',
        task_id: 'task-1',
        correlation_id: 'correlation-1',
        origin_id: 'origin-1',
        generation_id: 'generation-1',
        generation: 1,
      };
      if (method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD) {
        return { ok: true, result: p3ProgressResult('active', result) };
      }
      closeCalls += 1;
      if (closeCalls === 1) throw new Error('close response lost');
      return { ok: true, result: { ...result, status: 'closed', replayed: true } };
    },
  });
  await owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  });

  const cleanup = owner.closeWithRetry({ retry_delay_ms: 0 });
  const reconciliation = owner.closeWithRetry({
    retry_delay_ms: 0,
    on_retry: snapshot => reconciliationSnapshots.push(snapshot),
  });

  assert.equal(cleanup, reconciliation);
  assert.equal((await reconciliation).status, 'closed');
  assert.equal(closeCalls, 2);
  assert.equal(
    reconciliationSnapshots.some(snapshot => snapshot.status === 'cleanup_pending'),
    true
  );
});

test('P3 progress close rejects a partial binding response and retries exact cleanup', async () => {
  let closeCalls = 0;
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async method => {
      if (method === PRODUCT_P3_TASK_LIST_METHOD) {
        return { ok: true, result: { tasks: [{ task_id: 'task-1', state: 'running' }] } };
      }
      const result = {
        session_id: 'session-1',
        task_id: 'task-1',
        correlation_id: 'correlation-1',
        origin_id: 'origin-1',
        generation_id: 'generation-1',
        generation: 1,
      };
      if (method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD) {
        return { ok: true, result: p3ProgressResult('active', result) };
      }
      closeCalls += 1;
      return {
        ok: true,
        result: {
          ...result,
          status: 'closed',
          correlation_id: closeCalls === 1 ? 'wrong-correlation' : result.correlation_id,
        },
      };
    },
  });
  await owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  });

  await assert.rejects(owner.close(), /binding mismatch/);
  assert.equal(owner.snapshot().status, 'cleanup_pending');
  assert.equal((await owner.close()).status, 'closed');
  assert.equal(closeCalls, 2);
});
