// Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

export const CONTRACT_VERSION = 'live-voice.contract.v2' as const;
export const V1_CONTRACT_VERSION = 'live-voice.contract.v1' as const;
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
export type CancelScope = 'playback.stop' | 'response.cancel' | 'round.cancel' | 'task.cancel';
export type InputCommitState = 'partial' | 'uncommitted' | 'committed';
export type SideEffectTarget = 'agent' | 'tool' | 'task';
export type LifecycleKind = 'interaction' | 'turn' | 'response' | 'round' | 'task' | 'attempt';
export type TerminalOutcome = 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown';
export type Availability = 'available' | 'unavailable';
export type Knowledge = 'known' | 'unknown';
export type ContextRevisionKind = 'version' | 'snapshot' | 'unversioned';
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

function optionalStableReason(value: unknown, fieldName: string): string | null {
  if (value === null) return null;
  const parsed = requiredText(value, fieldName);
  if (!/^[A-Z][A-Z0-9_]*$/.test(parsed)) {
    throw violation('INVALID_ERROR_REASON', `${fieldName} must be a stable uppercase reason`);
  }
  return parsed;
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

export function canonicalJsonBytes(value: unknown): Uint8Array {
  return new TextEncoder().encode(canonicalJson(value));
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
const INPUT_COMMIT_STATES = ['partial', 'uncommitted', 'committed'] as const;
const LIFECYCLE_KINDS = ['interaction', 'turn', 'response', 'round', 'task', 'attempt'] as const;
const ERROR_CODES = [
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

export function parseConnectionEpochRef(value: unknown): Readonly<ConnectionEpochRef> {
  const data = strictRecord(value, 'connection_epoch_ref');
  exactKeys(data, ['connection_id', 'connection_epoch'], 'connection_epoch_ref');
  return Object.freeze({
    connection_id: requiredText(data.connection_id, 'connection_epoch_ref.connection_id'),
    connection_epoch: unsignedInteger(data.connection_epoch, 'connection_epoch_ref.connection_epoch'),
  });
}

export interface OriginRef {
  readonly kind: 'committed_turn' | 'structured';
  readonly turn_id: string | null;
  readonly commit_id: string | null;
}

function parseOriginRef(value: unknown): Readonly<OriginRef> {
  const data = strictRecord(value, 'origin');
  exactKeys(data, ['kind', 'turn_id', 'commit_id'], 'origin');
  const kind = enumeration(['committed_turn', 'structured'] as const, data.kind, 'origin.kind');
  const turnId = optionalId(data.turn_id, 'origin.turn_id');
  const commitId = optionalId(data.commit_id, 'origin.commit_id');
  if ((kind === 'committed_turn' && (turnId === null || commitId === null)) || (kind === 'structured' && (turnId !== null || commitId !== null))) {
    throw violation('INVALID_ORIGIN', 'committed_turn requires turn_id and commit_id; structured forbids both');
  }
  return Object.freeze({ kind, turn_id: turnId, commit_id: commitId });
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

const EXPECTED_PARENTS: Readonly<Record<IdentityKind, readonly IdentityKind[]>> = Object.freeze({
  connection: [],
  media_session: ['interaction'],
  track: ['media_session'],
  interaction: [],
  turn: ['interaction'],
  response: ['interaction', 'turn'],
  round: [],
  task: [],
  attempt: ['task'],
  command: [],
  request: [],
  event: [],
});

export interface IdentityRecord {
  readonly ref: Readonly<IdentityRef>;
  readonly scope: Readonly<ScopeRef>;
  readonly parents: readonly Readonly<IdentityRef>[];
  readonly connection_epoch_ref?: Readonly<ConnectionEpochRef> | null;
}

function scopeKey(scope: Readonly<ScopeRef>): string {
  return canonicalJson(scope);
}

export class IdentityRegistry {
  readonly #records = new Map<string, IdentityRecord>();
  readonly #kindById = new Map<string, IdentityKind>();

  register(record: IdentityRecord): IdentityRecord {
    const data = strictRecord(record, 'identity_record');
    exactKeys(data, ['ref', 'scope', 'parents'], 'identity_record', ['connection_epoch_ref']);
    record = {
      ref: parseIdentityRef(data.ref),
      scope: parseScopeRef(data.scope),
      parents: strictArray(data.parents, 'identity_record.parents').map(parent => parseIdentityRef(parent)),
      connection_epoch_ref:
        data.connection_epoch_ref === undefined || data.connection_epoch_ref === null ? null : parseConnectionEpochRef(data.connection_epoch_ref),
    };
    const expected = [...EXPECTED_PARENTS[record.ref.kind]].sort();
    const actual = record.parents.map(parent => parent.kind).sort();
    if (new Set(actual).size !== actual.length || actual.length !== expected.length || actual.some((kind, index) => kind !== expected[index])) {
      throw violation('IDENTITY_PARENT_MISMATCH', `${record.ref.kind} requires parent kinds ${expected.join(',')}`);
    }
    const connectionBinding = record.connection_epoch_ref ?? null;
    if ((record.ref.kind === 'connection' || record.ref.kind === 'media_session') && connectionBinding === null) {
      throw violation('CONNECTION_EPOCH_BINDING_REQUIRED', `${record.ref.kind} requires connection_epoch_ref`);
    }
    if (record.ref.kind !== 'connection' && record.ref.kind !== 'media_session' && connectionBinding !== null) {
      throw violation('CONNECTION_EPOCH_BINDING_FORBIDDEN', `${record.ref.kind} forbids connection_epoch_ref`);
    }
    if (record.ref.kind === 'connection' && connectionBinding?.connection_id !== record.ref.id) {
      throw violation('CONNECTION_EPOCH_BINDING_MISMATCH', 'connection binding must name the registered connection');
    }
    const knownKind = this.#kindById.get(record.ref.id);
    if (knownKind !== undefined && knownKind !== record.ref.kind) {
      throw violation('IDENTITY_KIND_MISMATCH', `${record.ref.id} is already ${knownKind}`);
    }
    for (const parent of record.parents) {
      const parentRecord = this.#records.get(`${parent.kind}:${parent.id}`);
      if (parentRecord === undefined) {
        throw violation('IDENTITY_PARENT_NOT_FOUND', `${parent.kind}:${parent.id} is unknown`);
      }
      if (scopeKey(parentRecord.scope) !== scopeKey(record.scope)) {
        throw violation('IDENTITY_SCOPE_MISMATCH', 'child and parent scope must match');
      }
    }
    if (record.ref.kind === 'media_session' && connectionBinding !== null) {
      const connection = this.#records.get(`connection:${connectionBinding.connection_id}`);
      if (connection === undefined) {
        throw violation('IDENTITY_CONNECTION_NOT_FOUND', `connection:${connectionBinding.connection_id} is unknown`);
      }
      if (scopeKey(connection.scope) !== scopeKey(record.scope)) {
        throw violation('IDENTITY_SCOPE_MISMATCH', 'media session and connection scope must match');
      }
      if (canonicalJson(connection.connection_epoch_ref ?? null) !== canonicalJson(connectionBinding)) {
        throw violation('CONNECTION_EPOCH_BINDING_MISMATCH', 'media session must use the active connection epoch binding');
      }
    }
    if (record.ref.kind === 'response') {
      const interaction = record.parents.find(parent => parent.kind === 'interaction');
      const turn = record.parents.find(parent => parent.kind === 'turn');
      const turnRecord = turn === undefined ? undefined : this.#records.get(`turn:${turn.id}`);
      if (
        interaction === undefined ||
        turnRecord === undefined ||
        !turnRecord.parents.some(parent => parent.kind === 'interaction' && parent.id === interaction.id)
      ) {
        throw violation('IDENTITY_PARENT_MISMATCH', 'response interaction must own its turn');
      }
    }
    const frozen = Object.freeze({
      ref: Object.freeze({ ...record.ref }),
      scope: Object.freeze({ ...record.scope }),
      parents: Object.freeze(record.parents.map(parent => Object.freeze({ ...parent }))),
      connection_epoch_ref: connectionBinding === null ? null : Object.freeze({ ...connectionBinding }),
    });
    const key = `${record.ref.kind}:${record.ref.id}`;
    const existing = this.#records.get(key);
    if (existing !== undefined) {
      if (canonicalJson(existing) !== canonicalJson(frozen)) {
        throw violation('IDENTITY_CONFLICT', 'identity registration is immutable', 'CONFLICT');
      }
      return existing;
    }
    this.#records.set(key, frozen);
    this.#kindById.set(record.ref.id, record.ref.kind);
    return frozen;
  }

  require(ref: Readonly<IdentityRef>, options: { scope?: Readonly<ScopeRef>; parent?: Readonly<IdentityRef> } = {}): IdentityRecord {
    const normalizedRef = parseIdentityRef(ref);
    const normalizedScope = options.scope === undefined ? undefined : parseScopeRef(options.scope);
    const normalizedParent = options.parent === undefined ? undefined : parseIdentityRef(options.parent);
    const record = this.#records.get(`${normalizedRef.kind}:${normalizedRef.id}`);
    if (record === undefined) {
      const knownKind = this.#kindById.get(normalizedRef.id);
      if (knownKind !== undefined) {
        throw violation('IDENTITY_KIND_MISMATCH', `${normalizedRef.id} is ${knownKind}, not ${normalizedRef.kind}`);
      }
      throw violation('IDENTITY_NOT_FOUND', `${normalizedRef.kind}:${normalizedRef.id} is unknown`, 'NOT_FOUND');
    }
    if (normalizedScope !== undefined && scopeKey(normalizedScope) !== scopeKey(record.scope)) {
      throw violation('IDENTITY_SCOPE_MISMATCH', 'identity scope does not match');
    }
    if (normalizedParent !== undefined && !record.parents.some(parent => parent.kind === normalizedParent.kind && parent.id === normalizedParent.id)) {
      throw violation('IDENTITY_PARENT_MISMATCH', 'identity parent does not match');
    }
    return record;
  }
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
const WAVE2_COMMAND_TYPES = new Set([
  'task.update',
  'task.provide_input',
  'task.pause',
  'task.resume',
  'task.reprioritize',
  'task.create_successor',
  'task.ack_events',
]);
const TASK_PRIORITIES = new Set(['low', 'normal', 'high', 'urgent']);
const PRESENTATION_CLASSES = new Set(['text', 'voice']);
const TASK_EVENT_STATES = ['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const;
const TASK_TERMINAL_EVENT_TYPES = new Set(['attempt.terminal', 'task.terminal']);
const TASK_SIDE_EFFECT_CLASSES = new Set(['read_only', 'project_mutation']);
const COMMAND_DISPOSITIONS = new Set([
  'accepted',
  'applied',
  'rejected',
  'unsupported',
  'conflict',
  'timeout',
  'unknown',
]);
const POSITIVE_COMMAND_DISPOSITIONS = new Set(['accepted', 'applied']);
const COMMAND_DISPOSITION_ERROR_CODES: Readonly<Record<string, ReadonlySet<ErrorCode>>> = Object.freeze({
  rejected: new Set<ErrorCode>(['INVALID_ARGUMENT', 'UNAUTHENTICATED', 'PERMISSION_DENIED', 'NOT_FOUND']),
  unsupported: new Set<ErrorCode>(['UNSUPPORTED', 'CAPABILITY_UNAVAILABLE']),
  conflict: new Set<ErrorCode>(['CONFLICT', 'STALE']),
  timeout: new Set<ErrorCode>(['TIMEOUT']),
  unknown: new Set<ErrorCode>(['RESULT_UNKNOWN']),
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

function contextRefs(value: unknown, fieldName: string, scope: Readonly<ScopeRef>): readonly Readonly<ContextRef>[] {
  const refs: Readonly<ContextRef>[] = [];
  strictArray(value, fieldName).forEach((item, index) => {
    const ref = parseContextRef(item);
    if (scopeKey(ref.scope) !== scopeKey(scope)) {
      throw violation('CONTEXT_SCOPE_MISMATCH', `${fieldName}[${index}] does not match the enclosing scope`, 'PERMISSION_DENIED');
    }
    refs.push(ref);
  });
  return Object.freeze(refs);
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

function requireOperationCapability(values: readonly string[], operation: string, fieldName: string): void {
  if (values.length !== 1 || values[0] !== operation) {
    throw violation(
      'REQUIRED_CAPABILITY_MISMATCH',
      `${fieldName} must contain only ${operation}`,
      'PERMISSION_DENIED'
    );
  }
}

function boundedText(value: unknown, fieldName: string, maxUtf8Bytes: number | null): string {
  const text = requiredText(value, fieldName);
  if (
    text.includes('\0')
    || (maxUtf8Bytes !== null && new TextEncoder().encode(text).byteLength > maxUtf8Bytes)
  ) {
    throw violation(
      'INVALID_BOUNDED_TEXT',
      `${fieldName} contains NUL or exceeds its UTF-8 byte bound`,
      'INVALID_ARGUMENT'
    );
  }
  return text;
}

function optionalBoundedText(value: unknown, fieldName: string, maxUtf8Bytes: number): string | null {
  return value === null ? null : boundedText(value, fieldName, maxUtf8Bytes);
}

function constraintList(value: unknown, fieldName: string, nullable: boolean): readonly string[] | null {
  if (value === null) {
    if (nullable) return null;
    throw violation('INVALID_TASK_CONSTRAINTS', `${fieldName} must be an array`, 'INVALID_ARGUMENT');
  }
  const values = strictArray(value, fieldName);
  if (values.length > 16) {
    throw violation('INVALID_TASK_CONSTRAINTS', `${fieldName} cannot contain more than 16 entries`, 'INVALID_ARGUMENT');
  }
  const parsed = values.map((item, index) => boundedText(item, `${fieldName}[${index}]`, 1_024));
  if (new Set(parsed).size !== parsed.length) {
    throw violation('INVALID_TASK_CONSTRAINTS', `${fieldName} entries must be unique`, 'INVALID_ARGUMENT');
  }
  const byteLength = parsed.reduce((total, item) => total + new TextEncoder().encode(item).byteLength, 0);
  if (byteLength > 4_096) {
    throw violation('INVALID_TASK_CONSTRAINTS', `${fieldName} exceeds its aggregate UTF-8 byte bound`, 'INVALID_ARGUMENT');
  }
  return Object.freeze(parsed);
}

function closedStringMap(value: unknown, fieldName: string): void {
  const data = strictRecord(value, fieldName);
  for (const [key, item] of Object.entries(data)) {
    boundedText(key, `${fieldName} key`, null);
    boundedText(item, `${fieldName}.${key}`, null);
  }
}

function closedValue(value: unknown, fieldName: string, values: ReadonlySet<string>): string {
  if (typeof value !== 'string' || !values.has(value)) {
    throw violation('INVALID_ENUM', `unknown ${fieldName} ${String(value)}`, 'INVALID_ARGUMENT');
  }
  return value;
}

function successorOutcomeAndDigest(data: Record<string, unknown>): void {
  const outcome = enumeration(TERMINAL_OUTCOMES, data.predecessor_outcome, 'command.payload.predecessor_outcome');
  const digest = data.predecessor_result_sha256;
  if (outcome === 'completed') {
    if (typeof digest !== 'string' || !/^[0-9a-f]{64}$/.test(digest)) {
      throw violation(
        'INVALID_PREDECESSOR_RESULT_DIGEST',
        'completed predecessor requires a lowercase SHA-256 digest',
        'INVALID_ARGUMENT'
      );
    }
  } else if (digest !== null) {
    throw violation(
      'INVALID_PREDECESSOR_RESULT_DIGEST',
      'non-completed predecessor forbids a result digest',
      'INVALID_ARGUMENT'
    );
  }
}

function commandPayload(commandType: string, value: unknown): Readonly<JsonObject> {
  const data = strictRecord(value, 'command.payload');
  if (commandType === 'playback.stop' || commandType === 'response.cancel') {
    exactKeys(data, ['interaction_id', 'response_generation'], 'command.payload');
    requiredText(data.interaction_id, 'command.payload.interaction_id');
    unsignedInteger(data.response_generation, 'command.payload.response_generation');
  } else if (commandType === 'round.cancel' || commandType === 'task.cancel') {
    exactKeys(data, [], 'command.payload');
  } else if (commandType === 'task.retry') {
    exactKeys(data, ['previous_attempt_id', 'previous_outcome', 'attempt_number'], 'command.payload');
    requiredText(data.previous_attempt_id, 'command.payload.previous_attempt_id');
    const outcome = enumeration(TERMINAL_OUTCOMES, data.previous_outcome, 'command.payload.previous_outcome');
    if (outcome !== 'cancelled' && outcome !== 'completed') {
      throw violation(
        'TASK_RETRY_OUTCOME_NOT_ELIGIBLE',
        'task.retry permits only cancelled or completed predecessors',
        'CONFLICT'
      );
    }
    const number = unsignedInteger(data.attempt_number, 'command.payload.attempt_number');
    if (number !== 2 && number !== 3) {
      throw violation('TASK_RETRY_ATTEMPT_NUMBER_INVALID', 'task.retry attempt_number must be 2 or 3', 'INVALID_ARGUMENT');
    }
  } else if (commandType === 'task.adjust') {
    exactKeys(data, ['adjustment'], 'command.payload');
    const adjustment = requiredText(data.adjustment, 'command.payload.adjustment');
    if (adjustment.includes('\0') || new TextEncoder().encode(adjustment).byteLength > 4_096) {
      throw violation(
        'INVALID_TASK_ADJUSTMENT',
        'task.adjust payload exceeds its closed content bound',
        'INVALID_ARGUMENT'
      );
    }
  } else if (commandType === 'task.update') {
    exactKeys(data, ['attempt_id', 'expected_event_head', 'instruction', 'constraints'], 'command.payload');
    requiredText(data.attempt_id, 'command.payload.attempt_id');
    unsignedInteger(data.expected_event_head, 'command.payload.expected_event_head');
    if (data.instruction === null && data.constraints === null) {
      throw violation('EMPTY_TASK_UPDATE', 'task.update requires instruction or constraints', 'INVALID_ARGUMENT');
    }
    if (data.instruction !== null) {
      boundedText(data.instruction, 'command.payload.instruction', 4_096);
    }
    constraintList(data.constraints, 'command.payload.constraints', true);
  } else if (commandType === 'task.provide_input') {
    exactKeys(
      data,
      ['attempt_id', 'expected_event_head', 'responds_to_event_id', 'text'],
      'command.payload'
    );
    requiredText(data.attempt_id, 'command.payload.attempt_id');
    unsignedInteger(data.expected_event_head, 'command.payload.expected_event_head');
    requiredText(data.responds_to_event_id, 'command.payload.responds_to_event_id');
    boundedText(data.text, 'command.payload.text', 4_096);
  } else if (commandType === 'task.pause' || commandType === 'task.resume') {
    exactKeys(data, ['attempt_id', 'expected_event_head', 'reason'], 'command.payload');
    requiredText(data.attempt_id, 'command.payload.attempt_id');
    unsignedInteger(data.expected_event_head, 'command.payload.expected_event_head');
    optionalBoundedText(data.reason, 'command.payload.reason', 1_024);
  } else if (commandType === 'task.reprioritize') {
    exactKeys(data, ['attempt_id', 'expected_event_head', 'priority', 'reason'], 'command.payload');
    requiredText(data.attempt_id, 'command.payload.attempt_id');
    unsignedInteger(data.expected_event_head, 'command.payload.expected_event_head');
    closedValue(data.priority, 'command.payload.priority', TASK_PRIORITIES);
    optionalBoundedText(data.reason, 'command.payload.reason', 1_024);
  } else if (commandType === 'task.create_successor') {
    exactKeys(
      data,
      [
        'expected_predecessor_revision_number',
        'expected_predecessor_event_head',
        'predecessor_terminal_event_id',
        'predecessor_outcome',
        'predecessor_result_sha256',
        'name',
        'instruction',
        'constraints',
        'executor_id',
        'side_effect_class',
        'attributes',
      ],
      'command.payload'
    );
    unsignedInteger(
      data.expected_predecessor_revision_number,
      'command.payload.expected_predecessor_revision_number'
    );
    unsignedInteger(data.expected_predecessor_event_head, 'command.payload.expected_predecessor_event_head');
    requiredText(data.predecessor_terminal_event_id, 'command.payload.predecessor_terminal_event_id');
    successorOutcomeAndDigest(data);
    boundedText(data.name, 'command.payload.name', null);
    boundedText(data.instruction, 'command.payload.instruction', 4_096);
    constraintList(data.constraints, 'command.payload.constraints', false);
    boundedText(data.executor_id, 'command.payload.executor_id', null);
    closedValue(data.side_effect_class, 'command.payload.side_effect_class', TASK_SIDE_EFFECT_CLASSES);
    closedStringMap(data.attributes, 'command.payload.attributes');
  } else if (commandType === 'task.ack_events') {
    exactKeys(
      data,
      ['presentation_class', 'acked_through_seq', 'acked_event_id', 'expected_event_head'],
      'command.payload'
    );
    closedValue(data.presentation_class, 'command.payload.presentation_class', PRESENTATION_CLASSES);
    unsignedInteger(data.acked_through_seq, 'command.payload.acked_through_seq');
    requiredText(data.acked_event_id, 'command.payload.acked_event_id');
    unsignedInteger(data.expected_event_head, 'command.payload.expected_event_head');
  }
  return cloneObject(data, 'command.payload');
}

function queryPayload(queryType: string, value: unknown): Readonly<JsonObject> {
  const data = strictRecord(value, 'query.payload');
  if (queryType === 'task.unread_events') {
    exactKeys(data, ['presentation_class', 'limit'], 'query.payload');
    closedValue(data.presentation_class, 'query.payload.presentation_class', PRESENTATION_CLASSES);
    const limit = unsignedInteger(data.limit, 'query.payload.limit');
    if (limit < 1 || limit > 500) {
      throw violation('INVALID_UNREAD_LIMIT', 'query.payload.limit must be between 1 and 500', 'INVALID_ARGUMENT');
    }
  }
  return cloneObject(data, 'query.payload');
}

interface EnvelopeBase {
  readonly contract_version: typeof CONTRACT_VERSION;
  readonly request_id: string;
  readonly issued_at: string;
  readonly scope: Readonly<ScopeRef>;
  readonly correlation_id: string;
  readonly causation_id: string | null;
  readonly target_ref: Readonly<IdentityRef>;
  readonly context_refs: readonly Readonly<ContextRef>[];
  readonly required_capabilities: readonly string[];
  readonly payload: Readonly<JsonObject>;
  readonly extensions: Readonly<JsonObject>;
}

export interface CommandEnvelope extends EnvelopeBase {
  readonly command_id: string;
  readonly command_type: string;
  readonly origin: Readonly<OriginRef>;
}

export function parseCommandEnvelope(value: unknown, identities?: IdentityRegistry, commits?: TurnCommitLedger): Readonly<CommandEnvelope> {
  const data = strictRecord(value, 'command');
  exactKeys(
    data,
    [
      'contract_version',
      'request_id',
      'command_id',
      'command_type',
      'issued_at',
      'scope',
      'correlation_id',
      'causation_id',
      'origin',
      'target_ref',
      'context_refs',
      'required_capabilities',
      'payload',
      'extensions',
    ],
    'command'
  );
  if (data.contract_version !== CONTRACT_VERSION) {
    throw violation('UNSUPPORTED_CONTRACT_VERSION', `expected ${CONTRACT_VERSION}`, 'UNSUPPORTED');
  }
  const commandType = namespaced(data.command_type, 'command.command_type');
  const expectedKind = COMMAND_TARGETS[commandType];
  if (expectedKind === undefined) {
    throw violation('UNSUPPORTED_COMMAND_TYPE', `unsupported ${commandType}`, 'UNSUPPORTED');
  }
  const scope = parseScopeRef(data.scope);
  const origin = parseOriginRef(data.origin);
  const targetRef = parseIdentityRef(data.target_ref, expectedKind);
  const requiredCapabilities = capabilityList(data.required_capabilities, 'command.required_capabilities');
  if (WAVE2_COMMAND_TYPES.has(commandType)) {
    requireOperationCapability(requiredCapabilities, commandType, 'command.required_capabilities');
  }
  const result = Object.freeze({
    contract_version: CONTRACT_VERSION,
    request_id: requiredText(data.request_id, 'command.request_id'),
    command_id: requiredText(data.command_id, 'command.command_id'),
    command_type: commandType,
    issued_at: timestamp(data.issued_at, 'command.issued_at'),
    scope,
    correlation_id: requiredText(data.correlation_id, 'command.correlation_id'),
    causation_id: optionalId(data.causation_id, 'command.causation_id'),
    origin,
    target_ref: targetRef,
    context_refs: contextRefs(data.context_refs, 'command.context_refs', scope),
    required_capabilities: requiredCapabilities,
    payload: commandPayload(commandType, data.payload),
    extensions: extensions(data.extensions, 'command.extensions'),
  });
  if (identities !== undefined) {
    if (commandType !== 'task.create') identities.require(targetRef, { scope });
    if (commandType === 'playback.stop' || commandType === 'response.cancel') {
      const interaction = {
        kind: 'interaction' as const,
        id: result.payload.interaction_id as string,
      };
      identities.require(interaction, { scope });
      identities.require(targetRef, { scope, parent: interaction });
    }
    if (origin.kind === 'committed_turn') {
      identities.require({ kind: 'turn', id: origin.turn_id ?? '' }, { scope });
    }
  }
  if (origin.kind === 'committed_turn' && commits !== undefined) {
    commits.requireOrigin(origin, scope);
  }
  return result;
}

export function commandFingerprint(command: Readonly<CommandEnvelope>): Uint8Array {
  const normalized = parseCommandEnvelope(command);
  const { request_id: _requestId, ...content } = normalized;
  return canonicalJsonBytes(content);
}

export interface QueryEnvelope extends Omit<EnvelopeBase, 'request_id'> {
  readonly request_id: string;
  readonly query_type: string;
}

export function parseQueryEnvelope(value: unknown, identities?: IdentityRegistry): Readonly<QueryEnvelope> {
  const data = strictRecord(value, 'query');
  exactKeys(
    data,
    [
      'contract_version',
      'request_id',
      'query_type',
      'issued_at',
      'scope',
      'correlation_id',
      'causation_id',
      'target_ref',
      'context_refs',
      'required_capabilities',
      'payload',
      'extensions',
    ],
    'query'
  );
  if (data.contract_version !== CONTRACT_VERSION) {
    throw violation('UNSUPPORTED_CONTRACT_VERSION', `expected ${CONTRACT_VERSION}`, 'UNSUPPORTED');
  }
  const queryType = namespaced(data.query_type, 'query.query_type');
  const expectedKind = QUERY_TARGETS[queryType];
  if (expectedKind === undefined) {
    throw violation('UNSUPPORTED_QUERY_TYPE', `unsupported ${queryType}`, 'UNSUPPORTED');
  }
  const scope = parseScopeRef(data.scope);
  const targetRef = parseIdentityRef(data.target_ref, expectedKind);
  const requiredCapabilities = capabilityList(data.required_capabilities, 'query.required_capabilities');
  if (queryType === 'task.unread_events') {
    requireOperationCapability(requiredCapabilities, queryType, 'query.required_capabilities');
  }
  const result = Object.freeze({
    contract_version: CONTRACT_VERSION,
    request_id: requiredText(data.request_id, 'query.request_id'),
    query_type: queryType,
    issued_at: timestamp(data.issued_at, 'query.issued_at'),
    scope,
    correlation_id: requiredText(data.correlation_id, 'query.correlation_id'),
    causation_id: optionalId(data.causation_id, 'query.causation_id'),
    target_ref: targetRef,
    context_refs: contextRefs(data.context_refs, 'query.context_refs', scope),
    required_capabilities: requiredCapabilities,
    payload: queryPayload(queryType, data.payload),
    extensions: extensions(data.extensions, 'query.extensions'),
  });
  if (identities !== undefined) identities.require(targetRef, { scope });
  return result;
}

export interface ResultEnvelope {
  readonly contract_version: typeof CONTRACT_VERSION;
  readonly request_id: string;
  readonly command_id: string | null;
  readonly ok: boolean;
  readonly result: Readonly<JsonObject> | null;
  readonly error: Readonly<ContractErrorValue> | null;
  readonly observed_at: string;
  readonly extensions: Readonly<JsonObject>;
}

export function parseContractError(value: unknown): Readonly<ContractErrorValue> {
  const data = strictRecord(value, 'error');
  exactKeys(data, ['code', 'reason', 'message', 'retriable', 'correlation_id', 'details'], 'error');
  return Object.freeze({
    code: enumeration(ERROR_CODES, data.code, 'error.code'),
    reason: optionalStableReason(data.reason, 'error.reason'),
    message: requiredText(data.message, 'error.message'),
    retriable: requiredBoolean(data.retriable, 'error.retriable'),
    correlation_id: optionalId(data.correlation_id, 'error.correlation_id'),
    details: cloneObject(data.details, 'error.details'),
  });
}

function errorToWire(error: Readonly<ContractErrorValue>): Readonly<JsonObject> {
  return Object.freeze({
    code: error.code,
    reason: error.reason,
    message: error.message,
    retriable: error.retriable,
    correlation_id: error.correlation_id,
    details: error.details,
  });
}

function resultExtensions(
  value: unknown,
  commandResult: boolean,
  ok: boolean,
  error: Readonly<ContractErrorValue> | null,
): Readonly<JsonObject> {
  const fieldName = 'result.extensions';
  const data = strictRecord(value, fieldName);
  for (const key of Object.keys(data)) namespaced(key, `${fieldName} key`);
  if (!Object.prototype.hasOwnProperty.call(data, 'live_voice.command')) {
    return cloneObject(data, fieldName);
  }
  if (!commandResult) {
    throw violation(
      'COMMAND_RESULT_EXTENSION_FORBIDDEN',
      'query results cannot carry a command disposition',
      'PROTOCOL_VIOLATION'
    );
  }
  const command = strictRecord(data['live_voice.command'], 'result.extensions.live_voice.command');
  exactKeys(
    command,
    ['disposition', 'admission_event_id', 'settlement_event_id'],
    'result.extensions.live_voice.command'
  );
  const dispositionValue = command.disposition;
  if (typeof dispositionValue !== 'string' || !COMMAND_DISPOSITIONS.has(dispositionValue)) {
    throw violation(
      'INVALID_COMMAND_DISPOSITION',
      'result command disposition is unknown',
      'PROTOCOL_VIOLATION'
    );
  }
  optionalId(command.admission_event_id, 'result.extensions.live_voice.command.admission_event_id');
  optionalId(command.settlement_event_id, 'result.extensions.live_voice.command.settlement_event_id');
  if (POSITIVE_COMMAND_DISPOSITIONS.has(dispositionValue)) {
    if (!ok || error !== null) {
      throw violation(
        'COMMAND_DISPOSITION_RESULT_MISMATCH',
        'accepted/applied command disposition requires ok=true',
        'PROTOCOL_VIOLATION'
      );
    }
  } else {
    if (ok || error === null) {
      throw violation(
        'COMMAND_DISPOSITION_RESULT_MISMATCH',
        'negative command disposition requires ok=false',
        'PROTOCOL_VIOLATION'
      );
    }
    const allowedCodes = COMMAND_DISPOSITION_ERROR_CODES[dispositionValue];
    if (allowedCodes === undefined || !allowedCodes.has(error.code)) {
      throw violation(
        'COMMAND_DISPOSITION_ERROR_MISMATCH',
        'command disposition does not match its error family',
        'PROTOCOL_VIOLATION'
      );
    }
  }
  return cloneObject(data, fieldName);
}

export function parseResultEnvelope(value: unknown, owner?: Readonly<CommandEnvelope | QueryEnvelope>): Readonly<ResultEnvelope> {
  const normalizedOwner = owner === undefined ? undefined : normalizeOwner(owner);
  const data = strictRecord(value, 'result');
  exactKeys(data, ['contract_version', 'request_id', 'command_id', 'ok', 'result', 'error', 'observed_at', 'extensions'], 'result');
  if (data.contract_version !== CONTRACT_VERSION) {
    throw violation('UNSUPPORTED_CONTRACT_VERSION', `expected ${CONTRACT_VERSION}`, 'UNSUPPORTED');
  }
  const ok = requiredBoolean(data.ok, 'result.ok');
  const resultValue = data.result === null ? null : cloneObject(data.result, 'result.result');
  const errorValue = data.error === null ? null : parseContractError(data.error);
  if (ok ? resultValue === null || errorValue !== null : resultValue !== null || errorValue === null) {
    throw violation('INVALID_RESULT_EXCLUSIVITY', 'success requires result only; failure requires error only', 'PROTOCOL_VIOLATION');
  }
  const requestId = requiredText(data.request_id, 'result.request_id');
  const commandId = optionalId(data.command_id, 'result.command_id');
  const commandResult = normalizedOwner === undefined
    ? commandId !== null
    : Object.prototype.hasOwnProperty.call(normalizedOwner, 'command_id');
  const parsed = Object.freeze({
    contract_version: CONTRACT_VERSION,
    request_id: requestId,
    command_id: commandId,
    ok,
    result: resultValue,
    error: errorValue,
    observed_at: timestamp(data.observed_at, 'result.observed_at'),
    extensions: resultExtensions(data.extensions, commandResult, ok, errorValue),
  });
  if (normalizedOwner !== undefined) {
    const expectedCommandId = 'command_id' in normalizedOwner ? normalizedOwner.command_id : null;
    if (parsed.request_id !== normalizedOwner.request_id || parsed.command_id !== expectedCommandId) {
      throw violation('RESULT_OWNER_MISMATCH', 'result request_id/command_id does not match its owner', 'PROTOCOL_VIOLATION');
    }
  }
  return parsed;
}

function normalizeOwner(owner: Readonly<CommandEnvelope | QueryEnvelope>): Readonly<CommandEnvelope | QueryEnvelope> {
  const data = strictRecord(owner, 'result.owner');
  return Object.prototype.hasOwnProperty.call(data, 'command_id') ? parseCommandEnvelope(data) : parseQueryEnvelope(data);
}

export type PresentationClass = 'text' | 'voice';

export interface TaskUnreadEvent {
  readonly event_id: string;
  readonly task_id: string;
  readonly attempt_id: string;
  readonly scope: Readonly<ScopeRef>;
  readonly seq: number;
  readonly event_type: string;
  readonly state: (typeof TASK_EVENT_STATES)[number];
  readonly outcome: TerminalOutcome | null;
  readonly producer: string;
  readonly source_event_id: string | null;
  readonly causation_id: string;
  readonly correlation_id: string;
  readonly occurred_at: string;
  readonly details: Readonly<JsonObject>;
}

export interface TaskUnreadEventsPage {
  readonly task_id: string;
  readonly presentation_class: PresentationClass;
  readonly watermark: number;
  readonly acked_event_id: string | null;
  readonly head_seq: number;
  readonly events: readonly Readonly<TaskUnreadEvent>[];
  readonly next_after_seq: number | null;
  readonly has_more: boolean;
}

export interface TaskUnreadEventsResultEnvelope extends Omit<ResultEnvelope, 'command_id' | 'ok' | 'result' | 'error'> {
  readonly command_id: null;
  readonly ok: true;
  readonly result: Readonly<TaskUnreadEventsPage>;
  readonly error: null;
}

export interface TaskUnreadEventsAckSeed {
  readonly request_id: string;
  readonly command_id: string;
  readonly issued_at: string;
  readonly correlation_id: string;
  readonly causation_id: string | null;
  readonly origin: Readonly<OriginRef>;
}

function taskUnreadOwner(owner: Readonly<QueryEnvelope>): Readonly<QueryEnvelope> {
  const normalized = parseQueryEnvelope(owner);
  if (normalized.query_type !== 'task.unread_events') {
    throw violation('UNREAD_RESULT_OWNER_REQUIRED', 'task unread results require a task.unread_events owner', 'PROTOCOL_VIOLATION');
  }
  if (normalized.scope.assurance !== 'authenticated') {
    throw violation('AUTHENTICATED_CONSUMER_REQUIRED', 'task unread results require an authenticated consumer scope', 'UNAUTHENTICATED');
  }
  return normalized;
}

function taskUnreadWatermark(value: unknown, fieldName: string): number {
  if (value === -1) return -1;
  return unsignedInteger(value, fieldName);
}

function taskUnreadDetails(value: unknown, fieldName: string): Readonly<JsonObject> {
  const data = strictRecord(value, fieldName);
  for (const [key, item] of Object.entries(data)) {
    requiredText(key, `${fieldName} key`);
    if (typeof item === 'string') {
      validUnicode(item, `${fieldName}.${key}`);
    } else if (typeof item === 'number') {
      if (!Number.isSafeInteger(item)) {
        throw violation('INVALID_SAFE_INTEGER', `${fieldName}.${key} must be a safe integer`, 'PROTOCOL_VIOLATION');
      }
    } else if (item !== null && typeof item !== 'boolean') {
      throw violation('INVALID_TASK_EVENT_DETAILS', `${fieldName}.${key} must be a scalar JSON fact`, 'PROTOCOL_VIOLATION');
    }
  }
  return cloneObject(data, fieldName);
}

function parseTaskUnreadEvent(value: unknown, owner: Readonly<QueryEnvelope>, expectedSeq: number, index: number): Readonly<TaskUnreadEvent> {
  const fieldName = `result.result.events[${index}]`;
  const data = strictRecord(value, fieldName);
  exactKeys(
    data,
    [
      'event_id',
      'task_id',
      'attempt_id',
      'scope',
      'seq',
      'event_type',
      'state',
      'outcome',
      'producer',
      'source_event_id',
      'causation_id',
      'correlation_id',
      'occurred_at',
      'details',
    ],
    fieldName,
  );
  const taskId = requiredText(data.task_id, `${fieldName}.task_id`);
  if (taskId !== owner.target_ref.id) {
    throw violation('TASK_UNREAD_IDENTITY_MISMATCH', 'unread event belongs to another Task', 'PERMISSION_DENIED');
  }
  const scope = parseScopeRef(data.scope);
  if (scope.assurance !== 'authenticated' || scope.subject_id !== owner.scope.subject_id || scope.project_id !== owner.scope.project_id) {
    throw violation('TASK_UNREAD_SCOPE_MISMATCH', 'unread event belongs to another authenticated consumer scope', 'PERMISSION_DENIED');
  }
  const seq = unsignedInteger(data.seq, `${fieldName}.seq`);
  if (seq !== expectedSeq) {
    throw violation('TASK_UNREAD_PREFIX_GAP', 'unread events must be one contiguous prefix', 'PROTOCOL_VIOLATION');
  }
  const eventType = requiredText(data.event_type, `${fieldName}.event_type`);
  const state = enumeration(TASK_EVENT_STATES, data.state, `${fieldName}.state`);
  const outcome = data.outcome === null ? null : enumeration(TERMINAL_OUTCOMES, data.outcome, `${fieldName}.outcome`);
  if ((state === 'terminal') !== (outcome !== null)) {
    throw violation('INVALID_TASK_EVENT_OUTCOME', 'terminal task events require an outcome and nonterminal events forbid it', 'PROTOCOL_VIOLATION');
  }
  if (TASK_TERMINAL_EVENT_TYPES.has(eventType) !== (state === 'terminal')) {
    throw violation(
      'INVALID_TASK_TERMINAL_EVENT',
      'only canonical attempt.terminal/task.terminal events may carry terminal state',
      'PROTOCOL_VIOLATION',
    );
  }
  return Object.freeze({
    event_id: requiredText(data.event_id, `${fieldName}.event_id`),
    task_id: taskId,
    attempt_id: requiredText(data.attempt_id, `${fieldName}.attempt_id`),
    scope,
    seq,
    event_type: eventType,
    state,
    outcome,
    producer: requiredText(data.producer, `${fieldName}.producer`),
    source_event_id: optionalId(data.source_event_id, `${fieldName}.source_event_id`),
    causation_id: requiredText(data.causation_id, `${fieldName}.causation_id`),
    correlation_id: requiredText(data.correlation_id, `${fieldName}.correlation_id`),
    occurred_at: timestamp(data.occurred_at, `${fieldName}.occurred_at`),
    details: taskUnreadDetails(data.details, `${fieldName}.details`),
  });
}

function parseTaskUnreadEventsPage(value: unknown, owner: Readonly<QueryEnvelope>): Readonly<TaskUnreadEventsPage> {
  const fieldName = 'result.result';
  const data = strictRecord(value, fieldName);
  exactKeys(data, ['task_id', 'presentation_class', 'watermark', 'acked_event_id', 'head_seq', 'events', 'next_after_seq', 'has_more'], fieldName);
  const taskId = requiredText(data.task_id, `${fieldName}.task_id`);
  if (taskId !== owner.target_ref.id) {
    throw violation('TASK_UNREAD_IDENTITY_MISMATCH', 'unread page belongs to another Task', 'PERMISSION_DENIED');
  }
  const presentationClass = closedValue(data.presentation_class, `${fieldName}.presentation_class`, PRESENTATION_CLASSES) as PresentationClass;
  if (presentationClass !== owner.payload.presentation_class) {
    throw violation('TASK_UNREAD_PRESENTATION_CLASS_MISMATCH', 'unread page belongs to another presentation class', 'PERMISSION_DENIED');
  }
  const watermark = taskUnreadWatermark(data.watermark, `${fieldName}.watermark`);
  const headSeq = unsignedInteger(data.head_seq, `${fieldName}.head_seq`);
  if (watermark > headSeq) {
    throw violation('INVALID_TASK_UNREAD_PAGE', 'unread watermark exceeds its frozen head', 'PROTOCOL_VIOLATION');
  }
  const ackedEventId = optionalId(data.acked_event_id, `${fieldName}.acked_event_id`);
  if ((watermark === -1) !== (ackedEventId === null)) {
    throw violation('INVALID_TASK_UNREAD_PAGE', 'only the logical initial watermark may omit an acknowledged event', 'PROTOCOL_VIOLATION');
  }
  const rawEvents = strictArray(data.events, `${fieldName}.events`);
  const limit = owner.payload.limit;
  if (typeof limit !== 'number' || rawEvents.length > limit || rawEvents.length > 500) {
    throw violation('INVALID_TASK_UNREAD_PAGE', 'unread page exceeds the requested limit', 'PROTOCOL_VIOLATION');
  }
  const events = rawEvents.map((event, index) => parseTaskUnreadEvent(event, owner, watermark + index + 1, index));
  if (new Set(events.map(event => event.event_id)).size !== events.length) {
    throw violation('TASK_UNREAD_EVENT_DUPLICATE', 'unread page contains a duplicate event identity', 'PROTOCOL_VIOLATION');
  }
  const nextAfterSeq = data.next_after_seq === null ? null : unsignedInteger(data.next_after_seq, `${fieldName}.next_after_seq`);
  const hasMore = requiredBoolean(data.has_more, `${fieldName}.has_more`);
  const lastSeq = events.length === 0 ? undefined : events[events.length - 1].seq;
  if (hasMore) {
    if (lastSeq === undefined || nextAfterSeq !== lastSeq || lastSeq >= headSeq) {
      throw violation('INVALID_TASK_UNREAD_PAGE', 'truncated unread page lacks its next prefix position', 'PROTOCOL_VIOLATION');
    }
  } else if (nextAfterSeq !== null || (lastSeq === undefined ? watermark !== headSeq : lastSeq !== headSeq)) {
    throw violation('INVALID_TASK_UNREAD_PAGE', 'complete unread page does not reach its frozen head', 'PROTOCOL_VIOLATION');
  }
  return Object.freeze({
    task_id: taskId,
    presentation_class: presentationClass,
    watermark,
    acked_event_id: ackedEventId,
    head_seq: headSeq,
    events: Object.freeze(events),
    next_after_seq: nextAfterSeq,
    has_more: hasMore,
  });
}

export function parseTaskUnreadEventsResult(value: unknown, owner: Readonly<QueryEnvelope>): Readonly<TaskUnreadEventsResultEnvelope> {
  const normalizedOwner = taskUnreadOwner(owner);
  const envelope = parseResultEnvelope(value, normalizedOwner);
  if (!envelope.ok || envelope.result === null || envelope.error !== null || envelope.command_id !== null) {
    throw violation('UNREAD_RESULT_SUCCESS_REQUIRED', 'task unread parser accepts only a successful query result', 'PROTOCOL_VIOLATION');
  }
  return Object.freeze({
    ...envelope,
    command_id: null,
    ok: true,
    result: parseTaskUnreadEventsPage(envelope.result, normalizedOwner),
    error: null,
  });
}

function parseTaskUnreadEventsAckSeed(value: unknown): Readonly<TaskUnreadEventsAckSeed> {
  const data = strictRecord(value, 'task_ack_seed');
  exactKeys(data, ['request_id', 'command_id', 'issued_at', 'correlation_id', 'causation_id', 'origin'], 'task_ack_seed');
  const origin = strictRecord(data.origin, 'task_ack_seed.origin');
  return Object.freeze({
    request_id: requiredText(data.request_id, 'task_ack_seed.request_id'),
    command_id: requiredText(data.command_id, 'task_ack_seed.command_id'),
    issued_at: timestamp(data.issued_at, 'task_ack_seed.issued_at'),
    correlation_id: requiredText(data.correlation_id, 'task_ack_seed.correlation_id'),
    causation_id: optionalId(data.causation_id, 'task_ack_seed.causation_id'),
    origin: cloneObject(origin, 'task_ack_seed.origin') as unknown as Readonly<OriginRef>,
  });
}

/**
 * Serializes a canonical ACK candidate for a validated unread prefix.
 *
 * This pure wire helper neither records presentation nor authorizes dispatch.
 * P3-5B composition must call it only after class-local text DOM adoption or
 * audio PresentationAck evidence has been accepted for the same final event.
 */
export function buildTaskUnreadEventsAck(unreadResult: unknown, owner: Readonly<QueryEnvelope>, seed: unknown): Readonly<CommandEnvelope> | null {
  const normalizedOwner = taskUnreadOwner(owner);
  const parsedResult = parseTaskUnreadEventsResult(unreadResult, normalizedOwner);
  const parsedSeed = parseTaskUnreadEventsAckSeed(seed);
  const lastEvent = parsedResult.result.events.length === 0 ? undefined : parsedResult.result.events[parsedResult.result.events.length - 1];
  if (lastEvent === undefined) return null;
  return parseCommandEnvelope({
    contract_version: CONTRACT_VERSION,
    request_id: parsedSeed.request_id,
    command_id: parsedSeed.command_id,
    command_type: 'task.ack_events',
    issued_at: parsedSeed.issued_at,
    scope: normalizedOwner.scope,
    correlation_id: parsedSeed.correlation_id,
    causation_id: parsedSeed.causation_id,
    origin: parsedSeed.origin,
    target_ref: normalizedOwner.target_ref,
    context_refs: normalizedOwner.context_refs,
    required_capabilities: ['task.ack_events'],
    payload: {
      presentation_class: parsedResult.result.presentation_class,
      acked_through_seq: lastEvent.seq,
      acked_event_id: lastEvent.event_id,
      expected_event_head: parsedResult.result.head_seq,
    },
    extensions: {},
  });
}

export function successResult(
  owner: Readonly<CommandEnvelope | QueryEnvelope>,
  result: JsonObject,
  observedAt: string,
  resultExtensionValue: JsonObject = {},
): Readonly<ResultEnvelope> {
  const normalizedOwner = normalizeOwner(owner);
  return parseResultEnvelope(
    {
      contract_version: CONTRACT_VERSION,
      request_id: normalizedOwner.request_id,
      command_id: 'command_id' in normalizedOwner ? normalizedOwner.command_id : null,
      ok: true,
      result,
      error: null,
      observed_at: observedAt,
      extensions: resultExtensionValue,
    },
    normalizedOwner
  );
}

export function failureResult(
  owner: Readonly<CommandEnvelope | QueryEnvelope>,
  error: Readonly<ContractErrorValue>,
  observedAt: string,
  resultExtensionValue: JsonObject = {},
): Readonly<ResultEnvelope> {
  const normalizedOwner = normalizeOwner(owner);
  return parseResultEnvelope(
    {
      contract_version: CONTRACT_VERSION,
      request_id: normalizedOwner.request_id,
      command_id: 'command_id' in normalizedOwner ? normalizedOwner.command_id : null,
      ok: false,
      result: null,
      error: errorToWire(error),
      observed_at: observedAt,
      extensions: resultExtensionValue,
    },
    normalizedOwner
  );
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

export interface CapabilityDescriptor {
  readonly component: string;
  readonly contract_major: 'v2';
  readonly supported_operations: readonly string[];
  readonly supported_event_types: readonly string[];
  readonly batch_modes: readonly 'batch'[];
  readonly stream_modes: readonly 'stream'[];
  readonly supports_cancel_ack: boolean;
  readonly supports_replay: boolean;
  readonly declared_limits: Readonly<JsonObject>;
  readonly fallback_identity: string | null;
  readonly availability: Availability;
}

function uniqueNamespaced(value: unknown, fieldName: string): readonly string[] {
  const result = strictArray(value, fieldName).map((item, index) => namespaced(item, `${fieldName}[${index}]`));
  if (new Set(result).size !== result.length) {
    throw violation('DUPLICATE_CAPABILITY_VALUE', `${fieldName} contains duplicates`);
  }
  return Object.freeze(result);
}

function uniqueModes<T extends string>(value: unknown, fieldName: string, choices: readonly T[]): readonly T[] {
  const result = strictArray(value, fieldName).map((item, index) => enumeration(choices, item, `${fieldName}[${index}]`));
  if (new Set(result).size !== result.length) {
    throw violation('DUPLICATE_CAPABILITY_VALUE', `${fieldName} contains duplicates`);
  }
  return Object.freeze(result);
}

export function parseCapabilityDescriptor(value: unknown): Readonly<CapabilityDescriptor> {
  const data = strictRecord(value, 'capability');
  exactKeys(
    data,
    [
      'component',
      'contract_major',
      'supported_operations',
      'supported_event_types',
      'batch_modes',
      'stream_modes',
      'supports_cancel_ack',
      'supports_replay',
      'declared_limits',
      'fallback_identity',
      'availability',
    ],
    'capability'
  );
  if (data.contract_major !== 'v2') {
    throw violation('UNSUPPORTED_CONTRACT_MAJOR', 'contract_major must be v2', 'UNSUPPORTED');
  }
  return Object.freeze({
    component: requiredText(data.component, 'capability.component'),
    contract_major: 'v2',
    supported_operations: uniqueNamespaced(data.supported_operations, 'capability.supported_operations'),
    supported_event_types: uniqueNamespaced(data.supported_event_types, 'capability.supported_event_types'),
    batch_modes: uniqueModes(data.batch_modes, 'capability.batch_modes', ['batch']),
    stream_modes: uniqueModes(data.stream_modes, 'capability.stream_modes', ['stream']),
    supports_cancel_ack: requiredBoolean(data.supports_cancel_ack, 'capability.supports_cancel_ack'),
    supports_replay: requiredBoolean(data.supports_replay, 'capability.supports_replay'),
    declared_limits: cloneObject(data.declared_limits, 'capability.declared_limits'),
    fallback_identity: optionalId(data.fallback_identity, 'capability.fallback_identity'),
    availability: enumeration(['available', 'unavailable'] as const, data.availability, 'capability.availability'),
  });
}

export class CapabilityRegistry {
  readonly #descriptors = new Map<string, Readonly<CapabilityDescriptor>>();

  register(descriptor: Readonly<CapabilityDescriptor>): void {
    const normalized = parseCapabilityDescriptor(descriptor);
    const existing = this.#descriptors.get(normalized.component);
    if (existing !== undefined && canonicalJson(existing) !== canonicalJson(normalized)) {
      throw violation('CAPABILITY_DESCRIPTOR_CONFLICT', `${normalized.component} changed descriptor`, 'CONFLICT');
    }
    this.#descriptors.set(normalized.component, normalized);
  }

  require(component: string, operation: string): void {
    const parsedComponent = requiredText(component, 'capability.component');
    const parsedOperation = namespaced(operation, 'capability.operation');
    const descriptor = this.#descriptors.get(parsedComponent);
    if (descriptor === undefined || !descriptor.supported_operations.includes(parsedOperation)) {
      throw violation('CAPABILITY_UNSUPPORTED', `${parsedComponent} does not support ${parsedOperation}`, 'UNSUPPORTED');
    }
    if (descriptor.availability === 'unavailable') {
      throw violation('CAPABILITY_TEMPORARILY_UNAVAILABLE', `${parsedComponent} is temporarily unavailable`, 'UNAVAILABLE');
    }
  }
}

export function contractError(
  code: ErrorCode,
  reason: string,
  message: string,
  retriable = false,
  correlationId: string | null = null,
  details: JsonObject = {}
): Readonly<ContractErrorValue> {
  return Object.freeze({
    code: enumeration(ERROR_CODES, code, 'error.code'),
    reason: optionalStableReason(reason, 'error.reason'),
    message: requiredText(message, 'error.message'),
    retriable,
    correlation_id: optionalId(correlationId, 'error.correlation_id'),
    details: cloneObject(details, 'error.details'),
  });
}

const LIFECYCLE_TRANSITIONS: Readonly<Record<LifecycleKind, Readonly<Record<string, readonly string[]>>>> = Object.freeze({
  interaction: Object.freeze({
    open: Object.freeze(['closing', 'closed']),
    closing: Object.freeze(['closed']),
  }),
  turn: Object.freeze({ capturing: Object.freeze(['committed', 'cancelled']) }),
  response: Object.freeze({
    accepted: Object.freeze(['generating', 'terminal']),
    generating: Object.freeze(['speaking', 'terminal']),
    speaking: Object.freeze(['terminal']),
  }),
  round: Object.freeze({
    accepted: Object.freeze(['running', 'blocked', 'decision_required', 'terminal']),
    running: Object.freeze(['blocked', 'decision_required', 'terminal']),
    blocked: Object.freeze(['running', 'decision_required', 'terminal']),
    decision_required: Object.freeze(['running', 'blocked', 'terminal']),
  }),
  task: Object.freeze({
    accepted: Object.freeze(['running', 'blocked', 'decision_required', 'terminal']),
    running: Object.freeze(['blocked', 'decision_required', 'terminal']),
    blocked: Object.freeze(['running', 'decision_required', 'terminal']),
    decision_required: Object.freeze(['running', 'blocked', 'terminal']),
  }),
  attempt: Object.freeze({ accepted: Object.freeze(['running']), running: Object.freeze(['terminal']) }),
});

export function validateTransition(kind: LifecycleKind, current: string, nextState: string, outcome: TerminalOutcome | null = null): void {
  const parsedKind = enumeration(LIFECYCLE_KINDS, kind, 'lifecycle.kind');
  const parsedCurrent = requiredText(current, 'lifecycle.current');
  const parsedNext = requiredText(nextState, 'lifecycle.next');
  const allowed = LIFECYCLE_TRANSITIONS[parsedKind][parsedCurrent] ?? [];
  if (!allowed.includes(parsedNext)) {
    throw violation('INVALID_LIFECYCLE_TRANSITION', `${parsedKind} cannot transition from ${parsedCurrent} to ${parsedNext}`, 'CONFLICT');
  }
  if (parsedNext === 'terminal') {
    if (outcome === null) {
      throw violation('TERMINAL_OUTCOME_REQUIRED', 'terminal transitions require an outcome');
    }
    enumeration(TERMINAL_OUTCOMES, outcome, 'lifecycle.outcome');
  } else if (outcome !== null) {
    throw violation('NON_TERMINAL_OUTCOME_FORBIDDEN', 'outcome is only valid for terminal transitions');
  }
}

export interface TurnCommit {
  readonly contract_version: typeof CONTRACT_VERSION;
  readonly commit_id: string;
  readonly turn_id: string;
  readonly interaction_id: string;
  readonly text: string;
  readonly hypothesis_provenance: Readonly<JsonObject>;
  readonly scope: Readonly<ScopeRef>;
  readonly context_refs: readonly Readonly<ContextRef>[];
  readonly committed_at: string;
}

export function parseTurnCommit(value: unknown, identities?: IdentityRegistry): Readonly<TurnCommit> {
  const data = strictRecord(value, 'turn_commit');
  exactKeys(
    data,
    ['contract_version', 'commit_id', 'turn_id', 'interaction_id', 'text', 'hypothesis_provenance', 'scope', 'context_refs', 'committed_at'],
    'turn_commit'
  );
  if (data.contract_version !== CONTRACT_VERSION) {
    throw violation('UNSUPPORTED_CONTRACT_VERSION', `expected ${CONTRACT_VERSION}`, 'UNSUPPORTED');
  }
  const scope = parseScopeRef(data.scope);
  const turnId = requiredText(data.turn_id, 'turn_commit.turn_id');
  const interactionId = requiredText(data.interaction_id, 'turn_commit.interaction_id');
  if (identities !== undefined) {
    const interaction = { kind: 'interaction' as const, id: interactionId };
    identities.require(interaction, { scope });
    identities.require({ kind: 'turn', id: turnId }, { scope, parent: interaction });
  }
  return Object.freeze({
    contract_version: CONTRACT_VERSION,
    commit_id: requiredText(data.commit_id, 'turn_commit.commit_id'),
    turn_id: turnId,
    interaction_id: interactionId,
    text: requiredText(data.text, 'turn_commit.text'),
    hypothesis_provenance: cloneObject(data.hypothesis_provenance, 'turn_commit.hypothesis_provenance'),
    scope,
    context_refs: contextRefs(data.context_refs, 'turn_commit.context_refs', scope),
    committed_at: timestamp(data.committed_at, 'turn_commit.committed_at'),
  });
}

export class TurnCommitLedger {
  readonly #byCommitId = new Map<string, Readonly<TurnCommit>>();
  readonly #byTurnId = new Map<string, Readonly<TurnCommit>>();

  accept(commit: Readonly<TurnCommit>): boolean {
    const normalized = parseTurnCommit(commit);
    const existing = this.#byCommitId.get(normalized.commit_id) ?? this.#byTurnId.get(normalized.turn_id);
    if (existing !== undefined) {
      if (canonicalJson(existing) === canonicalJson(normalized)) return false;
      throw violation('TURN_COMMIT_CONFLICT', 'commit_id and turn_id are immutable and may commit only once', 'CONFLICT');
    }
    this.#byCommitId.set(normalized.commit_id, normalized);
    this.#byTurnId.set(normalized.turn_id, normalized);
    return true;
  }

  requireOrigin(origin: Readonly<OriginRef>, scope: Readonly<ScopeRef>): Readonly<TurnCommit> {
    const normalizedOrigin = parseOriginRef(origin);
    const normalizedScope = parseScopeRef(scope);
    if (normalizedOrigin.kind !== 'committed_turn') {
      throw violation('COMMITTED_ORIGIN_REQUIRED', 'origin must identify a committed turn');
    }
    const commit = this.#byCommitId.get(normalizedOrigin.commit_id ?? '');
    if (commit === undefined || commit.turn_id !== normalizedOrigin.turn_id || scopeKey(commit.scope) !== scopeKey(normalizedScope)) {
      throw violation('TURN_COMMIT_NOT_ACCEPTED', 'origin does not match an accepted commit in the exact scope', 'PERMISSION_DENIED');
    }
    return commit;
  }

  dispatch<T>(commit: Readonly<TurnCommit>, target: SideEffectTarget, effect: (commit: Readonly<TurnCommit>) => T): readonly [boolean, T | undefined] {
    enumeration(['agent', 'tool', 'task'] as const, target, 'input.target');
    const normalized = parseTurnCommit(commit);
    if (!this.accept(normalized)) return Object.freeze([false, undefined]);
    return Object.freeze([true, effect(normalized)]);
  }
}

export function dispatchCommittedInput<T>(state: InputCommitState, target: SideEffectTarget, effect: () => T): T {
  const parsedState = enumeration(INPUT_COMMIT_STATES, state, 'input.state');
  enumeration(['agent', 'tool', 'task'] as const, target, 'input.target');
  if (parsedState !== 'committed') {
    throw violation('INPUT_NOT_COMMITTED', 'partial or uncommitted input cannot invoke Agent, Tool, or Task', 'PERMISSION_DENIED');
  }
  return effect();
}

export interface ResponseRef {
  readonly interaction_id: string;
  readonly response_id: string;
  readonly response_generation: number;
}

function parseResponseRef(ref: ResponseRef): Readonly<ResponseRef> {
  return Object.freeze({
    interaction_id: requiredText(ref.interaction_id, 'response_ref.interaction_id'),
    response_id: requiredText(ref.response_id, 'response_ref.response_id'),
    response_generation: unsignedInteger(ref.response_generation, 'response_ref.response_generation'),
  });
}

interface ResponseState {
  readonly ref: Readonly<ResponseRef>;
  fenced: boolean;
  terminal: boolean;
}

export class ResponseFence {
  readonly #byInteraction = new Map<string, ResponseState>();
  readonly #seenIds = new Set<string>();
  readonly #lastGeneration = new Map<string, number>();

  begin(input: ResponseRef): void {
    const ref = parseResponseRef(input);
    const last = this.#lastGeneration.get(ref.interaction_id) ?? -1;
    if (this.#seenIds.has(ref.response_id)) {
      throw violation('RESPONSE_ID_REUSED', 'every replacement response requires a new response_id', 'CONFLICT');
    }
    if (ref.response_generation <= last) {
      throw violation('RESPONSE_GENERATION_NOT_INCREASING', 'response_generation must strictly increase per interaction', 'STALE');
    }
    const prior = this.#byInteraction.get(ref.interaction_id);
    if (prior !== undefined) prior.fenced = true;
    this.#seenIds.add(ref.response_id);
    this.#lastGeneration.set(ref.interaction_id, ref.response_generation);
    this.#byInteraction.set(ref.interaction_id, { ref, fenced: false, terminal: false });
  }

  cancel(input: ResponseRef): void {
    this.#requireExact(parseResponseRef(input)).fenced = true;
  }

  terminal(input: ResponseRef): void {
    const state = this.#requireExact(parseResponseRef(input));
    state.fenced = true;
    state.terminal = true;
  }

  applyIfCurrent<T>(input: ResponseRef, effect: () => T): T {
    const ref = parseResponseRef(input);
    const state = this.#byInteraction.get(ref.interaction_id);
    if (state === undefined || canonicalJson(state.ref) !== canonicalJson(ref) || state.fenced || state.terminal) {
      throw violation('STALE_RESPONSE_OUTPUT', 'output does not match the exact active response tuple', 'STALE');
    }
    return effect();
  }

  #requireExact(ref: Readonly<ResponseRef>): ResponseState {
    const state = this.#byInteraction.get(ref.interaction_id);
    if (state === undefined || canonicalJson(state.ref) !== canonicalJson(ref)) {
      throw violation('STALE_RESPONSE_REFERENCE', 'operation does not match the exact active response tuple', 'STALE');
    }
    return state;
  }
}

export function defaultBargeInScopes(cancelResponse = false): readonly CancelScope[] {
  requiredBoolean(cancelResponse, 'barge_in.cancel_response');
  return Object.freeze(cancelResponse ? ['playback.stop', 'response.cancel'] : ['playback.stop']);
}

export function dispatchCancel<T>(
  command: Readonly<CommandEnvelope>,
  handlers: Readonly<Partial<Record<CancelScope, (command: Readonly<CommandEnvelope>) => T>>>
): T {
  const normalized = parseCommandEnvelope(command);
  const scope = normalized.command_type as CancelScope;
  if (!(['playback.stop', 'response.cancel', 'round.cancel', 'task.cancel'] as const).includes(scope)) {
    throw violation('NOT_A_CANCEL_COMMAND', 'command is not an explicit cancel operation');
  }
  const handler = handlers[scope];
  if (handler === undefined) {
    throw violation('CANCEL_HANDLER_UNAVAILABLE', `no handler is available for ${scope}`, 'CAPABILITY_UNAVAILABLE');
  }
  return handler(normalized);
}

interface CommandExecution {
  readonly fingerprint: Uint8Array;
  readonly result: Promise<Readonly<ResultEnvelope>>;
}

function bytesEqual(left: Uint8Array, right: Uint8Array): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function resultForRequest(result: Readonly<ResultEnvelope>, requestId: string): Readonly<ResultEnvelope> {
  return Object.freeze({ ...result, request_id: requiredText(requestId, 'result.request_id') });
}

export class CommandResultLedger {
  readonly #entries = new Map<string, CommandExecution>();

  async execute(
    command: Readonly<CommandEnvelope>,
    observedAt: string,
    handler: (command: Readonly<CommandEnvelope>) => Readonly<ResultEnvelope> | Promise<Readonly<ResultEnvelope>>
  ): Promise<Readonly<ResultEnvelope>> {
    const normalized = parseCommandEnvelope(command);
    const normalizedObservedAt = timestamp(observedAt, 'result.observed_at');
    const fingerprint = commandFingerprint(normalized);
    const existing = this.#entries.get(normalized.command_id);
    if (existing !== undefined) {
      if (!bytesEqual(existing.fingerprint, fingerprint)) {
        return failureResult(
          normalized,
          contractError('CONFLICT', 'IDEMPOTENCY_CONFLICT', 'command_id was reused with different content'),
          normalizedObservedAt
        );
      }
      return resultForRequest(await existing.result, normalized.request_id);
    }
    let resolvePending!: (value: Readonly<ResultEnvelope>) => void;
    const pending = new Promise<Readonly<ResultEnvelope>>(resolve => {
      resolvePending = resolve;
    });
    this.#entries.set(normalized.command_id, { fingerprint, result: pending });
    let result: Readonly<ResultEnvelope>;
    try {
      result = parseResultEnvelope(await handler(normalized), normalized);
    } catch (error: unknown) {
      if (error instanceof ContractViolation) {
        try {
          result = failureResult(normalized, error.error, normalizedObservedAt);
        } catch {
          result = failureResult(normalized, contractError('INTERNAL', 'COMMAND_HANDLER_FAILED', 'command handler failed'), normalizedObservedAt);
        }
      } else {
        result = failureResult(normalized, contractError('INTERNAL', 'COMMAND_HANDLER_FAILED', 'command handler failed'), normalizedObservedAt);
      }
    }
    resolvePending(result);
    return result;
  }
}

export type EventApplyStatus =
  | 'applied'
  | 'duplicate_applied'
  | 'quarantined_gap'
  | 'quarantined_causation'
  | 'quarantined_projection'
  | 'duplicate_quarantined'
  | 'rejected_conflict'
  | 'rejected_causation'
  | 'rejected_projection'
  | 'rejected_lifecycle';

export interface EventApplyResult {
  readonly status: EventApplyStatus;
  readonly error: Readonly<ContractErrorValue> | null;
  readonly appliedEventIds: readonly string[];
}

interface EventStreamState {
  nextSeq: number;
  readonly appliedBySeq: Map<number, Readonly<EventEnvelope>>;
  readonly quarantinedBySeq: Map<number, Readonly<EventEnvelope>>;
  readonly poisonedSeq: Set<number>;
}

const INITIAL_LIFECYCLE_STATES: Readonly<Partial<Record<IdentityKind, string>>> = Object.freeze({
  interaction: 'open',
  turn: 'capturing',
  response: 'accepted',
  round: 'accepted',
  task: 'accepted',
  attempt: 'accepted',
});
const PROJECTION_ERROR_REASONS = new Set([
  'PROGRESS_SEQUENCE_GAP',
  'PROGRESS_SEQUENCE_REUSED',
  'PROGRESS_SOURCE_ALREADY_PROJECTED',
  'PROGRESS_SOURCE_ORDER_MISMATCH',
  'PROGRESS_DETAIL_UNPROVEN',
]);

function eventStreamKey(event: Readonly<EventEnvelope>): string {
  return canonicalJson([event.producer.component, event.producer.instance_id, event.stream_ref.kind, event.stream_ref.id]);
}

function progressSourceKey(event: Readonly<EventEnvelope>): string {
  return canonicalJson([event.scope, event.stream_ref.kind, event.stream_ref.id]);
}

function applyResult(
  status: EventApplyStatus,
  error: Readonly<ContractErrorValue> | null = null,
  appliedEventIds: readonly string[] = []
): Readonly<EventApplyResult> {
  return Object.freeze({ status, error, appliedEventIds: Object.freeze([...appliedEventIds]) });
}

export class EventSequenceTracker {
  readonly #identities: IdentityRegistry | undefined;
  readonly #streams = new Map<string, EventStreamState>();
  readonly #events = new Map<string, Readonly<EventEnvelope>>();
  readonly #results = new Map<string, Readonly<EventApplyResult>>();
  readonly #appliedIds = new Set<string>();
  readonly #externalCauses = new Map<string, Readonly<CommandEnvelope>>();
  readonly #lifecycleByObject = new Map<string, string>();
  readonly #taskAttemptNumberByObject = new Map<string, number>();
  readonly #taskTerminalOutcomeByObject = new Map<string, string>();
  readonly #scopeByObject = new Map<string, Readonly<ScopeRef>>();
  readonly #nextProgressSeq = new Map<string, number>();
  readonly #progressSourceQueues = new Map<string, string[]>();
  readonly #projectedSources = new Set<string>();

  constructor(identities?: IdentityRegistry) {
    this.#identities = identities;
  }

  registerAppliedCause(command: Readonly<CommandEnvelope>): readonly string[] {
    const normalized = parseCommandEnvelope(command);
    const causeId = normalized.command_id;
    if (this.#events.has(causeId)) {
      throw violation('CAUSATION_ID_KIND_CONFLICT', 'an event_id cannot also be an external command cause', 'PROTOCOL_VIOLATION');
    }
    const existing = this.#externalCauses.get(causeId);
    if (existing !== undefined && !bytesEqual(commandFingerprint(existing), commandFingerprint(normalized))) {
      throw violation('CAUSATION_SOURCE_CONFLICT', 'an applied command cause cannot change its canonical facts', 'PROTOCOL_VIOLATION');
    }
    this.#externalCauses.set(causeId, normalized);
    return Object.freeze(this.#applyAndDrain());
  }

  accept(input: Readonly<EventEnvelope>): Readonly<EventApplyResult> {
    const event = parseEventEnvelope(input, this.#identities);
    if (this.#externalCauses.has(event.event_id)) {
      return this.#errorResult('rejected_conflict', 'CAUSATION_ID_KIND_CONFLICT', 'an external command cause cannot also be an event_id');
    }
    const existing = this.#events.get(event.event_id);
    if (existing !== undefined) {
      const prior = this.#results.get(event.event_id);
      if (canonicalJson(existing) !== canonicalJson(event)) {
        const result = this.#errorResult('rejected_conflict', 'EVENT_ID_CONFLICT', 'event_id was reused with different content');
        if (!this.#appliedIds.has(event.event_id)) {
          const existingStream = this.#streams.get(eventStreamKey(existing));
          existingStream?.quarantinedBySeq.delete(existing.seq);
          existingStream?.poisonedSeq.add(existing.seq);
          this.#results.set(event.event_id, result);
        }
        return result;
      }
      return applyResult(this.#appliedIds.has(event.event_id) ? 'duplicate_applied' : 'duplicate_quarantined', prior?.error ?? null);
    }

    this.#events.set(event.event_id, event);
    if (this.#causalCycle(event)) {
      const result = this.#errorResult('rejected_causation', 'CAUSATION_CYCLE', 'event causation must be acyclic');
      this.#results.set(event.event_id, result);
      return result;
    }

    const key = eventStreamKey(event);
    const stream = this.#streams.get(key) ?? {
      nextSeq: 0,
      appliedBySeq: new Map<number, Readonly<EventEnvelope>>(),
      quarantinedBySeq: new Map<number, Readonly<EventEnvelope>>(),
      poisonedSeq: new Set<number>(),
    };
    this.#streams.set(key, stream);
    const priorAtSeq = stream.appliedBySeq.get(event.seq) ?? stream.quarantinedBySeq.get(event.seq);
    if (priorAtSeq !== undefined) {
      stream.quarantinedBySeq.delete(event.seq);
      stream.poisonedSeq.add(event.seq);
      const result = this.#errorResult('rejected_conflict', 'EVENT_SEQUENCE_CONFLICT', 'two different events claim the same producer stream sequence');
      this.#results.set(event.event_id, result);
      return result;
    }
    if (event.seq < stream.nextSeq || stream.poisonedSeq.has(event.seq)) {
      const result = this.#errorResult('rejected_conflict', 'EVENT_SEQUENCE_REUSED', 'producer stream sequence was already consumed or poisoned');
      this.#results.set(event.event_id, result);
      return result;
    }
    stream.quarantinedBySeq.set(event.seq, event);
    if (event.seq > stream.nextSeq) {
      const result = this.#errorResult('quarantined_gap', 'EVENT_SEQUENCE_GAP', `expected sequence ${stream.nextSeq}, received ${event.seq}`);
      this.#results.set(event.event_id, result);
      return result;
    }
    const causalError = this.#causalBlock(event);
    if (causalError !== null) {
      if (causalError[2]) {
        stream.quarantinedBySeq.delete(event.seq);
        stream.poisonedSeq.add(event.seq);
        const result = this.#errorResult(
          PROJECTION_ERROR_REASONS.has(causalError[0]) ? 'rejected_projection' : 'rejected_causation',
          causalError[0],
          causalError[1]
        );
        this.#results.set(event.event_id, result);
        return result;
      }
      const result = this.#errorResult(
        causalError[0] === 'PROGRESS_SEQUENCE_GAP' ? 'quarantined_projection' : 'quarantined_causation',
        causalError[0],
        causalError[1]
      );
      this.#results.set(event.event_id, result);
      return result;
    }
    const lifecycleError = this.#lifecycleError(event);
    if (lifecycleError !== null) {
      stream.quarantinedBySeq.delete(event.seq);
      stream.poisonedSeq.add(event.seq);
      const result = applyResult('rejected_lifecycle', lifecycleError);
      this.#results.set(event.event_id, result);
      return result;
    }
    const applied = this.#applyAndDrain();
    const current = this.#results.get(event.event_id);
    if (!this.#appliedIds.has(event.event_id) && current !== undefined) return current;
    const result = applyResult('applied', null, applied);
    this.#results.set(event.event_id, result);
    return result;
  }

  #errorResult(status: EventApplyStatus, reason: string, message: string): Readonly<EventApplyResult> {
    const code: ErrorCode = 'PROTOCOL_VIOLATION';
    const retriable = status === 'quarantined_gap' || status === 'quarantined_causation' || status === 'quarantined_projection';
    return applyResult(status, contractError(code, reason, message, retriable));
  }

  #causalCycle(event: Readonly<EventEnvelope>): boolean {
    const seen = new Set([event.event_id]);
    let cursor = event.causation_id;
    while (cursor !== null) {
      if (seen.has(cursor)) return true;
      seen.add(cursor);
      cursor = this.#events.get(cursor)?.causation_id ?? null;
    }
    return false;
  }

  #causalBlock(event: Readonly<EventEnvelope>): readonly [string, string, boolean] | null {
    if (event.causation_id === null) return null;
    const source = this.#events.get(event.causation_id);
    const external = this.#externalCauses.get(event.causation_id);
    if (source === undefined && external !== undefined) {
      const mismatch = this.#causalContextError(event, external.scope, external.correlation_id);
      if (mismatch !== null) return mismatch;
      if (EVENT_RULES[event.event_type].adapter === true) {
        return ['ADAPTER_SOURCE_EVENT_REQUIRED', 'adapter events must reference an authoritative source event', true];
      }
      if (
        event.event_type === 'task.retry_accepted'
        && (
          external.command_type !== 'task.retry'
          || event.payload.command_id !== external.command_id
          || event.stream_ref.kind !== external.target_ref.kind
          || event.stream_ref.id !== external.target_ref.id
          || event.payload.retry_of_attempt_id !== external.payload.previous_attempt_id
          || event.payload.previous_outcome !== external.payload.previous_outcome
          || event.payload.attempt_number !== external.payload.attempt_number
        )
      ) {
        return [
          'TASK_RETRY_CAUSATION_MISMATCH',
          'task.retry_accepted must bind the exact applied retry command',
          true,
        ];
      }
      return null;
    }
    if (source === undefined || !this.#appliedIds.has(source.event_id)) {
      return ['CAUSATION_NOT_APPLIED', 'causation_id must reference an already applied event', false];
    }
    const mismatch = this.#causalContextError(event, source.scope, source.correlation_id);
    if (mismatch !== null) return mismatch;
    const rule = EVENT_RULES[event.event_type];
    if (rule.adapter === true) {
      if (source.producer.authority === 'adapter') {
        return ['ADAPTER_SOURCE_NOT_AUTHORITATIVE', 'adapter events cannot establish authority for another adapter event', true];
      }
      if (rule.progress === true) {
        const progress = parseWorkProgressEventV2(event.payload, event.scope);
        const sourceOutcome = source.payload.outcome ?? null;
        if (
          progress.source.event_id !== source.event_id ||
          progress.source.authority !== source.producer.authority ||
          progress.source.source_work_ref.kind !== source.stream_ref.kind ||
          progress.source.source_work_ref.id !== source.stream_ref.id ||
          progress.state !== source.payload.state ||
          progress.outcome !== sourceOutcome
        ) {
          return ['PROGRESS_SOURCE_MISMATCH', 'WorkProgress must preserve source identity, authority, state, and outcome', true];
        }
        const progressKey = canonicalJson([event.scope, progress.work_ref.kind, progress.work_ref.id]);
        const expected = this.#nextProgressSeq.get(progressKey) ?? 0;
        if (progress.seq > expected) {
          return ['PROGRESS_SEQUENCE_GAP', 'WorkProgress projection sequence is waiting for an earlier event', false];
        }
        if (progress.seq < expected) {
          return ['PROGRESS_SEQUENCE_REUSED', 'WorkProgress projection sequence was already consumed', true];
        }
        if (this.#projectedSources.has(source.event_id)) {
          return ['PROGRESS_SOURCE_ALREADY_PROJECTED', 'one authoritative source event can produce only one WorkProgress projection', true];
        }
        const sourceQueue = this.#progressSourceQueues.get(progressSourceKey(source));
        if (sourceQueue === undefined || sourceQueue.length === 0) {
          return ['PROGRESS_SOURCE_ORDER_MISMATCH', 'WorkProgress source has no pending authoritative position', true];
        }
        if (sourceQueue[0] !== source.event_id) {
          return ['PROGRESS_SOURCE_ORDER_MISMATCH', 'WorkProgress must preserve authoritative source application order', true];
        }
        if (
          progress.summary.knowledge === 'known' ||
          progress.blocking_question.knowledge === 'known' ||
          progress.artifact_refs.knowledge === 'known' ||
          progress.urgency !== 'unknown' ||
          progress.speakability !== 'not_speakable'
        ) {
          return ['PROGRESS_DETAIL_UNPROVEN', 'current source event schema cannot prove WorkProgress detail or notification hints', true];
        }
      } else if (event.payload.source_event_type !== source.event_type) {
        return ['ADAPTER_SOURCE_TYPE_MISMATCH', 'adapter source_event_type must match the causal source event', true];
      }
    }
    return null;
  }

  #causalContextError(event: Readonly<EventEnvelope>, sourceScope: Readonly<ScopeRef>, sourceCorrelationId: string): readonly [string, string, boolean] | null {
    if (scopeKey(event.scope) !== scopeKey(sourceScope)) {
      return ['CAUSATION_SCOPE_MISMATCH', 'a derived event must have the same scope as its immediate cause', true];
    }
    if (event.correlation_id !== sourceCorrelationId) {
      return ['CAUSATION_CORRELATION_MISMATCH', 'a derived event must have the same correlation_id as its immediate cause', true];
    }
    return null;
  }

  #lifecycleError(event: Readonly<EventEnvelope>): Readonly<ContractErrorValue> | null {
    if (EVENT_RULES[event.event_type].lifecycle === false) return null;
    const initial = INITIAL_LIFECYCLE_STATES[event.stream_ref.kind];
    if (initial === undefined) return null;
    const objectKey = `${event.stream_ref.kind}:${event.stream_ref.id}`;
    const objectScope = this.#scopeByObject.get(objectKey);
    if (objectScope !== undefined && scopeKey(objectScope) !== scopeKey(event.scope)) {
      return contractError('PROTOCOL_VIOLATION', 'LIFECYCLE_SCOPE_MISMATCH', 'lifecycle identity cannot change scope');
    }
    const state = event.payload.state;
    if (typeof state !== 'string') {
      return contractError('PROTOCOL_VIOLATION', 'INVALID_LIFECYCLE_STATE', 'lifecycle event payload must contain a state');
    }
    const currentState = this.#lifecycleByObject.get(objectKey);
    if (currentState === undefined) {
      return state === initial && event.event_type !== 'task.retry_accepted'
        ? null
        : contractError('PROTOCOL_VIOLATION', 'INVALID_INITIAL_LIFECYCLE_STATE', `${event.stream_ref.kind} must begin at ${initial}`);
    }
    if (event.event_type === 'task.retry_accepted') {
      if (
        currentState !== 'terminal'
        || event.payload.previous_outcome !== this.#taskTerminalOutcomeByObject.get(objectKey)
        || event.payload.attempt_number !== (this.#taskAttemptNumberByObject.get(objectKey) ?? 1) + 1
      ) {
        return contractError(
          'PROTOCOL_VIOLATION',
          'TASK_RETRY_PRECONDITION_STALE',
          'task.retry_accepted does not continue the exact terminal epoch'
        );
      }
      return null;
    }
    try {
      validateTransition(event.stream_ref.kind as LifecycleKind, currentState, state, (event.payload.outcome ?? null) as TerminalOutcome | null);
    } catch (error: unknown) {
      if (error instanceof ContractViolation) {
        return contractError(
          'PROTOCOL_VIOLATION',
          error.error.reason ?? 'INVALID_LIFECYCLE_TRANSITION',
          error.error.message,
          false,
          event.correlation_id,
          error.error.details
        );
      }
      throw error;
    }
    return null;
  }

  #applyAndDrain(): string[] {
    const applied: string[] = [];
    let madeProgress = true;
    while (madeProgress) {
      madeProgress = false;
      for (const stream of this.#streams.values()) {
        if (stream.poisonedSeq.has(stream.nextSeq)) continue;
        const candidate = stream.quarantinedBySeq.get(stream.nextSeq);
        if (candidate === undefined) continue;
        const causalError = this.#causalBlock(candidate);
        if (causalError !== null) {
          if (causalError[2]) {
            stream.quarantinedBySeq.delete(stream.nextSeq);
            stream.poisonedSeq.add(stream.nextSeq);
            this.#results.set(
              candidate.event_id,
              this.#errorResult(PROJECTION_ERROR_REASONS.has(causalError[0]) ? 'rejected_projection' : 'rejected_causation', causalError[0], causalError[1])
            );
          }
          continue;
        }
        const lifecycleError = this.#lifecycleError(candidate);
        if (lifecycleError !== null) {
          stream.quarantinedBySeq.delete(stream.nextSeq);
          stream.poisonedSeq.add(stream.nextSeq);
          this.#results.set(candidate.event_id, applyResult('rejected_lifecycle', lifecycleError));
          continue;
        }
        stream.quarantinedBySeq.delete(stream.nextSeq);
        stream.appliedBySeq.set(stream.nextSeq, candidate);
        stream.nextSeq += 1;
        if (EVENT_RULES[candidate.event_type].lifecycle !== false && typeof candidate.payload.state === 'string') {
          const objectKey = `${candidate.stream_ref.kind}:${candidate.stream_ref.id}`;
          this.#lifecycleByObject.set(objectKey, candidate.payload.state);
          this.#scopeByObject.set(objectKey, candidate.scope);
          if (candidate.stream_ref.kind === 'task') {
            if (candidate.event_type === 'task.accepted') {
              this.#taskAttemptNumberByObject.set(objectKey, 1);
            } else if (candidate.event_type === 'task.retry_accepted') {
              const retryNumber = candidate.payload.attempt_number;
              if (typeof retryNumber !== 'number') {
                throw violation('TASK_RETRY_ATTEMPT_NUMBER_INVALID', 'applied task.retry_accepted lost its attempt number');
              }
              this.#taskAttemptNumberByObject.set(objectKey, retryNumber);
              this.#taskTerminalOutcomeByObject.delete(objectKey);
            } else if (candidate.event_type === 'task.terminal') {
              const taskOutcome = candidate.payload.outcome;
              if (typeof taskOutcome !== 'string') {
                throw violation('TASK_TERMINAL_OUTCOME_INVALID', 'applied task.terminal lost its outcome');
              }
              this.#taskTerminalOutcomeByObject.set(objectKey, taskOutcome);
            }
          }
          if (candidate.stream_ref.kind === 'round' || candidate.stream_ref.kind === 'task' || candidate.stream_ref.kind === 'attempt') {
            const sourceProgressKey = progressSourceKey(candidate);
            const queue = this.#progressSourceQueues.get(sourceProgressKey) ?? [];
            queue.push(candidate.event_id);
            this.#progressSourceQueues.set(sourceProgressKey, queue);
          }
        }
        if (EVENT_RULES[candidate.event_type].progress === true) {
          const progress = parseWorkProgressEventV2(candidate.payload, candidate.scope);
          const progressKey = canonicalJson([candidate.scope, progress.work_ref.kind, progress.work_ref.id]);
          this.#nextProgressSeq.set(progressKey, progress.seq + 1);
          const sourceEvent = this.#events.get(progress.source.event_id);
          const sourceQueue = sourceEvent === undefined ? undefined : this.#progressSourceQueues.get(progressSourceKey(sourceEvent));
          if (sourceQueue === undefined || sourceQueue.shift() !== progress.source.event_id) {
            throw violation('PROGRESS_SOURCE_ORDER_MISMATCH', 'applied WorkProgress lost its authoritative source position', 'PROTOCOL_VIOLATION');
          }
          this.#projectedSources.add(progress.source.event_id);
        }
        this.#appliedIds.add(candidate.event_id);
        this.#results.set(candidate.event_id, applyResult('applied', null, [candidate.event_id]));
        applied.push(candidate.event_id);
        madeProgress = true;
      }
    }
    return applied;
  }
}

export function classifyContract(value: unknown): 'v1' | 'v2' {
  const data = strictRecord(value, 'contract');
  if (data.contract_version === CONTRACT_VERSION) return 'v2';
  if (data.contract_version === V1_CONTRACT_VERSION) return 'v1';
  throw violation('UNSUPPORTED_CONTRACT_VERSION', 'payload is neither the v1 nor v2 contract', 'UNSUPPORTED');
}

export function parseV2Envelope(
  value: unknown,
  identities?: IdentityRegistry,
  commits?: TurnCommitLedger
): Readonly<CommandEnvelope | QueryEnvelope | ResultEnvelope | EventEnvelope> {
  const data = strictRecord(value, 'envelope');
  if (data.contract_version !== CONTRACT_VERSION) {
    throw violation('UNSUPPORTED_CONTRACT_VERSION', `expected ${CONTRACT_VERSION}`, 'UNSUPPORTED');
  }
  if (Object.prototype.hasOwnProperty.call(data, 'command_type')) {
    return parseCommandEnvelope(data, identities, commits);
  }
  if (Object.prototype.hasOwnProperty.call(data, 'query_type')) {
    return parseQueryEnvelope(data, identities);
  }
  if (Object.prototype.hasOwnProperty.call(data, 'event_type')) {
    return parseEventEnvelope(data, identities);
  }
  if (Object.prototype.hasOwnProperty.call(data, 'ok')) return parseResultEnvelope(data);
  throw violation('UNKNOWN_ENVELOPE_KIND', 'cannot identify v2 envelope kind');
}
