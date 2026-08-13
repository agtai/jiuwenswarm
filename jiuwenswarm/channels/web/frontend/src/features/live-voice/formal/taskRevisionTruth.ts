export const TASK_REVISION_TRUTH_LIMITS = Object.freeze({
  max_text_chars: 2_000,
  max_diff_chars: 1_000,
  max_paths: 64,
  max_revisions: 2,
} as const);

export type TaskRevisionApplicationState = 'accepted' | 'fencing' | 'applied' | 'rejected' | 'unknown';
export type TaskRevisionVerifierState = 'not_run' | 'passed' | 'failed' | 'timeout' | 'mutated_fixture';

export interface TaskRevisionRecordView {
  readonly task_id: string;
  readonly task_revision: number;
  readonly predecessor_revision: number | null;
  readonly attempt_id: string;
  readonly created_by_command_id: string;
}

export interface TaskRevisionPendingCommandView {
  readonly command_id: string;
  readonly application_state: TaskRevisionApplicationState;
  readonly predecessor_revision: number;
  readonly successor_revision: number;
  readonly predecessor_attempt_id: string;
  readonly successor_attempt_id: string | null;
}

export interface TaskRevisionCleanupView {
  readonly command_id: string;
  readonly predecessor_attempt_id: string;
  readonly cleanup_id: string;
  readonly checkout_identity: string;
  readonly unapplied_changes_discarded: boolean;
  readonly acknowledged_at: string;
}

export interface TaskRevisionVerifierView {
  readonly verifier_id: string;
  readonly result: TaskRevisionVerifierState;
  readonly exit_code: number | null;
  readonly timed_out: boolean;
  readonly output_digest: string;
  readonly output_summary: string;
}

export interface TaskRevisionExecutionView {
  readonly task_id: string;
  readonly task_revision: number;
  readonly attempt_id: string;
  readonly executor_ref: string;
  readonly fixture_identity: string;
  readonly execution_ack: boolean;
  readonly changed_paths: readonly string[];
  readonly diff_summary: string;
  readonly verifier: TaskRevisionVerifierView;
  readonly cleanup_state: 'successor_cleanup_resolved';
  readonly forbidden_side_effect_count: number;
  readonly verified_success: boolean;
}

export interface TaskRevisionTruthSnapshot {
  readonly task_id: string;
  readonly task_state: 'accepted' | 'running' | 'blocked' | 'decision_required' | 'terminal';
  readonly outcome: 'completed' | 'failed' | 'cancelled' | 'interrupted' | 'unknown' | null;
  readonly current_revision: number;
  readonly current_attempt_id: string;
  readonly attempt_number: number;
  readonly revision_history: readonly TaskRevisionRecordView[];
  readonly pending_command: TaskRevisionPendingCommandView | null;
  readonly cleanup: TaskRevisionCleanupView | null;
  readonly execution: TaskRevisionExecutionView | null;
}

type JsonObject = Readonly<Record<string, unknown>>;

function objectValue(value: unknown, field: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${field} is invalid`);
  }
  return value as JsonObject;
}

function exactKeys(value: JsonObject, expected: readonly string[], field: string): void {
  const actual = Object.keys(value).sort();
  const sortedExpected = [...expected].sort();
  if (actual.length !== sortedExpected.length || actual.some((key, index) => key !== sortedExpected[index])) {
    throw new Error(`${field} fields are incomplete or unknown`);
  }
}

function text(value: unknown, field: string, maximum: number = TASK_REVISION_TRUTH_LIMITS.max_text_chars): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) {
    throw new Error(`${field} is invalid`);
  }
  return value;
}

function integer(value: unknown, field: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || Number(value) < minimum) throw new Error(`${field} is invalid`);
  return Number(value);
}

function nullableInteger(value: unknown, field: string): number | null {
  return value === null ? null : integer(value, field, 1);
}

function parseConstraints(value: unknown, field: string): void {
  const constraints = objectValue(value, field);
  exactKeys(constraints, [
    'write_scope',
    'dependency_policy',
    'public_api_policy',
    'configuration_policy',
    'regression_verifier_required',
  ], field);
  if (
    !Array.isArray(constraints.write_scope)
    || constraints.write_scope.length < 1
    || constraints.write_scope.length > 16
    || constraints.write_scope.some((path, index) => text(path, `${field}.write_scope[${index}]`) !== path)
    || new Set(constraints.write_scope).size !== constraints.write_scope.length
    || constraints.dependency_policy !== 'locked'
    || constraints.public_api_policy !== 'preserve'
    || constraints.configuration_policy !== 'preserve'
    || typeof constraints.regression_verifier_required !== 'boolean'
  ) {
    throw new Error(`${field} is invalid`);
  }
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], field: string): T {
  if (typeof value !== 'string' || !allowed.includes(value as T)) throw new Error(`${field} is invalid`);
  return value as T;
}

function parseTimestamp(value: unknown, field: string): string {
  const normalized = text(value, field);
  if (!Number.isFinite(Date.parse(normalized))) throw new Error(`${field} is invalid`);
  return normalized;
}

function parseRevision(value: unknown, taskId: string, index: number): TaskRevisionRecordView {
  const record = objectValue(value, `revision_history[${index}]`);
  exactKeys(record, [
    'task_id',
    'task_revision',
    'predecessor_revision',
    'attempt_id',
    'base_instruction',
    'additive_facts',
    'constraints',
    'origin_commit_id',
    'created_by_command_id',
  ], `revision_history[${index}]`);
  const revision = integer(record.task_revision, `revision_history[${index}].task_revision`, 1);
  const predecessor = nullableInteger(record.predecessor_revision, `revision_history[${index}].predecessor_revision`);
  if (
    text(record.task_id, `revision_history[${index}].task_id`) !== taskId
    || revision !== index + 1
    || predecessor !== (revision === 1 ? null : revision - 1)
  ) {
    throw new Error('revision history lineage is invalid');
  }
  text(record.base_instruction, `revision_history[${index}].base_instruction`);
  if (!Array.isArray(record.additive_facts) || record.additive_facts.length > 16) {
    throw new Error(`revision_history[${index}].additive_facts is invalid`);
  }
  record.additive_facts.forEach((fact, factIndex) => text(fact, `revision_history[${index}].additive_facts[${factIndex}]`));
  if (new Set(record.additive_facts).size !== record.additive_facts.length) {
    throw new Error(`revision_history[${index}].additive_facts is invalid`);
  }
  parseConstraints(record.constraints, `revision_history[${index}].constraints`);
  text(record.origin_commit_id, `revision_history[${index}].origin_commit_id`);
  return Object.freeze({
    task_id: taskId,
    task_revision: revision,
    predecessor_revision: predecessor,
    attempt_id: text(record.attempt_id, `revision_history[${index}].attempt_id`),
    created_by_command_id: text(record.created_by_command_id, `revision_history[${index}].created_by_command_id`),
  });
}

function parsePending(value: unknown, taskId: string): TaskRevisionPendingCommandView | null {
  if (value === null) return null;
  const pending = objectValue(value, 'pending_command');
  exactKeys(pending, [
    'command_id',
    'task_id',
    'application_state',
    'predecessor_revision',
    'successor_revision',
    'predecessor_attempt_id',
    'successor_attempt_id',
    'fence_outbox_id',
    'dispatch_outbox_id',
    'replayed',
  ], 'pending_command');
  if (text(pending.task_id, 'pending_command.task_id') !== taskId || typeof pending.replayed !== 'boolean') {
    throw new Error('pending command binding is invalid');
  }
  text(pending.fence_outbox_id, 'pending_command.fence_outbox_id');
  const predecessorRevision = integer(pending.predecessor_revision, 'pending_command.predecessor_revision', 1);
  const successorRevision = integer(pending.successor_revision, 'pending_command.successor_revision', 1);
  const applicationState = oneOf(
    pending.application_state,
    ['accepted', 'fencing', 'applied', 'rejected', 'unknown'] as const,
    'pending_command.application_state',
  );
  const successorAttemptId = pending.successor_attempt_id === null
    ? null
    : text(pending.successor_attempt_id, 'pending_command.successor_attempt_id');
  if (
    successorRevision !== predecessorRevision + 1
    || !['fencing', 'unknown'].includes(applicationState)
    || successorAttemptId !== null
    || pending.dispatch_outbox_id !== null
  ) {
    throw new Error('pending command application truth is invalid');
  }
  return Object.freeze({
    command_id: text(pending.command_id, 'pending_command.command_id'),
    application_state: applicationState,
    predecessor_revision: predecessorRevision,
    successor_revision: successorRevision,
    predecessor_attempt_id: text(pending.predecessor_attempt_id, 'pending_command.predecessor_attempt_id'),
    successor_attempt_id: successorAttemptId,
  });
}

function parseCleanup(value: unknown): TaskRevisionCleanupView | null {
  if (value === null) return null;
  const cleanup = objectValue(value, 'cleanup');
  exactKeys(cleanup, [
    'command_id',
    'predecessor_attempt_id',
    'cleanup_id',
    'checkout_identity',
    'unapplied_changes_discarded',
    'acknowledged_at',
  ], 'cleanup');
  if (typeof cleanup.unapplied_changes_discarded !== 'boolean') throw new Error('cleanup discard fact is invalid');
  return Object.freeze({
    command_id: text(cleanup.command_id, 'cleanup.command_id'),
    predecessor_attempt_id: text(cleanup.predecessor_attempt_id, 'cleanup.predecessor_attempt_id'),
    cleanup_id: text(cleanup.cleanup_id, 'cleanup.cleanup_id'),
    checkout_identity: text(cleanup.checkout_identity, 'cleanup.checkout_identity'),
    unapplied_changes_discarded: cleanup.unapplied_changes_discarded,
    acknowledged_at: parseTimestamp(cleanup.acknowledged_at, 'cleanup.acknowledged_at'),
  });
}

function parseVerifier(value: unknown): TaskRevisionVerifierView {
  const verifier = objectValue(value, 'execution.verifier');
  exactKeys(verifier, ['verifier_id', 'result', 'exit_code', 'timed_out', 'output_digest', 'output_summary'], 'execution.verifier');
  const result = oneOf(
    verifier.result,
    ['not_run', 'passed', 'failed', 'timeout', 'mutated_fixture'] as const,
    'execution.verifier.result',
  );
  const exitCode = verifier.exit_code === null ? null : integer(verifier.exit_code, 'execution.verifier.exit_code', -(2 ** 31));
  const timedOut = verifier.timed_out;
  const digest = text(verifier.output_digest, 'execution.verifier.output_digest');
  if (
    typeof timedOut !== 'boolean'
    || timedOut !== (result === 'timeout')
    || !/^[0-9a-f]{64}$/.test(digest)
    || (exitCode !== null && exitCode >= 2 ** 31)
    || (result === 'passed' && exitCode !== 0)
    || (result === 'not_run' && exitCode !== null)
  ) {
    throw new Error('execution verifier truth is inconsistent');
  }
  return Object.freeze({
    verifier_id: text(verifier.verifier_id, 'execution.verifier.verifier_id'),
    result,
    exit_code: exitCode,
    timed_out: timedOut,
    output_digest: digest,
    output_summary: typeof verifier.output_summary === 'string' && verifier.output_summary.length <= TASK_REVISION_TRUTH_LIMITS.max_text_chars
      ? verifier.output_summary
      : (() => { throw new Error('execution.verifier.output_summary is invalid'); })(),
  });
}

function parseExecution(value: unknown, taskId: string): TaskRevisionExecutionView | null {
  if (value === null) return null;
  const execution = objectValue(value, 'execution');
  exactKeys(execution, [
    'task_id',
    'task_revision',
    'attempt_id',
    'executor_ref',
    'fixture_identity',
    'execution_ack',
    'changed_paths',
    'diff_summary',
    'verifier',
    'cleanup_state',
    'forbidden_side_effect_count',
    'verified_success',
  ], 'execution');
  if (!Array.isArray(execution.changed_paths) || execution.changed_paths.length > TASK_REVISION_TRUTH_LIMITS.max_paths) {
    throw new Error('execution.changed_paths is invalid');
  }
  const paths = execution.changed_paths.map((path, index) => text(path, `execution.changed_paths[${index}]`));
  if (paths.some((path, index) => index > 0 && path <= paths[index - 1]) || typeof execution.execution_ack !== 'boolean') {
    throw new Error('execution changed paths or ACK is invalid');
  }
  const verifier = parseVerifier(execution.verifier);
  const forbiddenSideEffects = integer(execution.forbidden_side_effect_count, 'execution.forbidden_side_effect_count');
  const verifiedSuccess = execution.verified_success;
  const expectedSuccess = execution.execution_ack && paths.length > 0 && verifier.result === 'passed' && forbiddenSideEffects === 0;
  if (
    text(execution.task_id, 'execution.task_id') !== taskId
    || execution.cleanup_state !== 'successor_cleanup_resolved'
    || typeof verifiedSuccess !== 'boolean'
    || verifiedSuccess !== expectedSuccess
  ) {
    throw new Error('execution authority truth is inconsistent');
  }
  return Object.freeze({
    task_id: taskId,
    task_revision: integer(execution.task_revision, 'execution.task_revision', 1),
    attempt_id: text(execution.attempt_id, 'execution.attempt_id'),
    executor_ref: text(execution.executor_ref, 'execution.executor_ref'),
    fixture_identity: text(execution.fixture_identity, 'execution.fixture_identity'),
    execution_ack: execution.execution_ack,
    changed_paths: Object.freeze(paths),
    diff_summary: text(execution.diff_summary, 'execution.diff_summary', TASK_REVISION_TRUTH_LIMITS.max_diff_chars),
    verifier,
    cleanup_state: 'successor_cleanup_resolved',
    forbidden_side_effect_count: forbiddenSideEffects,
    verified_success: verifiedSuccess,
  });
}

export function parseTaskRevisionTruth(value: unknown, expectedTaskId?: string): Readonly<TaskRevisionTruthSnapshot> {
  const truth = objectValue(value, 'task revision truth');
  exactKeys(truth, [
    'task_id',
    'task_state',
    'outcome',
    'current_revision',
    'current_attempt_id',
    'attempt_number',
    'revision_history',
    'pending_command',
    'cleanup',
    'execution',
  ], 'task revision truth');
  const taskId = text(truth.task_id, 'task_id');
  if (expectedTaskId !== undefined && taskId !== text(expectedTaskId, 'expected_task_id')) {
    throw new Error('task revision truth target mismatch');
  }
  if (
    !Array.isArray(truth.revision_history)
    || truth.revision_history.length < 1
    || truth.revision_history.length > TASK_REVISION_TRUTH_LIMITS.max_revisions
  ) {
    throw new Error('revision_history is invalid');
  }
  const revisions = truth.revision_history.map((revision, index) => parseRevision(revision, taskId, index));
  if (new Set(revisions.map(revision => revision.attempt_id)).size !== revisions.length) {
    throw new Error('revision attempts must be unique');
  }
  const currentRevision = integer(truth.current_revision, 'current_revision', 1);
  const attemptNumber = integer(truth.attempt_number, 'attempt_number', 1);
  const currentAttemptId = text(truth.current_attempt_id, 'current_attempt_id');
  const pending = parsePending(truth.pending_command, taskId);
  const cleanup = parseCleanup(truth.cleanup);
  const execution = parseExecution(truth.execution, taskId);
  const taskState = oneOf(
    truth.task_state,
    ['accepted', 'running', 'blocked', 'decision_required', 'terminal'] as const,
    'task_state',
  );
  const outcome = truth.outcome === null
    ? null
    : oneOf(truth.outcome, ['completed', 'failed', 'cancelled', 'interrupted', 'unknown'] as const, 'outcome');
  const current = revisions[revisions.length - 1];
  if (
    currentRevision !== revisions.length
    || current.task_revision !== currentRevision
    || current.attempt_id !== currentAttemptId
    || attemptNumber !== currentRevision
    || ((taskState === 'terminal') !== (outcome !== null))
    || (pending !== null && (
      currentRevision !== 1
      || pending.predecessor_revision !== currentRevision
      || pending.successor_revision !== 2
      || pending.predecessor_attempt_id !== currentAttemptId
    ))
    || (cleanup !== null && (
      currentRevision !== 2
      || cleanup.command_id !== current.created_by_command_id
      || cleanup.predecessor_attempt_id !== revisions[0].attempt_id
    ))
    || (execution !== null && (
      execution.task_revision !== currentRevision
      || execution.attempt_id !== currentAttemptId
      || cleanup === null
    ))
    || (currentRevision === 2 && cleanup === null)
  ) {
    throw new Error('task revision truth is self-contradictory');
  }
  return Object.freeze({
    task_id: taskId,
    task_state: taskState,
    outcome,
    current_revision: currentRevision,
    current_attempt_id: currentAttemptId,
    attempt_number: attemptNumber,
    revision_history: Object.freeze(revisions),
    pending_command: pending,
    cleanup,
    execution,
  });
}

export function parseTaskRevisionTruthStatusResponse(
  value: unknown,
  expectedTaskId: string,
): Readonly<TaskRevisionTruthSnapshot> | null {
  const envelope = objectValue(value, 'task status response');
  if (envelope.ok !== true) throw new Error('task status response is unavailable');
  const result = objectValue(envelope.result, 'task status result');
  if (!Object.prototype.hasOwnProperty.call(result, 'task_revision')) {
    throw new Error('task status response has no task revision authority');
  }
  return result.task_revision === null
    ? null
    : parseTaskRevisionTruth(result.task_revision, expectedTaskId);
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function validTaskStateAdvance(
  previous: TaskRevisionTruthSnapshot['task_state'],
  next: TaskRevisionTruthSnapshot['task_state'],
): boolean {
  if (previous === 'terminal') return next === 'terminal';
  if (previous === 'accepted') return true;
  return next !== 'accepted';
}

export class TaskRevisionTruthReplica {
  readonly #enabled: boolean;
  #connected = true;
  #connectionGeneration = 1;
  #truth: Readonly<TaskRevisionTruthSnapshot> | null = null;

  constructor(enabled: boolean) {
    this.#enabled = enabled === true;
  }

  snapshot(): Readonly<TaskRevisionTruthSnapshot> | null {
    return this.#truth;
  }

  connectionGeneration(): number {
    return this.#connectionGeneration;
  }

  disconnect(): void {
    if (this.#connected) {
      this.#connected = false;
      this.#connectionGeneration += 1;
    }
  }

  reconnect(): void {
    this.#connected = true;
  }

  adopt(value: unknown, input: Readonly<{ task_id: string; connection_generation: number }>): Readonly<TaskRevisionTruthSnapshot> {
    if (!this.#enabled) throw new Error('task revision truth is disabled');
    if (!this.#connected || input.connection_generation !== this.#connectionGeneration) {
      throw new Error('task revision truth response is stale after disconnect');
    }
    const next = parseTaskRevisionTruth(value, input.task_id);
    const previous = this.#truth;
    if (previous !== null) {
      if (previous.task_id !== next.task_id) throw new Error('task revision truth cannot cross task identity');
      if (sameValue(previous, next)) return previous;
      const prefixStable = previous.revision_history.every((record, index) => sameValue(record, next.revision_history[index]));
      if (
        next.current_revision < previous.current_revision
        || !prefixStable
        || (previous.cleanup !== null && !sameValue(previous.cleanup, next.cleanup))
        || (previous.execution !== null && !sameValue(previous.execution, next.execution))
        || !validTaskStateAdvance(previous.task_state, next.task_state)
        || (
          next.current_revision === previous.current_revision
          && previous.pending_command !== null
          && (
            next.pending_command === null
            || next.pending_command.command_id !== previous.pending_command.command_id
            || (
              previous.pending_command.application_state === 'unknown'
              && next.pending_command.application_state !== 'unknown'
            )
          )
        )
        || (previous.task_state === 'terminal' && next.outcome !== previous.outcome)
      ) {
        throw new Error('task revision truth cannot regress or rewrite authority');
      }
    }
    this.#truth = next;
    return next;
  }
}

export function taskRevisionApplicationState(truth: Readonly<TaskRevisionTruthSnapshot>): TaskRevisionApplicationState | 'none' {
  if (truth.pending_command !== null) return truth.pending_command.application_state;
  return truth.current_revision === 2 ? 'applied' : 'none';
}

export function taskRevisionWarning(truth: Readonly<TaskRevisionTruthSnapshot>): string | null {
  if (truth.pending_command?.application_state === 'unknown') return 'Predecessor cleanup is unknown; no successor may start.';
  if (truth.current_revision === 2 && truth.cleanup === null) return 'Predecessor cleanup proof is unavailable.';
  if (truth.execution?.verifier.result === 'timeout') return 'Verification timed out; success is not established.';
  if (truth.execution?.verifier.result === 'failed' || truth.execution?.verifier.result === 'mutated_fixture') {
    return 'Verification failed; success is not established.';
  }
  if (truth.execution !== null && !truth.execution.verified_success) return 'Executor evidence does not establish verified success.';
  return null;
}
