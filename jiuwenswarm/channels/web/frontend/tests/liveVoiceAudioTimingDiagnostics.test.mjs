import assert from 'node:assert/strict';
import test from 'node:test';
import { CaptureTimingDiagnostics, firstSignalOffset, outputTimingFacts } from '../node_modules/.cache/live-voice-audio-diagnostics/audioTimingDiagnostics.mjs';

test('input timing retains numeric energy tail through silence, separates captures and never stores PCM', () => {
  const timing = new CaptureTimingDiagnostics();
  const samples = new Float32Array(20).fill(0.1, 0, 10);
  const frame = {
    capture: { capture_id: 'c1', capture_generation: 1 },
    seq: 3,
    sample_cursor: 60,
    context_time_s: 2,
    format: { sample_rate_hz: 1000 },
    samples,
  };
  timing.observe(frame, { currentTime: 2.03, sampleRate: 1000, state: 'running' }, 5000);
  samples.fill(0);
  timing.observe({ ...frame, seq: 4, sample_cursor: 80, context_time_s: 2.02 }, { currentTime: 2.05, sampleRate: 1000, state: 'running' }, 5020);
  const facts = timing.snapshot('c1');
  assert.equal(facts.input_tail_sample_end, 70);
  assert.equal(facts.input_tail_frame_seq, 3);
  assert.ok(Math.abs(facts.input_tail_estimate_ms - 4980) < 0.001);
  assert.equal(facts.acoustic_measured, false);
  assert.equal(
    Object.values(facts).some(value => typeof value === 'object' && value !== null),
    false,
  );
  assert.deepEqual(timing.snapshot('foreign'), {});
  timing.observe({ ...frame, capture: { capture_id: 'c2', capture_generation: 2 } }, { currentTime: 3, sampleRate: 1000, state: 'suspended' }, 6000);
  assert.deepEqual(timing.snapshot('c1'), {});
  assert.equal(timing.snapshot('c2').input_tail_estimate_ms, null);
});

test('leading silence and resume offset are retained, silence cannot count as first signal', () => {
  const samples = new Float32Array(100);
  assert.equal(firstSignalOffset(samples, 1000), null);
  samples.fill(0.1, 30, 50);
  assert.equal(firstSignalOffset(samples, 1000), 0.03);
  assert.equal(firstSignalOffset(samples, 1000, 0.04), 0.04);
  assert.equal(firstSignalOffset(samples, 1000, 0.05), null);
  assert.equal(firstSignalOffset(samples, 0), null);
});

test('device timestamp mapping excludes polling delay and never double-adds latency estimates', () => {
  const context = {
    currentTime: 8,
    sampleRate: 48000,
    state: 'running',
    baseLatency: 0.01,
    outputLatency: 0.08,
    getOutputTimestamp: () => ({ contextTime: 7.9, performanceTime: 9900 }),
  };
  const facts = outputTimingFacts(context, 8.02, 10050);
  assert.ok(Math.abs(facts.output_estimate_ms - 10020) < 0.001);
  assert.equal(facts.output_time_method, 'get_output_timestamp_estimate');
  assert.equal(facts.base_latency_ms, 10);
  assert.equal(facts.output_latency_ms, 80);
  assert.equal(facts.acoustic_measured, false);
  for (const stamp of [
    { contextTime: 0, performanceTime: 0 },
    { contextTime: 7.9, performanceTime: 10051 },
    { contextTime: 7.9, performanceTime: 1000 },
    { contextTime: 99, performanceTime: 9900 },
  ]) {
    assert.equal(outputTimingFacts({ ...context, getOutputTimestamp: () => stamp }, 8.02, 10050).output_estimate_ms, null);
  }
  assert.equal(
    outputTimingFacts(
      {
        ...context,
        getOutputTimestamp: () => {
          throw Error('private');
        },
      },
      8.02,
      10050,
    ).output_estimate_ms,
    null,
  );
  assert.equal(outputTimingFacts({ ...context, state: 'closed' }, 8.02, 10050).output_estimate_ms, null);
});
