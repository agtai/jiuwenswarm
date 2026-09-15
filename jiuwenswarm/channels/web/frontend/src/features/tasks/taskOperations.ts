// Shared task retry and authoritative progress reconciliation; no audio owner.
import { FormalTaskControlLeaf, isFormalTaskRetryEligible, type FormalTaskControlRecord, type FormalTaskState } from './formalTaskControlLeaf.js';
import type { ProductTextProgressEvent } from './productTextProgress';
import type { WebRequestOptions } from '../../types';
type ProductWebRequest = (method: string, params?: Record<string, unknown>, options?: WebRequestOptions) => Promise<unknown>;
const PRODUCT_P3_TASK_EVENTS_METHOD = 'live_voice.task.events';
export const PRODUCT_P3_PROGRESS_EXHAUSTED_CAPACITY = 128;
export const PRODUCT_P3_PROGRESS_RECONCILIATION_RETRY_MS = 250;
export const PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS = 4;

export function productP3ProgressReconciliationRetryDelayMs(failures: number): number | null {
  if (!Number.isSafeInteger(failures) || failures <= 0 || failures >= PRODUCT_P3_PROGRESS_RECONCILIATION_MAX_ATTEMPTS) return null;
  return Math.min(PRODUCT_P3_PROGRESS_RECONCILIATION_RETRY_MS * 2 ** (failures - 1), 2_000);
}


export function rememberProductP3ProgressExhaustion(exhausted: Map<string, true>, deliveryId: string): void {
  if (exhausted.has(deliveryId)) return;
  while (exhausted.size >= PRODUCT_P3_PROGRESS_EXHAUSTED_CAPACITY) {
    const oldest = exhausted.keys().next().value;
    if (typeof oldest !== 'string') break;
    exhausted.delete(oldest);
  }
  exhausted.set(deliveryId, true);
}

export function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function hasExactFields(value: Readonly<Record<string, unknown>>, fields: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  return actual.length === expected.length && actual.every((field, index) => field === expected[index]);
}

export const PRODUCT_P3_RETRY_INSPECTION_FAILED_REASON = 'PRODUCT_P3_RETRY_INSPECTION_FAILED';

export const PRODUCT_P3_STABLE_REASON_PATTERN = /^[A-Z][A-Z0-9_]{0,127}$/;


export type ProductP3RetryAdmission = Readonly<{
  eligible: boolean;
  reason: string;
  task_id: string;
  attempt_id: string | null;
  attempt_number: number | null;
}>;


export type ProductP3RetryInspection = Readonly<{
  record: Readonly<FormalTaskControlRecord>;
  admission: ProductP3RetryAdmission;
}>;


export function parseProductP3RetryAdmission(response: unknown, record: Readonly<FormalTaskControlRecord>): ProductP3RetryAdmission {
  const envelope = recordValue(response);
  const result = recordValue(envelope?.result);
  const raw = recordValue(result?.retry_admission);
  if (
    envelope?.ok !== true ||
    raw === null ||
    Object.keys(raw).sort().join(',') !== 'attempt_id,attempt_number,eligible,reason,task_id' ||
    typeof raw.eligible !== 'boolean' ||
    typeof raw.reason !== 'string' ||
    !PRODUCT_P3_STABLE_REASON_PATTERN.test(raw.reason) ||
    raw.task_id !== record.task_id
  ) {
    throw new Error('formal task retry admission is missing or malformed');
  }
  if (raw.eligible) {
    if (
      raw.reason !== 'TASK_RETRY_ELIGIBLE' ||
      typeof raw.attempt_id !== 'string' ||
      raw.attempt_id !== record.attempt_id ||
      !Number.isSafeInteger(raw.attempt_number) ||
      raw.attempt_number !== (record.attempt_number ?? -1) + 1 ||
      !isFormalTaskRetryEligible(record)
    ) {
      throw new Error('formal task retry admission does not bind the exact current attempt');
    }
  } else if (raw.attempt_id !== null || raw.attempt_number !== null) {
    throw new Error('formal task retry rejection carries ambiguous attempt authority');
  }
  return Object.freeze({
    eligible: raw.eligible,
    reason: raw.reason,
    task_id: raw.task_id as string,
    attempt_id: raw.attempt_id as string | null,
    attempt_number: raw.attempt_number as number | null,
  });
}


export type ProductP3TerminalStatus = 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown';


export type ProductP3MutationStatus = 'idle' | 'issuing' | 'confirmed' | 'mutating' | 'accepted' | ProductP3TerminalStatus;

export const PRODUCT_P3_TERMINAL_STATUSES = Object.freeze(['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const);

export const PRODUCT_P3_PROGRESS_EVENT_TYPES: Readonly<Record<FormalTaskState, readonly string[]>> = Object.freeze({
  accepted: Object.freeze(['task.accepted', 'task.retry_accepted']),
  running: Object.freeze(['task.running']),
  blocked: Object.freeze(['task.blocked']),
  decision_required: Object.freeze(['task.decision_required']),
  terminal: Object.freeze(['task.terminal']),
});

export function productP3ProgressState(value: unknown): FormalTaskState {
  if (!(['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const).includes(value as FormalTaskState)) {
    throw new Error('product P3 progress state is outside the formal lifecycle');
  }
  return value as FormalTaskState;
}

export function productP3ProgressOutcome(value: unknown): ProductP3TerminalStatus | null {
  if (value === null || value === undefined) return null;
  if (!PRODUCT_P3_TERMINAL_STATUSES.includes(value as ProductP3TerminalStatus)) {
    throw new Error('product P3 progress outcome is outside the formal lifecycle');
  }
  return value as ProductP3TerminalStatus;
}


export function productP3TerminalStatus(record: Readonly<FormalTaskControlRecord>): ProductP3TerminalStatus | null {
  if (record.state !== 'terminal') return null;
  return productP3ProgressOutcome(record.outcome);
}

export const PRODUCT_P3_PROGRESS_QUARANTINABLE_FAILURES = new Set([
  'formal product progress does not own the exact Session/task/attempt binding',
  'product P3 progress state is outside the formal lifecycle',
  'product P3 progress outcome is outside the formal lifecycle',
  'formal product progress source, state, outcome, or producer mismatch',
  'formal product progress task.events response is malformed',
  'formal product progress conflicts with authoritative task.events truth',
  'formal product progress conflicts with authoritative task.events head',
  'formal product progress lost its exact authoritative revision',
]);


export function productP3ProgressFailureIsQuarantinable(error: unknown): boolean {
  return error instanceof Error && PRODUCT_P3_PROGRESS_QUARANTINABLE_FAILURES.has(error.message);
}


/**
 * Rebuild the exact origin task from durable task.events before acknowledging
 * or displaying a product progress delivery.  The isolated probe prevents a
 * malformed response from partially updating the live replica.  Session,
 * connection, task, and attempt ownership are rechecked after the network
 * boundary so a predecessor or late response cannot update the current UI.
 */
export async function reconcileProductP3ProgressEvent(
  input: Readonly<{
    request: ProductWebRequest;
    leaf: FormalTaskControlLeaf;
    event: Readonly<ProductTextProgressEvent>;
    session_id: string;
    request_nonce: string;
    is_current: () => boolean;
    before_adopt?: (record: Readonly<FormalTaskControlRecord>) => void;
  }>,
): Promise<Readonly<FormalTaskControlRecord>> {
  const { event } = input;
  if (!input.session_id || !input.request_nonce || !input.is_current()) {
    throw new Error('formal product progress reconciliation is stale or incomplete');
  }
  const initialSnapshot = input.leaf.snapshot();
  const initialRecord = initialSnapshot.tasks.find(task => task.task_id === event.task_id) ?? null;
  if (
    !initialSnapshot.connected ||
    initialSnapshot.binding.session_id !== input.session_id ||
    event.session_id !== input.session_id ||
    event.project_id !== initialSnapshot.binding.project_id ||
    event.correlation_id !== initialSnapshot.binding.correlation_id ||
    initialRecord === null ||
    initialRecord.attempt_id !== event.attempt_id
  ) {
    throw new Error('formal product progress does not own the exact Session/task/attempt binding');
  }

  const state = productP3ProgressState(event.state);
  const sourceState = productP3ProgressState(event.source_event.payload.state);
  const progressState = productP3ProgressState(event.progress_event.payload.state);
  const sourceOutcome = productP3ProgressOutcome(event.source_event.payload.outcome);
  const progressOutcome = productP3ProgressOutcome(event.progress_event.payload.outcome);
  const expectedEventTypes = PRODUCT_P3_PROGRESS_EVENT_TYPES[state];
  const sourceExtensions = recordValue(event.source_event.raw.extensions);
  const progressReturn = recordValue(sourceExtensions?.['jiuwenswarm.task_progress_return']);
  const persistentProducer = progressReturn?.persistent_event_producer;
  const producerMatches =
    state === 'terminal'
      ? ['task_core', 'task_core.delivery', 'task_core.reconciliation'].includes(String(persistentProducer))
      : persistentProducer === 'task_core';
  if (
    state !== sourceState ||
    state !== progressState ||
    !expectedEventTypes.includes(event.source_event.event_type) ||
    !producerMatches ||
    sourceOutcome !== progressOutcome ||
    (state === 'terminal') !== (progressOutcome !== null)
  ) {
    throw new Error('formal product progress source, state, outcome, or producer mismatch');
  }

  const ownedConnectionGeneration = initialSnapshot.connection_generation;
  const expectedAttemptId = event.attempt_id;
  const stillCurrent = () => {
    if (!input.is_current()) return false;
    const snapshot = input.leaf.snapshot();
    const record = snapshot.tasks.find(task => task.task_id === event.task_id) ?? null;
    return (
      snapshot.connected &&
      snapshot.connection_generation === ownedConnectionGeneration &&
      snapshot.binding.session_id === input.session_id &&
      record?.attempt_id === expectedAttemptId
    );
  };
  const eventsResponse = await input.request(
    PRODUCT_P3_TASK_EVENTS_METHOD,
    { session_id: input.session_id, task_id: event.task_id, after_seq: -1 },
    { requestId: `web-task-progress-events-${input.request_nonce}` },
  );
  if (!stillCurrent()) throw new Error('formal product progress reconciliation became stale');

  const responseBody = recordValue(eventsResponse);
  const responseResult = recordValue(responseBody?.result);
  const responseEvents = Array.isArray(responseResult?.events) ? responseResult.events : null;
  if (responseBody === null || responseResult === null || responseEvents === null) {
    throw new Error('formal product progress task.events response is malformed');
  }
  const evidenceEvents = responseEvents.filter(candidate => {
    const raw = recordValue(candidate);
    return typeof raw?.seq === 'number' && Number.isSafeInteger(raw.seq) && raw.seq <= event.source_event.seq;
  });
  const evidenceResponse = Object.freeze({
    ...responseBody,
    result: Object.freeze({
      ...responseResult,
      head_seq: event.source_event.seq,
      events: Object.freeze(evidenceEvents),
    }),
  });
  const evidenceProbe = new FormalTaskControlLeaf({ enabled: true, binding: initialSnapshot.binding, event_capacity: input.leaf.eventCapacity });
  evidenceProbe.adopt('task.events', evidenceResponse, {
    connection_generation: evidenceProbe.snapshot().connection_generation,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: event.task_id, after_seq: -1 },
  });
  const evidence = evidenceProbe.snapshot().tasks.find(task => task.task_id === event.task_id) ?? null;
  if (
    evidence === null ||
    evidence.attempt_id !== expectedAttemptId ||
    evidence.last_event_id !== event.source_event.event_id ||
    evidence.last_event_seq !== event.source_event.seq ||
    evidence.state !== state ||
    evidence.outcome !== progressOutcome
  ) {
    throw new Error('formal product progress conflicts with authoritative task.events truth');
  }

  const headProbe = new FormalTaskControlLeaf({ enabled: true, binding: initialSnapshot.binding, event_capacity: input.leaf.eventCapacity });
  headProbe.adopt('task.events', eventsResponse, {
    connection_generation: headProbe.snapshot().connection_generation,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: event.task_id, after_seq: -1 },
  });
  const selected = headProbe.snapshot().tasks.find(task => task.task_id === event.task_id) ?? null;
  const selectedLastEventSeq = selected?.last_event_seq ?? null;
  if (
    selected === null ||
    selected.attempt_id !== expectedAttemptId ||
    selectedLastEventSeq === null ||
    selectedLastEventSeq < event.source_event.seq
  ) {
    throw new Error('formal product progress conflicts with authoritative task.events head');
  }
  if (!stillCurrent()) throw new Error('formal product progress reconciliation became stale');
  input.before_adopt?.(selected);
  if (!stillCurrent()) throw new Error('formal product progress reconciliation became stale');

  // Receipt rejection must happen before committing history to the shared
  // Task facts. No asynchronous boundary separates this check and both adopts.
  const progressOrigin = {
    task_id: event.task_id, correlation_id: event.correlation_id,
    source_event_id: event.source_event.event_id, source_event_seq: event.source_event.seq,
    progress_event_id: event.progress_event.event_id, progress_causation_id: event.progress_event.causation_id ?? '',
    state, outcome: progressOutcome,
  };
  if (selectedLastEventSeq === event.source_event.seq) {
    headProbe.adoptProgress(progressOrigin, headProbe.snapshot().connection_generation);
    input.leaf.assertProgressReceiptAvailable(event.progress_event.event_id, event.source_event.event_id);
  }

  input.leaf.adopt('task.events', eventsResponse, {
    connection_generation: ownedConnectionGeneration,
    command_id: null,
    target_task_id: null,
    events_query: { task_id: event.task_id, after_seq: -1 },
  });
  if (selectedLastEventSeq === event.source_event.seq) {
    input.leaf.adoptProgress(progressOrigin, ownedConnectionGeneration);
  }
  const adopted = input.leaf.snapshot().tasks.find(task => task.task_id === event.task_id) ?? null;
  if (
    !stillCurrent() ||
    adopted === null ||
    adopted.attempt_id !== selected.attempt_id ||
    adopted.last_event_id !== selected.last_event_id ||
    adopted.last_event_seq !== selected.last_event_seq ||
    adopted.state !== selected.state ||
    adopted.outcome !== selected.outcome
  ) {
    throw new Error('formal product progress lost its exact authoritative revision');
  }
  return adopted;
}
