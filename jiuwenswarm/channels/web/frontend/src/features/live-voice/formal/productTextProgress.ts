export const PRODUCT_TEXT_PROGRESS_EVENT = 'live_voice.task.progress' as const;

type JsonObject = Readonly<Record<string, unknown>>;

export interface ProductTextProgressScope {
  readonly subject_id: string;
  readonly project_id: string;
  readonly session_id: string;
  readonly assurance: 'authenticated';
}

export interface ProductTextProgressEnvelope {
  readonly event_id: string;
  readonly event_type: string;
  readonly seq: number;
  readonly correlation_id: string;
  readonly causation_id: string | null;
  readonly stream_ref: Readonly<{ kind: string; id: string }>;
  readonly scope: ProductTextProgressScope;
  readonly payload: JsonObject;
  readonly raw: JsonObject;
}

export interface ProductTextProgressEvent {
  readonly event_type: typeof PRODUCT_TEXT_PROGRESS_EVENT;
  readonly session_id: string;
  readonly task_id: string;
  readonly project_id: string;
  readonly correlation_id: string;
  readonly origin_id: string;
  readonly generation_kind: string;
  readonly generation_id: string;
  readonly generation: number;
  readonly source_event: ProductTextProgressEnvelope;
  readonly progress_event: ProductTextProgressEnvelope;
  readonly evidence_id: string;
  readonly state: string;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function uintValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function parseScope(value: unknown): ProductTextProgressScope | null {
  const raw = objectValue(value);
  if (!raw) return null;
  const keys = Object.keys(raw).sort();
  if (
    keys.length !== 4 ||
    keys[0] !== 'assurance' ||
    keys[1] !== 'project_id' ||
    keys[2] !== 'session_id' ||
    keys[3] !== 'subject_id'
  ) {
    return null;
  }
  const subjectId = textValue(raw.subject_id);
  const projectId = textValue(raw.project_id);
  const sessionId = textValue(raw.session_id);
  if (!subjectId || !projectId || !sessionId || raw.assurance !== 'authenticated') {
    return null;
  }
  return Object.freeze({
    subject_id: subjectId,
    project_id: projectId,
    session_id: sessionId,
    assurance: 'authenticated',
  });
}

function sameScope(left: ProductTextProgressScope, right: ProductTextProgressScope): boolean {
  return (
    left.subject_id === right.subject_id &&
    left.project_id === right.project_id &&
    left.session_id === right.session_id &&
    left.assurance === right.assurance
  );
}

function parseEnvelope(value: unknown): ProductTextProgressEnvelope | null {
  const raw = objectValue(value);
  if (!raw) return null;
  const eventId = textValue(raw.event_id);
  const eventType = textValue(raw.event_type);
  const seq = uintValue(raw.seq);
  const correlationId = textValue(raw.correlation_id);
  const causationId = raw.causation_id === null ? null : textValue(raw.causation_id);
  const streamRef = objectValue(raw.stream_ref);
  const streamKind = textValue(streamRef?.kind);
  const streamId = textValue(streamRef?.id);
  const scope = parseScope(raw.scope);
  const payload = objectValue(raw.payload);
  if (
    !eventId ||
    !eventType ||
    seq === null ||
    !correlationId ||
    (raw.causation_id !== null && !causationId) ||
    !streamKind ||
    !streamId ||
    !scope ||
    !payload
  ) {
    return null;
  }
  return Object.freeze({
    event_id: eventId,
    event_type: eventType,
    seq,
    correlation_id: correlationId,
    causation_id: causationId,
    stream_ref: Object.freeze({ kind: streamKind, id: streamId }),
    scope,
    payload: Object.freeze({ ...payload }),
    raw: Object.freeze({ ...raw }),
  });
}

export function parseProductTextProgressEvent(
  value: unknown
): ProductTextProgressEvent | null {
  const raw = objectValue(value);
  if (!raw || raw.event_type !== PRODUCT_TEXT_PROGRESS_EVENT) return null;
  const sessionId = textValue(raw.session_id);
  const taskId = textValue(raw.task_id);
  const projectId = textValue(raw.project_id);
  const correlationId = textValue(raw.correlation_id);
  const originId = textValue(raw.origin_id);
  const generationKind = textValue(raw.generation_kind);
  const generationId = textValue(raw.generation_id);
  const generation = uintValue(raw.generation);
  const evidenceId = textValue(raw.evidence_id);
  const sourceEvent = parseEnvelope(raw.source_event);
  const progressEvent = parseEnvelope(raw.progress_event);
  const progressPayload = progressEvent?.payload;
  const workRef = objectValue(progressPayload?.work_ref);
  const state = textValue(progressPayload?.state);
  const payloadSeq = uintValue(progressPayload?.seq);
  if (
    !sessionId ||
    !taskId ||
    !projectId ||
    !correlationId ||
    !originId ||
    generationKind !== 'web_task_progress_generation' ||
    !generationId ||
    generation === null ||
    generation === 0 ||
    !evidenceId ||
    !sourceEvent ||
    !progressEvent ||
    !state ||
    payloadSeq === null ||
    sourceEvent.stream_ref.kind !== 'task' ||
    sourceEvent.stream_ref.id !== taskId ||
    progressEvent.stream_ref.kind !== 'task' ||
    progressEvent.stream_ref.id !== taskId ||
    sourceEvent.correlation_id !== correlationId ||
    progressEvent.correlation_id !== correlationId ||
    sourceEvent.seq !== progressEvent.seq ||
    payloadSeq !== sourceEvent.seq ||
    progressEvent.event_type !== 'work.progress' ||
    progressEvent.causation_id !== sourceEvent.event_id ||
    workRef?.kind !== 'task' ||
    workRef.id !== taskId ||
    sourceEvent.scope.session_id !== sessionId ||
    sourceEvent.scope.project_id !== projectId ||
    progressEvent.scope.session_id !== sessionId ||
    progressEvent.scope.project_id !== projectId ||
    !sameScope(sourceEvent.scope, progressEvent.scope)
  ) {
    return null;
  }
  return Object.freeze({
    event_type: PRODUCT_TEXT_PROGRESS_EVENT,
    session_id: sessionId,
    task_id: taskId,
    project_id: projectId,
    correlation_id: correlationId,
    origin_id: originId,
    generation_kind: generationKind,
    generation_id: generationId,
    generation,
    source_event: sourceEvent,
    progress_event: progressEvent,
    evidence_id: evidenceId,
    state,
  });
}

export function adoptProductTextProgressEvent(
  current: Readonly<ProductTextProgressEvent> | null,
  value: unknown,
  activeSessionId: string | null
): Readonly<ProductTextProgressEvent> | null {
  const incoming = parseProductTextProgressEvent(value);
  if (!incoming || !activeSessionId || incoming.session_id !== activeSessionId) {
    return current;
  }
  if (
    current === null
  ) {
    return incoming;
  }
  const sameLineage =
    current.session_id === incoming.session_id &&
    current.project_id === incoming.project_id &&
    current.task_id === incoming.task_id &&
    current.origin_id === incoming.origin_id &&
    current.generation_kind === incoming.generation_kind &&
    current.generation_id === incoming.generation_id &&
    sameScope(current.source_event.scope, incoming.source_event.scope);
  if (!sameLineage) return current;
  if (
    incoming.generation < current.generation ||
    (incoming.generation === current.generation &&
      (incoming.correlation_id !== current.correlation_id ||
        incoming.source_event.seq <= current.source_event.seq))
  ) {
    return current;
  }
  return incoming;
}
