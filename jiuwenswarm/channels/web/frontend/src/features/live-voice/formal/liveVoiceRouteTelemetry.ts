export const ROUTE_CLASSES = Object.freeze(['formal', 'fallback', 'demo_substitute', 'unsupported', 'unknown'] as const);
export type RouteImplementationClass = (typeof ROUTE_CLASSES)[number];

export const CONTRACT_VERSION = 'live-voice.contract.v2' as const;

export interface RouteTelemetryInput {
  segment_id: string;
  implementation_class: string;
  owner_module?: string | null;
  capability_provider?: string | null;
  contract_version?: string | null;
  correlation_id: string;
  observed_at: string;
  safe_reason?: string | null;
}

export interface RouteTelemetryRecord {
  readonly segment_id: string;
  readonly implementation_class: RouteImplementationClass;
  readonly owner_module: string | null;
  readonly capability_provider: string | null;
  readonly contract_version: string | null;
  readonly correlation_id: string;
  readonly observed_at: string;
  readonly safe_reason: string | null;
}

export interface RouteTelemetryLedger {
  readonly enabled: boolean;
  add(record: RouteTelemetryRecord | RouteTelemetryInput): boolean;
  list(): readonly RouteTelemetryRecord[];
  queryBySegment(segmentId: string): readonly RouteTelemetryRecord[];
  size(): number;
}

export class RouteTelemetryViolation extends Error {
  readonly reason: string;

  constructor(reason: string, message: string) {
    super(message);
    this.name = 'RouteTelemetryViolation';
    this.reason = reason;
  }
}

function violation(reason: string, message: string): RouteTelemetryViolation {
  return new RouteTelemetryViolation(reason, message);
}

function validUnicode(value: string, fieldName: string): string {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (Number.isNaN(next) || next < 0xdc00 || next > 0xdfff) {
        throw violation('INVALID_UNICODE_SCALAR', `${fieldName} contains an unpaired surrogate`);
      }
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      throw violation('INVALID_UNICODE_SCALAR', `${fieldName} contains an unpaired surrogate`);
    }
  }
  return value;
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

function requiredText(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw violation('INVALID_REQUIRED_TEXT', `${fieldName} must be a non-empty string`);
  }
  return validUnicode(value, fieldName);
}

function optionalText(value: unknown, fieldName: string): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== 'string') {
    throw violation('INVALID_TEXT_TYPE', `${fieldName} must be a string or null`);
  }
  if (value.trim().length === 0) {
    return null;
  }
  return validUnicode(value, fieldName);
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

const INPUT_KEYS = [
  'segment_id',
  'implementation_class',
  'owner_module',
  'capability_provider',
  'contract_version',
  'correlation_id',
  'observed_at',
  'safe_reason',
] as const;

const REQUIRED_INPUT_KEYS = ['segment_id', 'implementation_class', 'correlation_id', 'observed_at'] as const;

function exactAllowedKeys(record: Record<string, unknown>, fieldName: string): void {
  for (const key of Object.keys(record)) {
    if (!INPUT_KEYS.includes(key as (typeof INPUT_KEYS)[number])) {
      throw violation('UNKNOWN_FIELD', `${fieldName} has unknown fields: ${key}`);
    }
  }
  for (const key of REQUIRED_INPUT_KEYS) {
    if (!(key in record)) {
      throw violation('MISSING_REQUIRED_FIELD', `${fieldName} is missing: ${key}`);
    }
  }
}

export function createRouteTelemetryRecord(input: RouteTelemetryInput): RouteTelemetryRecord {
  const data = strictRecord(input, 'route_telemetry');
  exactAllowedKeys(data, 'route_telemetry');

  const segmentId = requiredText(data.segment_id, 'segment_id');
  const implementationClass = data.implementation_class;
  if (typeof implementationClass !== 'string' || !ROUTE_CLASSES.includes(implementationClass as RouteImplementationClass)) {
    throw violation('INVALID_ROUTE_CLASS', `implementation_class must be one of: ${ROUTE_CLASSES.join(', ')}`);
  }
  let routeClass = implementationClass as RouteImplementationClass;
  const correlationId = requiredText(data.correlation_id, 'correlation_id');
  const observedAt = timestamp(data.observed_at, 'observed_at');
  const ownerModule = optionalText(data.owner_module, 'owner_module');
  const capabilityProvider = optionalText(data.capability_provider, 'capability_provider');
  const contractVersion = optionalText(data.contract_version, 'contract_version');
  let safeReason = optionalText(data.safe_reason, 'safe_reason');

  if (routeClass === 'formal') {
    if (safeReason !== null) {
      throw violation('FORMAL_REASON_FORBIDDEN', 'a formal route must not carry a safe_reason');
    }
    if (ownerModule === null || capabilityProvider === null || contractVersion !== CONTRACT_VERSION) {
      routeClass = 'unknown';
      safeReason = 'MISSING_FORMAL_PROVENANCE';
    }
  } else if (ownerModule === null) {
    routeClass = 'unknown';
    if (safeReason === null) {
      safeReason = 'MISSING_OWNER_MODULE';
    }
  }
  if (routeClass !== 'formal' && safeReason === null) {
    throw violation('NON_FORMAL_REASON_REQUIRED', 'a non-formal route requires a safe_reason');
  }

  return Object.freeze({
    segment_id: segmentId,
    implementation_class: routeClass,
    owner_module: ownerModule,
    capability_provider: capabilityProvider,
    contract_version: contractVersion,
    correlation_id: correlationId,
    observed_at: observedAt,
    safe_reason: safeReason,
  });
}

export function createRouteTelemetryLedger(options: { enabled?: boolean } = {}): RouteTelemetryLedger {
  const enabled = options.enabled ?? true;
  if (typeof enabled !== 'boolean') {
    throw violation('INVALID_BOOLEAN', 'enabled must be a boolean');
  }
  if (!enabled) {
    return {
      enabled: false,
      add: () => false,
      list: () => [],
      queryBySegment: () => [],
      size: () => 0,
    };
  }

  const records: RouteTelemetryRecord[] = [];
  return {
    enabled: true,
    add(record: RouteTelemetryRecord | RouteTelemetryInput): boolean {
      records.push(createRouteTelemetryRecord(record));
      return true;
    },
    list(): readonly RouteTelemetryRecord[] {
      return records.slice();
    },
    queryBySegment(segmentId: string): readonly RouteTelemetryRecord[] {
      return records.filter(record => record.segment_id === segmentId);
    },
    size(): number {
      return records.length;
    },
  };
}
