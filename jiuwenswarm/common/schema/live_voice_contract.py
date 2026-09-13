# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Minimal, dependency-free contract gate for Live Voice shared events.

This module deliberately contains only invariants that are already shared by
the P1/P2/P3 architecture.  It does not implement cancellation, task
execution, or conversation state ownership; adapters must call these gates
before dispatching work to those runtime components.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeVar


CONTRACT_VERSION: Final = "live-voice.contract.v1"


class ContractValidationError(ValueError):
    """Raised when a payload violates the shared Live Voice contract."""


class CancelScope(StrEnum):
    """Cancellation commands with intentionally non-overlapping scopes."""

    PLAYBACK_STOP = "playback.stop"
    RESPONSE_CANCEL = "response.cancel"
    ROUND_CANCEL = "round.cancel"
    TASK_CANCEL = "task.cancel"


class WorkProgressState(StrEnum):
    """Portable projection states for conversational rounds and tasks."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    BLOCKED = "blocked"
    DECISION_REQUIRED = "decision_required"
    TERMINAL = "terminal"


class WorkProgressOutcome(StrEnum):
    """Required outcome values for terminal work progress."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class InputCommitState(StrEnum):
    """Whether an observed input may cross the side-effect boundary."""

    PARTIAL = "partial"
    UNCOMMITTED = "uncommitted"
    COMMITTED = "committed"


class SideEffectTarget(StrEnum):
    """Runtime boundaries that must only receive committed input."""

    AGENT = "agent"
    TOOL = "tool"
    TASK = "task"


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def _parse_enum(enum_type: type[_EnumT], value: object, *, field: str) -> _EnumT:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise ContractValidationError(
            f"{field} must be a string; got {type(value).__name__}"
        )
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ContractValidationError(
            f"invalid {field} {value!r}; expected one of: {allowed}"
        ) from exc


def parse_cancel_scope(value: CancelScope | str) -> CancelScope:
    """Parse an exact cancel scope without widening or normalizing it."""

    return _parse_enum(CancelScope, value, field="cancel_scope")


def require_committed_input(
    input_state: InputCommitState | str,
    *,
    side_effect: SideEffectTarget | str,
) -> None:
    """Reject Agent, Tool, or Task dispatch for partial/uncommitted input."""

    parsed_state = _parse_enum(InputCommitState, input_state, field="input_state")
    parsed_target = _parse_enum(
        SideEffectTarget,
        side_effect,
        field="side_effect",
    )
    if parsed_state is not InputCommitState.COMMITTED:
        raise ContractValidationError(
            f"{parsed_target.value} side effects require input_state='committed'; "
            f"got {parsed_state.value!r}"
        )


@dataclass(frozen=True, slots=True)
class WorkProgressEvent:
    """Small serializable projection of real round/task progress.

    ``work_ref`` identifies the source round or task. ``provenance`` identifies
    the real source event or adapter observation from which this projection was
    derived.  Neither field may be invented or omitted by a bridge.
    """

    work_ref: str
    provenance: str
    seq: int
    state: WorkProgressState | str
    outcome: WorkProgressOutcome | str | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        self._validate_required_text("work_ref", self.work_ref)
        self._validate_required_text("provenance", self.provenance)

        if isinstance(self.seq, bool) or not isinstance(self.seq, int):
            raise ContractValidationError(
                f"seq must be a non-negative integer; got {self.seq!r}"
            )
        if self.seq < 0:
            raise ContractValidationError(
                f"seq must be a non-negative integer; got {self.seq}"
            )
        if self.contract_version != CONTRACT_VERSION:
            raise ContractValidationError(
                "unsupported contract_version "
                f"{self.contract_version!r}; expected {CONTRACT_VERSION!r}"
            )

        state = _parse_enum(WorkProgressState, self.state, field="state")
        outcome = (
            None
            if self.outcome is None
            else _parse_enum(WorkProgressOutcome, self.outcome, field="outcome")
        )

        if state is WorkProgressState.TERMINAL and outcome is None:
            raise ContractValidationError(
                "terminal work progress requires a valid outcome"
            )
        if state is not WorkProgressState.TERMINAL and outcome is not None:
            raise ContractValidationError(
                f"non-terminal state {state.value!r} must not include outcome"
            )

        object.__setattr__(self, "state", state)
        object.__setattr__(self, "outcome", outcome)

    @staticmethod
    def _validate_required_text(field: str, value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ContractValidationError(f"{field} must be a non-empty string")

    def to_dict(self) -> dict[str, str | int | None]:
        """Return a JSON-serializable contract payload."""

        return {
            "contract_version": self.contract_version,
            "work_ref": self.work_ref,
            "provenance": self.provenance,
            "seq": self.seq,
            "state": self.state.value,
            "outcome": self.outcome.value if self.outcome is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> WorkProgressEvent:
        """Validate and deserialize a mapping at an adapter boundary."""

        if not isinstance(payload, Mapping):
            raise ContractValidationError(
                f"work progress payload must be a mapping; got {type(payload).__name__}"
            )

        required = {
            "contract_version",
            "work_ref",
            "provenance",
            "seq",
            "state",
        }
        allowed = required | {"outcome"}
        missing = sorted(required - payload.keys())
        if missing:
            raise ContractValidationError(
                f"missing required field(s): {', '.join(missing)}"
            )
        unknown = sorted(payload.keys() - allowed)
        if unknown:
            raise ContractValidationError(
                f"unknown field(s) for {CONTRACT_VERSION}: {', '.join(unknown)}"
            )

        return cls(
            contract_version=payload["contract_version"],
            work_ref=payload["work_ref"],
            provenance=payload["provenance"],
            seq=payload["seq"],
            state=payload["state"],
            outcome=payload.get("outcome"),
        )


__all__ = [
    "CONTRACT_VERSION",
    "CancelScope",
    "ContractValidationError",
    "InputCommitState",
    "SideEffectTarget",
    "WorkProgressEvent",
    "WorkProgressOutcome",
    "WorkProgressState",
    "parse_cancel_scope",
    "require_committed_input",
]
