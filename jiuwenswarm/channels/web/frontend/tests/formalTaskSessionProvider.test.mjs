import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join } from 'node:path';
import test, { after } from 'node:test';
import { build } from 'esbuild';
import React from 'react';
import { act, create } from 'react-test-renderer';

const directory = await mkdtemp(fileURLToPath(new URL('../node_modules/.cache/formal-task-host-', import.meta.url)));
after(() => rm(directory, { recursive: true, force: true }));
const output = join(directory, 'host.mjs');
await build({
  stdin: {
    contents: `export * from './src/features/tasks/FormalTaskSessionProvider'; export { useFormalTaskStore } from './src/stores/formalTaskStore';`,
    resolveDir: fileURLToPath(new URL('..', import.meta.url)),
    loader: 'tsx',
  },
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  outfile: output,
  define: { 'import.meta.env': '{}' },
});
const {
  FormalTaskSessionProvider: Host,
  useFormalTaskSession,
  useFormalTaskStore,
} = await import(pathToFileURL(output).href);

function environment() {
  const previous = globalThis.window;
  const values = new Map();
  globalThis.window = {
    sessionStorage: {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  };
  return {
    values,
    restore: () => {
      globalThis.window = previous;
    },
  };
}
function empty(id) {
  return {
    request_id: id,
    ok: true,
    error: null,
    result: { tasks: [], has_more: false, next_cursor: null, supported_operations: [] },
  };
}
const settle = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

test('Host reader exists without Voice, survives consumer detach and reconnects read-only', async () => {
  const env = environment();
  const calls = [];
  const request = async (method, params, options) => {
    calls.push({ method, params, options });
    assert.equal(method, 'live_voice.task.list');
    return empty(options.requestId);
  };
  let observed;
  function Consumer() {
    observed = useFormalTaskSession();
    return null;
  }
  const element = (connected, consumer = false) =>
    React.createElement(
      Host,
      { sessionId: 'host-a', enabled: true, connected, request },
      consumer ? React.createElement(Consumer) : null,
    );
  let renderer;
  try {
    await act(async () => {
      renderer = create(element(true));
      await settle();
    });
    const owner = useFormalTaskStore.getState().entries['host-a'].owner;
    assert.equal(owner.snapshot().status, 'ready', owner.snapshot().reason);
    assert.equal(calls.length, 1);
    await act(async () => {
      renderer.update(element(true, true));
      await settle();
    });
    assert.equal(observed.owner, owner);
    assert.equal(observed.snapshot, useFormalTaskStore.getState().entries['host-a'].snapshot);
    await act(async () => {
      renderer.update(element(true));
      await settle();
    });
    assert.equal(owner.snapshot().status, 'ready', owner.snapshot().reason);
    assert.equal(calls.length, 1);
    await act(async () => {
      renderer.update(element(false));
      await settle();
    });
    assert.equal(owner.snapshot().status, 'disconnected');
    await act(async () => {
      renderer.update(element(true));
      await settle();
    });
    assert.equal(useFormalTaskStore.getState().entries['host-a'].owner, owner);
    assert.equal(owner.snapshot().status, 'ready', owner.snapshot().reason);
    assert.equal(calls.length, 2);
    await act(async () => {
      renderer.unmount();
    });
    renderer = null;
    assert.equal(owner.snapshot().status, 'closed');
    assert.equal(useFormalTaskStore.getState().entries['host-a'], undefined);
    assert.equal(calls.length, 2);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    env.restore();
  }
});

test('late previous-session response cannot publish into the current Host session', async () => {
  const env = environment();
  let release;
  const calls = [];
  const request = (method, params, options) => {
    calls.push({ method, params });
    if (params.session_id === 'host-old')
      return new Promise((resolve) => {
        release = () => resolve(empty(options.requestId));
      });
    return Promise.resolve(empty(options.requestId));
  };
  const element = (sessionId) => React.createElement(Host, { sessionId, connected: true, enabled: true, request });
  let renderer;
  try {
    await act(async () => {
      renderer = create(element('host-old'));
      await settle();
    });
    const old = useFormalTaskStore.getState().entries['host-old'].owner;
    await act(async () => {
      renderer.update(element('host-new'));
      await settle();
    });
    const current = useFormalTaskStore.getState().entries['host-new'];
    await act(async () => {
      release();
      await settle();
    });
    assert.equal(old.snapshot().status, 'closed');
    assert.equal(useFormalTaskStore.getState().entries['host-old'], undefined);
    assert.equal(useFormalTaskStore.getState().entries['host-new'], current);
    assert.equal(current.snapshot.status, 'ready');
    assert.deepEqual(
      calls.map((call) => call.params.session_id),
      ['host-old', 'host-new'],
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    env.restore();
  }
});

test('Host polling refreshes a live task after the Voice consumer detaches', async () => {
  const env = environment();
  const task = {
    task_id: 'task-live',
    attempt_id: 'attempt-live',
    correlation_id: 'correlation-live',
    scope: { subject_id: 'subject', session_id: 'host-poll', project_id: 'project', assurance: 'authenticated' },
    spec: { name: 'Live task' },
    state: 'running',
    outcome: null,
    queued: false,
    event_head: 1,
    revision: { number: 1, predecessor_task_id: null },
    successor_task_id: null,
  };
  const calls = [];
  const request = async (method, params, options) => {
    calls.push(method);
    const result =
      method === 'live_voice.task.list'
        ? { tasks: [task], has_more: false, next_cursor: null, supported_operations: [] }
        : method === 'live_voice.task.status'
          ? { task, supported_operations: [],
              attempt: { task_id: task.task_id, attempt_id: task.attempt_id, attempt_number: 1, state: task.state, outcome: task.outcome },
              retry_admission: { task_id: task.task_id, eligible: false, reason: 'TASK_RETRY_STATE_CONFLICT', attempt_id: null, attempt_number: null } }
          : method === 'live_voice.task.events'
            ? {
                task_id: task.task_id,
                after_seq: -1,
                head_seq: 1,
                has_more: false,
                next_after_seq: null,
                events: ['accepted', 'running'].map((state, seq) => ({
                    correlation_id: task.correlation_id,
                    scope: task.scope,
                    task_id: task.task_id,
                    attempt_id: task.attempt_id,
                    seq,
                    event_id: `event-${state}`,
                    event_type: `task.${state}`,
                    producer: 'task_core',
                    source_event_id: seq === 0 ? null : 'source-running',
                    causation_id: seq === 0 ? 'create-live' : 'source-running',
                    state,
                    outcome: null,
                    details: {},
                  })),
              }
            : method === 'live_voice.task.result'
              ? { task_id: task.task_id, availability: 'not_ready', task_result: null }
              : assert.fail(`unexpected effect ${method}`);
    return { request_id: options.requestId, ok: true, error: null, result };
  };
  function VoiceConsumer() {
    useFormalTaskSession();
    return null;
  }
  const element = (voice) =>
    React.createElement(
      Host,
      { sessionId: 'host-poll', connected: true, enabled: true, request },
      voice ? React.createElement(VoiceConsumer) : null,
    );
  let renderer;
  try {
    await act(async () => {
      renderer = create(element(true));
      await settle();
    });
    const owner = useFormalTaskStore.getState().entries['host-poll'].owner;
    assert.equal(owner.snapshot().status, 'ready', owner.snapshot().reason);
    await act(async () => {
      renderer.update(element(false));
      await settle();
    });
    const initial = calls.length;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5_100));
    });
    assert.deepEqual(calls.slice(initial), [
      'live_voice.task.list',
      'live_voice.task.status',
      'live_voice.task.events',
      'live_voice.task.result',
    ]);
    assert.equal(useFormalTaskStore.getState().entries['host-poll'].owner, owner);
    assert.equal(owner.snapshot().tasks[0].canonical_state, 'running');
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    env.restore();
  }
});

test('Host reconnect retains an unknown mutation and only explicit recovery replays its exact RPC', async () => {
  const env = environment();
  const mutations = [];
  const request = async (method, params, options) => {
    if (method === 'live_voice.task.list') {
      const response = empty(options.requestId);
      response.result.supported_operations = ['task.create'];
      return response;
    }
    mutations.push(structuredClone({ method, params, options }));
    throw new Error('response lost');
  };
  const element = (connected) =>
    React.createElement(Host, { sessionId: 'host-unknown', connected, enabled: true, request });
  let renderer;
  try {
    await act(async () => {
      renderer = create(element(true));
      await settle();
    });
    const owner = useFormalTaskStore.getState().entries['host-unknown'].owner;
    await act(async () => {
      await assert.rejects(
        owner.issue({ operation: 'task.create', name: 'retained', instruction: 'original input' }),
        /response lost/,
      );
    });
    assert.equal(owner.snapshot().command.phase, 'unknown');
    await act(async () => {
      renderer.update(element(false));
      await settle();
    });
    await act(async () => {
      renderer.update(element(true));
      await settle();
    });
    assert.equal(useFormalTaskStore.getState().entries['host-unknown'].owner, owner);
    assert.equal(owner.snapshot().command.phase, 'unknown');
    assert.equal(mutations.length, 1);
    await act(async () => {
      await assert.rejects(owner.confirm(), /response lost/);
    });
    assert.equal(mutations.length, 2);
    assert.deepEqual(mutations[1], mutations[0]);
    assert.equal(owner.snapshot().command.phase, 'unknown');
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    env.restore();
  }
});

for (const mode of ['disabled', 'new', 'null', 'malformed', 'unavailable']) {
  test(`Host ${mode} admission emits no task request`, async () => {
    const env = environment();
    if (mode === 'malformed') env.values.set('jiuwenswarm.live_voice.product_p3_task_target.v1:host-denied', '{');
    if (mode === 'unavailable')
      globalThis.window.sessionStorage.getItem = () => {
        throw new Error('unavailable');
      };
    let snapshot;
    function Consumer() {
      snapshot = useFormalTaskSession().snapshot;
      return null;
    }
    const calls = [];
    let renderer;
    try {
      await act(async () => {
        renderer = create(
          React.createElement(
            Host,
            {
              sessionId: mode === 'null' ? null : mode === 'new' ? 'new' : 'host-denied',
              enabled: mode !== 'disabled',
              connected: true,
              request: (...args) => {
                calls.push(args);
                return Promise.reject(new Error('forbidden request'));
              },
            },
            React.createElement(Consumer),
          ),
        );
        await settle();
      });
      assert.deepEqual(calls, []);
      assert.equal(
        snapshot.status,
        mode === 'disabled' ? 'disabled' : ['new', 'null'].includes(mode) ? 'idle' : 'failed',
      );
      assert.equal(useFormalTaskStore.getState().entries['host-denied'], undefined);
    } finally {
      if (renderer) await act(async () => renderer.unmount());
      env.restore();
    }
  });
}
