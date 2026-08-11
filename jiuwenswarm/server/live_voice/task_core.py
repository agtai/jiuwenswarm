# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Deterministic P3-alpha Task Core with replay and exact authorization."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    LifecycleKind,
    ScopeRef,
    TerminalOutcome,
    canonical_json_bytes,
    validate_transition,
)


class TaskCoreViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class TaskState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    BLOCKED = "blocked"
    DECISION_REQUIRED = "decision_required"
    TERMINAL = "terminal"


class AttemptState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    subject_id: str
    scope: ScopeRef
    allowed_operations: frozenset[str]


@dataclass(frozen=True, slots=True)
class TaskSpec:
    name: str
    instruction: str
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.instruction.strip():
            raise TaskCoreViolation(
                "INVALID_TASK_SPEC",
                "task name and instruction must be non-empty",
                ErrorCode.INVALID_ARGUMENT,
            )
        keys: set[str] = set()
        for key, value in self.attributes:
            if not key.strip() or not value.strip() or key in keys:
                raise TaskCoreViolation(
                    "INVALID_TASK_ATTRIBUTES",
                    "task attribute keys must be unique and values non-empty",
                    ErrorCode.INVALID_ARGUMENT,
                )
            keys.add(key)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "instruction": self.instruction,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class TaskCommand:
    request_id: str
    command_id: str
    operation: str
    scope: ScopeRef
    target_task_id: str | None
    spec: TaskSpec | None
    origin_commit_id: str
    previous_attempt_id: str | None = None
    previous_outcome: TerminalOutcome | None = None
    attempt_number: int | None = None

    def fingerprint(self) -> bytes:
        return canonical_json_bytes(
            {
                "command_id": self.command_id,
                "operation": self.operation,
                "scope": self.scope.to_dict(),
                "target_task_id": self.target_task_id,
                "spec": None if self.spec is None else self.spec.to_dict(),
                "origin_commit_id": self.origin_commit_id,
                "previous_attempt_id": self.previous_attempt_id,
                "previous_outcome": (
                    None
                    if self.previous_outcome is None
                    else self.previous_outcome.value
                ),
                "attempt_number": self.attempt_number,
            }
        )


@dataclass(frozen=True, slots=True)
class TaskQuery:
    request_id: str
    operation: str
    scope: ScopeRef
    task_id: str | None = None
    after_seq: int = -1


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    scope: ScopeRef
    spec: TaskSpec
    state: TaskState
    attempt_id: str
    cancel_requested: bool = False
    dispatch_fenced: bool = False
    outcome: TerminalOutcome | None = None


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: str
    task_id: str
    state: AttemptState
    outcome: TerminalOutcome | None = None
    attempt_number: int = 1


@dataclass(frozen=True, slots=True)
class TaskEvent:
    event_id: str
    task_id: str
    attempt_id: str
    seq: int
    event_type: str
    state: str
    outcome: str | None
    causation_id: str
    details: tuple[tuple[str, str | int], ...] = ()


@dataclass(frozen=True, slots=True)
class WorkProgress:
    task_id: str
    attempt_id: str
    state: str
    outcome: str | None
    source_event_id: str


def project_work_progress(event: TaskEvent) -> WorkProgress:
    return WorkProgress(
        task_id=event.task_id,
        attempt_id=event.attempt_id,
        state=event.state,
        outcome=event.outcome,
        source_event_id=event.event_id,
    )


@dataclass(frozen=True, slots=True)
class DispatchIntent:
    task_id: str
    attempt_id: str
    command_id: str
    scope: ScopeRef
    spec: TaskSpec


@dataclass(frozen=True, slots=True)
class CancelIntent:
    task_id: str
    attempt_id: str
    command_id: str
    scope: ScopeRef


@dataclass(frozen=True, slots=True)
class TaskCommandResult:
    request_id: str
    command_id: str
    applied: bool
    task_id: str
    attempt_id: str
    cancel_acknowledged: bool = False
    attempt_number: int = 1
    previous_attempt_id: str | None = None


@dataclass(frozen=True, slots=True)
class TaskCoreSnapshot:
    tasks: tuple[TaskRecord, ...]
    attempts: tuple[AttemptRecord, ...]
    events: tuple[TaskEvent, ...]
    dispatch_intents: tuple[DispatchIntent, ...]
    cancel_intents: tuple[CancelIntent, ...]
    mutation_version: int


class TaskCore:
    _COMMANDS = frozenset({"task.create", "task.cancel", "task.retry"})
    _QUERIES = frozenset({"task.get", "task.list", "task.status", "task.events"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, TaskRecord] = {}
        self._attempts: dict[str, AttemptRecord] = {}
        self._events: dict[str, list[TaskEvent]] = {}
        self._dispatch: list[DispatchIntent] = []
        self._cancels: list[CancelIntent] = []
        self._commands: dict[str, tuple[bytes, TaskCommandResult]] = {}
        self._next_id = 1
        self._mutation_version = 0

    def execute(
        self, command: TaskCommand, authorization: AuthorizationContext
    ) -> TaskCommandResult:
        self._authorize(command.scope, command.operation, authorization)
        self._validate_command(command)
        with self._lock:
            existing = self._commands.get(command.command_id)
            fingerprint = command.fingerprint()
            if existing is not None:
                if existing[0] != fingerprint:
                    raise TaskCoreViolation(
                        "COMMAND_FINGERPRINT_CONFLICT",
                        "command_id cannot change its meaning",
                        ErrorCode.CONFLICT,
                    )
                prior = existing[1]
                return replace(
                    prior,
                    request_id=command.request_id,
                    applied=(
                        prior.applied if command.operation == "task.retry" else False
                    ),
                )
            if command.operation == "task.create":
                result = self._create(command)
            elif command.operation == "task.cancel":
                result = self._cancel(command)
            else:
                result = self._retry(command)
            self._commands[command.command_id] = (fingerprint, result)
            return result

    def query(
        self, query: TaskQuery, authorization: AuthorizationContext
    ) -> TaskRecord | tuple[TaskRecord, ...] | tuple[TaskEvent, ...]:
        self._authorize(query.scope, query.operation, authorization)
        if query.operation not in self._QUERIES:
            raise TaskCoreViolation(
                "UNSUPPORTED_TASK_QUERY",
                f"unsupported query {query.operation!r}",
                ErrorCode.UNSUPPORTED,
            )
        if type(query.after_seq) is not int or query.after_seq < -1:
            raise TaskCoreViolation(
                "INVALID_EVENT_CURSOR",
                "after_seq must be an integer at least -1",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._lock:
            if query.operation == "task.list":
                return tuple(
                    task for task in self._tasks.values() if task.scope == query.scope
                )
            task = self._require_task(query.task_id, query.scope)
            if query.operation in {"task.get", "task.status"}:
                return task
            return tuple(
                event
                for event in self._events.get(task.task_id, [])
                if event.seq > query.after_seq
            )

    def mark_attempt_running(
        self,
        task_id: str,
        attempt_id: str,
        authorization: AuthorizationContext,
    ) -> TaskEvent:
        return self._transition_attempt(
            task_id,
            attempt_id,
            AttemptState.RUNNING,
            authorization,
            outcome=None,
        )

    def finish_attempt(
        self,
        task_id: str,
        attempt_id: str,
        outcome: TerminalOutcome,
        authorization: AuthorizationContext,
    ) -> tuple[TaskEvent, TaskEvent]:
        attempt_event = self._transition_attempt(
            task_id,
            attempt_id,
            AttemptState.TERMINAL,
            authorization,
            outcome=outcome,
        )
        with self._lock:
            task = self._require_task(task_id, authorization.scope)
            validate_transition(
                LifecycleKind.TASK,
                task.state.value,
                TaskState.TERMINAL.value,
                outcome=outcome,
            )
            updated = replace(task, state=TaskState.TERMINAL, outcome=outcome)
            self._tasks[task_id] = updated
            task_event = self._append_event(
                task_id,
                attempt_id,
                "task.terminal",
                TaskState.TERMINAL,
                outcome,
                attempt_event.event_id,
            )
            self._mutation_version += 1
            return attempt_event, task_event

    def transition_task(
        self,
        task_id: str,
        target: TaskState,
        authorization: AuthorizationContext,
    ) -> TaskEvent:
        self._authorize(authorization.scope, "task.execute", authorization)
        with self._lock:
            task = self._require_task(task_id, authorization.scope)
            if target is TaskState.TERMINAL:
                raise TaskCoreViolation(
                    "ATTEMPT_EVIDENCE_REQUIRED",
                    "terminal task state must come from a terminal attempt",
                    ErrorCode.CONFLICT,
                )
            validate_transition(LifecycleKind.TASK, task.state.value, target.value)
            self._tasks[task_id] = replace(task, state=target)
            event = self._append_event(
                task_id,
                task.attempt_id,
                f"task.{target.value}",
                target,
                None,
                "task-core",
            )
            self._mutation_version += 1
            return event

    def snapshot(self) -> TaskCoreSnapshot:
        with self._lock:
            return TaskCoreSnapshot(
                tasks=tuple(self._tasks.values()),
                attempts=tuple(self._attempts.values()),
                events=tuple(
                    event for events in self._events.values() for event in events
                ),
                dispatch_intents=tuple(self._dispatch),
                cancel_intents=tuple(self._cancels),
                mutation_version=self._mutation_version,
            )

    def _create(self, command: TaskCommand) -> TaskCommandResult:
        assert command.spec is not None
        task_id = f"task-{self._next_id}"
        attempt_id = f"attempt-{self._next_id}"
        self._next_id += 1
        task = TaskRecord(
            task_id,
            command.scope,
            command.spec,
            TaskState.ACCEPTED,
            attempt_id,
        )
        attempt = AttemptRecord(attempt_id, task_id, AttemptState.ACCEPTED)
        intent = DispatchIntent(
            task_id, attempt_id, command.command_id, command.scope, command.spec
        )
        self._tasks[task_id] = task
        self._attempts[attempt_id] = attempt
        self._dispatch.append(intent)
        self._append_event(
            task_id,
            attempt_id,
            "task.accepted",
            TaskState.ACCEPTED,
            None,
            command.command_id,
        )
        self._mutation_version += 1
        return TaskCommandResult(
            command.request_id,
            command.command_id,
            True,
            task_id,
            attempt_id,
        )

    def _cancel(self, command: TaskCommand) -> TaskCommandResult:
        task = self._require_task(command.target_task_id, command.scope)
        attempt = self._attempts[task.attempt_id]
        if task.state is TaskState.TERMINAL:
            raise TaskCoreViolation(
                "TASK_ALREADY_TERMINAL",
                "a terminal task cannot accept cancellation",
                ErrorCode.CONFLICT,
            )
        if task.cancel_requested:
            return TaskCommandResult(
                command.request_id,
                command.command_id,
                False,
                task.task_id,
                task.attempt_id,
                cancel_acknowledged=True,
                attempt_number=attempt.attempt_number,
            )
        self._tasks[task.task_id] = replace(
            task, cancel_requested=True, dispatch_fenced=True
        )
        self._cancels.append(
            CancelIntent(
                task.task_id,
                task.attempt_id,
                command.command_id,
                command.scope,
            )
        )
        self._append_event(
            task.task_id,
            task.attempt_id,
            "task.cancel_acknowledged",
            task.state,
            None,
            command.command_id,
        )
        self._mutation_version += 1
        return TaskCommandResult(
            command.request_id,
            command.command_id,
            True,
            task.task_id,
            task.attempt_id,
            cancel_acknowledged=True,
            attempt_number=attempt.attempt_number,
        )

    def _retry(self, command: TaskCommand) -> TaskCommandResult:
        task = self._require_task(command.target_task_id, command.scope)
        attempt = self._attempts[task.attempt_id]
        if (
            task.state is not TaskState.TERMINAL
            or attempt.state is not AttemptState.TERMINAL
        ):
            raise TaskCoreViolation(
                "TASK_RETRY_REQUIRES_TERMINAL",
                "task.retry requires a terminal current attempt",
                ErrorCode.CONFLICT,
            )
        if attempt.attempt_number >= 3:
            raise TaskCoreViolation(
                "TASK_RETRY_LIMIT_EXCEEDED",
                "formal task permits at most three total attempts",
                ErrorCode.CONFLICT,
            )
        if (
            task.outcome
            not in {
                TerminalOutcome.CANCELLED,
                TerminalOutcome.COMPLETED,
            }
            or attempt.outcome != task.outcome
        ):
            raise TaskCoreViolation(
                "TASK_RETRY_OUTCOME_NOT_ELIGIBLE",
                "only cancelled or completed attempts can be retried",
                ErrorCode.CONFLICT,
            )
        next_number = attempt.attempt_number + 1
        if (
            command.previous_attempt_id != attempt.attempt_id
            or command.previous_outcome != attempt.outcome
            or command.attempt_number != next_number
        ):
            raise TaskCoreViolation(
                "TASK_RETRY_PRECONDITION_STALE",
                "task.retry lineage does not match the current terminal attempt",
                ErrorCode.STALE,
            )
        attempt_id = f"attempt-{self._next_id}"
        self._next_id += 1
        self._attempts[attempt_id] = AttemptRecord(
            attempt_id,
            task.task_id,
            AttemptState.ACCEPTED,
            attempt_number=next_number,
        )
        self._tasks[task.task_id] = replace(
            task,
            state=TaskState.ACCEPTED,
            attempt_id=attempt_id,
            cancel_requested=False,
            dispatch_fenced=False,
            outcome=None,
        )
        self._dispatch.append(
            DispatchIntent(
                task.task_id,
                attempt_id,
                command.command_id,
                command.scope,
                task.spec,
            )
        )
        self._append_event(
            task.task_id,
            attempt_id,
            "task.retry_accepted",
            TaskState.ACCEPTED,
            None,
            command.command_id,
            details={
                "command_id": command.command_id,
                "retry_of_attempt_id": attempt.attempt_id,
                "previous_outcome": attempt.outcome.value,
                "attempt_number": next_number,
            },
        )
        self._mutation_version += 1
        return TaskCommandResult(
            command.request_id,
            command.command_id,
            True,
            task.task_id,
            attempt_id,
            attempt_number=next_number,
            previous_attempt_id=attempt.attempt_id,
        )

    def _transition_attempt(
        self,
        task_id: str,
        attempt_id: str,
        target: AttemptState,
        authorization: AuthorizationContext,
        *,
        outcome: TerminalOutcome | None,
    ) -> TaskEvent:
        self._authorize(authorization.scope, "task.execute", authorization)
        with self._lock:
            task = self._require_task(task_id, authorization.scope)
            if task.attempt_id != attempt_id:
                raise TaskCoreViolation(
                    "ATTEMPT_SCOPE_MISMATCH",
                    "attempt does not belong to the exact task",
                    ErrorCode.PERMISSION_DENIED,
                )
            attempt = self._attempts[attempt_id]
            validate_transition(
                LifecycleKind.ATTEMPT,
                attempt.state.value,
                target.value,
                outcome=outcome,
            )
            updated = replace(attempt, state=target, outcome=outcome)
            self._attempts[attempt_id] = updated
            event = self._append_event(
                task_id,
                attempt_id,
                f"attempt.{target.value}",
                target,
                outcome,
                attempt_id,
            )
            if target is AttemptState.RUNNING and task.state is TaskState.ACCEPTED:
                self._tasks[task_id] = replace(task, state=TaskState.RUNNING)
                self._append_event(
                    task_id,
                    attempt_id,
                    "task.running",
                    TaskState.RUNNING,
                    None,
                    event.event_id,
                )
            self._mutation_version += 1
            return event

    def _append_event(
        self,
        task_id: str,
        attempt_id: str,
        event_type: str,
        state: StrEnum,
        outcome: TerminalOutcome | None,
        causation_id: str,
        details: dict[str, str | int] | None = None,
    ) -> TaskEvent:
        events = self._events.setdefault(task_id, [])
        event = TaskEvent(
            event_id=f"event-{task_id}-{len(events)}",
            task_id=task_id,
            attempt_id=attempt_id,
            seq=len(events),
            event_type=event_type,
            state=state.value,
            outcome=None if outcome is None else outcome.value,
            causation_id=causation_id,
            details=tuple(sorted((details or {}).items())),
        )
        events.append(event)
        return event

    def _validate_command(self, command: TaskCommand) -> None:
        if command.operation not in self._COMMANDS:
            raise TaskCoreViolation(
                "UNSUPPORTED_TASK_COMMAND",
                f"unsupported command {command.operation!r}",
                ErrorCode.UNSUPPORTED,
            )
        for value, field in (
            (command.request_id, "request_id"),
            (command.command_id, "command_id"),
            (command.origin_commit_id, "origin_commit_id"),
        ):
            if not value.strip():
                raise TaskCoreViolation(
                    "INVALID_TASK_COMMAND",
                    f"{field} must be non-empty",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if command.operation == "task.create":
            if (
                command.target_task_id is not None
                or command.spec is None
                or command.previous_attempt_id is not None
                or command.previous_outcome is not None
                or command.attempt_number is not None
            ):
                raise TaskCoreViolation(
                    "INVALID_TASK_CREATE",
                    "task.create requires a spec and no client task id",
                    ErrorCode.INVALID_ARGUMENT,
                )
        elif command.operation == "task.cancel" and (
            command.target_task_id is None
            or command.spec is not None
            or command.previous_attempt_id is not None
            or command.previous_outcome is not None
            or command.attempt_number is not None
        ):
            raise TaskCoreViolation(
                "INVALID_TASK_CANCEL",
                "task.cancel requires an exact task id and no spec",
                ErrorCode.INVALID_ARGUMENT,
            )
        elif command.operation == "task.retry" and (
            command.target_task_id is None
            or command.spec is not None
            or not isinstance(command.previous_outcome, TerminalOutcome)
            or type(command.attempt_number) is not int
            or command.attempt_number not in {2, 3}
            or type(command.previous_attempt_id) is not str
            or not command.previous_attempt_id.strip()
        ):
            raise TaskCoreViolation(
                "INVALID_TASK_RETRY",
                "task.retry requires exact predecessor lineage and no replacement spec",
                ErrorCode.INVALID_ARGUMENT,
            )

    @staticmethod
    def _authorize(
        scope: ScopeRef, operation: str, authorization: AuthorizationContext
    ) -> None:
        if (
            authorization.subject_id != scope.subject_id
            or authorization.scope != scope
            or authorization.scope.assurance is not Assurance.AUTHENTICATED
            or operation not in authorization.allowed_operations
        ):
            raise TaskCoreViolation(
                "TASK_AUTHORIZATION_DENIED",
                "trusted authorization does not permit the exact scope and operation",
                ErrorCode.PERMISSION_DENIED,
            )

    def _require_task(self, task_id: str | None, scope: ScopeRef) -> TaskRecord:
        task = None if task_id is None else self._tasks.get(task_id)
        if task is None or task.scope != scope:
            raise TaskCoreViolation(
                "TASK_NOT_FOUND",
                "task is unavailable in the authorized scope",
                ErrorCode.NOT_FOUND,
            )
        return task
