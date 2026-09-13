import assert from 'node:assert/strict';
import { before, test } from 'node:test';

import { compareP2NotificationABReports, runP2NotificationABBenchmark } from '../scripts/liveVoiceP2NotificationABBenchmark.mjs';

const commit = 'a'.repeat(40);
let offReport;
let onReport;

async function runWithVirtualClock(mode) {
  let monotonicMs = 0;
  return runP2NotificationABBenchmark({
    runId: `p2-ab-${mode}-test`,
    gitCommit: commit,
    mode,
    sampleCount: 5,
    delayMs: 85,
    now: () => monotonicMs,
    sleep: async delayMs => {
      monotonicMs += delayMs;
    },
  });
}

before(async () => {
  offReport = await runWithVirtualClock('off');
  onReport = await runWithVirtualClock('on');
});

test('P2 bounded pull OFF records the one-notification-per-RPC causal baseline', context => {
  assert.equal(offReport.feature_mode, 'off');
  assert.equal(offReport.effective_batch_size, 1);
  assert.deepEqual(
    offReport.rows.map(row => [row.notification_count, row.notification_rpc_count, row.rpc_count_per_attempt, row.p50_ms, row.p95_ms]),
    [
      [10, 50, 10, 850, 850],
      [50, 250, 50, 4_250, 4_250],
      [100, 500, 100, 8_500, 8_500],
    ],
  );
  assert.deepEqual(offReport.forbidden_effects, {
    submit: 0,
    presentation_ack: 0,
    barge_in: 0,
    p3: 0,
    agent: 0,
    tool: 0,
    task: 0,
    history: 0,
    audio: 0,
  });
  context.diagnostic(`P2_AB_OFF ${JSON.stringify(offReport)}`);
});

test('P2 bounded pull ON records and compares the bounded-RPC causal result', context => {
  assert.equal(onReport.feature_mode, 'on');
  assert.equal(onReport.effective_batch_size, 16);
  assert.deepEqual(
    onReport.rows.map(row => [row.notification_count, row.notification_rpc_count, row.rpc_count_per_attempt, row.p50_ms, row.p95_ms]),
    [
      [10, 5, 1, 85, 85],
      [50, 20, 4, 340, 340],
      [100, 35, 7, 595, 595],
    ],
  );
  const comparison = compareP2NotificationABReports(offReport, onReport);
  assert.deepEqual(
    comparison.map(row => [row.notification_count, row.off_rpc_count_per_attempt, row.on_rpc_count_per_attempt, row.p50_reduction_percent]),
    [
      [10, 10, 1, 90],
      [50, 50, 4, 92],
      [100, 100, 7, 93],
    ],
  );
  assert.deepEqual(onReport.forbidden_effects, offReport.forbidden_effects);
  context.diagnostic(`P2_AB_ON ${JSON.stringify(onReport)}`);
  context.diagnostic(`P2_AB_COMPARISON ${JSON.stringify(comparison)}`);
});
