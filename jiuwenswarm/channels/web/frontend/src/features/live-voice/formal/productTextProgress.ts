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
  const deliveryId = textValue(raw.delivery_id);
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
    !deliveryId ||
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
    delivery_id: deliveryId,
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

export interface ProductTextProgressDeliveryAck {
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

export function createProductTextProgressDeliveryAck(
  event: Readonly<ProductTextProgressEvent>
): ProductTextProgressDeliveryAck {
  return Object.freeze({
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
  });
}

export type ProductTextProgressAckStatus = 'pending' | 'acknowledged' | 'failed';

export interface ProductTextProgressAckSnapshot {
  readonly delivery_id: string;
  readonly status: ProductTextProgressAckStatus;
  readonly attempts: number;
  readonly retained_deliveries: number;
}

export type ProductTextProgressAckRequest = (
  method: typeof PRODUCT_PROGRESS_ACK_METHOD,
  params: ProductTextProgressDeliveryAck
) => Promise<unknown>;

interface RetainedDeliveryAck {
  readonly ack: ProductTextProgressDeliveryAck;
  status: ProductTextProgressAckStatus;
  attempts: number;
  in_flight: boolean;
  retry_timer: ReturnType<typeof setTimeout> | null;
}

function sameDeliveryAck(
  left: Readonly<ProductTextProgressDeliveryAck>,
  right: Readonly<ProductTextProgressDeliveryAck>
): boolean {
  return (
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
    left.evidence_id === right.evidence_id
  );
}

function requireAckResponse(value: unknown, ack: ProductTextProgressDeliveryAck): void {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (
    payload?.ok !== true ||
    result?.status !== 'acknowledged' ||
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
    typeof result.replayed !== 'boolean'
  ) {
    throw new Error('product text-progress acknowledgement mismatch');
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
      if (!sameDeliveryAck(prior.ack, ack)) throw new Error('delivery_id binding conflict');
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
        requireAckResponse(value, retained.ack);
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
