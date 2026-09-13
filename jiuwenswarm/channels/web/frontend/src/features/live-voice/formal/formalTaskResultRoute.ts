export const FORMAL_TASK_RESULT_METHOD = 'live_voice.task.result' as const;

export const FORMAL_TASK_RESULT_LIMITS = Object.freeze({
  max_identity_chars: 256,
  max_reason_chars: 256,
  max_result_chars: 32_768,
  max_result_utf8_bytes: 131_072,
  max_artifacts: 32,
  max_path_chars: 512,
  max_path_utf8_bytes: 2_048,
} as const);

export type FormalTaskResultAvailability = 'available' | 'not_ready' | 'unavailable';

export type FormalTaskResultArtifact = Readonly<{
  relative_path: string;
  sha256: string;
}>;

export type FormalTaskResultRecord = Readonly<{
  task_id: string;
  attempt_id: string;
  source_event_id: string;
  result_text: string;
  artifacts: readonly FormalTaskResultArtifact[];
  completed_at: string;
}>;

export type FormalTaskResultReceipt = Readonly<{
  task_id: string;
  availability: FormalTaskResultAvailability;
  reason: string;
  task_result: FormalTaskResultRecord | null;
  retryable: boolean;
}>;

export type FormalTaskResultRequest = (
  method: typeof FORMAL_TASK_RESULT_METHOD,
  params: Readonly<Record<string, unknown>>,
  requestId: string,
) => Promise<unknown>;

export type FormalTaskResultOwnerSnapshot = Readonly<{
  status: 'disabled' | 'idle' | 'reading' | 'available' | 'not_ready' | 'unavailable' | 'failed' | 'closed';
  task_id: string | null;
  receipt: FormalTaskResultReceipt | null;
  reason: string | null;
}>;

type ReadInput = Readonly<{
  auth_token: unknown;
  session_id: string;
  task_id: string;
}>;

type JsonObject = Record<string, unknown>;

const HEX_64 = /^[0-9a-f]{64}$/;
const ISO_UTC = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?Z$/;
let fallbackSequence = 0;

function objectValue(value: unknown): JsonObject | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function exactKeys(value: JsonObject, expected: readonly string[], field: string): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new Error(`${field} schema is invalid`);
  }
}

function boundedText(value: unknown, field: string, maximum: number): string {
  if (typeof value !== 'string' || !value.trim() || value.includes('\0')) {
    throw new Error(`${field} is invalid`);
  }
  let scalars = 0;
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) throw new Error(`${field} is invalid`);
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new Error(`${field} is invalid`);
    }
    scalars += 1;
    if (scalars > maximum) throw new Error(`${field} is invalid`);
  }
  return value;
}

function identity(value: unknown, field: string): string {
  return boundedText(value, field, FORMAL_TASK_RESULT_LIMITS.max_identity_chars);
}

function isExactUtcTimestamp(value: string): boolean {
  const match = ISO_UTC.exec(value);
  if (match === null) return false;
  const [year, month, day, hour, minute, second] = match
    .slice(1)
    .map(component => Number(component));
  if (
    year < 1
    || month < 1
    || month > 12
    || hour > 23
    || minute > 59
    || second > 59
  ) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}

function artifact(value: unknown): FormalTaskResultArtifact {
  const raw = objectValue(value);
  if (raw === null) throw new Error('task result artifact is invalid');
  exactKeys(raw, ['relative_path', 'sha256'], 'task result artifact');
  const relativePath = boundedText(
    raw.relative_path,
    'task result artifact path',
    FORMAL_TASK_RESULT_LIMITS.max_path_chars,
  );
  const firstPart = relativePath.split('/', 1)[0];
  if (
    new TextEncoder().encode(relativePath).byteLength > FORMAL_TASK_RESULT_LIMITS.max_path_utf8_bytes
    || relativePath.includes('\\')
    || relativePath.startsWith('/')
    || relativePath.startsWith('./')
    || relativePath.split('/').some(part => part === '' || part === '.' || part === '..')
    || firstPart.includes(':')
  ) {
    throw new Error('task result artifact path is invalid');
  }
  if (typeof raw.sha256 !== 'string' || !HEX_64.test(raw.sha256)) {
    throw new Error('task result artifact digest is invalid');
  }
  return Object.freeze({ relative_path: relativePath, sha256: raw.sha256 });
}

function resultRecord(value: unknown, expectedTaskId: string): FormalTaskResultRecord {
  const raw = objectValue(value);
  if (raw === null) throw new Error('available task result is missing');
  exactKeys(
    raw,
    ['artifacts', 'attempt_id', 'completed_at', 'result_text', 'source_event_id', 'task_id'],
    'task result',
  );
  const taskId = identity(raw.task_id, 'task result task_id');
  if (taskId !== expectedTaskId) throw new Error('task result target mismatch');
  const resultText = boundedText(
    raw.result_text,
    'task result text',
    FORMAL_TASK_RESULT_LIMITS.max_result_chars,
  );
  if (new TextEncoder().encode(resultText).byteLength > FORMAL_TASK_RESULT_LIMITS.max_result_utf8_bytes) {
    throw new Error('task result text is oversized');
  }
  if (
    !Array.isArray(raw.artifacts)
    || raw.artifacts.length === 0
    || raw.artifacts.length > FORMAL_TASK_RESULT_LIMITS.max_artifacts
  ) {
    throw new Error('task result artifacts are invalid');
  }
  const artifacts = Object.freeze(raw.artifacts.map(artifact));
  if (new Set(artifacts.map(item => item.relative_path)).size !== artifacts.length) {
    throw new Error('task result artifacts are duplicated');
  }
  const completedAt = boundedText(raw.completed_at, 'task result completed_at', 64);
  if (!isExactUtcTimestamp(completedAt)) {
    throw new Error('task result completed_at is invalid');
  }
  return Object.freeze({
    task_id: taskId,
    attempt_id: identity(raw.attempt_id, 'task result attempt_id'),
    source_event_id: identity(raw.source_event_id, 'task result source_event_id'),
    result_text: resultText,
    artifacts,
    completed_at: completedAt,
  });
}

export function parseFormalTaskResultResponse(
  value: unknown,
  expectedRequestId: string,
  expectedTaskId: string,
): FormalTaskResultReceipt {
  const envelope = objectValue(value);
  if (envelope === null) throw new Error('task result response is invalid');
  const envelopeKeys = Object.keys(envelope).sort().join(',');
  if (
    envelopeKeys !== 'error,ok,request_id,result'
    && envelopeKeys !== 'error,ok,product_composition,request_id,result'
  ) {
    throw new Error('task result response schema is invalid');
  }
  if (envelope.request_id !== expectedRequestId || envelope.ok !== true || envelope.error !== null) {
    throw new Error('task result response was rejected or mismatched');
  }
  const result = objectValue(envelope.result);
  if (result === null) throw new Error('task result response body is invalid');
  exactKeys(result, ['availability', 'reason', 'task_id', 'task_result'], 'task result response body');
  const taskId = identity(result.task_id, 'task result response task_id');
  if (taskId !== expectedTaskId) throw new Error('task result response target mismatch');
  const availability = result.availability;
  if (availability !== 'available' && availability !== 'not_ready' && availability !== 'unavailable') {
    throw new Error('task result availability is invalid');
  }
  const reason = boundedText(
    result.reason,
    'task result reason',
    FORMAL_TASK_RESULT_LIMITS.max_reason_chars,
  );
  const record = availability === 'available'
    ? resultRecord(result.task_result, taskId)
    : null;
  if (availability !== 'available' && result.task_result !== null) {
    throw new Error('non-available task result must not expose content');
  }
  return Object.freeze({
    task_id: taskId,
    availability,
    reason,
    task_result: record,
    retryable: availability === 'not_ready',
  });
}

export class ProductFormalTaskResultOwner {
  private readonly enabled: boolean;
  private readonly request: FormalTaskResultRequest;
  private readonly requestId: () => string;
  private state: FormalTaskResultOwnerSnapshot;
  private pending = false;
  private generation = 0;

  constructor(options: Readonly<{
    enabled: boolean;
    request: FormalTaskResultRequest;
    request_id?: () => string;
  }>) {
    this.enabled = options.enabled;
    this.request = options.request;
    this.requestId = options.request_id ?? (() => `live-voice-task-result-${Date.now()}-${++fallbackSequence}`);
    this.state = Object.freeze({
      status: this.enabled ? 'idle' : 'disabled',
      task_id: null,
      receipt: null,
      reason: this.enabled ? null : 'TASK_RESULT_DISABLED',
    });
  }

  snapshot(): FormalTaskResultOwnerSnapshot {
    return this.state;
  }

  async read(input: ReadInput): Promise<FormalTaskResultReceipt> {
    if (!this.enabled) throw new Error('formal task result owner is disabled');
    if (this.state.status === 'closed') throw new Error('formal task result owner is closed');
    if (this.pending) throw new Error('formal task result read is already in progress');
    const sessionId = identity(input.session_id, 'task result session_id');
    const taskId = identity(input.task_id, 'task result task_id');
    const requestId = identity(this.requestId(), 'task result request_id');
    const generation = ++this.generation;
    this.pending = true;
    this.state = Object.freeze({ status: 'reading', task_id: taskId, receipt: null, reason: null });
    try {
      const response = await this.request(
        FORMAL_TASK_RESULT_METHOD,
        Object.freeze({ auth_token: input.auth_token, session_id: sessionId, task_id: taskId }),
        requestId,
      );
      if (generation !== this.generation || this.state.status === 'closed') {
        throw new Error('formal task result owner is closed');
      }
      const receipt = parseFormalTaskResultResponse(response, requestId, taskId);
      this.state = Object.freeze({
        status: receipt.availability,
        task_id: taskId,
        receipt,
        reason: receipt.reason,
      });
      return receipt;
    } catch (error) {
      if (generation !== this.generation || this.state.status === 'closed') {
        throw error;
      }
      this.state = Object.freeze({
        status: 'failed',
        task_id: taskId,
        receipt: null,
        reason: error instanceof Error ? error.message : 'TASK_RESULT_READ_FAILED',
      });
      throw error;
    } finally {
      if (generation === this.generation) this.pending = false;
    }
  }

  close(): FormalTaskResultOwnerSnapshot {
    this.generation += 1;
    this.pending = false;
    this.state = Object.freeze({ status: 'closed', task_id: null, receipt: null, reason: 'OWNER_CLOSED' });
    return this.state;
  }
}
