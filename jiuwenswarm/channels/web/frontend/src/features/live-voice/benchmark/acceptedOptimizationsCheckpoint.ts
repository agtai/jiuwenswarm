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
    notification_count: 10,
    successor_ack_delay_ms: 250,
    playout_duration_ms: 3000,
    tool_barriers: Object.freeze([] as number[]),
  }),
  W2: Object.freeze({
    id: 'W2',
    notification_count: 50,
    successor_ack_delay_ms: 750,
    playout_duration_ms: 6000,
    tool_barriers: Object.freeze([] as number[]),
  }),
  W3: Object.freeze({
    id: 'W3',
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

export interface CheckpointClock {
  nowMs(): number;
  waitMs(delayMs: number): Promise<void>;
}

export interface CheckpointOptimizationMode {
  readonly p2_notification_batch_size: 1 | 16;
  readonly tts_successor_ack_overlap: boolean;
}

export interface CheckpointAttemptConfig {
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
  readonly notification_rpc_count: number;
  readonly notification_batch_count: number;
  readonly ordered_barriers: readonly number[];
}

export interface CheckpointP1Facts {
  readonly successor_ack_confirmed: boolean;
  readonly next_turn_ready: boolean;
}

export interface CheckpointAttemptDependencies {
  readonly clock: CheckpointClock;
  deliverPresentation(input: Readonly<{ workload: (typeof CHECKPOINT_WORKLOADS)[CheckpointWorkloadId] }>): Promise<CheckpointP2Facts>;
  playResponse(
    input: Readonly<{
      workload: (typeof CHECKPOINT_WORKLOADS)[CheckpointWorkloadId];
      mark(point: CheckpointPoint): void;
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
  readonly population: CheckpointPopulation;
  readonly workload_id: CheckpointWorkloadId;
  readonly attempt_index: number;
  readonly outcome: 'completed' | 'invalid' | 'failed' | 'unknown';
  readonly reason: string | null;
  readonly events: readonly CheckpointEvent[];
  readonly segments: Readonly<Partial<Record<CheckpointSegment, CheckpointDuration>>>;
  readonly controlled_targets: Readonly<Record<string, Readonly<{ value_ms: number; truth_class: 'controlled' }>>>;
  readonly p2: CheckpointP2Facts | null;
  readonly p1: CheckpointP1Facts | null;
}

class AttemptInvalid extends Error {
  constructor(readonly reason: string) {
    super(reason);
  }
}

function frozenControlledTargets(): CheckpointAttempt['controlled_targets'] {
  return Object.freeze(
    Object.fromEntries(
      Object.entries(CHECKPOINT_CONTROLLED_TARGETS).map(([name, value_ms]) => [name, Object.freeze({ value_ms, truth_class: 'controlled' as const })]),
    ),
  );
}

function safeNow(clock: CheckpointClock): number {
  const value = clock.nowMs();
  if (!Number.isFinite(value) || value < 0) throw new AttemptInvalid('MONOTONIC_CLOCK_INVALID');
  return value;
}

async function controlledWait(clock: CheckpointClock, targetMs: number): Promise<void> {
  const started = safeNow(clock);
  await clock.waitMs(targetMs);
  const elapsed = safeNow(clock) - started;
  if (elapsed < targetMs) throw new AttemptInvalid('CONTROLLED_WAIT_EARLY');
  if (elapsed > targetMs + Math.max(25, targetMs * 0.05)) throw new AttemptInvalid('CONTROLLED_WAIT_LATE');
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
    await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.stt_settlement_ms);
    mark('stt_final');
    await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.admission_ms);
    mark('admission_accepted');
    await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.agent_model_ms);
    mark('model_complete_and_notifications_enqueued');
    p2 = Object.freeze(await dependencies.deliverPresentation({ workload }));
    mark('presentation_final_consumed');
    await controlledWait(dependencies.clock, CHECKPOINT_CONTROLLED_TARGETS.tts_generation_ms);
    mark('tts_ready_and_successor_capture_requested');
    p1 = Object.freeze(await dependencies.playResponse({ workload, mark }));
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
    population: config.population,
    workload_id: config.workload_id,
    attempt_index: config.attempt_index,
    outcome,
    reason,
    events: Object.freeze([...events]),
    segments: measuredSegments(events),
    controlled_targets: frozenControlledTargets(),
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
  readonly attempts: readonly CheckpointAttempt[];
  readonly summaries: Readonly<Record<CheckpointWorkloadId, CheckpointWorkloadSummary>>;
}

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SHA40 = /^[0-9a-f]{40}$/;
const SHA64 = /^[0-9a-f]{64}$/;

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
    (config.optimization_mode.p2_notification_batch_size !== 1 && config.optimization_mode.p2_notification_batch_size !== 16) ||
    typeof config.optimization_mode.tts_successor_ack_overlap !== 'boolean'
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

export function buildCheckpointReport(config: CheckpointReportConfig, attempts: readonly CheckpointAttempt[]): CheckpointReport {
  validateReportConfig(config);
  const seen = new Set<string>();
  for (const attempt of attempts) {
    if (attempt.population !== config.population || !Object.prototype.hasOwnProperty.call(CHECKPOINT_WORKLOADS, attempt.workload_id))
      reportViolation('CHECKPOINT_ATTEMPT_IDENTITY_INVALID');
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
    attempts: Object.freeze([...attempts]),
    summaries: Object.freeze(summaries),
  });
}

export interface CheckpointComparisonRow {
  readonly truth_class: 'derived';
  readonly a1_p50_ms: number;
  readonly b_p50_ms: number;
  readonly a2_p50_ms: number;
  readonly b_minus_a1_ms: number;
  readonly b_minus_a2_ms: number;
  readonly b_minus_a1_percent: number;
  readonly b_minus_a2_percent: number;
  readonly baseline_drift_ms: number;
  readonly baseline_drift_percent: number;
}

export interface CheckpointComparison {
  readonly schema_version: 'live-voice.accepted-optimizations-checkpoint-comparison.v0';
  readonly decision: 'accepted' | 'rejected' | 'inconclusive';
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
  let decision: CheckpointComparison['decision'] = 'accepted';
  for (const workloadId of Object.keys(CHECKPOINT_WORKLOADS) as CheckpointWorkloadId[]) {
    const segments = {} as Record<CheckpointSegment, CheckpointComparisonRow>;
    for (const segment of Object.keys(CHECKPOINT_SEGMENTS) as CheckpointSegment[]) {
      const a1Value = a1.summaries[workloadId].segments[segment].p50_ms;
      const bValue = b.summaries[workloadId].segments[segment].p50_ms;
      const a2Value = a2.summaries[workloadId].segments[segment].p50_ms;
      if (a1Value === null || bValue === null || a2Value === null || a1Value === 0 || a2Value === 0) {
        decision = 'inconclusive';
        continue;
      }
      const driftPercent = rounded(((a2Value - a1Value) / a1Value) * 100);
      const row = Object.freeze({
        truth_class: 'derived' as const,
        a1_p50_ms: a1Value,
        b_p50_ms: bValue,
        a2_p50_ms: a2Value,
        b_minus_a1_ms: bValue - a1Value,
        b_minus_a2_ms: bValue - a2Value,
        b_minus_a1_percent: rounded(((bValue - a1Value) / a1Value) * 100),
        b_minus_a2_percent: rounded(((bValue - a2Value) / a2Value) * 100),
        baseline_drift_ms: a2Value - a1Value,
        baseline_drift_percent: driftPercent,
      });
      segments[segment] = row;
      if (Math.abs(driftPercent) > 10 || bValue > Math.max(a1Value, a2Value)) decision = 'rejected';
    }
    workloads[workloadId] = Object.freeze({ segments: Object.freeze(segments) });
  }
  return Object.freeze({
    schema_version: 'live-voice.accepted-optimizations-checkpoint-comparison.v0',
    decision,
    workloads: Object.freeze(workloads),
  });
}
