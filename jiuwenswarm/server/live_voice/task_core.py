# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Task state and command values used by formal task intent and voice bridges."""

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
