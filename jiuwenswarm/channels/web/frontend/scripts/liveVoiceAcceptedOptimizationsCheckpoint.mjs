import { createHash, randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
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

  nowMs() {
    return this.#monotonicMs;
  }

  async waitMs(delayMs) {
    if (!Number.isFinite(delayMs) || delayMs < 0) throw new Error('CHECKPOINT_CLOCK_DELAY_INVALID');
    this.#monotonicMs += delayMs;
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
    const samples = canonicalInteger(values.get('--samples'), 1, 30);
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
  fail('CHECKPOINT_ARGUMENT_INVALID');
}

export async function writePrivateCheckpointReport(output, report) {
  return writePrivateJson(output, report, parseCheckpointReport, 'CHECKPOINT_REPORT_INVALID');
}

async function writePrivateJson(output, value, parser, invalidReason) {
  if (typeof output !== 'string' || !path.isAbsolute(output) || output.includes('\n') || output.includes('\r')) fail(invalidReason);
  let serialized;
  try {
    serialized = `${JSON.stringify(parser(value))}\n`;
  } catch {
    fail(invalidReason);
  }
  const temporary = `${output}.tmp-${process.pid}-${randomUUID()}`;
  let handle = null;
  try {
    handle = await fs.open(temporary, 'wx', 0o600);
    await handle.writeFile(serialized, 'utf8');
    await handle.sync();
    await handle.close();
    handle = null;
    parser(JSON.parse(await fs.readFile(temporary, 'utf8')));
    await fs.link(temporary, output);
  } catch (error) {
    if (error?.code === 'EEXIST') fail('CHECKPOINT_OUTPUT_EXISTS');
    if (error instanceof Error && error.message.startsWith('CHECKPOINT_')) throw error;
    fail(invalidReason);
  } finally {
    if (handle !== null) await handle.close().catch(() => undefined);
    await fs.unlink(temporary).catch(() => undefined);
  }
}

export async function readPrivateCheckpointReport(input) {
  try {
    return parseCheckpointReport(JSON.parse(await fs.readFile(input, 'utf8')));
  } catch (error) {
    if (error instanceof Error && error.message === 'CHECKPOINT_REPORT_INVALID') throw error;
    fail('CHECKPOINT_REPORT_INVALID');
  }
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
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
  const runnerBytes = await fs.readFile(new URL(import.meta.url));
  const runnerFingerprint = sha256(runnerBytes);
  const fixtureFingerprint = sha256(JSON.stringify(CHECKPOINT_WORKLOADS));
  const timingFingerprint = sha256(JSON.stringify(CHECKPOINT_CONTROLLED_TARGETS));
  const attempts = [];
  for (const workloadId of Object.keys(CHECKPOINT_WORKLOADS)) {
    for (let attemptIndex = 0; attemptIndex < input.samples; attemptIndex += 1) {
      attempts.push(
        await runControlledOwnerAttempt({
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
  const [a1, b, a2] = await Promise.all([
    readPrivateCheckpointReport(input.baseline_before),
    readPrivateCheckpointReport(input.candidate),
    readPrivateCheckpointReport(input.baseline_after),
  ]);
  const comparison = compareCheckpointReports(a1, b, a2);
  await writePrivateJson(input.output, comparison, parseCheckpointComparison, 'CHECKPOINT_COMPARISON_INVALID');
  return comparison;
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
    '| Workload | Stage | A1 p50 ms | B p50 ms | A2 p50 ms | B−A1 ms | B−A2 ms | B−A1 % | B−A2 % | A drift % | Truth |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|',
  ];
  for (const [workloadId, workload] of Object.entries(parsed.workloads)) {
    for (const [segment, row] of Object.entries(workload.segments)) {
      lines.push(
        `| ${workloadId} | ${segment} | ${fixed(row.a1_p50_ms)} | ${fixed(row.b_p50_ms)} | ${fixed(row.a2_p50_ms)} | ${fixed(row.b_minus_a1_ms)} | ${fixed(row.b_minus_a2_ms)} | ${fixed(row.b_minus_a1_percent)} | ${fixed(row.b_minus_a2_percent)} | ${fixed(row.baseline_drift_percent)} | DERIVED |`,
      );
    }
  }
  return `${lines.join('\n')}\n`;
}

const USAGE = `Usage: liveVoiceAcceptedOptimizationsCheckpoint <command> [options]

Commands:
  run --population A1|B|A2 --mode baseline|optimized --samples N --git-commit SHA --run-id ID --output PATH
  compare-a-b-a --baseline-before PATH --candidate PATH --baseline-after PATH --output PATH
`;

function assertExactCleanSource(expectedCommit) {
  const actualCommit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { encoding: 'utf8' });
  if (actualCommit !== expectedCommit || status !== '') fail('CHECKPOINT_SOURCE_NOT_CLEAN');
}

export async function main(argv = process.argv.slice(2)) {
  if (argv.length === 1 && argv[0] === '--help') {
    process.stdout.write(USAGE);
    return;
  }
  const args = parseAcceptedCheckpointArgs(argv);
  if (args.command === 'run') {
    assertExactCleanSource(args.git_commit);
    const report = await runAcceptedCheckpointPopulation(args);
    await writePrivateCheckpointReport(args.output, report);
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
  const suffix = `${config.workload_id}-${config.attempt_index}`;
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

function checkpointNotification(binding, requestId, publishSeq, workload) {
  const final = publishSeq === workload.notification_count - 1;
  const toolStarted = workload.id === 'W3' && publishSeq === 40;
  const toolCompleted = workload.id === 'W3' && publishSeq === 41;
  const eventType = final ? 'chat.final' : toolStarted ? 'tool_execution_started' : toolCompleted ? 'tool_execution_completed' : 'chat.delta';
  return boundResult(binding, 'notification', {
    kind: 'agent.output',
    request_id: requestId,
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
  let delivered = 0;
  let notificationRpcCount = 0;
  const observedBarriers = [];
  const batchSize = config.optimization_mode.p2_notification_batch_size;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    notification_batch_size: batchSize,
    request: async (method, params, requestId) => {
      if (!sameBinding(params, binding)) fail('CHECKPOINT_P2_BINDING_MISMATCH');
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return boundResult(binding, 'active', { replayed: false });
      if (method === PRODUCT_P2_CLOSE_METHOD) return boundResult(binding, 'closed');
      if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
        const requested = params.max_notifications ?? 1;
        if (params.notification_sequence !== notificationRpcCount + 1 || requested !== batchSize || delivered >= workload.notification_count)
          fail('CHECKPOINT_P2_SEQUENCE_INVALID');
        await clock.waitMs(CHECKPOINT_CONTROLLED_TARGETS.p2_rpc_ms);
        notificationRpcCount += 1;
        const length = batchLength(delivered, requested, workload);
        const notifications = [];
        for (let index = 0; index < length; index += 1) {
          const publishSeq = delivered;
          delivered += 1;
          const notification = checkpointNotification(binding, requestId, publishSeq, workload);
          notifications.push(typeof diagnostics.p2NotificationMutator === 'function' ? diagnostics.p2NotificationMutator(notification) : notification);
        }
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
    }
    if (!finalSeen || delivered !== workload.notification_count) fail('CHECKPOINT_P2_INCOMPLETE');
  } finally {
    try {
      await owner.close();
    } finally {
      diagnostics.onP2Close?.();
    }
  }
  return Object.freeze({
    notification_rpc_count: notificationRpcCount,
    notification_batch_count: notificationRpcCount,
    ordered_barriers: Object.freeze(observedBarriers),
  });
}

async function advanceObserved(clock, priorMs, nextMs) {
  if (typeof nextMs !== 'number' || !Number.isFinite(nextMs) || nextMs < priorMs) fail('CHECKPOINT_P1_TIMING_INVALID');
  await clock.waitMs(nextMs - priorMs);
  return nextMs;
}

async function playWithRealP1Owner(config, workload, clock, mark) {
  const report = await runTtsFirstAudioCausalBenchmark({
    runId: `checkpoint-${config.workload_id}-${config.attempt_index}`,
    gitCommit: config.source_commit,
    samples: 1,
    successorAckDelaysMs: [workload.successor_ack_delay_ms],
  });
  const attempt = report.populations[0]?.attempts[0];
  const expectedMode = config.optimization_mode.tts_successor_ack_overlap ? 'successor_ack_decoupled' : 'legacy_sequential';
  if (report.candidate_mode !== expectedMode || attempt?.outcome !== 'completed') fail('CHECKPOINT_P1_SOURCE_MODE_INVALID');
  let prior = 0;
  prior = await advanceObserved(clock, prior, attempt.downlink_opened_ms);
  mark('downlink_opened');
  prior = await advanceObserved(clock, prior, attempt.downlink_first_frame_received_ms);
  mark('first_frame_received');
  prior = await advanceObserved(clock, prior, attempt.first_source_scheduled_ms);
  mark('first_source_scheduled');
  await clock.waitMs(workload.playout_duration_ms);
  mark('playout_completed');
  mark('confirmed_ack_and_next_turn_ready');
  return Object.freeze({
    successor_ack_confirmed: typeof attempt.successor_first_ack_ms === 'number',
    next_turn_ready: typeof attempt.playout_receipt_accepted_ms === 'number',
    downlink_opened_before_successor_ack: typeof attempt.successor_first_ack_ms === 'number' && attempt.downlink_opened_ms < attempt.successor_first_ack_ms,
    product_owner: 'ProductP1VoiceRouteOwner',
  });
}

export async function runControlledOwnerAttempt(config, dependencies = {}) {
  const clock = dependencies.clock ?? new ControlledMonotonicClock();
  return runCheckpointAttempt(config, {
    clock,
    deliverPresentation: ({ workload }) => deliverWithRealP2Owner(config, workload, clock, dependencies),
    playResponse: ({ workload, mark }) => playWithRealP1Owner(config, workload, clock, mark),
  });
}
