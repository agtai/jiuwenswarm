# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Retained Task contract projections; production execution uses PersistentTaskCore.

The old deterministic in-memory implementation lives in tests/support/live_voice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ScopeRef,
    TerminalOutcome,
    canonical_json_bytes,
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
