import assert from 'node:assert/strict';
import { mkdtemp, readFile, stat, symlink } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  runEotSttSettlementBenchmark,
} from '../node_modules/.cache/live-voice-eot-stt-benchmark/eotSttSettlementBenchmark.js';
import {
  assertEotSttCleanSource,
  parseEotSttSettlementBenchmarkArgs,
  validateEotSttPythonExecutable,
  writeEotSttSettlementBenchmarkReport,
} from '../scripts/liveVoiceEotSttSettlementBenchmark.mjs';

const FIXTURES = Object.freeze([
  Object.freeze({ id: 'local-fast-provider-fast', localSettlementMs: 50, providerFinalMs: 50 }),
  Object.freeze({ id: 'local-slow-provider-fast', localSettlementMs: 500, providerFinalMs: 50 }),
  Object.freeze({ id: 'local-fast-provider-slow', localSettlementMs: 50, providerFinalMs: 500 }),
  Object.freeze({ id: 'both-slow', localSettlementMs: 500, providerFinalMs: 500 }),
]);

test('candidate A1 reduces the four exact fixtures into closed p50 and nearest-rank p95 summaries', async () => {
  const report = await runEotSttSettlementBenchmark({ fixtures: FIXTURES, attempts: 5, candidate: 'A1' });

  assert.equal(report.attempts.length, 20);
  assert.equal(report.forbidden_effects.agent_submit, 0);
  assert.equal(report.forbidden_effects.tts_request, 0);
  assert.equal(report.summaries[0].successful_samples, 5);
  assert.deepEqual(report.summaries[0].eot_to_recognized_final_ms, { p50_ms: 100, p95_ms: 100 });
  assert.deepEqual(report.summaries[3].eot_to_recognized_final_ms, { p50_ms: 1000, p95_ms: 1000 });
  assert.deepEqual(Object.keys(report.attempts[0]), [
    'fixture_id',
    'attempt_index',
    'outcome',
    'marks_ms',
    'rpc_count',
    'exact_result',
    'cleanup_complete',
  ]);
  assert.equal(JSON.stringify(report).includes('transcript'), false);
  assert.equal(JSON.stringify(report).includes('final_text'), false);
  assert.equal(JSON.stringify(report).includes('item_id'), false);
});

test('fixture validation rejects duplicates, mismatched exact delays, nonfinite delays, and attempt bounds', async () => {
  await assert.rejects(
    runEotSttSettlementBenchmark({ fixtures: [...FIXTURES.slice(0, 3), FIXTURES[0]], attempts: 5, candidate: 'A1' }),
    /EOT_STT_BENCHMARK_FIXTURES_INVALID/,
  );
  await assert.rejects(
    runEotSttSettlementBenchmark({
      fixtures: FIXTURES.map((fixture, index) => index === 0 ? { ...fixture, localSettlementMs: -1 } : fixture),
      attempts: 5,
      candidate: 'A1',
    }),
    /EOT_STT_BENCHMARK_FIXTURES_INVALID/,
  );
  await assert.rejects(
    runEotSttSettlementBenchmark({
      fixtures: FIXTURES.map((fixture, index) => index === 0 ? { ...fixture, providerFinalMs: Number.POSITIVE_INFINITY } : fixture),
      attempts: 5,
      candidate: 'A1',
    }),
    /EOT_STT_BENCHMARK_FIXTURES_INVALID/,
  );
  for (const attempts of [0, 21, 1.5]) {
    await assert.rejects(
      runEotSttSettlementBenchmark({ fixtures: FIXTURES, attempts, candidate: 'A1' }),
      /EOT_STT_BENCHMARK_ATTEMPTS_INVALID/,
    );
  }
});

test('attempt reduction rejects private fields, unknown fields, and non-monotonic closed marks without reflecting content', async () => {
  const privateSentinel = ['PRIVATE', 'TRANSCRIPT', 'SENTINEL'].join('_');
  const validAttempt = Object.freeze({
    fixture_id: 'local-fast-provider-fast',
    attempt_index: 0,
    outcome: 'completed',
    marks_ms: Object.freeze({
      'browser.eot_received': 0,
      'browser.uplink_closed': 50,
      'browser.streaming_result_request_started': 50,
      'browser.streaming_result_returned': 100,
      'browser.stt_final_received': 100,
    }),
    rpc_count: 1,
    exact_result: true,
    cleanup_complete: true,
  });
  const cases = [
    { ...validAttempt, transcript: privateSentinel },
    { ...validAttempt, unexpected: true },
    {
      ...validAttempt,
      marks_ms: {
        ...validAttempt.marks_ms,
        'browser.streaming_result_returned': 40,
      },
    },
  ];
  for (const invalidAttempt of cases) {
    let failure = null;
    try {
      await runEotSttSettlementBenchmark({
        fixtures: FIXTURES,
        attempts: 1,
        candidate: 'A1',
        attempt_runner: async (_fixture, _attemptIndex) => invalidAttempt,
      });
    } catch (error) {
      failure = error;
    }
    assert.notEqual(failure, null);
    assert.match(String(failure), /EOT_STT_BENCHMARK_ATTEMPT_INVALID/);
    assert.equal(String(failure).includes(privateSentinel), false);
  }
});

test('CLI requires the fixed A1 boundary, an absolute Python executable, and at least five attempts', () => {
  const parsed = parseEotSttSettlementBenchmarkArgs([
    '--output', '/tmp/eot-stt.json',
    '--git-commit', 'a'.repeat(40),
    '--run-id', 'eot-stt-a1',
    '--attempts', '5',
    '--candidate', 'A1',
    '--python-executable', '/usr/bin/python3',
  ]);
  assert.equal(parsed.pythonExecutable, '/usr/bin/python3');
  assert.equal(parsed.attempts, 5);
  for (const argv of [
    [
      '--output', '/tmp/eot-stt.json', '--git-commit', 'a'.repeat(40), '--run-id', 'eot-stt-a1',
      '--attempts', '4', '--candidate', 'A1', '--python-executable', '/usr/bin/python3',
    ],
    [
      '--output', '/tmp/eot-stt.json', '--git-commit', 'a'.repeat(40), '--run-id', 'eot-stt-a1',
      '--attempts', '5', '--candidate', 'B', '--python-executable', '/usr/bin/python3',
    ],
    [
      '--output', '/tmp/eot-stt.json', '--git-commit', 'a'.repeat(40), '--run-id', 'eot-stt-a1',
      '--attempts', '5', '--candidate', 'A1', '--python-executable', 'python3',
    ],
  ]) {
    assert.throws(() => parseEotSttSettlementBenchmarkArgs(argv), /EOT_STT_BENCHMARK_ARGUMENT_INVALID/);
  }
});

test('source validation rejects a dirty or mismatched candidate without including status content', () => {
  assert.doesNotThrow(() => assertEotSttCleanSource('a'.repeat(40), 'a'.repeat(40), ''));
  const privateStatus = ['PRIVATE', 'UNTRACKED', 'PATH'].join('_');
  for (const [actualCommit, statusText] of [['b'.repeat(40), ''], ['a'.repeat(40), privateStatus]]) {
    let failure = null;
    try {
      assertEotSttCleanSource('a'.repeat(40), actualCommit, statusText);
    } catch (error) {
      failure = error;
    }
    assert.match(String(failure), /EOT_STT_BENCHMARK_SOURCE_NOT_CLEAN/);
    assert.equal(String(failure).includes(privateStatus), false);
  }
});

test('Python executable validation preserves an absolute virtual-environment symlink', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'live-voice-eot-stt-python-'));
  const executable = path.join(directory, 'python3');
  await symlink(process.execPath, executable);
  assert.equal(await validateEotSttPythonExecutable(executable), executable);
});

test('report creation is exclusive, mode 600, and leaves an existing report untouched', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'live-voice-eot-stt-'));
  const output = path.join(directory, 'report.json');
  const report = await runEotSttSettlementBenchmark({ fixtures: FIXTURES, attempts: 1, candidate: 'A1' });
  await writeEotSttSettlementBenchmarkReport(output, report);
  assert.equal((await stat(output)).mode & 0o777, 0o600);
  const first = await readFile(output, 'utf8');
  await assert.rejects(writeEotSttSettlementBenchmarkReport(output, { overwritten: true }), /EOT_STT_BENCHMARK_OUTPUT_EXISTS/);
  assert.equal(await readFile(output, 'utf8'), first);
});
