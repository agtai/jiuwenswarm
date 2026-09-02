# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Trusted production policy for generalized multi-Task intent resolution.

Language output is only a proposal. A trusted committed-origin authority,
authenticated Task reader, clarification CAS owner and confirmation consumer
remain separate mandatory Ports. This module has no mutation or external-
effect Port and cannot mint any of their receipts.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    canonical_json_bytes,
)

from .task_core import AttemptState, TaskState
from .voice_task_policy import (
    FORMAL_TASK_MUTATION_OPERATIONS,
    FORMAL_TASK_QUERY_OPERATIONS,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.]{0,127}")
_ALL_OPERATIONS = FORMAL_TASK_QUERY_OPERATIONS | FORMAL_TASK_MUTATION_OPERATIONS
_COLLECTION_OPERATIONS = frozenset({"task.create", "task.list"})
_MATERIAL_OPERATIONS = frozenset(
    {
        "task.create",
        "task.update",
        "task.adjust",
        "task.cancel",
        "task.create_successor",
        "task.reprioritize",
    }
)
_TASK_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
_TARGET_AUTHORITY_CONVERGENCE_ATTEMPTS = 3
_ARGUMENT_FIELDS = {
    "task.create": frozenset({"name", "instruction"}),
    "task.get": frozenset({"query_kind"}),
    "task.list": frozenset({"query_kind", "limit"}),
    "task.status": frozenset({"query_kind"}),
    "task.events": frozenset({"query_kind", "after_seq", "limit"}),
    "task.result": frozenset({"query_kind"}),
    "task.update": frozenset({"instruction"}),
    "task.adjust": frozenset({"adjustment"}),
    "task.provide_input": frozenset({"answer", "responds_to_event_id"}),
    "task.pause": frozenset(),
    "task.resume": frozenset(),
    "task.reprioritize": frozenset({"priority"}),
    "task.cancel": frozenset(),
    "task.create_successor": frozenset({"name", "instruction"}),
}
_QUERY_KIND = {
    "task.get": "get",
    "task.list": "list",
    "task.status": "status",
    "task.events": "events",
    "task.result": "result",
}
_ZERO_EFFECTS = (
    "agent_calls",
    "tool_calls",
    "task_writes",
    "attempt_writes",
    "command_writes",
    "event_writes",
    "result_writes",
    "executor_calls",
    "scheduler_calls",
    "file_writes",
    "network_calls",
    "audio_tts_calls",
    "history_writes",
    "presentation_writes",
    "other_scope_writes",
)


class ProductionIntentOrigin(StrEnum):
    VOICE = "voice"
    NATURAL_TEXT = "natural_text"
    STRUCTURED = "structured"


class ProductionTaskPolicyOutcome(StrEnum):
    PROPOSED = "proposed"
    CLARIFICATION = "clarification"
    DIALOGUE = "dialogue"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"


def _require_text(value: object, name: str, *, maximum: int = 4_096) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"INVALID_{name.upper()}")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"INVALID_{name.upper()}") from error
    if len(encoded) > maximum:
        raise ValueError(f"INVALID_{name.upper()}")
    return value


def _require_opaque(value: object, name: str) -> str:
    """Validate only that a server identity is an opaque non-empty string."""

    if type(value) is not str or not value or "\x00" in value:
        raise ValueError(f"INVALID_{name.upper()}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"INVALID_{name.upper()}") from error
    return value


def _require_persistent_identity(value: object, name: str) -> str:
    """Match PersistentTaskRecord's syntax-free closed identity bounds."""

    identity = _require_opaque(value, name)
    if len(identity) > 256 or len(identity.encode("utf-8")) > 1_024:
        raise ValueError(f"INVALID_{name.upper()}")
    return identity


def _canonical_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("INVALID_TASK_INTENT_ARGUMENTS")
    clean = dict(value)
    if len(clean) > 16:
        raise ValueError("TASK_INTENT_ARGUMENT_BOUND_EXCEEDED")
    for key, item in clean.items():
        if type(key) is not str or not key or len(key) > 64:
            raise ValueError("INVALID_TASK_INTENT_ARGUMENT_KEY")
        if type(item) is str:
            _require_text(item, "task_intent_argument")
        elif type(item) is int:
            if not -(2**53 - 1) <= item <= 2**53 - 1:
                raise ValueError("TASK_INTENT_ARGUMENT_BOUND_EXCEEDED")
        elif item is not None:
            raise ValueError("INVALID_TASK_INTENT_ARGUMENT_VALUE")
    if len(canonical_json_bytes(clean)) > 8_192:
        raise ValueError("TASK_INTENT_ARGUMENT_BOUND_EXCEEDED")
    return MappingProxyType(clean)


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


_UNSPECIFIED_COLLECTION_CAPABILITY_DIGEST = _sha256(
    {
        "authority": "live_voice.production_task_intent",
        "fact": "unspecified_collection_capability",
        "version": 1,
    }
)
_UNSPECIFIED_CONTEXT_FINGERPRINT = _sha256(
    {
        "authority": "live_voice.production_task_intent",
        "fact": "unspecified_context",
        "version": 1,
    }
)
_UNSPECIFIED_MODEL_BINDING_FINGERPRINT = _sha256(
    {
        "authority": "live_voice.production_task_intent",
        "fact": "unspecified_model_binding",
        "version": 1,
    }
)


@dataclass(frozen=True, slots=True)
class AuthenticatedTaskFact:
    """Canonical Task/Attempt facts from one authenticated Core authority."""

    task_id: str
    stable_reference: str
    name: str
    state: TaskState
    outcome: TerminalOutcome | None
    revision_number: int
    event_head: int
    event_head_id: str
    terminal_event_id: str | None
    attempt_id: str
    attempt_state: AttemptState
    attempt_outcome: TerminalOutcome | None
    capability_profile_digest: str
    supported_operations: frozenset[str]
    result_digest: str | None = None
    decision_required_event_id: str | None = None
    dispatch_control: str = "none"
    admission_fingerprint: str | None = None
    predecessor_task_id: str | None = None
    successor_task_id: str | None = None
    context_fingerprint: str = _UNSPECIFIED_CONTEXT_FINGERPRINT
    model_binding_fingerprint: str = _UNSPECIFIED_MODEL_BINDING_FINGERPRINT

    def __post_init__(self) -> None:
        _require_persistent_identity(self.task_id, "task_id")
        _require_persistent_identity(self.stable_reference, "stable_task_reference")
        _require_text(self.name, "task_name", maximum=256)
        if not isinstance(self.state, TaskState):
            raise ValueError("INVALID_TASK_STATE_FACT")
        if self.outcome is not None and not isinstance(self.outcome, TerminalOutcome):
            raise ValueError("INVALID_TASK_OUTCOME_FACT")
        terminal = self.state is TaskState.TERMINAL
        if terminal != (self.outcome is not None):
            raise ValueError("INVALID_TASK_OUTCOME_FACT")
        if (
            type(self.revision_number) is not int
            or not 1 <= self.revision_number <= 1_000_000
        ):
            raise ValueError("INVALID_TASK_REVISION")
        if type(self.event_head) is not int or self.event_head < 0:
            raise ValueError("INVALID_TASK_EVENT_HEAD")
        _require_persistent_identity(self.event_head_id, "task_event_head_id")
        if terminal != (self.terminal_event_id is not None):
            raise ValueError("INVALID_TERMINAL_EVENT_FACT")
        if self.terminal_event_id is not None:
            _require_persistent_identity(self.terminal_event_id, "terminal_event_id")
        _require_persistent_identity(self.attempt_id, "attempt_id")
        if not isinstance(self.attempt_state, AttemptState):
            raise ValueError("INVALID_ATTEMPT_STATE_FACT")
        if self.attempt_outcome is not None and not isinstance(
            self.attempt_outcome, TerminalOutcome
        ):
            raise ValueError("INVALID_ATTEMPT_OUTCOME_FACT")
        attempt_terminal = self.attempt_state is AttemptState.TERMINAL
        if attempt_terminal != (self.attempt_outcome is not None):
            raise ValueError("INVALID_ATTEMPT_OUTCOME_FACT")
        expected_attempt_state = {
            TaskState.ACCEPTED: AttemptState.ACCEPTED,
            TaskState.RUNNING: AttemptState.RUNNING,
            TaskState.BLOCKED: AttemptState.RUNNING,
            TaskState.DECISION_REQUIRED: AttemptState.RUNNING,
            TaskState.TERMINAL: AttemptState.TERMINAL,
        }[self.state]
        if self.attempt_state is not expected_attempt_state:
            raise ValueError("TASK_ATTEMPT_LIFECYCLE_MISMATCH")
        if terminal and self.attempt_outcome is not self.outcome:
            raise ValueError("TASK_ATTEMPT_OUTCOME_MISMATCH")
        if _SHA256.fullmatch(self.capability_profile_digest) is None:
            raise ValueError("INVALID_CAPABILITY_PROFILE_DIGEST")
        if not isinstance(self.supported_operations, frozenset) or not all(
            type(operation) is str and operation in _ALL_OPERATIONS
            for operation in self.supported_operations
        ):
            raise ValueError("INVALID_SUPPORTED_OPERATION_FACT")
        if (
            self.result_digest is not None
            and _SHA256.fullmatch(self.result_digest) is None
        ):
            raise ValueError("INVALID_TASK_RESULT_DIGEST")
        if self.outcome is TerminalOutcome.COMPLETED:
            if self.result_digest is None:
                raise ValueError("COMPLETED_RESULT_REQUIRED")
        elif self.result_digest is not None:
            raise ValueError("NONCOMPLETED_RESULT_FORBIDDEN")
        if self.decision_required_event_id is not None:
            _require_persistent_identity(
                self.decision_required_event_id, "decision_required_event_id"
            )
        if (
            self.decision_required_event_id is not None
            and self.state is not TaskState.DECISION_REQUIRED
        ):
            raise ValueError("DECISION_REQUIRED_EVENT_MISMATCH")
        if self.dispatch_control not in {"none", "unclaimed", "taken_over"}:
            raise ValueError("INVALID_DISPATCH_FACT")
        if self.admission_fingerprint is not None and (
            _SHA256.fullmatch(self.admission_fingerprint) is None
        ):
            raise ValueError("INVALID_ADMISSION_FINGERPRINT")
        for name, value in (
            ("predecessor_task_id", self.predecessor_task_id),
            ("successor_task_id", self.successor_task_id),
        ):
            if value is not None:
                _require_persistent_identity(value, name)
                if value == self.task_id:
                    raise ValueError("INVALID_TASK_LINEAGE")
        if (self.revision_number == 1) != (self.predecessor_task_id is None):
            raise ValueError("TASK_REVISION_LINEAGE_MISMATCH")
        if self.successor_task_id is not None and (
            not terminal or self.outcome is TerminalOutcome.UNKNOWN
        ):
            raise ValueError("INVALID_TASK_LINEAGE")
        for digest in (
            self.context_fingerprint,
            self.model_binding_fingerprint,
        ):
            if _SHA256.fullmatch(digest) is None:
                raise ValueError("INVALID_TASK_AUTHORITY_FINGERPRINT")

    @property
    def terminal(self) -> bool:
        return self.state is TaskState.TERMINAL

    def canonical_dict(self) -> dict[str, object]:
        return {
            "admission_fingerprint": self.admission_fingerprint,
            "attempt_id": self.attempt_id,
            "attempt_outcome": (
                None if self.attempt_outcome is None else self.attempt_outcome.value
            ),
            "attempt_state": self.attempt_state.value,
            "capability_profile_digest": self.capability_profile_digest,
            "context_fingerprint": self.context_fingerprint,
            "decision_required_event_id": self.decision_required_event_id,
            "dispatch_control": self.dispatch_control,
            "event_head": self.event_head,
            "event_head_id": self.event_head_id,
            "name": self.name,
            "model_binding_fingerprint": self.model_binding_fingerprint,
            "outcome": None if self.outcome is None else self.outcome.value,
            "predecessor_task_id": self.predecessor_task_id,
            "result_digest": self.result_digest,
            "revision_number": self.revision_number,
            "stable_reference": self.stable_reference,
            "state": self.state.value,
            "successor_task_id": self.successor_task_id,
            "supported_operations": sorted(self.supported_operations),
            "task_id": self.task_id,
            "terminal_event_id": self.terminal_event_id,
        }

    @property
    def fingerprint(self) -> str:
        return _sha256(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class TaskAuthorityRead:
    scope: ScopeRef
    generation: str
    tasks: tuple[AuthenticatedTaskFact, ...]
    collection_capability_profile_digest: str = (
        _UNSPECIFIED_COLLECTION_CAPABILITY_DIGEST
    )
    authority_context_fingerprint: str = _UNSPECIFIED_CONTEXT_FINGERPRINT
    collection_model_binding_fingerprint: str = _UNSPECIFIED_MODEL_BINDING_FINGERPRINT

    def __post_init__(self) -> None:
        if self.scope.assurance != "authenticated":
            raise ValueError("AUTHENTICATED_TASK_AUTHORITY_REQUIRED")
        _require_opaque(self.generation, "task_set_generation")
        if not isinstance(self.tasks, tuple) or len(self.tasks) > 500:
            raise ValueError("INVALID_VISIBLE_TASK_SET")
        if not all(isinstance(task, AuthenticatedTaskFact) for task in self.tasks):
            raise ValueError("INVALID_VISIBLE_TASK_FACT")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("DUPLICATE_VISIBLE_TASK_ID")
        if len({task.stable_reference for task in self.tasks}) != len(self.tasks):
            raise ValueError("DUPLICATE_STABLE_TASK_REFERENCE")
        if _SHA256.fullmatch(self.collection_capability_profile_digest) is None:
            raise ValueError("INVALID_COLLECTION_CAPABILITY_PROFILE_DIGEST")
        for digest in (
            self.authority_context_fingerprint,
            self.collection_model_binding_fingerprint,
        ):
            if _SHA256.fullmatch(digest) is None:
                raise ValueError("INVALID_TASK_AUTHORITY_FINGERPRINT")

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "collection_capability_profile_digest": (
                    self.collection_capability_profile_digest
                ),
                "collection_model_binding_fingerprint": (
                    self.collection_model_binding_fingerprint
                ),
                "generation": self.generation,
                "scope": self.scope.to_dict(),
                "tasks": [
                    task.canonical_dict()
                    for task in sorted(self.tasks, key=lambda item: item.task_id)
                ],
            }
        )


@runtime_checkable
class ProductionTaskAuthorityReader(Protocol):
    def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead: ...

    def get_task(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None: ...

    def task_status(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None: ...

    def event_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str]: ...

    def result_digest(self, scope: ScopeRef, task_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ProductionFieldExtraction:
    field_name: str
    source_start: int
    source_end: int

    def __post_init__(self) -> None:
        if _FIELD_NAME.fullmatch(self.field_name) is None:
            raise ValueError("INVALID_EXTRACTION_FIELD")
        if (
            type(self.source_start) is not int
            or type(self.source_end) is not int
            or self.source_start < 0
            or self.source_end <= self.source_start
        ):
            raise ValueError("INVALID_EXTRACTION_SPAN")


@dataclass(frozen=True, slots=True)
class BoundProductionFieldExtraction:
    field_name: str
    source_start: int
    source_end: int
    content_sha256: str
    value_sha256: str

    def __post_init__(self) -> None:
        if _FIELD_NAME.fullmatch(self.field_name) is None:
            raise ValueError("INVALID_EXTRACTION_FIELD")
        if self.source_start < 0 or self.source_end <= self.source_start:
            raise ValueError("INVALID_EXTRACTION_SPAN")
        if (
            _SHA256.fullmatch(self.content_sha256) is None
            or _SHA256.fullmatch(self.value_sha256) is None
        ):
            raise ValueError("INVALID_EXTRACTION_CONTENT_DIGEST")

    def to_dict(self) -> dict[str, object]:
        return {
            "content_sha256": self.content_sha256,
            "field_name": self.field_name,
            "source_end": self.source_end,
            "source_start": self.source_start,
            "value_sha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProductionOriginBinding:
    principal_id: str
    scope: ScopeRef
    origin: ProductionIntentOrigin
    source_id: str
    commit_id: str | None
    commit_sha256: str | None
    extractions: tuple[BoundProductionFieldExtraction, ...]
    structured_semantic_sha256: str | None = None
    clarification_answer_sha256: str | None = None
    semantic_context_binding: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        _require_opaque(self.principal_id, "origin_principal_id")
        if self.scope.assurance != "authenticated":
            raise ValueError("AUTHENTICATED_ORIGIN_SCOPE_REQUIRED")
        if self.principal_id != self.scope.subject_id:
            raise ValueError("ORIGIN_PRINCIPAL_SCOPE_MISMATCH")
        if not isinstance(self.origin, ProductionIntentOrigin):
            raise ValueError("INVALID_PRODUCTION_INTENT_ORIGIN")
        _require_opaque(self.source_id, "origin_source_id")
        natural = self.origin is not ProductionIntentOrigin.STRUCTURED
        if self.semantic_context_binding is not None:
            if not natural:
                raise ValueError("STRUCTURED_ORIGIN_FORBIDS_MODEL_SEMANTICS")
            object.__setattr__(
                self,
                "semantic_context_binding",
                _semantic_context_binding(self.semantic_context_binding),
            )
        if natural != (self.commit_id is not None and self.commit_sha256 is not None):
            raise ValueError("INVALID_ORIGIN_COMMIT_BINDING")
        if self.commit_id is not None:
            _require_opaque(self.commit_id, "origin_commit_id")
        if (
            self.commit_sha256 is not None
            and _SHA256.fullmatch(self.commit_sha256) is None
        ):
            raise ValueError("INVALID_ORIGIN_COMMIT_DIGEST")
        if not isinstance(self.extractions, tuple) or len(self.extractions) > 18:
            raise ValueError("INVALID_ORIGIN_EXTRACTIONS")
        if len({item.field_name for item in self.extractions}) != len(self.extractions):
            raise ValueError("DUPLICATE_ORIGIN_EXTRACTION")
        if not natural and self.extractions:
            raise ValueError("STRUCTURED_ORIGIN_FORBIDS_EXTRACTIONS")
        if natural == (self.structured_semantic_sha256 is not None):
            raise ValueError("INVALID_STRUCTURED_SEMANTIC_BINDING")
        if (
            self.structured_semantic_sha256 is not None
            and _SHA256.fullmatch(self.structured_semantic_sha256) is None
        ):
            raise ValueError("INVALID_STRUCTURED_SEMANTIC_DIGEST")
        if (
            self.clarification_answer_sha256 is not None
            and _SHA256.fullmatch(self.clarification_answer_sha256) is None
        ):
            raise ValueError("INVALID_CLARIFICATION_ANSWER_DIGEST")

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "commit_id": self.commit_id,
                "commit_sha256": self.commit_sha256,
                "clarification_answer_sha256": self.clarification_answer_sha256,
                "extractions": [item.to_dict() for item in self.extractions],
                "origin": self.origin.value,
                "principal_id": self.principal_id,
                "scope": self.scope.to_dict(),
                "source_id": self.source_id,
                "structured_semantic_sha256": self.structured_semantic_sha256,
                **(
                    {}
                    if self.semantic_context_binding is None
                    else {
                        "semantic_context_binding": dict(self.semantic_context_binding),
                    }
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class TrustedProductionOriginReceipt:
    receipt_id: str
    principal_id: str
    binding_fingerprint: str

    def __post_init__(self) -> None:
        _require_opaque(self.receipt_id, "origin_receipt_id")
        _require_opaque(self.principal_id, "origin_receipt_principal")
        if _SHA256.fullmatch(self.binding_fingerprint) is None:
            raise ValueError("INVALID_ORIGIN_RECEIPT_FINGERPRINT")


@runtime_checkable
class ProductionOriginAuthority(Protocol):
    """Trusted Port that verifies an accepted commit/structured source."""

    def verify_origin(
        self, binding: ProductionOriginBinding
    ) -> TrustedProductionOriginReceipt: ...


@dataclass(frozen=True, slots=True)
class ProductionConfirmationBinding:
    principal_id: str
    scope: ScopeRef
    command_id: str
    origin: ProductionIntentOrigin
    origin_receipt_id: str
    origin_binding_fingerprint: str
    operation: str
    target_task_id: str | None
    target_attempt_id: str | None
    arguments_sha256: str
    task_set_fingerprint: str
    capability_profile_digest: str
    context_fingerprint: str
    model_binding_fingerprint: str

    def __post_init__(self) -> None:
        _require_opaque(self.principal_id, "confirmation_principal")
        if self.scope.assurance != "authenticated":
            raise ValueError("AUTHENTICATED_CONFIRMATION_SCOPE_REQUIRED")
        if self.principal_id != self.scope.subject_id:
            raise ValueError("CONFIRMATION_PRINCIPAL_SCOPE_MISMATCH")
        _require_opaque(self.command_id, "confirmation_command_id")
        if not isinstance(self.origin, ProductionIntentOrigin):
            raise ValueError("INVALID_CONFIRMATION_ORIGIN")
        _require_opaque(self.origin_receipt_id, "confirmation_origin_receipt")
        if self.operation not in _ALL_OPERATIONS:
            raise ValueError("INVALID_CONFIRMATION_OPERATION")
        if (self.target_task_id is None) != (self.target_attempt_id is None):
            raise ValueError("CONFIRMATION_TARGET_ATTEMPT_MISMATCH")
        if self.target_task_id is not None:
            _require_opaque(self.target_task_id, "confirmation_target_task_id")
            _require_opaque(self.target_attempt_id, "confirmation_target_attempt_id")
        for digest in (
            self.origin_binding_fingerprint,
            self.arguments_sha256,
            self.task_set_fingerprint,
            self.capability_profile_digest,
            self.context_fingerprint,
            self.model_binding_fingerprint,
        ):
            if _SHA256.fullmatch(digest) is None:
                raise ValueError("INVALID_CONFIRMATION_FINGERPRINT")

    @property
    def fingerprint(self) -> str:
        """Seal stable user intent, not the mutable observed Task collection."""

        return _sha256(
            {
                "arguments_sha256": self.arguments_sha256,
                "capability_profile_digest": self.capability_profile_digest,
                "command_id": self.command_id,
                "context_fingerprint": self.context_fingerprint,
                "model_binding_fingerprint": self.model_binding_fingerprint,
                "operation": self.operation,
                "origin": self.origin.value,
                "origin_binding_fingerprint": self.origin_binding_fingerprint,
                "origin_receipt_id": self.origin_receipt_id,
                "principal_id": self.principal_id,
                "scope": self.scope.to_dict(),
                "target_attempt_id": self.target_attempt_id,
                "target_task_id": self.target_task_id,
            }
        )


@dataclass(frozen=True, slots=True)
class TrustedConfirmationConsumptionReceipt:
    confirmation_id: str
    consumption_id: str
    binding_fingerprint: str
    replayed: bool

    def __post_init__(self) -> None:
        _require_opaque(self.confirmation_id, "confirmation_id")
        _require_opaque(self.consumption_id, "confirmation_consumption_id")
        if _SHA256.fullmatch(self.binding_fingerprint) is None:
            raise ValueError("INVALID_CONFIRMATION_RECEIPT_FINGERPRINT")
        if type(self.replayed) is not bool:
            raise ValueError("INVALID_CONFIRMATION_REPLAY_FACT")


@runtime_checkable
class ProductionConfirmationConsumer(Protocol):
    """Trusted Port that atomically verifies and consumes one confirmation."""

    def verify_and_consume(
        self, confirmation_id: str, binding: ProductionConfirmationBinding
    ) -> TrustedConfirmationConsumptionReceipt: ...


@dataclass(frozen=True, slots=True)
class ProductionTaskIntentProposal:
    """Untrusted classifier output. It carries no authority receipt."""

    operation: str | None
    target: str | None
    arguments: Mapping[str, object]
    confidence: float
    committed: bool
    target_kind: str | None = None
    reason: str = "TASK_INTENT_PROPOSED"
    extractions: tuple[ProductionFieldExtraction, ...] = ()
    observed_task_revision: int | None = None
    origin_deferred_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _canonical_mapping(self.arguments))
        if self.operation is not None and self.operation not in _ALL_OPERATIONS:
            raise ValueError("UNSUPPORTED_TASK_INTENT_OPERATION")
        if self.target is not None:
            _require_opaque(self.target, "task_target")
        if self.target_kind not in {
            None,
            "task_id",
            "stable_reference",
            "name",
            "hint",
        }:
            raise ValueError("INVALID_TASK_TARGET_KIND")
        if type(self.confidence) not in {int, float} or not 0 <= self.confidence <= 1:
            raise ValueError("INVALID_TASK_INTENT_CONFIDENCE")
        if type(self.committed) is not bool:
            raise ValueError("INVALID_TASK_INTENT_COMMIT_STATE")
        _require_text(self.reason, "task_intent_reason", maximum=128)
        if not isinstance(self.extractions, tuple) or not all(
            isinstance(item, ProductionFieldExtraction) for item in self.extractions
        ):
            raise ValueError("INVALID_TASK_INTENT_EXTRACTIONS")
        if self.observed_task_revision is not None and (
            type(self.observed_task_revision) is not int
            or self.observed_task_revision < 1
        ):
            raise ValueError("INVALID_OBSERVED_TASK_REVISION")
        if (
            not isinstance(self.origin_deferred_fields, tuple)
            or len(set(self.origin_deferred_fields)) != len(self.origin_deferred_fields)
            or any(
                type(field) is not str or _FIELD_NAME.fullmatch(field) is None
                for field in self.origin_deferred_fields
            )
        ):
            raise ValueError("INVALID_ORIGIN_DEFERRED_FIELDS")
        allowed_deferred = {
            "task.provide_input": ("responds_to_event_id",),
            "task.create_successor": ("name", "instruction"),
        }
        if self.origin_deferred_fields and (
            self.origin_deferred_fields != allowed_deferred.get(self.operation)
            or any(field in self.arguments for field in self.origin_deferred_fields)
        ):
            raise ValueError("INVALID_ORIGIN_DEFERRED_FIELD_BINDING")

    @classmethod
    def dialogue(cls, *, reason: str) -> ProductionTaskIntentProposal:
        return cls(None, None, {}, 1.0, True, reason=reason)


@dataclass(frozen=True, slots=True)
class ClarificationAnswer:
    handle_id: str
    generation: int
    selected_task_id: str
    task_set_fingerprint: str

    def __post_init__(self) -> None:
        _require_opaque(self.handle_id, "clarification_handle_id")
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("INVALID_CLARIFICATION_GENERATION")
        _require_opaque(self.selected_task_id, "clarification_target")
        if _SHA256.fullmatch(self.task_set_fingerprint) is None:
            raise ValueError("INVALID_CLARIFICATION_TASK_SET_FINGERPRINT")

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "generation": self.generation,
                "handle_id": self.handle_id,
                "selected_task_id": self.selected_task_id,
                "task_set_fingerprint": self.task_set_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class ProductionTaskIntentRequest:
    origin: ProductionIntentOrigin
    scope: ScopeRef
    command_id: str
    proposal: ProductionTaskIntentProposal
    commit: TurnCommit | None = None
    source_id: str = "structured-request"
    clarification_answer: ClarificationAnswer | None = None
    clarification_answer_fingerprint: str | None = None
    confirmation_id: str | None = None
    semantic_context_binding: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, ProductionIntentOrigin):
            raise ValueError("INVALID_PRODUCTION_INTENT_ORIGIN")
        if self.scope.assurance != "authenticated":
            raise ValueError("AUTHENTICATED_TASK_SCOPE_REQUIRED")
        _require_opaque(self.command_id, "task_intent_command_id")
        _require_opaque(self.source_id, "task_intent_source_id")
        if self.origin is ProductionIntentOrigin.STRUCTURED:
            if self.commit is not None or self.proposal.extractions:
                raise ValueError("INVALID_STRUCTURED_ORIGIN")
        elif not isinstance(self.commit, TurnCommit) or self.commit.scope != self.scope:
            raise ValueError("AUTHORITATIVE_COMMITTED_INPUT_REQUIRED")
        if self.clarification_answer_fingerprint is not None:
            if _SHA256.fullmatch(self.clarification_answer_fingerprint) is None:
                raise ValueError("INVALID_CLARIFICATION_ANSWER_DIGEST")
            if (
                self.clarification_answer is not None
                and self.clarification_answer.fingerprint
                != self.clarification_answer_fingerprint
            ):
                raise ValueError("CLARIFICATION_ANSWER_DIGEST_MISMATCH")
        if self.confirmation_id is not None:
            _require_opaque(self.confirmation_id, "confirmation_id")
        if self.semantic_context_binding is not None:
            if self.origin is ProductionIntentOrigin.STRUCTURED:
                raise ValueError("STRUCTURED_ORIGIN_FORBIDS_MODEL_SEMANTICS")
            object.__setattr__(
                self,
                "semantic_context_binding",
                _semantic_context_binding(self.semantic_context_binding),
            )


@dataclass(frozen=True, slots=True)
class ProductionTaskResolution:
    classification: str
    operation: str | None
    target_task_id: str | None
    arguments: Mapping[str, object]
    confirmation: str
    outcome: ProductionTaskPolicyOutcome
    reason: str
    command_id: str | None = None
    origin_receipt_id: str | None = None
    origin_binding_fingerprint: str | None = None
    origin_binding: ProductionOriginBinding | None = None
    task_set_fingerprint: str | None = None
    authority_fingerprint: str | None = None
    candidate_task_ids: tuple[str, ...] = ()
    clarification_handle_id: str | None = None
    clarification_generation: int | None = None
    predecessor_result_digest: str | None = None
    confirmation_consumption_id: str | None = None
    confirmation_binding: ProductionConfirmationBinding | None = None
    zero_effects: tuple[str, ...] = _ZERO_EFFECTS

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _canonical_mapping(self.arguments))
        if self.confirmation_binding is not None and (
            not isinstance(self.confirmation_binding, ProductionConfirmationBinding)
            or self.confirmation_binding.operation != self.operation
            or self.confirmation_binding.target_task_id != self.target_task_id
            or self.confirmation_binding.task_set_fingerprint
            != self.task_set_fingerprint
            or self.confirmation_binding.command_id != self.command_id
            or self.confirmation_binding.arguments_sha256
            != _sha256(dict(self.arguments))
        ):
            raise ValueError("INVALID_RESOLUTION_CONFIRMATION_BINDING")

    def canonical_policy_tuple(self) -> tuple[object, ...]:
        return (
            self.classification,
            self.operation,
            self.target_task_id,
            canonical_json_bytes(dict(self.arguments)),
            self.confirmation,
            self.outcome.value,
        )

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "arguments": dict(self.arguments),
                "authority_fingerprint": self.authority_fingerprint,
                "candidate_task_ids": list(self.candidate_task_ids),
                "classification": self.classification,
                "command_id": self.command_id,
                "confirmation": self.confirmation,
                "confirmation_binding": (
                    None
                    if self.confirmation_binding is None
                    else self.confirmation_binding.fingerprint
                ),
                "confirmation_consumption_id": self.confirmation_consumption_id,
                "operation": self.operation,
                "origin_binding_fingerprint": self.origin_binding_fingerprint,
                "origin_receipt_id": self.origin_receipt_id,
                "outcome": self.outcome.value,
                "predecessor_result_digest": self.predecessor_result_digest,
                "reason": self.reason,
                "target_task_id": self.target_task_id,
                "task_set_fingerprint": self.task_set_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class ClarificationHandle:
    handle_id: str
    boot_id: str
    generation: int
    principal_id: str
    scope: ScopeRef
    source_origin_fingerprint: str
    source_origin_receipt_id: str
    source_commit_id: str | None
    operation: str
    arguments_sha256: str
    ambiguous_fields: tuple[str, ...]
    candidate_task_ids: tuple[str, ...]
    task_set_fingerprint: str
    created_at: datetime
    expires_at: datetime


@dataclass(slots=True)
class _ClarificationEntry:
    handle: ClarificationHandle
    consumed: bool = False


class BoundedClarificationOwner:
    """Dedicated bounded, per-subject, single-use clarification CAS owner."""

    def __init__(
        self,
        *,
        capacity: int = 64,
        per_subject_capacity: int | None = None,
        ttl: timedelta = timedelta(minutes=5),
        boot_id: str,
    ) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 1_024:
            raise ValueError("INVALID_CLARIFICATION_CAPACITY")
        if per_subject_capacity is None:
            per_subject_capacity = min(8, capacity)
        if (
            type(per_subject_capacity) is not int
            or not 1 <= per_subject_capacity <= capacity
        ):
            raise ValueError("INVALID_CLARIFICATION_SUBJECT_CAPACITY")
        if not timedelta(seconds=1) <= ttl <= timedelta(minutes=30):
            raise ValueError("INVALID_CLARIFICATION_TTL")
        _require_opaque(boot_id, "clarification_boot_id")
        self._capacity = capacity
        self._per_subject_capacity = per_subject_capacity
        self._ttl = ttl
        self._boot_id = boot_id
        self._boot_fingerprint = hashlib.sha256(boot_id.encode("utf-8")).hexdigest()[
            :16
        ]
        self._generation = 0
        self._entries: OrderedDict[str, _ClarificationEntry] = OrderedDict()
        self._lock = RLock()

    def issue(
        self,
        *,
        origin_binding: ProductionOriginBinding,
        origin_receipt: TrustedProductionOriginReceipt,
        operation: str,
        arguments: Mapping[str, object],
        ambiguous_fields: tuple[str, ...],
        candidate_task_ids: tuple[str, ...],
        task_set_fingerprint: str,
        now: datetime,
    ) -> ClarificationHandle:
        if (
            origin_receipt.principal_id != origin_binding.principal_id
            or origin_receipt.binding_fingerprint != origin_binding.fingerprint
            or operation not in _ALL_OPERATIONS
            or not ambiguous_fields
            or len(ambiguous_fields) > 8
            or not all(
                type(field) is str and _FIELD_NAME.fullmatch(field)
                for field in ambiguous_fields
            )
            or not candidate_task_ids
            or len(candidate_task_ids) > 32
            or len(set(candidate_task_ids)) != len(candidate_task_ids)
            or _SHA256.fullmatch(task_set_fingerprint) is None
        ):
            raise ValueError("INVALID_CLARIFICATION_BINDING")
        for task_id in candidate_task_ids:
            _require_opaque(task_id, "clarification_candidate_task_id")
        canonical_arguments = _canonical_mapping(arguments)
        now = _aware_utc(now)
        with self._lock:
            self._drop_expired(now)
            subject_count = sum(
                entry.handle.principal_id == origin_binding.principal_id
                for entry in self._entries.values()
            )
            if len(self._entries) >= self._capacity:
                raise ValueError("CLARIFICATION_CAPACITY_EXCEEDED")
            if subject_count >= self._per_subject_capacity:
                raise ValueError("CLARIFICATION_SUBJECT_CAPACITY_EXCEEDED")
            self._generation += 1
            arguments_sha256 = _sha256(dict(canonical_arguments))
            identity = {
                "arguments_sha256": arguments_sha256,
                "ambiguous_fields": list(ambiguous_fields),
                "boot_id": self._boot_id,
                "candidate_task_ids": list(candidate_task_ids),
                "generation": self._generation,
                "operation": operation,
                "origin": origin_binding.fingerprint,
                "origin_receipt_id": origin_receipt.receipt_id,
                "principal_id": origin_binding.principal_id,
                "scope": origin_binding.scope.to_dict(),
                "task_set_fingerprint": task_set_fingerprint,
            }
            handle_id = f"clarification.{self._boot_fingerprint}." + _sha256(identity)
            handle = ClarificationHandle(
                handle_id=handle_id,
                boot_id=self._boot_id,
                generation=self._generation,
                principal_id=origin_binding.principal_id,
                scope=origin_binding.scope,
                source_origin_fingerprint=origin_binding.fingerprint,
                source_origin_receipt_id=origin_receipt.receipt_id,
                source_commit_id=origin_binding.commit_id,
                operation=operation,
                arguments_sha256=arguments_sha256,
                ambiguous_fields=ambiguous_fields,
                candidate_task_ids=candidate_task_ids,
                task_set_fingerprint=task_set_fingerprint,
                created_at=now,
                expires_at=now + self._ttl,
            )
            self._entries[handle_id] = _ClarificationEntry(handle)
            return handle

    def consume(
        self,
        answer: ClarificationAnswer,
        *,
        answer_origin: ProductionOriginBinding,
        answer_receipt: TrustedProductionOriginReceipt,
        operation: str,
        arguments: Mapping[str, object],
        task_set_fingerprint: str,
        now: datetime,
    ) -> str:
        now = _aware_utc(now)
        with self._lock:
            if not answer.handle_id.startswith(
                f"clarification.{self._boot_fingerprint}."
            ):
                raise ValueError("CLARIFICATION_HANDLE_INVALID_AFTER_RESTART")
            entry = self._entries.get(answer.handle_id)
            if entry is None:
                raise ValueError("CLARIFICATION_HANDLE_UNAVAILABLE")
            handle = entry.handle
            if now >= handle.expires_at:
                del self._entries[answer.handle_id]
                raise ValueError("CLARIFICATION_HANDLE_EXPIRED")
            if entry.consumed:
                raise ValueError("CLARIFICATION_ALREADY_CONSUMED")
            if (
                answer_origin.origin is ProductionIntentOrigin.STRUCTURED
                or answer_origin.commit_id is None
                or answer_origin.clarification_answer_sha256 != answer.fingerprint
                or answer_origin.commit_id == handle.source_commit_id
                or answer_origin.fingerprint == handle.source_origin_fingerprint
                or answer_receipt.principal_id != answer_origin.principal_id
                or answer_receipt.binding_fingerprint != answer_origin.fingerprint
                or answer.generation != handle.generation
                or answer_origin.principal_id != handle.principal_id
                or answer_origin.scope != handle.scope
                or operation != handle.operation
                or _sha256(dict(_canonical_mapping(arguments)))
                != handle.arguments_sha256
                or answer.task_set_fingerprint != handle.task_set_fingerprint
                or task_set_fingerprint != handle.task_set_fingerprint
                or answer.selected_task_id not in handle.candidate_task_ids
            ):
                raise ValueError("CLARIFICATION_BINDING_CONFLICT")
            entry.consumed = True
            return answer.selected_task_id

    def restart(self, boot_id: str) -> None:
        _require_opaque(boot_id, "clarification_boot_id")
        with self._lock:
            self._entries.clear()
            self._boot_id = boot_id
            self._boot_fingerprint = hashlib.sha256(
                boot_id.encode("utf-8")
            ).hexdigest()[:16]
            self._generation = 0

    def _drop_expired(self, now: datetime) -> None:
        for handle_id in [
            key
            for key, entry in self._entries.items()
            if now >= entry.handle.expires_at
        ]:
            del self._entries[handle_id]


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("AWARE_UTC_TIME_REQUIRED")
    return value.astimezone(UTC)


def _expected_extraction_fields(
    proposal: ProductionTaskIntentProposal,
) -> frozenset[str]:
    if proposal.operation is None:
        return frozenset({"dialogue"})
    fields = {"operation"}
    if proposal.target is not None:
        fields.add("target")
    fields.update(f"arguments.{key}" for key in proposal.arguments)
    return frozenset(fields)


def _structured_semantic_digest(proposal: ProductionTaskIntentProposal) -> str:
    semantic: dict[str, object] = {
        "arguments": dict(proposal.arguments),
        "observed_task_revision": proposal.observed_task_revision,
        "operation": proposal.operation,
        "target": proposal.target,
        "target_kind": proposal.target_kind,
    }
    if proposal.operation is None:
        semantic["dialogue_reason"] = proposal.reason
    return _sha256(semantic)


def _semantic_context_binding(value: Mapping[str, str]) -> Mapping[str, str]:
    fields = {
        "context_sha256",
        "semantic_config_sha256",
        "model_identity",
        "model_config_version",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("INVALID_SEMANTIC_CONTEXT_BINDING")
    frozen = dict(value)
    for key, item in frozen.items():
        _require_text(item, key, maximum=512)
        if key.endswith("sha256") and _SHA256.fullmatch(item) is None:
            raise ValueError("INVALID_SEMANTIC_CONTEXT_DIGEST")
    return MappingProxyType(frozen)


def _build_origin_binding(
    request: ProductionTaskIntentRequest,
) -> ProductionOriginBinding:
    clarification_answer_sha256 = (
        request.clarification_answer.fingerprint
        if request.clarification_answer is not None
        else request.clarification_answer_fingerprint
    )
    if request.origin is ProductionIntentOrigin.STRUCTURED:
        return ProductionOriginBinding(
            principal_id=request.scope.subject_id,
            scope=request.scope,
            origin=request.origin,
            source_id=request.source_id,
            commit_id=None,
            commit_sha256=None,
            extractions=(),
            structured_semantic_sha256=_structured_semantic_digest(request.proposal),
            clarification_answer_sha256=clarification_answer_sha256,
        )
    commit = request.commit
    assert commit is not None
    extraction_names = frozenset(
        item.field_name for item in request.proposal.extractions
    )
    if extraction_names != _expected_extraction_fields(request.proposal):
        raise ValueError("TASK_INTENT_EXTRACTION_COVERAGE_MISMATCH")
    bound: list[BoundProductionFieldExtraction] = []
    for extraction in request.proposal.extractions:
        if extraction.source_end > len(commit.text):
            raise ValueError("TASK_INTENT_SOURCE_SPAN_MISMATCH")
        content = commit.text[extraction.source_start : extraction.source_end]
        bound.append(
            BoundProductionFieldExtraction(
                extraction.field_name,
                extraction.source_start,
                extraction.source_end,
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
                _sha256(_proposal_field_value(request.proposal, extraction.field_name)),
            )
        )
    return ProductionOriginBinding(
        principal_id=request.scope.subject_id,
        scope=request.scope,
        origin=request.origin,
        source_id=request.source_id,
        commit_id=commit.commit_id,
        commit_sha256=hashlib.sha256(commit.canonical_bytes()).hexdigest(),
        extractions=tuple(bound),
        structured_semantic_sha256=None,
        clarification_answer_sha256=clarification_answer_sha256,
        semantic_context_binding=request.semantic_context_binding,
    )


def build_production_origin_binding(
    request: ProductionTaskIntentRequest,
) -> ProductionOriginBinding:
    """Build the exact call-local origin binding verified by product composition."""

    if not isinstance(request, ProductionTaskIntentRequest):
        raise TypeError("PRODUCTION_TASK_INTENT_REQUEST_REQUIRED")
    return _build_origin_binding(request)


def _proposal_field_value(
    proposal: ProductionTaskIntentProposal, field_name: str
) -> object:
    if field_name == "dialogue":
        return proposal.reason
    if field_name == "operation":
        return proposal.operation
    if field_name == "target":
        return proposal.target
    prefix = "arguments."
    if field_name.startswith(prefix):
        return proposal.arguments[field_name[len(prefix) :]]
    raise ValueError("INVALID_EXTRACTION_FIELD")


def _validate_arguments(
    operation: str,
    arguments: Mapping[str, object],
    deferred_fields: tuple[str, ...] = (),
) -> str | None:
    if set(arguments) != _ARGUMENT_FIELDS[operation] - set(deferred_fields):
        return "TASK_INTENT_ARGUMENT_SCHEMA_MISMATCH"
    if operation in _QUERY_KIND and arguments["query_kind"] != _QUERY_KIND[operation]:
        return "TASK_QUERY_KIND_MISMATCH"
    if operation in {"task.list", "task.events"}:
        limit = arguments["limit"]
        if type(limit) is not int or not 1 <= limit <= 500:
            return "TASK_QUERY_LIMIT_INVALID"
    if operation == "task.events":
        after_seq = arguments["after_seq"]
        if type(after_seq) is not int or after_seq < -1:
            return "TASK_EVENT_CURSOR_INVALID"
    text_fields = {
        "task.create": ("name", "instruction"),
        "task.update": ("instruction",),
        "task.adjust": ("adjustment",),
        "task.provide_input": ("answer",),
        "task.create_successor": ("name", "instruction"),
    }.get(operation, ())
    for field_name in text_fields:
        if field_name in deferred_fields:
            continue
        try:
            material = _require_text(
                arguments[field_name],
                field_name,
                maximum=256 if field_name == "name" else 4_096,
            )
            if not material.strip():
                raise ValueError("WHITESPACE_ONLY_MATERIAL_FIELD")
        except ValueError:
            return "TASK_INTENT_ARGUMENT_VALUE_INVALID"
    if operation == "task.provide_input":
        if "responds_to_event_id" in deferred_fields:
            return None
        try:
            _require_opaque(arguments["responds_to_event_id"], "responds_to_event_id")
        except ValueError:
            return "TASK_INTENT_ARGUMENT_VALUE_INVALID"
    if (
        operation == "task.reprioritize"
        and arguments["priority"] not in _TASK_PRIORITIES
    ):
        return "TASK_PRIORITY_INVALID"
    return None


class ProductionMultiTaskResolver:
    """Resolve one untrusted proposal against mandatory trusted authorities."""

    minimum_confidence = 0.80

    def __init__(self, clarification_owner: BoundedClarificationOwner) -> None:
        if not isinstance(clarification_owner, BoundedClarificationOwner):
            raise ValueError("TRUSTED_CLARIFICATION_OWNER_REQUIRED")
        self._clarifications = clarification_owner

    def resolve(
        self,
        request: ProductionTaskIntentRequest,
        authority: ProductionTaskAuthorityReader,
        origin_authority: ProductionOriginAuthority,
        confirmation_consumer: ProductionConfirmationConsumer,
    ) -> ProductionTaskResolution:
        proposal = request.proposal
        if not proposal.committed:
            return self._safe(
                request,
                "rejected",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "INPUT_NOT_COMMITTED",
            )
        try:
            origin_binding = _build_origin_binding(request)
            origin_receipt = origin_authority.verify_origin(origin_binding)
        except (TypeError, ValueError):
            return self._safe(
                request,
                "rejected",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "ORIGIN_AUTHORITY_REJECTED",
            )
        if (
            not isinstance(origin_receipt, TrustedProductionOriginReceipt)
            or origin_receipt.principal_id != request.scope.subject_id
            or origin_receipt.binding_fingerprint != origin_binding.fingerprint
        ):
            return self._safe(
                request,
                "rejected",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "ORIGIN_AUTHORITY_REJECTED",
            )
        origin_fields = {
            "origin_receipt_id": origin_receipt.receipt_id,
            "origin_binding_fingerprint": origin_binding.fingerprint,
            "origin_binding": origin_binding,
        }
        if proposal.confidence < self.minimum_confidence:
            return self._safe(
                request,
                "rejected",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_INTENT_LOW_CONFIDENCE",
                **origin_fields,
            )
        if proposal.operation is None:
            rejected = proposal.reason.startswith("REJECTED_")
            return self._safe(
                request,
                "rejected" if rejected else "dialogue",
                None,
                None,
                {},
                "not_applicable",
                (
                    ProductionTaskPolicyOutcome.REJECTED
                    if rejected
                    else ProductionTaskPolicyOutcome.DIALOGUE
                ),
                proposal.reason,
                **origin_fields,
            )
        operation = proposal.operation
        argument_error = _validate_arguments(
            operation, proposal.arguments, proposal.origin_deferred_fields
        )
        if argument_error is not None:
            return self._safe(
                request,
                "rejected",
                operation,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                argument_error,
                **origin_fields,
            )
        if operation in _COLLECTION_OPERATIONS and (
            proposal.target is not None or proposal.target_kind is not None
        ):
            return self._safe(
                request,
                "rejected",
                operation,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_COLLECTION_TARGET_FORBIDDEN",
                **origin_fields,
            )

        visible = authority.list_visible_tasks(request.scope)
        if visible.scope != request.scope:
            return self._safe(
                request,
                "rejected",
                operation,
                None,
                proposal.arguments,
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_AUTHORITY_SCOPE_MISMATCH",
                **origin_fields,
            )

        if request.clarification_answer is not None:
            try:
                selected_id = self._clarifications.consume(
                    request.clarification_answer,
                    answer_origin=origin_binding,
                    answer_receipt=origin_receipt,
                    operation=operation,
                    arguments=proposal.arguments,
                    task_set_fingerprint=visible.fingerprint,
                    now=datetime.now(UTC),
                )
            except ValueError:
                return self._safe(
                    request,
                    "rejected",
                    operation,
                    None,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "CLARIFICATION_BINDING_CONFLICT",
                    task_set_fingerprint=visible.fingerprint,
                    **origin_fields,
                )
            target = next(
                (item for item in visible.tasks if item.task_id == selected_id), None
            )
            candidates: tuple[AuthenticatedTaskFact, ...] = ()
            missing_kind = "clarification"
            if target is None:
                return self._safe(
                    request,
                    "rejected",
                    operation,
                    None,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "CLARIFICATION_TASK_SET_CHANGED",
                    task_set_fingerprint=visible.fingerprint,
                    **origin_fields,
                )
        else:
            target, candidates, missing_kind = self._select_target(
                operation, proposal.target, proposal.target_kind, visible
            )
        if operation not in _COLLECTION_OPERATIONS and target is None:
            if missing_kind == "explicit_task_id" or not candidates:
                return self._safe(
                    request,
                    "rejected",
                    operation,
                    None,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.REJECTED,
                    "TASK_TARGET_UNRESOLVED",
                    task_set_fingerprint=visible.fingerprint,
                    **origin_fields,
                )
            try:
                handle = self._clarifications.issue(
                    origin_binding=origin_binding,
                    origin_receipt=origin_receipt,
                    operation=operation,
                    arguments=proposal.arguments,
                    ambiguous_fields=("target",),
                    candidate_task_ids=tuple(item.task_id for item in candidates),
                    task_set_fingerprint=visible.fingerprint,
                    now=datetime.now(UTC),
                )
            except ValueError:
                return self._safe(
                    request,
                    "rejected",
                    operation,
                    None,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.REJECTED,
                    "CLARIFICATION_UNAVAILABLE",
                    task_set_fingerprint=visible.fingerprint,
                    **origin_fields,
                )
            return ProductionTaskResolution(
                classification="clarification",
                operation=operation,
                target_task_id=None,
                arguments=proposal.arguments,
                confirmation="not_applicable",
                outcome=ProductionTaskPolicyOutcome.CLARIFICATION,
                reason="TASK_TARGET_AMBIGUOUS",
                command_id=request.command_id,
                task_set_fingerprint=visible.fingerprint,
                candidate_task_ids=tuple(item.task_id for item in candidates),
                clarification_handle_id=handle.handle_id,
                clarification_generation=handle.generation,
                **origin_fields,
            )

        reread: AuthenticatedTaskFact | None = None
        if target is not None:
            target_task_id = target.task_id
            converged = False
            for attempt in range(_TARGET_AUTHORITY_CONVERGENCE_ATTEMPTS):
                reread = authority.get_task(request.scope, target_task_id)
                status = authority.task_status(request.scope, target_task_id)
                if (
                    reread is not None
                    and status is not None
                    and reread.fingerprint == target.fingerprint
                    and status.fingerprint == reread.fingerprint
                ):
                    converged = True
                    break
                # A queue admission/retry projection can legitimately advance
                # between the list/get/status reads.  Re-read the entire
                # authority generation, but never re-resolve the exact target
                # selected by the command.  Ambiguity clarifications remain
                # bound to their original complete Task set and cannot drift.
                if (
                    attempt + 1 == _TARGET_AUTHORITY_CONVERGENCE_ATTEMPTS
                    or request.clarification_answer is not None
                ):
                    break
                refreshed = authority.list_visible_tasks(request.scope)
                if refreshed.scope != request.scope:
                    return self._safe(
                        request,
                        "rejected",
                        operation,
                        target_task_id,
                        proposal.arguments,
                        "not_applicable",
                        ProductionTaskPolicyOutcome.REJECTED,
                        "TASK_AUTHORITY_SCOPE_MISMATCH",
                        **origin_fields,
                    )
                refreshed_target = next(
                    (
                        item
                        for item in refreshed.tasks
                        if item.task_id == target_task_id
                    ),
                    None,
                )
                if refreshed_target is None:
                    break
                visible = refreshed
                target = refreshed_target
            if not converged:
                return self._safe(
                    request,
                    "task_intent",
                    operation,
                    target_task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_AUTHORITY_CHANGED",
                    task_set_fingerprint=visible.fingerprint,
                    **origin_fields,
                )
            if (
                proposal.observed_task_revision is not None
                and proposal.observed_task_revision != reread.revision_number
            ):
                return self._safe(
                    request,
                    "task_intent",
                    operation,
                    target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_SNAPSHOT_STALE",
                    task_set_fingerprint=visible.fingerprint,
                    authority_fingerprint=reread.fingerprint,
                    **origin_fields,
                )

        try:
            resolved_arguments = self._bind_deferred_arguments(proposal, reread)
        except ValueError as error:
            return self._safe(
                request,
                "task_intent",
                operation,
                None if target is None else target.task_id,
                proposal.arguments,
                "not_applicable",
                ProductionTaskPolicyOutcome.CONFLICT,
                str(error),
                task_set_fingerprint=visible.fingerprint,
                authority_fingerprint=(None if reread is None else reread.fingerprint),
                **origin_fields,
            )
        if _validate_arguments(operation, resolved_arguments) is not None:
            return self._safe(
                request,
                "rejected",
                operation,
                None if target is None else target.task_id,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "AUTHORITY_DERIVED_ARGUMENT_INVALID",
                task_set_fingerprint=visible.fingerprint,
                authority_fingerprint=(None if reread is None else reread.fingerprint),
                **origin_fields,
            )
        outcome, reason, predecessor_digest = self._state_capability_policy(
            operation, resolved_arguments, reread, request.scope, authority
        )
        confirmation = "not_applicable"
        consumption_id = None
        confirmation_binding = None
        if outcome is ProductionTaskPolicyOutcome.PROPOSED:
            confirmation = (
                "required" if operation in _MATERIAL_OPERATIONS else "not_required"
            )
            if confirmation == "required":
                confirmation_binding = ProductionConfirmationBinding(
                    principal_id=request.scope.subject_id,
                    scope=request.scope,
                    command_id=request.command_id,
                    origin=request.origin,
                    origin_receipt_id=origin_receipt.receipt_id,
                    origin_binding_fingerprint=origin_binding.fingerprint,
                    operation=operation,
                    target_task_id=None if target is None else target.task_id,
                    target_attempt_id=None if reread is None else reread.attempt_id,
                    arguments_sha256=_sha256(dict(resolved_arguments)),
                    task_set_fingerprint=visible.fingerprint,
                    capability_profile_digest=self._capability_digest(visible, reread),
                    context_fingerprint=visible.authority_context_fingerprint,
                    model_binding_fingerprint=(
                        visible.collection_model_binding_fingerprint
                        if reread is None
                        else reread.model_binding_fingerprint
                    ),
                )
        if request.confirmation_id is not None:
            if confirmation != "required":
                return self._safe(
                    request,
                    "rejected",
                    operation,
                    None if target is None else target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "UNEXPECTED_CONFIRMATION",
                    task_set_fingerprint=visible.fingerprint,
                    authority_fingerprint=(
                        None if reread is None else reread.fingerprint
                    ),
                    **origin_fields,
                )
            assert confirmation_binding is not None
            try:
                consumed = confirmation_consumer.verify_and_consume(
                    request.confirmation_id, confirmation_binding
                )
            except (TypeError, ValueError):
                consumed = None
            if (
                not isinstance(consumed, TrustedConfirmationConsumptionReceipt)
                or consumed.confirmation_id != request.confirmation_id
                or consumed.binding_fingerprint != confirmation_binding.fingerprint
                or consumed.replayed
            ):
                return self._safe(
                    request,
                    "rejected",
                    operation,
                    None if target is None else target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "CONFIRMATION_BINDING_CONFLICT",
                    task_set_fingerprint=visible.fingerprint,
                    authority_fingerprint=(
                        None if reread is None else reread.fingerprint
                    ),
                    **origin_fields,
                )
            confirmation = "confirmed"
            consumption_id = consumed.consumption_id
        return ProductionTaskResolution(
            classification="task_intent",
            operation=operation,
            target_task_id=None if target is None else target.task_id,
            arguments=resolved_arguments,
            confirmation=confirmation,
            outcome=outcome,
            reason=reason,
            command_id=request.command_id,
            task_set_fingerprint=visible.fingerprint,
            authority_fingerprint=None if reread is None else reread.fingerprint,
            predecessor_result_digest=predecessor_digest,
            confirmation_consumption_id=consumption_id,
            confirmation_binding=confirmation_binding,
            **origin_fields,
        )

    @staticmethod
    def _bind_deferred_arguments(
        proposal: ProductionTaskIntentProposal,
        task: AuthenticatedTaskFact | None,
    ) -> Mapping[str, object]:
        if not proposal.origin_deferred_fields:
            return proposal.arguments
        if task is None:
            raise ValueError("AUTHORITY_DERIVED_TARGET_REQUIRED")
        resolved = dict(proposal.arguments)
        if proposal.operation == "task.provide_input":
            if task.decision_required_event_id is None:
                raise ValueError("TASK_INPUT_STATE_CONFLICT")
            resolved["responds_to_event_id"] = task.decision_required_event_id
        elif proposal.operation == "task.create_successor":
            predecessor = task.name.strip()
            if predecessor.casefold().endswith("build report"):
                name = predecessor[: -len("build report")] + "revised report"
            else:
                name = f"Revised {predecessor}"
            article_name = predecessor[0].lower() + predecessor[1:]
            instruction = f"Create a revised {article_name}."
            if (
                len(name.encode("utf-8")) > 256
                or len(instruction.encode("utf-8")) > 4_096
            ):
                raise ValueError("SUCCESSOR_SPEC_DERIVATION_FAILED")
            resolved.update({"name": name, "instruction": instruction})
        else:
            raise ValueError("AUTHORITY_DERIVED_ARGUMENT_UNSUPPORTED")
        return _canonical_mapping(resolved)

    @staticmethod
    def _select_target(
        operation: str,
        target: str | None,
        target_kind: str | None,
        visible: TaskAuthorityRead,
    ) -> tuple[AuthenticatedTaskFact | None, tuple[AuthenticatedTaskFact, ...], str]:
        if operation in _COLLECTION_OPERATIONS:
            return None, (), "collection"
        all_visible = visible.tasks[:32]
        if target is None and target_kind == "task_id":
            return None, (), "explicit_task_id"
        if (
            target is None
            or target_kind == "hint"
            or target.casefold() in {"current", "recent", "latest"}
        ):
            return None, all_visible, "hint_only"
        ids = tuple(item for item in visible.tasks if item.task_id == target)
        if target_kind == "task_id":
            return (
                (ids[0], ids, "explicit_task_id")
                if ids
                else (None, (), "explicit_task_id")
            )
        if ids:
            return ids[0], ids, "explicit_task_id"
        refs = tuple(item for item in visible.tasks if item.stable_reference == target)
        if target_kind == "stable_reference":
            return (
                (refs[0], refs, "stable_reference")
                if refs
                else (None, all_visible, "zero_candidate")
            )
        if refs:
            return refs[0], refs, "stable_reference"
        names = tuple(item for item in visible.tasks if item.name == target)
        if len(names) == 1:
            return names[0], names, "unique_name"
        if len(names) > 1:
            return None, names, "duplicate_name"
        return None, all_visible, "zero_candidate"

    @staticmethod
    def _state_capability_policy(
        operation: str,
        arguments: Mapping[str, object],
        task: AuthenticatedTaskFact | None,
        scope: ScopeRef,
        authority: ProductionTaskAuthorityReader,
    ) -> tuple[ProductionTaskPolicyOutcome, str, str | None]:
        if operation in FORMAL_TASK_QUERY_OPERATIONS:
            if (
                operation == "task.events"
                and task is not None
                and authority.event_head(scope, task.task_id)
                != (task.event_head, task.event_head_id)
            ):
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_EVENT_HEAD_CHANGED",
                    None,
                )
            if operation == "task.result" and task is not None:
                digest = authority.result_digest(scope, task.task_id)
                if digest != task.result_digest:
                    return (
                        ProductionTaskPolicyOutcome.CONFLICT,
                        "TASK_RESULT_CHANGED",
                        None,
                    )
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "TASK_QUERY_POLICY_ACCEPTED",
                None,
            )
        if operation == "task.create":
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "TASK_CREATE_POLICY_ACCEPTED",
                None,
            )
        if task is None:
            return (
                ProductionTaskPolicyOutcome.CONFLICT,
                "TASK_TARGET_REQUIRED",
                None,
            )
        if task.terminal and operation != "task.create_successor":
            return (
                ProductionTaskPolicyOutcome.CONFLICT,
                "TERMINAL_TASK_IMMUTABLE",
                None,
            )
        if operation == "task.create_successor":
            digest = authority.result_digest(scope, task.task_id)
            if (
                not task.terminal
                or task.outcome is TerminalOutcome.UNKNOWN
                or task.successor_task_id is not None
                or digest != task.result_digest
            ):
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "SUCCESSOR_PREDECESSOR_CONFLICT",
                    None,
                )
            if "task.create_successor" not in task.supported_operations:
                return (
                    ProductionTaskPolicyOutcome.UNSUPPORTED,
                    "TASK_SUCCESSOR_UNSUPPORTED",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "SUCCESSOR_POLICY_ACCEPTED",
                digest,
            )
        if operation == "task.update":
            if (
                task.state is not TaskState.ACCEPTED
                or task.attempt_state is not AttemptState.ACCEPTED
                or task.dispatch_control != "unclaimed"
                or "task.update" not in task.supported_operations
            ):
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_UPDATE_STATE_CONFLICT",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "TASK_UPDATE_POLICY_ACCEPTED",
                None,
            )
        if operation == "task.adjust":
            if task.state is not TaskState.RUNNING:
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_ADJUST_STATE_CONFLICT",
                    None,
                )
            if "task.adjust" not in task.supported_operations:
                return (
                    ProductionTaskPolicyOutcome.UNSUPPORTED,
                    "TASK_ADJUST_UNSUPPORTED",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "TASK_ADJUST_POLICY_ACCEPTED",
                None,
            )
        if operation == "task.provide_input":
            if (
                task.state is not TaskState.DECISION_REQUIRED
                or task.attempt_state is not AttemptState.RUNNING
                or task.decision_required_event_id != arguments["responds_to_event_id"]
            ):
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_INPUT_STATE_CONFLICT",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.UNSUPPORTED,
                "TASK_INPUT_UNSUPPORTED",
                None,
            )
        if operation in {"task.pause", "task.resume"}:
            return (
                ProductionTaskPolicyOutcome.UNSUPPORTED,
                "TASK_CONTROL_UNSUPPORTED",
                None,
            )
        if operation == "task.reprioritize":
            if (
                task.state is not TaskState.ACCEPTED
                or task.attempt_state is not AttemptState.ACCEPTED
                or task.dispatch_control != "unclaimed"
            ):
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_REPRIORITIZE_STATE_CONFLICT",
                    None,
                )
            if (
                task.admission_fingerprint is None
                or "task.reprioritize" not in task.supported_operations
            ):
                return (
                    ProductionTaskPolicyOutcome.UNSUPPORTED,
                    "TASK_REPRIORITIZE_UNSUPPORTED",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "TASK_REPRIORITIZE_POLICY_ACCEPTED",
                None,
            )
        if (
            operation == "task.cancel"
            and "task.cancel" not in task.supported_operations
        ):
            return (
                ProductionTaskPolicyOutcome.UNSUPPORTED,
                "TASK_CANCEL_UNSUPPORTED",
                None,
            )
        return (
            ProductionTaskPolicyOutcome.PROPOSED,
            "TASK_MUTATION_POLICY_ACCEPTED",
            None,
        )

    @staticmethod
    def _capability_digest(
        visible: TaskAuthorityRead, target: AuthenticatedTaskFact | None
    ) -> str:
        if target is not None:
            return target.capability_profile_digest
        return visible.collection_capability_profile_digest

    @staticmethod
    def _safe(
        request: ProductionTaskIntentRequest,
        classification: str,
        operation: str | None,
        target_task_id: str | None,
        arguments: Mapping[str, object],
        confirmation: str,
        outcome: ProductionTaskPolicyOutcome,
        reason: str,
        *,
        origin_receipt_id: str | None = None,
        origin_binding_fingerprint: str | None = None,
        origin_binding: ProductionOriginBinding | None = None,
        task_set_fingerprint: str | None = None,
        authority_fingerprint: str | None = None,
    ) -> ProductionTaskResolution:
        return ProductionTaskResolution(
            classification=classification,
            operation=operation,
            target_task_id=target_task_id,
            arguments=arguments,
            confirmation=confirmation,
            outcome=outcome,
            reason=reason,
            command_id=request.command_id,
            origin_receipt_id=origin_receipt_id,
            origin_binding_fingerprint=origin_binding_fingerprint,
            origin_binding=origin_binding,
            task_set_fingerprint=task_set_fingerprint,
            authority_fingerprint=authority_fingerprint,
        )


__all__ = [
    "AuthenticatedTaskFact",
    "BoundProductionFieldExtraction",
    "BoundedClarificationOwner",
    "ClarificationAnswer",
    "ClarificationHandle",
    "ProductionConfirmationBinding",
    "ProductionConfirmationConsumer",
    "ProductionFieldExtraction",
    "ProductionIntentOrigin",
    "ProductionMultiTaskResolver",
    "ProductionOriginAuthority",
    "ProductionOriginBinding",
    "ProductionTaskAuthorityReader",
    "ProductionTaskIntentProposal",
    "ProductionTaskIntentRequest",
    "ProductionTaskPolicyOutcome",
    "ProductionTaskResolution",
    "TaskAuthorityRead",
    "TrustedConfirmationConsumptionReceipt",
    "TrustedProductionOriginReceipt",
    "build_production_origin_binding",
]
