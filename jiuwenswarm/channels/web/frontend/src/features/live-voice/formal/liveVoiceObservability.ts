import { CONTRACT_VERSION as LIVE_VOICE_CONTRACT_VERSION } from './liveVoiceRouteTelemetry.js';

export const OBSERVABILITY_SCHEMA_VERSION = 'live-voice.observability.v1' as const;
export const IDENTITY_MAX_LENGTH = 128 as const;

export const ROUTE_IMPLEMENTATION_CLASSES = Object.freeze(['formal', 'fallback', 'demo_substitute', 'unsupported', 'unknown'] as const);
export type ObservedRouteClass = (typeof ROUTE_IMPLEMENTATION_CLASSES)[number];

export const CANCEL_SCOPES = Object.freeze(['playback.stop', 'response.cancel', 'round.cancel', 'task.cancel'] as const);
export type LiveVoiceCancelScope = (typeof CANCEL_SCOPES)[number];

export const SEGMENT_NAMES = Object.freeze([
  'speech.capture',
  'speech.recognition',
  'speech.synthesis',
  'speech.playout',
  'runtime.turn',
  'runtime.response',
  'runtime.presentation',
  'runtime.queue',
  'agent.dispatch',
  'agent.progress',
  'agent.queue',
  'task.command',
  'task.attempt',
  'task.progress',
  'task.queue',
  'route.fallback',
  'system.degradation',
] as const);
export type LiveVoiceSegmentName = (typeof SEGMENT_NAMES)[number];

export const EVENT_NAMES = Object.freeze([
  'route.selected',
  'segment.started',
  'segment.completed',
  'segment.failed',
  'speech.capture_state',
  'speech.playout_state',
  'speech.device_change',
  'queue.pressure',
  'cancel.requested',
  'cancel.acknowledged',
  'cancel.terminal',
  'cancel.result_unknown',
  'fence.stale_dropped',
  'task.state_observed',
  'task.dispatch_outbox_observed',
  'task.cancel_outbox_observed',
  'task.adjust_outbox_observed',
  'task.reconciliation_observed',
  'degradation.activated',
  'degradation.recovered',
  'failure.observed',
] as const);
export type LiveVoiceEventName = (typeof EVENT_NAMES)[number];

export const OBSERVED_STATES = Object.freeze([
  'idle',
  'starting',
  'active',
  'stopping',
  'stopped',
  'locked',
  'ready',
  'playing',
  'closed',
  'pending',
  'required',
  'in_progress',
  'resolved',
  'claimed',
  'delivered',
  'suppressed',
  'accepted',
  'running',
  'blocked',
  'decision_required',
  'terminal',
  'failed',
] as const);
export type LiveVoiceObservedState = (typeof OBSERVED_STATES)[number];

export const TERMINAL_OUTCOMES = Object.freeze(['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const);
export type LiveVoiceTerminalOutcome = (typeof TERMINAL_OUTCOMES)[number];

export const ERROR_CODES = Object.freeze([
  'INVALID_ARGUMENT',
  'UNSUPPORTED',
  'UNAUTHENTICATED',
  'PERMISSION_DENIED',
  'NOT_FOUND',
  'CONFLICT',
  'STALE',
  'CAPABILITY_UNAVAILABLE',
  'UNAVAILABLE',
  'TIMEOUT',
  'CANCELLED',
  'PROTOCOL_VIOLATION',
  'RESULT_UNKNOWN',
  'INTERNAL',
] as const);
export type LiveVoiceErrorCode = (typeof ERROR_CODES)[number];

export const REASON_CODES = Object.freeze([
  'ROUTE_FALLBACK',
  'DEMO_SUBSTITUTE',
  'UNSUPPORTED_CAPABILITY',
  'UNKNOWN_PROVENANCE',
  'QUEUE_CAPACITY',
  'CANCEL_REQUESTED',
  'CANCEL_ACKNOWLEDGED',
  'CANCEL_TERMINAL',
  'CANCEL_RESULT_UNKNOWN',
  'STALE_GENERATION',
  'PROVIDER_FAILURE',
  'AGENT_FAILURE',
  'TASK_FAILURE',
  'TIMEOUT',
  'UNAVAILABLE',
  'PROTOCOL_REJECTED',
  'DEGRADED',
  'RECOVERED',
  'DEVICE_CHANGED',
  'DEVICE_ENUMERATION_FAILED',
] as const);
export type LiveVoiceReasonCode = (typeof REASON_CODES)[number];

export interface EventSemanticRule {
  readonly segments: readonly LiveVoiceSegmentName[];
  readonly required_facts: readonly string[];
  readonly allowed_facts: readonly string[];
  readonly required_bindings: readonly string[];
  readonly source_kind: 'none' | 'optional' | 'event' | 'record';
  readonly states: readonly LiveVoiceObservedState[];
  readonly outcomes: readonly LiveVoiceTerminalOutcome[];
  readonly reasons: readonly LiveVoiceReasonCode[];
  readonly errors: readonly LiveVoiceErrorCode[];
  readonly cancel_scopes: readonly LiveVoiceCancelScope[];
}

function frozenList<T>(values: readonly T[]): readonly T[] {
  return Object.freeze([...values]);
}

function eventRule(options: {
  segments: readonly LiveVoiceSegmentName[];
  required?: readonly string[];
  allowed?: readonly string[];
  bindings?: readonly string[];
  source_kind?: EventSemanticRule['source_kind'];
  states?: readonly LiveVoiceObservedState[];
  outcomes?: readonly LiveVoiceTerminalOutcome[];
  reasons?: readonly LiveVoiceReasonCode[];
  errors?: readonly LiveVoiceErrorCode[];
  cancel_scopes?: readonly LiveVoiceCancelScope[];
}): Readonly<EventSemanticRule> {
  return Object.freeze({
    segments: frozenList(options.segments),
    required_facts: frozenList(options.required ?? []),
    allowed_facts: frozenList(options.allowed ?? []),
    required_bindings: frozenList(options.bindings ?? []),
    source_kind: options.source_kind ?? 'optional',
    states: frozenList(options.states ?? []),
    outcomes: frozenList(options.outcomes ?? []),
    reasons: frozenList(options.reasons ?? []),
    errors: frozenList(options.errors ?? []),
    cancel_scopes: frozenList(options.cancel_scopes ?? []),
  });
}

const SOURCE_FACTS = Object.freeze(['source_event_id', 'source_record_id', 'source_occurred_at', 'source_seq'] as const);
const EVENT_FACTS = Object.freeze([
  ...SOURCE_FACTS,
  'state',
  'outcome',
  'reason_code',
  'error_code',
  'duration_ms',
  'queue_depth',
  'queue_capacity',
  'cancel_scope',
] as const);
const LIFECYCLE_SEGMENTS = Object.freeze([
  'speech.capture',
  'speech.recognition',
  'speech.synthesis',
  'speech.playout',
  'runtime.turn',
  'runtime.response',
  'runtime.presentation',
  'runtime.queue',
  'agent.dispatch',
  'agent.progress',
  'agent.queue',
  'task.command',
  'task.attempt',
  'task.progress',
  'task.queue',
] as const);
const CANCEL_SEGMENTS = Object.freeze(['speech.playout', 'runtime.response', 'agent.progress', 'task.command'] as const);
const FAILURE_SEGMENTS = Object.freeze([
  'speech.capture',
  'speech.recognition',
  'speech.synthesis',
  'speech.playout',
  'runtime.turn',
  'runtime.response',
  'runtime.presentation',
  'agent.dispatch',
  'agent.progress',
  'task.command',
  'task.attempt',
  'task.progress',
  'task.queue',
] as const);

export const EVENT_SEMANTIC_MATRIX: Readonly<Record<LiveVoiceEventName, Readonly<EventSemanticRule>>> = Object.freeze({
  'route.selected': eventRule({
    segments: SEGMENT_NAMES,
    allowed: ['source_record_id', 'reason_code'],
    source_kind: 'optional',
    reasons: ['ROUTE_FALLBACK', 'DEMO_SUBSTITUTE', 'UNSUPPORTED_CAPABILITY', 'UNKNOWN_PROVENANCE'],
  }),
  'segment.started': eventRule({ segments: LIFECYCLE_SEGMENTS, allowed: SOURCE_FACTS }),
  'segment.completed': eventRule({
    segments: LIFECYCLE_SEGMENTS,
    required: ['outcome', 'duration_ms'],
    allowed: [...SOURCE_FACTS, 'state', 'outcome', 'duration_ms'],
    states: ['terminal'],
    outcomes: ['completed'],
  }),
  'segment.failed': eventRule({
    segments: LIFECYCLE_SEGMENTS,
    required: ['outcome', 'reason_code', 'error_code', 'duration_ms'],
    allowed: [...SOURCE_FACTS, 'state', 'outcome', 'reason_code', 'error_code', 'duration_ms'],
    states: ['terminal', 'failed'],
    outcomes: ['failed'],
    reasons: ['AGENT_FAILURE', 'PROTOCOL_REJECTED', 'PROVIDER_FAILURE', 'TASK_FAILURE', 'TIMEOUT', 'UNAVAILABLE'],
    errors: ERROR_CODES,
  }),
  'speech.capture_state': eventRule({
    segments: ['speech.capture'],
    required: ['state'],
    allowed: [...SOURCE_FACTS, 'state', 'reason_code', 'error_code'],
    states: ['idle', 'starting', 'active', 'stopping', 'stopped', 'failed'],
    reasons: ['UNAVAILABLE'],
    errors: ['UNAVAILABLE'],
  }),
  'speech.playout_state': eventRule({
    segments: ['speech.playout'],
    required: ['state'],
    allowed: [...SOURCE_FACTS, 'state', 'reason_code', 'error_code'],
    states: ['locked', 'ready', 'playing', 'stopped', 'failed', 'closed'],
    reasons: ['UNAVAILABLE'],
    errors: ['UNAVAILABLE'],
  }),
  'speech.device_change': eventRule({
    segments: ['speech.capture'],
    required: ['reason_code'],
    allowed: [...SOURCE_FACTS, 'reason_code', 'error_code'],
    reasons: ['DEVICE_CHANGED', 'DEVICE_ENUMERATION_FAILED'],
    errors: ['UNAVAILABLE'],
  }),
  'queue.pressure': eventRule({
    segments: ['runtime.queue', 'agent.queue', 'task.queue'],
    required: ['reason_code', 'queue_depth', 'queue_capacity'],
    allowed: [...SOURCE_FACTS, 'reason_code', 'queue_depth', 'queue_capacity'],
    reasons: ['QUEUE_CAPACITY'],
  }),
  'cancel.requested': eventRule({
    segments: CANCEL_SEGMENTS,
    required: ['reason_code', 'cancel_scope'],
    allowed: [...SOURCE_FACTS, 'reason_code', 'cancel_scope'],
    reasons: ['CANCEL_REQUESTED'],
    cancel_scopes: CANCEL_SCOPES,
  }),
  'cancel.acknowledged': eventRule({
    segments: CANCEL_SEGMENTS,
    required: ['reason_code', 'cancel_scope'],
    allowed: [...SOURCE_FACTS, 'reason_code', 'cancel_scope'],
    reasons: ['CANCEL_ACKNOWLEDGED'],
    cancel_scopes: CANCEL_SCOPES,
  }),
  'cancel.terminal': eventRule({
    segments: CANCEL_SEGMENTS,
    required: ['outcome', 'reason_code', 'cancel_scope'],
    allowed: [...SOURCE_FACTS, 'outcome', 'reason_code', 'cancel_scope'],
    outcomes: ['cancelled'],
    reasons: ['CANCEL_TERMINAL'],
    cancel_scopes: CANCEL_SCOPES,
  }),
  'cancel.result_unknown': eventRule({
    segments: CANCEL_SEGMENTS,
    required: ['outcome', 'reason_code', 'error_code', 'cancel_scope'],
    allowed: [...SOURCE_FACTS, 'outcome', 'reason_code', 'error_code', 'cancel_scope'],
    outcomes: ['unknown'],
    reasons: ['CANCEL_RESULT_UNKNOWN'],
    errors: ['RESULT_UNKNOWN'],
    cancel_scopes: CANCEL_SCOPES,
  }),
  'fence.stale_dropped': eventRule({
    segments: ['runtime.presentation'],
    required: ['reason_code', 'error_code'],
    allowed: [...SOURCE_FACTS, 'reason_code', 'error_code'],
    bindings: ['response_id'],
    reasons: ['STALE_GENERATION'],
    errors: ['STALE'],
  }),
  'task.state_observed': eventRule({
    segments: ['task.progress'],
    required: ['source_event_id', 'source_occurred_at', 'source_seq', 'state'],
    allowed: ['source_event_id', 'source_occurred_at', 'source_seq', 'state', 'outcome', 'reason_code'],
    bindings: ['task_id', 'attempt_id'],
    source_kind: 'event',
    states: ['accepted', 'running', 'blocked', 'decision_required', 'terminal'],
    outcomes: TERMINAL_OUTCOMES,
    reasons: ['TASK_FAILURE', 'CANCEL_TERMINAL'],
  }),
  'task.dispatch_outbox_observed': eventRule({
    segments: ['task.queue'],
    required: ['source_record_id', 'source_seq', 'state'],
    allowed: ['source_record_id', 'source_seq', 'state'],
    bindings: ['task_id', 'attempt_id'],
    source_kind: 'record',
    states: ['pending', 'claimed', 'delivered', 'suppressed'],
  }),
  'task.cancel_outbox_observed': eventRule({
    segments: ['task.queue'],
    required: ['source_record_id', 'source_seq', 'state'],
    allowed: ['source_record_id', 'source_seq', 'state'],
    bindings: ['task_id', 'attempt_id'],
    source_kind: 'record',
    states: ['pending', 'claimed', 'delivered', 'suppressed'],
  }),
  'task.adjust_outbox_observed': eventRule({
    segments: ['task.queue'],
    required: ['source_record_id', 'source_seq', 'state'],
    allowed: ['source_record_id', 'source_seq', 'state'],
    bindings: ['task_id', 'attempt_id'],
    source_kind: 'record',
    states: ['pending', 'claimed', 'delivered', 'suppressed'],
  }),
  'task.reconciliation_observed': eventRule({
    segments: ['task.attempt'],
    required: ['source_record_id', 'source_seq', 'state'],
    allowed: ['source_record_id', 'source_seq', 'state'],
    bindings: ['task_id', 'attempt_id'],
    source_kind: 'record',
    states: ['required', 'in_progress', 'pending', 'resolved'],
  }),
  'degradation.activated': eventRule({
    segments: ['system.degradation'],
    required: ['reason_code'],
    allowed: [...SOURCE_FACTS, 'reason_code'],
    reasons: ['DEGRADED'],
  }),
  'degradation.recovered': eventRule({
    segments: ['system.degradation'],
    required: ['reason_code'],
    allowed: [...SOURCE_FACTS, 'reason_code'],
    reasons: ['RECOVERED'],
  }),
  'failure.observed': eventRule({
    segments: FAILURE_SEGMENTS,
    required: ['reason_code', 'error_code'],
    allowed: [...SOURCE_FACTS, 'reason_code', 'error_code'],
    reasons: ['AGENT_FAILURE', 'PROTOCOL_REJECTED', 'PROVIDER_FAILURE', 'TASK_FAILURE', 'TIMEOUT', 'UNAVAILABLE'],
    errors: ERROR_CODES,
  }),
});

export interface TraceBindingInput {
  correlation_id: string;
  interaction_id?: string | null;
  turn_id?: string | null;
  response_id?: string | null;
  response_generation?: number | null;
  round_id?: string | null;
  task_id?: string | null;
  attempt_id?: string | null;
}

export interface TraceBinding {
  readonly correlation_id: string;
  readonly interaction_id: string | null;
  readonly turn_id: string | null;
  readonly response_id: string | null;
  readonly response_generation: number | null;
  readonly round_id: string | null;
  readonly task_id: string | null;
  readonly attempt_id: string | null;
}

export interface RouteDescriptorInput {
  implementation_class: string;
  owner_module: string | null;
  capability_provider: string | null;
  contract_version: string | null;
  reason_code: string | null;
}

export interface RouteDescriptor {
  readonly implementation_class: ObservedRouteClass;
  readonly owner_module: string | null;
  readonly capability_provider: string | null;
  readonly contract_version: string | null;
  readonly reason_code: LiveVoiceReasonCode | null;
}

export interface LiveVoiceObservationInput {
  schema_version: string;
  event_id: string;
  event_name: string;
  segment_name: string;
  observed_at: string;
  monotonic_ms: number;
  binding: TraceBindingInput | TraceBinding;
  route: RouteDescriptorInput | RouteDescriptor;
  source_component: string;
  source_event_id?: string | null;
  source_record_id?: string | null;
  source_occurred_at?: string | null;
  source_seq?: number | null;
  state?: string | null;
  outcome?: string | null;
  reason_code?: string | null;
  error_code?: string | null;
  duration_ms?: number | null;
  queue_depth?: number | null;
  queue_capacity?: number | null;
  cancel_scope?: string | null;
}

export interface LiveVoiceObservation {
  readonly schema_version: typeof OBSERVABILITY_SCHEMA_VERSION;
  readonly event_id: string;
  readonly event_name: LiveVoiceEventName;
  readonly segment_name: LiveVoiceSegmentName;
  readonly observed_at: string;
  readonly monotonic_ms: number;
  readonly binding: Readonly<TraceBinding>;
  readonly route: Readonly<RouteDescriptor>;
  readonly source_component: string;
  readonly source_event_id: string | null;
  readonly source_record_id: string | null;
  readonly source_occurred_at: string | null;
  readonly source_seq: number | null;
  readonly state: LiveVoiceObservedState | null;
  readonly outcome: LiveVoiceTerminalOutcome | null;
  readonly reason_code: LiveVoiceReasonCode | null;
  readonly error_code: LiveVoiceErrorCode | null;
  readonly duration_ms: number | null;
  readonly queue_depth: number | null;
  readonly queue_capacity: number | null;
  readonly cancel_scope: LiveVoiceCancelScope | null;
}

export class ObservabilityViolation extends Error {
  readonly reason: string;

  constructor(reason: string, message: string) {
    super(message);
    this.name = 'ObservabilityViolation';
    this.reason = reason;
  }
}

function violation(reason: string, message: string): ObservabilityViolation {
  return new ObservabilityViolation(reason, message);
}

function recordDescriptors(value: object, fieldName: string): PropertyDescriptorMap {
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw violation('INVALID_JSON_OBJECT', `${fieldName} must be a plain object`);
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some(key => typeof key !== 'string')) {
    throw violation('INVALID_OBJECT_KEY', `${fieldName} cannot contain symbol keys`);
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (
      descriptor === undefined ||
      !('value' in descriptor) ||
      descriptor.get !== undefined ||
      descriptor.set !== undefined ||
      descriptor.enumerable !== true
    ) {
      throw violation('INVALID_OBJECT_PROPERTY', `${fieldName}.${key} must be enumerable data`);
    }
  }
  return descriptors;
}

function strictRecord(value: unknown, fieldName: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw violation('INVALID_JSON_OBJECT', `${fieldName} must be a plain object`);
  }
  const descriptors = recordDescriptors(value, fieldName);
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(descriptors)) {
    Object.defineProperty(result, key, {
      value: descriptors[key].value,
      enumerable: true,
      configurable: true,
      writable: true,
    });
  }
  return result;
}

function exactKeys(record: Record<string, unknown>, fieldName: string, allowed: readonly string[], required: readonly string[]): void {
  for (const key of Object.keys(record)) {
    if (!allowed.includes(key)) throw violation('UNKNOWN_FIELD', `${fieldName} has unknown fields: ${key}`);
  }
  for (const key of required) {
    if (!(key in record)) throw violation('MISSING_REQUIRED_FIELD', `${fieldName} is missing: ${key}`);
  }
}

function validUnicode(value: string, fieldName: string): string {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (Number.isNaN(next) || next < 0xdc00 || next > 0xdfff) {
        throw violation('INVALID_UNICODE_SCALAR', `${fieldName} contains invalid Unicode`);
      }
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw violation('INVALID_UNICODE_SCALAR', `${fieldName} contains invalid Unicode`);
    }
  }
  return value;
}

function requiredText(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw violation('INVALID_REQUIRED_TEXT', `${fieldName} must be non-empty text`);
  }
  return validUnicode(value, fieldName);
}

function optionalText(value: unknown, fieldName: string): string | null {
  if (value === null || value === undefined) return null;
  return requiredText(value, fieldName);
}

function opaqueIdentity(value: unknown, fieldName: string): string {
  // This bounds the carrier; callers still must project an authoritative public
  // identity field because arbitrary opaque tokens cannot be content-classified.
  const result = requiredText(value, fieldName);
  const blockedMarker = /(?:^|[._:@-])(?:api[_-]?key|authorization|bearer|credential|password|passwd|secret|token|transcript)(?:$|[._:@-])/i;
  if (result.length > IDENTITY_MAX_LENGTH || !/^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$/.test(result) || blockedMarker.test(result)) {
    throw violation('INVALID_OPAQUE_IDENTITY', `${fieldName} must be a bounded opaque ID from a trusted identity field`);
  }
  return result;
}

function optionalIdentity(value: unknown, fieldName: string): string | null {
  if (value === null || value === undefined) return null;
  return opaqueIdentity(value, fieldName);
}

function stableToken(value: unknown, fieldName: string): string {
  const result = requiredText(value, fieldName);
  if (!/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(result)) {
    throw violation('INVALID_STABLE_TOKEN', `${fieldName} must be a bounded stable identifier`);
  }
  return result;
}

function utcTimestamp(value: unknown, fieldName: string): string {
  const result = requiredText(value, fieldName);
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?Z$/.exec(result);
  if (match === null) throw violation('INVALID_UTC_TIMESTAMP', `${fieldName} must be an RFC 3339 UTC timestamp`);
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hour, minute, second, 0);
  if (
    year === 0 ||
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day ||
    date.getUTCHours() !== hour ||
    date.getUTCMinutes() !== minute ||
    date.getUTCSeconds() !== second
  ) {
    throw violation('INVALID_UTC_TIMESTAMP', `${fieldName} must be an RFC 3339 UTC timestamp`);
  }
  return result;
}

function nonnegativeNumber(value: unknown, fieldName: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw violation('INVALID_NUMBER', `${fieldName} must be finite and non-negative`);
  }
  return value;
}

function safeInteger(value: unknown, fieldName: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    throw violation('INVALID_SAFE_INTEGER', `${fieldName} must be a non-negative safe integer`);
  }
  return value as number;
}

function optionalMember<T extends string>(value: unknown, allowed: readonly T[], fieldName: string): T | null {
  if (value === null || value === undefined) return null;
  const result = requiredText(value, fieldName);
  if (!allowed.includes(result as T)) throw violation('INVALID_VOCABULARY', `${fieldName} is not stable`);
  return result as T;
}

const BINDING_KEYS = Object.freeze([
  'correlation_id',
  'interaction_id',
  'turn_id',
  'response_id',
  'response_generation',
  'round_id',
  'task_id',
  'attempt_id',
] as const);

export function createTraceBinding(value: TraceBindingInput | TraceBinding): Readonly<TraceBinding> {
  const data = strictRecord(value, 'binding');
  exactKeys(data, 'binding', BINDING_KEYS, ['correlation_id']);
  const result: TraceBinding = {
    correlation_id: opaqueIdentity(data.correlation_id, 'binding.correlation_id'),
    interaction_id: optionalIdentity(data.interaction_id, 'binding.interaction_id'),
    turn_id: optionalIdentity(data.turn_id, 'binding.turn_id'),
    response_id: optionalIdentity(data.response_id, 'binding.response_id'),
    response_generation:
      data.response_generation === null || data.response_generation === undefined ? null : safeInteger(data.response_generation, 'binding.response_generation'),
    round_id: optionalIdentity(data.round_id, 'binding.round_id'),
    task_id: optionalIdentity(data.task_id, 'binding.task_id'),
    attempt_id: optionalIdentity(data.attempt_id, 'binding.attempt_id'),
  };
  if (result.turn_id !== null && result.interaction_id === null) {
    throw violation('TURN_INTERACTION_BINDING_REQUIRED', 'turn_id requires interaction_id');
  }
  if (result.response_id !== null || result.response_generation !== null) {
    if (result.interaction_id === null || result.response_id === null || result.response_generation === null) {
      throw violation('RESPONSE_BINDING_INCOMPLETE', 'response binding requires interaction_id, response_id, and generation');
    }
  }
  if (result.attempt_id !== null && result.task_id === null) {
    throw violation('ATTEMPT_TASK_BINDING_REQUIRED', 'attempt_id requires task_id');
  }
  return Object.freeze(result);
}

function validateCancelTarget(cancelScope: LiveVoiceCancelScope, binding: Readonly<TraceBinding>): void {
  if (cancelScope === 'playback.stop' || cancelScope === 'response.cancel') {
    if (binding.response_id === null) {
      throw violation('CANCEL_TARGET_BINDING_REQUIRED', `${cancelScope} requires the exact response tuple`);
    }
  } else if (cancelScope === 'round.cancel') {
    if (binding.round_id === null) throw violation('CANCEL_TARGET_BINDING_REQUIRED', 'round.cancel requires round_id');
  } else if (binding.task_id === null) {
    throw violation('CANCEL_TARGET_BINDING_REQUIRED', 'task.cancel requires task_id');
  }
}

const ROUTE_KEYS = Object.freeze(['implementation_class', 'owner_module', 'capability_provider', 'contract_version', 'reason_code'] as const);
const ROUTE_REASON: Readonly<Record<Exclude<ObservedRouteClass, 'formal'>, LiveVoiceReasonCode>> = Object.freeze({
  fallback: 'ROUTE_FALLBACK',
  demo_substitute: 'DEMO_SUBSTITUTE',
  unsupported: 'UNSUPPORTED_CAPABILITY',
  unknown: 'UNKNOWN_PROVENANCE',
});
const FAILURE_REASONS = Object.freeze(['PROVIDER_FAILURE', 'AGENT_FAILURE', 'TASK_FAILURE', 'TIMEOUT', 'UNAVAILABLE', 'PROTOCOL_REJECTED'] as const);
export const FAILURE_ERROR_MATRIX: Readonly<Record<(typeof FAILURE_REASONS)[number], readonly LiveVoiceErrorCode[]>> = Object.freeze({
  PROVIDER_FAILURE: Object.freeze(ERROR_CODES.filter(code => !['STALE', 'CANCELLED', 'RESULT_UNKNOWN'].includes(code))),
  AGENT_FAILURE: Object.freeze(ERROR_CODES.filter(code => !['STALE', 'CANCELLED', 'RESULT_UNKNOWN'].includes(code))),
  TASK_FAILURE: Object.freeze(ERROR_CODES.filter(code => !['STALE', 'CANCELLED', 'RESULT_UNKNOWN'].includes(code))),
  TIMEOUT: Object.freeze(['TIMEOUT'] as const),
  UNAVAILABLE: Object.freeze(['CAPABILITY_UNAVAILABLE', 'UNAVAILABLE'] as const),
  PROTOCOL_REJECTED: Object.freeze(['INVALID_ARGUMENT', 'UNSUPPORTED', 'CONFLICT', 'STALE', 'PROTOCOL_VIOLATION'] as const),
});
export const FAILURE_SEGMENT_MATRIX: Readonly<Record<(typeof FAILURE_REASONS)[number], readonly LiveVoiceSegmentName[]>> = Object.freeze({
  PROVIDER_FAILURE: Object.freeze(FAILURE_SEGMENTS.filter(segment => segment.startsWith('speech.'))),
  AGENT_FAILURE: Object.freeze(['agent.dispatch', 'agent.progress'] as const),
  TASK_FAILURE: Object.freeze(FAILURE_SEGMENTS.filter(segment => segment.startsWith('task.'))),
  TIMEOUT: FAILURE_SEGMENTS,
  UNAVAILABLE: FAILURE_SEGMENTS,
  PROTOCOL_REJECTED: FAILURE_SEGMENTS,
});

function validateFailureTarget(reasonCode: LiveVoiceReasonCode, binding: Readonly<TraceBinding>, route: Readonly<RouteDescriptor>): void {
  if (reasonCode === 'PROVIDER_FAILURE' && route.capability_provider === null) {
    throw violation('FAILURE_TARGET_BINDING_REQUIRED', 'Provider failure requires exact route provider provenance');
  }
  if (reasonCode === 'AGENT_FAILURE' && binding.round_id === null) {
    throw violation('FAILURE_TARGET_BINDING_REQUIRED', 'Agent failure requires round_id');
  }
  if (reasonCode === 'TASK_FAILURE' && binding.task_id === null) {
    throw violation('FAILURE_TARGET_BINDING_REQUIRED', 'Task failure requires task_id');
  }
}

function validateFailurePair(reasonCode: LiveVoiceReasonCode, errorCode: LiveVoiceErrorCode): void {
  const allowed = FAILURE_ERROR_MATRIX[reasonCode as (typeof FAILURE_REASONS)[number]];
  if (allowed === undefined || !allowed.includes(errorCode)) {
    throw violation('FAILURE_ERROR_MISMATCH', 'failure reason and error code do not describe the same governed failure');
  }
}

function validateFailureSegment(reasonCode: LiveVoiceReasonCode, segmentName: LiveVoiceSegmentName): void {
  const allowed = FAILURE_SEGMENT_MATRIX[reasonCode as (typeof FAILURE_REASONS)[number]];
  if (allowed === undefined || !allowed.includes(segmentName)) {
    throw violation('FAILURE_SEGMENT_MISMATCH', 'failure reason cannot describe this segment');
  }
}

function validateRequiredBindings(required: readonly string[], binding: Readonly<TraceBinding>, owner: string): void {
  const identity = binding as unknown as Readonly<Record<string, unknown>>;
  for (const fieldName of required) {
    if (identity[fieldName] === null || identity[fieldName] === undefined) {
      throw violation('SEMANTIC_TARGET_BINDING_REQUIRED', `${owner} requires binding.${fieldName}`);
    }
  }
}

export const SEGMENT_BINDING_MATRIX: Readonly<Record<string, readonly string[]>> = Object.freeze({
  'speech.capture': Object.freeze(['interaction_id']),
  'speech.recognition': Object.freeze(['interaction_id']),
  'speech.synthesis': Object.freeze(['response_id']),
  'speech.playout': Object.freeze(['response_id']),
  'runtime.turn': Object.freeze(['turn_id']),
  'runtime.response': Object.freeze(['response_id']),
  'runtime.presentation': Object.freeze(['response_id']),
  'runtime.queue': Object.freeze([]),
  'agent.dispatch': Object.freeze(['round_id']),
  'agent.progress': Object.freeze(['round_id']),
  'agent.queue': Object.freeze(['round_id']),
  'task.command': Object.freeze(['task_id']),
  'task.attempt': Object.freeze(['task_id', 'attempt_id']),
  'task.progress': Object.freeze(['task_id']),
  'task.queue': Object.freeze(['task_id']),
});

function validateSegmentTarget(segmentName: LiveVoiceSegmentName, binding: Readonly<TraceBinding>, owner: string): void {
  validateRequiredBindings(SEGMENT_BINDING_MATRIX[segmentName] ?? [], binding, owner);
}

export const CANCEL_TARGET_SEGMENT_MATRIX: Readonly<Record<LiveVoiceCancelScope, LiveVoiceSegmentName>> = Object.freeze({
  'playback.stop': 'speech.playout',
  'response.cancel': 'runtime.response',
  'round.cancel': 'agent.progress',
  'task.cancel': 'task.command',
});

export function createRouteDescriptor(value: RouteDescriptorInput | RouteDescriptor): Readonly<RouteDescriptor> {
  const data = strictRecord(value, 'route');
  exactKeys(data, 'route', ROUTE_KEYS, ROUTE_KEYS);
  const implementationClass = requiredText(data.implementation_class, 'route.implementation_class');
  if (!ROUTE_IMPLEMENTATION_CLASSES.includes(implementationClass as ObservedRouteClass)) {
    throw violation('INVALID_ROUTE_CLASS', 'implementation_class is not stable');
  }
  const ownerModule = data.owner_module === null ? null : stableToken(data.owner_module, 'route.owner_module');
  const capabilityProvider = data.capability_provider === null ? null : stableToken(data.capability_provider, 'route.capability_provider');
  const contractVersion = optionalText(data.contract_version, 'route.contract_version');
  const reasonCode = optionalMember(data.reason_code, REASON_CODES, 'route.reason_code');
  const routeClass = implementationClass as ObservedRouteClass;
  if (routeClass === 'formal') {
    if (ownerModule === null || capabilityProvider === null || contractVersion !== LIVE_VOICE_CONTRACT_VERSION || reasonCode !== null) {
      throw violation('MISSING_FORMAL_PROVENANCE', 'formal route requires exact v2 provenance');
    }
  } else {
    if (reasonCode !== ROUTE_REASON[routeClass]) {
      throw violation('INVALID_ROUTE_REASON', 'non-formal route requires its redacted reason code');
    }
    if (routeClass !== 'unknown' && ownerModule === null) {
      throw violation('MISSING_ROUTE_OWNER', 'known non-formal route requires owner_module');
    }
  }
  return Object.freeze({
    implementation_class: routeClass,
    owner_module: ownerModule,
    capability_provider: capabilityProvider,
    contract_version: contractVersion,
    reason_code: reasonCode,
  });
}

const OBSERVATION_KEYS = Object.freeze([
  'schema_version',
  'event_id',
  'event_name',
  'segment_name',
  'observed_at',
  'monotonic_ms',
  'binding',
  'route',
  'source_component',
  'source_event_id',
  'source_record_id',
  'source_occurred_at',
  'source_seq',
  'state',
  'outcome',
  'reason_code',
  'error_code',
  'duration_ms',
  'queue_depth',
  'queue_capacity',
  'cancel_scope',
] as const);
const OBSERVATION_REQUIRED = Object.freeze([
  'schema_version',
  'event_id',
  'event_name',
  'segment_name',
  'observed_at',
  'monotonic_ms',
  'binding',
  'route',
  'source_component',
] as const);

export function createObservation(value: LiveVoiceObservationInput | LiveVoiceObservation): Readonly<LiveVoiceObservation> {
  const data = strictRecord(value, 'observation');
  exactKeys(data, 'observation', OBSERVATION_KEYS, OBSERVATION_REQUIRED);
  if (data.schema_version !== OBSERVABILITY_SCHEMA_VERSION) {
    throw violation('INVALID_SCHEMA_VERSION', 'unsupported observability schema');
  }
  const eventName = requiredText(data.event_name, 'observation.event_name');
  if (!EVENT_NAMES.includes(eventName as LiveVoiceEventName)) throw violation('INVALID_EVENT_NAME', 'event_name is not stable');
  const segmentName = requiredText(data.segment_name, 'observation.segment_name');
  if (!SEGMENT_NAMES.includes(segmentName as LiveVoiceSegmentName)) {
    throw violation('INVALID_SEGMENT_NAME', 'segment_name is not stable');
  }
  const binding = createTraceBinding(data.binding as TraceBindingInput);
  const route = createRouteDescriptor(data.route as RouteDescriptorInput);
  const result: LiveVoiceObservation = {
    schema_version: OBSERVABILITY_SCHEMA_VERSION,
    event_id: opaqueIdentity(data.event_id, 'observation.event_id'),
    event_name: eventName as LiveVoiceEventName,
    segment_name: segmentName as LiveVoiceSegmentName,
    observed_at: utcTimestamp(data.observed_at, 'observation.observed_at'),
    monotonic_ms: nonnegativeNumber(data.monotonic_ms, 'observation.monotonic_ms'),
    binding,
    route,
    source_component: stableToken(data.source_component, 'observation.source_component'),
    source_event_id: optionalIdentity(data.source_event_id, 'observation.source_event_id'),
    source_record_id: optionalIdentity(data.source_record_id, 'observation.source_record_id'),
    source_occurred_at:
      data.source_occurred_at === null || data.source_occurred_at === undefined
        ? null
        : utcTimestamp(data.source_occurred_at, 'observation.source_occurred_at'),
    source_seq: data.source_seq === null || data.source_seq === undefined ? null : safeInteger(data.source_seq, 'observation.source_seq'),
    state: optionalMember(data.state, OBSERVED_STATES, 'observation.state'),
    outcome: optionalMember(data.outcome, TERMINAL_OUTCOMES, 'observation.outcome'),
    reason_code: optionalMember(data.reason_code, REASON_CODES, 'observation.reason_code'),
    error_code: optionalMember(data.error_code, ERROR_CODES, 'observation.error_code'),
    duration_ms: data.duration_ms === null || data.duration_ms === undefined ? null : nonnegativeNumber(data.duration_ms, 'observation.duration_ms'),
    queue_depth: data.queue_depth === null || data.queue_depth === undefined ? null : safeInteger(data.queue_depth, 'observation.queue_depth'),
    queue_capacity: data.queue_capacity === null || data.queue_capacity === undefined ? null : safeInteger(data.queue_capacity, 'observation.queue_capacity'),
    cancel_scope: optionalMember(data.cancel_scope, CANCEL_SCOPES, 'observation.cancel_scope'),
  };
  validateObservationSemantics(result);
  return Object.freeze(result);
}

function validateObservationSemantics(event: LiveVoiceObservation): void {
  if (event.source_event_id !== null && event.source_record_id !== null) {
    throw violation('SOURCE_KIND_CONFLICT', 'one observation cannot label a source as both Event and record');
  }
  if (event.source_occurred_at !== null && event.source_event_id === null) {
    throw violation('SOURCE_EVENT_REQUIRED', 'source occurrence time requires source_event_id');
  }
  if (event.source_seq !== null && event.source_event_id === null && event.source_record_id === null) {
    throw violation('SOURCE_ID_REQUIRED', 'source sequence requires an exact source ID');
  }

  const rule = EVENT_SEMANTIC_MATRIX[event.event_name];
  if (!rule.segments.includes(event.segment_name)) {
    throw violation('EVENT_SEGMENT_MISMATCH', 'event_name cannot describe this segment');
  }
  const populated = EVENT_FACTS.filter(fieldName => event[fieldName] !== null);
  const forbidden = populated.filter(fieldName => !rule.allowed_facts.includes(fieldName));
  if (forbidden.length > 0) {
    throw violation('EVENT_FACT_FORBIDDEN', `${event.event_name} forbids ${forbidden.sort()[0]}`);
  }
  const missing = rule.required_facts.filter(fieldName => !populated.includes(fieldName as (typeof EVENT_FACTS)[number]));
  if (missing.length > 0) {
    throw violation('EVENT_FACT_REQUIRED', `${event.event_name} requires ${[...missing].sort()[0]}`);
  }
  validateRequiredBindings(rule.required_bindings, event.binding, event.event_name);

  const semanticValues: readonly [
    LiveVoiceObservedState | LiveVoiceTerminalOutcome | LiveVoiceReasonCode | LiveVoiceErrorCode | LiveVoiceCancelScope | null,
    readonly string[],
    string,
  ][] = [
    [event.state, rule.states, 'state'],
    [event.outcome, rule.outcomes, 'outcome'],
    [event.reason_code, rule.reasons, 'reason_code'],
    [event.error_code, rule.errors, 'error_code'],
    [event.cancel_scope, rule.cancel_scopes, 'cancel_scope'],
  ];
  for (const [value, allowedValues, fieldName] of semanticValues) {
    if (value !== null && !allowedValues.includes(value)) {
      throw violation('EVENT_VALUE_MISMATCH', `${event.event_name} forbids ${fieldName}=${value}`);
    }
  }

  if (event.event_name === 'route.selected' && event.reason_code !== event.route.reason_code) {
    throw violation('ROUTE_REASON_MISMATCH', 'route event reason must match route provenance');
  }

  if (event.event_name.startsWith('segment.')) {
    validateSegmentTarget(event.segment_name, event.binding, event.event_name);
  }

  if (event.event_name === 'speech.capture_state' || event.event_name === 'speech.playout_state') {
    const failed = event.state === 'failed';
    const hasFailure = event.reason_code !== null || event.error_code !== null;
    if (failed !== hasFailure || (failed && (event.reason_code !== 'UNAVAILABLE' || event.error_code !== 'UNAVAILABLE'))) {
      throw violation('AUDIO_STATE_FACT_MISMATCH', 'only failed audio state carries UNAVAILABLE reason and error');
    }
  }

  if (event.event_name === 'speech.device_change') {
    const expectedError = event.reason_code === 'DEVICE_ENUMERATION_FAILED' ? 'UNAVAILABLE' : null;
    if (event.error_code !== expectedError) {
      throw violation('DEVICE_FACT_MISMATCH', 'device reason and error code must describe the same event');
    }
  }

  if (event.event_name === 'queue.pressure') {
    if (event.queue_depth === null || event.queue_capacity === null || event.queue_capacity === 0 || event.queue_depth < event.queue_capacity) {
      throw violation('QUEUE_PRESSURE_INCOMPLETE', 'queue pressure requires a full bounded queue');
    }
    validateSegmentTarget(event.segment_name, event.binding, event.event_name);
  }

  if (event.event_name.startsWith('cancel.')) {
    if (event.cancel_scope === null) throw violation('EVENT_FACT_REQUIRED', 'cancel scope is required');
    if (CANCEL_TARGET_SEGMENT_MATRIX[event.cancel_scope] !== event.segment_name) {
      throw violation('CANCEL_SEGMENT_MISMATCH', 'cancel scope must name its exact target segment');
    }
    validateCancelTarget(event.cancel_scope, event.binding);
  }

  if (event.event_name === 'segment.failed' || event.event_name === 'failure.observed') {
    if (event.reason_code === null || event.error_code === null) throw violation('EVENT_FACT_REQUIRED', 'failure facts are required');
    validateFailurePair(event.reason_code, event.error_code);
    validateFailureTarget(event.reason_code, event.binding, event.route);
    validateSegmentTarget(event.segment_name, event.binding, event.event_name);
    validateFailureSegment(event.reason_code, event.segment_name);
  }

  if (event.event_name === 'task.state_observed' && event.state === 'terminal') {
    const expectedTaskReason = event.outcome === 'failed' ? 'TASK_FAILURE' : event.outcome === 'cancelled' ? 'CANCEL_TERMINAL' : null;
    if (event.outcome === null || event.reason_code !== expectedTaskReason) {
      throw violation('TASK_TERMINAL_FACT_MISMATCH', 'task outcome and reason must describe the same terminal fact');
    }
  } else if (event.event_name === 'task.state_observed' && (event.outcome !== null || event.reason_code !== null)) {
    throw violation('TASK_NONTERMINAL_FACT_FORBIDDEN', 'nonterminal task evidence cannot carry terminal facts');
  }
}
