import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import React from 'react';
import { act, create } from 'react-test-renderer';
import i18next from 'i18next';
import { I18nextProvider } from 'react-i18next';

const root = fileURLToPath(new URL('..', import.meta.url));
const output = new URL('../node_modules/.cache/live-voice-home-start/entry.mjs', import.meta.url);
await mkdir(new URL('.', output), { recursive: true });
await build({
  stdin: {
    contents: `
    export { useProductVoiceSessionStart } from './src/components/ChatPanel/useProductVoiceSessionStart';
    export { createLiveVoiceConversation } from './src/multi-session/state/createLiveVoiceConversation';
    export { LiveVoiceDemoBar } from './src/components/ChatPanel/LiveVoiceDemoBar';
    export * from './src/stores';`,
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  packages: 'external',
  platform: 'node',
  format: 'esm',
  loader: { '.css': 'empty' },
  define: { 'import.meta.env': '{}' },
  outfile: fileURLToPath(output),
});
const {
  useProductVoiceSessionStart,
  createLiveVoiceConversation,
  LiveVoiceDemoBar,
  useChatStore,
  useSessionStore,
  useGoalStore,
  usePlanStore,
  ensureSessionRuntimes,
} = await import(output.href);
await i18next.init({
  lng: 'zh',
  resources: {
    zh: {
      translation: {
        liveVoice: {
          enable: '开启语音',
          exit: '退出语音',
          label: 'Live Voice',
          startingSession: '正在开启语音',
        },
      },
    },
  },
});

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};
async function mount(overrides = {}) {
  let lifecycle;
  const calls = [];
  let props = { sessionId: 'new', available: false, canPrepare: true, start: async () => calls.push('start'), ...overrides };
  function Harness(input) {
    lifecycle = useProductVoiceSessionStart(input);
    return null;
  }
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(Harness, props));
  });
  return {
    calls,
    get value() {
      return lifecycle;
    },
    update: async patch => {
      props = { ...props, ...patch };
      await act(async () => renderer.update(React.createElement(Harness, props)));
    },
    close: async () => act(async () => renderer.unmount()),
  };
}

test('home click allocates once and starts only after the exact Session becomes available', async () => {
  const pending = deferred();
  let accept;
  let creates = 0;
  const h = await mount({
    prepare: callback => {
      creates++;
      accept = callback;
      return pending.promise;
    },
  });
  let first;
  await act(async () => {
    first = h.value.start();
    void h.value.start();
  });
  assert.equal(creates, 1);
  assert.equal(h.value.pending, true);
  assert.deepEqual(h.calls, []);
  await act(async () => {
    assert.equal(accept('voice-home-a'), true);
    pending.resolve('voice-home-a');
    await first;
  });
  await h.update({ sessionId: 'voice-home-a' });
  assert.deepEqual(h.calls, [], 'allocation alone must not authorize capture');
  await h.update({ available: true });
  assert.deepEqual(h.calls, ['start']);
  assert.equal(h.value.pending, false);
  await h.update({ available: true });
  assert.deepEqual(h.calls, ['start']);
  await h.close();
});

for (const kind of ['cancel', 'navigate', 'unmount', 'disconnect']) {
  test(`late Session allocation after ${kind} cannot start audio or adopt another Session`, async () => {
    const pending = deferred();
    let accept;
    const h = await mount({
      prepare: callback => {
        accept = callback;
        return pending.promise;
      },
    });
    let task;
    await act(async () => {
      task = h.value.start();
    });
    if (kind === 'cancel') await act(async () => h.value.cancel());
    if (kind === 'navigate') {
      await h.update({ sessionId: 'another-session' });
      await h.update({ sessionId: 'new' });
    }
    if (kind === 'disconnect') await h.update({ canPrepare: false });
    if (kind === 'unmount') await h.close();
    await act(async () => {
      assert.equal(accept('late-session'), false);
      pending.resolve(null);
      await task;
    });
    assert.deepEqual(h.calls, []);
    if (kind !== 'unmount') await h.close();
  });
}

test('creation error can retry; activation timeout cannot start after a late ready event', async () => {
  const h = await mount({
    activationTimeoutMs: 15,
    prepare: async () => {
      throw new Error('offline');
    },
  });
  await act(async () => h.value.start());
  assert.equal(h.value.failed, true);
  assert.equal(h.value.pending, false);
  assert.deepEqual(h.calls, []);
  await h.update({ prepare: async accept => (accept('voice-retry') ? 'voice-retry' : null) });
  await act(async () => h.value.start());
  await h.update({ sessionId: 'voice-retry' });
  await act(async () => new Promise(resolve => setTimeout(resolve, 25)));
  assert.equal(h.value.failed, true);
  assert.equal(h.value.pending, false);
  await h.update({ available: true });
  assert.deepEqual(h.calls, []);
  await h.close();
});

test('existing Session and unavailable/feature-off entry preserve their old behavior', async () => {
  let creates = 0;
  const h = await mount({
    sessionId: 'existing',
    available: true,
    prepare: async () => {
      creates++;
      return 'wrong';
    },
  });
  await act(async () => h.value.start());
  assert.deepEqual(h.calls, ['start']);
  assert.equal(creates, 0);
  await h.update({ sessionId: 'new', available: false, canPrepare: false });
  await act(async () => h.value.start());
  assert.equal(creates, 0);
  assert.deepEqual(h.calls, ['start']);
  await h.close();
});

test('real stores receive an idle empty Session with scoped settings and the unsent draft', async () => {
  ensureSessionRuntimes('new');
  useChatStore.getState().setInputValue('new', 'unsent draft');
  usePlanStore.getState().setActive('new', true, { explicitEntry: true });
  useGoalStore.getState().setArmed('new', true);
  const calls = [];
  let attempt = 0;
  const session = await createLiveVoiceConversation({
    request: async (method, params) => {
      calls.push({ method, params });
      if (attempt++ === 0) throw { code: 'REQUEST_TIMEOUT' };
      return { session_id: 'voice-created', project_id: 'project-a', project_dir: '/project-a', work_mode: 'code' };
    },
    params: { create_token: 'same-token', mode: 'agent', model_name: 'selected-model', project_id: 'project-a', project_dir: '/project-a', work_mode: 'code' },
    settings: { mode: 'agent', selectedModelName: 'selected-model', projectDir: '/project-a' },
    accept: () => true,
  });
  assert.equal(session.session_id, 'voice-created');
  assert.equal(session.is_processing, false);
  assert.equal(session.project_id, 'project-a');
  assert.equal(session.message_count, 0);
  assert.deepEqual(
    calls.map(x => x.method),
    ['session.create', 'session.create'],
  );
  assert.equal(calls[0].params.create_token, calls[1].params.create_token);
  const runtime = useChatStore.getState().getRuntime(session.session_id);
  assert.equal(runtime.isProcessing, false);
  assert.deepEqual(runtime.messages, []);
  assert.equal(runtime.inputValue, 'unsent draft');
  assert.equal(useSessionStore.getState().getRuntime(session.session_id).selectedModelName, 'selected-model');
  assert.equal(usePlanStore.getState().hasPendingExplicitEntry(session.session_id), true);
  assert.equal(useGoalStore.getState().runtimes[session.session_id].armed, true);
});

test('stale allocation has zero local history, draft or Session adoption effects', async () => {
  ensureSessionRuntimes('new');
  useChatStore.getState().setInputValue('new', 'keep me');
  const before = useSessionStore.getState().sessions.length;
  const session = await createLiveVoiceConversation({
    request: async () => ({ session_id: 'stale-created' }),
    params: { create_token: 'stale', work_mode: 'code', project_id: 'project-a', project_dir: '/project-a' },
    settings: { mode: 'agent', selectedModelName: null },
    accept: () => false,
  });
  assert.equal(session, null);
  assert.equal(useSessionStore.getState().sessions.length, before);
  assert.equal(useChatStore.getState().runtimes['stale-created'], undefined);
  assert.equal(useChatStore.getState().getRuntime('new').inputValue, 'keep me');
});

test('projectless entry explains the existing prerequisite without allocating or starting; navigation clears the failure', async () => {
  let requests = 0;
  const h = await mount({
    prepare: accept =>
      createLiveVoiceConversation({
        request: async () => {
          requests++;
          throw new Error('must not dispatch');
        },
        params: { work_mode: 'work' },
        settings: { mode: 'agent', selectedModelName: null },
        accept,
      }),
  });
  await act(async () => h.value.start());
  assert.equal(h.value.failed, true);
  assert.equal(h.value.projectRequired, true);
  assert.equal(h.value.pending, false);
  assert.equal(requests, 0);
  assert.deepEqual(h.calls, []);
  await h.update({ sessionId: 'other' });
  assert.equal(h.value.failed, false);
  assert.equal(h.value.projectRequired, false);
  await h.close();
});

test('pending launch has an explicit cancel and a failed inactive launch has visible feedback', async () => {
  let renderer;
  let cancelled = 0;
  const render = extra =>
    React.createElement(
      I18nextProvider,
      { i18n: i18next },
      React.createElement(LiveVoiceDemoBar, {
        active: false,
        available: false,
        status: 'idle',
        interimTranscript: '',
        onEnable() {},
        onExit() {
          cancelled++;
        },
        onPrimaryAction() {},
        ...extra,
      }),
    );
  await act(async () => {
    renderer = create(render({ launchPending: true }));
  });
  const buttons = renderer.root.findAllByType('button');
  assert.equal(buttons[0].props.disabled, true);
  await act(async () => buttons[1].props.onClick());
  assert.equal(cancelled, 1);
  await act(async () => renderer.update(render({ launchError: 'Could not create session' })));
  assert.equal(renderer.root.findByProps({ role: 'alert' }).children[0], 'Could not create session');
  await act(async () => renderer.unmount());
});
