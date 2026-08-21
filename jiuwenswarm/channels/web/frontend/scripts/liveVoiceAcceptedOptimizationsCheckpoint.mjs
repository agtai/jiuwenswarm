import { createHash, randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import {
  CHECKPOINT_CONTROLLED_TARGETS,
  CHECKPOINT_WORKLOADS,
  buildCheckpointReport,
  compareCheckpointReports,
  parseCheckpointComparison,
  parseCheckpointReport,
  runCheckpointAttempt,
} from '../node_modules/.cache/live-voice-accepted-checkpoint/acceptedOptimizationsCheckpoint.js';
import {
  PRODUCT_P2_ACTIVATE_METHOD,
  PRODUCT_P2_BARGE_IN_METHOD,
  PRODUCT_P2_CLOSE_METHOD,
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_PRESENTATION_ACK_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
  ProductWebP2ActivationOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';
import { runTtsFirstAudioCausalBenchmark } from './liveVoiceTtsFirstAudioCausalBenchmark.mjs';

class ControlledMonotonicClock {
  #monotonicMs = 0;
  #scheduled = [];
  #drainScheduled = false;
  #sequence = 0;

  nowMs() {
    return this.#monotonicMs;
  }

  async waitMs(delayMs) {
    if (!Number.isFinite(delayMs) || delayMs < 0) throw new Error('CHECKPOINT_CLOCK_DELAY_INVALID');
    this.#monotonicMs += delayMs;
  }

  scheduleMs(delayMs, callback) {
    if (!Number.isFinite(delayMs) || delayMs < 0 || typeof callback !== 'function') throw new Error('CHECKPOINT_CLOCK_SCHEDULE_INVALID');
    this.#scheduled.push({ dueMs: this.#monotonicMs + delayMs, sequence: this.#sequence++, callback });
    this.#scheduleDrain();
  }

  #scheduleDrain() {
    if (this.#drainScheduled || this.#scheduled.length === 0) return;
    this.#drainScheduled = true;
    setImmediate(() => {
      setImmediate(() => {
        this.#scheduled.sort((left, right) => left.dueMs - right.dueMs || left.sequence - right.sequence);
        const next = this.#scheduled.shift();
        if (next !== undefined) {
          this.#monotonicMs = Math.max(this.#monotonicMs, next.dueMs);
          next.callback();
        }
        this.#drainScheduled = false;
        queueMicrotask(() => this.#scheduleDrain());
      });
    });
  }
}

function fail(reason) {
  throw new Error(reason);
}

const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const GIT_COMMIT = /^[0-9a-f]{40}$/;

function canonicalInteger(value, minimum, maximum) {
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

function closedFlags(argv, allowed) {
  if (!Array.isArray(argv) || argv.length !== allowed.size * 2) fail('CHECKPOINT_ARGUMENT_INVALID');
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!allowed.has(key) || values.has(key) || typeof value !== 'string' || value.length === 0) fail('CHECKPOINT_ARGUMENT_INVALID');
    values.set(key, value);
  }
  return values;
}

export function parseAcceptedCheckpointArgs(argv) {
  if (!Array.isArray(argv) || argv.length === 0) fail('CHECKPOINT_ARGUMENT_INVALID');
  const [command, ...tail] = argv;
  if (command === 'run') {
    const values = closedFlags(tail, new Set(['--population', '--mode', '--samples', '--git-commit', '--run-id', '--output']));
    const population = values.get('--population');
    const mode = values.get('--mode');
    const samples = canonicalInteger(values.get('--samples'), 5, 5);
    const gitCommit = values.get('--git-commit');
    const runId = values.get('--run-id');
    const output = values.get('--output');
    const populationModeValid = (population === 'B' && mode === 'optimized') || ((population === 'A1' || population === 'A2') && mode === 'baseline');
    if (
      !populationModeValid ||
      samples === null ||
      !GIT_COMMIT.test(gitCommit ?? '') ||
      !RUN_ID.test(runId ?? '') ||
      typeof output !== 'string' ||
      !path.isAbsolute(output) ||
      output.includes('\n') ||
      output.includes('\r')
    )
      fail('CHECKPOINT_ARGUMENT_INVALID');
    return Object.freeze({
      command: 'run',
      population,
      mode,
      samples,
      git_commit: gitCommit,
      run_id: runId,
      output,
    });
  }
  if (command === 'compare-a-b-a') {
    const values = closedFlags(tail, new Set(['--baseline-before', '--candidate', '--baseline-after', '--output']));
    const result = {
      command: 'compare-a-b-a',
      baseline_before: values.get('--baseline-before'),
      candidate: values.get('--candidate'),
      baseline_after: values.get('--baseline-after'),
      output: values.get('--output'),
    };
    const paths = [result.baseline_before, result.candidate, result.baseline_after, result.output];
    if (
      paths.some(value => typeof value !== 'string' || !path.isAbsolute(value) || value.includes('\n') || value.includes('\r')) ||
      new Set(paths).size !== paths.length
    )
      fail('CHECKPOINT_ARGUMENT_INVALID');
    return Object.freeze(result);
  }
  if (command === 'render-markdown') {
    const values = closedFlags(tail, new Set(['--comparison', '--output']));
    const comparison = values.get('--comparison');
    const output = values.get('--output');
    if (
      typeof comparison !== 'string' ||
      typeof output !== 'string' ||
      !path.isAbsolute(comparison) ||
      !path.isAbsolute(output) ||
      comparison === output ||
      comparison.includes('\n') ||
      comparison.includes('\r') ||
      output.includes('\n') ||
      output.includes('\r')
    )
      fail('CHECKPOINT_ARGUMENT_INVALID');
    return Object.freeze({ command: 'render-markdown', comparison, output });
  }
  fail('CHECKPOINT_ARGUMENT_INVALID');
}

export async function writePrivateCheckpointReport(output, report) {
  return writePrivateJson(output, report, parseCheckpointReport, 'CHECKPOINT_REPORT_INVALID');
}

const MAX_PRIVATE_REPORT_BYTES = 8 * 1024 * 1024;

async function writePrivateJson(output, value, parser, invalidReason) {
  if (typeof output !== 'string' || !path.isAbsolute(output) || output.includes('\n') || output.includes('\r')) fail(invalidReason);
  let serialized;
  try {
    serialized = `${JSON.stringify(parser(value))}\n`;
  } catch {
    fail(invalidReason);
  }
  if (Buffer.byteLength(serialized, 'utf8') > MAX_PRIVATE_REPORT_BYTES) fail(invalidReason);
  const temporary = `${output}.tmp-${process.pid}-${randomUUID()}`;
  let handle = null;
  let linked = false;
  let failed = false;
  try {
    handle = await fs.open(temporary, 'wx', 0o600);
    await handle.chmod(0o600);
    await handle.writeFile(serialized, 'utf8');
    await handle.sync();
    const temporaryStat = await handle.stat();
    if (!temporaryStat.isFile() || (temporaryStat.mode & 0o777) !== 0o600 || temporaryStat.size > MAX_PRIVATE_REPORT_BYTES) fail(invalidReason);
    await handle.close();
    handle = null;
    parser(JSON.parse(await fs.readFile(temporary, 'utf8')));
    await fs.link(temporary, output);
    linked = true;
    const directoryHandle = await fs.open(path.dirname(output), 'r');
    try {
      await directoryHandle.sync();
    } finally {
      await directoryHandle.close();
    }
    const installed = await fs.lstat(output);
    if (!installed.isFile() || installed.isSymbolicLink() || (installed.mode & 0o777) !== 0o600 || installed.size > MAX_PRIVATE_REPORT_BYTES)
      fail(invalidReason);
  } catch (error) {
    failed = true;
    if (error?.code === 'EEXIST') fail('CHECKPOINT_OUTPUT_EXISTS');
    if (error instanceof Error && error.message.startsWith('CHECKPOINT_')) throw error;
    fail(invalidReason);
  } finally {
    if (handle !== null) await handle.close().catch(() => undefined);
    await fs.unlink(temporary).catch(() => undefined);
    if (failed && linked) await fs.unlink(output).catch(() => undefined);
  }
}

export async function readPrivateCheckpointReport(input) {
  return (await readPrivateCheckpointReportWithHash(input)).report;
}

async function readPrivateCheckpointReportWithHash(input) {
  try {
    const stat = await fs.lstat(input);
    if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o777) !== 0o600 || stat.size < 1 || stat.size > MAX_PRIVATE_REPORT_BYTES)
      fail('CHECKPOINT_REPORT_INVALID');
    const bytes = await fs.readFile(input);
    return Object.freeze({ report: parseCheckpointReport(JSON.parse(bytes.toString('utf8'))), sha256: sha256(bytes) });
  } catch (error) {
    if (error instanceof Error && error.message === 'CHECKPOINT_REPORT_INVALID') throw error;
    fail('CHECKPOINT_REPORT_INVALID');
  }
}

export function assertCheckpointOutputOutsideGit(output, gitRoot) {
  let existingParent = path.dirname(path.resolve(output));
  const suffix = [path.basename(output)];
  while (!existsSync(existingParent)) {
    const parent = path.dirname(existingParent);
    if (parent === existingParent) fail('CHECKPOINT_OUTPUT_PATH_INVALID');
    suffix.unshift(path.basename(existingParent));
    existingParent = parent;
  }
  const resolvedOutput = path.join(realpathSync(existingParent), ...suffix);
  const resolvedRoot = realpathSync(gitRoot);
  const relative = path.relative(resolvedRoot, resolvedOutput);
  if (relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))) fail('CHECKPOINT_OUTPUT_INSIDE_GIT');
  return resolvedOutput;
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

async function neutralRunnerFingerprint() {
  const files = [
    ['checkpoint-runner', new URL(import.meta.url)],
    ['checkpoint-core', new URL('../src/features/live-voice/benchmark/acceptedOptimizationsCheckpoint.ts', import.meta.url)],
    ['tts-controlled-owner-seam', new URL('./liveVoiceTtsFirstAudioCausalBenchmark.mjs', import.meta.url)],
  ];
  const hash = createHash('sha256');
  for (const [label, file] of files) {
    hash.update(label);
    hash.update(await fs.readFile(file));
  }
  return hash.digest('hex');
}

export async function runAcceptedCheckpointPopulation(input) {
  const optimizationMode =
    input.mode === 'optimized'
      ? Object.freeze({ p2_notification_batch_size: 16, tts_successor_ack_overlap: true })
      : Object.freeze({ p2_notification_batch_size: 1, tts_successor_ack_overlap: false });
  if (
    !['A1', 'B', 'A2'].includes(input.population) ||
    !((input.population === 'B' && input.mode === 'optimized') || (input.population !== 'B' && input.mode === 'baseline')) ||
    !Number.isSafeInteger(input.samples) ||
    input.samples < 1 ||
    input.samples > 30 ||
    !GIT_COMMIT.test(input.git_commit ?? '') ||
    !RUN_ID.test(input.run_id ?? '')
  )
    fail('CHECKPOINT_RUN_INPUT_INVALID');
  const runnerFingerprint = await neutralRunnerFingerprint();
  const fixtureFingerprint = sha256(JSON.stringify(CHECKPOINT_WORKLOADS));
  const timingFingerprint = sha256(JSON.stringify(CHECKPOINT_CONTROLLED_TARGETS));
  const attempts = [];
  for (const workloadId of Object.keys(CHECKPOINT_WORKLOADS)) {
    for (let attemptIndex = 0; attemptIndex < input.samples; attemptIndex += 1) {
      attempts.push(
        await runControlledOwnerAttempt({
          run_id: input.run_id,
          population: input.population,
          workload_id: workloadId,
          attempt_index: attemptIndex,
          source_commit: input.git_commit,
          runner_fingerprint: runnerFingerprint,
          fixture_fingerprint: fixtureFingerprint,
          timing_fingerprint: timingFingerprint,
          optimization_mode: optimizationMode,
        }),
      );
    }
  }
  return buildCheckpointReport(
    {
      run_id: input.run_id,
      population: input.population,
      source_commit: input.git_commit,
      source_clean: true,
      runner_fingerprint: runnerFingerprint,
      fixture_fingerprint: fixtureFingerprint,
      timing_fingerprint: timingFingerprint,
      samples_per_workload: input.samples,
      optimization_mode: optimizationMode,
    },
    attempts,
  );
}

export async function comparePrivateCheckpointReports(input) {
  const [a1Input, bInput, a2Input] = await Promise.all([
    readPrivateCheckpointReportWithHash(input.baseline_before),
    readPrivateCheckpointReportWithHash(input.candidate),
    readPrivateCheckpointReportWithHash(input.baseline_after),
  ]);
  const comparison = compareCheckpointReports(a1Input.report, bInput.report, a2Input.report);
  const boundComparison = Object.freeze({
    ...comparison,
    inputs: Object.freeze({
      a1: Object.freeze({ ...comparison.inputs.a1, report_sha256: a1Input.sha256 }),
      b: Object.freeze({ ...comparison.inputs.b, report_sha256: bInput.sha256 }),
      a2: Object.freeze({ ...comparison.inputs.a2, report_sha256: a2Input.sha256 }),
    }),
  });
  await writePrivateJson(input.output, boundComparison, parseCheckpointComparison, 'CHECKPOINT_COMPARISON_INVALID');
  return boundComparison;
}

async function readPrivateCheckpointComparison(input) {
  try {
    const stat = await fs.lstat(input);
    if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o777) !== 0o600 || stat.size < 1 || stat.size > MAX_PRIVATE_REPORT_BYTES)
      fail('CHECKPOINT_COMPARISON_INVALID');
    return parseCheckpointComparison(JSON.parse(await fs.readFile(input, 'utf8')));
  } catch (error) {
    if (error instanceof Error && error.message === 'CHECKPOINT_COMPARISON_INVALID') throw error;
    fail('CHECKPOINT_COMPARISON_INVALID');
  }
}

async function writeRenderedMarkdown(output, markdown) {
  let handle = null;
  try {
    handle = await fs.open(output, 'wx', 0o644);
    await handle.chmod(0o644);
    await handle.writeFile(markdown, 'utf8');
    await handle.sync();
  } catch (error) {
    if (error?.code === 'EEXIST') fail('CHECKPOINT_OUTPUT_EXISTS');
    throw error;
  } finally {
    await handle?.close().catch(() => undefined);
  }
}

function fixed(value) {
  return value.toFixed(3);
}

export function renderCheckpointComparisonMarkdown(comparison) {
  const parsed = parseCheckpointComparison(comparison);
  const lines = [
    '# Accepted Optimizations Latency Checkpoint',
    '',
    `Decision: **${parsed.decision}**`,
    '',
    '## Exact inputs',
    '',
    '| Population | Run | Source commit | Raw report SHA-256 |',
    '|---|---|---|---|',
    `| A1 | ${parsed.inputs.a1.run_id} | ${parsed.inputs.a1.source_commit} | ${parsed.inputs.a1.report_sha256} |`,
    `| B | ${parsed.inputs.b.run_id} | ${parsed.inputs.b.source_commit} | ${parsed.inputs.b.report_sha256} |`,
    `| A2 | ${parsed.inputs.a2.run_id} | ${parsed.inputs.a2.source_commit} | ${parsed.inputs.a2.report_sha256} |`,
    '',
    '## Measured stages and derived deltas',
    '',
    '| Workload | Stage | A1 p50/p95 ms | B p50/p95 ms | A2 p50/p95 ms | B−A1 p50 ms | B−A2 p50 ms | B−A1 p95 ms | B−A2 p95 ms | B−A1 % | B−A2 % | A drift % | Result | Truth |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|',
  ];
  for (const [workloadId, workload] of Object.entries(parsed.workloads)) {
    for (const [segment, row] of Object.entries(workload.segments)) {
      lines.push(
        `| ${workloadId} | ${segment} | ${fixed(row.measurements.a1.p50_ms)}/${fixed(row.measurements.a1.p95_ms)} | ${fixed(row.measurements.b.p50_ms)}/${fixed(row.measurements.b.p95_ms)} | ${fixed(row.measurements.a2.p50_ms)}/${fixed(row.measurements.a2.p95_ms)} | ${fixed(row.deltas.b_minus_a1_p50_ms)} | ${fixed(row.deltas.b_minus_a2_p50_ms)} | ${fixed(row.deltas.b_minus_a1_p95_ms)} | ${fixed(row.deltas.b_minus_a2_p95_ms)} | ${row.deltas.b_minus_a1_p50_percent === null ? 'n/a' : fixed(row.deltas.b_minus_a1_p50_percent)} | ${row.deltas.b_minus_a2_p50_percent === null ? 'n/a' : fixed(row.deltas.b_minus_a2_p50_percent)} | ${row.deltas.baseline_drift_p50_percent === null ? 'n/a' : fixed(row.deltas.baseline_drift_p50_percent)} | ${row.result} | MEASURED + DERIVED |`,
      );
    }
  }
  lines.push(
    '',
    '## Measured B residual and share of total',
    '',
    '| Workload | Stage | B p50 ms | Share of B round total | Truth |',
    '|---|---|---:|---:|---|',
  );
  for (const [workloadId, workload] of Object.entries(parsed.workloads)) {
    const total = workload.segments.round_total.measurements.b.p50_ms;
    for (const [segment, row] of Object.entries(workload.segments)) {
      const value = row.measurements.b.p50_ms;
      lines.push(`| ${workloadId} | ${segment} | ${fixed(value)} | ${total === 0 ? 'n/a' : fixed((value / total) * 100)}% | MEASURED + DERIVED |`);
    }
  }
  lines.push(
    '',
    '## Proven removable headroom',
    '',
    'Only the compatible A1/B/A2 deltas above are proven removable. They cover bounded P2 pulls and successor-ACK/TTS overlap; no other optimization receives credit.',
    '',
    '## Estimated future headroom',
    '',
    '| Hypothesis | Truth | Status |',
    '|---|---|---|',
    '| EOT/STT settlement overlap | ESTIMATED | Not exercised |',
    '| Semantic/adaptive VAD | ESTIMATED | Not exercised |',
    '| Post-audio.done EOF draining | ESTIMATED | Not exercised |',
    '| Sentence-level Agent→TTS overlap | ESTIMATED | Not exercised |',
    '',
    '## Controlled fixture and out-of-scope boundaries',
    '',
    'CONTROLLED: fixed prompts, STT/admission/Agent/Tool/TTS waits, P2 RPC delay, successor ACK, and PCM playout duration.',
    '',
    'OUT_OF_SCOPE: microphone/device capture, real Provider/network latency, real Agent/Tool execution, physical Chrome/WebAudio scheduling, and human-perceived first audio.',
  );
  return `${lines.join('\n')}\n`;
}

const USAGE = `Usage: liveVoiceAcceptedOptimizationsCheckpoint <command> [options]

Commands:
  run --population A1|B|A2 --mode baseline|optimized --samples N --git-commit SHA --run-id ID --output PATH
  compare-a-b-a --baseline-before PATH --candidate PATH --baseline-after PATH --output PATH
  render-markdown --comparison PATH --output PATH
`;

function captureSourceState() {
  const actualCommit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { encoding: 'utf8' });
  return Object.freeze({ actualCommit, status });
}

function assertExactCleanSource(expectedCommit, expectedSnapshot = null) {
  const snapshot = captureSourceState();
  if (
    snapshot.actualCommit !== expectedCommit ||
    snapshot.status !== '' ||
    (expectedSnapshot !== null && (snapshot.actualCommit !== expectedSnapshot.actualCommit || snapshot.status !== expectedSnapshot.status))
  )
    fail('CHECKPOINT_SOURCE_NOT_CLEAN');
  return snapshot;
}

export async function main(argv = process.argv.slice(2)) {
  if (argv.length === 1 && argv[0] === '--help') {
    process.stdout.write(USAGE);
    return;
  }
  const args = parseAcceptedCheckpointArgs(argv);
  const gitRoot = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
  if (args.command === 'render-markdown') {
    assertCheckpointOutputOutsideGit(args.comparison, gitRoot);
    const comparison = await readPrivateCheckpointComparison(args.comparison);
    await writeRenderedMarkdown(args.output, renderCheckpointComparisonMarkdown(comparison));
    process.stdout.write(`${JSON.stringify({ decision: comparison.decision })}\n`);
    return;
  }
  assertCheckpointOutputOutsideGit(args.output, gitRoot);
  if (args.command === 'compare-a-b-a') {
    assertCheckpointOutputOutsideGit(args.baseline_before, gitRoot);
    assertCheckpointOutputOutsideGit(args.candidate, gitRoot);
    assertCheckpointOutputOutsideGit(args.baseline_after, gitRoot);
  }
  if (args.command === 'run') {
    const sourceBefore = assertExactCleanSource(args.git_commit);
    const report = await runAcceptedCheckpointPopulation(args);
    assertExactCleanSource(args.git_commit, sourceBefore);
    await writePrivateCheckpointReport(args.output, report);
    try {
      assertExactCleanSource(args.git_commit, sourceBefore);
    } catch (error) {
      await fs.unlink(args.output).catch(() => undefined);
      throw error;
    }
    const completed = report.attempts.filter(attempt => attempt.outcome === 'completed').length;
    process.stdout.write(`${JSON.stringify({ run_id: report.run_id, completed, intended: report.attempts.length })}\n`);
    if (completed !== report.attempts.length) fail('CHECKPOINT_POPULATION_INCOMPLETE');
    return;
  }
  const comparison = await comparePrivateCheckpointReports(args);
  process.stdout.write(`${JSON.stringify({ decision: comparison.decision })}\n`);
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  main().catch(() => {
    process.stderr.write('ACCEPTED_CHECKPOINT_FAILED\n');
    process.exitCode = 1;
  });
}

function bindingFor(config) {
  const suffix = `${config.run_id}-${config.population}-${config.workload_id}-${config.attempt_index}`;
  return Object.freeze({
    session_id: `checkpoint-session-${suffix}`,
    correlation_id: `checkpoint-correlation-${suffix}`,
    interaction_id: `checkpoint-interaction-${suffix}`,
    activation_id: `checkpoint-activation-${suffix}`,
    activation_generation: 1,
  });
}

function boundResult(binding, status, changes = {}) {
  return {
    ok: true,
    result: {
      status,
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: binding.interaction_id,
      activation_id: binding.activation_id,
      activation_generation: binding.activation_generation,
      ...changes,
    },
  };
}

function sameBinding(params, binding) {
  return (
    params.session_id === binding.session_id &&
    params.correlation_id === binding.correlation_id &&
    params.interaction_id === binding.interaction_id &&
    params.activation_id === binding.activation_id &&
    params.activation_generation === binding.activation_generation
  );
}

function checkpointNotification(binding, publishSeq, workload) {
  const final = publishSeq === workload.notification_count - 1;
  const toolStarted = workload.id === 'W3' && publishSeq === 40;
  const toolCompleted = workload.id === 'W3' && publishSeq === 41;
  const eventType = final ? 'chat.final' : toolStarted ? 'tool_execution_started' : toolCompleted ? 'tool_execution_completed' : 'chat.delta';
  return boundResult(binding, 'notification', {
    kind: 'agent.output',
    request_id: `checkpoint-notification-${workload.id}-${publishSeq}`,
    round_id: `checkpoint-round-${workload.id}`,
    response: {
      interaction_id: binding.interaction_id,
      response_id: `checkpoint-response-${workload.id}`,
      response_generation: 0,
    },
    agent_event: {
      seq: publishSeq,
      event_type: eventType,
      source_provenance: 'accepted.optimizations.checkpoint',
      text: null,
      capability: null,
      error_reason: null,
    },
    source_event: null,
    progress_event: null,
    presentation_unit: final
      ? {
          surface: 'text',
          unit_id: `checkpoint-final-${workload.id}`,
          seq: 0,
          source_start_utf8: 0,
          source_end_utf8: 1,
          content_ref: `sha256:${'0'.repeat(64)}`,
        }
      : null,
    error_reason: null,
    publish_seq: publishSeq,
  }).result;
}

function batchLength(delivered, requested, workload) {
  const remaining = workload.notification_count - delivered;
  let length = Math.min(requested, remaining);
  for (const barrier of workload.tool_barriers) {
    if (barrier >= delivered && barrier < delivered + length - 1) {
      length = barrier - delivered + 1;
      break;
    }
  }
  return length;
}

async function deliverWithRealP2Owner(config, workload, clock, diagnostics) {
  const binding = bindingFor(config);
  const backlog = Object.freeze(
    Array.from({ length: workload.notification_count }, (_, publishSeq) => Object.freeze(checkpointNotification(binding, publishSeq, workload))),
  );
  let delivered = 0;
  let notificationRpcCount = 0;
  const observedBarriers = [];
  const batches = [];
  let finalNotification = null;
  const batchSize = config.optimization_mode.p2_notification_batch_size;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    notification_batch_size: batchSize,
    request: async (method, params) => {
      if (!sameBinding(params, binding)) fail('CHECKPOINT_P2_BINDING_MISMATCH');
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return boundResult(binding, 'active', { replayed: false });
      if (method === PRODUCT_P2_CLOSE_METHOD) return boundResult(binding, 'closed');
      if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
        const requested = params.max_notifications ?? 1;
        if (params.notification_sequence !== notificationRpcCount + 1 || requested !== batchSize || delivered >= workload.notification_count)
          fail('CHECKPOINT_P2_SEQUENCE_INVALID');
        const startedAt = clock.nowMs();
        await clock.waitMs(CHECKPOINT_CONTROLLED_TARGETS.p2_rpc_ms);
        const completedAt = clock.nowMs();
        notificationRpcCount += 1;
        const length = batchLength(delivered, requested, workload);
        const startPublishSeq = delivered;
        const notifications = backlog
          .slice(delivered, delivered + length)
          .map(notification => (typeof diagnostics.p2NotificationMutator === 'function' ? diagnostics.p2NotificationMutator(notification) : notification));
        delivered += length;
        batches.push(
          Object.freeze({
            rpc_index: notificationRpcCount,
            start_publish_seq: startPublishSeq,
            end_publish_seq: delivered - 1,
            count: length,
            duration_ms: completedAt - startedAt,
          }),
        );
        return requested === 1 ? { ok: true, result: notifications[0] } : boundResult(binding, 'notification_batch', { notifications });
      }
      if (
        method === PRODUCT_P2_SUBMIT_METHOD ||
        method === PRODUCT_P2_PRESENTATION_ACK_METHOD ||
        method === PRODUCT_P2_BARGE_IN_METHOD ||
        method.startsWith('live_voice.composition.p3') ||
        method.startsWith('live_voice.task.')
      )
        fail('CHECKPOINT_FORBIDDEN_PRODUCT_EFFECT');
      fail('CHECKPOINT_P2_METHOD_INVALID');
    },
  });

  try {
    await owner.start(binding);
    let finalSeen = false;
    for (let publishSeq = 0; publishSeq < workload.notification_count; publishSeq += 1) {
      const notification = await owner.nextNotification();
      if (notification.publish_seq !== publishSeq || notification.agent_event?.seq !== publishSeq) fail('CHECKPOINT_P2_ORDER_INVALID');
      if (workload.tool_barriers.includes(publishSeq)) observedBarriers.push(publishSeq);
      const final = publishSeq === workload.notification_count - 1;
      if ((notification.agent_event?.event_type === 'chat.final') !== final || (notification.presentation_unit !== null) !== final || finalSeen)
        fail('CHECKPOINT_P2_FINAL_INVALID');
      finalSeen = final;
      if (final) finalNotification = notification;
    }
    if (!finalSeen || delivered !== workload.notification_count) fail('CHECKPOINT_P2_INCOMPLETE');
  } finally {
    try {
      await owner.close();
    } finally {
      diagnostics.onP2Close?.();
    }
  }
  if (finalNotification === null) fail('CHECKPOINT_P2_FINAL_INVALID');
  return Object.freeze({
    truth_class: 'measured',
    notification_rpc_count: notificationRpcCount,
    notification_batch_count: notificationRpcCount,
    ordered_barriers: Object.freeze(observedBarriers),
    batches: Object.freeze(batches),
    response: Object.freeze({
      session_id: binding.session_id,
      correlation_id: binding.correlation_id,
      interaction_id: finalNotification.response.interaction_id,
      activation_id: binding.activation_id,
      response_id: finalNotification.response.response_id,
      response_generation: finalNotification.response.response_generation,
      unit_id: finalNotification.presentation_unit.unit_id,
    }),
  });
}

async function playWithRealP1Owner(config, workload, clock, mark, p2) {
  const pointMap = new Map([
    ['browser.downlink_attach_started', 'downlink_opened'],
    ['browser.downlink_first_frame_received', 'first_frame_received'],
    ['browser.playout_first_frame_scheduled', 'first_source_scheduled'],
    ['browser.playout_completed', 'playout_completed'],
    ['browser.playout_ack_received', 'confirmed_ack_and_next_turn_ready'],
  ]);
  const marked = new Set();
  const report = await runTtsFirstAudioCausalBenchmark({
    runId: `checkpoint-${config.workload_id}-${config.attempt_index}`,
    gitCommit: config.source_commit,
    samples: 1,
    successorAckDelaysMs: [workload.successor_ack_delay_ms],
    identity: {
      session_id: p2.response.session_id,
      correlation_id: p2.response.correlation_id,
      interaction_id: p2.response.interaction_id,
      activation_id: p2.response.activation_id,
      turn_id: `checkpoint-turn-${config.run_id}-${config.workload_id}-${config.attempt_index}`,
      response_id: p2.response.response_id,
      response_generation: p2.response.response_generation,
      unit_id: p2.response.unit_id,
    },
    timing: {
      now: () => clock.nowMs(),
      scheduleAck: (delayMs, callback) => clock.scheduleMs(delayMs, callback),
      schedulePlayout: (delayMs, callback) => clock.scheduleMs(delayMs, callback),
      playoutDurationMs: workload.playout_duration_ms,
      onPoint(point) {
        const checkpointPoint = pointMap.get(point);
        if (checkpointPoint === undefined || marked.has(checkpointPoint)) return;
        marked.add(checkpointPoint);
        mark(checkpointPoint);
      },
    },
  });
  const attempt = report.populations[0]?.attempts[0];
  const expectedMode = config.optimization_mode.tts_successor_ack_overlap ? 'successor_ack_decoupled' : 'legacy_sequential';
  if (report.candidate_mode !== expectedMode || attempt?.outcome !== 'completed') fail('CHECKPOINT_P1_SOURCE_MODE_INVALID');
  if (marked.size !== pointMap.size) fail('CHECKPOINT_P1_TIMING_INCOMPLETE');
  return Object.freeze({
    successor_ack_confirmed: typeof attempt.successor_first_ack_ms === 'number',
    next_turn_ready: typeof attempt.playout_receipt_accepted_ms === 'number',
    downlink_opened_before_successor_ack: typeof attempt.successor_first_ack_ms === 'number' && attempt.downlink_opened_ms < attempt.successor_first_ack_ms,
    product_owner: 'ProductP1VoiceRouteOwner',
    successor_ack_observed: Object.freeze({ value_ms: attempt.successor_first_ack_ms, truth_class: 'measured' }),
    interaction_id: attempt.interaction_id,
    response_id: attempt.response_id,
    unit_id: attempt.unit_id,
  });
}

export async function runControlledOwnerAttempt(config, dependencies = {}) {
  const clock = dependencies.clock ?? new ControlledMonotonicClock();
  return runCheckpointAttempt(config, {
    clock,
    deliverPresentation: ({ workload }) => deliverWithRealP2Owner(config, workload, clock, dependencies),
    playResponse: ({ workload, mark, p2 }) => playWithRealP1Owner(config, workload, clock, mark, p2),
  });
}
