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

const SCHEMA_VERSION = 'live-voice.p2-notification-causal-report.v0';
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
  const counts = Array.isArray(input?.notificationCounts) ? [...input.notificationCounts] : [];
  if (
    !RUN_ID.test(input?.runId ?? '') ||
    !GIT_COMMIT.test(input?.gitCommit ?? '') ||
    counts.length === 0 ||
    counts.length > 16 ||
    counts.some(count => canonicalInteger(count, 1, 256) === null) ||
    new Set(counts).size !== counts.length ||
    canonicalInteger(input?.sampleCount, 1, 30) === null ||
    canonicalInteger(input?.delayMs, 0, 1_000) === null ||
    canonicalInteger(input?.notificationBatchSize, 2, 16) === null ||
    typeof input?.now !== 'function' ||
    typeof input?.sleep !== 'function'
  ) {
    fail('P2_BENCHMARK_INPUT_INVALID');
  }
  return Object.freeze({
    runId: input.runId,
    gitCommit: input.gitCommit,
    notificationCounts: Object.freeze(counts),
    sampleCount: input.sampleCount,
    delayMs: input.delayMs,
    notificationBatchSize: input.notificationBatchSize,
    now: input.now,
    sleep: input.sleep,
  });
}

function bindingFor(notificationCount, attempt) {
  return Object.freeze({
    session_id: `p2-benchmark-session-${notificationCount}-${attempt}`,
    correlation_id: `p2-benchmark-correlation-${notificationCount}-${attempt}`,
    interaction_id: `p2-benchmark-interaction-${notificationCount}-${attempt}`,
    activation_id: `p2-benchmark-activation-${notificationCount}-${attempt}`,
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
  const response = {
    interaction_id: binding.interaction_id,
    response_id: `p2-benchmark-response-${notificationCount}`,
    response_generation: 0,
  };
  return boundResult(binding, 'notification', {
    kind: 'agent.output',
    request_id: requestId,
    round_id: `p2-benchmark-round-${notificationCount}`,
    response,
    agent_event: {
      seq: sequence - 1,
      event_type: final ? 'chat.final' : 'chat.delta',
      source_provenance: 'p2.causal.benchmark',
      text: null,
      capability: null,
      error_reason: null,
    },
    source_event: null,
    progress_event: null,
    presentation_unit: final
      ? {
          surface: 'text',
          unit_id: `p2-benchmark-final-${notificationCount}`,
          seq: 0,
          source_start_utf8: 0,
          source_end_utf8: 1,
          content_ref: `sha256:${'0'.repeat(64)}`,
        }
      : null,
    error_reason: null,
    publish_seq: sequence - 1,
  });
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
  let delivered = 0;
  let notificationRpcCount = 0;
  const owner = new ProductWebP2ActivationOwner({
    enabled: true,
    notification_batch_size: config.notificationBatchSize,
    request: async (method, params, requestId) => {
      if (!sameBinding(params, binding)) fail('P2_BENCHMARK_BINDING_MISMATCH');
      if (method === PRODUCT_P2_ACTIVATE_METHOD) return boundResult(binding, 'active', { replayed: false });
      if (method === PRODUCT_P2_CLOSE_METHOD) return boundResult(binding, 'closed');
      if (method === PRODUCT_P2_NOTIFICATION_NEXT_METHOD) {
        if (params.notification_sequence !== delivered + 1 || delivered >= notificationCount) {
          fail('P2_BENCHMARK_SEQUENCE_MISMATCH');
        }
        const requestedBatchSize = params.max_notifications ?? 1;
        if (
          canonicalInteger(requestedBatchSize, 1, config.notificationBatchSize) === null ||
          (requestedBatchSize > 1 && requestedBatchSize !== config.notificationBatchSize)
        ) {
          fail('P2_BENCHMARK_BATCH_SIZE_MISMATCH');
        }
        await config.sleep(config.delayMs);
        notificationRpcCount += 1;
        const batchCount = Math.min(requestedBatchSize, notificationCount - delivered);
        const notifications = [];
        for (let index = 0; index < batchCount; index += 1) {
          delivered += 1;
          notifications.push(notificationResult(binding, requestId, delivered, notificationCount).result);
        }
        return requestedBatchSize === 1 ? { ok: true, result: notifications[0] } : boundResult(binding, 'notification_batch', { notifications });
      }
      if (
        method === PRODUCT_P2_SUBMIT_METHOD ||
        method === PRODUCT_P2_PRESENTATION_ACK_METHOD ||
        method === PRODUCT_P2_BARGE_IN_METHOD ||
        method.startsWith('live_voice.composition.p3') ||
        method.startsWith('live_voice.task.')
      ) {
        fail('P2_BENCHMARK_FORBIDDEN_EFFECT');
      }
      fail('P2_BENCHMARK_UNEXPECTED_METHOD');
    },
  });

  await owner.start(binding);
  const startedAt = config.now();
  let finalSeen = false;
  for (let sequence = 1; sequence <= notificationCount; sequence += 1) {
    const notification = await owner.nextNotification();
    const event = notification.agent_event;
    const presentation = notification.presentation_unit;
    if (notification.publish_seq !== sequence - 1 || event?.seq !== sequence - 1) {
      fail('P2_BENCHMARK_NOTIFICATION_ORDER_INVALID');
    }
    const shouldBeFinal = sequence === notificationCount;
    if ((event?.event_type === 'chat.final') !== shouldBeFinal || (presentation !== null) !== shouldBeFinal || finalSeen) {
      fail('P2_BENCHMARK_FINAL_INVALID');
    }
    finalSeen = shouldBeFinal;
  }
  const completedAt = config.now();
  await owner.close();
  if (!finalSeen || delivered !== notificationCount || notificationRpcCount !== notificationCount) {
    fail('P2_BENCHMARK_ATTEMPT_INCOMPLETE');
  }
  const duration = completedAt - startedAt;
  if (!Number.isFinite(duration) || duration < 0) fail('P2_BENCHMARK_CLOCK_INVALID');
  return Object.freeze({ duration, notificationRpcCount });
}

function nearestRank(samples, percentile) {
  const sorted = [...samples].sort((left, right) => left - right);
  return sorted[Math.ceil((percentile / 100) * sorted.length) - 1];
}

function rounded(value) {
  return Math.round(value * 1_000) / 1_000;
}

export async function runP2NotificationCausalBenchmark(input) {
  const config = validateRunInput(input);
  const rows = [];
  for (const notificationCount of config.notificationCounts) {
    const samples = [];
    let notificationRpcCount = 0;
    for (let attempt = 0; attempt < config.sampleCount; attempt += 1) {
      const result = await runAttempt(config, notificationCount, attempt);
      samples.push(rounded(result.duration));
      notificationRpcCount += result.notificationRpcCount;
    }
    rows.push(
      Object.freeze({
        notification_count: notificationCount,
        attempts: config.sampleCount,
        successful: config.sampleCount,
        notification_rpc_count: notificationRpcCount,
        expected_serial_ms: notificationCount * config.delayMs,
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
    sample_count: config.sampleCount,
    delay_ms: config.delayMs,
    batch_size: config.notificationBatchSize,
    notification_counts: config.notificationCounts,
    rows: Object.freeze(rows),
    forbidden_effects: FORBIDDEN_EFFECTS,
  });
}

export function parseP2NotificationBenchmarkArgs(argv) {
  if (!Array.isArray(argv) || argv.length % 2 !== 0) fail('P2_BENCHMARK_ARGUMENT_INVALID');
  const allowed = new Set(['--output', '--git-commit', '--run-id', '--samples', '--delay-ms', '--batch-size']);
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!allowed.has(key) || values.has(key) || typeof value !== 'string' || value === '') {
      fail('P2_BENCHMARK_ARGUMENT_INVALID');
    }
    values.set(key, value);
  }
  if (values.size !== allowed.size) fail('P2_BENCHMARK_ARGUMENT_INVALID');
  const output = values.get('--output');
  const gitCommit = values.get('--git-commit');
  const runId = values.get('--run-id');
  const sampleCount = canonicalInteger(values.get('--samples'), 1, 30);
  const delayMs = canonicalInteger(values.get('--delay-ms'), 0, 1_000);
  const notificationBatchSize = canonicalInteger(values.get('--batch-size'), 2, 16);
  if (
    typeof output !== 'string' ||
    !path.isAbsolute(output) ||
    output.includes('\n') ||
    output.includes('\r') ||
    !GIT_COMMIT.test(gitCommit ?? '') ||
    !RUN_ID.test(runId ?? '') ||
    sampleCount === null ||
    delayMs === null ||
    notificationBatchSize === null
  ) {
    fail('P2_BENCHMARK_ARGUMENT_INVALID');
  }
  return Object.freeze({ output, gitCommit, runId, sampleCount, delayMs, notificationBatchSize });
}

export async function writeP2NotificationCausalReport(output, report) {
  try {
    const handle = await fs.open(output, 'wx', 0o600);
    try {
      await handle.writeFile(`${JSON.stringify(report)}\n`, 'utf8');
    } finally {
      await handle.close();
    }
  } catch (error) {
    if (error?.code === 'EEXIST') fail('P2_BENCHMARK_OUTPUT_EXISTS');
    throw error;
  }
}

export async function main(argv = process.argv.slice(2)) {
  const args = parseP2NotificationBenchmarkArgs(argv);
  const actualCommit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { encoding: 'utf8' });
  if (actualCommit !== args.gitCommit || status !== '') fail('P2_BENCHMARK_SOURCE_NOT_CLEAN');
  const report = await runP2NotificationCausalBenchmark({
    runId: args.runId,
    gitCommit: args.gitCommit,
    notificationCounts: [10, 50, 100],
    sampleCount: args.sampleCount,
    delayMs: args.delayMs,
    notificationBatchSize: args.notificationBatchSize,
    now: () => performance.now(),
    sleep: delayMs => new Promise(resolve => setTimeout(resolve, delayMs)),
  });
  await writeP2NotificationCausalReport(args.output, report);
  process.stdout.write(`${JSON.stringify({ run_id: args.runId })}\n`);
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  main().catch(() => {
    process.stderr.write('P2_BENCHMARK_FAILED\n');
    process.exitCode = 1;
  });
}
