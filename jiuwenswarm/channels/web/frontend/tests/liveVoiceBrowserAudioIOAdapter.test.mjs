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

  async getUserMedia(constraints) {
    this.constraints.push(constraints);
    return this.getUserMediaImpl(constraints);
  }

  async enumerateDevices() {
    return this.devices;
  }
}

class FakeNode {
  connected = [];
  disconnectCount = 0;

  connect(destination) {
    this.connected.push(destination);
    return destination;
  }

  disconnect() {
    this.disconnectCount += 1;
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

  start(when = 0) {
    this.starts.push(when);
  }

  stop() {
    this.stopCount += 1;
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
    this.bufferSources.push(source);
    return source;
  }
}

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
    createAudioContext() {
      const context = new FakeAudioContext();
      contexts.push(context);
      return context;
    },
    createAudioWorkletNode(_context, _name, _options) {
      const worklet = new FakeWorkletNode();
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

test('disabled and insecure capture reject before media, context, listeners, or timers', async () => {
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
  await assert.rejects(
    () => missingDocumentAdapter.startCapture(),
    error => error instanceof BrowserAudioIOViolation && error.reason === 'DOCUMENT_VISIBILITY_UNAVAILABLE'
  );
  assert.equal(missingDocument.mediaDevices.constraints.length, 0);
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
  assert.equal(events.filter(event => event.reason === 'render_completed').length, 0);

  context.bufferSources[1].end();
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
