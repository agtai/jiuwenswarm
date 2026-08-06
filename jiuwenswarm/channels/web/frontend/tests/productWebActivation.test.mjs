import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_P2_ACTIVATE_METHOD,
  PRODUCT_P2_CLOSE_METHOD,
  PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
  PRODUCT_P3_PROGRESS_CLOSE_METHOD,
  PRODUCT_P3_TASK_LIST_METHOD,
  ProductWebP2ActivationOwner,
  ProductWebP3ProgressOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';

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
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P2_ACTIVATE_METHOD,
    PRODUCT_P2_CLOSE_METHOD,
  ]);
  for (const [, params] of calls) {
    assert.deepEqual(params, binding);
    assert.equal('auth_token' in params, false);
  }
});

test('close waits for an in-flight activation and still performs retained cleanup', async () => {
  const calls = [];
  let release;
  const activation = new Promise(resolve => { release = resolve; });
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
  assert.deepEqual(calls.map(([method]) => method), [PRODUCT_P2_ACTIVATE_METHOD]);
  release(response('active'));

  assert.equal((await started).status, 'active');
  assert.equal((await closed).status, 'closed');
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P2_ACTIVATE_METHOD,
    PRODUCT_P2_CLOSE_METHOD,
  ]);
});

test('binding mismatch fails closed and cleanup remains attempted', async () => {
  const calls = [];
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      return method === PRODUCT_P2_ACTIVATE_METHOD
        ? response('active', { activation_id: 'wrong-activation' })
        : response('closed');
    },
  });

  await assert.rejects(owner.start(binding), /binding mismatch/);
  assert.equal(owner.snapshot().status, 'unavailable');
  assert.equal((await owner.close()).status, 'closed');
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P2_ACTIVATE_METHOD,
    PRODUCT_P2_CLOSE_METHOD,
  ]);
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
  const createOwner = () => new ProductWebP2ActivationOwner({
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
  assert.equal(
    (await disconnectedOwner.closeWithRetry({ retry_delay_ms: 0 })).status,
    'closed'
  );

  disconnected = false;
  const reconnectedOwner = createOwner();
  assert.equal((await reconnectedOwner.start(binding)).status, 'active');
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P2_ACTIVATE_METHOD,
    PRODUCT_P2_CLOSE_METHOD,
    PRODUCT_P2_ACTIVATE_METHOD,
  ]);
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

  await assert.rejects(
    owner.closeWithRetry({ max_attempts: 3, retry_delay_ms: 0 }),
    /cleanup still unavailable/
  );

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
        result: {
          status: method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed',
          session_id: 'session-1',
          task_id: 'task-1',
          correlation_id: 'correlation-1',
          origin_id: 'origin-1',
          generation_id: 'generation-1',
          generation: 1,
        },
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
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P3_TASK_LIST_METHOD,
    PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
    PRODUCT_P3_PROGRESS_CLOSE_METHOD,
  ]);
  for (const [, params] of calls) assert.equal('auth_token' in params, false);
});

test('P3 close waits for in-flight task selection and cleans the resulting activation', async () => {
  const calls = [];
  let releaseTaskList;
  const taskList = new Promise(resolve => { releaseTaskList = resolve; });
  const owner = new ProductWebP3ProgressOwner({
    enabled: true,
    request: async (method, params) => {
      calls.push([method, params]);
      if (method === PRODUCT_P3_TASK_LIST_METHOD) return taskList;
      return {
        ok: true,
        result: {
          status: method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed',
          session_id: 'session-1',
          task_id: 'task-1',
          correlation_id: 'correlation-1',
          origin_id: 'origin-1',
          generation_id: 'generation-1',
          generation: 1,
        },
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
  assert.deepEqual(calls.map(([method]) => method), [PRODUCT_P3_TASK_LIST_METHOD]);
  releaseTaskList({
    ok: true,
    result: { tasks: [{ task_id: 'task-1', state: 'running' }] },
  });

  assert.equal((await started).status, 'active');
  assert.equal((await closed).status, 'closed');
  assert.deepEqual(calls.map(([method]) => method), [
    PRODUCT_P3_TASK_LIST_METHOD,
    PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
    PRODUCT_P3_PROGRESS_CLOSE_METHOD,
  ]);
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

  await assert.rejects(owner.start({
    session_id: 'session-1',
    correlation_id: 'correlation-1',
    origin_id: 'origin-1',
    generation_id: 'generation-1',
    generation: 1,
  }), /exactly one active task/);
  assert.deepEqual(calls.map(([method]) => method), [PRODUCT_P3_TASK_LIST_METHOD]);
  assert.equal(owner.snapshot().binding, null);
  assert.equal((await owner.close()).status, 'closed');
});

test('P3 authoritative activation unavailability stays unavailable and permits recovery', async () => {
  const calls = [];
  let dependencyAvailable = false;
  const createOwner = () => new ProductWebP3ProgressOwner({
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
        result: {
          status: method === PRODUCT_P3_PROGRESS_ACTIVATE_METHOD ? 'active' : 'closed',
          session_id: 'session-1',
          task_id: 'task-1',
          correlation_id: 'correlation-1',
          origin_id: 'origin-1',
          generation_id: 'generation-1',
          generation: 1,
        },
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
  assert.deepEqual(calls, [
    PRODUCT_P3_TASK_LIST_METHOD,
    PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
    PRODUCT_P3_TASK_LIST_METHOD,
    PRODUCT_P3_PROGRESS_ACTIVATE_METHOD,
  ]);
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
        return { ok: true, result: { ...result, status: 'active' } };
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
        return { ok: true, result: { ...result, status: 'active' } };
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
        return { ok: true, result: { ...result, status: 'active' } };
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
