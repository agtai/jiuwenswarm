import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  PRODUCT_P2_REFRESH_SERVER_STATE_LOST,
  ProductP2ActivationJournal,
  reconcileProductP2Predecessor,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productP2ActivationJournal.js';

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
  assert.equal(refreshedPage.snapshot().phase, 'result_unknown');
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

test('result-unknown, corrupt, and unavailable journals fail closed', async () => {
  const storage = memoryStorage();
  const firstPage = openJournal(storage);
  const first = firstPage.prepareSuccessor('page-a');
  firstPage.markResultUnknown(first);
  const refreshedPage = openJournal(storage, 'client-b');
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
  assert.deepEqual(recovered, {
    kind: 'blocked',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.equal(activationCalls, 0);

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

test('a delayed recovery never adopts or closes a same-session successor', async () => {
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

  const winningPage = openJournal(storage, 'client-winning');
  const winningRecovery = await reconcileProductP2Predecessor({
    journal: winningPage,
    activate_exact: async binding => {
      effects.push(['winning-activate', binding.activation_generation]);
      return { replayed: true };
    },
    close_exact: async binding => {
      effects.push(['winning-close', binding.activation_generation]);
    },
    error_reason: () => undefined,
    activation_retryable: () => false,
    is_current: () => true,
  });
  assert.deepEqual(winningRecovery, { kind: 'ready' });
  const successor = winningPage.prepareSuccessor('page-winning');
  winningPage.markActive(successor);

  releaseDelayedActivation();
  const delayedResult = await delayedRecovery;
  assert.deepEqual(delayedResult, {
    kind: 'superseded',
    reason: PRODUCT_P2_REFRESH_RECONCILIATION_REQUIRED,
  });
  assert.equal(successor.activation_generation, predecessor.activation_generation + 1);
  assert.deepEqual(effects, [
    ['delayed-activate', 1],
    ['winning-activate', 1],
    ['winning-close', 1],
  ]);
  assert.deepEqual(openJournal(storage, 'client-observer').predecessorForRecovery(), successor);
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
