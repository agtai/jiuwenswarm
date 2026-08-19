import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BrowserAudioIOAdapter,
  BrowserAudioIOViolation,
  inspectBrowserAudioPlatform,
} from '../node_modules/.cache/live-voice-browser-audio-io/browserAudioIOAdapter.mjs';

class FakeEventTarget {
  listeners = new Map();

  addEventListener(type, listener) {
    const values = this.listeners.get(type) ?? new Set();
    values.add(listener);
    this.listeners.set(type, values);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener();
  }

  listenerCount(type) {
    return this.listeners.get(type)?.size ?? 0;
  }
}

class FakeDocument extends FakeEventTarget {
  visibilityState = 'visible';
}

class FakeTrack extends FakeEventTarget {
  id = 'track-1';
  kind = 'audio';
  readyState = 'live';
  muted = false;
  stopCount = 0;
  stopThrows = false;

  constructor(settings = {}) {
    super();
    this.settings = {
      sampleRate: 48000,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: false,
      autoGainControl: true,
      deviceId: 'private-device-id',
      ...settings,
    };
  }

  stop() {
    this.stopCount += 1;
    if (this.stopThrows) throw new Error('track stop failed');
    this.readyState = 'ended';
  }

  getSettings() {
    return { ...this.settings };
  }
}

class FakeStream {
  constructor(track = new FakeTrack()) {
    this.track = track;
  }

  getAudioTracks() {
    return [this.track];
  }

  getTracks() {
    return [this.track];
  }
}

class FakeMediaDevices extends FakeEventTarget {
  constraints = [];
  stream = new FakeStream();
  devices = [{ kind: 'audioinput' }, { kind: 'videoinput' }];
  getUserMediaImpl = async () => this.stream;
  enumerateDevicesImpl = async () => this.devices;

  async getUserMedia(constraints) {
    this.constraints.push(constraints);
    return this.getUserMediaImpl(constraints);
  }

  async enumerateDevices() {
    return this.enumerateDevicesImpl();
  }
}

class FakePermissionStatus extends FakeEventTarget {
  state = 'granted';
  throwAfterAdd = false;
  onAdd = null;

  constructor(state = 'granted') {
    super();
    this.state = state;
  }

  addEventListener(type, listener) {
    super.addEventListener(type, listener);
    this.onAdd?.();
    if (this.throwAfterAdd) throw new Error('permission listener registration failed');
  }

  change(state) {
    this.state = state;
    this.emit('change');
  }
}

class FakePermissions {
  queries = [];
  queryImpl;

  constructor(status = new FakePermissionStatus()) {
    this.queryImpl = async () => status;
  }

  async query(descriptor) {
    this.queries.push(descriptor);
    return this.queryImpl(descriptor);
  }
}

class FakeNode {
  connected = [];
  connectThrows = false;
  disconnectCount = 0;
  disconnectThrows = false;

  connect(destination) {
    if (this.connectThrows) throw new Error('node connect failed');
    this.connected.push(destination);
    return destination;
  }

  disconnect() {
    this.disconnectCount += 1;
    if (this.disconnectThrows) throw new Error('node disconnect failed');
  }
}

class FakeMessagePort {
  onmessage = null;
  closeCount = 0;
  closeThrows = false;
  closePromise = null;

  emit(data) {
    this.onmessage?.({ data });
  }

  close() {
    this.closeCount += 1;
    if (this.closeThrows) throw new Error('port close failed');
  }
}

class FakeWorkletNode extends FakeNode {
  port = new FakeMessagePort();
  onprocessorerror = null;
}

class FakeAudioBuffer {
  copied = [];

  copyToChannel(source, channelNumber) {
    this.copied.push({ source: source.slice(), channelNumber });
  }
}

class FakeBufferSource extends FakeNode {
  buffer = null;
  onended = null;
  starts = [];
  stopCount = 0;
  stopThrows = false;
  startThrows = false;

  start(when = 0) {
    this.starts.push(when);
    if (this.startThrows) throw new Error('source start failed');
  }

  stop() {
    this.stopCount += 1;
    if (this.stopThrows) throw new Error('source stop failed');
  }

  end() {
    this.onended?.();
  }
}

class FakeAudioContext {
  sampleRate = 48000;
  currentTime = 10;
  destination = Object.freeze({ kind: 'destination' });
  state = 'suspended';
  onstatechange = null;
  addModuleUrls = [];
  sourceNode = new FakeNode();
  buffers = [];
  bufferSources = [];
  resumeLeavesSuspended = false;
  resumeErrorName = null;
  closeCount = 0;
  closeThrows = false;
  bufferSourceThrows = false;
  bufferSourceStartThrows = false;
  bufferSourceStopThrows = false;
  bufferSourceDisconnectThrows = false;
  onBufferSourceStart = null;
  addModulePromise = null;
  resumePromise = null;

  audioWorklet = {
    addModule: async url => {
      this.addModuleUrls.push(url);
      if (this.addModulePromise !== null) await this.addModulePromise;
    },
  };

  async resume() {
    if (this.resumeErrorName !== null) {
      const error = new Error('resume failed');
      error.name = this.resumeErrorName;
      throw error;
    }
    if (this.resumePromise !== null) await this.resumePromise;
    if (this.state === 'closed') return;
    if (!this.resumeLeavesSuspended) this.state = 'running';
  }

  async close() {
    this.closeCount += 1;
    if (this.closeThrows) throw new Error('context close failed');
    if (this.closePromise !== null) await this.closePromise;
    this.state = 'closed';
  }

  createMediaStreamSource() {
    return this.sourceNode;
  }

  createBuffer(numberOfChannels, length, sampleRate) {
    const buffer = new FakeAudioBuffer();
    buffer.numberOfChannels = numberOfChannels;
    buffer.length = length;
    buffer.sampleRate = sampleRate;
    this.buffers.push(buffer);
    return buffer;
  }

  createBufferSource() {
    if (this.bufferSourceThrows) throw new Error('buffer source failed');
    const source = new FakeBufferSource();
    source.startThrows = this.bufferSourceStartThrows;
    source.stopThrows = this.bufferSourceStopThrows;
    source.disconnectThrows = this.bufferSourceDisconnectThrows;
    const start = source.start.bind(source);
    source.start = when => {
      start(when);
      this.onBufferSourceStart?.(when);
    };
    this.bufferSources.push(source);
    return source;
  }
}

test('first accepted WebAudio schedule emits one content-free diagnostic estimate', async () => {
  const fake = fakeEnvironment();
  const timings = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    monotonicNowMs: () => 100,
    observer: { onPlayoutTiming: event => timings.push(event) },
  });
  await adapter.unlockPlayout();
  const context = fake.contexts[0];
  context.getOutputTimestamp = () => ({ contextTime: 10, performanceTime: 500 });
  context.outputLatency = 0.02;
  adapter.beginPlayout(firstResponse);

  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 1)), true);

  assert.deepEqual(timings, [{
    response: firstResponse,
    unit_id: 'unit-1',
    seq: 0,
    scheduled_at_monotonic_ms: 100,
    estimated_start_monotonic_ms: 1_500,
    uncertainty_ms: 20,
  }]);
});

test('first schedule timing falls back without touching diagnostic clocks when no observer exists', async () => {
  const observedFake = fakeEnvironment();
  const timings = [];
  const observed = new BrowserAudioIOAdapter({
    enabled: true,
    environment: observedFake.environment,
    monotonicNowMs: () => 100,
    observer: { onPlayoutTiming: event => timings.push(event) },
  });
  await observed.unlockPlayout();
  observedFake.contexts[0].baseLatency = 0.005;
  observed.beginPlayout(firstResponse);
  assert.equal(observed.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(timings[0].estimated_start_monotonic_ms, 1_100);
  assert.equal(timings[0].uncertainty_ms, 5);

  const inertFake = fakeEnvironment();
  const inert = new BrowserAudioIOAdapter({
    enabled: true,
    environment: inertFake.environment,
    monotonicNowMs: () => { throw new Error('diagnostic clock accessed'); },
  });
  await inert.unlockPlayout();
  Object.defineProperties(inertFake.contexts[0], {
    getOutputTimestamp: { get() { throw new Error('timestamp accessed'); } },
    outputLatency: { get() { throw new Error('latency accessed'); } },
    baseLatency: { get() { throw new Error('base latency accessed'); } },
  });
  inert.beginPlayout(firstResponse);
  assert.equal(inert.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
});

test('first schedule fallback never estimates before scheduling when currentTime advances past startAt', async () => {
  for (const timestampThrows of [false, true]) {
    const fake = fakeEnvironment();
    const timings = [];
    const adapter = new BrowserAudioIOAdapter({
      enabled: true,
      environment: fake.environment,
      monotonicNowMs: () => 100,
      observer: { onPlayoutTiming: event => timings.push(event) },
    });
    await adapter.unlockPlayout();
    const context = fake.contexts[0];
    if (timestampThrows) {
      context.getOutputTimestamp = () => { throw new Error('timestamp unavailable'); };
    }
    context.onBufferSourceStart = startAt => {
      context.currentTime = startAt + 1;
    };
    adapter.beginPlayout(firstResponse);

    assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
    assert.equal(timings[0].scheduled_at_monotonic_ms, 100);
    assert.equal(timings[0].estimated_start_monotonic_ms, 100);
  }
});

test('first-schedule observer throw and reentrant enqueue cannot duplicate or fail playout', async () => {
  const throwingFake = fakeEnvironment();
  const throwing = new BrowserAudioIOAdapter({
    enabled: true,
    environment: throwingFake.environment,
    observer: { onPlayoutTiming() { throw new Error('PRIVATE diagnostic failure'); } },
  });
  await throwing.unlockPlayout();
  throwing.beginPlayout(firstResponse);
  assert.equal(throwing.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(throwingFake.contexts[0].bufferSources.length, 1);

  const reentrantFake = fakeEnvironment();
  const timings = [];
  let reentrant;
  reentrant = new BrowserAudioIOAdapter({
    enabled: true,
    environment: reentrantFake.environment,
    observer: {
      onPlayoutTiming(event) {
        timings.push(event);
        assert.equal(reentrant.enqueuePlayout(pcmChunk(firstResponse, 1)), true);
      },
    },
  });
  await reentrant.unlockPlayout();
  reentrant.beginPlayout(firstResponse);
  assert.equal(reentrant.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(timings.length, 1);
  assert.equal(reentrantFake.contexts[0].bufferSources.length, 2);
});

function fakeEnvironment(overrides = {}) {
  const document = new FakeDocument();
  const mediaDevices = new FakeMediaDevices();
  const contexts = [];
  const worklets = [];
  let nextId = 0;
  const environment = {
    isSecureContext: true,
    document,
    mediaDevices,
    permissions: null,
    createAudioContext() {
      const context = new FakeAudioContext();
      contexts.push(context);
      return context;
    },
    createAudioWorkletNode(context, name, options) {
      const worklet = new FakeWorkletNode();
      worklet.creation = { context, name, options };
      worklets.push(worklet);
      return worklet;
    },
    createId() {
      nextId += 1;
      return `capture-${nextId}`;
    },
    ...overrides,
  };
  return { environment, document, mediaDevices, contexts, worklets };
}

const firstResponse = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 });
const secondResponse = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-2', response_generation: 1 });
const thirdResponse = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-3', response_generation: 2 });
const provider = Object.freeze({ provider_id: 'formal-tts', implementation_class: 'formal', fallback_from: null });

function pcmChunk(response, seq, overrides = {}) {
  return {
    response,
    unit_id: 'unit-1',
    seq,
    sample_rate_hz: 48000,
    channel_count: 1,
    samples: new Float32Array(960).fill((seq + 1) / 10),
    provider,
    ...overrides,
  };
}

function nextTask() {
  return new Promise(resolve => setImmediate(resolve));
}

async function outcomeWithin(operation, timeoutMessage) {
  let timeoutHandle = null;
  try {
    return await Promise.race([
      operation.then(
        () => null,
        error => error
      ),
      new Promise(resolve => {
        timeoutHandle = setTimeout(() => resolve(timeoutMessage), 100);
      }),
    ]);
  } finally {
    if (timeoutHandle !== null) clearTimeout(timeoutHandle);
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test('platform inspection is side-effect free and keeps capture identity separate from playout', async () => {
  const fake = fakeEnvironment();
  const capability = inspectBrowserAudioPlatform(true, fake.environment);
  assert.equal(capability.capture_pcm_f32, true);
  assert.equal(capability.playout_pcm_f32, true);
  assert.equal(capability.media_recorder_realtime, false);
  assert.equal(capability.output_device_selection, false);
  assert.equal(capability.physical_heard_ack, false);
  assert.equal(fake.contexts.length, 0);
  assert.equal(fake.mediaDevices.constraints.length, 0);

  const noCaptureIdentity = fakeEnvironment({ createId: null });
  const noCaptureIdentityCapability = inspectBrowserAudioPlatform(true, noCaptureIdentity.environment);
  assert.equal(noCaptureIdentityCapability.capture_pcm_f32, false);
  assert.equal(noCaptureIdentityCapability.playout_pcm_f32, true);
  assert.equal(noCaptureIdentityCapability.stable_identity, false);
  const playoutOnlyAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: noCaptureIdentity.environment });
  assert.equal((await playoutOnlyAdapter.unlockPlayout()).sample_rate_hz, 48000);
  await playoutOnlyAdapter.close();
});

test('capture reuses the user-unlocked playout context across bounded turns', async () => {
  const fake = fakeEnvironment();
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
  });

  await adapter.unlockPlayout();
  const sharedContext = fake.contexts[0];
  const playoutStateObserver = sharedContext.onstatechange;
  await adapter.startCapture();

  assert.equal(fake.contexts.length, 1);
  assert.notEqual(sharedContext.onstatechange, playoutStateObserver);
  await adapter.stopCapture('turn_committed');
  assert.equal(sharedContext.closeCount, 0);
  assert.equal(sharedContext.state, 'running');
  assert.equal(sharedContext.onstatechange, playoutStateObserver);

  fake.mediaDevices.stream = new FakeStream();
  await adapter.startCapture();
  assert.equal(fake.contexts.length, 1);
  await adapter.stopCapture('second_turn_committed');
  assert.equal(sharedContext.closeCount, 0);
  assert.equal(sharedContext.onstatechange, playoutStateObserver);

  await adapter.close();
  assert.equal(sharedContext.closeCount, 1);
  assert.equal(sharedContext.state, 'closed');
});

test('close fences an active capture on the shared context without restoring stale handlers', async () => {
  const fake = fakeEnvironment();
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
  });

  await adapter.unlockPlayout();
  const sharedContext = fake.contexts[0];
  const playoutStateObserver = sharedContext.onstatechange;
  await adapter.startCapture();
  const captureStateObserver = sharedContext.onstatechange;
  assert.notEqual(captureStateObserver, playoutStateObserver);

  await adapter.close();
  assert.equal(fake.contexts.length, 1);
  assert.equal(sharedContext.closeCount, 1);
  assert.equal(sharedContext.state, 'closed');
  assert.equal(sharedContext.onstatechange, null);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
});

test('shared context loss notifies both playout and capture owners before one cleanup', async () => {
  const fake = fakeEnvironment();
  const captureEvents = [];
  const playoutEvents = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState: event => captureEvents.push(event),
      onPlayoutState: event => playoutEvents.push(event),
    },
  });

  await adapter.unlockPlayout();
  await adapter.startCapture();
  const sharedContext = fake.contexts[0];
  const composedStateObserver = sharedContext.onstatechange;
  await adapter.unlockPlayout();
  assert.equal(sharedContext.onstatechange, composedStateObserver);
  sharedContext.state = 'suspended';
  sharedContext.onstatechange?.({});
  for (let turn = 0; turn < 100 && adapter.captureState() !== 'stopped'; turn += 1) {
    await nextTask();
  }

  assert.equal(adapter.captureState(), 'stopped');
  assert.equal(captureEvents.at(-1).reason, 'audio_context_not_running');
  assert.equal(playoutEvents.at(-1).reason, 'audio_context_not_running');
  assert.equal(sharedContext.closeCount, 0);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  await adapter.close();
  assert.equal(sharedContext.closeCount, 1);
});

test('disabled and insecure capture reject before media, context, listeners, or timers', async () => {
  let disabledEnvironmentReads = 0;
  const explodingEnvironment = new Proxy(
    {},
    {
      get() {
        disabledEnvironmentReads += 1;
        throw new Error('disabled browser environment was read');
      },
    }
  );
  assert.deepEqual(inspectBrowserAudioPlatform(false, explodingEnvironment), {
    enabled: false,
    secure_context: false,
    document_visibility: false,
    media_devices: false,
    audio_context: false,
    audio_worklet_node: false,
    stable_identity: false,
    capture_pcm_f32: false,
    playout_pcm_f32: false,
    media_recorder_realtime: false,
    output_device_selection: false,
    physical_heard_ack: false,
    reasons: ['FEATURE_DISABLED'],
  });
  const disabledAdapter = new BrowserAudioIOAdapter({ enabled: false, environment: explodingEnvironment });
  await assert.rejects(
    () => disabledAdapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'FEATURE_DISABLED'
  );
  await assert.rejects(
    () => disabledAdapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'FEATURE_DISABLED'
  );
  assert.equal(disabledEnvironmentReads, 0);

  for (const options of [
    { enabled: false, environment: fakeEnvironment().environment, reason: 'FEATURE_DISABLED' },
    {
      enabled: true,
      environment: fakeEnvironment({ isSecureContext: false }).environment,
      reason: 'INSECURE_CONTEXT',
    },
  ]) {
    const adapter = new BrowserAudioIOAdapter({ enabled: options.enabled, environment: options.environment });
    await assert.rejects(
      () => adapter.startCapture(),
      error => error instanceof BrowserAudioIOViolation && error.reason === options.reason
    );
    assert.equal(options.environment.mediaDevices.constraints.length, 0);
    assert.equal(options.environment.document.listenerCount('visibilitychange'), 0);
  }

  const missingDocument = fakeEnvironment({ document: null });
  const missingDocumentAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: missingDocument.environment });
  assert.equal(missingDocumentAdapter.capability().document_visibility, false);
  assert.equal(missingDocumentAdapter.capability().playout_pcm_f32, false);
  await assert.rejects(
    () => missingDocumentAdapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'DOCUMENT_VISIBILITY_UNAVAILABLE'
  );
  assert.equal(missingDocument.mediaDevices.constraints.length, 0);
  assert.equal(missingDocument.contexts.length, 0);
  await assert.rejects(
    () => missingDocumentAdapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'DOCUMENT_VISIBILITY_UNAVAILABLE'
  );
  assert.equal(missingDocument.contexts.length, 0);
});

test('capture requests explicit processing, reports actual settings, and emits copied ordered 20ms frames', async () => {
  const fake = fakeEnvironment();
  const frames = [];
  const states = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    captureWorkletModuleUrl: 'capture-worklet.js',
    observer: {
      onCaptureFrame: frame => frames.push(frame),
      onCaptureState: state => states.push(state),
    },
  });

  const metadata = await adapter.startCapture({ deviceId: 'mic-1' });
  assert.equal(metadata.requested_device, 'exact');
  assert.deepEqual(metadata.requested_processing, {
    echo_cancellation: true,
    noise_suppression: true,
    auto_gain_control: true,
    channel_count: 1,
  });
  assert.deepEqual(metadata.actual_processing, {
    echo_cancellation: true,
    noise_suppression: false,
    auto_gain_control: true,
    track_sample_rate_hz: 48000,
    track_channel_count: 1,
    device_id_present: true,
  });
  assert.equal(metadata.frame_format.samples_per_channel, 960);
  assert.equal(fake.mediaDevices.constraints[0].audio.deviceId.exact, 'mic-1');
  assert.equal(fake.mediaDevices.constraints[0].audio.echoCancellation.ideal, true);
  assert.equal(fake.contexts[0].addModuleUrls[0], 'capture-worklet.js');
  assert.equal(fake.worklets[0].creation.name, 'jiuwenswarm-live-voice-capture-v1');
  assert.equal(fake.worklets[0].creation.options.numberOfInputs, 1);
  assert.equal(fake.worklets[0].creation.options.numberOfOutputs, 1);
  assert.deepEqual(fake.worklets[0].creation.options.outputChannelCount, [1]);
  assert.deepEqual(fake.worklets[0].connected, [fake.contexts[0].destination]);
  assert.deepEqual(fake.contexts[0].sourceNode.connected, [fake.worklets[0]]);

  const samples = new Float32Array(960).fill(0.25);
  fake.worklets[0].port.emit({
    kind: 'frame',
    capture_generation: metadata.capture_generation,
    seq: 0,
    sample_cursor: 0,
    context_time_s: 3,
    sample_rate_hz: 48000,
    samples,
  });
  samples[0] = 0.75;
  assert.equal(frames.length, 1);
  assert.equal(frames[0].samples[0], 0.25);
  assert.equal(frames[0].capture.capture_id, metadata.capture_id);
  assert.equal(states.at(-1).state, 'active');

  assert.equal(await adapter.stopCapture(), true);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('capture fails closed and releases all resources when the silent keep-alive graph cannot connect', async () => {
  const worklet = new FakeWorkletNode();
  worklet.connectThrows = true;
  const fake = fakeEnvironment({ createAudioWorkletNode: () => worklet });
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_START_FAILED'
  );

  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].sourceNode.connected.length, 0);
  assert.equal(fake.contexts[0].sourceNode.disconnectCount, 1);
  assert.equal(worklet.disconnectCount, 1);
  assert.equal(worklet.port.closeCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
});

test('capture handoff rejects an input track that is already muted and releases every resource', async () => {
  const fake = fakeEnvironment();
  const events = [];
  fake.mediaDevices.stream.track.muted = true;
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: event => events.push(event) },
  });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_INPUT_MUTED'
  );
  assert.deepEqual(
    events.map(event => event.reason),
    ['start_requested', 'audio_input_muted']
  );
  assert.equal(adapter.captureState(), 'failed');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
});

test('capture handoff does not duplicate a simultaneously delivered mute event', async () => {
  const fake = fakeEnvironment();
  const events = [];
  let adapter;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState(event) {
        events.push(event);
        if (event.reason === 'capture_started') {
          fake.mediaDevices.stream.track.muted = true;
          fake.mediaDevices.stream.track.emit('mute');
        }
      },
    },
  });

  await adapter.startCapture();
  assert.equal(events.filter(event => event.reason === 'track_muted').length, 1);
  assert.equal(adapter.captureState(), 'active');
  await adapter.stopCapture('test_complete');
});

test('permission denial and pending-start cancellation fail closed with zero active capture', async () => {
  const denied = fakeEnvironment();
  denied.mediaDevices.getUserMediaImpl = async () => {
    const error = new Error('denied');
    error.name = 'NotAllowedError';
    throw error;
  };
  const deniedAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: denied.environment });
  await assert.rejects(
    () => deniedAdapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'MICROPHONE_PERMISSION_DENIED'
  );
  assert.equal(denied.contexts.length, 0);
  assert.equal(denied.document.listenerCount('visibilitychange'), 0);

  const pending = fakeEnvironment();
  let resolveStream;
  pending.mediaDevices.getUserMediaImpl = () => new Promise(resolve => (resolveStream = resolve));
  const pendingAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: pending.environment });
  const start = pendingAdapter.startCapture();
  assert.equal(await pendingAdapter.stopCapture('user_cancelled'), true);
  resolveStream(pending.mediaDevices.stream);
  await assert.rejects(
    () => start,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
  );
  assert.equal(pending.mediaDevices.stream.track.stopCount, 1);
  assert.equal(pending.contexts.length, 0);
});

test('active microphone permission revocation stops the exact capture with a stable reason and no listener leak', async () => {
  const status = new FakePermissionStatus('granted');
  const permissions = new FakePermissions(status);
  const fake = fakeEnvironment({ permissions });
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: event => events.push(event) },
  });

  await adapter.startCapture();
  assert.deepEqual(permissions.queries, [{ name: 'microphone' }]);
  assert.equal(status.listenerCount('change'), 1);

  status.change('denied');
  for (let turn = 0; turn < 100 && adapter.captureState() !== 'stopped'; turn += 1) await nextTask();

  assert.equal(adapter.captureState(), 'stopped');
  assert.deepEqual(
    events.filter(event => event.reason === 'microphone_permission_revoked').map(event => event.state),
    ['stopping', 'stopped']
  );
  assert.equal(status.listenerCount('change'), 0);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(adapter.businessCancelCount(), 0);
});

test('pending capture revocation rejects with MICROPHONE_PERMISSION_REVOKED and never allocates an AudioContext', async () => {
  const status = new FakePermissionStatus('prompt');
  const permissions = new FakePermissions(status);
  const fake = fakeEnvironment({ permissions });
  const primaryTrack = fake.mediaDevices.stream.track;
  const secondTrack = new FakeTrack();
  secondTrack.id = 'track-2';
  fake.mediaDevices.stream = {
    track: primaryTrack,
    getAudioTracks: () => [primaryTrack],
    getTracks: () => [primaryTrack, secondTrack],
  };
  const media = deferred();
  fake.mediaDevices.getUserMediaImpl = () => media.promise;
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  const starting = adapter.startCapture();
  await nextTask();
  assert.equal(status.listenerCount('change'), 1);
  status.change('denied');
  const outcome = await outcomeWithin(starting, 'permission revocation did not settle capture');
  assert.equal(outcome instanceof BrowserAudioIOViolation && outcome.reason === 'MICROPHONE_PERMISSION_REVOKED', true);
  assert.equal(status.listenerCount('change'), 0);
  media.resolve(fake.mediaDevices.stream);
  for (let turn = 0; turn < 100 && fake.mediaDevices.stream.track.stopCount === 0; turn += 1) await nextTask();
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(secondTrack.stopCount, 1);
  assert.equal(fake.contexts.length, 0);
  assert.equal(adapter.captureState(), 'stopped');
});

test('permission registration-window transition fails closed but initial denied remains getUserMedia denial', async () => {
  const transitionStatus = new FakePermissionStatus('granted');
  transitionStatus.onAdd = () => {
    transitionStatus.state = 'denied';
  };
  const transitionFake = fakeEnvironment({ permissions: new FakePermissions(transitionStatus) });
  const transitionAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: transitionFake.environment });
  await assert.rejects(
    () => transitionAdapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'MICROPHONE_PERMISSION_REVOKED'
  );
  assert.equal(transitionStatus.listenerCount('change'), 0);
  assert.equal(transitionFake.contexts.length, 0);

  const deniedStatus = new FakePermissionStatus('denied');
  const deniedFake = fakeEnvironment({ permissions: new FakePermissions(deniedStatus) });
  deniedFake.mediaDevices.getUserMediaImpl = async () => {
    const error = new Error('initial denial');
    error.name = 'NotAllowedError';
    throw error;
  };
  const deniedAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: deniedFake.environment });
  await assert.rejects(
    () => deniedAdapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'MICROPHONE_PERMISSION_DENIED'
  );
  assert.equal(deniedStatus.listenerCount('change'), 0);
});

test('a delayed first denied permission fact revokes exact media access after active handoff or during later startup', async () => {
  const activeQuery = deferred();
  const activeStatus = new FakePermissionStatus('denied');
  const activeFake = fakeEnvironment({ permissions: { query: () => activeQuery.promise } });
  const activeEvents = [];
  const activeAdapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: activeFake.environment,
    observer: { onCaptureState: event => activeEvents.push(event) },
  });
  await activeAdapter.startCapture();
  activeQuery.resolve(activeStatus);
  for (let turn = 0; turn < 100 && activeAdapter.captureState() !== 'stopped'; turn += 1) await nextTask();
  assert.equal(activeAdapter.captureState(), 'stopped');
  assert.equal(
    activeEvents.some(event => event.reason === 'microphone_permission_revoked'),
    true
  );
  assert.equal(activeFake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(activeFake.contexts[0].state, 'closed');

  const startupQuery = deferred();
  const startupStatus = new FakePermissionStatus('denied');
  const startupFake = fakeEnvironment({ permissions: { query: () => startupQuery.promise } });
  const addModule = deferred();
  const originalCreate = startupFake.environment.createAudioContext;
  startupFake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.addModulePromise = addModule.promise;
    return context;
  };
  const startupAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: startupFake.environment });
  const starting = startupAdapter.startCapture();
  for (let turn = 0; turn < 100 && startupFake.contexts[0]?.addModuleUrls.length !== 1; turn += 1) await nextTask();
  assert.equal(startupFake.contexts[0].addModuleUrls.length, 1);
  startupQuery.resolve(startupStatus);
  const startupOutcome = await outcomeWithin(starting, 'delayed permission denial did not settle later startup');
  assert.equal(startupOutcome instanceof BrowserAudioIOViolation && startupOutcome.reason === 'MICROPHONE_PERMISSION_REVOKED', true);
  assert.equal(startupFake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(startupFake.contexts[0].state, 'closed');
  assert.equal(startupFake.worklets.length, 0);
  addModule.resolve();
  await nextTask();
});

test('unsupported, throwing, hanging, and unknown permission observations never block or guess capture state', async () => {
  const cases = [
    { permissions: {} },
    {
      permissions: {
        query() {
          throw new Error('permission query unavailable');
        },
      },
    },
  ];
  for (const current of cases) {
    const fake = fakeEnvironment({ permissions: current.permissions });
    const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
    await adapter.startCapture();
    assert.equal(adapter.captureState(), 'active');
    await adapter.stopCapture('test_complete');
  }

  const lateQuery = deferred();
  const lateStatus = new FakePermissionStatus('granted');
  const hangingFake = fakeEnvironment({ permissions: { query: () => lateQuery.promise } });
  const hangingAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: hangingFake.environment });
  await hangingAdapter.startCapture();
  assert.equal(hangingAdapter.captureState(), 'active');
  await hangingAdapter.stopCapture('test_complete');
  lateQuery.resolve(lateStatus);
  await nextTask();
  assert.equal(lateStatus.listenerCount('change'), 0);

  const unknownStatus = new FakePermissionStatus('unknown');
  const unknownFake = fakeEnvironment({ permissions: new FakePermissions(unknownStatus) });
  const unknownAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: unknownFake.environment });
  await unknownAdapter.startCapture();
  unknownStatus.emit('change');
  await nextTask();
  assert.equal(unknownAdapter.captureState(), 'active');
  unknownStatus.change('prompt');
  unknownStatus.change('granted');
  assert.equal(unknownAdapter.captureState(), 'active');
  assert.equal(unknownFake.mediaDevices.constraints.length, 1);
  assert.equal(unknownFake.contexts.length, 1);
  await unknownAdapter.stopCapture('test_complete');
  assert.equal(unknownStatus.listenerCount('change'), 0);

  const throwingStatus = new FakePermissionStatus('granted');
  Object.defineProperty(throwingStatus, 'state', {
    configurable: true,
    get() {
      throw new Error('permission state unavailable');
    },
  });
  const throwingFake = fakeEnvironment({ permissions: new FakePermissions(throwingStatus) });
  const throwingAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: throwingFake.environment });
  await throwingAdapter.startCapture();
  throwingStatus.emit('change');
  await nextTask();
  assert.equal(throwingAdapter.captureState(), 'active');
  await throwingAdapter.stopCapture('test_complete');
  assert.equal(throwingStatus.listenerCount('change'), 0);
});

test('permission listener ownership is cleaned after partial add, startup failure, explicit stop, and close', async () => {
  const partialStatus = new FakePermissionStatus('granted');
  partialStatus.throwAfterAdd = true;
  const partialFake = fakeEnvironment({ permissions: new FakePermissions(partialStatus) });
  const partialAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: partialFake.environment });
  await partialAdapter.startCapture();
  assert.equal(partialStatus.listenerCount('change'), 0);
  await partialAdapter.stopCapture('test_complete');

  const failureStatus = new FakePermissionStatus('granted');
  const failureFake = fakeEnvironment({ permissions: new FakePermissions(failureStatus) });
  const failedMedia = deferred();
  failureFake.mediaDevices.getUserMediaImpl = () => failedMedia.promise;
  const failureAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: failureFake.environment });
  const failedStart = failureAdapter.startCapture();
  await nextTask();
  assert.equal(failureStatus.listenerCount('change'), 1);
  const failure = new Error('device unavailable');
  failure.name = 'NotFoundError';
  failedMedia.reject(failure);
  await assert.rejects(
    () => failedStart,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_INPUT_NOT_FOUND'
  );
  assert.equal(failureStatus.listenerCount('change'), 0);

  const stopStatus = new FakePermissionStatus('granted');
  const stopFake = fakeEnvironment({ permissions: new FakePermissions(stopStatus) });
  const stopAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: stopFake.environment });
  await stopAdapter.startCapture();
  assert.equal(stopStatus.listenerCount('change'), 1);
  await stopAdapter.stopCapture('test_complete');
  assert.equal(stopStatus.listenerCount('change'), 0);

  const closeStatus = new FakePermissionStatus('granted');
  const closeFake = fakeEnvironment({ permissions: new FakePermissions(closeStatus) });
  const closeAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: closeFake.environment });
  await closeAdapter.startCapture();
  assert.equal(closeStatus.listenerCount('change'), 1);
  await closeAdapter.close();
  assert.equal(closeStatus.listenerCount('change'), 0);
});

test('late permission query and change callbacks from an old capture generation have zero successor effect', async () => {
  const lateQuery = deferred();
  const oldStatus = new FakePermissionStatus('granted');
  const successorStatus = new FakePermissionStatus('granted');
  const finalStatus = new FakePermissionStatus('granted');
  let queryCount = 0;
  const permissions = {
    query() {
      queryCount += 1;
      if (queryCount === 1) return lateQuery.promise;
      return Promise.resolve(queryCount === 2 ? successorStatus : finalStatus);
    },
  };
  const fake = fakeEnvironment({ permissions });
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  const first = await adapter.startCapture();
  await adapter.stopCapture('first_complete');
  fake.mediaDevices.stream = new FakeStream();
  const second = await adapter.startCapture();
  await nextTask();
  assert.notEqual(second.capture_generation, first.capture_generation);
  assert.equal(successorStatus.listenerCount('change'), 1);

  lateQuery.resolve(oldStatus);
  await nextTask();
  assert.equal(oldStatus.listenerCount('change'), 0);
  oldStatus.change('denied');
  await nextTask();
  assert.equal(adapter.captureState(), 'active');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 0);

  const retainedOldChange = [...successorStatus.listeners.get('change')][0];
  await adapter.stopCapture('second_complete');
  assert.equal(successorStatus.listenerCount('change'), 0);
  fake.mediaDevices.stream = new FakeStream();
  const third = await adapter.startCapture();
  await nextTask();
  assert.notEqual(third.capture_generation, second.capture_generation);
  successorStatus.state = 'denied';
  retainedOldChange();
  await nextTask();
  assert.equal(adapter.captureState(), 'active');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 0);

  await adapter.stopCapture('test_complete');
  assert.equal(finalStatus.listenerCount('change'), 0);
});

test('partial device-listener registration failure removes the listener before media effects', async () => {
  const fake = fakeEnvironment();
  const originalAdd = fake.mediaDevices.addEventListener.bind(fake.mediaDevices);
  fake.mediaDevices.addEventListener = (type, listener) => {
    originalAdd(type, listener);
    throw new Error('listener registration failed');
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_START_FAILED'
  );

  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
  assert.equal(fake.mediaDevices.constraints.length, 0);
  assert.equal(fake.contexts.length, 0);
});

test('active permission revocation still releases every capture resource when listener removal throws', async () => {
  const permission = new FakePermissionStatus('granted');
  const fake = fakeEnvironment({ permissions: new FakePermissions(permission) });
  const events = [];
  const originalDeviceRemove = fake.mediaDevices.removeEventListener.bind(fake.mediaDevices);
  let deviceRemoveThrows = true;
  fake.mediaDevices.removeEventListener = (type, listener) => {
    if (type === 'devicechange' && deviceRemoveThrows) throw new Error('device listener removal failed');
    originalDeviceRemove(type, listener);
  };
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: event => events.push(event) },
  });

  await adapter.startCapture();
  const oldDeviceChange = [...fake.mediaDevices.listeners.get('devicechange')][0];
  const oldTrack = fake.mediaDevices.stream.track;
  const oldTrackEnded = [...oldTrack.listeners.get('ended')][0];
  const originalTrackRemove = oldTrack.removeEventListener.bind(oldTrack);
  oldTrack.removeEventListener = (type, listener) => {
    if (type === 'ended') throw new Error('track listener removal failed');
    originalTrackRemove(type, listener);
  };
  const activeContext = fake.contexts[0];
  const installedContextStateChange = activeContext.onstatechange;
  Object.defineProperty(activeContext, 'onstatechange', {
    configurable: true,
    get: () => installedContextStateChange,
    set() {
      throw new Error('context listener restoration failed');
    },
  });

  permission.change('denied');
  for (let turn = 0; turn < 100 && adapter.captureState() !== 'failed'; turn += 1) await nextTask();

  assert.equal(adapter.captureState(), 'failed');
  assert.equal(events.at(-1).reason, 'capture_cleanup_failed');
  assert.equal(oldTrack.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(fake.contexts[0].sourceNode.disconnectCount, 1);
  assert.equal(fake.worklets[0].disconnectCount, 1);
  assert.equal(fake.worklets[0].port.closeCount, 1);
  assert.equal(adapter.businessCancelCount(), 0);

  deviceRemoveThrows = false;
  permission.state = 'granted';
  fake.mediaDevices.stream = new FakeStream();
  await nextTask();
  await adapter.startCapture();
  fake.mediaDevices.devices = [];
  oldDeviceChange();
  oldTrackEnded();
  await nextTask();
  assert.equal(adapter.captureState(), 'active');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 0);
  fake.mediaDevices.devices = [{ kind: 'audioinput' }];
  await adapter.stopCapture('test_complete');
});

test('partial device-listener add and removal failures stay visible without blocking a successor', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const originalAdd = fake.mediaDevices.addEventListener.bind(fake.mediaDevices);
  const originalRemove = fake.mediaDevices.removeEventListener.bind(fake.mediaDevices);
  let oldDeviceChange = null;
  fake.mediaDevices.addEventListener = (type, listener) => {
    oldDeviceChange = listener;
    originalAdd(type, listener);
    throw new Error('device listener add failed after partial registration');
  };
  fake.mediaDevices.removeEventListener = () => {
    throw new Error('device listener removal failed');
  };
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: event => events.push(event) },
  });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CLEANUP_FAILED'
  );
  assert.equal(adapter.captureState(), 'failed');
  assert.equal(events.at(-1).reason, 'capture_cleanup_failed');
  assert.equal(fake.mediaDevices.constraints.length, 0);
  assert.equal(fake.contexts.length, 0);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 1);

  fake.mediaDevices.addEventListener = originalAdd;
  fake.mediaDevices.removeEventListener = originalRemove;
  await adapter.startCapture();
  fake.mediaDevices.devices = [];
  oldDeviceChange();
  await nextTask();
  assert.equal(adapter.captureState(), 'active');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 0);
  fake.mediaDevices.devices = [{ kind: 'audioinput' }];
  await adapter.stopCapture('test_complete');
});

test('a starting observer can fence capture before any microphone or context effect', async () => {
  const fake = fakeEnvironment();
  let adapter;
  let stopPromise = null;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState(event) {
        if (event.reason === 'start_requested') stopPromise = adapter.stopCapture('observer_fence');
      },
    },
  });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
  );
  assert.notEqual(stopPromise, null);
  await stopPromise;
  assert.equal(fake.mediaDevices.constraints.length, 0);
  assert.equal(fake.contexts.length, 0);
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
  assert.equal(adapter.captureState(), 'stopped');
});

test('a page-hidden transition during starting is cleaned before media effects', async () => {
  const fake = fakeEnvironment();
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState(event) {
        if (event.reason === 'start_requested') fake.document.visibilityState = 'hidden';
      },
    },
  });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PAGE_HIDDEN'
  );
  assert.equal(fake.mediaDevices.constraints.length, 0);
  assert.equal(fake.contexts.length, 0);
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
  assert.equal(adapter.captureState(), 'failed');
});

test('an active-handoff observer stop prevents capture startup from reporting success', async () => {
  const fake = fakeEnvironment();
  const reasons = [];
  let adapter;
  let stopPromise = null;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState(event) {
        reasons.push(event.reason);
        if (event.reason === 'capture_started') stopPromise = adapter.stopCapture('observer_handoff_fence');
      },
    },
  });

  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
  );
  assert.notEqual(stopPromise, null);
  await stopPromise;
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(adapter.captureState(), 'stopped');
  assert.equal(reasons.includes('track_muted'), false);
});

test('stop releases microphone and context while AudioWorklet loading remains pending', async () => {
  const fake = fakeEnvironment();
  const addModule = deferred();
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.addModulePromise = addModule.promise;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  const start = adapter.startCapture();
  await nextTask();
  assert.equal(fake.contexts[0].addModuleUrls.length, 1);
  assert.equal(await adapter.stopCapture('pending_stop'), true);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  addModule.resolve();
  await assert.rejects(
    () => start,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
});

test('stop releases microphone and context while AudioContext resume remains pending', async () => {
  const fake = fakeEnvironment();
  const resume = deferred();
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.resumePromise = resume.promise;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  const start = adapter.startCapture();
  await nextTask();
  assert.equal(await adapter.stopCapture('pending_resume_stop'), true);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  resume.resolve();
  await assert.rejects(
    () => start,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
});

test('track end and AudioContext loss during worklet loading never publish active capture', async () => {
  for (const failure of ['track', 'context']) {
    const fake = fakeEnvironment();
    const addModule = deferred();
    const states = [];
    const originalCreate = fake.environment.createAudioContext;
    fake.environment.createAudioContext = () => {
      const context = originalCreate();
      context.addModulePromise = addModule.promise;
      return context;
    };
    const adapter = new BrowserAudioIOAdapter({
      enabled: true,
      environment: fake.environment,
      observer: { onCaptureState: state => states.push(state) },
    });
    const start = adapter.startCapture();
    await nextTask();
    if (failure === 'track') {
      fake.mediaDevices.stream.track.readyState = 'ended';
      fake.mediaDevices.stream.track.emit('ended');
    } else {
      fake.contexts[0].state = 'suspended';
      fake.contexts[0].onstatechange();
    }
    await nextTask();
    assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
    assert.equal(fake.contexts[0].state, 'closed');
    addModule.resolve();
    await assert.rejects(
      () => start,
      error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
    );
    assert.equal(
      states.some(state => state.reason === 'capture_started'),
      false
    );
  }
});

test('active track end or AudioContext loss releases capture and fences late frames', async () => {
  for (const failure of ['track', 'context']) {
    const fake = fakeEnvironment();
    const frames = [];
    const adapter = new BrowserAudioIOAdapter({
      enabled: true,
      environment: fake.environment,
      observer: { onCaptureFrame: frame => frames.push(frame) },
    });
    const metadata = await adapter.startCapture();
    const stalePort = fake.worklets[0].port;
    if (failure === 'track') {
      fake.mediaDevices.stream.track.readyState = 'ended';
      fake.mediaDevices.stream.track.emit('ended');
    } else {
      fake.contexts[0].state = 'suspended';
      fake.contexts[0].onstatechange();
    }
    await nextTask();
    assert.equal(adapter.captureState(), 'stopped');
    assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
    assert.equal(fake.contexts[0].state, 'closed');
    stalePort.emit({
      kind: 'frame',
      capture_generation: metadata.capture_generation,
      seq: 0,
      sample_cursor: 0,
      context_time_s: 0,
      sample_rate_hz: 48000,
      samples: new Float32Array(960),
    });
    assert.equal(frames.length, 0);
  }
});

test('a context rate that cannot form exact 20ms frames releases the partial capture', async () => {
  const fake = fakeEnvironment();
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.sampleRate = 44117;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'NON_INTEGRAL_AUDIO_FRAME'
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
});

test('sequence gaps, hidden page, and stale worklet callbacks never revive capture', async () => {
  const fake = fakeEnvironment();
  const frames = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureFrame: frame => frames.push(frame) },
  });
  const first = await adapter.startCapture();
  fake.worklets[0].port.emit({
    kind: 'frame',
    capture_generation: first.capture_generation,
    seq: 1,
    sample_cursor: 960,
    context_time_s: 1,
    sample_rate_hz: 48000,
    samples: new Float32Array(960),
  });
  await nextTask();
  assert.equal(frames.length, 0);
  assert.equal(adapter.captureState(), 'stopped');

  fake.mediaDevices.stream = new FakeStream();
  const second = await adapter.startCapture();
  fake.document.visibilityState = 'hidden';
  fake.document.emit('visibilitychange');
  await nextTask();
  assert.equal(adapter.captureState(), 'stopped');
  fake.worklets[1].port.emit({
    kind: 'frame',
    capture_generation: second.capture_generation,
    seq: 0,
    sample_cursor: 0,
    context_time_s: 2,
    sample_rate_hz: 48000,
    samples: new Float32Array(960),
  });
  assert.equal(frames.length, 0);
  fake.document.visibilityState = 'visible';
  fake.document.emit('visibilitychange');
  assert.equal(adapter.captureState(), 'stopped');
});

test('AudioWorklet failures retain exact bounded-gap reasons and fence stale callbacks', async () => {
  const diagnostics = [];
  const fake = fakeEnvironment({ reportCaptureDiagnostic: diagnostic => diagnostics.push(diagnostic) });
  const states = [];
  const frames = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState: event => states.push([event.state, event.reason]),
      onCaptureFrame: frame => frames.push(frame),
    },
  });
  const metadata = await adapter.startCapture();
  const staleCallback = fake.worklets[0].port.onmessage;

  fake.worklets[0].port.emit({
    kind: 'error',
    reason: 'input_gap_exceeded',
    diagnostic: {
      trigger: 'rolling_budget',
      single_gap_exceeded: false,
      rolling_budget_exceeded: true,
      missing_samples: 128,
      recent_gap_samples: 2816,
      rolling_gap_candidate_samples: 2944,
      max_transient_gap_samples: 720,
      max_rolling_gap_samples: 2880,
      render_frame: 48000,
      expected_render_frame: 47872,
      render_delta_samples: 256,
      input_quantum_samples: 128,
      previous_input_quantum_samples: 128,
      input_empty: false,
      context_sample_rate_hz: 48000,
      ignored_private_value: 'must-not-propagate',
    },
  });
  await nextTask();

  assert.equal(adapter.captureState(), 'stopped');
  assert.ok(states.some(([state, reason]) => state === 'stopping' && reason === 'audio_input_gap_exceeded'));
  assert.ok(states.some(([state, reason]) => state === 'stopped' && reason === 'audio_input_gap_exceeded'));
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.deepEqual(diagnostics, [
    {
      event: 'audio_input_gap_exceeded',
      trigger: 'rolling_budget',
      single_gap_exceeded: false,
      rolling_budget_exceeded: true,
      missing_samples: 128,
      recent_gap_samples: 2816,
      rolling_gap_candidate_samples: 2944,
      max_transient_gap_samples: 720,
      max_rolling_gap_samples: 2880,
      render_frame: 48000,
      expected_render_frame: 47872,
      render_delta_samples: 256,
      input_quantum_samples: 128,
      previous_input_quantum_samples: 128,
      input_empty: false,
      context_sample_rate_hz: 48000,
      track_sample_rate_hz: 48000,
      capture_generation: metadata.capture_generation,
      process_call_count: null,
      initial_render_frame: null,
      emitted_frame_count: null,
      sample_cursor: null,
      output_count: null,
      output_channel_count: null,
      output_quantum_samples: null,
      context_state: 'running',
      playout_active: false,
    },
  ]);
  staleCallback?.({
    data: {
      kind: 'frame',
      capture_generation: metadata.capture_generation,
      seq: 0,
      sample_cursor: 0,
      context_time_s: 0,
      sample_rate_hz: 48_000,
      samples: new Float32Array(960),
    },
  });
  assert.equal(frames.length, 0);
});

test('capture diagnostics cannot weaken exact input-gap cleanup', async () => {
  const fake = fakeEnvironment({
    reportCaptureDiagnostic() {
      throw new Error('diagnostic sink unavailable');
    },
  });
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await adapter.startCapture();

  fake.worklets[0].port.emit({ kind: 'error', reason: 'input_gap_exceeded', diagnostic: { trigger: 'single_gap' } });
  await nextTask();

  assert.equal(adapter.captureState(), 'stopped');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
});

test('unknown AudioWorklet errors retain the generic stable gap reason', async () => {
  const fake = fakeEnvironment();
  const states = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: event => states.push([event.state, event.reason]) },
  });
  await adapter.startCapture();

  fake.worklets[0].port.emit({ kind: 'error', reason: 'future_worklet_failure' });
  await nextTask();

  assert.equal(adapter.captureState(), 'stopped');
  assert.ok(states.some(([state, reason]) => state === 'stopped' && reason === 'audio_worklet_gap'));
});

test('fatal AudioWorklet clock and configuration errors retain their exact stable reasons', async () => {
  const cases = [
    ['render_frame_regressed', 'audio_render_frame_regressed'],
    ['render_frame_not_advanced', 'audio_render_frame_not_advanced'],
    ['invalid_frame_configuration', 'invalid_audio_worklet_configuration'],
  ];
  for (const [workletReason, stableReason] of cases) {
    const fake = fakeEnvironment();
    const states = [];
    const adapter = new BrowserAudioIOAdapter({
      enabled: true,
      environment: fake.environment,
      observer: { onCaptureState: event => states.push([event.state, event.reason]) },
    });
    await adapter.startCapture();

    fake.worklets[0].port.emit({ kind: 'error', reason: workletReason });
    await nextTask();

    assert.equal(adapter.captureState(), 'stopped');
    assert.ok(states.some(([state, reason]) => state === 'stopping' && reason === stableReason));
    assert.ok(states.some(([state, reason]) => state === 'stopped' && reason === stableReason));
    assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  }
});

test('capture identity reuse fails closed and releases the replacement resources', async () => {
  const fake = fakeEnvironment({ createId: () => 'reused-capture-id' });
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  const first = await adapter.startCapture();
  assert.equal(first.capture_id, 'reused-capture-id');
  await adapter.stopCapture('restart');

  fake.mediaDevices.stream = new FakeStream();
  await assert.rejects(
    () => adapter.startCapture(),
    error => error.reason === 'CAPTURE_ID_REUSED'
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[1].state, 'closed');
  assert.equal(adapter.captureState(), 'failed');
  await adapter.close();
});

test('observer failures cannot leak capture resources or interrupt lifecycle fencing', async () => {
  const stateObserverFake = fakeEnvironment();
  const stateObserverAdapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: stateObserverFake.environment,
    observer: {
      onCaptureState: () => {
        throw new Error('observer failed');
      },
    },
  });
  await stateObserverAdapter.startCapture();
  assert.equal(stateObserverAdapter.captureState(), 'active');
  assert.equal(await stateObserverAdapter.stopCapture(), true);
  assert.equal(stateObserverFake.mediaDevices.stream.track.stopCount, 1);

  const frameObserverFake = fakeEnvironment();
  const frameObserverAdapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: frameObserverFake.environment,
    observer: {
      onCaptureFrame: () => {
        throw new Error('consumer failed');
      },
    },
  });
  const metadata = await frameObserverAdapter.startCapture();
  frameObserverFake.worklets[0].port.emit({
    kind: 'frame',
    capture_generation: metadata.capture_generation,
    seq: 0,
    sample_cursor: 0,
    context_time_s: 1,
    sample_rate_hz: 48000,
    samples: new Float32Array(960),
  });
  await nextTask();
  assert.equal(frameObserverAdapter.captureState(), 'stopped');
  assert.equal(frameObserverFake.mediaDevices.stream.track.stopCount, 1);
});

test('queued mute callbacks cannot revive stopped capture state', async () => {
  const fake = fakeEnvironment();
  const states = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: state => states.push(state) },
  });
  await adapter.startCapture();
  const staleMute = [...fake.mediaDevices.stream.track.listeners.get('mute')][0];
  await adapter.stopCapture();
  const stateCount = states.length;
  staleMute();
  assert.equal(states.length, stateCount);
  assert.equal(adapter.captureState(), 'stopped');
});

test('cleanup failures remain visible after every releasable resource is attempted', async () => {
  const fake = fakeEnvironment();
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await adapter.startCapture();
  fake.worklets[0].port.closeThrows = true;
  await assert.rejects(
    () => adapter.stopCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CLEANUP_FAILED'
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].state, 'closed');
  assert.equal(adapter.captureState(), 'failed');
});

test('capture cleanup is serialized, blocks restart, and is awaited by close', async () => {
  const fake = fakeEnvironment();
  const closing = deferred();
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await adapter.startCapture();
  fake.contexts[0].closePromise = closing.promise;
  const stop = adapter.stopCapture('slow_cleanup');
  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_STOP_IN_PROGRESS'
  );
  let closeSettled = false;
  const close = adapter.close().then(() => {
    closeSettled = true;
  });
  await nextTask();
  assert.equal(closeSettled, false);
  closing.resolve();
  assert.equal(await stop, true);
  await close;
  assert.equal(closeSettled, true);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].closeCount, 1);
});

test('a stopping observer cannot restart before cleanup ownership is published', async () => {
  const fake = fakeEnvironment();
  const closeGate = deferred();
  let adapter;
  let restartResult = null;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onCaptureState(event) {
        if (event.state === 'stopping') restartResult = adapter.startCapture().catch(error => error);
      },
    },
  });
  await adapter.startCapture();
  fake.contexts[0].closePromise = closeGate.promise;

  const stopPromise = adapter.stopCapture('observer_restart_probe');
  assert.notEqual(restartResult, null);
  const restartError = await restartResult;
  assert.equal(restartError instanceof BrowserAudioIOViolation, true);
  assert.equal(restartError.reason, 'CAPTURE_STOP_IN_PROGRESS');
  assert.equal(fake.mediaDevices.constraints.length, 1);
  closeGate.resolve();
  await stopPromise;
  assert.equal(adapter.captureState(), 'stopped');
});

test('startup-failure cleanup also blocks restart and is awaited by close', async () => {
  const fake = fakeEnvironment();
  const addModule = deferred();
  const closing = deferred();
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.addModulePromise = addModule.promise;
    context.closePromise = closing.promise;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  const start = adapter.startCapture();
  await nextTask();
  addModule.reject(new Error('module failed'));
  await nextTask();
  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_STOP_IN_PROGRESS'
  );
  let closeSettled = false;
  const close = adapter.close().then(() => {
    closeSettled = true;
  });
  await nextTask();
  assert.equal(closeSettled, false);
  closing.resolve();
  await assert.rejects(
    () => start,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_WORKLET_LOAD_FAILED'
  );
  await close;
  assert.equal(closeSettled, true);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].closeCount, 1);
});

test('close immediately fences playout while slow capture cleanup continues', async () => {
  const fake = fakeEnvironment();
  const captureClosing = deferred();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.startCapture();
  fake.contexts[0].closePromise = captureClosing.promise;
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  const playoutContext = fake.contexts[1];
  const source = playoutContext.bufferSources[0];

  let closeSettled = false;
  const close = adapter.close().then(() => {
    closeSettled = true;
  });

  assert.equal(source.stopCount, 1);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 1)), false);
  assert.equal(playoutContext.bufferSources.length, 1);
  assert.equal(playoutContext.closeCount, 1);
  assert.equal(adapter.businessCancelCount(), 0);
  source.end();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  await nextTask();
  assert.equal(closeSettled, false);

  captureClosing.resolve();
  await close;
  assert.equal(closeSettled, true);
  assert.equal(adapter.playoutState(), 'closed');
  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(playoutContext.closeCount, 1);
});

test('close keeps a failed final state when active source cleanup is unknown while releasing capture and contexts', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.startCapture();
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const source = fake.contexts[1].bufferSources[0];
  const lateEnded = source.onended;
  source.stopThrows = true;
  source.disconnectThrows = true;
  const businessCancelCountBefore = adapter.businessCancelCount();

  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );

  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).state, 'failed');
  assert.equal(events.at(-1).reason, 'adapter_closed_source_unknown');
  assert.equal(
    events.some(event => event.state === 'closed'),
    false
  );
  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(fake.contexts[1].closeCount, 1);
  lateEnded();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(adapter.businessCancelCount() - businessCancelCountBefore, 0);
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'ADAPTER_CLOSED'
  );
});

test('playout context close failure keeps admission fenced and final playout state failed', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  fake.contexts[0].closeThrows = true;

  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'ADAPTER_CLOSE_FAILED'
  );

  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).state, 'failed');
  assert.equal(events.at(-1).reason, 'adapter_close_failed');
  assert.equal(
    events.some(event => event.state === 'closed'),
    false
  );
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'ADAPTER_CLOSED'
  );
});

test('capture cleanup failure during close still attempts every resource and leaves playout failed', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.startCapture();
  fake.mediaDevices.stream.track.stopThrows = true;

  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CLEANUP_FAILED'
  );

  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).state, 'failed');
  assert.equal(events.at(-1).reason, 'adapter_close_failed');
  assert.equal(
    events.some(event => event.state === 'closed'),
    false
  );
  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'ADAPTER_CLOSED'
  );
});

test('device changes are diagnostic only and never switch the active track', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onDeviceChange: event => events.push(event) },
  });
  const metadata = await adapter.startCapture();
  fake.mediaDevices.devices = [{ kind: 'audioinput' }, { kind: 'audioinput' }];
  fake.mediaDevices.emit('devicechange');
  await nextTask();
  assert.deepEqual(events, [{ audio_input_count: 2, reason: 'devicechange' }]);
  assert.equal(metadata.track_id, fake.mediaDevices.stream.track.id);
  assert.equal(fake.mediaDevices.constraints.length, 1);
  await adapter.stopCapture();
});

test('losing every enumerated input fails closed only the current active capture', async () => {
  const fake = fakeEnvironment();
  const deviceEvents = [];
  const captureEvents = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onDeviceChange: event => deviceEvents.push(event),
      onCaptureState: event => captureEvents.push(event),
    },
  });
  await adapter.startCapture();

  fake.mediaDevices.devices = [{ kind: 'videoinput' }];
  fake.mediaDevices.emit('devicechange');
  for (let turn = 0; turn < 10 && adapter.captureState() !== 'stopped'; turn += 1) await nextTask();

  assert.equal(adapter.captureState(), 'stopped');
  assert.deepEqual(deviceEvents, [{ audio_input_count: 0, reason: 'devicechange' }]);
  assert.equal(
    captureEvents.some(event => event.state === 'stopping' && event.reason === 'audio_input_unavailable'),
    true
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
});

test('losing every input while permission is pending cancels startup before context allocation', async () => {
  const fake = fakeEnvironment();
  const media = deferred();
  const deviceEvents = [];
  fake.mediaDevices.getUserMediaImpl = () => media.promise;
  fake.mediaDevices.devices = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onDeviceChange: event => deviceEvents.push(event) },
  });

  const start = adapter.startCapture();
  fake.mediaDevices.emit('devicechange');
  await nextTask();
  media.resolve(fake.mediaDevices.stream);
  await assert.rejects(
    () => start,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CANCELLED'
  );

  assert.deepEqual(deviceEvents, [{ audio_input_count: 0, reason: 'devicechange' }]);
  assert.equal(fake.contexts.length, 0);
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
});

test('unknown device enumeration keeps the current capture active', async () => {
  const fake = fakeEnvironment();
  const events = [];
  fake.mediaDevices.enumerateDevicesImpl = async () => {
    throw new Error('browser device query failed');
  };
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onDeviceChange: event => events.push(event) },
  });
  await adapter.startCapture();

  fake.mediaDevices.emit('devicechange');
  await nextTask();

  assert.deepEqual(events, [{ audio_input_count: null, reason: 'enumeration_failed' }]);
  assert.equal(adapter.captureState(), 'active');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 0);
  await adapter.stopCapture();
});

test('a late device enumeration from a stopped generation has zero successor effect', async () => {
  const fake = fakeEnvironment();
  const enumeration = deferred();
  const events = [];
  fake.mediaDevices.enumerateDevicesImpl = () => enumeration.promise;
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onDeviceChange: event => events.push(event) },
  });
  await adapter.startCapture();
  fake.mediaDevices.emit('devicechange');
  await adapter.stopCapture('restart');

  fake.mediaDevices.stream = new FakeStream();
  fake.mediaDevices.enumerateDevicesImpl = async () => fake.mediaDevices.devices;
  await adapter.startCapture();
  enumeration.resolve([]);
  await nextTask();

  assert.deepEqual(events, []);
  assert.equal(adapter.captureState(), 'active');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 0);
  await adapter.stopCapture();
});

test('an exact input loss fails closed even when another microphone remains available', async () => {
  const fake = fakeEnvironment();
  fake.mediaDevices.devices = [
    { kind: 'audioinput', deviceId: 'mic-1' },
    { kind: 'audioinput', deviceId: 'mic-2' },
  ];
  const states = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onCaptureState: state => states.push(state) },
  });
  await adapter.startCapture({ deviceId: 'mic-1' });
  fake.mediaDevices.devices = [{ kind: 'audioinput', deviceId: 'mic-2' }];
  fake.mediaDevices.emit('devicechange');
  for (let turn = 0; turn < 10 && adapter.captureState() !== 'stopped'; turn += 1) await nextTask();
  assert.equal(adapter.captureState(), 'stopped');
  assert.equal(states.some(state => state.reason === 'audio_input_selection_lost'), true);
  assert.equal(fake.mediaDevices.constraints.length, 1);
  await adapter.close();
});

test('an exact input enumeration failure fails closed rather than silently retaining an unverified device', async () => {
  const fake = fakeEnvironment();
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await adapter.startCapture({ deviceId: 'mic-1' });
  fake.mediaDevices.enumerateDevicesImpl = async () => { throw new Error('blocked'); };
  fake.mediaDevices.emit('devicechange');
  for (let turn = 0; turn < 10 && adapter.captureState() !== 'stopped'; turn += 1) await nextTask();
  assert.equal(adapter.captureState(), 'stopped');
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  await adapter.close();
});

test('explicit output selection is feature-detected, applied before ready, and released on close', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true });
  const calls = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    const originalResume = context.resume.bind(context);
    context.setSinkId = async deviceId => { calls.push(`sink:${deviceId}`); };
    context.resume = async () => { calls.push('resume'); await originalResume(); };
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  assert.equal(adapter.capability().output_device_selection, true);
  const metadata = await adapter.unlockPlayout({ deviceId: 'speaker-private' });
  assert.equal(metadata.output_device_selection, true);
  assert.deepEqual(calls, ['sink:speaker-private', 'resume']);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 1);
  await adapter.close();
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
});

test('an explicit output can be deliberately reset to system default without retaining device observation', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true });
  const sinkIds = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.setSinkId = async deviceId => { sinkIds.push(deviceId); };
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  await adapter.unlockPlayout({ deviceId: 'speaker-private' });
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 1);
  const defaultMetadata = await adapter.unlockPlayout();

  assert.deepEqual(sinkIds, ['speaker-private', '']);
  assert.equal(defaultMetadata.output_device_selection, false);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
  await adapter.close();
});

test('partial output-device listener registration is rolled back and never becomes ready', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true });
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.setSinkId = async () => undefined;
    return context;
  };
  const originalAdd = fake.mediaDevices.addEventListener.bind(fake.mediaDevices);
  fake.mediaDevices.addEventListener = (type, listener) => {
    originalAdd(type, listener);
    throw new Error('listener policy failure');
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

  await assert.rejects(
    () => adapter.unlockPlayout({ deviceId: 'speaker-private' }),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_OUTPUT_DEVICE_LISTENER_FAILED'
  );
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
  assert.throws(
    () => adapter.beginPlayout(firstResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_NOT_UNLOCKED'
  );
  assert.equal(fake.contexts[0].bufferSources.length, 0);
  await adapter.close();
});

test('explicit output selection is unavailable without device observation even when setSinkId exists', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true, mediaDevices: null });
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  assert.equal(adapter.capability().output_device_selection, false);
  await assert.rejects(
    () => adapter.unlockPlayout({ deviceId: 'speaker-private' }),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_OUTPUT_SELECTION_UNAVAILABLE'
  );
  assert.equal(fake.contexts.length, 0);
  await adapter.close();
});

test('unsupported or denied explicit output selection never creates a playable route', async () => {
  const unsupported = fakeEnvironment();
  const unsupportedAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: unsupported.environment });
  await assert.rejects(
    () => unsupportedAdapter.unlockPlayout({ deviceId: 'speaker-private' }),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_OUTPUT_SELECTION_UNAVAILABLE'
  );
  assert.equal(unsupported.contexts.length, 0);

  const denied = fakeEnvironment({ outputDeviceSelection: true });
  const originalCreate = denied.environment.createAudioContext;
  denied.environment.createAudioContext = () => {
    const context = originalCreate();
    context.setSinkId = async () => {
      const error = new Error('private browser detail');
      error.name = 'NotAllowedError';
      throw error;
    };
    return context;
  };
  const deniedAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: denied.environment });
  await assert.rejects(
    () => deniedAdapter.unlockPlayout({ deviceId: 'speaker-private' }),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_OUTPUT_PERMISSION_DENIED' && !error.message.includes('private')
  );
  assert.equal(deniedAdapter.playoutState(), 'failed');
  await deniedAdapter.close();
});

test('a failed exact sink switch fences an older ready default route until explicit recovery', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true });
  const originalCreate = fake.environment.createAudioContext;
  const sinkIds = [];
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.setSinkId = async deviceId => {
      sinkIds.push(deviceId);
      if (deviceId === 'speaker-denied') {
        const error = new Error('private browser policy');
        error.name = 'NotAllowedError';
        throw error;
      }
    };
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await adapter.unlockPlayout();
  await assert.rejects(
    () => adapter.unlockPlayout({ deviceId: 'speaker-denied' }),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_OUTPUT_PERMISSION_DENIED'
  );
  assert.equal(adapter.playoutState(), 'failed');
  assert.throws(
    () => adapter.beginPlayout(firstResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_NOT_UNLOCKED'
  );
  await adapter.unlockPlayout();
  assert.equal(adapter.playoutState(), 'ready');
  assert.deepEqual(sinkIds, ['speaker-denied']);
  await adapter.close();
});

test('exact output loss fences the current response with zero business cancel and never switches to an alternate', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true });
  fake.mediaDevices.devices = [
    { kind: 'audiooutput', deviceId: 'speaker-private' },
    { kind: 'audiooutput', deviceId: 'speaker-other' },
  ];
  const sinkIds = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.setSinkId = async deviceId => { sinkIds.push(deviceId); };
    return context;
  };
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout({ deviceId: 'speaker-private' });
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  fake.mediaDevices.devices = [{ kind: 'audiooutput', deviceId: 'speaker-other' }];
  fake.mediaDevices.emit('devicechange');
  await nextTask();
  assert.equal(events.some(event => event.state === 'failed' && event.reason === 'audio_output_selection_lost'), true);
  assert.equal(adapter.businessCancelCount(), 0);
  assert.equal(fake.contexts[0].bufferSources[0].stopCount, 1);
  assert.equal(fake.mediaDevices.constraints.length, 0);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
  assert.throws(
    () => adapter.beginPlayout(secondResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_NOT_UNLOCKED'
  );
  await adapter.unlockPlayout();
  assert.deepEqual(sinkIds, ['speaker-private', '']);
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
  await adapter.close();
});

test('page hide fences a pending setSinkId completion before ready and removes output observation', async () => {
  const fake = fakeEnvironment({ outputDeviceSelection: true });
  const sink = deferred();
  const sinkIds = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.setSinkId = deviceId => {
      sinkIds.push(deviceId);
      return sink.promise;
    };
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  const unlocking = adapter.unlockPlayout({ deviceId: 'speaker-private' });
  fake.document.visibilityState = 'hidden';
  fake.document.emit('visibilitychange');
  sink.resolve();
  await assert.rejects(
    () => unlocking,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PAGE_HIDDEN'
  );
  assert.equal(fake.mediaDevices.listenerCount('devicechange'), 0);
  fake.document.visibilityState = 'visible';
  await adapter.unlockPlayout();
  assert.deepEqual(sinkIds, ['speaker-private', '']);
  await adapter.close();
});

test('playout schedules exact current response and acknowledges only contiguous render completion', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 1)), true);
  const context = fake.contexts[0];
  assert.equal(context.bufferSources.length, 2);
  assert.deepEqual(context.bufferSources.map(source => source.starts), [[11], [11.02]]);
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);

  context.bufferSources[1].end();
  assert.equal(context.bufferSources[1].disconnectCount, 1);
  context.bufferSources[1].end();
  assert.equal(context.bufferSources[1].disconnectCount, 1);
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  context.bufferSources[0].end();
  const completed = events.filter(event => event.reason === 'render_completed');
  assert.equal(completed.length, 1);
  assert.equal(completed[0].through_seq, 1);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('playout unlock exposes the actual PCM rate and reports idle context loss', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.sampleRate = 44100;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });

  const metadata = await adapter.unlockPlayout();
  assert.deepEqual(metadata, {
    encoding: 'pcm_f32',
    sample_rate_hz: 44100,
    channel_count: 1,
    output_device_selection: false,
    physical_heard_ack: false,
  });
  adapter.beginPlayout(firstResponse);
  assert.equal(
    adapter.enqueuePlayout(
      pcmChunk(firstResponse, 0, {
        sample_rate_hz: 44100,
        samples: new Float32Array(882),
      })
    ),
    true
  );
  adapter.stopPlayout(firstResponse, 'test_complete');

  fake.contexts[0].state = 'suspended';
  fake.contexts[0].onstatechange();
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'audio_context_not_running');
  await adapter.close();
});

test('playout unlock rejects an invalid AudioContext rate before playback effects', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.sampleRate = 0;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });

  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'INVALID_AUDIO_CONTEXT_RATE'
  );
  assert.equal(fake.contexts[0].buffers.length, 0);
  assert.equal(fake.contexts[0].bufferSources.length, 0);
  assert.equal(adapter.businessCancelCount(), 0);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'invalid_audio_context_rate');
  await adapter.close();
});

test('wrong-response and invalid playout have zero browser or acknowledgement effect', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 0)), false);
  assert.throws(
    () => adapter.enqueuePlayout(pcmChunk(firstResponse, 0, { channel_count: 2 })),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'INVALID_PLAYOUT_FORMAT'
  );
  assert.throws(
    () => adapter.enqueuePlayout(pcmChunk(firstResponse, 0, { sample_rate_hz: 44100 })),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SAMPLE_RATE_MISMATCH'
  );
  assert.equal(fake.contexts[0].bufferSources.length, 0);
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
});

test('opaque response IDs compare structurally and observer events expose only normalized identity fields', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  const activeResponse = Object.freeze({
    interaction_id: 'scope',
    response_id: 'part\u0000tail',
    response_generation: 0,
    private_extension: 'must-not-propagate',
  });
  const collidingDelimitedKey = Object.freeze({
    interaction_id: 'scope\u0000part',
    response_id: 'tail',
    response_generation: 0,
  });

  await adapter.unlockPlayout();
  adapter.beginPlayout(activeResponse);
  assert.deepEqual(events.at(-1).response, {
    interaction_id: 'scope',
    response_id: 'part\u0000tail',
    response_generation: 0,
  });
  assert.equal(adapter.enqueuePlayout(pcmChunk(collidingDelimitedKey, 0, { channel_count: 2 })), false);
  assert.equal(adapter.stopPlayout(collidingDelimitedKey), false);
  assert.equal(fake.contexts[0].buffers.length, 0);
  assert.equal(fake.contexts[0].bufferSources.length, 0);
  assert.equal(adapter.enqueuePlayout(pcmChunk(activeResponse, 0)), true);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('an invalid replacement response leaves the current browser playback active', async () => {
  const fake = fakeEnvironment();
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const source = fake.contexts[0].bufferSources[0];
  assert.throws(
    () => adapter.beginPlayout(firstResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'RESPONSE_ID_REUSED'
  );
  assert.throws(
    () => adapter.beginPlayout(null),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_BEGIN_FAILED'
  );
  assert.equal(source.stopCount, 0);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 1)), true);
});

test('browser source setup failure clears the accepted chunk without ACK or business cancel', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  fake.contexts[0].bufferSourceThrows = true;
  assert.throws(
    () => adapter.enqueuePlayout(pcmChunk(firstResponse, 0)),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_FAILED'
  );
  assert.equal(adapter.stopPlayout(firstResponse), false);
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('source setup cleanup uncertainty latches the same fail-closed playout admission fault', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  fake.contexts[0].bufferSourceStartThrows = true;
  fake.contexts[0].bufferSourceStopThrows = true;
  fake.contexts[0].bufferSourceDisconnectThrows = true;

  assert.throws(
    () => adapter.enqueuePlayout(pcmChunk(firstResponse, 0)),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN' && error.retriable === false
  );

  const source = fake.contexts[0].bufferSources[0];
  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'source_setup_cleanup_unknown');
  assert.equal(
    events.some(event => event.state === 'stopped'),
    false
  );
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.throws(
    () => adapter.beginPlayout(secondResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 0)), false);
  assert.equal(fake.contexts[0].bufferSources.length, 1);
  assert.equal(adapter.businessCancelCount(), 0);
  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(fake.contexts[0].closeCount, 1);
});

test('exact local stop fences late playout callbacks without widening business cancel', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const source = fake.contexts[0].bufferSources[0];
  assert.equal(adapter.stopPlayout(secondResponse), false);
  assert.equal(source.stopCount, 0);
  assert.equal(adapter.stopPlayout(firstResponse), true);
  assert.equal(source.stopCount, 1);
  source.end();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('exact local stop confirms the fenced tuple, prior cursors, source calls, timing, and zero business cancel', async () => {
  const fake = fakeEnvironment();
  const events = [];
  let now = 100;
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    monotonicNowMs: () => {
      const value = now;
      now += 4;
      return value;
    },
    observer: { onPlayoutState: event => events.push(event) },
  });
  const responseWithPrivateField = Object.freeze({ ...firstResponse, private_extension: 'must-not-propagate' });
  await adapter.unlockPlayout();
  adapter.beginPlayout(responseWithPrivateField);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  adapter.enqueuePlayout(pcmChunk(firstResponse, 1));
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0, { unit_id: 'unit-2' }));
  const context = fake.contexts[0];
  context.bufferSources[0].end();
  const lateEnded = context.bufferSources[1].onended;

  const receipt = adapter.stopPlayoutExact(responseWithPrivateField, 'barge_in_local_only');

  assert.deepEqual(receipt.response, firstResponse);
  assert.equal(receipt.kind, 'browser_audio.local_stop.v1');
  assert.equal(receipt.outcome, 'local_fence_established');
  assert.equal(receipt.local_fence_established, true);
  assert.deepEqual(receipt.confirmed_cursor_before_stop, [
    { unit_id: 'unit-1', contiguous_through_seq: 0 },
    { unit_id: 'unit-2', contiguous_through_seq: null },
  ]);
  assert.deepEqual(receipt.browser_sources, {
    source_count: 2,
    stop_request: { status: 'completed', attempted_count: 2, completed_count: 2, failed_count: 0 },
    disconnect: { status: 'completed', attempted_count: 2, completed_count: 2, failed_count: 0 },
  });
  assert.deepEqual(receipt.timing, {
    status: 'confirmed',
    requested_at_monotonic_ms: 100,
    confirmed_at_monotonic_ms: 104,
    duration_ms: 4,
  });
  assert.equal(receipt.physical_heard, 'unproven');
  assert.equal(receipt.physical_silence, 'unproven');
  assert.equal(receipt.business_cancel_count_before, 0);
  assert.equal(receipt.business_cancel_count_after, 0);
  assert.equal(receipt.business_cancel_count_delta, 0);
  assert.equal(Object.isFrozen(receipt), true);
  lateEnded();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 1);

  const repeated = adapter.stopPlayoutExact(firstResponse);
  assert.equal(repeated.outcome, 'already_stopped');
  assert.equal(repeated.local_fence_established, false);
  assert.equal(repeated.browser_sources.stop_request.status, 'not_attempted');
  assert.equal(context.bufferSources[1].stopCount, 1);
  assert.equal(context.bufferSources[2].stopCount, 1);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('exact local stop distinguishes mismatch, no target, disabled, and closed without audio effects', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  assert.equal(adapter.stopPlayoutExact(firstResponse).outcome, 'no_active_target');
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const source = fake.contexts[0].bufferSources[0];

  const mismatches = [
    { ...firstResponse, interaction_id: 'interaction-wrong' },
    { ...firstResponse, response_id: 'response-wrong' },
    { ...firstResponse, response_generation: 1 },
  ].map(response => adapter.stopPlayoutExact(response));
  assert.deepEqual(
    mismatches.map(receipt => receipt.outcome),
    ['target_mismatch', 'target_mismatch', 'target_mismatch']
  );
  assert.equal(
    mismatches.every(receipt => !receipt.local_fence_established),
    true
  );
  assert.equal(
    mismatches.every(receipt => receipt.browser_sources.source_count === 0),
    true
  );
  assert.equal(source.stopCount, 0);
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);

  const close = adapter.close();
  const closed = adapter.stopPlayoutExact(firstResponse);
  assert.equal(closed.outcome, 'adapter_closed');
  assert.equal(closed.local_fence_established, false);
  assert.equal(source.stopCount, 1);
  await close;

  const disabledFake = fakeEnvironment();
  const disabled = new BrowserAudioIOAdapter({ enabled: false, environment: disabledFake.environment });
  const flagOff = disabled.stopPlayoutExact(firstResponse);
  assert.equal(flagOff.outcome, 'feature_disabled');
  assert.equal(flagOff.local_fence_established, false);
  assert.equal(disabledFake.contexts.length, 0);
  assert.equal(disabledFake.mediaDevices.constraints.length, 0);
  assert.equal(disabled.businessCancelCount(), 0);
});

test('source stop and disconnect failures return stable unknown truth after the local fence', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.startCapture();
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const source = fake.contexts[1].bufferSources[0];
  const lateEnded = source.onended;
  source.stopThrows = true;
  source.disconnectThrows = true;
  const businessCancelCountBefore = adapter.businessCancelCount();

  const receipt = adapter.stopPlayoutExact(firstResponse, 'fault_injection');

  assert.equal(receipt.outcome, 'local_fence_established_source_unknown');
  assert.equal(receipt.local_fence_established, true);
  assert.deepEqual(receipt.browser_sources, {
    source_count: 1,
    stop_request: { status: 'unknown', attempted_count: 1, completed_count: 0, failed_count: 1 },
    disconnect: { status: 'unknown', attempted_count: 1, completed_count: 0, failed_count: 1 },
  });
  assert.equal(receipt.physical_heard, 'unproven');
  assert.equal(receipt.physical_silence, 'unproven');
  assert.equal(receipt.business_cancel_count_delta, 0);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'fault_injection_source_unknown');
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 1)), false);
  assert.throws(
    () => adapter.beginPlayout(secondResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN' && error.retriable === false
  );
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(fake.contexts.length, 2);
  assert.equal(fake.contexts[1].bufferSources.length, 1);
  assert.equal(events.at(-1).reason, 'fault_injection_source_unknown');
  lateEnded();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(adapter.businessCancelCount() - businessCancelCountBefore, 0);
  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN' && error.retriable === false
  );
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'adapter_closed_source_unknown');
  assert.equal(
    events.some(event => event.state === 'closed'),
    false
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(fake.contexts[1].closeCount, 1);

  const replacementFake = fakeEnvironment();
  const replacementAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: replacementFake.environment });
  await replacementAdapter.unlockPlayout();
  replacementAdapter.beginPlayout(firstResponse);
  assert.equal(replacementAdapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(replacementFake.contexts[0].bufferSources.length, 1);
  await replacementAdapter.close();
});

test('a broken monotonic clock cannot prevent exact local fencing or fabricate duration', async () => {
  const fake = fakeEnvironment();
  const clockValues = [10, 9];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    monotonicNowMs: () => clockValues.shift(),
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));

  const receipt = adapter.stopPlayoutExact(firstResponse);

  assert.equal(receipt.local_fence_established, true);
  assert.deepEqual(receipt.timing, {
    status: 'unknown',
    requested_at_monotonic_ms: 10,
    confirmed_at_monotonic_ms: 9,
    duration_ms: null,
  });
  assert.equal(fake.contexts[0].bufferSources[0].stopCount, 1);
});

test('stop observer reentrancy can start one replacement without reviving the fenced response', async () => {
  const fake = fakeEnvironment();
  const events = [];
  let adapter;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onPlayoutState(event) {
        events.push(event);
        if (event.reason === 'observer_replacement') {
          adapter.beginPlayout(secondResponse);
          adapter.enqueuePlayout(pcmChunk(secondResponse, 0));
        }
      },
    },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const firstSource = fake.contexts[0].bufferSources[0];
  const lateEnded = firstSource.onended;

  const receipt = adapter.stopPlayoutExact(firstResponse, 'observer_replacement');

  assert.equal(receipt.outcome, 'local_fence_established');
  assert.equal(fake.contexts[0].bufferSources.length, 2);
  assert.equal(firstSource.stopCount, 1);
  assert.equal(adapter.stopPlayoutExact(firstResponse).outcome, 'target_mismatch');
  assert.equal(fake.contexts[0].bufferSources[1].stopCount, 0);
  lateEnded();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 1)), true);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('response replacement observer reentrancy cannot restore an older playout authority', async () => {
  const fake = fakeEnvironment();
  let adapter;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onPlayoutState(event) {
        if (event.reason === 'response_replaced') adapter.beginPlayout(thirdResponse);
      },
    },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));

  assert.throws(
    () => adapter.beginPlayout(secondResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_REPLACED_DURING_BEGIN'
  );
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 0)), false);
  assert.equal(adapter.enqueuePlayout(pcmChunk(thirdResponse, 0)), true);
  assert.equal(adapter.stopPlayoutExact(firstResponse).outcome, 'target_mismatch');
  assert.equal(adapter.stopPlayoutExact(secondResponse).outcome, 'target_mismatch');
  assert.equal(fake.contexts[0].bufferSources[0].stopCount, 1);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('response replacement fails closed when prior browser source cleanup is unknown', async () => {
  const fake = fakeEnvironment();
  const events = [];
  let observerBeginReason = null;
  let adapter;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onPlayoutState(event) {
        events.push(event);
        if (event.reason !== 'response_replaced_source_unknown') return;
        try {
          adapter.beginPlayout(thirdResponse);
        } catch (error) {
          observerBeginReason = error.reason;
        }
      },
    },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  adapter.enqueuePlayout(pcmChunk(firstResponse, 0));
  const source = fake.contexts[0].bufferSources[0];
  const lateEnded = source.onended;
  source.stopThrows = true;
  source.disconnectThrows = true;
  const businessCancelCountBefore = adapter.businessCancelCount();

  assert.throws(
    () => adapter.beginPlayout(secondResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN' && error.retriable === false
  );
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'response_replaced_source_unknown');
  assert.equal(observerBeginReason, 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN');
  assert.throws(
    () => adapter.beginPlayout(thirdResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 0)), false);
  assert.equal(adapter.enqueuePlayout(pcmChunk(thirdResponse, 0)), false);
  assert.equal(fake.contexts[0].bufferSources.length, 1);
  assert.equal(adapter.stopPlayoutExact(secondResponse).outcome, 'already_stopped');
  lateEnded();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(adapter.businessCancelCount() - businessCancelCountBefore, 0);
  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'adapter_closed_source_unknown');
  assert.equal(fake.contexts[0].closeCount, 1);
});

test('an invalid reentrant begin does not cancel the playout that emitted the observer event', async () => {
  const fake = fakeEnvironment();
  let adapter;
  let rejectedReason = null;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onPlayoutState(event) {
        if (event.reason !== 'response_started') return;
        try {
          adapter.beginPlayout(null);
        } catch (error) {
          rejectedReason = error.reason;
        }
      },
    },
  });
  await adapter.unlockPlayout();

  adapter.beginPlayout(firstResponse);

  assert.equal(rejectedReason, 'PLAYOUT_BEGIN_FAILED');
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  assert.equal(fake.contexts[0].bufferSources.length, 1);
  assert.equal(adapter.businessCancelCount(), 0);
});

test('playout remains visibly locked when AudioContext cannot resume', async () => {
  const fake = fakeEnvironment();
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.resumeLeavesSuspended = true;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_USER_ACTIVATION_REQUIRED'
  );
  assert.throws(
    () => adapter.beginPlayout(firstResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_NOT_UNLOCKED'
  );

  const rejected = fakeEnvironment();
  const rejectedCreate = rejected.environment.createAudioContext;
  rejected.environment.createAudioContext = () => {
    const context = rejectedCreate();
    context.resumeErrorName = 'NotAllowedError';
    return context;
  };
  const rejectedAdapter = new BrowserAudioIOAdapter({ enabled: true, environment: rejected.environment });
  await assert.rejects(
    () => rejectedAdapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'AUDIO_USER_ACTIVATION_REQUIRED'
  );
});

test('page hidden synchronously fences exact playout and visible requires an explicit successor', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  const source = fake.contexts[0].bufferSources[0];
  const lateEnded = source.onended;
  const businessCancelCountBefore = adapter.businessCancelCount();

  fake.document.visibilityState = 'hidden';
  fake.document.emit('visibilitychange');

  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(events.at(-1).state, 'stopped');
  assert.equal(events.at(-1).reason, 'page_hidden');
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 1)), false);
  assert.equal(fake.document.listenerCount('visibilitychange'), 1);
  lateEnded();
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);
  assert.equal(adapter.businessCancelCount() - businessCancelCountBefore, 0);

  const eventCountBeforeVisible = events.length;
  fake.document.visibilityState = 'visible';
  fake.document.emit('visibilitychange');
  assert.equal(events.length, eventCountBeforeVisible);
  adapter.beginPlayout(secondResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 0)), true);
  await adapter.close();
  assert.equal(fake.contexts[0].bufferSources[1].stopCount, 1);
  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
});

test('page hidden fences a pending playout unlock and never auto-resumes it on visible', async () => {
  const fake = fakeEnvironment();
  const resume = deferred();
  const events = [];
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.resumePromise = resume.promise;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  const unlock = adapter.unlockPlayout();
  await nextTask();
  assert.equal(fake.document.listenerCount('visibilitychange'), 1);

  fake.document.visibilityState = 'hidden';
  fake.document.emit('visibilitychange');
  fake.document.visibilityState = 'visible';
  fake.document.emit('visibilitychange');
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_UNLOCK_IN_PROGRESS'
  );
  resume.resolve();

  await assert.rejects(
    () => unlock,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PAGE_HIDDEN'
  );
  assert.equal(
    events.some(event => event.reason === 'playout_unlocked'),
    false
  );
  assert.equal(adapter.businessCancelCount(), 0);
  await adapter.unlockPlayout();
  assert.equal(events.filter(event => event.reason === 'playout_unlocked').length, 1);
  await adapter.close();
  assert.equal(fake.document.listenerCount('visibilitychange'), 0);
});

test('visibility listener partial-add failure is released before browser media or context effects', async () => {
  for (const operation of ['capture', 'playout']) {
    const fake = fakeEnvironment();
    const originalAdd = fake.document.addEventListener.bind(fake.document);
    fake.document.addEventListener = (type, listener) => {
      originalAdd(type, listener);
      throw new Error('visibility listener add failed after registration');
    };
    const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });

    await assert.rejects(
      () => (operation === 'capture' ? adapter.startCapture() : adapter.unlockPlayout()),
      error => error instanceof BrowserAudioIOViolation && error.reason === 'VISIBILITY_LISTENER_FAILED'
    );
    assert.equal(fake.document.listenerCount('visibilitychange'), 0);
    assert.equal(fake.mediaDevices.constraints.length, 0);
    assert.equal(fake.contexts.length, 0);
    assert.equal(adapter.businessCancelCount(), 0);
    await adapter.close();
  }
});

test('close attempts every capture and playout release when visibility listener removal throws', async () => {
  const fake = fakeEnvironment();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  await adapter.startCapture();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  const context = fake.contexts[0];
  const playoutSource = context.bufferSources[0];
  const staleVisibilityListener = [...fake.document.listeners.get('visibilitychange')][0];
  fake.document.removeEventListener = () => {
    throw new Error('visibility listener removal failed');
  };

  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'CAPTURE_CLEANUP_FAILED'
  );
  assert.equal(fake.mediaDevices.stream.track.stopCount, 1);
  assert.equal(fake.worklets[0].port.closeCount, 1);
  assert.equal(context.sourceNode.disconnectCount, 1);
  assert.equal(playoutSource.stopCount, 1);
  assert.equal(playoutSource.disconnectCount, 1);
  assert.equal(context.closeCount, 1);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'adapter_close_failed');
  assert.equal(adapter.businessCancelCount(), 0);

  const stateAfterClose = adapter.playoutState();
  fake.document.visibilityState = 'hidden';
  staleVisibilityListener();
  assert.equal(adapter.playoutState(), stateAfterClose);
  assert.equal(playoutSource.stopCount, 1);
});

test('a pending unlock inherits active source cleanup uncertainty before publishing ready success', async () => {
  const fake = fakeEnvironment();
  const resume = deferred();
  const events = [];
  const adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: { onPlayoutState: event => events.push(event) },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  const context = fake.contexts[0];
  const source = context.bufferSources[0];
  context.state = 'suspended';
  context.resumePromise = resume.promise;
  source.stopThrows = true;
  source.disconnectThrows = true;
  const readyCountBefore = events.filter(event => event.reason === 'playout_unlocked').length;
  const businessCancelCountBefore = adapter.businessCancelCount();

  const unlock = adapter.unlockPlayout();
  await nextTask();
  const receipt = adapter.stopPlayoutExact(firstResponse, 'fault_during_resume');
  assert.equal(receipt.outcome, 'local_fence_established_source_unknown');
  resume.resolve();

  await assert.rejects(
    () => unlock,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(events.filter(event => event.reason === 'playout_unlocked').length, readyCountBefore);
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'fault_during_resume_source_unknown');
  assert.equal(context.bufferSources.length, 1);
  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(adapter.businessCancelCount() - businessCancelCountBefore, 0);
});

test('a playout-ready observer cleanup fault rejects unlock and latches every later admission closed', async () => {
  const fake = fakeEnvironment();
  const events = [];
  let adapter;
  let triggerCleanup = false;
  let cleanupReceipt = null;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onPlayoutState(event) {
        events.push(event);
        if (!triggerCleanup || event.reason !== 'playout_unlocked') return;
        triggerCleanup = false;
        cleanupReceipt = adapter.stopPlayoutExact(firstResponse, 'observer_cleanup_fault');
      },
    },
  });
  await adapter.unlockPlayout();
  adapter.beginPlayout(firstResponse);
  assert.equal(adapter.enqueuePlayout(pcmChunk(firstResponse, 0)), true);
  const source = fake.contexts[0].bufferSources[0];
  source.stopThrows = true;
  source.disconnectThrows = true;
  const businessCancelCountBefore = adapter.businessCancelCount();
  triggerCleanup = true;

  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(cleanupReceipt?.outcome, 'local_fence_established_source_unknown');
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'observer_cleanup_fault_source_unknown');
  assert.equal(fake.contexts[0].bufferSources.length, 1);
  assert.throws(
    () => adapter.beginPlayout(secondResponse),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(adapter.enqueuePlayout(pcmChunk(secondResponse, 0)), false);
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  await assert.rejects(
    () => adapter.close(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_SOURCE_CLEANUP_UNKNOWN'
  );
  assert.equal(adapter.playoutState(), 'failed');
  assert.equal(events.at(-1).reason, 'adapter_closed_source_unknown');
  assert.equal(source.stopCount, 1);
  assert.equal(source.disconnectCount, 1);
  assert.equal(adapter.businessCancelCount() - businessCancelCountBefore, 0);
});

test('close fences a pending playout unlock and remains terminal', async () => {
  const fake = fakeEnvironment();
  const resume = deferred();
  const originalCreate = fake.environment.createAudioContext;
  fake.environment.createAudioContext = () => {
    const context = originalCreate();
    context.resumePromise = resume.promise;
    return context;
  };
  const adapter = new BrowserAudioIOAdapter({ enabled: true, environment: fake.environment });
  const unlock = adapter.unlockPlayout();
  await nextTask();
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_UNLOCK_IN_PROGRESS'
  );
  await adapter.close();
  assert.equal(fake.contexts[0].state, 'closed');
  resume.resolve();
  await assert.rejects(
    () => unlock,
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_CANCELLED'
  );
  assert.equal(adapter.playoutState(), 'closed');
  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'ADAPTER_CLOSED'
  );
  await assert.rejects(
    () => adapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'ADAPTER_CLOSED'
  );
});

test('a playout-ready observer that closes the adapter fences the unlock result', async () => {
  const fake = fakeEnvironment();
  let adapter;
  let closePromise = null;
  adapter = new BrowserAudioIOAdapter({
    enabled: true,
    environment: fake.environment,
    observer: {
      onPlayoutState(event) {
        if (event.reason === 'playout_unlocked') closePromise = adapter.close();
      },
    },
  });

  await assert.rejects(
    () => adapter.unlockPlayout(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'PLAYOUT_CANCELLED'
  );
  assert.notEqual(closePromise, null);
  await closePromise;
  assert.equal(fake.contexts[0].closeCount, 1);
  assert.equal(adapter.playoutState(), 'closed');
});
