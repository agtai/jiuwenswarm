import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

import {
  PRODUCT_P2_ACTIVATE_METHOD,
  PRODUCT_P2_BARGE_IN_METHOD,
  PRODUCT_P2_CLOSE_METHOD,
  PRODUCT_P2_NOTIFICATION_NEXT_METHOD,
  PRODUCT_P2_PRESENTATION_ACK_METHOD,
  PRODUCT_P2_SUBMIT_METHOD,
  ProductWebP2ActivationOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/productWebActivation.js';

const SCHEMA_VERSION = 'live-voice.p2-notification-ab-report.v0';
const NOTIFICATION_COUNTS = Object.freeze([10, 50, 100]);
const BATCH_SIZE = 16;
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const GIT_COMMIT = /^[0-9a-f]{40}$/;
const FORBIDDEN_EFFECTS = Object.freeze({
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

function fail(code) {
  throw new Error(code);
}

function canonicalInteger(value, minimum, maximum) {
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) && value >= minimum && value <= maximum ? value : null;
  }
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

function validateRunInput(input) {
  if (
    !RUN_ID.test(input?.runId ?? '') ||
    !GIT_COMMIT.test(input?.gitCommit ?? '') ||
    !['off', 'on'].includes(input?.mode) ||
    canonicalInteger(input?.sampleCount, 1, 10) === null ||
    canonicalInteger(input?.delayMs, 0, 1_000) === null ||
    typeof input?.now !== 'function' ||
    typeof input?.sleep !== 'function'
  ) {
    fail('P2_AB_BENCHMARK_INPUT_INVALID');
  }
  return Object.freeze({
    runId: input.runId,
    gitCommit: input.gitCommit,
    mode: input.mode,
    sampleCount: input.sampleCount,
    delayMs: input.delayMs,
    now: input.now,
    sleep: input.sleep,
  });
}

function bindingFor(notificationCount, attempt) {
  return Object.freeze({
    session_id: `p2-ab-session-${notificationCount}-${attempt}`,
    correlation_id: `p2-ab-correlation-${notificationCount}-${attempt}`,
    interaction_id: `p2-ab-interaction-${notificationCount}-${attempt}`,
    activation_id: `p2-ab-activation-${notificationCount}-${attempt}`,
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

function notificationResult(binding, requestId, sequence, notificationCount) {
  const final = sequence === notificationCount;
  return boundResult(binding, 'notification', {
    kind: 'agent.output',
    request_id: requestId,
    round_id: `p2-ab-round-${notificationCount}`,
    response: {
      interaction_id: binding.interaction_id,
      response_id: `p2-ab-response-${notificationCount}`,
      response_generation: 0,
    },
    agent_event: {
      seq: sequence - 1,
      event_type: final ? 'chat.final' : 'chat.delta',
      source_provenance: 'p2.ab.benchmark',
      text: null,
      capability: null,
      error_reason: null,
    },
    source_event: null,
    progress_event: null,
    presentation_unit: final
      ? {
          surface: 'text',
          unit_id: `p2-ab-final-${notificationCount}`,
          seq: 0,
          source_start_utf8: 0,
          source_end_utf8: 1,
          content_ref: `sha256:${'0'.repeat(64)}`,
        }
      : null,
    error_reason: null,
    publish_seq: sequence - 1,
  }).result;
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

async function runAttempt(config, notificationCount, attempt) {
  const binding = bindingFor(notificationCount, attempt);
  const batchEnabled = config.mode === 'on';
  let delivered = 0;
  let notificationRpcCount = 0;
  const ownerInput = {
    enabled: true,
    notification_batch_size: batchEnabled ? BATCH_SIZE : 1,
    request: async (method, params, requestId) => {
      if (!sameBinding(params, binding)) fail('P2_AB_BENCHMARK_BINDING_MISMATCH');
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return boundResult(binding, 'active', { replayed: false });
      if (method === PRODUCT_P2_CLOSE_METHOD) return boundResult(binding, 'closed');
      if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
        const hasBatchParameter = Object.hasOwn(params, 'max_notifications');
        if (
          params.notification_sequence !== notificationRpcCount + 1 ||
          delivered >= notificationCount ||
          hasBatchParameter !== batchEnabled ||
          (batchEnabled && params.max_notifications !== BATCH_SIZE)
        ) {
          fail('P2_AB_BENCHMARK_REQUEST_INVALID');
        }
        await config.sleep(config.delayMs);
        notificationRpcCount += 1;
        const requested = batchEnabled ? BATCH_SIZE : 1;
        const itemCount = Math.min(requested, notificationCount - delivered);
        const notifications = [];
        for (let index = 0; index < itemCount; index += 1) {
          delivered += 1;
          notifications.push(notificationResult(binding, requestId, delivered, notificationCount));
        }
        return batchEnabled ? boundResult(binding, 'notification_batch', { notifications }) : { ok: true, result: notifications[0] };
      }
      if (
        method === PRODUCT_P2_SUBMIT_METHOD ||
        method === PRODUCT_P2_PRESENTATION_ACK_METHOD ||
        method === PRODUCT_P2_BARGE_IN_METHOD ||
        method.startsWith('live_voice.composition.p3') ||
        method.startsWith('live_voice.task.') ||
        method.startsWith('agent.') ||
        method.startsWith('tool.') ||
        method.startsWith('history.')
      ) {
        fail('P2_AB_BENCHMARK_FORBIDDEN_EFFECT');
      }
      fail('P2_AB_BENCHMARK_UNEXPECTED_METHOD');
    },
  };
  const owner = new ProductWebP2ActivationOwner(ownerInput);

  await owner.start(binding);
  const startedAt = config.now();
  let finalSeen = false;
  for (let sequence = 1; sequence <= notificationCount; sequence += 1) {
    const notification = await owner.nextNotification();
    const shouldBeFinal = sequence === notificationCount;
    if (
      notification.publish_seq !== sequence - 1 ||
      notification.agent_event?.seq !== sequence - 1 ||
      (notification.agent_event?.event_type === 'chat.final') !== shouldBeFinal ||
      (notification.presentation_unit !== null) !== shouldBeFinal ||
      finalSeen
    ) {
      fail('P2_AB_BENCHMARK_NOTIFICATION_INVALID');
    }
    finalSeen = shouldBeFinal;
  }
  const durationMs = config.now() - startedAt;
  await owner.close();
  if (!finalSeen || delivered !== notificationCount || !Number.isFinite(durationMs) || durationMs < 0) {
    fail('P2_AB_BENCHMARK_ATTEMPT_INCOMPLETE');
  }
  return Object.freeze({ durationMs, notificationRpcCount });
}

function nearestRank(samples, percentile) {
  const sorted = [...samples].sort((left, right) => left - right);
  return sorted[Math.ceil((percentile / 100) * sorted.length) - 1];
}

function rounded(value) {
  return Math.round(value * 1_000) / 1_000;
}

export async function runP2NotificationABBenchmark(input) {
  const config = validateRunInput(input);
  const runStartedAt = config.now();
  const rows = [];
  for (const notificationCount of NOTIFICATION_COUNTS) {
    const samples = [];
    let notificationRpcCount = 0;
    for (let attempt = 0; attempt < config.sampleCount; attempt += 1) {
      const result = await runAttempt(config, notificationCount, attempt);
      samples.push(rounded(result.durationMs));
      notificationRpcCount += result.notificationRpcCount;
    }
    rows.push(
      Object.freeze({
        notification_count: notificationCount,
        attempts: config.sampleCount,
        successful: config.sampleCount,
        notification_rpc_count: notificationRpcCount,
        rpc_count_per_attempt: notificationRpcCount / config.sampleCount,
        samples_ms: Object.freeze(samples),
        p50_ms: rounded(nearestRank(samples, 50)),
        p95_ms: rounded(nearestRank(samples, 95)),
      }),
    );
  }
  return Object.freeze({
    schema_version: SCHEMA_VERSION,
    run_id: config.runId,
    git_commit: config.gitCommit,
    source_state: 'clean',
    feature_mode: config.mode,
    effective_batch_size: config.mode === 'on' ? BATCH_SIZE : 1,
    sample_count: config.sampleCount,
    delay_ms: config.delayMs,
    notification_counts: NOTIFICATION_COUNTS,
    elapsed_ms: rounded(config.now() - runStartedAt),
    rows: Object.freeze(rows),
    forbidden_effects: FORBIDDEN_EFFECTS,
  });
}

export function compareP2NotificationABReports(offReport, onReport) {
  if (
    offReport?.feature_mode !== 'off' ||
    onReport?.feature_mode !== 'on' ||
    offReport.git_commit !== onReport.git_commit ||
    offReport.sample_count !== onReport.sample_count ||
    offReport.delay_ms !== onReport.delay_ms ||
    offReport.rows.length !== onReport.rows.length
  ) {
    fail('P2_AB_BENCHMARK_REPORT_MISMATCH');
  }
  return Object.freeze(
    offReport.rows.map((offRow, index) => {
      const onRow = onReport.rows[index];
      if (offRow.notification_count !== onRow.notification_count || onRow.p50_ms >= offRow.p50_ms) {
        fail('P2_AB_BENCHMARK_NO_IMPROVEMENT');
      }
      return Object.freeze({
        notification_count: offRow.notification_count,
        off_rpc_count_per_attempt: offRow.rpc_count_per_attempt,
        on_rpc_count_per_attempt: onRow.rpc_count_per_attempt,
        off_p50_ms: offRow.p50_ms,
        on_p50_ms: onRow.p50_ms,
        p50_reduction_percent: rounded((1 - onRow.p50_ms / offRow.p50_ms) * 100),
      });
    }),
  );
}

export function parseP2NotificationABBenchmarkArgs(argv) {
  if (!Array.isArray(argv) || argv.length % 2 !== 0) fail('P2_AB_BENCHMARK_ARGUMENT_INVALID');
  const allowed = new Set(['--output', '--git-commit', '--run-id', '--mode', '--samples', '--delay-ms']);
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!allowed.has(key) || values.has(key) || typeof value !== 'string' || value === '') {
      fail('P2_AB_BENCHMARK_ARGUMENT_INVALID');
    }
    values.set(key, value);
  }
  const output = values.get('--output');
  const gitCommit = values.get('--git-commit');
  const runId = values.get('--run-id');
  const mode = values.get('--mode');
  const sampleCount = canonicalInteger(values.get('--samples'), 1, 10);
  const delayMs = canonicalInteger(values.get('--delay-ms'), 0, 1_000);
  if (
    values.size !== allowed.size ||
    typeof output !== 'string' ||
    !path.isAbsolute(output) ||
    output.includes('\n') ||
    output.includes('\r') ||
    !GIT_COMMIT.test(gitCommit ?? '') ||
    !RUN_ID.test(runId ?? '') ||
    !['off', 'on'].includes(mode) ||
    sampleCount === null ||
    delayMs === null
  ) {
    fail('P2_AB_BENCHMARK_ARGUMENT_INVALID');
  }
  return Object.freeze({ output, gitCommit, runId, mode, sampleCount, delayMs });
}

export async function writeP2NotificationABReport(output, report) {
  try {
    const handle = await fs.open(output, 'wx', 0o600);
    try {
      await handle.writeFile(`${JSON.stringify(report)}\n`, 'utf8');
    } finally {
      await handle.close();
    }
  } catch (error) {
    if (error?.code === 'EEXIST') fail('P2_AB_BENCHMARK_OUTPUT_EXISTS');
    throw error;
  }
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseP2NotificationABBenchmarkArgs(argv);
  const actualCommit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { encoding: 'utf8' });
  if (actualCommit !== args.gitCommit || status !== '') fail('P2_AB_BENCHMARK_SOURCE_NOT_CLEAN');
  const report = await runP2NotificationABBenchmark({
    runId: args.runId,
    gitCommit: args.gitCommit,
    mode: args.mode,
    sampleCount: args.sampleCount,
    delayMs: args.delayMs,
    now: () => performance.now(),
    sleep: delayMs => new Promise(resolve => setTimeout(resolve, delayMs)),
  });
  await writeP2NotificationABReport(args.output, report);
  process.stdout.write(`${JSON.stringify({ run_id: args.runId, feature_mode: args.mode })}\n`);
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  main().catch(() => {
    process.stderr.write('P2_AB_BENCHMARK_FAILED\n');
    process.exitCode = 1;
  });
}

export { BATCH_SIZE, NOTIFICATION_COUNTS, SCHEMA_VERSION };
