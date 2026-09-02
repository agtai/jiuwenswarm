export const FORMAL_P3_TASK_METHODS = Object.freeze({
  list: 'live_voice.task.list',
  status: 'live_voice.task.status',
  events: 'live_voice.task.events',
  result: 'live_voice.task.result',
  intent: 'live_voice.composition.p3.intent',
  confirmation: 'live_voice.composition.p3.confirmation.issue',
  mutate: 'live_voice.composition.p3.mutate',
} as const);

export const FORMAL_P3_TASK_OPERATIONS = Object.freeze([
  'task.create',
  'task.update',
  'task.adjust',
  'task.reprioritize',
  'task.cancel',
  'task.create_successor',
  'task.retry',
  'task.provide_input',
  'task.pause',
  'task.resume',
] as const);

export type FormalP3TaskOperation = (typeof FORMAL_P3_TASK_OPERATIONS)[number];
export type FormalP3TaskDisplayState =
  | 'accepted'
  | 'queued'
  | 'running'
  | 'blocked'
  | 'decision_required'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'unknown';

export type FormalP3TaskCommandPhase =
  | 'idle'
  | 'issuing'
  | 'confirmation_required'
  | 'accepted'
  | 'applied'
  | 'rejected'
  | 'unknown';

export type FormalP3TaskRecord = Readonly<{
  task_id: string;
  attempt_id: string;
  attempt_number: number | null;
  correlation_id: string;
  subject_id: string;
  session_id: string;
  project_id: string;
  name: string;
  canonical_state: 'accepted' | 'running' | 'blocked' | 'decision_required' | 'terminal';
  display_state: FormalP3TaskDisplayState;
  outcome: 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown' | null;
  queued: boolean;
  admission_priority: 'low' | 'normal' | 'high' | 'urgent' | null;
  admission_reason: string | null;
  event_head: number;
  revision_number: number;
  predecessor_task_id: string | null;
  successor_task_id: string | null;
  blocking_question: string | null;
  progress: string | null;
  result_availability: 'available' | 'not_ready' | 'unavailable' | null;
  result_text: string | null;
  result_attempt_id: string | null;
  replay_event_count: number;
  replay_event_types: readonly string[];
  available_operations: readonly FormalP3TaskOperation[];
}>;

export type FormalP3TaskCommand = Readonly<{
  command_id: string;
  request_id: string | null;
  operation: FormalP3TaskOperation;
  task_id: string | null;
  attempt_id: string | null;
  event_head: number | null;
  revision_number: number | null;
  phase: FormalP3TaskCommandPhase;
  accepted: boolean;
  applied: boolean;
  terminal_outcome: FormalP3TaskRecord['outcome'];
  reason: string | null;
}>;

export type FormalP3TaskExperienceSnapshot = Readonly<{
  status: 'disabled' | 'idle' | 'loading' | 'ready' | 'failed' | 'disconnected' | 'closed';
  session_id: string | null;
  tasks: readonly FormalP3TaskRecord[];
  selected_task_id: string | null;
  collection_operations: readonly FormalP3TaskOperation[];
  command: FormalP3TaskCommand | null;
  reason: string | null;
}>;

export type FormalP3TaskMutationInput = Readonly<{
  operation: FormalP3TaskOperation;
  task_id?: string | null;
  name?: string;
  instruction?: string;
  adjustment?: string;
  priority?: 'low' | 'normal' | 'high' | 'urgent';
}>;

export type FormalP3TaskRequest = (
  method: string,
  params: Record<string, unknown>,
  requestId: string,
) => Promise<unknown>;

export type FormalP3TaskSelectionStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const SELECTION_PREFIX = 'jiuwenswarm.live_voice.formal_p3_selection.v1:';
const IDENTITY_LIMIT = 256;
const CONTENT_LIMIT = 100_000;
const TASK_LIMIT = 100;
const MAX_LIST_PAGES = 5;
const MAX_EVENT_PAGES = 10;
const OPERATIONS = new Set<string>(FORMAL_P3_TASK_OPERATIONS);
const TERMINAL_OUTCOMES = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'unknown']);
let requestSequence = 0;

type JsonObject = Record<string, unknown>;

class FormalP3DefinitiveRejection extends Error {}

function objectValue(value: unknown): JsonObject | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : null;
}

function text(value: unknown, field: string, maximum = IDENTITY_LIMIT): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum || value.includes('\0')) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function optionalText(value: unknown, field: string, maximum = IDENTITY_LIMIT): string | null {
  return value === null || value === undefined ? null : text(value, field, maximum);
}

function integer(value: unknown, field: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || Number(value) < minimum) throw new Error(`${field} is invalid`);
  return Number(value);
}

function envelope(value: unknown, requestId: string): JsonObject {
  const raw = objectValue(value);
  if (raw === null || raw.request_id !== requestId) {
    throw new Error('FORMAL_P3_REQUEST_REJECTED');
  }
  if (raw.ok === false) {
    const error = objectValue(raw?.error);
    throw new FormalP3DefinitiveRejection(optionalText(error?.reason, 'formal P3 error reason') ?? 'FORMAL_P3_REQUEST_REJECTED');
  }
  if (raw.ok !== true || raw.error !== null) {
    const error = objectValue(raw.error);
    throw new Error(optionalText(error?.reason, 'formal P3 error reason') ?? 'FORMAL_P3_REQUEST_REJECTED');
  }
  const result = objectValue(raw.result);
  if (result === null) throw new Error('formal P3 response result is invalid');
  return result;
}

function serverRejectionReason(error: unknown, requestId: string): string | null {
  const raw = objectValue(error);
  if (raw === null || raw.requestId !== requestId || raw.retriable !== false || objectValue(raw.payload) === null) return null;
  const exact = typeof raw.reason === 'string' && raw.reason.trim() ? raw.reason.trim() : null;
  return exact ?? reason(error);
}

function scope(value: unknown, expectedSessionId: string): Readonly<{ subject_id: string; session_id: string; project_id: string }> {
  const raw = objectValue(value);
  if (raw === null || raw.assurance !== 'authenticated') throw new Error('formal P3 Task scope is invalid');
  const sessionId = text(raw.session_id, 'task scope session_id');
  if (sessionId !== expectedSessionId) throw new Error('formal P3 Task Session binding mismatch');
  return Object.freeze({
    subject_id: text(raw.subject_id, 'task scope subject_id'),
    session_id: sessionId,
    project_id: text(raw.project_id, 'task scope project_id'),
  });
}

function displayState(state: FormalP3TaskRecord['canonical_state'], outcome: FormalP3TaskRecord['outcome'], queued: boolean): FormalP3TaskDisplayState {
  if (state === 'terminal') return outcome ?? 'unknown';
  if (state === 'accepted' && queued) return 'queued';
  return state;
}

function supportedOperations(value: unknown): readonly FormalP3TaskOperation[] {
  if (value === undefined) return Object.freeze([]);
  if (!Array.isArray(value)) throw new Error('formal P3 supported operations are invalid');
  const operations: FormalP3TaskOperation[] = [];
  for (const item of value) {
    const operation = text(item, 'supported operation', 64);
    if (OPERATIONS.has(operation)) operations.push(operation as FormalP3TaskOperation);
  }
  if (new Set(operations).size !== operations.length) throw new Error('formal P3 supported operations are duplicated');
  return Object.freeze(operations);
}

function parseTask(
  value: unknown,
  expectedSessionId: string,
  details?: Readonly<{ attempt?: unknown; admission?: unknown; supported_operations?: unknown; successor_task_id?: string | null }>,
): FormalP3TaskRecord {
  const raw = objectValue(value);
  if (raw === null) throw new Error('formal P3 Task is invalid');
  const boundScope = scope(raw.scope, expectedSessionId);
  const spec = objectValue(raw.spec);
  const revision = objectValue(raw.revision);
  if (spec === null || revision === null) throw new Error('formal P3 Task projection is incomplete');
  const state = text(raw.state, 'task state') as FormalP3TaskRecord['canonical_state'];
  if (!['accepted', 'running', 'blocked', 'decision_required', 'terminal'].includes(state)) throw new Error('formal P3 Task state is invalid');
  const outcome = optionalText(raw.outcome, 'task outcome') as FormalP3TaskRecord['outcome'];
  if ((state === 'terminal') !== (outcome !== null) || (outcome !== null && !TERMINAL_OUTCOMES.has(outcome))) {
    throw new Error('formal P3 Task outcome is invalid');
  }
  const attempt = objectValue(details?.attempt);
  const admission = objectValue(details?.admission ?? raw.admission);
  const queued = raw.queued === true;
  if (typeof raw.queued !== 'boolean') throw new Error('formal P3 Task admission truth is invalid');
  const predecessor = optionalText(revision.predecessor_task_id, 'predecessor_task_id');
  const successor = details?.successor_task_id ?? optionalText(raw.successor_task_id, 'successor_task_id');
  const attemptId = text(raw.attempt_id, 'task attempt_id');
  if (attempt !== null && (attempt.task_id !== raw.task_id || attempt.attempt_id !== attemptId)) {
    throw new Error('formal P3 Task Attempt binding mismatch');
  }
  if (
    (queued && state !== 'accepted')
    || (admission === null && queued)
    || (admission !== null && (
      admission.task_id !== raw.task_id
      || admission.attempt_id !== attemptId
      || admission.queued !== queued
    ))
  ) throw new Error('formal P3 Task admission binding mismatch');
  if (attempt !== null) {
    const expectedAttemptState = state === 'accepted' ? 'accepted' : state === 'terminal' ? 'terminal' : 'running';
    if (attempt.state !== expectedAttemptState || (attempt.outcome ?? null) !== outcome) {
      throw new Error('formal P3 Task Attempt lifecycle mismatch');
    }
  }
  const admissionPriority = admission === null ? null : optionalText(admission.priority, 'admission priority');
  if (admissionPriority !== null && !['low', 'normal', 'high', 'urgent'].includes(admissionPriority)) {
    throw new Error('formal P3 Task admission priority is invalid');
  }
  const operations = supportedOperations(details?.supported_operations);
  return Object.freeze({
    task_id: text(raw.task_id, 'task_id'),
    attempt_id: attemptId,
    attempt_number: attempt === null ? null : integer(attempt.attempt_number, 'attempt_number', 1),
    correlation_id: text(raw.correlation_id, 'task correlation_id'),
    ...boundScope,
    name: text(spec.name, 'task name', 256),
    canonical_state: state,
    display_state: displayState(state, outcome, queued),
    outcome,
    queued,
    admission_priority: admissionPriority as FormalP3TaskRecord['admission_priority'],
    admission_reason: admission === null ? null : optionalText(admission.reason, 'admission reason'),
    event_head: integer(raw.event_head, 'task event_head'),
    revision_number: integer(revision.number, 'task revision number', 1),
    predecessor_task_id: predecessor,
    successor_task_id: successor,
    blocking_question: null,
    progress: null,
    result_availability: null,
    result_text: null,
    result_attempt_id: null,
    replay_event_count: 0,
    replay_event_types: Object.freeze([]),
    available_operations: operations,
  });
}

function linkSuccessors(tasks: readonly FormalP3TaskRecord[]): readonly FormalP3TaskRecord[] {
  const byId = new Map(tasks.map(task => [task.task_id, task]));
  const successorByPredecessor = new Map<string, string>();
  for (const task of tasks) {
    if (task.predecessor_task_id === null || !byId.has(task.predecessor_task_id)) continue;
    const previous = successorByPredecessor.get(task.predecessor_task_id);
    if (previous !== undefined && previous !== task.task_id) throw new Error('formal P3 Task successor lineage forks');
    successorByPredecessor.set(task.predecessor_task_id, task.task_id);
  }
  return Object.freeze(tasks.map(task => {
    const successor = successorByPredecessor.get(task.task_id) ?? null;
    return successor === task.successor_task_id
      ? task
      : Object.freeze({
          ...task,
          successor_task_id: successor,
          available_operations: Object.freeze(task.available_operations.filter(operation => operation !== 'task.create_successor')),
        });
  }));
}

function parseList(value: unknown, requestId: string, sessionId: string): Readonly<{
  tasks: readonly FormalP3TaskRecord[];
  next_cursor: string | null;
  has_more: boolean;
  supported_operations: readonly FormalP3TaskOperation[];
}> {
  const result = envelope(value, requestId);
  if (!Array.isArray(result.tasks) || typeof result.has_more !== 'boolean') throw new Error('formal P3 Task list is invalid');
  const tasks = result.tasks.map(item => parseTask(item, sessionId));
  const ids = new Set(tasks.map(task => task.task_id));
  if (ids.size !== tasks.length) throw new Error('formal P3 Task list contains duplicate identity');
  return Object.freeze({
    tasks: Object.freeze(tasks),
    next_cursor: optionalText(result.next_cursor, 'task list next_cursor'),
    has_more: result.has_more,
    supported_operations: supportedOperations(result.supported_operations),
  });
}

function parseEventPage(
  record: FormalP3TaskRecord,
  value: unknown,
  requestId: string,
  expectedAfter: number,
): Readonly<{ events: readonly JsonObject[]; head_seq: number; next_after_seq: number | null; has_more: boolean }> {
  const result = envelope(value, requestId);
  if (
    result.task_id !== record.task_id
    || result.after_seq !== expectedAfter
    || !Array.isArray(result.events)
    || integer(result.head_seq, 'event head', -1) !== record.event_head
    || typeof result.has_more !== 'boolean'
  ) {
    throw new Error('formal P3 Task events binding mismatch');
  }
  const events = result.events.map(value => {
    const event = objectValue(value);
    if (event === null) throw new Error('formal P3 TaskEvent is invalid');
    return event;
  });
  const next = result.next_after_seq === null ? null : integer(result.next_after_seq, 'TaskEvent next cursor');
  const finalEvent = events.length === 0 ? undefined : events[events.length - 1];
  if (result.has_more !== (next !== null) || (next !== null && next !== finalEvent?.seq)) {
    throw new Error('formal P3 TaskEvent pagination mismatch');
  }
  return Object.freeze({ events: Object.freeze(events), head_seq: record.event_head, next_after_seq: next, has_more: result.has_more });
}

function enrichEvents(record: FormalP3TaskRecord, events: readonly JsonObject[]): FormalP3TaskRecord {
  let previous = -1;
  let blockingQuestion: string | null = null;
  let progress: string | null = null;
  const eventTypes: string[] = [];
  for (const event of events) {
    if (event.task_id !== record.task_id || event.correlation_id !== record.correlation_id) throw new Error('formal P3 TaskEvent identity mismatch');
    const eventScope = scope(event.scope, record.session_id);
    if (eventScope.subject_id !== record.subject_id || eventScope.project_id !== record.project_id) throw new Error('formal P3 TaskEvent scope mismatch');
    const attemptId = text(event.attempt_id, 'TaskEvent attempt_id');
    const seq = integer(event.seq, 'TaskEvent seq');
    if (seq !== previous + 1) throw new Error('formal P3 TaskEvent order mismatch');
    previous = seq;
    const eventType = text(event.event_type, 'TaskEvent type');
    eventTypes.push(eventType);
    const details = objectValue(event.details);
    if (attemptId === record.attempt_id && eventType === 'task.decision_required') {
      blockingQuestion = details === null ? null : optionalText(details.question ?? details.prompt, 'blocking question', 8192);
    }
    if (attemptId === record.attempt_id && details !== null) {
      progress = optionalText(details.progress ?? details.summary, 'task progress', 8192) ?? progress;
    }
  }
  if (previous !== record.event_head) throw new Error('formal P3 TaskEvent head mismatch');
  const last = events.length === 0 ? undefined : events[events.length - 1];
  if (last?.attempt_id !== record.attempt_id || last.state !== record.canonical_state || (last.outcome ?? null) !== record.outcome) {
    throw new Error('formal P3 TaskEvent current Attempt mismatch');
  }
  return Object.freeze({
    ...record,
    blocking_question: record.canonical_state === 'decision_required' ? blockingQuestion : null,
    progress,
    replay_event_count: events.length,
    replay_event_types: Object.freeze(eventTypes),
  });
}

function enrichResult(record: FormalP3TaskRecord, value: unknown, requestId: string, terminalSourceEventId: string | null): FormalP3TaskRecord {
  const result = envelope(value, requestId);
  if (result.task_id !== record.task_id || !['available', 'not_ready', 'unavailable'].includes(String(result.availability))) {
    throw new Error('formal P3 TaskResult binding mismatch');
  }
  const availability = result.availability as FormalP3TaskRecord['result_availability'];
  const taskResult = objectValue(result.task_result);
  if ((availability === 'available') !== (taskResult !== null)) throw new Error('formal P3 TaskResult availability mismatch');
  if (
    (availability === 'available' && (record.canonical_state !== 'terminal' || record.outcome !== 'completed'))
    || (availability === 'not_ready' && record.canonical_state === 'terminal')
    || (availability === 'unavailable' && record.canonical_state !== 'terminal')
  ) throw new Error('formal P3 TaskResult lifecycle mismatch');
  if (taskResult === null) {
    const availableOperations = record.canonical_state === 'terminal' && record.outcome === 'completed'
      ? Object.freeze(record.available_operations.filter(operation => operation !== 'task.create_successor'))
      : record.available_operations;
    return Object.freeze({
      ...record,
      result_availability: availability,
      result_text: null,
      result_attempt_id: null,
      available_operations: availableOperations,
    });
  }
  if (
    taskResult.task_id !== record.task_id
    || taskResult.attempt_id !== record.attempt_id
    || terminalSourceEventId === null
    || taskResult.source_event_id !== terminalSourceEventId
  ) throw new Error('formal P3 TaskResult identity mismatch');
  const operations = record.canonical_state === 'terminal'
    && record.outcome === 'completed'
    && availability !== 'available'
    ? Object.freeze(record.available_operations.filter(operation => operation !== 'task.create_successor'))
    : record.available_operations;
  return Object.freeze({
    ...record,
    result_availability: availability,
    result_text: text(taskResult.result_text, 'TaskResult text', CONTENT_LIMIT),
    result_attempt_id: text(taskResult.attempt_id, 'TaskResult attempt_id'),
    available_operations: operations,
  });
}

function storageKey(sessionId: string): string {
  return `${SELECTION_PREFIX}${encodeURIComponent(text(sessionId, 'session_id'))}`;
}

function browserStore(): FormalP3TaskSelectionStore | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

function readHint(store: FormalP3TaskSelectionStore | null, sessionId: string): string | null {
  if (store === null) return null;
  try {
    const value = store.getItem(storageKey(sessionId));
    return value === null ? null : text(value, 'selected task hint');
  } catch {
    return null;
  }
}

function writeHint(store: FormalP3TaskSelectionStore | null, sessionId: string, taskId: string | null): void {
  if (store === null) return;
  try {
    if (taskId === null) store.removeItem(storageKey(sessionId));
    else store.setItem(storageKey(sessionId), taskId);
  } catch {
    // Browser storage is a hint only and cannot alter Task authority.
  }
}

function reason(error: unknown): string {
  return error instanceof Error && error.message ? error.message : 'FORMAL_P3_TASK_EXPERIENCE_FAILED';
}

function requestId(prefix: string): string {
  requestSequence += 1;
  return `${prefix}-${Date.now()}-${requestSequence}`;
}

type PendingMutation = Readonly<{
  input: FormalP3TaskMutationInput;
  command: FormalP3TaskCommand;
  continuation_id: string;
  structured_intent: Readonly<Record<string, unknown>> | null;
  correlation_id: string;
}>;

export class FormalP3TaskExperienceOwner {
  readonly #enabled: boolean;
  readonly #request: FormalP3TaskRequest;
  readonly #store: FormalP3TaskSelectionStore | null;
  readonly #onSnapshot?: (snapshot: FormalP3TaskExperienceSnapshot) => void;
  #state: FormalP3TaskExperienceSnapshot;
  #generation = 0;
  #pending: PendingMutation | null = null;

  constructor(input: Readonly<{
    enabled: boolean;
    request: FormalP3TaskRequest;
    store?: FormalP3TaskSelectionStore | null;
    on_snapshot?: (snapshot: FormalP3TaskExperienceSnapshot) => void;
  }>) {
    this.#enabled = input.enabled;
    this.#request = input.request;
    this.#store = input.store === undefined ? browserStore() : input.store;
    this.#onSnapshot = input.on_snapshot;
    this.#state = Object.freeze({ status: input.enabled ? 'idle' : 'disabled', session_id: null, tasks: Object.freeze([]), selected_task_id: null, collection_operations: Object.freeze([]), command: null, reason: input.enabled ? null : 'FORMAL_P3_TASK_EXPERIENCE_DISABLED' });
  }

  snapshot(): FormalP3TaskExperienceSnapshot { return this.#state; }

  async refresh(sessionIdInput: string): Promise<FormalP3TaskExperienceSnapshot> {
    if (!this.#enabled) throw new Error('formal P3 Task experience is disabled');
    const sessionId = text(sessionIdInput, 'session_id');
    const generation = ++this.#generation;
    const retainedCommand = this.#state.session_id === sessionId ? this.#state.command : null;
    this.#publish({ status: 'loading', session_id: sessionId, tasks: this.#state.session_id === sessionId ? this.#state.tasks : Object.freeze([]), selected_task_id: this.#state.session_id === sessionId ? this.#state.selected_task_id : null, collection_operations: Object.freeze([]), command: retainedCommand, reason: null });
    try {
      const collected: FormalP3TaskRecord[] = [];
      let collectionOperations: readonly FormalP3TaskOperation[] | null = null;
      let cursor: string | null = null;
      for (let page = 0; page < MAX_LIST_PAGES; page += 1) {
        const id = requestId('formal-p3-task-list');
        const response = await this.#request(FORMAL_P3_TASK_METHODS.list, { session_id: sessionId, limit: TASK_LIMIT, ...(cursor === null ? {} : { cursor }) }, id);
        if (generation !== this.#generation) throw new Error('formal P3 Task refresh became stale');
        const parsed = parseList(response, id, sessionId);
        if (collectionOperations !== null && (
          collectionOperations.length !== parsed.supported_operations.length
          || collectionOperations.some((operation, index) => operation !== parsed.supported_operations[index])
        )) throw new Error('formal P3 Task collection authority changed during pagination');
        collectionOperations = parsed.supported_operations;
        collected.push(...parsed.tasks);
        if (!parsed.has_more) break;
        if (parsed.next_cursor === null || parsed.next_cursor === cursor || page === MAX_LIST_PAGES - 1) throw new Error('formal P3 Task list pagination is invalid');
        cursor = parsed.next_cursor;
      }
      if (new Set(collected.map(task => task.task_id)).size !== collected.length) throw new Error('formal P3 Task pages overlap');
      const linked = linkSuccessors(collected);
      const hint = readHint(this.#store, sessionId);
      const prior = this.#state.session_id === sessionId ? this.#state.selected_task_id : null;
      const selected = [prior, hint].find(candidate => candidate !== null && linked.some(task => task.task_id === candidate))
        ?? linked[0]?.task_id
        ?? null;
      this.#publish({ status: 'loading', session_id: sessionId, tasks: Object.freeze([...linked].sort((left, right) => left.task_id.localeCompare(right.task_id))), selected_task_id: null, collection_operations: collectionOperations ?? Object.freeze([]), command: retainedCommand, reason: null });
      if (selected !== null) {
        await this.select(selected);
      } else {
        this.#publish({ ...this.#state, status: 'ready', reason: null });
      }
      writeHint(this.#store, sessionId, this.#state.selected_task_id);
      return this.#state;
    } catch (error) {
      if (generation === this.#generation) this.#publish({ status: 'failed', session_id: sessionId, tasks: Object.freeze([]), selected_task_id: null, collection_operations: Object.freeze([]), command: retainedCommand, reason: reason(error) });
      throw error;
    }
  }

  async select(taskIdInput: string): Promise<FormalP3TaskExperienceSnapshot> {
    const sessionId = this.#state.session_id;
    if (!this.#enabled || sessionId === null || this.#state.status === 'closed') throw new Error('formal P3 Task experience is unavailable');
    const taskId = text(taskIdInput, 'task_id');
    const listedTasks = this.#state.tasks;
    const listed = listedTasks.find(task => task.task_id === taskId);
    if (listed === undefined) throw new Error('formal P3 Task selection is not authoritative');
    const collectionOperations = this.#state.collection_operations;
    const retainedCommand = this.#state.command;
    const generation = ++this.#generation;
    this.#publish({ status: 'loading', session_id: sessionId, tasks: listedTasks, selected_task_id: null, collection_operations: Object.freeze([]), command: retainedCommand, reason: null });
    try {
    const statusId = requestId('formal-p3-task-status');
    const statusResponse = await this.#request(FORMAL_P3_TASK_METHODS.status, { session_id: sessionId, task_id: taskId }, statusId);
    if (generation !== this.#generation) throw new Error('formal P3 Task selection became stale');
    const status = envelope(statusResponse, statusId);
    const selected = parseTask(status.task, sessionId, {
      attempt: status.attempt,
      admission: status.admission,
      supported_operations: status.supported_operations,
      successor_task_id: listed.successor_task_id,
    });
    if (selected.task_id !== taskId) throw new Error('formal P3 Task selection target mismatch');
    if (
      selected.subject_id !== listed.subject_id
      || selected.project_id !== listed.project_id
      || selected.correlation_id !== listed.correlation_id
      || selected.revision_number !== listed.revision_number
      || selected.predecessor_task_id !== listed.predecessor_task_id
    ) throw new Error('formal P3 Task selection authority changed identity');
    const events: JsonObject[] = [];
    let afterSeq = -1;
    for (let page = 0; page < MAX_EVENT_PAGES; page += 1) {
      const eventsId = requestId('formal-p3-task-events');
      const response = await this.#request(FORMAL_P3_TASK_METHODS.events, { session_id: sessionId, task_id: taskId, after_seq: afterSeq, limit: 500 }, eventsId);
      if (generation !== this.#generation) throw new Error('formal P3 Task detail became stale');
      const parsed = parseEventPage(selected, response, eventsId, afterSeq);
      events.push(...parsed.events);
      if (!parsed.has_more) break;
      if (parsed.next_after_seq === null || parsed.next_after_seq <= afterSeq || page === MAX_EVENT_PAGES - 1) throw new Error('formal P3 TaskEvent replay exceeds its bound');
      afterSeq = parsed.next_after_seq;
    }
    const resultId = requestId('formal-p3-task-result');
    const resultResponse = await this.#request(
      FORMAL_P3_TASK_METHODS.result,
      { session_id: sessionId, task_id: taskId },
      resultId,
    );
    if (generation !== this.#generation) throw new Error('formal P3 Task detail became stale');
    const terminalSourceEventId = events.length === 0 || events[events.length - 1].source_event_id === null
      ? null
      : text(events[events.length - 1].source_event_id, 'TaskEvent source_event_id');
    const enriched = enrichResult(enrichEvents(selected, events), resultResponse, resultId, terminalSourceEventId);
    const tasks = listedTasks.map(task => task.task_id === taskId ? enriched : task);
    const command = retainedCommand?.task_id === taskId
      ? Object.freeze({ ...retainedCommand, terminal_outcome: enriched.outcome })
      : retainedCommand;
    this.#publish({ status: 'ready', session_id: sessionId, tasks: Object.freeze(tasks), selected_task_id: taskId, collection_operations: collectionOperations, command, reason: null });
    writeHint(this.#store, sessionId, taskId);
    return this.#state;
    } catch (error) {
      if (generation === this.#generation) {
        this.#publish({ status: 'failed', session_id: sessionId, tasks: Object.freeze([]), selected_task_id: null, collection_operations: Object.freeze([]), command: this.#state.command, reason: reason(error) });
      }
      throw error;
    }
  }

  async issue(input: FormalP3TaskMutationInput): Promise<FormalP3TaskExperienceSnapshot> {
    if (!this.#enabled || this.#state.session_id === null || this.#state.status !== 'ready' || this.#pending !== null) {
      throw new Error('formal P3 Task mutation owner is unavailable');
    }
    if (!OPERATIONS.has(input.operation)) throw new Error('formal P3 Task operation is invalid');
    if (['task.provide_input', 'task.pause', 'task.resume'].includes(input.operation)) {
      const command = this.#command(input, 'rejected', 'TASK_CONTROL_UNSUPPORTED');
      this.#publish({ ...this.#state, command });
      return this.#state;
    }
    const targeted = input.operation !== 'task.create';
    const taskId = targeted ? text(input.task_id ?? this.#state.selected_task_id, 'task_id') : null;
    if (taskId !== null) await this.select(taskId);
    else await this.refresh(this.#state.session_id);
    const record = taskId === null ? null : this.#state.tasks.find(task => task.task_id === taskId) ?? null;
    if (input.operation === 'task.create' && !this.#state.collection_operations.includes('task.create')) {
      const command = this.#command(input, 'rejected', 'TASK_CONTROL_UNSUPPORTED');
      this.#publish({ ...this.#state, command });
      return this.#state;
    }
    if (record !== null && !record.available_operations.includes(input.operation)) {
      const command = this.#command({ ...input, task_id: taskId }, 'rejected', 'TASK_CONTROL_UNSUPPORTED');
      this.#publish({ ...this.#state, command });
      return this.#state;
    }
    const command = this.#command({ ...input, task_id: taskId }, 'issuing', null);
    this.#publish({ ...this.#state, command });
    const correlationId = record?.correlation_id ?? command.command_id;
    try {
      if (input.operation === 'task.retry') {
        const id = requestId('formal-p3-retry-confirmation');
        const response = await this.#request(FORMAL_P3_TASK_METHODS.confirmation, {
          session_id: this.#state.session_id,
          operation: input.operation,
          command_id: command.command_id,
          issued_at: new Date().toISOString(),
          correlation_id: correlationId,
          task_id: taskId,
        }, id);
        const result = envelope(response, id);
        if (
          result.status !== 'confirmation_issued'
          || result.operation !== input.operation
          || result.command_id !== command.command_id
          || result.target_task_id !== taskId
        ) throw new Error('formal P3 retry confirmation binding mismatch');
        const continuation = text(result.confirmation_id, 'confirmation_id');
        const next = Object.freeze({ ...command, request_id: id, phase: 'confirmation_required' as const });
        this.#pending = Object.freeze({ input: { ...input, task_id: taskId }, command: next, continuation_id: continuation, structured_intent: null, correlation_id: correlationId });
        this.#publish({ ...this.#state, command: next });
        return this.#state;
      }
      const structured = this.#structuredIntent({ ...input, task_id: taskId });
      const response = await this.#sendStructured(structured, command, correlationId, null);
      const result = envelope(response.value, response.request_id);
      if (result.status === 'clarification' && typeof result.confirmation_token === 'string') {
        if (
          result.operation !== input.operation
          || (result.task_id ?? null) !== taskId
          || result.confirmation_form !== `confirm task request ${result.confirmation_token}`
        ) throw new Error('formal P3 confirmation target mismatch');
        const next = Object.freeze({ ...command, request_id: response.request_id, phase: 'confirmation_required' as const });
        this.#pending = Object.freeze({ input: { ...input, task_id: taskId }, command: next, continuation_id: text(result.confirmation_token, 'confirmation token'), structured_intent: structured, correlation_id: correlationId });
        this.#publish({ ...this.#state, command: next });
        return this.#state;
      }
      await this.#settle(result, Object.freeze({ ...command, request_id: response.request_id }), taskId);
      return this.#state;
    } catch (error) {
      this.#pending = null;
      this.#publish({ ...this.#state, command: Object.freeze({ ...command, phase: 'rejected', reason: reason(error) }) });
      throw error;
    }
  }

  async confirm(): Promise<FormalP3TaskExperienceSnapshot> {
    let pending = this.#pending;
    if (pending === null || this.#state.session_id === null) throw new Error('formal P3 Task confirmation is unavailable');
    this.#pending = null;
    try {
      if (pending.command.task_id !== null) {
        const targetTaskId = pending.command.task_id;
        await this.select(targetTaskId);
        const current = this.#state.tasks.find(task => task.task_id === targetTaskId);
        if (
          current === undefined
          || current.attempt_id !== pending.command.attempt_id
          || current.event_head !== pending.command.event_head
          || current.revision_number !== pending.command.revision_number
        ) {
          throw new FormalP3DefinitiveRejection('FORMAL_P3_TASK_CONFIRMATION_STALE');
        }
      }
      let result: JsonObject;
      if (pending.input.operation === 'task.retry') {
        const id = requestId('formal-p3-retry-mutate');
        const response = await this.#requestRecognizingRejection(FORMAL_P3_TASK_METHODS.mutate, {
          session_id: this.#state.session_id,
          operation: pending.input.operation,
          command_id: pending.command.command_id,
          issued_at: new Date().toISOString(),
          correlation_id: pending.correlation_id,
          task_id: pending.input.task_id,
          confirmation_id: pending.continuation_id,
        }, id);
        result = envelope(response, id);
        if (
          result.status !== 'mutation_processed'
          || result.operation !== pending.input.operation
          || result.command_id !== pending.command.command_id
          || result.target_task_id !== pending.input.task_id
        ) throw new Error('formal P3 retry mutation binding mismatch');
        pending = Object.freeze({ ...pending, command: Object.freeze({ ...pending.command, request_id: id }) });
      } else {
        const response = await this.#sendStructured(pending.structured_intent!, pending.command, pending.correlation_id, pending.continuation_id);
        result = envelope(response.value, response.request_id);
        pending = Object.freeze({ ...pending, command: Object.freeze({ ...pending.command, request_id: response.request_id }) });
      }
      await this.#settle(result, pending.command, pending.input.task_id ?? null);
      return this.#state;
    } catch (error) {
      const retained = this.#state.command?.command_id === pending.command.command_id ? this.#state.command : pending.command;
      const definitive = error instanceof FormalP3DefinitiveRejection;
      this.#publish({
        ...this.#state,
        command: retained.accepted
          ? Object.freeze({ ...retained, reason: reason(error) })
          : Object.freeze({ ...retained, phase: definitive ? 'rejected' : 'unknown', reason: reason(error) }),
      });
      throw error;
    }
  }

  disconnect(): FormalP3TaskExperienceSnapshot {
    this.#generation += 1;
    this.#pending = null;
    return this.#publish({ ...this.#state, status: this.#enabled ? 'disconnected' : 'disabled', command: null, reason: this.#enabled ? 'FORMAL_P3_TASK_RECONNECT_REQUIRED' : this.#state.reason });
  }

  close(): FormalP3TaskExperienceSnapshot {
    this.#generation += 1;
    this.#pending = null;
    return this.#publish({ status: 'closed', session_id: null, tasks: Object.freeze([]), selected_task_id: null, collection_operations: Object.freeze([]), command: null, reason: 'OWNER_CLOSED' });
  }

  #command(input: FormalP3TaskMutationInput, phase: FormalP3TaskCommandPhase, commandReason: string | null): FormalP3TaskCommand {
    const taskId = input.operation === 'task.create' ? null : input.task_id ?? this.#state.selected_task_id;
    const record = taskId === null ? null : this.#state.tasks.find(task => task.task_id === taskId) ?? null;
    return Object.freeze({
      command_id: requestId('formal-p3-command'),
      request_id: null,
      operation: input.operation,
      task_id: taskId,
      attempt_id: record?.attempt_id ?? null,
      event_head: record?.event_head ?? null,
      revision_number: record?.revision_number ?? null,
      phase,
      accepted: false,
      applied: false,
      terminal_outcome: record?.outcome ?? null,
      reason: commandReason,
    });
  }

  #structuredIntent(input: FormalP3TaskMutationInput): Readonly<Record<string, unknown>> {
    const operation = input.operation;
    const target = operation === 'task.create' ? null : text(input.task_id, 'task_id');
    let args: Record<string, unknown>;
    if (operation === 'task.create' || operation === 'task.create_successor') {
      args = { name: text(input.name, 'task name', 256), instruction: text(input.instruction, 'task instruction', 4096) };
    } else if (operation === 'task.update') {
      args = { instruction: text(input.instruction, 'task instruction', 4096) };
    } else if (operation === 'task.adjust') {
      args = { adjustment: text(input.adjustment ?? input.instruction, 'task adjustment', 4096) };
    } else if (operation === 'task.reprioritize') {
      if (!['low', 'normal', 'high', 'urgent'].includes(String(input.priority))) throw new Error('task priority is invalid');
      args = { priority: input.priority };
    } else if (operation === 'task.cancel') {
      args = {};
    } else {
      throw new Error('formal P3 Task operation requires a separately accepted primitive');
    }
    return Object.freeze({ operation, target, arguments: Object.freeze(args) });
  }

  async #sendStructured(structured: Readonly<Record<string, unknown>>, command: FormalP3TaskCommand, correlationId: string, continuationId: string | null): Promise<Readonly<{ value: unknown; request_id: string }>> {
    const id = requestId('formal-p3-structured-intent');
    const value = await this.#requestRecognizingRejection(FORMAL_P3_TASK_METHODS.intent, {
      session_id: this.#state.session_id,
      correlation_id: correlationId,
      source: 'structured',
      operation_hint: command.operation,
      ...(command.task_id === null ? {} : { task_id_hint: command.task_id }),
      source_id: command.command_id,
      source_confidence: 1,
      committed: true,
      structured_intent: structured,
      ...(continuationId === null ? {} : { continuation_id: continuationId }),
    }, id);
    return Object.freeze({ value, request_id: id });
  }

  async #requestRecognizingRejection(method: string, params: Record<string, unknown>, id: string): Promise<unknown> {
    try {
      return await this.#request(method, params, id);
    } catch (error) {
      const exactReason = serverRejectionReason(error, id);
      if (exactReason !== null) throw new FormalP3DefinitiveRejection(exactReason);
      throw error;
    }
  }

  async #settle(result: JsonObject, command: FormalP3TaskCommand, taskId: string | null): Promise<void> {
    const status = result.status;
    if (status !== 'dispatched' && status !== 'mutation_processed') {
      throw new FormalP3DefinitiveRejection(optionalText(result.reason, 'mutation reason') ?? 'FORMAL_P3_MUTATION_REJECTED');
    }
    if (result.operation !== command.operation) throw new Error('formal P3 mutation operation binding mismatch');
    if (
      (status === 'mutation_processed'
        && (result.command_id !== command.command_id || (result.target_task_id ?? null) !== taskId))
      || (status === 'dispatched' && taskId !== null && result.task_id !== taskId)
    ) throw new Error('formal P3 mutation command binding mismatch');
    const formal = objectValue(result.formal_task_result);
    if (formal === null) throw new Error('formal P3 mutation result is missing');
    const formalTaskId = text(formal.task_id, 'formal mutation task_id');
    text(formal.attempt_id, 'formal mutation attempt_id');
    if (formal.applied !== undefined && typeof formal.applied !== 'boolean') throw new Error('formal P3 mutation applied truth is invalid');
    if (
      taskId !== null
      && command.operation !== 'task.create_successor'
      && formalTaskId !== taskId
    ) throw new Error('formal P3 mutation result target mismatch');
    if (
      command.operation === 'task.create_successor'
      && formal.predecessor_task_id !== taskId
    ) throw new Error('formal P3 successor lineage mismatch');
    const applied = formal.applied === true;
    const accepted = true;
    const resolvedTaskId = command.operation === 'task.create' || command.operation === 'task.create_successor' ? formalTaskId : taskId;
    this.#publish({ ...this.#state, command: Object.freeze({ ...command, task_id: resolvedTaskId, phase: applied ? 'applied' : 'accepted', accepted, applied, reason: optionalText(formal.reason, 'formal mutation reason') }) });
    if (this.#state.session_id !== null) {
      await this.refresh(this.#state.session_id);
      if (resolvedTaskId !== null && this.#state.tasks.some(task => task.task_id === resolvedTaskId)) await this.select(resolvedTaskId);
    }
  }

  #publish(next: FormalP3TaskExperienceSnapshot): FormalP3TaskExperienceSnapshot {
    this.#state = Object.freeze({
      ...next,
      tasks: Object.freeze([...next.tasks]),
      collection_operations: Object.freeze([...next.collection_operations]),
    });
    this.#onSnapshot?.(this.#state);
    return this.#state;
  }
}
