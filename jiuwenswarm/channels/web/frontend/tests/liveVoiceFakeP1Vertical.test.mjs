import assert from 'node:assert/strict';
import test from 'node:test';

import { AudioPortViolation } from '../node_modules/.cache/live-voice-fake-p1/features/live-voice/formal/audioPort.js';
import { FakeP1Vertical, FakeP1VerticalViolation } from '../node_modules/.cache/live-voice-fake-p1/features/live-voice/formal/fakeP1Vertical.js';

const first = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 });
const second = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-2', response_generation: 1 });

function input(overrides = {}) {
  return {
    state: 'committed',
    response: first,
    display_text: 'WHO update',
    spoken_text: 'World Health Organization update',
    audio: new Uint8Array([1, 2, 3]),
    correlation_id: 'correlation-1',
    observed_at: '2026-08-04T08:00:00Z',
    ...overrides,
  };
}

test('partial and uncommitted text have zero audio and telemetry effects', () => {
  const vertical = new FakeP1Vertical();
  for (const state of ['partial', 'uncommitted']) {
    const result = vertical.run(input({ state }));
    assert.equal(result.committed, false);
    assert.equal(result.available, true);
    assert.equal(result.queued_audio, 0);
    assert.equal(result.route, null);
  }
  assert.deepEqual(vertical.pending(first), []);
  assert.deepEqual(vertical.routes(), []);
  assert.equal(vertical.businessCancelCount(), 0);
});

test('committed text queues deterministic audio with a truthful substitute route', () => {
  const vertical = new FakeP1Vertical();
  const result = vertical.run(input());
  assert.equal(result.committed, true);
  assert.equal(result.available, true);
  assert.equal(result.queued_audio, 1);
  assert.equal(result.route.implementation_class, 'demo_substitute');
  assert.equal(result.route.safe_reason, 'DETERMINISTIC_FAKE_ONLY');
  assert.equal(result.route.capability_provider, 'deterministic-speech-fake');
  assert.equal(vertical.pending(first).length, 1);
  assert.equal(vertical.routes().length, 1);
  assert.equal(vertical.businessCancelCount(), 0);
});

test('a replacement response removes stale queued audio', () => {
  const vertical = new FakeP1Vertical();
  vertical.run(input());
  vertical.run(input({ response: second, correlation_id: 'correlation-2' }));
  assert.deepEqual(vertical.pending(first), []);
  assert.equal(vertical.pending(second).length, 1);
  assert.equal(vertical.routes().length, 2);
});

test('an unavailable track is explicit and never queues audio', () => {
  const vertical = new FakeP1Vertical({ enabled: false });
  const result = vertical.run(input());
  assert.equal(result.committed, true);
  assert.equal(result.available, false);
  assert.equal(result.queued_audio, 0);
  assert.equal(result.route.implementation_class, 'unsupported');
  assert.equal(result.route.safe_reason, 'TRACK_UNAVAILABLE');
  assert.equal(result.route.capability_provider, null);
  assert.deepEqual(vertical.pending(first), []);
});

test('invalid input fails before replacing current audio or recording a route', () => {
  const vertical = new FakeP1Vertical();
  vertical.run(input());
  assert.throws(
    () => vertical.run(input({ response: second, audio: new Uint8Array(), correlation_id: 'correlation-2' })),
    error => error instanceof AudioPortViolation && error.reason === 'INVALID_AUDIO_CHUNK'
  );
  assert.equal(vertical.pending(first).length, 1);
  assert.deepEqual(vertical.pending(second), []);
  assert.equal(vertical.routes().length, 1);
});

test('invalid commit state rejects without effects', () => {
  const vertical = new FakeP1Vertical();
  assert.throws(
    () => vertical.run(input({ state: 'final' })),
    error => error instanceof FakeP1VerticalViolation && error.reason === 'INVALID_COMMIT_STATE'
  );
  assert.deepEqual(vertical.routes(), []);
  assert.deepEqual(vertical.pending(first), []);
});
