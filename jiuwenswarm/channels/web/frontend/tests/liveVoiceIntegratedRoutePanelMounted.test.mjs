import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test, { after } from 'node:test';

import { build } from 'esbuild';
import i18next from 'i18next';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { act, create } from 'react-test-renderer';

import { LiveVoiceIntegratedRoutePanel } from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';

const mountedBundleDirectory = await mkdtemp(
  fileURLToPath(new URL('../node_modules/.cache/jiuwenswarm-live-voice-mounted-', import.meta.url))
);
after(async () => {
  await rm(mountedBundleDirectory, { recursive: true, force: true });
});

const enabledBundleUrl = pathToFileURL(join(mountedBundleDirectory, 'LiveVoiceIntegratedRoutePanelEnabled.mjs'));
await build({
  entryPoints: [fileURLToPath(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  loader: { '.css': 'empty' },
  outfile: fileURLToPath(enabledBundleUrl),
  define: {
    'import.meta.env': JSON.stringify({
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB: 'true',
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1: 'true',
      VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION: 'false',
      VITE_FEATURE_LIVE_VOICE_TASK_DEMO: 'false',
      VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH: 'false',
    }),
  },
});
const { LiveVoiceIntegratedRoutePanel: EnabledLiveVoiceIntegratedRoutePanel } = await import(`${enabledBundleUrl.href}?enabled=${Date.now()}`);

const p3EnabledBundleUrl = pathToFileURL(join(mountedBundleDirectory, 'LiveVoiceIntegratedRoutePanelP3Enabled.mjs'));
await build({
  entryPoints: [fileURLToPath(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  loader: { '.css': 'empty' },
  outfile: fileURLToPath(p3EnabledBundleUrl),
  define: {
    'import.meta.env': JSON.stringify({
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB: 'true',
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1: 'false',
      VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION: 'true',
      VITE_FEATURE_LIVE_VOICE_TASK_DEMO: 'false',
      VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH: 'false',
    }),
  },
});
const { LiveVoiceIntegratedRoutePanel: P3EnabledLiveVoiceIntegratedRoutePanel } = await import(`${p3EnabledBundleUrl.href}?enabled=${Date.now()}`);

async function createI18n() {
  const translations = JSON.parse(await readFile(new URL('../src/i18n/locales/en.json', import.meta.url), 'utf8'));
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: 'en',
    fallbackLng: false,
    resources: { en: { translation: translations } },
    interpolation: { escapeValue: false },
  });
  return i18n;
}

function installP1BrowserEnvironment() {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const audioContextDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext');
  const audioWorkletNodeDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'AudioWorkletNode');
  const values = new Map();
  const counts = { getUserMedia: 0 };

  class FakeAudioTrack {
    constructor(id) {
      this.id = id;
      this.kind = 'audio';
      this.readyState = 'live';
      this.muted = false;
      this.listeners = new Map();
    }

    stop() {
      this.readyState = 'ended';
    }

    getSettings() {
      return {
        sampleRate: 48_000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        deviceId: `device-${this.id}`,
      };
    }

    addEventListener(name, listener) {
      this.listeners.set(name, listener);
    }

    removeEventListener(name) {
      this.listeners.delete(name);
    }
  }

  class FakeAudioNode {
    connect() {}
    disconnect() {}
  }

  class FakeAudioContext {
    constructor() {
      this.sampleRate = 48_000;
      this.currentTime = 0;
      this.destination = {};
      this.state = 'running';
      this.onstatechange = null;
      this.audioWorklet = { addModule: async () => {} };
    }

    async resume() {
      this.state = 'running';
    }

    async close() {
      this.state = 'closed';
    }

    createMediaStreamSource() {
      return new FakeAudioNode();
    }

    createBuffer() {
      return { copyToChannel() {} };
    }

    createBufferSource() {
      return {
        buffer: null,
        onended: null,
        connect() {},
        disconnect() {},
        start() {},
        stop() {},
      };
    }
  }

  class FakeAudioWorkletNode extends FakeAudioNode {
    constructor() {
      super();
      this.port = { onmessage: null, close() {} };
      this.onprocessorerror = null;
    }
  }

  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const mediaDeviceListeners = new Map();
  const mediaDevices = {
    async getUserMedia() {
      counts.getUserMedia += 1;
      const track = new FakeAudioTrack(`mounted-p1-track-${counts.getUserMedia}`);
      return {
        getAudioTracks: () => [track],
        getTracks: () => [track],
      };
    },
    enumerateDevices: async () => [{ kind: 'audioinput' }, { kind: 'audiooutput' }],
    addEventListener: (name, listener) => mediaDeviceListeners.set(name, listener),
    removeEventListener: name => mediaDeviceListeners.delete(name),
  };

  globalThis.window = {
    sessionStorage: storage,
    location: { origin: 'http://localhost:5173' },
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
    addEventListener() {},
    removeEventListener() {},
    isSecureContext: true,
  };
  globalThis.document = {
    visibilityState: 'visible',
    wasDiscarded: false,
    addEventListener() {},
    removeEventListener() {},
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      userAgent: 'Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36',
      platform: 'Win32',
      onLine: true,
      userActivation: { hasBeenActive: true, isActive: true },
      permissions: {
        query: async () => ({
          state: 'granted',
          addEventListener() {},
          removeEventListener() {},
        }),
      },
      mediaDevices,
    },
  });
  Object.defineProperty(globalThis, 'AudioContext', { configurable: true, value: FakeAudioContext });
  Object.defineProperty(globalThis, 'AudioWorkletNode', { configurable: true, value: FakeAudioWorkletNode });

  return {
    counts,
    restore() {
      if (originalWindow === undefined) delete globalThis.window;
      else globalThis.window = originalWindow;
      if (originalDocument === undefined) delete globalThis.document;
      else globalThis.document = originalDocument;
      if (navigatorDescriptor) Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
      else delete globalThis.navigator;
      if (audioContextDescriptor) Object.defineProperty(globalThis, 'AudioContext', audioContextDescriptor);
      else delete globalThis.AudioContext;
      if (audioWorkletNodeDescriptor) Object.defineProperty(globalThis, 'AudioWorkletNode', audioWorkletNodeDescriptor);
      else delete globalThis.AudioWorkletNode;
    },
  };
}

function mountedP1Element(i18n, sessionId, request) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(EnabledLiveVoiceIntegratedRoutePanel, {
      activeSessionId: sessionId,
      isConnected: true,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
    })
  );
}

function mountedP3Element(i18n, sessionId, request, p3RetryInspectionWait) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(P3EnabledLiveVoiceIntegratedRoutePanel, {
      activeSessionId: sessionId,
      isConnected: true,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      p3RetryInspectionWait,
    })
  );
}

function mountedP3Controls(renderer) {
  const root = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-p3-mutation' });
  const select = root.findByType('select');
  const buttons = root.findAllByType('button');
  const button = label => {
    const selected = buttons.find(candidate => candidate.children.some(child => child === label));
    assert.ok(selected, `mounted P3 button ${label} must exist`);
    return selected;
  };
  const hasButton = label => buttons.some(candidate => candidate.children.some(child => child === label));
  return { root, select, button, hasButton };
}

function mountedP3Status(binding, {
  attemptId = 'attempt-a',
  attemptNumber = 1,
  state = 'running',
  outcome = null,
  eventHead = 1,
} = {}) {
  return {
    ok: true,
    result: {
      task: {
        task_id: 'task-a',
        scope: {
          subject_id: binding.subject_id,
          session_id: binding.session_id,
          project_id: binding.project_id,
          assurance: 'authenticated',
        },
        correlation_id: binding.correlation_id,
        attempt_id: attemptId,
        state,
        outcome,
        event_head: eventHead,
      },
      attempt: { task_id: 'task-a', attempt_id: attemptId, attempt_number: attemptNumber },
    },
  };
}

function mountedP3Events(binding, { terminalA = false, terminalB = false } = {}) {
  const scope = {
    subject_id: binding.subject_id,
    session_id: binding.session_id,
    project_id: binding.project_id,
    assurance: 'authenticated',
  };
  const events = [
    {
      event_id: 'task-a:event:0',
      task_id: 'task-a',
      attempt_id: 'attempt-a',
      scope,
      seq: 0,
      event_type: 'task.accepted',
      state: 'accepted',
      outcome: null,
      producer: 'task_core',
      source_event_id: null,
      causation_id: 'create-a',
      correlation_id: binding.correlation_id,
      occurred_at: '2026-08-10T10:00:00Z',
      details: {},
    },
    {
      event_id: 'task-a:event:1',
      task_id: 'task-a',
      attempt_id: 'attempt-a',
      scope,
      seq: 1,
      event_type: 'task.running',
      state: 'running',
      outcome: null,
      producer: 'task_core',
      source_event_id: 'executor-a:1',
      causation_id: 'executor-a:1',
      correlation_id: binding.correlation_id,
      occurred_at: '2026-08-10T10:00:01Z',
      details: {},
    },
  ];
  if (terminalA || terminalB) {
    events.push({
      event_id: 'task-a:event:2',
      task_id: 'task-a',
      attempt_id: 'attempt-a',
      scope,
      seq: 2,
      event_type: 'task.terminal',
      state: 'terminal',
      outcome: 'cancelled',
      producer: 'task_core.delivery',
      source_event_id: 'executor-a:2',
      causation_id: 'executor-a:2',
      correlation_id: binding.correlation_id,
      occurred_at: '2026-08-10T10:00:02Z',
      details: {},
    });
  }
  if (terminalB) {
    events.push(
      {
        event_id: 'task-a:event:3',
        task_id: 'task-a',
        attempt_id: 'attempt-b',
        scope,
        seq: 3,
        event_type: 'task.retry_accepted',
        state: 'accepted',
        outcome: null,
        producer: 'task_core',
        source_event_id: null,
        causation_id: 'retry-b',
        correlation_id: binding.correlation_id,
        occurred_at: '2026-08-10T10:00:03Z',
        details: {
          attempt_number: 2,
          command_id: 'retry-b',
          previous_outcome: 'cancelled',
          retry_of_attempt_id: 'attempt-a',
        },
      },
      {
        event_id: 'task-a:event:4',
        task_id: 'task-a',
        attempt_id: 'attempt-b',
        scope,
        seq: 4,
        event_type: 'task.running',
        state: 'running',
        outcome: null,
        producer: 'task_core',
        source_event_id: 'executor-b:1',
        causation_id: 'executor-b:1',
        correlation_id: binding.correlation_id,
        occurred_at: '2026-08-10T10:00:04Z',
        details: {},
      },
      {
        event_id: 'task-a:event:5',
        task_id: 'task-a',
        attempt_id: 'attempt-b',
        scope,
        seq: 5,
        event_type: 'task.terminal',
        state: 'terminal',
        outcome: 'completed',
        producer: 'task_core.delivery',
        source_event_id: 'executor-b:2',
        causation_id: 'executor-b:2',
        correlation_id: binding.correlation_id,
        occurred_at: '2026-08-10T10:00:05Z',
        details: {},
      }
    );
  }
  return {
    ok: true,
    result: {
      task_id: 'task-a',
      after_seq: -1,
      head_seq: terminalB ? 5 : terminalA ? 2 : 1,
      events,
    },
  };
}

function formalVoiceStartButton(renderer) {
  const button = renderer.root
    .findAllByType('button')
    .find(candidate => candidate.children.some(child => typeof child === 'string' && child.includes('Start formal voice turn')));
  assert.ok(button, 'formal P1 Start button must be mounted');
  return button;
}

async function waitForMounted(predicate, message, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) assert.fail(message);
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}

test('mounted route panel survives session replacement and closes every effect on unmount', async () => {
  const i18n = await createI18n();
  let renderer;
  await act(async () => {
    renderer = create(
      React.createElement(
        I18nextProvider,
        { i18n },
        React.createElement(LiveVoiceIntegratedRoutePanel, {
          activeSessionId: 'mounted-session-1',
          isConnected: false,
          agentRouteAvailable: false,
          taskCompatibilityAvailable: false,
        })
      )
    );
  });
  assert.notEqual(renderer.toJSON(), null);

  await act(async () => {
    renderer.update(
      React.createElement(
        I18nextProvider,
        { i18n },
        React.createElement(LiveVoiceIntegratedRoutePanel, {
          activeSessionId: 'mounted-session-2',
          isConnected: false,
          agentRouteAvailable: false,
          taskCompatibilityAvailable: false,
        })
      )
    );
  });
  await act(async () => {
    renderer.unmount();
  });
  assert.equal(renderer.toJSON(), null);
});

test('mounted P3 reconciles create A through cancel and authoritative A/B terminals to retry B/C without stale effects', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const calls = [];
  const retryWaiters = [];
  let binding = null;
  let authoritativeAttempt = 1;
  let terminalA = false;
  let terminalB = false;
  let deferNextStatus = false;
  let releaseDeferredStatus = null;
  let renderer;

  const p3RetryInspectionWait = (_delayMs, signal) => new Promise((resolve, reject) => {
    const waiter = { resolve, reject };
    const abort = () => {
      const index = retryWaiters.indexOf(waiter);
      if (index >= 0) retryWaiters.splice(index, 1);
      reject(new Error('mounted P3 inspection wait aborted'));
    };
    signal.addEventListener('abort', abort, { once: true });
    waiter.resolve = () => {
      signal.removeEventListener('abort', abort);
      const index = retryWaiters.indexOf(waiter);
      if (index >= 0) retryWaiters.splice(index, 1);
      resolve();
    };
    retryWaiters.push(waiter);
  });

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.progress.activate') {
      return { ok: true, result: { status: 'active', ...params } };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p3.confirmation.issue') {
      binding ??= {
        subject_id: 'mounted-p3-subject',
        session_id: params.session_id,
        project_id: 'mounted-p3-project',
        correlation_id: params.correlation_id,
        generation: 1,
      };
      return {
        ok: true,
        result: {
          status: 'confirmation_issued',
          operation: params.operation,
          command_id: params.command_id,
          target_task_id: params.operation === 'task.create' ? null : params.task_id,
          confirmation_id: `confirmation-${params.command_id}`,
          expires_at: '2999-08-10T10:00:00Z',
          task_control_binding: binding,
        },
      };
    }
    if (method === 'live_voice.composition.p3.mutate') {
      const common = {
        status: 'mutation_processed',
        operation: params.operation,
        command_id: params.command_id,
        target_task_id: params.operation === 'task.create' ? null : params.task_id,
      };
      if (params.operation === 'task.create') {
        return {
          ok: true,
          result: {
            ...common,
            formal_task_result: {
              task_id: 'task-a',
              attempt_id: 'attempt-a',
              attempt_number: 1,
              state: 'accepted',
              outbox_id: 'outbox-create-a',
            },
          },
        };
      }
      if (params.operation === 'task.cancel') {
        return {
          ok: true,
          result: {
            ...common,
            formal_task_result: {
              task_id: 'task-a',
              attempt_id: 'attempt-a',
              cancel_acknowledged: true,
              applied: true,
              state: 'running',
              outbox_id: 'outbox-cancel-a',
            },
          },
        };
      }
      const previousAttempt = authoritativeAttempt === 1 ? 'attempt-a' : 'attempt-b';
      const nextAttempt = authoritativeAttempt === 1 ? 'attempt-b' : 'attempt-c';
      const nextAttemptNumber = authoritativeAttempt + 1;
      authoritativeAttempt = nextAttemptNumber;
      return {
        ok: true,
        result: {
          ...common,
          formal_task_result: {
            task_id: 'task-a',
            previous_attempt_id: previousAttempt,
            attempt_id: nextAttempt,
            attempt_number: nextAttemptNumber,
            applied: true,
            state: 'accepted',
            outbox_id: `outbox-retry-${nextAttempt.at(-1)}`,
          },
        },
      };
    }
    if (method === 'live_voice.task.status') {
      if (deferNextStatus) {
        deferNextStatus = false;
        return new Promise(resolve => {
          releaseDeferredStatus = () => resolve(mountedP3Status(binding, {
            attemptId: 'attempt-c',
            attemptNumber: 3,
            state: 'accepted',
            eventHead: 6,
          }));
        });
      }
      if (authoritativeAttempt === 2 && terminalB) {
        return mountedP3Status(binding, {
          attemptId: 'attempt-b',
          attemptNumber: 2,
          state: 'terminal',
          outcome: 'completed',
          eventHead: 5,
        });
      }
      return mountedP3Status(binding, terminalA
        ? { state: 'terminal', outcome: 'cancelled', eventHead: 2 }
        : { state: 'running', outcome: null, eventHead: 1 });
    }
    if (method === 'live_voice.task.events') return mountedP3Events(binding, { terminalA, terminalB });
    throw new Error(`unexpected mounted P3 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'mounted-p3-session', request, p3RetryInspectionWait));
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'),
        'formal P3 controls did not mount'
      );
    });

    await act(async () => {
      const controls = mountedP3Controls(renderer);
      const inputs = controls.root.findAllByType('input');
      controls.root.findByType('textarea').props.onChange({ target: { value: 'Edit only the disposable fixture.' } });
      inputs[0].props.onChange({ target: { value: 'Mounted P3 task' } });
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'),
        'task.create confirmation did not settle'
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted task.create did not transition the mounted controller to task.cancel'
      );
    });
    assert.equal(mountedP3Controls(renderer).root.findByType('input').props.value, 'task-a');

    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'),
        'task.cancel confirmation did not settle'
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => retryWaiters.length === 1 && JSON.stringify(renderer.toJSON()).includes('checking'),
        'nonterminal task.cancel did not retain an authoritative retry inspection'
      );
    });
    assert.equal(mountedP3Controls(renderer).select.findAllByType('option').some(option => option.props.value === 'task.retry'), false);

    terminalA = true;
    await act(async () => {
      retryWaiters[0].resolve();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'terminal cancelled attempt did not automatically expose task.retry'
      );
    });
    assert.equal(retryWaiters.length, 0, 'terminal reconciliation must release its deterministic waiter');
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'),
        'task.retry confirmation did not settle'
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted retry B did not return the mounted controller to task.cancel'
      );
    });
    assert.equal(mountedP3Controls(renderer).select.findAllByType('option').some(option => option.props.value === 'task.retry'), false);

    terminalB = true;
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'authoritative terminal completed attempt B did not expose task.retry'
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'),
        'task.retry C confirmation did not settle'
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted retry C did not return the mounted controller to task.cancel'
      );
    });
    assert.equal(authoritativeAttempt, 3);
    assert.equal(mountedP3Controls(renderer).root.findByType('input').props.value, 'task-a');
    assert.equal(mountedP3Controls(renderer).select.findAllByType('option').some(option => option.props.value === 'task.retry'), false);
    assert.deepEqual(
      calls
        .filter(call => call.method === 'live_voice.composition.p3.confirmation.issue')
        .map(call => [call.params.operation, call.params.task_id ?? null]),
      [['task.create', null], ['task.cancel', 'task-a'], ['task.retry', 'task-a'], ['task.retry', 'task-a']]
    );
    assert.deepEqual(
      calls
        .filter(call => call.method === 'live_voice.composition.p3.mutate')
        .map(call => [call.params.operation, call.params.task_id ?? null]),
      [['task.create', null], ['task.cancel', 'task-a'], ['task.retry', 'task-a'], ['task.retry', 'task-a']]
    );

    const eventsBeforeFence = calls.filter(call => call.method === 'live_voice.task.events').length;
    deferNextStatus = true;
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(() => typeof releaseDeferredStatus === 'function', 'old retry inspection did not reach status');
    });
    await act(async () => {
      renderer.update(mountedP3Element(i18n, 'mounted-p3-successor-session', request, p3RetryInspectionWait));
      releaseDeferredStatus();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, eventsBeforeFence);
    assert.equal(mountedP3Controls(renderer).select.props.value, 'task.create');
    assert.equal(mountedP3Controls(renderer).select.findAllByType('option').some(option => option.props.value === 'task.retry'), false);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 4);
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await Promise.resolve();
      });
    }
    browser.restore();
  }
});

test('mounted P1 cleanup singleflight fences two retained Start attempts until exact close, then allocates one successor', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const mediaActivations = [];
  const mediaCloses = [];
  let resolveFirstClose = null;
  let renderer;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      mediaActivations.push({ ...params });
      if (mediaActivations.length === 1) {
        return {
          status: 'active',
          reason_id: null,
          subject_id: 'mounted-p1-old-subject',
          endpoint_path: '/api/v1/live_voice/media',
          subprotocol: 'live-voice.media.v1',
          ticket_ttl_ms: 30_000,
          binding: {},
          privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: false },
        };
      }
      return { status: 'unavailable', reason_id: 'MOUNTED_SUCCESSOR_PROBE_COMPLETE' };
    }
    if (method === 'live_voice.media.close') {
      mediaCloses.push({ ...params });
      if (mediaCloses.length === 1) throw { code: 'WS_NOT_READY' };
      assert.equal(mediaCloses.length, 2, 'the retained Start must share one exact close retry before successor allocation');
      return new Promise(resolve => {
        resolveFirstClose = () => resolve({ status: 'closed', reason_id: null, ...params });
      });
    }
    throw new Error(`unexpected mounted P1 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-singleflight-session', request));
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose the formal P1 Start control');
    });
    await act(async () => {
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(
        () => mediaCloses.length === 1 && JSON.stringify(renderer.toJSON()).includes('cleanup_pending'),
        'the first failed exact close did not settle the old P1 owner as cleanup_pending'
      );
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(mediaActivations.length, 1);
    assert.match(JSON.stringify(renderer.toJSON()), /cleanup_pending/);

    await act(async () => {
      const retainedStart = formalVoiceStartButton(renderer);
      assert.equal(retainedStart.props.disabled, true, 'cleanup_pending must remain terminal to real browser clicks');
      // Invoke the retained callback directly to cover the singleflight guard even
      // though the mounted button correctly blocks these clicks in the browser.
      retainedStart.props.onClick();
      retainedStart.props.onClick();
      await waitForMounted(() => mediaCloses.length === 2, 'the retained Start did not retry the exact old close');
    });
    assert.equal(browser.counts.getUserMedia, 1, 'no successor microphone may open while exact close is pending');
    assert.equal(mediaActivations.length, 1, 'no successor media authority may activate while exact close is pending');
    assert.equal(mediaCloses.length, 2);

    assert.equal(typeof resolveFirstClose, 'function');
    await act(async () => {
      resolveFirstClose();
      await waitForMounted(
        () => browser.counts.getUserMedia === 2 && mediaActivations.length === 2,
        'the retained Start did not allocate its single successor after exact close'
      );
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(browser.counts.getUserMedia, 2, 'two retained clicks must allocate exactly one successor microphone');
    assert.equal(mediaActivations.length, 2, 'two retained clicks must allocate exactly one successor media activation');
    assert.equal(mediaActivations[0].capture_generation, 1);
    assert.equal(mediaActivations[1].capture_generation, 1, 'the successor must be a new owner, not a concurrent generation on the old owner');
    assert.notEqual(mediaActivations[1].track_id, mediaActivations[0].track_id);
    assert.deepEqual(mediaCloses[0], {
      session_id: 'mounted-p1-singleflight-session',
      subject_id: 'mounted-p1-old-subject',
      correlation_id: mediaActivations[0].correlation_id,
      interaction_id: mediaActivations[0].interaction_id,
      activation_id: mediaActivations[0].activation_id,
      activation_generation: mediaActivations[0].activation_generation,
    });
    assert.deepEqual(mediaCloses[1], mediaCloses[0], 'the successful retry must revoke the same retained old authority');
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    browser.restore();
  }
});

test('mounted P1 retained Start cannot allocate an old-binding successor after Session replacement wins during exact close', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const p2Activations = [];
  const p2Closes = [];
  const mediaActivations = [];
  const mediaCloses = [];
  let resolveRetainedClose = null;
  let renderer;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      p2Activations.push({ ...params });
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      p2Closes.push({ ...params });
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      mediaActivations.push({ ...params });
      if (mediaActivations.length > 1) {
        return { status: 'unavailable', reason_id: 'STALE_BINDING_SUCCESSOR_FORBIDDEN' };
      }
      return {
        status: 'active',
        reason_id: null,
        subject_id: 'mounted-p1-replaced-session-subject',
        endpoint_path: '/api/v1/live_voice/media',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: {},
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: false },
      };
    }
    if (method === 'live_voice.media.close') {
      mediaCloses.push({ ...params });
      if (mediaCloses.length === 1) throw { code: 'WS_NOT_READY' };
      assert.equal(mediaCloses.length, 2, 'Session replacement must share the one retained exact close retry');
      return new Promise(resolve => {
        resolveRetainedClose = () => resolve({ status: 'closed', reason_id: null, ...params });
      });
    }
    throw new Error(`unexpected mounted replaced-Session request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-old-session', request));
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'old Session did not expose formal P1 Start');
    });
    await act(async () => {
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(
        () => mediaCloses.length === 1 && JSON.stringify(renderer.toJSON()).includes('cleanup_pending'),
        'old Session P1 did not retain its failed exact authority'
      );
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    await act(async () => {
      const retainedStart = formalVoiceStartButton(renderer);
      retainedStart.props.onClick();
      retainedStart.props.onClick();
      await waitForMounted(() => mediaCloses.length === 2, 'retained Start did not enter the exact close gate');
    });
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(mediaActivations.length, 1);

    await act(async () => {
      renderer.update(mountedP1Element(i18n, 'mounted-p1-new-session', request));
      await waitForMounted(
        () => p2Activations.some(activation => activation.session_id === 'mounted-p1-new-session'),
        'replacement Session did not acquire its current P2 binding'
      );
    });
    assert.equal(typeof resolveRetainedClose, 'function');
    assert.equal(browser.counts.getUserMedia, 1, 'replacement P2 binding must not bypass the pending old P1 close');
    assert.equal(mediaActivations.length, 1);

    await act(async () => {
      resolveRetainedClose();
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    assert.equal(browser.counts.getUserMedia, 1, 'settled old close must not open a microphone for its stale captured binding');
    assert.equal(mediaActivations.length, 1, 'settled old close must not activate stale media authority');
    assert.equal(mediaActivations[0].session_id, 'mounted-p1-old-session');
    assert.equal(
      p2Activations.some(activation => activation.session_id === 'mounted-p1-new-session'),
      true
    );
    assert.equal(
      p2Closes.some(close => close.session_id === 'mounted-p1-old-session'),
      true
    );
    assert.equal(mediaCloses.length, 2);
    assert.deepEqual(mediaCloses[1], mediaCloses[0]);
    assert.equal(mediaCloses[0].session_id, 'mounted-p1-old-session');
    assert.equal(mediaCloses[0].subject_id, 'mounted-p1-replaced-session-subject');
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    browser.restore();
  }
});

test('mounted P1 retained Start cannot allocate a successor after unmount wins during exact close', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const mediaActivations = [];
  const mediaCloses = [];
  const p2Closes = [];
  let resolveRetainedClose = null;
  let resolveP2Close = null;
  let renderer;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      p2Closes.push({ ...params });
      return new Promise(resolve => {
        resolveP2Close = () => resolve({ ok: true, result: { status: 'closed', ...params } });
      });
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      mediaActivations.push({ ...params });
      if (mediaActivations.length > 1) {
        return { status: 'unavailable', reason_id: 'UNMOUNTED_SUCCESSOR_FORBIDDEN' };
      }
      return {
        status: 'active',
        reason_id: null,
        subject_id: 'mounted-p1-unmount-subject',
        endpoint_path: '/api/v1/live_voice/media',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: {},
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: false },
      };
    }
    if (method === 'live_voice.media.close') {
      mediaCloses.push({ ...params });
      if (mediaCloses.length === 1) throw { code: 'WS_NOT_READY' };
      assert.equal(mediaCloses.length, 2, 'unmount must share the retained old P1 exact close');
      return new Promise(resolve => {
        resolveRetainedClose = () => resolve({ status: 'closed', reason_id: null, ...params });
      });
    }
    throw new Error(`unexpected mounted unmount-fence request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-unmount-session', request));
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'unmount case did not expose formal P1 Start');
    });
    await act(async () => {
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(
        () => mediaCloses.length === 1 && JSON.stringify(renderer.toJSON()).includes('cleanup_pending'),
        'unmount case did not retain the failed old P1 exact authority'
      );
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    await act(async () => {
      const retainedStart = formalVoiceStartButton(renderer);
      retainedStart.props.onClick();
      retainedStart.props.onClick();
      await waitForMounted(() => mediaCloses.length === 2, 'unmount case did not enter the second old P1 close gate');
    });
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(mediaActivations.length, 1);

    await act(async () => {
      renderer.unmount();
      renderer = null;
      await waitForMounted(() => p2Closes.length === 1, 'unmount did not begin cleanup of the still-current P2 binding');
    });
    assert.equal(typeof resolveRetainedClose, 'function');
    assert.equal(typeof resolveP2Close, 'function');
    assert.equal(p2Closes.length, 1, 'P2 close must remain unsettled while the old P1 close is released');

    await act(async () => {
      resolveRetainedClose();
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    assert.equal(browser.counts.getUserMedia, 1, 'unmounted retained Start must not open a successor microphone');
    assert.equal(mediaActivations.length, 1, 'unmounted retained Start must not activate successor media authority');
    assert.equal(mediaCloses.length, 2);
    assert.deepEqual(mediaCloses[1], mediaCloses[0]);
    assert.equal(mediaCloses[0].session_id, 'mounted-p1-unmount-session');
    assert.equal(mediaCloses[0].subject_id, 'mounted-p1-unmount-subject');
    assert.equal(p2Closes.length, 1, 'P2 owner may still look active when mountedRef independently fences P1 allocation');

    await act(async () => {
      resolveP2Close();
      await new Promise(resolve => setTimeout(resolve, 20));
    });
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    browser.restore();
  }
});

test('mounted P1 retains failed exact authority and blocks two user Start attempts when close keeps failing', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const mediaActivations = [];
  const mediaCloses = [];
  let renderer;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      mediaActivations.push({ ...params });
      return {
        status: 'active',
        reason_id: null,
        subject_id: 'mounted-p1-retained-subject',
        endpoint_path: '/api/v1/live_voice/media',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: {},
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: false },
      };
    }
    if (method === 'live_voice.media.close') {
      mediaCloses.push({ ...params });
      throw { code: 'WS_NOT_READY' };
    }
    throw new Error(`unexpected mounted retained-P1 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-retained-session', request));
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose the retained-P1 Start control');
    });
    await act(async () => {
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(
        () => mediaCloses.length === 1 && JSON.stringify(renderer.toJSON()).includes('cleanup_pending'),
        'the failed exact close did not retain cleanup_pending truth'
      );
    });

    const terminalStart = formalVoiceStartButton(renderer);
    assert.equal(terminalStart.props.disabled, true);
    let browserDispatchedStarts = 0;
    await act(async () => {
      // Disabled controls do not dispatch clicks in the browser. Model two
      // consecutive user attempts and assert that neither reaches the callback.
      for (let attempt = 0; attempt < 2; attempt += 1) {
        if (!terminalStart.props.disabled) {
          browserDispatchedStarts += 1;
          terminalStart.props.onClick();
        }
      }
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(browserDispatchedStarts, 0);
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(mediaActivations.length, 1);
    assert.equal(mediaCloses.length, 1);

    await act(async () => {
      renderer.unmount();
      renderer = null;
      await waitForMounted(() => mediaCloses.length === 4, 'unmount did not retry the retained exact P1 authority three times');
    });
    assert.equal(browser.counts.getUserMedia, 1, 'failed exact close must never allocate a successor microphone');
    assert.equal(mediaActivations.length, 1, 'failed exact close must never allocate a successor authority');
    assert.equal(mediaCloses.length, 4);
    for (const close of mediaCloses) assert.deepEqual(close, mediaCloses[0]);
    assert.equal(mediaCloses[0].subject_id, 'mounted-p1-retained-subject');
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    browser.restore();
  }
});

test('enabled mounted panel remount reconciles the exact predecessor and reopens P1', async () => {
  const i18n = await createI18n();
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const listeners = new Map();
  globalThis.window = {
    sessionStorage: storage,
    location: { origin: 'http://localhost:5173' },
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
    addEventListener: (name, handler) => listeners.set(`window:${name}`, handler),
    removeEventListener: name => listeners.delete(`window:${name}`),
    isSecureContext: true,
  };
  globalThis.document = {
    visibilityState: 'visible',
    wasDiscarded: false,
    addEventListener: (name, handler) => listeners.set(`document:${name}`, handler),
    removeEventListener: name => listeners.delete(`document:${name}`),
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      userAgent: 'Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36',
      platform: 'Win32',
      onLine: true,
      userActivation: { hasBeenActive: true, isActive: true },
      permissions: {
        query: async () => ({
          state: 'granted',
          addEventListener: () => {},
          removeEventListener: () => {},
        }),
      },
      mediaDevices: {
        enumerateDevices: async () => [{ kind: 'audioinput' }, { kind: 'audiooutput' }],
      },
    },
  });

  const activeBindings = new Map();
  const highWaters = new Map();
  const effects = [];
  let retryableActivationAttempts = 0;
  const retryActivationIds = [];
  let missingReplayCloseFailuresRemaining = 3;
  let deferredRaceResolve = null;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      if (params.session_id === 'mounted-retry-session') {
        retryActivationIds.push(params.activation_id);
      }
      if (params.session_id === 'mounted-retry-session' && retryableActivationAttempts++ === 0) {
        effects.push(['activate-retryable', params.session_id, params.activation_generation, params.activation_id]);
        throw { code: 'WS_NOT_READY' };
      }
      const current = activeBindings.get(params.session_id) ?? null;
      const replayed = current !== null;
      if (current !== null) {
        assert.deepEqual(params, current);
      } else {
        assert.equal(params.activation_generation > (highWaters.get(params.session_id) ?? 0), true);
        activeBindings.set(params.session_id, { ...params });
      }
      effects.push(['activate', params.session_id, params.activation_generation, replayed]);
      if (params.session_id === 'mounted-race-session' && params.activation_id === 'web-activation-race-1') {
        return new Promise(resolve => {
          deferredRaceResolve = () =>
            resolve({
              ok: true,
              result: { status: 'active', ...params, replayed: true },
            });
        });
      }
      if (params.session_id === 'mounted-missing-replay-session') {
        return { ok: true, result: { status: 'active', ...params } };
      }
      return { ok: true, result: { status: 'active', ...params, replayed } };
    }
    if (method === 'live_voice.composition.p2.close') {
      if (params.session_id === 'mounted-missing-replay-session' && params.activation_generation === 1 && missingReplayCloseFailuresRemaining > 0) {
        missingReplayCloseFailuresRemaining -= 1;
        effects.push(['close-retryable', params.session_id, params.activation_generation]);
        throw { code: 'WS_NOT_READY' };
      }
      assert.deepEqual(params, activeBindings.get(params.session_id));
      effects.push(['close', params.session_id, params.activation_generation]);
      highWaters.set(params.session_id, params.activation_generation);
      activeBindings.delete(params.session_id);
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    throw new Error(`unexpected mounted request: ${method}`);
  };
  const element = (sessionId = 'mounted-refresh-session') =>
    React.createElement(
      I18nextProvider,
      { i18n },
      React.createElement(EnabledLiveVoiceIntegratedRoutePanel, {
        activeSessionId: sessionId,
        isConnected: true,
        agentRouteAvailable: true,
        taskCompatibilityAvailable: false,
        request,
      })
    );
  const refreshPredecessor = {
    session_id: 'mounted-refresh-session',
    correlation_id: 'integrated-web-refresh',
    interaction_id: 'web-interaction-refresh',
    activation_id: 'web-activation-refresh-1',
    activation_generation: 1,
  };
  activeBindings.set(refreshPredecessor.session_id, { ...refreshPredecessor });
  values.set(
    `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(refreshPredecessor.session_id)}`,
    JSON.stringify({
      schema: 'live-voice.product-p2-activation-journal.v1',
      client_instance_id: 'refresh-client',
      session_id: refreshPredecessor.session_id,
      correlation_id: refreshPredecessor.correlation_id,
      interaction_id: refreshPredecessor.interaction_id,
      binding: refreshPredecessor,
      phase: 'active',
      last_generation: 1,
    })
  );
  let first;
  let second;
  let retried;
  let missingReplay;
  let raced;
  try {
    await act(async () => {
      first = create(element());
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    const firstText = JSON.stringify(first.toJSON());
    assert.match(firstText, /Start formal voice turn/);
    assert.match(firstText, /active/);
    assert.deepEqual(effects.slice(0, 3), [
      ['activate', 'mounted-refresh-session', 1, true],
      ['close', 'mounted-refresh-session', 1],
      ['activate', 'mounted-refresh-session', 2, false],
    ]);
    assert.equal(activeBindings.get('mounted-refresh-session').activation_generation, 2);

    await act(async () => {
      first.unmount();
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    await act(async () => {
      second = create(element());
      await new Promise(resolve => setTimeout(resolve, 30));
    });
    const secondText = JSON.stringify(second.toJSON());
    assert.match(secondText, /Start formal voice turn/);
    assert.match(secondText, /active/);
    assert.equal(
      effects.some(([kind]) => kind === 'close'),
      true
    );
    assert.equal(effects.at(-1)[0], 'activate');
    assert.equal(activeBindings.get('mounted-refresh-session').activation_generation, (highWaters.get('mounted-refresh-session') ?? 0) + 1);

    await act(async () => {
      second.unmount();
      second = null;
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    await act(async () => {
      retried = create(element('mounted-retry-session'));
      await new Promise(resolve => setTimeout(resolve, 1250));
    });
    const retriedText = JSON.stringify(retried.toJSON());
    assert.match(retriedText, /Start formal voice turn/);
    assert.match(retriedText, /active/);
    const retryEffects = effects.filter(([, sessionId]) => sessionId === 'mounted-retry-session');
    assert.equal(retryEffects[0][0], 'activate-retryable');
    assert.equal(retryEffects[0][2], 1);
    assert.deepEqual(
      retryEffects.slice(1).map(([kind, , generation]) => [kind, generation]),
      [
        ['activate', 1],
        ['close', 1],
        ['activate', 2],
      ]
    );
    assert.deepEqual(retryActivationIds.slice(0, 2), [retryActivationIds[0], retryActivationIds[0]]);
    assert.notEqual(retryActivationIds[2], retryActivationIds[0]);
    await act(async () => {
      retried.unmount();
      retried = null;
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    const missingReplayBinding = {
      session_id: 'mounted-missing-replay-session',
      correlation_id: 'integrated-web-missing-replay',
      interaction_id: 'web-interaction-missing-replay',
      activation_id: 'web-activation-missing-replay-1',
      activation_generation: 1,
    };
    activeBindings.set(missingReplayBinding.session_id, { ...missingReplayBinding });
    values.set(
      `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(missingReplayBinding.session_id)}`,
      JSON.stringify({
        schema: 'live-voice.product-p2-activation-journal.v1',
        client_instance_id: 'missing-replay-client',
        session_id: missingReplayBinding.session_id,
        correlation_id: missingReplayBinding.correlation_id,
        interaction_id: missingReplayBinding.interaction_id,
        binding: missingReplayBinding,
        phase: 'active',
        last_generation: 1,
      })
    );
    await act(async () => {
      missingReplay = create(element('mounted-missing-replay-session'));
      await new Promise(resolve => setTimeout(resolve, 350));
    });
    let missingReplayEffects = effects.filter(([, sessionId]) => sessionId === 'mounted-missing-replay-session');
    assert.deepEqual(
      missingReplayEffects.map(([kind, , generation]) => [kind, generation]),
      [
        ['activate', 1],
        ['close-retryable', 1],
        ['close-retryable', 1],
        ['close-retryable', 1],
      ]
    );
    assert.equal(missingReplayCloseFailuresRemaining, 0);
    assert.equal(activeBindings.get('mounted-missing-replay-session').activation_generation, 1);
    const retainedMissingReplayJournal = JSON.parse(
      values.get(`jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(missingReplayBinding.session_id)}`)
    );
    assert.equal(retainedMissingReplayJournal.phase, 'closing');
    assert.deepEqual(retainedMissingReplayJournal.binding, missingReplayBinding);
    assert.equal(
      missingReplayEffects.some(([kind, , generation]) => kind === 'activate' && generation === 2),
      false
    );

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 1250));
    });
    missingReplayEffects = effects.filter(([, sessionId]) => sessionId === 'mounted-missing-replay-session');
    assert.deepEqual(
      missingReplayEffects.map(([kind, , generation]) => [kind, generation]),
      [
        ['activate', 1],
        ['close-retryable', 1],
        ['close-retryable', 1],
        ['close-retryable', 1],
        ['close', 1],
        ['activate', 2],
      ]
    );
    assert.equal(activeBindings.get('mounted-missing-replay-session').activation_generation, 2);
    const recoveredMissingReplayJournal = JSON.parse(
      values.get(`jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(missingReplayBinding.session_id)}`)
    );
    assert.equal(recoveredMissingReplayJournal.phase, 'active');
    assert.equal(recoveredMissingReplayJournal.binding.activation_generation, 2);
    assert.equal(
      missingReplayEffects.some(([kind, , generation]) => (kind === 'close' || kind === 'close-retryable') && generation === 2),
      false
    );
    await act(async () => {
      missingReplay.unmount();
      missingReplay = null;
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    const raceBinding = {
      session_id: 'mounted-race-session',
      correlation_id: 'integrated-web-race',
      interaction_id: 'web-interaction-race',
      activation_id: 'web-activation-race-1',
      activation_generation: 1,
    };
    activeBindings.set(raceBinding.session_id, { ...raceBinding });
    values.set(
      `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(raceBinding.session_id)}`,
      JSON.stringify({
        schema: 'live-voice.product-p2-activation-journal.v1',
        client_instance_id: 'race-client',
        session_id: raceBinding.session_id,
        correlation_id: raceBinding.correlation_id,
        interaction_id: raceBinding.interaction_id,
        binding: raceBinding,
        phase: 'active',
        last_generation: 1,
      })
    );
    await act(async () => {
      raced = create(element('mounted-race-session'));
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(typeof deferredRaceResolve, 'function');
    await act(async () => {
      raced.update(element('mounted-switched-session'));
      deferredRaceResolve();
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    assert.equal(
      effects.some(([kind, sessionId, generation]) => kind === 'activate' && sessionId === 'mounted-race-session' && generation > 1),
      false
    );
    assert.equal(
      effects.some(([kind, sessionId, generation]) => kind === 'close' && sessionId === 'mounted-race-session' && generation === 1),
      true
    );
    assert.equal(activeBindings.has('mounted-switched-session'), true);
  } finally {
    if (raced) {
      await act(async () => {
        raced.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    if (second) {
      await act(async () => {
        second.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    if (missingReplay) {
      await act(async () => {
        missingReplay.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    if (retried) {
      await act(async () => {
        retried.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
    } else {
      delete globalThis.navigator;
    }
  }
});
