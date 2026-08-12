import assert from 'node:assert/strict';
import test from 'node:test';

import {
  WebPlatformDiagnosticsMonitor,
  collectWebPlatformDiagnostics,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/webPlatformDiagnostics.js';

class EventTargetFake {
  listeners = new Map();
  adds = 0;
  removes = 0;

  addEventListener(type, listener) {
    this.adds += 1;
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    this.removes += 1;
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type) {
    for (const listener of this.listeners.get(type) ?? []) listener();
  }

  count() {
    return [...this.listeners.values()].reduce((sum, listeners) => sum + listeners.size, 0);
  }
}

function audioCapability(overrides = {}) {
  return Object.freeze({
    enabled: true,
    secure_context: true,
    document_visibility: true,
    media_devices: true,
    audio_context: true,
    audio_worklet_node: true,
    stable_identity: true,
    capture_pcm_f32: true,
    playout_pcm_f32: true,
    media_recorder_realtime: false,
    output_device_selection: false,
    physical_heard_ack: false,
    reasons: Object.freeze([]),
    ...overrides,
  });
}

function environment(overrides = {}) {
  const permission = Object.assign(new EventTargetFake(), { state: 'granted' });
  const mediaDevices = Object.assign(new EventTargetFake(), {
    enumerateDevices: async () => [
      { kind: 'audioinput', deviceId: 'private-input-id', label: 'Private microphone label' },
      { kind: 'audiooutput', deviceId: 'private-output-id', label: 'Private speaker label' },
    ],
  });
  const document = Object.assign(new EventTargetFake(), { visibilityState: 'visible', wasDiscarded: false });
  return {
    is_secure_context: true,
    protocol: 'https:',
    hostname: 'voice.example.test',
    user_agent: 'Mozilla/5.0 Chrome/150.0.7871.116 Safari/537.36',
    reported_platform: 'Win32',
    online: true,
    user_activation_observed: true,
    document,
    window_events: new EventTargetFake(),
    media_devices: mediaDevices,
    query_microphone_permission: async () => permission,
    audio_capability: audioCapability(),
    ...overrides,
  };
}

test('secure desktop Chrome diagnostics expose exact bounded facts without device identity', async () => {
  const snapshot = await collectWebPlatformDiagnostics(environment());
  assert.equal(snapshot.browser_family, 'google_chrome');
  assert.equal(snapshot.browser_version, '150.0.7871.116');
  assert.equal(snapshot.alpha_browser_scope, 'desktop_google_chrome_candidate');
  assert.equal(snapshot.reported_platform, 'Win32');
  assert.equal(snapshot.origin_scope, 'deployed');
  assert.equal(snapshot.transport_security, 'secure');
  assert.equal(snapshot.microphone_permission, 'granted');
  assert.equal(snapshot.audio_input, 'enumerated');
  assert.equal(snapshot.audio_output, 'enumerated');
  assert.equal(snapshot.user_activation, 'observed');
  assert.equal(snapshot.page_visibility, 'visible');
  assert.equal(snapshot.network, 'online');
  assert.equal(snapshot.aio_capability.capture_pcm_f32, true);
  const serialized = JSON.stringify(snapshot);
  assert.equal(serialized.includes('private-input-id'), false);
  assert.equal(serialized.includes('private-output-id'), false);
  assert.equal(serialized.includes('Private microphone label'), false);
  assert.equal(serialized.includes('Private speaker label'), false);
});

test('permission denial, missing devices, hidden page, and insecure deployment remain explicit', async () => {
  const permission = Object.assign(new EventTargetFake(), { state: 'denied' });
  const document = Object.assign(new EventTargetFake(), { visibilityState: 'hidden', wasDiscarded: true });
  const mediaDevices = Object.assign(new EventTargetFake(), { enumerateDevices: async () => [] });
  const snapshot = await collectWebPlatformDiagnostics(
    environment({
      is_secure_context: false,
      protocol: 'http:',
      hostname: 'voice.example.test',
      online: false,
      user_activation_observed: false,
      document,
      media_devices: mediaDevices,
      query_microphone_permission: async () => permission,
      audio_capability: audioCapability({ secure_context: false, capture_pcm_f32: false, playout_pcm_f32: false, reasons: ['INSECURE_CONTEXT'] }),
    })
  );
  assert.equal(snapshot.transport_security, 'insecure');
  assert.equal(snapshot.microphone_permission, 'denied');
  assert.equal(snapshot.audio_input, 'not_enumerated');
  assert.equal(snapshot.audio_output, 'not_enumerated');
  assert.equal(snapshot.user_activation, 'required');
  assert.equal(snapshot.page_visibility, 'hidden');
  assert.equal(snapshot.page_was_discarded, true);
  assert.equal(snapshot.network, 'offline');
  assert.equal(snapshot.aio_capability.capture_pcm_f32, false);
  assert.equal(mediaDevices.enumerations ?? 0, 0);
});

test('prompt and denied permission perform zero diagnostic device enumeration', async () => {
  for (const state of ['prompt', 'denied']) {
    const permission = Object.assign(new EventTargetFake(), { state });
    let enumerations = 0;
    const mediaDevices = Object.assign(new EventTargetFake(), {
      async enumerateDevices() {
        enumerations += 1;
        return [{ kind: 'audioinput', deviceId: 'private-id', label: 'private label' }];
      },
    });
    const snapshot = await collectWebPlatformDiagnostics(
      environment({ media_devices: mediaDevices, query_microphone_permission: async () => permission })
    );
    assert.equal(enumerations, 0);
    assert.equal(snapshot.audio_input, 'not_enumerated');
    assert.equal(snapshot.audio_output, 'not_enumerated');
    assert.equal(JSON.stringify(snapshot).includes('private'), false);
  }
});

test('localhost is disclosed as controlled scope and never relabelled secure when the browser says insecure', async () => {
  const snapshot = await collectWebPlatformDiagnostics(environment({ is_secure_context: false, protocol: 'http:', hostname: '127.0.0.1' }));
  assert.equal(snapshot.secure_context, false);
  assert.equal(snapshot.origin_scope, 'localhost_controlled');
  assert.equal(snapshot.transport_security, 'localhost_controlled_exception');
});

test('mobile Chrome and other Chromium evidence remain outside the declared desktop Google Chrome scope', async () => {
  const mobile = await collectWebPlatformDiagnostics(environment({ user_agent: 'Mozilla/5.0 (Linux; Android 16) Chrome/150.0.7871.116 Mobile Safari/537.36' }));
  assert.equal(mobile.browser_family, 'google_chrome');
  assert.equal(mobile.alpha_browser_scope, 'outside_declared_scope');
  const edge = await collectWebPlatformDiagnostics(environment({ user_agent: 'Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0' }));
  assert.equal(edge.browser_family, 'other_chromium');
  assert.equal(edge.alpha_browser_scope, 'outside_declared_scope');
  assert.equal(edge.aio_capability.capture_pcm_f32, true);
});

test('unavailable and failed browser queries stay unknown or explicitly not enumerated instead of succeeding', async () => {
  const snapshot = await collectWebPlatformDiagnostics(
    environment({
      query_microphone_permission: async () => {
        throw new Error('blocked');
      },
      media_devices: Object.assign(new EventTargetFake(), {
        enumerateDevices: async () => {
          throw new Error('enumeration failed');
        },
      }),
      user_agent: '',
      reported_platform: '',
      user_activation_observed: null,
      online: null,
      document: null,
    })
  );
  assert.equal(snapshot.browser_family, 'unknown');
  assert.equal(snapshot.reported_platform, null);
  assert.equal(snapshot.microphone_permission, 'unknown');
  assert.equal(snapshot.audio_input, 'not_enumerated');
  assert.equal(snapshot.audio_output, 'not_enumerated');
  assert.equal(snapshot.user_activation, 'unknown');
  assert.equal(snapshot.page_visibility, 'unknown');
  assert.equal(snapshot.network, 'unknown');
  assert.deepEqual(snapshot.diagnostic_errors, ['MICROPHONE_PERMISSION_QUERY_FAILED']);
});

test('diagnostics flag-off performs zero permission, device, listener, callback, or timer effects', async () => {
  const document = Object.assign(new EventTargetFake(), { visibilityState: 'visible' });
  const mediaDevices = Object.assign(new EventTargetFake(), {
    enumerations: 0,
    async enumerateDevices() {
      this.enumerations += 1;
      return [];
    },
  });
  let permissionQueries = 0;
  let snapshots = 0;
  const monitor = new WebPlatformDiagnosticsMonitor({
    enabled: false,
    environment: environment({
      document,
      media_devices: mediaDevices,
      query_microphone_permission: async () => {
        permissionQueries += 1;
        return Object.assign(new EventTargetFake(), { state: 'prompt' });
      },
    }),
    on_snapshot: () => {
      snapshots += 1;
    },
  });
  assert.equal(monitor.start(), false);
  assert.equal(await monitor.refresh(), false);
  assert.equal(monitor.stop(), false);
  assert.equal(permissionQueries, 0);
  assert.equal(mediaDevices.enumerations, 0);
  assert.equal(document.adds + document.removes + mediaDevices.adds + mediaDevices.removes, 0);
  assert.equal(snapshots, 0);
});

test('monitor refreshes observable facts, removes every listener, and fences late snapshots', async () => {
  const document = Object.assign(new EventTargetFake(), { visibilityState: 'visible' });
  const windowEvents = new EventTargetFake();
  const permission = Object.assign(new EventTargetFake(), { state: 'prompt' });
  let resolveDevices;
  const devicesPromise = new Promise(resolve => {
    resolveDevices = resolve;
  });
  const mediaDevices = Object.assign(new EventTargetFake(), { enumerateDevices: () => devicesPromise });
  let snapshots = 0;
  const monitor = new WebPlatformDiagnosticsMonitor({
    enabled: true,
    environment: environment({
      document,
      window_events: windowEvents,
      media_devices: mediaDevices,
      query_microphone_permission: async () => permission,
    }),
    on_snapshot: () => {
      snapshots += 1;
    },
  });

  assert.equal(monitor.start(), true);
  await Promise.resolve();
  assert.equal(document.count(), 1);
  assert.equal(mediaDevices.count(), 1);
  assert.equal(windowEvents.count(), 2);
  assert.equal(permission.count(), 1);
  assert.equal(monitor.stop(), true);
  assert.equal(document.count() + mediaDevices.count() + windowEvents.count() + permission.count(), 0);
  resolveDevices([{ kind: 'audioinput', deviceId: 'late-private-id', label: 'late private label' }]);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(snapshots, 0);
  assert.equal(await monitor.refresh(), false);
});

test('monitor refresh reads current network and user-activation facts instead of stale construction values', async () => {
  let online = true;
  let activated = false;
  const dynamicEnvironment = environment();
  Object.defineProperty(dynamicEnvironment, 'online', { get: () => online });
  Object.defineProperty(dynamicEnvironment, 'user_activation_observed', { get: () => activated });
  const snapshots = [];
  const monitor = new WebPlatformDiagnosticsMonitor({
    enabled: true,
    environment: dynamicEnvironment,
    on_snapshot: snapshot => snapshots.push(snapshot),
  });
  monitor.start();
  await monitor.refresh();
  assert.equal(snapshots.at(-1).network, 'online');
  assert.equal(snapshots.at(-1).user_activation, 'required');
  online = false;
  activated = true;
  await monitor.refresh();
  assert.equal(snapshots.at(-1).network, 'offline');
  assert.equal(snapshots.at(-1).user_activation, 'observed');
  monitor.stop();
});

test('stop and restart fence a late permission listener from the prior lifecycle', async () => {
  const oldPermission = Object.assign(new EventTargetFake(), { state: 'prompt' });
  const currentPermission = Object.assign(new EventTargetFake(), { state: 'granted' });
  let resolveOldPermission;
  const oldPermissionQuery = new Promise(resolve => {
    resolveOldPermission = resolve;
  });
  let queries = 0;
  const monitor = new WebPlatformDiagnosticsMonitor({
    enabled: true,
    environment: environment({
      query_microphone_permission: () => {
        queries += 1;
        return queries === 1 ? oldPermissionQuery : Promise.resolve(currentPermission);
      },
    }),
    on_snapshot: () => {},
  });

  assert.equal(monitor.start(), true);
  assert.equal(monitor.stop(), true);
  assert.equal(monitor.start(), true);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(currentPermission.count(), 1);
  resolveOldPermission(oldPermission);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(oldPermission.count(), 0);
  assert.equal(currentPermission.count(), 1);
  assert.equal(monitor.stop(), true);
  assert.equal(currentPermission.count(), 0);
});

test('permission listener registration failure remains a stable diagnostic fact and cleans the partial listener', async () => {
  const permission = Object.assign(new EventTargetFake(), {
    state: 'granted',
    addEventListener(type, listener) {
      EventTargetFake.prototype.addEventListener.call(this, type, listener);
      throw new Error('permission listener registration rejected');
    },
  });
  const snapshots = [];
  const monitor = new WebPlatformDiagnosticsMonitor({
    enabled: true,
    environment: environment({ query_microphone_permission: async () => permission }),
    on_snapshot: snapshot => snapshots.push(snapshot),
  });

  assert.equal(monitor.start(), true);
  await Promise.resolve();
  await monitor.refresh();
  const snapshot = snapshots.at(-1);
  assert.equal(snapshot.microphone_permission, 'granted');
  assert.equal(snapshot.diagnostic_errors.includes('MICROPHONE_PERMISSION_LISTENER_REGISTRATION_FAILED'), true);
  assert.equal(permission.count(), 0);
  assert.equal(permission.removes >= 1, true);
  await monitor.refresh();
  assert.equal(snapshots.at(-1).diagnostic_errors.includes('MICROPHONE_PERMISSION_LISTENER_REGISTRATION_FAILED'), true);
  assert.equal(monitor.stop(), true);
});

test('listener registration failure releases earlier listeners and starts no diagnostics work', async () => {
  const document = Object.assign(new EventTargetFake(), { visibilityState: 'visible' });
  const mediaDevices = Object.assign(new EventTargetFake(), {
    enumerateDevices: async () => [],
    addEventListener() {
      this.adds += 1;
      throw new Error('listener rejected');
    },
  });
  let snapshots = 0;
  const monitor = new WebPlatformDiagnosticsMonitor({
    enabled: true,
    environment: environment({ document, media_devices: mediaDevices }),
    on_snapshot: () => {
      snapshots += 1;
    },
  });
  assert.equal(monitor.start(), false);
  await Promise.resolve();
  assert.equal(document.count(), 0);
  assert.equal(snapshots, 0);
  assert.equal(await monitor.refresh(), false);
});
