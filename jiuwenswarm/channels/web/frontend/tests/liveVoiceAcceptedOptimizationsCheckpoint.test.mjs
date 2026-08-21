import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
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
  parseCheckpointComparison,
  parseCheckpointReport,
  runCheckpointAttempt,
} from '../node_modules/.cache/live-voice-accepted-checkpoint/acceptedOptimizationsCheckpoint.js';
import {
  assertCheckpointOutputOutsideGit,
  comparePrivateCheckpointReports,
  parseAcceptedCheckpointArgs,
  readPrivateCheckpointReport,
  renderCheckpointComparisonMarkdown,
  runAcceptedCheckpointPopulation,
  runControlledOwnerAttempt,
  writePrivateCheckpointReport,
} from '../scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs';

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
    run_id: 'checkpoint-b',
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
  const optimizedRpcCounts = { W1: 1, W2: 4, W3: 8 };
  const notificationRpcCount = population === 'B' ? optimizedRpcCounts[workloadId] : CHECKPOINT_WORKLOADS[workloadId].notification_count;
  const d0 = 100;
  const d1 = d0 + 400;
  const d2 = d1 + 500;
  const d3 = d2 + 2000;
  const d4 = d3 + notificationRpcCount * 85;
  const d5 = d4 + 1000;
  const d6 = d5 + (population === 'B' ? 0 : CHECKPOINT_WORKLOADS[workloadId].successor_ack_delay_ms);
  const d8 = d6;
  const d9 = d8 + CHECKPOINT_WORKLOADS[workloadId].playout_duration_ms;
  const d10 = d9 + roundTotalMs;
  const timestamps = [d0, d1, d2, d3, d4, d5, d6, d6, d8, d9, d10];
  const eventTimes = Object.fromEntries(CHECKPOINT_POINTS.map((point, index) => [point, timestamps[index]]));
  const runId = `checkpoint-${population.toLowerCase()}`;
  const identitySuffix = `${runId}-${population}-${workloadId}-${attemptIndex}`;
  const batchTails =
    population !== 'B'
      ? Array.from({ length: CHECKPOINT_WORKLOADS[workloadId].notification_count }, (_, index) => index)
      : workloadId === 'W1'
        ? [9]
        : workloadId === 'W2'
          ? [15, 31, 47, 49]
          : [15, 31, 40, 41, 57, 73, 89, 99];
  return {
    run_id: runId,
    population,
    workload_id: workloadId,
    attempt_index: attemptIndex,
    source_commit: population === 'B' ? 'e'.repeat(40) : 'a'.repeat(40),
    runner_fingerprint: 'b'.repeat(64),
    fixture_fingerprint: 'c'.repeat(64),
    timing_fingerprint: 'd'.repeat(64),
    optimization_mode:
      population === 'B'
        ? { p2_notification_batch_size: 16, tts_successor_ack_overlap: true }
        : { p2_notification_batch_size: 1, tts_successor_ack_overlap: false },
    outcome: 'completed',
    reason: null,
    events: CHECKPOINT_POINTS.map((point, index) => ({ point, monotonic_ms: timestamps[index], truth_class: 'measured' })),
    segments: Object.fromEntries(
      Object.entries(CHECKPOINT_SEGMENTS).map(([name, [start, end]]) => [name, { duration_ms: eventTimes[end] - eventTimes[start], truth_class: 'measured' }]),
    ),
    controlled_targets: Object.fromEntries(
      [
        ...Object.entries(CHECKPOINT_CONTROLLED_TARGETS),
        ['successor_ack_ms', CHECKPOINT_WORKLOADS[workloadId].successor_ack_delay_ms],
        ['playout_ms', CHECKPOINT_WORKLOADS[workloadId].playout_duration_ms],
      ].map(([name, value_ms]) => [name, { value_ms, truth_class: 'controlled' }]),
    ),
    controlled_observations: {
      stt_settlement: { value_ms: 400, truth_class: 'measured' },
      admission: { value_ms: 500, truth_class: 'measured' },
      agent_model: { value_ms: 2000, truth_class: 'measured' },
      tool_interval: { value_ms: workloadId === 'W3' ? 1000 : null, truth_class: 'measured' },
      tts_generation: { value_ms: 1000, truth_class: 'measured' },
    },
    p2: {
      truth_class: 'measured',
      notification_rpc_count: notificationRpcCount,
      notification_batch_count: notificationRpcCount,
      ordered_barriers: [...CHECKPOINT_WORKLOADS[workloadId].tool_barriers],
      batches: batchTails.map((tail, index) => ({
        rpc_index: index + 1,
        start_publish_seq: index === 0 ? 0 : batchTails[index - 1] + 1,
        end_publish_seq: tail,
        count: tail - (index === 0 ? 0 : batchTails[index - 1] + 1) + 1,
        duration_ms: 85,
      })),
      response: {
        session_id: `checkpoint-session-${identitySuffix}`,
        correlation_id: `checkpoint-correlation-${identitySuffix}`,
        interaction_id: `checkpoint-interaction-${identitySuffix}`,
        activation_id: `checkpoint-activation-${identitySuffix}`,
        response_id: `checkpoint-response-${workloadId}`,
        response_generation: 0,
        unit_id: `checkpoint-final-${workloadId}`,
      },
    },
    p1: {
      successor_ack_confirmed: true,
      next_turn_ready: true,
      downlink_opened_before_successor_ack: population === 'B',
      product_owner: 'ProductP1VoiceRouteOwner',
      successor_ack_observed: {
        value_ms: CHECKPOINT_WORKLOADS[workloadId].successor_ack_delay_ms,
        truth_class: 'measured',
      },
      interaction_id: `checkpoint-interaction-${identitySuffix}`,
      response_id: `checkpoint-response-${workloadId}`,
      unit_id: `checkpoint-final-${workloadId}`,
    },
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
    recognized_prompt: 'In two short sentences, please introduce Paris.',
    notification_count: 10,
    successor_ack_delay_ms: 250,
    playout_duration_ms: 3000,
    tool_barriers: [],
  });
  assert.deepEqual(CHECKPOINT_WORKLOADS.W2, {
    id: 'W2',
    recognized_prompt: 'Plan a three-day itinerary for Paris with morning, afternoon, and evening activities.',
    notification_count: 50,
    successor_ack_delay_ms: 750,
    playout_duration_ms: 6000,
    tool_barriers: [],
  });
  assert.deepEqual(CHECKPOINT_WORKLOADS.W3, {
    id: 'W3',
    recognized_prompt: 'What is the weather today in Paris, and should I carry an umbrella?',
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
    segments: {},
    p2: null,
    p1: null,
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
    samples_ms: [8100, 8200, 8300, 8400, 8500],
    p50_ms: 8300,
    p95_ms: 8500,
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
    result: 'IMPROVED',
    measurements: {
      a1: { truth_class: 'measured', p50_ms: 8200, p95_ms: 8200 },
      b: { truth_class: 'measured', p50_ms: 7155, p95_ms: 7155 },
      a2: { truth_class: 'measured', p50_ms: 8210, p95_ms: 8210 },
    },
    deltas: {
      truth_class: 'derived',
      b_minus_a1_p50_ms: -1045,
      b_minus_a2_p50_ms: -1055,
      b_minus_a1_p95_ms: -1045,
      b_minus_a2_p95_ms: -1055,
      b_minus_a1_p50_percent: -12.743902,
      b_minus_a2_p50_percent: -12.850183,
      baseline_drift_p50_ms: 10,
      baseline_drift_p50_percent: 0.121951,
    },
  });
  assert.equal(comparison.decision, 'IMPROVED');
});

test('comparison fails closed when runner fingerprints or A source differ', () => {
  const attempts = [100, 200, 300, 400, 500].map((value, index) => literalCompletedAttempt('A1', 'W1', index, value));
  const a1 = buildCheckpointReport(reportConfig('A1'), attempts);
  const b = buildCheckpointReport(
    reportConfig('B'),
    [100, 200, 300, 400, 500].map((value, index) => literalCompletedAttempt('B', 'W1', index, value)),
  );
  const mismatchedA2 = buildCheckpointReport(
    reportConfig('A2', { source_commit: 'f'.repeat(40) }),
    [100, 200, 300, 400, 500].map((value, index) => ({ ...literalCompletedAttempt('A2', 'W1', index, value), source_commit: 'f'.repeat(40) })),
  );
  assert.throws(() => compareCheckpointReports(a1, b, mismatchedA2), /CHECKPOINT_SOURCE_MISMATCH/);
  const runnerMismatch = buildCheckpointReport(
    reportConfig('A2', { runner_fingerprint: 'f'.repeat(64) }),
    [100, 200, 300, 400, 500].map((value, index) => ({ ...literalCompletedAttempt('A2', 'W1', index, value), runner_fingerprint: 'f'.repeat(64) })),
  );
  assert.throws(() => compareCheckpointReports(a1, b, runnerMismatch), /CHECKPOINT_FINGERPRINT_MISMATCH/);
});

test('W1 owner composition uses one bounded P2 pull and overlaps successor ACK on optimized source', async () => {
  const startedAt = performance.now();
  const result = await runControlledOwnerAttempt(attemptConfig({ workload_id: 'W1' }));
  const wallElapsedMs = performance.now() - startedAt;

  assert.equal(result.outcome, 'completed');
  assert.equal(result.segments.p2_final_delivery.duration_ms, 85);
  assert.equal(result.segments.round_total.duration_ms, 6985);
  assert.ok(wallElapsedMs < 150);
  assert.deepEqual(result.p2, {
    truth_class: 'measured',
    notification_rpc_count: 1,
    notification_batch_count: 1,
    ordered_barriers: [],
    batches: [{ rpc_index: 1, start_publish_seq: 0, end_publish_seq: 9, count: 10, duration_ms: 85 }],
    response: {
      session_id: 'checkpoint-session-checkpoint-b-B-W1-0',
      correlation_id: 'checkpoint-correlation-checkpoint-b-B-W1-0',
      interaction_id: 'checkpoint-interaction-checkpoint-b-B-W1-0',
      activation_id: 'checkpoint-activation-checkpoint-b-B-W1-0',
      response_id: 'checkpoint-response-W1',
      response_generation: 0,
      unit_id: 'checkpoint-final-W1',
    },
  });
  assert.deepEqual(result.p1, {
    successor_ack_confirmed: true,
    next_turn_ready: true,
    downlink_opened_before_successor_ack: true,
    product_owner: 'ProductP1VoiceRouteOwner',
    successor_ack_observed: { value_ms: 250, truth_class: 'measured' },
    interaction_id: 'checkpoint-interaction-checkpoint-b-B-W1-0',
    response_id: 'checkpoint-response-W1',
    unit_id: 'checkpoint-final-W1',
  });
});

test('W2 and W3 preserve bounded RPC counts and exact Tool barrier tails', async () => {
  const w2 = await runControlledOwnerAttempt(attemptConfig({ workload_id: 'W2' }));
  const w3 = await runControlledOwnerAttempt(attemptConfig({ workload_id: 'W3' }));

  assert.equal(w2.outcome, 'completed');
  assert.equal(w2.p2.notification_rpc_count, 4);
  assert.equal(w2.segments.p2_final_delivery.duration_ms, 340);
  assert.deepEqual(w2.p2.ordered_barriers, []);
  assert.equal(w3.outcome, 'completed');
  assert.equal(w3.p2.notification_rpc_count, 8);
  assert.equal(w3.segments.p2_final_delivery.duration_ms, 680);
  assert.deepEqual(w3.p2.ordered_barriers, [40, 41]);
  assert.deepEqual(
    w3.p2.batches.map(batch => batch.end_publish_seq),
    [15, 31, 40, 41, 57, 73, 89, 99],
  );
});

test('malformed P2 evidence fails closed before P1 and still closes its real owner once', async () => {
  let mutated = 0;
  let closes = 0;
  const result = await runControlledOwnerAttempt(attemptConfig({ workload_id: 'W1' }), {
    p2NotificationMutator(notification) {
      mutated += 1;
      return mutated === 1 ? { ...notification, publish_seq: 99 } : notification;
    },
    onP2Close() {
      closes += 1;
    },
  });

  assert.equal(result.outcome, 'unknown');
  assert.equal(result.reason, 'CHECKPOINT_DEPENDENCY_FAILED');
  assert.equal(mutated, 10);
  assert.equal(closes, 1);
  assert.equal(result.p1, null);
  assert.deepEqual(
    result.events.map(event => event.point),
    ['speech_end', 'stt_final', 'admission_accepted', 'model_complete_and_notifications_enqueued'],
  );
});

test('duplicate final nested Agent error and wrong Tool tail stay fail-closed without P1 effects', async () => {
  const mutations = [
    notification =>
      notification.publish_seq === 0
        ? {
            ...notification,
            agent_event: { ...notification.agent_event, event_type: 'chat.final' },
            presentation_unit: {
              surface: 'text',
              unit_id: 'forged-final',
              seq: 0,
              source_start_utf8: 0,
              source_end_utf8: 1,
              content_ref: `sha256:${'0'.repeat(64)}`,
            },
          }
        : notification,
    notification =>
      notification.publish_seq === 0 ? { ...notification, agent_event: { ...notification.agent_event, error_reason: 'PRIVATE_SENTINEL' } } : notification,
    notification => (notification.publish_seq === 40 ? { ...notification, publish_seq: 42 } : notification),
  ];
  for (let index = 0; index < mutations.length; index += 1) {
    const result = await runControlledOwnerAttempt(attemptConfig({ workload_id: index === 2 ? 'W3' : 'W1', attempt_index: index + 10 }), {
      p2NotificationMutator: mutations[index],
    });
    assert.equal(result.outcome, 'unknown');
    assert.equal(result.reason, 'CHECKPOINT_DEPENDENCY_FAILED');
    assert.equal(result.p1, null);
  }
});

test('checkpoint CLI parser is closed and never echoes an unknown private value', () => {
  const output = '/tmp/accepted-checkpoint-report.json';
  assert.deepEqual(
    parseAcceptedCheckpointArgs([
      'run',
      '--population',
      'B',
      '--mode',
      'optimized',
      '--samples',
      '5',
      '--git-commit',
      'a'.repeat(40),
      '--run-id',
      'accepted-checkpoint-b',
      '--output',
      output,
    ]),
    {
      command: 'run',
      population: 'B',
      mode: 'optimized',
      samples: 5,
      git_commit: 'a'.repeat(40),
      run_id: 'accepted-checkpoint-b',
      output,
    },
  );
  assert.deepEqual(parseAcceptedCheckpointArgs(['render-markdown', '--comparison', '/tmp/comparison.json', '--output', '/tmp/checkpoint.md']), {
    command: 'render-markdown',
    comparison: '/tmp/comparison.json',
    output: '/tmp/checkpoint.md',
  });
  const sentinel = 'PRIVATE_SENTINEL_VALUE';
  assert.throws(
    () => parseAcceptedCheckpointArgs(['run', '--unknown', sentinel]),
    error => error instanceof Error && error.message === 'CHECKPOINT_ARGUMENT_INVALID' && !error.message.includes(sentinel),
  );
  assert.throws(
    () =>
      parseAcceptedCheckpointArgs([
        'run',
        '--population',
        'B',
        '--mode',
        'optimized',
        '--samples',
        '1',
        '--git-commit',
        'a'.repeat(40),
        '--run-id',
        'bad-sample-count',
        '--output',
        output,
      ]),
    /CHECKPOINT_ARGUMENT_INVALID/,
  );
  assert.deepEqual(
    parseAcceptedCheckpointArgs([
      'compare-a-b-a',
      '--baseline-before',
      '/tmp/a1.json',
      '--candidate',
      '/tmp/b.json',
      '--baseline-after',
      '/tmp/a2.json',
      '--output',
      '/tmp/comparison.json',
    ]),
    {
      command: 'compare-a-b-a',
      baseline_before: '/tmp/a1.json',
      candidate: '/tmp/b.json',
      baseline_after: '/tmp/a2.json',
      output: '/tmp/comparison.json',
    },
  );
  assert.throws(() => assertCheckpointOutputOutsideGit(path.join(process.cwd(), 'private-report.json'), process.cwd()), /CHECKPOINT_OUTPUT_INSIDE_GIT/);
  assert.equal(assertCheckpointOutputOutsideGit('/tmp/private-report.json', process.cwd()), '/tmp/private-report.json');
});

test('checkpoint CLI help is side-effect free and executable without source checks', () => {
  const result = spawnSync(process.execPath, ['scripts/liveVoiceAcceptedOptimizationsCheckpoint.mjs', '--help'], {
    cwd: process.cwd(),
    encoding: 'utf8',
  });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /^Usage: liveVoiceAcceptedOptimizationsCheckpoint/m);
  assert.equal(result.stderr, '');
});

test('private report writer installs one mode-0600 deep-reparsed report without partial files', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'accepted-checkpoint-'));
  const output = path.join(root, 'report.json');
  const attempts = Object.keys(CHECKPOINT_WORKLOADS).map((workloadId, index) => literalCompletedAttempt('B', workloadId, 0, 200 + index * 10));
  const report = buildCheckpointReport(reportConfig('B', { samples_per_workload: 1 }), attempts);

  await writePrivateCheckpointReport(output, report);
  assert.equal((await fs.stat(output)).mode & 0o077, 0);
  assert.deepEqual(await readPrivateCheckpointReport(output), report);
  await assert.rejects(writePrivateCheckpointReport(output, report), /CHECKPOINT_OUTPUT_EXISTS/);
  assert.deepEqual(await readPrivateCheckpointReport(output), report);
  await fs.chmod(output, 0o400);
  await assert.rejects(readPrivateCheckpointReport(output), /CHECKPOINT_REPORT_INVALID/);
  await fs.chmod(output, 0o600);
  const symlink = path.join(root, 'report-link.json');
  await fs.symlink(output, symlink);
  await assert.rejects(readPrivateCheckpointReport(symlink), /CHECKPOINT_REPORT_INVALID/);
  await fs.unlink(symlink);

  const cyclicOutput = path.join(root, 'cyclic.json');
  const cyclic = {};
  cyclic.self = cyclic;
  await assert.rejects(writePrivateCheckpointReport(cyclicOutput, cyclic), /CHECKPOINT_REPORT_INVALID/);
  await assert.rejects(fs.stat(cyclicOutput), error => error?.code === 'ENOENT');
  const oversized = path.join(root, 'oversized.json');
  await fs.writeFile(oversized, Buffer.alloc(8 * 1024 * 1024 + 1));
  await fs.chmod(oversized, 0o600);
  await assert.rejects(readPrivateCheckpointReport(oversized), /CHECKPOINT_REPORT_INVALID/);
  await fs.unlink(oversized);
  const repositoryLink = path.join(root, 'repository-link');
  await fs.symlink(process.cwd(), repositoryLink);
  assert.throws(() => assertCheckpointOutputOutsideGit(path.join(repositoryLink, 'ignored', 'private.json'), process.cwd()), /CHECKPOINT_OUTPUT_INSIDE_GIT/);
  await fs.unlink(repositoryLink);
  assert.deepEqual((await fs.readdir(root)).sort(), ['report.json']);
});

test('one-sample optimized population runs all real-owner workloads with stable fingerprints and zero forbidden effects', async () => {
  const report = await runAcceptedCheckpointPopulation({
    population: 'B',
    mode: 'optimized',
    samples: 1,
    git_commit: 'a'.repeat(40),
    run_id: 'checkpoint-b-smoke',
  });

  assert.equal(report.attempts.length, 3);
  assert.ok(report.attempts.every(attempt => attempt.outcome === 'completed'));
  assert.deepEqual(
    report.attempts.map(attempt => attempt.p2.notification_rpc_count),
    [1, 4, 8],
  );
  assert.match(report.runner_fingerprint, /^[0-9a-f]{64}$/);
  assert.match(report.fixture_fingerprint, /^[0-9a-f]{64}$/);
  assert.match(report.timing_fingerprint, /^[0-9a-f]{64}$/);
  assert.deepEqual(report.forbidden_effects, {
    agent: 0,
    tool: 0,
    task: 0,
    history: 0,
    network: 0,
    provider: 0,
    microphone: 0,
  });
});

test('private A1/B/A2 compare writes absolute deltas and renders milliseconds before percentages', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'accepted-checkpoint-compare-'));
  const make = population => {
    const value = population === 'B' ? 170 : population === 'A2' ? 210 : 200;
    return buildCheckpointReport(
      reportConfig(population),
      Object.keys(CHECKPOINT_WORKLOADS).flatMap(workloadId =>
        Array.from({ length: 5 }, (_, index) => literalCompletedAttempt(population, workloadId, index, value)),
      ),
    );
  };
  const a1Path = path.join(root, 'a1.json');
  const bPath = path.join(root, 'b.json');
  const a2Path = path.join(root, 'a2.json');
  const comparisonPath = path.join(root, 'comparison.json');
  await writePrivateCheckpointReport(a1Path, make('A1'));
  await writePrivateCheckpointReport(bPath, make('B'));
  await writePrivateCheckpointReport(a2Path, make('A2'));

  const comparison = await comparePrivateCheckpointReports({
    baseline_before: a1Path,
    candidate: bPath,
    baseline_after: a2Path,
    output: comparisonPath,
  });
  const markdown = renderCheckpointComparisonMarkdown(comparison);

  assert.equal((await fs.stat(comparisonPath)).mode & 0o077, 0);
  assert.equal(comparison.decision, 'IMPROVED');
  assert.match(markdown, /\| W1 \| round_total \| 8200\.000\/8200\.000 \| 7155\.000\/7155\.000 \| 8210\.000\/8210\.000 \| -1045\.000 \| -1055\.000 \|/);
  assert.ok(markdown.indexOf('B−A1 p50 ms') < markdown.indexOf('B−A1 %'));
  assert.match(markdown, /## Exact inputs/);
  assert.match(markdown, /## Measured B residual and share of total/);
  assert.match(markdown, /## Proven removable headroom/);
  assert.match(markdown, /## Estimated future headroom/);
  assert.match(markdown, /## Controlled fixture and out-of-scope boundaries/);
  for (const mutate of [
    value => {
      value.inputs.a1.report_sha256 = null;
    },
    value => {
      value.inputs.a1.optimization_mode.private_transcript = 'PRIVATE_SENTINEL';
    },
    value => {
      value.inputs.a1.optimization_mode = { p2_notification_batch_size: 16, tts_successor_ack_overlap: true };
    },
    value => {
      value.inputs.a2.source_commit = 'f'.repeat(40);
    },
  ]) {
    const corrupted = JSON.parse(JSON.stringify(comparison));
    mutate(corrupted);
    assert.throws(() => parseCheckpointComparison(corrupted), /CHECKPOINT_COMPARISON_INVALID/);
  }
});

test('comparison remains inconclusive when one attempted candidate round is unknown', () => {
  const make = population =>
    buildCheckpointReport(
      reportConfig(population),
      Object.keys(CHECKPOINT_WORKLOADS).flatMap(workloadId =>
        Array.from({ length: 5 }, (_, index) => literalCompletedAttempt(population, workloadId, index, population === 'B' ? 170 : 200)),
      ),
    );
  const a1 = make('A1');
  const bAttempts = make('B').attempts.map((attempt, index) =>
    index === 0 ? { ...attempt, outcome: 'unknown', reason: 'CHECKPOINT_DEPENDENCY_FAILED', events: [], segments: {}, p2: null, p1: null } : attempt,
  );
  const b = buildCheckpointReport(reportConfig('B'), bAttempts);
  const a2 = make('A2');

  assert.equal(compareCheckpointReports(a1, b, a2).decision, 'INCONCLUSIVE');
});

test('deep report parser rejects private or contradictory nested attempt fields', () => {
  const report = buildCheckpointReport(
    reportConfig('B', { samples_per_workload: 1 }),
    Object.keys(CHECKPOINT_WORKLOADS).map((workloadId, index) => literalCompletedAttempt('B', workloadId, 0, 200 + index * 10)),
  );
  const corrupted = JSON.parse(JSON.stringify(report));
  corrupted.attempts[0].private_transcript = 'PRIVATE_SENTINEL';
  corrupted.attempts[0].p2.notification_rpc_count = 999;
  corrupted.attempts[0].p2.ordered_barriers = [999];
  corrupted.attempts[0].p1.successor_ack_confirmed = false;

  assert.throws(() => parseCheckpointReport(corrupted), /CHECKPOINT_REPORT_INVALID/);
  for (const mutate of [
    value => {
      value.attempts[0].optimization_mode.private_value = 'PRIVATE_SENTINEL';
    },
    value => {
      value.attempts[0].p2.batches[0].private_payload = 'PRIVATE_SENTINEL';
    },
    value => {
      value.attempts[0].p2.response.private_transcript = 'PRIVATE_SENTINEL';
    },
    value => {
      value.attempts[0].controlled_observations.stt_settlement.value_ms = 10;
      value.attempts[0].events[1].monotonic_ms = value.attempts[0].events[0].monotonic_ms + 10;
      value.attempts[0].segments.stt_settlement.duration_ms = 10;
    },
  ]) {
    const nested = JSON.parse(JSON.stringify(report));
    mutate(nested);
    assert.throws(() => parseCheckpointReport(nested), /CHECKPOINT_REPORT_INVALID/);
  }
});

test('comparison parser rejects empty accepted evidence and straddled baselines are inconclusive', () => {
  assert.throws(
    () =>
      parseCheckpointComparison({
        schema_version: 'live-voice.accepted-optimizations-checkpoint-comparison.v0',
        decision: 'IMPROVED',
        populations_complete: true,
        workloads: { W1: { segments: {} }, W2: { segments: {} }, W3: { segments: {} } },
      }),
    /CHECKPOINT_COMPARISON_INVALID/,
  );
  const make = (population, value) =>
    buildCheckpointReport(
      reportConfig(population),
      Object.keys(CHECKPOINT_WORKLOADS).flatMap(workloadId =>
        Array.from({ length: 5 }, (_, index) => literalCompletedAttempt(population, workloadId, index, value)),
      ),
    );
  assert.equal(compareCheckpointReports(make('A1', 200), make('B', 205), make('A2', 210)).decision, 'INCONCLUSIVE');
});
