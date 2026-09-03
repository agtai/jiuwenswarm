import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test, { after } from 'node:test';

import { build } from 'esbuild';
import i18next from 'i18next';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { act, create as createRenderer } from 'react-test-renderer';

import {
  LiveVoiceIntegratedRoutePanel,
  progressMatchesOwnedBinding,
  terminalTextFallbackCompletesVoiceAnnouncement,
} from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';
import { parseProductTextProgressEvent } from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productTextProgress.js';

// Temporary C019 diagnostic capture: Product P1 names every failure and media
// authority revoke with a closed caller label. Scenarios assert on them.
const p1TransitionDiagnostics = [];
const originalMountedConsoleInfo = console.info;
console.info = (...args) => {
  if (
    args[0] === '[LiveVoiceC019] transition diagnostic'
    && ['browser_p1_failure_requested', 'browser_media_authority_revoke_requested'].includes(args[1]?.event)
  ) {
    p1TransitionDiagnostics.push(args[1]);
  }
  return originalMountedConsoleInfo(...args);
};
function p1FailureCallers() {
  return p1TransitionDiagnostics
    .filter(item => item.event === 'browser_p1_failure_requested')
    .map(item => `${item.caller}:${item.reason}:${item.status}`);
}
function p1RevokeCallers() {
  return p1TransitionDiagnostics
    .filter(item => item.event === 'browser_media_authority_revoke_requested')
    .map(item => `${item.caller}/${item.binding_role}`);
}
import {
  encodeAudioFrame,
  serializeMediaControl,
} from '../node_modules/.cache/live-voice-browser-dedicated-media/browserDedicatedMediaRoute.mjs';

function create(element) {
  return createRenderer(element, {
    createNodeMock(node) {
      if (node.type !== 'div' || typeof node.props?.['data-delivery-id'] !== 'string') return null;
      return {
        isConnected: true,
        getAttribute(name) {
          const value = node.props[name];
          return value === undefined || value === null ? null : String(value);
        },
      };
    },
  });
}

function mountedProgressActivation(params, overrides = {}) {
  const requested = params.origin_kind === 'voice' ? 'voice' : 'text';
  const fallback = requested === 'voice' ? 'TASK_PROGRESS_VOICE_DELIVERY_UNAVAILABLE' : null;
  return {
    status: 'active',
    ...params,
    requested_origin_kind: requested,
    origin_kind: 'text',
    voice_progress: 'unavailable',
    voice_reason: fallback ?? 'TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE',
    fallback_reason: fallback,
    replayed: false,
    ...overrides,
  };
}

function createMountedP2ActivationResponder() {
  const activeBindings = new Set();
  return params => {
    const key = JSON.stringify([params.session_id, params.correlation_id, params.interaction_id, params.activation_id, params.activation_generation]);
    const replayed = activeBindings.has(key);
    activeBindings.add(key);
    return { ok: true, result: { status: 'active', ...params, replayed } };
  };
}

const mountedBundleDirectory = await mkdtemp(fileURLToPath(new URL('../node_modules/.cache/jiuwenswarm-live-voice-mounted-', import.meta.url)));
after(async () => {
  await rm(mountedBundleDirectory, { recursive: true, force: true });
});

const ownershipLifecycleBundleUrl = pathToFileURL(join(mountedBundleDirectory, 'useProductVoiceBrowserOwnership.mjs'));
await build({
  entryPoints: [fileURLToPath(new URL('../src/components/ChatPanel/useProductVoiceBrowserOwnership.ts', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  outfile: fileURLToPath(ownershipLifecycleBundleUrl),
});
const { useProductVoiceBrowserOwnership } = await import(`${ownershipLifecycleBundleUrl.href}?ownership=${Date.now()}`);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const MountedProductVoiceBrowserOwnership = React.forwardRef((props, ref) => {
  const lifecycle = useProductVoiceBrowserOwnership(props);
  React.useImperativeHandle(ref, () => lifecycle, [lifecycle]);
  return null;
});

test('mounted production ChatPanel ownership lifecycle completes Session handoff before successor start', async () => {
  const closeSessionGate = deferred();
  const firstReleaseGate = deferred();
  const events = [];
  const releaseGates = [firstReleaseGate.promise, Promise.resolve()];
  let ownershipHeld = false;
  let activeSessionId = 'session-a';
  let takeover = null;
  const ownership = {
    async acquire(onTakeover) {
      takeover = onTakeover;
      events.push(`acquire-${ownershipHeld ? 'held' : 'free'}`);
      ownershipHeld = true;
    },
    async release() {
      events.push('release-start');
      await (releaseGates.shift() ?? Promise.resolve());
      ownershipHeld = false;
      events.push('release-finished');
    },
    async dispose() {
      await this.release();
    },
    disposeAfterRelease() {
      ownershipHeld = false;
      events.push('dispose-after-release');
    },
    isOwner() {
      return ownershipHeld;
    },
  };
  const oldControl = {
    async start() {
      events.push(`old-start-owner-${ownershipHeld}`);
    },
    async closeSession(sessionId) {
      events.push(`old-close-session-${sessionId}-start`);
      await closeSessionGate.promise;
      events.push(`old-close-session-${sessionId}-finished`);
    },
    async close() {
      events.push('old-close');
    },
  };
  const successorControl = {
    async start() {
      events.push(`successor-start-owner-${ownershipHeld}`);
    },
    async closeSession(sessionId) {
      events.push(`successor-close-session-${sessionId}`);
    },
    async close() {
      events.push('successor-close');
    },
  };
  const controlRef = { current: oldControl };
  const lifecycleRef = React.createRef();
  const createOwnership = () => ownership;
  const getActiveSessionId = () => activeSessionId;
  const element = sessionId => React.createElement(MountedProductVoiceBrowserOwnership, {
    ref: lifecycleRef,
    activeSessionId: sessionId,
    controlRef,
    createOwnership,
    getActiveSessionId,
  });
  let renderer;

  try {
    await act(async () => {
      renderer = create(element(activeSessionId));
    });
    await act(async () => {
      await lifecycleRef.current.start();
    });
    assert.deepEqual(events, ['acquire-free', 'old-start-owner-true']);

    activeSessionId = 'session-b';
    controlRef.current = successorControl;
    await act(async () => {
      renderer.update(element(activeSessionId));
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(events.at(-1), 'old-close-session-session-a-start');

    let successorStart;
    await act(async () => {
      successorStart = lifecycleRef.current.start();
      await new Promise(resolve => setImmediate(resolve));
    });
    closeSessionGate.resolve();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(events.at(-1), 'release-start');
    assert.equal(events.includes('successor-start-owner-true'), false);

    firstReleaseGate.resolve();
    await act(async () => {
      await successorStart;
    });
    assert.deepEqual(events.slice(-3), [
      'release-finished',
      'acquire-free',
      'successor-start-owner-true',
    ]);
    assert.equal(ownershipHeld, true);

    await act(async () => {
      await lifecycleRef.current.stop();
    });
    assert.equal(events.includes('old-close'), false);
    assert.equal(events.filter(event => event === 'successor-close').length, 1);
    assert.equal(events.at(-1), 'release-finished');
    assert.equal(ownershipHeld, false);
    assert.equal(typeof takeover, 'function');
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
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
const {
  LiveVoiceIntegratedRoutePanel: FullyEnabledLiveVoiceIntegratedRoutePanel,
  hasDurableProductVoiceSession,
} = await import(`${fullyEnabledBundleUrl.href}?enabled=${Date.now()}`);

const prefetchEnabledBundleUrl = pathToFileURL(join(mountedBundleDirectory, 'LiveVoiceIntegratedRoutePanelPrefetchEnabled.mjs'));
await build({
  entryPoints: [fileURLToPath(new URL('../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  loader: { '.css': 'empty' },
  outfile: fileURLToPath(prefetchEnabledBundleUrl),
  define: {
    'import.meta.env': JSON.stringify({
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB: 'true',
      VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1: 'true',
      VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION: 'true',
      VITE_FEATURE_LIVE_VOICE_TASK_DEMO: 'false',
      VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH: 'false',
      VITE_FEATURE_LIVE_VOICE_PREFETCH_PROMOTION: 'true',
    }),
  },
});
const { LiveVoiceIntegratedRoutePanel: PrefetchEnabledLiveVoiceIntegratedRoutePanel } =
  await import(`${prefetchEnabledBundleUrl.href}?enabled=${Date.now()}`);

const commandBarBundleUrl = pathToFileURL(join(mountedBundleDirectory, 'LiveVoiceCommandBar.mjs'));
await build({
  entryPoints: [fileURLToPath(new URL('../src/components/ChatPanel/LiveVoiceDemoBar.tsx', import.meta.url))],
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  loader: { '.css': 'empty' },
  outfile: fileURLToPath(commandBarBundleUrl),
});
const {
  FormalProductLiveVoiceDemoBar: MountedFormalProductLiveVoiceDemoBar,
  LiveVoiceDemoBar: MountedLiveVoiceDemoBar,
} = await import(`${commandBarBundleUrl.href}?commandBar=${Date.now()}`);

async function createI18n(language = 'en') {
  const translations = JSON.parse(await readFile(new URL(`../src/i18n/locales/${language}.json`, import.meta.url), 'utf8'));
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: false,
    resources: { [language]: { translation: translations } },
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

function installP1BrowserEnvironment({
  mediaBinding = null,
  getUserMedia: getUserMediaOverride = null,
  holdDownlinkDetach = false,
  holdDownlinkAttach = false,
  holdPrefetchPromotionAck = false,
  holdPrefetchParkAck = false,
  emitSocketCloseOnLocalClose = false,
  closeAudioContext: closeAudioContextOverride = null,
  startAudioSource: startAudioSourceOverride = null,
} = {}) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const audioContextDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext');
  const audioWorkletNodeDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'AudioWorkletNode');
  const webSocketDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'WebSocket');
  const values = new Map();
  const counts = {
    getUserMedia: 0,
    stoppedTracks: 0,
    enumerateDevices: 0,
    constraints: [],
    sinkIds: [],
    sourceStarts: 0,
    sourceStops: 0,
    sourceEnds: 0,
    audioContexts: 0,
    closedAudioContexts: 0,
    workletPorts: 0,
    closedWorkletPorts: 0,
    socketOpens: 0,
    socketCloses: 0,
  };
  let latestWorklet = null;
  let latestSource = null;
  let releasePrefetchPromotionAck = null;
  let releaseDownlinkAttach = null;
  let nextWorkletFirstFrameSamples = null;
  const sockets = [];
  const speechStartSignals = [];
  const endOfTurnSignals = [];

  class FakeAudioTrack {
    constructor(id) {
      this.id = id;
      this.kind = 'audio';
      this.readyState = 'live';
      this.muted = false;
      this.listeners = new Map();
    }

    stop() {
      if (this.readyState !== 'ended') counts.stoppedTracks += 1;
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
      counts.audioContexts += 1;
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

    async setSinkId(deviceId) {
      counts.sinkIds.push(deviceId);
    }

    async close() {
      if (closeAudioContextOverride !== null) await closeAudioContextOverride();
      if (this.state !== 'closed') counts.closedAudioContexts += 1;
      this.state = 'closed';
    }

    createMediaStreamSource() {
      return new FakeAudioNode();
    }

    createBuffer() {
      return { copyToChannel() {} };
    }

    createBufferSource() {
      const source = {
        buffer: null,
        onended: null,
        connect() {},
        disconnect() {},
        start() {
          counts.sourceStarts += 1;
          if (startAudioSourceOverride !== null) startAudioSourceOverride({ source, counts });
        },
        stop() {
          counts.sourceStops += 1;
        },
      };
      latestSource = source;
      return source;
    }
  }

  class FakeAudioWorkletNode extends FakeAudioNode {
    constructor(_context, _name, options) {
      super();
      counts.workletPorts += 1;
      this.captureGeneration = options.processorOptions.captureGeneration;
      let onmessage = null;
      let portClosed = false;
      this.port = {
        close() {
          if (!portClosed) counts.closedWorkletPorts += 1;
          portClosed = true;
        },
      };
      Object.defineProperty(this.port, 'onmessage', {
        get: () => onmessage,
        set: handler => {
          onmessage = handler;
          const samples = nextWorkletFirstFrameSamples;
          if (typeof handler !== 'function' || samples === null) return;
          nextWorkletFirstFrameSamples = null;
          setTimeout(() =>
            handler({
              data: {
                kind: 'frame',
                capture_generation: this.captureGeneration,
                seq: 0,
                sample_rate_hz: 48_000,
                sample_cursor: 0,
                context_time_s: 0,
                samples,
              },
            }),
          250);
        },
      });
      this.onprocessorerror = null;
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
    binding = null;
    sent = [];

    constructor() {
      sockets.push(this);
      counts.socketOpens += 1;
      queueMicrotask(() => {
        const fallbackBinding = mediaBinding?.();
        if (fallbackBinding === null || fallbackBinding === undefined) {
          this.readyState = 3;
          this.onerror?.({});
          return;
        }
        this.readyState = 1;
        this.protocol = 'live-voice.media.v1';
        this.onopen?.({});
      });
    }

    send(value) {
      this.sent.push(value);
      if (typeof value === 'string') {
        const control = JSON.parse(value);
        if (control.type === 'media.auth') {
          this.binding = control.binding;
          const attach = () => {
            this.onmessage?.({
              data: serializeMediaControl({ type: 'media.attach', binding: this.binding }),
            });
          };
          if (
            this.binding?.direction === 'downlink'
            && (typeof holdDownlinkAttach === 'function' ? holdDownlinkAttach(this.binding) : holdDownlinkAttach)
          ) {
            // The Gateway has not attached this downlink yet; the test
            // decides when (or whether) the server attach arrives.
            releaseDownlinkAttach = attach;
            return;
          }
          queueMicrotask(attach);
          return;
        }
        if (control.type === 'media.detach') {
          queueMicrotask(() => this.onmessage?.({ data: value }));
        }
        if (control.type === 'media.prefetch_transition') {
          const acknowledge = () => this.onmessage?.({
            data: serializeMediaControl({
              ...control,
              type: 'media.prefetch_transition_ack',
            }),
          });
          if (
            (holdPrefetchPromotionAck && control.state !== 'prefetch_parked')
            || (holdPrefetchParkAck && control.state === 'prefetch_parked')
          ) {
            releasePrefetchPromotionAck = acknowledge;
          } else {
            queueMicrotask(acknowledge);
          }
          return;
        }
        if (
          control.type === 'media.ack'
          && this.binding?.direction === 'downlink'
          && !(typeof holdDownlinkDetach === 'function'
            ? holdDownlinkDetach(this.binding)
            : holdDownlinkDetach)
        ) {
          queueMicrotask(() =>
            this.onmessage?.({
              data: serializeMediaControl({
                type: 'media.detach',
                lease_id: this.binding.lease_id,
                generation: this.binding.generation.value,
                reason_id: 'MEDIA_LOCAL_CLOSE',
                through_seq: control.through_seq,
                business_cancel_count_delta: 0,
              }),
            }),
          );
        }
        return;
      }
      const binding = this.binding;
      assert.ok(binding);
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
        }),
      );
    }

    close() {
      if (this.readyState !== 3) counts.socketCloses += 1;
      this.readyState = 3;
      if (emitSocketCloseOnLocalClose) {
        queueMicrotask(() => this.onclose?.({ code: 1000, reason: '', wasClean: true }));
      }
    }
  }

  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  const mediaDeviceListeners = new Map();
  let enumerateDevices = async () => [
    { kind: 'audioinput', deviceId: 'mounted-private-input', label: 'Mounted microphone' },
    { kind: 'audiooutput', deviceId: 'mounted-private-output', label: 'Mounted speaker' },
  ];
  const mediaDevices = {
    async getUserMedia(constraints) {
      counts.getUserMedia += 1;
      counts.constraints.push(constraints);
      const createStream = () => {
        const track = new FakeAudioTrack(`mounted-p1-track-${counts.getUserMedia}`);
        return {
          getAudioTracks: () => [track],
          getTracks: () => [track],
        };
      };
      return getUserMediaOverride === null ? createStream() : getUserMediaOverride({ constraints, createStream });
    },
    enumerateDevices: async () => {
      counts.enumerateDevices += 1;
      return enumerateDevices();
    },
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
    speechStartSignals,
    endOfTurnSignals,
    emitDeviceChange() {
      mediaDeviceListeners.get('devicechange')?.();
    },
    setEnumerateDevices(implementation) {
      enumerateDevices = implementation;
    },
    async emitFirstFrame(sampleValue = 0.25) {
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
          samples: new Float32Array(960).fill(sampleValue),
        },
      });
    },
    async rotateSilentCaptureWindow() {
      await waitForMounted(() => typeof latestWorklet?.port.onmessage === 'function', 'mounted silent P1 worklet did not become ready');
      const priorWorklet = latestWorklet;
      const handler = priorWorklet.port.onmessage;
      const frameCount = 30_000 / 20;
      const samples = new Float32Array(960);
      nextWorkletFirstFrameSamples = samples;
      for (let seq = 1; seq < frameCount; seq += 1) {
        handler({
          data: {
            kind: 'frame',
            capture_generation: priorWorklet.captureGeneration,
            seq,
            sample_rate_hz: 48_000,
            sample_cursor: seq * 960,
            context_time_s: seq * 0.02,
            samples,
          },
        });
        if (seq % 64 === 0) await new Promise(resolve => setImmediate(resolve));
      }
      await waitForMounted(
        () => latestWorklet !== priorWorklet && typeof latestWorklet?.port.onmessage === 'function',
        'mounted silent P1 capture did not rotate',
        4_000,
      );
    },
    async emitDownlinkFrame() {
      await waitForMounted(
        () => sockets.some(socket => socket.binding?.direction === 'downlink'),
        `dedicated downlink media route did not attach; sockets=${sockets.map(socket => socket.binding?.direction ?? 'unbound').join(',')}`,
      );
      await new Promise(resolve => setImmediate(resolve));
      const socket =
        sockets.filter(candidate => candidate.binding?.direction === 'downlink' && candidate.readyState === FakeWebSocket.OPEN).at(-1)
        ?? sockets.filter(candidate => candidate.binding?.direction === 'downlink').at(-1);
      socket.onmessage?.({
        data: encodeAudioFrame(socket.binding, {
          seq: 0,
          sample_cursor: 0,
          samples: new Float32Array(960).fill(0.125),
        }),
      });
      await new Promise(resolve => setImmediate(resolve));
    },
    async emitDownlinkFrames(count, { fromSeq = 0 } = {}) {
      // Drive the latest attached downlink far enough for a staged successor
      // to retain its PARK reserve (25 frames) without rendering any audio.
      await waitForMounted(
        () => sockets.some(socket => socket.binding?.direction === 'downlink' && socket.readyState === FakeWebSocket.OPEN),
        'dedicated downlink media route did not attach',
      );
      const socket = sockets
        .filter(candidate => candidate.binding?.direction === 'downlink' && candidate.readyState === FakeWebSocket.OPEN)
        .at(-1);
      for (let seq = fromSeq; seq < fromSeq + count; seq += 1) {
        socket.onmessage?.({
          data: encodeAudioFrame(socket.binding, {
            seq,
            sample_cursor: seq * 960,
            samples: new Float32Array(960).fill(0.125),
          }),
        });
        if (seq % 8 === 7) await new Promise(resolve => setImmediate(resolve));
      }
      await new Promise(resolve => setImmediate(resolve));
    },
    hasRetainedPrefetchTransition() {
      return releasePrefetchPromotionAck !== null;
    },
    latestDownlinkControlTypes() {
      const socket = sockets
        .filter(candidate => candidate.binding?.direction === 'downlink')
        .at(-1);
      return socket === undefined
        ? []
        : socket.sent
          .filter(value => typeof value === 'string')
          .map(JSON.parse)
          .map(control => control.type);
    },
    releasePrefetchPromotion() {
      const release = releasePrefetchPromotionAck;
      releasePrefetchPromotionAck = null;
      assert.equal(typeof release, 'function', 'no retained prefetch promotion ACK exists');
      release();
    },
    hasHeldDownlinkAttach() {
      return releaseDownlinkAttach !== null;
    },
    releaseDownlinkAttach() {
      const release = releaseDownlinkAttach;
      releaseDownlinkAttach = null;
      assert.equal(typeof release, 'function', 'no held downlink attach exists');
      release();
    },
    closeRoutesForLease(leaseId) {
      // Gateway `live_voice.media.close` revokes every route of the subject
      // and aborts its streaming recognition; the Browser observes each
      // attached socket closing remotely and can never receive a later EOT.
      let closed = 0;
      for (const socket of sockets) {
        if (socket.binding?.lease_id !== leaseId || socket.readyState === 3) continue;
        socket.readyState = 3;
        closed += 1;
        queueMicrotask(() => socket.onclose?.({ code: 1000, reason: '', wasClean: true }));
      }
      return closed;
    },
    async emitSpeechStartDuringPlayout() {
      await waitForMounted(
        () => sockets.filter(socket => socket.binding?.direction === 'uplink').length >= 2,
        'successor uplink media route did not attach during playout',
      );
      const uplinkSockets = sockets.filter(socket => socket.binding?.direction === 'uplink');
      const socket = uplinkSockets.at(-1);
      const event = {
        type: 'media.speech_start',
        capability_version: 'media.end_of_turn.v1',
        lease_id: socket.binding.lease_id,
        generation: socket.binding.generation.value,
        detector: 'server_vad',
        provider_start_ms: 100,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      };
      speechStartSignals.push(event);
      socket.onmessage?.({ data: serializeMediaControl(event) });
      await new Promise(resolve => setImmediate(resolve));
    },
    async emitSpeechEndOfTurnDuringPlayout() {
      const uplinkSockets = sockets.filter(socket => socket.binding?.direction === 'uplink');
      const socket = uplinkSockets.at(-1);
      // A revoked or closed uplink can never deliver a later server EOT.
      if (socket.readyState === 3) return false;
      const event = {
        type: 'media.end_of_turn',
        capability_version: 'media.end_of_turn.v1',
        lease_id: socket.binding.lease_id,
        generation: socket.binding.generation.value,
        detector: 'server_vad',
        speech_started_observed: true,
        provider_start_ms: 100,
        provider_end_ms: 700,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      };
      endOfTurnSignals.push(event);
      socket.onmessage?.({
        data: serializeMediaControl(event),
      });
      await new Promise(resolve => setImmediate(resolve));
      return true;
    },
    async emitSpeechEndOfTurn() {
      await waitForMounted(
        () => sockets.some(socket => socket.binding?.direction === 'uplink'),
        'active uplink media route did not attach for server EOT',
      );
      const socket = sockets.filter(candidate => candidate.binding?.direction === 'uplink').at(-1);
      const speechStart = {
        type: 'media.speech_start',
        capability_version: 'media.end_of_turn.v1',
        lease_id: socket.binding.lease_id,
        generation: socket.binding.generation.value,
        detector: 'server_vad',
        provider_start_ms: 100,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      };
      speechStartSignals.push(speechStart);
      socket.onmessage?.({ data: serializeMediaControl(speechStart) });
      const event = {
        type: 'media.end_of_turn',
        capability_version: 'media.end_of_turn.v1',
        lease_id: socket.binding.lease_id,
        generation: socket.binding.generation.value,
        detector: 'server_vad',
        speech_started_observed: true,
        provider_start_ms: 100,
        provider_end_ms: 700,
        timing_basis: 'provider_time',
        timing_provenance: 'adapter_derived',
        create_response: false,
        interrupt_response: false,
        business_cancel_count_delta: 0,
      };
      endOfTurnSignals.push(event);
      socket.onmessage?.({ data: serializeMediaControl(event) });
      await new Promise(resolve => setImmediate(resolve));
    },
    endLatestSource() {
      if (latestSource?.onended) {
        counts.sourceEnds += 1;
        latestSource.onended();
      }
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

function mountedP1Element(i18n, sessionId, request, extraProps = {}) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(EnabledLiveVoiceIntegratedRoutePanel, {
      activeSessionId: sessionId,
      isConnected: true,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      ...extraProps,
    }),
  );
}

function mountedP3Element(
  i18n,
  sessionId,
  request,
  p3RetryInspectionWait,
  isConnected = true,
  progressSubscribe = undefined,
  extraProps = {},
) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(MountedProductCarrier, {
      routeComponent: P3EnabledLiveVoiceIntegratedRoutePanel,
      activeSessionId: sessionId,
      isConnected,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      p3RetryInspectionWait,
      progressSubscribe,
      ...extraProps,
    }),
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
    }),
  );
}

function mountedPrefetchEnabledElement(i18n, sessionId, request, isConnected = true, extraProps = {}) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(PrefetchEnabledLiveVoiceIntegratedRoutePanel, {
      activeSessionId: sessionId,
      isConnected,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      ...extraProps,
    }),
  );
}

function MountedProductCarrier({ routeComponent: RouteComponent, onProductVoiceStateChange, ...routeProps }) {
  const [surfaceState, setSurfaceState] = React.useState(null);
  const adoptSurfaceState = React.useCallback(next => {
    setSurfaceState(next);
    onProductVoiceStateChange?.(next);
  }, [onProductVoiceStateChange]);
  return React.createElement(
    React.Fragment,
    null,
    React.createElement(RouteComponent, {
      ...routeProps,
      onProductVoiceStateChange: adoptSurfaceState,
    }),
    React.createElement(MountedFormalProductLiveVoiceDemoBar, {
      active: true,
      available: true,
      status: 'listening',
      interimTranscript: '',
      committedTranscript: '',
      handsFree: true,
      surfaceState,
      async onTaskRefresh() {},
      async onTaskSelect() {},
      async onTaskMutation() {},
      async onTaskConfirm() {},
      onEnable() {},
      onExit() {},
      onPrimaryAction() {},
    }),
  );
}

function mountedFullyEnabledProductCarrierElement(i18n, sessionId, request, isConnected = true, extraProps = {}) {
  return React.createElement(
    I18nextProvider,
    { i18n },
    React.createElement(MountedProductCarrier, {
      routeComponent: FullyEnabledLiveVoiceIntegratedRoutePanel,
      activeSessionId: sessionId,
      isConnected,
      agentRouteAvailable: true,
      taskCompatibilityAvailable: false,
      request,
      ...extraProps,
    }),
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

function mountedTaskIntentControls(renderer) {
  const root = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-formal-task-intent' });
  return {
    root,
    select: root.findByProps({ 'aria-label': 'Task intent operation hint' }),
    textarea: root.findByProps({ 'aria-label': 'Committed natural-language Task intent' }),
    submit: root.findAllByType('button').find(button => button.children.some(child => child === 'Submit committed Task turn')),
  };
}

function mountedP3Status(
  binding,
  { taskId = 'task-a', attemptId = 'attempt-a', attemptNumber = 1, state = 'running', outcome = null, eventHead = 1, retryAdmission = undefined } = {},
) {
  const eligible = state === 'terminal' && attemptNumber < 3;
  return {
    ok: true,
    result: {
      task: {
        task_id: taskId,
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
      attempt: { task_id: taskId, attempt_id: attemptId, attempt_number: attemptNumber },
      retry_admission: retryAdmission ?? {
        eligible,
        reason: eligible ? 'TASK_RETRY_ELIGIBLE' : 'TASK_RETRY_PRECONDITION_STALE',
        task_id: taskId,
        attempt_id: eligible ? attemptId : null,
        attempt_number: eligible ? attemptNumber + 1 : null,
      },
    },
  };
}

function mountedP3Events(
  binding,
  { taskId = 'task-a', terminalA = false, terminalB = false, terminalC = false, terminalAOutcome = 'cancelled' } = {},
) {
  const scope = {
    subject_id: binding.subject_id,
    session_id: binding.session_id,
    project_id: binding.project_id,
    assurance: 'authenticated',
  };
  const events = [
    {
      event_id: `${taskId}:event:0`,
      task_id: taskId,
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
      event_id: `${taskId}:event:1`,
      task_id: taskId,
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
  if (terminalA || terminalB || terminalC) {
    events.push({
      event_id: `${taskId}:event:2`,
      task_id: taskId,
      attempt_id: 'attempt-a',
      scope,
      seq: 2,
      event_type: 'task.terminal',
      state: 'terminal',
      outcome: terminalAOutcome,
      producer: 'task_core.delivery',
      source_event_id: 'executor-a:2',
      causation_id: 'executor-a:2',
      correlation_id: binding.correlation_id,
      occurred_at: '2026-08-10T10:00:02Z',
      details: {},
    });
  }
  if (terminalB || terminalC) {
    events.push(
      {
        event_id: `${taskId}:event:3`,
        task_id: taskId,
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
        event_id: `${taskId}:event:4`,
        task_id: taskId,
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
        event_id: `${taskId}:event:5`,
        task_id: taskId,
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
      },
    );
  }
  if (terminalC) {
    events.push(
      {
        event_id: `${taskId}:event:6`,
        task_id: taskId,
        attempt_id: 'attempt-c',
        scope,
        seq: 6,
        event_type: 'task.retry_accepted',
        state: 'accepted',
        outcome: null,
        producer: 'task_core',
        source_event_id: null,
        causation_id: 'retry-c',
        correlation_id: binding.correlation_id,
        occurred_at: '2026-08-10T10:00:06Z',
        details: {
          attempt_number: 3,
          command_id: 'retry-c',
          previous_outcome: 'completed',
          retry_of_attempt_id: 'attempt-b',
        },
      },
      {
        event_id: `${taskId}:event:7`,
        task_id: taskId,
        attempt_id: 'attempt-c',
        scope,
        seq: 7,
        event_type: 'task.running',
        state: 'running',
        outcome: null,
        producer: 'task_core',
        source_event_id: 'executor-c:1',
        causation_id: 'executor-c:1',
        correlation_id: binding.correlation_id,
        occurred_at: '2026-08-10T10:00:07Z',
        details: {},
      },
      {
        event_id: `${taskId}:event:8`,
        task_id: taskId,
        attempt_id: 'attempt-c',
        scope,
        seq: 8,
        event_type: 'task.terminal',
        state: 'terminal',
        outcome: 'interrupted',
        producer: 'task_core.reconciliation',
        source_event_id: 'executor-c:2',
        causation_id: 'executor-c:2',
        correlation_id: binding.correlation_id,
        occurred_at: '2026-08-10T10:00:08Z',
        details: {},
      },
    );
  }
  return {
    ok: true,
    result: {
      task_id: taskId,
      after_seq: -1,
      head_seq: terminalC ? 8 : terminalB ? 5 : terminalA ? 2 : 1,
      events,
    },
  };
}

function mountedLifecycleProgress(
  binding,
  activation,
  { state, eventType, seq, outcome = null, taskId = 'task-a', attemptId = 'attempt-a' },
) {
  const scope = {
    subject_id: binding.subject_id,
    session_id: binding.session_id,
    project_id: binding.project_id,
    assurance: 'authenticated',
  };
  const sourceEventId = `${taskId}:event:${seq}`;
  return {
    event_type: 'live_voice.task.progress',
    delivery_id: `mounted-${state}-${seq}-${outcome ?? 'none'}`,
    session_id: binding.session_id,
    project_id: binding.project_id,
    task_id: taskId,
    correlation_id: binding.correlation_id,
    origin_id: activation.origin_id,
    origin_kind: 'text',
    requested_origin_kind: 'text',
    effective_origin_kind: 'text',
    delivery_mode: 'text',
    fallback_reason: null,
    generation_kind: 'web_task_progress_generation',
    generation_id: activation.generation_id,
    generation: activation.generation,
    evidence_id: `mounted-evidence-${state}-${seq}-${outcome ?? 'none'}`,
    presentation_class: 'text',
    response_ref: {
      interaction_id: `mounted-interaction-${taskId}`,
      response_id: `mounted-response-${taskId}-${seq}`,
      response_generation: activation.generation,
    },
    unit_id: `mounted-unit-${taskId}-${seq}`,
    expected_event_head: seq,
    result_source_event_id: outcome === 'completed' ? `executor-a:${seq}` : null,
    state,
    source_event: {
      contract_version: 'live-voice.contract.v2',
      event_id: sourceEventId,
      event_type: eventType,
      producer: {
        component: 'task_core',
        instance_id: 'agent_server.p3_core',
        authority: 'task_core',
      },
      seq,
      occurred_at: '2030-01-01T00:00:00Z',
      correlation_id: binding.correlation_id,
      causation_id: seq === 0 ? 'create-a' : `executor-a:${seq}`,
      stream_ref: { kind: 'task', id: taskId },
      scope,
      required_capabilities: [],
      payload: outcome === null ? { state } : { state, outcome },
      extensions: {
        'jiuwenswarm.task_progress_return': {
          consumer_scope_rebound: true,
          persistent_correlation_id: binding.correlation_id,
          persistent_event_seq: seq,
          persistent_event_type: eventType,
          persistent_event_producer: state === 'terminal' ? 'task_core.delivery' : 'task_core',
          persistent_scope: { ...scope },
          persistent_attempt_id: attemptId,
          persistent_source_event_id: seq === 0 ? null : `executor-a:${seq}`,
        },
      },
    },
    progress_event: {
      contract_version: 'live-voice.contract.v2',
      event_id: `task-progress:${sourceEventId}`,
      event_type: 'work.progress',
      producer: {
        component: 'product_p3_voice',
        instance_id: `${binding.session_id}:${activation.origin_id}:${activation.generation}`,
        authority: 'adapter',
      },
      seq,
      occurred_at: '2030-01-01T00:00:00Z',
      correlation_id: binding.correlation_id,
      causation_id: sourceEventId,
      stream_ref: { kind: 'task', id: taskId },
      scope,
      required_capabilities: [],
      payload: {
        work_ref: { kind: 'task', id: taskId },
        source: {
          authority: 'task_core',
          event_id: sourceEventId,
          source_work_ref: { kind: 'task', id: taskId },
          adapter: 'agent_server.product_p3_voice.v1',
        },
        seq,
        state,
        outcome,
        summary: { knowledge: 'unknown' },
        blocking_question: { knowledge: 'unknown' },
        artifact_refs: { knowledge: 'unknown' },
        urgency: 'unknown',
        speakability: 'not_speakable',
      },
      extensions: {
        'jiuwenswarm.task_progress_return': {
          consumer_scope_rebound: true,
          persistent_correlation_id: binding.correlation_id,
          persistent_event_seq: seq,
          persistent_scope: { ...scope },
        },
      },
    },
  };
}

function mountedTerminalProgress(binding, activation, outcome, taskId = 'task-a', attemptId = 'attempt-a', seq = 1) {
  return mountedLifecycleProgress(binding, activation, {
    state: 'terminal',
    eventType: 'task.terminal',
    seq,
    outcome,
    taskId,
    attemptId,
  });
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

function mountedAudioDeviceControls(renderer) {
  const root = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-device-selection' });
  const selects = root.findAllByType('select');
  const button = label => {
    const selected = root.findAllByType('button').find(candidate => candidate.children.some(child => child === label));
    assert.ok(selected, `audio device button ${label} must exist`);
    return selected;
  };
  const token = (select, label) => {
    const option = select.findAllByType('option').find(candidate => candidate.children.some(child => child === label));
    assert.ok(option, `audio device option ${label} must exist`);
    return option.props.value;
  };
  return { root, input: selects[0], output: selects[1], button, token };
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

function mountedDownlinkBinding(response, unitId, index, uplinkBinding) {
  return {
    lease_id: `mounted-downlink-lease-${index}`,
    authority_evidence_id: `mounted-downlink-authority-${index}`,
    connection_id: `mounted-downlink-connection-${index}`,
    connection_epoch: 0,
    session_id: uplinkBinding.session_id,
    media_session_id: `mounted-downlink-session-${index}`,
    interaction_id: response.interaction_id,
    track_id: `mounted-downlink-track-${index}`,
    correlation_id: uplinkBinding.correlation_id,
    direction: 'downlink',
    generation: {
      kind: 'response',
      id: response.response_id,
      value: response.response_generation,
    },
    frame_format: {
      sample_rate_hz: 48_000,
      samples_per_channel: 960,
      encoding: 'pcm_f32',
      byte_order: 'little',
      channel_count: 1,
      frame_duration_ms: 20,
    },
    playout: {
      response_id: response.response_id,
      response_generation: response.response_generation,
      unit_id: unitId,
    },
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

function mountedWavBase64(sampleRate = 48_000, sampleCount = 960) {
  const bytes = new Uint8Array(44 + sampleCount * 2);
  const view = new DataView(bytes.buffer);
  const ascii = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  };
  ascii(0, 'RIFF');
  view.setUint32(4, bytes.length - 8, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, 'data');
  view.setUint32(40, sampleCount * 2, true);
  return Buffer.from(bytes).toString('base64');
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

async function waitForMountedDefault(predicate, message, timeoutMs = 2_000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) assert.fail(message);
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}

const waitForMounted = (predicate, message, timeoutMs = 2_000) =>
  waitForMountedDefault(predicate, message, timeoutMs);

test('mounted placeholder new Session never allocates or retries Product voice authority', async () => {
  const i18n = await createI18n();
  const calls = [];
  const states = [];
  let renderer;
  assert.equal(hasDurableProductVoiceSession('new'), false);
  assert.equal(hasDurableProductVoiceSession('  '), false);
  assert.equal(hasDurableProductVoiceSession('web-durable-session'), true);
  const request = async (method, params) => {
    calls.push({ method, params });
    throw new Error(`placeholder Session must not call ${method}`);
  };
  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, 'new', request, true, {
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await new Promise(resolve => setTimeout(resolve, 30));
    });
    assert.deepEqual(calls, []);
    assert.equal(states.at(-1)?.available, false);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted Live Voice bar exposes Agent and formal Task commands without a raw-ASR confirmation card', async () => {
  const i18n = await createI18n();
  const routeChanges = [];
  const operationChanges = [];
  const taskIdChanges = [];
  let abandoned = 0;
  let renderer;
  const renderBar = (route, taskAvailable = true) =>
    React.createElement(
      I18nextProvider,
      { i18n },
      React.createElement(MountedLiveVoiceDemoBar, {
        active: true,
        available: true,
        status: 'idle',
        interimTranscript: '',
        committedTranscript: 'Create the demo task',
        editableTranscript: 'Create the demo task',
        onTranscriptChange() {},
        onEnable() {},
        onExit() {},
        onPrimaryAction() {},
        commandCenter: {
          route,
          taskAvailable,
          taskOperation: 'task.cancel',
          taskId: 'task-command-center-1',
          taskStatus: 'clarification',
          taskConfirmationForm: route === 'task' ? 'confirm task request cccccccccccccccccccccccccccccccc' : null,
          taskProgressTaskId: 'task-command-center-1',
          taskProgressState: 'running',
          taskProgressDeliveryMode: 'text_fallback',
          onRouteChange: value => routeChanges.push(value),
          onTaskOperationChange: value => operationChanges.push(value),
          onTaskIdChange: value => taskIdChanges.push(value),
          onCancelTaskConfirmation: () => {
            abandoned += 1;
          },
        },
      }),
    );
  try {
    await act(async () => {
      renderer = create(renderBar('agent', false));
    });
    const center = renderer.root.findByProps({ 'data-testid': 'live-voice-command-center' });
    assert.equal(center.findAllByProps({ 'data-testid': 'live-voice-task-command' }).length, 0);
    assert.equal(renderer.root.findAllByProps({ 'data-testid': 'live-voice-product-confirmation' }).length, 0);
    const taskRouteButton = center.findAllByType('button').find(button => button.children.includes('Task'));
    assert.equal(taskRouteButton.props.disabled, true, 'flag-off Task route must be unavailable');
    await act(async () => renderer.update(renderBar('agent')));
    const enabledTaskRouteButton = renderer.root
      .findByProps({ 'data-testid': 'live-voice-command-center' })
      .findAllByType('button')
      .find(button => button.children.includes('Task'));
    await act(async () => enabledTaskRouteButton.props.onClick());
    assert.deepEqual(routeChanges, ['task']);

    await act(async () => renderer.update(renderBar('task')));
    const taskCommand = renderer.root.findByProps({ 'data-testid': 'live-voice-task-command' });
    taskCommand.findByType('select').props.onChange({ target: { value: 'task.status' } });
    taskCommand.findByType('input').props.onChange({ target: { value: 'task-command-center-2' } });
    assert.deepEqual(operationChanges, ['task.status']);
    assert.deepEqual(taskIdChanges, ['task-command-center-2']);
    assert.equal(renderer.root.findByProps({ 'data-testid': 'live-voice-command-progress' }).children.includes(' · running'), true);
    const confirmation = renderer.root.findByProps({ 'data-testid': 'live-voice-command-task-confirmation' });
    await act(async () => confirmation.findByType('button').props.onClick());
    assert.equal(abandoned, 1);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted bounded text Task route requires a later committed confirmation and activates exact origin progress', async () => {
  const i18n = await createI18n();
  const calls = [];
  const values = new Map();
  const restoreBrowser = installP2RecoveryBrowser({
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  });
  const resolutionId = 'a'.repeat(64);
  const commitSha256 = 'b'.repeat(64);
  const confirmationToken = resolutionId.slice(0, 32);
  let intentCalls = 0;
  let routeCorrelation = null;
  let progressListener = null;
  let exactProgressActivation = null;
  let renderer;
  const progressSubscribe = listener => {
    progressListener = listener;
    return () => {
      if (progressListener === listener) progressListener = null;
    };
  };
  const naturalBinding = () => ({
    subject_id: 'subject-natural',
    session_id: 'session-natural',
    project_id: 'project-natural',
    correlation_id: routeCorrelation,
    generation: 4441,
  });
  const naturalStatus = () => ({
    ok: true,
    result: {
      task: {
        task_id: 'task-natural-1',
        scope: {
          subject_id: 'subject-natural',
          session_id: 'session-natural',
          project_id: 'project-natural',
          assurance: 'authenticated',
        },
        correlation_id: routeCorrelation,
        attempt_id: 'attempt-natural-1',
        state: 'terminal',
        outcome: 'completed',
        event_head: 1,
      },
      attempt: {
        task_id: 'task-natural-1',
        attempt_id: 'attempt-natural-1',
        attempt_number: 1,
      },
      retry_admission: {
        eligible: false,
        reason: 'TASK_RETRY_PRECONDITION_STALE',
        task_id: 'task-natural-1',
        attempt_id: null,
        attempt_number: null,
      },
    },
  });
  const naturalEvents = () => {
    const scope = {
      subject_id: 'subject-natural',
      session_id: 'session-natural',
      project_id: 'project-natural',
      assurance: 'authenticated',
    };
    return {
      ok: true,
      result: {
        task_id: 'task-natural-1',
        after_seq: -1,
        head_seq: 1,
        events: [
          {
            event_id: 'task-natural-1:event:0',
            task_id: 'task-natural-1',
            attempt_id: 'attempt-natural-1',
            scope,
            seq: 0,
            event_type: 'task.accepted',
            state: 'accepted',
            outcome: null,
            producer: 'task_core',
            source_event_id: null,
            causation_id: 'create-natural-1',
            correlation_id: routeCorrelation,
            occurred_at: '2026-08-14T17:00:00Z',
            details: {},
          },
          {
            event_id: 'task-natural-1:event:1',
            task_id: 'task-natural-1',
            attempt_id: 'attempt-natural-1',
            scope,
            seq: 1,
            event_type: 'task.terminal',
            state: 'terminal',
            outcome: 'completed',
            producer: 'task_core.delivery',
            source_event_id: 'executor-natural-1',
            causation_id: 'executor-natural-1',
            correlation_id: routeCorrelation,
            occurred_at: '2026-08-14T17:00:01Z',
            details: {},
          },
        ],
      },
    };
  };
  const request = async (method, params, options) => {
    const requestId = options?.requestId ?? null;
    calls.push({ method, params: { ...params }, requestId });
    if (method === 'live_voice.composition.p2.activate') {
      routeCorrelation = params.correlation_id;
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.task.list') {
      return {
        request_id: options?.requestId ?? null,
        ok: true,
        error: null,
        result: {
          tasks: [],
          cursor: null,
          next_cursor: null,
          has_more: false,
          limit: 100,
          supported_operations: [],
        },
      };
    }
    if (method === 'live_voice.composition.p3.intent') {
      routeCorrelation = params.correlation_id;
      intentCalls += 1;
      const base = {
        resolver_provider: 'local.closed_schema',
        resolver_implementation_class: 'bounded_deterministic_alpha_v1',
        resolution_id: resolutionId,
        commit_sha256: commitSha256,
        operation: 'task.create',
        source_span: { start: 13, end: 35 },
        target_span: null,
      };
      return intentCalls === 1
        ? {
            request_id: requestId,
            ok: true,
            error: null,
            result: {
              status: 'clarification',
              reason: 'TASK_CONFIRMATION_REQUIRED',
              ...base,
              task_id: null,
              confirmation_token: confirmationToken,
              confirmation_form: `confirm task request ${confirmationToken}`,
              partial_command_count: 0,
            },
          }
        : {
            request_id: requestId,
            ok: true,
            error: null,
            result: {
              status: 'dispatched',
              reason: 'TASK_INTENT_DISPATCHED',
              ...base,
              task_id: 'task-natural-1',
              origin_kind: 'text',
              origin_id: params.interaction_id,
              task_control_binding: naturalBinding(),
              confirmation_commit_id: params.commit_id,
              formal_task_result: { task_id: 'task-natural-1', state: 'accepted' },
            },
          };
    }
    if (method === 'live_voice.task.status') return naturalStatus();
    if (method === 'live_voice.task.events') return naturalEvents();
    if (method === 'live_voice.composition.p3.progress.activate') {
      if (params.task_id === 'task-natural-1') exactProgressActivation = { ...params };
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p3.progress.ack') {
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          replayed: false,
          attempt_id: 'attempt-natural-1',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
        },
      };
    }
    throw new Error(`unexpected mounted request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'session-natural', request, undefined, true, progressSubscribe));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Bounded natural-language Task route'), 'bounded task intent route did not mount');
    });
    const first = mountedTaskIntentControls(renderer);
    assert.equal(first.submit !== undefined, true);
    await act(async () => {
      first.textarea.props.onChange({ target: { value: 'create task: inspect the repository' } });
      const structured = mountedP3Controls(renderer).root;
      structured.findByType('input').props.onChange({ target: { value: 'must stay blocked' } });
      structured.findByType('textarea').props.onChange({ target: { value: 'must not issue while natural confirmation is pending' } });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-task-intent-confirmation' }).length === 1,
        'task intent did not expose its later-turn confirmation form',
      );
    });
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({
        target: { value: `confirm task request ${confirmationToken}` },
      });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === 'task-natural-1'),
        'natural task did not activate progress on its exact created task',
      );
    });
    const intents = calls.filter(call => call.method === 'live_voice.composition.p3.intent');
    assert.equal(intents.length, 2);
    assert.equal(intents[0].params.interaction_id, intents[1].params.interaction_id);
    assert.notEqual(intents[0].params.commit_id, intents[1].params.commit_id);
    assert.equal('confirmed' in intents[0].params, false);
    assert.equal('confirmed' in intents[1].params, false);
    const progress = calls.find(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === 'task-natural-1');
    assert.equal(progress.params.origin_kind, 'text');
    assert.equal(progress.params.origin_id, intents[0].params.interaction_id);
    assert.equal(
      calls.some(call => call.method === 'live_voice.task.status' && call.params.task_id === 'task-natural-1'),
      true,
    );
    assert.equal(
      calls.some(call => call.method === 'live_voice.task.events' && call.params.task_id === 'task-natural-1'),
      true,
    );
    assert.equal(typeof progressListener, 'function');
    assert.notEqual(exactProgressActivation, null);
    const terminalProgress = mountedTerminalProgress(naturalBinding(), exactProgressActivation, 'completed', 'task-natural-1', 'attempt-natural-1');
    await act(async () => {
      progressListener(terminalProgress);
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-product-progress' }).length === 1,
        'natural task did not project its authenticated terminal progress',
      );
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p3.progress.ack'),
        'natural task terminal progress was not acknowledged',
      );
    });
    const rendered = JSON.stringify(renderer.toJSON());
    assert.equal(rendered.includes('task-natural-1'), true);
    assert.equal(rendered.includes('completed'), true);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restoreBrowser();
  }
});

test('mounted Task intent failure renders only the stable content-free reason', async () => {
  const i18n = await createI18n();
  const sentinel = 'SENTINEL_PROVIDER_SECRET_TRANSCRIPT';
  let renderer;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.task.list') {
      return {
        request_id: options?.requestId ?? null,
        ok: true,
        error: null,
        result: {
          tasks: [],
          cursor: null,
          next_cursor: null,
          has_more: false,
          limit: 100,
          supported_operations: [],
        },
      };
    }
    if (method === 'live_voice.composition.p3.intent') throw new Error(sentinel);
    throw new Error(`unexpected mounted request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'session-safe-error', request));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Bounded natural-language Task route'), 'bounded task intent route did not mount');
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({
        target: { value: 'create task: bounded request' },
      });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('FORMAL_TASK_INTENT_REQUEST_FAILED'),
        'stable content-free task intent failure was not rendered',
      );
    });
    const rendered = JSON.stringify(renderer.toJSON());
    assert.equal(rendered.includes('FORMAL_TASK_INTENT_REQUEST_FAILED'), true);
    assert.equal(rendered.includes(sentinel), false);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted definitive structured mutation failure releases the natural Task route without reload', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const calls = [];
  const activateP2 = createMountedP2ActivationResponder();
  let binding = null;
  let renderer;
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.progress.activate') {
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.task.status') return mountedP3Status(binding, { taskId: 'task-terminal' });
    if (method === 'live_voice.task.events') return mountedP3Events(binding, { taskId: 'task-terminal' });
    if (method === 'live_voice.composition.p3.confirmation.issue') {
      binding ??= {
        subject_id: 'mounted-terminal-subject',
        session_id: params.session_id,
        project_id: 'mounted-terminal-project',
        correlation_id: params.correlation_id,
        generation: 41,
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
      if (params.operation === 'task.cancel') {
        throw Object.assign(new Error('terminal task cannot be cancelled'), {
          code: 'CONFLICT',
          reason: 'TASK_ALREADY_TERMINAL',
        });
      }
      return {
        ok: true,
        result: {
          status: 'mutation_processed',
          operation: 'task.create',
          command_id: params.command_id,
          target_task_id: null,
          formal_task_result: {
            task_id: 'task-terminal',
            attempt_id: 'attempt-a',
            attempt_number: 1,
            state: 'accepted',
            outbox_id: 'outbox-terminal',
          },
        },
      };
    }
    if (method === 'live_voice.composition.p3.intent') {
      const result = {
        status: 'rejected',
        reason: 'UNSUPPORTED_TASK_INTENT',
        operation: null,
        task_id: null,
        source_span: null,
        target_span: null,
        formal_task_result: null,
      };
      const error = new Error('bounded request rejected');
      error.payload = {
        request_id: options?.requestId ?? null,
        ok: false,
        result,
        error: { code: 'INVALID_ARGUMENT', reason: result.reason, message: 'rejected' },
        product_composition: {},
      };
      throw error;
    }
    throw new Error(`unexpected mounted request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'session-terminal-recovery', request));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'formal P3 controls did not mount');
    });
    await act(async () => {
      const controls = mountedP3Controls(renderer).root;
      controls.findByType('input').props.onChange({ target: { value: 'Terminal recovery task' } });
      controls.findByType('textarea').props.onChange({ target: { value: 'Edit only the disposable fixture.' } });
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.create confirmation did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.cancel', 'task.create did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.cancel confirmation did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('TASK_ALREADY_TERMINAL'), 'definitive task.cancel failure did not settle');
    });

    const taskIntent = mountedTaskIntentControls(renderer);
    await act(async () => {
      taskIntent.textarea.props.onChange({ target: { value: 'help me with this task' } });
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(mountedTaskIntentControls(renderer).submit.props.disabled, false);
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.intent').length === 1,
        'definitive structured failure did not release the natural Task route',
      );
    });
    assert.equal(JSON.stringify(renderer.toJSON()).includes('UNSUPPORTED_TASK_INTENT'), true);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 2);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

for (const failureMode of ['malformed-inner', 'transport-unknown', 'stale-disconnect']) {
  test(`mounted ${failureMode} structured mutation failure retains the natural Task barrier`, async () => {
    const i18n = await createI18n();
    const browser = installP1BrowserEnvironment();
    const calls = [];
    const activateP2 = createMountedP2ActivationResponder();
    let binding = null;
    let releaseDeferredMutation = null;
    let renderer;
    const processedMutation = params => ({
      ok: true,
      result: {
        status: 'mutation_processed',
        operation: params.operation,
        command_id: params.command_id,
        target_task_id: null,
        formal_task_result: {
          task_id: 'task-retained',
          attempt_id: 'attempt-retained',
          attempt_number: 1,
          state: 'accepted',
          ...(failureMode === 'malformed-inner' ? {} : { outbox_id: 'outbox-retained' }),
        },
      },
    });
    const request = async (method, params, options) => {
      calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
      if (method === 'live_voice.composition.p2.activate') return activateP2(params);
      if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
      if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
      if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
      if (method === 'live_voice.composition.p3.progress.activate') {
        return { ok: true, result: mountedProgressActivation(params) };
      }
      if (method === 'live_voice.composition.p3.progress.close') {
        return { ok: true, result: { status: 'closed', ...params } };
      }
      if (method === 'live_voice.composition.p3.confirmation.issue') {
        binding ??= {
          subject_id: `mounted-${failureMode}-subject`,
          session_id: params.session_id,
          project_id: `mounted-${failureMode}-project`,
          correlation_id: params.correlation_id,
          generation: 42,
        };
        return {
          ok: true,
          result: {
            status: 'confirmation_issued',
            operation: params.operation,
            command_id: params.command_id,
            target_task_id: null,
            confirmation_id: `confirmation-${params.command_id}`,
            expires_at: '2999-08-10T10:00:00Z',
            task_control_binding: binding,
          },
        };
      }
      if (method === 'live_voice.composition.p3.mutate') {
        if (failureMode === 'transport-unknown') {
          throw Object.assign(new Error('mutation transport outcome is unknown'), {
            code: 'UNAVAILABLE',
            reason: 'PRODUCT_P3_MUTATION_OUTCOME_UNKNOWN',
            retriable: true,
          });
        }
        if (failureMode === 'stale-disconnect') {
          return new Promise(resolve => {
            releaseDeferredMutation = () => resolve(processedMutation(params));
          });
        }
        return processedMutation(params);
      }
      if (method === 'live_voice.composition.p3.intent') {
        throw new Error('natural Task intent must remain fenced');
      }
      throw new Error(`unexpected mounted retained-barrier request: ${method}`);
    };
    const sessionId = `session-${failureMode}`;

    try {
      await act(async () => {
        renderer = create(mountedP3Element(i18n, sessionId, request));
        await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'formal P3 controls did not mount');
      });
      await act(async () => {
        const controls = mountedP3Controls(renderer).root;
        controls.findByType('input').props.onChange({ target: { value: `Retained ${failureMode} task` } });
        controls.findByType('textarea').props.onChange({ target: { value: 'Edit only the disposable fixture.' } });
      });
      await act(async () => {
        mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
        await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.create confirmation did not settle');
      });
      if (failureMode === 'stale-disconnect') {
        await act(async () => {
          mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
          await waitForMounted(() => releaseDeferredMutation !== null, 'stale mutation did not reach the deferred transport');
        });
        await act(async () => {
          renderer.update(mountedP3Element(i18n, sessionId, request, undefined, false));
          await new Promise(resolve => setImmediate(resolve));
        });
        await act(async () => {
          releaseDeferredMutation();
          await new Promise(resolve => setTimeout(resolve, 20));
        });
        await act(async () => {
          renderer.update(mountedP3Element(i18n, sessionId, request));
          await waitForMounted(
            () =>
              JSON.stringify(renderer.toJSON()).includes('PRODUCT_P3_MUTATION_FAILED') && mountedTaskIntentControls(renderer).textarea.props.disabled === true,
            'reconnect released the stale mutation barrier',
          );
        });
      } else {
        await act(async () => {
          mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
          await waitForMounted(
            () =>
              JSON.stringify(renderer.toJSON()).includes(
                failureMode === 'transport-unknown' ? 'PRODUCT_P3_MUTATION_OUTCOME_UNKNOWN' : 'PRODUCT_P3_MUTATION_FAILED',
              ),
            `${failureMode} mutation did not fail closed`,
          );
        });
      }

      const taskIntent = mountedTaskIntentControls(renderer);
      assert.equal(taskIntent.textarea.props.disabled, true, `${failureMode} must retain the visible natural Task barrier`);
      const intentCallsBefore = calls.filter(call => call.method === 'live_voice.composition.p3.intent').length;
      await act(async () => {
        taskIntent.root.props.onSubmit({ preventDefault() {} });
        await new Promise(resolve => setImmediate(resolve));
      });
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p3.intent').length,
        intentCallsBefore,
        `${failureMode} must allocate zero natural Task intent effects`,
      );
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 1);
    } finally {
      if (renderer) await act(async () => renderer.unmount());
      browser.restore();
    }
  });
}

test('mounted natural Task create rejects a same-Session foreign project and correlation before progress or acknowledgement', async () => {
  const i18n = await createI18n();
  const calls = [];
  const resolutionId = 'e'.repeat(64);
  const commitSha256 = 'f'.repeat(64);
  const confirmationToken = resolutionId.slice(0, 32);
  let intentCalls = 0;
  let routeCorrelation = null;
  let renderer;
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      routeCorrelation = params.correlation_id;
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.intent') {
      routeCorrelation = params.correlation_id;
      intentCalls += 1;
      const base = {
        resolver_provider: 'local.closed_schema',
        resolver_implementation_class: 'bounded_deterministic_alpha_v1',
        resolution_id: resolutionId,
        commit_sha256: commitSha256,
        operation: 'task.create',
        source_span: { start: 13, end: 35 },
        target_span: null,
      };
      return intentCalls === 1
        ? {
            request_id: options?.requestId ?? null,
            ok: true,
            error: null,
            result: {
              status: 'clarification',
              reason: 'TASK_CONFIRMATION_REQUIRED',
              ...base,
              task_id: null,
              confirmation_token: confirmationToken,
              confirmation_form: `confirm task request ${confirmationToken}`,
              partial_command_count: 0,
            },
          }
        : {
            request_id: options?.requestId ?? null,
            ok: true,
            error: null,
            result: {
              status: 'dispatched',
              reason: 'TASK_INTENT_DISPATCHED',
              ...base,
              task_id: 'task-natural-foreign',
              origin_kind: 'text',
              origin_id: params.interaction_id,
              task_control_binding: {
                subject_id: 'subject-natural-expected',
                session_id: 'session-natural-foreign',
                project_id: 'project-natural-expected',
                correlation_id: routeCorrelation,
                generation: 17,
              },
              confirmation_commit_id: params.commit_id,
              formal_task_result: { task_id: 'task-natural-foreign', state: 'accepted' },
            },
          };
    }
    if (method === 'live_voice.task.status') {
      return {
        ok: true,
        result: {
          task: {
            task_id: 'task-natural-foreign',
            scope: {
              subject_id: 'foreign-subject',
              session_id: 'session-natural-foreign',
              project_id: 'foreign-project',
              assurance: 'authenticated',
            },
            correlation_id: 'foreign-correlation',
            attempt_id: 'attempt-natural-foreign',
            state: 'accepted',
            outcome: null,
            event_head: 0,
          },
          attempt: {
            task_id: 'task-natural-foreign',
            attempt_id: 'attempt-natural-foreign',
            attempt_number: 1,
          },
          retry_admission: {
            eligible: false,
            reason: 'TASK_RETRY_PRECONDITION_STALE',
            task_id: 'task-natural-foreign',
            attempt_id: null,
            attempt_number: null,
          },
        },
      };
    }
    throw new Error(`foreign status must block before ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, 'session-natural-foreign', request));
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('Bounded natural-language Task route'),
        'bounded foreign-status route did not mount',
      );
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({ target: { value: 'create task: inspect the repository' } });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-task-intent-confirmation' }).length === 1,
        'foreign-status natural task did not expose its confirmation turn',
      );
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({
        target: { value: `confirm task request ${confirmationToken}` },
      });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.task.status'),
        `foreign natural task did not request authoritative status: ${JSON.stringify(calls)}`,
      );
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.task.status').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length, 0);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted second natural create preserves the old exact leaf until the new status and events handoff succeeds', async () => {
  const i18n = await createI18n();
  const sessionId = 'session-natural-replacement';
  const oldBinding = {
    subject_id: 'subject-old-task',
    session_id: sessionId,
    project_id: 'project-old-task',
    correlation_id: 'correlation-old-task',
    generation: 1,
  };
  const values = new Map();
  values.set(
    `jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`,
    JSON.stringify({
      contract_version: 'live-voice.product-p3-task-target.v1',
      session_id: sessionId,
      correlation_id: oldBinding.correlation_id,
      task_id: 'task-a',
      task_control_binding: oldBinding,
    }),
  );
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  const restore = installP2RecoveryBrowser(storage);
  const calls = [];
  const resolutionId = '9'.repeat(64);
  const commitSha256 = '8'.repeat(64);
  const confirmationToken = resolutionId.slice(0, 32);
  let intentCalls = 0;
  let routeCorrelation = null;
  let renderer;
  const newTaskStatus = () => ({
    ok: true,
    result: {
      task: {
        task_id: 'task-natural-second',
        scope: {
          subject_id: 'subject-new-task',
          session_id: sessionId,
          project_id: 'project-new-task',
          assurance: 'authenticated',
        },
        correlation_id: routeCorrelation,
        attempt_id: 'attempt-natural-second',
        state: 'accepted',
        outcome: null,
        event_head: 0,
      },
      attempt: {
        task_id: 'task-natural-second',
        attempt_id: 'attempt-natural-second',
        attempt_number: 1,
      },
      retry_admission: {
        eligible: false,
        reason: 'TASK_RETRY_PRECONDITION_STALE',
        task_id: 'task-natural-second',
        attempt_id: null,
        attempt_number: null,
      },
    },
  });
  const request = async (method, params, options) => {
    const requestId = options?.requestId ?? null;
    calls.push({ method, params: { ...params }, requestId });
    if (method === 'live_voice.composition.p2.activate') {
      routeCorrelation = params.correlation_id;
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.task.status') {
      return params.task_id === 'task-a' ? mountedP3Status(oldBinding) : newTaskStatus();
    }
    if (method === 'live_voice.task.events') {
      if (params.task_id === 'task-a') return mountedP3Events(oldBinding);
      throw new Error('new task events are temporarily unavailable');
    }
    if (method === 'live_voice.composition.p3.progress.activate') {
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p3.intent') {
      routeCorrelation = params.correlation_id;
      intentCalls += 1;
      const base = {
        resolver_provider: 'local.closed_schema',
        resolver_implementation_class: 'bounded_deterministic_alpha_v1',
        resolution_id: resolutionId,
        commit_sha256: commitSha256,
        operation: 'task.create',
        source_span: { start: 13, end: 35 },
        target_span: null,
      };
      return intentCalls === 1
        ? {
            request_id: requestId,
            ok: true,
            error: null,
            result: {
              status: 'clarification',
              reason: 'TASK_CONFIRMATION_REQUIRED',
              ...base,
              task_id: null,
              confirmation_token: confirmationToken,
              confirmation_form: `confirm task request ${confirmationToken}`,
              partial_command_count: 0,
            },
          }
        : {
            request_id: requestId,
            ok: true,
            error: null,
            result: {
              status: 'dispatched',
              reason: 'TASK_INTENT_DISPATCHED',
              ...base,
              task_id: 'task-natural-second',
              origin_kind: 'text',
              origin_id: params.interaction_id,
              task_control_binding: {
                subject_id: 'subject-new-task',
                session_id: sessionId,
                project_id: 'project-new-task',
                correlation_id: routeCorrelation,
                generation: 23,
              },
              confirmation_commit_id: params.commit_id,
              formal_task_result: { task_id: 'task-natural-second', state: 'accepted' },
            },
          };
    }
    throw new Error(`unexpected replacement request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === 'task-a'),
        'old exact task progress route did not recover before the replacement create',
      );
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({ target: { value: 'create task: inspect the repository' } });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-task-intent-confirmation' }).length === 1,
        'replacement natural task did not expose confirmation',
      );
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({
        target: { value: `confirm task request ${confirmationToken}` },
      });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.task.events' && call.params.task_id === 'task-natural-second'),
        'replacement natural task did not reach its events handoff',
      );
    });
    assert.equal(intentCalls, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === 'task-a').length, 1);
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === 'task-natural-second').length,
      0,
    );
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.progress.close' && call.params.task_id === 'task-a').length,
      0,
      'failed replacement handoff must not close the old exact progress route',
    );
    assert.equal(values.get('jiuwenswarm.liveVoice.formalTaskIntentRecovery.v2').includes('post_create_binding'), true);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
});

test('mounted Task intent response loss reconnects by content-free status with one side effect', async () => {
  const i18n = await createI18n();
  const values = new Map();
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  const restore = installP2RecoveryBrowser(storage);
  const sessionId = 'session-natural-recovery';
  const formalJournalKey = 'jiuwenswarm.liveVoice.formalTaskIntentRecovery.v2';
  const instructionCanary = 'SENTINEL_PRIVATE_TASK_INSTRUCTION';
  const calls = [];
  let completedIntent = null;
  let taskSideEffects = 0;
  let taskEventsAttempts = 0;
  let routeCorrelation = null;
  let renderer;
  const resolutionId = 'c'.repeat(64);
  const commitSha256 = 'd'.repeat(64);
  const request = async (method, params, options) => {
    const requestId = options?.requestId ?? null;
    calls.push({ method, params: { ...params }, requestId });
    if (method === 'live_voice.composition.p2.activate') {
      routeCorrelation = params.correlation_id;
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.intent') {
      taskSideEffects += 1;
      completedIntent = { params: { ...params }, requestId };
      throw new Error('response lost after server completion');
    }
    if (method === 'live_voice.composition.p3.intent.status') {
      assert.notEqual(completedIntent, null);
      assert.deepEqual(Object.keys(params).sort(), ['correlation_id', 'intent_request_id', 'session_id']);
      assert.equal(params.intent_request_id, completedIntent.requestId);
      return {
        request_id: requestId,
        ok: true,
        error: null,
        result: {
          status: 'settled',
          phase: 'final',
          intent_request_id: completedIntent.requestId,
          source: 'text',
          intent: {
            status: 'dispatched',
            reason: 'TASK_INTENT_DISPATCHED',
            resolver_provider: 'local.closed_schema',
            resolver_implementation_class: 'bounded_deterministic_alpha_v1',
            resolution_id: resolutionId,
            commit_sha256: commitSha256,
            operation: 'task.create',
            task_id: 'task-natural-recovered',
            source_span: { start: 13, end: 35 },
            target_span: null,
            confirmation_token: null,
            confirmation_form: null,
            partial_command_count: 0,
            origin_kind: 'text',
            origin_id: completedIntent.params.interaction_id,
            task_control_binding: {
              subject_id: 'subject-natural-recovered',
              session_id: sessionId,
              project_id: 'project-natural-recovered',
              correlation_id: routeCorrelation,
              generation: 29,
            },
            formal_task_result: { recovered: true, task_id: 'task-natural-recovered' },
          },
        },
      };
    }
    if (method === 'live_voice.task.status') {
      return {
        ok: true,
        result: {
          task: {
            task_id: 'task-natural-recovered',
            scope: {
              subject_id: 'subject-natural-recovered',
              session_id: sessionId,
              project_id: 'project-natural-recovered',
              assurance: 'authenticated',
            },
            correlation_id: routeCorrelation,
            attempt_id: 'attempt-natural-recovered',
            state: 'terminal',
            outcome: 'completed',
            event_head: 1,
          },
          attempt: {
            task_id: 'task-natural-recovered',
            attempt_id: 'attempt-natural-recovered',
            attempt_number: 1,
          },
          retry_admission: {
            eligible: false,
            reason: 'TASK_RETRY_PRECONDITION_STALE',
            task_id: 'task-natural-recovered',
            attempt_id: null,
            attempt_number: null,
          },
        },
      };
    }
    if (method === 'live_voice.task.events') {
      taskEventsAttempts += 1;
      if (taskEventsAttempts === 1) throw new Error('task events temporarily unavailable after create receipt');
      const scope = {
        subject_id: 'subject-natural-recovered',
        session_id: sessionId,
        project_id: 'project-natural-recovered',
        assurance: 'authenticated',
      };
      return {
        ok: true,
        result: {
          task_id: 'task-natural-recovered',
          after_seq: -1,
          head_seq: 1,
          events: [
            {
              event_id: 'task-natural-recovered:event:0',
              task_id: 'task-natural-recovered',
              attempt_id: 'attempt-natural-recovered',
              scope,
              seq: 0,
              event_type: 'task.accepted',
              state: 'accepted',
              outcome: null,
              producer: 'task_core',
              source_event_id: null,
              causation_id: 'create-natural-recovered',
              correlation_id: routeCorrelation,
              occurred_at: '2026-08-14T17:30:00Z',
              details: {},
            },
            {
              event_id: 'task-natural-recovered:event:1',
              task_id: 'task-natural-recovered',
              attempt_id: 'attempt-natural-recovered',
              scope,
              seq: 1,
              event_type: 'task.terminal',
              state: 'terminal',
              outcome: 'completed',
              producer: 'task_core.delivery',
              source_event_id: 'executor-natural-recovered',
              causation_id: 'executor-natural-recovered',
              correlation_id: routeCorrelation,
              occurred_at: '2026-08-14T17:30:01Z',
              details: {},
            },
          ],
        },
      };
    }
    if (method === 'live_voice.composition.p3.progress.activate') {
      return {
        ok: true,
        result: {
          status: 'active',
          ...params,
          requested_origin_kind: params.origin_kind,
          origin_kind: 'text',
          voice_progress: 'unavailable',
          voice_reason: 'TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE',
          fallback_reason: null,
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    throw new Error(`unexpected mounted recovery request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('Bounded natural-language Task route'),
        'bounded recovery task intent route did not mount',
      );
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).textarea.props.onChange({
        target: { value: `create task: ${instructionCanary}` },
      });
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('FORMAL_TASK_INTENT_REQUEST_FAILED'),
        'response loss did not retain the recoverable task status',
      );
    });
    assert.equal(taskSideEffects, 1);
    assert.equal(values.get(formalJournalKey).includes(instructionCanary), false);

    await act(async () => {
      renderer.update(mountedP3Element(i18n, sessionId, request, undefined, false));
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      renderer.update(mountedP3Element(i18n, sessionId, request, undefined, true));
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.task.events'),
        'content-free recovered task did not reach the post-create events handoff',
      );
    });
    assert.equal(taskSideEffects, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length, 0);
    assert.equal(values.has(formalJournalKey), true, 'failed events handoff must retain the post-create checkpoint');
    assert.equal(
      mountedP3Controls(renderer).button('Issue confirmation').props.disabled,
      true,
      'structured mutation must stay locked while post-create Task authority is unresolved',
    );
    // Model a reload in the narrow window after the exact Task target was
    // persisted but before progress activation cleared the post-create CAS.
    // The generic historical-target recovery must yield to the richer
    // post-create checkpoint so only one origin-bound progress owner starts.
    const recoveredTaskBinding = {
      subject_id: 'subject-natural-recovered',
      session_id: sessionId,
      project_id: 'project-natural-recovered',
      correlation_id: routeCorrelation,
      generation: 29,
    };
    values.set(
      `jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`,
      JSON.stringify({
        contract_version: 'live-voice.product-p3-task-target.v1',
        session_id: sessionId,
        correlation_id: routeCorrelation,
        task_id: 'task-natural-recovered',
        task_control_binding: recoveredTaskBinding,
      }),
    );

    await act(async () => {
      renderer.update(mountedP3Element(i18n, sessionId, request, undefined, false));
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      renderer.update(mountedP3Element(i18n, sessionId, request, undefined, true));
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === 'task-natural-recovered'),
        'content-free recovered task did not reactivate its exact progress route',
      );
    });

    assert.equal(taskSideEffects, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.intent').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.intent.status').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.status').length, 4);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 2);
    const progressActivations = calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate');
    assert.equal(progressActivations.length, 1);
    assert.equal(progressActivations[0].params.origin_kind, 'text');
    assert.equal(progressActivations[0].params.origin_id, completedIntent.params.interaction_id);
    assert.equal(values.has(formalJournalKey), false);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
});

test('mounted predecessor submit cannot wake a same-Session successor notification lane', async () => {
  const i18n = await createI18n();
  const calls = [];
  const p2Activations = [];
  let activeMediaBinding = null;
  let rejectFirstNotification = null;
  let releasePredecessorSubmit = null;
  let successorNotificationCalls = 0;
  let renderer;
  const controlRef = { current: null };
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      p2Activations.push({ ...params });
      return activateP2(params);
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
      successorNotificationCalls += 1;
      return new Promise(() => {});
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(params, 1);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'mounted-rollover-media-subject',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'S'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'fallback',
          requested_capability: 'media.end_of_turn.v1',
          reason_id: 'MEDIA_END_OF_TURN_FEATURE_OFF',
          fallback: 'manual',
          visible: true,
        },
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
    if (method === 'live_voice.composition.unified.submit') {
      return new Promise(resolve => {
        releasePredecessorSubmit = () => resolve({
          request_id: options.requestId,
          ok: true,
          result: {
            status: 'round_accepted',
            session_id: params.session_id,
            correlation_id: params.correlation_id,
            interaction_id: params.interaction_id,
            activation_id: params.activation_id,
            activation_generation: params.activation_generation,
            turn_id: params.turn_id,
            commit_id: params.commit_id,
            request_id: `mounted-rollover-agent-${params.voice_claim_id}`,
            round_id: `mounted-rollover-round-${params.voice_claim_id}`,
            response: {
              interaction_id: params.interaction_id,
              response_id: `mounted-rollover-response-${params.voice_claim_id}`,
              response_generation: 0,
            },
          },
          error: null,
        });
      });
    }
    throw new Error(`forbidden rollover business effect: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(
          i18n,
          'mounted-rollover-session',
          request,
          true,
          { productVoiceControlRef: controlRef },
        ),
      );
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Start formal voice turn'), 'rollover panel did not mount');
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'rollover panel did not activate P2');
      void controlRef.current.start();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('starting'), 'rollover capture did not enter readiness');
      await browser.emitFirstFrame();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('capturing'), 'rollover capture did not start');
    });
    await act(async () => {
      void controlRef.current.stop();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 1,
        'rollover recognition was not auto-submitted',
      );
      for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(typeof rejectFirstNotification, 'function');
    assert.equal(p2Activations.length, 2, 'explicit media start must revalidate the exact active P2 binding');
    assert.deepEqual(p2Activations[1], p2Activations[0]);
    const firstBinding = p2Activations[0];
    await act(async () => {
      rejectFirstNotification();
      await waitForMounted(() => p2Activations.length >= 3, 'closed notification did not activate one exact P2 successor');
    });
    assert.equal(p2Activations[2].session_id, firstBinding.session_id);
    assert.equal(p2Activations[2].activation_generation, firstBinding.activation_generation + 1);
    assert.notEqual(p2Activations[2].activation_id, firstBinding.activation_id);
    assert.equal(
      p2Activations.slice(2).every(binding => JSON.stringify(binding) === JSON.stringify(p2Activations[2])),
      true,
      'post-successor media revalidation must replay only the exact successor binding',
    );
    const unified = calls.find(call => call.method === 'live_voice.composition.unified.submit');
    assert.equal(unified.params.activation_id, firstBinding.activation_id);
    assert.equal(unified.params.activation_generation, firstBinding.activation_generation);
    assert.equal(unified.params.text, 'Mounted stale activation speech');
    assert.equal(typeof releasePredecessorSubmit, 'function', 'predecessor unified submit was not retained for the turnover fence');
    await act(async () => {
      releasePredecessorSubmit();
      await new Promise(resolve => setImmediate(resolve));
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(
      successorNotificationCalls,
      0,
      'a settled predecessor submit must not wake successor notification.next under its old foreground fence',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 0);
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
        }),
      ),
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
        }),
      ),
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
    const productStates = [];
    let binding = null;
    let p2Binding = null;
    let publishP2Notification = null;
    let exactProgressActivation = null;
    let progressListener = null;
    let mutationCount = 0;
    let progressAckTransportFailuresRemaining = outcome === 'completed' ? 1 : 0;
    let taskEventsTransportFailuresRemaining = outcome === 'failed' ? 4 : 0;
    let taskEventsIncludeTerminal = outcome !== 'completed';
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
          occurred_at: '2026-08-11T08:00:00Z',
          details: {},
        },
      ];
      if (taskEventsIncludeTerminal) {
        events.push({
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
        });
      }
      return {
        ok: true,
        result: {
          task_id: 'task-a',
          after_seq: -1,
          head_seq: taskEventsIncludeTerminal ? 1 : 0,
          events,
        },
      };
    };
    const request = async (method, params, options) => {
      calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
      if (method === 'live_voice.composition.p2.activate') {
        p2Binding = { ...params };
        return { ok: true, result: { status: 'active', ...params, replayed: false } };
      }
      if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
      if (method === 'live_voice.composition.p2.notification.next') {
        return new Promise(resolve => {
          publishP2Notification = resolve;
        });
      }
      if (method === 'live_voice.composition.p2.presentation.ack') {
        return {
          ok: true,
          result: {
            status: 'presentation_acknowledged',
            ...params,
            accepted: true,
            replayed: false,
            history_records_written: 1,
            history_pending: false,
          },
        };
      }
      if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
      if (method === 'live_voice.composition.p3.progress.activate') {
        exactProgressActivation = { ...params };
        return { ok: true, result: mountedProgressActivation(params) };
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
      if (method === 'live_voice.task.events') {
        if (taskEventsTransportFailuresRemaining > 0) {
          taskEventsTransportFailuresRemaining -= 1;
          throw Object.assign(new Error('mounted task.events transport timeout'), { reason: 'REQUEST_TIMEOUT' });
        }
        return taskEvents();
      }
      if (method === 'live_voice.composition.p3.progress.ack') {
        if (progressAckTransportFailuresRemaining > 0) {
          progressAckTransportFailuresRemaining -= 1;
          throw Object.assign(new Error('mounted progress ACK transport unavailable'), { reason: 'REQUEST_TIMEOUT' });
        }
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
        renderer = create(
          mountedP3Element(i18n, `mounted-terminal-${outcome}`, request, undefined, true, progressSubscribe, {
            onProductVoiceStateChange: state => productStates.push(state),
            progressAckCapacity: outcome === 'completed' ? 1 : undefined,
          }),
        );
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
          'terminal-progress task.create confirmation did not settle',
        );
      });
      await act(async () => {
        mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
        await waitForMounted(
          () => exactProgressActivation !== null && mountedP3Controls(renderer).select.props.value === 'task.cancel',
          'terminal-progress task.create did not bind its exact progress route',
        );
        await waitForMounted(
          () =>
            renderer.root
              .findByProps({ 'data-testid': 'live-voice-integrated-p3-activation' })
              .findAllByType('code')
              .some(node => node.children.some(child => child === 'p3:active')),
          'terminal-progress exact route did not become active',
        );
      });
      assert.equal(typeof progressListener, 'function');
      if (outcome === 'completed') {
        const acceptedProgress = mountedLifecycleProgress(binding, exactProgressActivation, {
          state: 'accepted',
          eventType: 'task.accepted',
          seq: 0,
        });
        for (const field of [
          'presentation_class',
          'response_ref',
          'unit_id',
          'expected_event_head',
          'result_source_event_id',
          'state',
        ]) {
          delete acceptedProgress[field];
        }
        const parsedLegacyAccepted = parseProductTextProgressEvent(acceptedProgress);
        assert.notEqual(parsedLegacyAccepted, null);
        assert.equal(parsedLegacyAccepted.consumption_mode, 'legacy_delivery');
        await act(async () => {
          progressListener(acceptedProgress);
          await waitForMounted(
            () => renderer.root.findAllByType('code').some(node => node.children.some(child => child === acceptedProgress.delivery_id)),
            'mounted origin panel did not publish the retained accepted delivery',
          );
          await waitForMounted(
            () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length === 1,
            'mounted origin panel did not attempt the accepted delivery ACK',
          );
        });
        const legacyAck = calls.find(call => call.method === 'live_voice.composition.p3.progress.ack');
        assert.ok(legacyAck);
        const legacyNode = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-product-progress' });
        assert.equal(legacyNode.props['data-delivery-id'], acceptedProgress.delivery_id);
        for (const attribute of [
          'data-presentation-binding',
          'data-presentation-class',
          'data-response-interaction-id',
          'data-response-id',
          'data-response-generation',
          'data-unit-id',
          'data-expected-event-head',
          'data-result-source-event-id',
        ]) {
          assert.equal(legacyNode.props[attribute], undefined, `feature-off legacy DOM retained ${attribute}`);
        }
        for (const forbidden of [
          'presentation_class',
          'response_ref',
          'unit_id',
          'expected_event_head',
          'result_source_event_id',
          'presentation_binding',
        ]) {
          assert.equal(forbidden in legacyAck.params, false, `feature-off legacy ACK acquired ${forbidden}`);
        }
      }
      const terminalProgress = mountedTerminalProgress(binding, exactProgressActivation, outcome);
      taskEventsIncludeTerminal = true;
      const parsedTerminalProgress = parseProductTextProgressEvent(terminalProgress);
      assert.notEqual(parsedTerminalProgress, null);
      assert.equal(progressMatchesOwnedBinding(parsedTerminalProgress, exactProgressActivation, binding.session_id), true);
      await act(async () => {
        progressListener(terminalProgress);
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.task.events'),
          `mounted origin panel did not reconcile ${outcome}: ${calls.map(call => call.method).join(',')}`,
        );
        if (outcome === 'completed') {
          await waitForMounted(
            () => calls.filter(call => call.method === 'live_voice.task.events').length === 2,
            'mounted origin panel did not reconcile the terminal delivery before ACK retention capacity recovery',
          );
          assert.equal(
            renderer.root.findAllByType('code').some(node => node.children.some(child => child === terminalProgress.delivery_id)),
            true,
            'actual DOM adoption remains truthful when ACK retention fails; durable unread must replay it',
          );
        }
        if (outcome === 'failed') {
          await waitForMounted(
            () => calls.filter(call => call.method === 'live_voice.task.events').length === 4,
            'transient task.events failures did not stop after the bounded reconciliation attempts',
            3_000,
          );
          assert.equal(
            renderer.root.findAllByType('code').some(node => node.children.some(child => child === terminalProgress.delivery_id)),
            false,
            'transient task.events exhaustion must not publish unverified progress',
          );
          progressListener(terminalProgress);
          await waitForMounted(
            () => calls.filter(call => call.method === 'live_voice.task.events').length === 5,
            'server replay of a transiently exhausted delivery was quarantined',
          );
        }
        await waitForMounted(
          () => renderer.root.findAllByType('code').some(node => node.children.some(child => child === outcome)),
          `mounted origin panel did not render ${outcome}`,
        );
        await waitForMounted(() => calls.some(call => call.method === 'live_voice.composition.p3.progress.ack'), `mounted origin panel did not ACK ${outcome}`);
      });
      assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, outcome === 'completed' ? 2 : 5);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length, 1);

      const terminalText = `Mounted ${outcome} notification for task-a.`;
      assert.notEqual(p2Binding, null);
      assert.equal(typeof publishP2Notification, 'function');
      await act(async () => {
        publishP2Notification({
          ok: true,
          result: {
            status: 'notification',
            ...p2Binding,
            kind: 'agent.output',
            response: {
              interaction_id: p2Binding.interaction_id,
              response_id: `mounted-terminal-notification-${outcome}`,
              response_generation: 1,
            },
            agent_event: {
              event_type: 'chat.final',
              text: terminalText,
              source_provenance: 'server.task_notification',
            },
            presentation_unit: { surface: 'text', unit_id: `mounted-terminal-unit-${outcome}`, seq: 0 },
          },
        });
        await waitForMounted(
          () => productStates.at(-1)?.terminal_notification === terminalText,
          'the terminal notification was not associated with task-a',
        );
      });

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
          'second task.create did not bind its exact progress route',
        );
      });
      assert.equal(
        renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-product-progress' }).length,
        0,
        'a successor task must clear the predecessor progress projection before replay arrives',
      );
      assert.equal(
        productStates.at(-1)?.terminal_notification,
        null,
        'a successor task must clear the predecessor terminal notification before capture can resume',
      );
      await act(async () => {
        progressListener(terminalProgress);
        await Promise.resolve();
      });
      assert.equal(
        renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-product-progress' }).length,
        0,
        'a late predecessor event must not repopulate the successor task projection',
      );
      assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, outcome === 'completed' ? 2 : 5);
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

test('mounted Task AUDIO failure retry clears its transient recovery error after exact TEXT fallback acceptance', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-task-audio-owner-unavailable-session';
  const calls = [];
  const states = [];
  let binding = null;
  let delivered = false;
  let presentationFailureAttempts = 0;
  let renderer;
  const browser = installP1BrowserEnvironment();
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      binding = { ...params };
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: { status: 'closed', ...params },
      };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      if (delivered) return new Promise(() => {});
      delivered = true;
      return {
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-audio-owner-unavailable-response',
            response_generation: 3,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The background task is running.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-task-audio-owner-unavailable-unit',
            seq: 0,
            content_ref: `sha256:${'e'.repeat(64)}`,
          },
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      presentationFailureAttempts += 1;
      if (presentationFailureAttempts === 1) {
        throw Object.assign(new Error('transient mounted Task fallback transport failure'), {
          code: 'UNAVAILABLE',
          reason: 'PRODUCT_TASK_AUDIO_FALLBACK_RECOVERY_REQUIRED',
          retriable: true,
        });
      }
      return {
        ok: true,
        result: {
          status: 'presentation_failed_fallback_text',
          ...params,
          fallback: 'text',
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    throw new Error(`unexpected Task AUDIO owner-unavailable request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedP3Element(i18n, sessionId, request, undefined, true, undefined, {
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 2,
        'Task AUDIO without P1 did not retry its exact failure',
      );
      await waitForMounted(
        () => states.at(-1)?.terminal_announcement_state === 'idle',
        'accepted Task TEXT fallback did not settle the terminal announcement owner',
      );
    });

    const failures = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed');
    assert.equal(failures.length, 2);
    assert.equal(failures[0].params.response_id, 'mounted-task-audio-owner-unavailable-response');
    assert.equal(failures[0].params.response_generation, 3);
    assert.equal(failures[0].params.surface, 'audio');
    assert.equal(failures[0].params.unit_id, 'mounted-task-audio-owner-unavailable-unit');
    assert.equal(failures[0].params.failure_reason, 'task_audio_owner_unavailable');
    assert.match(failures[0].requestId, /^live-voice-p2-presentation-failed-/);
    assert.equal(failures[1].requestId, failures[0].requestId, 'retry must retain the exact request identity');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    assert.equal(states.at(-1)?.terminal_announcement_state, 'idle');
    assert.notEqual(states.at(-1)?.text_status, 'failed');
    assert.equal(states.at(-1)?.text_reason, null);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted nonterminal Task AUDIO ACK drains one follow-up then resumes listening', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-task-audio-normal-session';
  const controlRef = { current: null };
  const calls = [];
  const states = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  let binding = null;
  let activeMediaBinding = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      binding = { ...params };
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: { status: 'closed', ...params },
      };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 0,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      throw new Error('successful non-stale Task AUDIO must not report presentation failure');
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-task-audio-normal-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'N'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Read the current background task update.', 1);
    }
    if (method === 'live_voice.composition.unified.submit') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: `mounted-task-audio-normal-agent-${params.voice_claim_id}`,
          round_id: `mounted-task-audio-normal-round-${params.voice_claim_id}`,
          response: {
            interaction_id: params.interaction_id,
            response_id: 'mounted-task-audio-normal-response',
            response_generation: 4,
          },
        },
      };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-task-audio-normal-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected normal Task AUDIO request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'normal Task AUDIO P1 owner did not activate',
      );
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'normal Task AUDIO capture did not start');
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'normal Task AUDIO capture did not become ready');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.unified.submit'),
        'normal Task AUDIO source turn was not committed',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'normal Task AUDIO notification poll did not start');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-audio-normal-response',
            response_generation: 4,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'Background task update: running.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-task-audio-normal-unit',
            seq: 0,
            content_ref: `sha256:${'d'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.speech.synthesize_batch'),
        'normal Task AUDIO did not reach the formal batch TTS owner',
      );
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'normal Task AUDIO did not start browser playout');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'work.progress',
          response: null,
          agent_event: null,
          source_event: null,
          progress_event: {
            event_type: 'task.running',
            payload: { state: 'running' },
          },
          presentation_unit: null,
          error_reason: null,
        },
      });
    });

    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 0);
    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.presentation.ack'),
        'normal Task AUDIO successful playout did not emit its exact ACK',
      );
    });
    const acknowledgements = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.equal(acknowledgements.length, 1);
    assert.equal(acknowledgements[0].params.response_id, 'mounted-task-audio-normal-response');
    assert.equal(acknowledgements[0].params.response_generation, 4);
    assert.equal(acknowledgements[0].params.surface, 'audio');
    assert.equal(acknowledgements[0].params.unit_id, 'mounted-task-audio-normal-unit');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 1);
    const playoutReceiptIndex = calls.findIndex(call => call.method === 'live_voice.media.playout_receipt');
    const presentationAckIndex = calls.findIndex(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.equal(playoutReceiptIndex >= 0 && playoutReceiptIndex < presentationAckIndex, true);
    await act(async () => {
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'normal Task AUDIO playout did not resume listening');
      await browser.emitFirstFrame(0);
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'normal Task AUDIO successor capture did not become ready');
    });
    assert.equal(states.at(-1)?.terminal_announcement_state, 'idle');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted stale Task AUDIO settles a server-deferred TEXT fallback after foreground ACK without blocking later terminal AUDIO', async () => {
  const i18n = await createI18n();
  const waitForMounted = (predicate, message) => waitForMountedDefault(predicate, message, 10_000);
  const sessionId = 'mounted-task-audio-success-session';
  const controlRef = { current: null };
  const calls = [];
  const states = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  const unifiedGate = deferred();
  const serverDeferredTextFallbacks = [];
  const serverDeferredTextDeliveries = [];
  const eventOrder = [];
  let foregroundAckObserved = false;
  let binding = null;
  let activeMediaBinding = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      binding = { ...params };
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.response_id === 'mounted-task-audio-foreground-response') {
        foregroundAckObserved = true;
        eventOrder.push('foreground-ack');
        assert.equal(serverDeferredTextFallbacks.length, 1, 'the foreground ACK must release the one retained Task TEXT fallback');
        serverDeferredTextDeliveries.push({
          ...serverDeferredTextFallbacks[0],
          released_after_foreground_ack: true,
        });
        eventOrder.push('deferred-text-release');
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 0,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      assert.equal(
        foregroundAckObserved,
        false,
        'Task AUDIO failure must reach the server while the foreground presentation is still busy',
      );
      eventOrder.push('task-audio-failure');
      serverDeferredTextFallbacks.push({
        ...params,
        request_id: options.requestId,
        status: 'presentation_failed_fallback_text',
        fallback: 'text',
        deferred: true,
      });
      return {
        ok: true,
        result: {
          status: 'presentation_failed_fallback_text',
          ...params,
          fallback: 'text',
          deferred: true,
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-task-audio-success-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'S'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Read the latest background task update.', 1);
    }
    if (method === 'live_voice.composition.unified.submit') {
      await unifiedGate.promise;
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: `mounted-task-audio-success-agent-${params.voice_claim_id}`,
          round_id: `mounted-task-audio-success-round-${params.voice_claim_id}`,
          response: {
            interaction_id: params.interaction_id,
            response_id: 'mounted-task-audio-foreground-response',
            response_generation: 3,
          },
        },
      };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-task-audio-success-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected Task AUDIO success request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'Task AUDIO success P1 owner did not activate',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'Task AUDIO predecessor poll did not start');
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'Task AUDIO success capture did not start');
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'Task AUDIO success capture did not become ready');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.unified.submit'),
        'Task AUDIO success source turn was not committed',
      );
      const notification = {
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-audio-success-response',
            response_generation: 2,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The background task is running.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-task-audio-success-unit',
            seq: 0,
            content_ref: `sha256:${'f'.repeat(64)}`,
          },
        },
      };
      publishNotification(notification);
      try {
        await waitForMounted(
          () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 1,
          'failed Task AUDIO did not settle through its exact failure owner before foreground ACK',
        );
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-12)
            .map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}/${state.terminal_announcement_state}`)
            .join(',')}; methods=${calls.map(call => call.method).join(',')}`,
        );
      }
      assert.equal(foregroundAckObserved, false);
      assert.equal(serverDeferredTextFallbacks.length, 1);
      assert.equal(serverDeferredTextDeliveries.length, 0, 'the deferred TEXT fallback must not be delivered before foreground ACK');
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
      assert.equal(
        calls.filter(
          call =>
            call.method === 'live_voice.speech.synthesize_batch' &&
            call.params.response.response_id === 'mounted-task-audio-success-response',
        ).length,
        0,
        'failed Task AUDIO must not start or replay TTS while its foreground-busy fallback is deferred',
      );
      unifiedGate.resolve();
      await waitForMounted(
        () => states.at(-1)?.text_status === 'waiting',
        'the accepted foreground response did not establish its busy presentation fence',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'Task failure settlement did not release the foreground notification poll');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-audio-foreground-response',
            response_generation: 3,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The foreground response remains authoritative.',
            source_provenance: 'server.authoritative',
          },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-task-audio-foreground-unit',
            seq: 0,
            content_ref: `sha256:${'e'.repeat(64)}`,
          },
        },
      });
      try {
        await waitForMounted(
          () =>
            calls.some(
              call =>
                call.method === 'live_voice.speech.synthesize_batch' &&
                call.params.response.response_id === 'mounted-task-audio-foreground-response',
            ),
          'foreground successor did not reach the formal batch TTS owner',
        );
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-12)
            .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.terminal_announcement_state}`)
            .join(',')}; methods=${calls.map(call => call.method).join(',')}`,
        );
      }
      try {
        await waitForMounted(() => browser.counts.sourceStarts === 1, 'foreground successor did not start browser playout');
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-12)
            .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`)
            .join(',')}; methods=${calls
            .map(call => `${call.method}:${call.params.response?.response_id ?? call.params.response_id ?? 'none'}`)
            .join(',')}`,
        );
      }
    });

    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 0);
    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(
        () =>
          calls.some(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-task-audio-foreground-response',
          ),
        'foreground successor playout did not emit its exact ACK',
      );
      await waitForMounted(
        () => serverDeferredTextDeliveries.length === 1,
        'the exact foreground ACK did not release the server-deferred Task TEXT fallback',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'foreground settlement did not release the next notification poll');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-audio-subsequent-terminal-response',
            response_generation: 4,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The background task is complete.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-task-audio-subsequent-terminal-unit',
            seq: 0,
            content_ref: `sha256:${'c'.repeat(64)}`,
          },
        },
      });
      try {
        await waitForMounted(
          () =>
            calls.some(
              call =>
                call.method === 'live_voice.speech.synthesize_batch' &&
                call.params.response.response_id === 'mounted-task-audio-subsequent-terminal-response',
            ),
          'the subsequent terminal Task AUDIO did not advance after predecessor settlement',
        );
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-12)
            .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`)
            .join(',')}; methods=${calls
            .map(call => `${call.method}:${call.params.response?.response_id ?? call.params.response_id ?? 'none'}`)
            .join(',')}`,
        );
      }
      await waitForMounted(() => browser.counts.sourceStarts === 2, 'subsequent terminal Task AUDIO did not start browser playout');
    });
    let acknowledgements = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.deepEqual(
      acknowledgements.map(call => call.params.response_id),
      ['mounted-task-audio-foreground-response'],
      'the subsequent terminal Task AUDIO must wait for successful playout before ACK',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 1);
    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(
        () =>
          calls.some(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-task-audio-subsequent-terminal-response',
          ),
        'subsequent terminal Task AUDIO successful playout did not emit its exact ACK',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.activate').length === 3,
        'subsequent terminal Task AUDIO settlement did not resume the exact successor capture',
      );
    });
    acknowledgements = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.deepEqual(
      acknowledgements.map(call => ({
        response_id: call.params.response_id,
        response_generation: call.params.response_generation,
        surface: call.params.surface,
        unit_id: call.params.unit_id,
      })),
      [
        {
          response_id: 'mounted-task-audio-foreground-response',
          response_generation: 3,
          surface: 'text',
          unit_id: 'mounted-task-audio-foreground-unit',
        },
        {
          response_id: 'mounted-task-audio-subsequent-terminal-response',
          response_generation: 4,
          surface: 'audio',
          unit_id: 'mounted-task-audio-subsequent-terminal-unit',
        },
      ],
      'the foreground response and later terminal Task AUDIO must settle in route order',
    );
    const failures = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed');
    assert.equal(failures.length, 1);
    assert.equal(failures[0].params.response_id, 'mounted-task-audio-success-response');
    assert.equal(failures[0].params.response_generation, 2);
    assert.equal(failures[0].params.surface, 'audio');
    assert.equal(failures[0].params.unit_id, 'mounted-task-audio-success-unit');
    assert.equal(failures[0].params.failure_reason, 'task_audio_playout_failed');
    assert.deepEqual(
      serverDeferredTextFallbacks.map(fallback => ({
        response_id: fallback.response_id,
        response_generation: fallback.response_generation,
        surface: fallback.surface,
        unit_id: fallback.unit_id,
        status: fallback.status,
        fallback: fallback.fallback,
        deferred: fallback.deferred,
      })),
      [{
        response_id: 'mounted-task-audio-success-response',
        response_generation: 2,
        surface: 'audio',
        unit_id: 'mounted-task-audio-success-unit',
        status: 'presentation_failed_fallback_text',
        fallback: 'text',
        deferred: true,
      }],
      'exactly one Task AUDIO failure must settle as the server-deferred TEXT fallback',
    );
    assert.deepEqual(
      serverDeferredTextDeliveries.map(fallback => ({
        response_id: fallback.response_id,
        response_generation: fallback.response_generation,
        surface: fallback.surface,
        unit_id: fallback.unit_id,
        released_after_foreground_ack: fallback.released_after_foreground_ack,
      })),
      [{
        response_id: 'mounted-task-audio-success-response',
        response_generation: 2,
        surface: 'audio',
        unit_id: 'mounted-task-audio-success-unit',
        released_after_foreground_ack: true,
      }],
      'only the exact foreground ACK may release the one deferred Task TEXT fallback',
    );
    assert.deepEqual(
      eventOrder,
      ['task-audio-failure', 'foreground-ack', 'deferred-text-release'],
      'the Task failure must precede the foreground ACK, which alone releases deferred TEXT',
    );
    const syntheses = calls.filter(call => call.method === 'live_voice.speech.synthesize_batch');
    assert.deepEqual(
      syntheses.map(call => call.params.response.response_id),
      [
        'mounted-task-audio-foreground-response',
        'mounted-task-audio-subsequent-terminal-response',
      ],
    );
    assert.equal(
      syntheses.filter(call => call.params.response.response_id === 'mounted-task-audio-success-response').length,
      0,
      'failed Task AUDIO must not start or replay TTS after its accepted deferred TEXT fallback',
    );
    const p2Activations = calls.filter(call => call.method === 'live_voice.composition.p2.activate');
    assert.equal(p2Activations.length, 3);
    assert.deepEqual(
      p2Activations.slice(1).map(call => call.params),
      [p2Activations[0].params, p2Activations[0].params],
      'initial and post-terminal media starts must replay only the exact P2 activation binding',
    );
    assert.equal(
      calls.some(
        call =>
          call.method === 'live_voice.composition.p2.presentation.ack' &&
          call.params.response_id === 'mounted-task-audio-success-response',
      ),
      false,
      'the predecessor Task response must never receive a forged AUDIO ACK',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 2);
    const playoutReceiptIndex = calls.findIndex(
      call =>
        call.method === 'live_voice.media.playout_receipt' &&
        call.params.response_id === 'mounted-task-audio-foreground-response',
    );
    const presentationAckIndex = calls.findIndex(
      call =>
        call.method === 'live_voice.composition.p2.presentation.ack' &&
        call.params.response_id === 'mounted-task-audio-foreground-response',
    );
    assert.equal(playoutReceiptIndex >= 0 && playoutReceiptIndex < presentationAckIndex, true);
    const taskPlayoutReceiptIndex = calls.findIndex(
      call =>
        call.method === 'live_voice.media.playout_receipt' &&
        call.params.response_id === 'mounted-task-audio-subsequent-terminal-response',
    );
    const taskPresentationAckIndex = calls.findIndex(
      call =>
        call.method === 'live_voice.composition.p2.presentation.ack' &&
        call.params.response_id === 'mounted-task-audio-subsequent-terminal-response',
    );
    assert.equal(taskPlayoutReceiptIndex >= 0 && taskPlayoutReceiptIndex < taskPresentationAckIndex, true);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted post-submit Task AUDIO fallback retains the exact foreground P1 playout owner through receipt and ACK', async () => {
  const i18n = await createI18n();
  const waitForMounted = (predicate, message) => waitForMountedDefault(predicate, message, 10_000);
  const sessionId = 'mounted-task-audio-foreground-owner-session';
  const controlRef = { current: null };
  const calls = [];
  const states = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  const unifiedGate = deferred();
  const eventOrder = [];
  let binding = null;
  let activeMediaBinding = null;
  let lastSynthesisResponseId = null;
  let deferredTextFallbackCount = 0;
  let deferredTextReleaseCount = 0;
  let renderer;
  const browser = installP1BrowserEnvironment({
    mediaBinding: () => activeMediaBinding,
    startAudioSource: () => {
      if (lastSynthesisResponseId === 'mounted-post-submit-task-response') {
        throw Object.assign(new Error('mounted Task AUDIO browser source start failed'), {
          reason: 'MOUNTED_TASK_AUDIO_SOURCE_START_FAILED',
        });
      }
    },
  });
  const activateP2 = createMountedP2ActivationResponder();
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      binding = { ...params };
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      eventOrder.push('task-audio-failure');
      deferredTextFallbackCount += 1;
      return {
        ok: true,
        result: {
          status: 'presentation_failed_fallback_text',
          ...params,
          fallback: 'text',
          deferred: true,
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.response_id === 'mounted-post-submit-foreground-response') {
        eventOrder.push('foreground-ack');
        assert.equal(deferredTextFallbackCount, 1);
        deferredTextReleaseCount += 1;
        eventOrder.push('deferred-text-release');
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 0,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-task-audio-foreground-owner-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'L'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Add a validation step to the current task.', 1);
    }
    if (method === 'live_voice.composition.unified.submit') {
      await unifiedGate.promise;
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: `mounted-task-audio-foreground-owner-agent-${params.voice_claim_id}`,
          round_id: `mounted-task-audio-foreground-owner-round-${params.voice_claim_id}`,
          response: {
            interaction_id: params.interaction_id,
            response_id: 'mounted-post-submit-foreground-response',
            response_generation: 4,
          },
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      lastSynthesisResponseId = params.response.response_id;
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    if (method === 'live_voice.media.playout_receipt') {
      eventOrder.push('foreground-receipt');
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-task-audio-foreground-owner-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    throw new Error(`unexpected foreground owner request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'foreground owner P1 route did not activate',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'foreground owner predecessor poll did not start');
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'foreground owner capture did not start');
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'foreground owner capture did not become ready');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.unified.submit'),
        'foreground owner voice final was not submitted',
      );
      unifiedGate.resolve();
      await waitForMounted(
        () => states.at(-1)?.text_status === 'waiting',
        'accepted foreground response did not retain its post-submit presentation fence',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'post-submit Task AUDIO poll did not remain active');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-post-submit-task-response',
            response_generation: 3,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'Background task update: accepted.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-post-submit-task-unit',
            seq: 0,
            content_ref: `sha256:${'a'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 1,
        'post-submit Task AUDIO did not emit its one exact failure settlement',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'Task fallback did not release the foreground notification poll');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-post-submit-foreground-response',
            response_generation: 4,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The validation step was added to the background task.',
            source_provenance: 'server.authoritative',
          },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-post-submit-foreground-unit',
            seq: 0,
            content_ref: `sha256:${'b'.repeat(64)}`,
          },
        },
      });
      try {
        await waitForMounted(
          () =>
            calls.some(
              call =>
                call.method === 'live_voice.speech.synthesize_batch' &&
                call.params.response.response_id === 'mounted-post-submit-foreground-response',
            ) || states.some(state => state.text_reason === 'PRODUCT_TTS_PLAYBACK_FAILED'),
          'foreground response neither reached TTS nor exposed the ownership failure',
        );
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-16)
            .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`)
            .join(',')}; methods=${calls
            .map(call => `${call.method}:${call.params.response?.response_id ?? call.params.response_id ?? 'none'}`)
            .join(',')}`,
        );
      }
    });

    const foregroundSyntheses = calls.filter(
      call =>
        call.method === 'live_voice.speech.synthesize_batch' &&
        call.params.response.response_id === 'mounted-post-submit-foreground-response',
    );
    assert.equal(
      foregroundSyntheses.length,
      1,
      `the exact retained P1 owner must synthesize foreground generation 4 once; states=${states
        .slice(-12)
        .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`)
        .join(',')}`,
    );
    assert.equal(
      calls.some(
        call =>
          call.method === 'live_voice.speech.synthesize_batch' &&
          call.params.response.response_id === 'mounted-post-submit-task-response',
      ),
      false,
      'foreground-busy Task AUDIO must enter exact fallback without consuming the foreground P1 owner',
    );
    assert.equal(browser.counts.sourceStarts, 1, 'only the foreground response may start browser playout');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 0);

    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.media.playout_receipt'),
        'foreground playout did not emit its exact media receipt',
      );
      await waitForMounted(
        () =>
          calls.some(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-post-submit-foreground-response',
          ),
        'foreground playout receipt did not advance to Presentation ACK',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.activate').length === 2,
        'foreground ACK and deferred fallback did not resume exactly one successor listening turn',
      );
    });

    const failures = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed');
    assert.equal(failures.length, 1);
    assert.deepEqual(
      {
        response_id: failures[0].params.response_id,
        response_generation: failures[0].params.response_generation,
        surface: failures[0].params.surface,
        unit_id: failures[0].params.unit_id,
        failure_reason: failures[0].params.failure_reason,
      },
      {
        response_id: 'mounted-post-submit-task-response',
        response_generation: 3,
        surface: 'audio',
        unit_id: 'mounted-post-submit-task-unit',
        failure_reason: 'task_audio_playout_failed',
      },
    );
    const acknowledgements = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.deepEqual(
      acknowledgements.map(call => ({
        response_id: call.params.response_id,
        response_generation: call.params.response_generation,
        surface: call.params.surface,
        unit_id: call.params.unit_id,
      })),
      [{
        response_id: 'mounted-post-submit-foreground-response',
        response_generation: 4,
        surface: 'text',
        unit_id: 'mounted-post-submit-foreground-unit',
      }],
      'Task AUDIO must never receive a forged ACK',
    );
    assert.equal(deferredTextFallbackCount, 1);
    assert.equal(deferredTextReleaseCount, 1);
    assert.deepEqual(eventOrder, [
      'task-audio-failure',
      'foreground-receipt',
      'foreground-ack',
      'deferred-text-release',
    ]);
    const receiptIndex = calls.findIndex(call => call.method === 'live_voice.media.playout_receipt');
    const ackIndex = calls.findIndex(
      call =>
        call.method === 'live_voice.composition.p2.presentation.ack' &&
        call.params.response_id === 'mounted-post-submit-foreground-response',
    );
    assert.equal(receiptIndex >= 0 && receiptIndex < ackIndex, true);
    assert.equal(
      states.some(state => state.text_reason === 'PRODUCT_TTS_PLAYBACK_FAILED'),
      false,
      'foreground playout ownership must not collapse into PRODUCT_TTS_PLAYBACK_FAILED',
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted stale Task TEXT replays after foreground ACK and presents before its only ACK', async () => {
  const i18n = await createI18n();
  const waitForMounted = (predicate, message) => waitForMountedDefault(predicate, message, 10_000);
  const sessionId = 'mounted-task-text-deferred-session';
  const controlRef = { current: null };
  const calls = [];
  const states = [];
  const projectedMessages = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  const notificationResults = new Map();
  const unifiedGate = deferred();
  const eventOrder = [];
  let foregroundAckObserved = false;
  let binding = null;
  let activeMediaBinding = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) {
      notificationResults.set(waiter.requestId, notification);
      waiter.resolve(notification);
    }
    else queuedNotifications.push(notification);
  };
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      binding = { ...params };
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      notificationWaiters.length = 0;
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      if (notificationResults.has(options.requestId)) return notificationResults.get(options.requestId);
      if (queuedNotifications.length > 0) {
        const notification = queuedNotifications.shift();
        notificationResults.set(options.requestId, notification);
        return notification;
      }
      return new Promise(resolve => notificationWaiters.push({ requestId: options.requestId, resolve }));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.response_id === 'mounted-task-text-foreground-response') {
        foregroundAckObserved = true;
        eventOrder.push('foreground-ack');
      } else {
        assert.equal(params.response_id, 'mounted-task-text-stale-response');
        assert.equal(foregroundAckObserved, true, 'replayed Task TEXT may ACK only after its authoritative foreground ACK');
        eventOrder.push('replayed-text-ack');
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 0,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      assert.fail('a stale Task TEXT presentation must never enter the AUDIO-only presentation.failed authority');
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-task-text-deferred-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'T'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Read the latest background task update.', 1);
    }
    if (method === 'live_voice.composition.unified.submit') {
      await unifiedGate.promise;
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: `mounted-task-text-deferred-agent-${params.voice_claim_id}`,
          round_id: `mounted-task-text-deferred-round-${params.voice_claim_id}`,
          response: {
            interaction_id: params.interaction_id,
            response_id: 'mounted-task-text-foreground-response',
            response_generation: 3,
          },
        },
      };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-task-text-deferred-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected Task TEXT deferred request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: event => projectedMessages.push(event),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'stale Task TEXT P1 owner did not activate',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'stale Task TEXT predecessor poll did not start');
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'stale Task TEXT capture did not start');
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'stale Task TEXT capture did not become ready');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.unified.submit'),
        'stale Task TEXT source turn was not committed',
      );
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-text-stale-response',
            response_generation: 2,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'This stale Task TEXT must remain side-effect free until foreground settlement.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-task-text-stale-unit',
            seq: 0,
            content_ref: `sha256:${'d'.repeat(64)}`,
          },
        },
      });
    });

    assert.equal(foregroundAckObserved, false);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
    assert.equal(
      calls.filter(
        call =>
          call.method === 'live_voice.speech.synthesize_batch' &&
          call.params.response.response_id === 'mounted-task-text-stale-response',
      ).length,
      0,
      'stale Task TEXT must not synthesize before foreground settlement',
    );
    assert.equal(
      projectedMessages.some(event => event.message.content.includes('This stale Task TEXT')),
      false,
      'stale Task TEXT must not project into UI/history before its ACK authority',
    );

    unifiedGate.resolve();
    await act(async () => {
      await waitForMounted(
        () => states.at(-1)?.text_status === 'waiting',
        'accepted foreground response did not establish its busy presentation fence',
      );
      try {
        await waitForMounted(() => notificationWaiters.length === 1, 'foreground notification poll did not resume');
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-12)
            .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}`)
            .join(',')}; methods=${calls.map(call => call.method).join(',')}`,
        );
      }
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-text-foreground-response',
            response_generation: 3,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The foreground response remains authoritative.',
            source_provenance: 'server.authoritative',
          },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-task-text-foreground-unit',
            seq: 0,
            content_ref: `sha256:${'e'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () =>
          calls.some(
            call =>
              call.method === 'live_voice.speech.synthesize_batch' &&
              call.params.response.response_id === 'mounted-task-text-foreground-response',
          ),
        'foreground successor did not reach the formal batch TTS owner',
      );
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'foreground successor did not start browser playout');
    });

    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(
        () =>
          calls.some(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-task-text-foreground-response',
        ),
        'foreground settlement did not emit its exact ACK',
      );
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.activate' && call.params.activation_generation > 1),
        'foreground settlement did not refresh the P2 owner for retained Task TEXT replay',
      );
    });

    await act(async () => {
      await waitForMounted(
        () =>
          notificationWaiters.length === 1 &&
          calls.some(
            call =>
              call.method === 'live_voice.composition.p2.notification.next' &&
              call.params.activation_generation > 1,
          ),
        'successor P2 owner did not request retained Task TEXT replay',
      );
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.output',
          response: {
            interaction_id: binding.interaction_id,
            response_id: 'mounted-task-text-stale-response',
            response_generation: 1,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'This stale Task TEXT must remain side-effect free until foreground settlement.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-task-text-replayed-unit',
            seq: 0,
            content_ref: `sha256:${'d'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () =>
          calls.filter(call => call.method === 'live_voice.media.activate').length === 2 &&
          states.at(-1)?.p1_status === 'starting',
        'successor Task TEXT did not prepare a fresh media owner',
      );
      await browser.emitFirstFrame(0);
    });

    await act(async () => {
      try {
        await waitForMounted(
          () =>
            calls.some(
              call =>
                call.method === 'live_voice.speech.synthesize_batch' &&
                call.params.response.response_id === 'mounted-task-text-stale-response',
            ),
          'successor did not present retained Task TEXT through TTS',
        );
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-12)
            .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}`)
            .join(',')}; methods=${calls
            .map(call => `${call.method}:${call.params.response?.response_id ?? call.params.response_id ?? call.params.activation_generation ?? 'none'}`)
            .join(',')}`,
        );
      }
      await waitForMounted(() => browser.counts.sourceStarts === 2, 'replayed Task TEXT did not start browser playout');
    });

    assert.equal(
      calls.filter(
        call =>
          call.method === 'live_voice.composition.p2.presentation.ack' &&
          call.params.response_id === 'mounted-task-text-stale-response',
      ).length,
      0,
      'replayed Task TEXT must remain unacknowledged until browser playout completes',
    );

    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(
        () =>
          calls.some(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-task-text-stale-response',
          ),
        'replayed Task TEXT successful playout did not emit its exact ACK',
      );
    });

    const acknowledgements = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.deepEqual(
      acknowledgements.map(call => ({
        response_id: call.params.response_id,
        response_generation: call.params.response_generation,
        surface: call.params.surface,
        unit_id: call.params.unit_id,
      })),
      [
        {
          response_id: 'mounted-task-text-foreground-response',
          response_generation: 3,
          surface: 'text',
          unit_id: 'mounted-task-text-foreground-unit',
        },
        {
          response_id: 'mounted-task-text-stale-response',
          response_generation: 1,
          surface: 'text',
          unit_id: 'mounted-task-text-replayed-unit',
        },
      ],
      'foreground ACK must precede exactly one replayed and presented Task TEXT ACK',
    );
    assert.deepEqual(eventOrder, ['foreground-ack', 'replayed-text-ack']);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
    assert.equal(
      calls.filter(
        call =>
          call.method === 'live_voice.speech.synthesize_batch' &&
          call.params.response.response_id === 'mounted-task-text-stale-response',
      ).length,
      1,
      'retained Task TEXT must present exactly once after successor replay',
    );
    assert.equal(
      projectedMessages.filter(event => event.message.content.includes('This stale Task TEXT')).length,
      1,
      'retained Task TEXT must project into UI/history exactly once after foreground settlement',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
    assert.equal(
      calls.some(
        call =>
          (call.method.includes('.task.') && call.method !== 'live_voice.task.list') ||
          call.method.includes('.agent.') ||
          call.method.includes('.tool.'),
      ),
      false,
      'stale Task TEXT must not mutate Task, Agent, or Tool authority',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 2);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted Task AUDIO failure adopts server TEXT fallback through visible running and terminal ACKs', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-task-audio-text-fallback-session';
  const taskId = 'mounted-task-audio-text-fallback-task';
  const controlRef = { current: null };
  const calls = [];
  const states = [];
  const messages = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  let p2Binding = null;
  let taskBinding = null;
  let taskTerminal = false;
  let progressActivation = null;
  let progressListener = null;
  let activeMediaBinding = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const progressSubscribe = listener => {
    progressListener = listener;
    return () => {
      if (progressListener === listener) progressListener = null;
    };
  };
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      p2Binding = { ...params };
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      throw new Error('failed Task AUDIO must never emit a presentation ACK');
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      assert.notEqual(taskBinding, null);
      assert.notEqual(progressActivation, null);
      assert.equal(typeof progressListener, 'function');
      const fallback = mountedLifecycleProgress(taskBinding, progressActivation, {
        state: 'running',
        eventType: 'task.running',
        seq: 1,
        taskId,
        attemptId: 'attempt-a',
      });
      Object.assign(fallback, {
        origin_kind: 'voice',
        requested_origin_kind: 'voice',
        effective_origin_kind: 'text',
        delivery_mode: 'text_fallback',
        fallback_reason: 'TASK_PROGRESS_AUDIO_PLAYOUT_FAILED',
      });
      globalThis.queueMicrotask(() => progressListener?.(fallback));
      return {
        ok: true,
        result: {
          status: 'presentation_failed_fallback_text',
          ...params,
          fallback: 'text',
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.task.status') {
      assert.notEqual(taskBinding, null);
      return mountedP3Status(taskBinding, {
        taskId,
        state: taskTerminal ? 'terminal' : 'running',
        outcome: taskTerminal ? 'completed' : null,
        eventHead: taskTerminal ? 2 : 1,
      });
    }
    if (method === 'live_voice.task.events') {
      assert.notEqual(taskBinding, null);
      return mountedP3Events(taskBinding, { taskId, terminalA: taskTerminal, terminalAOutcome: 'completed' });
    }
    if (method === 'live_voice.composition.p3.progress.activate') {
      progressActivation = { ...params };
      return {
        ok: true,
        result: mountedProgressActivation(params, {
          origin_kind: 'voice',
          requested_origin_kind: 'voice',
          voice_progress: 'available',
          voice_reason: null,
          fallback_reason: null,
        }),
      };
    }
    if (method === 'live_voice.composition.p3.progress.ack') {
      if (params.seq === 2) {
        assert.equal(messages.filter(entry => entry.message.content === 'The background task is complete and its result is ready.').length, 1,
          'terminal fallback ACK preceded its formal chat projection');
      }
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          attempt_id: 'attempt-a',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-task-audio-text-fallback-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'F'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Start a background task and read its progress.', 1);
    }
    if (method === 'live_voice.composition.unified.submit') {
      taskBinding = {
        subject_id: 'mounted-task-audio-text-fallback-subject',
        session_id: params.session_id,
        project_id: 'mounted-task-audio-text-fallback-project',
        correlation_id: params.correlation_id,
        generation: 1,
      };
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'authoritative_presentation_accepted',
          response: {
            interaction_id: params.interaction_id,
            response_id: 'mounted-task-audio-text-fallback-response',
            response_generation: 2,
          },
          task_id: taskId,
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      throw Object.assign(new Error('mounted Task AUDIO provider unavailable'), {
        reason: 'SPEECH_PROVIDER_UNAVAILABLE',
      });
    }
    throw new Error(`unexpected Task AUDIO fallback request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledProductCarrierElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          progressSubscribe,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: entry => messages.push(entry),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'Task AUDIO fallback P1 owner did not activate',
      );
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'Task AUDIO fallback capture did not start');
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'Task AUDIO fallback capture did not become ready');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => progressActivation?.task_id === taskId,
        'voice-created Task did not activate its exact progress route',
      );
      await waitForMounted(() => notificationWaiters.length === 1, 'Task AUDIO fallback notification poll did not start');
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          ...p2Binding,
          kind: 'agent.output',
          response: {
            interaction_id: p2Binding.interaction_id,
            response_id: 'mounted-task-audio-text-fallback-response',
            response_generation: 2,
          },
          agent_event: {
            event_type: 'chat.final',
            text: 'The background task is running.',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-task-audio-text-fallback-audio-unit',
            seq: 0,
            content_ref: `sha256:${'a'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 1,
        'failed Task AUDIO did not report its exact playout failure',
      );
      await waitForMounted(
        () => renderer.root.findAllByProps({ 'data-testid': 'live-voice-product-task-notification' }).length === 1,
        'server TEXT fallback did not reach the visible product task notification',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length === 1,
        'connected TEXT fallback did not emit its exact progress ACK',
      );
      taskTerminal = true;
      const terminal = mountedLifecycleProgress(taskBinding, progressActivation, {
        state: 'terminal',
        eventType: 'task.terminal',
        seq: 2,
        outcome: 'completed',
        taskId,
        attemptId: 'attempt-a',
      });
      Object.assign(terminal, {
        origin_kind: 'voice',
        requested_origin_kind: 'voice',
        effective_origin_kind: 'text',
        delivery_mode: 'text_fallback',
        fallback_reason: 'TASK_PROGRESS_AUDIO_PLAYOUT_FAILED',
      });
      progressListener(terminal);
      await waitForMounted(
        () => renderer.root.findByProps({ 'data-testid': 'live-voice-product-task-notification' }).props['data-event-seq'] === '2',
        'terminal TEXT fallback did not replace the visible running notification',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length === 2,
        'visible terminal TEXT fallback did not emit its exact progress ACK',
      );
      assert.equal(
        terminalTextFallbackCompletesVoiceAnnouncement(states.at(-1)?.task_progress_event, taskId),
        true,
        'mounted terminal fallback no longer matches the exact settlement contract',
      );
      await waitForMounted(
        () => states.at(-1)?.terminal_announcement_state === 'idle',
        `visible terminal TEXT fallback ACK left the voice announcement unsettled; states=${states
          .slice(-12)
          .map(state => `${state.p1_status}/${state.terminal_announcement_state}/${state.task_progress_state}/${state.task_progress_delivery_mode}/${state.task_unread_delivery?.acknowledgement}`)
          .join(',')}`,
      );
      progressListener(terminal);
      progressListener({ ...terminal, session_id: 'foreign-session' });
      progressListener({ ...terminal, task_id: 'foreign-task' });
      progressListener({ ...terminal, generation: terminal.generation + 1 });
      await new Promise(resolve => setTimeout(resolve, 25));
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length, 2);
      assert.equal(messages.filter(entry => entry.message.content === 'The background task is complete and its result is ready.').length, 1);
    });

    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
    const failures = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed');
    assert.equal(failures.length, 1);
    assert.equal(failures[0].params.response_id, 'mounted-task-audio-text-fallback-response');
    assert.equal(failures[0].params.surface, 'audio');
    assert.equal(failures[0].params.failure_reason, 'task_audio_playout_failed');
    const textAcks = calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack');
    assert.equal(textAcks.length, 2);
    assert.deepEqual(textAcks.map(call => call.params.seq), [1, 2]);
    assert.equal(textAcks.every(call => call.params.presentation_class === 'text'), true);
    assert.equal(textAcks.every(call => call.params.task_id === taskId), true);
    assert.equal(
      states.at(-1)?.output,
      'The background task is complete and its result is ready.',
      'terminal TEXT fallback must replace the primary Live Voice output before consumption',
    );
    assert.equal(states.at(-1)?.terminal_notification, states.at(-1)?.output);
    const progressNode = renderer.root.findByProps({ 'data-testid': 'live-voice-product-task-notification' });
    assert.equal(progressNode.props['data-delivery-id'], 'mounted-terminal-2-completed');
    assert.equal(progressNode.props['data-presentation-class'], 'text');
    assert.equal(progressNode.props['data-event-seq'], '2');
    assert.equal(
      renderer.root.findByProps({ className: 'live-voice-demo__task-detail' }).children[0],
      'Background task completed.',
    );
    assert.equal(renderer.root.findAllByProps({ 'data-testid': 'live-voice-integrated-product-progress' }).length, 1);
    assert.equal(JSON.stringify(renderer.toJSON()).includes('TASK_PROGRESS_AUDIO_PLAYOUT_FAILED'), true);
    assert.equal(
      states.at(-1)?.terminal_announcement_state,
      'idle',
      'terminal fallback settlement must not block the next recognized owner from resuming capture',
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

for (const { recognitionFailure, recognitionStart, recovery = 'play', arrivalDuringRecovery = false } of [
  ...['SPEECH_PROVIDER_EMPTY_TRANSCRIPT', 'STREAMING_SPEECH_PROVIDER_TIMEOUT'].flatMap(recognitionFailure =>
    ['deadline', 'natural_eot'].map(recognitionStart => ({ recognitionFailure, recognitionStart }))),
  { recognitionFailure: 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT', recognitionStart: 'deadline', recovery: 'exit' },
  { recognitionFailure: 'STREAMING_SPEECH_PROVIDER_TIMEOUT', recognitionStart: 'deadline', recovery: 'replay_failure' },
  { recognitionFailure: 'STREAMING_SPEECH_PROVIDER_TIMEOUT', recognitionStart: 'deadline', recovery: 'exit_during_replay' },
  { recognitionFailure: 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT', recognitionStart: 'natural_eot', arrivalDuringRecovery: true },
  { recognitionFailure: 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT', recognitionStart: 'natural_eot', arrivalDuringRecovery: true, recovery: 'replay_failure' },
  { recognitionFailure: 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT', recognitionStart: 'natural_eot', arrivalDuringRecovery: true, recovery: 'exit_during_replay' },
]) {
  test(`mounted captured terminal AUDIO waits for owned recognition settlement: ${recognitionFailure}/${recognitionStart}/${recovery}${arrivalDuringRecovery ? '/media_start' : ''}`, async () => {
    const i18n = await createI18n();
    const sessionId = `mounted-captured-terminal-${recognitionFailure}-${recognitionStart}`;
    const taskId = 'mounted-captured-terminal-task';
    const controlRef = { current: null };
    const states = [];
    const calls = [];
    const messages = [];
    const queued = [];
    const waiters = [];
    const replayable = new Map();
    let p2Binding;
    let taskBinding;
    let progressActivation;
    let activeMediaBinding;
    let mediaAuthorityAvailable = false;
    let rejectRecognition;
    let recognitionCount = 0;
    let taskTerminal = false;
    let terminalMediaAuthorization;
    let releaseReplay;
    let terminalReplayCount = 0;
    let releaseMediaActivation;
    let synthesisAuthorizationFailures = 0;
    let renderer;
    const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
    const activateP2 = createMountedP2ActivationResponder();
    const presentation = (responseId, generation, text) => ({
      ok: true,
      result: {
        status: 'notification', ...p2Binding, kind: 'agent.output',
        response: { interaction_id: p2Binding.interaction_id, response_id: responseId, response_generation: generation },
        agent_event: { event_type: 'chat.final', text, source_provenance: 'server.task_notification' },
        presentation_unit: { surface: 'audio', unit_id: `${responseId}-unit`, seq: 0, content_ref: `sha256:${'a'.repeat(64)}` },
      },
    });
    const publish = value => {
      if (value.result.response.response_id === 'captured-terminal') {
        terminalMediaAuthorization = mediaAuthorityAvailable ? activeMediaBinding : null;
      }
      const waiter = waiters.shift();
      if (waiter) {
        replayable.set(waiter.requestId, value);
        waiter.resolve(value);
      } else queued.push(value);
    };
    const request = async (method, params, options) => {
      const requestId = options?.requestId;
      calls.push({ method, params: { ...params }, requestId });
      if (method === 'live_voice.composition.p2.activate') {
        p2Binding = { ...params };
        return activateP2(params);
      }
      if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
      if (method === 'live_voice.composition.p2.notification.next') {
        if (replayable.has(requestId)) {
          const value = replayable.get(requestId);
          if (value.result.response.response_id === 'captured-terminal') {
            terminalReplayCount += 1;
            if (recovery === 'replay_failure') throw Object.assign(new Error('replay authority changed'), { reason: 'STALE_RESPONSE_OUTPUT' });
            if (recovery === 'exit_during_replay') await new Promise(resolve => { releaseReplay = resolve; });
            terminalMediaAuthorization = activeMediaBinding;
          }
          return value;
        }
        if (queued.length) {
          const value = queued.shift();
          replayable.set(requestId, value);
          return value;
        }
        return new Promise(resolve => waiters.push({ resolve, requestId }));
      }
      if (method === 'live_voice.composition.p2.presentation.ack') return {
        request_id: requestId, ok: true, error: null,
        result: { status: 'presentation_acknowledged', ...params, accepted: true, replayed: false, history_records_written: 1, history_pending: false },
      };
      if (method === 'live_voice.composition.p2.presentation.failed') return {
        ok: true, result: { status: 'presentation_failed_fallback_text', ...params, fallback: 'text', replayed: false },
      };
      if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
      if (method === 'live_voice.task.status') return mountedP3Status(taskBinding, { taskId });
      if (method === 'live_voice.task.events') return mountedP3Events(taskBinding, { taskId, terminalA: taskTerminal, terminalAOutcome: 'completed' });
      if (method === 'live_voice.composition.p3.progress.activate') {
        progressActivation = { ...params };
        return { ok: true, result: mountedProgressActivation(params) };
      }
      if (method === 'live_voice.composition.p3.progress.close') return { ok: true, result: { status: 'closed', ...params } };
      if (method === 'live_voice.media.activate') {
        if (arrivalDuringRecovery && recognitionCount > 1 && !taskTerminal) {
          await new Promise(resolve => { releaseMediaActivation = resolve; });
        }
        activeMediaBinding = mountedMediaBinding(params, calls.filter(call => call.method === method).length);
        mediaAuthorityAvailable = true;
        return {
          status: 'active', reason_id: 'MEDIA_ROUTE_TICKET_ISSUED', subject_id: 'mounted-captured-terminal-subject',
          endpoint_path: '/ws/live-voice/media', media_ticket: 'C'.repeat(43), subprotocol: 'live-voice.media.v1', ticket_ttl_ms: 30_000,
          end_of_turn: { status: 'active', capability_version: 'media.end_of_turn.v1', detector: 'server_vad', create_response: false, interrupt_response: false },
          binding: activeMediaBinding, privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
        };
      }
      if (method === 'live_voice.media.close') {
        mediaAuthorityAvailable = false;
        return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
      }
      if (method === 'live_voice.media.playout_receipt') return {
        status: 'media_playout_acknowledged', reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `receipt-${params.response_id}`, ...params, duplex_media_observed: false,
      };
      if (method === 'live_voice.speech.recognize_batch') {
        recognitionCount += 1;
        if (recognitionCount === 1) return mountedRecognition(params, 'Create a background itinerary task.', 1);
        return new Promise((_resolve, reject) => { rejectRecognition = reject; });
      }
      if (method === 'live_voice.composition.unified.submit') {
        taskBinding = { subject_id: 'mounted-captured-terminal-subject', session_id: sessionId, project_id: 'mounted-captured-terminal-project', correlation_id: params.correlation_id, generation: 1 };
        return {
          request_id: requestId, ok: true, error: null,
          result: { status: 'authoritative_presentation_accepted', response: { interaction_id: params.interaction_id, response_id: 'captured-accepted', response_generation: 1 }, task_id: taskId },
        };
      }
      if (method === 'live_voice.speech.synthesize_batch') {
        if (params.response.response_id === 'captured-terminal' && terminalMediaAuthorization !== activeMediaBinding) {
          synthesisAuthorizationFailures += 1;
          throw Object.assign(new Error('terminal TTS lacks authorization on the active media route'), { reason: 'SPEECH_OPERATION_NOT_AUTHORIZED' });
        }
        return {
        contract_version: 'live-voice.contract.v2', request_id: params.request_id, operation_id: params.operation_id, ok: true, error: null,
        result: {
          operation: 'speech.synthesize.batch', response: params.response, unit_id: params.unit_id,
          audio: { format: 'wav_pcm16_mono', sample_rate_hz: 48_000, channel_count: 1, data_base64: mountedWavBase64() },
          provider: { provider_id: 'mounted-provider', implementation_class: 'formal', fallback_from: null, model: 'mounted-tts', voice: 'mounted-voice' }, presented: false,
        },
        };
      }
      throw new Error(`unexpected captured terminal request: ${method}`);
    };
    try {
      await act(async () => {
        renderer = create(mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef, progressSubscribe: () => () => undefined,
          taskNotificationPlayoutTimeoutMs: arrivalDuringRecovery ? 500 : 50,
          onProductVoiceStateChange: state => states.push(state), onProductVoiceMessage: entry => messages.push(entry),
        }));
        await waitForMounted(() => states.at(-1)?.available === true, 'captured terminal route unavailable');
        void controlRef.current.start();
        await browser.emitFirstFrame(0);
        await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'initial capture not ready');
        await browser.emitSpeechEndOfTurn();
        await waitForMounted(() => progressActivation?.task_id === taskId && waiters.length > 0, 'voice Task route not established');
        publish(presentation('captured-accepted', 1, 'Background task update: accepted.'));
        await waitForMounted(() => browser.counts.sourceStarts === 1, 'accepted AUDIO did not play');
        browser.endLatestSource();
        await waitForMounted(() => calls.some(call => call.method === 'live_voice.composition.p2.presentation.ack'), 'accepted AUDIO not ACKed');
        await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'listening did not restart');
        await browser.emitFirstFrame(0.25);
        await waitForMounted(() => states.at(-1)?.p1_status === 'capturing' && waiters.length > 0, 'speech-marked capture not ready');
        if (!arrivalDuringRecovery) {
          taskTerminal = true;
          publish(presentation('captured-terminal', 2, 'The background task is complete and its result is ready.'));
        }
        if (recognitionStart === 'natural_eot') {
          if (!arrivalDuringRecovery) await waitForMounted(() => states.at(-1)?.terminal_announcement_state === 'queued', 'terminal notification was not parked');
          await browser.emitSpeechEndOfTurn();
        }
        await waitForMounted(() => typeof rejectRecognition === 'function', 'notification did not settle the speech-marked capture');
        await new Promise(resolve => setTimeout(resolve, 120));
        assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0,
          'notification acquisition deadline raced the still-owned recognition/fallback operation');
        assert.equal(browser.counts.sourceStarts, 1, 'terminal AUDIO preempted unresolved speech');
        assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
        if (recovery === 'exit') {
          await controlRef.current.close();
          const mediaCount = calls.filter(call => call.method === 'live_voice.media.activate').length;
          rejectRecognition(Object.assign(new Error('late recognition after Exit'), { reason: recognitionFailure }));
          await new Promise(resolve => setTimeout(resolve, 120));
          assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, mediaCount);
          return;
        }
        rejectRecognition(Object.assign(new Error('injected recognition settlement'), { reason: recognitionFailure }));
        if (arrivalDuringRecovery) {
          const waiter = waiters.shift();
          waiter?.resolve({ ok: true, result: {
            status: 'notification', ...p2Binding, kind: 'transport.keepalive',
            response: null, agent_event: null, progress_event: null, presentation_unit: null,
          } });
        }
        if (recognitionFailure !== 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT' || arrivalDuringRecovery) {
          await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'failed recognition owner was not recovered');
          if (arrivalDuringRecovery) {
            await waitForMounted(() => typeof releaseMediaActivation === 'function', 'successor media activation was not held');
            assert.equal(mediaAuthorityAvailable, false, 'predecessor media must be revoked before the terminal is observed');
            taskTerminal = true;
            publish(presentation('captured-terminal', 2, 'The background task is complete and its result is ready.'));
            // Let the in-flight notification settle while media.activate is
            // still held; React may batch the intermediate queued render.
            await new Promise(resolve => setTimeout(resolve, 10));
            assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
            assert.equal(browser.counts.sourceStarts, 1);
            releaseMediaActivation();
          }
          await browser.emitFirstFrame(0);
        }
        if (recovery === 'replay_failure') {
          await waitForMounted(() => calls.some(call => call.method === 'live_voice.composition.p2.presentation.failed'), 'failed reauthorization did not retain TEXT fallback');
          return;
        }
        if (recovery === 'exit_during_replay') {
          await waitForMounted(() => typeof releaseReplay === 'function', 'exact terminal reauthorization did not start');
          await controlRef.current.close();
          releaseReplay();
          await new Promise(resolve => setTimeout(resolve, 120));
          return;
        }
        await waitForMounted(
          () => browser.counts.sourceStarts === 2 || synthesisAuthorizationFailures > 0,
          `retained terminal AUDIO did not play after recognition settled; states=${states
            .slice(-16)
            .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}`)
            .join(',')}; methods=${calls.slice(-24).map(call => call.method).join(',')}`,
        );
        assert.equal(synthesisAuthorizationFailures, 0, 'terminal TTS used a new media route without exact P2 reauthorization');
        assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'captured-terminal').length, 0);
        browser.endLatestSource();
        await waitForMounted(() => calls.some(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'captured-terminal'), 'terminal AUDIO not ACKed');
        await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'terminal AUDIO did not resume listening');
        await browser.emitFirstFrame(0);
        await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'post-terminal capture not ready');
      });
      if (recovery !== 'play') {
        assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch' && call.params.response.response_id === 'captured-terminal').length, 0);
        assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'captured-terminal').length, 0);
        assert.equal(messages.filter(entry => entry.message.content === 'The background task is complete and its result is ready.').length, 0);
        assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
        assert.equal(calls.some(call => call.method.includes('task.cancel') || call.method.includes('.mutate')), false);
        if (recovery === 'replay_failure') {
          const failures = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed');
          assert.equal(failures.length, 1);
          assert.equal(failures[0].params.response_id, 'captured-terminal');
          assert.equal(failures[0].params.unit_id, 'captured-terminal-unit');
          await act(async () => controlRef.current.close());
        }
        return;
      }
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch' && call.params.response.response_id === 'captured-terminal').length, 1);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'captured-terminal').length, 1);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
      assert.equal(messages.filter(entry => entry.message.content === 'The background task is complete and its result is ready.').length, 1);
      assert.equal(terminalReplayCount, 1);
      assert.equal(calls.some(call => call.method.includes('task.cancel') || call.method.includes('.mutate')), false);
      await act(async () => controlRef.current.close());
      assert.equal(browser.counts.stoppedTracks, browser.counts.getUserMedia);
      assert.equal(browser.counts.closedAudioContexts, browser.counts.audioContexts);
      assert.equal(browser.counts.socketCloses, browser.counts.socketOpens);
    } finally {
      releaseMediaActivation?.();
      rejectRecognition?.(Object.assign(new Error('test cleanup'), { reason: 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT' }));
      releaseReplay?.();
      if (renderer) await act(async () => renderer.unmount());
      browser.restore();
    }
  });
}

test('mounted P3 reconciles create A through cancel and authoritative A/B terminals to retry B/C without stale effects', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const calls = [];
  const retryWaiters = [];
  let binding = null;
  let authoritativeAttempt = 1;
  let terminalA = false;
  let terminalB = false;
  let failNextStatusReason = null;
  let rejectNextRetryAdmissionReason = null;
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
      return { ok: true, result: mountedProgressActivation(params) };
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
      if (failNextStatusReason !== null) {
        const reason = failNextStatusReason;
        failNextStatusReason = null;
        const error = new Error('private fixture path and credentials must not reach the UI');
        error.reason = reason;
        throw error;
      }
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
              }),
            );
        });
      }
      if (rejectNextRetryAdmissionReason !== null) {
        const reason = rejectNextRetryAdmissionReason;
        rejectNextRetryAdmissionReason = null;
        return mountedP3Status(binding, {
          attemptId: 'attempt-b',
          attemptNumber: 2,
          state: 'terminal',
          outcome: 'completed',
          eventHead: 5,
          retryAdmission: {
            eligible: false,
            reason,
            task_id: 'task-a',
            attempt_id: null,
            attempt_number: null,
          },
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
        terminalA ? { state: 'terminal', outcome: 'cancelled', eventHead: 2 } : { state: 'running', outcome: null, eventHead: 1 },
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
      mountedTaskIntentControls(renderer).textarea.props.onChange({ target: { value: 'create task: must remain blocked' } });
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.create confirmation did not settle');
    });
    assert.equal(mountedTaskIntentControls(renderer).submit.props.disabled, true);
    const naturalCallsBeforeStructuredExecution = calls.filter(call => call.method === 'live_voice.composition.p3.intent').length;
    await act(async () => {
      mountedTaskIntentControls(renderer).root.props.onSubmit({ preventDefault() {} });
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.intent').length,
      naturalCallsBeforeStructuredExecution,
      'a programmatic natural submit while structured confirmation is pending must allocate zero Task intent effects',
    );
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted task.create did not transition the mounted controller to task.cancel',
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
        'nonterminal task.cancel did not retain an authoritative retry inspection',
      );
    });
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);
    const confirmationsBeforeDefensiveFence = calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length;
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => retryWaiters.length === 0 && !JSON.stringify(renderer.toJSON()).includes('checking'),
        'defensive confirmation entry did not fence the retained retry inspection',
      );
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length,
      confirmationsBeforeDefensiveFence,
      'a programmatic confirmation during inspection must allocate zero confirmation effects',
    );
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false,
    );

    terminalA = true;
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'terminal cancelled attempt did not automatically expose task.retry',
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
        'full page remount did not validate and restore the exact cancelled task target',
      );
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate' && call.params.operation === 'task.create').length,
      createsBeforeRefresh,
      'refresh recovery must not duplicate task.create',
    );
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.retry confirmation did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted retry B did not return the mounted controller to task.cancel',
      );
    });
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false,
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
        'formal P3 controls did not recover after reconnect',
      );
    });

    failNextStatusReason = 'EXECUTION_CONTEXT_REVISION_MISMATCH';
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('EXECUTION_CONTEXT_REVISION_MISMATCH'),
        'retry inspection did not expose its stable failure reason',
      );
    });
    assert.equal(JSON.stringify(renderer.toJSON()).includes('private fixture path'), false);
    assert.equal(JSON.stringify(renderer.toJSON()).includes('failed'), true);

    terminalB = true;
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'authoritative terminal completed attempt B did not expose task.retry',
      );
    });
    assert.equal(JSON.stringify(renderer.toJSON()).includes('EXECUTION_CONTEXT_REVISION_MISMATCH'), false);

    const mutationsBeforeUnknownRefresh = calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length;
    failNextStatusReason = 'FORMAL_TASK_STATUS_TRANSPORT_UNAVAILABLE';
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('FORMAL_TASK_STATUS_TRANSPORT_UNAVAILABLE'),
        'ambiguous post-confirmation status failure did not remain visible',
      );
    });
    assert.equal(mountedP3Controls(renderer).button('Check retry eligibility').props.disabled, true);
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);
    assert.equal(mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), false);
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length,
      mutationsBeforeUnknownRefresh,
      'ambiguous status failure must have zero mutation effect',
    );

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
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'remount did not recover the exact retry candidate after ambiguous status',
      );
    });

    const mutationsBeforeDefinitiveRejection = calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length;
    rejectNextRetryAdmissionReason = 'TASK_CONTEXT_WORKTREE_DIRTY';
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('TASK_CONTEXT_WORKTREE_DIRTY'),
        'definitive post-confirmation admission rejection did not expose its reason',
      );
    });
    assert.equal(mountedP3Controls(renderer).button('Check retry eligibility').props.disabled, false);
    assert.equal(mountedP3Controls(renderer).button('Issue confirmation').props.disabled, true);
    assert.equal(mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), false);
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length,
      mutationsBeforeDefinitiveRejection,
      'definitive retry ineligibility must have zero mutation effect',
    );
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'definitive ineligibility did not release the owner for reinspection',
      );
    });
    assert.equal(JSON.stringify(renderer.toJSON()).includes('TASK_CONTEXT_WORKTREE_DIRTY'), false);
    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'task.retry C confirmation did not settle');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.cancel',
        'accepted retry C did not return the mounted controller to task.cancel',
      );
    });
    assert.equal(authoritativeAttempt, 3);
    assert.equal(mountedP3Controls(renderer).root.findByType('input').props.value, 'task-a');
    assert.equal(
      mountedP3Controls(renderer)
        .select.findAllByType('option')
        .some(option => option.props.value === 'task.retry'),
      false,
    );
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').map(call => [call.params.operation, call.params.task_id ?? null]),
      [
        ['task.create', null],
        ['task.cancel', 'task-a'],
        ['task.retry', 'task-a'],
        ['task.retry', 'task-a'],
        ['task.retry', 'task-a'],
        ['task.retry', 'task-a'],
      ],
    );
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate').map(call => [call.params.operation, call.params.task_id ?? null]),
      [
        ['task.create', null],
        ['task.cancel', 'task-a'],
        ['task.retry', 'task-a'],
        ['task.retry', 'task-a'],
      ],
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
      false,
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

test('mounted P3 recovers an eligible historical task without a browser task-target journal', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const historicalBinding = {
    subject_id: 'mounted-historical-subject',
    session_id: 'mounted-historical-session',
    project_id: 'mounted-historical-project',
    correlation_id: 'mounted-historical-correlation',
    generation: 1,
  };
  const calls = [];
  let retryApplied = false;
  let renderer;
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
    if (method === 'live_voice.task.status') {
      if (retryApplied) {
        return mountedP3Status(historicalBinding, {
          attemptId: 'attempt-c',
          attemptNumber: 3,
          state: 'terminal',
          outcome: 'interrupted',
          eventHead: 8,
        });
      }
      return mountedP3Status(historicalBinding, {
        attemptId: 'attempt-b',
        attemptNumber: 2,
        state: 'terminal',
        outcome: 'completed',
        eventHead: 5,
      });
    }
    if (method === 'live_voice.task.events') {
      return mountedP3Events(historicalBinding, { terminalA: true, terminalB: true, terminalC: retryApplied });
    }
    if (method === 'live_voice.composition.p3.confirmation.issue') {
      assert.equal(params.operation, 'task.retry');
      assert.equal(params.task_id, 'task-a');
      assert.equal(params.correlation_id, historicalBinding.correlation_id);
      return {
        ok: true,
        result: {
          status: 'confirmation_issued',
          operation: params.operation,
          command_id: params.command_id,
          target_task_id: params.task_id,
          confirmation_id: `confirmation-${params.command_id}`,
          expires_at: '2999-08-10T10:00:00Z',
          task_control_binding: { ...historicalBinding },
        },
      };
    }
    if (method === 'live_voice.composition.p3.mutate') {
      retryApplied = true;
      return {
        ok: true,
        result: {
          status: 'mutation_processed',
          operation: 'task.retry',
          command_id: params.command_id,
          target_task_id: 'task-a',
          formal_task_result: {
            task_id: 'task-a',
            previous_attempt_id: 'attempt-b',
            attempt_id: 'attempt-c',
            attempt_number: 3,
            applied: true,
            state: 'accepted',
            outbox_id: 'outbox-retry-c',
          },
        },
      };
    }
    throw new Error(`unexpected historical P3 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, historicalBinding.session_id, request));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'historical P3 controls did not mount');
    });
    await act(async () => {
      mountedP3Controls(renderer).select.props.onChange({ target: { value: 'task.cancel' } });
    });
    await act(async () => {
      mountedP3Controls(renderer)
        .root.findByType('input')
        .props.onChange({ target: { value: 'task-a' } });
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.retry', 'historical task inspection did not expose task.retry');
    });
    assert.equal(JSON.stringify(renderer.toJSON()).includes('eligible:2/3'), true);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.status').length, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 1);

    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'historical retry confirmation did not settle');
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.task.status').length, 3);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 2);

    await act(async () => {
      mountedP3Controls(renderer).button('Execute confirmed mutation').props.onClick();
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('interrupted'),
        'historical retry C terminal truth did not replace accepted status',
      );
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.status').length, 4);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.events').length, 3);

    const mutationsBeforeRefresh = calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length;
    await act(async () => {
      renderer.unmount();
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    renderer = null;
    await act(async () => {
      renderer = create(mountedP3Element(i18n, historicalBinding.session_id, request));
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(
        () =>
          mountedP3Controls(renderer).root.findByType('input').props.value === 'task-a' &&
          JSON.stringify(renderer.toJSON()).includes('interrupted') &&
          JSON.stringify(renderer.toJSON()).includes('ineligible'),
        'validated historical task target did not persist and recover after refresh',
      );
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length,
      mutationsBeforeRefresh,
      'historical task-target recovery must perform zero mutation effects',
    );
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

test('mounted P3 atomically switches from the current task leaf to a historical task with a different correlation', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const activateP2 = createMountedP2ActivationResponder();
  const sessionId = 'mounted-task-switch-session';
  const currentBinding = {
    subject_id: 'mounted-task-switch-subject',
    session_id: sessionId,
    project_id: 'mounted-task-switch-project',
    correlation_id: 'mounted-current-task-correlation',
    generation: 7,
  };
  const historicalBinding = {
    ...currentBinding,
    correlation_id: 'mounted-historical-task-correlation',
    generation: 1,
  };
  globalThis.window.sessionStorage.setItem(
    `jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`,
    JSON.stringify({
      contract_version: 'live-voice.product-p3-task-target.v1',
      session_id: sessionId,
      correlation_id: currentBinding.correlation_id,
      task_id: 'task-current',
      task_control_binding: currentBinding,
    }),
  );
  const calls = [];
  let failHistoricalEvents = true;
  let issuedCorrelation = null;
  let renderer;
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.progress.activate') {
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.task.status') {
      if (params.task_id === 'task-current') {
        return mountedP3Status(currentBinding, {
          taskId: 'task-current',
          state: 'terminal',
          outcome: 'cancelled',
          eventHead: 2,
        });
      }
      assert.equal(params.task_id, 'task-a');
      return mountedP3Status(historicalBinding, {
        attemptId: 'attempt-b',
        attemptNumber: 2,
        state: 'terminal',
        outcome: 'completed',
        eventHead: 5,
      });
    }
    if (method === 'live_voice.task.events') {
      if (params.task_id === 'task-current') {
        return mountedP3Events(currentBinding, { taskId: 'task-current', terminalA: true });
      }
      assert.equal(params.task_id, 'task-a');
      if (failHistoricalEvents) throw new Error('injected historical events failure');
      return mountedP3Events(historicalBinding, { terminalB: true });
    }
    if (method === 'live_voice.composition.p3.confirmation.issue') {
      issuedCorrelation = params.correlation_id;
      return {
        ok: true,
        result: {
          status: 'confirmation_issued',
          operation: params.operation,
          command_id: params.command_id,
          target_task_id: params.task_id,
          confirmation_id: `confirmation-${params.command_id}`,
          expires_at: '2999-08-10T10:00:00Z',
          task_control_binding: historicalBinding,
        },
      };
    }
    throw new Error(`unexpected switched-task P3 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'switched-task P3 controls did not mount');
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry',
        'persisted current task did not recover its exact non-1 generation leaf',
      );
      await waitForMounted(
        () =>
          renderer.root
            .findByProps({ 'data-testid': 'live-voice-integrated-p3-activation' })
            .findAllByType('code')
            .some(node => node.children.some(child => child === 'p3:active')),
        'current task progress owner did not settle before target switch',
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).select.props.onChange({ target: { value: 'task.cancel' } });
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.cancel', 'task.cancel did not become selectable');
    });

    await act(async () => {
      mountedP3Controls(renderer)
        .root.findByType('input')
        .props.onChange({ target: { value: 'task-a' } });
      await waitForMounted(
        () =>
          mountedP3Controls(renderer).root.findByType('input').props.value === 'task-a' &&
          mountedP3Controls(renderer).button('Check retry eligibility').props.disabled === false,
        'historical task inspection did not become available',
      );
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('PRODUCT_P3_RETRY_INSPECTION_FAILED'),
        'failed historical candidate did not publish its stable inspection failure',
      );
    });
    const retainedTarget = JSON.parse(
      globalThis.window.sessionStorage.getItem(`jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`),
    );
    assert.equal(retainedTarget.task_id, 'task-current');
    assert.equal(retainedTarget.correlation_id, currentBinding.correlation_id);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);

    failHistoricalEvents = false;
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry' && JSON.stringify(renderer.toJSON()).includes('eligible:2/3'),
        'historical task with a different correlation did not replace the current leaf',
      );
    });
    assert.equal(JSON.stringify(renderer.toJSON()).includes('PRODUCT_P3_RETRY_INSPECTION_FAILED'), false);
    assert.equal(calls.filter(call => call.method === 'live_voice.task.status' && call.params.task_id === 'task-a').length, 4);
    assert.ok(calls.some(call => call.method === 'live_voice.task.status' && call.params.task_id === 'task-current'));
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.task.events').map(call => call.params.task_id),
      ['task-current', 'task-a', 'task-a'],
    );

    await act(async () => {
      mountedP3Controls(renderer).button('Issue confirmation').props.onClick();
      await waitForMounted(() => mountedP3Controls(renderer).hasButton('Execute confirmed mutation'), 'historical task confirmation did not settle');
    });
    assert.equal(issuedCorrelation, historicalBinding.correlation_id);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);
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

test('mounted P3 restores the historical task correlation and advances progress generation after a full remount', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const activateP2 = createMountedP2ActivationResponder();
  const sessionId = 'mounted-historical-progress-remount-session';
  const historicalBinding = {
    subject_id: 'mounted-historical-progress-subject',
    session_id: sessionId,
    project_id: 'mounted-historical-progress-project',
    correlation_id: 'mounted-historical-progress-correlation',
    generation: 11,
  };
  globalThis.window.sessionStorage.setItem(
    `jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`,
    JSON.stringify({
      contract_version: 'live-voice.product-p3-task-target.v1',
      session_id: sessionId,
      correlation_id: historicalBinding.correlation_id,
      task_id: 'task-historical-progress',
      task_control_binding: historicalBinding,
    }),
  );
  const calls = [];
  const progressHighWater = new Map();
  let renderer;
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') {
      return {
        request_id: options?.requestId ?? null,
        ok: true,
        error: null,
        result: {
          tasks: [],
          cursor: null,
          next_cursor: null,
          has_more: false,
          limit: 100,
          supported_operations: [],
        },
      };
    }
    if (method === 'live_voice.task.status') {
      assert.equal(params.task_id, 'task-historical-progress');
      return mountedP3Status(historicalBinding, {
        taskId: 'task-historical-progress',
        state: 'terminal',
        outcome: 'cancelled',
        eventHead: 2,
      });
    }
    if (method === 'live_voice.task.events') {
      assert.equal(params.task_id, 'task-historical-progress');
      return mountedP3Events(historicalBinding, { taskId: 'task-historical-progress', terminalA: true });
    }
    if (method === 'live_voice.composition.p3.progress.activate') {
      assert.equal(params.task_id, 'task-historical-progress');
      assert.equal(params.correlation_id, historicalBinding.correlation_id);
      const key = JSON.stringify([params.session_id, params.task_id, params.origin_id, params.generation_id]);
      const previous = progressHighWater.get(key) ?? 0;
      assert.equal(params.generation, previous + 1);
      progressHighWater.set(key, params.generation);
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    throw new Error(`unexpected historical progress remount request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length === 1,
        'historical task progress did not activate on the first mount',
      );
    });
    await act(async () => {
      renderer.unmount();
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    renderer = null;

    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length === 2,
        'historical task progress did not reactivate after a full remount',
      );
    });

    const activations = calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate');
    assert.deepEqual(
      activations.map(call => [call.params.correlation_id, call.params.generation_id, call.params.generation]),
      [
        [historicalBinding.correlation_id, historicalBinding.correlation_id, 1],
        [historicalBinding.correlation_id, historicalBinding.correlation_id, 2],
      ],
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.task.list').length, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);
    assert.equal(
      renderer.root
        .findByProps({ 'data-testid': 'live-voice-integrated-p3-activation' })
        .findAllByType('code')
        .some(node => node.children.some(child => child === 'p3:active')),
      true,
    );
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

for (const targetFault of ['malformed', 'unavailable']) {
  test(`mounted P3 treats an ${targetFault} persisted task target as a zero-effect authority barrier`, async () => {
    const i18n = await createI18n();
    const browser = installP1BrowserEnvironment();
    const activateP2 = createMountedP2ActivationResponder();
    const sessionId = `mounted-task-target-${targetFault}-session`;
    const targetKey = `jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`;
    const storage = globalThis.window.sessionStorage;
    if (targetFault === 'malformed') {
      storage.setItem(targetKey, '{');
    } else {
      const read = storage.getItem.bind(storage);
      storage.getItem = key => {
        if (key === targetKey) throw new Error('injected target storage failure');
        return read(key);
      };
    }
    const calls = [];
    let renderer;
    const request = async (method, params, options) => {
      calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
      if (method === 'live_voice.composition.p2.activate') return activateP2(params);
      if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
      if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
      if (method === 'live_voice.task.list') {
        return { ok: true, result: { tasks: [{ task_id: 'task-forbidden-generic', state: 'running' }] } };
      }
      if (method === 'live_voice.composition.p3.progress.activate') {
        return { ok: true, result: mountedProgressActivation(params) };
      }
      throw new Error(`unexpected task-target barrier request: ${method}`);
    };

    try {
      await act(async () => {
        renderer = create(mountedP3Element(i18n, sessionId, request));
        await waitForMounted(
          () => JSON.stringify(renderer.toJSON()).includes('PRODUCT_P3_TASK_TARGET_RECOVERY_REQUIRED'),
          `${targetFault} task target did not publish its stable recovery barrier`,
        );
      });
      assert.equal(calls.filter(call => call.method === 'live_voice.task.list').length, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);
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
}

test('mounted P3 lets only the current historical-task inspection publish after a deferred predecessor', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const activateP2 = createMountedP2ActivationResponder();
  const sessionId = 'mounted-task-switch-generation-session';
  const commonBinding = {
    subject_id: 'mounted-task-switch-generation-subject',
    session_id: sessionId,
    project_id: 'mounted-task-switch-generation-project',
  };
  const bindings = {
    'task-b': { ...commonBinding, correlation_id: 'mounted-task-b-correlation', generation: 5 },
    'task-c': { ...commonBinding, correlation_id: 'mounted-task-c-correlation', generation: 9 },
  };
  const calls = [];
  let releaseTaskBStatus = null;
  let renderer;
  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.progress.activate') {
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.task.status') {
      const taskId = params.task_id;
      assert.ok(taskId === 'task-b' || taskId === 'task-c');
      if (taskId === 'task-b') {
        return new Promise(resolve => {
          releaseTaskBStatus = () =>
            resolve(
              mountedP3Status(bindings[taskId], {
                taskId,
                attemptId: 'attempt-b',
                attemptNumber: 2,
                state: 'terminal',
                outcome: 'completed',
                eventHead: 5,
              }),
            );
        });
      }
      return mountedP3Status(bindings[taskId], {
        taskId,
        attemptId: 'attempt-b',
        attemptNumber: 2,
        state: 'terminal',
        outcome: 'completed',
        eventHead: 5,
      });
    }
    if (method === 'live_voice.task.events') {
      assert.equal(params.task_id, 'task-c');
      return mountedP3Events(bindings['task-c'], { taskId: 'task-c', terminalB: true });
    }
    throw new Error(`unexpected overlapping switched-task request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP3Element(i18n, sessionId, request));
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Formal P3 task control'), 'overlapping task-switch controls did not mount');
    });
    await act(async () => {
      mountedP3Controls(renderer).select.props.onChange({ target: { value: 'task.cancel' } });
      await waitForMounted(() => mountedP3Controls(renderer).select.props.value === 'task.cancel', 'task.cancel did not become selectable');
      mountedP3Controls(renderer)
        .root.findByType('input')
        .props.onChange({ target: { value: 'task-b' } });
      await waitForMounted(() => mountedP3Controls(renderer).root.findByType('input').props.value === 'task-b', 'task-b did not become the target');
    });
    await act(async () => {
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(() => typeof releaseTaskBStatus === 'function', 'task-b inspection did not reach deferred status');
    });

    await act(async () => {
      mountedP3Controls(renderer)
        .root.findByType('input')
        .props.onChange({ target: { value: 'task-c' } });
      await waitForMounted(() => mountedP3Controls(renderer).root.findByType('input').props.value === 'task-c', 'task-c did not supersede task-b input');
      mountedP3Controls(renderer).button('Check retry eligibility').props.onClick();
      await waitForMounted(
        () => mountedP3Controls(renderer).select.props.value === 'task.retry' && JSON.stringify(renderer.toJSON()).includes('eligible:2/3'),
        'task-c did not win the overlapping inspection generation',
      );
    });
    releaseTaskBStatus();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.task.events').map(call => call.params.task_id),
      ['task-c'],
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.confirmation.issue').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);
    const retainedTarget = JSON.parse(
      globalThis.window.sessionStorage.getItem(`jiuwenswarm.live_voice.product_p3_task_target.v1:${encodeURIComponent(sessionId)}`),
    );
    assert.equal(retainedTarget.task_id, 'task-c');
    assert.equal(retainedTarget.correlation_id, bindings['task-c'].correlation_id);
    assert.equal(retainedTarget.task_control_binding.generation, 1);
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

test('mounted P1 applies opaque UI device choices to exact local browser routes without sending IDs to the backend', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const mediaActivations = [];
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = value => warnings.push(String(value));
  let renderer;
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      mediaActivations.push({ ...params });
      return { status: 'unavailable', reason_id: 'MOUNTED_DEVICE_ROUTE_PROBE_COMPLETE' };
    }
    throw new Error(`unexpected mounted device-selection request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-device-session', request));
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose formal P1');
      mountedAudioDeviceControls(renderer).button('Authorize and load devices').props.onClick();
      await waitForMounted(
        () => JSON.stringify(renderer.toJSON()).includes('Mounted microphone') && JSON.stringify(renderer.toJSON()).includes('Mounted speaker'),
        'page-memory device inventory did not render',
      );
    });
    const controls = mountedAudioDeviceControls(renderer);
    const inputToken = controls.token(controls.input, 'Mounted microphone');
    const outputToken = controls.token(controls.output, 'Mounted speaker');
    assert.notEqual(inputToken, 'mounted-private-input');
    assert.notEqual(outputToken, 'mounted-private-output');
    assert.equal(JSON.stringify(renderer.toJSON()).includes('mounted-private-input'), false);
    assert.equal(JSON.stringify(renderer.toJSON()).includes('mounted-private-output'), false);

    await act(async () => {
      controls.input.props.onChange({ target: { value: inputToken } });
      controls.output.props.onChange({ target: { value: outputToken } });
      await Promise.resolve();
    });
    await act(async () => {
      mountedAudioDeviceControls(renderer).button('Apply devices').props.onClick();
      await Promise.resolve();
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(() => mediaActivations.length === 1, 'exact local device route did not reach formal P1 startup');
    });

    assert.deepEqual(browser.counts.sinkIds, ['mounted-private-output']);
    assert.equal(browser.counts.constraints[0].audio.deviceId.exact, 'mounted-private-input');
    assert.equal(JSON.stringify(mediaActivations[0]).includes('mounted-private-input'), false);
    assert.equal(JSON.stringify(mediaActivations[0]).includes('mounted-private-output'), false);
    assert.equal(browser.counts.getUserMedia, 1, 'granted inventory load must not allocate a permission-probe stream');
    assert.equal(
      warnings.some(value => value.includes('MOUNTED_DEVICE_ROUTE_PROBE_COMPLETE') && value.includes('fallback=text visible=true')),
      true,
    );
    assert.equal(
      warnings.some(value => value.includes('mounted-private-input') || value.includes('mounted-private-output')),
      false,
    );
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await Promise.resolve();
      });
    }
    console.warn = originalWarn;
    browser.restore();
  }
});

test('mounted explicit P1 Start fails before media when exact P2 authority refresh is rejected', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const calls = [];
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = value => warnings.push(String(value));
  let activationCalls = 0;
  let renderer;
  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') {
      activationCalls += 1;
      if (activationCalls === 1) {
        return { ok: true, result: { status: 'active', ...params, replayed: false } };
      }
      if (activationCalls === 2) {
        throw Object.assign(new Error('media activation trust expired'), {
          code: 'PERMISSION_DENIED',
          reason: 'MEDIA_PRODUCT_ACTIVATION_UNTRUSTED',
        });
      }
      throw new Error('failed refresh must not allocate a successor P2 route');
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    throw new Error(`authority refresh failure must not call ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-authority-refresh-session', request));
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose formal P1');
    });
    await act(async () => {
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(() => calls.some(call => call.method === 'live_voice.composition.p2.close'), 'failed authority refresh did not enter exact cleanup');
    });

    assert.equal(activationCalls, 2, 'failed refresh must not allocate a successor P2 route');
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 0);
    assert.equal(browser.counts.getUserMedia, 0);
    const refreshIndex = calls.findIndex((call, index) => call.method === 'live_voice.composition.p2.activate' && index > 0);
    const closeIndex = calls.findIndex(call => call.method === 'live_voice.composition.p2.close');
    assert.equal(refreshIndex < closeIndex, true);
    assert.equal(
      warnings.some(value => value.includes('MEDIA_PRODUCT_ACTIVATION_UNTRUSTED') && value.includes('fallback=text visible=true')),
      true,
    );
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await Promise.resolve();
      });
    }
    console.warn = originalWarn;
    browser.restore();
  }
});

for (const refreshFailure of ['new-route', 'ambiguous-transport']) {
  test(`mounted ${refreshFailure} authority refresh closes exact P2 before route recovery and opens no media`, async () => {
    const i18n = await createI18n();
    const browser = installP1BrowserEnvironment();
    const calls = [];
    let activationCalls = 0;
    let renderer;
    const request = async (method, params) => {
      calls.push({ method, params: { ...params } });
      if (method === 'live_voice.composition.p2.activate') {
        activationCalls += 1;
        if (activationCalls === 2 && refreshFailure === 'ambiguous-transport') {
          throw Object.assign(new Error('refresh response was lost'), { code: 'WS_NOT_READY' });
        }
        if (activationCalls > 2) throw new Error('failed refresh must not allocate a successor P2 route');
        return { ok: true, result: { status: 'active', ...params, replayed: false } };
      }
      if (method === 'live_voice.composition.p2.close') {
        return { ok: true, result: { status: 'closed', ...params } };
      }
      if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
        return new Promise(() => {});
      }
      if (method === 'live_voice.media.activate') {
        throw new Error('failed authority refresh must not activate media');
      }
      throw new Error(`unexpected authority recovery request: ${method}`);
    };

    try {
      await act(async () => {
        renderer = create(mountedP1Element(i18n, `mounted-p1-${refreshFailure}-session`, request));
        await Promise.resolve();
      });
      await act(async () => {
        await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose formal P1');
        formalVoiceStartButton(renderer).props.onClick();
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.composition.p2.close'),
          'failed authority refresh did not close its exact P2 owner',
        );
      });

      const activateIndices = calls.map((call, index) => (call.method === 'live_voice.composition.p2.activate' ? index : -1)).filter(index => index >= 0);
      const closeIndex = calls.findIndex(call => call.method === 'live_voice.composition.p2.close');
      assert.equal(activateIndices.length, 2, 'failed refresh must not allocate a successor P2 route');
      assert.equal(activateIndices[1] < closeIndex, true);
      assert.equal(browser.counts.getUserMedia, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 0);

      await act(async () => {
        renderer.unmount();
        renderer = null;
        await Promise.resolve();
      });
      await act(async () => {
        renderer = create(mountedP1Element(i18n, `mounted-p1-${refreshFailure}-session`, request));
        await new Promise(resolve => setTimeout(resolve, 50));
      });
      assert.equal(activationCalls, 2, 'durable state-loss barrier must block every successor after reload');
      assert.equal(browser.counts.getUserMedia, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 0);
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
}

test('mounted P2 close fences a successful in-flight authority refresh before microphone acquisition', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const calls = [];
  let activationCalls = 0;
  let resolveRefresh;
  let refreshParams = null;
  const refresh = new Promise(resolve => {
    resolveRefresh = resolve;
  });
  let renderer;
  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') {
      activationCalls += 1;
      if (activationCalls === 1) {
        return { ok: true, result: { status: 'active', ...params, replayed: false } };
      }
      refreshParams = { ...params };
      return refresh;
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    throw new Error(`close-fenced authority refresh must not call ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-refresh-close-session', request));
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose formal P1');
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(() => activationCalls === 2, 'explicit Start did not enter authority refresh');
    });
    await act(async () => {
      renderer.unmount();
      renderer = null;
      assert.notEqual(refreshParams, null);
      resolveRefresh({
        ok: true,
        result: {
          status: 'active',
          ...refreshParams,
          replayed: true,
        },
      });
      await new Promise(resolve => setTimeout(resolve, 20));
    });

    assert.equal(browser.counts.getUserMedia, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.close').length, 1);
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

test('mounted P2 close cancels pending getUserMedia and stops its late stream before any media activation', async () => {
  const i18n = await createI18n();
  let resolveUserMedia;
  const userMedia = new Promise(resolve => {
    resolveUserMedia = resolve;
  });
  let createLateStream = null;
  const browser = installP1BrowserEnvironment({
    getUserMedia: ({ createStream }) => {
      createLateStream = createStream;
      return userMedia;
    },
  });
  const calls = [];
  const activateP2 = createMountedP2ActivationResponder();
  let renderer;
  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      throw new Error('cancelled pending microphone acquisition must not activate media');
    }
    throw new Error(`unexpected pending-microphone request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p1-pending-microphone-session', request));
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose formal P1');
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(() => browser.counts.getUserMedia === 1, 'explicit Start did not enter microphone acquisition');
    });
    await act(async () => {
      renderer.unmount();
      renderer = null;
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.close').length === 1,
        'P2 close did not settle after cancelling pending microphone acquisition',
      );
    });

    assert.notEqual(createLateStream, null);
    resolveUserMedia(createLateStream());
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(browser.counts.stoppedTracks, 1, 'the fenced late microphone stream must be physically stopped');
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.activate').length, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.close').length, 1);
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

test('mounted Product start fails closed while devicechange verification owns the selected route', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const productVoiceControlRef = { current: null };
  const mediaActivations = [];
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = value => warnings.push(String(value));
  let renderer;
  let resolveRefresh;
  const refresh = new Promise(resolve => {
    resolveRefresh = resolve;
  });
  const currentDevices = [
    { kind: 'audioinput', deviceId: 'mounted-private-input', label: 'Mounted microphone' },
    { kind: 'audiooutput', deviceId: 'mounted-private-output', label: 'Mounted speaker' },
  ];
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    if (method === 'live_voice.media.activate') {
      mediaActivations.push({ ...params });
      return { status: 'unavailable', reason_id: 'UNEXPECTED_REFRESHING_PRODUCT_START' };
    }
    throw new Error(`unexpected mounted refreshing-device request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedP1Element(i18n, 'mounted-p1-refreshing-device-session', request, {
          productVoiceControlRef,
        }),
      );
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose formal P1');
      mountedAudioDeviceControls(renderer).button('Authorize and load devices').props.onClick();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Mounted microphone'), 'page-memory device inventory did not render');
    });
    const controls = mountedAudioDeviceControls(renderer);
    const inputToken = controls.token(controls.input, 'Mounted microphone');
    await act(async () => {
      controls.input.props.onChange({ target: { value: inputToken } });
      await Promise.resolve();
      mountedAudioDeviceControls(renderer).button('Apply devices').props.onClick();
      await Promise.resolve();
    });

    browser.setEnumerateDevices(() => refresh);
    await act(async () => {
      browser.emitDeviceChange();
      await waitForMounted(() => JSON.stringify(renderer.toJSON()).includes('Checking current devices...'), 'devicechange verification did not become visible');
    });
    assert.equal(formalVoiceStartButton(renderer).props.disabled, true);
    assert.equal(productVoiceControlRef.current !== null, true);

    await act(async () => {
      await productVoiceControlRef.current.start();
      await Promise.resolve();
    });
    assert.equal(mediaActivations.length, 0);
    assert.equal(browser.counts.getUserMedia, 0);
    assert.deepEqual(browser.counts.sinkIds, []);
    assert.equal(JSON.stringify(renderer.toJSON()).includes('AUDIO_DEVICE_REFRESH_IN_PROGRESS'), true);
    assert.equal(
      warnings.some(value => value.includes('AUDIO_DEVICE_REFRESH_IN_PROGRESS') && value.includes('fallback=text visible=true')),
      true,
    );
    assert.equal(
      warnings.some(value => value.includes('mounted-private-input') || value.includes('mounted-private-output')),
      false,
    );

    await act(async () => {
      resolveRefresh(currentDevices);
      await waitForMounted(
        () => !JSON.stringify(renderer.toJSON()).includes('Checking current devices...'),
        'verified device route did not leave refreshing status',
      );
    });
  } finally {
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await Promise.resolve();
      });
    }
    console.warn = originalWarn;
    browser.restore();
  }
});

test('mounted P1 cleanup singleflight fences two retained Start attempts until exact close, then allocates one successor', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const calls = [];
  const states = [];
  const projectedMessages = [];
  const mediaActivations = [];
  const mediaCloses = [];
  let productBinding = null;
  let resolveFirstClose = null;
  let renderer;
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    calls.push({ method, params });
    if (method === 'live_voice.composition.p2.activate') {
      const activated = activateP2(params);
      productBinding = {
        session_id: params.session_id,
        correlation_id: params.correlation_id,
        interaction_id: params.interaction_id,
        activation_id: params.activation_id,
        activation_generation: params.activation_generation,
      };
      return activated;
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
          media_ticket: 'S'.repeat(43),
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
      renderer = create(
        mountedP1Element(i18n, 'mounted-p1-singleflight-session', request, {
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: event => projectedMessages.push(event),
        }),
      );
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'P2 did not expose the formal P1 Start control');
    });
    await act(async () => {
      formalVoiceStartButton(renderer).props.onClick();
      await waitForMounted(
        () =>
          mediaCloses.length === 1 &&
          JSON.stringify(renderer.toJSON()).includes('cleanup_pending') &&
          states.some(
            state =>
              state.p1_status === 'cleanup_pending' &&
              state.recovery_diagnostic?.seam === 'activation' &&
              state.recovery_diagnostic.disposition === 'retrying',
          ),
        'the first failed exact close did not settle the old P1 owner as cleanup_pending',
      );
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(mediaActivations.length, 1);
    assert.match(JSON.stringify(renderer.toJSON()), /cleanup_pending/);
    const cleanupState = states.find(
      state =>
        state.p1_status === 'cleanup_pending' &&
        state.recovery_diagnostic?.seam === 'activation' &&
        state.recovery_diagnostic.disposition === 'retrying',
    );
    assert.ok(productBinding);
    assert.deepEqual(cleanupState.recovery_diagnostic, {
      seam: 'activation',
      disposition: 'retrying',
      reason: 'FORMAL_P1_ROUTE_FAILED',
      ...productBinding,
      response_id: null,
      response_generation: null,
    });
    assert.equal(
      calls.some(call =>
        call.method.includes('task.cancel') ||
        call.method.includes('task.mutate') ||
        call.method === 'live_voice.composition.p3.mutate' ||
        call.method === 'live_voice.composition.p2.presentation.ack'
      ),
      false,
      'P1 cleanup diagnostics must not acquire Task or presentation authority',
    );
    assert.equal(projectedMessages.length, 0, 'P1 cleanup diagnostics must not create dialogue history');

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
      try {
        await waitForMounted(
          () => browser.counts.getUserMedia === 2 && mediaActivations.length === 2,
          'the retained Start did not allocate its single successor after exact close',
        );
      } catch (error) {
        assert.fail(`${error.message}; methods=${calls.map(call => call.method).join(',')}; states=${states.slice(-12).map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}`).join(',')}`);
      }
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(browser.counts.getUserMedia, 2, 'two retained clicks must allocate exactly one successor microphone');
    assert.equal(mediaActivations.length, 2, 'two retained clicks must allocate exactly one successor media activation');
    assert.equal(mediaActivations[0].capture_generation, 1);
    assert.equal(mediaActivations[1].capture_generation, 1, 'the successor must be a new owner, not a concurrent generation on the old owner');
    assert.notEqual(mediaActivations[1].track_id, mediaActivations[0].track_id);
    assert.notDeepEqual(
      states.at(-1)?.recovery_diagnostic,
      cleanupState.recovery_diagnostic,
      'successful exact cleanup must clear the predecessor recovery diagnostic before successor publication',
    );
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
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      p2Activations.push({ ...params });
      return activateP2(params);
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
        media_ticket: 'S'.repeat(43),
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
        'old Session P1 did not retain its failed exact authority',
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
        'replacement Session did not acquire its current P2 binding',
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
      true,
    );
    assert.equal(
      p2Closes.some(close => close.session_id === 'mounted-p1-old-session'),
      true,
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

test('mounted late old-Session capture cleanup cannot close or rotate the replacement Session activation', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const controlRef = { current: null };
  const p2Activations = [];
  const p2Closes = [];
  const mediaActivations = [];
  const mediaCloses = [];
  let resolveOldMediaClose = null;
  let oldSessionCleanup = null;
  let renderer;
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      p2Activations.push({ ...params });
      return activateP2(params);
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
      return {
        status: 'active',
        reason_id: null,
        subject_id: `mounted-session-scoped-${params.session_id}`,
        endpoint_path: '/api/v1/live_voice/media',
        media_ticket: 'S'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        binding: {},
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: false },
      };
    }
    if (method === 'live_voice.media.close') {
      mediaCloses.push({ ...params });
      if (params.session_id === 'mounted-session-scoped-old' && mediaCloses.filter(close => close.session_id === params.session_id).length === 1) {
        return new Promise(resolve => {
          resolveOldMediaClose = () => resolve({ status: 'closed', reason_id: null, ...params });
        });
      }
      return { status: 'closed', reason_id: null, ...params };
    }
    throw new Error(`unexpected mounted session-scoped request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-session-scoped-old', request, {
        productVoiceControlRef: controlRef,
      }));
    });
    await act(async () => {
      await waitForMounted(() => formalVoiceStartButton(renderer).props.disabled === false, 'old Session did not expose formal P1 Start');
      void controlRef.current.start();
      await waitForMounted(
        () => mediaActivations.some(activation => activation.session_id === 'mounted-session-scoped-old'),
        'old Session did not start capture',
      );
    });

    await act(async () => {
      renderer.update(mountedP1Element(i18n, 'mounted-session-scoped-new', request, {
        productVoiceControlRef: controlRef,
      }));
      await waitForMounted(
        () =>
          p2Activations.some(activation => activation.session_id === 'mounted-session-scoped-new') &&
          mediaCloses.some(close => close.session_id === 'mounted-session-scoped-old'),
        'replacement Session did not activate while exact old capture cleanup remained pending',
      );
      oldSessionCleanup = controlRef.current.closeSession('mounted-session-scoped-old');
      await Promise.resolve();
    });

    assert.equal(typeof resolveOldMediaClose, 'function');
    assert.equal(
      p2Closes.some(close => close.session_id === 'mounted-session-scoped-new'),
      false,
      'a late parent cleanup for the old Session must not close the replacement P2 activation',
    );

    await act(async () => {
      resolveOldMediaClose();
      await oldSessionCleanup;
      await Promise.resolve();
    });
    assert.equal(
      p2Closes.some(close => close.session_id === 'mounted-session-scoped-new'),
      false,
      'settling exact old capture cleanup must not rotate the replacement P2 activation',
    );

    await act(async () => {
      void controlRef.current.start();
      await waitForMounted(
        () => mediaActivations.some(activation => activation.session_id === 'mounted-session-scoped-new'),
        'replacement Session did not start capture after exact old cleanup settled',
      );
    });
    assert.equal(browser.counts.getUserMedia, 2, 'replacement Session must allocate exactly one successor microphone');
    assert.equal(
      mediaActivations.filter(activation => activation.session_id === 'mounted-session-scoped-new').length,
      1,
    );
    assert.equal(
      p2Closes.some(close => close.session_id === 'mounted-session-scoped-new'),
      false,
    );
  } finally {
    if (resolveOldMediaClose !== null) resolveOldMediaClose();
    if (renderer) {
      await act(async () => {
        renderer.unmount();
        await new Promise(resolve => setTimeout(resolve, 20));
      });
    }
    browser.restore();
  }
});

test('mounted old-Session P2 cleanup failure cannot publish recovery state into the replacement Session', async () => {
  const i18n = await createI18n();
  const browser = installP1BrowserEnvironment();
  const oldSessionId = 'mounted-p2-cleanup-old-session';
  const newSessionId = 'mounted-p2-cleanup-new-session';
  const states = [];
  const p2Activations = [];
  const p2Closes = [];
  let oldCloseFailuresRemaining = 3;
  let renderer;
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      p2Activations.push({ ...params });
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      p2Closes.push({ ...params });
      if (params.session_id === oldSessionId && oldCloseFailuresRemaining > 0) {
        oldCloseFailuresRemaining -= 1;
        throw { code: 'UNAVAILABLE' };
      }
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
      return new Promise(() => {});
    }
    throw new Error(`unexpected mounted cross-Session P2 cleanup request: ${method}`);
  };
  const element = sessionId => mountedP1Element(i18n, sessionId, request, {
    onProductVoiceStateChange: state => states.push({ sessionId, state }),
  });

  try {
    await act(async () => {
      renderer = create(element(oldSessionId));
      await waitForMounted(
        () => p2Activations.some(activation => activation.session_id === oldSessionId),
        'old Session did not activate P2',
      );
    });
    await act(async () => {
      renderer.update(element(newSessionId));
      await waitForMounted(
        () => oldCloseFailuresRemaining === 0,
        'replacement Session did not exhaust the old P2 close failure',
      );
      await waitForMounted(
        () => p2Activations.some(activation => activation.session_id === newSessionId),
        'replacement Session did not activate after the bounded old P2 cleanup failure',
        3_000,
      );
    });

    assert.equal(
      p2Closes.filter(close => close.session_id === oldSessionId).length,
      3,
      'the mounted schedule must exhaust the old P2 owner bounded close failure before successor activation',
    );
    assert.equal(
      states.some(
        entry =>
          entry.sessionId === newSessionId &&
          entry.state.recovery_diagnostic?.session_id === oldSessionId,
      ),
      false,
      'the old P2 cleanup failure must have zero recovery-UI effect in the replacement Session',
    );
    assert.equal(
      states.filter(entry => entry.sessionId === newSessionId).at(-1)?.state.recovery_diagnostic,
      null,
      'replacement activation must not retain the old-Session diagnostic',
    );
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
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return activateP2(params);
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
        media_ticket: 'S'.repeat(43),
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
        'unmount case did not retain the failed old P1 exact authority',
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
  const activateP2 = createMountedP2ActivationResponder();
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      return activateP2(params);
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
        media_ticket: 'S'.repeat(43),
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
        'the failed exact close did not retain cleanup_pending truth',
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

test('mounted refresh retires a presentation ACK, opens a successor, and unmount closes only owned routes', async () => {
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
        assert.deepEqual(checkpoint.retired_presentation_acks, [operation]);
        assert.equal(options.requestId, operation.request_id);
        return new Promise(() => {});
      }
      if (method === 'live_voice.composition.p2.activate') {
        return {
          ok: true,
          result: {
            status: 'active',
            ...params,
            replayed: params.activation_generation === binding.activation_generation,
          },
        };
      }
      if (method === 'live_voice.composition.p2.close') {
        return { ok: true, result: { status: 'closed', ...params } };
      }
      if (method === 'live_voice.composition.p2.notification.next' || method === 'live_voice.task.list') {
        return new Promise(() => {});
      }
      throw new Error(`pending refresh must not call ${method}`);
    };
    await act(async () => {
      renderer = create(mountedP3Element(i18n, binding.session_id, request));
    });
    await act(async () => {
      await waitForMounted(
        () => effects.some(([method, params]) => method === 'live_voice.composition.p2.activate' && params.activation_generation === 2),
        'retired ACK blocked the refreshed successor activation',
      );
      await waitForMounted(() => effects.filter(([method]) => method === operation.method).length === 1, 'retired ACK did not begin exact background replay');
    });
    await act(async () => {
      renderer.unmount();
      renderer = null;
      await waitForMounted(
        () => effects.some(([method, params]) => method === 'live_voice.composition.p2.close' && params.activation_generation === 2),
        'unmount did not close the exact successor route',
      );
    });

    assert.equal(effects.filter(([method]) => method === operation.method).length, 1);
    assert.deepEqual(
      effects.filter(([method]) => method === 'live_voice.composition.p2.activate').map(([, params]) => params.activation_generation),
      [1, 2],
    );
    assert.deepEqual(
      effects.filter(([method]) => method === 'live_voice.composition.p2.close').map(([, params]) => params.activation_generation),
      [1, 2],
    );
    const checkpoint = JSON.parse(values.get(key));
    assert.equal(checkpoint.phase, 'closed');
    assert.equal(checkpoint.pending_operation, null);
    assert.deepEqual(checkpoint.retired_presentation_acks, [operation]);
    assert.equal(checkpoint.binding.activation_generation, 2);
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
        'current route did not activate before CAS takeover',
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
        'recovered task instruction was not restored',
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
      },
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

test('mounted same-tab refresh stays fail-closed until Listen again exactly cleans generation 12 and captures on its successor', async () => {
  const i18n = await createI18n();
  const binding = {
    session_id: 'web_1a0264434af_931825e3380f',
    correlation_id: 'integrated-web-7f885fb1-9e2a-4381-9051-466eb586662d-web_1a0264434af_931825e3380f-5e24a88e-36cf-478a-8d87-9c3c076a4a5c',
    interaction_id: 'web-interaction-7f885fb1-9e2a-4381-9051-466eb586662d-web_1a0264434af_931825e3380f-5e24a88e-36cf-478a-8d87-9c3c076a4a5c',
    activation_id: 'web-activation-mounted-result-unknown-12',
    activation_generation: 12,
  };
  let activeP2Binding = { ...binding };
  let activeMediaBinding = null;
  let mediaGeneration = 0;
  let deliveredKeepalive = false;
  const calls = [];
  const states = [];
  const controlRef = { current: null };
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const key = `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(binding.session_id)}`;
  globalThis.window.sessionStorage.setItem(key, JSON.stringify({
    schema: 'live-voice.product-p2-activation-journal.v2',
    revision: 7,
    client_instance_id: 'mounted-result-unknown-client',
    session_id: binding.session_id,
    correlation_id: binding.correlation_id,
    interaction_id: binding.interaction_id,
    binding,
    phase: 'result_unknown',
    last_generation: binding.activation_generation,
    pending_operation: null,
    recovery_owner_id: null,
    recovery_token: null,
    recovery_epoch: 0,
  }));
  const sameP2Binding = params => activeP2Binding !== null
    && params.session_id === activeP2Binding.session_id
    && params.correlation_id === activeP2Binding.correlation_id
    && params.interaction_id === activeP2Binding.interaction_id
    && params.activation_id === activeP2Binding.activation_id
    && params.activation_generation === activeP2Binding.activation_generation;
  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') {
      const replayed = sameP2Binding(params);
      if (!replayed) {
        assert.equal(activeP2Binding, null, 'a successor P2 route must wait for exact predecessor cleanup');
        activeP2Binding = { ...params };
      }
      return { ok: true, result: { status: 'active', ...params, replayed } };
    }
    if (method === 'live_voice.composition.p2.close') {
      assert.equal(sameP2Binding(params), true, 'P2 cleanup must target the exact active binding');
      activeP2Binding = null;
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      if (deliveredKeepalive) return new Promise(() => {});
      deliveredKeepalive = true;
      return {
        ok: true,
        result: {
          status: 'notification',
          ...params,
          kind: 'transport.keepalive',
          response: null,
          agent_event: null,
          progress_event: null,
          presentation_unit: null,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      mediaGeneration += 1;
      activeMediaBinding = mountedMediaBinding(params, mediaGeneration);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-result-unknown-media-${mediaGeneration}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'R'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'fallback',
          requested_capability: 'media.end_of_turn.v1',
          reason_id: 'MEDIA_END_OF_TURN_FEATURE_OFF',
          fallback: 'manual',
          visible: true,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      activeMediaBinding = null;
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    throw new Error(`unexpected result-unknown retry request: ${method}`);
  };
  const element = () => mountedP1Element(i18n, binding.session_id, request, {
    productVoiceControlRef: controlRef,
    onProductVoiceStateChange: state => states.push(state),
  });
  let first;
  let second;
  try {
    await act(async () => {
      first = create(element());
      await waitForMounted(
        () => states.some(state => state.recovery_diagnostic?.reason === 'P2_REFRESH_RECONCILIATION_REQUIRED'),
        'first refresh did not publish the retained generation-12 barrier',
      );
    });
    assert.equal(
      calls.filter(call => call.method.startsWith('live_voice.composition.p2.') || call.method.startsWith('live_voice.media.')).length,
      0,
      'an automatic refresh must retain zero P2/media effects for generic unknown truth',
    );
    assert.equal(JSON.parse(globalThis.window.sessionStorage.getItem(key)).phase, 'result_unknown');

    await act(async () => {
      first.unmount();
      first = null;
      second = create(element());
      await waitForMounted(
        () => states.filter(state => state.recovery_diagnostic?.reason === 'P2_REFRESH_RECONCILIATION_REQUIRED').length >= 2,
        'second same-tab refresh did not retain the exact barrier',
      );
    });
    assert.equal(
      calls.filter(call => call.method.startsWith('live_voice.composition.p2.') || call.method.startsWith('live_voice.media.')).length,
      0,
      'repeated F5 recovery must not guess or duplicate an old P2/media effect',
    );

    await act(async () => {
      await controlRef.current.start();
    });
    await act(async () => {
      await waitForMounted(
        () => browser.counts.getUserMedia === 1,
        `Listen again did not recover P2 and start successor capture; calls=${JSON.stringify(calls)} states=${JSON.stringify(states.slice(-6))} journal=${globalThis.window.sessionStorage.getItem(key)}`,
      );
    });

    const p2Calls = calls.filter(call => call.method === 'live_voice.composition.p2.activate' || call.method === 'live_voice.composition.p2.close');
    assert.deepEqual(
      p2Calls.slice(0, 3).map(call => [call.method, call.params.activation_generation]),
      [
        ['live_voice.composition.p2.activate', 12],
        ['live_voice.composition.p2.close', 12],
        ['live_voice.composition.p2.activate', 13],
      ],
    );
    assert.equal(
      p2Calls.filter(call => call.method === 'live_voice.composition.p2.close' && call.params.activation_generation === 12).length,
      1,
      'the exact old activation must close once',
    );
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 1);
    assert.equal(calls.some(call => call.method.includes('submit') || call.method.includes('presentation.ack')), false);
    const recoveredJournal = JSON.parse(globalThis.window.sessionStorage.getItem(key));
    assert.equal(recoveredJournal.phase, 'active');
    assert.equal(recoveredJournal.binding.activation_generation, 13);
    assert.equal(states.at(-1).recovery_diagnostic, null);
  } finally {
    if (first) first.unmount();
    if (second) {
      await act(async () => {
        second.unmount();
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
  const recoveryStates = [];
  let retryableActivationAttempts = 0;
  const retryActivationIds = [];
  let missingReplayCloseFailuresRemaining = 3;
  let deferredRaceResolve = null;
  let deferredRaceReject = null;
  const request = async (method, params) => {
    if (method === 'live_voice.composition.p2.activate') {
      if (params.session_id === 'mounted-retry-session') {
        retryActivationIds.push(params.activation_id);
      }
      if (params.session_id === 'mounted-retry-session' && retryableActivationAttempts++ === 0) {
        effects.push(['activate-retryable', params.session_id, params.activation_generation, params.activation_id]);
        throw { code: 'WS_NOT_READY' };
      }
      if (params.session_id === 'mounted-terminal-reason-session') {
        throw Object.assign(new Error('provider secret must remain private'), {
          reason: 'provider secret must remain private',
        });
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
      if (params.session_id === 'mounted-reject-race-session' && params.activation_id === 'web-activation-reject-race-1') {
        return new Promise((_, reject) => {
          deferredRaceReject = reject;
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
        onProductVoiceStateChange: state => recoveryStates.push({ sessionId, state }),
      }),
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
    }),
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
      true,
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
      ],
    );
    assert.deepEqual(retryActivationIds.slice(0, 2), [retryActivationIds[0], retryActivationIds[0]]);
    assert.notEqual(retryActivationIds[2], retryActivationIds[0]);
    const activationDiagnostic = recoveryStates.find(
      entry => entry.sessionId === 'mounted-retry-session' && entry.state.recovery_diagnostic?.seam === 'activation',
    )?.state.recovery_diagnostic;
    assert.equal(activationDiagnostic?.disposition, 'retrying');
    assert.equal(activationDiagnostic?.reason, 'P2_REFRESH_RECONCILIATION_REQUIRED');
    assert.equal(activationDiagnostic?.session_id, 'mounted-retry-session');
    assert.equal(activationDiagnostic?.activation_id, retryActivationIds[0]);
    assert.equal(activationDiagnostic?.activation_generation, 1);
    assert.equal(
      recoveryStates.filter(entry => entry.sessionId === 'mounted-retry-session').at(-1).state.recovery_diagnostic,
      null,
    );
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
      }),
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
      ],
    );
    assert.equal(missingReplayCloseFailuresRemaining, 0);
    assert.equal(activeBindings.get('mounted-missing-replay-session').activation_generation, 1);
    const retainedMissingReplayJournal = JSON.parse(
      values.get(`jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(missingReplayBinding.session_id)}`),
    );
    assert.equal(retainedMissingReplayJournal.phase, 'closing_unconfirmed');
    assert.deepEqual(retainedMissingReplayJournal.binding, missingReplayBinding);
    assert.equal(
      missingReplayEffects.some(([kind, , generation]) => kind === 'activate' && generation === 2),
      false,
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
      ],
    );
    assert.equal(activeBindings.get('mounted-missing-replay-session').activation_generation, 2);
    const recoveredMissingReplayJournal = JSON.parse(
      values.get(`jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(missingReplayBinding.session_id)}`),
    );
    assert.equal(recoveredMissingReplayJournal.phase, 'active');
    assert.equal(recoveredMissingReplayJournal.binding.activation_generation, 2);
    assert.equal(
      missingReplayEffects.some(([kind, , generation]) => (kind === 'close' || kind === 'close-retryable') && generation === 2),
      false,
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
      }),
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
      false,
    );
    assert.equal(
      effects.some(([kind, sessionId, generation]) => kind === 'close' && sessionId === 'mounted-race-session' && generation === 1),
      true,
    );
    assert.equal(activeBindings.has('mounted-switched-session'), true);

    await act(async () => {
      raced.unmount();
      raced = null;
      await new Promise(resolve => setTimeout(resolve, 40));
    });
    const rejectRaceBinding = {
      session_id: 'mounted-reject-race-session',
      correlation_id: 'integrated-web-reject-race',
      interaction_id: 'web-interaction-reject-race',
      activation_id: 'web-activation-reject-race-1',
      activation_generation: 1,
    };
    activeBindings.set(rejectRaceBinding.session_id, { ...rejectRaceBinding });
    values.set(
      `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(rejectRaceBinding.session_id)}`,
      JSON.stringify({
        schema: 'live-voice.product-p2-activation-journal.v1',
        client_instance_id: 'reject-race-client',
        session_id: rejectRaceBinding.session_id,
        correlation_id: rejectRaceBinding.correlation_id,
        interaction_id: rejectRaceBinding.interaction_id,
        binding: rejectRaceBinding,
        phase: 'active',
        last_generation: 1,
      }),
    );
    await act(async () => {
      raced = create(element(rejectRaceBinding.session_id));
      await new Promise(resolve => setTimeout(resolve, 20));
    });
    assert.equal(typeof deferredRaceReject, 'function');
    const rejectBoundary = recoveryStates.length;
    await act(async () => {
      raced.update(element('mounted-reject-race-successor-session'));
      deferredRaceReject(Object.assign(new Error('provider secret must remain private'), {
        code: 'WS_DISCONNECTED',
        reason: 'provider secret must remain private',
      }));
      await new Promise(resolve => setTimeout(resolve, 80));
    });
    assert.equal(
      effects.some(([kind, sessionId, generation]) => kind === 'close' && sessionId === rejectRaceBinding.session_id && generation === 1),
      true,
    );
    assert.equal(activeBindings.has('mounted-reject-race-successor-session'), true);
    assert.equal(
      recoveryStates
        .slice(rejectBoundary)
        .some(entry => entry.state.recovery_diagnostic?.session_id === rejectRaceBinding.session_id),
      false,
    );
    assert.doesNotMatch(JSON.stringify(recoveryStates.slice(rejectBoundary)), /provider secret/i);

    await act(async () => {
      raced.unmount();
      raced = null;
      await new Promise(resolve => setTimeout(resolve, 40));
    });
    const terminalReasonBoundary = recoveryStates.length;
    await act(async () => {
      raced = create(element('mounted-terminal-reason-session'));
      await new Promise(resolve => setTimeout(resolve, 100));
    });
    const terminalActivationDiagnostic = recoveryStates
      .slice(terminalReasonBoundary)
      .find(entry => entry.sessionId === 'mounted-terminal-reason-session' && entry.state.recovery_diagnostic?.seam === 'activation')
      ?.state.recovery_diagnostic;
    assert.ok(
      terminalActivationDiagnostic,
      `terminal activation diagnostic was not projected: ${JSON.stringify(recoveryStates.slice(terminalReasonBoundary).map(entry => ({
        sessionId: entry.sessionId,
        activation: entry.state.p2_activation,
        diagnostic: entry.state.recovery_diagnostic,
      })))}`,
    );
    assert.equal(terminalActivationDiagnostic?.disposition, 'terminal');
    assert.equal(terminalActivationDiagnostic?.reason, 'P2_REFRESH_RECONCILIATION_REQUIRED');
    assert.doesNotMatch(JSON.stringify(terminalActivationDiagnostic), /provider secret/i);
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

test('mounted hands-free bar exposes bounded playout controls while hiding legacy commands in English and Chinese', async () => {
  for (const [language, statusLabel, interruptLabel, stopLabel, exitLabel] of [
    ['en', 'Reading the response', 'Interrupt and speak', 'Stop playback', 'Exit Live Voice'],
    ['zh', '正在朗读回答', '打断并说话', '停止播放', '退出 Live Voice'],
  ]) {
    const i18n = await createI18n(language);
    let interrupts = 0;
    let stops = 0;
    let renderer;
    try {
      await act(async () => {
        renderer = create(
          React.createElement(
            I18nextProvider,
            { i18n },
            React.createElement(MountedLiveVoiceDemoBar, {
              active: true,
              available: true,
              status: 'speaking',
              interimTranscript: '',
              committedTranscript: '第二天最早的固定安排是什么？',
              editableTranscript: 'must not become editable',
              onTranscriptChange() {},
              handsFree: true,
              commandCenter: {
                route: 'task',
                taskAvailable: true,
                taskOperation: 'task.cancel',
                taskId: 'task-stale-control',
                taskStatus: 'running',
                onRouteChange() {},
                onTaskOperationChange() {},
                onTaskIdChange() {},
                onCancelTaskConfirmation() {},
              },
              onEnable() {},
              onExit() {},
              onPrimaryAction() {},
              onInterruptAndSpeak() {
                interrupts += 1;
              },
              onStopPlayback() {
                stops += 1;
              },
            }),
          ),
        );
      });
      assert.equal(renderer.root.findAllByProps({ 'data-testid': 'live-voice-command-center' }).length, 0);
      assert.equal(renderer.root.findAllByType('textarea').length, 0);
      const interrupt = renderer.root.findByProps({ 'aria-label': interruptLabel });
      const stop = renderer.root.findByProps({ 'aria-label': stopLabel });
      await act(async () => interrupt.props.onClick());
      await act(async () => stop.props.onClick());
      assert.equal(interrupts, 1);
      assert.equal(stops, 1);
      assert.equal(renderer.root.findByProps({ role: 'status' }).children.includes(statusLabel), true);
      assert.equal(renderer.root.findByProps({ className: 'live-voice-demo__transcript live-voice-demo__transcript--committed' }).children[0], '第二天最早的固定安排是什么？');
      assert.equal(renderer.root.findByProps({ 'aria-label': exitLabel }).props.type, 'button');
      await act(async () => {
        renderer.update(
          React.createElement(
            I18nextProvider,
            { i18n },
            React.createElement(MountedLiveVoiceDemoBar, {
              active: true,
              available: true,
              status: 'thinking',
              interimTranscript: '',
              committedTranscript: '第二天最早的固定安排是什么？',
              handsFree: true,
              onEnable() {},
              onExit() {},
              onPrimaryAction() {},
              onInterruptAndSpeak() {},
              onStopPlayback() {},
            }),
          ),
        );
      });
      assert.equal(renderer.root.findAllByProps({ 'aria-label': interruptLabel }).length, 0);
      assert.equal(renderer.root.findAllByProps({ 'aria-label': stopLabel }).length, 0);
    } finally {
      if (renderer) await act(async () => renderer.unmount());
    }
  }
});

test('mounted production task adapter renders distinct lifecycle states and terminal outcomes', async () => {
  for (const [language, acceptedText, runningText, completedText, failedText] of [
    ['en', 'Accepted; waiting to run', 'Running', 'Background task completed.', 'Background task did not complete successfully (outcome: failed).'],
    ['zh', '已受理，正在等待执行', '正在执行', '后台任务已完成。', '后台任务未成功完成（结果：failed）。'],
  ]) {
    const i18n = await createI18n(language);
    let renderer;
    const binding = {
      subject_id: 'mounted-adapter-subject',
      session_id: 'mounted-adapter-session',
      project_id: 'mounted-adapter-project',
      correlation_id: 'mounted-adapter-correlation',
    };
    const activation = {
      origin_id: 'mounted-adapter-origin',
      generation_id: 'mounted-adapter-generation',
      generation: 1,
    };
    const element = (state, taskProgressEvent = null) =>
      React.createElement(
        I18nextProvider,
        { i18n },
        React.createElement(MountedFormalProductLiveVoiceDemoBar, {
          active: false,
          available: true,
          status: 'idle',
          interimTranscript: '',
          committedTranscript: '',
          handsFree: true,
          surfaceState: {
            terminal_notification: null,
            adjustment_notification: null,
            task_progress_state: state,
            task_progress_event: taskProgressEvent,
            task_progress_node_ref() {},
          },
          onEnable() {},
          onExit() {},
          onPrimaryAction() {},
        }),
      );
    try {
      await act(async () => {
        renderer = create(element('accepted'));
      });
      const detail = () =>
        renderer.root.findByProps({ className: 'live-voice-demo__task-detail' }).children[0];
      assert.equal(detail(), acceptedText);
      assert.notEqual(detail(), runningText);

      await act(async () => {
        renderer.update(element('running'));
      });
      assert.equal(detail(), runningText);
      assert.notEqual(detail(), acceptedText);

      await act(async () => {
        renderer.update(element('terminal', mountedLifecycleProgress(binding, activation, {
          state: 'terminal',
          eventType: 'task.terminal',
          seq: 2,
          outcome: 'completed',
        })));
      });
      assert.equal(detail(), completedText);

      await act(async () => {
        renderer.update(element('terminal', mountedLifecycleProgress(binding, activation, {
          state: 'terminal',
          eventType: 'task.terminal',
          seq: 3,
          outcome: 'failed',
        })));
      });
      assert.equal(detail(), failedText);
    } finally {
      if (renderer) await act(async () => renderer.unmount());
    }
  }
});

test('mounted formal product carrier exposes two authoritative Tasks, replay/result lineage and separate command truth', async () => {
  const i18n = await createI18n('en');
  const selected = {
    task_id: 'task-visible-a',
    attempt_id: 'attempt-visible-a',
    attempt_number: 1,
    correlation_id: 'correlation-visible-a',
    subject_id: 'subject-visible',
    session_id: 'session-visible',
    project_id: 'project-visible',
    name: 'Visible predecessor',
    canonical_state: 'terminal',
    display_state: 'completed',
    outcome: 'completed',
    queued: false,
    admission_priority: null,
    admission_reason: null,
    event_head: 1,
    revision_number: 1,
    predecessor_task_id: null,
    successor_task_id: 'task-visible-b',
    blocking_question: null,
    progress: 'complete',
    result_availability: 'available',
    result_text: 'immutable result A',
    result_attempt_id: 'attempt-visible-a',
    replay_event_count: 2,
    replay_event_types: ['task.accepted', 'task.terminal'],
    available_operations: [],
  };
  const successor = {
    ...selected,
    task_id: 'task-visible-b',
    attempt_id: 'attempt-visible-b',
    correlation_id: 'correlation-visible-b',
    name: 'Visible successor',
    canonical_state: 'running',
    display_state: 'running',
    outcome: null,
    revision_number: 2,
    predecessor_task_id: 'task-visible-a',
    successor_task_id: null,
    result_availability: 'not_ready',
    result_text: null,
    result_attempt_id: null,
    replay_event_types: ['task.accepted', 'task.running'],
    available_operations: ['task.adjust', 'task.cancel'],
  };
  const selectedTasks = [];
  let refreshes = 0;
  let confirms = 0;
  let renderer;
  try {
    await act(async () => {
      renderer = create(
        React.createElement(
          I18nextProvider,
          { i18n },
          React.createElement(MountedFormalProductLiveVoiceDemoBar, {
            active: false,
            available: true,
            status: 'idle',
            interimTranscript: '',
            committedTranscript: '',
            handsFree: true,
            surfaceState: {
              terminal_notification: null,
              adjustment_notification: null,
              task_progress_state: null,
              task_unread_delivery: {
                task_id: successor.task_id,
                attempt_id: 'attempt-visible-b-prior',
                event_id: 'task-visible-b:event:1',
                event_seq: 1,
                acknowledgement: 'pending',
              },
              task_experience: {
                status: 'ready',
                session_id: 'session-visible',
                tasks: [selected, successor],
                selected_task_id: selected.task_id,
                collection_operations: ['task.create'],
                command: {
                  command_id: 'server-command-visible',
                  request_id: 'request-visible',
                  operation: 'task.create_successor',
                  task_id: selected.task_id,
                  attempt_id: selected.attempt_id,
                  event_head: selected.event_head,
                  revision_number: selected.revision_number,
                  phase: 'confirmation_required',
                  accepted: false,
                  applied: false,
                  terminal_outcome: selected.outcome,
                  reason: null,
                },
                reason: null,
              },
            },
            async onTaskRefresh() { refreshes += 1; },
            async onTaskSelect(taskId) { selectedTasks.push(taskId); },
            async onTaskMutation() {},
            async onTaskConfirm() { confirms += 1; },
            onEnable() {},
            onExit() {},
            onPrimaryAction() {},
          }),
        ),
      );
    });
    const panel = renderer.root.findByProps({ 'data-testid': 'formal-p3-task-experience' });
    const taskNav = panel.findByProps({ 'aria-label': 'Authoritative Tasks' });
    const rendered = JSON.stringify(renderer.toJSON());
    assert.equal(taskNav.findAllByType('button').length, 2);
    assert.match(rendered, /immutable result A/);
    assert.match(rendered, /task\.accepted → task\.terminal/);
    assert.match(rendered, /task-visible-a/);
    assert.match(rendered, /task-visible-b/);
    assert.match(rendered, /server-command-visible/);
    assert.match(rendered, /request-visible/);
    assert.match(rendered, /Accepted.*false/);
    assert.match(rendered, /Applied.*false/);
    assert.match(rendered, /Terminal outcome.*completed/);
    assert.doesNotMatch(rendered, /Unread delivery: pending/);
    const control = panel.findByProps({ className: 'live-voice-demo__p3-control' });
    const exactConfirmationButtons = panel.findAll(
      node => node.type === 'button' && node.props.children === 'Confirm exact control',
    );
    assert.equal(exactConfirmationButtons.length, 1);
    assert.equal(control.findAllByType('button')[0].props.children, 'Confirm exact control');
    assert.equal(control.findAllByType('select')[0].props.disabled, true);
    assert.equal(control.findAllByType('input')[0].props.disabled, true);
    assert.match(rendered, /Confirmation pending: the current form has not been applied/);

    await act(async () => taskNav.findAllByType('button')[1].props.onClick());
    await act(async () => panel.findByProps({ children: 'Refresh Tasks' }).props.onClick());
    await act(async () => exactConfirmationButtons[0].props.onClick());
    assert.deepEqual(selectedTasks, ['task-visible-b']);
    assert.equal(refreshes, 1);
    assert.equal(confirms, 1);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted formal P3 owner revalidates list through result before adoption and repeats the full chain on reconnect', async () => {
  const i18n = await createI18n('en');
  const browser = installP1BrowserEnvironment();
  const sessionId = 'mounted-formal-p3-owner-session';
  const scope = {
    subject_id: 'mounted-formal-p3-owner-subject',
    session_id: sessionId,
    project_id: 'mounted-formal-p3-owner-project',
    assurance: 'authenticated',
  };
  const makeTask = suffix => ({
    task_id: `mounted-formal-p3-task-${suffix}`,
    scope,
    spec: {
      name: `Mounted Task ${suffix}`,
      instruction: `Mounted instruction ${suffix}`,
      origin: {},
      context: {},
      executor_id: 'mounted-executor',
      required_capabilities: [],
      side_effect_class: 'project_mutation',
      constraints: [],
      attributes: {},
    },
    state: 'running',
    attempt_id: `mounted-formal-p3-attempt-${suffix}`,
    correlation_id: `mounted-formal-p3-correlation-${suffix}`,
    cancel_requested: false,
    dispatch_fenced: false,
    outcome: null,
    reconciliation: null,
    revision: { number: 1, predecessor_task_id: null, create_command_id: `mounted-create-${suffix}` },
    event_head: 1,
    queued: false,
    admission: null,
  });
  const tasks = [makeTask('a'), makeTask('b')];
  const timeline = [];
  const calls = [];
  const states = [];
  let holdReconnectResult = false;
  let rejectReconnectResult = false;
  let releaseReconnectResult = null;
  let renderer;
  const request = async (method, params, options) => {
    const requestId = options?.requestId ?? null;
    calls.push({ method, params: { ...params }, requestId });
    const timelineMethod = method === 'live_voice.composition.p3.progress.activate'
      ? `${method}:${params.task_id ?? 'generic'}`
      : method;
    timeline.push(`${timelineMethod}:start`);
    if (method === 'live_voice.composition.p2.activate') {
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') {
      timeline.push(`${method}:success`);
      return {
        request_id: requestId,
        ok: true,
        error: null,
        result: { tasks, cursor: null, next_cursor: null, has_more: false, limit: 100, supported_operations: ['task.create'] },
      };
    }
    if (method === 'live_voice.composition.p3.progress.activate') {
      timeline.push(`${timelineMethod}:success`);
      return {
        ok: true,
        result: mountedProgressActivation(params, {
          task_id: params.task_id ?? tasks[0].task_id,
          attempt_id: tasks[0].attempt_id,
        }),
      };
    }
    if (method === 'live_voice.composition.p3.progress.close') return { ok: true, result: { status: 'closed', ...params } };
    const task = tasks.find(candidate => candidate.task_id === params.task_id);
    assert.ok(task, `unknown mounted Task ${params.task_id}`);
    if (method === 'live_voice.task.status') {
      timeline.push(`${method}:success`);
      return {
        request_id: requestId,
        ok: true,
        error: null,
        result: {
          task,
          attempt: {
            task_id: task.task_id,
            attempt_id: task.attempt_id,
            attempt_number: 1,
            executor_id: 'mounted-executor',
            executor_ref: 'mounted-carrier',
            state: 'running',
            outcome: null,
            source_seq: 1,
          },
          admission: null,
          retry_admission: { eligible: false, reason: 'TASK_RETRY_STATE_CONFLICT', task_id: task.task_id, attempt_id: null, attempt_number: null },
          supported_operations: ['task.adjust', 'task.cancel'],
        },
      };
    }
    if (method === 'live_voice.task.events') {
      timeline.push(`${method}:success`);
      return {
        request_id: requestId,
        ok: true,
        error: null,
        result: {
          task_id: task.task_id,
          after_seq: -1,
          events: [
            {
              event_id: `${task.task_id}:event:0`, task_id: task.task_id, attempt_id: task.attempt_id, scope, seq: 0,
              event_type: 'task.accepted', state: 'accepted', outcome: null, producer: 'task_core', source_event_id: null,
              causation_id: task.revision.create_command_id, correlation_id: task.correlation_id, occurred_at: '2026-08-21T00:00:00Z', details: {},
            },
            {
              event_id: `${task.task_id}:event:1`, task_id: task.task_id, attempt_id: task.attempt_id, scope, seq: 1,
              event_type: 'task.running', state: 'running', outcome: null, producer: 'task_core', source_event_id: 'mounted-dispatch',
              causation_id: task.revision.create_command_id, correlation_id: task.correlation_id, occurred_at: '2026-08-21T00:00:01Z', details: { progress: 'mounted current Attempt' },
            },
          ],
          head_seq: 1,
          next_after_seq: null,
          has_more: false,
          limit: 500,
          truncated: false,
          cursor_replay_supported: true,
        },
      };
    }
    if (method === 'live_voice.task.result') {
      if (rejectReconnectResult) {
        rejectReconnectResult = false;
        timeline.push(`${method}:failure`);
        throw new Error('mounted reconnect result authority unavailable');
      }
      if (holdReconnectResult) {
        holdReconnectResult = false;
        await new Promise(resolve => {
          releaseReconnectResult = resolve;
        });
        releaseReconnectResult = null;
      }
      timeline.push(`${method}:success`);
      return {
        request_id: requestId,
        ok: true,
        error: null,
        result: { task_id: task.task_id, availability: 'not_ready', reason: 'TASK_RESULT_NOT_READY', task_result: null },
      };
    }
    throw new Error(`unexpected mounted formal P3 owner request: ${method}`);
  };

  const element = isConnected => mountedP3Element(i18n, sessionId, request, undefined, isConnected, undefined, {
    onProductVoiceStateChange: state => states.push(state),
  });
  try {
    await act(async () => {
      renderer = create(element(true));
      await waitForMounted(() => states.at(-1)?.task_experience.status === 'ready', 'formal P3 owner did not complete initial revalidation');
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p3.progress.activate' && call.params.task_id === tasks[0].task_id),
        'formal P3 owner did not adopt its selected durable progress route',
      );
    });
    const firstActivation = timeline.indexOf(`live_voice.composition.p3.progress.activate:${tasks[0].task_id}:start`);
    assert.ok(firstActivation > timeline.indexOf('live_voice.task.result:success'));
    assert.ok(firstActivation > timeline.indexOf('live_voice.task.events:success'));
    assert.equal(states.at(-1).task_experience.tasks.length, 2);
    assert.equal(states.at(-1).task_experience.selected_task_id, tasks[0].task_id);

    const initialLists = calls.filter(call => call.method === 'live_voice.task.list').length;
    const initialResults = calls.filter(call => call.method === 'live_voice.task.result').length;
    const initialActivations = calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length;
    const initialAcks = calls.filter(call => call.method.includes('.ack')).length;
    await act(async () => {
      renderer.update(element(false));
      await waitForMounted(() => states.at(-1)?.task_experience.status === 'disconnected', 'formal P3 owner did not disconnect');
    });
    const mutationCallsAtDisconnect = calls.filter(call => call.method === 'live_voice.composition.p3.intent' || call.method === 'live_voice.composition.p3.mutate').length;
    holdReconnectResult = true;
    await act(async () => {
      renderer.update(element(true));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.task.result').length > initialResults,
        'formal P3 owner did not reach the deferred reconnect result read',
      );
    });
    assert.equal(states.at(-1)?.task_experience.status, 'loading');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length, initialActivations);
    assert.equal(calls.filter(call => call.method.includes('.ack')).length, initialAcks);
    await act(async () => {
      assert.equal(typeof releaseReconnectResult, 'function');
      releaseReconnectResult();
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(
        () => states.at(-1)?.task_experience.status === 'ready'
          && calls.filter(call => call.method === 'live_voice.task.list').length > initialLists
          && calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length > initialActivations,
        'formal P3 owner did not activate after its fresh reconnect revalidation',
      );
    });
    const reconnectResultSuccess = timeline.lastIndexOf('live_voice.task.result:success');
    const reconnectActivation = timeline.lastIndexOf(`live_voice.composition.p3.progress.activate:${tasks[0].task_id}:start`);
    assert.ok(reconnectActivation > reconnectResultSuccess);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.intent' || call.method === 'live_voice.composition.p3.mutate').length, mutationCallsAtDisconnect);

    const activationsBeforeFailedReconnect = calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length;
    const acksBeforeFailedReconnect = calls.filter(call => call.method.includes('.ack')).length;
    await act(async () => {
      renderer.update(element(false));
      await waitForMounted(() => states.at(-1)?.task_experience.status === 'disconnected', 'formal P3 owner did not enter the second disconnect');
    });
    rejectReconnectResult = true;
    await act(async () => {
      renderer.update(element(true));
      await waitForMounted(
        () => timeline.at(-1) === 'live_voice.task.result:failure',
        'formal P3 owner did not reach the rejected reconnect result read',
      );
    });
    await act(async () => {
      await waitForMounted(
        () => states.at(-1)?.task_experience.status === 'failed',
        'formal P3 owner did not fail closed after reconnect result rejection',
      );
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.progress.activate').length, activationsBeforeFailedReconnect);
    assert.equal(calls.filter(call => call.method.includes('.ack')).length, acksBeforeFailedReconnect);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted P3 feature-off composition allocates no Task experience transport', async () => {
  const i18n = await createI18n('en');
  const calls = [];
  const states = [];
  let renderer;
  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') return { ok: true, result: { status: 'active', ...params, replayed: false } };
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    throw new Error(`feature-off mounted route must not call ${method}`);
  };
  try {
    await act(async () => {
      renderer = create(mountedP1Element(i18n, 'mounted-p3-feature-off', request, {
        onProductVoiceStateChange: state => states.push(state),
      }));
      await waitForMounted(() => states.at(-1)?.task_experience.status === 'disabled', 'mounted P3 feature-off state was not published');
    });
    assert.equal(calls.some(call => call.method.startsWith('live_voice.task.') || call.method.startsWith('live_voice.composition.p3.')), false);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted hands-free error stays separate from transcript, retries listening, and retains task activity after exit', async () => {
  const i18n = await createI18n('en');
  let retries = 0;
  let renderer;
  const common = {
    available: true,
    status: 'error',
    interimTranscript: '',
    committedTranscript: 'Move dinner to 19:00.',
    handsFree: true,
    onEnable() {},
    onExit() {},
    onPrimaryAction() {},
    onRetryListening() {
      retries += 1;
    },
  };
  try {
    await act(async () => {
      renderer = create(
        React.createElement(
          I18nextProvider,
          { i18n },
          React.createElement(MountedLiveVoiceDemoBar, {
            ...common,
            active: true,
            errorMessage: 'Voice connection recovery failed.',
          }),
        ),
      );
    });
    const transcript = renderer.root.findByProps({
      className: 'live-voice-demo__transcript live-voice-demo__transcript--committed',
    });
    assert.equal(transcript.children[0], 'Move dinner to 19:00.');
    assert.equal(renderer.root.findByProps({ role: 'alert' }).findByType('span').children[0], 'Voice connection recovery failed.');
    const retry = renderer.root.findAllByProps({ className: 'live-voice-demo__primary' })[0];
    assert.equal(retry.findByProps({ className: 'live-voice-demo__primary-label' }).children[0], 'Listen again');
    await act(async () => retry.props.onClick());
    assert.equal(retries, 1);

    await act(async () => {
      renderer.update(
        React.createElement(
          I18nextProvider,
          { i18n },
          React.createElement(MountedLiveVoiceDemoBar, {
            ...common,
            active: false,
            errorMessage: '',
            taskActivity: {
              level: 'success',
              title: 'Background task',
              detail: 'The background task is complete and its result is ready.',
            },
          }),
        ),
      );
    });
    assert.equal(renderer.root.findByProps({ className: 'live-voice-demo__task-title' }).children[0], 'Background task');
    assert.equal(renderer.root.findByProps({ className: 'live-voice-demo__task-detail' }).children[0], 'The background task is complete and its result is ready.');
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
});

test('mounted response-generation failure projects exact terminal recovery identity with zero Task authority', async () => {
  const i18n = await createI18n('en');
  const sessionId = 'mounted-response-generation-failure-session';
  const states = [];
  const calls = [];
  let binding = null;
  let delivered = false;
  let renderer;
  const browser = installP1BrowserEnvironment();

  const request = async (method, params) => {
    calls.push({ method, params: { ...params } });
    if (method === 'live_voice.composition.p2.activate') {
      binding = { ...params };
      return { ok: true, result: { status: 'active', ...params, replayed: false } };
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      if (delivered) return new Promise(() => {});
      delivered = true;
      const response = {
        interaction_id: binding.interaction_id,
        response_id: 'mounted-response-generation-failure-response',
        response_generation: 7,
      };
      return {
        ok: true,
        result: {
          status: 'notification',
          ...binding,
          kind: 'agent.error',
          response,
          agent_event: {
            event_type: 'agent.failed',
            error_reason: 'AGENT_PROVIDER_FAILURE',
          },
          presentation_unit: null,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    throw new Error(`unexpected response-generation diagnostic request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedP1Element(i18n, sessionId, request, {
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => states.some(state => state.recovery_diagnostic?.seam === 'response_generation'),
        'response-generation diagnostic was not projected',
      );
    });

    const diagnostic = states.find(state => state.recovery_diagnostic?.seam === 'response_generation')?.recovery_diagnostic;
    assert.deepEqual(diagnostic, {
      seam: 'response_generation',
      disposition: 'terminal',
      reason: 'AGENT_PROVIDER_FAILURE',
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: binding.interaction_id,
      activation_id: binding.activation_id,
      activation_generation: binding.activation_generation,
      response_id: 'mounted-response-generation-failure-response',
      response_generation: 7,
    });
    assert.equal(
      calls.some(call => call.method.includes('task.cancel') || call.method.includes('task.mutate') || call.method === 'live_voice.composition.p3.mutate'),
      false,
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted terminal notification replays its exact P2 observation after Live Voice creates a media owner', async () => {
  const i18n = await createI18n('zh');
  const sessionId = 'mounted-terminal-media-handoff-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  let activeMediaBinding = null;
  let notificationRequestId = null;
  let notificationParams = null;
  let notificationResponse = null;
  let speechAuthorized = false;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();

  const request = async (method, params, options) => {
    const requestId = options?.requestId ?? null;
    calls.push({ method, params: { ...params }, requestId });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (notificationRequestId === null) {
        notificationRequestId = requestId;
        notificationParams = { ...params };
        notificationResponse = {
          ok: true,
          result: {
            status: 'notification',
            ...params,
            kind: 'agent.output',
            response: {
              interaction_id: params.interaction_id,
              response_id: 'mounted-terminal-media-handoff-response',
              response_generation: 12,
            },
            agent_event: {
              event_type: 'chat.final',
              source_provenance: 'server.task_notification',
              text: '后台任务已完成，结果已经生成。',
            },
            presentation_unit: {
              surface: 'text',
              unit_id: 'mounted-terminal-media-handoff-unit',
              seq: 0,
              content_ref: `sha256:${'a'.repeat(64)}`,
            },
          },
        };
        return notificationResponse;
      }
      if (requestId === notificationRequestId) {
        assert.deepEqual(params, notificationParams);
        assert.notEqual(activeMediaBinding, null, 'notification replay must follow media activation');
        speechAuthorized = true;
        return notificationResponse;
      }
      return new Promise(() => {});
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      return {
        request_id: requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(params, 1);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'mounted-terminal-media-handoff-subject',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'H'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: 'mounted-terminal-media-handoff-receipt',
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      if (!speechAuthorized) {
        throw Object.assign(new Error('speech operation is not authorized'), {
          reason: 'SPEECH_OPERATION_NOT_AUTHORIZED',
        });
      }
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected mounted terminal media handoff request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => states.at(-1)?.terminal_announcement_state === 'recovering',
        'terminal notification was not retained while Live Voice was off',
      );
      assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 0);
      assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 0);
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'terminal recovery did not start a media owner');
      await browser.emitFirstFrame(0);
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.notification.next' && call.requestId === notificationRequestId).length === 2,
        'terminal recovery did not replay the exact notification request',
      );
      await waitForMounted(() => states.at(-1)?.p1_status === 'playing', 'authorized terminal announcement did not play');
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'terminal audio did not reach browser playout');
      browser.endLatestSource();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length === 1,
        'terminal presentation was not ACKed exactly once',
      );
    });

    const exactNotificationCalls = calls.filter(
      call => call.method === 'live_voice.composition.p2.notification.next' && call.requestId === notificationRequestId,
    );
    assert.equal(exactNotificationCalls.length, 2);
    assert.deepEqual(exactNotificationCalls[1].params, exactNotificationCalls[0].params);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 0);
    assert.equal(
      calls.some(call => call.method.includes('task.cancel') || call.method.includes('task.mutate') || call.method === 'live_voice.composition.p3.mutate'),
      false,
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted TTS failure and ACK transport loss keep text visible, replay one ACK identity, and resume one capture', async () => {
  const i18n = await createI18n('zh');
  const sessionId = 'mounted-tts-failure-recovery-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const projectedMessages = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  let notificationFailuresRemaining = 0;
  let activeMediaBinding = null;
  let presentationAckAttempts = 0;
  let rejectSynthesis = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const publishNotification = notification => {
    queuedNotifications.push(notification);
    notificationFailuresRemaining = 3;
    const waiter = notificationWaiters.shift();
    if (waiter) {
      notificationFailuresRemaining -= 1;
      waiter.reject(Object.assign(new Error('mounted notification response unknown'), { code: 'WS_DISCONNECTED' }));
    }
  };

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (notificationFailuresRemaining > 0) {
        notificationFailuresRemaining -= 1;
        throw Object.assign(new Error('mounted notification response unknown'), { code: 'WS_DISCONNECTED' });
      }
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise((resolve, reject) => notificationWaiters.push({ resolve, reject }));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      presentationAckAttempts += 1;
      if (presentationAckAttempts === 1) {
        throw Object.assign(new Error('mounted ACK response unknown'), { code: 'WS_DISCONNECTED' });
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-tts-failure-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'F'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') return mountedRecognition(params, '请用中文简短介绍杭州。', 1);
    if (method === 'live_voice.composition.unified.submit') {
      const response = {
        interaction_id: params.interaction_id,
        response_id: 'mounted-tts-failure-response',
        response_generation: 1,
      };
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          kind: 'agent.output',
          response,
          agent_event: { event_type: 'chat.final', text: '杭州是一座兼具山水与人文魅力的城市。' },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-tts-failure-unit',
            seq: 0,
            content_ref: `sha256:${'f'.repeat(64)}`,
          },
        },
      });
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: 'mounted-tts-failure-agent-request',
          round_id: 'mounted-tts-failure-round',
          response,
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return new Promise((_, reject) => {
        rejectSynthesis = reject;
      });
    }
    throw new Error(`unexpected mounted TTS failure request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: event => projectedMessages.push(event),
        }),
      );
      await waitForMounted(() => controlRef.current !== null && states.at(-1)?.available === true, 'TTS failure route unavailable');
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'initial TTS failure capture unavailable');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => projectedMessages.some(event => event.message.role === 'assistant') && rejectSynthesis !== null,
        'recovered notification did not reach held TTS',
      );
      assert.equal(states.some(state => state.p1_status === 'playing'), false);
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 0);
      rejectSynthesis(Object.assign(new Error('mounted synthesis unavailable'), { reason: 'SPEECH_PROVIDER_UNAVAILABLE' }));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length === 2,
        `TTS failure did not retain the text presentation ACK; states=${states.map(state => `${state.p1_status}/${state.p1_reason}/${state.text_status}/${state.text_reason}/retained=${state.operation_retained}`).join(',')}; methods=${calls.map(call => call.method).join(',')}`,
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 2,
        `TTS failure did not allocate one bounded successor: ${states.map(state => `${state.p1_status}/${state.p1_reason}/${state.text_status}/${state.text_reason}`).join(',')}; methods=${calls.map(call => call.method).join(',')}`,
      );
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'TTS failure successor did not resume capture');
    });

    assert.deepEqual(projectedMessages.map(event => [event.message.role, event.message.content]), [
      ['user', '请用中文简短介绍杭州。'],
      ['assistant', '杭州是一座兼具山水与人文魅力的城市。'],
    ]);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 1);
    const presentationAcks = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.equal(presentationAcks.length, 2);
    assert.equal(new Set(presentationAcks.map(call => call.requestId)).size, 1);
    assert.equal(browser.counts.getUserMedia, 2);
    const ttsDiagnostic = states.find(
      state =>
        state.recovery_diagnostic?.seam === 'tts' &&
        state.recovery_diagnostic.reason === 'SPEECH_PROVIDER_UNAVAILABLE' &&
        state.recovery_diagnostic.disposition === 'terminal',
    )?.recovery_diagnostic;
    assert.deepEqual(ttsDiagnostic, {
      seam: 'tts',
      disposition: 'terminal',
      reason: 'SPEECH_PROVIDER_UNAVAILABLE',
      session_id: sessionId,
      correlation_id: presentationAcks[0].params.correlation_id,
      interaction_id: presentationAcks[0].params.interaction_id,
      activation_id: presentationAcks[0].params.activation_id,
      activation_generation: presentationAcks[0].params.activation_generation,
      response_id: 'mounted-tts-failure-response',
      response_generation: 1,
    });
    const ackDiagnostic = states.find(
      state => state.recovery_diagnostic?.seam === 'presentation_ack' && state.recovery_diagnostic.disposition === 'retrying',
    )?.recovery_diagnostic;
    assert.equal(ackDiagnostic?.correlation_id, ttsDiagnostic.correlation_id);
    assert.equal(ackDiagnostic?.response_id, ttsDiagnostic.response_id);
    assert.equal(ackDiagnostic?.response_generation, ttsDiagnostic.response_generation);
    assert.equal(ackDiagnostic?.reason, 'PRODUCT_PRESENTATION_ACK_RECOVERY_REQUIRED');
    assert.equal(states.at(-1).recovery_diagnostic, null);
    assert.equal(
      calls.some(call => call.method.includes('task.cancel') || call.method.includes('task.mutate') || call.method === 'live_voice.composition.p3.mutate'),
      false,
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted terminal-response barge converges without voice failure and keeps zero Task mutation', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-barge-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  let activeMediaBinding = null;
  let recognitionIndex = 0;
  let renderer;
  const browser = installP1BrowserEnvironment({
    mediaBinding: () => activeMediaBinding,
    holdDownlinkDetach: true,
  });
  const activateP2 = createMountedP2ActivationResponder();
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.response_id === 'mounted-barge-response-1') {
        throw Object.assign(new Error('ACK belongs to a stale response generation'), {
          code: 'STALE',
          reason: 'UNKNOWN_AGENT_RESPONSE',
        });
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.barge_in') {
      throw Object.assign(new Error('response completed before remote barge-in'), {
        code: 'CONFLICT',
        reason: 'RESPONSE_ALREADY_TERMINAL',
      });
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(params, calls.filter(call => call.method === method).length);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-barge-media-subject-${params.capture_generation}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'B'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.speech.recognize_batch') {
      recognitionIndex += 1;
      return mountedRecognition(
        params,
        recognitionIndex === 1 ? '请回答我的问题。' : '这是播放期间的插话。',
        recognitionIndex,
      );
    }
    if (method === 'live_voice.composition.unified.submit') {
      if (recognitionIndex === 1) {
        const response = {
          interaction_id: params.interaction_id,
          response_id: 'mounted-barge-response-1',
          response_generation: 1,
        };
        publishNotification({
          ok: true,
          result: {
            status: 'notification',
            session_id: params.session_id,
            correlation_id: params.correlation_id,
            interaction_id: params.interaction_id,
            activation_id: params.activation_id,
            activation_generation: params.activation_generation,
            kind: 'agent.output',
            response,
            agent_event: { event_type: 'chat.final', text: '这是一个可插话的简短回答。' },
            presentation_unit: { surface: 'text', unit_id: 'mounted-barge-unit-1', seq: 0 },
          },
        });
      } else {
        publishNotification({
          ok: true,
          result: {
            status: 'notification',
            session_id: params.session_id,
            correlation_id: params.correlation_id,
            interaction_id: params.interaction_id,
            activation_id: params.activation_id,
            activation_generation: params.activation_generation,
            kind: 'agent.output',
            response: {
              interaction_id: params.interaction_id,
              response_id: 'mounted-barge-response-2',
              response_generation: 2,
            },
            agent_event: { event_type: 'chat.final', text: '插话后的新回答仍然正常呈现。' },
            presentation_unit: { surface: 'text', unit_id: 'mounted-barge-unit-2', seq: 0 },
          },
        });
      }
      return {
        request_id: options.requestId,
        ok: true,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: `mounted-agent-request-${recognitionIndex}`,
          round_id: `mounted-round-${recognitionIndex}`,
          response: {
            interaction_id: params.interaction_id,
            response_id: recognitionIndex === 1
              ? 'mounted-barge-response-1'
              : 'mounted-barge-response-2',
            response_generation: recognitionIndex,
          },
        },
        error: null,
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      const downlink = mountedDownlinkBinding(
        params.response,
        params.unit_id,
        1,
        activeMediaBinding,
      );
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'pcm_f32_mono_20ms',
            sample_rate_hz: 48_000,
            channel_count: 1,
            delivery: 'dedicated_media_downlink',
            endpoint_path: '/ws/live-voice/media',
            media_ticket: 'D'.repeat(43),
            subprotocol: 'live-voice.media.v1',
            ticket_ttl_ms: 30_000,
            frame_count: 1,
            streaming: false,
            degradation_reason: null,
            binding: downlink,
            max_pending_frames: 8,
            max_pending_bytes: 131_072,
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: 'mounted-barge-playout-receipt',
        ...params,
        duplex_media_observed: true,
      };
    }
    throw new Error(`unexpected mounted barge-in request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'barge-in Live Voice did not become available',
      );
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'initial capture did not start');
      await controlRef.current.stop();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.speech.synthesize_batch'),
        'Agent answer did not request authoritative synthesis',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 2,
        'successor capture authority was not requested during playout',
      );
      await browser.emitFirstFrame();
      try {
        await browser.emitDownlinkFrame();
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-6)
            .map(state => `${state.p1_status}/${state.p1_reason}`)
            .join(',')}; methods=${calls
            .slice(-10)
            .map(call => call.method)
            .join(',')}`,
        );
      }
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'playing',
        `Agent answer did not start playout; states=${states
          .slice(-12)
          .map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`)
          .join(',')}; methods=${calls
          .slice(-16)
          .map(call => call.method)
          .join(',')}`,
      );
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'dedicated Agent audio did not begin browser rendering');
      await browser.emitSpeechStartDuringPlayout();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
        'server speech-start did not reach the mounted P2 barge-in owner',
      );
      assert.equal(browser.counts.sourceStops, 1, 'speech-start did not immediately stop browser playout');
      assert.equal(
        calls.filter(call => call.method === 'live_voice.speech.recognize_batch').length,
        1,
        'speech-start must not submit recognition before EOT',
      );
      await browser.emitSpeechEndOfTurnDuringPlayout();
    });

    const bargeCalls = calls.filter(call => call.method === 'live_voice.composition.p2.barge_in');
    assert.equal(bargeCalls.length, 1);
    assert.equal(bargeCalls[0].params.cancel_response, true);
    assert.equal(browser.counts.sourceStops, 1);
    assert.equal(browser.speechStartSignals.length, 1);
    assert.equal(browser.speechStartSignals[0].business_cancel_count_delta, 0);
    assert.equal(browser.endOfTurnSignals.length, 1);
    assert.equal(browser.endOfTurnSignals[0].speech_started_observed, true);
    assert.equal(browser.endOfTurnSignals[0].business_cancel_count_delta, 0);
    assert.equal(
      calls.some(call =>
        call.method.includes('task.cancel')
        || call.method.includes('task.mutate')
        || call.method === 'live_voice.composition.p3.mutate'),
      false,
    );
    await waitForMounted(
      () => calls.filter(call => call.method === 'live_voice.speech.recognize_batch').length === 2,
      'barge-in speech was not recognized through the successor capture',
    );
    await waitForMounted(
      () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 2,
      'barge-in speech was not committed through unified submit',
    );
    await waitForMounted(
      () => calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length === 2,
      `stale predecessor ACK blocked the new answer from reaching TTS; methods=${calls.map(call => call.method).join(',')}; states=${states
        .slice(-8)
        .map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`)
        .join(',')}`,
    );
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p2.close').length,
      0,
      'a definitive stale predecessor ACK must not tear down the active route',
    );
    assert.equal(
      states.some(state => state.text_reason === 'PRODUCT_BARGE_IN_RECOVERY_REQUIRED'),
      false,
      'a response that completed before remote barge-in must not degrade Live Voice',
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted stale TTS settlement after Session switch cannot retain predecessor ACK or block successor capture', async () => {
  const i18n = await createI18n();
  const predecessorSession = 'mounted-tts-predecessor-session';
  const successorSession = 'mounted-tts-successor-session';
  const lateRejectPredecessorSession = 'mounted-tts-late-reject-predecessor-session';
  const lateRejectSuccessorSession = 'mounted-tts-late-reject-successor-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const queuedNotifications = new Map();
  const notificationWaiters = new Map();
  const activateP2 = createMountedP2ActivationResponder();
  let activeMediaBinding = null;
  let rejectLateSynthesis = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });

  const publishNotification = (sessionId, notification) => {
    const waiters = notificationWaiters.get(sessionId) ?? [];
    const waiter = waiters.shift();
    notificationWaiters.set(sessionId, waiters);
    if (waiter) {
      waiter(notification);
      return;
    }
    const queued = queuedNotifications.get(sessionId) ?? [];
    queued.push(notification);
    queuedNotifications.set(sessionId, queued);
  };

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      const queued = queuedNotifications.get(params.session_id) ?? [];
      if (queued.length > 0) {
        const notification = queued.shift();
        queuedNotifications.set(params.session_id, queued);
        return notification;
      }
      return new Promise(resolve => {
        const waiters = notificationWaiters.get(params.session_id) ?? [];
        waiters.push(resolve);
        notificationWaiters.set(params.session_id, waiters);
      });
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(
        params,
        calls.filter(call => call.method === method).length,
      );
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-stale-tts-media-${params.capture_generation}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'S'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(params, 'Please answer this predecessor question.', 1);
    }
    if (method === 'live_voice.composition.unified.submit') {
      const response = {
        interaction_id: params.interaction_id,
        response_id: 'mounted-stale-tts-response',
        response_generation: 1,
      };
      publishNotification(params.session_id, {
        ok: true,
        result: {
          status: 'notification',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          kind: 'agent.output',
          response,
          agent_event: { event_type: 'chat.final', text: 'This predecessor answer is still playing.' },
          presentation_unit: { surface: 'text', unit_id: 'mounted-stale-tts-unit', seq: 0 },
        },
      });
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: 'mounted-stale-tts-agent-request',
          round_id: 'mounted-stale-tts-round',
          response,
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      if (activeMediaBinding?.session_id === lateRejectPredecessorSession) {
        return new Promise((_, reject) => {
          rejectLateSynthesis = reject;
        });
      }
      const downlink = mountedDownlinkBinding(
        params.response,
        params.unit_id,
        1,
        activeMediaBinding,
      );
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'pcm_f32_mono_20ms',
            sample_rate_hz: 48_000,
            channel_count: 1,
            delivery: 'dedicated_media_downlink',
            endpoint_path: '/ws/live-voice/media',
            media_ticket: 'T'.repeat(43),
            subprotocol: 'live-voice.media.v1',
            ticket_ttl_ms: 30_000,
            frame_count: 1,
            streaming: false,
            degradation_reason: null,
            binding: downlink,
            max_pending_frames: 8,
            max_pending_bytes: 131_072,
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: 'mounted-stale-tts-playout-receipt',
        ...params,
        duplex_media_observed: true,
      };
    }
    throw new Error(`unexpected stale TTS request: ${method}`);
  };

  const element = sessionId => mountedFullyEnabledElement(i18n, sessionId, request, true, {
    productVoiceControlRef: controlRef,
    onProductVoiceStateChange: state => states.push(state),
  });

  try {
    await act(async () => {
      renderer = create(element(predecessorSession));
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'predecessor Live Voice did not become available',
      );
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'predecessor capture did not start',
      );
      await controlRef.current.stop();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.speech.synthesize_batch'),
        'predecessor TTS did not request authoritative synthesis',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 2,
        'predecessor playout did not allocate its serialized successor capture',
      );
      await browser.emitFirstFrame();
      try {
        await browser.emitDownlinkFrame();
      } catch (error) {
        assert.fail(
          `${error.message}; states=${states
            .slice(-6)
            .map(state => `${state.p1_status}/${state.p1_reason}`)
            .join(',')}; methods=${calls
            .slice(-12)
            .map(call => call.method)
            .join(',')}`,
        );
      }
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'playing',
        'predecessor TTS did not start',
      );
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'predecessor TTS did not begin browser rendering');
    });

    await act(async () => {
      renderer.update(element(successorSession));
      await waitForMounted(
        () => calls.some(call =>
          call.method === 'live_voice.composition.p2.activate'
          && call.params.session_id === successorSession),
        'successor P2 activation did not start',
      );
      browser.endLatestSource();
      await new Promise(resolve => setImmediate(resolve));
      await new Promise(resolve => setImmediate(resolve));
    });

    assert.equal(
      calls.some(call =>
        call.method === 'live_voice.composition.p2.presentation.ack'
        && call.params.session_id === predecessorSession),
      false,
    );

    await act(async () => {
      void controlRef.current.start();
      await waitForMounted(
        () => calls.some(call =>
          call.method === 'live_voice.media.activate'
          && call.params.session_id === successorSession),
        'successor capture remained blocked by the predecessor presentation',
      );
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'successor capture did not reach capturing',
      );
    });

    await act(async () => {
      renderer.unmount();
      renderer = null;
      await new Promise(resolve => setTimeout(resolve, 30));
    });
    const lateRejectBoundary = states.length;
    await act(async () => {
      renderer = create(element(lateRejectPredecessorSession));
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'late-reject predecessor Live Voice did not become available',
      );
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'late-reject predecessor capture did not start');
      await controlRef.current.stop();
      await waitForMounted(() => typeof rejectLateSynthesis === 'function', 'late-reject predecessor synthesis did not start');
    });
    await act(async () => {
      renderer.update(element(lateRejectSuccessorSession));
      await waitForMounted(
        () => calls.some(call =>
          call.method === 'live_voice.composition.p2.activate'
          && call.params.session_id === lateRejectSuccessorSession),
        'late-reject successor P2 activation did not start',
      );
      rejectLateSynthesis(Object.assign(new Error('stale predecessor synthesis failed'), { reason: 'SPEECH_PROVIDER_UNAVAILABLE' }));
      await new Promise(resolve => setTimeout(resolve, 50));
    });
    assert.equal(
      states
        .slice(lateRejectBoundary)
        .some(state => state.recovery_diagnostic?.session_id === lateRejectPredecessorSession),
      false,
    );
    assert.equal(
      calls.some(call =>
        call.method === 'live_voice.composition.p2.presentation.ack'
        && call.params.session_id === lateRejectPredecessorSession),
      false,
    );
    await act(async () => {
      void controlRef.current.start();
      await waitForMounted(
        () => calls.some(call =>
          call.method === 'live_voice.media.activate'
          && call.params.session_id === lateRejectSuccessorSession),
        'late-reject successor capture remained blocked by stale TTS failure',
      );
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'late-reject successor capture did not reach capturing');
    });
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted Exit fences a blocked start and immediate re-enable starts only the new loop generation', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-exit-reenable-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const activateP2 = createMountedP2ActivationResponder();
  let activeMediaBinding = null;
  let p2ActivationCount = 0;
  let releaseBlockedRefresh = null;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      p2ActivationCount += 1;
      if (p2ActivationCount === 2) {
        return new Promise(resolve => {
          releaseBlockedRefresh = () => resolve(activateP2(params));
        });
      }
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') return new Promise(() => {});
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(
        params,
        calls.filter(call => call.method === method).length,
      );
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'mounted-exit-reenable-media-subject',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'R'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    throw new Error(`unexpected Exit/re-enable request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'Exit/re-enable Live Voice did not become available',
      );
    });

    let oldStart;
    await act(async () => {
      oldStart = controlRef.current.start();
      await waitForMounted(
        () => p2ActivationCount === 2 && typeof releaseBlockedRefresh === 'function',
        'first loop generation did not block in media-authority refresh',
      );
    });
    let newStart;
    await act(async () => {
      await controlRef.current.close();
      newStart = controlRef.current.start();
      releaseBlockedRefresh();
      try {
        await waitForMounted(
          () => calls.filter(call => call.method === 'live_voice.media.activate').length === 1,
          'new loop generation did not start exactly one media authority',
        );
      } catch (error) {
        assert.fail(`${error.message}; methods=${calls.map(call => `${call.method}:${call.params.activation_generation ?? '-'}`).join(',')}; states=${states.slice(-12).map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}`).join(',')}`);
      }
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'new loop generation media did not reach capturing');
      await Promise.all([oldStart, newStart]);
    });

    assert.equal(p2ActivationCount, 4);
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.p2.activate').map(call => call.params.activation_generation),
      [1, 1, 2, 2],
      'Exit/re-enable must close generation 1, prepare generation 2, then refresh only that successor media authority',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.close').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 1);
    assert.equal(browser.counts.getUserMedia, 1);
    assert.equal(states.at(-1)?.p1_status, 'capturing');
    await act(async () => controlRef.current.close());
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted Exit preserves the wake for a cleanup-window ACK retired behind an active drainer', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-exit-pending-ack-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const projectedMessages = [];
  const notificationWaiters = [];
  const activateP2 = createMountedP2ActivationResponder();
  let activeMediaBinding = null;
  let releaseAck = null;
  let releaseRetiredAck = null;
  let releaseSuccessorAck = null;
  let predecessorAckAttempts = 0;
  let successorAckAttempts = 0;
  let recognitionIndex = 0;
  let firstAudioContextCloseStarted = false;
  let releaseFirstAudioContextClose = null;
  let secondAudioContextCloseStarted = false;
  let releaseSecondAudioContextClose = null;
  let audioContextCloseAttempts = 0;
  let renderer;
  const browser = installP1BrowserEnvironment({
    mediaBinding: () => activeMediaBinding,
    closeAudioContext: async () => {
      audioContextCloseAttempts += 1;
      if (audioContextCloseAttempts === 1) {
        firstAudioContextCloseStarted = true;
        await new Promise(resolve => {
          releaseFirstAudioContextClose = resolve;
        });
      } else if (audioContextCloseAttempts === 2) {
        secondAudioContextCloseStarted = true;
        await new Promise(resolve => {
          releaseSecondAudioContextClose = resolve;
        });
      }
    },
  });

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      return new Promise(resolve => notificationWaiters.push({ params: { ...params }, resolve }));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.activation_generation === 2) {
        successorAckAttempts += 1;
        if (successorAckAttempts === 1) {
          return new Promise((_resolve, reject) => {
            releaseSuccessorAck = () => reject(Object.assign(new Error('successor presentation ACK result is unknown'), {
              code: 'REQUEST_TIMEOUT',
              reason: 'REQUEST_TIMEOUT',
              retriable: true,
            }));
          });
        }
        return {
          request_id: options.requestId,
          ok: true,
          error: null,
          result: {
            status: 'presentation_acknowledged',
            ...params,
            accepted: true,
            replayed: false,
            history_records_written: 1,
            history_pending: false,
          },
        };
      }
      predecessorAckAttempts += 1;
      if (predecessorAckAttempts > 1) {
        return new Promise(resolve => {
          releaseRetiredAck = () => resolve({
            request_id: options.requestId,
            ok: true,
            error: null,
            result: {
              status: 'presentation_acknowledged',
              ...params,
              accepted: true,
              replayed: false,
              history_records_written: 1,
              history_pending: false,
            },
          });
        });
      }
      return new Promise((_resolve, reject) => {
        releaseAck = () => reject(Object.assign(new Error('presentation ACK result is unknown'), {
          code: 'REQUEST_TIMEOUT',
          reason: 'REQUEST_TIMEOUT',
          retriable: true,
        }));
      });
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-exit-pending-ack-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'K'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: 'mounted-exit-pending-ack-receipt',
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      recognitionIndex += 1;
      return mountedRecognition(params, `请回答第 ${recognitionIndex} 条 ACK 生命周期问题。`, recognitionIndex);
    }
    if (method === 'live_voice.composition.unified.submit') {
      const successor = params.activation_generation === 2;
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: successor ? 'mounted-exit-successor-agent-request' : 'mounted-exit-pending-ack-agent-request',
          round_id: successor ? 'mounted-exit-successor-round' : 'mounted-exit-pending-ack-round',
          response: {
            interaction_id: params.interaction_id,
            response_id: successor ? 'mounted-exit-successor-response' : 'mounted-exit-pending-ack-response',
            response_generation: 1,
          },
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected pending-ACK Exit request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: entry => projectedMessages.push(entry),
        }),
      );
      await waitForMounted(() => controlRef.current !== null && states.at(-1)?.available === true, 'pending-ACK route unavailable');
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'pending-ACK initial capture unavailable');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 1,
        'pending-ACK authoritative final was not submitted',
      );
      await waitForMounted(() => notificationWaiters.length > 0, 'pending-ACK response poll was not retained');
      const waiter = notificationWaiters.at(-1);
      waiter.resolve({
        ok: true,
        result: {
          status: 'notification',
          ...waiter.params,
          kind: 'agent.output',
          response: {
            interaction_id: waiter.params.interaction_id,
            response_id: 'mounted-exit-pending-ack-response',
            response_generation: 1,
          },
          agent_event: { event_type: 'chat.final', text: '这是 ACK 期间退出前的回答。' },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-exit-pending-ack-unit',
            seq: 0,
            content_ref: `sha256:${'a'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(() => states.at(-1)?.p1_status === 'playing', 'pending-ACK answer did not play');
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'pending-ACK audio did not reach the browser');
      browser.endLatestSource();
      await waitForMounted(() => typeof releaseAck === 'function', 'presentation ACK did not enter retained transport');
    });

    let exitAndReenable = null;
    await act(async () => {
      exitAndReenable = (async () => {
        await controlRef.current.close();
        await controlRef.current.start();
      })();
      await waitForMounted(
        () => firstAudioContextCloseStarted && typeof releaseFirstAudioContextClose === 'function',
        'Exit did not enter the deterministic AudioContext cleanup gate',
      );
      releaseAck();
      await new Promise(resolve => setTimeout(resolve, 300));
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 1).length,
        1,
        'an exited predecessor ACK must not retry in the foreground before durable retirement',
      );
      assert.equal(states.at(-1)?.text_status, 'idle', 'the exited predecessor ACK timeout polluted the closed UI state');
      assert.equal(states.at(-1)?.text_reason, null, 'the exited predecessor ACK timeout published a stale recovery reason');
      releaseFirstAudioContextClose();
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      await exitAndReenable;
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 1).length === 2,
        'cleanup-window timeout was not replayed from the durable retired-ACK ledger',
      );
      assert.equal(typeof releaseRetiredAck, 'function', 'durable retired-ACK replay did not remain independently in flight');
      try {
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.composition.p2.activate' && call.params.activation_generation === 2),
          'retained predecessor ACK blocked generation-2 activation',
        );
      } catch (error) {
        const journal = globalThis.window?.sessionStorage?.getItem(
          `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`,
        );
        assert.fail(
          `${error.message}; methods=${calls.map(call => `${call.method}:${call.params.activation_generation ?? '-'}`).join(',')}; states=${states.slice(-12).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? '-'}`).join(',')}; journal=${journal}`,
        );
      }
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 2,
        'retained predecessor ACK blocked generation-2 media activation',
      );
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'retained predecessor ACK blocked generation-2 capture',
      );
      const mediaActivationCountBeforeOldAck = calls.filter(call => call.method === 'live_voice.media.activate').length;
      assert.equal(predecessorAckAttempts, 2, 'successor journal updates duplicated the in-flight durable ACK replay');
      assert.equal(states.at(-1)?.p1_status, 'capturing', 'old ACK settlement changed successor capture state');
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p2.close').length,
        1,
        'retained ACK settlement closed a successor generation',
      );
      assert.equal(
        calls.filter(call => call.method === 'live_voice.media.activate').length,
        mediaActivationCountBeforeOldAck,
        'retained ACK settlement allocated another media authority',
      );
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 2,
        'generation-2 capture did not submit its own committed final',
      );
      await waitForMounted(
        () => notificationWaiters.some(waiter => waiter.params.activation_generation === 2),
        'generation-2 response poll was not retained',
      );
      const successorWaiter = notificationWaiters.find(waiter => waiter.params.activation_generation === 2);
      successorWaiter.resolve({
        ok: true,
        result: {
          status: 'notification',
          ...successorWaiter.params,
          kind: 'agent.output',
          response: {
            interaction_id: successorWaiter.params.interaction_id,
            response_id: 'mounted-exit-successor-response',
            response_generation: 1,
          },
          agent_event: { event_type: 'chat.final', text: '这是 generation 2 自己的回答。' },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-exit-successor-unit',
            seq: 0,
            content_ref: `sha256:${'b'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(() => states.at(-1)?.p1_status === 'playing', 'generation-2 response did not enter playout');
      await waitForMounted(() => browser.counts.sourceStarts === 2, 'generation-2 response did not reach the browser');
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.close').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length, 2);
    assert.equal(states.at(-1)?.p1_status, 'playing', 'old ACK settlement changed successor playout state');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 2);
    assert.equal(browser.counts.sourceStarts, 2);
    browser.endLatestSource();
    await waitForMounted(
      () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 2).length === 1,
      'generation-2 presentation ACK did not enter its original transport',
    );
    assert.equal(typeof releaseSuccessorAck, 'function', 'generation-2 ACK transport was not held for the overlapping retirement');

    let secondExitAndReenable = null;
    await act(async () => {
      secondExitAndReenable = (async () => {
        await controlRef.current.close();
        await controlRef.current.start();
      })();
      await waitForMounted(
        () => secondAudioContextCloseStarted && typeof releaseSecondAudioContextClose === 'function',
        'second Exit did not enter the deterministic AudioContext cleanup gate',
      );
      releaseSuccessorAck();
      await new Promise(resolve => setTimeout(resolve, 300));
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 2).length,
        1,
        'the newly exited ACK retried in the foreground before its overlapping retirement',
      );
      assert.equal(states.at(-1)?.text_status, 'idle', 'the second exited ACK timeout polluted the closed UI state');
      assert.equal(states.at(-1)?.text_reason, null, 'the second exited ACK timeout published a stale recovery reason');
      releaseSecondAudioContextClose();
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      await secondExitAndReenable;
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.activate' && call.params.activation_generation === 3),
        'the overlapping retirement blocked generation-3 activation',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 3,
        'the overlapping retirement blocked generation-3 media activation',
      );
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'generation-3 capture did not start');
      assert.equal(predecessorAckAttempts, 2, 'the held generation-1 drainer replayed in parallel');
      assert.equal(successorAckAttempts, 1, 'generation-2 replay began while generation-1 still held the retired-ACK lock');
    });
    await act(async () => {
      releaseRetiredAck();
      await new Promise(resolve => setImmediate(resolve));
    });
    await act(async () => {
      try {
        await waitForMounted(
          () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 2).length === 2,
          'the held drainer lost the wake for an ACK retired after its initial snapshot',
        );
      } catch (error) {
        const journal = globalThis.window.sessionStorage.getItem(
          `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`,
        );
        assert.fail(
          `${error.message}; predecessorAckAttempts=${predecessorAckAttempts}; successorAckAttempts=${successorAckAttempts}; methods=${calls.slice(-24).map(call => `${call.method}:${call.params.activation_generation ?? '-'}`).join(',')}; journal=${journal}`,
        );
      }
      await waitForMounted(() => {
        const journal = JSON.parse(
          globalThis.window.sessionStorage.getItem(
            `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`,
          ),
        );
        return journal.retired_presentation_acks.length === 0;
      }, 'overlapping retired ACKs did not drain to zero');
    });

    const predecessorAckCalls = calls.filter(
      call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 1,
    );
    const successorAckCalls = calls.filter(
      call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.activation_generation === 2,
    );
    assert.equal(predecessorAckCalls.length, 2);
    assert.equal(successorAckCalls.length, 2);
    assert.equal(
      predecessorAckCalls[1].requestId,
      predecessorAckCalls[0].requestId,
      'generation-1 durable ACK replay must preserve the exact original request id',
    );
    assert.equal(
      successorAckCalls[1].requestId,
      successorAckCalls[0].requestId,
      'generation-2 durable ACK replay must preserve the exact original request id',
    );
    assert.equal(states.at(-1)?.p1_status, 'capturing', 'old ACK recovery changed generation-3 capture state');
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.close').length, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 3);
    assert.equal(projectedMessages.filter(entry => entry.message.role === 'user').length, 2);
    assert.equal(projectedMessages.filter(entry => entry.message.role === 'assistant').length, 2);
    assert.equal(new Set(projectedMessages.map(entry => entry.message.id)).size, projectedMessages.length);
    assert.equal(
      new Set(
        calls
          .filter(call => call.method === 'live_voice.composition.p2.activate' && call.params.activation_generation === 2)
          .map(call => call.params.activation_id),
      ).size,
      1,
      'ACK settlement must open only one exact successor identity',
    );
    await act(async () => controlRef.current.close());
    await waitForMounted(() => states.at(-1)?.p1_status === 'closed', 'final Exit did not close generation-3 resources');
    assert.equal(browser.counts.stoppedTracks, browser.counts.getUserMedia, 'final Exit leaked a microphone track');
    assert.equal(browser.counts.closedAudioContexts, browser.counts.audioContexts, 'final Exit leaked an AudioContext');
    assert.equal(browser.counts.closedWorkletPorts, browser.counts.workletPorts, 'final Exit leaked an AudioWorklet port');
    assert.equal(browser.counts.socketCloses, browser.counts.socketOpens, 'final Exit leaked a dedicated media socket');
    const journal = JSON.parse(
      globalThis.window.sessionStorage.getItem(
        `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`,
      ),
    );
    assert.deepEqual(journal.retired_presentation_acks, [], 'settled old ACK retained a durable resource');
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted Exit retires a deferred stale Task AUDIO owner before same-Session successor capture', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-exit-pending-unified-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const projectedMessages = [];
  const activateP2 = createMountedP2ActivationResponder();
  let activeMediaBinding = null;
  let releaseUnified = null;
  let unifiedParams = null;
  let recognitionIndex = 0;
  let unifiedAttempt = 0;
  let predecessorActivationGeneration = null;
  let predecessorCloseAttempts = 0;
  let releasePredecessorPresentationFailure = null;
  const notificationWaiters = [];
  let firstAudioContextCloseStarted = false;
  let releaseFirstAudioContextClose = null;
  let audioContextCloseAttempts = 0;
  let renderer;
  const browser = installP1BrowserEnvironment({
    mediaBinding: () => activeMediaBinding,
    closeAudioContext: async () => {
      audioContextCloseAttempts += 1;
      if (audioContextCloseAttempts !== 1) return;
      firstAudioContextCloseStarted = true;
      await new Promise(resolve => {
        releaseFirstAudioContextClose = resolve;
      });
    },
  });
  const hasPendingNotificationForGeneration = generation => notificationWaiters.some(
    waiter => !waiter.settled && waiter.params.activation_generation === generation,
  );
  const publishNotificationForGeneration = (generation, notification) => {
    const waiter = [...notificationWaiters]
      .reverse()
      .find(candidate => !candidate.settled && candidate.params.activation_generation === generation);
    assert.ok(waiter, `no pending notification.next for activation generation ${generation}`);
    waiter.settled = true;
    waiter.resolve({
      ...notification,
      result: {
        ...notification.result,
        session_id: waiter.params.session_id,
        correlation_id: waiter.params.correlation_id,
        interaction_id: waiter.params.interaction_id,
        activation_id: waiter.params.activation_id,
        activation_generation: waiter.params.activation_generation,
      },
    });
  };

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      predecessorActivationGeneration ??= params.activation_generation;
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') {
      if (params.activation_generation === predecessorActivationGeneration) {
        predecessorCloseAttempts += 1;
        if (predecessorCloseAttempts <= 3) {
          throw Object.assign(new Error('predecessor exact close result is unknown'), {
            code: 'REQUEST_TIMEOUT',
            reason: 'REQUEST_TIMEOUT',
          });
        }
      }
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.composition.p2.notification.next') {
      return new Promise(resolve => {
        notificationWaiters.push({ params: { ...params }, resolve, settled: false });
      });
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      if (params.response_id === 'mounted-exit-pending-task-after-exit-response') {
        assert.equal(params.response_generation, 3);
        assert.equal(params.surface, 'audio');
        assert.equal(params.unit_id, 'mounted-exit-pending-task-after-exit-unit');
        assert.equal(params.failure_reason, 'task_audio_playout_failed');
        return {
          request_id: options.requestId,
          ok: true,
          error: null,
          result: {
            status: 'presentation_failed_fallback_text',
            ...params,
            fallback: 'text',
            deferred: true,
            replayed: false,
          },
        };
      }
      assert.equal(
        params.response_id,
        'mounted-exit-pending-stale-task-response',
        'only the stale predecessor Task AUDIO may report failure during Exit',
      );
      assert.equal(params.response_generation, 0);
      assert.equal(params.surface, 'audio');
      assert.equal(params.unit_id, 'mounted-exit-pending-stale-task-unit');
      assert.equal(params.failure_reason, 'task_audio_playout_failed');
      return new Promise(resolve => {
        releasePredecessorPresentationFailure = () => resolve({
          request_id: options.requestId,
          ok: true,
          error: null,
          result: {
            status: 'presentation_failed_fallback_text',
            ...params,
            fallback: 'text',
            deferred: true,
            replayed: false,
          },
        });
      });
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(
        params,
        calls.filter(call => call.method === method).length,
      );
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-exit-pending-media-${calls.filter(call => call.method === method).length}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'W'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-exit-pending-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      recognitionIndex += 1;
      return mountedRecognition(params, '请回答这条退出前的问题。', recognitionIndex);
    }
    if (method === 'live_voice.composition.unified.submit') {
      unifiedAttempt += 1;
      const attempt = unifiedAttempt;
      unifiedParams = { ...params };
      return new Promise(resolve => {
        releaseUnified = () =>
          resolve(
            attempt !== 2
              ? {
                  request_id: options.requestId,
                  ok: true,
                  result: {
                    status: 'round_accepted',
                    session_id: params.session_id,
                    correlation_id: params.correlation_id,
                    interaction_id: params.interaction_id,
                    activation_id: params.activation_id,
                    activation_generation: params.activation_generation,
                    turn_id: params.turn_id,
                    commit_id: params.commit_id,
                    request_id: `mounted-exit-pending-agent-request-${attempt}`,
                    round_id: `mounted-exit-pending-round-${attempt}`,
                    response: {
                      interaction_id: params.interaction_id,
                      response_id: `mounted-exit-pending-response-${attempt}`,
                      response_generation: attempt,
                    },
                  },
                  error: null,
                }
              : {
                  request_id: options.requestId,
                  ok: false,
                  result: null,
                  error: {
                    code: 'CAPABILITY_UNAVAILABLE',
                    reason: 'PRODUCT_COMPOSITION_STOPPED',
                    message: 'unavailable',
                  },
                },
          );
      });
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      if (![
        'mounted-exit-pending-task-after-exit-response',
        'mounted-exit-pending-response-4',
      ].includes(params.response?.response_id)) {
        throw new Error('the pre-Exit answer must not be spoken into the new loop generation');
      }
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected pending-unified Exit request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: entry => projectedMessages.push(entry),
        }),
      );
      await waitForMounted(
        () => controlRef.current !== null && states.at(-1)?.available === true,
        'pending-unified Exit Live Voice did not become available',
      );
      void controlRef.current.start();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'starting',
        'pending-unified first capture did not start',
      );
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'pending-unified first capture was not ready',
      );
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => typeof releaseUnified === 'function',
        'authoritative final did not enter the retained unified request',
      );
      await waitForMounted(
        () => hasPendingNotificationForGeneration(unifiedParams.activation_generation),
        'predecessor notification poll was not active before Exit',
      );
    });

    const predecessorGeneration = unifiedParams.activation_generation;
    const successorGeneration = predecessorGeneration + 1;
    const deferredStaleTaskPresentation = {
      ok: true,
      result: {
        status: 'notification',
        session_id: sessionId,
        correlation_id: unifiedParams.correlation_id,
        interaction_id: unifiedParams.interaction_id,
        activation_id: unifiedParams.activation_id,
        activation_generation: unifiedParams.activation_generation,
        kind: 'agent.output',
        response: {
          interaction_id: unifiedParams.interaction_id,
          response_id: 'mounted-exit-pending-stale-task-response',
          response_generation: 0,
        },
        agent_event: {
          event_type: 'chat.final',
          text: '这是退出前已出队的旧 Task 通知。',
          source_provenance: 'server.task_notification',
        },
        presentation_unit: {
          surface: 'audio',
          unit_id: 'mounted-exit-pending-stale-task-unit',
          seq: 0,
          content_ref: `sha256:${'1'.repeat(64)}`,
        },
      },
    };
    let exitAndReenable = null;
    await act(async () => {
      publishNotificationForGeneration(predecessorGeneration, deferredStaleTaskPresentation);
      await waitForMounted(
        () =>
          calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 1
          && typeof releasePredecessorPresentationFailure === 'function',
        'the stale predecessor Task AUDIO did not enter one retained presentation failure before Exit',
      );
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length,
      0,
      'the deferred stale Task AUDIO must have zero ACK effect before Exit',
    );
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length,
      1,
      'the stale predecessor Task AUDIO must report exactly one failure while its foreground submit remains pending',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 0);
    assert.equal(browser.counts.sourceStarts, 0);
    assert.equal(projectedMessages.filter(entry => entry.message.role === 'assistant').length, 0);
    assert.equal(
      JSON.stringify(renderer.toJSON()).includes('这是退出前已出队的旧 Task 通知。'),
      false,
      'the deferred stale Task AUDIO must not enter rendered UI or history',
    );
    await act(async () => {
      exitAndReenable = (async () => {
        await controlRef.current.close();
        await controlRef.current.start();
      })();
      releaseUnified();
      await waitForMounted(
        () => firstAudioContextCloseStarted && typeof releaseFirstAudioContextClose === 'function',
        'Exit did not enter the deterministic AudioContext cleanup gate',
      );
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length,
        1,
        'Exit must not replay the retained predecessor Task AUDIO failure before exact close',
      );
      releaseFirstAudioContextClose();
      releasePredecessorPresentationFailure();
      await Promise.resolve();
    });
    await act(async () => {
      await exitAndReenable;
    });
    try {
      const recoveryDeadline = Date.now() + 3_000;
      while (
        !calls.some(call =>
          call.method === 'live_voice.composition.p2.activate'
          && call.params.activation_generation === successorGeneration)
      ) {
        if (Date.now() >= recoveryDeadline) {
          assert.fail('Exit/re-enable did not prepare the exact P2 successor generation after the retained submit settled');
        }
        await act(async () => {
          await new Promise(resolve => setTimeout(resolve, 25));
        });
      }
    } catch (error) {
      const journal = globalThis.window.sessionStorage.getItem(
        `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`,
      );
      assert.fail(
        `${error.message}; closeAttempts=${predecessorCloseAttempts}; methods=${calls
          .filter(call => call.method.startsWith('live_voice.composition.p2.'))
          .map(call => `${call.method}:${call.params.activation_generation ?? '-'}`)
          .join(',')}; journal=${journal}`,
      );
    }
    assert.equal(
      calls.filter(call =>
        call.method === 'live_voice.composition.p2.close'
        && call.params.activation_generation === predecessorGeneration).length,
      4,
      'Exit must retain the exact predecessor through three unknown closes and journal recovery',
    );
    const predecessorActivations = calls.filter(call =>
      call.method === 'live_voice.composition.p2.activate'
      && call.params.activation_generation === predecessorGeneration);
    assert.equal(
      predecessorActivations.length,
      3,
      'initial activation, media replay, and journal recovery must retain one exact predecessor binding',
    );
    assert.deepEqual(
      predecessorActivations.at(-1).params,
      predecessorActivations[0].params,
      'journal recovery changed the predecessor binding after an unknown close result',
    );
    await act(async () => {
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 2,
        'successor capture remained blocked by the old accepted response',
      );
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'new loop generation did not reach capturing',
      );
    });

    releaseUnified = null;
    await act(async () => {
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => unifiedAttempt === 2 && typeof releaseUnified === 'function',
        'second authoritative final did not enter the retained unified request',
      );
    });
    await act(async () => {
      await controlRef.current.close();
      await controlRef.current.start();
      await new Promise(resolve => setImmediate(resolve));
    });
    assert.equal(calls.filter(call => call.method === 'live_voice.media.activate').length, 2);
    await act(async () => {
      releaseUnified();
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 3,
        'new loop generation did not resume after old unified rejection',
      );
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'post-rejection loop generation did not reach capturing',
      );
    });

    releaseUnified = null;
    await act(async () => {
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => unifiedAttempt === 3 && typeof releaseUnified === 'function',
        'third authoritative final did not enter the retained unified request',
      );
      releaseUnified();
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(
        () => states.at(-1)?.text_status === 'waiting',
        'terminal-without-final setup did not accept the Agent round',
      );
      await waitForMounted(
        () => hasPendingNotificationForGeneration(successorGeneration + 1),
        'current P2 generation did not retain the terminal-without-final notification poll',
      );
      publishNotificationForGeneration(successorGeneration + 1, {
        ok: true,
        result: {
          status: 'notification',
          session_id: sessionId,
          correlation_id: unifiedParams.correlation_id,
          interaction_id: unifiedParams.interaction_id,
          activation_id: unifiedParams.activation_id,
          activation_generation: unifiedParams.activation_generation,
          kind: 'work.progress',
          response: {
            interaction_id: unifiedParams.interaction_id,
            response_id: 'mounted-exit-pending-response-3',
            response_generation: 3,
          },
          progress_event: {
            payload: { state: 'terminal', outcome: 'completed' },
          },
        },
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.media.activate').length === 4,
        'terminal-without-final did not resume the hands-free loop',
      );
      await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'post-terminal-without-final loop did not reach capturing',
      );
    });

    releaseUnified = null;
    await act(async () => {
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => unifiedAttempt === 4 && typeof releaseUnified === 'function',
        'current post-re-enable final did not enter one authoritative submit',
      );
      releaseUnified();
      await waitForMounted(
        () => states.at(-1)?.text_status === 'waiting',
        'current post-re-enable round was not accepted',
      );
      await waitForMounted(
        () => hasPendingNotificationForGeneration(successorGeneration + 1),
        'current post-re-enable response did not retain its P2 notification poll',
      );
      publishNotificationForGeneration(successorGeneration + 1, {
        ok: true,
        result: {
          status: 'notification',
          session_id: sessionId,
          correlation_id: unifiedParams.correlation_id,
          interaction_id: unifiedParams.interaction_id,
          activation_id: unifiedParams.activation_id,
          activation_generation: unifiedParams.activation_generation,
          kind: 'agent.output',
          response: {
            interaction_id: unifiedParams.interaction_id,
            response_id: 'mounted-exit-pending-task-after-exit-response',
            response_generation: 3,
          },
          agent_event: {
            event_type: 'chat.final',
            text: '这是旧 owner 关闭后由 successor 精确消费的 Task 通知。',
            source_provenance: 'server.task_notification',
          },
          presentation_unit: {
            surface: 'audio',
            unit_id: 'mounted-exit-pending-task-after-exit-unit',
            seq: 0,
            content_ref: `sha256:${'3'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 2,
        'foreground-busy Task AUDIO did not settle through its exact fallback owner',
      );
      assert.equal(browser.counts.sourceStarts, 0, 'foreground-busy Task AUDIO must not consume the successor P1 owner');
      assert.equal(
        calls.some(
          call =>
            call.method === 'live_voice.composition.p2.presentation.ack' &&
            call.params.response_id === 'mounted-exit-pending-task-after-exit-response',
        ),
        false,
        'foreground-busy Task AUDIO must never receive a forged ACK',
      );
      await waitForMounted(
        () => hasPendingNotificationForGeneration(successorGeneration + 1),
        'Task AUDIO fallback did not release the foreground notification poll',
      );
      publishNotificationForGeneration(successorGeneration + 1, {
        ok: true,
        result: {
          status: 'notification',
          session_id: sessionId,
          correlation_id: unifiedParams.correlation_id,
          interaction_id: unifiedParams.interaction_id,
          activation_id: unifiedParams.activation_id,
          activation_generation: unifiedParams.activation_generation,
          kind: 'agent.output',
          response: {
            interaction_id: unifiedParams.interaction_id,
            response_id: 'mounted-exit-pending-response-4',
            response_generation: 4,
          },
          agent_event: { event_type: 'chat.final', text: '这是重新启用后的当前回答。' },
          presentation_unit: {
            surface: 'text',
            unit_id: 'mounted-exit-pending-current-unit',
            seq: 0,
            content_ref: `sha256:${'4'.repeat(64)}`,
          },
        },
      });
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'playing',
        'current post-re-enable response did not enter playout',
      );
      await waitForMounted(
        () => browser.counts.sourceStarts === 1,
        'current post-re-enable response did not start after Task fallback',
      );
      browser.endLatestSource();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length === 1,
        'current post-re-enable response was not ACKed after Task fallback',
      );
      await waitForMounted(
        () => ['starting', 'capturing'].includes(states.at(-1)?.p1_status),
        'current post-re-enable playout did not resume listening',
      );
      if (states.at(-1)?.p1_status === 'starting') await browser.emitFirstFrame();
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'capturing',
        'current post-re-enable successor capture did not become ready',
      );
    });

    const unifiedSubmissions = calls.filter(call => call.method === 'live_voice.composition.unified.submit');
    const presentationAcks = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack');
    assert.equal(unifiedSubmissions.length, 4);
    assert.equal(new Set(unifiedSubmissions.map(call => call.requestId)).size, 4, 'committed finals must not duplicate Agent submission');
    assert.deepEqual(
      presentationAcks.map(call => call.params.response_id),
      ['mounted-exit-pending-response-4'],
      'only the current successor response may be ACKed',
    );
    const presentationFailures = calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed');
    assert.deepEqual(
      presentationFailures.map(call => call.params.response_id),
      ['mounted-exit-pending-stale-task-response', 'mounted-exit-pending-task-after-exit-response'],
    );
    assert.equal(presentationFailures.every(call => call.params.failure_reason === 'task_audio_playout_failed'), true);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.media.playout_receipt').length, 1);
    assert.equal(calls.filter(call => call.method.startsWith('live_voice.task.') && call.method !== 'live_voice.task.list').length, 0);
    assert.equal(browser.counts.sourceStarts, 1);
    assert.equal(browser.counts.sourceEnds, 1);
    assert.equal(browser.counts.getUserMedia, 5);
    assert.equal(new Set(projectedMessages.map(entry => entry.message.id)).size, projectedMessages.length);
    assert.equal(projectedMessages.filter(entry => entry.message.role === 'user').length, 3);
    assert.equal(projectedMessages.filter(entry => entry.message.role === 'assistant').length, 1);
    await act(async () => controlRef.current.close());
    await waitForMounted(() => states.at(-1)?.p1_status === 'closed', 'final Exit did not publish closed capture state');
    assert.equal(browser.counts.stoppedTracks, browser.counts.getUserMedia, 'final Exit leaked a microphone track');
    assert.equal(browser.counts.closedAudioContexts, browser.counts.audioContexts, 'final Exit leaked an AudioContext');
    assert.equal(browser.counts.closedWorkletPorts, browser.counts.workletPorts, 'final Exit leaked an AudioWorklet port');
    assert.equal(browser.counts.socketCloses, browser.counts.socketOpens, 'final Exit leaked a dedicated media socket');
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

function visibleFailureStates(states) {
  return states
    .filter(state =>
      state.recovery_diagnostic !== null
      || state.text_status === 'failed'
      || state.p1_status === 'failed'
      || state.p1_reason === 'MEDIA_LOCAL_CLOSE'
      || state.text_reason === 'MEDIA_LOCAL_CLOSE')
    .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}/${state.recovery_diagnostic ? `${state.recovery_diagnostic.disposition}:${state.recovery_diagnostic.seam}:${state.recovery_diagnostic.reason}` : 'none'}`);
}

async function assertNoExpectedCloseFailure(states, label) {
  for (let turn = 0; turn < 10; turn += 1) await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(visibleFailureStates(states), [], `${label}: an expected local close was promoted to a visible failure`);
}

async function runMountedC2FirstTailScenario({
  bargeDuringPrefetch = false,
  bargeContinuation = false,
  bargeWhileTailPlayAwaitsAttach = false,
  bargeContinuousOneAhead = false,
  bargeWhileAttaching = false,
  bargeDuringActiveTail = false,
  closeWhileBuffered = false,
  exitWhileParkInFlight = false,
  bargeWhileParkInFlight = false,
  delayPrefixAck = false,
  delayLastTailAck = false,
  twoTails = false,
  rejectPrefixAck = false,
  retryablePrefixAck = false,
  prefetchPromotion = false,
  batchTails = false,
  admissionOnly = false,
} = {}) {
  const i18n = await createI18n();
  const sessionId = 'mounted-c2-continuation-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const projectedMessages = [];
  const lifecycle = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  let activeMediaBinding = null;
  let notificationBinding = null;
  let releasePrefixAck = null;
  let releaseLastTailAck = null;
  let rootPublishedWhileLastTailAckPending = false;
  let notificationCallsBeforeLastTailRelease = null;
  let renderer;
  const activationSubjects = [];
  const browser = installP1BrowserEnvironment({
    mediaBinding: () => activeMediaBinding,
    holdDownlinkDetach: prefetchPromotion
      ? binding => binding.playout?.unit_id !== 'mounted-c2-prefix'
      : false,
    holdDownlinkAttach: bargeWhileTailPlayAwaitsAttach
      ? binding => binding.playout?.unit_id === 'mounted-c2-tail'
      : false,
    holdPrefetchPromotionAck: admissionOnly,
    holdPrefetchParkAck: exitWhileParkInFlight || bargeWhileParkInFlight,
    emitSocketCloseOnLocalClose:
      bargeDuringPrefetch
      || bargeWhileAttaching
      || bargeDuringActiveTail
      || exitWhileParkInFlight
      || bargeWhileParkInFlight
      || bargeWhileTailPlayAwaitsAttach
      || bargeContinuousOneAhead,
  });
  const activateP2 = createMountedP2ActivationResponder();
  const response = {
    interaction_id: 'mounted-c2-interaction',
    response_id: 'mounted-c2-response',
    response_generation: 1,
  };
  const threeTails = bargeContinuousOneAhead;
  const firstTailText = twoTails ? 'Second stable sentence. ' : 'Final tail.';
  const secondTailText = threeTails ? 'Third stable sentence. ' : 'Final tail.';
  const thirdTailText = 'Final tail.';
  const completeText = `First stable sentence. ${firstTailText}${twoTails ? secondTailText : ''}${threeTails ? thirdTailText : ''}`;
  const prefixEndUtf8 = Buffer.byteLength('First stable sentence. ', 'utf8');
  const firstTailEndUtf8 = prefixEndUtf8 + Buffer.byteLength(firstTailText, 'utf8');
  const secondTailEndUtf8 = firstTailEndUtf8 + Buffer.byteLength(secondTailText, 'utf8');
  const completeEndUtf8 = Buffer.byteLength(completeText, 'utf8');
  const notifications = [
    {
      eventType: 'chat.delta',
      text: 'First stable sentence. ',
      surface: 'audio',
      unitId: 'mounted-c2-prefix',
      seq: 0,
      sourceStartUtf8: 0,
      sourceEndUtf8: prefixEndUtf8,
      projectionRole: 'audio_segment',
      delivery: 'speak_only',
      digest: 'a',
    },
    {
      eventType: twoTails ? 'chat.delta' : 'chat.final',
      text: firstTailText,
      surface: 'audio',
      unitId: 'mounted-c2-tail',
      seq: 1,
      sourceStartUtf8: prefixEndUtf8,
      sourceEndUtf8: firstTailEndUtf8,
      projectionRole: 'audio_segment',
      delivery: 'speak_only',
      digest: 'b',
    },
    ...(twoTails ? [{
      eventType: threeTails ? 'chat.delta' : 'chat.final',
      text: secondTailText,
      surface: 'audio',
      unitId: 'mounted-c2-tail-2',
      seq: 2,
      sourceStartUtf8: firstTailEndUtf8,
      sourceEndUtf8: threeTails ? secondTailEndUtf8 : completeEndUtf8,
      projectionRole: 'audio_segment',
      delivery: 'speak_only',
      digest: 'd',
    }] : []),
    ...(threeTails ? [{
      eventType: 'chat.final',
      text: thirdTailText,
      surface: 'audio',
      unitId: 'mounted-c2-tail-3',
      seq: 3,
      sourceStartUtf8: secondTailEndUtf8,
      sourceEndUtf8: completeEndUtf8,
      projectionRole: 'audio_segment',
      delivery: 'speak_only',
      digest: 'e',
    }] : []),
    {
      eventType: 'chat.final',
      text: completeText,
      surface: 'text',
      unitId: 'mounted-c2-root',
      seq: 0,
      sourceStartUtf8: 0,
      sourceEndUtf8: completeEndUtf8,
      projectionRole: 'authoritative_text_root',
      delivery: 'display_only',
      digest: 'c',
    },
  ];
  const publishNotification = notification => {
    assert.ok(notificationWaiters.length <= 1, 'C2 fixture created concurrent notification waiters');
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const productNotification = (item, binding) => ({
    ok: true,
    result: {
      status: 'notification',
      session_id: sessionId,
      correlation_id: binding.correlation_id,
      interaction_id: response.interaction_id,
      activation_id: binding.activation_id,
      activation_generation: binding.activation_generation,
      kind: 'agent.output',
      request_id: 'mounted-c2-agent-request',
      round_id: 'mounted-c2-round',
      response,
      agent_event: { event_type: item.eventType, text: item.text },
      source_event: null,
      progress_event: null,
      presentation_unit: {
        surface: item.surface,
        unit_id: item.unitId,
        seq: item.seq,
        source_start_utf8: item.sourceStartUtf8,
        source_end_utf8: item.sourceEndUtf8,
        content_ref: `sha256:${item.digest.repeat(64)}`,
        projection_role: item.projectionRole,
      },
      presentation_text: item.text,
      presentation_delivery: item.delivery,
      error_reason: null,
      publish_seq: item.seq + 1,
    },
  });

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.media.prefetch.capability.negotiate') {
      return { selected: 'live-voice.media.prefetch-promotion.v1' };
    }
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      const nextIndex =
        params.unit_id === (twoTails ? 'mounted-c2-tail-2' : 'mounted-c2-tail')
            ? notifications.length - 1
            : null;
      if (nextIndex !== null) {
        assert.ok(notificationBinding);
        setTimeout(
          () => {
            publishNotification(productNotification(notifications[nextIndex], notificationBinding));
            if (delayLastTailAck) rootPublishedWhileLastTailAckPending = true;
          },
          0,
        );
      }
      const result = {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: params.surface === 'text' ? 1 : 0,
          history_pending: params.surface !== 'text',
        },
      };
      if (rejectPrefixAck && params.unit_id === 'mounted-c2-prefix') {
        throw Object.assign(new Error('prefix presentation ACK was rejected'), {
          code: 'CONFLICT',
          reason: 'CONFLICT',
          retriable: false,
        });
      }
      if (retryablePrefixAck && params.unit_id === 'mounted-c2-prefix') {
        throw Object.assign(new Error('prefix presentation ACK result is unknown'), {
          code: 'REQUEST_TIMEOUT',
          reason: 'REQUEST_TIMEOUT',
          retriable: true,
        });
      }
      if (delayPrefixAck && params.unit_id === 'mounted-c2-prefix') {
        return new Promise(resolve => {
          releasePrefixAck = () => resolve(result);
        });
      }
      if (
        delayLastTailAck
        && params.unit_id === (twoTails ? 'mounted-c2-tail-2' : 'mounted-c2-tail')
      ) {
        return new Promise(resolve => {
          releaseLastTailAck = () => resolve(result);
        });
      }
      return result;
    }
    if (method === 'live_voice.composition.p2.barge_in') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'barge_in_applied',
          ...params,
          applied: true,
          replayed: false,
          effect_ids: ['mounted-c2-response-cancel'],
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      activationSubjects.push(`mounted-c2-media-${index}`);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-c2-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'C'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') {
      if (bargeContinuation) {
        // Gateway revoke closes every route of the subject and aborts its
        // streaming recognition (STREAMING_SPEECH_ROUTE_ABORTED).
        const index = String(params.subject_id).replace('mounted-c2-media-', '');
        browser.closeRoutesForLease(`mounted-media-lease-${index}`);
      }
      return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    }
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-c2-receipt-${params.unit_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      return mountedRecognition(
        params,
        'Explain Paris.',
        calls.filter(call => call.method === method).length,
      );
    }
    if (method === 'live_voice.composition.unified.submit') {
      const submissionCount = calls.filter(call => call.method === method).length;
      const acceptedResponse = submissionCount === 1
        ? response
        : {
            interaction_id: params.interaction_id,
            response_id: `mounted-c2-followup-response-${submissionCount}`,
            response_generation: submissionCount,
          };
      if (submissionCount === 1) {
        response.interaction_id = params.interaction_id;
        notificationBinding = { ...params };
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'round_accepted',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          turn_id: params.turn_id,
          commit_id: params.commit_id,
          request_id: 'mounted-c2-agent-request',
          round_id: 'mounted-c2-round',
          response: acceptedResponse,
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      const downlink = mountedDownlinkBinding(
        params.response,
        params.unit_id,
        calls.filter(call => call.method === method).length,
        activeMediaBinding,
      );
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'pcm_f32_mono_20ms',
            sample_rate_hz: 48_000,
            channel_count: 1,
            delivery: 'dedicated_media_downlink',
            endpoint_path: '/ws/live-voice/media',
            media_ticket: 'D'.repeat(43),
            subprotocol: 'live-voice.media.v1',
            ticket_ttl_ms: 30_000,
            // A parking successor is a long streaming unit: it must retain its
            // 25-frame PARK reserve, which a single-frame result never can.
            ...((exitWhileParkInFlight || bargeWhileParkInFlight || bargeContinuousOneAhead)
              && params.unit_id !== 'mounted-c2-prefix'
              ? { frame_count: null, streaming: true }
              : { frame_count: 1, streaming: false }),
            degradation_reason: null,
            binding: downlink,
            max_pending_frames: 8,
            max_pending_bytes: 131_072,
            ...(params.prefetch_promotion_capability === undefined
              ? {}
              : { prefetch_promotion_capability: params.prefetch_promotion_capability }),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected mounted C2 request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        (prefetchPromotion ? mountedPrefetchEnabledElement : mountedFullyEnabledElement)(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: event => projectedMessages.push(event),
        }),
      );
      await waitForMounted(() => controlRef.current !== null && states.at(-1)?.available === true, 'C2 route unavailable');
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'C2 initial capture unavailable');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.unified.submit'),
        'C2 unified submit did not retain its response binding',
      );
      assert.ok(notificationBinding);
      await waitForMounted(
        () => notificationWaiters.length === 1,
        'C2 prefix notification owner was not waiting',
      );
      publishNotification(productNotification(notifications[0], notificationBinding));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length === 1,
        `C2 prefix synthesis did not start; queued=${queuedNotifications.length} waiters=${notificationWaiters.length} states=${states.slice(-8).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')} calls=${calls.map(call => call.method).join(',')}`,
      );
      await browser.emitDownlinkFrame();
      await waitForMounted(
        () => browser.counts.sourceStarts === 1,
        `C2 prefix did not start; states=${states.map(state => `${state.p1_status}/${state.p1_reason}/${state.text_status}/${state.text_reason}/${state.recovery_diagnostic?.reason ?? 'none'}`).join(',')} calls=${calls.map(call => call.method).join(',')}`,
      );
      await waitForMounted(
        () => browser.counts.getUserMedia === 2 && browser.counts.workletPorts === 2,
        'C2 successor capture did not allocate during prefix playout',
      );
      await browser.emitFirstFrame(0);
      await waitForMounted(
        () => notificationWaiters.length === 1,
        'C2 first-tail prefetch owner was not waiting during prefix playout',
      );
      if (batchTails) {
        publishNotification({
          ok: true,
          result: {
            status: 'notification_batch',
            session_id: sessionId,
            correlation_id: notificationBinding.correlation_id,
            interaction_id: response.interaction_id,
            activation_id: notificationBinding.activation_id,
            activation_generation: notificationBinding.activation_generation,
            notifications: [
              productNotification(notifications[1], notificationBinding).result,
              productNotification(notifications[2], notificationBinding).result,
            ],
          },
        });
      } else {
        publishNotification(productNotification(notifications[1], notificationBinding));
      }
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length === 2,
        `C2 first-tail preparation did not overlap prefix playout; synthesized=${calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').map(call => call.params.unit_id).join(',')} notifications=${calls.filter(call => call.method === 'live_voice.composition.p2.notification.next').length} states=${states.slice(-8).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
        5_000,
      );
      if (prefetchPromotion) {
        assert.equal(
          calls.filter(call => call.method === 'live_voice.speech.synthesize_batch')[1]?.params.prefetch_promotion_capability,
          'live-voice.media.prefetch-promotion.v1',
          'mounted successor synthesis did not retain negotiated prefetch capability',
        );
      }
      lifecycle.push('preparing', 'attaching');
      await waitForMounted(
        () => browser.counts.socketOpens >= 4,
        'C2 first-tail downlink did not attach during prefix playout',
      );
      lifecycle.push('attached');
      if (bargeWhileTailPlayAwaitsAttach) {
        // The tail downlink socket is open but the Gateway attach is still
        // pending. Prefix render completion makes the scheduler play the tail,
        // which now waits on that attach. A spoken barge in this window closes
        // the staged route locally: an owned, expected close that must not be
        // promoted to a terminal recovery banner or a failed text status.
        assert.equal(browser.hasHeldDownlinkAttach(), true, 'tail downlink attach was not held');
        browser.endLatestSource();
        await waitForMounted(
          () => calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-prefix',
          ),
          'C2 prefix ACK did not settle while the tail awaited attach',
          5_000,
        );
        await waitForMounted(
          () => states.at(-1)?.p1_status === 'capturing',
          `C2 P1 did not return to capturing while the tail awaited attach; states=${states.slice(-8).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
          5_000,
        );
        assert.equal(browser.counts.sourceStarts, 1, 'unattached tail reached playout');
        assert.equal(browser.hasHeldDownlinkAttach(), true, 'tail downlink attach was released early');
        await browser.emitSpeechStartDuringPlayout();
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
          `C2 barge did not fence the tail awaiting attach; states=${states.slice(-8).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
        );
        await assertNoExpectedCloseFailure(states, 'barge while the tail play awaits its staged attach');
        assert.equal(browser.counts.sourceStarts, 1, 'fenced tail reached playout after barge');
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-tail',
          ),
          false,
          'fenced tail received a presentation ACK after barge',
        );
        assert.equal(projectedMessages.some(event => event.message.role === 'assistant'), false);
        return;
      }
      if (bargeWhileAttaching) {
        await browser.emitSpeechStartDuringPlayout();
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
          'C2 barge did not fence the attaching first tail',
        );
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(browser.counts.sourceStarts, 1, 'attaching first tail reached playout after barge');
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-tail',
          ),
          false,
          'attaching first tail received a presentation ACK after barge',
        );
        assert.equal(projectedMessages.some(event => event.message.role === 'assistant'), false);
        assert.equal(
          states.some(state => state.text_status === 'failed'),
          false,
          `expected barge-in close became a visible failure: ${states
            .filter(state => state.text_status === 'failed')
            .map(state => state.text_reason ?? 'unknown')
            .join(',')}`,
        );
        await assertNoExpectedCloseFailure(states, 'barge while the first tail attaches');
        return;
      }
      await browser.emitDownlinkFrame();
      lifecycle.push('buffered');
      assert.equal(browser.counts.sourceStarts, 1, 'prepared tail played before prefix completion');
      if (admissionOnly) {
        assert.deepEqual(
          calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').map(call => call.params.unit_id),
          ['mounted-c2-prefix', 'mounted-c2-tail'],
          'second batched tail crossed synthesis while its predecessor remained unpromoted',
        );
      }
      if (!batchTails) {
        assert.equal(
          calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length,
          0,
          'prefix ACK was emitted before its audio completed',
        );
      }
      if (exitWhileParkInFlight || bargeWhileParkInFlight) {
        // Retain the successor's PARK reserve so the Browser requests PARK,
        // and hold the Gateway ACK so that transition is still in flight when
        // the local Stop/Exit closes the staged route.
        await browser.emitDownlinkFrames(24, { fromSeq: 1 });
        await waitForMounted(
          () => browser.latestDownlinkControlTypes().includes('media.prefetch_transition'),
          'staged successor did not request PARK after retaining its reserve',
          5_000,
        );
        assert.equal(browser.hasRetainedPrefetchTransition(), true, 'PARK ACK was not held in flight');
        const failureStates = () => states
          .filter(state => state.p1_status === 'failed' || state.text_status === 'failed' || state.p1_reason === 'MEDIA_LOCAL_CLOSE')
          .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`)
          .join(',');
        if (exitWhileParkInFlight) {
          await controlRef.current.close();
          await waitForMounted(() => states.at(-1)?.p1_status === 'closed', 'C2 Exit did not close the parking successor');
        } else {
          await browser.emitSpeechStartDuringPlayout();
          await waitForMounted(
            () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
            'C2 barge did not fence the parking successor',
          );
          await new Promise(resolve => setImmediate(resolve));
        }
        assert.equal(browser.counts.sourceStarts, 1, 'parking successor reached playout after the local close');
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-tail',
          ),
          false,
          'parking successor received a presentation ACK after the local close',
        );
        assert.equal(projectedMessages.some(event => event.message.role === 'assistant'), false);
        assert.equal(
          states.some(state => state.p1_status === 'failed' || state.p1_reason === 'MEDIA_LOCAL_CLOSE'),
          false,
          `expected local close of a parking successor became a P1 failure: ${failureStates()}`,
        );
        assert.equal(
          states.some(state => state.text_status === 'failed'),
          false,
          `expected local close of a parking successor became a visible failure: ${failureStates()}`,
        );
        await assertNoExpectedCloseFailure(states, exitWhileParkInFlight ? 'Exit while PARK in flight' : 'barge while PARK in flight');
        return;
      }
      if (closeWhileBuffered) {
        await controlRef.current.close();
        await waitForMounted(() => states.at(-1)?.p1_status === 'closed', 'C2 Exit did not close buffered successor');
        assert.equal(browser.counts.sourceStarts, 1, 'buffered first tail reached playout after Exit');
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-tail',
          ),
          false,
          'buffered first tail received a presentation ACK after Exit',
        );
        assert.equal(projectedMessages.some(event => event.message.role === 'assistant'), false);
        assert.equal(browser.counts.socketCloses, browser.counts.socketOpens, 'C2 Exit leaked a staged media socket');
        await assertNoExpectedCloseFailure(states, 'Exit while the first tail is buffered');
        return;
      }
      if (bargeDuringPrefetch) {
        await browser.emitSpeechStartDuringPlayout();
        await waitForMounted(
          () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
          'C2 barge did not fence the response during muted first-tail preparation',
        );
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(browser.counts.sourceStarts, 1, 'cancelled first tail reached playout');
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.unit_id === 'mounted-c2-tail',
          ),
          false,
          'cancelled first tail received a presentation ACK',
        );
        assert.equal(
          projectedMessages.some(event => event.message.role === 'assistant'),
          false,
          'cancelled first-tail response wrote authoritative assistant history',
        );
        assert.equal(
          states.some(state => state.text_status === 'failed'),
          false,
          `expected barge-in close became a visible failure: ${states
            .filter(state => state.text_status === 'failed')
            .map(state => state.text_reason ?? 'unknown')
            .join(',')}`,
        );
        await assertNoExpectedCloseFailure(states, 'barge during muted first-tail preparation');
        if (bargeContinuation) {
          // C019-SPOKEN-BARGE-CONTINUATION-01: the successor capture that
          // carried the interrupting speech must stay authoritative until its
          // own EOT and produce exactly one new committed unified submit. The
          // fenced response's successors are discarded, never the capture.
          // The successor capture activated during playout carries the
          // interrupting speech; the earlier subject only owns the fenced
          // response's TTS receipts.
          assert.equal(activationSubjects.length, 2, 'spoken barge scenario did not open exactly one successor capture');
          const interruptingSubject = activationSubjects[1];
          const closedSubjects = () => calls
            .filter(call => call.method === 'live_voice.media.close')
            .map(call => call.params.subject_id);
          assert.equal(
            calls.filter(call => call.method === 'live_voice.media.activate').length,
            2,
            'spoken barge re-allocated a capture instead of retaining the interrupting one',
          );
          await waitForMounted(
            () => ['capturing'].includes(states.at(-1)?.p1_status),
            `interrupting capture did not remain authoritative after the barge fence; states=${states.slice(-12).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
          );
          await browser.emitSpeechEndOfTurnDuringPlayout();
          await waitForMounted(
            () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 2,
            `spoken barge EOT did not submit exactly one new committed turn; submits=${calls.filter(call => call.method === 'live_voice.composition.unified.submit').length} closes=${closedSubjects().join(',')} states=${states.slice(-12).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')} methods=${calls.slice(-20).map(call => call.method).join(',')}`,
            5_000,
          );
          for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
          assert.equal(
            calls.filter(call => call.method === 'live_voice.composition.unified.submit').length,
            2,
            'spoken barge produced more than one committed follow-up submit',
          );
          assert.equal(
            closedSubjects().includes(interruptingSubject),
            false,
            `spoken barge revoked the capture that carried the interrupting speech; closes=${closedSubjects().join(',')} methods=${calls.map(call => `${call.method}${call.method === 'live_voice.media.close' ? `(${call.params.subject_id})` : ''}${call.method === 'live_voice.speech.synthesize_batch' ? `(${call.params.unit_id})` : ''}`).join(',')} states=${states.slice(-12).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
          );
          assert.equal(
            calls.some(
              call => call.method === 'live_voice.composition.p2.presentation.ack'
                && call.params.unit_id === 'mounted-c2-tail',
            ),
            false,
            'fenced response received a late tail ACK after the spoken barge',
          );
          assert.equal(projectedMessages.some(event => event.message.role === 'assistant'), false);
          assert.equal(browser.counts.sourceStarts, 1, 'fenced response released audio after the spoken barge');
          assert.equal(
            states.some(state => state.p1_status === 'failed' || state.p1_reason === 'MEDIA_LOCAL_CLOSE'),
            false,
            `spoken barge continuation became a P1 failure: ${states.filter(state => state.p1_status === 'failed' || state.p1_reason === 'MEDIA_LOCAL_CLOSE').map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}`).join(',')}`,
          );
          await assertNoExpectedCloseFailure(states, 'spoken barge continuation');
        }
        return;
      }
    });
    if (admissionOnly) {
      await act(async () => {
        browser.endLatestSource();
        await waitForMounted(
          () => browser.latestDownlinkControlTypes().includes('media.prefetch_transition'),
          'mounted scheduler did not request exact successor promotion',
        );
        assert.deepEqual(
          calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').map(call => call.params.unit_id),
          ['mounted-c2-prefix', 'mounted-c2-tail'],
          'second batched tail crossed synthesis before exact promotion ACK',
        );
        browser.releasePrefetchPromotion();
        await waitForMounted(
          () => calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length === 3,
          'exact promotion ACK did not admit the second batched tail',
        );
        const synthesisCalls = calls.filter(
          call => call.method === 'live_voice.speech.synthesize_batch',
        );
        assert.deepEqual(
          synthesisCalls.map(call => call.params.unit_id),
          ['mounted-c2-prefix', 'mounted-c2-tail', 'mounted-c2-tail-2'],
        );
        assert.equal(
          synthesisCalls[2].params.prefetch_promotion_capability,
          'live-voice.media.prefetch-promotion.v1',
        );
        for (let turn = 0; turn < 5; turn += 1) {
          await new Promise(resolve => setImmediate(resolve));
        }
        assert.equal(
          calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length,
          3,
          'exact promotion ACK duplicated the admitted successor synthesis',
        );
        await controlRef.current.close();
      });
      return;
    }
    if (
      bargeDuringPrefetch
      || bargeWhileAttaching
      || bargeWhileTailPlayAwaitsAttach
      || closeWhileBuffered
      || exitWhileParkInFlight
      || bargeWhileParkInFlight
    ) return;
    await act(async () => {
      browser.endLatestSource();
      lifecycle.push('predecessor_rendered');
      await waitForMounted(
        () => calls.some(
          call => call.method === 'live_voice.composition.p2.presentation.ack' &&
            call.params.unit_id === 'mounted-c2-prefix',
        ),
        `C2 prefix ACK did not enter settlement; calls=${calls.map(call => call.method).join(',')} states=${states.slice(-12).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
        5_000,
      );
      if (delayPrefixAck) {
        assert.equal(typeof releasePrefixAck, 'function', 'prefix ACK was not retained in flight');
      }
      await waitForMounted(
        () => browser.counts.sourceStarts === 2,
        `C2 tail did not start; sources=${browser.counts.sourceStarts}/${browser.counts.sourceEnds} acks=${calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').map(call => call.params.unit_id).join(',')} states=${states.slice(-10).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
      );
      lifecycle.push('promoted');
      assert.equal(browser.latestDownlinkControlTypes().includes('media.ack'), true);
      lifecycle.push('media_acked');
      if (rejectPrefixAck || retryablePrefixAck) {
        browser.endLatestSource();
        await new Promise(resolve => setTimeout(resolve, retryablePrefixAck ? 1_200 : 50));
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-tail',
          ),
          false,
          'unsettled prefix authority released a later tail ACK',
        );
        assert.equal(
          projectedMessages.some(event => event.message.role === 'assistant'),
          false,
          'unsettled prefix authority wrote assistant history',
        );
        return;
      }
      if (!twoTails) releasePrefixAck?.();
    });
    if (rejectPrefixAck || retryablePrefixAck) return;
    if (twoTails) {
      await act(async () => {
        if (!batchTails) {
          await waitForMounted(
            () => notificationWaiters.length === 1,
            'C2 second-tail prefetch owner was not waiting while first tail played',
          );
          publishNotification(productNotification(notifications[2], notificationBinding));
        }
        await waitForMounted(
          () => calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length === 3,
          'released first tail did not start second-tail synthesis while it still played',
        );
        assert.equal(browser.counts.sourceStarts, 2, 'prepared second tail started before first-tail render completion');
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-tail-2',
          ),
          false,
          'prepared second tail received a presentation ACK before first-tail render completion',
        );
        if (bargeContinuousOneAhead) {
          // Physical B 198ec657b sample 2: unit 1 promoted and playing, unit 2
          // staged with its reserve retained (PARK acknowledged), the third
          // unit still owned by the Gateway (one-ahead fetches it only at the
          // second unit's adoption), then a spoken barge-in. Every fenced
          // callback must settle as an owned cancellation without a Product P1
          // failure, the interrupting capture must stay authoritative until
          // its own EOT, and exactly one new turn must be submitted.
          await browser.emitDownlinkFrame();
          await browser.emitDownlinkFrames(24, { fromSeq: 1 });
          await waitForMounted(
            () => browser.latestDownlinkControlTypes().includes('media.prefetch_transition'),
            'staged second tail did not request PARK after retaining its reserve',
            5_000,
          );
          for (let turn = 0; turn < 10; turn += 1) await new Promise(resolve => setImmediate(resolve));
          assert.equal(browser.hasRetainedPrefetchTransition(), false, 'PARK ACK was not delivered');
          assert.equal(browser.counts.sourceStarts, 2, 'staged second tail played before the active first tail completed');
          p1TransitionDiagnostics.splice(0);
          assert.equal(activationSubjects.length, 2, 'scenario did not open exactly one successor capture');
          const interruptingSubject = activationSubjects[1];
          await browser.emitSpeechStartDuringPlayout();
          await waitForMounted(
            () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
            `C2 barge did not fence the active tail; states=${states.slice(-8).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
          );
          for (let turn = 0; turn < 20; turn += 1) await new Promise(resolve => setImmediate(resolve));
          // The Gateway still holds the fenced response's next audio unit and
          // delivers it through the notification lane after the barge.
          for (let turn = 0; turn < 200 && notificationWaiters.length === 0; turn += 1) {
            await new Promise(resolve => setImmediate(resolve));
          }
          if (notificationWaiters.length === 1) {
            publishNotification(productNotification(notifications[3], notificationBinding));
            for (let turn = 0; turn < 20; turn += 1) await new Promise(resolve => setImmediate(resolve));
          }
          const closedSubjects = () => calls
            .filter(call => call.method === 'live_voice.media.close')
            .map(call => call.params.subject_id);
          assert.deepEqual(
            p1FailureCallers(),
            [],
            `spoken barge raced a Product P1 failure; waiters=${notificationWaiters.length} revokes=${p1RevokeCallers().join(',')} closes=${closedSubjects().join(',')} states=${states.slice(-10).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
          );
          assert.equal(closedSubjects().includes(interruptingSubject), false, `spoken barge revoked the interrupting capture; revokes=${p1RevokeCallers().join(',')}`);
          assert.equal(browser.counts.sourceStarts, 2, 'staged successor played after the spoken barge');
          assert.equal(
            calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length,
            3,
            'fenced third tail crossed synthesis after the spoken barge',
          );
          assert.equal(
            calls.some(
              call => call.method === 'live_voice.composition.p2.presentation.ack'
                && ['mounted-c2-tail', 'mounted-c2-tail-2', 'mounted-c2-tail-3'].includes(call.params.unit_id),
            ),
            false,
            'fenced tail received a presentation ACK after the spoken barge',
          );
          await waitForMounted(
            () => states.at(-1)?.p1_status === 'capturing',
            `interrupting capture did not remain authoritative; states=${states.slice(-10).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
          );
          await assertNoExpectedCloseFailure(states, 'continuous one-ahead spoken barge');
          const delivered = await browser.emitSpeechEndOfTurnDuringPlayout();
          assert.equal(delivered, true, 'interrupting capture could not deliver its EOT');
          await waitForMounted(
            () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 2,
            `spoken barge EOT did not submit exactly one new turn; submits=${calls.filter(call => call.method === 'live_voice.composition.unified.submit').length} failures=${p1FailureCallers().join(',')} states=${states.slice(-10).map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
            5_000,
          );
          for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
          assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 2);
          assert.deepEqual(p1FailureCallers(), []);
          assert.equal(projectedMessages.some(event => event.message.role === 'assistant'), false);
          return;
        }
        if (bargeDuringActiveTail) {
          await browser.emitDownlinkFrame();
          assert.equal(
            browser.counts.sourceStarts,
            2,
            'prepared second tail played before the active first tail completed',
          );
          await browser.emitSpeechStartDuringPlayout();
          await waitForMounted(
            () => calls.some(call => call.method === 'live_voice.composition.p2.barge_in'),
            'C2 barge did not fence the active tail and its staged successor',
          );
          await new Promise(resolve => setImmediate(resolve));
          assert.equal(browser.counts.sourceStarts, 2, 'staged successor played after active-tail barge');
          assert.equal(
            calls.some(
              call => call.method === 'live_voice.composition.p2.presentation.ack'
                && ['mounted-c2-tail', 'mounted-c2-tail-2'].includes(call.params.unit_id),
            ),
            false,
            'active or staged tail received presentation ACK after barge',
          );
          assert.equal(
            states.some(state => state.text_status === 'failed'),
            false,
            `active-tail barge became visible failure: ${states
              .filter(state => state.text_status === 'failed')
              .map(state => state.text_reason ?? 'unknown')
              .join(',')}`,
          );
          return;
        }
        releasePrefixAck?.();
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(browser.counts.sourceStarts, 2, 'prefix ACK adopted the second tail before first-tail render completion');
        assert.equal(states.some(state => state.text_status === 'failed'), false, 'prefix ACK failed the active first tail');
        browser.endLatestSource();
        await browser.emitDownlinkFrame();
        await waitForMounted(
          () => browser.counts.sourceStarts === 3,
          'first-tail render completion did not promote the second tail',
        );
      });
    }
    if (bargeDuringActiveTail || bargeContinuousOneAhead) return;
    await act(async () => {
      browser.endLatestSource();
      lifecycle.push('rendered');
      if (delayLastTailAck) {
        await waitForMounted(
          () => calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === (twoTails ? 'mounted-c2-tail-2' : 'mounted-c2-tail'),
          ),
          'C2 last-tail ACK did not enter delayed settlement',
        );
        await waitForMounted(
          () => rootPublishedWhileLastTailAckPending,
          'C2 authoritative root did not arrive while the last-tail ACK remained in flight',
        );
        for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
        assert.equal(
          states.some(state => state.text_reason === 'TTS_CONTINUATION_LOCAL_RELEASE_FAILED'),
          false,
          'C2 treated its own in-flight last-tail ACK as a foreign root conflict',
        );
        assert.equal(
          calls.some(
            call => call.method === 'live_voice.composition.p2.presentation.ack'
              && call.params.unit_id === 'mounted-c2-root',
          ),
          false,
          'C2 root ACK bypassed the delayed last-tail ACK',
        );
        notificationCallsBeforeLastTailRelease = calls.filter(
          call => call.method === 'live_voice.composition.p2.notification.next',
        ).length;
        assert.equal(typeof releaseLastTailAck, 'function', 'C2 last-tail ACK was not retained in flight');
        releaseLastTailAck();
        await waitForMounted(
          () => projectedMessages.some(
            event => event.message.role === 'assistant' && event.message.content === completeText,
          ),
          `C2 authoritative root was lost after the delayed last-tail ACK settled; states=${states.slice(-10).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
        );
      }
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length === (twoTails ? 4 : 3),
        `C2 root did not settle after both audio units; sources=${browser.counts.sourceStarts}/${browser.counts.sourceEnds} acks=${calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').map(call => call.params.unit_id).join(',')} states=${states.slice(-10).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')}`,
      );
      lifecycle.push('presentation_acked');
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'C2 did not retain successor capture');
      if (notificationCallsBeforeLastTailRelease !== null) {
        await browser.emitSpeechEndOfTurn();
        await waitForMounted(
          () => calls.filter(
            call => call.method === 'live_voice.composition.unified.submit',
          ).length === 2,
          `C2 did not submit the continuous follow-up turn; states=${states.slice(-12).map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`).join(',')} methods=${calls.slice(-20).map(call => call.method).join(',')}`,
        );
        await waitForMounted(
          () => calls.filter(
            call => call.method === 'live_voice.composition.p2.notification.next',
          ).length > notificationCallsBeforeLastTailRelease,
          'C2 did not resume P2 polling for the continuous follow-up turn',
        );
      }
    });

    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').map(call => call.params.unit_id),
      twoTails
        ? ['mounted-c2-prefix', 'mounted-c2-tail', 'mounted-c2-tail-2']
        : ['mounted-c2-prefix', 'mounted-c2-tail'],
    );
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').map(call => call.params.unit_id),
      twoTails
        ? ['mounted-c2-prefix', 'mounted-c2-tail', 'mounted-c2-tail-2', 'mounted-c2-root']
        : ['mounted-c2-prefix', 'mounted-c2-tail', 'mounted-c2-root'],
    );
    assert.deepEqual(
      projectedMessages.map(event => [event.message.role, event.message.content]),
      [
        ['user', 'Explain Paris.'],
        ['assistant', completeText],
        ...(delayLastTailAck ? [['user', 'Explain Paris.']] : []),
      ],
    );
    assert.equal(browser.counts.getUserMedia, 2);
    assert.equal(states.some(state => state.text_reason === 'PRODUCT_AGENT_OUTPUT_FAILED'), false);
    const statesBeforeExit = states.length;
    await act(async () => controlRef.current.close());
    for (let turn = 0; turn < 10; turn += 1) await new Promise(resolve => setImmediate(resolve));
    // Exit closes the retained successor uplink locally (MEDIA_LOCAL_CLOSE).
    // That expected close must never surface as a terminal recovery banner,
    // a failed text status or a failed P1 owner.
    const exitStates = states.slice(statesBeforeExit);
    assert.deepEqual(
      exitStates
        .filter(state => state.recovery_diagnostic !== null || state.text_status === 'failed' || state.p1_status === 'failed' || state.p1_reason === 'MEDIA_LOCAL_CLOSE')
        .map(state => `${state.p1_status}/${state.p1_reason ?? 'none'}/${state.text_status}/${state.text_reason ?? 'none'}/${state.recovery_diagnostic ? `${state.recovery_diagnostic.disposition}:${state.recovery_diagnostic.seam}:${state.recovery_diagnostic.reason}` : 'none'}`),
      [],
      'expected Exit close was promoted to a visible failure',
    );
    lifecycle.push('closed');
    assert.deepEqual(lifecycle, [
      'preparing',
      'attaching',
      'attached',
      'buffered',
      'predecessor_rendered',
      'promoted',
      'media_acked',
      'rendered',
      'presentation_acked',
      'closed',
    ]);
  } finally {
    releaseLastTailAck?.();
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
}

test('mounted C2 prebuffers the first tail and completes the ordered lifecycle', async () => {
  await runMountedC2FirstTailScenario();
});

test('mounted C2 promotes the staged tail before a delayed prefix ACK settles', async () => {
  await runMountedC2FirstTailScenario({ delayPrefixAck: true });
});

test('mounted C2 keeps local render as the sole adoption authority across two prefetched tails', async () => {
  await runMountedC2FirstTailScenario({ delayPrefixAck: true, twoTails: true });
});

test('mounted C2 preserves its authoritative root while the last-tail ACK is in flight', async () => {
  await runMountedC2FirstTailScenario({ delayLastTailAck: true, twoTails: true });
});

test('mounted C2 notification batch defers the second negotiated tail until exact promotion ACK', async () => {
  await runMountedC2FirstTailScenario({
    twoTails: true,
    prefetchPromotion: true,
    batchTails: true,
    admissionOnly: true,
  });
});

test('mounted C2 terminal prefix ACK rejection fences every later tail ACK and history effect', async () => {
  await runMountedC2FirstTailScenario({ rejectPrefixAck: true });
});

test('mounted C2 retryable prefix ACK uncertainty retains FIFO ownership over later tail ACKs', async () => {
  await runMountedC2FirstTailScenario({ retryablePrefixAck: true });
});

test('mounted C2 barge during muted first-tail preparation releases no tail audio or ACK', async () => {
  await runMountedC2FirstTailScenario({ bargeDuringPrefetch: true });
});

test('mounted C2 spoken barge keeps the interrupting capture authoritative until its own EOT submits one new turn', async () => {
  await runMountedC2FirstTailScenario({ bargeDuringPrefetch: true, bargeContinuation: true });
});

test('mounted C2 spoken barge over a negotiated staged successor keeps the interrupting capture authoritative', async () => {
  await runMountedC2FirstTailScenario({ prefetchPromotion: true, bargeDuringPrefetch: true, bargeContinuation: true });
});

test('mounted C2 spoken barge while the tail play awaits its staged attach is an expected close', async () => {
  await runMountedC2FirstTailScenario({ bargeWhileTailPlayAwaitsAttach: true });
});

test('mounted C2 barge while the first tail attaches fences every late tail effect', async () => {
  await runMountedC2FirstTailScenario({ bargeWhileAttaching: true });
});

test('mounted C2 spoken barge over a promoted tail, a parked successor and a queued third unit keeps the capture and submits once', async () => {
  await runMountedC2FirstTailScenario({
    twoTails: true,
    prefetchPromotion: true,
    bargeContinuousOneAhead: true,
  });
});

test('mounted C2 barge during active tail keeps staged successor close invisible', async () => {
  await runMountedC2FirstTailScenario({
    twoTails: true,
    prefetchPromotion: true,
    bargeDuringActiveTail: true,
  });
});

test('mounted C2 Exit while the successor PARK is in flight is an expected close', async () => {
  await runMountedC2FirstTailScenario({
    prefetchPromotion: true,
    exitWhileParkInFlight: true,
  });
});

test('mounted C2 barge while the successor PARK is in flight is an expected close', async () => {
  await runMountedC2FirstTailScenario({
    prefetchPromotion: true,
    bargeWhileParkInFlight: true,
  });
});

test('mounted C2 Exit while the first tail is buffered closes the staged slot exactly once', async () => {
  await runMountedC2FirstTailScenario({ closeWhileBuffered: true });
});

test('mounted unified hands-free itinerary journey auto-submits and keeps one current task', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-unified-session';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const projectedMessages = [];
  const utterances = [
    '帮我根据这些要求制定三天的行程。',
    '不用停止后台任务，告诉我第二天最早的固定安排是什么。',
    '第一天晚上给我留出的自由时间是几点？',
    '后台现在做到哪了？',
    '停止刚才的行程规划。',
  ];
  const answers = [
    '后台任务已受理，正在等待执行。开始执行后会显示正在执行。',
    '最终结果尚未生成；后台任务当前尚未结束。',
    '最终结果尚未生成；后台任务当前尚未结束。',
    '后台任务已受理，正在等待执行，尚未生成最终结果。',
    '已请求停止。',
  ];
  let recognitionIndex = 0;
  let presentationGeneration = 0;
  let activeMediaBinding = null;
  let currentTaskNonTerminal = false;
  let createEffects = 0;
  let cancelEffects = 0;
  let releaseFirstUnifiedResponse = null;
  const queuedNotifications = [];
  const notificationWaiters = [];
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  let renderer;

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.media.activate') {
      activeMediaBinding = mountedMediaBinding(params, calls.filter(call => call.method === method).length);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: 'mounted-unified-media-subject',
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'U'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-playout-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      const text = utterances[recognitionIndex];
      recognitionIndex += 1;
      return mountedRecognition(params, text, recognitionIndex);
    }
    if (method === 'live_voice.composition.unified.submit') {
      const text = params.text;
      const index = utterances.indexOf(text);
      assert.notEqual(index, -1);
      assert.equal(params.input_state, 'final');
      assert.equal('dispatch_target' in params, false);
      assert.equal('critical_confirmation' in params, false);
      if (index === 0) {
        assert.equal(currentTaskNonTerminal, false);
        currentTaskNonTerminal = true;
        createEffects += 1;
      } else if (index === 1) {
        assert.equal(currentTaskNonTerminal, true);
        assert.equal(text.startsWith('不用停止'), true);
      } else if (index === 4) {
        assert.equal(currentTaskNonTerminal, true);
        currentTaskNonTerminal = false;
        cancelEffects += 1;
      }
      presentationGeneration += 1;
      const response = {
        interaction_id: params.interaction_id,
        response_id: `mounted-unified-response-${presentationGeneration}`,
        response_generation: presentationGeneration,
      };
      publishNotification({
        ok: true,
        result: {
          status: 'notification',
          session_id: params.session_id,
          correlation_id: params.correlation_id,
          interaction_id: params.interaction_id,
          activation_id: params.activation_id,
          activation_generation: params.activation_generation,
          kind: 'agent.output',
          response,
          agent_event: { event_type: 'chat.final', text: answers[index] },
          presentation_unit: {
            surface: 'text',
            unit_id: `unit-${presentationGeneration}`,
            seq: 0,
            content_ref: `sha256:${String(presentationGeneration).padStart(64, '0')}`,
          },
        },
      });
      if (index === 0) {
        await new Promise(resolve => {
          releaseFirstUnifiedResponse = resolve;
        });
      }
      return {
        request_id: options.requestId,
        ok: true,
        result: { status: 'authoritative_presentation_accepted', response },
        error: null,
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected unified mounted request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          onProductVoiceStateChange: state => states.push(state),
          onProductVoiceMessage: event => projectedMessages.push(event),
        }),
      );
      await waitForMounted(() => controlRef.current !== null && states.at(-1)?.available === true, 'unified Live Voice did not become available');
    });
    const diagnosticOwner = renderer.root.findByProps({ 'data-testid': 'live-voice-integrated-route' });
    assert.equal(diagnosticOwner.props.hidden, true);
    assert.equal(diagnosticOwner.props['aria-hidden'], 'true');

    await act(async () => {
      void controlRef.current.start();
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'unified Live Voice did not begin its first capture');
    });
    for (let index = 0; index < utterances.length; index += 1) {
      await act(async () => {
        await waitForMounted(() => ['starting', 'capturing'].includes(states.at(-1)?.p1_status), `turn ${index + 1} did not prepare listening`);
        if (states.at(-1)?.p1_status === 'starting') await browser.emitFirstFrame();
        await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', `turn ${index + 1} did not enter listening`);
        await browser.emitSpeechEndOfTurn();
        await waitForMounted(
          () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === index + 1,
          `turn ${index + 1} was not auto-submitted exactly once`,
        );
        if (index === 0) {
          await waitForMounted(
            () => typeof releaseFirstUnifiedResponse === 'function',
            'first unified response gate was not retained',
          );
          for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
          assert.equal(
            calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length,
            0,
            'a pop-on-read foreground presentation must not be consumed before unified.submit returns its exact response fence',
          );
          assert.equal(
            projectedMessages.filter(event => event.message.role === 'assistant').length,
            0,
            'a pre-fence foreground presentation must not enter visible history',
          );
          assert.equal(
            calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack').length,
            0,
            'a pre-fence foreground presentation must not be ACKed',
          );
          releaseFirstUnifiedResponse();
          releaseFirstUnifiedResponse = null;
        }
        await waitForMounted(() => states.at(-1)?.p1_status === 'playing', `turn ${index + 1} was not read aloud`);
        await waitForMounted(() => browser.counts.sourceStarts === index + 1, `turn ${index + 1} did not schedule its authoritative browser audio`);
      });
      await act(async () => {
        browser.endLatestSource();
        await new Promise(resolve => setImmediate(resolve));
      });
      if (index < utterances.length - 1) {
        await act(async () => {
          await waitForMounted(
            () => ['starting', 'capturing'].includes(states.at(-1)?.p1_status),
            `turn ${index + 1} did not automatically resume listening: ${states.map(state => `${state.p1_status}/${state.text_status}/retained=${state.operation_retained}`).join(',')} calls=${calls.map(call => call.method).join(',')} sources=${browser.counts.sourceStarts}/${browser.counts.sourceEnds}`,
          );
        });
      }
    }
    assert.equal(createEffects, 1);
    assert.equal(cancelEffects, 1);
    assert.equal(answers.slice(0, 4).some(answer => answer.includes('运行')), false);
    assert.equal(browser.endOfTurnSignals.length, utterances.length);
    assert.equal(
      browser.endOfTurnSignals.every(event => event.speech_started_observed === true),
      true,
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.submit').length, 0);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p3.mutate').length, 0);
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.unified.submit').map(call => call.params.text),
      utterances,
    );
    assert.deepEqual(
      projectedMessages.map(event => [event.session_id, event.message.role, event.message.content]),
      utterances.flatMap((text, index) => [
        [sessionId, 'user', text],
        [sessionId, 'assistant', answers[index]],
      ]),
    );
    assert.equal(new Set(projectedMessages.map(event => event.message.id)).size, projectedMessages.length);

    const captureCountBeforeExit = browser.counts.getUserMedia;
    await act(async () => {
      await controlRef.current.close();
      await new Promise(resolve => setTimeout(resolve, 5));
    });
    assert.equal(browser.counts.getUserMedia, captureCountBeforeExit);
    assert.equal(states.at(-1)?.p1_status, 'closed');
    assert.equal(states.at(-1)?.recovery_diagnostic, null);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

test('mounted foreground status query restarts an idle P2 poll after background terminal settlement', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-terminal-dialogue-session';
  const taskId = 'mounted-terminal-dialogue-task';
  const statusResponse = 'mounted-terminal-dialogue-status';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  const recognizedTexts = [
    '帮我在后台制定一份三天杭州行程。',
    '上海晚上有什么适合逛逛顺便吃东西的地方？',
    '后台任务怎么样了？',
  ];
  let progressListener = null;
  let progressActivation = null;
  let taskControlBinding = null;
  let taskStatusBootstrapFailuresRemaining = 1;
  let taskTerminal = false;
  let p2Binding = null;
  let activeMediaBinding = null;
  let recognitionIndex = 0;
  let keepaliveAfterTaskStart = false;
  let releaseStatusAck = null;
  let statusAckAttempts = 0;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const progressSubscribe = listener => {
    progressListener = listener;
    return () => {
      if (progressListener === listener) progressListener = null;
    };
  };
  const publishNotification = notification => {
    const waiter = notificationWaiters.shift();
    if (waiter) waiter(notification);
    else queuedNotifications.push(notification);
  };
  const keepalive = binding => ({
    ok: true,
    result: {
      status: 'notification',
      ...binding,
      kind: 'transport.keepalive',
      response: null,
      agent_event: null,
      progress_event: null,
      presentation_unit: null,
    },
  });
  const presentation = (binding, responseId, responseGeneration, text, taskNotification = false) => ({
    ok: true,
    result: {
      status: 'notification',
      ...binding,
      kind: 'agent.output',
      response: {
        interaction_id: binding.interaction_id,
        response_id: responseId,
        response_generation: responseGeneration,
      },
      agent_event: {
        event_type: 'chat.final',
        text,
        ...(taskNotification ? { source_provenance: 'server.task_notification' } : {}),
      },
      presentation_unit: {
        surface: 'text',
        unit_id: `${responseId}-unit`,
        seq: 0,
        content_ref: `sha256:${String(responseGeneration).padStart(64, '0')}`,
      },
    },
  });

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') return activateP2(params);
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      if (keepaliveAfterTaskStart && p2Binding !== null) {
        keepaliveAfterTaskStart = false;
        return keepalive(p2Binding);
      }
      return new Promise(resolve => notificationWaiters.push(resolve));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.response_id === statusResponse) {
        statusAckAttempts += 1;
        if (statusAckAttempts === 1) {
          return new Promise((_resolve, reject) => {
            releaseStatusAck = () => reject(Object.assign(new Error('visible-text ACK result is unknown'), {
              code: 'REQUEST_TIMEOUT',
              reason: 'REQUEST_TIMEOUT',
              retriable: true,
            }));
          });
        }
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.task.status') {
      assert.ok(taskControlBinding);
      if (taskStatusBootstrapFailuresRemaining > 0) {
        taskStatusBootstrapFailuresRemaining -= 1;
        throw Object.assign(new Error('mounted first created-task bootstrap is unavailable'), {
          reason: 'REQUEST_TIMEOUT',
        });
      }
      return mountedP3Status(taskControlBinding, { taskId });
    }
    if (method === 'live_voice.task.events') {
      assert.ok(taskControlBinding);
      return mountedP3Events(taskControlBinding, { taskId, terminalA: taskTerminal, terminalAOutcome: 'completed' });
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.progress.activate') {
      progressActivation = { ...params };
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-terminal-dialogue-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'J'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-terminal-dialogue-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      const text = recognizedTexts[recognitionIndex];
      recognitionIndex += 1;
      if (typeof text !== 'string') throw new Error('unexpected extra mounted recognition');
      return mountedRecognition(params, text, recognitionIndex);
    }
    if (method === 'live_voice.composition.unified.submit') {
      const submitIndex = calls.filter(call => call.method === method).length;
      p2Binding = {
        session_id: params.session_id,
        correlation_id: params.correlation_id,
        interaction_id: params.interaction_id,
        activation_id: params.activation_id,
        activation_generation: params.activation_generation,
      };
      if (submitIndex === 1) {
        taskControlBinding = {
          subject_id: 'mounted-terminal-dialogue-subject',
          session_id: params.session_id,
          project_id: 'mounted-terminal-dialogue-project',
          correlation_id: params.correlation_id,
          generation: 1,
        };
      }
      const response = {
        interaction_id: params.interaction_id,
        response_id:
          submitIndex === 1
            ? 'mounted-terminal-dialogue-start'
            : submitIndex === 2
              ? 'mounted-terminal-dialogue-answer'
              : 'mounted-terminal-dialogue-status',
        response_generation: submitIndex === 3 ? 4 : submitIndex,
      };
      if (submitIndex === 1) {
        keepaliveAfterTaskStart = true;
        publishNotification(
          presentation(
            p2Binding,
            response.response_id,
            response.response_generation,
            '后台任务已受理，正在等待执行。开始执行后会显示正在执行。',
          ),
        );
      } else if (submitIndex === 3) {
        publishNotification(
          presentation(
            p2Binding,
            response.response_id,
            response.response_generation,
            '后台任务已完成。',
          ),
        );
      }
      const result = {
        request_id: options.requestId,
        ok: true,
        error: null,
        result:
          submitIndex === 1
            ? {
                status: 'authoritative_presentation_accepted',
                response,
                task_id: taskId,
              }
            : submitIndex === 3
              ? {
                  status: 'authoritative_presentation_accepted',
                  response,
                }
            : {
                status: 'round_accepted',
                session_id: params.session_id,
                correlation_id: params.correlation_id,
                interaction_id: params.interaction_id,
                activation_id: params.activation_id,
                activation_generation: params.activation_generation,
                turn_id: params.turn_id,
                commit_id: params.commit_id,
                request_id: 'mounted-terminal-dialogue-agent-request',
                round_id: 'mounted-terminal-dialogue-round',
                response,
              },
      };
      return result;
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected mounted terminal dialogue request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          progressSubscribe,
          p3RetryInspectionWait: async () => undefined,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(() => controlRef.current !== null && states.at(-1)?.available === true, 'terminal dialogue route unavailable');
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'terminal dialogue initial capture unavailable');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(() => states.at(-1)?.p1_status === 'playing', 'task-start response did not play');
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'task-start audio did not reach the browser');
      browser.endLatestSource();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-dialogue-start'),
        'task-start response was not ACKed',
      );
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'starting',
        `listening did not restart after task-start; states=${states
          .slice(-12)
          .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}/${state.text_reason ?? 'none'}`)
          .join(',')}; methods=${calls
          .slice(-20)
          .map(call => call.method)
          .join(',')}`,
      );
      await browser.emitFirstFrame(0);
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'intervening dialogue capture unavailable');
      await waitForMounted(
        () => progressActivation?.task_id === taskId && typeof progressListener === 'function',
        'voice-created task did not retain its exact progress wakeup before intervening dialogue',
      );
      await assert.rejects(
        controlRef.current.refreshTasks(),
        /FORMAL_P3_REQUEST_REJECTED|formal P3 response result is invalid/i,
        'a failed Task collection refresh must remain a fail-closed UI read',
      );
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
      assert.equal(calls.filter(call => call.method === 'live_voice.task.status').length, 3);
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 2,
        `intervening dialogue was not accepted; states=${states
          .slice(-12)
          .map(state => `${state.p1_status}/${state.text_status}/${state.text_reason ?? 'none'}`)
          .join(',')}; methods=${calls
          .slice(-20)
          .map(call => call.method)
          .join(',')}`,
      );
      for (let turn = 0; turn < 5; turn += 1) await new Promise(resolve => setImmediate(resolve));
      await waitForMounted(() => notificationWaiters.length > 0, 'intervening dialogue did not own a pending P2 poll');
      taskTerminal = true;
      progressListener(
        mountedTerminalProgress(
          taskControlBinding,
          progressActivation,
          'completed',
          taskId,
          'attempt-a',
          2,
        ),
      );
      await waitForMounted(
        () => states.at(-1)?.terminal_announcement_state === 'queued',
        'background terminal announcement did not remain queued behind the foreground response',
      );
      assert.equal(states.at(-1)?.text_status, 'waiting');
      assert.equal(
        calls.filter(call => call.method === 'live_voice.speech.synthesize_batch').length,
        1,
        'queued terminal completion must not speak before the foreground response',
      );
    });

    const pollsBeforeKeepalive = calls.filter(call => call.method === 'live_voice.composition.p2.notification.next').length;
    await act(async () => {
      publishNotification(keepalive(p2Binding));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.notification.next').length > pollsBeforeKeepalive && notificationWaiters.length > 0,
        `foreground dialogue yielded P2 after keepalive; states=${states
          .slice(-10)
          .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}`)
          .join(',')}`,
      );
      assert.equal(states.at(-1)?.text_status, 'waiting');
      assert.notEqual(states.at(-1)?.p1_status, 'starting');
      assert.notEqual(states.at(-1)?.p1_status, 'capturing');
      publishNotification(presentation(p2Binding, 'mounted-terminal-dialogue-answer', 2, '可以去外滩、南京东路和云南南路。'));
      await waitForMounted(() => states.at(-1)?.p1_status === 'playing', 'intervening dialogue response did not play');
      await waitForMounted(() => browser.counts.sourceStarts === 2, 'intervening dialogue audio did not reach the browser');
      browser.endLatestSource();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-dialogue-answer').length === 1,
        'intervening dialogue response was not ACKed exactly once',
      );
      await waitForMounted(() => notificationWaiters.length > 0, 'background terminal check did not retain its post-dialogue P2 poll');
      publishNotification(
        presentation(
          p2Binding,
          'mounted-terminal-dialogue-complete',
          3,
          '后台任务已完成，结果已经准备好。',
          true,
        ),
      );
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'playing',
        `background terminal announcement did not play after foreground ACK; states=${states
          .slice(-16)
          .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}/retained=${state.operation_retained}`)
          .join(',')}; methods=${calls.slice(-24).map(call => call.method).join(',')}`,
      );
      await waitForMounted(() => browser.counts.sourceStarts === 3, 'background terminal audio did not reach the browser');
      browser.endLatestSource();
      await waitForMounted(
        () => calls.filter(call =>
          call.method === 'live_voice.composition.p2.presentation.ack'
          && call.params.response_id === 'mounted-terminal-dialogue-complete').length === 1,
        'background terminal announcement was not ACKed exactly once',
      );
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'listening did not resume after terminal announcement');
      await browser.emitFirstFrame(0);
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'terminal announcement successor capture unavailable');
      // Resolve the cancelled predecessor long-poll while capture is active.
      // The next foreground query must create its own notification.next;
      // retaining a fixture waiter here would mask the production wakeup bug.
      while (notificationWaiters.length > 0) publishNotification(keepalive(p2Binding));
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(notificationWaiters.length, 0, 'predecessor P2 poll did not reach a true idle boundary');
      const pollsBeforeStatusQuery = calls.filter(call => call.method === 'live_voice.composition.p2.notification.next').length;
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.unified.submit').length === 3,
        'post-terminal status query was not submitted exactly once',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.notification.next').length > pollsBeforeStatusQuery,
        'post-terminal status query did not restart P2 notification polling',
      );
      await waitForMounted(
        () => states.at(-1)?.p1_status === 'playing',
        `post-terminal status response did not play; states=${states
          .slice(-16)
          .map(state => `${state.p1_status}/${state.text_status}/${state.terminal_announcement_state}/${state.text_reason ?? 'none'}`)
          .join(',')}; methods=${calls.slice(-24).map(call => call.method).join(',')}`,
      );
      await waitForMounted(() => browser.counts.sourceStarts === 4, 'post-terminal status audio did not reach the browser');
    });

    const currentStatusResponse = calls
      .filter(call => call.method === 'live_voice.speech.synthesize_batch')
      .at(-1)?.params.response;
    assert.equal(currentStatusResponse?.response_id, statusResponse);
    const predecessorGeneration = p2Binding.activation_generation;
    await act(async () => {
      browser.endLatestSource();
      await waitForMounted(() => typeof releaseStatusAck === 'function', 'visible-text ACK did not enter its original transport');
      await controlRef.current.close();
      await controlRef.current.start();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.close' && call.params.activation_generation === predecessorGeneration),
        'TTS Exit did not close the exact predecessor P2 generation',
      );
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.activate' && call.params.activation_generation === predecessorGeneration + 1),
        'TTS Exit did not activate one P2 successor generation',
      );
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'TTS Exit successor did not restart listening');
      await browser.emitFirstFrame(0);
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'TTS Exit successor capture unavailable');
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === statusResponse).length,
        1,
        'the retired visible-text ACK replayed while its original transport remained in flight',
      );
      releaseStatusAck();
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === statusResponse).length === 2,
        'the original visible-text ACK timeout did not wake same-id durable recovery',
      );
      await waitForMounted(() => {
        const journal = JSON.parse(
          globalThis.window.sessionStorage.getItem(
            `jiuwenswarm.liveVoice.productP2ActivationJournal.v1:${encodeURIComponent(sessionId)}`,
          ),
        );
        return journal.retired_presentation_acks.length === 0;
      }, 'the visible-text ACK durable ledger did not return to zero');
    });

    assert.equal(calls.filter(call => call.method === 'live_voice.speech.recognize_batch').length, 3);
    assert.deepEqual(
      calls.filter(call => call.method === 'live_voice.composition.unified.submit').map(call => call.params.text),
      recognizedTexts,
    );
    const presentationAckOrder = calls
      .filter(call => call.method === 'live_voice.composition.p2.presentation.ack')
      .map(call => call.params.response_id);
    assert.ok(
      presentationAckOrder.indexOf('mounted-terminal-dialogue-answer')
        < presentationAckOrder.indexOf('mounted-terminal-dialogue-complete'),
      'foreground response ACK must settle before the queued terminal announcement ACK',
    );
    assert.equal(
      calls.filter(call =>
        call.method === 'live_voice.speech.synthesize_batch'
        && call.params.response.response_id === 'mounted-terminal-dialogue-complete').length,
      1,
    );
    assert.equal(states.at(-1)?.terminal_announcement_state, 'idle');
    assert.equal(states.at(-1)?.recovery_diagnostic, null);
    const statusAckCalls = calls.filter(
      call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === statusResponse,
    );
    assert.equal(statusAckCalls.length, 2, 'TTS Exit must settle the exact durable text ACK after its original timeout');
    assert.equal(statusAckCalls[1].requestId, statusAckCalls[0].requestId, 'visible-text ACK recovery changed request identity');
    assert.equal(states.at(-1)?.text_status, 'idle', 'the exited visible-text ACK success polluted successor text status');
    assert.equal(states.at(-1)?.text_reason, null, 'the exited visible-text ACK success published a stale reason');
    assert.equal(
      calls.filter(call => call.method === 'live_voice.speech.synthesize_batch' && call.params.response.response_id === statusResponse).length,
      1,
      'TTS Exit must not replay status speech into the successor generation',
    );
    assert.equal(
      calls.some(call => call.method.includes('task.cancel') || call.method.includes('task.mutate') || call.method === 'live_voice.composition.p3.mutate'),
      false,
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});

// Superseded by the exact P3 TEXT fallback regression above. This legacy
// harness fabricates P2 TEXT agent.output notifications that the server no
// longer emits after presentation.failed.
test.skip('mounted voice-created Task keeps polling through provider-starting capture and running AUDIO fallback', async () => {
  const i18n = await createI18n();
  const sessionId = 'mounted-terminal-idle-session';
  const taskId = 'mounted-terminal-idle-task';
  const controlRef = { current: null };
  const states = [];
  const calls = [];
  const queuedNotifications = [];
  const notificationWaiters = [];
  let progressListener = null;
  let progressActivation = null;
  let taskControlBinding = null;
  let taskTerminal = false;
  let p2Binding = null;
  let activeMediaBinding = null;
  let keepaliveAfterTaskStart = false;
  let recognitionCalls = 0;
  let renderer;
  const browser = installP1BrowserEnvironment({ mediaBinding: () => activeMediaBinding });
  const activateP2 = createMountedP2ActivationResponder();
  const progressSubscribe = listener => {
    progressListener = listener;
    return () => {
      if (progressListener === listener) progressListener = null;
    };
  };
  const publishNotification = notification => {
    const result = notification?.result;
    let matchingIndex = -1;
    for (let index = notificationWaiters.length - 1; index >= 0; index -= 1) {
      const waiter = notificationWaiters[index];
      if (
        result &&
        waiter.binding.activation_id === result.activation_id &&
        waiter.binding.activation_generation === result.activation_generation
      ) {
        matchingIndex = index;
        break;
      }
    }
    const waiter = matchingIndex >= 0 ? notificationWaiters.splice(matchingIndex, 1)[0] : undefined;
    if (waiter) waiter.resolve(notification);
    else queuedNotifications.push(notification);
  };
  const presentation = (
    binding,
    responseId,
    responseGeneration,
    text,
    taskNotification = false,
    surface = taskNotification ? 'audio' : 'text',
  ) => ({
    ok: true,
    result: {
      status: 'notification',
      ...binding,
      kind: 'agent.output',
      response: {
        interaction_id: binding.interaction_id,
        response_id: responseId,
        response_generation: responseGeneration,
      },
      agent_event: {
        event_type: 'chat.final',
        text,
        ...(taskNotification ? { source_provenance: 'server.task_notification' } : {}),
      },
      presentation_unit: {
        surface,
        unit_id: `${responseId}-unit`,
        seq: 0,
        content_ref: `sha256:${String(responseGeneration).padStart(64, '0')}`,
      },
    },
  });
  const keepalive = binding => ({
    ok: true,
    result: {
      status: 'notification',
      ...binding,
      kind: 'transport.keepalive',
      response: null,
      agent_event: null,
      progress_event: null,
      presentation_unit: null,
    },
  });

  const request = async (method, params, options) => {
    calls.push({ method, params: { ...params }, requestId: options?.requestId ?? null });
    if (method === 'live_voice.composition.p2.activate') {
      p2Binding = { ...params };
      return activateP2(params);
    }
    if (method === 'live_voice.composition.p2.close') return { ok: true, result: { status: 'closed', ...params } };
    if (method === 'live_voice.composition.p2.notification.next') {
      if (queuedNotifications.length > 0) return queuedNotifications.shift();
      if (keepaliveAfterTaskStart && p2Binding !== null) {
        keepaliveAfterTaskStart = false;
        return keepalive(p2Binding);
      }
      return new Promise(resolve => notificationWaiters.push({ resolve, binding: { ...params } }));
    }
    if (method === 'live_voice.composition.p2.presentation.ack') {
      if (params.response_id === 'mounted-terminal-idle-complete') {
        throw Object.assign(new Error('mounted terminal ACK belongs to a stale response generation'), {
          code: 'STALE',
          reason: 'STALE_RESPONSE_OUTPUT',
        });
      }
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'presentation_acknowledged',
          ...params,
          accepted: true,
          replayed: false,
          history_records_written: 1,
          history_pending: false,
        },
      };
    }
    if (method === 'live_voice.composition.p2.presentation.failed') {
      if (p2Binding !== null && params.response_id === 'mounted-terminal-idle-running') {
        publishNotification(
          presentation(
            p2Binding,
            'mounted-terminal-idle-running-text',
            20,
            'Background task update: running.',
            true,
            'text',
          ),
        );
      }
      if (p2Binding !== null && params.response_id === 'mounted-terminal-idle-complete') {
        publishNotification(
          presentation(
            p2Binding,
            'mounted-terminal-idle-complete-text',
            30,
            '后台任务已完成，结果已经准备好。',
            true,
            'text',
          ),
        );
      }
      return {
        ok: true,
        result: {
          status: 'presentation_failed_fallback_text',
          ...params,
          fallback: 'text',
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.task.status') {
      assert.ok(taskControlBinding);
      return mountedP3Status(taskControlBinding, { taskId });
    }
    if (method === 'live_voice.task.events') {
      assert.ok(taskControlBinding);
      return mountedP3Events(taskControlBinding, {
        taskId,
        terminalA: taskTerminal,
        terminalAOutcome: 'completed',
      });
    }
    if (method === 'live_voice.task.list') return { ok: true, result: { tasks: [] } };
    if (method === 'live_voice.composition.p3.progress.activate') {
      progressActivation = { ...params };
      assert.equal(typeof progressListener, 'function');
      progressListener(
        mountedLifecycleProgress(taskControlBinding, progressActivation, {
          state: 'accepted',
          eventType: 'task.accepted',
          seq: 0,
          taskId,
        }),
      );
      progressListener(
        mountedLifecycleProgress(taskControlBinding, progressActivation, {
          state: 'running',
          eventType: 'task.running',
          seq: 1,
          taskId,
        }),
      );
      return { ok: true, result: mountedProgressActivation(params) };
    }
    if (method === 'live_voice.composition.p3.progress.ack') {
      return {
        ok: true,
        result: {
          status: 'acknowledged',
          attempt_id: 'attempt-a',
          ...params,
          acknowledgement: 'web_ui_text_consumed',
          replayed: false,
        },
      };
    }
    if (method === 'live_voice.composition.p3.progress.close') {
      return { ok: true, result: { status: 'closed', ...params } };
    }
    if (method === 'live_voice.media.activate') {
      const index = calls.filter(call => call.method === method).length;
      activeMediaBinding = mountedMediaBinding(params, index);
      return {
        status: 'active',
        reason_id: 'MEDIA_ROUTE_TICKET_ISSUED',
        subject_id: `mounted-terminal-idle-media-${index}`,
        endpoint_path: '/ws/live-voice/media',
        media_ticket: 'I'.repeat(43),
        subprotocol: 'live-voice.media.v1',
        ticket_ttl_ms: 30_000,
        end_of_turn: {
          status: 'active',
          capability_version: 'media.end_of_turn.v1',
          detector: 'server_vad',
          create_response: false,
          interrupt_response: false,
        },
        binding: activeMediaBinding,
        privacy: { raw_audio_persisted: false, raw_audio_logged: false, memory_only: true },
      };
    }
    if (method === 'live_voice.media.close') return { status: 'closed', reason_id: 'MEDIA_ROUTE_REVOKED', ...params };
    if (method === 'live_voice.media.playout_receipt') {
      return {
        status: 'media_playout_acknowledged',
        reason_id: 'MEDIA_PLAYOUT_RECEIPT_ACCEPTED',
        receipt_id: `mounted-terminal-idle-receipt-${params.response_id}`,
        ...params,
        duplex_media_observed: false,
      };
    }
    if (method === 'live_voice.speech.recognize_batch') {
      recognitionCalls += 1;
      if (recognitionCalls === 1) {
        return mountedRecognition(params, '帮我在后台制定一份三天杭州行程。', 1);
      }
      throw Object.assign(new Error('mounted idle capture contained no committed speech'), {
        reason: 'SPEECH_PROVIDER_EMPTY_TRANSCRIPT',
      });
    }
    if (method === 'live_voice.composition.unified.submit') {
      p2Binding = {
        session_id: params.session_id,
        correlation_id: params.correlation_id,
        interaction_id: params.interaction_id,
        activation_id: params.activation_id,
        activation_generation: params.activation_generation,
      };
      taskControlBinding = {
        subject_id: 'mounted-terminal-idle-subject',
        session_id: params.session_id,
        project_id: 'mounted-terminal-idle-project',
        correlation_id: params.correlation_id,
        generation: 1,
      };
      const response = {
        interaction_id: params.interaction_id,
        response_id: 'mounted-terminal-idle-start',
        response_generation: 1,
      };
      keepaliveAfterTaskStart = true;
      publishNotification(
        presentation(
          p2Binding,
          response.response_id,
          response.response_generation,
          '后台任务已受理，正在等待执行。开始执行后会显示正在执行。',
        ),
      );
      return {
        request_id: options.requestId,
        ok: true,
        error: null,
        result: {
          status: 'authoritative_presentation_accepted',
          response,
          task_id: taskId,
        },
      };
    }
    if (method === 'live_voice.speech.synthesize_batch') {
      return {
        contract_version: 'live-voice.contract.v2',
        request_id: params.request_id,
        operation_id: params.operation_id,
        ok: true,
        error: null,
        result: {
          operation: 'speech.synthesize.batch',
          response: params.response,
          unit_id: params.unit_id,
          audio: {
            format: 'wav_pcm16_mono',
            sample_rate_hz: 48_000,
            channel_count: 1,
            data_base64: mountedWavBase64(),
          },
          provider: {
            provider_id: 'mounted-provider',
            implementation_class: 'formal',
            fallback_from: null,
            model: 'mounted-tts',
            voice: 'mounted-voice',
          },
          presented: false,
        },
      };
    }
    throw new Error(`unexpected mounted terminal idle request: ${method}`);
  };

  try {
    await act(async () => {
      renderer = create(
        mountedFullyEnabledElement(i18n, sessionId, request, true, {
          productVoiceControlRef: controlRef,
          progressSubscribe,
          taskNotificationPlayoutTimeoutMs: 25,
          onProductVoiceStateChange: state => states.push(state),
        }),
      );
      await waitForMounted(() => controlRef.current !== null && states.at(-1)?.available === true, 'terminal idle route unavailable');
      void controlRef.current.start();
      await browser.emitFirstFrame();
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'terminal idle initial capture unavailable');
      await browser.emitSpeechEndOfTurn();
      await waitForMounted(() => states.at(-1)?.p1_status === 'playing', 'task-start response did not play');
      await waitForMounted(() => browser.counts.sourceStarts === 1, 'task-start audio did not reach the browser');
      browser.endLatestSource();
      await waitForMounted(
        () => calls.some(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-idle-start'),
        'task-start response was not ACKed',
      );
      await waitForMounted(() => states.at(-1)?.p1_status === 'starting', 'idle listening did not restart after task-start');
      await waitForMounted(
        () => notificationWaiters.length > 0,
        'provider-starting capture did not retain one outstanding Task notification subscription',
      );
      const notificationCallsBeforeStartingKeepalive = calls.filter(
        call => call.method === 'live_voice.composition.p2.notification.next',
      ).length;
      publishNotification(keepalive(p2Binding));
      await waitForMounted(
        () =>
          calls.filter(call => call.method === 'live_voice.composition.p2.notification.next').length >
          notificationCallsBeforeStartingKeepalive,
        'provider-starting capture did not replace the Task subscription consumed by a keepalive',
      );
      await browser.emitFirstFrame(0.25);
      await waitForMounted(() => states.at(-1)?.p1_status === 'capturing', 'speech-marked idle listening did not become ready');
      await waitForMounted(
        () => progressActivation?.task_id === taskId && typeof progressListener === 'function',
        'voice-created task did not activate exact progress wakeup',
      );
      assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
      await waitForMounted(
        () => states.at(-1)?.task_progress_state === 'running',
        'activation-time accepted/running replay did not drain serially to visible running truth',
      );
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length === 2,
        'activation-time accepted/running replay was not ACKed exactly once per delivery',
      );
      await waitForMounted(
        () => notificationWaiters.length > 0,
        'speech-marked capture did not retain one Task notification receive subscription',
      );
    });

    const taskBinding = {
      subject_id: 'mounted-terminal-idle-subject',
      session_id: sessionId,
      project_id: 'mounted-terminal-idle-project',
      correlation_id: progressActivation.correlation_id,
      generation: 1,
    };
    taskTerminal = true;
    const progress = mountedTerminalProgress(taskBinding, progressActivation, 'completed', taskId, 'attempt-a', 2);
    assert.notEqual(parseProductTextProgressEvent(progress), null);
    await act(async () => {
      progressListener(progress);
      await waitForMounted(
        () => states.at(-1)?.terminal_announcement_state === 'queued',
        `terminal wake did not defer behind the speech-marked capture; states=${states
          .slice(-12)
          .map(state => `${state.p1_status}/${state.terminal_announcement_state}/${state.text_status}/${state.text_reason ?? 'none'}`)
          .join(',')}`,
      );
      await waitForMounted(() => states.at(-1)?.task_progress_state === 'terminal', 'completed progress was not visible');
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p3.progress.ack').length === 3,
        'completed progress was not ACKed exactly once after authoritative reconciliation',
      );
    });

    await act(async () => {
      await waitForMounted(
        () => notificationWaiters.length > 0,
        'speech-marked capture did not retain the terminal notification poll',
      );
      publishNotification(
        presentation(p2Binding, 'mounted-terminal-idle-running', 2, 'Background task update: running.', true),
      );
      await waitForMounted(
        () =>
          calls.filter(
            call =>
              call.method === 'live_voice.composition.p2.presentation.failed' &&
              call.params.response_id === 'mounted-terminal-idle-running',
          ).length === 1,
        `capture-blocked running Task AUDIO did not fail over after its finite acquisition deadline; states=${states
          .slice(-12)
          .map(state => `${state.p1_status}/${state.terminal_announcement_state}/${state.text_reason ?? 'none'}`)
          .join(',')}`,
      );
      assert.equal(
        calls.filter(
          call =>
            call.method === 'live_voice.speech.synthesize_batch' &&
            call.params.response.response_id === 'mounted-terminal-idle-running',
        ).length,
        0,
        'capture-blocked running Task AUDIO must not start an unauthorized TTS playout',
      );
      assert.equal(browser.counts.sourceStarts, 1, 'capture-blocked running Task AUDIO unexpectedly reached browser playout');
      await waitForMounted(
        () =>
          calls.filter(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-terminal-idle-running-text' &&
              call.params.surface === 'text',
          ).length === 1,
        'visible running Task TEXT fallback did not emit its exact ACK',
      );
      assert.equal(
        calls.filter(
          call =>
            call.method === 'live_voice.speech.synthesize_batch' &&
            call.params.response.response_id === 'mounted-terminal-idle-running-text',
        ).length,
        0,
        'visible running Task TEXT fallback must not depend on another TTS owner',
      );
      await waitForMounted(
        () => states.at(-1)?.terminal_announcement_state === 'fetching',
        'running Task fallback did not retain the terminal follow-up subscription',
      );
      await waitForMounted(
        () => notificationWaiters.length > 0,
        'running Task AUDIO ACK incorrectly stopped the terminal notification poll',
      );
    });

    await act(async () => {
      publishNotification(presentation(p2Binding, 'mounted-terminal-idle-complete', 3, '后台任务已完成，结果已经准备好。', true));
      await waitForMounted(
        () => calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length === 2,
        `terminal notification did not report its failed AUDIO playout; states=${states
          .slice(-10)
          .map(state => `${state.p1_status}/${state.terminal_announcement_state}/${state.text_reason ?? 'none'}`)
          .join(',')}`,
      );
      assert.equal(
        calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-idle-complete')
          .length,
        0,
        'failed first terminal playout must not ACK',
      );
      await waitForMounted(
        () =>
          calls.filter(
            call =>
              call.method === 'live_voice.composition.p2.presentation.ack' &&
              call.params.response_id === 'mounted-terminal-idle-complete-text' &&
              call.params.surface === 'text',
          ).length === 1,
        'successful terminal Task TEXT fallback did not emit its exact ACK',
      );
      assert.equal(
        calls.filter(
          call =>
            call.method === 'live_voice.speech.synthesize_batch' &&
            call.params.response.response_id === 'mounted-terminal-idle-complete-text',
        ).length,
        0,
        'visible terminal Task TEXT fallback must not depend on another TTS owner',
      );
    });

    const presentationFailures = calls.filter(
      call => call.method === 'live_voice.composition.p2.presentation.failed' && call.params.response_id === 'mounted-terminal-idle-complete',
    );
    assert.equal(presentationFailures.length, 1);
    assert.equal(presentationFailures[0].params.response_generation, 3);
    assert.equal(presentationFailures[0].params.surface, 'audio');
    assert.equal(presentationFailures[0].params.unit_id, 'mounted-terminal-idle-complete-unit');
    assert.equal(presentationFailures[0].params.failure_reason, 'task_audio_playout_failed');
    assert.match(presentationFailures[0].requestId, /^live-voice-p2-presentation-failed-/);
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-idle-complete').length,
      0,
      'failed Task AUDIO must never become a presentation ACK',
    );
    assert.equal(states.at(-1)?.terminal_announcement_state, 'idle');
    const terminalTtsCount = calls.filter(
      call => call.method === 'live_voice.speech.synthesize_batch' && call.params.response.response_id === 'mounted-terminal-idle-complete',
    ).length;
    const terminalAckCount = calls.filter(
      call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-idle-complete',
    ).length;
    await act(async () => {
      progressListener(progress);
      await new Promise(resolve => setTimeout(resolve, 25));
    });
    assert.equal(
      calls.filter(call => call.method === 'live_voice.speech.synthesize_batch' && call.params.response.response_id === 'mounted-terminal-idle-complete')
        .length,
      terminalTtsCount,
      'duplicate current-Task terminal progress must not replay its announcement',
    );
    assert.equal(
      calls.filter(call => call.method === 'live_voice.composition.p2.presentation.ack' && call.params.response_id === 'mounted-terminal-idle-complete')
        .length,
      terminalAckCount,
      'duplicate current-Task terminal progress must not replay its stale ACK',
    );

    assert.equal(
      calls.filter(call => call.method === 'live_voice.speech.synthesize_batch' && call.params.response.response_id === 'mounted-terminal-idle-complete')
        .length,
      0,
      'deferred terminal Task AUDIO must fall back without an unauthorized local replay',
    );
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.p2.presentation.failed').length, 2);
    assert.equal(calls.filter(call => call.method === 'live_voice.speech.recognize_batch').length, 1);
    assert.equal(calls.filter(call => call.method === 'live_voice.composition.unified.submit').length, 1);
    assert.equal(
      calls.filter(
        call =>
          call.method === 'live_voice.composition.p2.presentation.ack' &&
          call.params.response_id === 'mounted-terminal-idle-complete-text',
      ).length,
      1,
    );
    assert.equal(
      calls.some(call => call.method.includes('task.cancel') || call.method.includes('task.mutate') || call.method === 'live_voice.composition.p3.mutate'),
      false,
    );
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    browser.restore();
  }
});
