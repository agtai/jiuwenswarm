/**
 * Development-only, best-effort Browser recorder for the Live Voice latency
 * baseline. The probe is deliberately isolated from every product decision.
 */

export const LATENCY_PROBE_BATCH_METHOD = 'live_voice.latency_probe.batch' as const;
export const LATENCY_CONTEXT_SCHEMA_VERSION = 'live-voice.latency-context.v0' as const;
export const LATENCY_MARK_SCHEMA_VERSION = 'live-voice.latency-probe.v0' as const;
export const LATENCY_BATCH_SCHEMA_VERSION = 'live-voice.latency-batch.v0' as const;

export const LATENCY_PROFILE_IDS = Object.freeze(['dialogue_no_tool', 'dialogue_with_tool', 'task_create', 'task_status', 'task_cancel'] as const);

export const BROWSER_LATENCY_CORE_POINTS = Object.freeze([
  'browser.eot_received',
  'browser.stt_final_received',
  'browser.commit_submit_started',
  'browser.presentation_received',
  'browser.tts_request_started',
  'browser.downlink_first_frame_received',
  'browser.playout_first_frame_scheduled',
  'browser.playout_first_frame_started_estimate',
  'browser.playout_completed',
  'browser.playout_ack_received',
  'browser.next_turn_capture_activated',
  'browser.capture_start_requested',
  'browser.capture_device_started',
  'browser.media_socket_attached',
  'browser.capture_first_frame_sent',
  'browser.capture_first_ack_received',
  'browser.capture_stop_requested',
  'browser.capture_stopped',
  'browser.uplink_last_frame_sent',
  'browser.uplink_last_ack_received',
  'browser.uplink_closed',
  'browser.successor_capture_requested',
  'browser.successor_capture_ready',
  'browser.downlink_attach_started',
  'browser.downlink_attached',
  'browser.playout_underrun',
  'browser.playout_rebuffer',
] as const);

const TERMINAL_OUTCOMES = new Set<string>(['completed', 'failed', 'cancelled', 'unknown']);
const MARK_OUTCOMES = new Set<string>(['observed', 'completed', 'failed', 'cancelled', 'fallback', 'unknown']);
const REASON_CODES = new Set<string>([
  'FEATURE_OFF',
  'CAPACITY',
  'EXPORT_FAILED',
  'BATCH_CONFLICT',
  'MISSING_MARK',
  'DUPLICATE_MARK',
  'SEQUENCE_GAP',
  'IDENTITY_MISMATCH',
  'CROSS_CLOCK',
  'FAILED',
  'CANCELLED',
  'FALLBACK',
  'UNDERRUN',
  'REBUFFER',
  'TIMEOUT',
  'INCOMPATIBLE_RUN',
  'INSUFFICIENT_SAMPLES',
]);
const PROFILE_IDS = new Set<string>(LATENCY_PROFILE_IDS);
const CORE_POINTS = new Set<string>(BROWSER_LATENCY_CORE_POINTS);
const MAX_STRING_UTF8_BYTES = 256;
const MAX_ROUNDS = 256;
const MAX_ORDINARY_MARKS = 63;
const PUBLIC_TOKEN = /^[A-Za-z0-9_-][A-Za-z0-9._-]{0,255}$/;
const SENSITIVE_DESCRIPTOR = /(?:private|secret|credential|password|transcript|prompt|authorization|bearer|api[_-]?key)/i;
const STORAGE_PREFIX = 'jiuwenswarm.live_voice.latency_probe.v0';
const IDENTITY_KEYS = new Set([
  'correlation_id',
  'interaction_id',
  'activation_id',
  'activation_generation',
  'turn_id',
  'response_id',
  'response_generation',
  'task_id',
]);
const OBSERVATION_KEYS = new Set(['uncertainty_ms', 'outcome', 'reason_code']);

export type LatencyProfileId = (typeof LATENCY_PROFILE_IDS)[number];
export type BrowserLatencyPoint = (typeof BROWSER_LATENCY_CORE_POINTS)[number] | string;
export type LatencyTerminalOutcome = 'completed' | 'failed' | 'cancelled' | 'unknown';
export type LatencyMarkOutcome = 'observed' | 'completed' | 'failed' | 'cancelled' | 'fallback' | 'unknown';

export type LatencyProbeContext = Readonly<{
  schema_version: typeof LATENCY_CONTEXT_SCHEMA_VERSION;
  run_id: string;
  profile_id: LatencyProfileId;
  input_case_id: string;
  round_index: number;
}>;

export interface LatencyIdentityPatch {
  readonly correlation_id: string;
  readonly interaction_id: string;
  readonly activation_id?: string | null;
  readonly activation_generation?: number | null;
  readonly turn_id?: string | null;
  readonly response_id?: string | null;
  readonly response_generation?: number | null;
  readonly task_id?: string | null;
}

export interface LatencyObservation {
  readonly uncertainty_ms?: number | null;
  readonly outcome?: LatencyMarkOutcome;
  readonly reason_code?: string | null;
}

export interface LatencyMark {
  readonly schema_version: typeof LATENCY_MARK_SCHEMA_VERSION;
  readonly run_id: string;
  readonly profile_id: LatencyProfileId;
  readonly input_case_id: string;
  readonly round_index: number;
  readonly source_instance_id: string;
  readonly mark_index: number;
  readonly component: 'browser';
  readonly clock_domain_id: string;
  readonly point: string;
  readonly monotonic_ms: number;
  readonly uncertainty_ms: number | null;
  readonly outcome: LatencyMarkOutcome;
  readonly reason_code: string | null;
  readonly correlation_id: string;
  readonly interaction_id: string;
  readonly activation_id: string | null;
  readonly activation_generation: number | null;
  readonly turn_id: string | null;
  readonly response_id: string | null;
  readonly response_generation: number | null;
  readonly task_id: string | null;
}

export interface LatencyBatch {
  readonly schema_version: typeof LATENCY_BATCH_SCHEMA_VERSION;
  readonly batch_id: string;
  readonly run_id: string;
  readonly profile_id: LatencyProfileId;
  readonly input_case_id: string;
  readonly round_index: number;
  readonly source_instance_id: string;
  readonly component: 'browser';
  readonly phase: 'browser_round';
  readonly terminal_outcome: LatencyTerminalOutcome;
  readonly marks: readonly Readonly<LatencyMark>[];
}

export interface BrowserLatencyRound {
  readonly context: LatencyProbeContext;
  mark(point: BrowserLatencyPoint, identity: LatencyIdentityPatch, observation?: LatencyObservation): boolean;
  finish(outcome: LatencyTerminalOutcome): Readonly<LatencyBatch> | null;
}

export interface BrowserLatencyProbe {
  beginRound(identity: LatencyIdentityPatch): BrowserLatencyRound;
  exportBatch(sessionId: string, batch: Readonly<LatencyBatch>): Promise<void>;
}

export interface LatencyProbeStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface BrowserLatencyProbeDependencies {
  readonly enabled: boolean;
  readonly location: Pick<Location, 'search'>;
  readonly storage: LatencyProbeStorage;
  readonly monotonicMs: () => number;
  readonly randomId: () => string;
  readonly request: (method: string, params: Record<string, unknown>) => unknown;
  readonly experimentPoints?: readonly string[];
}

type Identity = Readonly<{
  correlation_id: string;
  interaction_id: string;
  activation_id: string | null;
  activation_generation: number | null;
  turn_id: string | null;
  response_id: string | null;
  response_generation: number | null;
  task_id: string | null;
}>;

type Selection = Readonly<{
  run_id: string;
  profile_id: LatencyProfileId;
  input_case_id: string;
}>;

function hasOnlyKeys(value: unknown, allowed: ReadonlySet<string>): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  let keys: (string | symbol)[];
  try {
    keys = Reflect.ownKeys(value);
  } catch {
    return false;
  }
  return keys.every(key => typeof key === 'string' && allowed.has(key));
}

function hasUnpairedSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return true;
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function boundedToken(value: unknown): value is string {
  if (typeof value !== 'string' || value === '' || value === '.' || value === '..') return false;
  if (hasUnpairedSurrogate(value) || !PUBLIC_TOKEN.test(value) || SENSITIVE_DESCRIPTOR.test(value)) return false;
  try {
    return new TextEncoder().encode(value).byteLength <= MAX_STRING_UTF8_BYTES;
  } catch {
    return false;
  }
}

function nonnegativeSafeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function finiteNonnegative(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function parseSelection(location: Pick<Location, 'search'>): Selection | null {
  try {
    if (typeof location.search !== 'string') return null;
    const query = new URLSearchParams(location.search);
    const runValues = query.getAll('lv_latency_run');
    const profileValues = query.getAll('lv_latency_profile');
    const caseValues = query.getAll('lv_latency_case');
    if (runValues.length !== 1 || profileValues.length !== 1 || caseValues.length !== 1) return null;
    const [runId] = runValues;
    const [profileId] = profileValues;
    const [inputCaseId] = caseValues;
    if (!boundedToken(runId) || !boundedToken(profileId) || !boundedToken(inputCaseId) || !PROFILE_IDS.has(profileId)) return null;
    return Object.freeze({ run_id: runId, profile_id: profileId as LatencyProfileId, input_case_id: inputCaseId });
  } catch {
    return null;
  }
}

function parseExperimentPoints(value: readonly string[] | undefined): ReadonlySet<string> | null {
  if (value === undefined) return new Set<string>();
  if (!Array.isArray(value) || value.length > 64) return null;
  const points = new Set<string>();
  for (const point of value) {
    if (!boundedToken(point) || !point.startsWith('experiment.') || CORE_POINTS.has(point) || points.has(point)) return null;
    points.add(point);
  }
  return points;
}

function storageKey(selection: Selection): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(selection.run_id)}:${encodeURIComponent(selection.profile_id)}:${encodeURIComponent(selection.input_case_id)}`;
}

function allocateRoundIndex(storage: LatencyProbeStorage, key: string): number | null {
  try {
    const raw = storage.getItem(key);
    let current: number;
    if (raw === null) {
      current = 0;
    } else {
      if (!/^(?:0|[1-9][0-9]{0,2})$/.test(raw)) return null;
      current = Number(raw);
      if (!nonnegativeSafeInteger(current) || current >= MAX_ROUNDS) return null;
    }
    const next = String(current + 1);
    storage.setItem(key, next);
    if (storage.getItem(key) !== next) return null;
    return current;
  } catch {
    return null;
  }
}

function rollbackRoundIndex(storage: LatencyProbeStorage, key: string, roundIndex: number): void {
  try {
    const allocatedNext = String(roundIndex + 1);
    if (storage.getItem(key) !== allocatedNext) return;
    const restoredNext = String(roundIndex);
    storage.setItem(key, restoredNext);
    storage.getItem(key);
  } catch {
    // Rollback is best-effort and can only affect this diagnostic allocator.
  }
}

function parseIdentity(value: unknown, current: Identity | null): Identity | null {
  try {
    if (!hasOnlyKeys(value, IDENTITY_KEYS)) return null;
    if (!boundedToken(value.correlation_id) || !boundedToken(value.interaction_id)) return null;
    if (current !== null && (value.correlation_id !== current.correlation_id || value.interaction_id !== current.interaction_id)) return null;

    const next: Record<string, string | number | null> = {
      correlation_id: value.correlation_id,
      interaction_id: value.interaction_id,
    };
    for (const field of ['activation_id', 'turn_id', 'response_id', 'task_id'] as const) {
      const supplied = Object.prototype.hasOwnProperty.call(value, field);
      const candidate = supplied ? value[field] : (current?.[field] ?? null);
      if (candidate !== null && !boundedToken(candidate)) return null;
      if (current?.[field] !== null && current?.[field] !== undefined && candidate !== current[field]) return null;
      next[field] = candidate;
    }
    for (const field of ['activation_generation', 'response_generation'] as const) {
      const supplied = Object.prototype.hasOwnProperty.call(value, field);
      const candidate = supplied ? value[field] : (current?.[field] ?? null);
      if (candidate !== null && !nonnegativeSafeInteger(candidate)) return null;
      if (current?.[field] !== null && current?.[field] !== undefined && candidate !== current[field]) return null;
      next[field] = candidate;
    }
    return Object.freeze(next) as Identity;
  } catch {
    return null;
  }
}

function parseObservation(point: string, value: unknown): Readonly<Required<LatencyObservation>> | null {
  try {
    if (value === undefined) return Object.freeze({ uncertainty_ms: null, outcome: 'observed', reason_code: null });
    if (!hasOnlyKeys(value, OBSERVATION_KEYS)) return null;
    const uncertainty = Object.prototype.hasOwnProperty.call(value, 'uncertainty_ms') ? value.uncertainty_ms : null;
    const outcome = Object.prototype.hasOwnProperty.call(value, 'outcome') ? value.outcome : 'observed';
    const reason = Object.prototype.hasOwnProperty.call(value, 'reason_code') ? value.reason_code : null;
    if (uncertainty !== null && (!finiteNonnegative(uncertainty) || point !== 'browser.playout_first_frame_started_estimate')) return null;
    if (typeof outcome !== 'string' || !MARK_OUTCOMES.has(outcome)) return null;
    if (reason !== null && (typeof reason !== 'string' || !REASON_CODES.has(reason))) return null;
    return Object.freeze({
      uncertainty_ms: uncertainty as number | null,
      outcome: outcome as LatencyMarkOutcome,
      reason_code: reason as string | null,
    });
  } catch {
    return null;
  }
}

function freezeContext(selection: Selection, roundIndex: number): LatencyProbeContext {
  return Object.freeze({
    schema_version: LATENCY_CONTEXT_SCHEMA_VERSION,
    ...selection,
    round_index: roundIndex,
  });
}

function inertRound(selection: Selection): BrowserLatencyRound {
  return Object.freeze({
    context: freezeContext(selection, 0),
    mark: () => false,
    finish: () => null,
  });
}

function deepFreezeBatch(batch: LatencyBatch): Readonly<LatencyBatch> {
  for (const mark of batch.marks) Object.freeze(mark);
  Object.freeze(batch.marks);
  return Object.freeze(batch);
}

function validateProducedBatch(batch: unknown, selection: Selection, points: ReadonlySet<string>): batch is Readonly<LatencyBatch> {
  if (
    !hasOnlyKeys(
      batch,
      new Set([
        'schema_version',
        'batch_id',
        'run_id',
        'profile_id',
        'input_case_id',
        'round_index',
        'source_instance_id',
        'component',
        'phase',
        'terminal_outcome',
        'marks',
      ]),
    )
  )
    return false;
  if (
    batch.schema_version !== LATENCY_BATCH_SCHEMA_VERSION ||
    !boundedToken(batch.batch_id) ||
    batch.run_id !== selection.run_id ||
    batch.profile_id !== selection.profile_id ||
    batch.input_case_id !== selection.input_case_id ||
    !nonnegativeSafeInteger(batch.round_index) ||
    !boundedToken(batch.source_instance_id) ||
    batch.component !== 'browser' ||
    batch.phase !== 'browser_round' ||
    !TERMINAL_OUTCOMES.has(String(batch.terminal_outcome)) ||
    !Array.isArray(batch.marks) ||
    batch.marks.length > 64
  )
    return false;
  let capacityCount = 0;
  const seen = new Set<string>();
  for (let index = 0; index < batch.marks.length; index += 1) {
    const mark = batch.marks[index];
    if (!validateMark(mark, batch, index, points, seen)) return false;
    if (mark.point === 'probe.capacity') capacityCount += 1;
  }
  if (capacityCount > 1) return false;
  if (capacityCount === 1 && (batch.marks.length !== 64 || batch.marks[63]?.point !== 'probe.capacity')) return false;
  if (batch.marks.length === 64 && capacityCount !== 1) return false;
  return true;
}

function validateMark(
  mark: unknown,
  batch: Record<string, unknown>,
  index: number,
  points: ReadonlySet<string>,
  seen: Set<string>,
): mark is Readonly<LatencyMark> {
  if (
    !hasOnlyKeys(
      mark,
      new Set([
        'schema_version',
        'run_id',
        'profile_id',
        'input_case_id',
        'round_index',
        'source_instance_id',
        'mark_index',
        'component',
        'clock_domain_id',
        'point',
        'monotonic_ms',
        'uncertainty_ms',
        'outcome',
        'reason_code',
        'correlation_id',
        'interaction_id',
        'activation_id',
        'activation_generation',
        'turn_id',
        'response_id',
        'response_generation',
        'task_id',
      ]),
    )
  )
    return false;
  if (!boundedToken(mark.point) || seen.has(mark.point)) return false;
  const capacity = mark.point === 'probe.capacity';
  if (!capacity && !points.has(mark.point)) return false;
  if (
    mark.schema_version !== LATENCY_MARK_SCHEMA_VERSION ||
    mark.run_id !== batch.run_id ||
    mark.profile_id !== batch.profile_id ||
    mark.input_case_id !== batch.input_case_id ||
    mark.round_index !== batch.round_index ||
    mark.source_instance_id !== batch.source_instance_id ||
    mark.mark_index !== index ||
    mark.component !== 'browser' ||
    !boundedToken(mark.clock_domain_id) ||
    !finiteNonnegative(mark.monotonic_ms) ||
    !MARK_OUTCOMES.has(String(mark.outcome)) ||
    (mark.reason_code !== null && !REASON_CODES.has(String(mark.reason_code))) ||
    !boundedToken(mark.correlation_id) ||
    !boundedToken(mark.interaction_id)
  )
    return false;
  if (capacity && (index !== 63 || mark.outcome !== 'unknown' || mark.reason_code !== 'CAPACITY')) return false;
  if (mark.uncertainty_ms !== null && (!finiteNonnegative(mark.uncertainty_ms) || mark.point !== 'browser.playout_first_frame_started_estimate')) return false;
  if (
    !optionalToken(mark.activation_id) ||
    !optionalInteger(mark.activation_generation) ||
    !optionalToken(mark.turn_id) ||
    !optionalToken(mark.response_id) ||
    !optionalInteger(mark.response_generation) ||
    !optionalToken(mark.task_id)
  )
    return false;
  seen.add(mark.point);
  return true;
}

function optionalToken(value: unknown): boolean {
  return value === null || boundedToken(value);
}

function optionalInteger(value: unknown): boolean {
  return value === null || nonnegativeSafeInteger(value);
}

class ActiveBrowserLatencyRound implements BrowserLatencyRound {
  readonly context: LatencyProbeContext;
  readonly #sourceInstanceId: string;
  readonly #clockDomainId: string;
  readonly #batchId: string;
  readonly #monotonicMs: () => number;
  readonly #points: ReadonlySet<string>;
  readonly #onFinish: (batch: Readonly<LatencyBatch>) => void;
  readonly #marks: LatencyMark[] = [];
  readonly #seen = new Set<string>();
  #identity: Identity;
  #finished = false;
  #capacityRecorded = false;

  constructor(input: {
    context: LatencyProbeContext;
    identity: Identity;
    sourceInstanceId: string;
    clockDomainId: string;
    batchId: string;
    monotonicMs: () => number;
    points: ReadonlySet<string>;
    onFinish: (batch: Readonly<LatencyBatch>) => void;
  }) {
    this.context = input.context;
    this.#identity = input.identity;
    this.#sourceInstanceId = input.sourceInstanceId;
    this.#clockDomainId = input.clockDomainId;
    this.#batchId = input.batchId;
    this.#monotonicMs = input.monotonicMs;
    this.#points = input.points;
    this.#onFinish = input.onFinish;
  }

  mark(point: BrowserLatencyPoint, identity: LatencyIdentityPatch, observation?: LatencyObservation): boolean {
    if (this.#finished || this.#capacityRecorded) return false;
    if (this.#marks.length >= MAX_ORDINARY_MARKS) {
      this.#recordCapacity();
      return false;
    }
    try {
      if (!boundedToken(point) || this.#seen.has(point) || !this.#points.has(point)) return false;
      const nextIdentity = parseIdentity(identity, this.#identity);
      const normalizedObservation = parseObservation(point, observation);
      if (nextIdentity === null || normalizedObservation === null) return false;
      const monotonicMs = this.#monotonicMs();
      if (!finiteNonnegative(monotonicMs)) return false;
      const mark = Object.freeze({
        schema_version: LATENCY_MARK_SCHEMA_VERSION,
        run_id: this.context.run_id,
        profile_id: this.context.profile_id,
        input_case_id: this.context.input_case_id,
        round_index: this.context.round_index,
        source_instance_id: this.#sourceInstanceId,
        mark_index: this.#marks.length,
        component: 'browser' as const,
        clock_domain_id: this.#clockDomainId,
        point,
        monotonic_ms: monotonicMs,
        uncertainty_ms: normalizedObservation.uncertainty_ms,
        outcome: normalizedObservation.outcome,
        reason_code: normalizedObservation.reason_code,
        ...nextIdentity,
      });
      this.#marks.push(mark);
      this.#seen.add(point);
      this.#identity = nextIdentity;
      return true;
    } catch {
      return false;
    }
  }

  #recordCapacity(): void {
    if (this.#capacityRecorded || this.#marks.length !== MAX_ORDINARY_MARKS) return;
    this.#capacityRecorded = true;
    try {
      const monotonicMs = this.#monotonicMs();
      if (!finiteNonnegative(monotonicMs)) return;
      this.#marks.push(
        Object.freeze({
          schema_version: LATENCY_MARK_SCHEMA_VERSION,
          run_id: this.context.run_id,
          profile_id: this.context.profile_id,
          input_case_id: this.context.input_case_id,
          round_index: this.context.round_index,
          source_instance_id: this.#sourceInstanceId,
          mark_index: MAX_ORDINARY_MARKS,
          component: 'browser' as const,
          clock_domain_id: this.#clockDomainId,
          point: 'probe.capacity',
          monotonic_ms: monotonicMs,
          uncertainty_ms: null,
          outcome: 'unknown' as const,
          reason_code: 'CAPACITY',
          correlation_id: this.#identity.correlation_id,
          interaction_id: this.#identity.interaction_id,
          activation_id: null,
          activation_generation: null,
          turn_id: null,
          response_id: null,
          response_generation: null,
          task_id: null,
        }),
      );
    } catch {
      // A capacity observation is diagnostic-only and never escapes into product work.
    }
  }

  finish(outcome: LatencyTerminalOutcome): Readonly<LatencyBatch> | null {
    if (this.#finished || !TERMINAL_OUTCOMES.has(outcome)) return null;
    this.#finished = true;
    const batch = deepFreezeBatch({
      schema_version: LATENCY_BATCH_SCHEMA_VERSION,
      batch_id: this.#batchId,
      run_id: this.context.run_id,
      profile_id: this.context.profile_id,
      input_case_id: this.context.input_case_id,
      round_index: this.context.round_index,
      source_instance_id: this.#sourceInstanceId,
      component: 'browser',
      phase: 'browser_round',
      terminal_outcome: outcome,
      marks: this.#marks,
    });
    this.#onFinish(batch);
    return batch;
  }
}

class DefaultBrowserLatencyProbe implements BrowserLatencyProbe {
  readonly #selection: Selection;
  readonly #storage: LatencyProbeStorage;
  readonly #storageKey: string;
  readonly #sourceInstanceId: string;
  readonly #clockDomainId: string;
  readonly #monotonicMs: () => number;
  readonly #randomId: () => string;
  readonly #request: (method: string, params: Record<string, unknown>) => unknown;
  readonly #points: ReadonlySet<string>;
  readonly #ownedBatches = new WeakSet<object>();
  readonly #settledExports = new WeakSet<object>();

  constructor(input: {
    selection: Selection;
    storage: LatencyProbeStorage;
    sourceInstanceId: string;
    clockDomainId: string;
    monotonicMs: () => number;
    randomId: () => string;
    request: (method: string, params: Record<string, unknown>) => unknown;
    experimentPoints: ReadonlySet<string>;
  }) {
    this.#selection = input.selection;
    this.#storage = input.storage;
    this.#storageKey = storageKey(input.selection);
    this.#sourceInstanceId = input.sourceInstanceId;
    this.#clockDomainId = input.clockDomainId;
    this.#monotonicMs = input.monotonicMs;
    this.#randomId = input.randomId;
    this.#request = input.request;
    this.#points = new Set([...CORE_POINTS, ...input.experimentPoints]);
  }

  beginRound(identity: LatencyIdentityPatch): BrowserLatencyRound {
    const parsedIdentity = parseIdentity(identity, null);
    if (parsedIdentity === null) return inertRound(this.#selection);
    const roundIndex = allocateRoundIndex(this.#storage, this.#storageKey);
    if (roundIndex === null) return inertRound(this.#selection);
    let batchId: string;
    try {
      batchId = this.#randomId();
    } catch {
      rollbackRoundIndex(this.#storage, this.#storageKey, roundIndex);
      return inertRound(this.#selection);
    }
    if (!boundedToken(batchId)) {
      rollbackRoundIndex(this.#storage, this.#storageKey, roundIndex);
      return inertRound(this.#selection);
    }
    return new ActiveBrowserLatencyRound({
      context: freezeContext(this.#selection, roundIndex),
      identity: parsedIdentity,
      sourceInstanceId: this.#sourceInstanceId,
      clockDomainId: this.#clockDomainId,
      batchId,
      monotonicMs: this.#monotonicMs,
      points: this.#points,
      onFinish: batch => this.#ownedBatches.add(batch),
    });
  }

  async exportBatch(sessionId: string, batch: Readonly<LatencyBatch>): Promise<void> {
    try {
      if (!boundedToken(sessionId) || batch === null || typeof batch !== 'object') return;
      if (!this.#ownedBatches.has(batch) || this.#settledExports.has(batch)) return;
      if (!validateProducedBatch(batch, this.#selection, this.#points)) return;
      this.#settledExports.add(batch);
      await this.#request(LATENCY_PROBE_BATCH_METHOD, { session_id: sessionId, batch });
    } catch {
      // Export is a one-shot diagnostic side channel; product work never retries it.
    }
  }
}

export function createBrowserLatencyProbe(dependencies: Readonly<BrowserLatencyProbeDependencies> | null | undefined): BrowserLatencyProbe | null {
  try {
    if (dependencies === null || dependencies === undefined || dependencies.enabled !== true) return null;
    const selection = parseSelection(dependencies.location);
    if (selection === null) return null;
    const experimentPoints = parseExperimentPoints(dependencies.experimentPoints);
    if (experimentPoints === null) return null;
    if (
      dependencies.storage === null ||
      typeof dependencies.storage !== 'object' ||
      typeof dependencies.storage.getItem !== 'function' ||
      typeof dependencies.storage.setItem !== 'function' ||
      typeof dependencies.monotonicMs !== 'function' ||
      typeof dependencies.randomId !== 'function' ||
      typeof dependencies.request !== 'function'
    )
      return null;
    const sourceInstanceId = dependencies.randomId();
    const clockDomainId = dependencies.randomId();
    if (!boundedToken(sourceInstanceId) || !boundedToken(clockDomainId)) return null;
    return new DefaultBrowserLatencyProbe({
      selection,
      storage: dependencies.storage,
      sourceInstanceId,
      clockDomainId,
      monotonicMs: dependencies.monotonicMs,
      randomId: dependencies.randomId,
      request: dependencies.request,
      experimentPoints,
    });
  } catch {
    return null;
  }
}
