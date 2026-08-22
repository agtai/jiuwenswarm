import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
  ProductP2ActivationJournal,
  reconcileProductP2Predecessor,
  reconcileRetiredProductP2PresentationAcks,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP2ActivationJournal.js';
import { replayProductP2DurableOperation } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';

function memoryStorage(initial = new Map()) {
  return {
    values: initial,
    getItem(key) {
      return this.values.get(key) ?? null;
    },
    setItem(key, value) {
      this.values.set(key, value);
    },
  };
}

function openJournal(storage, client = 'client-a') {
  return ProductP2ActivationJournal.open({
    session_id: 'session-a',
    client_instance_id: client,
    storage,
  });
}

function durableOperations(binding) {
  return [
    {
      method: 'live_voice.composition.p2.submit',
      request_id: 'request-submit',
      params: {
        ...binding,
        commit_id: 'commit-a',
        turn_id: 'turn-a',
        committed_at: '2026-08-10T00:00:00.000Z',
        text: 'create the task',
        dispatch_target: 'task',
        voice_commit_receipt: 'v'.repeat(32),
        critical_confirmation: true,
      },
    },
    {
      method: 'live_voice.composition.p2.presentation.ack',
      request_id: 'request-ack',
      params: {
        ...binding,
        response_id: 'response-a',
        response_generation: 0,
        surface: 'text',
        unit_id: 'unit-a',
        contiguous_cursor: 12,
        presented_at: '2026-08-10T00:00:01.000Z',
      },
    },
    {
      method: 'live_voice.composition.p2.barge_in',
      request_id: 'request-barge',
      params: {
        ...binding,
        action_id: 'barge-a',
        response_id: 'response-a',
        response_generation: 0,
        cancel_response: true,
      },
    },
  ];
}

test('journal writes the exact successor before activation and restores it after refresh', () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const binding = firstPage.prepareSuccessor('page-a');
  const refreshedPage = openJournal(storage, 'client-b');

  assert.equal(firstPage.snapshot().phase, 'activating');
  assert.deepEqual(refreshedPage.predecessorForRecovery(), binding);
  assert.equal(refreshedPage.snapshot().client_instance_id, 'client-a');
});

test('active predecessor is replayed, exactly closed, then advances one generation', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(first);
  const refreshedPage = openJournal(storage, 'client-b');
  const effects = [];

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async binding => {
      effects.push(['activate', binding]);
      return { replayed: true };
    },
    close_exact: async binding => {
      effects.push(['close', binding]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });
  const successor = refreshedPage.prepareSuccessor('page-b');

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.deepEqual(effects, [
    ['activate', first],
    ['close', first],
  ]);
  assert.equal(successor.activation_generation, first.activation_generation + 1);
  assert.notEqual(successor.activation_id, first.activation_id);
});

test('authoritative stale predecessor advances without a close replay', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markClosing(first);
  const refreshedPage = openJournal(storage, 'client-b');
  let closeCalls = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => {
      throw { reason: 'ACTIVATION_GENERATION_STALE' };
    },
    close_exact: async () => {
      closeCalls += 1;
    },
    error_reason: error => error?.reason,
    activation_retryable: () => false,
  });
  const successor = refreshedPage.prepareSuccessor('page-b');

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.equal(closeCalls, 0);
  assert.equal(successor.activation_generation, 2);
});

test('new allocation under an old binding proves server state loss and blocks', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(first);
  const refreshedPage = openJournal(storage, 'client-b');
  let closeCalls = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => ({ replayed: false }),
    close_exact: async () => {
      closeCalls += 1;
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
  });
  assert.equal(closeCalls, 1);
  assert.equal(refreshedPage.snapshot().phase, 'activation_result_unknown');
  assert.throws(() => refreshedPage.prepareSuccessor('page-b'), new RegExp(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED));
});

test('unknown reconcile or close result preserves the barrier and creates no successor', async () => {
  for (const failingOperation of ['activate', 'close']) {
    const storage = memoryStorage();
    const firstPage = openJournal(storage);
    const first = firstPage.prepareSuccessor('page-a');
    firstPage.markActive(first);
    const refreshedPage = openJournal(storage, 'client-b');
    let closeCalls = 0;

    const recovered = await reconcileProductP2Predecessor({
      journal: refreshedPage,
      activate_exact: async () => {
        if (failingOperation === 'activate') throw new Error('transport lost');
        return { replayed: true };
      },
      close_exact: async () => {
        closeCalls += 1;
        if (failingOperation === 'close') throw new Error('transport lost');
      },
      error_reason: () => undefined,
      activation_retryable: () => failingOperation === 'activate',
    });

    assert.deepEqual(recovered, {
      kind: 'retry',
      reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
    });
    assert.equal(closeCalls, failingOperation === 'activate' ? 0 : 1);
    assert.equal(refreshedPage.snapshot().phase, failingOperation === 'activate' ? 'reconciling' : 'closing');
  }
});

test('legacy result-unknown remains a zero-effect recovery barrier', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markResultUnknown(first);
  const refreshedPage = openJournal(storage, 'client-b');
  const effects = [];
  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async binding => {
      effects.push(['activate', binding]);
      return { replayed: true };
    },
    close_exact: async binding => {
      effects.push(['close', binding]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.deepEqual(effects, []);
  assert.equal(refreshedPage.snapshot().phase, 'result_unknown');
  assert.throws(() => refreshedPage.prepareSuccessor('page-b'), new RegExp(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED));
});

test('explicit retry promotes a generic unknown only into exact predecessor cleanup', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const predecessor = firstPage.prepareSuccessor('page-a');
  firstPage.markResultUnknown(predecessor);
  const refreshedPage = openJournal(storage, 'client-b');
  const effects = [];

  refreshedPage.requestResultUnknownRecovery(predecessor);
  assert.equal(refreshedPage.snapshot().phase, 'activation_result_unknown');
  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async binding => {
      effects.push(['activate', binding]);
      return { replayed: true };
    },
    close_exact: async binding => {
      effects.push(['close', binding]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.deepEqual(effects, [
    ['activate', predecessor],
    ['close', predecessor],
  ]);
  const successor = refreshedPage.prepareSuccessor('page-b');
  assert.equal(successor.activation_generation, predecessor.activation_generation + 1);
  assert.notEqual(successor.activation_id, predecessor.activation_id);
});

test('explicit generic-unknown retry retains the exact barrier when cleanup is uncertain', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const predecessor = firstPage.prepareSuccessor('page-a');
  firstPage.markResultUnknown(predecessor);
  const refreshedPage = openJournal(storage, 'client-b');
  refreshedPage.requestResultUnknownRecovery(predecessor);

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => ({ replayed: true }),
    close_exact: async () => {
      throw new Error('transport result unknown');
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, {
    kind: 'retry',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.equal(refreshedPage.snapshot().phase, 'closing_unconfirmed');
  assert.throws(() => refreshedPage.prepareSuccessor('page-b'), new RegExp(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED));
});

test('v1 generic result-unknown upgrades in place and retains its zero-effect barrier', async () => {
  const storage = memoryStorage();
  const created = openJournal(storage);
  const binding = created.prepareSuccessor('page-a');
  const [key] = storage.values.keys();
  storage.values.set(
    key,
    JSON.stringify({
      schema: 'live-voice.product-p2-activation-journal.v1',
      client_instance_id: 'client-a',
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: binding.interaction_id,
      binding,
      phase: 'result_unknown',
      last_generation: binding.activation_generation,
    })
  );
  const upgraded = openJournal(storage, 'client-upgrade');
  let callbacks = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: upgraded,
    replay_operation: async () => {
      callbacks += 1;
    },
    activate_exact: async () => {
      callbacks += 1;
      return { replayed: true };
    },
    close_exact: async () => {
      callbacks += 1;
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.equal(callbacks, 0);
  assert.equal(upgraded.snapshot().schema, 'live-voice.product-p2-activation-journal.v3');
  assert.equal(upgraded.snapshot().phase, 'result_unknown');
  assert.equal(JSON.parse(storage.values.get(key)).schema, 'live-voice.product-p2-activation-journal.v3');
});

test('submit ACK and barge-in replay exact durable operation before activation cleanup', async () => {
  for (const expectedOperation of ['submit', 'presentation.ack', 'barge_in']) {
    const storage = memoryStorage();
    const firstPage = openJournal(storage, `client-${expectedOperation}`);
    const binding = firstPage.prepareSuccessor(`page-${expectedOperation}`);
    firstPage.markActive(binding);
    const operation = durableOperations(binding).find(candidate => candidate.method.endsWith(expectedOperation));
    assert.ok(operation);
    firstPage.checkpointOperation(operation);
    const refreshedPage = openJournal(storage, `refresh-${expectedOperation}`);
    const effects = [];

    const recovered = await reconcileProductP2Predecessor({
      journal: refreshedPage,
      replay_operation: async retained => {
        effects.push(['operation', retained]);
      },
      activate_exact: async retained => {
        effects.push(['activate', retained]);
        return { replayed: true };
      },
      close_exact: async retained => {
        effects.push(['close', retained]);
      },
      error_reason: () => undefined,
      activation_retryable: () => false,
    });

    assert.deepEqual(recovered, { kind: 'ready' });
    assert.deepEqual(
      effects,
      expectedOperation === 'presentation.ack'
        ? [
            ['activate', binding],
            ['close', binding],
          ]
        : [
            ['operation', operation],
            ['activate', binding],
            ['close', binding],
          ],
    );
    assert.equal(refreshedPage.snapshot().phase, 'closed');
    assert.equal(refreshedPage.snapshot().pending_operation, null);
    if (expectedOperation === 'presentation.ack') {
      assert.deepEqual(refreshedPage.snapshot().retired_presentation_acks, [operation]);
      const successor = refreshedPage.prepareSuccessor('page-after-retired-ack');
      refreshedPage.markActive(successor);
      const background = await reconcileRetiredProductP2PresentationAcks({
        journal: refreshedPage,
        replay_operation: async retained => effects.push(['operation', retained]),
        operation_definitive: () => false,
      });
      assert.deepEqual(background, { kind: 'ready', retained: 0 });
      assert.deepEqual(refreshedPage.snapshot().binding, successor);
      assert.equal(refreshedPage.snapshot().phase, 'active');
      assert.deepEqual(refreshedPage.snapshot().retired_presentation_acks, []);
    } else {
      assert.deepEqual(refreshedPage.snapshot().retired_presentation_acks, []);
    }
  }
});

test('recovered operation result is idempotently published before the exact journal CAS settles', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage, 'client-recovered-result');
  const binding = firstPage.prepareSuccessor('page-recovered-result');
  firstPage.markActive(binding);
  const [operation] = durableOperations(binding);
  firstPage.checkpointOperation(operation);
  const refreshedPage = openJournal(storage, 'refresh-recovered-result');
  const result = { status: 'task_origin_accepted', response: { response_id: 'server-response' } };
  const effects = [];

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    replay_operation: async retained => {
      effects.push(['operation', retained.request_id]);
      return result;
    },
    on_operation_recovered: (retained, recoveredResult) => {
      assert.deepEqual(refreshedPage.snapshot().pending_operation, operation);
      effects.push(['publish', retained.request_id, recoveredResult]);
    },
    activate_exact: async () => {
      effects.push(['activate']);
      return { replayed: true };
    },
    close_exact: async () => {
      effects.push(['close']);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.deepEqual(effects, [['operation', operation.request_id], ['publish', operation.request_id, result], ['activate'], ['close']]);
  assert.equal(refreshedPage.snapshot().pending_operation, null);
});

test('failed settle retains the exact operation so idempotent adoption repeats on recovery', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage, 'client-adoption-retry');
  const binding = firstPage.prepareSuccessor('page-adoption-retry');
  firstPage.markActive(binding);
  const [operation] = durableOperations(binding);
  firstPage.checkpointOperation(operation);
  let failSettle = true;
  const baseSetItem = storage.setItem.bind(storage);
  storage.setItem = (key, value) => {
    const next = JSON.parse(value);
    if (failSettle && next.pending_operation === null && next.recovery_token !== null) {
      failSettle = false;
      throw new Error('settle unavailable');
    }
    baseSetItem(key, value);
  };
  let adoptions = 0;
  let replays = 0;
  let activationCalls = 0;
  const recover = journal =>
    reconcileProductP2Predecessor({
      journal,
      replay_operation: async () => {
        replays += 1;
        return { status: 'task_origin_accepted' };
      },
      on_operation_recovered: () => {
        adoptions += 1;
      },
      activate_exact: async () => {
        activationCalls += 1;
        return { replayed: true };
      },
      close_exact: async () => {},
      error_reason: () => undefined,
      activation_retryable: () => false,
    });

  assert.deepEqual(await recover(openJournal(storage, 'refresh-adoption-a')), {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.deepEqual(openJournal(storage, 'observer-adoption').snapshot().pending_operation, operation);
  assert.equal(activationCalls, 0);
  assert.deepEqual(await recover(openJournal(storage, 'refresh-adoption-b')), { kind: 'ready' });
  assert.equal(adoptions, 2);
  assert.equal(replays, 2);
  assert.equal(activationCalls, 1);
});

test('operation timeout or expired replay keeps activation close and successor effects at zero', async () => {
  for (const retryable of [true, false]) {
    const storage = memoryStorage();
    const firstPage = openJournal(storage, `client-${retryable}`);
    const binding = firstPage.prepareSuccessor(`page-${retryable}`);
    firstPage.markActive(binding);
    const [operation] = durableOperations(binding);
    firstPage.checkpointOperation(operation);
    const refreshedPage = openJournal(storage, `refresh-${retryable}`);
    const effects = [];
    const failure = retryable ? { code: 'REQUEST_TIMEOUT' } : { code: 'CONFLICT', reason: 'PRODUCT_OPERATION_REPLAY_EXPIRED' };

    const recovered = await reconcileProductP2Predecessor({
      journal: refreshedPage,
      replay_operation: async retained => {
        effects.push(['operation', retained.request_id]);
        throw failure;
      },
      activate_exact: async () => {
        effects.push(['activate']);
        return { replayed: true };
      },
      close_exact: async () => {
        effects.push(['close']);
      },
      error_reason: () => undefined,
      activation_retryable: () => false,
      operation_retryable: () => retryable,
    });

    assert.deepEqual(recovered, {
      kind: retryable ? 'retry' : 'blocked',
      reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
    });
    assert.deepEqual(effects, [['operation', operation.request_id]]);
    assert.equal(refreshedPage.snapshot().phase, 'operation_reconciling');
    assert.deepEqual(refreshedPage.snapshot().pending_operation, operation);
    assert.throws(() => refreshedPage.prepareSuccessor('forbidden'), new RegExp(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED));
  }
});

test('same-tab Session switches allocate independent interaction and correlation generations', () => {
  const storage = memoryStorage();
  const firstSession = ProductP2ActivationJournal.open({
    session_id: 'session-a',
    client_instance_id: 'same-tab-client',
    storage,
  });
  const firstBinding = firstSession.prepareSuccessor('same-tab-page');
  firstSession.markActive(firstBinding);
  firstSession.markClosing(firstBinding);
  firstSession.markClosed(firstBinding);

  const secondSession = ProductP2ActivationJournal.open({
    session_id: 'session-b',
    client_instance_id: 'same-tab-client',
    storage,
  });
  const secondBinding = secondSession.prepareSuccessor('same-tab-page');

  assert.notEqual(secondBinding.interaction_id, firstBinding.interaction_id);
  assert.notEqual(secondBinding.correlation_id, firstBinding.correlation_id);
  assert.equal(firstBinding.activation_generation, 1);
  assert.equal(secondBinding.activation_generation, 1);

  const restoredFirst = ProductP2ActivationJournal.open({
    session_id: 'session-a',
    client_instance_id: 'same-tab-client',
    storage,
  });
  assert.equal(restoredFirst.snapshot().interaction_id, firstBinding.interaction_id);
  assert.equal(restoredFirst.snapshot().correlation_id, firstBinding.correlation_id);
  assert.equal(restoredFirst.snapshot().last_generation, 1);
});

test('refresh activates a successor before a retired presentation ACK reports route-not-found', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage, 'client-missing-ack-route');
  const binding = firstPage.prepareSuccessor('page-missing-ack-route');
  firstPage.markActive(binding);
  const operation = durableOperations(binding)[1];
  firstPage.checkpointOperation(operation);
  const refreshedPage = openJournal(storage, 'refresh-missing-ack-route');
  const effects = [];

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => {
      effects.push(['activate']);
      return { replayed: false };
    },
    close_exact: async () => effects.push(['close']),
    error_reason: error => error?.reason,
    activation_retryable: () => false,
    operation_retryable: () => false,
  });

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.deepEqual(effects, [['activate'], ['close']]);
  assert.equal(refreshedPage.snapshot().phase, 'closed');
  assert.equal(refreshedPage.snapshot().pending_operation, null);
  assert.deepEqual(refreshedPage.snapshot().retired_presentation_acks, [operation]);
  const successor = refreshedPage.prepareSuccessor('page-after-missing-route');
  refreshedPage.markActive(successor);
  const background = await reconcileRetiredProductP2PresentationAcks({
    journal: refreshedPage,
    replay_operation: async retained => {
      effects.push(['operation', retained.request_id]);
      throw { code: 'NOT_FOUND', reason: 'PRODUCT_P2_ROUTE_NOT_FOUND' };
    },
    operation_definitive: error => error?.code === 'NOT_FOUND',
  });
  assert.deepEqual(background, { kind: 'ready', retained: 0 });
  assert.deepEqual(effects, [['activate'], ['close'], ['operation', operation.request_id]]);
  assert.deepEqual(refreshedPage.snapshot().binding, successor);
  assert.equal(refreshedPage.snapshot().phase, 'active');
});

test('refresh keeps a successor active when a retired presentation ACK is definitively rejected', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage, 'client-stale-ack-output');
  const binding = firstPage.prepareSuccessor('page-stale-ack-output');
  firstPage.markActive(binding);
  const operation = durableOperations(binding)[1];
  firstPage.checkpointOperation(operation);
  const refreshedPage = openJournal(storage, 'refresh-stale-ack-output');
  const effects = [];

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => {
      effects.push(['activate']);
      return { replayed: true };
    },
    close_exact: async () => effects.push(['close']),
    error_reason: error => error?.reason,
    activation_retryable: () => false,
    operation_retryable: () => false,
  });

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.deepEqual(effects, [['activate'], ['close']]);
  assert.equal(refreshedPage.snapshot().phase, 'closed');
  assert.equal(refreshedPage.snapshot().pending_operation, null);
  const successor = refreshedPage.prepareSuccessor('page-after-stale-output');
  refreshedPage.markActive(successor);
  const background = await reconcileRetiredProductP2PresentationAcks({
    journal: refreshedPage,
    replay_operation: async retained => {
      effects.push(['operation', retained.request_id]);
      throw { code: 'STALE', reason: 'UNKNOWN_AGENT_RESPONSE' };
    },
    operation_definitive: error => error?.code === 'STALE',
  });
  assert.deepEqual(background, { kind: 'ready', retained: 0 });
  assert.deepEqual(effects, [['activate'], ['close'], ['operation', operation.request_id]]);
  assert.deepEqual(refreshedPage.snapshot().binding, successor);
  assert.equal(refreshedPage.snapshot().phase, 'active');
});

test('retired presentation ACK timeout preserves one durable request without blocking the active successor', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage, 'client-retired-ack-timeout');
  const predecessor = firstPage.prepareSuccessor('page-retired-ack-timeout');
  firstPage.markActive(predecessor);
  const operation = durableOperations(predecessor)[1];
  firstPage.checkpointOperation(operation);
  const refreshedPage = openJournal(storage, 'refresh-retired-ack-timeout');
  assert.deepEqual(
    await reconcileProductP2Predecessor({
      journal: refreshedPage,
      activate_exact: async () => ({ replayed: true }),
      close_exact: async () => {},
      error_reason: () => undefined,
      activation_retryable: () => false,
    }),
    { kind: 'ready' },
  );
  const successor = refreshedPage.prepareSuccessor('page-retired-ack-successor');
  refreshedPage.markActive(successor);
  const requestIds = [];

  const timedOut = await reconcileRetiredProductP2PresentationAcks({
    journal: refreshedPage,
    replay_operation: async retained => {
      requestIds.push(retained.request_id);
      throw { code: 'REQUEST_TIMEOUT' };
    },
    operation_definitive: () => false,
  });

  assert.deepEqual(timedOut, { kind: 'retry', retained: 1 });
  assert.deepEqual(refreshedPage.snapshot().binding, successor);
  assert.equal(refreshedPage.snapshot().phase, 'active');
  assert.deepEqual(refreshedPage.snapshot().retired_presentation_acks, [operation]);

  const settled = await reconcileRetiredProductP2PresentationAcks({
    journal: refreshedPage,
    replay_operation: async retained => {
      requestIds.push(retained.request_id);
      return { accepted: true };
    },
    operation_definitive: () => false,
  });
  assert.deepEqual(settled, { kind: 'ready', retained: 0 });
  assert.deepEqual(requestIds, [operation.request_id, operation.request_id]);
  assert.deepEqual(refreshedPage.snapshot().binding, successor);
  assert.equal(refreshedPage.snapshot().phase, 'active');
});

test('authoritative accepted-false ACK response settles only the retired predecessor operation', async () => {
  const storage = memoryStorage();
  const journal = openJournal(storage, 'client-retired-ack-rejected');
  const predecessor = journal.prepareSuccessor('page-retired-ack-rejected');
  journal.markActive(predecessor);
  const operation = durableOperations(predecessor)[1];
  journal.checkpointOperation(operation);
  journal.retirePendingPresentationAck(predecessor);
  journal.markClosing(predecessor);
  journal.markClosed(predecessor);
  const successor = journal.prepareSuccessor('page-after-ack-rejected');
  journal.markActive(successor);
  let calls = 0;

  const result = await reconcileRetiredProductP2PresentationAcks({
    journal,
    replay_operation: retained =>
      replayProductP2DurableOperation({
        operation: retained,
        request: async (method, params, requestId) => {
          calls += 1;
          assert.equal(method, operation.method);
          assert.equal(requestId, operation.request_id);
          assert.deepEqual(params, operation.params);
          return {
            request_id: operation.request_id,
            ok: true,
            error: null,
            result: {
              status: 'presentation_acknowledged',
              ...operation.params,
              accepted: false,
              replayed: false,
              history_records_written: 0,
              history_pending: false,
            },
          };
        },
      }),
    operation_definitive: () => false,
  });

  assert.deepEqual(result, { kind: 'ready', retained: 0 });
  assert.equal(calls, 1);
  assert.deepEqual(journal.snapshot().binding, successor);
  assert.equal(journal.snapshot().phase, 'active');
  assert.deepEqual(journal.snapshot().retired_presentation_acks, []);
});

test('late predecessor ACK settlement preserves a successor ACK checkpoint byte-for-byte', () => {
  const storage = memoryStorage();
  const journal = openJournal(storage, 'client-overlapping-ack-settlement');
  const predecessor = journal.prepareSuccessor('page-overlapping-ack-predecessor');
  journal.markActive(predecessor);
  const predecessorAck = durableOperations(predecessor)[1];
  journal.checkpointOperation(predecessorAck);
  journal.retirePendingPresentationAck(predecessor);
  journal.markClosing(predecessor);
  journal.markClosed(predecessor);

  const successor = journal.prepareSuccessor('page-overlapping-ack-successor');
  journal.markActive(successor);
  const successorAck = {
    ...durableOperations(successor)[1],
    request_id: 'request-successor-ack',
    params: {
      ...durableOperations(successor)[1].params,
      response_id: 'response-successor',
      unit_id: 'unit-successor',
    },
  };
  journal.checkpointOperation(successorAck);
  const before = journal.snapshot();

  journal.settleOperation(predecessorAck);

  const after = journal.snapshot();
  assert.deepEqual(after.binding, before.binding);
  assert.equal(after.phase, 'operation_result_unknown');
  assert.deepEqual(after.pending_operation, successorAck);
  assert.deepEqual(after.retired_presentation_acks, []);
  journal.settleOperation(successorAck);
  assert.equal(journal.snapshot().phase, 'active');
});

test('retired presentation ACK settlement is isolated from a same-tab Session switch', async () => {
  const storage = memoryStorage();
  const oldSession = ProductP2ActivationJournal.open({
    session_id: 'session-old',
    client_instance_id: 'same-tab-client',
    storage,
  });
  const oldBinding = oldSession.prepareSuccessor('page-old');
  oldSession.markActive(oldBinding);
  const oldOperation = durableOperations({ ...oldBinding, session_id: 'session-old' })[1];
  oldSession.checkpointOperation(oldOperation);
  oldSession.retirePendingPresentationAck(oldBinding);
  oldSession.markClosing(oldBinding);
  oldSession.markClosed(oldBinding);

  const newSession = ProductP2ActivationJournal.open({
    session_id: 'session-new',
    client_instance_id: 'same-tab-client',
    storage,
  });
  const newBinding = newSession.prepareSuccessor('page-new');
  newSession.markActive(newBinding);
  let releaseOldAck;
  const oldSettlement = reconcileRetiredProductP2PresentationAcks({
    journal: oldSession,
    replay_operation: () =>
      new Promise(resolve => {
        releaseOldAck = resolve;
      }),
    operation_definitive: () => false,
  });
  await Promise.resolve();
  assert.equal(typeof releaseOldAck, 'function');
  assert.deepEqual(newSession.snapshot().binding, newBinding);
  assert.equal(newSession.snapshot().phase, 'active');

  releaseOldAck({ accepted: true });
  assert.deepEqual(await oldSettlement, { kind: 'ready', retained: 0 });
  assert.deepEqual(newSession.snapshot().binding, newBinding);
  assert.equal(newSession.snapshot().phase, 'active');
  assert.deepEqual(oldSession.snapshot().retired_presentation_acks, []);
});

test('retired presentation ACK storage is bounded and never evicts an unresolved predecessor', () => {
  const storage = memoryStorage();
  const journal = openJournal(storage, 'client-retired-ack-bound');
  for (let index = 0; index < 16; index += 1) {
    const binding = journal.prepareSuccessor(`page-retired-${index}`);
    journal.markActive(binding);
    const operation = {
      ...durableOperations(binding)[1],
      request_id: `request-retired-${index}`,
      params: {
        ...durableOperations(binding)[1].params,
        response_id: `response-retired-${index}`,
        unit_id: `unit-retired-${index}`,
      },
    };
    journal.checkpointOperation(operation);
    journal.retirePendingPresentationAck(binding);
    journal.markClosing(binding);
    journal.markClosed(binding);
  }
  const overflowBinding = journal.prepareSuccessor('page-retired-overflow');
  journal.markActive(overflowBinding);
  const overflowOperation = {
    ...durableOperations(overflowBinding)[1],
    request_id: 'request-retired-overflow',
  };
  journal.checkpointOperation(overflowOperation);
  const before = journal.snapshot();

  assert.throws(() => journal.retirePendingPresentationAck(overflowBinding), /bounded retired presentation ACK ledger is full/);
  assert.deepEqual(journal.snapshot(), before);
  assert.equal(journal.snapshot().retired_presentation_acks.length, 16);
});

test('retired presentation ACK parser rejects duplicate and future-generation durable authority', () => {
  const storage = memoryStorage();
  const journal = openJournal(storage, 'client-retired-ack-corrupt');
  const binding = journal.prepareSuccessor('page-retired-ack-corrupt');
  journal.markActive(binding);
  const operation = durableOperations(binding)[1];
  journal.checkpointOperation(operation);
  journal.retirePendingPresentationAck(binding);
  assert.throws(
    () => journal.checkpointOperation({ ...operation, request_id: 'request-duplicate-retired-ack' }),
    /presentation ACK is already retired/,
  );
  const [key] = storage.values.keys();
  const valid = JSON.parse(storage.values.get(key));

  const duplicateStorage = memoryStorage(new Map(storage.values));
  duplicateStorage.values.set(
    key,
    JSON.stringify({
      ...valid,
      retired_presentation_acks: [
        ...valid.retired_presentation_acks,
        { ...operation, request_id: 'request-corrupt-duplicate' },
      ],
    }),
  );
  assert.throws(() => openJournal(duplicateStorage, 'duplicate-reader'), /retired presentation ACKs are inconsistent/);

  const reusedRequestStorage = memoryStorage(new Map(storage.values));
  reusedRequestStorage.values.set(
    key,
    JSON.stringify({
      ...valid,
      retired_presentation_acks: [
        ...valid.retired_presentation_acks,
        {
          ...operation,
          params: {
            ...operation.params,
            response_id: 'response-corrupt-reused-request',
            unit_id: 'unit-corrupt-reused-request',
          },
        },
      ],
    }),
  );
  assert.throws(() => openJournal(reusedRequestStorage, 'reused-request-reader'), /retired presentation ACKs are inconsistent/);

  const futureStorage = memoryStorage(new Map(storage.values));
  futureStorage.values.set(
    key,
    JSON.stringify({
      ...valid,
      retired_presentation_acks: valid.retired_presentation_acks.map(retired => ({
        ...retired,
        params: {
          ...retired.params,
          activation_generation: valid.last_generation + 1,
          activation_id: 'future-retired-activation',
        },
      })),
    }),
  );
  assert.throws(() => openJournal(futureStorage, 'future-reader'), /retired presentation ACKs are inconsistent/);
});

test('foreign retained result keeps the journal pending and later recovery effects at zero', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage, 'client-foreign-result');
  const binding = firstPage.prepareSuccessor('page-foreign-result');
  firstPage.markActive(binding);
  const [operation] = durableOperations(binding);
  firstPage.checkpointOperation(operation);
  const refreshedPage = openJournal(storage, 'refresh-foreign-result');
  const effects = [];

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    replay_operation: retained =>
      replayProductP2DurableOperation({
        operation: retained,
        request: async () => {
          effects.push(['operation']);
          return {
            request_id: 'foreign-request',
            ok: true,
            result: {
              status: 'task_origin_accepted',
              ...binding,
              turn_id: operation.params.turn_id,
              commit_id: operation.params.commit_id,
              response: {
                interaction_id: binding.interaction_id,
                response_id: 'server-owned-response',
                response_generation: 0,
              },
            },
            error: null,
          };
        },
      }),
    on_operation_recovered: () => effects.push(['adopt']),
    activate_exact: async () => {
      effects.push(['activate']);
      return { replayed: true };
    },
    close_exact: async () => effects.push(['close']),
    error_reason: () => undefined,
    activation_retryable: () => false,
    operation_retryable: () => false,
  });

  assert.deepEqual(recovered, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.deepEqual(effects, [['operation']]);
  assert.deepEqual(refreshedPage.snapshot().pending_operation, operation);
  assert.equal(refreshedPage.snapshot().phase, 'operation_reconciling');
  assert.throws(() => refreshedPage.prepareSuccessor('forbidden'), new RegExp(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED));
});

test('strict operation parser rejects secrets raw audio and overflow without changing the active checkpoint', () => {
  const storage = memoryStorage();
  const journal = openJournal(storage);
  const binding = journal.prepareSuccessor('page-a');
  journal.markActive(binding);
  const [operation] = durableOperations(binding);
  const baseline = journal.snapshot();

  for (const forbidden of [
    { ...operation, params: { ...operation.params, auth_token: 'secret' } },
    { ...operation, params: { ...operation.params, raw_audio: 'bytes' } },
    { ...operation, params: { ...operation.params, text: 'x'.repeat(100_001) } },
    { ...operation, params: { ...operation.params, response_id: 'client-forged-response' } },
    { ...operation, params: { ...operation.params, text: '你'.repeat(45_000) } },
  ]) {
    assert.throws(() => journal.checkpointOperation(forbidden), /unexpected fields|invalid|durable bound/);
    assert.deepEqual(journal.snapshot(), baseline);
  }
});

test('activation-unknown closed predecessor adopts authoritative stale truth without another close', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markActivationResultUnknown(first);
  const refreshedPage = openJournal(storage, 'client-b');
  let closeCalls = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async binding => {
      assert.deepEqual(binding, first);
      throw { reason: 'ACTIVATION_GENERATION_STALE' };
    },
    close_exact: async () => {
      closeCalls += 1;
    },
    error_reason: error => error?.reason,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.equal(closeCalls, 0);
  assert.equal(refreshedPage.snapshot().phase, 'closed');
  const successor = refreshedPage.prepareSuccessor('page-b');
  assert.equal(successor.activation_generation, first.activation_generation + 1);
});

test('activation-unknown missing server state is exactly cleaned as unconfirmed', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markActivationResultUnknown(first);
  const refreshedPage = openJournal(storage, 'client-b');
  let closeCalls = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async binding => {
      assert.deepEqual(binding, first);
      return { replayed: false };
    },
    close_exact: async binding => {
      assert.deepEqual(binding, first);
      closeCalls += 1;
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.equal(closeCalls, 1);
  assert.equal(refreshedPage.snapshot().phase, 'closed');
  const successor = refreshedPage.prepareSuccessor('page-b');
  assert.equal(successor.activation_generation, 2);
});

test('corrupt and unavailable journals fail closed', () => {
  const storage = memoryStorage();
  openJournal(storage);

  const corrupt = memoryStorage(new Map(storage.values));
  const [key] = corrupt.values.keys();
  corrupt.values.set(key, '{');
  assert.throws(() => openJournal(corrupt), /journal JSON is invalid/);
  assert.throws(
    () =>
      openJournal({
        getItem: () => {
          throw new Error('blocked');
        },
        setItem: () => {},
      }),
    /cannot be read/
  );
});

test('checkpoint storage failure blocks recovery before opening a successor', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(first);
  const refreshedPage = openJournal(storage, 'client-b');
  let activationCalls = 0;
  storage.setItem = () => {
    throw new Error('storage unavailable');
  };

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => {
      activationCalls += 1;
      return { replayed: true };
    },
    close_exact: async () => {},
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(recovered, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.equal(activationCalls, 0);
  assert.throws(() => refreshedPage.prepareSuccessor('page-b'), new RegExp(PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED));
});

test('a late predecessor page cannot overwrite a refreshed successor journal', () => {
  const storage = memoryStorage();
  const predecessorPage = openJournal(storage);
  const predecessor = predecessorPage.prepareSuccessor('page-a');
  predecessorPage.markActive(predecessor);
  predecessorPage.markClosing(predecessor);

  const refreshedPage = openJournal(storage, 'client-b');
  refreshedPage.markReconciling(predecessor);
  assert.throws(() => predecessorPage.markClosed(predecessor), /journal ownership changed/);

  refreshedPage.markClosed(predecessor);
  const successor = refreshedPage.prepareSuccessor('page-b');
  refreshedPage.markActive(successor);
  assert.throws(() => predecessorPage.markClosed(predecessor), /journal ownership changed/);

  const nextPage = openJournal(storage, 'client-c');
  assert.deepEqual(nextPage.predecessorForRecovery(), successor);
  assert.equal(nextPage.snapshot().phase, 'active');
});

test('a delayed same-tab refresh recovery holds its exclusive lease until the exact predecessor settles', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const predecessor = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(predecessor);
  const delayedPage = openJournal(storage, 'client-delayed');
  const effects = [];
  let releaseDelayedActivation;

  const delayedRecovery = reconcileProductP2Predecessor({
    journal: delayedPage,
    activate_exact: binding => {
      effects.push(['delayed-activate', binding.activation_generation]);
      return new Promise(resolve => {
        releaseDelayedActivation = () => resolve({ replayed: true });
      });
    },
    close_exact: async binding => {
      effects.push(['delayed-close', binding.activation_generation]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
    is_current: () => true,
  });
  await Promise.resolve();
  assert.equal(typeof releaseDelayedActivation, 'function');

  const overlappingPage = openJournal(storage, 'client-overlapping');
  const overlappingRecovery = await reconcileProductP2Predecessor({
    journal: overlappingPage,
    activate_exact: async binding => {
      effects.push(['overlapping-activate', binding.activation_generation]);
      return { replayed: true };
    },
    close_exact: async binding => {
      effects.push(['overlapping-close', binding.activation_generation]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
    is_current: () => true,
  });
  assert.deepEqual(overlappingRecovery, {
    kind: 'superseded',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });

  releaseDelayedActivation();
  const delayedResult = await delayedRecovery;
  assert.deepEqual(delayedResult, { kind: 'ready' });
  const successor = delayedPage.prepareSuccessor('page-winning');
  delayedPage.markActive(successor);
  assert.equal(successor.activation_generation, predecessor.activation_generation + 1);
  assert.deepEqual(effects, [
    ['delayed-activate', 1],
    ['delayed-close', 1],
  ]);
  assert.deepEqual(openJournal(storage, 'client-observer').predecessorForRecovery(), successor);
});

test('one same-tab sessionStorage recovery owner prevents false-first true-second activation reordering', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const predecessor = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(predecessor);
  const falseFirstPage = openJournal(storage, 'client-false-first');
  const effects = [];
  let releaseFalseFirst;

  const falseFirstRecovery = reconcileProductP2Predecessor({
    journal: falseFirstPage,
    activate_exact: binding => {
      effects.push(['false-first-activate', binding.activation_generation]);
      return new Promise(resolve => {
        releaseFalseFirst = () => resolve({ replayed: false });
      });
    },
    close_exact: async binding => {
      effects.push(['false-first-close', binding.activation_generation]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });
  await Promise.resolve();
  assert.equal(typeof releaseFalseFirst, 'function');

  // A second journal owner in the same top-level tab, created after the first
  // checkpoint, sees `reconciling`; CAS alone must not make it a peer owner.
  const trueSecondPage = openJournal(storage, 'client-true-second');
  const trueSecondRecovery = await reconcileProductP2Predecessor({
    journal: trueSecondPage,
    activate_exact: async binding => {
      effects.push(['true-second-activate', binding.activation_generation]);
      return { replayed: true };
    },
    close_exact: async binding => {
      effects.push(['true-second-close', binding.activation_generation]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });

  assert.deepEqual(trueSecondRecovery, {
    kind: 'superseded',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.throws(() => trueSecondPage.prepareSuccessor('page-b'), /recovery is in progress|P2_REFRESH_RECONCILIATION_REQUIRED/);

  releaseFalseFirst();
  const falseFirstResult = await falseFirstRecovery;
  assert.deepEqual(falseFirstResult, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
  });
  assert.deepEqual(effects, [
    ['false-first-activate', 1],
    ['false-first-close', 1],
  ]);
  assert.equal(openJournal(storage, 'client-observer').snapshot().phase, 'activation_result_unknown');
});

test('a released same-tab browser lease takes over a crashed refresh token while fencing the old page', async () => {
  const storage = memoryStorage();
  const crashedPage = openJournal(storage, 'client-crashed');
  const predecessor = crashedPage.prepareSuccessor('page-crashed');
  crashedPage.markActive(predecessor);
  const crashedClaim = crashedPage.beginRecovery();
  const replacementPage = openJournal(storage, 'client-replacement');
  let releaseReplacement;

  const replacementRecovery = reconcileProductP2Predecessor({
    journal: replacementPage,
    activate_exact: () =>
      new Promise(resolve => {
        releaseReplacement = () => resolve({ replayed: true });
      }),
    close_exact: async () => {},
    error_reason: () => undefined,
    activation_retryable: () => false,
  });
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(typeof releaseReplacement, 'function');
  assert.throws(() => crashedPage.markClosed(predecessor, crashedClaim), /ownership changed/);

  releaseReplacement();
  assert.deepEqual(await replacementRecovery, { kind: 'ready' });
  const successor = replacementPage.prepareSuccessor('page-replacement');
  assert.equal(successor.activation_generation, 2);
});

test('contended browser recovery lease is superseded before every callback', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const binding = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(binding);
  const refreshedPage = openJournal(storage, 'client-b');
  let callbacks = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => {
      callbacks += 1;
      return { replayed: true };
    },
    close_exact: async () => {
      callbacks += 1;
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
    recovery_lease: {
      runExclusive: async () => null,
    },
  });

  assert.deepEqual(recovered, {
    kind: 'superseded',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.equal(callbacks, 0);
  assert.equal(refreshedPage.snapshot().phase, 'active');
});

test('missing browser Web Locks fails blocked before every callback', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const binding = firstPage.prepareSuccessor('page-a');
  firstPage.markActive(binding);
  const refreshedPage = openJournal(storage, 'client-b');
  const originalWindow = globalThis.window;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  let callbacks = 0;
  globalThis.window = {};
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {} });
  try {
    const recovered = await reconcileProductP2Predecessor({
      journal: refreshedPage,
      activate_exact: async () => {
        callbacks += 1;
        return { replayed: true };
      },
      close_exact: async () => {
        callbacks += 1;
      },
      error_reason: () => undefined,
      activation_retryable: () => false,
    });

    assert.deepEqual(recovered, {
      kind: 'blocked',
      reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
    });
    assert.equal(callbacks, 0);
    assert.equal(refreshedPage.snapshot().phase, 'active');
  } finally {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (navigatorDescriptor) Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
    else delete globalThis.navigator;
  }
});

test('refresh recovery adopts an exact close that wins before reconciliation', async () => {
  const storage = memoryStorage();
  const predecessorPage = openJournal(storage);
  const predecessor = predecessorPage.prepareSuccessor('page-a');
  predecessorPage.markActive(predecessor);
  predecessorPage.markClosing(predecessor);
  const refreshedPage = openJournal(storage, 'client-b');

  predecessorPage.markClosed(predecessor);
  let activationCalls = 0;
  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => {
      activationCalls += 1;
      return { replayed: true };
    },
    close_exact: async () => {},
    error_reason: () => undefined,
    activation_retryable: () => false,
  });
  const successor = refreshedPage.prepareSuccessor('page-b');

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.equal(activationCalls, 0);
  assert.equal(successor.activation_generation, 2);
});

test('an unconfirmed activation newly allocated during recovery closes and advances', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markClosing(first);
  const refreshedPage = openJournal(storage, 'client-b');
  let closeCalls = 0;

  const recovered = await reconcileProductP2Predecessor({
    journal: refreshedPage,
    activate_exact: async () => ({ replayed: false }),
    close_exact: async () => {
      closeCalls += 1;
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
  });
  const successor = refreshedPage.prepareSuccessor('page-b');

  assert.deepEqual(recovered, { kind: 'ready' });
  assert.equal(closeCalls, 1);
  assert.equal(successor.activation_generation, first.activation_generation + 1);
});
