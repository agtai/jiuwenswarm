import assert from 'node:assert/strict';
import test from 'node:test';

import { createFixedAudioCaptureOwner } from '../node_modules/.cache/live-voice-fixed-audio-benchmark/fixedAudioCaptureEnvironment.mjs';

function pcm16MonoWav({ sampleRate = 48_000, samples = [0, 100, -100, 0] } = {}) {
  const dataBytes = samples.length * 2;
  const bytes = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(bytes);
  const write = (offset, value) => [...value].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)));
  write(0, 'RIFF');
  view.setUint32(4, 36 + dataBytes, true);
  write(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, 'data');
  view.setUint32(40, dataBytes, true);
  samples.forEach((sample, index) => view.setInt16(44 + index * 2, sample, true));
  return bytes;
}

function fakePlatform({ sampleRate = 48_000, sourceStartError = false, contextError = false, contextState = 'running', resumeStaysSuspended = false } = {}) {
  const state = { sourceStarts: [], tracksStopped: 0, contextClosed: false, getUserMediaCalls: 0, copied: [], destinations: 0, resumeCalls: 0 };
  const streams = [];
  const createStream = () => {
    const track = {
      id: `fixture-track-${streams.length + 1}`,
      kind: 'audio',
      stop() {
        state.tracksStopped += 1;
      },
      getSettings() {
        return { sampleRate, channelCount: 1 };
      },
      addEventListener() {},
      removeEventListener() {},
    };
    const stream = { getAudioTracks: () => [track], getTracks: () => [track] };
    streams.push(stream);
    return stream;
  };
  const stream = createStream();
  const context = {
    sampleRate,
    currentTime: 0,
    destination: {},
    state: contextState,
    onstatechange: null,
    async resume() {
      state.resumeCalls += 1;
      if (!resumeStaysSuspended) this.state = 'running';
    },
    async close() {
      state.contextClosed = true;
    },
    createMediaStreamSource() {
      return { connect() {}, disconnect() {} };
    },
    createBuffer(_channels, length) {
      return {
        copyToChannel(values) {
          state.copied.push([...values]);
          assert.equal(values.length, length);
        },
      };
    },
    createBufferSource() {
      return {
        buffer: null,
        onended: null,
        connect() {},
        disconnect() {},
        start(when) {
          state.sourceStarts.push(when);
          if (sourceStartError) throw new Error('private source failure');
        },
        stop() {},
      };
    },
    createMediaStreamDestination() {
      state.destinations += 1;
      return { stream: state.destinations === 1 ? stream : createStream() };
    },
  };
  return {
    state,
    stream,
    context,
    createAudioContext() {
      if (contextError) throw new Error('private context failure');
      return context;
    },
  };
}

function fixture(overrides = {}) {
  return { input_case_id: 'dialogue-paris-en-v1', wav_bytes: pcm16MonoWav(), expected_sample_rate_hz: 48_000, start_delay_ms: 1_000, ...overrides };
}

test('fixed audio owner starts one memory-only stream after the declared lead', async () => {
  const platform = fakePlatform();
  const owner = createFixedAudioCaptureOwner(fixture(), platform);
  const stream = await owner.environment.mediaDevices.getUserMedia({ audio: true });
  assert.equal(stream, platform.stream);
  assert.deepEqual(platform.state.sourceStarts, [1]);
  assert.equal(platform.state.getUserMediaCalls, 0);
  await owner.close();
  assert.equal(platform.state.contextClosed, true);
  assert.equal(platform.state.tracksStopped, 1);
});

test('fixed audio owner resumes its private fixture context and requires running truth', async () => {
  const resumable = fakePlatform({ contextState: 'suspended' });
  const owner = createFixedAudioCaptureOwner(fixture(), resumable);
  await owner.environment.mediaDevices.getUserMedia({ audio: true });
  assert.equal(resumable.state.resumeCalls, 1);
  assert.deepEqual(resumable.state.sourceStarts, [1]);
  await owner.close();

  const blocked = fakePlatform({
    contextState: 'suspended',
    resumeStaysSuspended: true,
  });
  const blockedOwner = createFixedAudioCaptureOwner(fixture(), blocked);
  await assert.rejects(
    () => blockedOwner.environment.mediaDevices.getUserMedia({ audio: true }),
    error => error?.message === 'FIXED_AUDIO_CONTEXT_NOT_RUNNING',
  );
  assert.equal(blocked.state.resumeCalls, 1);
  assert.deepEqual(blocked.state.sourceStarts, []);
  assert.equal(blocked.state.contextClosed, true);
});

test('fixed audio owner snapshots fixture scalars before returning retained closures', async () => {
  const platform = fakePlatform();
  const mutableFixture = fixture();
  const owner = createFixedAudioCaptureOwner(mutableFixture, platform);

  mutableFixture.input_case_id = 'foreign-case';
  mutableFixture.start_delay_ms = 5_000;
  mutableFixture.expected_sample_rate_hz = 44_100;
  mutableFixture.wav_bytes = new ArrayBuffer(0);

  await owner.environment.mediaDevices.getUserMedia({ audio: true });

  assert.equal(owner.input_case_id, 'dialogue-paris-en-v1');
  assert.deepEqual(platform.state.sourceStarts, [1]);
  await owner.close();
});

test('fixed audio owner rejects invalid WAV fixture inputs without exposing bytes', () => {
  const platform = fakePlatform();
  for (const invalid of [
    fixture({ wav_bytes: new Uint8Array([1, 2, 3]).buffer }),
    fixture({ wav_bytes: pcm16MonoWav({ sampleRate: 44_100 }) }),
    fixture({ wav_bytes: new ArrayBuffer(4 * 1024 * 1024 + 1) }),
    fixture({ start_delay_ms: 249 }),
    fixture({ start_delay_ms: 5_001 }),
  ]) {
    assert.throws(
      () => createFixedAudioCaptureOwner(invalid, platform),
      error => {
        assert.match(String(error?.message), /^FIXED_AUDIO_/);
        assert.doesNotMatch(String(error?.message), /dialogue-paris|1,2,3/);
        return true;
      },
    );
  }
});

test('fixed audio owner plays the fixture once and permits one silent successor stream', async () => {
  const platform = fakePlatform();
  const owner = createFixedAudioCaptureOwner(fixture(), platform);
  const primary = await owner.environment.mediaDevices.getUserMedia({ audio: true });
  platform.context.state = 'suspended';
  const successor = await owner.environment.mediaDevices.getUserMedia({ audio: true });
  assert.notEqual(successor, primary);
  assert.equal(platform.state.resumeCalls, 1);
  assert.deepEqual(platform.state.sourceStarts, [1]);
  await assert.rejects(
    () => owner.environment.mediaDevices.getUserMedia({ audio: true }),
    error => error?.message === 'FIXED_AUDIO_STREAM_ALREADY_CLAIMED',
  );
  await owner.close();
  await owner.close();
  assert.equal(platform.state.tracksStopped, 2);
});

test('fixed audio owner closes before a stream claim and contains source failures', async () => {
  const beforeStart = fakePlatform();
  const owner = createFixedAudioCaptureOwner(fixture(), beforeStart);
  await owner.close();
  await assert.rejects(
    () => owner.environment.mediaDevices.getUserMedia({ audio: true }),
    error => error?.message === 'FIXED_AUDIO_OWNER_CLOSED',
  );
  assert.equal(beforeStart.state.contextClosed, true);

  const failing = fakePlatform({ sourceStartError: true });
  const failedOwner = createFixedAudioCaptureOwner(fixture(), failing);
  await assert.rejects(
    () => failedOwner.environment.mediaDevices.getUserMedia({ audio: true }),
    error => error?.message === 'FIXED_AUDIO_SOURCE_START_FAILED',
  );
  assert.equal(failing.state.contextClosed, true);
  assert.equal(failing.state.tracksStopped, 1);
});
