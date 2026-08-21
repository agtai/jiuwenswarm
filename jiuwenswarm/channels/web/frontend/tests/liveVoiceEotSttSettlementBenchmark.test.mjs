import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, stat, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  runEotSttSettlementBenchmark,
} from '../node_modules/.cache/live-voice-eot-stt-benchmark/eotSttSettlementBenchmark.js';
import {
  assertEotSttCleanSource,
  JsonLineRegistryFixture,
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
const ATTEMPT_MARKS = Object.freeze([
  'browser.eot_received',
  'browser.capture_stop_requested',
  'browser.capture_stopped',
  'browser.uplink_last_frame_sent',
  'browser.uplink_last_ack_received',
  'browser.uplink_closed',
  'benchmark.provider_final_ready',
  'browser.streaming_result_request_started',
  'browser.streaming_result_returned',
  'browser.stt_final_received',
]);
const SEGMENTS = Object.freeze([
  'eot_to_capture_stopped',
  'capture_stopped_to_last_ack',
  'last_ack_to_route_settled',
  'eot_to_provider_final_ready',
  'route_settled_to_result_request_started',
  'result_request_started_to_result_returned',
  'route_settled_to_result_returned',
  'eot_to_recognized_final',
]);

test('candidate A1 reduces the four exact fixtures into closed p50 and nearest-rank p95 summaries', async () => {
  const report = await runEotSttSettlementBenchmark({ fixtures: FIXTURES, attempts: 5, candidate: 'A1' });

  assert.equal(report.attempts.length, 20);
  assert.equal(report.forbidden_effects.agent_submit, 0);
  assert.equal(report.forbidden_effects.tts_request, 0);
  assert.equal(report.summaries[0].successful_samples, 5);
  assert.deepEqual(report.summaries[0].eot_to_recognized_final_ms, { p50_ms: 50, p95_ms: 50 });
  assert.deepEqual(report.summaries[3].eot_to_recognized_final_ms, { p50_ms: 500, p95_ms: 500 });
  assert.deepEqual(Object.keys(report.attempts[0].marks_ms), ATTEMPT_MARKS);
  assert.deepEqual(Object.keys(report.attempts[0].segments_ms), SEGMENTS);
  assert.deepEqual(Object.keys(report.attempts[0]), [
    'fixture_id',
    'attempt_index',
    'outcome',
    'marks_ms',
    'rpc_count',
    'exact_result',
    'cleanup_complete',
    'segments_ms',
    'removable_serial_gap_ms',
    'removable_serial_gap_fraction',
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
      'browser.capture_stop_requested': 1,
      'browser.capture_stopped': 2,
      'browser.uplink_last_frame_sent': 1,
      'browser.uplink_last_ack_received': 50,
      'browser.uplink_closed': 50,
      'benchmark.provider_final_ready': 75,
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
    {
      ...validAttempt,
      marks_ms: Object.fromEntries(
        Object.entries(validAttempt.marks_ms).filter(([point]) => point !== 'benchmark.provider_final_ready'),
      ),
    },
    { ...validAttempt, marks_ms: { ...validAttempt.marks_ms, 'benchmark.provider_final_ready': Number.NaN } },
    { ...validAttempt, marks_ms: { ...validAttempt.marks_ms, 'benchmark.provider_final_ready': -1 } },
    { ...validAttempt, marks_ms: { ...validAttempt.marks_ms, 'benchmark.provider_final_ready': 110 } },
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

function concurrentAttempt(fixture, attemptIndex, removableTailMs) {
  const providerReadyMs = fixture.providerFinalMs;
  const uplinkClosedMs = fixture.localSettlementMs;
  const resultReturnedMs = Math.max(uplinkClosedMs, providerReadyMs) + removableTailMs;
  return Object.freeze({
    fixture_id: fixture.id,
    attempt_index: attemptIndex,
    outcome: 'completed',
    marks_ms: Object.freeze({
      'browser.eot_received': 0,
      'browser.capture_stop_requested': 1,
      'browser.capture_stopped': 2,
      'browser.uplink_last_frame_sent': 1,
      'browser.uplink_last_ack_received': uplinkClosedMs,
      'browser.uplink_closed': uplinkClosedMs,
      'benchmark.provider_final_ready': providerReadyMs,
      'browser.streaming_result_request_started': uplinkClosedMs,
      'browser.streaming_result_returned': resultReturnedMs,
      'browser.stt_final_received': resultReturnedMs,
    }),
    rpc_count: 1,
    exact_result: true,
    cleanup_complete: true,
  });
}

test('local-fast/provider-slow retains a large route wait but only the removable post-readiness tail', async () => {
  const report = await runEotSttSettlementBenchmark({
    fixtures: FIXTURES,
    attempts: 1,
    candidate: 'A1',
    attempt_runner: (fixture, attemptIndex) => concurrentAttempt(fixture, attemptIndex, 10),
  });
  const summary = report.summaries.find(item => item.fixture_id === 'local-fast-provider-slow');
  const attempt = report.attempts.find(item => item.fixture_id === 'local-fast-provider-slow');
  assert.deepEqual(summary.route_settled_to_result_returned_ms, { p50_ms: 460, p95_ms: 460 });
  assert.deepEqual(summary.removable_serial_gap_ms, { p50_ms: 10, p95_ms: 10 });
  assert.deepEqual(summary.removable_serial_gap_fraction, { p50: 0.02, p95: 0.02 });
  assert.equal(attempt.removable_serial_gap_ms, 10);
  assert.equal(attempt.removable_serial_gap_fraction, 0.02);
  assert.deepEqual(attempt.segments_ms, {
    eot_to_capture_stopped: 2,
    capture_stopped_to_last_ack: 48,
    last_ack_to_route_settled: 0,
    eot_to_provider_final_ready: 500,
    route_settled_to_result_request_started: 0,
    result_request_started_to_result_returned: 460,
    route_settled_to_result_returned: 460,
    eot_to_recognized_final: 510,
  });
  assert.deepEqual(summary.eot_to_capture_stopped_ms, { p50_ms: 2, p95_ms: 2 });
  assert.deepEqual(summary.capture_stopped_to_last_ack_ms, { p50_ms: 48, p95_ms: 48 });
  assert.deepEqual(summary.last_ack_to_route_settled_ms, { p50_ms: 0, p95_ms: 0 });
  assert.deepEqual(summary.eot_to_provider_final_ready_ms, { p50_ms: 500, p95_ms: 500 });
  assert.deepEqual(summary.route_settled_to_result_request_started_ms, { p50_ms: 0, p95_ms: 0 });
  assert.deepEqual(summary.result_request_started_to_result_returned_ms, { p50_ms: 460, p95_ms: 460 });
});

test('an injected scheduling and result-RPC tail remains a material removable gap', async () => {
  const report = await runEotSttSettlementBenchmark({
    fixtures: FIXTURES,
    attempts: 1,
    candidate: 'A1',
    attempt_runner: (fixture, attemptIndex) => concurrentAttempt(fixture, attemptIndex, 100),
  });
  const summary = report.summaries[0];
  assert.deepEqual(summary.route_settled_to_result_returned_ms, { p50_ms: 100, p95_ms: 100 });
  assert.deepEqual(summary.removable_serial_gap_ms, { p50_ms: 100, p95_ms: 100 });
  assert.deepEqual(summary.removable_serial_gap_fraction, { p50: 0.667, p95: 0.667 });
});

test('completed attempts reject a zero EOT-to-final duration before derived statistics', async () => {
  const zeroDuration = Object.freeze({
    fixture_id: 'local-fast-provider-fast',
    attempt_index: 0,
    outcome: 'completed',
    marks_ms: Object.freeze(Object.fromEntries(ATTEMPT_MARKS.map(point => [point, 0]))),
    rpc_count: 1,
    exact_result: true,
    cleanup_complete: true,
  });
  await assert.rejects(
    runEotSttSettlementBenchmark({
      fixtures: FIXTURES,
      attempts: 1,
      candidate: 'A1',
      attempt_runner: async () => zeroDuration,
    }),
    /EOT_STT_BENCHMARK_ATTEMPT_INVALID/,
  );
});

test('failed or inexact attempts retain no attractive numeric segment or removable gap', async () => {
  const report = await runEotSttSettlementBenchmark({
    fixtures: FIXTURES,
    attempts: 1,
    candidate: 'A1',
    attempt_runner: (fixture, attemptIndex) => ({
      ...concurrentAttempt(fixture, attemptIndex, 100),
      outcome: 'failed',
      exact_result: false,
      cleanup_complete: false,
    }),
  });
  assert.deepEqual(Object.values(report.attempts[0].segments_ms), Array(8).fill(null));
  assert.equal(report.attempts[0].removable_serial_gap_ms, null);
  assert.equal(report.attempts[0].removable_serial_gap_fraction, null);
  assert.equal(report.summaries[0].successful_samples, 0);
  assert.deepEqual(report.summaries[0].eot_to_recognized_final_ms, { p50_ms: null, p95_ms: null });
});

test('finite marks whose millisecond rounding scale overflows are rejected', async () => {
  const extreme = {
    ...concurrentAttempt(FIXTURES[0], 0, 1),
    marks_ms: Object.fromEntries(ATTEMPT_MARKS.map((point, index) => [
      point,
      index === 0 ? 0 : Number.MAX_VALUE,
    ])),
  };
  await assert.rejects(
    runEotSttSettlementBenchmark({
      fixtures: FIXTURES,
      attempts: 1,
      candidate: 'A1',
      attempt_runner: (_fixture, attemptIndex) => ({ ...extreme, attempt_index: attemptIndex }),
    }),
    /EOT_STT_BENCHMARK_ATTEMPT_INVALID/,
  );
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

test('report publication failure removes its private temporary and creates no final file', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'live-voice-eot-stt-atomic-'));
  const output = path.join(directory, 'report.json');
  const privateSentinel = ['PRIVATE', 'PUBLICATION', 'FAILURE'].join('_');
  let failure = null;
  try {
    await writeEotSttSettlementBenchmarkReport(output, { safe: true }, {
      before_publish: async () => { throw new Error(privateSentinel); },
    });
  } catch (error) {
    failure = error;
  }
  assert.match(String(failure), /EOT_STT_BENCHMARK_REPORT_WRITE_FAILED/);
  assert.equal(String(failure).includes(privateSentinel), false);
  assert.deepEqual(await readdir(directory), []);
});

async function writeChildScript(source) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'live-voice-eot-stt-child-'));
  const script = path.join(directory, 'child.mjs');
  await writeFile(script, source, { encoding: 'utf8', mode: 0o600 });
  return script;
}

test('fixture spawn failure is awaited, stable, and has no unreaped child', async () => {
  const fixture = new JsonLineRegistryFixture(
    path.join(os.tmpdir(), 'missing-eot-stt-python'),
    50,
    50,
    { request_timeout_ms: 50, shutdown_timeout_ms: 50, kill_timeout_ms: 50 },
  );
  await assert.rejects(fixture.request('open'), /EOT_STT_BENCHMARK_FIXTURE_FAILED/);
  assert.deepEqual(fixture.lifecycle(), {
    reaped: true,
    term_sent: false,
    kill_sent: false,
  });
});

test('fixture immediate-exit write race stays stable and reaps without unhandled EPIPE', async () => {
  const script = await writeChildScript(`
    process.stdin.destroy();
    process.exit(0);
  `);
  const fixture = new JsonLineRegistryFixture(process.execPath, 50, 50, {
    fixture_script: script,
    request_timeout_ms: 100,
    shutdown_timeout_ms: 100,
    kill_timeout_ms: 100,
  });
  await assert.rejects(fixture.request('open'), /EOT_STT_BENCHMARK_FIXTURE_FAILED/);
  assert.equal(fixture.lifecycle().reaped, true);
});

test('nonresponsive fixture request times out and TERM reaps the child', async () => {
  const script = await writeChildScript(`
    process.stdin.resume();
    setInterval(() => undefined, 1000);
  `);
  const fixture = new JsonLineRegistryFixture(process.execPath, 50, 50, {
    fixture_script: script,
    request_timeout_ms: 100,
    shutdown_timeout_ms: 100,
    kill_timeout_ms: 100,
  });
  await assert.rejects(fixture.request('open'), /EOT_STT_BENCHMARK_FIXTURE_FAILED/);
  assert.deepEqual(fixture.lifecycle(), {
    reaped: true,
    term_sent: true,
    kill_sent: false,
  });
});

test('fixture cleanup escalates ignored TERM to KILL and awaits the reaped child', async () => {
  const script = await writeChildScript(`
    process.on('SIGTERM', () => undefined);
    process.stdin.resume();
    setInterval(() => undefined, 1000);
  `);
  const fixture = new JsonLineRegistryFixture(process.execPath, 50, 50, {
    fixture_script: script,
    request_timeout_ms: 150,
    shutdown_timeout_ms: 50,
    kill_timeout_ms: 250,
  });
  await assert.rejects(fixture.request('open'), /EOT_STT_BENCHMARK_FIXTURE_FAILED/);
  assert.deepEqual(fixture.lifecycle(), {
    reaped: true,
    term_sent: true,
    kill_sent: true,
  });
});

test('fixture termination rejects stable when post-KILL exit cannot be confirmed', async () => {
  const script = await writeChildScript(`
    process.stdin.resume();
    setInterval(() => undefined, 1000);
  `);
  const fixture = new JsonLineRegistryFixture(process.execPath, 50, 50, {
    fixture_script: script,
    request_timeout_ms: 100,
    shutdown_timeout_ms: 30,
    kill_timeout_ms: 30,
  });
  await fixture._requireSpawned();
  const actualKill = fixture.child.kill.bind(fixture.child);
  fixture.child.kill = () => true;
  try {
    await assert.rejects(
      fixture.terminate(),
      /EOT_STT_BENCHMARK_FIXTURE_CLEANUP_FAILED/,
    );
    assert.deepEqual(fixture.lifecycle(), {
      reaped: false,
      term_sent: true,
      kill_sent: true,
    });
  } finally {
    fixture.child.kill = actualKill;
    actualKill('SIGKILL');
    await fixture.exited;
    fixture._closePipes();
  }
});
