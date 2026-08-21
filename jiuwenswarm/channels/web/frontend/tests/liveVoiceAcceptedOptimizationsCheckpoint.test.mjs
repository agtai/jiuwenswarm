import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CHECKPOINT_B_BATCH_BOUND,
  CHECKPOINT_CONTROLLED_TARGETS,
  CHECKPOINT_POINTS,
  CHECKPOINT_POPULATIONS,
  CHECKPOINT_SEGMENTS,
  CHECKPOINT_TRUTH_CLASSES,
  CHECKPOINT_WORKLOADS,
  buildCheckpointReport,
  compareCheckpointReports,
  runCheckpointAttempt,
} from '../node_modules/.cache/live-voice-accepted-checkpoint/acceptedOptimizationsCheckpoint.js';

class ManualClock {
  #time;
  #adjust;

  constructor(time = 100, adjust = delayMs => delayMs) {
    this.#time = time;
    this.#adjust = adjust;
  }

  nowMs() {
    return this.#time;
  }

  async waitMs(delayMs) {
    this.#time += this.#adjust(delayMs);
  }
}

function attemptConfig(overrides = {}) {
  return {
    population: 'B',
    workload_id: 'W1',
    attempt_index: 0,
    source_commit: 'a'.repeat(40),
    runner_fingerprint: 'b'.repeat(64),
    fixture_fingerprint: 'c'.repeat(64),
    timing_fingerprint: 'd'.repeat(64),
    optimization_mode: {
      p2_notification_batch_size: 16,
      tts_successor_ack_overlap: true,
    },
    ...overrides,
  };
}

function controlledDependencies(clock) {
  return {
    clock,
    async deliverPresentation({ workload }) {
      await clock.waitMs(85);
      return {
        notification_rpc_count: 1,
        notification_batch_count: 1,
        ordered_barriers: [...workload.tool_barriers],
      };
    },
    async playResponse({ mark, workload }) {
      mark('downlink_opened');
      mark('first_frame_received');
      mark('first_source_scheduled');
      await clock.waitMs(workload.playout_duration_ms);
      mark('playout_completed');
      mark('confirmed_ack_and_next_turn_ready');
      return {
        successor_ack_confirmed: true,
        next_turn_ready: true,
      };
    },
  };
}

function reportConfig(population, overrides = {}) {
  return {
    run_id: `checkpoint-${population.toLowerCase()}`,
    population,
    source_commit: population === 'B' ? 'e'.repeat(40) : 'a'.repeat(40),
    source_clean: true,
    runner_fingerprint: 'b'.repeat(64),
    fixture_fingerprint: 'c'.repeat(64),
    timing_fingerprint: 'd'.repeat(64),
    samples_per_workload: 5,
    optimization_mode:
      population === 'B'
        ? { p2_notification_batch_size: 16, tts_successor_ack_overlap: true }
        : { p2_notification_batch_size: 1, tts_successor_ack_overlap: false },
    ...overrides,
  };
}

function literalCompletedAttempt(population, workloadId, attemptIndex, roundTotalMs) {
  const timestamps = [100, 110, 120, 130, 140, 150, 160, 165, 170, 180, 100 + roundTotalMs];
  return {
    population,
    workload_id: workloadId,
    attempt_index: attemptIndex,
    outcome: 'completed',
    reason: null,
    events: CHECKPOINT_POINTS.map((point, index) => ({ point, monotonic_ms: timestamps[index], truth_class: 'measured' })),
    segments: {
      round_total: { duration_ms: 999999, truth_class: 'measured' },
    },
    controlled_targets: {},
    p2: { notification_rpc_count: 1, notification_batch_count: 1, ordered_barriers: [] },
    p1: { successor_ack_confirmed: true, next_turn_ready: true },
  };
}

test('closed checkpoint catalog preserves reviewed workloads and event graph', () => {
  assert.deepEqual(CHECKPOINT_TRUTH_CLASSES, ['measured', 'controlled', 'derived', 'estimated', 'out_of_scope']);
  assert.deepEqual(CHECKPOINT_POPULATIONS, ['A1', 'B', 'A2']);
  assert.deepEqual(CHECKPOINT_POINTS, [
    'speech_end',
    'stt_final',
    'admission_accepted',
    'model_complete_and_notifications_enqueued',
    'presentation_final_consumed',
    'tts_ready_and_successor_capture_requested',
    'downlink_opened',
    'first_frame_received',
    'first_source_scheduled',
    'playout_completed',
    'confirmed_ack_and_next_turn_ready',
  ]);
  assert.deepEqual(CHECKPOINT_SEGMENTS, {
    stt_settlement: ['speech_end', 'stt_final'],
    admission: ['stt_final', 'admission_accepted'],
    agent_model: ['admission_accepted', 'model_complete_and_notifications_enqueued'],
    p2_final_delivery: ['model_complete_and_notifications_enqueued', 'presentation_final_consumed'],
    tts_generation: ['presentation_final_consumed', 'tts_ready_and_successor_capture_requested'],
    tts_ready_to_downlink: ['tts_ready_and_successor_capture_requested', 'downlink_opened'],
    downlink_to_first_source: ['downlink_opened', 'first_source_scheduled'],
    first_source_to_playout: ['first_source_scheduled', 'playout_completed'],
    playout_to_confirmed_ack: ['playout_completed', 'confirmed_ack_and_next_turn_ready'],
    round_total: ['speech_end', 'confirmed_ack_and_next_turn_ready'],
  });
  assert.deepEqual(CHECKPOINT_WORKLOADS.W1, {
    id: 'W1',
    notification_count: 10,
    successor_ack_delay_ms: 250,
    playout_duration_ms: 3000,
    tool_barriers: [],
  });
  assert.deepEqual(CHECKPOINT_WORKLOADS.W2, {
    id: 'W2',
    notification_count: 50,
    successor_ack_delay_ms: 750,
    playout_duration_ms: 6000,
    tool_barriers: [],
  });
  assert.deepEqual(CHECKPOINT_WORKLOADS.W3, {
    id: 'W3',
    notification_count: 100,
    successor_ack_delay_ms: 750,
    playout_duration_ms: 4000,
    tool_barriers: [40, 41],
  });
  assert.deepEqual(CHECKPOINT_CONTROLLED_TARGETS, {
    stt_settlement_ms: 400,
    admission_ms: 500,
    agent_model_ms: 2000,
    tool_interval_ms: 1000,
    tts_generation_ms: 1000,
    p2_rpc_ms: 85,
  });
  assert.equal(CHECKPOINT_B_BATCH_BOUND, 16);
});

test('attempt records ordered observations and computes round total directly from D0 and D10', async () => {
  const clock = new ManualClock();
  const attempt = await runCheckpointAttempt(attemptConfig(), controlledDependencies(clock));

  assert.equal(attempt.outcome, 'completed');
  assert.equal(attempt.reason, null);
  assert.deepEqual(
    attempt.events.map(event => [event.point, event.monotonic_ms, event.truth_class]),
    [
      ['speech_end', 100, 'measured'],
      ['stt_final', 500, 'measured'],
      ['admission_accepted', 1000, 'measured'],
      ['model_complete_and_notifications_enqueued', 3000, 'measured'],
      ['presentation_final_consumed', 3085, 'measured'],
      ['tts_ready_and_successor_capture_requested', 4085, 'measured'],
      ['downlink_opened', 4085, 'measured'],
      ['first_frame_received', 4085, 'measured'],
      ['first_source_scheduled', 4085, 'measured'],
      ['playout_completed', 7085, 'measured'],
      ['confirmed_ack_and_next_turn_ready', 7085, 'measured'],
    ],
  );
  assert.equal(attempt.segments.stt_settlement.duration_ms, 400);
  assert.equal(attempt.segments.p2_final_delivery.duration_ms, 85);
  assert.equal(attempt.segments.round_total.duration_ms, 6985);
  assert.equal(attempt.segments.round_total.truth_class, 'measured');
  assert.deepEqual(attempt.p2, {
    notification_rpc_count: 1,
    notification_batch_count: 1,
    ordered_barriers: [],
  });
});

test('controlled wait that completes early invalidates the attempt', async () => {
  const clock = new ManualClock(0, delayMs => (delayMs === 400 ? 399 : delayMs));
  const attempt = await runCheckpointAttempt(attemptConfig(), controlledDependencies(clock));

  assert.equal(attempt.outcome, 'invalid');
  assert.equal(attempt.reason, 'CONTROLLED_WAIT_EARLY');
  assert.deepEqual(
    attempt.events.map(event => event.point),
    ['speech_end'],
  );
});

test('controlled wait beyond max of 25ms or five percent invalidates the attempt', async () => {
  const clock = new ManualClock(0, delayMs => (delayMs === 400 ? 426 : delayMs));
  const attempt = await runCheckpointAttempt(attemptConfig(), controlledDependencies(clock));

  assert.equal(attempt.outcome, 'invalid');
  assert.equal(attempt.reason, 'CONTROLLED_WAIT_LATE');
  assert.deepEqual(
    attempt.events.map(event => event.point),
    ['speech_end'],
  );
});

test('report uses direct attempt endpoints, nearest-rank percentiles, and missing denominators', () => {
  const attempts = [100, 200, 300, 400, 500].map((value, index) => literalCompletedAttempt('A1', 'W1', index, value));
  attempts.push({
    ...literalCompletedAttempt('A1', 'W1', 5, 600),
    outcome: 'unknown',
    reason: 'CHECKPOINT_DEPENDENCY_FAILED',
    events: [],
  });
  const report = buildCheckpointReport(reportConfig('A1', { samples_per_workload: 6 }), attempts);

  assert.equal(report.schema_version, 'live-voice.accepted-optimizations-checkpoint.v0');
  assert.equal(report.lane, 'deterministic_owner_checkpoint');
  assert.deepEqual(report.summaries.W1.outcomes, {
    intended: 6,
    attempts: 6,
    completed: 5,
    invalid: 0,
    failed: 0,
    unknown: 1,
    missing: 0,
  });
  assert.deepEqual(report.summaries.W1.segments.round_total, {
    truth_class: 'measured',
    samples_ms: [100, 200, 300, 400, 500],
    p50_ms: 300,
    p95_ms: 500,
  });
  assert.deepEqual(report.summaries.W2.outcomes, {
    intended: 6,
    attempts: 0,
    completed: 0,
    invalid: 0,
    failed: 0,
    unknown: 0,
    missing: 6,
  });
  assert.equal(report.summaries.W2.segments.round_total.p50_ms, null);
});

test('A1/B/A2 comparison emits absolute milliseconds before percentages and baseline drift', () => {
  const build = (population, roundValues) =>
    buildCheckpointReport(
      reportConfig(population),
      CHECKPOINT_POINTS.length > 0
        ? Object.keys(CHECKPOINT_WORKLOADS).flatMap(workloadId =>
            roundValues.map((value, index) => literalCompletedAttempt(population, workloadId, index, value)),
          )
        : [],
    );
  const comparison = compareCheckpointReports(
    build('A1', [200, 200, 200, 200, 200]),
    build('B', [170, 170, 170, 170, 170]),
    build('A2', [210, 210, 210, 210, 210]),
  );
  const row = comparison.workloads.W1.segments.round_total;

  assert.deepEqual(row, {
    truth_class: 'derived',
    a1_p50_ms: 200,
    b_p50_ms: 170,
    a2_p50_ms: 210,
    b_minus_a1_ms: -30,
    b_minus_a2_ms: -40,
    b_minus_a1_percent: -15,
    b_minus_a2_percent: -19.047619,
    baseline_drift_ms: 10,
    baseline_drift_percent: 5,
  });
  assert.equal(comparison.decision, 'accepted');
});

test('comparison fails closed when runner fingerprints or A source differ', () => {
  const attempts = [100, 200, 300, 400, 500].map((value, index) => literalCompletedAttempt('A1', 'W1', index, value));
  const a1 = buildCheckpointReport(reportConfig('A1'), attempts);
  const b = buildCheckpointReport(
    reportConfig('B'),
    attempts.map(attempt => ({ ...attempt, population: 'B' })),
  );
  const mismatchedA2 = buildCheckpointReport(
    reportConfig('A2', { source_commit: 'f'.repeat(40) }),
    attempts.map(attempt => ({ ...attempt, population: 'A2' })),
  );
  assert.throws(() => compareCheckpointReports(a1, b, mismatchedA2), /CHECKPOINT_SOURCE_MISMATCH/);
  const runnerMismatch = buildCheckpointReport(
    reportConfig('A2', { runner_fingerprint: 'f'.repeat(64) }),
    attempts.map(attempt => ({ ...attempt, population: 'A2' })),
  );
  assert.throws(() => compareCheckpointReports(a1, b, runnerMismatch), /CHECKPOINT_FINGERPRINT_MISMATCH/);
});
