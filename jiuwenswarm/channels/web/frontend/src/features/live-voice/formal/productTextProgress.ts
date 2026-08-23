export const PRODUCT_TEXT_PROGRESS_EVENT = 'live_voice.task.progress' as const;
export const PRODUCT_PROGRESS_ACK_METHOD = 'live_voice.composition.p3.progress.ack' as const;

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
  readonly delivery_id: string;
  readonly session_id: string;
  readonly task_id: string;
  readonly attempt_id: string;
  readonly project_id: string;
  readonly correlation_id: string;
  readonly origin_id: string;
  readonly origin_kind: 'text' | 'voice';
  readonly requested_origin_kind: 'text' | 'voice';
  readonly effective_origin_kind: 'text';
  readonly delivery_mode: 'text' | 'text_fallback';
  readonly fallback_reason: string | null;
  readonly generation_kind: string;
  readonly generation_id: string;
  readonly generation: number;
  readonly source_event: ProductTextProgressEnvelope;
  readonly progress_event: ProductTextProgressEnvelope;
  readonly evidence_id: string;
  readonly consumption_mode: 'legacy_delivery' | 'presentation';
  readonly presentation_class: 'text' | null;
  readonly response_ref: Readonly<{
    interaction_id: string;
    response_id: string;
    response_generation: number;
  }> | null;
  readonly unit_id: string | null;
  readonly expected_event_head: number | null;
  readonly result_source_event_id: string | null;
  readonly state: string;
}

const PRESENTATION_PROGRESS_KEYS = Object.freeze([
  'correlation_id',
  'delivery_id',
  'delivery_mode',
  'effective_origin_kind',
  'event_type',
  'evidence_id',
  'expected_event_head',
  'fallback_reason',
  'generation',
  'generation_id',
  'generation_kind',
  'origin_id',
  'origin_kind',
  'presentation_class',
  'progress_event',
  'project_id',
  'requested_origin_kind',
  'response_ref',
  'result_source_event_id',
  'session_id',
  'source_event',
  'task_id',
  'unit_id',
]);

const LEGACY_PROGRESS_KEYS = Object.freeze(
  PRESENTATION_PROGRESS_KEYS.filter(
    key => !['expected_event_head', 'presentation_class', 'response_ref', 'result_source_event_id', 'unit_id'].includes(key),
  ),
);

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function uintValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function parseScope(value: unknown): ProductTextProgressScope | null {
  const raw = objectValue(value);
  if (!raw) return null;
  const keys = Object.keys(raw).sort();
  if (keys.length !== 4 || keys[0] !== 'assurance' || keys[1] !== 'project_id' || keys[2] !== 'session_id' || keys[3] !== 'subject_id') {
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
    left.subject_id === right.subject_id && left.project_id === right.project_id && left.session_id === right.session_id && left.assurance === right.assurance
  );
}

function parseEnvelope(value: unknown): ProductTextProgressEnvelope | null {
  const raw = objectValue(value);
  if (!raw) return null;
  const envelopeKeys = Object.keys(raw).sort();
  if (
    ![
      [
        'causation_id',
        'correlation_id',
        'event_id',
        'event_type',
        'payload',
        'scope',
        'seq',
        'stream_ref',
      ],
      [
        'causation_id',
        'correlation_id',
        'event_id',
        'event_type',
        'extensions',
        'payload',
        'scope',
        'seq',
        'stream_ref',
      ],
    ].some(expected => expected.length === envelopeKeys.length && expected.every((key, index) => key === envelopeKeys[index]))
  ) {
    return null;
  }
  const eventId = textValue(raw.event_id);
  const eventType = textValue(raw.event_type);
  const seq = uintValue(raw.seq);
  const correlationId = textValue(raw.correlation_id);
  const causationId = raw.causation_id === null ? null : textValue(raw.causation_id);
  const streamRef = objectValue(raw.stream_ref);
  if (!streamRef || !hasExactKeys(streamRef, ['id', 'kind'])) return null;
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

export function parseProductTextProgressEvent(value: unknown): ProductTextProgressEvent | null {
  const raw = objectValue(value);
  if (!raw || raw.event_type !== PRODUCT_TEXT_PROGRESS_EVENT) return null;
  const consumptionMode = hasExactKeys(raw, PRESENTATION_PROGRESS_KEYS)
    ? 'presentation'
    : hasExactKeys(raw, LEGACY_PROGRESS_KEYS)
      ? 'legacy_delivery'
      : null;
  if (consumptionMode === null) return null;
  const sessionId = textValue(raw.session_id);
  const deliveryId = textValue(raw.delivery_id);
  const taskId = textValue(raw.task_id);
  const projectId = textValue(raw.project_id);
  const correlationId = textValue(raw.correlation_id);
  const originId = textValue(raw.origin_id);
  const originKind = raw.origin_kind;
  const requestedOriginKind = raw.requested_origin_kind;
  const effectiveOriginKind = raw.effective_origin_kind;
  const deliveryMode = raw.delivery_mode;
  const fallbackReason = raw.fallback_reason === null ? null : textValue(raw.fallback_reason);
  const generationKind = textValue(raw.generation_kind);
  const generationId = textValue(raw.generation_id);
  const generation = uintValue(raw.generation);
  const evidenceId = textValue(raw.evidence_id);
  const presentationClass = consumptionMode === 'presentation' ? raw.presentation_class : null;
  const responseRef = consumptionMode === 'presentation' ? objectValue(raw.response_ref) : null;
  if (consumptionMode === 'presentation' && (!responseRef || !hasExactKeys(responseRef, ['interaction_id', 'response_generation', 'response_id']))) {
    return null;
  }
  const responseInteractionId = responseRef === null ? null : textValue(responseRef.interaction_id);
  const responseId = responseRef === null ? null : textValue(responseRef.response_id);
  const responseGeneration = responseRef === null ? null : uintValue(responseRef.response_generation);
  const unitId = consumptionMode === 'presentation' ? textValue(raw.unit_id) : null;
  const expectedEventHead = consumptionMode === 'presentation' ? uintValue(raw.expected_event_head) : null;
  const resultSourceEventId =
    consumptionMode === 'legacy_delivery' || raw.result_source_event_id === null ? null : textValue(raw.result_source_event_id);
  const sourceEvent = parseEnvelope(raw.source_event);
  const progressEvent = parseEnvelope(raw.progress_event);
  const sourceExtensions = objectValue(sourceEvent?.raw.extensions);
  const progressReturn = objectValue(sourceExtensions?.['jiuwenswarm.task_progress_return']);
  const attemptId = textValue(progressReturn?.persistent_attempt_id);
  const persistentEventSeq = uintValue(progressReturn?.persistent_event_seq);
  const persistentEventType = textValue(progressReturn?.persistent_event_type);
  const persistentSourceEventId = progressReturn?.persistent_source_event_id;
  const progressPayload = progressEvent?.payload;
  const workRef = objectValue(progressPayload?.work_ref);
  const state = textValue(progressPayload?.state);
  const sourceState = textValue(sourceEvent?.payload.state);
  const sourceOutcome =
    sourceEvent?.payload.outcome === null || sourceEvent?.payload.outcome === undefined
      ? null
      : textValue(sourceEvent.payload.outcome);
  const progressOutcome =
    progressPayload?.outcome === null || progressPayload?.outcome === undefined
      ? null
      : textValue(progressPayload.outcome);
  const payloadSeq = uintValue(progressPayload?.seq);
  const terminal = sourceEvent?.event_type === 'task.terminal';
  const completed = terminal && sourceOutcome === 'completed';
  const terminalOutcomeLegal =
    sourceOutcome === 'completed' ||
    sourceOutcome === 'failed' ||
    sourceOutcome === 'cancelled' ||
    sourceOutcome === 'interrupted' ||
    sourceOutcome === 'unknown';
  const resultBindingLegal =
    consumptionMode === 'legacy_delivery' ||
    (completed ? resultSourceEventId !== null && textValue(persistentSourceEventId) === resultSourceEventId : resultSourceEventId === null);
  if (
    !sessionId ||
    !deliveryId ||
    !taskId ||
    !attemptId ||
    persistentEventSeq !== sourceEvent?.seq ||
    persistentEventType !== sourceEvent?.event_type ||
    (persistentSourceEventId !== undefined && persistentSourceEventId !== null && !textValue(persistentSourceEventId)) ||
    !projectId ||
    !correlationId ||
    !originId ||
    (originKind !== 'text' && originKind !== 'voice') ||
    requestedOriginKind !== originKind ||
    effectiveOriginKind !== 'text' ||
    (deliveryMode !== 'text' && deliveryMode !== 'text_fallback') ||
    (deliveryMode === 'text_fallback' && originKind !== 'voice') ||
    (deliveryMode === 'text_fallback') !== (fallbackReason !== null) ||
    generationKind !== 'web_task_progress_generation' ||
    !generationId ||
    generation === null ||
    generation === 0 ||
    !evidenceId ||
    (consumptionMode === 'presentation' &&
      (presentationClass !== 'text' ||
        !responseInteractionId ||
        !responseId ||
        responseGeneration === null ||
        !unitId ||
        expectedEventHead === null ||
        expectedEventHead < sourceEvent?.seq ||
        (raw.result_source_event_id !== null && !resultSourceEventId))) ||
    !sourceEvent ||
    !progressEvent ||
    !state ||
    !sourceState ||
    sourceState !== state ||
    (terminal && (state !== 'terminal' || !terminalOutcomeLegal || progressOutcome !== sourceOutcome)) ||
    (!terminal && (state === 'terminal' || sourceOutcome !== null || progressOutcome !== null)) ||
    !resultBindingLegal ||
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
    delivery_id: deliveryId,
    session_id: sessionId,
    task_id: taskId,
    attempt_id: attemptId,
    project_id: projectId,
    correlation_id: correlationId,
    origin_id: originId,
    origin_kind: originKind,
    requested_origin_kind: requestedOriginKind as 'text' | 'voice',
    effective_origin_kind: effectiveOriginKind,
    delivery_mode: deliveryMode,
    fallback_reason: fallbackReason,
    generation_kind: generationKind,
    generation_id: generationId,
    generation,
    source_event: sourceEvent,
    progress_event: progressEvent,
    evidence_id: evidenceId,
    consumption_mode: consumptionMode,
    presentation_class: consumptionMode === 'presentation' ? 'text' : null,
    response_ref:
      responseInteractionId === null || responseId === null || responseGeneration === null
        ? null
        : Object.freeze({
            interaction_id: responseInteractionId,
            response_id: responseId,
            response_generation: responseGeneration,
          }),
    unit_id: unitId,
    expected_event_head: expectedEventHead,
    result_source_event_id: resultSourceEventId,
    state,
  });
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map(key => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
    .join(',')}}`;
}

/** Exact immutable tuple placed in the committed DOM and echoed in its ACK. */
export function productTextProgressPresentationBinding(event: Readonly<ProductTextProgressEvent>): string {
  const common = {
    consumption_mode: event.consumption_mode,
    correlation_id: event.correlation_id,
    delivery_id: event.delivery_id,
    delivery_mode: event.delivery_mode,
    effective_origin_kind: event.effective_origin_kind,
    evidence_id: event.evidence_id,
    expected_event_head: event.expected_event_head,
    fallback_reason: event.fallback_reason,
    generation: event.generation,
    generation_id: event.generation_id,
    generation_kind: event.generation_kind,
    origin_id: event.origin_id,
    origin_kind: event.origin_kind,
    progress_event: event.progress_event.raw,
    project_id: event.project_id,
    requested_origin_kind: event.requested_origin_kind,
    session_id: event.session_id,
    source_event: event.source_event.raw,
    state: event.state,
    task_id: event.task_id,
  };
  return canonicalJson(
    event.consumption_mode === 'legacy_delivery'
      ? common
      : {
          ...common,
          expected_event_head: event.expected_event_head,
          presentation_class: event.presentation_class,
          response_ref: event.response_ref,
          result_source_event_id: event.result_source_event_id,
          unit_id: event.unit_id,
        },
  );
}

export function adoptProductTextProgressEvent(
  current: Readonly<ProductTextProgressEvent> | null,
  value: unknown,
  activeSessionId: string | null
): Readonly<ProductTextProgressEvent> | null {
  const incoming = parseProductTextProgressEvent(value);
  if (!incoming) return current;
  return adoptParsedProductTextProgressEvent(current, incoming, activeSessionId);
}

export function adoptParsedProductTextProgressEvent(
  current: Readonly<ProductTextProgressEvent> | null,
  incoming: Readonly<ProductTextProgressEvent>,
  activeSessionId: string | null
): Readonly<ProductTextProgressEvent> | null {
  if (!incoming || !activeSessionId || incoming.session_id !== activeSessionId) {
    return current;
  }
  if (current === null) {
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
      (incoming.correlation_id !== current.correlation_id || incoming.source_event.seq <= current.source_event.seq))
  ) {
    return current;
  }
  return incoming;
}

export interface ProductTextProgressLegacyDeliveryAck {
  readonly session_id: string;
  readonly task_id: string;
  readonly correlation_id: string;
  readonly origin_id: string;
  readonly generation_id: string;
  readonly generation: number;
  readonly delivery_id: string;
  readonly source_event_id: string;
  readonly progress_event_id: string;
  readonly seq: number;
  readonly evidence_id: string;
}

export interface ProductTextProgressPresentationAck extends ProductTextProgressLegacyDeliveryAck {
  readonly presentation_class: 'text';
  readonly response_ref: NonNullable<ProductTextProgressEvent['response_ref']>;
  readonly unit_id: string;
  readonly expected_event_head: number;
  readonly result_source_event_id: string | null;
  readonly presentation_binding: string;
}

export type ProductTextProgressDeliveryAck = ProductTextProgressLegacyDeliveryAck | ProductTextProgressPresentationAck;

export function createProductTextProgressDeliveryAck(event: Readonly<ProductTextProgressEvent>): ProductTextProgressDeliveryAck {
  const base = {
    session_id: event.session_id,
    task_id: event.task_id,
    correlation_id: event.correlation_id,
    origin_id: event.origin_id,
    generation_id: event.generation_id,
    generation: event.generation,
    delivery_id: event.delivery_id,
    source_event_id: event.source_event.event_id,
    progress_event_id: event.progress_event.event_id,
    seq: event.source_event.seq,
    evidence_id: event.evidence_id,
  };
  if (event.consumption_mode === 'legacy_delivery') return Object.freeze(base);
  if (
    event.presentation_class !== 'text' ||
    event.response_ref === null ||
    event.unit_id === null ||
    event.expected_event_head === null
  ) {
    throw new Error('presentation progress binding is incomplete');
  }
  return Object.freeze({
    ...base,
    presentation_class: event.presentation_class,
    response_ref: event.response_ref,
    unit_id: event.unit_id,
    expected_event_head: event.expected_event_head,
    result_source_event_id: event.result_source_event_id,
    presentation_binding: productTextProgressPresentationBinding(event),
  });
}

export type ProductTextProgressAckStatus = 'pending' | 'acknowledged' | 'failed';

export interface ProductTextProgressAckSnapshot {
  readonly delivery_id: string;
  readonly status: ProductTextProgressAckStatus;
  readonly attempts: number;
  readonly retained_deliveries: number;
}

export type ProductTextProgressAckRequest = (method: typeof PRODUCT_PROGRESS_ACK_METHOD, params: ProductTextProgressDeliveryAck) => Promise<unknown>;

interface RetainedDeliveryAck {
  readonly ack: ProductTextProgressDeliveryAck;
  readonly expected_attempt_id: string;
  status: ProductTextProgressAckStatus;
  attempts: number;
  in_flight: boolean;
  retry_timer: ReturnType<typeof setTimeout> | null;
}

function sameDeliveryAck(left: Readonly<ProductTextProgressDeliveryAck>, right: Readonly<ProductTextProgressDeliveryAck>): boolean {
  const baseMatches =
    left.session_id === right.session_id &&
    left.task_id === right.task_id &&
    left.correlation_id === right.correlation_id &&
    left.origin_id === right.origin_id &&
    left.generation_id === right.generation_id &&
    left.generation === right.generation &&
    left.delivery_id === right.delivery_id &&
    left.source_event_id === right.source_event_id &&
    left.progress_event_id === right.progress_event_id &&
    left.seq === right.seq &&
    left.evidence_id === right.evidence_id;
  if (!baseMatches) return false;
  const leftPresentation = 'presentation_class' in left;
  const rightPresentation = 'presentation_class' in right;
  if (leftPresentation !== rightPresentation) return false;
  if (!leftPresentation || !rightPresentation) return true;
  return (
    left.presentation_class === right.presentation_class &&
    left.response_ref.interaction_id === right.response_ref.interaction_id &&
    left.response_ref.response_id === right.response_ref.response_id &&
    left.response_ref.response_generation === right.response_ref.response_generation &&
    left.unit_id === right.unit_id &&
    left.expected_event_head === right.expected_event_head &&
    left.result_source_event_id === right.result_source_event_id &&
    left.presentation_binding === right.presentation_binding
  );
}

function requireAckResponse(value: unknown, retained: RetainedDeliveryAck): void {
  const ack = retained.ack;
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  const baseMismatch =
    payload?.ok !== true ||
    result?.status !== 'acknowledged' ||
    result.attempt_id !== retained.expected_attempt_id ||
    result.session_id !== ack.session_id ||
    result.delivery_id !== ack.delivery_id ||
    result.task_id !== ack.task_id ||
    result.correlation_id !== ack.correlation_id ||
    result.origin_id !== ack.origin_id ||
    result.generation_id !== ack.generation_id ||
    result.generation !== ack.generation ||
    result.source_event_id !== ack.source_event_id ||
    result.progress_event_id !== ack.progress_event_id ||
    result.seq !== ack.seq ||
    result.evidence_id !== ack.evidence_id ||
    result.acknowledgement !== 'web_ui_text_consumed' ||
    typeof result.replayed !== 'boolean';
  if (baseMismatch) {
    throw new Error('product text-progress acknowledgement mismatch');
  }
  if (!('presentation_class' in ack)) {
    if (
      'presentation_class' in result ||
      'response_ref' in result ||
      'unit_id' in result ||
      'expected_event_head' in result ||
      'result_source_event_id' in result ||
      'presentation_binding' in result
    ) {
      throw new Error('legacy text-progress acknowledgement gained presentation authority');
    }
    return;
  }
  const responseRef = objectValue(result.response_ref);
  if (
    result.presentation_class !== ack.presentation_class ||
    responseRef?.interaction_id !== ack.response_ref.interaction_id ||
    responseRef?.response_id !== ack.response_ref.response_id ||
    responseRef?.response_generation !== ack.response_ref.response_generation ||
    result.unit_id !== ack.unit_id ||
    result.expected_event_head !== ack.expected_event_head ||
    result.result_source_event_id !== ack.result_source_event_id ||
    result.presentation_binding !== ack.presentation_binding
  ) {
    throw new Error('product text-progress presentation acknowledgement mismatch');
  }
}

/** Retains and retries every exact delivery ACK until the server confirms it. */
export class ProductTextProgressAckOwner {
  private readonly enabled: boolean;
  private readonly request: ProductTextProgressAckRequest;
  private readonly onSnapshot?: (snapshot: ProductTextProgressAckSnapshot) => void;
  private readonly capacity: number;
  private readonly retryDelayMs: number;
  private readonly deliveries = new Map<string, RetainedDeliveryAck>();
  private connected = false;
  private closed = false;

  constructor(input: {
    enabled: boolean;
    request: ProductTextProgressAckRequest;
    on_snapshot?: (snapshot: ProductTextProgressAckSnapshot) => void;
    capacity?: number;
    retry_delay_ms?: number;
  }) {
    if (typeof input.request !== 'function') throw new Error('ACK request owner is required');
    const capacity = input.capacity ?? 128;
    const retryDelayMs = input.retry_delay_ms ?? 250;
    if (!Number.isSafeInteger(capacity) || capacity <= 0) throw new Error('ACK capacity is invalid');
    if (!Number.isSafeInteger(retryDelayMs) || retryDelayMs < 0) throw new Error('ACK retry delay is invalid');
    this.enabled = input.enabled;
    this.request = input.request;
    this.onSnapshot = input.on_snapshot;
    this.capacity = capacity;
    this.retryDelayMs = retryDelayMs;
  }

  setConnected(connected: boolean): void {
    if (!this.enabled || this.closed || this.connected === connected) return;
    this.connected = connected;
    if (connected) this.retryPending();
  }

  retain(event: Readonly<ProductTextProgressEvent>): ProductTextProgressAckSnapshot | null {
    if (!this.enabled || this.closed) return null;
    const ack = createProductTextProgressDeliveryAck(event);
    const prior = this.deliveries.get(ack.delivery_id);
    if (prior) {
      if (!sameDeliveryAck(prior.ack, ack) || prior.expected_attempt_id !== event.attempt_id) {
        throw new Error('delivery_id binding conflict');
      }
      if (prior.status !== 'acknowledged' && this.connected) this.send(prior);
      return this.snapshot(prior);
    }
    if (this.deliveries.size >= this.capacity) {
      const acknowledged = [...this.deliveries.entries()].find(([, item]) => item.status === 'acknowledged');
      if (!acknowledged) throw new Error('ACK retention capacity has no safe eviction');
      this.deliveries.delete(acknowledged[0]);
    }
    const retained: RetainedDeliveryAck = {
      ack,
      expected_attempt_id: event.attempt_id,
      status: this.connected ? 'pending' : 'failed',
      attempts: 0,
      in_flight: false,
      retry_timer: null,
    };
    this.deliveries.set(ack.delivery_id, retained);
    this.publish(retained);
    if (this.connected) this.send(retained);
    return this.snapshot(retained);
  }

  retryPending(): void {
    if (!this.enabled || this.closed || !this.connected) return;
    for (const retained of this.deliveries.values()) {
      if (retained.status !== 'acknowledged') this.send(retained);
    }
  }

  status(deliveryId: string): ProductTextProgressAckSnapshot | null {
    const retained = this.deliveries.get(deliveryId);
    return retained ? this.snapshot(retained) : null;
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    for (const retained of this.deliveries.values()) {
      if (retained.retry_timer !== null) clearTimeout(retained.retry_timer);
    }
    this.deliveries.clear();
  }

  private send(retained: RetainedDeliveryAck): void {
    if (retained.in_flight || retained.status === 'acknowledged' || !this.connected || this.closed) return;
    if (retained.retry_timer !== null) {
      clearTimeout(retained.retry_timer);
      retained.retry_timer = null;
    }
    retained.in_flight = true;
    retained.status = 'pending';
    retained.attempts += 1;
    this.publish(retained);
    void Promise.resolve()
      .then(() => this.request(PRODUCT_PROGRESS_ACK_METHOD, retained.ack))
      .then(value => {
        requireAckResponse(value, retained);
        if (!this.closed) retained.status = 'acknowledged';
      })
      .catch(() => {
        if (this.closed) return;
        retained.status = 'failed';
        if (this.connected && !this.closed) {
          retained.retry_timer = setTimeout(() => {
            retained.retry_timer = null;
            this.send(retained);
          }, this.retryDelayMs);
        }
      })
      .finally(() => {
        retained.in_flight = false;
        if (!this.closed) this.publish(retained);
      });
  }

  private snapshot(retained: RetainedDeliveryAck): ProductTextProgressAckSnapshot {
    return Object.freeze({
      delivery_id: retained.ack.delivery_id,
      status: retained.status,
      attempts: retained.attempts,
      retained_deliveries: this.deliveries.size,
    });
  }

  private publish(retained: RetainedDeliveryAck): ProductTextProgressAckSnapshot {
    const snapshot = this.snapshot(retained);
    this.onSnapshot?.(snapshot);
    return snapshot;
  }
}

export interface ProductTextProgressDomNode {
  readonly isConnected: boolean;
  getAttribute(name: string): string | null;
}

/**
 * Converts real, exact DOM adoption into the existing delivery ACK.
 *
 * React state assignment is not presentation.  The mounted product carrier calls
 * this owner from a layout effect with the actual connected element after commit.
 */
export class ProductTextProgressDomAdoptionOwner {
  private readonly ackOwner: Pick<ProductTextProgressAckOwner, 'retain'>;

  constructor(ackOwner: Pick<ProductTextProgressAckOwner, 'retain'>) {
    if (!ackOwner || typeof ackOwner.retain !== 'function') {
      throw new Error('product text-progress ACK owner is required');
    }
    this.ackOwner = ackOwner;
  }

  adopt(
    event: Readonly<ProductTextProgressEvent>,
    node: ProductTextProgressDomNode | null
  ): ProductTextProgressAckSnapshot | null {
    if (!node || node.isConnected !== true) return null;
    const expected: Record<string, string> = {
      'data-delivery-id': event.delivery_id,
      'data-session-id': event.session_id,
      'data-subject-id': event.source_event.scope.subject_id,
      'data-project-id': event.project_id,
      'data-task-id': event.task_id,
      'data-attempt-id': event.attempt_id,
      'data-event-id': event.source_event.event_id,
      'data-event-seq': String(event.source_event.seq),
      'data-generation-id': event.generation_id,
      'data-generation': String(event.generation),
    };
    if (event.consumption_mode === 'presentation') {
      if (
        event.presentation_class !== 'text' ||
        event.response_ref === null ||
        event.unit_id === null ||
        event.expected_event_head === null
      ) {
        throw new Error('DOM presentation authority is incomplete');
      }
      expected['data-presentation-binding'] = productTextProgressPresentationBinding(event);
      expected['data-presentation-class'] = event.presentation_class;
      expected['data-response-interaction-id'] = event.response_ref.interaction_id;
      expected['data-response-id'] = event.response_ref.response_id;
      expected['data-response-generation'] = String(event.response_ref.response_generation);
      expected['data-unit-id'] = event.unit_id;
      expected['data-expected-event-head'] = String(event.expected_event_head);
      expected['data-result-source-event-id'] = event.result_source_event_id ?? '';
    } else {
      for (const name of [
        'data-presentation-binding',
        'data-presentation-class',
        'data-response-interaction-id',
        'data-response-id',
        'data-response-generation',
        'data-unit-id',
        'data-expected-event-head',
        'data-result-source-event-id',
      ]) {
        if (node.getAttribute(name) !== null) {
          throw new Error('legacy DOM acquired presentation authority');
        }
      }
    }
    for (const [name, value] of Object.entries(expected)) {
      if (node.getAttribute(name) !== value) {
        throw new Error('DOM presentation binding mismatch');
      }
    }
    return this.ackOwner.retain(event);
  }
}
