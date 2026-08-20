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

function fakePlatform({ sampleRate = 48_000, sourceStartError = false, contextError = false } = {}) {
  const state = { sourceStarts: [], tracksStopped: 0, contextClosed: false, getUserMediaCalls: 0, copied: [] };
  const track = {
    id: 'fixture-track',
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
  const context = {
    sampleRate,
    currentTime: 0,
    destination: {},
    state: 'running',
    onstatechange: null,
    async resume() {},
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
      return { stream };
    },
  };
  return {
    state,
    stream,
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

test('fixed audio owner has one stream claim and close is idempotent', async () => {
  const platform = fakePlatform();
  const owner = createFixedAudioCaptureOwner(fixture(), platform);
  await owner.environment.mediaDevices.getUserMedia({ audio: true });
  await assert.rejects(
    () => owner.environment.mediaDevices.getUserMedia({ audio: true }),
    error => error?.message === 'FIXED_AUDIO_STREAM_ALREADY_CLAIMED',
  );
  await owner.close();
  await owner.close();
  assert.equal(platform.state.tracksStopped, 1);
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
