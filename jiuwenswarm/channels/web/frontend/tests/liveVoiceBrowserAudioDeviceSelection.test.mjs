import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  BrowserAudioDeviceSelectionOwner,
  BrowserAudioDeviceSelectionViolation,
} from '../node_modules/.cache/live-voice-device-selection/browserAudioDeviceSelection.mjs';

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

  emit(type) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener();
  }

  count(type) {
    return this.listeners.get(type)?.size ?? 0;
  }
}

class PermissionFake extends EventTargetFake {
  constructor(state) {
    super();
    this.state = state;
  }

  change(state) {
    this.state = state;
    this.emit('change');
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolveValue, rejectValue) => {
    resolve = resolveValue;
    reject = rejectValue;
  });
  return { promise, resolve, reject };
}

function environment(overrides = {}) {
  const permission = new PermissionFake('granted');
  const mediaDevices = new EventTargetFake();
  mediaDevices.devices = [
    { kind: 'audioinput', deviceId: 'private-input-1', label: 'Headset microphone' },
    { kind: 'audiooutput', deviceId: 'private-output-1', label: 'Headset speaker' },
  ];
  mediaDevices.enumerations = 0;
  mediaDevices.probes = 0;
  mediaDevices.probeTracks = [];
  mediaDevices.getUserMedia = async constraints => {
    mediaDevices.probes += 1;
    mediaDevices.lastConstraints = constraints;
    const track = {
      stops: 0,
      stop() {
        this.stops += 1;
      },
    };
    mediaDevices.probeTracks.push(track);
    return { getTracks: () => [track] };
  };
  mediaDevices.enumerateDevices = async () => {
    mediaDevices.enumerations += 1;
    return mediaDevices.devices;
  };
  let token = 0;
  return {
    permission,
    mediaDevices,
    value: {
      is_secure_context: true,
      media_devices: mediaDevices,
      query_microphone_permission: async () => permission,
      create_token: () => `opaque-${++token}`,
      ...overrides,
    },
  };
}

test('flag off performs zero browser reads, probes, enumerations, listeners, or callbacks', async () => {
  let reads = 0;
  let callbacks = 0;
  const exploding = new Proxy(
    {},
    {
      get() {
        reads += 1;
        throw new Error('read');
      },
    }
  );
  const owner = new BrowserAudioDeviceSelectionOwner({
    enabled: false,
    environment: exploding,
    on_snapshot: () => {
      callbacks += 1;
    },
  });
  assert.equal(owner.snapshot().status, 'closed');
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'FEATURE_DISABLED'
  );
  await assert.rejects(
    () => owner.load(),
    error => error.reason === 'FEATURE_DISABLED'
  );
  assert.equal(owner.close(), false);
  assert.equal(reads, 0);
  assert.equal(callbacks, 0);
});

test('granted permission enumerates without probing and exposes only opaque tokens plus labels', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const snapshot = await owner.load();
  assert.equal(fake.mediaDevices.probes, 0);
  assert.equal(fake.mediaDevices.enumerations, 1);
  assert.equal(snapshot.status, 'ready');
  assert.deepEqual(
    snapshot.inputs.map(value => value.label),
    ['Headset microphone']
  );
  assert.deepEqual(
    snapshot.outputs.map(value => value.label),
    ['Headset speaker']
  );
  assert.equal(JSON.stringify(snapshot).includes('private-input-1'), false);
  assert.equal(JSON.stringify(snapshot).includes('private-output-1'), false);
  assert.equal(fake.mediaDevices.count('devicechange'), 1);
  assert.equal(fake.permission.count('change'), 1);
  owner.close();
});

test('prompt permission uses one bounded getUserMedia probe, stops it, then enumerates', async () => {
  const fake = environment();
  fake.permission.state = 'prompt';
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const snapshot = await owner.load();
  assert.equal(snapshot.status, 'ready');
  assert.equal(fake.mediaDevices.probes, 1);
  assert.deepEqual(fake.mediaDevices.lastConstraints, { audio: true, video: false });
  assert.equal(fake.mediaDevices.probeTracks[0].stops, 1);
  assert.equal(fake.mediaDevices.enumerations, 1);
  owner.close();
});

test('a retained load owns the only permission probe and a concurrent load has zero added effects', async () => {
  const fake = environment();
  fake.permission.state = 'prompt';
  const probe = deferred();
  fake.mediaDevices.getUserMedia = async constraints => {
    fake.mediaDevices.probes += 1;
    fake.mediaDevices.lastConstraints = constraints;
    return probe.promise;
  };
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const first = owner.load();
  await Promise.resolve();

  await assert.rejects(
    () => owner.load(),
    error => error.reason === 'AUDIO_DEVICE_LOAD_IN_PROGRESS'
  );
  assert.equal(fake.mediaDevices.probes, 1);
  const track = {
    stops: 0,
    stop() {
      this.stops += 1;
    },
  };
  probe.resolve({ getTracks: () => [track] });
  await first;
  assert.equal(track.stops, 1);
  assert.equal(fake.mediaDevices.enumerations, 1);
  owner.close();
});

test('denied permission performs zero getUserMedia and zero enumeration', async () => {
  const fake = environment();
  fake.permission.state = 'denied';
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const snapshot = await owner.load();
  assert.equal(snapshot.status, 'permission_denied');
  assert.equal(snapshot.reason, 'MICROPHONE_PERMISSION_DENIED');
  assert.equal(fake.mediaDevices.probes, 0);
  assert.equal(fake.mediaDevices.enumerations, 0);
  assert.equal(fake.mediaDevices.count('devicechange'), 0);
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'MICROPHONE_PERMISSION_DENIED'
  );
});

test('a reload failure clears an already-applied exact route and removes prior listeners', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const loaded = await owner.load();
  owner.apply({
    inventory_generation: loaded.inventory_generation,
    input_token: loaded.inputs[0].token,
    output_token: loaded.outputs[0].token,
  });
  fake.permission.state = 'denied';

  const failed = await owner.load();

  assert.equal(failed.status, 'permission_denied');
  assert.equal(failed.inputs.length + failed.outputs.length, 0);
  assert.equal(fake.mediaDevices.count('devicechange'), 0);
  assert.equal(fake.permission.count('change'), 0);
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'MICROPHONE_PERMISSION_DENIED'
  );
});

test('partial listener registration is rolled back and the route remains unavailable', async () => {
  const fake = environment();
  fake.permission.addEventListener = () => {
    throw new Error('policy blocked listener');
  };
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });

  const failed = await owner.load();

  assert.equal(failed.status, 'unavailable');
  assert.equal(failed.reason, 'AUDIO_DEVICE_LISTENER_FAILED');
  assert.equal(fake.mediaDevices.count('devicechange'), 0);
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'AUDIO_DEVICE_LISTENER_FAILED'
  );
});

test('default is explicit and applying current opaque tokens yields a page-memory-only route', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const loaded = await owner.load();
  assert.deepEqual(owner.appliedRoute(), { selection_generation: 1 });
  const applied = owner.apply({
    inventory_generation: loaded.inventory_generation,
    input_token: loaded.inputs[0].token,
    output_token: loaded.outputs[0].token,
  });
  assert.equal(applied.selection_generation, 2);
  assert.deepEqual(owner.appliedRoute(), {
    selection_generation: 2,
    input_device_id: 'private-input-1',
    output_device_id: 'private-output-1',
  });
  const defaults = owner.apply({
    inventory_generation: applied.inventory_generation,
    input_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
    output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  });
  assert.deepEqual(owner.appliedRoute(), { selection_generation: defaults.selection_generation });
  owner.close();
});

test('reload remaps an applied physical device to fresh opaque inventory tokens without changing the route', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const first = await owner.load();
  const applied = owner.apply({
    inventory_generation: first.inventory_generation,
    input_token: first.inputs[0].token,
    output_token: first.outputs[0].token,
  });

  const reloaded = await owner.load();

  assert.notEqual(reloaded.inputs[0].token, first.inputs[0].token);
  assert.notEqual(reloaded.outputs[0].token, first.outputs[0].token);
  assert.equal(reloaded.applied_input_token, reloaded.inputs[0].token);
  assert.equal(reloaded.applied_output_token, reloaded.outputs[0].token);
  assert.equal(reloaded.selection_generation, applied.selection_generation);
  assert.deepEqual(owner.appliedRoute(), {
    selection_generation: applied.selection_generation,
    input_device_id: 'private-input-1',
    output_device_id: 'private-output-1',
  });
  assert.equal(fake.mediaDevices.count('devicechange'), 1);
  assert.equal(fake.permission.count('change'), 1);
  owner.close();
});

test('reload invalidates a missing exact device instead of silently changing to default', async () => {
  const fake = environment();
  fake.mediaDevices.devices.push({ kind: 'audioinput', deviceId: 'private-input-2', label: 'Other microphone' });
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const first = await owner.load();
  owner.apply({
    inventory_generation: first.inventory_generation,
    input_token: first.inputs[0].token,
    output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  });
  fake.mediaDevices.devices = fake.mediaDevices.devices.filter(device => device.deviceId !== 'private-input-1');

  const reloaded = await owner.load();

  assert.equal(reloaded.status, 'selection_invalidated');
  assert.equal(reloaded.reason, 'AUDIO_INPUT_SELECTION_LOST');
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'AUDIO_INPUT_SELECTION_LOST'
  );
});

test('stale inventory token and generation fail without changing the applied route', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const loaded = await owner.load();
  assert.throws(
    () =>
      owner.apply({
        inventory_generation: loaded.inventory_generation + 1,
        input_token: loaded.inputs[0].token,
        output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
      }),
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_INVENTORY_STALE'
  );
  assert.throws(
    () => owner.apply({ inventory_generation: loaded.inventory_generation, input_token: 'stale-token', output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN }),
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_TOKEN_STALE'
  );
  assert.deepEqual(owner.appliedRoute(), { selection_generation: 1 });
  owner.close();
});

test('exact input loss invalidates selection even while another microphone remains', async () => {
  const fake = environment();
  fake.mediaDevices.devices.push({ kind: 'audioinput', deviceId: 'private-input-2', label: 'Other microphone' });
  const reasons = [];
  const owner = new BrowserAudioDeviceSelectionOwner({
    enabled: true,
    environment: fake.value,
    on_device_invalidated: reason => reasons.push(reason),
  });
  const loaded = await owner.load();
  owner.apply({ inventory_generation: loaded.inventory_generation, input_token: loaded.inputs[0].token, output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN });
  fake.mediaDevices.devices = fake.mediaDevices.devices.filter(device => device.deviceId !== 'private-input-1');
  fake.mediaDevices.emit('devicechange');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(owner.snapshot().status, 'selection_invalidated');
  assert.equal(owner.snapshot().reason, 'AUDIO_INPUT_SELECTION_LOST');
  assert.deepEqual(reasons, ['AUDIO_INPUT_SELECTION_LOST']);
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'AUDIO_INPUT_SELECTION_LOST'
  );
  assert.equal(JSON.stringify(owner.snapshot()).includes('private-input-1'), false);
});

test('device refresh owns an exact generation and rejects apply or Product start until every queued verification completes', async () => {
  const fake = environment();
  fake.mediaDevices.devices.splice(1, 0, {
    kind: 'audioinput',
    deviceId: 'private-input-2',
    label: 'Other microphone',
  });
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const initial = await owner.load();
  owner.apply({
    inventory_generation: initial.inventory_generation,
    input_token: initial.inputs.find(option => option.label === 'Headset microphone').token,
    output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  });
  const appliedGeneration = owner.appliedRoute().selection_generation;
  const pending = deferred();
  let refreshCalls = 0;
  fake.mediaDevices.enumerateDevices = () => {
    refreshCalls += 1;
    return refreshCalls === 1 ? pending.promise : Promise.resolve(fake.mediaDevices.devices);
  };

  fake.mediaDevices.emit('devicechange');
  assert.equal(owner.snapshot().status, 'refreshing');
  assert.equal(owner.snapshot().selection_generation, appliedGeneration + 1);
  const staleInventory = owner.snapshot();
  assert.throws(
    () =>
      owner.apply({
        inventory_generation: staleInventory.inventory_generation,
        input_token: staleInventory.inputs.find(option => option.label === 'Other microphone').token,
        output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
      }),
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_REFRESH_IN_PROGRESS'
  );
  assert.throws(
    () => owner.appliedRoute(),
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_REFRESH_IN_PROGRESS'
  );
  await assert.rejects(
    () => owner.load(),
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_REFRESH_IN_PROGRESS'
  );

  // A second browser fact cannot be lost while the first enumeration is pending.
  fake.mediaDevices.emit('devicechange');
  pending.resolve(fake.mediaDevices.devices);
  for (let turn = 0; turn < 8 && owner.snapshot().status !== 'ready'; turn += 1) await Promise.resolve();
  assert.equal(owner.snapshot().status, 'ready');
  assert.equal(refreshCalls, 2);
  assert.equal(owner.appliedRoute().input_device_id, 'private-input-1');
  assert.equal(owner.appliedRoute().selection_generation, appliedGeneration + 1);

  const verified = owner.snapshot();
  owner.apply({
    inventory_generation: verified.inventory_generation,
    input_token: verified.inputs.find(option => option.label === 'Other microphone').token,
    output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  });
  assert.equal(owner.appliedRoute().input_device_id, 'private-input-2');
  assert.equal(owner.appliedRoute().selection_generation, appliedGeneration + 2);
  owner.close();
});

test('exact output loss and unverified enumeration never silently switch to default', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const loaded = await owner.load();
  owner.apply({ inventory_generation: loaded.inventory_generation, input_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN, output_token: loaded.outputs[0].token });
  fake.mediaDevices.devices = fake.mediaDevices.devices.filter(device => device.kind !== 'audiooutput');
  fake.mediaDevices.emit('devicechange');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(owner.snapshot().reason, 'AUDIO_OUTPUT_SELECTION_LOST');
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'AUDIO_OUTPUT_SELECTION_LOST'
  );

  const second = environment();
  const secondOwner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: second.value });
  const secondLoaded = await secondOwner.load();
  secondOwner.apply({
    inventory_generation: secondLoaded.inventory_generation,
    input_token: secondLoaded.inputs[0].token,
    output_token: BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  });
  second.mediaDevices.enumerateDevices = async () => {
    throw new Error('blocked');
  };
  second.mediaDevices.emit('devicechange');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(secondOwner.snapshot().reason, 'AUDIO_DEVICE_SELECTION_UNVERIFIED');
});

test('inventory enumeration failure invalidates even an explicit system-default selection', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  await owner.load();
  fake.mediaDevices.enumerateDevices = async () => {
    throw new Error('blocked');
  };

  fake.mediaDevices.emit('devicechange');
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(owner.snapshot().status, 'selection_invalidated');
  assert.equal(owner.snapshot().reason, 'AUDIO_DEVICE_SELECTION_UNVERIFIED');
  assert.throws(
    () => owner.appliedRoute(),
    error => error.reason === 'AUDIO_DEVICE_SELECTION_UNVERIFIED'
  );
});

test('permission revocation clears private inventory and selection and removes listeners', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const loaded = await owner.load();
  owner.apply({ inventory_generation: loaded.inventory_generation, input_token: loaded.inputs[0].token, output_token: loaded.outputs[0].token });
  fake.permission.change('denied');
  const snapshot = owner.snapshot();
  assert.equal(snapshot.status, 'selection_invalidated');
  assert.equal(snapshot.reason, 'MICROPHONE_PERMISSION_REVOKED');
  assert.equal(snapshot.inputs.length + snapshot.outputs.length, 0);
  assert.equal(fake.mediaDevices.count('devicechange'), 0);
  assert.equal(fake.permission.count('change'), 0);
});

test('close fences late permission grant before enumeration and cleans the probe stream exactly once', async () => {
  const fake = environment();
  fake.permission.state = 'prompt';
  const probe = deferred();
  const track = {
    stops: 0,
    stop() {
      this.stops += 1;
    },
  };
  fake.mediaDevices.getUserMedia = () => probe.promise;
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const loading = owner.load();
  await Promise.resolve();
  owner.close();
  probe.resolve({ getTracks: () => [track] });
  await assert.rejects(
    () => loading,
    error => error.reason === 'AUDIO_DEVICE_SELECTION_CANCELLED'
  );
  assert.equal(track.stops, 1);
  assert.equal(fake.mediaDevices.enumerations, 0);
  assert.equal(owner.snapshot().status, 'closed');
});

test('close fences a late rejected permission probe without resurrecting state or invalidation callbacks', async () => {
  const fake = environment();
  const probe = deferred();
  const invalidations = [];
  fake.permission.state = 'prompt';
  fake.mediaDevices.getUserMedia = () => {
    fake.mediaDevices.probes += 1;
    return probe.promise;
  };
  const owner = new BrowserAudioDeviceSelectionOwner({
    enabled: true,
    environment: fake.value,
    on_device_invalidated: reason => invalidations.push(reason),
  });

  const loading = owner.load();
  for (let turn = 0; turn < 4 && fake.mediaDevices.probes === 0; turn += 1) await Promise.resolve();
  assert.equal(fake.mediaDevices.probes, 1);
  owner.close();
  probe.reject(Object.assign(new Error('late private browser failure'), { name: 'NotAllowedError' }));

  await assert.rejects(
    () => loading,
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_SELECTION_CANCELLED'
  );
  assert.equal(owner.snapshot().status, 'closed');
  assert.deepEqual(invalidations, []);
  assert.equal(fake.mediaDevices.enumerations, 0);
});

test('an in-progress reload cannot expose its retained exact route to a concurrent product start', async () => {
  const fake = environment();
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const first = await owner.load();
  owner.apply({
    inventory_generation: first.inventory_generation,
    input_token: first.inputs[0].token,
    output_token: first.outputs[0].token,
  });
  const enumeration = deferred();
  fake.mediaDevices.enumerateDevices = () => enumeration.promise;

  const reloading = owner.load();
  assert.throws(
    () => owner.appliedRoute(),
    error => error instanceof BrowserAudioDeviceSelectionViolation && error.reason === 'AUDIO_DEVICE_LOAD_IN_PROGRESS'
  );
  enumeration.resolve(fake.mediaDevices.devices);
  await reloading;
  assert.equal(owner.appliedRoute().input_device_id, 'private-input-1');
  owner.close();
});

test('blank and duplicate IDs are omitted and labels receive safe UI fallbacks', async () => {
  const fake = environment();
  fake.mediaDevices.devices = [
    { kind: 'audioinput', deviceId: '', label: 'hidden default' },
    { kind: 'audioinput', deviceId: 'default', label: 'default alias' },
    { kind: 'audioinput', deviceId: 'mic-1', label: '' },
    { kind: 'audioinput', deviceId: 'mic-1', label: 'duplicate' },
    { kind: 'audiooutput', deviceId: 'out-1', label: '' },
  ];
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const snapshot = await owner.load();
  assert.deepEqual(
    snapshot.inputs.map(value => value.label),
    ['Microphone 1']
  );
  assert.deepEqual(
    snapshot.outputs.map(value => value.label),
    ['Speaker 1']
  );
  owner.close();
});

test('labels are control-free and bounded while reserved or duplicate opaque tokens fail closed', async () => {
  const fake = environment();
  fake.mediaDevices.devices = [{ kind: 'audioinput', deviceId: 'mic-1', label: `  Desk\n${'x'.repeat(200)}  ` }];
  const owner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: fake.value });
  const snapshot = await owner.load();
  assert.equal(snapshot.inputs[0].label.includes('\n'), false);
  assert.equal(Array.from(snapshot.inputs[0].label).length, 128);
  owner.close();

  for (const createToken of [() => BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN, () => 'duplicate']) {
    const collision = environment({ create_token: createToken });
    const failedOwner = new BrowserAudioDeviceSelectionOwner({ enabled: true, environment: collision.value });
    const failed = await failedOwner.load();
    assert.equal(failed.status, 'unavailable');
    assert.equal(failed.reason, 'AUDIO_DEVICE_TOKEN_COLLISION');
    assert.equal(failed.inputs.length + failed.outputs.length, 0);
  }
});
