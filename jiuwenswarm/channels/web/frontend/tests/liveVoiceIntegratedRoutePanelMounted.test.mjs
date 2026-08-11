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

import { LiveVoiceIntegratedRoutePanel, progressMatchesOwnedBinding } from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';
import { parseProductTextProgressEvent } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

const mountedBundleDirectory = await mkdtemp(fileURLToPath(new URL('../node_modules/.cache/jiuwenswarm-live-voice-mounted-', import.meta.url)));
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

const fullyEnabledBundleUrl = pathToFileURL(join(mountedBundleDirectory, 'LiveVoiceIntegratedRoutePanelFullyEnabled.mjs'));
await build({
  entryPoints: [fileURLToPath(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  loader: { '.css': 'empty' },
  outfile: fileURLToPath(fullyEnabledBundleUrl),
  define: {
    'import.meta.env': JSON.stringify({
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB: 'true',
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1: 'true',
      VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION: 'true',
      VITE_FEATURE_LIVE_VOICE_TASK_DEMO: 'false',
      VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH: 'false',
    }),
  },
});
const { LiveVoiceIntegratedRoutePanel: FullyEnabledLiveVoiceIntegratedRoutePanel } = await import(`${fullyEnabledBundleUrl.href}?enabled=${Date.now()}`);

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

function createFakeWebLocks() {
  const held = new Set();
  return {
    async request(name, options, callback) {
      assert.deepEqual(options, { mode: 'exclusive', ifAvailable: true });
      if (held.has(name)) return callback(null);
      held.add(name);
      try {
        return await callback({ name });
      } finally {
        held.delete(name);
      }
    },
  };
}

function installP2RecoveryBrowser(storage) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
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
      locks: createFakeWebLocks(),
      permissions: {
        query: async () => ({
          state: 'granted',
          addEventListener() {},
          removeEventListener() {},
        }),
      },
      mediaDevices: {
        enumerateDevices: async () => [{ kind: 'audioinput' }, { kind: 'audiooutput' }],
      },
    },
  });
  return () => {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (navigatorDescriptor) Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
    else delete globalThis.navigator;
  };
}

function pendingP2Journal(binding, operation) {
  return {
    schema: 'live-voice.product-p2-activation-journal.v2',
    revision: 3,
    client_instance_id: 'pre-refresh-client',
    session_id: binding.session_id,
    correlation_id: binding.correlation_id,
    interaction_id: binding.interaction_id,
    binding,
    phase: 'operation_result_unknown',
    last_generation: binding.activation_generation,
    pending_operation: operation,
    recovery_owner_id: null,
    recovery_token: null,
    recovery_epoch: 0,
  };
}

function installP1BrowserEnvironment({ mediaBinding = null } = {}) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const audioContextDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext');
  const audioWorkletNodeDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'AudioWorkletNode');
  const webSocketDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'WebSocket');
  const values = new Map();
  const counts = { getUserMedia: 0 };
  let latestWorklet = null;

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
    constructor(_context, _name, options) {
      super();
      this.port = { onmessage: null, close() {} };
      this.onprocessorerror = null;
      this.captureGeneration = options.processorOptions.captureGeneration;
      latestWorklet = this;
    }
  }

  class FakeWebSocket {
    static OPEN = 1;
    readyState = 0;
    bufferedAmount = 0;
    protocol = '';
    binaryType = 'blob';
    onopen = null;
    onmessage = null;
    onerror = null;
    onclose = null;
    binarySeq = 0;

    constructor() {
      const binding = mediaBinding?.();
      queueMicrotask(() => {
        if (binding === null || binding === undefined) {
          this.readyState = 3;
          this.onerror?.({});
          return;
        }
        this.readyState = 1;
        this.protocol = 'live-voice.media.v1';
        this.onopen?.({});
        this.onmessage?.({
          data: JSON.stringify({ type: 'media.attach', contract_version: 'live-voice.media.v1', binding }),
        });
      });
    }

    send(value) {
      if (typeof value === 'string') {
        const control = JSON.parse(value);
        if (control.type === 'media.detach') {
          queueMicrotask(() => this.onmessage?.({ data: value }));
        }
        return;
      }
      const binding = mediaBinding?.();
      const throughSeq = this.binarySeq;
      this.binarySeq += 1;
      queueMicrotask(() =>
        this.onmessage?.({
          data: JSON.stringify({
            type: 'media.ack',
            contract_version: 'live-voice.media.v1',
            lease_id: binding.lease_id,
            generation: binding.generation.value,
            through_seq: throughSeq,
          }),
        })
      );
    }

    close() {
      this.readyState = 3;
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
      locks: createFakeWebLocks(),
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
  if (mediaBinding !== null) Object.defineProperty(globalThis, 'WebSocket', { configurable: true, value: FakeWebSocket });

  return {
    counts,
    async emitFirstFrame() {
      await waitForMounted(() => typeof latestWorklet?.port.onmessage === 'function', 'mounted P1 worklet did not become ready');
      await new Promise(resolve => setImmediate(resolve));
      latestWorklet.port.onmessage({
        data: {
          kind: 'frame',
          capture_generation: latestWorklet.captureGeneration,
          seq: 0,
          sample_rate_hz: 48_000,
          sample_cursor: 0,
          context_time_s: 0,
          samples: new Float32Array(960).fill(0.25),
        },
      });
    },
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
      if (webSocketDescriptor) Object.defineProperty(globalThis, 'WebSocket', webSocketDescriptor);
      else delete globalThis.WebSocket;
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

function mountedP3Element(i18n, sessionId, request, p3RetryInspectionWait, isConnected = true, progressSubscribe = undefined) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(P3EnabledLiveVoiceIntegratedRoutePanel, {
      activeSessionId: sessionId,
      isConnected,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      p3RetryInspectionWait,
      progressSubscribe,
    })
  );
}

function mountedFullyEnabledElement(i18n, sessionId, request, isConnected = true, extraProps = {}) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(FullyEnabledLiveVoiceIntegratedRoutePanel, {
      activeSessionId: sessionId,
      isConnected,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      ...extraProps,
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

function mountedP3Status(binding, { attemptId = 'attempt-a', attemptNumber = 1, state = 'running', outcome = null, eventHead = 1 } = {}) {
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

function mountedTerminalProgress(binding, activation, outcome) {
  const scope = {
    subject_id: binding.subject_id,
    session_id: binding.session_id,
    project_id: binding.project_id,
    assurance: 'authenticated',
  };
  const sourceEventId = 'task-a:event:1';
  return {
    event_type: 'live_voice.task.progress',
    delivery_id: `mounted-terminal-${outcome}`,
    session_id: binding.session_id,
    project_id: binding.project_id,
    task_id: 'task-a',
    correlation_id: binding.correlation_id,
    origin_id: activation.origin_id,
    generation_kind: 'web_task_progress_generation',
    generation_id: activation.generation_id,
    generation: activation.generation,
    evidence_id: `mounted-evidence-${outcome}`,
    source_event: {
      event_id: sourceEventId,
      event_type: 'task.terminal',
      seq: 1,
      correlation_id: binding.correlation_id,
      causation_id: 'executor-terminal-a',
      stream_ref: { kind: 'task', id: 'task-a' },
      scope,
      payload: { state: 'terminal', outcome },
      extensions: {
        'jiuwenswarm.task_progress_return': {
          persistent_event_seq: 1,
          persistent_event_type: 'task.terminal',
          persistent_event_producer: 'task_core.delivery',
          persistent_attempt_id: 'attempt-a',
          persistent_source_event_id: 'executor-terminal-a',
        },
      },
    },
    progress_event: {
      event_id: `task-progress:${sourceEventId}`,
      event_type: 'work.progress',
      seq: 1,
      correlation_id: binding.correlation_id,
      causation_id: sourceEventId,
      stream_ref: { kind: 'task', id: 'task-a' },
      scope,
      payload: {
        work_ref: { kind: 'task', id: 'task-a' },
        seq: 1,
        state: 'terminal',
        outcome,
      },
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

function formalVoiceStopButton(renderer) {
  const button = renderer.root
    .findAllByType('button')
    .find(candidate => candidate.children.some(child => typeof child === 'string' && child.includes('Stop and recognize')));
  assert.ok(button, 'formal P1 Stop button must be mounted');
  return button;
}

function mountedRecognizedConfirmation(renderer) {
  const root = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' });
  const buttons = root.findAllByType('button');
  const button = label => {
    const selected = buttons.find(candidate => candidate.children.some(child => child === label));
    assert.ok(selected, `recognized confirmation button ${label} must exist`);
    return selected;
  };
  return { root, button };
}

function mountedMediaBinding(params, index) {
  return {
    lease_id: `mounted-media-lease-${index}`,
    authority_evidence_id: `mounted-media-authority-${index}`,
    connection_id: `mounted-media-connection-${index}`,
    connection_epoch: 0,
    session_id: params.session_id,
    media_session_id: `mounted-media-session-${index}`,
    interaction_id: params.interaction_id,
    track_id: params.track_id,
    correlation_id: params.correlation_id,
    direction: 'uplink',
    generation: { kind: 'capture', id: params.capture_id, value: params.capture_generation },
    frame_format: {
      sample_rate_hz: 48_000,
      samples_per_channel: 960,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
    playout: null,
  };
}

function mountedRecognition(params, text, index) {
  return {
    contract_version: 'live-voice.contract.v2',
    request_id: params.request_id,
    operation_id: params.operation_id,
    ok: true,
    error: null,
    result: {
      operation: 'speech.recognize.batch',
      voice_commit_receipt: `mounted-voice-receipt-${index}`,
      capture: params.capture,
      event: {
        session_id: params.capture.capture_id,
        generation: params.capture.capture_generation,
        seq: 0,
        kind: 'final',
        commits_turn: false,
        hypothesis: {
          alternatives: [{ raw_text: text, display_text: text, confidence: null }],
          selected_index: 0,
        },
      },
      provider: {
        provider_id: 'mounted-provider',
        implementation_class: 'formal',
        fallback_from: null,
        model: 'mounted-stt',
      },
    },
  };
}

function mountedP2SubmitResult(params, requestId) {
  const task = params.dispatch_target === 'task';
  return {
    request_id: requestId,
    ok: true,
    error: null,
    result: {
      status: task ? 'task_origin_accepted' : 'round_accepted',
      session_id: params.session_id,
      correlation_id: params.correlation_id,
      interaction_id: params.interaction_id,
      activation_id: params.activation_id,
      activation_generation: params.activation_generation,
      turn_id: params.turn_id,
      commit_id: params.commit_id,
      ...(task ? {} : { round_id: 'mounted-round-1' }),
      response: {
        interaction_id: params.interaction_id,
        response_id: task ? 'mounted-server-task-response' : params.response_id,
        response_generation: 0,
      },
    },
  };
}

async function waitForMounted(predicate, message, timeoutMs = 1_000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) assert.fail(message);
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}

test('mounted recognized speech requires an exact in-page second action and fences Agent and task dispatch', async () => {
  const i18n = await createI18n();
  const calls = [];
  const productVoiceControlRef = { current: null };
  const productVoiceStates = [];
  let activeMediaBinding = null;
  let recognitionIndex = 0;
  let resolveAgentSubmit = null;
  let resolveTaskSubmit = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });

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
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(params, calls.filter(call => call.method === method).length);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'mounted-media-subject',
        endpoint_path: '/ws/live-voice/media/private-ticket',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      recognitionIndex += 1;
      return mountedRecognition(params, recognitionIndex === 1 ? 'Mounted Agent speech' : 'Mounted task speech', recognitionIndex);
    }
    if (method === 'live_voice.composition.p2.submit') {
      const requestId = options?.requestId;
      assert.equal(typeof requestId, 'string');
      if (params.dispatch_target === 'task') {
        return new Promise(resolve => {
          resolveTaskSubmit = () => resolve(mountedP2SubmitResult(params, requestId));
        });
      }
      return new Promise(resolve => {
        resolveAgentSubmit = () => resolve(mountedP2SubmitResult(params, requestId));
      });
    }
    if (method === 'live_voice.composition.p3.confirmation.issue') {
      return {
        ok: true,
        result: {
          status: 'confirmation_issued',
          operation: params.operation,
          command_id: params.command_id,
          target_task_id: null,
          confirmation_id: `mounted-confirmation-${params.command_id}`,
          expires_at: '2999-08-10T10:00:00Z',
          task_control_binding: {
            subject_id: 'mounted-p3-subject',
            session_id: params.session_id,
            project_id: 'mounted-project',
            correlation_id: params.correlation_id,
            generation: 1,
          },
        },
      };
    }
    if (method === 'live_voice.composition.p3.mutate') {
      return {
        ok: true,
        result: {
          status: 'mutation_processed',
          operation: params.operation,
          command_id: params.command_id,
          target_task_id: null,
          formal_task_result: {
            task_id: 'mounted-structured-task',
            attempt_id: 'mounted-structured-attempt',
            attempt_number: 1,
            state: 'accepted',
            outbox_id: 'mounted-structured-outbox',
          },
        },
      };
    }
    throw new Error(`unexpected fully-enabled mounted request: ${method}`);
  };

  const capture = async text => {
    await act(async () => {
      void productVoiceControlRef.current.start();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('starting'), 'formal voice capture did not enter readiness');
      await browser.emitFirstFrame();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('capturing'), 'formal voice capture did not start');
    });
    await act(async () => {
      await productVoiceControlRef.current.stop();
      await waitForMounted(
        () => renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-product-text' }).findByType('textarea').props.value === text,
        'recognized speech did not populate the mounted product form'
      );
    });
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, 'mounted-confirm-session', request, true, {
          productVoiceControlRef,
          onProductVoiceStateChange: state => productVoiceStates.push(state),
        })
      );
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Start formal voice turn'), 'both-on panel did not mount');
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'both-on panel did not activate P2');
      await waitForMounted(() => productVoiceControlRef.current !== null, 'formal product Live Voice control was not published');
      await waitForMounted(() => productVoiceStates.at(-1)?.available === true, 'formal product Live Voice state did not become available');
    });

    await capture('Mounted Agent speech');
    const productForm = () => renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-product-text' });
    await act(async () => {
      productVoiceControlRef.current.submit();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 1,
        'Agent speech did not open the in-page confirmation'
      );
      await waitForMounted(() => productVoiceStates.at(-1)?.confirmation_phase === 'confirming', 'formal product Live Voice did not publish confirmation');
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 0);
    assert.equal(productForm().findByType('textarea').props.disabled, true);
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);

    await act(async () => {
      productVoiceControlRef.current.cancelConfirmation();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 0,
        'cancel did not close the in-page confirmation'
      );
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 0, 'cancel must have zero Agent transport effect');

    await act(async () => {
      productForm()
        .findByType('textarea')
        .props.onChange({ target: { value: 'Edited Agent speech' } });
      await waitForMounted(() => productForm().findByType('textarea').props.value === 'Edited Agent speech', 'speech edit did not settle');
    });
    await act(async () => {
      productVoiceControlRef.current.submit();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 1,
        'edited speech did not retain the explicit confirmation boundary'
      );
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 0, 'editing speech must not dispatch before confirmation');
    await act(async () => {
      productVoiceControlRef.current.cancelConfirmation();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 0,
        'edited speech confirmation did not cancel'
      );
    });

    await capture('Mounted task speech');
    await act(async () => {
      productVoiceControlRef.current.submit();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 1,
        'Agent speech did not reopen confirmation after cancel'
      );
    });
    await act(async () => {
      void productVoiceControlRef.current.confirm();
      void productVoiceControlRef.current.confirm();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.submit').length === 1,
        'confirmed Agent speech did not issue one exact P2 submit'
      );
    });
    assert.equal(typeof resolveAgentSubmit, 'function');
    assert.equal(mountedP3Controls(renderer).select.props.disabled, true);
    assert.equal(mountedP3Controls(renderer).root.findByType('textarea').props.disabled, true);
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);
    await act(async () => {
      resolveAgentSubmit();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 0,
        'Agent confirmation did not settle after the exact P2 result'
      );
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 1, 'duplicate confirm must have zero extra Agent effect');

    await capture('Mounted task speech');
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 1,
        'task speech did not open the in-page confirmation'
      );
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 1);
    const taskConfirm = mountedRecognizedConfirmation(renderer).button('Confirm and dispatch').props.onClick;
    await act(async () => {
      taskConfirm();
      taskConfirm();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.submit').length === 2,
        'confirmed task speech did not issue one exact task-origin submit'
      );
    });
    assert.equal(typeof resolveTaskSubmit, 'function');
    assert.equal(mountedP3Controls(renderer).select.props.disabled, true);
    assert.equal(
      mountedP3Controls(renderer)
        .root.findAllByType('input')
        .every(input => input.props.disabled),
      true
    );
    assert.equal(mountedP3Controls(renderer).root.findByType('textarea').props.disabled, true);
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);

    const disabledOperationChange = mountedP3Controls(renderer).select.props.onChange;
    await act(async () => {
      disabledOperationChange({ target: { value: 'task.cancel' } });
      resolveTaskSubmit();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 0,
        'changed task controls did not fence the retained speech confirmation'
      );
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length,
      0,
      'a stale task-origin result must not issue a P3 confirmation'
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 2, 'stale task confirm must not duplicate P2 submit');

    await act(async () => {
      mountedP3Controls(renderer).select.props.onChange({ target: { value: 'task.create' } });
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.create', 'task controls did not return to create');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length === 1,
        'fresh structured task confirmation did not settle after the stale voice origin was fenced'
      );
    });
    const structuredConfirmation = calls.find(call => call.method === 'live_voice.composition.p3.confirmation.issue');
    assert.equal(structuredConfirmation.params.source, 'structured', 'the invalidated task-origin must not be reused as voice authority');
    assert.equal('interaction_id' in structuredConfirmation.params, false);
    assert.equal('turn_id' in structuredConfirmation.params, false);
    assert.equal('commit_id' in structuredConfirmation.params, false);

    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.cancel', 'structured task.create did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).select.props.onChange({ target: { value: 'task.create' } });
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.create', 'fresh voice task did not restore task.create');
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'settled task-origin did not reopen formal voice capture');
    });
    await capture('Mounted task speech');
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length === 1,
        'fresh voice task did not open its exact in-page confirmation'
      );
    });
    await act(async () => {
      mountedRecognizedConfirmation(renderer).button('Confirm and dispatch').props.onClick();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.submit').length === 3,
        'fresh voice task did not issue one task-origin submit'
      );
    });
    assert.equal(typeof resolveTaskSubmit, 'function');
    await act(async () => {
      resolveTaskSubmit();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length === 2,
        'exact task-origin result did not issue the positive voice P3 confirmation'
      );
    });
    const taskSubmit = calls.filter(call => call.method === 'live_voice.composition.p2.submit').at(-1);
    const voiceConfirmation = calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').at(-1);
    assert.deepEqual(
      {
        source: voiceConfirmation.params.source,
        interaction_id: voiceConfirmation.params.interaction_id,
        turn_id: voiceConfirmation.params.turn_id,
        commit_id: voiceConfirmation.params.commit_id,
        instruction: voiceConfirmation.params.instruction,
      },
      {
        source: 'voice',
        interaction_id: taskSubmit.params.interaction_id,
        turn_id: taskSubmit.params.turn_id,
        commit_id: taskSubmit.params.commit_id,
        instruction: taskSubmit.params.text,
      }
    );
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setImmediate(resolve));
      });
    }
    browser.restore();
  }
});

test('mounted recognized speech cannot cross a same-Session P2 activation rollover', async () => {
  const i18n = await createI18n();
  const calls = [];
  const p2Activations = [];
  let activeMediaBinding = null;
  let rejectFirstNotification = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });

  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') {
      p2Activations.push({ ...params });
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      if (rejectFirstNotification === null) {
        return new Promise((_, reject) => {
          rejectFirstNotification = () => {
            const error = Object.assign(new Error('notification stream closed'), {
              code: 'UNAVAILABLE',
              reason: 'NOTIFICATION_STREAM_CLOSED',
            });
            reject(error);
          };
        });
      }
      return new Promise(() => {});
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(params, 1);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'mounted-rollover-media-subject',
        endpoint_path: '/ws/live-voice/media/private-ticket',
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Mounted stale activation speech', 1);
    }
    throw new Error(`forbidden rollover business effect: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedFullyEnabledElement(i18n, 'mounted-rollover-session', request));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Start formal voice turn'), 'rollover panel did not mount');
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'rollover panel did not activate P2');
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('starting'), 'rollover capture did not enter readiness');
      await browser.emitFirstFrame();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('capturing'), 'rollover capture did not start');
    });
    await act(async () => {
      formalVoiceStopButton(renderer).props.onClick();
      await waitForMounted(
        () =>
          renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-product-text' }).findByType('textarea').props.value ===
          'Mounted stale activation speech',
        'rollover recognition did not settle'
      );
    });
    assert.equal(typeof rejectFirstNotification, 'function');
    const firstBinding = p2Activations[0];
    await act(async () => {
      rejectFirstNotification();
      await waitForMounted(() => p2Activations.length === 2, 'closed notification did not activate one exact P2 successor');
    });
    assert.equal(p2Activations[1].session_id, firstBinding.session_id);
    assert.equal(p2Activations[1].activation_generation, firstBinding.activation_generation + 1);
    assert.notEqual(p2Activations[1].activation_id, firstBinding.activation_id);

    const productForm = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-product-text' });
    await act(async () => {
      productForm.props.onSubmit({ preventDefault() {} });
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-recognized-confirmation' }).length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length, 0);
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setImmediate(resolve));
      });
    }
    browser.restore();
  }
});

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

test('mounted P3 origin panel reconciles and ACKs authoritative completed and failed progress', async () => {
  for (const outcome of ['completed', 'failed']) {
    const i18n = await createI18n();
    const browser = installP1BrowserEnvironment();
    const calls = [];
    let binding = null;
    let exactProgressActivation = null;
    let progressListener = null;
    let mutationCount = 0;
    let renderer;
    const progressSubscribe = listener => {
      progressListener = listener;
      return () => {
        if (progressListener === listener) progressListener = null;
      };
    };
    const taskEvents = () => {
      const scope = {
        subject_id: binding.subject_id,
        session_id: binding.session_id,
        project_id: binding.project_id,
        assurance: 'authenticated',
      };
      return {
        ok: true,
        result: {
          task_id: 'task-a',
          after_seq: -1,
          head_seq: 1,
          events: [
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
              occurred_at: '2026-08-11T08:00:00Z',
              details: {},
            },
            {
              event_id: 'task-a:event:1',
              task_id: 'task-a',
              attempt_id: 'attempt-a',
              scope,
              seq: 1,
              event_type: 'task.terminal',
              state: 'terminal',
              outcome,
              producer: 'task_core.delivery',
              source_event_id: 'executor-terminal-a',
              causation_id: 'executor-terminal-a',
              correlation_id: binding.correlation_id,
              occurred_at: '2026-08-11T08:00:01Z',
              details: {},
            },
          ],
        },
      };
    };
    const request = async (method, params, options) => {
      calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
      if (method === 'live_voice.composition.p2.activate') {
        return { ok: true, result: { status: 'active', ...params, replayed: false } };
      }
      if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
      if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
      if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
      if (method === 'live_voice.composition.p3.progress.activate') {
        exactProgressActivation = { ...params };
        return { ok: true, result: { status: 'active', ...params } };
      }
      if (method === 'live_voice.composition.p3.progress.close') {
        return { ok: true, result: { status: 'closed', ...params } };
      }
      if (method === 'live_voice.composition.p3.confirmation.issue') {
        binding = {
          subject_id: 'mounted-terminal-subject',
          session_id: params.session_id,
          project_id: 'mounted-terminal-project',
          correlation_id: params.correlation_id,
          generation: 1,
        };
        return {
          ok: true,
          result: {
            status: 'confirmation_issued',
            operation: 'task.create',
            command_id: params.command_id,
            target_task_id: null,
            confirmation_id: `confirmation-${params.command_id}`,
            expires_at: '2999-08-11T08:00:00Z',
            task_control_binding: binding,
          },
        };
      }
      if (method === 'live_voice.composition.p3.mutate') {
        mutationCount += 1;
        const taskId = mutationCount === 1 ? 'task-a' : 'task-b';
        return {
          ok: true,
          result: {
            status: 'mutation_processed',
            operation: 'task.create',
            command_id: params.command_id,
            target_task_id: null,
            formal_task_result: {
              task_id: taskId,
              attempt_id: mutationCount === 1 ? 'attempt-a' : 'attempt-b',
              attempt_number: 1,
              state: 'accepted',
              outbox_id: 'outbox-create-a',
            },
          },
        };
      }
      if (method === 'live_voice.task.events') return taskEvents();
      if (method === 'live_voice.composition.p3.progress.ack') {
        return {
          ok: true,
          result: {
            status: 'acknowledged',
            replayed: false,
            attempt_id: 'attempt-a',
            ...params,
            acknowledgement: 'web_ui_text_consumed',
          },
        };
      }
      throw new Error(`unexpected terminal-progress request: ${method}`);
    };

    try {
      await act(async () => {
        renderer = create(mountedP3Element(i18n, `mounted-terminal-${outcome}`, request, undefined, true, progressSubscribe));
        await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'terminal-progress P3 controls did not mount');
      });
      await act(async () => {
        const controls = mountedP3Controls(renderer);
        controls.root.findByType('textarea').props.onChange({ target: { value: 'Read the disposable fixture.' } });
        controls.root.findAllByType('input')[0].props.onChange({ target: { value: 'Mounted terminal task' } });
      });
      await act(async () => {
        mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
        await waitForMounted(
          () => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'),
          'terminal-progress task.create confirmation did not settle'
        );
      });
      await act(async () => {
        mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
        await waitForMounted(
          () => exactProgressActivation !== null && mountedP3Controls(renderer).select.props.value === 'task.cancel',
          'terminal-progress task.create did not bind its exact progress route'
        );
        await waitForMounted(
          () =>
            renderer.root
              .findByProps({ 'data-testid': 'live-voice-integrated-p3-activation' })
              .findAllByType('code')
              .some(node => node.children.some(child => child === 'p3:active')),
          'terminal-progress exact route did not become active'
        );
      });
      assert.equal(typeof progressListener, 'function');
      const terminalProgress = mountedTerminalProgress(binding, exactProgressActivation, outcome);
      const parsedTerminalProgress = parseProductTextProgressEvent(terminalProgress);
      assert.notEqual(parsedTerminalProgress, null);
      assert.equal(progressMatchesOwnedBinding(parsedTerminalProgress, exactProgressActivation, binding.session_id), true);
      await act(async () => {
        progressListener(terminalProgress);
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.task.events'),
          `mounted origin panel did not reconcile ${outcome}: ${calls.map(call => call.method).join(',')}`
        );
        await waitForMounted(
          () => renderer.root.findAllByType('code').some(node => node.children.some(child => child === outcome)),
          `mounted origin panel did not render ${outcome}`
        );
        await waitForMounted(() => calls.some(call => call.method === 'live_voice.composition.p3.progress.ack'), `mounted origin panel did not ACK ${outcome}`);
      });
      assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 1);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length, 1);

      await act(async () => {
        mountedP3Controls(renderer).select.props.onChange({ target: { value: 'task.create' } });
        await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.create', 'second create did not become selectable');
        mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
        await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'second task.create confirmation did not settle');
      });
      await act(async () => {
        mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
        await waitForMounted(
          () => exactProgressActivation?.task_id === 'task-b' && mountedP3Controls(renderer).select.props.value === 'task.cancel',
          'second task.create did not bind its exact progress route'
        );
      });
      assert.equal(
        renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-product-progress' }).length,
        0,
        'a successor task must clear the predecessor progress projection before replay arrives'
      );
      await act(async () => {
        progressListener(terminalProgress);
        await Promise.resolve();
      });
      assert.equal(
        renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-product-progress' }).length,
        0,
        'a late predecessor event must not repopulate the successor task projection'
      );
      assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 1);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length, 1);
    } finally {
      if (renderer) {
        await act(async () => {
          renderer.unmount();
          await Promise.resolve();
        });
      }
      browser.restore();
    }
  }
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

  const p3RetryInspectionWait = (_delayMs, signal) =>
    new Promise((resolve, reject) => {
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
          releaseDeferredStatus = () =>
            resolve(
              mountedP3Status(binding, {
                attemptId: 'attempt-c',
                attemptNumber: 3,
                state: 'accepted',
                eventHead: 6,
              })
            );
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
      return mountedP3Status(
        binding,
        terminalA ? { state: 'terminal', outcome: 'cancelled', eventHead: 2 } : { state: 'running', outcome: null, eventHead: 1 }
      );
    }
    if (method === 'live_voice.task.events') return mountedP3Events(binding, { terminalA, terminalB });
    throw new Error(`unexpected mounted P3 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'mounted-p3-session', request, p3RetryInspectionWait));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'formal P3 controls did not mount');
    });

    await act(async () => {
      const controls = mountedP3Controls(renderer);
      const inputs = controls.root.findAllByType('input');
      controls.root.findByType('textarea').props.onChange({ target: { value: 'Edit only the disposable fixture.' } });
      inputs[0].props.onChange({ target: { value: 'Mounted P3 task' } });
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.create confirmation did not settle');
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
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.cancel confirmation did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => retryWaiters.length === 1 && JSON.stringify(renderer.toJSON()).includes('checking'),
        'nonterminal task.cancel did not retain an authoritative retry inspection'
      );
    });
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);
    const confirmationsBeforeDefensiveFence = calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length;
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => retryWaiters.length === 0 && !JSON.stringify(renderer.toJSON()).includes('checking'),
        'defensive confirmation entry did not fence the retained retry inspection'
      );
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length,
      confirmationsBeforeDefensiveFence,
      'a programmatic confirmation during inspection must allocate zero confirmation effects'
    );
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false
    );

    terminalA = true;
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'terminal cancelled attempt did not automatically expose task.retry'
      );
    });
    assert.equal(retryWaiters.length, 0, 'terminal reconciliation must release its deterministic waiter');
    const createsBeforeRefresh = calls.filter(call => call.method === 'live_voice.composition.p3.mutate' && call.params.operation === 'task.create').length;
    await act(async () => {
      renderer.unmount();
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    renderer = null;
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'mounted-p3-session', request, p3RetryInspectionWait));
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(
        () =>
          mountedP3Controls(renderer).root.findByType('input').props.value === 'task-a' &&
          mountedP3Controls(renderer).select.props.value === 'task.retry' &&
          JSON.stringify(renderer.toJSON()).includes('cancelled'),
        'full page remount did not validate and restore the exact cancelled task target'
      );
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate' && call.params.operation === 'task.create').length,
      createsBeforeRefresh,
      'refresh recovery must not duplicate task.create'
    );
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.retry confirmation did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted retry B did not return the mounted controller to task.cancel'
      );
    });
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false
    );

    const mutationsBeforeDisconnect = calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length;
    await act(async () => {
      renderer.update(mountedP3Element(i18n, 'mounted-p3-session', request, p3RetryInspectionWait, false));
      await Promise.resolve();
    });
    assert.equal(renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-p3-mutation' }).length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, mutationsBeforeDisconnect);
    await act(async () => {
      renderer.update(mountedP3Element(i18n, 'mounted-p3-session', request, p3RetryInspectionWait, true));
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-p3-mutation' }).length === 1,
        'formal P3 controls did not recover after reconnect'
      );
    });

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
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.retry C confirmation did not settle');
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
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false
    );
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').map(call => [call.params.operation, call.params.task_id ?? null]),
      [
        ['task.create', null],
        ['task.cancel', 'task-a'],
        ['task.retry', 'task-a'],
        ['task.retry', 'task-a'],
      ]
    );
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate').map(call => [call.params.operation, call.params.task_id ?? null]),
      [
        ['task.create', null],
        ['task.cancel', 'task-a'],
        ['task.retry', 'task-a'],
        ['task.retry', 'task-a'],
      ]
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
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false
    );
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

test('mounted pending operation is checkpointed before replay and unmount performs zero close', async () => {
  const i18n = await createI18n();
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const binding = {
    session_id: 'mounted-pending-unmount-session',
    correlation_id: 'mounted-pending-unmount-correlation',
    interaction_id: 'mounted-pending-unmount-interaction',
    activation_id: 'mounted-pending-unmount-activation',
    activation_generation: 1,
  };
  const operation = {
    method: 'live_voice.composition.p2.presentation.ack',
    request_id: 'mounted-pending-unmount-request',
    params: {
      ...binding,
      response_id: 'mounted-pending-unmount-response',
      response_generation: 0,
      surface: 'text',
      unit_id: 'mounted-pending-unmount-unit',
      contiguous_cursor: 0,
      presented_at: '2026-08-10T12:00:00.000Z',
    },
  };
  const key = `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(binding.session_id)}`;
  values.set(key, JSON.stringify(pendingP2Journal(binding, operation)));
  const restore = installP2RecoveryBrowser(storage);
  const effects = [];
  let renderer;
  try {
    const request = async (method, params, options) => {
      effects.push([method, params, options]);
      if (method === operation.method) {
        const checkpoint = JSON.parse(values.get(key));
        assert.equal(checkpoint.phase, 'operation_reconciling');
        assert.deepEqual(checkpoint.pending_operation, operation);
        assert.equal(options.requestId, operation.request_id);
        return new Promise(() => {});
      }
      throw new Error(`pending unmount must not call ${method}`);
    };
    await act(async () => {
      renderer = create(mountedP3Element(i18n, binding.session_id, request));
    });
    await act(async () => {
      await waitForMounted(() => effects.filter(([method]) => method === operation.method).length === 1, 'pending operation did not begin exact replay');
    });
    await act(async () => {
      renderer.unmount();
      renderer = null;
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    assert.equal(effects.filter(([method]) => method === operation.method).length, 1);
    assert.equal(
      effects.some(([method]) => method === 'live_voice.composition.p2.activate' || method === 'live_voice.composition.p2.close'),
      false
    );
    assert.equal(JSON.parse(values.get(key)).pending_operation.request_id, operation.request_id);
  } finally {
    if (renderer) renderer.unmount();
    restore();
  }
});

test('mounted teardown performs zero close after a newer recovery CAS owns the journal', async () => {
  const i18n = await createI18n();
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const sessionId = 'mounted-cas-stolen-session';
  const key = `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`;
  const restore = installP2RecoveryBrowser(storage);
  const calls = [];
  let renderer;
  try {
    const request = async (method, params) => {
      calls.push({ method, params });
      if (method === 'live_voice.composition.p2.activate') {
        return { ok: true, result: { status: 'active', ...params, replayed: false } };
      }
      if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
        return new Promise(() => {});
      }
      if (method === 'live_voice.composition.p2.close') {
        return { ok: true, result: { status: 'closed', ...params } };
      }
      throw new Error(`unexpected CAS-stolen request: ${method}`);
    };
    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
    });
    await act(async () => {
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.activate').length === 1,
        'current route did not activate before CAS takeover'
      );
    });
    const stolen = JSON.parse(values.get(key));
    stolen.revision += 1;
    stolen.recovery_owner_id = 'newer-page';
    stolen.recovery_token = 'newer-page-token';
    stolen.recovery_epoch += 1;
    values.set(key, JSON.stringify(stolen));

    await act(async () => {
      renderer.unmount();
      renderer = null;
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.close').length, 0);
    assert.equal(JSON.parse(values.get(key)).recovery_token, 'newer-page-token');
  } finally {
    if (renderer) renderer.unmount();
    restore();
  }
});

test('mounted task submit recovery restores the exact voice origin for P3 create', async () => {
  const i18n = await createI18n();
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const binding = {
    session_id: 'mounted-task-recovery-session',
    correlation_id: 'mounted-task-recovery-correlation',
    interaction_id: 'mounted-task-recovery-interaction',
    activation_id: 'mounted-task-recovery-activation',
    activation_generation: 1,
  };
  const operation = {
    method: 'live_voice.composition.p2.submit',
    request_id: 'mounted-task-recovery-request',
    params: {
      ...binding,
      commit_id: 'mounted-task-recovery-commit',
      turn_id: 'mounted-task-recovery-turn',
      committed_at: '2026-08-10T12:00:00.000Z',
      text: 'Create the recovered voice task.',
      dispatch_target: 'task',
      voice_commit_receipt: 'r'.repeat(32),
      critical_confirmation: true,
    },
  };
  const key = `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(binding.session_id)}`;
  values.set(key, JSON.stringify(pendingP2Journal(binding, operation)));
  const restore = installP2RecoveryBrowser(storage);
  const calls = [];
  let renderer;
  try {
    const request = async (method, params, options) => {
      calls.push({ method, params, options });
      if (method === operation.method) {
        assert.deepEqual(params, operation.params);
        assert.equal(options.requestId, operation.request_id);
        return {
          request_id: operation.request_id,
          ok: true,
          result: {
            status: 'task_origin_accepted',
            ...binding,
            turn_id: operation.params.turn_id,
            commit_id: operation.params.commit_id,
            response: {
              interaction_id: binding.interaction_id,
              response_id: 'mounted-server-owned-response',
              response_generation: 0,
            },
          },
          error: null,
        };
      }
      if (method === 'live_voice.composition.p2.activate') {
        return { ok: true, result: { status: 'active', ...params, replayed: params.activation_generation === 1 } };
      }
      if (method === 'live_voice.composition.p2.close') {
        return { ok: true, result: { status: 'closed', ...params } };
      }
      if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
        return new Promise(() => {});
      }
      if (method === 'live_voice.composition.p3.confirmation.issue') {
        return {
          ok: true,
          result: {
            status: 'confirmation_issued',
            operation: params.operation,
            command_id: params.command_id,
            target_task_id: null,
            confirmation_id: 'mounted-task-recovery-confirmation',
            expires_at: '2999-08-10T12:00:00.000Z',
            task_control_binding: {
              subject_id: 'mounted-task-recovery-subject',
              session_id: binding.session_id,
              project_id: 'mounted-task-recovery-project',
              correlation_id: params.correlation_id,
              generation: 1,
            },
          },
        };
      }
      throw new Error(`unexpected mounted task recovery request: ${method}`);
    };
    await act(async () => {
      renderer = create(mountedP3Element(i18n, binding.session_id, request));
    });
    await act(async () => {
      await waitForMounted(
        () => mountedP3Controls(renderer).root.findByType('textarea').props.value === operation.params.text,
        'recovered task instruction was not restored'
      );
    });
    assert.equal(mountedP3Controls(renderer).root.findAllByType('input')[0].props.value, 'Voice task');
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'recovered voice origin did not issue P3 confirmation');
    });

    const confirmations = calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue');
    assert.equal(confirmations.length, 1);
    assert.deepEqual(
      {
        source: confirmations[0].params.source,
        interaction_id: confirmations[0].params.interaction_id,
        turn_id: confirmations[0].params.turn_id,
        commit_id: confirmations[0].params.commit_id,
        instruction: confirmations[0].params.instruction,
      },
      {
        source: 'voice',
        interaction_id: binding.interaction_id,
        turn_id: operation.params.turn_id,
        commit_id: operation.params.commit_id,
        instruction: operation.params.text,
      }
    );
    assert.equal(calls.filter(call => call.method === operation.method).length, 1);
    assert.equal(JSON.parse(values.get(key)).pending_operation, null);
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    restore();
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
      locks: createFakeWebLocks(),
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
    assert.equal(retainedMissingReplayJournal.phase, 'closing_unconfirmed');
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
