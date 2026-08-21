const SCHEMA_VERSION = 'live-voice.eot-stt-settlement-benchmark.v0' as const;

const FIXTURE_IDS = Object.freeze([
  'local-fast-provider-fast',
  'local-slow-provider-fast',
  'local-fast-provider-slow',
  'both-slow',
] as const);

const FIXTURE_DELAYS = Object.freeze({
  'local-fast-provider-fast': Object.freeze({ localSettlementMs: 50, providerFinalMs: 50 }),
  'local-slow-provider-fast': Object.freeze({ localSettlementMs: 500, providerFinalMs: 50 }),
  'local-fast-provider-slow': Object.freeze({ localSettlementMs: 50, providerFinalMs: 500 }),
  'both-slow': Object.freeze({ localSettlementMs: 500, providerFinalMs: 500 }),
} as const);

const MARK_POINTS = Object.freeze([
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
] as const);

const SEGMENT_IDS = Object.freeze([
  'eot_to_capture_stopped',
  'capture_stopped_to_last_ack',
  'last_ack_to_route_settled',
  'eot_to_provider_final_ready',
  'route_settled_to_result_request_started',
  'result_request_started_to_result_returned',
  'route_settled_to_result_returned',
  'eot_to_recognized_final',
] as const);

const ATTEMPT_KEYS = Object.freeze([
  'fixture_id',
  'attempt_index',
  'outcome',
  'marks_ms',
  'rpc_count',
  'exact_result',
  'cleanup_complete',
] as const);

const FORBIDDEN_EFFECTS = Object.freeze({
  agent_submit: 0,
  tool_call: 0,
  task_mutation: 0,
  tts_request: 0,
  browser: 0,
  web_audio: 0,
  microphone: 0,
  audio_history: 0,
  product_submission: 0,
});

export type EotSttFixtureId = (typeof FIXTURE_IDS)[number];
export type EotSttMarkPoint = (typeof MARK_POINTS)[number];
export type EotSttSegmentId = (typeof SEGMENT_IDS)[number];

export interface EotSttFixture {
  readonly id: 'local-fast-provider-fast' | 'local-slow-provider-fast' | 'local-fast-provider-slow' | 'both-slow';
  readonly localSettlementMs: 50 | 500;
  readonly providerFinalMs: 50 | 500;
}

export interface EotSttAttempt {
  readonly fixture_id: EotSttFixture['id'];
  readonly attempt_index: number;
  readonly outcome: 'completed' | 'failed' | 'invalid';
  readonly marks_ms: Readonly<Record<string, number>>;
  readonly rpc_count: number;
  readonly exact_result: boolean;
  readonly cleanup_complete: boolean;
  readonly segments_ms: Readonly<Record<EotSttSegmentId, number | null>>;
  readonly removable_serial_gap_ms: number | null;
  readonly removable_serial_gap_fraction: number | null;
}

export interface EotSttBenchmarkSummary {
  readonly fixture_id: EotSttFixtureId;
  readonly local_settlement_ms: 50 | 500;
  readonly provider_final_ms: 50 | 500;
  readonly attempted_samples: number;
  readonly successful_samples: number;
  readonly eot_to_capture_stopped_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly capture_stopped_to_last_ack_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly last_ack_to_route_settled_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly eot_to_provider_final_ready_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly route_settled_to_result_request_started_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly result_request_started_to_result_returned_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly route_settled_to_result_returned_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly eot_to_recognized_final_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly removable_serial_gap_ms: Readonly<{ p50_ms: number | null; p95_ms: number | null }>;
  readonly removable_serial_gap_fraction: Readonly<{ p50: number | null; p95: number | null }>;
}

export interface EotSttBenchmarkReport {
  readonly schema_version: typeof SCHEMA_VERSION;
  readonly candidate: 'A1';
  readonly fixture_count: 4;
  readonly attempts_per_fixture: number;
  readonly attempts: readonly Readonly<EotSttAttempt>[];
  readonly summaries: readonly Readonly<EotSttBenchmarkSummary>[];
  readonly forbidden_effects: typeof FORBIDDEN_EFFECTS;
}

type AttemptRunner = (
  fixture: Readonly<EotSttFixture>,
  attemptIndex: number,
) => Promise<unknown> | unknown;

export interface EotSttBenchmarkConfig {
  readonly fixtures: readonly Readonly<EotSttFixture>[];
  readonly attempts: number;
  readonly candidate: 'A1';
  readonly attempt_runner?: AttemptRunner;
}

function fail(code: string): never {
  throw new Error(code);
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Object.getPrototypeOf(value) !== Object.prototype) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Object.values(descriptors).every(descriptor => 'value' in descriptor && descriptor.enumerable === true);
}

function ownValue(record: Record<string, unknown>, key: string): unknown {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor !== undefined && 'value' in descriptor ? descriptor.value : undefined;
}

function hasExactKeys(record: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(record);
  return keys.length === expected.length && expected.every(key => Object.prototype.hasOwnProperty.call(record, key));
}

function validateFixtures(value: unknown): readonly Readonly<EotSttFixture>[] {
  if (!Array.isArray(value) || value.length !== FIXTURE_IDS.length) fail('EOT_STT_BENCHMARK_FIXTURES_INVALID');
  const seen = new Set<string>();
  const fixtures: Readonly<EotSttFixture>[] = [];
  for (const raw of value) {
    if (!isPlainRecord(raw) || !hasExactKeys(raw, ['id', 'localSettlementMs', 'providerFinalMs'])) {
      fail('EOT_STT_BENCHMARK_FIXTURES_INVALID');
    }
    const id = ownValue(raw, 'id');
    if (typeof id !== 'string' || !FIXTURE_IDS.includes(id as EotSttFixtureId) || seen.has(id)) {
      fail('EOT_STT_BENCHMARK_FIXTURES_INVALID');
    }
    const expected = FIXTURE_DELAYS[id as EotSttFixtureId];
    const localSettlementMs = ownValue(raw, 'localSettlementMs');
    const providerFinalMs = ownValue(raw, 'providerFinalMs');
    if (
      typeof localSettlementMs !== 'number' ||
      !Number.isFinite(localSettlementMs) ||
      localSettlementMs !== expected.localSettlementMs ||
      typeof providerFinalMs !== 'number' ||
      !Number.isFinite(providerFinalMs) ||
      providerFinalMs !== expected.providerFinalMs
    ) {
      fail('EOT_STT_BENCHMARK_FIXTURES_INVALID');
    }
    seen.add(id);
    fixtures.push(Object.freeze({ id: id as EotSttFixtureId, localSettlementMs, providerFinalMs } as EotSttFixture));
  }
  if (FIXTURE_IDS.some(id => !seen.has(id))) fail('EOT_STT_BENCHMARK_FIXTURES_INVALID');
  return Object.freeze(fixtures);
}

function validateConfig(input: unknown): Readonly<{
  fixtures: readonly Readonly<EotSttFixture>[];
  attempts: number;
  attemptRunner: AttemptRunner;
}> {
  if (!isPlainRecord(input)) fail('EOT_STT_BENCHMARK_CONFIG_INVALID');
  const allowedKeys = new Set(['fixtures', 'attempts', 'candidate', 'attempt_runner']);
  if (Object.keys(input).some(key => !allowedKeys.has(key))) fail('EOT_STT_BENCHMARK_CONFIG_INVALID');
  if (ownValue(input, 'candidate') !== 'A1') fail('EOT_STT_BENCHMARK_CANDIDATE_INVALID');
  const attempts = ownValue(input, 'attempts');
  if (!Number.isSafeInteger(attempts) || (attempts as number) < 1 || (attempts as number) > 20) {
    fail('EOT_STT_BENCHMARK_ATTEMPTS_INVALID');
  }
  const configuredRunner = ownValue(input, 'attempt_runner');
  if (configuredRunner !== undefined && typeof configuredRunner !== 'function') fail('EOT_STT_BENCHMARK_CONFIG_INVALID');
  return Object.freeze({
    fixtures: validateFixtures(ownValue(input, 'fixtures')),
    attempts: attempts as number,
    attemptRunner: configuredRunner as AttemptRunner | undefined ?? defaultAttempt,
  });
}

function defaultAttempt(fixture: Readonly<EotSttFixture>, attemptIndex: number): Readonly<Record<string, unknown>> {
  const recognized = Math.max(fixture.localSettlementMs, fixture.providerFinalMs);
  return Object.freeze({
    fixture_id: fixture.id,
    attempt_index: attemptIndex,
    outcome: 'completed',
    marks_ms: Object.freeze({
      'browser.eot_received': 0,
      'browser.capture_stop_requested': 0,
      'browser.capture_stopped': 0,
      'browser.uplink_last_frame_sent': 0,
      'browser.uplink_last_ack_received': fixture.localSettlementMs,
      'browser.uplink_closed': fixture.localSettlementMs,
      'benchmark.provider_final_ready': fixture.providerFinalMs,
      'browser.streaming_result_request_started': fixture.localSettlementMs,
      'browser.streaming_result_returned': recognized,
      'browser.stt_final_received': recognized,
    }),
    rpc_count: 1,
    exact_result: true,
    cleanup_complete: true,
  });
}

function validateMarks(value: unknown): Readonly<Record<EotSttMarkPoint, number>> {
  if (!isPlainRecord(value) || !hasExactKeys(value, MARK_POINTS)) fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  const marks = {} as Record<EotSttMarkPoint, number>;
  for (const point of MARK_POINTS) {
    const mark = ownValue(value, point);
    if (typeof mark !== 'number' || !Number.isFinite(mark) || mark < 0) {
      fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
    }
    marks[point] = mark;
  }
  const eot = marks['browser.eot_received'];
  const captureStopRequested = marks['browser.capture_stop_requested'];
  const captureStopped = marks['browser.capture_stopped'];
  const lastFrameSent = marks['browser.uplink_last_frame_sent'];
  const lastAck = marks['browser.uplink_last_ack_received'];
  const uplink = marks['browser.uplink_closed'];
  const request = marks['browser.streaming_result_request_started'];
  const providerReady = marks['benchmark.provider_final_ready'];
  const returned = marks['browser.streaming_result_returned'];
  const final = marks['browser.stt_final_received'];
  if (
    captureStopRequested < eot ||
    captureStopped < captureStopRequested ||
    lastFrameSent < eot ||
    lastAck < captureStopped ||
    lastAck < lastFrameSent ||
    uplink < lastAck ||
    request < uplink ||
    providerReady < eot ||
    returned < request ||
    returned < providerReady ||
    final < returned
  ) {
    fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  }
  return Object.freeze(marks);
}

function validateAttempt(
  value: unknown,
  fixture: Readonly<EotSttFixture>,
  attemptIndex: number,
): Readonly<EotSttAttempt> {
  if (!isPlainRecord(value) || !hasExactKeys(value, ATTEMPT_KEYS)) fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  const outcome = ownValue(value, 'outcome');
  const rpcCount = ownValue(value, 'rpc_count');
  if (
    ownValue(value, 'fixture_id') !== fixture.id ||
    ownValue(value, 'attempt_index') !== attemptIndex ||
    !['completed', 'failed', 'invalid'].includes(String(outcome)) ||
    !Number.isSafeInteger(rpcCount) ||
    (rpcCount as number) < 0 ||
    (rpcCount as number) > 1 ||
    typeof ownValue(value, 'exact_result') !== 'boolean' ||
    typeof ownValue(value, 'cleanup_complete') !== 'boolean'
  ) {
    fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  }
  const marks = validateMarks(ownValue(value, 'marks_ms'));
  if (
    outcome === 'completed' &&
    marks['browser.stt_final_received'] <= marks['browser.eot_received']
  ) {
    fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  }
  const successful = outcome === 'completed'
    && rpcCount === 1
    && ownValue(value, 'exact_result') === true
    && ownValue(value, 'cleanup_complete') === true;
  const duration = marks['browser.stt_final_received'] - marks['browser.eot_received'];
  const derivedSegments = Object.freeze({
    eot_to_capture_stopped: rounded(
      marks['browser.capture_stopped'] - marks['browser.eot_received'],
    ),
    capture_stopped_to_last_ack: rounded(
      marks['browser.uplink_last_ack_received'] - marks['browser.capture_stopped'],
    ),
    last_ack_to_route_settled: rounded(
      marks['browser.uplink_closed'] - marks['browser.uplink_last_ack_received'],
    ),
    eot_to_provider_final_ready: rounded(
      marks['benchmark.provider_final_ready'] - marks['browser.eot_received'],
    ),
    route_settled_to_result_request_started: rounded(
      marks['browser.streaming_result_request_started'] - marks['browser.uplink_closed'],
    ),
    result_request_started_to_result_returned: rounded(
      marks['browser.streaming_result_returned'] - marks['browser.streaming_result_request_started'],
    ),
    route_settled_to_result_returned: rounded(
      marks['browser.streaming_result_returned'] - marks['browser.uplink_closed'],
    ),
    eot_to_recognized_final: rounded(duration),
  });
  const removableGap = marks['browser.streaming_result_returned'] - Math.max(
    marks['browser.uplink_closed'],
    marks['benchmark.provider_final_ready'],
  );
  const removableFraction = successful ? rounded(removableGap / duration) : null;
  if (
    removableGap < 0 ||
    (successful && (
      !Number.isFinite(removableFraction) ||
      removableFraction === null ||
      removableFraction < 0 ||
      removableFraction > 1
    ))
  ) {
    fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  }
  const segments = Object.freeze(Object.fromEntries(
    SEGMENT_IDS.map(segment => [segment, successful ? derivedSegments[segment] : null]),
  )) as Readonly<Record<EotSttSegmentId, number | null>>;
  return Object.freeze({
    fixture_id: fixture.id,
    attempt_index: attemptIndex,
    outcome: outcome as EotSttAttempt['outcome'],
    marks_ms: marks,
    rpc_count: rpcCount as number,
    exact_result: ownValue(value, 'exact_result') as boolean,
    cleanup_complete: ownValue(value, 'cleanup_complete') as boolean,
    segments_ms: segments,
    removable_serial_gap_ms: successful ? rounded(removableGap) : null,
    removable_serial_gap_fraction: removableFraction,
  });
}

function rounded(value: number): number {
  if (!Number.isFinite(value)) fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  const scaled = value * 1_000;
  if (!Number.isFinite(scaled)) fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  const result = Math.round(scaled) / 1_000;
  if (!Number.isFinite(result)) fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  return result;
}

function nearestRank(values: readonly number[], percentile: 50 | 95): number | null {
  if (values.length === 0) return null;
  if (values.some(value => !Number.isFinite(value))) fail('EOT_STT_BENCHMARK_ATTEMPT_INVALID');
  const sorted = [...values].sort((left, right) => left - right);
  return rounded(sorted[Math.ceil((percentile / 100) * sorted.length) - 1]);
}

function percentiles(values: readonly number[]): Readonly<{ p50_ms: number | null; p95_ms: number | null }> {
  return Object.freeze({ p50_ms: nearestRank(values, 50), p95_ms: nearestRank(values, 95) });
}

function fractionPercentiles(values: readonly number[]): Readonly<{ p50: number | null; p95: number | null }> {
  return Object.freeze({ p50: nearestRank(values, 50), p95: nearestRank(values, 95) });
}

function summarize(
  fixture: Readonly<EotSttFixture>,
  attempts: readonly Readonly<EotSttAttempt>[],
): Readonly<EotSttBenchmarkSummary> {
  const successful = attempts.filter(
    attempt => attempt.outcome === 'completed' && attempt.rpc_count === 1 && attempt.exact_result && attempt.cleanup_complete,
  );
  const segmentSamples = (segment: EotSttSegmentId): number[] =>
    successful.map(attempt => attempt.segments_ms[segment] as number);
  const removableGaps = successful.map(attempt => attempt.removable_serial_gap_ms as number);
  const removableFractions = successful.map(attempt => attempt.removable_serial_gap_fraction as number);
  return Object.freeze({
    fixture_id: fixture.id,
    local_settlement_ms: fixture.localSettlementMs,
    provider_final_ms: fixture.providerFinalMs,
    attempted_samples: attempts.length,
    successful_samples: successful.length,
    eot_to_capture_stopped_ms: percentiles(segmentSamples('eot_to_capture_stopped')),
    capture_stopped_to_last_ack_ms: percentiles(segmentSamples('capture_stopped_to_last_ack')),
    last_ack_to_route_settled_ms: percentiles(segmentSamples('last_ack_to_route_settled')),
    eot_to_provider_final_ready_ms: percentiles(segmentSamples('eot_to_provider_final_ready')),
    route_settled_to_result_request_started_ms: percentiles(segmentSamples('route_settled_to_result_request_started')),
    result_request_started_to_result_returned_ms: percentiles(segmentSamples('result_request_started_to_result_returned')),
    route_settled_to_result_returned_ms: percentiles(segmentSamples('route_settled_to_result_returned')),
    eot_to_recognized_final_ms: percentiles(segmentSamples('eot_to_recognized_final')),
    removable_serial_gap_ms: percentiles(removableGaps),
    removable_serial_gap_fraction: fractionPercentiles(removableFractions),
  });
}

export async function runEotSttSettlementBenchmark(input: Readonly<EotSttBenchmarkConfig>): Promise<Readonly<EotSttBenchmarkReport>> {
  const config = validateConfig(input);
  const attempts: Readonly<EotSttAttempt>[] = [];
  const summaries: Readonly<EotSttBenchmarkSummary>[] = [];
  for (const fixture of config.fixtures) {
    const fixtureAttempts: Readonly<EotSttAttempt>[] = [];
    for (let attemptIndex = 0; attemptIndex < config.attempts; attemptIndex += 1) {
      const attempt = validateAttempt(await config.attemptRunner(fixture, attemptIndex), fixture, attemptIndex);
      fixtureAttempts.push(attempt);
      attempts.push(attempt);
    }
    summaries.push(summarize(fixture, fixtureAttempts));
  }
  return Object.freeze({
    schema_version: SCHEMA_VERSION,
    candidate: 'A1',
    fixture_count: 4,
    attempts_per_fixture: config.attempts,
    attempts: Object.freeze(attempts),
    summaries: Object.freeze(summaries),
    forbidden_effects: FORBIDDEN_EFFECTS,
  });
}

export { FIXTURE_IDS, MARK_POINTS, SCHEMA_VERSION, SEGMENT_IDS };
