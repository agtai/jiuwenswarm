# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure contract kernel for the bounded S8.5 task-revision profile.

This module deliberately owns no database, Executor process, Voice parser, or UI.
It canonicalizes one already-committed revision request and decides whether it
may become a fence candidate against one Task-Core-owned authority snapshot.
An accepted plan is not proof that the predecessor stopped or a successor ran.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    Assurance,
    CommandEnvelope,
    ErrorCode,
    IdentityKind,
    ScopeRef,
    canonical_json_bytes,
)


S8_5_TASK_REVISION_PROFILE = "live-voice.s8-5-task-revision.v1"
S8_5_TASK_REVISION_EXTENSION = "jiuwenswarm.task_revision"
S8_5_TASK_REVISION_OPERATIONS = frozenset(
    {"task.provide_input", "task.update_constraints"}
)
MAX_REVISION_FACTS = 16
MAX_TASK_REVISIONS = 2
MAX_FACT_CHARACTERS = 2_000
MAX_WRITE_SCOPES = 16


class TaskRevisionViolation(ValueError):
    """Stable fail-closed contract error."""

    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class TaskRevisionOperation(StrEnum):
    PROVIDE_INPUT = "task.provide_input"
    UPDATE_CONSTRAINTS = "task.update_constraints"


class RevisionApplicationState(StrEnum):
    ACCEPTED = "accepted"
    FENCING = "fencing"
    APPLIED = "applied"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


def _violation(
    reason: str,
    message: str,
    code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
) -> TaskRevisionViolation:
    return TaskRevisionViolation(reason, message, code)


def _text(value: object, field_name: str, *, maximum: int | None = None) -> str:
    if type(value) is not str or not value.strip():
        raise _violation(
            "INVALID_TASK_REVISION_FIELD",
            f"{field_name} must be a non-empty string",
        )
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise _violation(
            "INVALID_TASK_REVISION_UNICODE",
            f"{field_name} must contain Unicode scalar values",
        )
    if maximum is not None and len(value) > maximum:
        raise _violation(
            "TASK_REVISION_FIELD_TOO_LARGE",
            f"{field_name} exceeds its bounded size",
        )
    return value


def _positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SAFE_INTEGER:
        raise _violation(
            "INVALID_TASK_REVISION_NUMBER",
            f"{field_name} must be a positive JSON-safe integer",
        )
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise _violation(
            "INVALID_TASK_REVISION_TIMESTAMP",
            f"{field_name} must be RFC3339",
        ) from error
    if parsed.tzinfo is None:
        raise _violation(
            "INVALID_TASK_REVISION_TIMESTAMP",
            f"{field_name} must include a timezone",
        )
    return parsed.astimezone(UTC)


def _scope(value: object, field_name: str) -> ScopeRef:
    if type(value) is not ScopeRef or type(value.assurance) is not Assurance:
        raise _violation(
            "INVALID_TASK_REVISION_SCOPE",
            f"{field_name} must be an exact ScopeRef",
        )
    try:
        normalized = ScopeRef.from_dict(value.to_dict())
    except (AttributeError, TypeError, ValueError) as error:
        raise _violation(
            "INVALID_TASK_REVISION_SCOPE",
            f"{field_name} is invalid",
        ) from error
    if normalized != value:
        raise _violation(
            "INVALID_TASK_REVISION_SCOPE",
            f"{field_name} is not canonical",
        )
    return normalized


def _relative_path(value: object, field_name: str) -> str:
    path = _text(value, field_name, maximum=512)
    if "\\" in path or path.startswith("/") or ":" in path:
        raise _violation(
            "INVALID_TASK_REVISION_WRITE_SCOPE",
            f"{field_name} must be a normalized fixture-relative POSIX path",
        )
    normalized = posixpath.normpath(path)
    if (
        normalized in {"", ".", ".."}
        or normalized.startswith("../")
        or normalized != path.rstrip("/")
    ):
        raise _violation(
            "INVALID_TASK_REVISION_WRITE_SCOPE",
            f"{field_name} must be a normalized fixture-relative POSIX path",
        )
    return normalized


def _path_within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


@dataclass(frozen=True, slots=True)
class TaskRevisionConstraints:
    """Complete effective constraints supplied by trusted fixture policy."""

    write_scope: tuple[str, ...]
    dependency_policy: str = "locked"
    public_api_policy: str = "preserve"
    configuration_policy: str = "preserve"
    regression_verifier_required: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.write_scope) is not tuple
            or not self.write_scope
            or len(self.write_scope) > MAX_WRITE_SCOPES
        ):
            raise _violation(
                "INVALID_TASK_REVISION_WRITE_SCOPE",
                "write_scope must contain a bounded non-empty path tuple",
            )
        normalized = tuple(
            _relative_path(path, f"write_scope[{index}]")
            for index, path in enumerate(self.write_scope)
        )
        if len(set(normalized)) != len(normalized):
            raise _violation(
                "INVALID_TASK_REVISION_WRITE_SCOPE",
                "write_scope paths must be unique",
            )
        for index, path in enumerate(normalized):
            if any(
                index != other_index and _path_within(path, other)
                for other_index, other in enumerate(normalized)
            ):
                raise _violation(
                    "INVALID_TASK_REVISION_WRITE_SCOPE",
                    "write_scope must not contain redundant descendant paths",
                )
        if self.dependency_policy != "locked":
            raise _violation(
                "TASK_REVISION_DEPENDENCY_CHANGE_FORBIDDEN",
                "dependency policy must remain locked",
                ErrorCode.PERMISSION_DENIED,
            )
        if self.public_api_policy != "preserve":
            raise _violation(
                "TASK_REVISION_PUBLIC_API_CHANGE_FORBIDDEN",
                "public API policy must remain preserve",
                ErrorCode.PERMISSION_DENIED,
            )
        if self.configuration_policy != "preserve":
            raise _violation(
                "TASK_REVISION_CONFIGURATION_CHANGE_FORBIDDEN",
                "configuration policy must remain preserve",
                ErrorCode.PERMISSION_DENIED,
            )
        if type(self.regression_verifier_required) is not bool:
            raise _violation(
                "INVALID_TASK_REVISION_CONSTRAINT",
                "regression_verifier_required must be boolean",
            )
        object.__setattr__(self, "write_scope", tuple(sorted(normalized)))

    def to_dict(self) -> dict[str, object]:
        return {
            "write_scope": list(self.write_scope),
            "dependency_policy": self.dependency_policy,
            "public_api_policy": self.public_api_policy,
            "configuration_policy": self.configuration_policy,
            "regression_verifier_required": self.regression_verifier_required,
        }

    @classmethod
    def from_dict(cls, payload: object) -> TaskRevisionConstraints:
        if type(payload) is not dict or set(payload) != {
            "write_scope",
            "dependency_policy",
            "public_api_policy",
            "configuration_policy",
            "regression_verifier_required",
        }:
            raise _violation(
                "INVALID_TASK_REVISION_CONSTRAINTS",
                "effective constraints have incomplete or unknown fields",
            )
        write_scope = payload["write_scope"]
        if type(write_scope) is not list:
            raise _violation(
                "INVALID_TASK_REVISION_WRITE_SCOPE",
                "write_scope must be an array",
            )
        return cls(
            write_scope=tuple(write_scope),
            dependency_policy=payload["dependency_policy"],  # type: ignore[arg-type]
            public_api_policy=payload["public_api_policy"],  # type: ignore[arg-type]
            configuration_policy=payload["configuration_policy"],  # type: ignore[arg-type]
            regression_verifier_required=payload[  # type: ignore[arg-type]
                "regression_verifier_required"
            ],
        )

    def tighten(self, patch: TaskConstraintPatch) -> TaskRevisionConstraints:
        write_scope = self.write_scope
        if patch.write_scope is not None:
            for path in patch.write_scope:
                if not any(_path_within(path, parent) for parent in self.write_scope):
                    raise _violation(
                        "TASK_REVISION_CONSTRAINT_RELAXATION_FORBIDDEN",
                        "write_scope may only narrow the current scope",
                        ErrorCode.PERMISSION_DENIED,
                    )
            write_scope = patch.write_scope
        verifier_required = self.regression_verifier_required
        if patch.regression_verifier_required is not None:
            if verifier_required and not patch.regression_verifier_required:
                raise _violation(
                    "TASK_REVISION_CONSTRAINT_RELAXATION_FORBIDDEN",
                    "required regression verification cannot be disabled",
                    ErrorCode.PERMISSION_DENIED,
                )
            verifier_required = patch.regression_verifier_required
        return TaskRevisionConstraints(
            write_scope=write_scope,
            regression_verifier_required=verifier_required,
        )


@dataclass(frozen=True, slots=True)
class TaskConstraintPatch:
    write_scope: tuple[str, ...] | None = None
    regression_verifier_required: bool | None = None

    def __post_init__(self) -> None:
        if self.write_scope is None and self.regression_verifier_required is None:
            raise _violation(
                "INVALID_TASK_REVISION_CONSTRAINT_PATCH",
                "constraint patch must contain at least one allowlisted field",
            )
        if self.write_scope is not None:
            if type(self.write_scope) is not tuple or not self.write_scope:
                raise _violation(
                    "INVALID_TASK_REVISION_WRITE_SCOPE",
                    "write_scope patch must be a non-empty immutable tuple",
                )
            normalized = TaskRevisionConstraints(self.write_scope).write_scope
            object.__setattr__(self, "write_scope", normalized)
        if (
            self.regression_verifier_required is not None
            and type(self.regression_verifier_required) is not bool
        ):
            raise _violation(
                "INVALID_TASK_REVISION_CONSTRAINT_PATCH",
                "regression_verifier_required patch must be boolean",
            )

    @classmethod
    def from_dict(cls, payload: object) -> TaskConstraintPatch:
        if type(payload) is not dict or not payload:
            raise _violation(
                "INVALID_TASK_REVISION_CONSTRAINT_PATCH",
                "constraint patch must be a non-empty object",
            )
        allowed = {"write_scope", "regression_verifier_required"}
        if not set(payload).issubset(allowed):
            raise _violation(
                "TASK_REVISION_CONSTRAINT_NOT_ALLOWLISTED",
                "constraint patch contains a key outside the S8.5 allowlist",
                ErrorCode.PERMISSION_DENIED,
            )
        raw_scope = payload.get("write_scope")
        write_scope: tuple[str, ...] | None = None
        if raw_scope is not None:
            if type(raw_scope) is not list or not raw_scope:
                raise _violation(
                    "INVALID_TASK_REVISION_WRITE_SCOPE",
                    "write_scope patch must be a non-empty array",
                )
            write_scope = tuple(raw_scope)
        verifier = payload.get("regression_verifier_required")
        if verifier is not None and type(verifier) is not bool:
            raise _violation(
                "INVALID_TASK_REVISION_CONSTRAINT_PATCH",
                "regression_verifier_required patch must be boolean",
            )
        return cls(write_scope, verifier)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {}
        if self.write_scope is not None:
            result["write_scope"] = list(self.write_scope)
        if self.regression_verifier_required is not None:
            result["regression_verifier_required"] = self.regression_verifier_required
        return result


@dataclass(frozen=True, slots=True)
class TaskRevisionCommand:
    command_id: str
    operation: TaskRevisionOperation
    scope: ScopeRef
    task_id: str
    expected_task_revision: int
    expected_attempt_id: str
    origin_commit_id: str
    facts: tuple[str, ...] = ()
    constraint_patch: TaskConstraintPatch | None = None

    def __post_init__(self) -> None:
        _text(self.command_id, "command_id")
        if type(self.operation) is not TaskRevisionOperation:
            raise _violation(
                "INVALID_TASK_REVISION_OPERATION",
                "operation must be an exact S8.5 revision operation",
            )
        _scope(self.scope, "scope")
        _text(self.task_id, "task_id")
        _positive_int(self.expected_task_revision, "expected_task_revision")
        _text(self.expected_attempt_id, "expected_attempt_id")
        _text(self.origin_commit_id, "origin_commit_id")
        if type(self.facts) is not tuple:
            raise _violation(
                "INVALID_TASK_REVISION_FACTS", "facts must be an immutable tuple"
            )
        normalized_facts = tuple(
            _text(fact, f"facts[{index}]", maximum=MAX_FACT_CHARACTERS)
            for index, fact in enumerate(self.facts)
        )
        if len(normalized_facts) > MAX_REVISION_FACTS or len(
            set(normalized_facts)
        ) != len(normalized_facts):
            raise _violation(
                "INVALID_TASK_REVISION_FACTS",
                "facts must be bounded and unique",
            )
        if self.operation is TaskRevisionOperation.PROVIDE_INPUT:
            if not normalized_facts or self.constraint_patch is not None:
                raise _violation(
                    "INVALID_TASK_REVISION_PAYLOAD",
                    "task.provide_input requires only additive facts",
                )
        elif normalized_facts or type(self.constraint_patch) is not TaskConstraintPatch:
            raise _violation(
                "INVALID_TASK_REVISION_PAYLOAD",
                "task.update_constraints requires only an allowlisted patch",
            )
        object.__setattr__(self, "facts", normalized_facts)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "expected_task_revision": self.expected_task_revision,
            "expected_attempt_id": self.expected_attempt_id,
        }
        if self.operation is TaskRevisionOperation.PROVIDE_INPUT:
            payload["facts"] = list(self.facts)
        else:
            assert self.constraint_patch is not None
            payload["constraints"] = self.constraint_patch.to_dict()
        return {
            "profile": S8_5_TASK_REVISION_PROFILE,
            "command_id": self.command_id,
            "operation": self.operation.value,
            "scope": self.scope.to_dict(),
            "task_id": self.task_id,
            "origin_commit_id": self.origin_commit_id,
            "payload": payload,
        }

    @classmethod
    def from_dict(cls, payload: object) -> TaskRevisionCommand:
        if type(payload) is not dict or set(payload) != {
            "profile",
            "command_id",
            "operation",
            "scope",
            "task_id",
            "origin_commit_id",
            "payload",
        }:
            raise _violation(
                "INVALID_TASK_REVISION_COMMAND",
                "revision command fields are incomplete or unknown",
            )
        if payload["profile"] != S8_5_TASK_REVISION_PROFILE:
            raise _violation(
                "UNSUPPORTED_TASK_REVISION_PROFILE",
                "revision command profile is unavailable",
                ErrorCode.UNSUPPORTED,
            )
        try:
            operation = TaskRevisionOperation(payload["operation"])
        except (TypeError, ValueError) as error:
            raise _violation(
                "UNSUPPORTED_TASK_REVISION_OPERATION",
                "revision command operation is unsupported",
                ErrorCode.UNSUPPORTED,
            ) from error
        body = payload["payload"]
        if type(body) is not dict:
            raise _violation(
                "INVALID_TASK_REVISION_PAYLOAD",
                "revision command payload must be an object",
            )
        common = {"expected_task_revision", "expected_attempt_id"}
        expected = common | (
            {"facts"}
            if operation is TaskRevisionOperation.PROVIDE_INPUT
            else {"constraints"}
        )
        if set(body) != expected:
            raise _violation(
                "INVALID_TASK_REVISION_PAYLOAD",
                "revision command payload fields are incomplete or unknown",
            )
        facts: tuple[str, ...] = ()
        patch: TaskConstraintPatch | None = None
        if operation is TaskRevisionOperation.PROVIDE_INPUT:
            raw_facts = body["facts"]
            if type(raw_facts) is not list:
                raise _violation(
                    "INVALID_TASK_REVISION_FACTS", "facts must be an array"
                )
            facts = tuple(raw_facts)
        else:
            patch = TaskConstraintPatch.from_dict(body["constraints"])
        return cls(
            command_id=payload["command_id"],  # type: ignore[arg-type]
            operation=operation,
            scope=ScopeRef.from_dict(payload["scope"]),
            task_id=payload["task_id"],  # type: ignore[arg-type]
            expected_task_revision=body["expected_task_revision"],  # type: ignore[arg-type]
            expected_attempt_id=body["expected_attempt_id"],  # type: ignore[arg-type]
            origin_commit_id=payload["origin_commit_id"],  # type: ignore[arg-type]
            facts=facts,
            constraint_patch=patch,
        )

    @classmethod
    def from_envelope(cls, envelope: CommandEnvelope) -> TaskRevisionCommand:
        """Narrow one validated ACG v2 command into the S8.5 kernel type."""

        if type(envelope) is not CommandEnvelope:
            raise _violation(
                "INVALID_TASK_REVISION_COMMAND",
                "task revision requires an exact CommandEnvelope",
            )
        try:
            operation = TaskRevisionOperation(envelope.command_type)
        except ValueError as error:
            raise _violation(
                "UNSUPPORTED_TASK_REVISION_OPERATION",
                "command envelope is not an S8.5 task revision",
                ErrorCode.UNSUPPORTED,
            ) from error
        if (
            envelope.target_ref.kind is not IdentityKind.TASK
            or envelope.target_ref.id.startswith("create:")
            or envelope.required_capabilities != (operation.value,)
            or envelope.origin.kind != "committed_turn"
            or envelope.origin.commit_id is None
            or envelope.extensions
            != {S8_5_TASK_REVISION_EXTENSION: {"profile": S8_5_TASK_REVISION_PROFILE}}
        ):
            raise _violation(
                "TASK_REVISION_ENVELOPE_BINDING_INVALID",
                "revision envelope must bind its task, capability, committed turn, and profile",
                ErrorCode.PERMISSION_DENIED,
            )
        body = envelope.payload
        facts: tuple[str, ...] = ()
        patch: TaskConstraintPatch | None = None
        if operation is TaskRevisionOperation.PROVIDE_INPUT:
            raw_facts = body.get("facts")
            if type(raw_facts) is not list:
                raise _violation(
                    "INVALID_TASK_REVISION_FACTS",
                    "task.provide_input facts must be an array",
                )
            facts = tuple(raw_facts)
        else:
            patch = TaskConstraintPatch.from_dict(body.get("constraints"))
        return cls(
            command_id=envelope.command_id,
            operation=operation,
            scope=envelope.scope,
            task_id=envelope.target_ref.id,
            expected_task_revision=body.get("expected_task_revision"),  # type: ignore[arg-type]
            expected_attempt_id=body.get("expected_attempt_id"),  # type: ignore[arg-type]
            origin_commit_id=envelope.origin.commit_id,
            facts=facts,
            constraint_patch=patch,
        )

    def fingerprint(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class TaskRevisionGrant:
    principal_id: str
    scope: ScopeRef
    operation: TaskRevisionOperation
    command_id: str
    task_id: str
    expected_task_revision: int
    expected_attempt_id: str
    command_fingerprint: bytes
    confirmation_id: str
    confirmed: bool
    expires_at: str

    def __post_init__(self) -> None:
        _text(self.principal_id, "grant.principal_id")
        _scope(self.scope, "grant.scope")
        if type(self.operation) is not TaskRevisionOperation:
            raise _violation(
                "INVALID_TASK_REVISION_GRANT", "grant operation must be exact"
            )
        _text(self.command_id, "grant.command_id")
        _text(self.task_id, "grant.task_id")
        _positive_int(self.expected_task_revision, "grant.expected_task_revision")
        _text(self.expected_attempt_id, "grant.expected_attempt_id")
        if type(self.command_fingerprint) is not bytes:
            raise _violation(
                "INVALID_TASK_REVISION_GRANT",
                "grant fingerprint must be canonical bytes",
            )
        _text(self.confirmation_id, "grant.confirmation_id")
        if type(self.confirmed) is not bool:
            raise _violation(
                "INVALID_TASK_REVISION_GRANT", "grant confirmed must be boolean"
            )
        _timestamp(self.expires_at, "grant.expires_at")

    def authorize(self, command: TaskRevisionCommand, *, now: str) -> None:
        if (
            self.scope.assurance is not Assurance.AUTHENTICATED
            or command.scope.assurance is not Assurance.AUTHENTICATED
        ):
            raise _violation(
                "TASK_REVISION_AUTHENTICATION_REQUIRED",
                "task revision requires authenticated scope",
                ErrorCode.UNAUTHENTICATED,
            )
        if (
            self.principal_id != command.scope.subject_id
            or self.scope != command.scope
            or self.operation is not command.operation
            or self.command_id != command.command_id
            or self.task_id != command.task_id
            or self.expected_task_revision != command.expected_task_revision
            or self.expected_attempt_id != command.expected_attempt_id
            or self.command_fingerprint != command.fingerprint()
        ):
            raise _violation(
                "TASK_REVISION_AUTHORIZATION_DENIED",
                "confirmation does not bind the exact revision command",
                ErrorCode.PERMISSION_DENIED,
            )
        if not self.confirmed:
            raise _violation(
                "TASK_REVISION_CONFIRMATION_REQUIRED",
                "task revision requires explicit confirmation",
                ErrorCode.PERMISSION_DENIED,
            )
        if _timestamp(self.expires_at, "grant.expires_at") <= _timestamp(now, "now"):
            raise _violation(
                "TASK_REVISION_CONFIRMATION_EXPIRED",
                "task revision confirmation has expired",
                ErrorCode.PERMISSION_DENIED,
            )


@dataclass(frozen=True, slots=True)
class TaskRevisionAuthority:
    task_id: str
    scope: ScopeRef
    task_revision: int
    attempt_id: str
    task_state: str
    base_instruction: str
    additive_facts: tuple[str, ...]
    constraints: TaskRevisionConstraints
    pending_command_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.task_id, "authority.task_id")
        _scope(self.scope, "authority.scope")
        _positive_int(self.task_revision, "authority.task_revision")
        if self.task_revision > MAX_TASK_REVISIONS:
            raise _violation(
                "INVALID_TASK_REVISION_AUTHORITY",
                "authority revision exceeds the S8.5 profile",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        _text(self.attempt_id, "authority.attempt_id")
        if self.task_state not in {
            "accepted",
            "running",
            "blocked",
            "decision_required",
            "terminal",
        }:
            raise _violation("INVALID_TASK_REVISION_AUTHORITY", "task state is invalid")
        _text(self.base_instruction, "authority.base_instruction")
        if type(self.additive_facts) is not tuple or any(
            type(fact) is not str or not fact.strip() for fact in self.additive_facts
        ):
            raise _violation(
                "INVALID_TASK_REVISION_AUTHORITY",
                "authority facts must be immutable non-empty strings",
            )
        if len(self.additive_facts) > MAX_REVISION_FACTS or len(
            set(self.additive_facts)
        ) != len(self.additive_facts):
            raise _violation(
                "INVALID_TASK_REVISION_AUTHORITY",
                "authority facts must be bounded and unique",
            )
        if type(self.constraints) is not TaskRevisionConstraints:
            raise _violation(
                "INVALID_TASK_REVISION_AUTHORITY", "authority constraints must be exact"
            )
        if self.pending_command_id is not None:
            _text(self.pending_command_id, "authority.pending_command_id")


@dataclass(frozen=True, slots=True)
class TaskRevisionTargetSnapshot:
    """Minimal Store-owned target facts safe for a revision intent bridge."""

    task_id: str
    scope: ScopeRef
    task_revision: int
    attempt_id: str
    attempt_number: int
    task_state: str
    pending_command_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.task_id, "target.task_id")
        _scope(self.scope, "target.scope")
        _positive_int(self.task_revision, "target.task_revision")
        if self.task_revision > MAX_TASK_REVISIONS:
            raise _violation(
                "INVALID_TASK_REVISION_TARGET",
                "target revision exceeds the S8.5 profile",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        _text(self.attempt_id, "target.attempt_id")
        _positive_int(self.attempt_number, "target.attempt_number")
        if self.task_state not in {
            "accepted",
            "running",
            "blocked",
            "decision_required",
            "terminal",
        }:
            raise _violation(
                "INVALID_TASK_REVISION_TARGET",
                "target task state is invalid",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if self.pending_command_id is not None:
            _text(self.pending_command_id, "target.pending_command_id")


@dataclass(frozen=True, slots=True)
class TaskRevisionPlan:
    command_id: str
    operation: TaskRevisionOperation
    task_id: str
    predecessor_revision: int
    successor_revision: int
    predecessor_attempt_id: str
    additive_facts: tuple[str, ...]
    constraints: TaskRevisionConstraints
    effective_instruction: str
    application_state: RevisionApplicationState = RevisionApplicationState.FENCING

    def __post_init__(self) -> None:
        _text(self.command_id, "plan.command_id")
        if type(self.operation) is not TaskRevisionOperation:
            raise _violation(
                "INVALID_TASK_REVISION_PLAN",
                "revision plan operation must be exact",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        _text(self.task_id, "plan.task_id")
        _positive_int(self.predecessor_revision, "plan.predecessor_revision")
        _positive_int(self.successor_revision, "plan.successor_revision")
        _text(self.predecessor_attempt_id, "plan.predecessor_attempt_id")
        if (
            type(self.additive_facts) is not tuple
            or type(self.constraints) is not TaskRevisionConstraints
        ):
            raise _violation(
                "INVALID_TASK_REVISION_PLAN",
                "revision plan facts and constraints must be immutable",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        _text(self.effective_instruction, "plan.effective_instruction")
        if (
            self.successor_revision != self.predecessor_revision + 1
            or self.successor_revision > MAX_TASK_REVISIONS
            or self.application_state is not RevisionApplicationState.FENCING
        ):
            raise _violation(
                "INVALID_TASK_REVISION_PLAN",
                "revision plan must bind the next immutable revision in fencing state",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "operation": self.operation.value,
            "task_id": self.task_id,
            "predecessor_revision": self.predecessor_revision,
            "successor_revision": self.successor_revision,
            "predecessor_attempt_id": self.predecessor_attempt_id,
            "additive_facts": list(self.additive_facts),
            "constraints": self.constraints.to_dict(),
            "effective_instruction": self.effective_instruction,
            "application_state": self.application_state.value,
        }


def _effective_instruction(
    base_instruction: str,
    facts: tuple[str, ...],
    constraints: TaskRevisionConstraints,
) -> str:
    sections = [base_instruction.rstrip()]
    if facts:
        sections.append(
            "Committed additive facts:\n" + "\n".join(f"- {fact}" for fact in facts)
        )
    sections.append(
        "Trusted execution constraints:\n"
        + f"- write_scope: {', '.join(constraints.write_scope)}\n"
        + "- dependency_policy: locked\n"
        + "- public_api_policy: preserve\n"
        + "- configuration_policy: preserve\n"
        + "- regression_verifier_required: "
        + ("true" if constraints.regression_verifier_required else "false")
    )
    return "\n\n".join(sections)


def plan_task_revision(
    command: TaskRevisionCommand,
    grant: TaskRevisionGrant,
    authority: TaskRevisionAuthority,
    *,
    feature_enabled: bool,
    now: str,
) -> TaskRevisionPlan:
    """Validate one exact request and return a fence candidate with zero I/O."""

    if not feature_enabled:
        raise _violation(
            "TASK_REVISION_FEATURE_DISABLED",
            "S8.5 task revision is disabled",
            ErrorCode.UNSUPPORTED,
        )
    grant.authorize(command, now=now)
    if command.task_id != authority.task_id or command.scope != authority.scope:
        raise _violation(
            "TASK_REVISION_SCOPE_MISMATCH",
            "revision request does not bind the authoritative task scope",
            ErrorCode.PERMISSION_DENIED,
        )
    if authority.task_state == "terminal":
        raise _violation(
            "TASK_REVISION_TERMINAL",
            "terminal tasks cannot be revised",
            ErrorCode.CONFLICT,
        )
    if authority.task_state == "accepted":
        raise _violation(
            "TASK_REVISION_NOT_RUNNING",
            "a task must have started before it can be revised",
            ErrorCode.CONFLICT,
        )
    if authority.pending_command_id is not None:
        raise _violation(
            "TASK_REVISION_ALREADY_PENDING",
            "another revision command already owns the predecessor fence",
            ErrorCode.CONFLICT,
        )
    if (
        command.expected_task_revision != authority.task_revision
        or command.expected_attempt_id != authority.attempt_id
    ):
        raise _violation(
            "TASK_REVISION_PRECONDITION_STALE",
            "revision target no longer matches the current revision and attempt",
            ErrorCode.STALE,
        )
    if authority.task_revision >= MAX_TASK_REVISIONS:
        raise _violation(
            "TASK_REVISION_LIMIT_EXCEEDED",
            "the S8.5 showcase permits one revision from revision 1 to revision 2",
            ErrorCode.CONFLICT,
        )
    facts = authority.additive_facts
    constraints = authority.constraints
    if command.operation is TaskRevisionOperation.PROVIDE_INPUT:
        if any(fact in facts for fact in command.facts):
            raise _violation(
                "TASK_REVISION_FACT_CONFLICT",
                "provided facts must be new immutable additions",
                ErrorCode.CONFLICT,
            )
        if len(facts) + len(command.facts) > MAX_REVISION_FACTS:
            raise _violation(
                "TASK_REVISION_FACT_LIMIT_EXCEEDED",
                "task revision exceeds the bounded additive-fact limit",
                ErrorCode.CONFLICT,
            )
        facts = facts + command.facts
    else:
        assert command.constraint_patch is not None
        constraints = constraints.tighten(command.constraint_patch)
        if constraints == authority.constraints:
            raise _violation(
                "TASK_REVISION_CONSTRAINT_NOOP",
                "constraint update must strictly tighten the effective policy",
                ErrorCode.CONFLICT,
            )
    return TaskRevisionPlan(
        command_id=command.command_id,
        operation=command.operation,
        task_id=command.task_id,
        predecessor_revision=authority.task_revision,
        successor_revision=authority.task_revision + 1,
        predecessor_attempt_id=authority.attempt_id,
        additive_facts=facts,
        constraints=constraints,
        effective_instruction=_effective_instruction(
            authority.base_instruction, facts, constraints
        ),
    )


@dataclass(frozen=True, slots=True)
class TaskRevisionRecord:
    task_id: str
    task_revision: int
    predecessor_revision: int | None
    attempt_id: str
    base_instruction: str
    additive_facts: tuple[str, ...]
    constraints: TaskRevisionConstraints
    origin_commit_id: str
    created_by_command_id: str

    def __post_init__(self) -> None:
        _text(self.task_id, "revision.task_id")
        _positive_int(self.task_revision, "revision.task_revision")
        expected_predecessor = (
            None if self.task_revision == 1 else self.task_revision - 1
        )
        if (
            self.task_revision > MAX_TASK_REVISIONS
            or self.predecessor_revision != expected_predecessor
        ):
            raise _violation(
                "INVALID_TASK_REVISION_LINEAGE",
                "revision predecessor must be exactly N-1",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        _text(self.attempt_id, "revision.attempt_id")
        _text(self.base_instruction, "revision.base_instruction")
        if type(self.additive_facts) is not tuple or len(
            set(self.additive_facts)
        ) != len(self.additive_facts):
            raise _violation(
                "INVALID_TASK_REVISION_RECORD",
                "revision facts must be an immutable unique tuple",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        for index, fact in enumerate(self.additive_facts):
            _text(
                fact,
                f"revision.additive_facts[{index}]",
                maximum=MAX_FACT_CHARACTERS,
            )
        if type(self.constraints) is not TaskRevisionConstraints:
            raise _violation(
                "INVALID_TASK_REVISION_RECORD",
                "revision constraints must be exact",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        _text(self.origin_commit_id, "revision.origin_commit_id")
        _text(self.created_by_command_id, "revision.created_by_command_id")

    @property
    def effective_instruction(self) -> str:
        return _effective_instruction(
            self.base_instruction, self.additive_facts, self.constraints
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "task_revision": self.task_revision,
            "predecessor_revision": self.predecessor_revision,
            "attempt_id": self.attempt_id,
            "base_instruction": self.base_instruction,
            "additive_facts": list(self.additive_facts),
            "constraints": self.constraints.to_dict(),
            "origin_commit_id": self.origin_commit_id,
            "created_by_command_id": self.created_by_command_id,
        }


@dataclass(frozen=True, slots=True)
class RevisionFenceRequest:
    command_id: str
    task_id: str
    predecessor_revision: int
    predecessor_attempt_id: str

    def __post_init__(self) -> None:
        _text(self.command_id, "fence.command_id")
        _text(self.task_id, "fence.task_id")
        _positive_int(self.predecessor_revision, "fence.predecessor_revision")
        _text(self.predecessor_attempt_id, "fence.predecessor_attempt_id")


@dataclass(frozen=True, slots=True)
class RevisionFenceAck:
    command_id: str
    task_id: str
    predecessor_revision: int
    predecessor_attempt_id: str
    executor_id: str
    executor_ref: str
    cleanup_id: str
    checkout_identity: str
    unapplied_changes_discarded: bool
    acknowledged_at: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("command_id", self.command_id),
            ("task_id", self.task_id),
            ("predecessor_attempt_id", self.predecessor_attempt_id),
            ("executor_id", self.executor_id),
            ("executor_ref", self.executor_ref),
            ("cleanup_id", self.cleanup_id),
            ("checkout_identity", self.checkout_identity),
        ):
            _text(value, f"fence_ack.{field_name}")
        _positive_int(self.predecessor_revision, "fence_ack.predecessor_revision")
        if type(self.unapplied_changes_discarded) is not bool:
            raise _violation(
                "INVALID_TASK_REVISION_FENCE_ACK",
                "unapplied_changes_discarded must be boolean",
            )
        _timestamp(self.acknowledged_at, "fence_ack.acknowledged_at")


def immutable_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Small helper for downstream truth projections without mutable aliases."""

    canonical_json_bytes(dict(value))
    return MappingProxyType(dict(value))


__all__ = [
    "MAX_REVISION_FACTS",
    "RevisionApplicationState",
    "RevisionFenceAck",
    "RevisionFenceRequest",
    "S8_5_TASK_REVISION_EXTENSION",
    "S8_5_TASK_REVISION_OPERATIONS",
    "S8_5_TASK_REVISION_PROFILE",
    "TaskConstraintPatch",
    "TaskRevisionAuthority",
    "TaskRevisionCommand",
    "TaskRevisionConstraints",
    "TaskRevisionGrant",
    "TaskRevisionOperation",
    "TaskRevisionPlan",
    "TaskRevisionRecord",
    "TaskRevisionTargetSnapshot",
    "TaskRevisionViolation",
    "immutable_mapping",
    "plan_task_revision",
]
