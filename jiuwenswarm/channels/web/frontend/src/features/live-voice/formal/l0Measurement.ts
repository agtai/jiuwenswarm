import {
  OBSERVABILITY_SCHEMA_VERSION,
  createObservation,
  type LiveVoiceObservation,
} from './liveVoiceObservability.js';

export const L0_MEASUREMENT_ENVELOPE_VERSION = 'live-voice.l0-measurement-envelope.v1' as const;
export const L0_BROWSER_QUERY_FLAG = 'live_voice_l0_measurement' as const;
const L0_BROWSER_CAPACITY = 4096;

export type BrowserL0Milestone =
  | 'browser_eot_receipt'
  | 'capture_stopped'
  | 'last_frame_sent'
  | 'successor_capture_ready'
  | 'browser_first_frame'
  | 'webaudio_first_frame_scheduled'
  | 'webaudio_actually_started'
  | 'playout_completed'
  | 'barge_in'
  | 'fence_cancel_completion'
  | 'browser_failure'
  | 'fallback'
  | 'discarded_work'
  | 'unit_tts_requested'
  | 'unit_first_pcm'
  | 'unit_prepared'
  | 'unit_playout_started'
  | 'unit_playout_completed'
  | 'unit_acknowledged'
  | 'successor_tts_requested'
  | 'successor_downlink_attached'
  | 'successor_first_frame_buffered'
  | 'successor_promoted_to_playout'
  | 'successor_park_requested'
  | 'successor_parked'
  | 'successor_promotion_requested'
  | 'successor_promoted'
  | 'successor_promoted_unparked';

export interface BrowserL0Binding {
  readonly correlation_id: string;
  readonly session_id: string;
  readonly interaction_id: string;
  readonly activation_id: string;
  readonly activation_generation: number;
  readonly response_id: string | null;
  readonly response_generation: number | null;
  readonly unit_id: string | null;
  readonly unit_seq: number | null;
  readonly turn_id: string | null;
  readonly round_id: string | null;
  readonly task_id: string | null;
  readonly attempt_id: string | null;
}

export interface BrowserL0RunLabels {
  readonly profile_id: string;
  readonly scenario_id: string;
  readonly sample_index: number;
  readonly temperature: 'cold' | 'warm' | 'unknown';
  readonly evidence_source: 'prerecorded' | 'digital_loopback' | 'physical';
}

export interface BrowserL0Envelope {
  readonly schema_version: typeof L0_MEASUREMENT_ENVELOPE_VERSION;
  readonly milestone: BrowserL0Milestone;
  readonly binding: Readonly<BrowserL0Binding>;
  readonly observation: Readonly<LiveVoiceObservation>;
  readonly profile_id: string;
  readonly scenario_id: string;
  readonly sample_index: number;
  readonly temperature: BrowserL0RunLabels['temperature'];
  readonly classification: 'success' | 'failure' | 'fallback' | 'cancelled' | 'unknown';
  readonly evidence_source: BrowserL0RunLabels['evidence_source'];
}

export interface BrowserL0ControlSnapshot {
  readonly enabled: true;
  readonly configured: boolean;
  readonly accepted_records: number;
  readonly dropped_records: number;
  readonly records: readonly Readonly<BrowserL0Envelope>[];
}

export interface BrowserL0Control {
  configure(labels: Readonly<BrowserL0RunLabels>): boolean;
  disable(): void;
  clear(): void;
  snapshot(): Readonly<BrowserL0ControlSnapshot>;
}

type BrowserGlobal = typeof globalThis & {
  __JIUWENSWARM_LIVE_VOICE_L0__?: BrowserL0Control;
};

interface BrowserL0State {
  labels: Readonly<BrowserL0RunLabels> | null;
  sequence: number;
  droppedRecords: number;
  readonly records: Readonly<BrowserL0Envelope>[];
  readonly responseLabels: Map<string, Readonly<BrowserL0RunLabels>>;
}

interface MarkerRule {
  readonly event_name: string;
  readonly segment_name: string;
  readonly source_component: string;
  readonly state?: string;
  readonly outcome?: string;
  readonly reason_code?: string;
  readonly error_code?: string;
  readonly cancel_scope?: string;
  readonly route_class?: 'formal' | 'fallback';
}

const MARKERS: Readonly<Record<BrowserL0Milestone, Readonly<MarkerRule>>> = Object.freeze({
  browser_eot_receipt: Object.freeze({ event_name: 'speech.capture_state', segment_name: 'speech.capture', source_component: 'measurement.browser.eot_receipt', state: 'stopping' }),
  capture_stopped: Object.freeze({ event_name: 'speech.capture_state', segment_name: 'speech.capture', source_component: 'measurement.browser.capture_stopped', state: 'stopped' }),
  last_frame_sent: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.capture', source_component: 'measurement.browser.last_frame_sent', state: 'terminal', outcome: 'completed' }),
  successor_capture_ready: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.capture', source_component: 'measurement.browser.successor_capture_ready' }),
  browser_first_frame: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.playout', source_component: 'measurement.browser.first_frame' }),
  webaudio_first_frame_scheduled: Object.freeze({ event_name: 'speech.playout_state', segment_name: 'speech.playout', source_component: 'measurement.browser.webaudio_scheduled', state: 'ready' }),
  webaudio_actually_started: Object.freeze({ event_name: 'speech.playout_state', segment_name: 'speech.playout', source_component: 'measurement.browser.webaudio_started', state: 'playing' }),
  playout_completed: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.playout', source_component: 'measurement.browser.playout_completed', state: 'terminal', outcome: 'completed' }),
  barge_in: Object.freeze({ event_name: 'cancel.requested', segment_name: 'speech.playout', source_component: 'measurement.browser.barge_in', reason_code: 'CANCEL_REQUESTED', cancel_scope: 'playback.stop' }),
  fence_cancel_completion: Object.freeze({ event_name: 'cancel.terminal', segment_name: 'speech.playout', source_component: 'measurement.browser.fence_cancel_completion', outcome: 'cancelled', reason_code: 'CANCEL_TERMINAL', cancel_scope: 'playback.stop' }),
  browser_failure: Object.freeze({ event_name: 'failure.observed', segment_name: 'runtime.response', source_component: 'measurement.browser.failure', reason_code: 'UNAVAILABLE', error_code: 'UNAVAILABLE' }),
  fallback: Object.freeze({ event_name: 'route.selected', segment_name: 'route.fallback', source_component: 'measurement.runtime.fallback', reason_code: 'ROUTE_FALLBACK', route_class: 'fallback' }),
  discarded_work: Object.freeze({ event_name: 'fence.stale_dropped', segment_name: 'runtime.presentation', source_component: 'measurement.runtime.discarded_work', reason_code: 'STALE_GENERATION', error_code: 'STALE' }),
  unit_tts_requested: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.synthesis', source_component: 'measurement.browser.unit_tts_requested' }),
  unit_first_pcm: Object.freeze({ event_name: 'speech.playout_state', segment_name: 'speech.synthesis', source_component: 'measurement.browser.unit_first_pcm', state: 'ready' }),
  unit_prepared: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.synthesis', source_component: 'measurement.browser.unit_prepared', state: 'terminal', outcome: 'completed' }),
  unit_playout_started: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.playout', source_component: 'measurement.browser.unit_playout_started' }),
  unit_playout_completed: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.playout', source_component: 'measurement.browser.unit_playout_completed', state: 'terminal', outcome: 'completed' }),
  unit_acknowledged: Object.freeze({ event_name: 'presentation.acknowledged', segment_name: 'runtime.presentation', source_component: 'measurement.browser.unit_acknowledged', state: 'terminal', outcome: 'completed' }),
  successor_tts_requested: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.synthesis', source_component: 'measurement.browser.successor_tts_requested' }),
  successor_downlink_attached: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.playout', source_component: 'measurement.browser.successor_downlink_attached' }),
  successor_first_frame_buffered: Object.freeze({ event_name: 'speech.playout_state', segment_name: 'speech.playout', source_component: 'measurement.browser.successor_first_frame_buffered', state: 'ready' }),
  successor_promoted_to_playout: Object.freeze({ event_name: 'speech.playout_state', segment_name: 'speech.playout', source_component: 'measurement.browser.successor_promoted_to_playout', state: 'ready' }),
  successor_park_requested: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.transport', source_component: 'measurement.browser.successor_park_requested' }),
  successor_parked: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.transport', source_component: 'measurement.browser.successor_parked', outcome: 'completed' }),
  successor_promotion_requested: Object.freeze({ event_name: 'segment.started', segment_name: 'speech.transport', source_component: 'measurement.browser.successor_promotion_requested' }),
  successor_promoted: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.transport', source_component: 'measurement.browser.successor_promoted', outcome: 'completed' }),
  successor_promoted_unparked: Object.freeze({ event_name: 'segment.completed', segment_name: 'speech.transport', source_component: 'measurement.browser.successor_promoted_unparked', outcome: 'completed' }),
});

function stableToken(value: unknown, field: string): string {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value)) {
    throw new TypeError(`${field} is invalid`);
  }
  return value;
}

function opaqueIdentity(value: unknown, field: string): string {
  const blockedMarker = /(?:^|[._:@-])(?:api[_-]?key|authorization|bearer|credential|password|passwd|secret|token|transcript)(?:$|[._:@-])/i;
  if (
    typeof value !== 'string'
    || value.length === 0
    || value.length > 128
    || value !== value.trim()
    || !/^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/.test(value)
    || blockedMarker.test(value)
  ) {
    throw new TypeError(`${field} is invalid`);
  }
  return value;
}

function exactKeys(value: object, expected: readonly string[], field: string): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((item, index) => item !== wanted[index])) {
    throw new TypeError(`${field} has an invalid closed shape`);
  }
}

function normalizeLabels(value: Readonly<BrowserL0RunLabels>): Readonly<BrowserL0RunLabels> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('labels are invalid');
  exactKeys(value, ['profile_id', 'scenario_id', 'sample_index', 'temperature', 'evidence_source'], 'labels');
  const profileId = stableToken(value.profile_id, 'profile_id');
  const scenarioId = stableToken(value.scenario_id, 'scenario_id');
  if (!Number.isSafeInteger(value.sample_index) || value.sample_index < 0) throw new TypeError('sample_index is invalid');
  if (!['cold', 'warm', 'unknown'].includes(value.temperature)) throw new TypeError('temperature is invalid');
  if (!['prerecorded', 'digital_loopback', 'physical'].includes(value.evidence_source)) throw new TypeError('evidence_source is invalid');
  return Object.freeze({
    profile_id: profileId,
    scenario_id: scenarioId,
    sample_index: value.sample_index,
    temperature: value.temperature,
    evidence_source: value.evidence_source,
  });
}

function normalizeBinding(value: Readonly<BrowserL0Binding>): Readonly<BrowserL0Binding> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('binding is invalid');
  exactKeys(value, ['correlation_id', 'session_id', 'interaction_id', 'activation_id', 'activation_generation', 'response_id', 'response_generation', 'unit_id', 'unit_seq', 'turn_id', 'round_id', 'task_id', 'attempt_id'], 'binding');
  const normalized = {
    correlation_id: opaqueIdentity(value.correlation_id, 'correlation_id'),
    session_id: opaqueIdentity(value.session_id, 'session_id'),
    interaction_id: opaqueIdentity(value.interaction_id, 'interaction_id'),
    activation_id: opaqueIdentity(value.activation_id, 'activation_id'),
    activation_generation: value.activation_generation,
    response_id: value.response_id,
    response_generation: value.response_generation,
    unit_id: value.unit_id,
    unit_seq: value.unit_seq,
    turn_id: value.turn_id,
    round_id: value.round_id,
    task_id: value.task_id,
    attempt_id: value.attempt_id,
  };
  if (!Number.isSafeInteger(normalized.activation_generation) || normalized.activation_generation <= 0) throw new TypeError('activation_generation is invalid');
  for (const field of ['response_id', 'unit_id', 'turn_id', 'round_id', 'task_id', 'attempt_id'] as const) {
    const item = normalized[field];
    if (item !== null) opaqueIdentity(item, field);
  }
  if ((normalized.response_id === null) !== (normalized.response_generation === null)) throw new TypeError('response identity is incomplete');
  if (normalized.response_generation !== null && (!Number.isSafeInteger(normalized.response_generation) || normalized.response_generation < 0)) throw new TypeError('response_generation is invalid');
  if (normalized.unit_seq !== null && (!Number.isSafeInteger(normalized.unit_seq) || normalized.unit_seq < 0)) throw new TypeError('unit_seq is invalid');
  if (normalized.unit_seq !== null && normalized.response_id === null) throw new TypeError('unit response identity is incomplete');
  if ((normalized.unit_id === null) !== (normalized.unit_seq === null)) throw new TypeError('unit identity is incomplete');
  if ((normalized.task_id === null) !== (normalized.attempt_id === null)) throw new TypeError('task identity is incomplete');
  return Object.freeze(normalized);
}

function queryEnabled(): boolean {
  try {
    const location = (globalThis as { location?: { search?: string } }).location;
    if (typeof location?.search !== 'string') return false;
    return new URLSearchParams(location.search).get(L0_BROWSER_QUERY_FLAG) === '1';
  } catch {
    return false;
  }
}

function createBrowserL0State(): BrowserL0State {
  return {
    labels: null,
    sequence: 0,
    droppedRecords: 0,
    records: [],
    responseLabels: new Map(),
  };
}

function sameLabels(
  left: Readonly<BrowserL0RunLabels>,
  right: Readonly<BrowserL0RunLabels>,
): boolean {
  return left.profile_id === right.profile_id
    && left.scenario_id === right.scenario_id
    && left.sample_index === right.sample_index
    && left.temperature === right.temperature
    && left.evidence_source === right.evidence_source;
}

function responseKey(binding: Readonly<BrowserL0Binding>): string | null {
  if (binding.response_id === null || binding.response_generation === null) return null;
  return JSON.stringify([
    binding.correlation_id,
    binding.session_id,
    binding.interaction_id,
    binding.activation_id,
    binding.activation_generation,
    binding.response_id,
    binding.response_generation,
  ]);
}

const state: BrowserL0State | null = queryEnabled() ? createBrowserL0State() : null;
let exposedControl: BrowserL0Control | null = null;

if (state !== null) {
  const active = state;
  const control: BrowserL0Control = Object.freeze({
    configure(value: Readonly<BrowserL0RunLabels>): boolean {
      try {
        active.labels = normalizeLabels(value);
        return true;
      } catch {
        active.labels = null;
        return false;
      }
    },
    disable(): void {
      active.labels = null;
      active.records.splice(0, active.records.length);
      active.droppedRecords = 0;
    },
    clear(): void {
      active.records.splice(0, active.records.length);
      active.droppedRecords = 0;
    },
    snapshot(): Readonly<BrowserL0ControlSnapshot> {
      return Object.freeze({
        enabled: true,
        configured: active.labels !== null,
        accepted_records: active.records.length,
        dropped_records: active.droppedRecords,
        records: Object.freeze([...active.records]),
      });
    },
  });
  exposedControl = control;
  Object.defineProperty(globalThis as BrowserGlobal, '__JIUWENSWARM_LIVE_VOICE_L0__', {
    configurable: false,
    enumerable: false,
    writable: false,
    value: control,
  });
}

export function browserL0Enabled(): boolean {
  return state !== null && state.labels !== null;
}

export function browserL0Available(): boolean {
  return state !== null;
}

export function browserL0Control(): BrowserL0Control | null {
  return exposedControl;
}

export function registerBrowserL0Response(
  value: Readonly<BrowserL0Binding>,
): boolean {
  const active = state;
  if (active === null || active.labels === null) return false;
  try {
    const binding = normalizeBinding(value);
    const key = responseKey(binding);
    if (key === null) return false;
    const prior = active.responseLabels.get(key);
    if (prior !== undefined) return sameLabels(prior, active.labels);
    if (active.responseLabels.size >= L0_BROWSER_CAPACITY) return false;
    active.responseLabels.set(key, active.labels);
    return true;
  } catch {
    return false;
  }
}

export function recordBrowserL0Milestone(input: Readonly<{
  milestone: BrowserL0Milestone;
  binding: Readonly<BrowserL0Binding>;
  duration_ms?: number;
  classification?: BrowserL0Envelope['classification'];
  observed_at?: string;
  monotonic_ms?: number;
}>): boolean {
  const active = state;
  if (active === null || active.labels === null) return false;
  try {
    if (active.records.length >= L0_BROWSER_CAPACITY) {
      active.droppedRecords += 1;
      return false;
    }
    const marker = MARKERS[input.milestone];
    if (marker === undefined) return false;
    const binding = normalizeBinding(input.binding);
    const requiresUnitIdentity =
      input.milestone.startsWith('unit_')
      || [
        'successor_tts_requested',
        'successor_downlink_attached',
        'successor_first_frame_buffered',
        'successor_promoted_to_playout',
        'successor_park_requested',
        'successor_parked',
        'successor_promotion_requested',
        'successor_promoted',
        'successor_promoted_unparked',
      ].includes(input.milestone);
    if (
      requiresUnitIdentity
      && (binding.response_id === null || binding.unit_id === null || binding.unit_seq === null)
    ) return false;
    const duration = input.duration_ms;
    if (duration !== undefined && (!Number.isFinite(duration) || duration < 0)) return false;
    if ((input.observed_at === undefined) !== (input.monotonic_ms === undefined)) return false;
    const observedAt = input.observed_at ?? new Date().toISOString();
    const monotonic = input.monotonic_ms ?? (typeof performance === 'undefined' ? Date.now() : performance.now());
    const key = responseKey(binding);
    let recordLabels = active.labels;
    if (key !== null) {
      const registeredLabels = active.responseLabels.get(key);
      if (registeredLabels === undefined || !sameLabels(registeredLabels, active.labels)) {
        active.droppedRecords += 1;
        return false;
      }
      recordLabels = registeredLabels;
    }
    active.sequence += 1;
    const observation = createObservation({
      schema_version: OBSERVABILITY_SCHEMA_VERSION,
      event_id: `l0-browser-${Date.now()}-${active.sequence}`,
      event_name: marker.event_name,
      segment_name: marker.segment_name,
      observed_at: observedAt,
      monotonic_ms: monotonic,
      binding: {
        correlation_id: binding.correlation_id,
        interaction_id: binding.interaction_id,
        turn_id: binding.turn_id,
        response_id: binding.response_id,
        response_generation: binding.response_generation,
        round_id: binding.round_id,
        task_id: binding.task_id,
        attempt_id: binding.attempt_id,
      },
      route: {
        implementation_class: marker.route_class ?? 'formal',
        owner_module: marker.source_component,
        capability_provider: 'jiuwenswarm-runtime',
        contract_version: 'live-voice.contract.v2',
        reason_code: marker.route_class === 'fallback' ? marker.reason_code ?? null : null,
      },
      source_component: marker.source_component,
      state: marker.state ?? null,
      outcome: marker.outcome ?? null,
      reason_code: marker.reason_code ?? null,
      error_code: marker.error_code ?? null,
      duration_ms: duration ?? null,
      cancel_scope: marker.cancel_scope ?? null,
    });
    const envelope = Object.freeze({
      schema_version: L0_MEASUREMENT_ENVELOPE_VERSION,
      milestone: input.milestone,
      binding,
      observation,
      profile_id: recordLabels.profile_id,
      scenario_id: recordLabels.scenario_id,
      sample_index: recordLabels.sample_index,
      temperature: recordLabels.temperature,
      classification: input.classification ?? 'unknown',
      evidence_source: recordLabels.evidence_source,
    });
    active.records.push(envelope);
    return true;
  } catch {
    return false;
  }
}
