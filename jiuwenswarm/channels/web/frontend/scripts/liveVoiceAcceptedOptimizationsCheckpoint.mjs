import {
  CHECKPOINT_CONTROLLED_TARGETS,
  CHECKPOINT_WORKLOADS,
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
