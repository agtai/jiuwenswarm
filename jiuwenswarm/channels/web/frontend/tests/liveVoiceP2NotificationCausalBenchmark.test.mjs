import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  parseP2NotificationBenchmarkArgs,
  runP2NotificationCausalBenchmark,
  writeP2NotificationCausalReport,
} from '../scripts/liveVoiceP2NotificationCausalBenchmark.mjs';

test('real P2 owner exposes bounded notification cost with zero forbidden effects', async () => {
  let monotonicMs = 0;
  const report = await runP2NotificationCausalBenchmark({
    runId: 'p2-a1-test',
    gitCommit: 'a'.repeat(40),
    notificationCounts: [2, 4],
    sampleCount: 2,
    delayMs: 85,
    notificationBatchSize: 16,
    now: () => monotonicMs,
    sleep: async delayMs => {
      monotonicMs += delayMs;
    },
  });

  assert.deepEqual(Object.keys(report).sort(), [
    'batch_size',
    'delay_ms',
    'forbidden_effects',
    'git_commit',
    'notification_counts',
    'rows',
    'run_id',
    'sample_count',
    'schema_version',
    'source_state',
  ]);
  assert.equal(report.schema_version, 'live-voice.p2-notification-causal-report.v0');
  assert.equal(report.batch_size, 16);
  assert.deepEqual(report.rows, [
    {
      notification_count: 2,
      attempts: 2,
      successful: 2,
      notification_rpc_count: 2,
      expected_serial_ms: 85,
      samples_ms: [85, 85],
      p50_ms: 85,
      p95_ms: 85,
    },
    {
      notification_count: 4,
      attempts: 2,
      successful: 2,
      notification_rpc_count: 2,
      expected_serial_ms: 85,
      samples_ms: [85, 85],
      p50_ms: 85,
      p95_ms: 85,
    },
  ]);
  assert.deepEqual(report.forbidden_effects, {
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
});

test('closed benchmark input rejects unsafe identifiers and numeric boundaries before owner effects', async () => {
  const base = {
    runId: 'p2-a1-test',
    gitCommit: 'a'.repeat(40),
    notificationCounts: [10, 50, 100],
    sampleCount: 1,
    delayMs: 0,
    notificationBatchSize: 16,
    now: () => 0,
    sleep: async () => undefined,
  };
  const invalid = [
    { ...base, runId: '../private' },
    { ...base, gitCommit: 'A'.repeat(40) },
    { ...base, notificationCounts: [0] },
    { ...base, notificationCounts: [257] },
    { ...base, notificationCounts: [10, 10] },
    { ...base, sampleCount: 0 },
    { ...base, sampleCount: 31 },
    { ...base, delayMs: -1 },
    { ...base, delayMs: 1_001 },
    { ...base, notificationBatchSize: 1 },
    { ...base, notificationBatchSize: 17 },
  ];

  for (const input of invalid) {
    await assert.rejects(runP2NotificationCausalBenchmark(input), /P2_BENCHMARK_INPUT_INVALID/);
  }
});

test('CLI parser is closed and report writer refuses overwrite', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'p2-causal-benchmark-'));
  const output = path.join(root, 'report.json');
  const parsed = parseP2NotificationBenchmarkArgs([
    '--output',
    output,
    '--git-commit',
    'b'.repeat(40),
    '--run-id',
    'p2-a1-cli',
    '--samples',
    '5',
    '--delay-ms',
    '85',
    '--batch-size',
    '16',
  ]);

  assert.deepEqual(parsed, {
    output,
    gitCommit: 'b'.repeat(40),
    runId: 'p2-a1-cli',
    sampleCount: 5,
    delayMs: 85,
    notificationBatchSize: 16,
  });
  assert.throws(() => parseP2NotificationBenchmarkArgs(['--output', output, '--output', output]), /P2_BENCHMARK_ARGUMENT_INVALID/);
  assert.throws(() => parseP2NotificationBenchmarkArgs(['--unknown', 'value']), /P2_BENCHMARK_ARGUMENT_INVALID/);

  const report = Object.freeze({ schema_version: 'live-voice.p2-notification-causal-report.v0' });
  await writeP2NotificationCausalReport(output, report);
  await assert.rejects(writeP2NotificationCausalReport(output, report), /P2_BENCHMARK_OUTPUT_EXISTS/);
  assert.equal(JSON.parse(await fs.readFile(output, 'utf8')).schema_version, report.schema_version);
});
