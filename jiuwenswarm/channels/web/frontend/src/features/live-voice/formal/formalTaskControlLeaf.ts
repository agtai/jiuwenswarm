export const FORMAL_TASK_CONTROL_OPERATIONS = Object.freeze(['task.create', 'task.get', 'task.list', 'task.status', 'task.cancel', 'task.retry', 'task.events'] as const);

export const FORMAL_TASK_CONTROL_LIMITS = Object.freeze({
  max_text_chars: 4_096,
  max_tasks: 256,
  max_events_per_response: 256,
  max_mutation_receipts: 512,
  max_progress_receipts: 512,
  max_pending_mutations: 64,
} as const);

export type FormalTaskControlOperation = (typeof FORMAL_TASK_CONTROL_OPERATIONS)[number];
export type FormalTaskCancelScope = 'playback.stop' | 'response.cancel' | 'round.cancel' | 'task.cancel';
export type FormalTaskState = 'accepted' | 'running' | 'blocked' | 'decision_required' | 'terminal';

export interface FormalTaskControlBinding {
  readonly subject_id: string;
  readonly session_id: string;
  readonly project_id: string;
  readonly correlation_id: string;
  readonly generation: number;
}

export interface FormalTaskControlRecord {
  readonly task_id: string;
  readonly attempt_id: string | null;
  readonly attempt_number: number | null;
  readonly state: FormalTaskState | null;
  readonly outcome: string | null;
  readonly event_head: number | null;
  readonly last_event_id: string | null;
  readonly last_event_seq: number | null;
}

export interface FormalTaskMutationInput {
  readonly operation: 'task.create' | 'task.cancel' | 'task.retry';
  readonly command_id: string;
  readonly task_id: string | null;
}

export interface FormalTaskConfirmationReceipt {
  readonly confirmation_id: string;
  readonly operation: 'task.create' | 'task.cancel' | 'task.retry';
  readonly command_id: string;
  readonly target_task_id: string | null;
  readonly expires_at: string;
}

export interface PreparedFormalTaskMutation {
  readonly binding: FormalTaskControlBinding;
  readonly mutation: FormalTaskMutationInput;
  readonly confirmation: FormalTaskConfirmationReceipt;
}

export interface FormalTaskProgressOrigin {
  readonly task_id: string;
  readonly correlation_id: string;
  readonly source_event_id: string;
  readonly source_event_seq: number;
  readonly progress_event_id: string;
  readonly progress_causation_id: string;
  readonly state: FormalTaskState;
  readonly outcome: string | null;
}

export interface FormalTaskEventsQueryContext {
  readonly task_id: string;
  readonly after_seq: number;
}

export interface FormalTaskAdoptionContext {
  readonly connection_generation: number;
  readonly command_id: string | null;
  readonly target_task_id: string | null;
  readonly events_query: FormalTaskEventsQueryContext | null;
}

export interface FormalTaskControlSnapshot {
  readonly enabled: boolean;
  readonly connected: boolean;
  readonly connection_generation: number;
  readonly binding: FormalTaskControlBinding;
  readonly tasks: readonly FormalTaskControlRecord[];
  readonly mutation_receipts: readonly string[];
  readonly progress_receipts: readonly string[];
}

type JsonObject = Readonly<Record<string, unknown>>;

function objectValue(value: unknown): JsonObject | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as JsonObject) : null;
}

function text(value: unknown, field: string): string {
  if (
    typeof value !== 'string'
    || !value.trim()
    || value.length > FORMAL_TASK_CONTROL_LIMITS.max_text_chars
  ) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function adoptionContext(
  operation: FormalTaskControlOperation,
  value: unknown,
): Readonly<FormalTaskAdoptionContext> {
  const context = objectValue(value);
  const contextKeys = context === null ? [] : Object.keys(context).sort();
  const expectedContextKeys = ['command_id', 'connection_generation', 'events_query', 'target_task_id'];
  if (
    context === null
    || !Number.isSafeInteger(context.connection_generation)
    || Number(context.connection_generation) <= 0
    || contextKeys.length !== expectedContextKeys.length
    || contextKeys.some((key, index) => key !== expectedContextKeys[index])
  ) {
    throw new Error('formal task adoption context is invalid');
  }
  const commandId = context.command_id === null ? null : text(context.command_id, 'adoption.command_id');
  const targetTaskId = context.target_task_id === null ? null : text(context.target_task_id, 'adoption.target_task_id');
  const events = context.events_query === null ? null : objectValue(context.events_query);
  if (
    (operation === 'task.create' || operation === 'task.cancel' || operation === 'task.retry') !== (commandId !== null)
    || (operation === 'task.get' || operation === 'task.status') !== (targetTaskId !== null)
    || (operation === 'task.events') !== (events !== null)
    || (events !== null && Object.keys(events).some(key => !['task_id', 'after_seq'].includes(key)))
  ) {
    throw new Error('formal task adoption context does not match its operation');
  }
  let eventsQuery: FormalTaskEventsQueryContext | null = null;
  if (events !== null) {
    const afterSeq = events.after_seq;
    if (!Number.isSafeInteger(afterSeq) || Number(afterSeq) < -1) {
      throw new Error('task.events.after_seq is invalid');
    }
    eventsQuery = Object.freeze({
      task_id: text(events.task_id, 'task.events.task_id'),
      after_seq: Number(afterSeq),
    });
  }
  return Object.freeze({
    connection_generation: Number(context.connection_generation),
    command_id: commandId,
    target_task_id: targetTaskId,
    events_query: eventsQuery,
  });
}

interface SubmittedMutationBinding {
  readonly operation: 'task.create' | 'task.cancel' | 'task.retry';
  readonly command_id: string;
  readonly target_task_id: string | null;
  readonly target_attempt_id: string | null;
  readonly target_attempt_number: number | null;
  readonly adopted_task_id: string | null;
  readonly adopted_attempt_id: string | null;
  readonly adopted_state: FormalTaskState | null;
  readonly adopted_outbox_id: string | null;
}

const PROJECT_CODE_EXECUTOR_ID = 'jiuwenswarm_code_agent.project_code';
const EVENT_TYPE_STATE = Object.freeze({
  'task.accepted': 'accepted',
  'task.retry_accepted': 'accepted',
  'task.running': 'running',
  'task.blocked': 'blocked',
  'task.decision_required': 'decision_required',
  'task.terminal': 'terminal',
  'attempt.accepted': 'accepted',
  'attempt.running': 'running',
  'attempt.terminal': 'terminal',
} as const);

function validTaskStateTransition(
  previous: FormalTaskState | null,
  next: FormalTaskState,
  retryBoundary = false,
): boolean {
  if (previous === null) return next === 'accepted';
  if (retryBoundary) return previous === 'terminal' && next === 'accepted';
  if (previous === 'terminal') return next === 'terminal';
  if (previous === 'accepted') return ['accepted', 'running', 'blocked', 'decision_required', 'terminal'].includes(next);
  return ['running', 'blocked', 'decision_required', 'terminal'].includes(next);
}

function validateEventProvenance(
  event: JsonObject,
  seq: number,
  state: FormalTaskState,
  outcome: string | null,
  previousState: FormalTaskState | null,
  previousOutcome: string | null,
  previousAttemptId: string | null,
  previousAttemptNumber: number | null,
): number {
  const eventType = text(event.event_type, 'event.event_type');
  const producer = text(event.producer, 'event.producer');
  const sourceEventId = event.source_event_id === null
    ? null
    : text(event.source_event_id, 'event.source_event_id');
  const causationId = text(event.causation_id, 'event.causation_id');
  const expectedState = EVENT_TYPE_STATE[eventType as keyof typeof EVENT_TYPE_STATE];
  const cancelRequested = eventType === 'task.cancel_requested';
  const retryAccepted = eventType === 'task.retry_accepted';
  if (expectedState === undefined && !cancelRequested) {
    throw new Error('task event type is outside the closed lifecycle vocabulary');
  }
  if (
    (expectedState !== undefined && state !== expectedState)
    || (cancelRequested && (previousState === null || state !== previousState || outcome !== previousOutcome))
    || !validTaskStateTransition(previousState, state, retryAccepted)
    || (previousState === 'terminal' && !retryAccepted && outcome !== previousOutcome)
    || (seq === 0 && eventType !== 'task.accepted')
  ) {
    throw new Error('task event lifecycle is self-contradictory');
  }
  const taskProducerValid = (
    ((eventType === 'task.accepted' || eventType === 'task.retry_accepted') && producer === 'task_core')
    || (['task.running', 'task.blocked', 'task.decision_required'].includes(eventType) && producer === 'task_core')
    || (eventType === 'task.cancel_requested' && producer === 'task_core.control')
    || (eventType === 'task.terminal' && ['task_core', 'task_core.delivery', 'task_core.reconciliation'].includes(producer))
  );
  const attemptProducerValid = eventType.startsWith('attempt.')
    && [PROJECT_CODE_EXECUTOR_ID, 'task_core.reconciliation'].includes(producer);
  if (!taskProducerValid && !attemptProducerValid) {
    throw new Error('task event producer is not authoritative for its event type');
  }
  if (
    ((eventType === 'task.accepted' || eventType === 'task.retry_accepted' || eventType === 'task.cancel_requested') && sourceEventId !== null)
    || (sourceEventId !== null && causationId !== sourceEventId)
    || (
      sourceEventId === null
      && (
        ['task.running', 'task.blocked', 'task.decision_required'].includes(eventType)
        || (eventType.startsWith('attempt.') && producer === PROJECT_CODE_EXECUTOR_ID)
      )
    )
  ) {
    throw new Error('task event source and causation provenance mismatch');
  }
  const details = objectValue(event.details);
  if (details === null) throw new Error('task event details are invalid');
  if (!retryAccepted) return previousAttemptNumber ?? 1;
  const attemptId = text(event.attempt_id, 'event.attempt_id');
  const retryOfAttemptId = text(details.retry_of_attempt_id, 'event.details.retry_of_attempt_id');
  const commandId = text(details.command_id, 'event.details.command_id');
  const previous = text(details.previous_outcome, 'event.details.previous_outcome');
  const attemptNumber = details.attempt_number;
  if (
    Object.keys(details).sort().join(',') !== 'attempt_number,command_id,previous_outcome,retry_of_attempt_id'
    || previousAttemptId === null
    || previousAttemptNumber === null
    || retryOfAttemptId !== previousAttemptId
    || attemptId === previousAttemptId
    || previous !== previousOutcome
    || !['cancelled', 'completed'].includes(previous)
    || !Number.isSafeInteger(attemptNumber)
    || Number(attemptNumber) !== previousAttemptNumber + 1
    || ![2, 3].includes(Number(attemptNumber))
    || commandId !== causationId
  ) {
    throw new Error('task.retry_accepted lineage is invalid');
  }
  return Number(attemptNumber);
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) {
    throw new Error(`${field} is invalid`);
  }
  return Number(value);
}

function attemptNumber(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || ![1, 2, 3].includes(Number(value))) {
    throw new Error(`${field} is invalid`);
  }
  return Number(value);
}

function freezeBinding(input: FormalTaskControlBinding): FormalTaskControlBinding {
  if (!Number.isSafeInteger(input.generation) || input.generation <= 0) {
    throw new Error('generation is invalid');
  }
  return Object.freeze({
    subject_id: text(input.subject_id, 'subject_id'),
    session_id: text(input.session_id, 'session_id'),
    project_id: text(input.project_id, 'project_id'),
    correlation_id: text(input.correlation_id, 'correlation_id'),
    generation: input.generation,
  });
}

function canonicalTaskState(value: unknown): FormalTaskState {
  if (!(['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const).includes(value as FormalTaskState)) {
    throw new Error('task.state is invalid');
  }
  return value as FormalTaskState;
}

function requireScope(value: unknown, binding: FormalTaskControlBinding): void {
  const scope = objectValue(value);
  if (
    scope === null ||
    scope.subject_id !== binding.subject_id ||
    scope.session_id !== binding.session_id ||
    scope.project_id !== binding.project_id ||
    scope.assurance !== 'authenticated' ||
    Object.keys(scope).some(key => !['subject_id', 'session_id', 'project_id', 'assurance'].includes(key))
  ) {
    throw new Error('formal task scope binding mismatch');
  }
}

function parseTask(
  value: unknown,
  binding: FormalTaskControlBinding,
  authoritativeAttemptNumber: number | null = null,
): FormalTaskControlRecord {
  const task = objectValue(value);
  if (task === null) throw new Error('task result is invalid');
  requireScope(task.scope, binding);
  if (text(task.correlation_id, 'task.correlation_id') !== binding.correlation_id) {
    throw new Error('formal task correlation binding mismatch');
  }
  const state = canonicalTaskState(task.state);
  const outcome = task.outcome === null ? null : text(task.outcome, 'task.outcome');
  if ((state === 'terminal') !== (outcome !== null)) {
    throw new Error('task terminal outcome mismatch');
  }
  return Object.freeze({
    task_id: text(task.task_id, 'task_id'),
    attempt_id: text(task.attempt_id, 'attempt_id'),
    attempt_number: authoritativeAttemptNumber,
    state,
    outcome,
    event_head: nonNegativeInteger(task.event_head, 'task.event_head'),
    last_event_id: null,
    last_event_seq: null,
  });
}

export function isFormalTaskRetryEligible(record: Readonly<FormalTaskControlRecord> | null | undefined): boolean {
  return Boolean(
    record
    && record.attempt_id !== null
    && record.attempt_number !== null
    && record.attempt_number < 3
    && record.state === 'terminal'
    && (record.outcome === 'cancelled' || record.outcome === 'completed')
  );
}

function sameBinding(left: FormalTaskControlBinding, right: FormalTaskControlBinding): boolean {
  return (
    left.subject_id === right.subject_id &&
    left.session_id === right.session_id &&
    left.project_id === right.project_id &&
    left.correlation_id === right.correlation_id &&
    left.generation === right.generation
  );
}

export function mapFormalTaskCancel(scope: FormalTaskCancelScope, taskId: string | null): Readonly<{ operation: 'task.cancel'; task_id: string }> | null {
  if (scope !== 'task.cancel') return null;
  return Object.freeze({ operation: 'task.cancel', task_id: text(taskId, 'task_id') });
}

export function prepareFormalTaskMutation(
  bindingInput: FormalTaskControlBinding,
  mutationInput: FormalTaskMutationInput,
  confirmationInput: FormalTaskConfirmationReceipt
): PreparedFormalTaskMutation {
  const binding = freezeBinding(bindingInput);
  const operation = mutationInput.operation;
  const commandId = text(mutationInput.command_id, 'command_id');
  const taskId = mutationInput.task_id === null ? null : text(mutationInput.task_id, 'task_id');
  if ((operation === 'task.create') !== (taskId === null) || !['task.create', 'task.cancel', 'task.retry'].includes(operation)) {
    throw new Error('formal task mutation target is invalid');
  }
  const confirmation = Object.freeze({
    confirmation_id: text(confirmationInput.confirmation_id, 'confirmation_id'),
    operation: confirmationInput.operation,
    command_id: text(confirmationInput.command_id, 'confirmation.command_id'),
    target_task_id: confirmationInput.target_task_id === null ? null : text(confirmationInput.target_task_id, 'confirmation.target_task_id'),
    expires_at: text(confirmationInput.expires_at, 'confirmation.expires_at'),
  });
  if (
    confirmation.operation !== operation ||
    confirmation.command_id !== commandId ||
    confirmation.target_task_id !== taskId ||
    !Number.isFinite(Date.parse(confirmation.expires_at)) ||
    Date.parse(confirmation.expires_at) <= Date.now()
  ) {
    throw new Error('formal task confirmation binding mismatch');
  }
  return Object.freeze({
    binding,
    mutation: Object.freeze({ operation, command_id: commandId, task_id: taskId }),
    confirmation,
  });
}

export class FormalTaskControlLeaf {
  readonly #enabled: boolean;
  readonly #binding: FormalTaskControlBinding;
  #connected = true;
  #connectionGeneration = 1;
  readonly #tasks = new Map<string, FormalTaskControlRecord>();
  readonly #mutationReceipts = new Set<string>();
  readonly #confirmationReceipts = new Set<string>();
  readonly #pendingMutationCommands = new Set<string>();
  readonly #pendingConfirmations = new Set<string>();
  readonly #submittedMutations = new Map<string, SubmittedMutationBinding>();
  readonly #progressReceipts = new Map<string, string>();

  constructor(input: { enabled: boolean; binding: FormalTaskControlBinding }) {
    this.#enabled = input.enabled === true;
    this.#binding = freezeBinding(input.binding);
  }

  snapshot(): FormalTaskControlSnapshot {
    return Object.freeze({
      enabled: this.#enabled,
      connected: this.#connected,
      connection_generation: this.#connectionGeneration,
      binding: this.#binding,
      tasks: Object.freeze([...this.#tasks.values()].sort((left, right) => left.task_id.localeCompare(right.task_id))),
      mutation_receipts: Object.freeze([...this.#mutationReceipts].sort()),
      progress_receipts: Object.freeze([...this.#progressReceipts.keys()].sort()),
    });
  }

  disconnect(): FormalTaskControlSnapshot {
    if (this.#connected) {
      this.#connected = false;
      this.#connectionGeneration += 1;
    }
    return this.snapshot();
  }

  reconnect(bindingInput: FormalTaskControlBinding): FormalTaskControlSnapshot {
    const binding = freezeBinding(bindingInput);
    if (!sameBinding(binding, this.#binding)) {
      throw new Error('formal task control cannot cross scope or generation on reconnect');
    }
    this.#connected = true;
    return this.snapshot();
  }

  async submitMutation<T>(prepared: PreparedFormalTaskMutation, send: (prepared: PreparedFormalTaskMutation) => Promise<T>): Promise<T> {
    if (!this.#enabled) throw new Error('formal task control is disabled');
    if (!this.#connected) throw new Error('formal task control is disconnected');
    const normalized = prepareFormalTaskMutation(prepared.binding, prepared.mutation, prepared.confirmation);
    if (!sameBinding(normalized.binding, this.#binding)) {
      throw new Error('formal task mutation binding mismatch');
    }
    const commandId = normalized.mutation.command_id;
    const confirmationId = normalized.confirmation.confirmation_id;
    if (this.#mutationReceipts.has(commandId) || this.#confirmationReceipts.has(confirmationId)) {
      throw new Error('formal task mutation command is already acknowledged');
    }
    if (this.#pendingMutationCommands.has(commandId) || this.#pendingConfirmations.has(confirmationId)) {
      throw new Error('formal task mutation command is already in flight');
    }
    if (
      this.#pendingMutationCommands.size >= FORMAL_TASK_CONTROL_LIMITS.max_pending_mutations
      || this.#pendingConfirmations.size >= FORMAL_TASK_CONTROL_LIMITS.max_pending_mutations
    ) {
      throw new Error('formal task mutation pending capacity is exhausted');
    }
    if (
      this.#mutationReceipts.size >= FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts
      || this.#confirmationReceipts.size >= FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts
      || this.#submittedMutations.size >= FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts
    ) {
      throw new Error('formal task mutation receipt capacity is exhausted');
    }
    const targetTask = normalized.mutation.task_id === null
      ? null
      : this.#tasks.get(normalized.mutation.task_id);
    if (
      (normalized.mutation.operation === 'task.cancel' || normalized.mutation.operation === 'task.retry')
      && (targetTask === null || targetTask === undefined || targetTask.attempt_id === null)
    ) {
      throw new Error(`formal ${normalized.mutation.operation} requires an observed exact task attempt`);
    }
    if (normalized.mutation.operation === 'task.retry' && !isFormalTaskRetryEligible(targetTask)) {
      throw new Error('formal task.retry requires an eligible authoritative terminal attempt');
    }
    const connectionGeneration = this.#connectionGeneration;
    const retained: SubmittedMutationBinding = Object.freeze({
      operation: normalized.mutation.operation,
      command_id: commandId,
      target_task_id: normalized.mutation.task_id,
      target_attempt_id: targetTask?.attempt_id ?? null,
      target_attempt_number: targetTask?.attempt_number ?? null,
      adopted_task_id: null,
      adopted_attempt_id: null,
      adopted_state: null,
      adopted_outbox_id: null,
    });
    this.#pendingMutationCommands.add(commandId);
    this.#pendingConfirmations.add(confirmationId);
    try {
      const result = await send(normalized);
      if (!this.#connected || this.#connectionGeneration !== connectionGeneration) {
        throw new Error('formal task mutation response is stale after disconnect');
      }
      this.#mutationReceipts.add(commandId);
      this.#confirmationReceipts.add(confirmationId);
      this.#submittedMutations.set(commandId, retained);
      return result;
    } finally {
      this.#pendingMutationCommands.delete(commandId);
      this.#pendingConfirmations.delete(confirmationId);
    }
  }

  adopt(
    operation: FormalTaskControlOperation,
    response: unknown,
    contextInput: FormalTaskAdoptionContext,
  ): FormalTaskControlSnapshot {
    if (!this.#enabled) throw new Error('formal task control is disabled');
    if (!this.#connected) throw new Error('formal task control is disconnected');
    const context = adoptionContext(operation, contextInput);
    if (context.connection_generation !== this.#connectionGeneration) {
      throw new Error('formal task response belongs to a stale connection');
    }
    const payload = objectValue(response);
    const productMutation =
      (operation === 'task.create' || operation === 'task.cancel' || operation === 'task.retry')
      && payload?.status === 'mutation_processed'
        ? payload
        : null;
    if (productMutation !== null && productMutation.operation !== operation) {
      throw new Error('formal task mutation response operation binding mismatch');
    }
    const result = productMutation === null
      ? objectValue(payload?.result)
      : objectValue(productMutation.formal_task_result);
    if (result === null || (productMutation === null && payload?.ok !== true)) {
      throw new Error(`formal ${operation} result is unavailable`);
    }
    if (operation === 'task.list') {
      if (!Array.isArray(result.tasks)) throw new Error('task.list result is invalid');
      if (result.tasks.length > FORMAL_TASK_CONTROL_LIMITS.max_tasks) {
        throw new Error('task.list exceeds the formal task capacity');
      }
      const next = new Map<string, FormalTaskControlRecord>();
      for (const value of result.tasks) {
        const rawTask = objectValue(value);
        const number = rawTask !== null && Object.prototype.hasOwnProperty.call(rawTask, 'attempt_number')
          ? attemptNumber(rawTask.attempt_number, 'task.attempt_number')
          : null;
        const task = parseTask(value, this.#binding, number);
        if (next.has(task.task_id)) throw new Error('task.list contains a duplicate task');
        next.set(task.task_id, task);
      }
      this.#tasks.clear();
      for (const [taskId, task] of next) this.#tasks.set(taskId, task);
    } else if (operation === 'task.get' || operation === 'task.status') {
      const attempt = objectValue(result.attempt);
      if (attempt === null) throw new Error('formal task/attempt result binding mismatch');
      const task = parseTask(result.task, this.#binding, attemptNumber(attempt.attempt_number, 'attempt.attempt_number'));
      if (
        context.target_task_id === null
        || task.task_id !== context.target_task_id
        || attempt.task_id !== task.task_id
        || attempt.attempt_id !== task.attempt_id
      ) {
        throw new Error('formal task/attempt result binding mismatch');
      }
      if (!this.#tasks.has(task.task_id) && this.#tasks.size >= FORMAL_TASK_CONTROL_LIMITS.max_tasks) {
        throw new Error('formal task capacity is exhausted');
      }
      this.#tasks.set(task.task_id, task);
    } else if (operation === 'task.events') {
      if (context.events_query === null) throw new Error('task.events adoption context is missing');
      this.#adoptEvents(result, context.events_query);
    } else {
      if (context.command_id === null) throw new Error('formal task mutation adoption context is missing');
      const responseCommandId = productMutation === null
        ? text(result.command_id, 'result.command_id')
        : text(productMutation.command_id, 'product mutation command_id');
      if (responseCommandId !== context.command_id) {
        throw new Error('formal task mutation response command binding mismatch');
      }
      const submitted = this.#submittedMutations.get(responseCommandId);
      if (submitted === undefined || submitted.operation !== operation) {
        throw new Error('formal task mutation response has no exact submitted binding');
      }
      let responseState: FormalTaskState | null = null;
      let responseOutboxId: string | null = null;
      let responseAttemptNumber: number | null = null;
      let responsePreviousAttemptId: string | null = null;
      if (productMutation !== null) {
        const responseTargetTaskId = productMutation.target_task_id === null
          ? null
          : text(productMutation.target_task_id, 'product mutation target_task_id');
        if (responseTargetTaskId !== submitted.target_task_id) {
          throw new Error('formal task mutation response target binding mismatch');
        }
        if (
          Object.prototype.hasOwnProperty.call(result, 'operation')
          || Object.prototype.hasOwnProperty.call(result, 'command_id')
          || Object.prototype.hasOwnProperty.call(result, 'target_task_id')
        ) {
          throw new Error('formal task mutation result contains misplaced authority fields');
        }
        responseState = canonicalTaskState(result.state);
        responseOutboxId = !Object.prototype.hasOwnProperty.call(result, 'outbox_id') || result.outbox_id === null
          ? null
          : text(result.outbox_id, 'result.outbox_id');
        if (operation === 'task.create') {
          responseAttemptNumber = Object.prototype.hasOwnProperty.call(result, 'attempt_number')
            ? attemptNumber(result.attempt_number, 'result.attempt_number')
            : 1;
          if (responseState !== 'accepted' || responseOutboxId === null || responseAttemptNumber !== 1) {
            throw new Error('formal task.create result is not an accepted durable task initial attempt');
          }
        }
        if (operation === 'task.cancel') {
          if (result.cancel_acknowledged !== true) {
            throw new Error('formal task.cancel result is not acknowledged');
          }
          if (typeof result.applied !== 'boolean') {
            throw new Error('formal task.cancel applied result is invalid');
          }
          if (!result.applied && responseOutboxId !== null) {
            throw new Error('formal task.cancel unapplied result cannot own an outbox');
          }
          if (
            result.applied
            && ((responseState === 'terminal') !== (responseOutboxId === null))
          ) {
            throw new Error('formal task.cancel applied result has an invalid durable outbox');
          }
          if (
            Object.prototype.hasOwnProperty.call(result, 'attempt_number')
            && attemptNumber(result.attempt_number, 'result.attempt_number') !== submitted.target_attempt_number
          ) {
            throw new Error('formal task.cancel result attempt number mismatch');
          }
        }
        if (operation === 'task.retry') {
          responseAttemptNumber = attemptNumber(result.attempt_number, 'result.attempt_number');
          responsePreviousAttemptId = text(result.previous_attempt_id, 'result.previous_attempt_id');
          if (
            result.applied !== true
            || responseState !== 'accepted'
            || responseOutboxId === null
            || responsePreviousAttemptId !== submitted.target_attempt_id
            || submitted.target_attempt_number === null
            || responseAttemptNumber !== submitted.target_attempt_number + 1
            || responseAttemptNumber > 3
          ) {
            throw new Error('formal task.retry result lineage is invalid');
          }
        }
      }
      const taskId = text(result.task_id, 'result.task_id');
      const attemptId = text(result.attempt_id, 'result.attempt_id');
      if (submitted.adopted_task_id !== null || submitted.adopted_attempt_id !== null) {
        if (
          submitted.adopted_task_id !== taskId
          || submitted.adopted_attempt_id !== attemptId
          || submitted.adopted_state !== responseState
          || submitted.adopted_outbox_id !== responseOutboxId
        ) {
          throw new Error('formal task mutation replay conflicts with its adopted result');
        }
        // A command-ledger replay may arrive after the task has advanced to a
        // later attempt.  The original result is accepted as a receipt only and
        // must never roll the current replica back to that historical attempt.
        return this.snapshot();
      }
      const existing = this.#tasks.get(taskId);
      if ((operation === 'task.cancel' || operation === 'task.retry') && existing === undefined) {
        throw new Error(`${operation} result targets an unobserved formal task`);
      }
      if (
        (operation === 'task.cancel' || operation === 'task.retry')
        && (
          taskId !== submitted.target_task_id
          || existing?.attempt_id !== submitted.target_attempt_id
        )
      ) {
        throw new Error(`${operation} result attempt binding mismatch`);
      }
      if (operation === 'task.cancel' && attemptId !== submitted.target_attempt_id) {
        throw new Error('task.cancel result attempt binding mismatch');
      }
      if (operation === 'task.retry' && (attemptId === submitted.target_attempt_id || responsePreviousAttemptId !== submitted.target_attempt_id)) {
        throw new Error('task.retry result attempt binding mismatch');
      }
      if (operation !== 'task.retry' && existing !== undefined && existing.attempt_id !== null && existing.attempt_id !== attemptId) {
        throw new Error('formal task mutation result conflicts with the observed task attempt');
      }
      if (existing === undefined && this.#tasks.size >= FORMAL_TASK_CONTROL_LIMITS.max_tasks) {
        throw new Error('formal task capacity is exhausted');
      }
      const adoptedBinding: SubmittedMutationBinding = Object.freeze({
        ...submitted,
        adopted_task_id: taskId,
        adopted_attempt_id: attemptId,
        adopted_state: responseState,
        adopted_outbox_id: responseOutboxId,
      });
      if (existing === undefined) {
        const task: FormalTaskControlRecord = Object.freeze({
          task_id: taskId,
          attempt_id: attemptId,
          attempt_number: responseAttemptNumber,
          state: responseState,
          outcome: null,
          event_head: null,
          last_event_id: null,
          last_event_seq: null,
        });
        this.#submittedMutations.set(responseCommandId, adoptedBinding);
        this.#tasks.set(taskId, task);
      } else if (operation === 'task.retry') {
        this.#submittedMutations.set(responseCommandId, adoptedBinding);
        this.#tasks.set(taskId, Object.freeze({
          task_id: taskId,
          attempt_id: attemptId,
          attempt_number: responseAttemptNumber,
          state: responseState,
          outcome: null,
          // The accepted retry result advances the authoritative attempt but does
          // not carry an event cursor.  Discard the predecessor cursor so a
          // caller must rebuild the replica from a complete task.events history.
          event_head: null,
          last_event_id: null,
          last_event_seq: null,
        }));
      } else {
        this.#submittedMutations.set(responseCommandId, adoptedBinding);
      }
    }
    return this.snapshot();
  }

  adoptProgress(
    origin: FormalTaskProgressOrigin,
    connectionGeneration: number,
  ): FormalTaskControlSnapshot {
    if (!this.#enabled) throw new Error('formal task control is disabled');
    if (!this.#connected) throw new Error('formal task control is disconnected');
    if (
      !Number.isSafeInteger(connectionGeneration)
      || connectionGeneration !== this.#connectionGeneration
    ) {
      throw new Error('formal progress belongs to a stale connection');
    }
    const record = this.#tasks.get(text(origin.task_id, 'progress.task_id'));
    if (
      record === undefined ||
      origin.correlation_id !== this.#binding.correlation_id ||
      origin.source_event_id !== record.last_event_id ||
      origin.source_event_seq !== record.last_event_seq ||
      origin.progress_causation_id !== origin.source_event_id ||
      origin.state !== record.state ||
      origin.outcome !== record.outcome ||
      (origin.state === 'terminal') !== (origin.outcome !== null)
    ) {
      throw new Error('formal progress origin binding mismatch');
    }
    const receipt = text(origin.progress_event_id, 'progress.progress_event_id');
    const retainedSource = this.#progressReceipts.get(receipt);
    if (retainedSource !== undefined && retainedSource !== origin.source_event_id) {
      throw new Error('formal progress receipt conflicts with its TaskEvent source');
    }
    if (
      retainedSource === undefined
      && this.#progressReceipts.size >= FORMAL_TASK_CONTROL_LIMITS.max_progress_receipts
    ) {
      throw new Error('formal progress receipt capacity is exhausted');
    }
    this.#progressReceipts.set(receipt, origin.source_event_id);
    return this.snapshot();
  }

  #adoptEvents(result: JsonObject, contextInput: FormalTaskEventsQueryContext | undefined): void {
    if (!Array.isArray(result.events)) throw new Error('task.events result is invalid');
    if (result.events.length > FORMAL_TASK_CONTROL_LIMITS.max_events_per_response) {
      throw new Error('task.events result exceeds the formal event capacity');
    }
    if (contextInput === undefined) throw new Error('task.events query context is required');
    const taskId = text(contextInput.task_id, 'task.events.task_id');
    const afterSeq = contextInput.after_seq;
    if (!Number.isSafeInteger(afterSeq) || afterSeq < -1) {
      throw new Error('task.events.after_seq is invalid');
    }
    const responseTaskId = text(result.task_id, 'task.events.result.task_id');
    const responseAfterSeq = result.after_seq;
    if (
      !Number.isSafeInteger(responseAfterSeq)
      || Number(responseAfterSeq) < -1
      || responseTaskId !== taskId
      || Number(responseAfterSeq) !== afterSeq
    ) {
      throw new Error('task.events response query binding mismatch');
    }
    const head = nonNegativeInteger(result.head_seq, 'task.events.head_seq');
    if (afterSeq > head) {
      throw new Error('task.events cursor exceeds the authoritative head');
    }
    const existing = this.#tasks.get(taskId);
    if (existing === undefined && this.#tasks.size >= FORMAL_TASK_CONTROL_LIMITS.max_tasks) {
      throw new Error('formal task capacity is exhausted');
    }
    if (
      afterSeq !== -1
      && (
        existing === undefined
        || existing.last_event_seq !== afterSeq
        || existing.state === null
      )
    ) {
      throw new Error('task.events cursor does not bind the observed task replica');
    }
    if (existing !== undefined && existing.event_head !== null && head < existing.event_head) {
      throw new Error('task.events head cannot move backwards');
    }
    if (afterSeq < head && result.events.length === 0) {
      throw new Error('task.events result omits events after its cursor');
    }
    if (result.events.length > 0 && afterSeq >= head) {
      throw new Error('task.events result contains events beyond its head or cursor');
    }
    let selected: FormalTaskControlRecord | null = null;
    let previous = afterSeq;
    let previousState: FormalTaskState | null = afterSeq === -1 ? null : existing?.state ?? null;
    let previousOutcome: string | null = afterSeq === -1 ? null : existing?.outcome ?? null;
    let previousAttemptId: string | null = afterSeq === -1 ? null : existing?.attempt_id ?? null;
    let previousAttemptNumber: number | null = afterSeq === -1 ? null : existing?.attempt_number ?? null;
    const eventIds = new Set<string>();
    for (const value of result.events) {
      const event = objectValue(value);
      if (event === null) throw new Error('task event is invalid');
      requireScope(event.scope, this.#binding);
      const eventTaskId = text(event.task_id, 'event.task_id');
      const attemptId = text(event.attempt_id, 'event.attempt_id');
      const seq = nonNegativeInteger(event.seq, 'event.seq');
      const eventId = text(event.event_id, 'event.event_id');
      if (
        eventTaskId !== taskId ||
        event.correlation_id !== this.#binding.correlation_id ||
        seq !== previous + 1 ||
        eventIds.has(eventId)
      ) {
        throw new Error('task event sequence or origin binding mismatch');
      }
      eventIds.add(eventId);
      const state = canonicalTaskState(event.state);
      const outcome = event.outcome === null ? null : text(event.outcome, 'event.outcome');
      if ((state === 'terminal') !== (outcome !== null)) {
        throw new Error('task event terminal outcome mismatch');
      }
      const eventType = text(event.event_type, 'event.event_type');
      const nextAttemptNumber = validateEventProvenance(
        event,
        seq,
        state,
        outcome,
        previousState,
        previousOutcome,
        previousAttemptId,
        previousAttemptNumber,
      );
      if (
        (previousAttemptId === null && (seq !== 0 || eventType !== 'task.accepted' || nextAttemptNumber !== 1))
        || (previousAttemptId !== null && eventType !== 'task.retry_accepted' && attemptId !== previousAttemptId)
      ) {
        throw new Error('task event attempt segment binding mismatch');
      }
      selected = Object.freeze({
        task_id: eventTaskId,
        attempt_id: attemptId,
        attempt_number: nextAttemptNumber,
        state,
        outcome,
        event_head: head,
        last_event_id: eventId,
        last_event_seq: seq,
      });
      previous = seq;
      previousState = state;
      previousOutcome = outcome;
      previousAttemptId = attemptId;
      previousAttemptNumber = nextAttemptNumber;
    }
    if (selected !== null) {
      if (selected.last_event_seq !== head) throw new Error('task.events head mismatch');
      if (
        existing !== undefined &&
        afterSeq !== -1 && existing.last_event_seq !== null && existing.last_event_seq !== afterSeq
      ) {
        throw new Error('task.events result conflicts with observed task truth');
      }
      if (afterSeq === -1 && existing !== undefined && existing.event_head === head) {
        const summaryConflict = (
          existing.attempt_id !== selected.attempt_id
          || (existing.attempt_number !== null && existing.attempt_number !== selected.attempt_number)
          || existing.state !== selected.state
          || existing.outcome !== selected.outcome
        );
        const cursorConflict = existing.last_event_seq !== null && (
          existing.last_event_id !== selected.last_event_id
          || existing.last_event_seq !== selected.last_event_seq
        );
        if (summaryConflict || cursorConflict) {
          throw new Error('task.events replay conflicts with observed task truth');
        }
      }
      this.#tasks.set(selected.task_id, selected);
    } else {
      this.#tasks.set(
        taskId,
        Object.freeze({
          task_id: taskId,
          attempt_id: existing?.attempt_id ?? null,
          attempt_number: existing?.attempt_number ?? null,
          state: existing?.state ?? null,
          outcome: existing?.outcome ?? null,
          event_head: head,
          last_event_id: existing?.last_event_id ?? null,
          last_event_seq: existing?.last_event_seq ?? null,
        })
      );
    }
  }
}
