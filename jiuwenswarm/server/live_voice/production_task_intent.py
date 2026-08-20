# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed production policy for generalized multi-Task intent resolution.

The resolver treats language/model output as an untrusted proposal.  It reads
only authenticated Task Core facts through :class:`ProductionTaskAuthorityReader`,
re-reads an exact target before returning a policy decision, and has no write or
external-effect Port.  Clarification is owned by a dedicated bounded state
object, never by product UI or Registry state.
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
    TurnCommit,
    canonical_json_bytes,
)

from .voice_task_policy import (
    FORMAL_TASK_MUTATION_OPERATIONS,
    FORMAL_TASK_QUERY_OPERATIONS,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}")
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_TERMINAL_STATES = frozenset(
    {"completed", "failed", "cancelled", "interrupted", "unknown"}
)
_TASK_STATES = (
    frozenset({"accepted", "running", "blocked", "decision_required"})
    | _TERMINAL_STATES
)
_ATTEMPT_STATES = frozenset({"accepted", "running", "terminal"})
_ALL_OPERATIONS = FORMAL_TASK_QUERY_OPERATIONS | FORMAL_TASK_MUTATION_OPERATIONS
_COLLECTION_OPERATIONS = frozenset({"task.create", "task.list"})
_MATERIAL_OPERATIONS = frozenset(
    {
        "task.create",
        "task.update",
        "task.adjust",
        "task.cancel",
        "task.create_successor",
    }
)
_UNSUPPORTED_WITHOUT_PRIMITIVE = frozenset(
    {"task.provide_input", "task.pause", "task.resume"}
)
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
    if type(value) is not str or not value or "\x00" in value or len(value) > maximum:
        raise ValueError(f"INVALID_{name.upper()}")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"INVALID_{name.upper()}") from error
    return value


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
            _require_text(item, "task_intent_argument", maximum=4_096)
        elif type(item) is int:
            if not -(2**53 - 1) <= item <= 2**53 - 1:
                raise ValueError("TASK_INTENT_ARGUMENT_BOUND_EXCEEDED")
        elif item is not None:
            raise ValueError("INVALID_TASK_INTENT_ARGUMENT_VALUE")
    if len(canonical_json_bytes(clean)) > 8_192:
        raise ValueError("TASK_INTENT_ARGUMENT_BOUND_EXCEEDED")
    return MappingProxyType(clean)


@dataclass(frozen=True, slots=True)
class AuthenticatedTaskFact:
    """Exact visible Task facts supplied by an authenticated Core read owner."""

    task_id: str
    stable_reference: str
    name: str
    state: str
    terminal: bool
    task_generation: int
    event_head: int
    event_head_id: str
    attempt_id: str | None
    attempt_state: str | None
    capability_profile_digest: str
    supported_operations: frozenset[str]
    result_digest: str | None = None
    decision_required_event_id: str | None = None
    dispatch_unclaimed: bool = False

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id", maximum=128)
        _require_text(self.stable_reference, "stable_task_reference", maximum=128)
        _require_text(self.name, "task_name", maximum=256)
        _require_text(self.state, "task_state", maximum=64)
        if self.state not in _TASK_STATES:
            raise ValueError("INVALID_TASK_STATE_FACT")
        if type(self.terminal) is not bool or self.terminal != (
            self.state in _TERMINAL_STATES
        ):
            raise ValueError("INVALID_TASK_TERMINAL_FACT")
        if type(self.task_generation) is not int or self.task_generation < 0:
            raise ValueError("INVALID_TASK_GENERATION")
        if type(self.event_head) is not int or self.event_head < 0:
            raise ValueError("INVALID_TASK_EVENT_HEAD")
        _require_text(self.event_head_id, "task_event_head_id", maximum=128)
        if (self.attempt_id is None) != (self.attempt_state is None):
            raise ValueError("INVALID_TASK_ATTEMPT_FACT")
        if self.attempt_id is not None:
            _require_text(self.attempt_id, "attempt_id", maximum=128)
            _require_text(self.attempt_state, "attempt_state", maximum=64)
            if self.attempt_state not in _ATTEMPT_STATES:
                raise ValueError("INVALID_ATTEMPT_STATE_FACT")
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
        if self.decision_required_event_id is not None:
            _require_text(
                self.decision_required_event_id,
                "decision_required_event_id",
                maximum=128,
            )
        if type(self.dispatch_unclaimed) is not bool:
            raise ValueError("INVALID_DISPATCH_FACT")

    def canonical_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "attempt_state": self.attempt_state,
            "capability_profile_digest": self.capability_profile_digest,
            "decision_required_event_id": self.decision_required_event_id,
            "dispatch_unclaimed": self.dispatch_unclaimed,
            "event_head": self.event_head,
            "event_head_id": self.event_head_id,
            "name": self.name,
            "result_digest": self.result_digest,
            "stable_reference": self.stable_reference,
            "state": self.state,
            "supported_operations": sorted(self.supported_operations),
            "task_generation": self.task_generation,
            "task_id": self.task_id,
            "terminal": self.terminal,
        }

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class TaskAuthorityRead:
    scope: ScopeRef
    generation: str
    tasks: tuple[AuthenticatedTaskFact, ...]

    def __post_init__(self) -> None:
        if self.scope.assurance != "authenticated":
            raise ValueError("AUTHENTICATED_TASK_AUTHORITY_REQUIRED")
        _require_text(self.generation, "task_set_generation", maximum=128)
        if not isinstance(self.tasks, tuple) or len(self.tasks) > 500:
            raise ValueError("INVALID_VISIBLE_TASK_SET")
        if not all(isinstance(task, AuthenticatedTaskFact) for task in self.tasks):
            raise ValueError("INVALID_VISIBLE_TASK_FACT")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("DUPLICATE_VISIBLE_TASK_ID")
        if len({task.stable_reference for task in self.tasks}) != len(self.tasks):
            raise ValueError("DUPLICATE_STABLE_TASK_REFERENCE")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    "generation": self.generation,
                    "scope": self.scope.to_dict(),
                    "tasks": [
                        task.canonical_dict()
                        for task in sorted(self.tasks, key=lambda task: task.task_id)
                    ],
                }
            )
        ).hexdigest()


@runtime_checkable
class ProductionTaskAuthorityReader(Protocol):
    """Read-only authenticated Core surface consumed by the resolver."""

    def list_visible_tasks(self, scope: ScopeRef) -> TaskAuthorityRead: ...

    def get_task(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None: ...

    def task_status(
        self, scope: ScopeRef, task_id: str
    ) -> AuthenticatedTaskFact | None: ...

    def event_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str]: ...

    def result_digest(self, scope: ScopeRef, task_id: str) -> str | None: ...

    def unread_head(self, scope: ScopeRef, task_id: str) -> tuple[int, str] | None: ...


@dataclass(frozen=True, slots=True)
class ProductionInteractionBinding:
    kind: str
    binding_id: str
    operation: str
    target_task_id: str | None
    arguments: Mapping[str, object]
    candidate_task_ids: tuple[str, ...]
    task_set_fingerprint: str

    def __post_init__(self) -> None:
        if self.kind not in {"clarification", "confirmation"}:
            raise ValueError("INVALID_INTERACTION_BINDING_KIND")
        _require_text(self.binding_id, "interaction_binding_id", maximum=128)
        if self.operation not in _ALL_OPERATIONS:
            raise ValueError("INVALID_INTERACTION_BINDING_OPERATION")
        object.__setattr__(self, "arguments", _canonical_mapping(self.arguments))
        if self.target_task_id is not None:
            _require_text(self.target_task_id, "bound_target_task_id", maximum=128)
        if (
            not isinstance(self.candidate_task_ids, tuple)
            or len(self.candidate_task_ids) > 32
            or len(set(self.candidate_task_ids)) != len(self.candidate_task_ids)
            or not all(
                type(task_id) is str and _TASK_ID.fullmatch(task_id)
                for task_id in self.candidate_task_ids
            )
        ):
            raise ValueError("INVALID_INTERACTION_CANDIDATE_SET")
        if _SHA256.fullmatch(self.task_set_fingerprint) is None:
            raise ValueError("INVALID_INTERACTION_TASK_SET_FINGERPRINT")


@dataclass(frozen=True, slots=True)
class ProductionConfirmationFact:
    confirmation_id: str
    operation: str
    target_task_id: str | None
    arguments_sha256: str
    task_set_fingerprint: str
    consumed: bool = False

    def __post_init__(self) -> None:
        _require_text(self.confirmation_id, "confirmation_id", maximum=128)
        if self.operation not in _ALL_OPERATIONS:
            raise ValueError("INVALID_CONFIRMATION_OPERATION")
        if self.target_task_id is not None:
            _require_text(
                self.target_task_id, "confirmation_target_task_id", maximum=128
            )
        if (
            _SHA256.fullmatch(self.arguments_sha256) is None
            or _SHA256.fullmatch(self.task_set_fingerprint) is None
        ):
            raise ValueError("INVALID_CONFIRMATION_FINGERPRINT")
        if type(self.consumed) is not bool:
            raise ValueError("INVALID_CONFIRMATION_STATE")


@dataclass(frozen=True, slots=True)
class ProductionTaskIntentProposal:
    """Untrusted classifier/NLU output; never an authorization artifact."""

    operation: str | None
    target: str | None
    arguments: Mapping[str, object]
    confidence: float
    committed: bool
    target_kind: str | None = None
    reason: str = "TASK_INTENT_PROPOSED"
    source_start: int | None = None
    source_end: int | None = None
    observed_task_generation: int | None = None
    interaction_binding: ProductionInteractionBinding | None = None
    confirmation: ProductionConfirmationFact | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _canonical_mapping(self.arguments))
        if self.operation is not None and self.operation not in _ALL_OPERATIONS:
            raise ValueError("UNSUPPORTED_TASK_INTENT_OPERATION")
        if self.target is not None:
            _require_text(self.target, "task_target", maximum=256)
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
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("INVALID_TASK_INTENT_SOURCE_SPAN")
        if self.observed_task_generation is not None and (
            type(self.observed_task_generation) is not int
            or self.observed_task_generation < 0
        ):
            raise ValueError("INVALID_OBSERVED_TASK_GENERATION")

    @classmethod
    def intent(
        cls,
        operation: str,
        target: str | None,
        arguments: Mapping[str, object],
    ) -> ProductionTaskIntentProposal:
        return cls(operation, target, arguments, 1.0, True)

    @classmethod
    def dialogue(cls, *, reason: str) -> ProductionTaskIntentProposal:
        return cls(None, None, {}, 1.0, True, reason=reason)


@dataclass(frozen=True, slots=True)
class ProductionTaskIntentRequest:
    origin: ProductionIntentOrigin
    scope: ScopeRef
    proposal: ProductionTaskIntentProposal
    commit: TurnCommit | None = None
    source_id: str = "structured-request"

    def __post_init__(self) -> None:
        if not isinstance(self.origin, ProductionIntentOrigin):
            raise ValueError("INVALID_PRODUCTION_INTENT_ORIGIN")
        if self.scope.assurance != "authenticated":
            raise ValueError("AUTHENTICATED_TASK_SCOPE_REQUIRED")
        if self.origin is ProductionIntentOrigin.STRUCTURED:
            if self.commit is not None:
                raise ValueError("INVALID_STRUCTURED_COMMIT_ORIGIN")
            _require_text(self.source_id, "structured_source_id", maximum=128)
        else:
            if (
                not isinstance(self.commit, TurnCommit)
                or self.commit.scope != self.scope
            ):
                raise ValueError("AUTHORITATIVE_COMMITTED_INPUT_REQUIRED")
            if (
                self.proposal.operation is not None
                and self.proposal.source_start is None
            ):
                raise ValueError("TASK_INTENT_SOURCE_BINDING_REQUIRED")
            if self.proposal.source_start is not None:
                source_end = self.proposal.source_end
                assert source_end is not None
                if not (
                    0
                    <= self.proposal.source_start
                    < source_end
                    <= len(self.commit.text)
                ):
                    raise ValueError("TASK_INTENT_SOURCE_SPAN_MISMATCH")

    @property
    def committed_source_id(self) -> str:
        return self.source_id if self.commit is None else self.commit.commit_id


@dataclass(frozen=True, slots=True)
class ProductionTaskResolution:
    classification: str
    operation: str | None
    target_task_id: str | None
    arguments: Mapping[str, object]
    confirmation: str
    outcome: ProductionTaskPolicyOutcome
    reason: str
    task_set_fingerprint: str | None = None
    authority_fingerprint: str | None = None
    candidate_task_ids: tuple[str, ...] = ()
    clarification_handle_id: str | None = None
    predecessor_result_digest: str | None = None
    zero_effects: tuple[str, ...] = _ZERO_EFFECTS

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _canonical_mapping(self.arguments))

    @classmethod
    def task_intent(
        cls,
        *,
        operation: str,
        target_task_id: str | None,
        arguments: Mapping[str, object],
        confirmation: str,
        outcome: ProductionTaskPolicyOutcome,
        task_set_fingerprint: str | None,
        authority_fingerprint: str | None,
        reason: str = "TASK_INTENT_POLICY_DECIDED",
        predecessor_result_digest: str | None = None,
    ) -> ProductionTaskResolution:
        return cls(
            "task_intent",
            operation,
            target_task_id,
            arguments,
            confirmation,
            outcome,
            reason,
            task_set_fingerprint,
            authority_fingerprint,
            predecessor_result_digest=predecessor_result_digest,
        )

    def canonical_policy_tuple(self) -> tuple[object, ...]:
        return (
            self.classification,
            self.operation,
            self.target_task_id,
            canonical_json_bytes(dict(self.arguments)),
            self.confirmation,
            self.outcome.value,
        )


@dataclass(frozen=True, slots=True)
class ClarificationHandle:
    handle_id: str
    boot_id: str
    generation: int
    scope: ScopeRef
    source_commit_id: str
    operation: str
    ambiguous_fields: tuple[str, ...]
    candidate_task_ids: tuple[str, ...]
    task_set_fingerprint: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ClarificationAnswer:
    handle_id: str
    generation: int
    scope: ScopeRef
    commit_id: str
    selected_task_id: str
    task_set_fingerprint: str

    def __post_init__(self) -> None:
        _require_text(self.handle_id, "clarification_handle_id", maximum=256)
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("INVALID_CLARIFICATION_GENERATION")
        if self.scope.assurance != "authenticated":
            raise ValueError("INVALID_CLARIFICATION_SCOPE")
        _require_text(self.commit_id, "clarification_answer_commit", maximum=128)
        _require_text(self.selected_task_id, "clarification_target", maximum=128)
        if _SHA256.fullmatch(self.task_set_fingerprint) is None:
            raise ValueError("INVALID_CLARIFICATION_TASK_SET_FINGERPRINT")


@dataclass(slots=True)
class _ClarificationEntry:
    handle: ClarificationHandle
    answer: ClarificationAnswer | None = None


class BoundedClarificationOwner:
    """Dedicated bounded pre-command state with restart-invalidated handles."""

    def __init__(
        self,
        *,
        capacity: int = 64,
        ttl: timedelta = timedelta(minutes=5),
        boot_id: str,
    ) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 1_024:
            raise ValueError("INVALID_CLARIFICATION_CAPACITY")
        if not timedelta(seconds=1) <= ttl <= timedelta(minutes=30):
            raise ValueError("INVALID_CLARIFICATION_TTL")
        _require_text(boot_id, "clarification_boot_id", maximum=128)
        self._capacity = capacity
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
        scope: ScopeRef,
        source_commit_id: str,
        operation: str,
        ambiguous_fields: tuple[str, ...],
        candidate_task_ids: tuple[str, ...],
        task_set_fingerprint: str,
        now: datetime,
    ) -> ClarificationHandle:
        if scope.assurance != "authenticated" or operation not in _ALL_OPERATIONS:
            raise ValueError("INVALID_CLARIFICATION_BINDING")
        _require_text(source_commit_id, "clarification_source_commit", maximum=128)
        if (
            not ambiguous_fields
            or len(ambiguous_fields) > 8
            or not all(_SAFE_TOKEN.fullmatch(field) for field in ambiguous_fields)
            or len(candidate_task_ids) > 32
            or len(set(candidate_task_ids)) != len(candidate_task_ids)
            or not all(_TASK_ID.fullmatch(task_id) for task_id in candidate_task_ids)
            or _SHA256.fullmatch(task_set_fingerprint) is None
        ):
            raise ValueError("INVALID_CLARIFICATION_BINDING")
        now = _aware_utc(now)
        with self._lock:
            self._drop_expired(now)
            if len(self._entries) >= self._capacity:
                raise ValueError("CLARIFICATION_CAPACITY_EXCEEDED")
            self._generation += 1
            identity = {
                "ambiguous_fields": list(ambiguous_fields),
                "boot_id": self._boot_id,
                "candidate_task_ids": list(candidate_task_ids),
                "generation": self._generation,
                "operation": operation,
                "scope": scope.to_dict(),
                "source_commit_id": source_commit_id,
                "task_set_fingerprint": task_set_fingerprint,
            }
            handle_id = (
                f"clarification.{self._boot_fingerprint}."
                + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
            )
            handle = ClarificationHandle(
                handle_id=handle_id,
                boot_id=self._boot_id,
                generation=self._generation,
                scope=scope,
                source_commit_id=source_commit_id,
                operation=operation,
                ambiguous_fields=ambiguous_fields,
                candidate_task_ids=candidate_task_ids,
                task_set_fingerprint=task_set_fingerprint,
                created_at=now,
                expires_at=now + self._ttl,
            )
            self._entries[handle_id] = _ClarificationEntry(handle)
            return handle

    def consume(
        self, answer: ClarificationAnswer, *, now: datetime
    ) -> ClarificationAnswer:
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
            if (
                answer.generation != handle.generation
                or answer.scope != handle.scope
                or answer.task_set_fingerprint != handle.task_set_fingerprint
                or answer.selected_task_id not in handle.candidate_task_ids
            ):
                raise ValueError("CLARIFICATION_BINDING_CONFLICT")
            if entry.answer is None:
                entry.answer = answer
                return answer
            if entry.answer == answer:
                return entry.answer
            raise ValueError("CLARIFICATION_ALREADY_CONSUMED")

    def restart(self, boot_id: str) -> None:
        _require_text(boot_id, "clarification_boot_id", maximum=128)
        with self._lock:
            self._entries.clear()
            self._boot_id = boot_id
            self._boot_fingerprint = hashlib.sha256(
                boot_id.encode("utf-8")
            ).hexdigest()[:16]
            self._generation = 0

    def _drop_expired(self, now: datetime) -> None:
        expired = [
            handle_id
            for handle_id, entry in self._entries.items()
            if now >= entry.handle.expires_at
        ]
        for handle_id in expired:
            del self._entries[handle_id]


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("AWARE_UTC_TIME_REQUIRED")
    return value.astimezone(UTC)


def _arguments_fingerprint(arguments: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(arguments))).hexdigest()


class ProductionMultiTaskResolver:
    """Resolve an untrusted proposal against exact authenticated Core facts."""

    minimum_confidence = 0.80

    def __init__(
        self, clarification_owner: BoundedClarificationOwner | None = None
    ) -> None:
        self._clarifications = clarification_owner

    def resolve(
        self,
        request: ProductionTaskIntentRequest,
        authority: ProductionTaskAuthorityReader,
    ) -> ProductionTaskResolution:
        proposal = request.proposal
        if not proposal.committed:
            return self._safe(
                "rejected",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "INPUT_NOT_COMMITTED",
            )
        if proposal.confidence < self.minimum_confidence:
            return self._safe(
                "rejected",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_INTENT_LOW_CONFIDENCE",
            )
        if proposal.operation is None:
            if proposal.reason.startswith("REJECTED_"):
                return self._safe(
                    "rejected",
                    None,
                    None,
                    {},
                    "not_applicable",
                    ProductionTaskPolicyOutcome.REJECTED,
                    proposal.reason,
                )
            return self._safe(
                "dialogue",
                None,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.DIALOGUE,
                proposal.reason,
            )
        operation = proposal.operation
        expected_fields = _ARGUMENT_FIELDS[operation]
        if not set(proposal.arguments) <= expected_fields:
            return self._safe(
                "rejected",
                operation,
                None,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_INTENT_ARGUMENT_SCHEMA_MISMATCH",
            )

        visible = authority.list_visible_tasks(request.scope)
        if visible.scope != request.scope:
            return self._safe(
                "rejected",
                operation,
                None,
                proposal.arguments,
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_AUTHORITY_SCOPE_MISMATCH",
            )
        if (
            proposal.interaction_binding is not None
            and proposal.interaction_binding.kind == "clarification"
            and proposal.interaction_binding.task_set_fingerprint != visible.fingerprint
        ):
            return self._safe(
                "rejected",
                operation,
                None,
                proposal.arguments,
                "not_applicable",
                ProductionTaskPolicyOutcome.CONFLICT,
                "CLARIFICATION_TASK_SET_CHANGED",
                visible.fingerprint,
            )
        target, candidates, missing_kind = self._select_target(
            operation, proposal.target, proposal.target_kind, visible
        )
        if operation not in _COLLECTION_OPERATIONS and target is None:
            outcome = (
                ProductionTaskPolicyOutcome.REJECTED
                if missing_kind == "explicit_task_id"
                else ProductionTaskPolicyOutcome.CLARIFICATION
            )
            handle_id = None
            if (
                outcome is ProductionTaskPolicyOutcome.CLARIFICATION
                and self._clarifications is not None
            ):
                handle = self._clarifications.issue(
                    scope=request.scope,
                    source_commit_id=request.committed_source_id,
                    operation=operation,
                    ambiguous_fields=("target",),
                    candidate_task_ids=tuple(task.task_id for task in candidates),
                    task_set_fingerprint=visible.fingerprint,
                    now=datetime.now(UTC),
                )
                handle_id = handle.handle_id
            return ProductionTaskResolution(
                "clarification"
                if outcome is ProductionTaskPolicyOutcome.CLARIFICATION
                else "rejected",
                operation,
                None,
                proposal.arguments,
                "not_applicable",
                outcome,
                "TASK_TARGET_AMBIGUOUS" if candidates else "TASK_TARGET_UNRESOLVED",
                visible.fingerprint,
                candidate_task_ids=tuple(task.task_id for task in candidates),
                clarification_handle_id=handle_id,
            )
        if set(proposal.arguments) != expected_fields:
            return self._safe(
                "rejected",
                operation,
                None if target is None else target.task_id,
                {},
                "not_applicable",
                ProductionTaskPolicyOutcome.REJECTED,
                "TASK_INTENT_ARGUMENT_SCHEMA_MISMATCH",
                visible.fingerprint,
            )

        if proposal.interaction_binding is not None and not self._binding_matches(
            proposal.interaction_binding,
            operation,
            target,
            proposal.arguments,
            visible,
        ):
            bound_target = (
                None
                if proposal.interaction_binding.kind == "clarification"
                else (None if target is None else target.task_id)
            )
            return self._safe(
                "rejected",
                operation,
                bound_target,
                proposal.arguments,
                "not_applicable",
                ProductionTaskPolicyOutcome.CONFLICT,
                "INTERACTION_BINDING_CONFLICT",
                visible.fingerprint,
            )

        reread: AuthenticatedTaskFact | None = None
        if target is not None:
            reread = authority.get_task(request.scope, target.task_id)
            if reread is None or reread.fingerprint != target.fingerprint:
                return self._safe(
                    "task_intent",
                    operation,
                    target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_AUTHORITY_CHANGED",
                    visible.fingerprint,
                )
            status = authority.task_status(request.scope, target.task_id)
            if status is None or status.fingerprint != reread.fingerprint:
                return self._safe(
                    "task_intent",
                    operation,
                    target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_AUTHORITY_CHANGED",
                    visible.fingerprint,
                )
            if (
                proposal.observed_task_generation is not None
                and proposal.observed_task_generation != reread.task_generation
            ):
                return self._safe(
                    "task_intent",
                    operation,
                    target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "TASK_SNAPSHOT_STALE",
                    visible.fingerprint,
                    reread.fingerprint,
                )

        outcome, reason, predecessor_digest = self._state_capability_policy(
            operation, proposal.arguments, reread, request.scope, authority
        )
        confirmation = (
            "required"
            if operation in _MATERIAL_OPERATIONS
            and outcome is ProductionTaskPolicyOutcome.PROPOSED
            else "not_required"
        )
        if outcome is not ProductionTaskPolicyOutcome.PROPOSED:
            confirmation = "not_applicable"
        if proposal.confirmation is not None:
            if not self._confirmation_matches(
                proposal.confirmation,
                operation,
                None if target is None else target.task_id,
                proposal.arguments,
                visible.fingerprint,
            ):
                return self._safe(
                    "rejected",
                    operation,
                    None if target is None else target.task_id,
                    proposal.arguments,
                    "not_applicable",
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "CONFIRMATION_BINDING_CONFLICT",
                    visible.fingerprint,
                    None if reread is None else reread.fingerprint,
                )
            confirmation = "confirmed"
        return ProductionTaskResolution.task_intent(
            operation=operation,
            target_task_id=None if target is None else target.task_id,
            arguments=proposal.arguments,
            confirmation=confirmation,
            outcome=outcome,
            task_set_fingerprint=visible.fingerprint,
            authority_fingerprint=None if reread is None else reread.fingerprint,
            reason=reason,
            predecessor_result_digest=predecessor_digest,
        )

    @staticmethod
    def _select_target(
        operation: str,
        target: str | None,
        target_kind: str | None,
        visible: TaskAuthorityRead,
    ) -> tuple[AuthenticatedTaskFact | None, tuple[AuthenticatedTaskFact, ...], str]:
        if operation in _COLLECTION_OPERATIONS:
            return None, (), "collection"
        if target is None or target.casefold() in {"current", "recent", "latest"}:
            return None, (), "hint_only"
        if target_kind == "hint":
            return None, (), "hint_only"
        ids = tuple(task for task in visible.tasks if task.task_id == target)
        if target_kind == "task_id":
            return (
                (ids[0], ids, "explicit_task_id")
                if ids
                else (
                    None,
                    (),
                    "explicit_task_id",
                )
            )
        if ids:
            return ids[0], ids, "explicit_task_id"
        refs = tuple(task for task in visible.tasks if task.stable_reference == target)
        if target_kind == "stable_reference":
            return (
                (refs[0], refs, "stable_reference")
                if refs
                else (
                    None,
                    (),
                    "zero_candidate",
                )
            )
        if refs:
            return refs[0], refs, "stable_reference"
        names = tuple(task for task in visible.tasks if task.name == target)
        if len(names) == 1:
            return names[0], names, "unique_name"
        if len(names) > 1:
            return None, names, "duplicate_name"
        return None, (), "zero_candidate"

    @staticmethod
    def _state_capability_policy(
        operation: str,
        arguments: Mapping[str, object],
        task: AuthenticatedTaskFact | None,
        scope: ScopeRef,
        authority: ProductionTaskAuthorityReader,
    ) -> tuple[ProductionTaskPolicyOutcome, str, str | None]:
        if operation in FORMAL_TASK_QUERY_OPERATIONS:
            if operation == "task.events" and task is not None:
                if authority.event_head(scope, task.task_id) != (
                    task.event_head,
                    task.event_head_id,
                ):
                    return (
                        ProductionTaskPolicyOutcome.CONFLICT,
                        "TASK_EVENT_HEAD_CHANGED",
                        None,
                    )
            elif operation == "task.result" and task is not None:
                digest = authority.result_digest(scope, task.task_id)
                authority.unread_head(scope, task.task_id)
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
        assert task is not None
        if task.terminal and operation != "task.create_successor":
            return ProductionTaskPolicyOutcome.CONFLICT, "TERMINAL_TASK_IMMUTABLE", None
        if operation == "task.create_successor":
            digest = authority.result_digest(scope, task.task_id)
            if (
                task.state == "unknown"
                or not task.terminal
                or digest is None
                or digest != task.result_digest
            ):
                return (
                    ProductionTaskPolicyOutcome.CONFLICT,
                    "SUCCESSOR_PREDECESSOR_CONFLICT",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.PROPOSED,
                "SUCCESSOR_POLICY_ACCEPTED",
                digest,
            )
        if operation == "task.update":
            if (
                task.state != "accepted"
                or task.attempt_state != "accepted"
                or not task.dispatch_unclaimed
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
            if (
                task.state != "running"
                or "task.adjust" not in task.supported_operations
            ):
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
        if operation == "task.reprioritize":
            if (
                task.state == "accepted"
                and task.dispatch_unclaimed
                and "task.reprioritize" in task.supported_operations
            ):
                return (
                    ProductionTaskPolicyOutcome.PROPOSED,
                    "TASK_REPRIORITIZE_POLICY_ACCEPTED",
                    None,
                )
            return (
                ProductionTaskPolicyOutcome.UNSUPPORTED,
                "TASK_REPRIORITIZE_UNSUPPORTED",
                None,
            )
        if operation in _UNSUPPORTED_WITHOUT_PRIMITIVE:
            return (
                ProductionTaskPolicyOutcome.UNSUPPORTED,
                "TASK_CONTROL_UNSUPPORTED",
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
    def _binding_matches(
        binding: ProductionInteractionBinding,
        operation: str,
        target: AuthenticatedTaskFact | None,
        arguments: Mapping[str, object],
        visible: TaskAuthorityRead,
    ) -> bool:
        return (
            binding.operation == operation
            and binding.target_task_id == (None if target is None else target.task_id)
            and dict(binding.arguments) == dict(arguments)
            and binding.task_set_fingerprint == visible.fingerprint
            and set(binding.candidate_task_ids)
            <= {task.task_id for task in visible.tasks}
            and (target is None or target.task_id in set(binding.candidate_task_ids))
        )

    @staticmethod
    def _confirmation_matches(
        confirmation: ProductionConfirmationFact,
        operation: str,
        target_task_id: str | None,
        arguments: Mapping[str, object],
        task_set_fingerprint: str,
    ) -> bool:
        return (
            not confirmation.consumed
            and confirmation.operation == operation
            and confirmation.target_task_id == target_task_id
            and confirmation.arguments_sha256 == _arguments_fingerprint(arguments)
            and confirmation.task_set_fingerprint == task_set_fingerprint
        )

    @staticmethod
    def _safe(
        classification: str,
        operation: str | None,
        target_task_id: str | None,
        arguments: Mapping[str, object],
        confirmation: str,
        outcome: ProductionTaskPolicyOutcome,
        reason: str,
        task_set_fingerprint: str | None = None,
        authority_fingerprint: str | None = None,
    ) -> ProductionTaskResolution:
        return ProductionTaskResolution(
            classification,
            operation,
            target_task_id,
            arguments,
            confirmation,
            outcome,
            reason,
            task_set_fingerprint,
            authority_fingerprint,
        )


__all__ = [
    "AuthenticatedTaskFact",
    "BoundedClarificationOwner",
    "ClarificationAnswer",
    "ClarificationHandle",
    "ProductionConfirmationFact",
    "ProductionInteractionBinding",
    "ProductionIntentOrigin",
    "ProductionMultiTaskResolver",
    "ProductionTaskAuthorityReader",
    "ProductionTaskIntentProposal",
    "ProductionTaskIntentRequest",
    "ProductionTaskPolicyOutcome",
    "ProductionTaskResolution",
    "TaskAuthorityRead",
]
