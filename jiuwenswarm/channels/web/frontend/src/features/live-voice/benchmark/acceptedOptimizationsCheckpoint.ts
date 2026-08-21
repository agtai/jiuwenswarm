export const CHECKPOINT_TRUTH_CLASSES = Object.freeze(['measured', 'controlled', 'derived', 'estimated', 'out_of_scope'] as const);
export type CheckpointTruthClass = (typeof CHECKPOINT_TRUTH_CLASSES)[number];

export const CHECKPOINT_POPULATIONS = Object.freeze(['A1', 'B', 'A2'] as const);
export type CheckpointPopulation = (typeof CHECKPOINT_POPULATIONS)[number];

export const CHECKPOINT_POINTS = Object.freeze([
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
] as const);
export type CheckpointPoint = (typeof CHECKPOINT_POINTS)[number];

export const CHECKPOINT_SEGMENTS = Object.freeze({
  stt_settlement: Object.freeze(['speech_end', 'stt_final'] as const),
  admission: Object.freeze(['stt_final', 'admission_accepted'] as const),
  agent_model: Object.freeze(['admission_accepted', 'model_complete_and_notifications_enqueued'] as const),
  p2_final_delivery: Object.freeze(['model_complete_and_notifications_enqueued', 'presentation_final_consumed'] as const),
  tts_generation: Object.freeze(['presentation_final_consumed', 'tts_ready_and_successor_capture_requested'] as const),
  tts_ready_to_downlink: Object.freeze(['tts_ready_and_successor_capture_requested', 'downlink_opened'] as const),
  downlink_to_first_source: Object.freeze(['downlink_opened', 'first_source_scheduled'] as const),
  first_source_to_playout: Object.freeze(['first_source_scheduled', 'playout_completed'] as const),
  playout_to_confirmed_ack: Object.freeze(['playout_completed', 'confirmed_ack_and_next_turn_ready'] as const),
  round_total: Object.freeze(['speech_end', 'confirmed_ack_and_next_turn_ready'] as const),
});
export type CheckpointSegment = keyof typeof CHECKPOINT_SEGMENTS;

export const CHECKPOINT_WORKLOADS = Object.freeze({
  W1: Object.freeze({
    id: 'W1',
    recognized_prompt: 'In two short sentences, please introduce Paris.',
    notification_count: 10,
    successor_ack_delay_ms: 250,
    playout_duration_ms: 3000,
    tool_barriers: Object.freeze([] as number[]),
  }),
  W2: Object.freeze({
    id: 'W2',
    recognized_prompt: 'Plan a three-day itinerary for Paris with morning, afternoon, and evening activities.',
    notification_count: 50,
    successor_ack_delay_ms: 750,
    playout_duration_ms: 6000,
    tool_barriers: Object.freeze([] as number[]),
  }),
  W3: Object.freeze({
    id: 'W3',
    recognized_prompt: 'What is the weather today in Paris, and should I carry an umbrella?',
    notification_count: 100,
    successor_ack_delay_ms: 750,
    playout_duration_ms: 4000,
    tool_barriers: Object.freeze([40, 41]),
  }),
});
export type CheckpointWorkloadId = keyof typeof CHECKPOINT_WORKLOADS;

export const CHECKPOINT_CONTROLLED_TARGETS = Object.freeze({
  stt_settlement_ms: 400,
  admission_ms: 500,
  agent_model_ms: 2000,
  tool_interval_ms: 1000,
  tts_generation_ms: 1000,
  p2_rpc_ms: 85,
});

export const CHECKPOINT_B_BATCH_BOUND = 16;
export const CHECKPOINT_FORBIDDEN_EFFECTS = Object.freeze({
  agent: 0,
  tool: 0,
  task: 0,
  history: 0,
  network: 0,
  provider: 0,
  microphone: 0,
});

export interface CheckpointClock {
  nowMs(): number;
  waitMs(delayMs: number): Promise<void>;
}

export interface CheckpointOptimizationMode {
  readonly p2_notification_batch_size: 1 | 16;
  readonly tts_successor_ack_overlap: boolean;
}

export interface CheckpointAttemptConfig {
  readonly run_id: string;
  readonly population: CheckpointPopulation;
  readonly workload_id: CheckpointWorkloadId;
  readonly attempt_index: number;
  readonly source_commit: string;
  readonly runner_fingerprint: string;
  readonly fixture_fingerprint: string;
  readonly timing_fingerprint: string;
  readonly optimization_mode: CheckpointOptimizationMode;
}

export interface CheckpointP2Facts {
  readonly truth_class: 'measured';
  readonly notification_rpc_count: number;
  readonly notification_batch_count: number;
  readonly ordered_barriers: readonly number[];
  readonly batches: readonly Readonly<{
    rpc_index: number;
    start_publish_seq: number;
    end_publish_seq: number;
    count: number;
    duration_ms: number;
  }>[];
  readonly response: Readonly<{
    session_id: string;
    correlation_id: string;
    interaction_id: string;
    activation_id: string;
    response_id: string;
    response_generation: number;
    unit_id: string;
  }>;
}

export interface CheckpointP1Facts {
  readonly successor_ack_confirmed: boolean;
  readonly next_turn_ready: boolean;
  readonly downlink_opened_before_successor_ack: boolean;
  readonly product_owner: 'ProductP1VoiceRouteOwner';
  readonly successor_ack_observed: Readonly<{ value_ms: number; truth_class: 'measured' }>;
  readonly interaction_id: string;
  readonly response_id: string;
  readonly unit_id: string;
}

export interface CheckpointAttemptDependencies {
  readonly clock: CheckpointClock;
  deliverPresentation(input: Readonly<{ workload: (typeof CHECKPOINT_WORKLOADS)[CheckpointWorkloadId] }>): Promise<CheckpointP2Facts>;
  playResponse(
    input: Readonly<{
      workload: (typeof CHECKPOINT_WORKLOADS)[CheckpointWorkloadId];
      mark(point: CheckpointPoint): void;
      p2: CheckpointP2Facts;
    }>,
  ): Promise<CheckpointP1Facts>;
}

export interface CheckpointEvent {
  readonly point: CheckpointPoint;
  readonly monotonic_ms: number;
  readonly truth_class: 'measured';
}

export interface CheckpointDuration {
  readonly duration_ms: number;
  readonly truth_class: 'measured';
}

export interface CheckpointAttempt {
  readonly run_id: string;
  readonly population: CheckpointPopulation;
  readonly workload_id: CheckpointWorkloadId;
  readonly attempt_index: number;
  readonly source_commit: string;
  readonly runner_fingerprint: string;
  readonly fixture_fingerprint: string;
  readonly timing_fingerprint: string;
  readonly optimization_mode: CheckpointOptimizationMode;
  readonly outcome: 'completed' | 'invalid' | 'failed' | 'unknown';
  readonly reason: string | null;
  readonly events: readonly CheckpointEvent[];
  readonly segments: Readonly<Partial<Record<CheckpointSegment, CheckpointDuration>>>;
  readonly controlled_targets: Readonly<Record<string, Readonly<{ value_ms: number; truth_class: 'controlled' }>>>;
  readonly controlled_observations: Readonly<{
    stt_settlement: Readonly<{ value_ms: number | null; truth_class: 'measured' }>;
    admission: Readonly<{ value_ms: number | null; truth_class: 'measured' }>;
    agent_model: Readonly<{ value_ms: number | null; truth_class: 'measured' }>;
    tool_interval: Readonly<{ value_ms: number | null; truth_class: 'measured' }>;
    tts_generation: Readonly<{ value_ms: number | null; truth_class: 'measured' }>;
  }>;
  readonly p2: CheckpointP2Facts | null;
  readonly p1: CheckpointP1Facts | null;
}

class AttemptInvalid extends Error {
  constructor(readonly reason: string) {
    super(reason);
  }
}

function frozenControlledTargets(workloadId: CheckpointWorkloadId): CheckpointAttempt['controlled_targets'] {
  const targets: [string, number][] = [
    ...(Object.entries(CHECKPOINT_CONTROLLED_TARGETS) as [string, number][]),
    ['successor_ack_ms', CHECKPOINT_WORKLOADS[workloadId].successor_ack_delay_ms],
    ['playout_ms', CHECKPOINT_WORKLOADS[workloadId].playout_duration_ms],
  ];
  return Object.freeze(Object.fromEntries(targets.map(([name, value_ms]) => [name, Object.freeze({ value_ms, truth_class: 'controlled' as const })])));
}

function safeNow(clock: CheckpointClock): number {
  const value = clock.nowMs();
  if (!Number.isFinite(value) || value < 0) throw new AttemptInvalid('MONOTONIC_CLOCK_INVALID');
  return value;
}

async function controlledWait(clock: CheckpointClock, targetMs: number): Promise<number> {
  const started = safeNow(clock);
  await clock.waitMs(targetMs);
  const elapsed = safeNow(clock) - started;
  if (elapsed < targetMs) throw new AttemptInvalid('CONTROLLED_WAIT_EARLY');
  if (elapsed > targetMs + Math.max(25, targetMs * 0.05)) throw new AttemptInvalid('CONTROLLED_WAIT_LATE');
  return elapsed;
}

function measuredSegments(events: readonly CheckpointEvent[]): CheckpointAttempt['segments'] {
  const byPoint = new Map(events.map(event => [event.point, event.monotonic_ms]));
  const segments: Partial<Record<CheckpointSegment, CheckpointDuration>> = {};
  for (const [name, [start, end]] of Object.entries(CHECKPOINT_SEGMENTS) as [CheckpointSegment, readonly [CheckpointPoint, CheckpointPoint]][]) {
    const startMs = byPoint.get(start);
    const endMs = byPoint.get(end);
    if (startMs === undefined || endMs === undefined) continue;
    segments[name] = Object.freeze({ duration_ms: endMs - startMs, truth_class: 'measured' });
  }
  return Object.freeze(segments);
}

export async function runCheckpointAttempt(config: CheckpointAttemptConfig, dependencies: CheckpointAttemptDependencies): Promise<CheckpointAttempt> {
  const workload = CHECKPOINT_WORKLOADS[config.workload_id];
  const events: CheckpointEvent[] = [];
  let p2: CheckpointP2Facts | null = null;
  let p1: CheckpointP1Facts | null = null;
  const controlledObserved: Record<'stt_settlement' | 'admission' | 'agent_model' | 'tool_interval' | 'tts_generation', number | null> = {
    stt_settlement: null,
    admission: null,
    agent_model: null,
    tool_interval: null,
    tts_generation: null,
  };

  const mark = (point: CheckpointPoint): void => {
    const expected = CHECKPOINT_POINTS[events.length];
    if (point !== expected) throw new AttemptInvalid('EVENT_ORDER_INVALID');
    const monotonic_ms = safeNow(dependencies.clock);
    const previous = events.length === 0 ? undefined : events[events.length - 1].monotonic_ms;
    if (previous !== undefined && monotonic_ms < previous) throw new AttemptInvalid('MONOTONIC_CLOCK_REWOUND');
    events.push(Object.freeze({ point, monotonic_ms, truth_class: 'measured' }));
  };

  let outcome: CheckpointAttempt['outcome'] = 'completed';
  let reason: string | null = null;
  try {
    mark('speech_end');
    controlledObserved.stt_settlement = await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.stt_settlement_ms);
    mark('stt_final');
    controlledObserved.admission = await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.admission_ms);
    mark('admission_accepted');
    if (config.workload_id === 'W3') {
      controlledObserved.tool_interval = await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.tool_interval_ms);
      const remainder = await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.agent_model_ms - CHECKPOINT_CONTROLLED_TARGETS.tool_interval_ms);
      controlledObserved.agent_model = controlledObserved.tool_interval + remainder;
    } else {
      controlledObserved.agent_model = await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.agent_model_ms);
    }
    mark('model_complete_and_notifications_enqueued');
    p2 = Object.freeze(await dependencies.deliverPresentation({ workload }));
    mark('presentation_final_consumed');
    controlledObserved.tts_generation = await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.tts_generation_ms);
    mark('tts_ready_and_successor_capture_requested');
    p1 = Object.freeze(await dependencies.playResponse({ workload, mark, p2 }));
    if (events.length !== CHECKPOINT_POINTS.length || !p1.successor_ack_confirmed || !p1.next_turn_ready)
      throw new AttemptInvalid('ATTEMPT_SETTLEMENT_INCOMPLETE');
  } catch (error) {
    if (error instanceof AttemptInvalid) {
      outcome = 'invalid';
      reason = error.reason;
    } else {
      outcome = 'unknown';
      reason = 'CHECKPOINT_DEPENDENCY_FAILED';
    }
  }

  return Object.freeze({
    run_id: config.run_id,
    population: config.population,
    workload_id: config.workload_id,
    attempt_index: config.attempt_index,
    source_commit: config.source_commit,
    runner_fingerprint: config.runner_fingerprint,
    fixture_fingerprint: config.fixture_fingerprint,
    timing_fingerprint: config.timing_fingerprint,
    optimization_mode: Object.freeze({ ...config.optimization_mode }),
    outcome,
    reason,
    events: Object.freeze([...events]),
    segments: measuredSegments(events),
    controlled_targets: frozenControlledTargets(config.workload_id),
    controlled_observations: Object.freeze(
      Object.fromEntries(Object.entries(controlledObserved).map(([name, value_ms]) => [name, Object.freeze({ value_ms, truth_class: 'measured' as const })])),
    ) as CheckpointAttempt['controlled_observations'],
    p2,
    p1,
  });
}

export interface CheckpointReportConfig {
  readonly run_id: string;
  readonly population: CheckpointPopulation;
  readonly source_commit: string;
  readonly source_clean: boolean;
  readonly runner_fingerprint: string;
  readonly fixture_fingerprint: string;
  readonly timing_fingerprint: string;
  readonly samples_per_workload: number;
  readonly optimization_mode: CheckpointOptimizationMode;
}

export interface CheckpointOutcomeSummary {
  readonly intended: number;
  readonly attempts: number;
  readonly completed: number;
  readonly invalid: number;
  readonly failed: number;
  readonly unknown: number;
  readonly missing: number;
}

export interface CheckpointSegmentSummary {
  readonly truth_class: 'measured';
  readonly samples_ms: readonly number[];
  readonly p50_ms: number | null;
  readonly p95_ms: number | null;
}

export interface CheckpointWorkloadSummary {
  readonly outcomes: CheckpointOutcomeSummary;
  readonly segments: Readonly<Record<CheckpointSegment, CheckpointSegmentSummary>>;
}

export interface CheckpointReport {
  readonly schema_version: 'live-voice.accepted-optimizations-checkpoint.v0';
  readonly lane: 'deterministic_owner_checkpoint';
  readonly run_id: string;
  readonly population: CheckpointPopulation;
  readonly source_commit: string;
  readonly source_clean: boolean;
  readonly runner_fingerprint: string;
  readonly fixture_fingerprint: string;
  readonly timing_fingerprint: string;
  readonly samples_per_workload: number;
  readonly optimization_mode: CheckpointOptimizationMode;
  readonly forbidden_effects: typeof CHECKPOINT_FORBIDDEN_EFFECTS;
  readonly attempts: readonly CheckpointAttempt[];
  readonly summaries: Readonly<Record<CheckpointWorkloadId, CheckpointWorkloadSummary>>;
}

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SHA40 = /^[0-9a-f]{40}$/;
const SHA64 = /^[0-9a-f]{64}$/;
const OPTIMIZATION_MODE_KEYS = Object.freeze(['p2_notification_batch_size', 'tts_successor_ack_overlap']);

function validOptimizationMode(value: unknown): value is CheckpointOptimizationMode {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    exactKeys(value as Record<string, unknown>, OPTIMIZATION_MODE_KEYS) &&
    ((value as CheckpointOptimizationMode).p2_notification_batch_size === 1 || (value as CheckpointOptimizationMode).p2_notification_batch_size === 16) &&
    typeof (value as CheckpointOptimizationMode).tts_successor_ack_overlap === 'boolean'
  );
}

function reportViolation(reason: string): never {
  throw new Error(reason);
}

function validateReportConfig(config: CheckpointReportConfig): void {
  if (
    !TOKEN.test(config.run_id) ||
    !CHECKPOINT_POPULATIONS.includes(config.population) ||
    !SHA40.test(config.source_commit) ||
    config.source_clean !== true ||
    !SHA64.test(config.runner_fingerprint) ||
    !SHA64.test(config.fixture_fingerprint) ||
    !SHA64.test(config.timing_fingerprint) ||
    !Number.isSafeInteger(config.samples_per_workload) ||
    config.samples_per_workload < 1 ||
    config.samples_per_workload > 30 ||
    !validOptimizationMode(config.optimization_mode)
  )
    reportViolation('CHECKPOINT_REPORT_CONFIG_INVALID');
}

function directSegmentsForCompletedAttempt(attempt: CheckpointAttempt): Readonly<Record<CheckpointSegment, CheckpointDuration>> {
  if (attempt.events.length !== CHECKPOINT_POINTS.length) reportViolation('CHECKPOINT_ATTEMPT_EVENTS_INVALID');
  for (let index = 0; index < CHECKPOINT_POINTS.length; index += 1) {
    const event = attempt.events[index];
    if (event.point !== CHECKPOINT_POINTS[index] || event.truth_class !== 'measured' || !Number.isFinite(event.monotonic_ms) || event.monotonic_ms < 0)
      reportViolation('CHECKPOINT_ATTEMPT_EVENTS_INVALID');
    if (index > 0 && event.monotonic_ms < attempt.events[index - 1].monotonic_ms) reportViolation('CHECKPOINT_ATTEMPT_EVENTS_INVALID');
  }
  const direct = measuredSegments(attempt.events);
  for (const name of Object.keys(CHECKPOINT_SEGMENTS) as CheckpointSegment[])
    if (direct[name] === undefined) reportViolation('CHECKPOINT_ATTEMPT_SEGMENTS_INVALID');
  return direct as Readonly<Record<CheckpointSegment, CheckpointDuration>>;
}

function nearestRank(values: readonly number[], percentile: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.max(0, Math.ceil(percentile * sorted.length) - 1)];
}

function buildWorkloadSummary(workloadId: CheckpointWorkloadId, attempts: readonly CheckpointAttempt[], intended: number): CheckpointWorkloadSummary {
  const selected = attempts.filter(attempt => attempt.workload_id === workloadId);
  if (selected.length > intended) reportViolation('CHECKPOINT_ATTEMPT_COUNT_INVALID');
  const completed = selected.filter(attempt => attempt.outcome === 'completed');
  const direct = completed.map(directSegmentsForCompletedAttempt);
  const segments = {} as Record<CheckpointSegment, CheckpointSegmentSummary>;
  for (const name of Object.keys(CHECKPOINT_SEGMENTS) as CheckpointSegment[]) {
    const samples = direct.map(item => item[name].duration_ms);
    segments[name] = Object.freeze({
      truth_class: 'measured',
      samples_ms: Object.freeze(samples),
      p50_ms: nearestRank(samples, 0.5),
      p95_ms: nearestRank(samples, 0.95),
    });
  }
  return Object.freeze({
    outcomes: Object.freeze({
      intended,
      attempts: selected.length,
      completed: completed.length,
      invalid: selected.filter(attempt => attempt.outcome === 'invalid').length,
      failed: selected.filter(attempt => attempt.outcome === 'failed').length,
      unknown: selected.filter(attempt => attempt.outcome === 'unknown').length,
      missing: intended - selected.length,
    }),
    segments: Object.freeze(segments),
  });
}

const ATTEMPT_KEYS = Object.freeze([
  'run_id',
  'population',
  'workload_id',
  'attempt_index',
  'source_commit',
  'runner_fingerprint',
  'fixture_fingerprint',
  'timing_fingerprint',
  'optimization_mode',
  'outcome',
  'reason',
  'events',
  'segments',
  'controlled_targets',
  'controlled_observations',
  'p2',
  'p1',
]);
const EVENT_KEYS = Object.freeze(['point', 'monotonic_ms', 'truth_class']);
const CONTROLLED_OBSERVATION_KEYS = Object.freeze(['stt_settlement', 'admission', 'agent_model', 'tool_interval', 'tts_generation']);
const OBSERVED_VALUE_KEYS = Object.freeze(['value_ms', 'truth_class']);
const P2_KEYS = Object.freeze(['truth_class', 'notification_rpc_count', 'notification_batch_count', 'ordered_barriers', 'batches', 'response']);
const P2_BATCH_KEYS = Object.freeze(['rpc_index', 'start_publish_seq', 'end_publish_seq', 'count', 'duration_ms']);
const P2_RESPONSE_KEYS = Object.freeze(['session_id', 'correlation_id', 'interaction_id', 'activation_id', 'response_id', 'response_generation', 'unit_id']);
const P1_KEYS = Object.freeze([
  'successor_ack_confirmed',
  'next_turn_ready',
  'downlink_opened_before_successor_ack',
  'product_owner',
  'successor_ack_observed',
  'interaction_id',
  'response_id',
  'unit_id',
]);
const ATTEMPT_REASONS = new Set([
  'CONTROLLED_WAIT_EARLY',
  'CONTROLLED_WAIT_LATE',
  'MONOTONIC_CLOCK_INVALID',
  'MONOTONIC_CLOCK_REWOUND',
  'EVENT_ORDER_INVALID',
  'ATTEMPT_SETTLEMENT_INCOMPLETE',
  'CHECKPOINT_DEPENDENCY_FAILED',
]);

function expectedP2RpcCount(config: CheckpointReportConfig, workloadId: CheckpointWorkloadId): number {
  if (config.optimization_mode.p2_notification_batch_size === 1) return CHECKPOINT_WORKLOADS[workloadId].notification_count;
  return workloadId === 'W1' ? 1 : workloadId === 'W2' ? 4 : 8;
}

function expectedBatchTails(config: CheckpointReportConfig, workloadId: CheckpointWorkloadId): readonly number[] {
  if (config.optimization_mode.p2_notification_batch_size === 1)
    return Object.freeze(Array.from({ length: CHECKPOINT_WORKLOADS[workloadId].notification_count }, (_, index) => index));
  return workloadId === 'W1' ? Object.freeze([9]) : workloadId === 'W2' ? Object.freeze([15, 31, 47, 49]) : Object.freeze([15, 31, 40, 41, 57, 73, 89, 99]);
}

function validateAttemptForReport(attempt: CheckpointAttempt, config: CheckpointReportConfig): void {
  if (attempt === null || typeof attempt !== 'object' || Array.isArray(attempt) || !exactKeys(attempt as unknown as Record<string, unknown>, ATTEMPT_KEYS))
    reportViolation('CHECKPOINT_ATTEMPT_INVALID');
  if (
    attempt.run_id !== config.run_id ||
    attempt.population !== config.population ||
    attempt.source_commit !== config.source_commit ||
    attempt.runner_fingerprint !== config.runner_fingerprint ||
    attempt.fixture_fingerprint !== config.fixture_fingerprint ||
    attempt.timing_fingerprint !== config.timing_fingerprint ||
    !validOptimizationMode(attempt.optimization_mode) ||
    JSON.stringify(attempt.optimization_mode) !== JSON.stringify(config.optimization_mode) ||
    !Object.prototype.hasOwnProperty.call(CHECKPOINT_WORKLOADS, attempt.workload_id) ||
    !['completed', 'invalid', 'failed', 'unknown'].includes(attempt.outcome) ||
    (attempt.outcome === 'completed' ? attempt.reason !== null : typeof attempt.reason !== 'string' || !ATTEMPT_REASONS.has(attempt.reason))
  )
    reportViolation('CHECKPOINT_ATTEMPT_INVALID');
  if (!Array.isArray(attempt.events) || attempt.events.length > CHECKPOINT_POINTS.length) reportViolation('CHECKPOINT_ATTEMPT_EVENTS_INVALID');
  for (let index = 0; index < attempt.events.length; index += 1) {
    const event = attempt.events[index];
    if (
      event === null ||
      typeof event !== 'object' ||
      Array.isArray(event) ||
      !exactKeys(event as unknown as Record<string, unknown>, EVENT_KEYS) ||
      event.point !== CHECKPOINT_POINTS[index] ||
      event.truth_class !== 'measured' ||
      !Number.isFinite(event.monotonic_ms) ||
      event.monotonic_ms < 0 ||
      (index > 0 && event.monotonic_ms < attempt.events[index - 1].monotonic_ms)
    )
      reportViolation('CHECKPOINT_ATTEMPT_EVENTS_INVALID');
  }
  if (attempt.outcome === 'completed' && attempt.events.length !== CHECKPOINT_POINTS.length) reportViolation('CHECKPOINT_ATTEMPT_EVENTS_INVALID');
  if (JSON.stringify(attempt.segments) !== JSON.stringify(measuredSegments(attempt.events))) reportViolation('CHECKPOINT_ATTEMPT_SEGMENTS_INVALID');
  if (JSON.stringify(attempt.controlled_targets) !== JSON.stringify(frozenControlledTargets(attempt.workload_id)))
    reportViolation('CHECKPOINT_ATTEMPT_TARGETS_INVALID');
  if (
    attempt.controlled_observations === null ||
    typeof attempt.controlled_observations !== 'object' ||
    Array.isArray(attempt.controlled_observations) ||
    !exactKeys(attempt.controlled_observations as unknown as Record<string, unknown>, CONTROLLED_OBSERVATION_KEYS)
  )
    reportViolation('CHECKPOINT_ATTEMPT_CONTROLLED_INVALID');
  for (const [name, observation] of Object.entries(attempt.controlled_observations)) {
    if (
      observation === null ||
      typeof observation !== 'object' ||
      Array.isArray(observation) ||
      !exactKeys(observation as unknown as Record<string, unknown>, OBSERVED_VALUE_KEYS) ||
      observation.truth_class !== 'measured' ||
      (observation.value_ms !== null && (!Number.isFinite(observation.value_ms) || observation.value_ms < 0)) ||
      (name === 'tool_interval' && attempt.workload_id !== 'W3' && observation.value_ms !== null)
    )
      reportViolation('CHECKPOINT_ATTEMPT_CONTROLLED_INVALID');
  }
  if (attempt.p2 !== null) {
    const expectedRpcCount = expectedP2RpcCount(config, attempt.workload_id);
    if (
      typeof attempt.p2 !== 'object' ||
      Array.isArray(attempt.p2) ||
      !exactKeys(attempt.p2 as unknown as Record<string, unknown>, P2_KEYS) ||
      attempt.p2.truth_class !== 'measured' ||
      attempt.p2.notification_rpc_count !== expectedRpcCount ||
      attempt.p2.notification_batch_count !== expectedRpcCount ||
      JSON.stringify(attempt.p2.ordered_barriers) !== JSON.stringify(CHECKPOINT_WORKLOADS[attempt.workload_id].tool_barriers) ||
      !Array.isArray(attempt.p2.batches) ||
      JSON.stringify(attempt.p2.batches.map(batch => batch.end_publish_seq)) !== JSON.stringify(expectedBatchTails(config, attempt.workload_id)) ||
      attempt.p2.batches.some(
        (batch, index) =>
          batch === null ||
          typeof batch !== 'object' ||
          Array.isArray(batch) ||
          !exactKeys(batch as unknown as Record<string, unknown>, P2_BATCH_KEYS) ||
          !Number.isSafeInteger(batch.rpc_index) ||
          !Number.isSafeInteger(batch.start_publish_seq) ||
          !Number.isSafeInteger(batch.end_publish_seq) ||
          !Number.isSafeInteger(batch.count) ||
          !Number.isFinite(batch.duration_ms) ||
          batch.rpc_index !== index + 1 ||
          batch.start_publish_seq !== (index === 0 ? 0 : attempt.p2!.batches[index - 1].end_publish_seq + 1) ||
          batch.count !== batch.end_publish_seq - batch.start_publish_seq + 1 ||
          batch.duration_ms !== CHECKPOINT_CONTROLLED_TARGETS.p2_rpc_ms,
      ) ||
      attempt.p2.response === null ||
      typeof attempt.p2.response !== 'object' ||
      Array.isArray(attempt.p2.response) ||
      !exactKeys(attempt.p2.response as unknown as Record<string, unknown>, P2_RESPONSE_KEYS) ||
      !['session_id', 'correlation_id', 'interaction_id', 'activation_id', 'response_id', 'unit_id'].every(key =>
        TOKEN.test(attempt.p2!.response[key as keyof typeof attempt.p2.response] as string),
      ) ||
      !Number.isSafeInteger(attempt.p2.response.response_generation) ||
      attempt.p2.response.response_generation !== 0
    )
      reportViolation('CHECKPOINT_ATTEMPT_P2_INVALID');
  }
  if (attempt.p1 !== null) {
    if (
      typeof attempt.p1 !== 'object' ||
      Array.isArray(attempt.p1) ||
      !exactKeys(attempt.p1 as unknown as Record<string, unknown>, P1_KEYS) ||
      attempt.p1.successor_ack_confirmed !== true ||
      attempt.p1.next_turn_ready !== true ||
      attempt.p1.downlink_opened_before_successor_ack !== config.optimization_mode.tts_successor_ack_overlap ||
      attempt.p1.product_owner !== 'ProductP1VoiceRouteOwner' ||
      attempt.p1.successor_ack_observed === null ||
      typeof attempt.p1.successor_ack_observed !== 'object' ||
      !exactKeys(attempt.p1.successor_ack_observed as unknown as Record<string, unknown>, OBSERVED_VALUE_KEYS) ||
      attempt.p1.successor_ack_observed.truth_class !== 'measured' ||
      attempt.p1.successor_ack_observed.value_ms !== CHECKPOINT_WORKLOADS[attempt.workload_id].successor_ack_delay_ms ||
      attempt.p2 === null ||
      attempt.p1.interaction_id !== attempt.p2.response.interaction_id ||
      attempt.p1.response_id !== attempt.p2.response.response_id ||
      attempt.p1.unit_id !== attempt.p2.response.unit_id
    )
      reportViolation('CHECKPOINT_ATTEMPT_P1_INVALID');
  }
  if (attempt.outcome === 'completed' && (attempt.p2 === null || attempt.p1 === null)) reportViolation('CHECKPOINT_ATTEMPT_SETTLEMENT_INVALID');
  if (attempt.outcome === 'completed') {
    const controlledPairs: readonly (readonly [number | null, number])[] = [
      [attempt.controlled_observations.stt_settlement.value_ms, CHECKPOINT_CONTROLLED_TARGETS.stt_settlement_ms],
      [attempt.controlled_observations.admission.value_ms, CHECKPOINT_CONTROLLED_TARGETS.admission_ms],
      [attempt.controlled_observations.agent_model.value_ms, CHECKPOINT_CONTROLLED_TARGETS.agent_model_ms],
      [attempt.controlled_observations.tts_generation.value_ms, CHECKPOINT_CONTROLLED_TARGETS.tts_generation_ms],
      ...(attempt.workload_id === 'W3'
        ? ([[attempt.controlled_observations.tool_interval.value_ms, CHECKPOINT_CONTROLLED_TARGETS.tool_interval_ms]] as const)
        : []),
    ];
    if (controlledPairs.some(([observed, target]) => observed === null || observed < target || observed > target + Math.max(25, target * 0.05)))
      reportViolation('CHECKPOINT_ATTEMPT_CONTROLLED_INVALID');
  }
  if (
    attempt.outcome === 'completed' &&
    attempt.segments.first_source_to_playout?.duration_ms !== CHECKPOINT_WORKLOADS[attempt.workload_id].playout_duration_ms
  )
    reportViolation('CHECKPOINT_ATTEMPT_PLAYOUT_INVALID');
}

export function buildCheckpointReport(config: CheckpointReportConfig, attempts: readonly CheckpointAttempt[]): CheckpointReport {
  validateReportConfig(config);
  const seen = new Set<string>();
  for (const attempt of attempts) {
    validateAttemptForReport(attempt, config);
    const key = `${attempt.workload_id}:${attempt.attempt_index}`;
    if (!Number.isSafeInteger(attempt.attempt_index) || attempt.attempt_index < 0 || attempt.attempt_index >= config.samples_per_workload || seen.has(key))
      reportViolation('CHECKPOINT_ATTEMPT_IDENTITY_INVALID');
    seen.add(key);
  }
  const summaries = {} as Record<CheckpointWorkloadId, CheckpointWorkloadSummary>;
  for (const workloadId of Object.keys(CHECKPOINT_WORKLOADS) as CheckpointWorkloadId[])
    summaries[workloadId] = buildWorkloadSummary(workloadId, attempts, config.samples_per_workload);
  return Object.freeze({
    schema_version: 'live-voice.accepted-optimizations-checkpoint.v0',
    lane: 'deterministic_owner_checkpoint',
    ...config,
    optimization_mode: Object.freeze({ ...config.optimization_mode }),
    forbidden_effects: CHECKPOINT_FORBIDDEN_EFFECTS,
    attempts: Object.freeze([...attempts]),
    summaries: Object.freeze(summaries),
  });
}

function exactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === [...expected].sort()[index]);
}

export function parseCheckpointReport(value: unknown): CheckpointReport {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) reportViolation('CHECKPOINT_REPORT_INVALID');
  const raw = value as Record<string, unknown>;
  if (
    !exactKeys(raw, [
      'schema_version',
      'lane',
      'run_id',
      'population',
      'source_commit',
      'source_clean',
      'runner_fingerprint',
      'fixture_fingerprint',
      'timing_fingerprint',
      'samples_per_workload',
      'optimization_mode',
      'forbidden_effects',
      'attempts',
      'summaries',
    ]) ||
    raw.schema_version !== 'live-voice.accepted-optimizations-checkpoint.v0' ||
    raw.lane !== 'deterministic_owner_checkpoint' ||
    JSON.stringify(raw.forbidden_effects) !== JSON.stringify(CHECKPOINT_FORBIDDEN_EFFECTS) ||
    !Array.isArray(raw.attempts) ||
    raw.optimization_mode === null ||
    typeof raw.optimization_mode !== 'object' ||
    Array.isArray(raw.optimization_mode)
  )
    reportViolation('CHECKPOINT_REPORT_INVALID');
  let rebuilt: CheckpointReport;
  try {
    rebuilt = buildCheckpointReport(
      {
        run_id: raw.run_id as string,
        population: raw.population as CheckpointPopulation,
        source_commit: raw.source_commit as string,
        source_clean: raw.source_clean as boolean,
        runner_fingerprint: raw.runner_fingerprint as string,
        fixture_fingerprint: raw.fixture_fingerprint as string,
        timing_fingerprint: raw.timing_fingerprint as string,
        samples_per_workload: raw.samples_per_workload as number,
        optimization_mode: raw.optimization_mode as unknown as CheckpointOptimizationMode,
      },
      raw.attempts as unknown as readonly CheckpointAttempt[],
    );
  } catch {
    reportViolation('CHECKPOINT_REPORT_INVALID');
  }
  if (JSON.stringify(rebuilt.summaries) !== JSON.stringify(raw.summaries)) reportViolation('CHECKPOINT_REPORT_INVALID');
  return rebuilt;
}

export type CheckpointComparisonResult = 'IMPROVED' | 'REGRESSED' | 'UNCHANGED' | 'INCONCLUSIVE';

export interface CheckpointComparisonRow {
  readonly result: CheckpointComparisonResult;
  readonly measurements: Readonly<{
    a1: Readonly<{ truth_class: 'measured'; p50_ms: number; p95_ms: number }>;
    b: Readonly<{ truth_class: 'measured'; p50_ms: number; p95_ms: number }>;
    a2: Readonly<{ truth_class: 'measured'; p50_ms: number; p95_ms: number }>;
  }>;
  readonly deltas: Readonly<{
    truth_class: 'derived';
    b_minus_a1_p50_ms: number;
    b_minus_a2_p50_ms: number;
    b_minus_a1_p95_ms: number;
    b_minus_a2_p95_ms: number;
    b_minus_a1_p50_percent: number | null;
    b_minus_a2_p50_percent: number | null;
    baseline_drift_p50_ms: number;
    baseline_drift_p50_percent: number | null;
  }>;
}

export interface CheckpointComparison {
  readonly schema_version: 'live-voice.accepted-optimizations-checkpoint-comparison.v0';
  readonly decision: Exclude<CheckpointComparisonResult, 'UNCHANGED'>;
  readonly populations_complete: boolean;
  readonly inputs: Readonly<
    Record<
      'a1' | 'b' | 'a2',
      Readonly<{
        run_id: string;
        source_commit: string;
        runner_fingerprint: string;
        fixture_fingerprint: string;
        timing_fingerprint: string;
        optimization_mode: CheckpointOptimizationMode;
        report_sha256: string | null;
      }>
    >
  >;
  readonly workloads: Readonly<Record<CheckpointWorkloadId, Readonly<{ segments: Readonly<Record<CheckpointSegment, CheckpointComparisonRow>> }>>>;
}

function rounded(value: number): number {
  return Number(value.toFixed(6));
}

function assertComparable(a1: CheckpointReport, b: CheckpointReport, a2: CheckpointReport): void {
  if (a1.population !== 'A1' || b.population !== 'B' || a2.population !== 'A2') reportViolation('CHECKPOINT_POPULATION_INVALID');
  if (a1.source_commit !== a2.source_commit) reportViolation('CHECKPOINT_SOURCE_MISMATCH');
  for (const report of [b, a2]) {
    if (
      report.runner_fingerprint !== a1.runner_fingerprint ||
      report.fixture_fingerprint !== a1.fixture_fingerprint ||
      report.timing_fingerprint !== a1.timing_fingerprint ||
      report.samples_per_workload !== a1.samples_per_workload
    )
      reportViolation('CHECKPOINT_FINGERPRINT_MISMATCH');
  }
  const baselineMode = (report: CheckpointReport): boolean =>
    report.optimization_mode.p2_notification_batch_size === 1 && report.optimization_mode.tts_successor_ack_overlap === false;
  const optimizedMode = b.optimization_mode.p2_notification_batch_size === 16 && b.optimization_mode.tts_successor_ack_overlap === true;
  if (!baselineMode(a1) || !baselineMode(a2) || !optimizedMode) reportViolation('CHECKPOINT_OPTIMIZATION_MODE_INVALID');
}

export function compareCheckpointReports(a1: CheckpointReport, b: CheckpointReport, a2: CheckpointReport): CheckpointComparison {
  assertComparable(a1, b, a2);
  const workloads = {} as Record<CheckpointWorkloadId, { segments: Record<CheckpointSegment, CheckpointComparisonRow> }>;
  const populationsComplete = [a1, b, a2].every(
    report =>
      report.samples_per_workload === 5 &&
      (Object.keys(CHECKPOINT_WORKLOADS) as CheckpointWorkloadId[]).every(workloadId => {
        const outcomes = report.summaries[workloadId].outcomes;
        return (
          outcomes.intended === 5 &&
          outcomes.attempts === 5 &&
          outcomes.completed === 5 &&
          outcomes.invalid === 0 &&
          outcomes.failed === 0 &&
          outcomes.unknown === 0 &&
          outcomes.missing === 0
        );
      }),
  );
  let anyImproved = false;
  let anyRegressed = false;
  let anyInconclusive = false;
  for (const workloadId of Object.keys(CHECKPOINT_WORKLOADS) as CheckpointWorkloadId[]) {
    const segments = {} as Record<CheckpointSegment, CheckpointComparisonRow>;
    for (const segment of Object.keys(CHECKPOINT_SEGMENTS) as CheckpointSegment[]) {
      const a1Summary = a1.summaries[workloadId].segments[segment];
      const bSummary = b.summaries[workloadId].segments[segment];
      const a2Summary = a2.summaries[workloadId].segments[segment];
      const values = [a1Summary.p50_ms, a1Summary.p95_ms, bSummary.p50_ms, bSummary.p95_ms, a2Summary.p50_ms, a2Summary.p95_ms];
      if (values.some(value => value === null)) {
        anyInconclusive = true;
        continue;
      }
      const [a1P50, a1P95, bP50, bP95, a2P50, a2P95] = values as number[];
      const directions = [bP50 - a1P50, bP50 - a2P50, bP95 - a1P95, bP95 - a2P95];
      const result: CheckpointComparisonResult =
        directions.every(value => value <= 0) && directions.some(value => value < 0)
          ? 'IMPROVED'
          : directions.every(value => value >= 0) && directions.some(value => value > 0)
            ? 'REGRESSED'
            : directions.every(value => value === 0)
              ? 'UNCHANGED'
              : 'INCONCLUSIVE';
      const driftPercent = a1P50 === 0 ? null : rounded(((a2P50 - a1P50) / a1P50) * 100);
      const row = Object.freeze({
        result,
        measurements: Object.freeze({
          a1: Object.freeze({ truth_class: 'measured' as const, p50_ms: a1P50, p95_ms: a1P95 }),
          b: Object.freeze({ truth_class: 'measured' as const, p50_ms: bP50, p95_ms: bP95 }),
          a2: Object.freeze({ truth_class: 'measured' as const, p50_ms: a2P50, p95_ms: a2P95 }),
        }),
        deltas: Object.freeze({
          truth_class: 'derived' as const,
          b_minus_a1_p50_ms: bP50 - a1P50,
          b_minus_a2_p50_ms: bP50 - a2P50,
          b_minus_a1_p95_ms: bP95 - a1P95,
          b_minus_a2_p95_ms: bP95 - a2P95,
          b_minus_a1_p50_percent: a1P50 === 0 ? null : rounded(((bP50 - a1P50) / a1P50) * 100),
          b_minus_a2_p50_percent: a2P50 === 0 ? null : rounded(((bP50 - a2P50) / a2P50) * 100),
          baseline_drift_p50_ms: a2P50 - a1P50,
          baseline_drift_p50_percent: driftPercent,
        }),
      });
      segments[segment] = row;
      anyImproved ||= result === 'IMPROVED';
      anyRegressed ||= result === 'REGRESSED';
      anyInconclusive ||= result === 'INCONCLUSIVE' || (driftPercent !== null && Math.abs(driftPercent) > 10);
    }
    workloads[workloadId] = Object.freeze({ segments: Object.freeze(segments) });
  }
  const decision: CheckpointComparison['decision'] =
    !populationsComplete || anyInconclusive || (anyImproved && anyRegressed)
      ? 'INCONCLUSIVE'
      : anyRegressed
        ? 'REGRESSED'
        : anyImproved
          ? 'IMPROVED'
          : 'INCONCLUSIVE';
  const inputIdentity = (report: CheckpointReport) =>
    Object.freeze({
      run_id: report.run_id,
      source_commit: report.source_commit,
      runner_fingerprint: report.runner_fingerprint,
      fixture_fingerprint: report.fixture_fingerprint,
      timing_fingerprint: report.timing_fingerprint,
      optimization_mode: Object.freeze({ ...report.optimization_mode }),
      report_sha256: null,
    });
  return Object.freeze({
    schema_version: 'live-voice.accepted-optimizations-checkpoint-comparison.v0',
    decision,
    populations_complete: populationsComplete,
    inputs: Object.freeze({ a1: inputIdentity(a1), b: inputIdentity(b), a2: inputIdentity(a2) }),
    workloads: Object.freeze(workloads),
  });
}

export function parseCheckpointComparison(value: unknown): CheckpointComparison {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) reportViolation('CHECKPOINT_COMPARISON_INVALID');
  const raw = value as Record<string, unknown>;
  if (
    !exactKeys(raw, ['schema_version', 'decision', 'populations_complete', 'inputs', 'workloads']) ||
    raw.schema_version !== 'live-voice.accepted-optimizations-checkpoint-comparison.v0' ||
    !['IMPROVED', 'REGRESSED', 'INCONCLUSIVE'].includes(raw.decision as string) ||
    typeof raw.populations_complete !== 'boolean' ||
    raw.inputs === null ||
    typeof raw.inputs !== 'object' ||
    Array.isArray(raw.inputs) ||
    raw.workloads === null ||
    typeof raw.workloads !== 'object' ||
    Array.isArray(raw.workloads)
  )
    reportViolation('CHECKPOINT_COMPARISON_INVALID');
  const workloads = raw.workloads as Record<string, unknown>;
  if (!exactKeys(workloads, Object.keys(CHECKPOINT_WORKLOADS))) reportViolation('CHECKPOINT_COMPARISON_INVALID');
  const inputs = raw.inputs as Record<string, unknown>;
  if (!exactKeys(inputs, ['a1', 'b', 'a2'])) reportViolation('CHECKPOINT_COMPARISON_INVALID');
  for (const input of Object.values(inputs)) {
    if (
      input === null ||
      typeof input !== 'object' ||
      Array.isArray(input) ||
      !exactKeys(input as Record<string, unknown>, [
        'run_id',
        'source_commit',
        'runner_fingerprint',
        'fixture_fingerprint',
        'timing_fingerprint',
        'optimization_mode',
        'report_sha256',
      ])
    )
      reportViolation('CHECKPOINT_COMPARISON_INVALID');
    const identity = input as CheckpointComparison['inputs']['a1'];
    if (
      !TOKEN.test(identity.run_id) ||
      !SHA40.test(identity.source_commit) ||
      !SHA64.test(identity.runner_fingerprint) ||
      !SHA64.test(identity.fixture_fingerprint) ||
      !SHA64.test(identity.timing_fingerprint) ||
      identity.report_sha256 === null ||
      !SHA64.test(identity.report_sha256) ||
      !validOptimizationMode(identity.optimization_mode)
    )
      reportViolation('CHECKPOINT_COMPARISON_INVALID');
  }
  const a1Input = inputs.a1 as CheckpointComparison['inputs']['a1'];
  const bInput = inputs.b as CheckpointComparison['inputs']['b'];
  const a2Input = inputs.a2 as CheckpointComparison['inputs']['a2'];
  if (
    a1Input.source_commit !== a2Input.source_commit ||
    a1Input.runner_fingerprint !== bInput.runner_fingerprint ||
    a1Input.runner_fingerprint !== a2Input.runner_fingerprint ||
    a1Input.fixture_fingerprint !== bInput.fixture_fingerprint ||
    a1Input.fixture_fingerprint !== a2Input.fixture_fingerprint ||
    a1Input.timing_fingerprint !== bInput.timing_fingerprint ||
    a1Input.timing_fingerprint !== a2Input.timing_fingerprint ||
    a1Input.optimization_mode.p2_notification_batch_size !== 1 ||
    a1Input.optimization_mode.tts_successor_ack_overlap !== false ||
    a2Input.optimization_mode.p2_notification_batch_size !== 1 ||
    a2Input.optimization_mode.tts_successor_ack_overlap !== false ||
    bInput.optimization_mode.p2_notification_batch_size !== 16 ||
    bInput.optimization_mode.tts_successor_ack_overlap !== true
  )
    reportViolation('CHECKPOINT_COMPARISON_INVALID');
  for (const workloadId of Object.keys(CHECKPOINT_WORKLOADS)) {
    const workload = workloads[workloadId];
    if (workload === null || typeof workload !== 'object' || Array.isArray(workload) || !exactKeys(workload as Record<string, unknown>, ['segments']))
      reportViolation('CHECKPOINT_COMPARISON_INVALID');
    const segments = (workload as { segments: unknown }).segments;
    if (
      segments === null ||
      typeof segments !== 'object' ||
      Array.isArray(segments) ||
      !exactKeys(segments as Record<string, unknown>, Object.keys(CHECKPOINT_SEGMENTS))
    )
      reportViolation('CHECKPOINT_COMPARISON_INVALID');
    for (const row of Object.values(segments as Record<string, unknown>)) {
      if (
        row === null ||
        typeof row !== 'object' ||
        Array.isArray(row) ||
        !exactKeys(row as Record<string, unknown>, ['result', 'measurements', 'deltas']) ||
        !['IMPROVED', 'REGRESSED', 'UNCHANGED', 'INCONCLUSIVE'].includes((row as { result?: unknown }).result as string)
      )
        reportViolation('CHECKPOINT_COMPARISON_INVALID');
      const parsedRow = row as CheckpointComparisonRow;
      if (
        !exactKeys(parsedRow.measurements as unknown as Record<string, unknown>, ['a1', 'b', 'a2']) ||
        !exactKeys(parsedRow.deltas as unknown as Record<string, unknown>, [
          'truth_class',
          'b_minus_a1_p50_ms',
          'b_minus_a2_p50_ms',
          'b_minus_a1_p95_ms',
          'b_minus_a2_p95_ms',
          'b_minus_a1_p50_percent',
          'b_minus_a2_p50_percent',
          'baseline_drift_p50_ms',
          'baseline_drift_p50_percent',
        ]) ||
        parsedRow.deltas.truth_class !== 'derived'
      )
        reportViolation('CHECKPOINT_COMPARISON_INVALID');
      for (const measurement of Object.values(parsedRow.measurements)) {
        if (
          !exactKeys(measurement as unknown as Record<string, unknown>, ['truth_class', 'p50_ms', 'p95_ms']) ||
          measurement.truth_class !== 'measured' ||
          !Number.isFinite(measurement.p50_ms) ||
          !Number.isFinite(measurement.p95_ms)
        )
          reportViolation('CHECKPOINT_COMPARISON_INVALID');
      }
      const { a1, b, a2 } = parsedRow.measurements;
      const directions = [b.p50_ms - a1.p50_ms, b.p50_ms - a2.p50_ms, b.p95_ms - a1.p95_ms, b.p95_ms - a2.p95_ms];
      const expectedResult: CheckpointComparisonResult =
        directions.every(item => item <= 0) && directions.some(item => item < 0)
          ? 'IMPROVED'
          : directions.every(item => item >= 0) && directions.some(item => item > 0)
            ? 'REGRESSED'
            : directions.every(item => item === 0)
              ? 'UNCHANGED'
              : 'INCONCLUSIVE';
      const expectedDeltas = {
        truth_class: 'derived',
        b_minus_a1_p50_ms: b.p50_ms - a1.p50_ms,
        b_minus_a2_p50_ms: b.p50_ms - a2.p50_ms,
        b_minus_a1_p95_ms: b.p95_ms - a1.p95_ms,
        b_minus_a2_p95_ms: b.p95_ms - a2.p95_ms,
        b_minus_a1_p50_percent: a1.p50_ms === 0 ? null : rounded(((b.p50_ms - a1.p50_ms) / a1.p50_ms) * 100),
        b_minus_a2_p50_percent: a2.p50_ms === 0 ? null : rounded(((b.p50_ms - a2.p50_ms) / a2.p50_ms) * 100),
        baseline_drift_p50_ms: a2.p50_ms - a1.p50_ms,
        baseline_drift_p50_percent: a1.p50_ms === 0 ? null : rounded(((a2.p50_ms - a1.p50_ms) / a1.p50_ms) * 100),
      };
      if (parsedRow.result !== expectedResult || JSON.stringify(parsedRow.deltas) !== JSON.stringify(expectedDeltas))
        reportViolation('CHECKPOINT_COMPARISON_INVALID');
    }
  }
  const parsed = value as CheckpointComparison;
  const results = Object.values(parsed.workloads).flatMap(workload => Object.values(workload.segments).map(row => row.result));
  const excessiveDrift = Object.values(parsed.workloads).some(workload =>
    Object.values(workload.segments).some(row => row.deltas.baseline_drift_p50_percent !== null && Math.abs(row.deltas.baseline_drift_p50_percent) > 10),
  );
  const recomputed: CheckpointComparison['decision'] =
    !parsed.populations_complete || excessiveDrift || results.includes('INCONCLUSIVE') || (results.includes('IMPROVED') && results.includes('REGRESSED'))
      ? 'INCONCLUSIVE'
      : results.includes('REGRESSED')
        ? 'REGRESSED'
        : results.includes('IMPROVED')
          ? 'IMPROVED'
          : 'INCONCLUSIVE';
  if (parsed.decision !== recomputed) reportViolation('CHECKPOINT_COMPARISON_INVALID');
  return Object.freeze(parsed);
}
