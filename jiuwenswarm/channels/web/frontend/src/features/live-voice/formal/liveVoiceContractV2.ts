// Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

export const CONTRACT_VERSION = 'live-voice.contract.v2' as const;
export const MAX_SAFE_INTEGER = 9_007_199_254_740_991;

export type ErrorCode =
  | 'INVALID_ARGUMENT'
  | 'UNSUPPORTED'
  | 'UNAUTHENTICATED'
  | 'PERMISSION_DENIED'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'STALE'
  | 'CAPABILITY_UNAVAILABLE'
  | 'UNAVAILABLE'
  | 'TIMEOUT'
  | 'CANCELLED'
  | 'PROTOCOL_VIOLATION'
  | 'RESULT_UNKNOWN'
  | 'INTERNAL';

export type Assurance = 'request_asserted' | 'authenticated';
export type IdentityKind =
  | 'connection'
  | 'media_session'
  | 'track'
  | 'interaction'
  | 'turn'
  | 'response'
  | 'round'
  | 'task'
  | 'attempt'
  | 'command'
  | 'request'
  | 'event';
export type TerminalOutcome = 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown';
export type WorkState = 'accepted' | 'running' | 'blocked' | 'decision_required' | 'terminal';
export type WorkSourceAuthority = 'harness' | 'task_core' | 'executor';
export type WorkUrgency = 'normal' | 'attention' | 'urgent' | 'unknown';
export type Speakability = 'not_speakable' | 'eligible' | 'attention_requested';
export type KnownFact<T> = { readonly knowledge: 'known'; readonly value: T } | { readonly knowledge: 'unknown' };

export type JsonPrimitive = null | boolean | number | string;
export type JsonValue = JsonPrimitive | readonly JsonValue[] | { readonly [key: string]: JsonValue };
export type JsonObject = { readonly [key: string]: JsonValue };

export interface ContractErrorValue {
  readonly code: ErrorCode;
  readonly reason: string | null;
  readonly message: string;
  readonly retriable: boolean;
  readonly correlation_id: string | null;
  readonly details: Readonly<JsonObject>;
}

export class ContractViolation extends Error {
  readonly error: ContractErrorValue;

  constructor(error: ContractErrorValue) {
    super(error.message);
    this.name = 'ContractViolation';
    this.error = error;
  }
}

function violation(reason: string, message: string, code: ErrorCode = 'INVALID_ARGUMENT'): ContractViolation {
  return new ContractViolation(
    Object.freeze({
      code,
      reason,
      message,
      retriable: false,
      correlation_id: null,
      details: Object.freeze({}),
    })
  );
}

function validUnicode(value: string, fieldName: string): string {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw violation('INVALID_UNICODE_SCALAR', `${fieldName} contains an unpaired surrogate`);
      }
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw violation('INVALID_UNICODE_SCALAR', `${fieldName} contains an unpaired surrogate`);
    }
  }
  return value;
}

function requiredText(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw violation('INVALID_REQUIRED_TEXT', `${fieldName} must be a non-empty string`);
  }
  return validUnicode(value, fieldName);
}

const CONTEXT_WHITESPACE = new Set([
  0x0085, 0x00a0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
  0xfeff,
]);

function isContextWhitespaceOrControl(code: number): boolean {
  return code <= 0x20 || (code >= 0x7f && code <= 0x9f) || CONTEXT_WHITESPACE.has(code);
}

function contextRequiredText(value: unknown, fieldName: string): string {
  if (typeof value !== 'string') {
    throw violation('INVALID_REQUIRED_TEXT', `${fieldName} must be a non-empty string`);
  }
  const normalized = validUnicode(value, fieldName);
  if (![...normalized].some(char => !isContextWhitespaceOrControl(char.codePointAt(0) ?? 0))) {
    throw violation('INVALID_REQUIRED_TEXT', `${fieldName} must be a non-empty string`);
  }
  return normalized;
}

function contextUri(value: unknown): string {
  const uri = contextRequiredText(value, 'context_ref.uri');
  const scheme = /^[A-Za-z][A-Za-z0-9+.-]*:/.exec(uri);
  if (scheme === null || scheme[0].length === uri.length || [...uri].some(char => isContextWhitespaceOrControl(char.codePointAt(0) ?? 0))) {
    throw violation('INVALID_CONTEXT_URI', 'context_ref.uri must be a non-empty absolute URI without whitespace or controls');
  }
  return uri;
}

function optionalId(value: unknown, fieldName: string): string | null {
  return value === null ? null : requiredText(value, fieldName);
}

function requiredBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value !== 'boolean') {
    throw violation('INVALID_BOOLEAN', `${fieldName} must be a boolean`);
  }
  return value;
}

function unsignedInteger(value: unknown, fieldName: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0 || value > MAX_SAFE_INTEGER) {
    throw violation('INVALID_SAFE_INTEGER', `${fieldName} must be an integer between 0 and ${MAX_SAFE_INTEGER}`);
  }
  return value;
}

function timestamp(value: unknown, fieldName: string): string {
  const parsed = requiredText(value, fieldName);
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?Z$/.exec(parsed);
  if (match === null) {
    throw violation('INVALID_UTC_TIMESTAMP', `${fieldName} must be an RFC 3339 UTC timestamp`);
  }
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
    throw violation('INVALID_UTC_TIMESTAMP', `${fieldName} is not a real timestamp`);
  }
  return parsed;
}

function namespaced(value: unknown, fieldName: string): string {
  const parsed = requiredText(value, fieldName);
  if (!/^[a-z][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)+$/.test(parsed)) {
    throw violation('INVALID_NAMESPACED_VALUE', `${fieldName} must be namespaced`);
  }
  return parsed;
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

function strictArray(value: unknown, fieldName: string): unknown[] {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    throw violation('INVALID_JSON_ARRAY', `${fieldName} must be an ordinary array`);
  }
  const keys = Reflect.ownKeys(value);
  for (const key of keys) {
    if (typeof key === 'symbol') {
      throw violation('INVALID_ARRAY_PROPERTY', `${fieldName} cannot contain symbol keys`);
    }
    if (key === 'length') continue;
    if (!/^(0|[1-9]\d*)$/.test(key)) {
      throw violation('INVALID_ARRAY_PROPERTY', `${fieldName} cannot contain extra properties`);
    }
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor === undefined || !('value' in descriptor) || descriptor.enumerable !== true) {
      throw violation('INVALID_ARRAY_PROPERTY', `${fieldName}[${key}] must be enumerable data`);
    }
  }
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.prototype.hasOwnProperty.call(value, index)) {
      throw violation('SPARSE_ARRAY', `${fieldName} must be dense`);
    }
  }
  return value.map(item => item);
}

function exactKeys(value: Record<string, unknown>, required: readonly string[], fieldName: string, optional: readonly string[] = []): void {
  const actual = Object.keys(value).sort();
  const expected = [...required].sort();
  const allowed = [...required, ...optional];
  const missing = expected.filter(key => !actual.includes(key));
  const unknown = actual.filter(key => !allowed.includes(key));
  if (missing.length > 0) {
    throw violation('MISSING_REQUIRED_FIELD', `${fieldName} is missing: ${missing.join(', ')}`);
  }
  if (unknown.length > 0) {
    throw violation('UNKNOWN_FIELD', `${fieldName} has unknown fields: ${unknown.join(', ')}`);
  }
}

function cloneJson(value: unknown, fieldName: string, ancestors: ReadonlySet<object> = new Set<object>()): JsonValue {
  if (value === null) return null;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return validUnicode(value, fieldName);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw violation('INVALID_NUMBER', `${fieldName} must be finite`);
    }
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw violation('INVALID_SAFE_INTEGER', `${fieldName} exceeds the shared safe integer range`);
    }
    return Object.is(value, -0) ? 0 : value;
  }
  if (typeof value !== 'object') {
    throw violation('INVALID_JSON_VALUE', `${fieldName} is not JSON data`);
  }
  if (ancestors.has(value)) {
    throw violation('CYCLIC_JSON', `${fieldName} contains a cycle`);
  }
  const nextAncestors = new Set(ancestors);
  nextAncestors.add(value);
  if (Array.isArray(value)) {
    const items = strictArray(value, fieldName).map((item, index) => cloneJson(item, `${fieldName}[${index}]`, nextAncestors));
    return Object.freeze(items);
  }
  const data = strictRecord(value, fieldName);
  const result: Record<string, JsonValue> = {};
  for (const key of Object.keys(data).sort()) {
    validUnicode(key, `${fieldName} key`);
    Object.defineProperty(result, key, {
      value: cloneJson(data[key], `${fieldName}.${key}`, nextAncestors),
      enumerable: true,
      configurable: true,
      writable: true,
    });
  }
  return Object.freeze(result);
}

function cloneObject(value: unknown, fieldName: string): Readonly<JsonObject> {
  const cloned = cloneJson(value, fieldName);
  if (cloned === null || Array.isArray(cloned) || typeof cloned !== 'object') {
    throw violation('INVALID_JSON_OBJECT', `${fieldName} must be an object`);
  }
  return cloned as Readonly<JsonObject>;
}

export function canonicalJson(value: unknown): string {
  const cloned = cloneJson(value, '$');
  const encode = (item: JsonValue): string => {
    if (item === null || typeof item === 'boolean' || typeof item === 'number') {
      return JSON.stringify(item);
    }
    if (typeof item === 'string') return JSON.stringify(item);
    if (Array.isArray(item)) return `[${item.map(encode).join(',')}]`;
    const objectItem = item as Readonly<JsonObject>;
    return `{${Object.keys(objectItem)
      .sort()
      .map(key => `${JSON.stringify(key)}:${encode(objectItem[key])}`)
      .join(',')}}`;
  };
  return encode(cloned);
}

const ASSURANCES = ['request_asserted', 'authenticated'] as const;
const IDENTITY_KINDS = [
  'connection',
  'media_session',
  'track',
  'interaction',
  'turn',
  'response',
  'round',
  'task',
  'attempt',
  'command',
  'request',
  'event',
] as const;

function enumeration<T extends string>(values: readonly T[], value: unknown, fieldName: string): T {
  if (typeof value !== 'string' || !values.includes(value as T)) {
    throw violation('INVALID_ENUM', `${fieldName} is not a supported value`);
  }
  return value as T;
}

export interface ScopeRef {
  readonly subject_id: string;
  readonly project_id: string | null;
  readonly session_id: string | null;
  readonly assurance: Assurance;
}

export function parseScopeRef(value: unknown): Readonly<ScopeRef> {
  const data = strictRecord(value, 'scope');
  exactKeys(data, ['subject_id', 'project_id', 'session_id', 'assurance'], 'scope');
  return Object.freeze({
    subject_id: requiredText(data.subject_id, 'scope.subject_id'),
    project_id: optionalId(data.project_id, 'scope.project_id'),
    session_id: optionalId(data.session_id, 'scope.session_id'),
    assurance: enumeration(ASSURANCES, data.assurance, 'scope.assurance'),
  });
}

export type ContextRevision = { readonly kind: 'version' | 'snapshot'; readonly value: string } | { readonly kind: 'unversioned' };

export interface ContextRedaction {
  readonly policy_id: string;
  readonly redacted: boolean;
  readonly fields: readonly string[];
}

export interface ContextRef {
  readonly source: string;
  readonly stable_id: string;
  readonly uri: string;
  readonly revision: Readonly<ContextRevision>;
  readonly scope: Readonly<ScopeRef>;
  readonly permissions: readonly string[];
  readonly expires_at: string | null;
  readonly redaction: Readonly<ContextRedaction>;
  readonly extensions: Readonly<JsonObject>;
}

function parseContextRevision(value: unknown): Readonly<ContextRevision> {
  const data = strictRecord(value, 'context_ref.revision');
  const kind = enumeration(['version', 'snapshot', 'unversioned'] as const, data.kind, 'context_ref.revision.kind');
  if (kind === 'unversioned') {
    exactKeys(data, ['kind'], 'context_ref.revision');
    return Object.freeze({ kind });
  }
  exactKeys(data, ['kind', 'value'], 'context_ref.revision');
  return Object.freeze({ kind, value: contextRequiredText(data.value, 'context_ref.revision.value') });
}

function parseContextRedaction(value: unknown): Readonly<ContextRedaction> {
  const data = strictRecord(value, 'context_ref.redaction');
  exactKeys(data, ['policy_id', 'redacted', 'fields'], 'context_ref.redaction');
  const fields: string[] = [];
  strictArray(data.fields, 'context_ref.redaction.fields').forEach((item, index) => {
    fields.push(contextRequiredText(item, `context_ref.redaction.fields[${index}]`));
  });
  return Object.freeze({
    policy_id: contextRequiredText(data.policy_id, 'context_ref.redaction.policy_id'),
    redacted: requiredBoolean(data.redacted, 'context_ref.redaction.redacted'),
    fields: Object.freeze(fields),
  });
}

export function parseContextRef(value: unknown): Readonly<ContextRef> {
  const data = strictRecord(value, 'context_ref');
  exactKeys(data, ['source', 'stable_id', 'uri', 'revision', 'scope', 'permissions', 'expires_at', 'redaction', 'extensions'], 'context_ref');
  const uri = contextUri(data.uri);
  const permissions: string[] = [];
  strictArray(data.permissions, 'context_ref.permissions').forEach((item, index) => {
    permissions.push(namespaced(item, `context_ref.permissions[${index}]`));
  });
  return Object.freeze({
    source: namespaced(data.source, 'context_ref.source'),
    stable_id: contextRequiredText(data.stable_id, 'context_ref.stable_id'),
    uri,
    revision: parseContextRevision(data.revision),
    scope: parseScopeRef(data.scope),
    permissions: Object.freeze(permissions),
    expires_at: data.expires_at === null ? null : timestamp(data.expires_at, 'context_ref.expires_at'),
    redaction: parseContextRedaction(data.redaction),
    extensions: extensions(data.extensions, 'context_ref.extensions'),
  });
}

export interface IdentityRef {
  readonly kind: IdentityKind;
  readonly id: string;
}

export function parseIdentityRef(value: unknown, expectedKind?: IdentityKind): Readonly<IdentityRef> {
  const data = strictRecord(value, 'identity_ref');
  exactKeys(data, ['kind', 'id'], 'identity_ref');
  const kind = enumeration(IDENTITY_KINDS, data.kind, 'identity_ref.kind');
  if (expectedKind !== undefined && kind !== expectedKind) {
    throw violation('IDENTITY_KIND_MISMATCH', `expected ${expectedKind}, received ${kind}`);
  }
  return Object.freeze({ kind, id: requiredText(data.id, 'identity_ref.id') });
}

export interface ConnectionEpochRef {
  readonly connection_id: string;
  readonly connection_epoch: number;
}

export interface ProducerRef {
  readonly component: string;
  readonly instance_id: string;
  readonly authority: string;
}

function parseProducerRef(value: unknown): Readonly<ProducerRef> {
  const data = strictRecord(value, 'producer');
  exactKeys(data, ['component', 'instance_id', 'authority'], 'producer');
  return Object.freeze({
    component: requiredText(data.component, 'producer.component'),
    instance_id: requiredText(data.instance_id, 'producer.instance_id'),
    authority: requiredText(data.authority, 'producer.authority'),
  });
}

export interface IdentityRecord {
  readonly ref: Readonly<IdentityRef>;
  readonly scope: Readonly<ScopeRef>;
  readonly parents: readonly Readonly<IdentityRef>[];
  readonly connection_epoch_ref?: Readonly<ConnectionEpochRef> | null;
}

function scopeKey(scope: Readonly<ScopeRef>): string {
  return canonicalJson(scope);
}

export interface IdentityRegistry {
  require(ref: Readonly<IdentityRef>, options?: { scope?: Readonly<ScopeRef>; parent?: Readonly<IdentityRef> }): IdentityRecord;
}

const COMMAND_TARGETS: Readonly<Record<string, IdentityKind>> = Object.freeze({
  'task.create': 'task',
  'task.adjust': 'task',
  'task.update': 'task',
  'task.provide_input': 'task',
  'task.pause': 'task',
  'task.resume': 'task',
  'task.reprioritize': 'task',
  'task.create_successor': 'task',
  'task.ack_events': 'task',
  'playback.stop': 'response',
  'response.cancel': 'response',
  'round.cancel': 'round',
  'task.cancel': 'task',
  'task.retry': 'task',
});
const QUERY_TARGETS: Readonly<Record<string, IdentityKind>> = Object.freeze({
  'task.get': 'task',
  'task.list': 'task',
  'task.status': 'task',
  'task.events': 'task',
  'task.result': 'task',
  'task.unread_events': 'task',
});
const CORE_CAPABILITIES = new Set([
  ...Object.keys(COMMAND_TARGETS),
  ...Object.keys(QUERY_TARGETS),
  'event.replay',
  'recognize.batch',
  'recognize.stream',
  'synthesize.batch',
  'synthesize.stream',
  'cancel.ack',
]);

function extensions(value: unknown, fieldName: string): Readonly<JsonObject> {
  const data = strictRecord(value, fieldName);
  for (const key of Object.keys(data)) namespaced(key, `${fieldName} key`);
  return cloneObject(data, fieldName);
}

function capabilityList(value: unknown, fieldName: string): readonly string[] {
  const result: string[] = [];
  strictArray(value, fieldName).forEach((item, index) => {
    const capability = namespaced(item, `${fieldName}[${index}]`);
    if (!CORE_CAPABILITIES.has(capability)) {
      throw violation('UNKNOWN_REQUIRED_CAPABILITY', `unknown required capability ${capability}`, 'UNSUPPORTED');
    }
    if (result.includes(capability)) {
      throw violation('DUPLICATE_REQUIRED_CAPABILITY', `duplicate ${capability}`);
    }
    result.push(capability);
  });
  return Object.freeze(result);
}

export interface WorkProgressSource {
  readonly authority: WorkSourceAuthority;
  readonly event_id: string;
  readonly source_work_ref: Readonly<IdentityRef>;
  readonly adapter: string | null;
}

export interface WorkProgressEventV2 {
  readonly work_ref: Readonly<IdentityRef>;
  readonly source: Readonly<WorkProgressSource>;
  readonly seq: number;
  readonly state: WorkState;
  readonly outcome: TerminalOutcome | null;
  readonly summary: Readonly<KnownFact<string>>;
  readonly blocking_question: Readonly<KnownFact<string>>;
  readonly artifact_refs: Readonly<KnownFact<readonly Readonly<ContextRef>[]>>;
  readonly urgency: WorkUrgency;
  readonly speakability: Speakability;
}

function parseKnownFact<T>(value: unknown, fieldName: string, parser: (item: unknown) => T): Readonly<KnownFact<T>> {
  const data = strictRecord(value, fieldName);
  const knowledge = enumeration(['known', 'unknown'] as const, data.knowledge, `${fieldName}.knowledge`);
  if (knowledge === 'unknown') {
    exactKeys(data, ['knowledge'], fieldName);
    return Object.freeze({ knowledge });
  }
  exactKeys(data, ['knowledge', 'value'], fieldName);
  return Object.freeze({ knowledge, value: parser(data.value) });
}

function parseFactText(value: unknown, fieldName: string): string {
  if (typeof value !== 'string') {
    throw violation('INVALID_FACT_TEXT', `${fieldName} must be a string`);
  }
  return validUnicode(value, fieldName);
}

function parseWorkProgressSource(value: unknown): Readonly<WorkProgressSource> {
  const data = strictRecord(value, 'work_progress.source');
  exactKeys(data, ['authority', 'event_id', 'source_work_ref', 'adapter'], 'work_progress.source');
  const authority = enumeration(['harness', 'task_core', 'executor'] as const, data.authority, 'work_progress.source.authority');
  const sourceWorkRef = parseIdentityRef(data.source_work_ref);
  const expectedKind: IdentityKind = ({ harness: 'round', task_core: 'task', executor: 'attempt' } as const)[authority];
  if (sourceWorkRef.kind !== expectedKind) {
    throw violation('PROGRESS_SOURCE_AUTHORITY_MISMATCH', `${authority} progress requires ${expectedKind} source_work_ref`, 'PERMISSION_DENIED');
  }
  return Object.freeze({
    authority,
    event_id: requiredText(data.event_id, 'work_progress.source.event_id'),
    source_work_ref: sourceWorkRef,
    adapter: optionalId(data.adapter, 'work_progress.source.adapter'),
  });
}

export function parseWorkProgressEventV2(value: unknown, scope?: Readonly<ScopeRef>, identities?: IdentityRegistry): Readonly<WorkProgressEventV2> {
  const data = strictRecord(value, 'work_progress');
  exactKeys(
    data,
    ['work_ref', 'source', 'seq', 'state', 'outcome', 'summary', 'blocking_question', 'artifact_refs', 'urgency', 'speakability'],
    'work_progress'
  );
  const workRef = parseIdentityRef(data.work_ref);
  if (workRef.kind !== 'round' && workRef.kind !== 'task') {
    throw violation('INVALID_WORK_REF_KIND', 'work_ref must identify a round or task');
  }
  const source = parseWorkProgressSource(data.source);
  if (source.source_work_ref.kind === 'round' || source.source_work_ref.kind === 'task') {
    if (source.source_work_ref.kind !== workRef.kind || source.source_work_ref.id !== workRef.id) {
      throw violation('PROGRESS_SOURCE_WORK_MISMATCH', 'round/task source_work_ref must equal work_ref');
    }
  } else if (workRef.kind !== 'task') {
    throw violation('PROGRESS_ATTEMPT_PARENT_MISMATCH', 'an attempt source can project only to a task');
  }
  if (scope !== undefined && identities !== undefined) {
    identities.require(workRef, { scope });
    identities.require(source.source_work_ref, {
      scope,
      parent: source.source_work_ref.kind === 'attempt' ? workRef : undefined,
    });
  }
  const state = enumeration(['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const, data.state, 'work_progress.state');
  const outcome = data.outcome === null ? null : enumeration(TERMINAL_OUTCOMES, data.outcome, 'work_progress.outcome');
  if (state === 'terminal' && outcome === null) {
    throw violation('TERMINAL_OUTCOME_REQUIRED', 'terminal WorkProgress requires an outcome');
  }
  if (state !== 'terminal' && outcome !== null) {
    throw violation('NON_TERMINAL_OUTCOME_FORBIDDEN', 'non-terminal WorkProgress forbids an outcome');
  }
  const artifacts = parseKnownFact(data.artifact_refs, 'work_progress.artifact_refs', item => {
    const refs = strictArray(item, 'work_progress.artifact_refs.value').map(parseContextRef);
    if (scope !== undefined) {
      for (const ref of refs) {
        if (scopeKey(ref.scope) !== scopeKey(scope)) {
          throw violation('CONTEXT_SCOPE_MISMATCH', 'artifact context scope must match WorkProgress scope', 'PERMISSION_DENIED');
        }
      }
    }
    return Object.freeze(refs);
  });
  return Object.freeze({
    work_ref: workRef,
    source,
    seq: unsignedInteger(data.seq, 'work_progress.seq'),
    state,
    outcome,
    summary: parseKnownFact(data.summary, 'work_progress.summary', item => parseFactText(item, 'work_progress.summary.value')),
    blocking_question: parseKnownFact(data.blocking_question, 'work_progress.blocking_question', item =>
      parseFactText(item, 'work_progress.blocking_question.value')
    ),
    artifact_refs: artifacts,
    urgency: enumeration(['normal', 'attention', 'urgent', 'unknown'] as const, data.urgency, 'work_progress.urgency'),
    speakability: enumeration(['not_speakable', 'eligible', 'attention_requested'] as const, data.speakability, 'work_progress.speakability'),
  });
}

interface EventRule {
  readonly streamKind: IdentityKind | readonly IdentityKind[];
  readonly authority: string;
  readonly state?: string;
  readonly terminal?: boolean;
  readonly adapter?: boolean;
  readonly lifecycle?: boolean;
  readonly progress?: boolean;
}

const EVENT_RULES: Readonly<Record<string, EventRule>> = Object.freeze({
  'interaction.opened': { streamKind: 'interaction', authority: 'conversation_runtime', state: 'open' },
  'interaction.closing': {
    streamKind: 'interaction',
    authority: 'conversation_runtime',
    state: 'closing',
  },
  'interaction.closed': {
    streamKind: 'interaction',
    authority: 'conversation_runtime',
    state: 'closed',
  },
  'turn.capturing': { streamKind: 'turn', authority: 'conversation_runtime', state: 'capturing' },
  'turn.committed': { streamKind: 'turn', authority: 'conversation_runtime', state: 'committed' },
  'turn.cancelled': { streamKind: 'turn', authority: 'conversation_runtime', state: 'cancelled' },
  'response.accepted': {
    streamKind: 'response',
    authority: 'conversation_runtime',
    state: 'accepted',
  },
  'response.generating': {
    streamKind: 'response',
    authority: 'conversation_runtime',
    state: 'generating',
  },
  'response.speaking': {
    streamKind: 'response',
    authority: 'conversation_runtime',
    state: 'speaking',
  },
  'response.terminal': {
    streamKind: 'response',
    authority: 'conversation_runtime',
    state: 'terminal',
    terminal: true,
  },
  'round.accepted': { streamKind: 'round', authority: 'harness', state: 'accepted' },
  'round.running': { streamKind: 'round', authority: 'harness', state: 'running' },
  'round.blocked': { streamKind: 'round', authority: 'harness', state: 'blocked' },
  'round.decision_required': {
    streamKind: 'round',
    authority: 'harness',
    state: 'decision_required',
  },
  'round.terminal': {
    streamKind: 'round',
    authority: 'harness',
    state: 'terminal',
    terminal: true,
  },
  'task.accepted': { streamKind: 'task', authority: 'task_core', state: 'accepted' },
  'task.retry_accepted': { streamKind: 'task', authority: 'task_core', state: 'accepted' },
  'task.running': { streamKind: 'task', authority: 'task_core', state: 'running' },
  'task.blocked': { streamKind: 'task', authority: 'task_core', state: 'blocked' },
  'task.decision_required': {
    streamKind: 'task',
    authority: 'task_core',
    state: 'decision_required',
  },
  'task.terminal': {
    streamKind: 'task',
    authority: 'task_core',
    state: 'terminal',
    terminal: true,
  },
  'attempt.accepted': { streamKind: 'attempt', authority: 'executor', state: 'accepted' },
  'attempt.running': { streamKind: 'attempt', authority: 'executor', state: 'running' },
  'attempt.terminal': {
    streamKind: 'attempt',
    authority: 'executor',
    state: 'terminal',
    terminal: true,
  },
  'adapter.observed': { streamKind: 'event', authority: 'adapter', adapter: true },
  'work.progress': {
    streamKind: Object.freeze(['round', 'task'] as const),
    authority: 'adapter',
    adapter: true,
    lifecycle: false,
    progress: true,
  },
});

const TERMINAL_OUTCOMES = ['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const;

function eventPayload(value: unknown, eventType: string, rule: EventRule): Readonly<JsonObject> {
  const data = strictRecord(value, 'event.payload');
  if (rule.progress === true) {
    return parseWorkProgressEventV2(data) as unknown as Readonly<JsonObject>;
  }
  if (rule.adapter === true) {
    exactKeys(data, ['source_event_type'], 'event.payload');
    namespaced(data.source_event_type, 'event.payload.source_event_type');
  } else if (rule.terminal === true) {
    exactKeys(data, ['state', 'outcome'], 'event.payload');
    if (data.state !== rule.state) {
      throw violation('EVENT_STATE_MISMATCH', `${eventType} requires state ${rule.state}`);
    }
    enumeration(TERMINAL_OUTCOMES, data.outcome, 'event.payload.outcome');
  } else if (eventType === 'task.retry_accepted') {
    exactKeys(
      data,
      ['state', 'command_id', 'retry_of_attempt_id', 'previous_outcome', 'attempt_number'],
      'event.payload'
    );
    if (data.state !== rule.state) {
      throw violation('EVENT_STATE_MISMATCH', `${eventType} requires state ${rule.state}`);
    }
    requiredText(data.command_id, 'event.payload.command_id');
    requiredText(data.retry_of_attempt_id, 'event.payload.retry_of_attempt_id');
    const outcome = enumeration(TERMINAL_OUTCOMES, data.previous_outcome, 'event.payload.previous_outcome');
    if (outcome !== 'cancelled' && outcome !== 'completed') {
      throw violation(
        'TASK_RETRY_OUTCOME_NOT_ELIGIBLE',
        'task.retry_accepted permits only cancelled or completed predecessors',
        'PROTOCOL_VIOLATION'
      );
    }
    const number = unsignedInteger(data.attempt_number, 'event.payload.attempt_number');
    if (number !== 2 && number !== 3) {
      throw violation(
        'TASK_RETRY_ATTEMPT_NUMBER_INVALID',
        'task.retry_accepted attempt_number must be 2 or 3',
        'PROTOCOL_VIOLATION'
      );
    }
  } else {
    exactKeys(data, ['state'], 'event.payload');
    if (data.state !== rule.state) {
      throw violation('EVENT_STATE_MISMATCH', `${eventType} requires state ${rule.state}`);
    }
  }
  return cloneObject(data, 'event.payload');
}

export interface EventEnvelope {
  readonly contract_version: typeof CONTRACT_VERSION;
  readonly event_id: string;
  readonly event_type: string;
  readonly producer: Readonly<ProducerRef>;
  readonly stream_ref: Readonly<IdentityRef>;
  readonly seq: number;
  readonly occurred_at: string;
  readonly scope: Readonly<ScopeRef>;
  readonly correlation_id: string;
  readonly causation_id: string | null;
  readonly required_capabilities: readonly string[];
  readonly payload: Readonly<JsonObject>;
  readonly extensions: Readonly<JsonObject>;
}

export function parseEventEnvelope(value: unknown, identities?: IdentityRegistry): Readonly<EventEnvelope> {
  const data = strictRecord(value, 'event');
  exactKeys(
    data,
    [
      'contract_version',
      'event_id',
      'event_type',
      'producer',
      'stream_ref',
      'seq',
      'occurred_at',
      'scope',
      'correlation_id',
      'causation_id',
      'required_capabilities',
      'payload',
      'extensions',
    ],
    'event'
  );
  if (data.contract_version !== CONTRACT_VERSION) {
    throw violation('UNSUPPORTED_CONTRACT_VERSION', `expected ${CONTRACT_VERSION}`, 'UNSUPPORTED');
  }
  const eventType = namespaced(data.event_type, 'event.event_type');
  const rule = EVENT_RULES[eventType];
  if (rule === undefined) {
    throw violation('UNKNOWN_EVENT_TYPE', `unknown ${eventType}`, 'UNSUPPORTED');
  }
  const producer = parseProducerRef(data.producer);
  if (producer.authority !== rule.authority) {
    throw violation('EVENT_AUTHORITY_MISMATCH', `${eventType} requires authority ${rule.authority}`, 'PERMISSION_DENIED');
  }
  const streamRef = parseIdentityRef(data.stream_ref);
  const streamKinds = Array.isArray(rule.streamKind) ? rule.streamKind : [rule.streamKind];
  if (!streamKinds.includes(streamRef.kind)) {
    throw violation('IDENTITY_KIND_MISMATCH', `expected one of ${streamKinds.join(', ')}, received ${streamRef.kind}`);
  }
  const causationId = optionalId(data.causation_id, 'event.causation_id');
  if (rule.adapter === true && causationId === null) {
    throw violation('ADAPTER_CAUSATION_REQUIRED', 'adapter events require a source event');
  }
  const scope = parseScopeRef(data.scope);
  const result = Object.freeze({
    contract_version: CONTRACT_VERSION,
    event_id: requiredText(data.event_id, 'event.event_id'),
    event_type: eventType,
    producer,
    stream_ref: streamRef,
    seq: unsignedInteger(data.seq, 'event.seq'),
    occurred_at: timestamp(data.occurred_at, 'event.occurred_at'),
    scope,
    correlation_id: requiredText(data.correlation_id, 'event.correlation_id'),
    causation_id: causationId,
    required_capabilities: capabilityList(data.required_capabilities, 'event.required_capabilities'),
    payload: eventPayload(data.payload, eventType, rule),
    extensions: extensions(data.extensions, 'event.extensions'),
  });
  if (
    eventType === 'task.retry_accepted'
    && (causationId === null || result.payload.command_id !== causationId)
  ) {
    throw violation(
      'TASK_RETRY_CAUSATION_MISMATCH',
      'task.retry_accepted command_id must equal its causation_id',
      'PROTOCOL_VIOLATION'
    );
  }
  if (rule.progress === true) {
    const progress = parseWorkProgressEventV2(result.payload, scope, identities);
    if (progress.source.source_work_ref.kind === 'attempt' && identities === undefined) {
      throw violation('PROGRESS_ATTEMPT_PARENT_UNVERIFIED', 'attempt-to-task WorkProgress requires an IdentityRegistry parent binding', 'PERMISSION_DENIED');
    }
    if (progress.work_ref.kind !== streamRef.kind || progress.work_ref.id !== streamRef.id) {
      throw violation('PROGRESS_ENVELOPE_MISMATCH', 'work.progress stream_ref must match its projection work_ref');
    }
    if (progress.source.event_id !== causationId) {
      throw violation('PROGRESS_CAUSATION_MISMATCH', 'work.progress causation_id must equal source.event_id');
    }
  }
  if (identities !== undefined) identities.require(streamRef, { scope });
  return result;
}
