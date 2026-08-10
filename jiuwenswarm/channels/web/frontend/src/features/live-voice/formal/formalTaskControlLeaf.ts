export const FORMAL_TASK_CONTROL_OPERATIONS = Object.freeze(['task.create', 'task.get', 'task.list', 'task.status', 'task.cancel', 'task.events'] as const);

export const FORMAL_TASK_CONTROL_LIMITS = Object.freeze({
  max_text_chars: 4_096,
  max_tasks: 256,
  max_events_per_response: 256,
  max_retained_event_identities: 65_536,
  max_mutation_receipts: 512,
  max_progress_receipts: 512,
  max_pending_mutations: 64,
} as const);

export type FormalTaskControlOperation = (typeof FORMAL_TASK_CONTROL_OPERATIONS)[number];
export type FormalTaskCancelScope = 'playback.stop' | 'response.cancel' | 'round.cancel' | 'task.cancel';
export type FormalTaskState = 'accepted' | 'running' | 'blocked' | 'decision_required' | 'terminal';
export type FormalTerminalOutcome = 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown';

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
  /**
   * The Task's authoritative correlation, or `null` while still unconfirmed.
   * A mutation result does not carry one, so it must never be inferred from
   * the local control binding: every read path enforces this field by
   * equality, and one inferred value that later disagreed with Task Core would
   * fail `task.list` permanently for the entire scope.
   */
  readonly correlation_id: string | null;
  readonly state: FormalTaskState | null;
  readonly outcome: FormalTerminalOutcome | null;
  readonly event_head: number | null;
  readonly last_event_id: string | null;
  readonly last_event_seq: number | null;
}

export interface FormalTaskMutationInput {
  readonly operation: 'task.create' | 'task.cancel';
  readonly command_id: string;
  readonly task_id: string | null;
}

export interface FormalTaskConfirmationReceipt {
  readonly confirmation_id: string;
  readonly operation: 'task.create' | 'task.cancel';
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
  readonly outcome: FormalTerminalOutcome | null;
}

export interface FormalTaskEventsQueryContext {
  readonly task_id: string;
  readonly after_seq: number;
}

export interface FormalTaskAdoptionContext {
  readonly connection_generation: number;
  readonly command_id: string | null;
  readonly query_task_id: string | null;
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

function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const record = objectValue(value);
  if (record === null) throw new Error('task event contains a non-JSON identity value');
  return `{${Object.keys(record).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`;
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
  const expectedContextKeys = ['command_id', 'connection_generation', 'events_query', 'query_task_id'];
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
  const queryTaskId = context.query_task_id === null ? null : text(context.query_task_id, 'adoption.query_task_id');
  const events = context.events_query === null ? null : objectValue(context.events_query);
  if (
    (operation === 'task.create' || operation === 'task.cancel') !== (commandId !== null)
    || (operation === 'task.get' || operation === 'task.status') !== (queryTaskId !== null)
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
    query_task_id: queryTaskId,
    events_query: eventsQuery,
  });
}

interface SubmittedMutationBinding {
  readonly operation: 'task.create' | 'task.cancel';
  readonly command_id: string;
  readonly target_task_id: string | null;
  readonly target_attempt_id: string | null;
  readonly adopted_task_id: string | null;
  readonly adopted_attempt_id: string | null;
}

const PROJECT_CODE_EXECUTOR_ID = 'jiuwenswarm_code_agent.project_code';
type FormalAttemptState = 'accepted' | 'running' | 'terminal';

interface FormalTaskEventCheckpoint {
  readonly task_state: FormalTaskState;
  readonly task_outcome: FormalTerminalOutcome | null;
  readonly attempt_state: FormalAttemptState | null;
  readonly attempt_outcome: FormalTerminalOutcome | null;
  readonly expected_task_type: 'task.running' | 'task.terminal' | null;
  readonly expected_task_producers: readonly string[];
  readonly expected_task_source: string | null;
  readonly expected_task_cause: string | null;
  readonly expected_task_outcome: FormalTerminalOutcome | null;
}
const EVENT_TYPE_STATE = Object.freeze({
  'task.accepted': 'accepted',
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
): boolean {
  if (previous === null) return next === 'accepted';
  if (previous === 'terminal') return next === 'terminal';
  if (previous === 'accepted') return ['accepted', 'running', 'blocked', 'decision_required', 'terminal'].includes(next);
  return ['running', 'blocked', 'decision_required', 'terminal'].includes(next);
}

function validTaskEventTransition(previous: FormalTaskState, next: FormalTaskState): boolean {
  if (previous === 'accepted') return ['running', 'blocked', 'decision_required', 'terminal'].includes(next);
  if (previous === 'running') return ['blocked', 'decision_required', 'terminal'].includes(next);
  if (previous === 'blocked') return ['running', 'decision_required', 'terminal'].includes(next);
  if (previous === 'decision_required') return ['running', 'blocked', 'terminal'].includes(next);
  return false;
}

function validateEventProvenance(
  event: JsonObject,
  seq: number,
  state: FormalTaskState,
  outcome: FormalTerminalOutcome | null,
  previous: FormalTaskEventCheckpoint | null,
): FormalTaskEventCheckpoint {
  const eventType = text(event.event_type, 'event.event_type');
  const producer = text(event.producer, 'event.producer');
  const sourceEventId = event.source_event_id === null
    ? null
    : text(event.source_event_id, 'event.source_event_id');
  const causationId = text(event.causation_id, 'event.causation_id');
  const expectedState = EVENT_TYPE_STATE[eventType as keyof typeof EVENT_TYPE_STATE];
  const cancelRequested = eventType === 'task.cancel_requested';
  if (expectedState === undefined && !cancelRequested) {
    throw new Error('task event type is outside the closed lifecycle vocabulary');
  }
  if (
    (expectedState !== undefined && state !== expectedState)
    || (seq === 0 && eventType !== 'task.accepted')
    || (seq !== 0 && eventType === 'task.accepted')
  ) {
    throw new Error('task event lifecycle is self-contradictory');
  }
  const taskProducerValid = (
    (eventType === 'task.accepted' && producer === 'task_core')
    || (eventType === 'task.running' && producer === 'task_core')
    || (eventType === 'task.blocked' && producer === 'task_core')
    || (eventType === 'task.decision_required' && producer === 'task_core')
    || (eventType === 'task.cancel_requested' && producer === 'task_core.control')
    || (eventType === 'task.terminal' && ['task_core', 'task_core.delivery', 'task_core.reconciliation'].includes(producer))
  );
  const attemptProducerValid = eventType.startsWith('attempt.')
    && (
      [PROJECT_CODE_EXECUTOR_ID, 'task_core.reconciliation'].includes(producer)
      || (eventType === 'attempt.terminal' && producer === 'task_core.delivery')
    );
  if (!taskProducerValid && !attemptProducerValid) {
    throw new Error('task event producer is not authoritative for its event type');
  }
  if (
    ((eventType === 'task.accepted' || eventType === 'task.cancel_requested') && sourceEventId !== null)
    || (
      eventType.startsWith('attempt.')
      && producer === PROJECT_CODE_EXECUTOR_ID
      && (sourceEventId === null || causationId !== sourceEventId)
    )
    || (
      eventType.startsWith('attempt.')
      && producer !== PROJECT_CODE_EXECUTOR_ID
      && sourceEventId !== null
    )
  ) {
    throw new Error('task event source and causation provenance mismatch');
  }

  if (previous?.expected_task_type !== null && previous?.expected_task_type !== undefined) {
    if (
      eventType !== previous.expected_task_type
      || !previous.expected_task_producers.includes(producer)
      || sourceEventId !== previous.expected_task_source
      || causationId !== previous.expected_task_cause
      || outcome !== previous.expected_task_outcome
    ) {
      throw new Error('attempt lifecycle event lacks its exact consecutive task lifecycle event');
    }
  }

  if (eventType.startsWith('task.')) {
    if (cancelRequested) {
      if (
        previous === null
        || previous.task_state === 'terminal'
        || state !== previous.task_state
        || outcome !== previous.task_outcome
      ) {
        throw new Error('task event lifecycle is self-contradictory');
      }
      return previous;
    }
    if (eventType === 'task.accepted') {
      if (previous !== null || outcome !== null) {
        throw new Error('task event lifecycle is self-contradictory');
      }
      return Object.freeze({
        task_state: 'accepted',
        task_outcome: null,
        attempt_state: 'accepted',
        attempt_outcome: null,
        expected_task_type: null,
        expected_task_producers: Object.freeze([]),
        expected_task_source: null,
        expected_task_cause: null,
        expected_task_outcome: null,
      });
    }
    if (previous === null || !validTaskEventTransition(previous.task_state, state)) {
      throw new Error('task event lifecycle is self-contradictory');
    }
    const coupled = previous.expected_task_type !== null;
    if (
      (['running', 'blocked', 'decision_required'].includes(state) && previous.attempt_state !== 'running')
      || (
        state === 'terminal'
        && (
          previous.attempt_state !== 'terminal'
          || previous.attempt_outcome !== outcome
          || !coupled
        )
      )
    ) {
      throw new Error('task lifecycle disagrees with its canonical attempt truth');
    }
    return Object.freeze({
      task_state: state,
      task_outcome: outcome,
      attempt_state: previous.attempt_state,
      attempt_outcome: previous.attempt_outcome,
      expected_task_type: null,
      expected_task_producers: Object.freeze([]),
      expected_task_source: null,
      expected_task_cause: null,
      expected_task_outcome: null,
    });
  }

  if (previous === null) throw new Error('attempt event precedes canonical task truth');
  const priorAttempt = previous.attempt_state;
  const validAttemptTransition = (
    (state === 'accepted' && priorAttempt === 'accepted')
    || (state === 'running' && priorAttempt === 'accepted')
    || (state === 'terminal' && ['accepted', 'running'].includes(priorAttempt ?? ''))
  );
  if (
    !validAttemptTransition
    || (['accepted', 'running'].includes(state) && producer !== PROJECT_CODE_EXECUTOR_ID)
    || (state === 'terminal' && priorAttempt === 'accepted' && producer === PROJECT_CODE_EXECUTOR_ID)
    || (state === 'terminal' && ![PROJECT_CODE_EXECUTOR_ID, 'task_core.delivery', 'task_core.reconciliation'].includes(producer))
  ) {
    throw new Error('attempt event lifecycle is self-contradictory');
  }
  const terminal = state === 'terminal';
  return Object.freeze({
    task_state: previous.task_state,
    task_outcome: previous.task_outcome,
    attempt_state: state as FormalAttemptState,
    attempt_outcome: outcome,
    expected_task_type: terminal ? 'task.terminal' : state === 'running' ? 'task.running' : null,
    expected_task_producers: Object.freeze(
      !terminal
        ? ['task_core']
        : producer === PROJECT_CODE_EXECUTOR_ID
          ? ['task_core']
          : producer === 'task_core.delivery'
            ? ['task_core.delivery']
            : ['task_core', 'task_core.reconciliation'],
    ),
    expected_task_source: state === 'accepted' ? null : sourceEventId,
    expected_task_cause: state === 'accepted' ? null : causationId,
    expected_task_outcome: terminal ? outcome : null,
  });
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) {
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

function canonicalTerminalOutcome(value: unknown, field: string): FormalTerminalOutcome {
  if (!(['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const).includes(value as FormalTerminalOutcome)) {
    throw new Error(`${field} is outside the closed terminal outcome vocabulary`);
  }
  return value as FormalTerminalOutcome;
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

function parseTask(value: unknown, binding: FormalTaskControlBinding): FormalTaskControlRecord {
  const task = objectValue(value);
  if (task === null) throw new Error('task result is invalid');
  requireScope(task.scope, binding);
  const state = canonicalTaskState(task.state);
  const outcome = task.outcome === null ? null : canonicalTerminalOutcome(task.outcome, 'task.outcome');
  if ((state === 'terminal') !== (outcome !== null)) {
    throw new Error('task terminal outcome mismatch');
  }
  return Object.freeze({
    task_id: text(task.task_id, 'task_id'),
    attempt_id: text(task.attempt_id, 'attempt_id'),
    correlation_id: text(task.correlation_id, 'task.correlation_id'),
    state,
    outcome,
    event_head: nonNegativeInteger(task.event_head, 'task.event_head'),
    last_event_id: null,
    last_event_seq: null,
  });
}

function mergeObservedTask(
  existing: FormalTaskControlRecord | undefined,
  next: FormalTaskControlRecord,
): FormalTaskControlRecord {
  if (existing === undefined) return next;
  if (
    (existing.correlation_id !== null && existing.correlation_id !== next.correlation_id)
    || (existing.attempt_id !== null && existing.attempt_id !== next.attempt_id)
    || (existing.event_head !== null && next.event_head !== null && next.event_head < existing.event_head)
  ) {
    throw new Error('formal task query conflicts with retained task identity or event head');
  }
  if (
    existing.state !== null
    && next.state !== null
    && (
      !validTaskStateTransition(existing.state, next.state)
      || (existing.state === 'terminal' && existing.outcome !== next.outcome)
      || (
        existing.event_head === next.event_head
        && (existing.state !== next.state || existing.outcome !== next.outcome)
      )
    )
  ) {
    throw new Error('formal task query conflicts with retained lifecycle truth');
  }
  const sameHead = existing.event_head === next.event_head;
  return Object.freeze({
    ...next,
    last_event_id: sameHead ? existing.last_event_id : null,
    last_event_seq: sameHead ? existing.last_event_seq : null,
  });
}

function queryResult(value: unknown): JsonObject {
  const payload = objectValue(value);
  const result = objectValue(payload?.result);
  if (payload?.ok !== true || result === null) {
    throw new Error('formal task query result is unavailable');
  }
  return result;
}

function queryBindingCandidate(operation: Exclude<FormalTaskControlOperation, 'task.create' | 'task.cancel'>, response: unknown): JsonObject | null {
  const result = queryResult(response);
  if (operation === 'task.list') {
    if (!Array.isArray(result.tasks)) throw new Error('task.list result is invalid');
    if (result.tasks.length === 0) return null;
    const first = objectValue(result.tasks[0]);
    if (first === null) throw new Error('task.list result is invalid');
    return first;
  }
  if (operation === 'task.get' || operation === 'task.status') {
    const task = objectValue(result.task);
    if (task === null) throw new Error(`formal ${operation} task is invalid`);
    return task;
  }
  if (!Array.isArray(result.events)) throw new Error('task.events result is invalid');
  if (result.events.length === 0) return null;
  const event = objectValue(result.events[0]);
  if (event === null) throw new Error('task.events result is invalid');
  return event;
}

/** Derive only the exact authenticated task binding returned by Task Core. */
export function deriveFormalTaskQueryBinding(
  input: Readonly<{
    operation: Exclude<FormalTaskControlOperation, 'task.create' | 'task.cancel'>;
    response: unknown;
    expected_session_id: string;
    generation: number;
  }>,
): FormalTaskControlBinding | null {
  const candidate = queryBindingCandidate(input.operation, input.response);
  if (candidate === null) return null;
  const scope = objectValue(candidate.scope);
  if (scope === null || scope.assurance !== 'authenticated' || scope.session_id !== input.expected_session_id || Object.keys(scope).sort().join(',') !== 'assurance,project_id,session_id,subject_id') {
    throw new Error('formal task query scope binding mismatch');
  }
  const correlationId = text(candidate.correlation_id, 'task.correlation_id');
  const binding = freezeBinding({
    subject_id: text(scope.subject_id, 'scope.subject_id'),
    session_id: text(scope.session_id, 'scope.session_id'),
    project_id: text(scope.project_id, 'scope.project_id'),
    correlation_id: correlationId,
    generation: input.generation,
  });
  const result = queryResult(input.response);
  const values = input.operation === 'task.list' ? result.tasks : input.operation === 'task.events' ? result.events : [result.task];
  if (!Array.isArray(values)) throw new Error('formal task query result is invalid');
  for (const value of values) {
    const record = objectValue(value);
    if (record === null) throw new Error('formal task query record is invalid');
    requireScope(record.scope, binding);
    if (input.operation === 'task.events' && record.correlation_id !== correlationId) {
      throw new Error('task.events contains cross-correlation facts');
    }
  }
  return binding;
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

function normalizeFormalTaskMutation(
  bindingInput: FormalTaskControlBinding,
  mutationInput: FormalTaskMutationInput,
  confirmationInput: FormalTaskConfirmationReceipt,
  requireFreshConfirmation: boolean,
): PreparedFormalTaskMutation {
  const binding = freezeBinding(bindingInput);
  const operation = mutationInput.operation;
  const commandId = text(mutationInput.command_id, 'command_id');
  const taskId = mutationInput.task_id === null ? null : text(mutationInput.task_id, 'task_id');
  if ((operation === 'task.create') !== (taskId === null)) {
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
    (requireFreshConfirmation && Date.parse(confirmation.expires_at) <= Date.now())
  ) {
    throw new Error('formal task confirmation binding mismatch');
  }
  return Object.freeze({
    binding,
    mutation: Object.freeze({ operation, command_id: commandId, task_id: taskId }),
    confirmation,
  });
}

export function prepareFormalTaskMutation(
  bindingInput: FormalTaskControlBinding,
  mutationInput: FormalTaskMutationInput,
  confirmationInput: FormalTaskConfirmationReceipt
): PreparedFormalTaskMutation {
  return normalizeFormalTaskMutation(bindingInput, mutationInput, confirmationInput, true);
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
  readonly #eventIdentities = new Map<string, Readonly<{ task_id: string; fingerprint: string }>>();
  readonly #eventSequences = new Map<string, Readonly<{ event_id: string; fingerprint: string }>>();
  readonly #eventCheckpoints = new Map<string, FormalTaskEventCheckpoint>();

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

  /**
   * Transfer only one observed exact task replica to a fresh server-confirmed
   * mutation binding. This changes no Task truth and cannot widen Session or
   * project scope.
   */
  rebindConfirmedMutation(bindingInput: FormalTaskControlBinding, taskIdInput: string): FormalTaskControlLeaf {
    const binding = freezeBinding(bindingInput);
    const taskId = text(taskIdInput, 'task_id');
    if (!this.#connected) {
      throw new Error('formal task mutation rebind requires a connected observed replica');
    }
    if (binding.subject_id !== this.#binding.subject_id || binding.session_id !== this.#binding.session_id || binding.project_id !== this.#binding.project_id) {
      throw new Error('formal task mutation rebind cannot cross scope');
    }
    if (this.#pendingMutationCommands.size > 0 || this.#pendingConfirmations.size > 0) {
      throw new Error('formal task mutation rebind is unavailable while a mutation is pending');
    }
    const task = this.#tasks.get(taskId);
    if (task === undefined || task.attempt_id === null) {
      throw new Error('formal task mutation rebind requires an observed exact task attempt');
    }
    const next = new FormalTaskControlLeaf({ enabled: this.#enabled, binding });
    next.#tasks.set(taskId, task);
    const checkpoint = this.#eventCheckpoints.get(taskId);
    if (checkpoint !== undefined) next.#eventCheckpoints.set(taskId, checkpoint);
    for (const [eventId, identity] of this.#eventIdentities) {
      if (identity.task_id === taskId) next.#eventIdentities.set(eventId, identity);
    }
    for (const [sequenceKey, identity] of this.#eventSequences) {
      if (sequenceKey.startsWith(`${taskId}\0`)) next.#eventSequences.set(sequenceKey, identity);
    }
    this.disconnect();
    return next;
  }

  /** Move the complete durable query replica to a newer transport generation. */
  rebindQueryReplica(bindingInput: FormalTaskControlBinding): FormalTaskControlLeaf {
    const candidate = freezeBinding(bindingInput);
    if (
      candidate.subject_id !== this.#binding.subject_id
      || candidate.session_id !== this.#binding.session_id
      || candidate.project_id !== this.#binding.project_id
      || candidate.generation <= this.#binding.generation
    ) {
      throw new Error('formal task query rebind cannot cross scope or move backwards');
    }
    if (this.#pendingMutationCommands.size > 0 || this.#pendingConfirmations.size > 0) {
      throw new Error('formal task query rebind is unavailable while a mutation is pending');
    }
    const next = new FormalTaskControlLeaf({
      enabled: this.#enabled,
      binding: Object.freeze({ ...this.#binding, generation: candidate.generation }),
    });
    for (const [taskId, task] of this.#tasks) next.#tasks.set(taskId, task);
    for (const commandId of this.#mutationReceipts) next.#mutationReceipts.add(commandId);
    for (const confirmationId of this.#confirmationReceipts) next.#confirmationReceipts.add(confirmationId);
    for (const [commandId, submitted] of this.#submittedMutations) next.#submittedMutations.set(commandId, submitted);
    for (const [receipt, source] of this.#progressReceipts) next.#progressReceipts.set(receipt, source);
    for (const [eventId, identity] of this.#eventIdentities) next.#eventIdentities.set(eventId, identity);
    for (const [sequenceKey, identity] of this.#eventSequences) next.#eventSequences.set(sequenceKey, identity);
    for (const [taskId, checkpoint] of this.#eventCheckpoints) next.#eventCheckpoints.set(taskId, checkpoint);
    this.disconnect();
    return next;
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
      normalized.mutation.operation === 'task.cancel'
      && (targetTask === null || targetTask === undefined || targetTask.attempt_id === null)
    ) {
      throw new Error('formal task cancellation requires an observed exact task attempt');
    }
    const connectionGeneration = this.#connectionGeneration;
    const retained: SubmittedMutationBinding = Object.freeze({
      operation: normalized.mutation.operation,
      command_id: commandId,
      target_task_id: normalized.mutation.task_id,
      target_attempt_id: targetTask?.attempt_id ?? null,
      adopted_task_id: null,
      adopted_attempt_id: null,
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

  /** Re-adopt one exact server-processed result without replaying its business request. */
  adoptRetainedMutationResult(
    prepared: PreparedFormalTaskMutation,
    response: unknown,
    connectionGeneration: number,
  ): FormalTaskControlSnapshot {
    if (!this.#enabled) throw new Error('formal task control is disabled');
    if (!this.#connected) throw new Error('formal task control is disconnected');
    if (connectionGeneration !== this.#connectionGeneration) {
      throw new Error('formal task mutation result belongs to a stale connection');
    }
    const normalized = normalizeFormalTaskMutation(
      prepared.binding,
      prepared.mutation,
      prepared.confirmation,
      false,
    );
    if (!sameBinding(normalized.binding, this.#binding)) {
      throw new Error('formal task mutation binding mismatch');
    }
    const commandId = normalized.mutation.command_id;
    const confirmationId = normalized.confirmation.confirmation_id;
    const targetTask = normalized.mutation.task_id === null
      ? null
      : this.#tasks.get(normalized.mutation.task_id);
    if (
      normalized.mutation.operation === 'task.cancel'
      && (targetTask === null || targetTask === undefined || targetTask.attempt_id === null)
    ) {
      throw new Error('formal task cancellation requires an observed exact task attempt');
    }
    const retained: SubmittedMutationBinding = Object.freeze({
      operation: normalized.mutation.operation,
      command_id: commandId,
      target_task_id: normalized.mutation.task_id,
      target_attempt_id: targetTask?.attempt_id ?? null,
      adopted_task_id: null,
      adopted_attempt_id: null,
    });
    const existing = this.#submittedMutations.get(commandId);
    if (
      existing !== undefined
      && (
        existing.operation !== retained.operation
        || existing.target_task_id !== retained.target_task_id
        || existing.target_attempt_id !== retained.target_attempt_id
      )
    ) {
      throw new Error('retained formal task mutation conflicts with submitted truth');
    }
    const addsCommand = !this.#mutationReceipts.has(commandId);
    const addsConfirmation = !this.#confirmationReceipts.has(confirmationId);
    if (
      (addsCommand || addsConfirmation || existing === undefined)
      && (
        this.#mutationReceipts.size >= FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts
        || this.#confirmationReceipts.size >= FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts
        || this.#submittedMutations.size >= FORMAL_TASK_CONTROL_LIMITS.max_mutation_receipts
      )
    ) {
      throw new Error('formal task mutation receipt capacity is exhausted');
    }
    if (addsCommand) this.#mutationReceipts.add(commandId);
    if (addsConfirmation) this.#confirmationReceipts.add(confirmationId);
    if (existing === undefined) this.#submittedMutations.set(commandId, retained);
    try {
      return this.adopt(normalized.mutation.operation, response, {
        connection_generation: connectionGeneration,
        command_id: commandId,
        query_task_id: null,
        events_query: null,
      });
    } catch (error) {
      if (addsCommand) this.#mutationReceipts.delete(commandId);
      if (addsConfirmation) this.#confirmationReceipts.delete(confirmationId);
      if (existing === undefined) this.#submittedMutations.delete(commandId);
      throw error;
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
      (operation === 'task.create' || operation === 'task.cancel') && payload?.status === 'mutation_processed' && payload.operation === operation
        ? objectValue(payload.formal_task_result)
        : null;
    const result = productMutation ?? objectValue(payload?.result);
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
        const task = parseTask(value, this.#binding);
        if (next.has(task.task_id)) throw new Error('task.list contains a duplicate task');
        next.set(task.task_id, mergeObservedTask(this.#tasks.get(task.task_id), task));
      }
      for (const taskId of this.#tasks.keys()) {
        if (!next.has(taskId)) {
          throw new Error('task.list omits retained durable task truth');
        }
      }
      this.#tasks.clear();
      for (const [taskId, task] of next) this.#tasks.set(taskId, task);
    } else if (operation === 'task.get' || operation === 'task.status') {
      const task = parseTask(result.task, this.#binding);
      const attempt = objectValue(result.attempt);
      if (
        context.query_task_id !== task.task_id
        || attempt === null
        || attempt.task_id !== task.task_id
        || attempt.attempt_id !== task.attempt_id
      ) {
        throw new Error('formal task/attempt result binding mismatch');
      }
      if (!this.#tasks.has(task.task_id) && this.#tasks.size >= FORMAL_TASK_CONTROL_LIMITS.max_tasks) {
        throw new Error('formal task capacity is exhausted');
      }
      this.#tasks.set(task.task_id, mergeObservedTask(this.#tasks.get(task.task_id), task));
    } else if (operation === 'task.events') {
      if (context.events_query === null) throw new Error('task.events adoption context is missing');
      this.#adoptEvents(result, context.events_query);
    } else {
      if (context.command_id === null) throw new Error('formal task mutation adoption context is missing');
      const responseCommandId = text(result.command_id, 'result.command_id');
      if (responseCommandId !== context.command_id) {
        throw new Error('formal task mutation response command binding mismatch');
      }
      const submitted = this.#submittedMutations.get(responseCommandId);
      if (submitted === undefined || submitted.operation !== operation) {
        throw new Error('formal task mutation response has no exact submitted binding');
      }
      const taskId = text(result.task_id, 'result.task_id');
      const attemptId = text(result.attempt_id, 'result.attempt_id');
      const existing = this.#tasks.get(taskId);
      if (operation === 'task.cancel' && existing === undefined) {
        throw new Error('task.cancel result targets an unobserved formal task');
      }
      if (
        operation === 'task.cancel'
        && (
          taskId !== submitted.target_task_id
          || attemptId !== submitted.target_attempt_id
          || existing?.attempt_id !== submitted.target_attempt_id
        )
      ) {
        throw new Error('task.cancel result attempt binding mismatch');
      }
      if (existing !== undefined && existing.attempt_id !== null && existing.attempt_id !== attemptId) {
        throw new Error('formal task mutation result conflicts with the observed task attempt');
      }
      if (
        (submitted.adopted_task_id !== null || submitted.adopted_attempt_id !== null)
        && (submitted.adopted_task_id !== taskId || submitted.adopted_attempt_id !== attemptId)
      ) {
        throw new Error('formal task mutation replay conflicts with its adopted result');
      }
      if (existing === undefined && this.#tasks.size >= FORMAL_TASK_CONTROL_LIMITS.max_tasks) {
        throw new Error('formal task capacity is exhausted');
      }
      const adoptedBinding: SubmittedMutationBinding = Object.freeze({
        ...submitted,
        adopted_task_id: taskId,
        adopted_attempt_id: attemptId,
      });
      if (existing === undefined) {
        const task: FormalTaskControlRecord = Object.freeze({
          task_id: taskId,
          attempt_id: attemptId,
          // Task Core does not echo a correlation on a mutation result, so it
          // stays unconfirmed until an authoritative query supplies it.
          correlation_id: null,
          state: null,
          outcome: null,
          event_head: null,
          last_event_id: null,
          last_event_seq: null,
        });
        this.#submittedMutations.set(responseCommandId, adoptedBinding);
        this.#tasks.set(taskId, task);
      } else {
        this.#submittedMutations.set(responseCommandId, adoptedBinding);
      }
    }
    return this.snapshot();
  }

  /**
   * Bind one WorkProgress observation to its exact retained TaskEvent source.
   *
   * Source/conformance only: no product path calls this today. The panel's
   * progress route goes through `ProductWebP3ProgressOwner` and does not pass
   * through this leaf, so passing tests here are not evidence that product
   * progress carries authoritative TaskEvent provenance.
   */
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
    const taskId = text(origin.task_id, 'progress.task_id');
    const state = canonicalTaskState(origin.state);
    const outcome = origin.outcome === null
      ? null
      : canonicalTerminalOutcome(origin.outcome, 'progress.outcome');
    if ((state === 'terminal') !== (outcome !== null)) {
      throw new Error('formal progress terminal outcome mismatch');
    }
    const record = this.#tasks.get(taskId);
    // A record whose correlation is still unconfirmed (`null`) cannot validate
    // a progress origin, so it is rejected here until a query confirms it.
    if (
      record === undefined ||
      origin.correlation_id !== record.correlation_id ||
      origin.source_event_id !== record.last_event_id ||
      origin.source_event_seq !== record.last_event_seq ||
      origin.progress_causation_id !== origin.source_event_id ||
      state !== record.state ||
      outcome !== record.outcome
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
    let checkpoint = afterSeq === -1 ? null : this.#eventCheckpoints.get(taskId) ?? null;
    if (afterSeq !== -1 && checkpoint === null) {
      throw new Error('task.events cursor has no retained lifecycle checkpoint');
    }
    // `null` means unconfirmed, so the first authoritative event establishes it
    // rather than conflicting with it.
    let selectedCorrelationId: string | undefined = existing?.correlation_id ?? undefined;
    const projectedEventIdentities = new Map(this.#eventIdentities);
    const projectedEventSequences = new Map(this.#eventSequences);
    for (const value of result.events) {
      const event = objectValue(value);
      if (event === null) throw new Error('task event is invalid');
      requireScope(event.scope, this.#binding);
      const eventTaskId = text(event.task_id, 'event.task_id');
      const attemptId = text(event.attempt_id, 'event.attempt_id');
      const seq = nonNegativeInteger(event.seq, 'event.seq');
      const eventId = text(event.event_id, 'event.event_id');
      const eventCorrelationId = text(event.correlation_id, 'event.correlation_id');
      const expectedCorrelationId = selectedCorrelationId;
      if (
        eventTaskId !== taskId ||
        (expectedCorrelationId !== undefined && eventCorrelationId !== expectedCorrelationId) ||
        seq !== previous + 1 ||
        (selected !== null && (selected.task_id !== eventTaskId || selected.attempt_id !== attemptId))
      ) {
        throw new Error('task event sequence or origin binding mismatch');
      }
      const state = canonicalTaskState(event.state);
      const outcome = event.outcome === null ? null : canonicalTerminalOutcome(event.outcome, 'event.outcome');
      if ((state === 'terminal') !== (outcome !== null)) {
        throw new Error('task event terminal outcome mismatch');
      }
      checkpoint = validateEventProvenance(event, seq, state, outcome, checkpoint);
      const fingerprint = canonicalJson(event);
      const retainedIdentity = projectedEventIdentities.get(eventId);
      const sequenceKey = `${eventTaskId}\0${seq}`;
      const retainedSequence = projectedEventSequences.get(sequenceKey);
      if (
        retainedIdentity !== undefined
        && (
          retainedIdentity.task_id !== eventTaskId
          || retainedIdentity.fingerprint !== fingerprint
          || afterSeq !== -1
        )
      ) {
        throw new Error('task event_id was reused outside its exact retained identity');
      }
      if (retainedIdentity === undefined) {
        if (projectedEventIdentities.size >= FORMAL_TASK_CONTROL_LIMITS.max_retained_event_identities) {
          throw new Error('formal task event identity capacity is exhausted');
        }
        projectedEventIdentities.set(eventId, Object.freeze({ task_id: eventTaskId, fingerprint }));
      }
      if (
        retainedSequence !== undefined
        && (retainedSequence.event_id !== eventId || retainedSequence.fingerprint !== fingerprint)
      ) {
        throw new Error('task event sequence was reused with different canonical content');
      }
      if (retainedSequence === undefined) {
        if (projectedEventSequences.size >= FORMAL_TASK_CONTROL_LIMITS.max_retained_event_identities) {
          throw new Error('formal task event identity capacity is exhausted');
        }
        projectedEventSequences.set(sequenceKey, Object.freeze({ event_id: eventId, fingerprint }));
      }
      selected = Object.freeze({
        task_id: eventTaskId,
        attempt_id: attemptId,
        correlation_id: eventCorrelationId,
        state: checkpoint.task_state,
        outcome: checkpoint.task_outcome,
        event_head: head,
        last_event_id: eventId,
        last_event_seq: seq,
      });
      selectedCorrelationId = eventCorrelationId;
      previous = seq;
    }
    if (selected !== null) {
      if (selected.last_event_seq !== head) throw new Error('task.events head mismatch');
      if (checkpoint?.expected_task_type !== null) {
        throw new Error('attempt lifecycle event lacks its consecutive task lifecycle event');
      }
      if (
        existing !== undefined &&
        ((existing.attempt_id !== null && existing.attempt_id !== selected.attempt_id) ||
          (afterSeq !== -1 && existing.last_event_seq !== null && existing.last_event_seq !== afterSeq))
      ) {
        throw new Error('task.events result conflicts with observed task truth');
      }
      if (
        afterSeq === -1
        && existing !== undefined
        && existing.last_event_seq !== null
        && existing.event_head === head
        && (
          existing.attempt_id !== selected.attempt_id
          || existing.last_event_id !== selected.last_event_id
          || existing.last_event_seq !== selected.last_event_seq
          || existing.state !== selected.state
          || existing.outcome !== selected.outcome
        )
      ) {
        throw new Error('task.events replay conflicts with observed task truth');
      }
      if (checkpoint === null) throw new Error('task.events result has no canonical task truth');
      this.#eventIdentities.clear();
      for (const [eventId, identity] of projectedEventIdentities) this.#eventIdentities.set(eventId, identity);
      this.#eventSequences.clear();
      for (const [sequenceKey, identity] of projectedEventSequences) this.#eventSequences.set(sequenceKey, identity);
      this.#eventCheckpoints.set(taskId, checkpoint);
      this.#tasks.set(selected.task_id, selected);
    } else {
      this.#tasks.set(
        taskId,
        Object.freeze({
          task_id: taskId,
          attempt_id: existing?.attempt_id ?? null,
          correlation_id: existing?.correlation_id ?? null,
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
