import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED,
  BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE,
  createBrowserLiveVoiceOwnership,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/browserLiveVoiceOwnership.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function flushAsyncWork() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}

class FakeChannelHub {
  #channels = new Map();

  create = name => {
    const listeners = new Set();
    const channel = {
      addEventListener(type, listener) {
        if (type === 'message') listeners.add(listener);
      },
      removeEventListener(type, listener) {
        if (type === 'message') listeners.delete(listener);
      },
      postMessage: data => {
        queueMicrotask(() => {
          for (const peer of this.#channels.get(name) ?? []) {
            if (peer !== channel) peer.deliver(data);
          }
        });
      },
      close: () => {
        this.#channels.get(name)?.delete(channel);
      },
      deliver(data) {
        for (const listener of listeners) listener({ data });
      },
    };
    const channels = this.#channels.get(name) ?? new Set();
    channels.add(channel);
    this.#channels.set(name, channels);
    return channel;
  };

  inject(name, data) {
    for (const channel of this.#channels.get(name) ?? []) channel.deliver(data);
  }
}

class FakeLockManager {
  #queues = new Map();
  #active = new Set();

  request = (name, signal, callback) => new Promise((resolve, reject) => {
    const entry = { callback, reject, resolve, signal, aborted: false };
    const onAbort = () => {
      entry.aborted = true;
      const error = new Error('lock request aborted');
      error.name = 'AbortError';
      reject(error);
      this.#drain(name);
    };
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener('abort', onAbort, { once: true });
    const queue = this.#queues.get(name) ?? [];
    queue.push(entry);
    this.#queues.set(name, queue);
    queueMicrotask(() => this.#drain(name));
  });

  #drain(name) {
    if (this.#active.has(name)) return;
    const queue = this.#queues.get(name) ?? [];
    let entry = queue.shift();
    while (entry?.aborted) entry = queue.shift();
    if (!entry) return;
    this.#active.add(name);
    Promise.resolve(entry.callback(Object.freeze({ name, mode: 'exclusive' })))
      .then(entry.resolve, entry.reject)
      .finally(() => {
        this.#active.delete(name);
        queueMicrotask(() => this.#drain(name));
      });
  }
}

function ownershipEnvironment({ hub, locks, now, randomId }) {
  return {
    createChannel: hub === null ? null : hub?.create,
    requestLock: locks === null ? null : locks?.request,
    now: typeof now === 'function' ? now : () => now,
    randomId: () => randomId,
  };
}

test('latest tab starts only after the prior Live Voice owner finishes cleanup', async () => {
  const hub = new FakeChannelHub();
  const locks = new FakeLockManager();
  const cleanup = deferred();
  const events = [];
  const ownerA = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 100, randomId: 'tab-a' }),
  );
  const ownerB = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 200, randomId: 'tab-b' }),
  );

  await ownerA.acquire(async () => {
    events.push('a-close-start');
    await cleanup.promise;
    events.push('a-close-finished');
  });
  events.push('a-acquired');

  let bAcquired = false;
  const acquireB = ownerB.acquire(async () => {}).then(() => {
    bAcquired = true;
    events.push('b-acquired');
  });
  await flushAsyncWork();

  assert.equal(ownerA.isOwner(), true);
  assert.equal(bAcquired, false);
  assert.deepEqual(events, ['a-acquired', 'a-close-start']);

  cleanup.resolve();
  await acquireB;
  assert.equal(ownerA.isOwner(), false);
  assert.equal(ownerB.isOwner(), true);
  assert.deepEqual(events, ['a-acquired', 'a-close-start', 'a-close-finished', 'b-acquired']);

  await ownerB.release();
  await ownerA.dispose();
  await ownerB.dispose();
});

test('failed prior-owner cleanup keeps the browser lock and blocks the successor', async () => {
  const hub = new FakeChannelHub();
  const locks = new FakeLockManager();
  const ownerA = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 100, randomId: 'tab-a' }),
  );
  const ownerB = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 200, randomId: 'tab-b' }),
  );

  let cleanupAttempts = 0;
  await ownerA.acquire(async () => {
    cleanupAttempts += 1;
    if (cleanupAttempts === 1) throw new Error('microphone cleanup failed');
  });
  let bAcquired = false;
  const acquireB = ownerB.acquire(async () => {}).then(() => {
    bAcquired = true;
  });
  await flushAsyncWork();

  assert.equal(ownerA.isOwner(), true);
  assert.equal(ownerB.isOwner(), false);
  assert.equal(bAcquired, false);

  const retryB = ownerB.acquire(async () => {});
  await Promise.all([acquireB, retryB]);
  assert.equal(cleanupAttempts, 2);
  await ownerB.release();
  await ownerA.dispose();
  await ownerB.dispose();
});

test('an older takeover notice cannot revoke the current browser owner', async () => {
  const hub = new FakeChannelHub();
  const locks = new FakeLockManager();
  let cleanupCalls = 0;
  const owner = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 200, randomId: 'current-tab' }),
  );

  await owner.acquire(async () => {
    cleanupCalls += 1;
  });
  hub.inject('jiuwenswarm.live-voice.capture-owner.v1', {
    type: 'takeover',
    claim: { issued_at: 100, claim_id: 'older-tab' },
  });
  await flushAsyncWork();

  assert.equal(cleanupCalls, 0);
  assert.equal(owner.isOwner(), true);
  await owner.release();
  await owner.dispose();
});

test('same-tab retry reuses its exact ownership instead of reopening the lock', async () => {
  const hub = new FakeChannelHub();
  const locks = new FakeLockManager();
  const owner = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 100, randomId: 'same-tab' }),
  );

  await owner.acquire(async () => {});
  await owner.acquire(async () => {});
  assert.equal(owner.isOwner(), true);

  await owner.release();
  assert.equal(owner.isOwner(), false);
  await owner.dispose();
});

test('re-enable during takeover waits for release and returns as a newer claim', async () => {
  const hub = new FakeChannelHub();
  const locks = new FakeLockManager();
  const cleanupA = deferred();
  const events = [];
  let nowA = 100;
  const ownerA = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: () => nowA, randomId: 'tab-a' }),
  );
  const ownerB = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks, now: 200, randomId: 'tab-b' }),
  );

  await ownerA.acquire(async () => {
    events.push('a-close');
    await cleanupA.promise;
  });
  const acquireB = ownerB.acquire(async () => {
    events.push('b-close');
  }).then(
    () => events.push('b-acquired'),
    error => {
      assert.equal(error?.message, BROWSER_LIVE_VOICE_OWNERSHIP_SUPERSEDED);
      events.push('b-superseded');
    },
  );
  await flushAsyncWork();
  nowA = 300;
  let aReacquired = false;
  const reacquireA = ownerA.acquire(async () => {}).then(() => {
    aReacquired = true;
    events.push('a-reacquired');
  });
  await flushAsyncWork();
  assert.equal(aReacquired, false);

  cleanupA.resolve();
  await Promise.all([acquireB, reacquireA]);
  assert.deepEqual(events, ['a-close', 'b-close', 'b-superseded', 'a-reacquired']);
  assert.equal(ownerA.isOwner(), true);
  assert.equal(ownerB.isOwner(), false);

  await ownerA.release();
  await ownerA.dispose();
  await ownerB.dispose();
});

test('missing Web Locks or BroadcastChannel fails closed before capture ownership', async () => {
  const hub = new FakeChannelHub();
  const locks = new FakeLockManager();
  const withoutLocks = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub, locks: null, now: 100, randomId: 'no-locks' }),
  );
  const withoutChannel = createBrowserLiveVoiceOwnership(
    ownershipEnvironment({ hub: null, locks, now: 100, randomId: 'no-channel' }),
  );

  await assert.rejects(
    withoutLocks.acquire(async () => {}),
    error => error instanceof Error && error.message === BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE,
  );
  await assert.rejects(
    withoutChannel.acquire(async () => {}),
    error => error instanceof Error && error.message === BROWSER_LIVE_VOICE_OWNERSHIP_UNAVAILABLE,
  );
  assert.equal(withoutLocks.isOwner(), false);
  assert.equal(withoutChannel.isOwner(), false);
  await withoutLocks.dispose();
  await withoutChannel.dispose();
});
