# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure critical-kernel primitives for ``live-voice.contract.v2``."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from openjiuwen.core.application.tasks.contracts import (
    Assurance as Assurance,
    CONTRACT_VERSION as CONTRACT_VERSION,
    CancelScope as CancelScope,
    CommandEnvelope as CommandEnvelope,
    ConnectionEpochRef as ConnectionEpochRef,
    ContextRedaction as ContextRedaction,
    ContextRef as ContextRef,
    ContextRevision as ContextRevision,
    ContextRevisionKind as ContextRevisionKind,
    ContractError as ContractError,
    ContractViolation as ContractViolation,
    ErrorCode as ErrorCode,
    FrozenJson as FrozenJson,
    IdentityKind as IdentityKind,
    IdentityRef as IdentityRef,
    Knowledge as Knowledge,
    KnownFact as KnownFact,
    LifecycleKind as LifecycleKind,
    MAX_SAFE_INTEGER as MAX_SAFE_INTEGER,
    OriginRef as OriginRef,
    QueryEnvelope as QueryEnvelope,
    ResultEnvelope as ResultEnvelope,
    ScopeRef as ScopeRef,
    SideEffectTarget as SideEffectTarget,
    Speakability as Speakability,
    TerminalOutcome as TerminalOutcome,
    WorkProgressEventV2 as WorkProgressEventV2,
    WorkProgressSource as WorkProgressSource,
    WorkSourceAuthority as WorkSourceAuthority,
    WorkState as WorkState,
    WorkUrgency as WorkUrgency,
    _COMMAND_DISPOSITIONS as _COMMAND_DISPOSITIONS,
    _COMMAND_DISPOSITION_ERROR_CODES as _COMMAND_DISPOSITION_ERROR_CODES,
    _COMMAND_TARGETS as _COMMAND_TARGETS,
    _CONTEXT_WHITESPACE as _CONTEXT_WHITESPACE,
    _CORE_CAPABILITIES as _CORE_CAPABILITIES,
    _EnumT as _EnumT,
    _FactT as _FactT,
    _FrozenArray as _FrozenArray,
    _FrozenObject as _FrozenObject,
    _LIFECYCLE_TRANSITIONS as _LIFECYCLE_TRANSITIONS,
    _LOWER_SHA256_RE as _LOWER_SHA256_RE,
    _NAMESPACE_RE as _NAMESPACE_RE,
    _POSITIVE_COMMAND_DISPOSITIONS as _POSITIVE_COMMAND_DISPOSITIONS,
    _PRESENTATION_CLASSES as _PRESENTATION_CLASSES,
    _QUERY_TARGETS as _QUERY_TARGETS,
    _REASON_RE as _REASON_RE,
    _TASK_PRIORITIES as _TASK_PRIORITIES,
    _TASK_SIDE_EFFECT_CLASSES as _TASK_SIDE_EFFECT_CLASSES,
    _URI_SCHEME_RE as _URI_SCHEME_RE,
    _UTC_RE as _UTC_RE,
    _ValueT as _ValueT,
    _WAVE2_COMMAND_TYPES as _WAVE2_COMMAND_TYPES,
    _bool as _bool,
    _bounded_text as _bounded_text,
    _canonical_frozen as _canonical_frozen,
    _canonical_number as _canonical_number,
    _capability_list as _capability_list,
    _closed_string_map as _closed_string_map,
    _closed_value as _closed_value,
    _command_payload as _command_payload,
    _constraint_list as _constraint_list,
    _context_refs as _context_refs,
    _context_required_text as _context_required_text,
    _context_uri as _context_uri,
    _enum as _enum,
    _extensions as _extensions,
    _fact_text as _fact_text,
    _freeze_json as _freeze_json,
    _freeze_object as _freeze_object,
    _known_fact as _known_fact,
    _namespaced as _namespaced,
    _optional_bounded_text as _optional_bounded_text,
    _optional_id as _optional_id,
    _optional_stable_reason as _optional_stable_reason,
    _query_payload as _query_payload,
    _require_exact_keys as _require_exact_keys,
    _require_operation_capability as _require_operation_capability,
    _required_text as _required_text,
    _result_extensions as _result_extensions,
    _strict_array as _strict_array,
    _strict_object as _strict_object,
    _successor_outcome_and_digest as _successor_outcome_and_digest,
    _thaw_json as _thaw_json,
    _thaw_object as _thaw_object,
    _timestamp as _timestamp,
    _uint as _uint,
    _validate_unicode as _validate_unicode,
    _violation as _violation,
    canonical_json as canonical_json,
    canonical_json_bytes as canonical_json_bytes,
    validate_transition as validate_transition,
)


V1_CONTRACT_VERSION: Final = "live-voice.contract.v1"


class InputCommitState(StrEnum):
    PARTIAL = "partial"
    UNCOMMITTED = "uncommitted"
    COMMITTED = "committed"


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class EventApplyStatus(StrEnum):
    APPLIED = "applied"
    DUPLICATE_APPLIED = "duplicate_applied"
    QUARANTINED_GAP = "quarantined_gap"
    QUARANTINED_CAUSATION = "quarantined_causation"
    QUARANTINED_PROJECTION = "quarantined_projection"
    DUPLICATE_QUARANTINED = "duplicate_quarantined"
    REJECTED_CONFLICT = "rejected_conflict"
    REJECTED_CAUSATION = "rejected_causation"
    REJECTED_PROJECTION = "rejected_projection"
    REJECTED_LIFECYCLE = "rejected_lifecycle"


@dataclass(frozen=True, slots=True)
class ProducerRef:
    component: str
    instance_id: str
    authority: str

    @classmethod
    def from_dict(cls, payload: object) -> ProducerRef:
        data = _strict_object(payload, field_name="producer")
        _require_exact_keys(
            data,
            required={"component", "instance_id", "authority"},
            field_name="producer",
        )
        return cls(
            component=_required_text(data["component"], "producer.component"),
            instance_id=_required_text(data["instance_id"], "producer.instance_id"),
            authority=_required_text(data["authority"], "producer.authority"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "component": self.component,
            "instance_id": self.instance_id,
            "authority": self.authority,
        }


@dataclass(frozen=True, slots=True)
class _EventRule:
    stream_kind: IdentityKind | tuple[IdentityKind, ...]
    authority: str
    state: str | None = None
    terminal: bool = False
    adapter: bool = False
    lifecycle: bool = True
    progress: bool = False


_EVENT_RULES: Final = MappingProxyType(
    {
        "interaction.opened": _EventRule(
            IdentityKind.INTERACTION, "conversation_runtime", "open"
        ),
        "interaction.closing": _EventRule(
            IdentityKind.INTERACTION, "conversation_runtime", "closing"
        ),
        "interaction.closed": _EventRule(
            IdentityKind.INTERACTION, "conversation_runtime", "closed"
        ),
        "turn.capturing": _EventRule(
            IdentityKind.TURN, "conversation_runtime", "capturing"
        ),
        "turn.committed": _EventRule(
            IdentityKind.TURN, "conversation_runtime", "committed"
        ),
        "turn.cancelled": _EventRule(
            IdentityKind.TURN, "conversation_runtime", "cancelled"
        ),
        "response.accepted": _EventRule(
            IdentityKind.RESPONSE, "conversation_runtime", "accepted"
        ),
        "response.generating": _EventRule(
            IdentityKind.RESPONSE, "conversation_runtime", "generating"
        ),
        "response.speaking": _EventRule(
            IdentityKind.RESPONSE, "conversation_runtime", "speaking"
        ),
        "response.terminal": _EventRule(
            IdentityKind.RESPONSE,
            "conversation_runtime",
            "terminal",
            terminal=True,
        ),
        "round.accepted": _EventRule(IdentityKind.ROUND, "harness", "accepted"),
        "round.running": _EventRule(IdentityKind.ROUND, "harness", "running"),
        "round.blocked": _EventRule(IdentityKind.ROUND, "harness", "blocked"),
        "round.decision_required": _EventRule(
            IdentityKind.ROUND, "harness", "decision_required"
        ),
        "round.terminal": _EventRule(
            IdentityKind.ROUND, "harness", "terminal", terminal=True
        ),
        "task.accepted": _EventRule(IdentityKind.TASK, "task_core", "accepted"),
        "task.retry_accepted": _EventRule(IdentityKind.TASK, "task_core", "accepted"),
        "task.recovery_accepted": _EventRule(
            IdentityKind.TASK, "task_core", "accepted"
        ),
        "task.running": _EventRule(IdentityKind.TASK, "task_core", "running"),
        "task.blocked": _EventRule(IdentityKind.TASK, "task_core", "blocked"),
        "task.decision_required": _EventRule(
            IdentityKind.TASK, "task_core", "decision_required"
        ),
        "task.terminal": _EventRule(
            IdentityKind.TASK, "task_core", "terminal", terminal=True
        ),
        "attempt.accepted": _EventRule(IdentityKind.ATTEMPT, "executor", "accepted"),
        "attempt.running": _EventRule(IdentityKind.ATTEMPT, "executor", "running"),
        "attempt.terminal": _EventRule(
            IdentityKind.ATTEMPT, "executor", "terminal", terminal=True
        ),
        "adapter.observed": _EventRule(IdentityKind.EVENT, "adapter", adapter=True),
        "work.progress": _EventRule(
            (IdentityKind.ROUND, IdentityKind.TASK),
            "adapter",
            adapter=True,
            lifecycle=False,
            progress=True,
        ),
    }
)


def _validate_event_payload(
    event_type: str, data: Mapping[str, object], rule: _EventRule
) -> _FrozenObject:
    if rule.progress:
        progress = WorkProgressEventV2.from_dict(dict(data))
        return _freeze_object(progress.to_dict(), "event.payload")
    if rule.adapter:
        _require_exact_keys(
            data,
            required={"source_event_type"},
            field_name="event.payload",
        )
        _namespaced(data["source_event_type"], "event.payload.source_event_type")
        return _freeze_object(dict(data), "event.payload")
    required = {"state", "outcome"} if rule.terminal else {"state"}
    if event_type == "task.retry_accepted":
        required = {
            "state",
            "command_id",
            "retry_of_attempt_id",
            "previous_outcome",
            "attempt_number",
        }
    elif event_type == "task.recovery_accepted":
        required = {
            "state",
            "recovery_id",
            "producer_attempt_id",
            "producer_outcome",
            "recovery_generation",
            "recovery_budget_remaining",
            "attempt_number",
        }
    _require_exact_keys(data, required=required, field_name="event.payload")
    if data["state"] != rule.state:
        raise _violation(
            "EVENT_STATE_MISMATCH",
            f"{event_type} requires payload.state={rule.state!r}",
        )
    if rule.terminal:
        _enum(TerminalOutcome, data["outcome"], "event.payload.outcome")
    elif event_type == "task.retry_accepted":
        _required_text(data["command_id"], "event.payload.command_id")
        _required_text(data["retry_of_attempt_id"], "event.payload.retry_of_attempt_id")
        outcome = _enum(
            TerminalOutcome,
            data["previous_outcome"],
            "event.payload.previous_outcome",
        )
        if outcome not in {TerminalOutcome.CANCELLED, TerminalOutcome.COMPLETED}:
            raise _violation(
                "TASK_RETRY_OUTCOME_NOT_ELIGIBLE",
                "task.retry_accepted permits only cancelled or completed predecessors",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
        attempt_number = _uint(data["attempt_number"], "event.payload.attempt_number")
        if attempt_number not in {2, 3}:
            raise _violation(
                "TASK_RETRY_ATTEMPT_NUMBER_INVALID",
                "task.retry_accepted attempt_number must be 2 or 3",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
    elif event_type == "task.recovery_accepted":
        _required_text(data["recovery_id"], "event.payload.recovery_id")
        _required_text(
            data["producer_attempt_id"],
            "event.payload.producer_attempt_id",
        )
        outcome = _enum(
            TerminalOutcome,
            data["producer_outcome"],
            "event.payload.producer_outcome",
        )
        attempt_number = _uint(
            data["attempt_number"],
            "event.payload.attempt_number",
        )
        recovery_generation = _uint(
            data["recovery_generation"],
            "event.payload.recovery_generation",
        )
        recovery_budget_remaining = _uint(
            data["recovery_budget_remaining"],
            "event.payload.recovery_budget_remaining",
        )
        if (
            outcome is not TerminalOutcome.INTERRUPTED
            or attempt_number not in {2, 3}
            or recovery_generation != attempt_number - 1
            or recovery_budget_remaining != 3 - attempt_number
        ):
            raise _violation(
                "TASK_RECOVERY_EPOCH_INVALID",
                "task.recovery_accepted must bind one interrupted recovery epoch",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
    return _freeze_object(dict(data), "event.payload")


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    producer: ProducerRef
    stream_ref: IdentityRef
    seq: int
    occurred_at: str
    scope: ScopeRef
    correlation_id: str
    causation_id: str | None
    required_capabilities: tuple[str, ...]
    _payload: _FrozenObject = field(repr=False)
    _extensions: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def payload(self) -> dict[str, object]:
        return _thaw_object(self._payload)

    @property
    def extensions(self) -> dict[str, object]:
        return _thaw_object(self._extensions)

    @property
    def stream_key(self) -> tuple[str, str, IdentityKind, str]:
        return (
            self.producer.component,
            self.producer.instance_id,
            self.stream_ref.kind,
            self.stream_ref.id,
        )

    @property
    def progress_source_key(self) -> tuple[ScopeRef, IdentityKind, str]:
        """Logical source identity that survives an authority instance restart."""

        return (self.scope, self.stream_ref.kind, self.stream_ref.id)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        identities: IdentityRegistry | None = None,
    ) -> EventEnvelope:
        data = _strict_object(payload, field_name="event")
        _require_exact_keys(
            data,
            required={
                "contract_version",
                "event_id",
                "event_type",
                "producer",
                "stream_ref",
                "seq",
                "occurred_at",
                "scope",
                "correlation_id",
                "causation_id",
                "required_capabilities",
                "payload",
                "extensions",
            },
            field_name="event",
        )
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        event_type = _namespaced(data["event_type"], "event.event_type")
        rule = _EVENT_RULES.get(event_type)
        if rule is None:
            raise _violation(
                "UNKNOWN_EVENT_TYPE",
                f"unknown event type {event_type!r}",
                code=ErrorCode.UNSUPPORTED,
            )
        producer = ProducerRef.from_dict(data["producer"])
        if producer.authority != rule.authority:
            raise _violation(
                "EVENT_AUTHORITY_MISMATCH",
                f"{event_type} requires authority {rule.authority!r}",
                code=ErrorCode.PERMISSION_DENIED,
            )
        stream_ref = IdentityRef.from_dict(data["stream_ref"])
        allowed_stream_kinds = (
            rule.stream_kind
            if isinstance(rule.stream_kind, tuple)
            else (rule.stream_kind,)
        )
        if stream_ref.kind not in allowed_stream_kinds:
            expected = ", ".join(kind.value for kind in allowed_stream_kinds)
            raise _violation(
                "IDENTITY_KIND_MISMATCH",
                f"expected one of {expected}, got {stream_ref.kind.value}",
            )
        causation_id = _optional_id(data["causation_id"], "event.causation_id")
        if rule.adapter and causation_id is None:
            raise _violation(
                "ADAPTER_CAUSATION_REQUIRED",
                "adapter events must reference their authoritative source event",
            )
        scope = ScopeRef.from_dict(data["scope"])
        event_payload = _strict_object(data["payload"], field_name="event.payload")
        result = cls(
            event_id=_required_text(data["event_id"], "event.event_id"),
            event_type=event_type,
            producer=producer,
            stream_ref=stream_ref,
            seq=_uint(data["seq"], "event.seq"),
            occurred_at=_timestamp(data["occurred_at"], "event.occurred_at"),
            scope=scope,
            correlation_id=_required_text(
                data["correlation_id"], "event.correlation_id"
            ),
            causation_id=causation_id,
            required_capabilities=_capability_list(
                data["required_capabilities"], "event.required_capabilities"
            ),
            _payload=_validate_event_payload(event_type, event_payload, rule),
            _extensions=_extensions(data["extensions"], "event.extensions"),
        )
        if event_type == "task.retry_accepted" and (
            causation_id is None or result.payload["command_id"] != causation_id
        ):
            raise _violation(
                "TASK_RETRY_CAUSATION_MISMATCH",
                "task.retry_accepted command_id must equal its causation_id",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
        if event_type == "task.recovery_accepted" and (
            causation_id is None or result.payload["recovery_id"] != causation_id
        ):
            raise _violation(
                "TASK_RECOVERY_CAUSATION_MISMATCH",
                "task.recovery_accepted recovery_id must equal its causation_id",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
        if rule.progress:
            progress = WorkProgressEventV2.from_dict(
                result.payload, scope=scope, identities=identities
            )
            if (
                progress.source.source_work_ref.kind is IdentityKind.ATTEMPT
                and identities is None
            ):
                raise _violation(
                    "PROGRESS_ATTEMPT_PARENT_UNVERIFIED",
                    "attempt-to-task WorkProgress requires an IdentityRegistry parent binding",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            if progress.work_ref != stream_ref:
                raise _violation(
                    "PROGRESS_ENVELOPE_MISMATCH",
                    "work.progress stream_ref must match its projection work_ref",
                )
            if progress.source.event_id != causation_id:
                raise _violation(
                    "PROGRESS_CAUSATION_MISMATCH",
                    "work.progress causation_id must equal source.event_id",
                )
        if identities is not None:
            identities.require(stream_ref, scope=scope)
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "producer": self.producer.to_dict(),
            "stream_ref": self.stream_ref.to_dict(),
            "seq": self.seq,
            "occurred_at": self.occurred_at,
            "scope": self.scope.to_dict(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "required_capabilities": list(self.required_capabilities),
            "payload": self.payload,
            "extensions": self.extensions,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    component: str
    contract_major: str
    supported_operations: tuple[str, ...]
    supported_event_types: tuple[str, ...]
    batch_modes: tuple[str, ...]
    stream_modes: tuple[str, ...]
    supports_cancel_ack: bool
    supports_replay: bool
    _declared_limits: _FrozenObject = field(repr=False)
    fallback_identity: str | None
    availability: Availability

    @property
    def declared_limits(self) -> dict[str, object]:
        return _thaw_object(self._declared_limits)

    @staticmethod
    def _unique_namespaced(value: object, field_name: str) -> tuple[str, ...]:
        items = _strict_array(value, field_name=field_name)
        parsed = tuple(
            _namespaced(item, f"{field_name}[{index}]")
            for index, item in enumerate(items)
        )
        if len(parsed) != len(set(parsed)):
            raise _violation("DUPLICATE_CAPABILITY", f"{field_name} has duplicates")
        return parsed

    @staticmethod
    def _unique_modes(
        value: object, field_name: str, allowed: frozenset[str]
    ) -> tuple[str, ...]:
        items = _strict_array(value, field_name=field_name)
        parsed: list[str] = []
        for index, item in enumerate(items):
            mode = _required_text(item, f"{field_name}[{index}]")
            if mode not in allowed:
                raise _violation("INVALID_CAPABILITY_MODE", f"unknown mode {mode!r}")
            if mode in parsed:
                raise _violation(
                    "DUPLICATE_CAPABILITY_MODE", f"duplicate mode {mode!r}"
                )
            parsed.append(mode)
        return tuple(parsed)

    @classmethod
    def from_dict(cls, payload: object) -> CapabilityDescriptor:
        data = _strict_object(payload, field_name="capability")
        _require_exact_keys(
            data,
            required={
                "component",
                "contract_major",
                "supported_operations",
                "supported_event_types",
                "batch_modes",
                "stream_modes",
                "supports_cancel_ack",
                "supports_replay",
                "declared_limits",
                "fallback_identity",
                "availability",
            },
            field_name="capability",
        )
        if data["contract_major"] != "v2":
            raise _violation(
                "UNSUPPORTED_CONTRACT_MAJOR",
                "capability.contract_major must be 'v2'",
                code=ErrorCode.UNSUPPORTED,
            )
        return cls(
            component=_required_text(data["component"], "capability.component"),
            contract_major="v2",
            supported_operations=cls._unique_namespaced(
                data["supported_operations"], "capability.supported_operations"
            ),
            supported_event_types=cls._unique_namespaced(
                data["supported_event_types"], "capability.supported_event_types"
            ),
            batch_modes=cls._unique_modes(
                data["batch_modes"],
                "capability.batch_modes",
                frozenset({"batch"}),
            ),
            stream_modes=cls._unique_modes(
                data["stream_modes"],
                "capability.stream_modes",
                frozenset({"stream"}),
            ),
            supports_cancel_ack=_bool(
                data["supports_cancel_ack"], "capability.supports_cancel_ack"
            ),
            supports_replay=_bool(
                data["supports_replay"], "capability.supports_replay"
            ),
            _declared_limits=_freeze_object(
                data["declared_limits"], "capability.declared_limits"
            ),
            fallback_identity=_optional_id(
                data["fallback_identity"], "capability.fallback_identity"
            ),
            availability=_enum(
                Availability, data["availability"], "capability.availability"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "component": self.component,
            "contract_major": self.contract_major,
            "supported_operations": list(self.supported_operations),
            "supported_event_types": list(self.supported_event_types),
            "batch_modes": list(self.batch_modes),
            "stream_modes": list(self.stream_modes),
            "supports_cancel_ack": self.supports_cancel_ack,
            "supports_replay": self.supports_replay,
            "declared_limits": self.declared_limits,
            "fallback_identity": self.fallback_identity,
            "availability": self.availability.value,
        }


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._descriptors: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        with self._lock:
            existing = self._descriptors.get(descriptor.component)
            if existing is not None and existing != descriptor:
                raise _violation(
                    "CAPABILITY_DESCRIPTOR_CONFLICT",
                    f"component {descriptor.component!r} changed descriptor",
                    code=ErrorCode.CONFLICT,
                )
            self._descriptors[descriptor.component] = descriptor

    def require(self, component: str, operation: str) -> None:
        parsed_component = _required_text(component, "capability.component")
        parsed_operation = _namespaced(operation, "capability.operation")
        with self._lock:
            descriptor = self._descriptors.get(parsed_component)
            if (
                descriptor is None
                or parsed_operation not in descriptor.supported_operations
            ):
                raise _violation(
                    "CAPABILITY_UNSUPPORTED",
                    f"{parsed_component!r} does not support {parsed_operation!r}",
                    code=ErrorCode.UNSUPPORTED,
                )
            if descriptor.availability is Availability.UNAVAILABLE:
                raise _violation(
                    "CAPABILITY_TEMPORARILY_UNAVAILABLE",
                    f"{parsed_component!r} is temporarily unavailable",
                    code=ErrorCode.UNAVAILABLE,
                )


def dispatch_committed_input(
    state: InputCommitState | str,
    target: SideEffectTarget | str,
    effect: Callable[[], _ValueT],
) -> _ValueT:
    commit_state = _enum(InputCommitState, state, "input.state")
    _enum(SideEffectTarget, target, "input.target")
    if commit_state is not InputCommitState.COMMITTED:
        raise _violation(
            "INPUT_NOT_COMMITTED",
            "partial or uncommitted input cannot invoke Agent, Tool, or Task",
            code=ErrorCode.PERMISSION_DENIED,
        )
    return effect()


@dataclass(frozen=True, slots=True)
class ResponseRef:
    interaction_id: str
    response_id: str
    response_generation: int

    def __post_init__(self) -> None:
        _required_text(self.interaction_id, "response_ref.interaction_id")
        _required_text(self.response_id, "response_ref.response_id")
        _uint(self.response_generation, "response_ref.response_generation")


@dataclass(slots=True)
class _ResponseState:
    ref: ResponseRef
    fenced: bool = False
    terminal: bool = False


class ResponseFence:
    """Accepts effects only for the exact active response tuple."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_interaction: dict[str, _ResponseState] = {}
        self._seen_ids: set[str] = set()
        self._last_generation: dict[str, int] = {}

    def begin(self, ref: ResponseRef) -> None:
        with self._lock:
            last = self._last_generation.get(ref.interaction_id, -1)
            if ref.response_id in self._seen_ids:
                raise _violation(
                    "RESPONSE_ID_REUSED",
                    "every replacement response requires a new response_id",
                    code=ErrorCode.CONFLICT,
                )
            if ref.response_generation <= last:
                raise _violation(
                    "RESPONSE_GENERATION_NOT_INCREASING",
                    "response_generation must strictly increase per interaction",
                    code=ErrorCode.STALE,
                )
            prior = self._by_interaction.get(ref.interaction_id)
            if prior is not None:
                prior.fenced = True
            self._seen_ids.add(ref.response_id)
            self._last_generation[ref.interaction_id] = ref.response_generation
            self._by_interaction[ref.interaction_id] = _ResponseState(ref)

    def cancel(self, ref: ResponseRef) -> None:
        with self._lock:
            state = self._require_exact(ref)
            state.fenced = True

    def terminal(self, ref: ResponseRef) -> None:
        with self._lock:
            state = self._require_exact(ref)
            state.fenced = True
            state.terminal = True

    def apply_if_current(
        self, ref: ResponseRef, effect: Callable[[], _ValueT]
    ) -> _ValueT:
        with self._lock:
            state = self._by_interaction.get(ref.interaction_id)
            if state is None or state.ref != ref or state.fenced or state.terminal:
                raise _violation(
                    "STALE_RESPONSE_OUTPUT",
                    "output does not match the exact active response tuple",
                    code=ErrorCode.STALE,
                )
            return effect()

    def _require_exact(self, ref: ResponseRef) -> _ResponseState:
        state = self._by_interaction.get(ref.interaction_id)
        if state is None or state.ref != ref:
            raise _violation(
                "STALE_RESPONSE_REFERENCE",
                "operation does not match the exact active response tuple",
                code=ErrorCode.STALE,
            )
        return state


def default_barge_in_scopes(
    *, cancel_response: bool = False
) -> tuple[CancelScope, ...]:
    cancel_response = _bool(cancel_response, "barge_in.cancel_response")
    scopes = [CancelScope.PLAYBACK_STOP]
    if cancel_response:
        scopes.append(CancelScope.RESPONSE_CANCEL)
    return tuple(scopes)


def dispatch_cancel(
    command: CommandEnvelope,
    handlers: Mapping[CancelScope, Callable[[CommandEnvelope], _ValueT]],
) -> _ValueT:
    try:
        scope = CancelScope(command.command_type)
    except ValueError as error:
        raise _violation(
            "NOT_A_CANCEL_COMMAND", "command is not an explicit cancel operation"
        ) from error
    handler = handlers.get(scope)
    if handler is None:
        raise _violation(
            "CANCEL_HANDLER_UNAVAILABLE",
            f"no handler is available for {scope.value}",
            code=ErrorCode.CAPABILITY_UNAVAILABLE,
        )
    return handler(command)


@dataclass(slots=True)
class _CommandExecution:
    fingerprint: bytes
    result: ResultEnvelope | None = None
    pending: bool = True


class CommandResultLedger:
    """Thread-safe command idempotency with cached owner-bound results."""

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._entries: dict[str, _CommandExecution] = {}

    def execute(
        self,
        command: CommandEnvelope,
        *,
        observed_at: str,
        handler: Callable[[CommandEnvelope], ResultEnvelope],
    ) -> ResultEnvelope:
        observed_at = _timestamp(observed_at, "result.observed_at")
        fingerprint = command.fingerprint()
        with self._condition:
            entry = self._entries.get(command.command_id)
            if entry is not None and entry.fingerprint != fingerprint:
                return ResultEnvelope.failure(
                    owner=command,
                    error=ContractError(
                        code=ErrorCode.CONFLICT,
                        reason="IDEMPOTENCY_CONFLICT",
                        message="command_id was reused with different content",
                        retriable=False,
                        correlation_id=command.correlation_id,
                        _details=_freeze_object({}, "error.details"),
                    ),
                    observed_at=observed_at,
                )
            if entry is not None:
                while entry.pending:
                    self._condition.wait()
                assert entry.result is not None
                return entry.result.for_request(command.request_id)
            entry = _CommandExecution(fingerprint=fingerprint)
            self._entries[command.command_id] = entry

        try:
            result = handler(command)
            ResultEnvelope.from_dict(result.to_dict(), owner=command)
        except ContractViolation as error:
            result = ResultEnvelope.failure(
                owner=command, error=error.error, observed_at=observed_at
            )
        except Exception:
            result = ResultEnvelope.failure(
                owner=command,
                error=ContractError(
                    code=ErrorCode.INTERNAL,
                    reason="COMMAND_HANDLER_FAILED",
                    message="command handler failed",
                    retriable=False,
                    correlation_id=command.correlation_id,
                    _details=_freeze_object({}, "error.details"),
                ),
                observed_at=observed_at,
            )
        with self._condition:
            entry.result = result
            entry.pending = False
            self._condition.notify_all()
        return result


@dataclass(frozen=True, slots=True)
class EventApplyResult:
    status: EventApplyStatus
    error: ContractError | None = None
    applied_event_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class _EventStreamState:
    next_seq: int = 0
    applied_by_seq: dict[int, EventEnvelope] = field(default_factory=dict)
    quarantined_by_seq: dict[int, EventEnvelope] = field(default_factory=dict)
    poisoned_seq: set[int] = field(default_factory=set)


_INITIAL_LIFECYCLE_STATES: Final = MappingProxyType(
    {
        IdentityKind.INTERACTION: "open",
        IdentityKind.TURN: "capturing",
        IdentityKind.RESPONSE: "accepted",
        IdentityKind.ROUND: "accepted",
        IdentityKind.TASK: "accepted",
        IdentityKind.ATTEMPT: "accepted",
    }
)
_PROJECTION_ERROR_REASONS: Final = frozenset(
    {
        "PROGRESS_SEQUENCE_GAP",
        "PROGRESS_SEQUENCE_REUSED",
        "PROGRESS_SOURCE_ALREADY_PROJECTED",
        "PROGRESS_SOURCE_ORDER_MISMATCH",
        "PROGRESS_DETAIL_UNPROVEN",
    }
)


class EventSequenceTracker:
    """Orders producer streams and resolves only applied causal ancestry."""

    def __init__(self, identities: IdentityRegistry | None = None) -> None:
        self._lock = threading.RLock()
        self._identities = identities
        self._streams: dict[tuple[str, str, IdentityKind, str], _EventStreamState] = {}
        self._events: dict[str, EventEnvelope] = {}
        self._results: dict[str, EventApplyResult] = {}
        self._applied_ids: set[str] = set()
        self._external_causes: dict[str, CommandEnvelope] = {}
        self._lifecycle_by_object: dict[tuple[IdentityKind, str], str] = {}
        self._task_attempt_number_by_object: dict[tuple[IdentityKind, str], int] = {}
        self._task_terminal_outcome_by_object: dict[tuple[IdentityKind, str], str] = {}
        self._scope_by_object: dict[tuple[IdentityKind, str], ScopeRef] = {}
        self._next_progress_seq: dict[tuple[ScopeRef, IdentityKind, str], int] = {}
        self._progress_source_queues: dict[
            tuple[ScopeRef, IdentityKind, str], deque[str]
        ] = {}
        self._projected_sources: set[str] = set()

    def register_applied_cause(self, command: CommandEnvelope) -> tuple[str, ...]:
        with self._lock:
            normalized = CommandEnvelope.from_dict(command.to_dict())
            cause_id = normalized.command_id
            if cause_id in self._events:
                raise _violation(
                    "CAUSATION_ID_KIND_CONFLICT",
                    "an event_id cannot also be an external command cause",
                    code=ErrorCode.PROTOCOL_VIOLATION,
                )
            existing = self._external_causes.get(cause_id)
            if (
                existing is not None
                and existing.fingerprint() != normalized.fingerprint()
            ):
                raise _violation(
                    "CAUSATION_SOURCE_CONFLICT",
                    "an applied command cause cannot change its canonical facts",
                    code=ErrorCode.PROTOCOL_VIOLATION,
                )
            self._external_causes[cause_id] = normalized
            return tuple(self._apply_and_drain())

    def accept(self, event: EventEnvelope) -> EventApplyResult:
        with self._lock:
            event = EventEnvelope.from_dict(
                event.to_dict(), identities=self._identities
            )
            if event.event_id in self._external_causes:
                return self._error_result(
                    EventApplyStatus.REJECTED_CONFLICT,
                    "CAUSATION_ID_KIND_CONFLICT",
                    "an external command cause cannot also be an event_id",
                )
            existing = self._events.get(event.event_id)
            if existing is not None:
                prior = self._results[event.event_id]
                if existing.canonical_bytes() != event.canonical_bytes():
                    result = self._error_result(
                        EventApplyStatus.REJECTED_CONFLICT,
                        "EVENT_ID_CONFLICT",
                        "event_id was reused with different content",
                    )
                    if event.event_id not in self._applied_ids:
                        existing_stream = self._streams.get(existing.stream_key)
                        if existing_stream is not None:
                            existing_stream.quarantined_by_seq.pop(existing.seq, None)
                            existing_stream.poisoned_seq.add(existing.seq)
                        self._results[event.event_id] = result
                    return result
                duplicate_status = (
                    EventApplyStatus.DUPLICATE_APPLIED
                    if event.event_id in self._applied_ids
                    else EventApplyStatus.DUPLICATE_QUARANTINED
                )
                return EventApplyResult(duplicate_status, prior.error)

            self._events[event.event_id] = event
            cycle_error = self._causal_cycle(event)
            if cycle_error is not None:
                result = self._error_result(
                    EventApplyStatus.REJECTED_CAUSATION,
                    "CAUSATION_CYCLE",
                    cycle_error,
                )
                self._results[event.event_id] = result
                return result

            stream = self._streams.setdefault(event.stream_key, _EventStreamState())
            prior_at_seq = stream.applied_by_seq.get(event.seq)
            prior_at_seq = prior_at_seq or stream.quarantined_by_seq.get(event.seq)
            if prior_at_seq is not None:
                stream.quarantined_by_seq.pop(event.seq, None)
                stream.poisoned_seq.add(event.seq)
                result = self._error_result(
                    EventApplyStatus.REJECTED_CONFLICT,
                    "EVENT_SEQUENCE_CONFLICT",
                    "two different events claim the same producer stream sequence",
                )
                self._results[event.event_id] = result
                return result
            if event.seq < stream.next_seq or event.seq in stream.poisoned_seq:
                result = self._error_result(
                    EventApplyStatus.REJECTED_CONFLICT,
                    "EVENT_SEQUENCE_REUSED",
                    "producer stream sequence was already consumed or poisoned",
                )
                self._results[event.event_id] = result
                return result

            stream.quarantined_by_seq[event.seq] = event
            if event.seq > stream.next_seq:
                result = self._error_result(
                    EventApplyStatus.QUARANTINED_GAP,
                    "EVENT_SEQUENCE_GAP",
                    f"expected sequence {stream.next_seq}, received {event.seq}",
                )
                self._results[event.event_id] = result
                return result

            causal_error = self._causal_block(event)
            if causal_error is not None:
                if causal_error[2]:
                    del stream.quarantined_by_seq[event.seq]
                    stream.poisoned_seq.add(event.seq)
                    result = self._error_result(
                        (
                            EventApplyStatus.REJECTED_PROJECTION
                            if causal_error[0] in _PROJECTION_ERROR_REASONS
                            else EventApplyStatus.REJECTED_CAUSATION
                        ),
                        causal_error[0],
                        causal_error[1],
                    )
                    self._results[event.event_id] = result
                    return result
                result = self._error_result(
                    (
                        EventApplyStatus.QUARANTINED_PROJECTION
                        if causal_error[0] == "PROGRESS_SEQUENCE_GAP"
                        else EventApplyStatus.QUARANTINED_CAUSATION
                    ),
                    causal_error[0],
                    causal_error[1],
                )
                self._results[event.event_id] = result
                return result

            lifecycle_error = self._lifecycle_error(event)
            if lifecycle_error is not None:
                del stream.quarantined_by_seq[event.seq]
                stream.poisoned_seq.add(event.seq)
                result = EventApplyResult(
                    EventApplyStatus.REJECTED_LIFECYCLE, lifecycle_error
                )
                self._results[event.event_id] = result
                return result

            applied = self._apply_and_drain()
            current = self._results.get(event.event_id)
            if event.event_id not in self._applied_ids and current is not None:
                return current
            result = EventApplyResult(
                EventApplyStatus.APPLIED, applied_event_ids=tuple(applied)
            )
            self._results[event.event_id] = result
            return result

    @staticmethod
    def _error_result(
        status: EventApplyStatus, reason: str, message: str
    ) -> EventApplyResult:
        return EventApplyResult(
            status,
            ContractError(
                code=ErrorCode.PROTOCOL_VIOLATION,
                reason=reason,
                message=message,
                retriable=status
                in {
                    EventApplyStatus.QUARANTINED_GAP,
                    EventApplyStatus.QUARANTINED_CAUSATION,
                    EventApplyStatus.QUARANTINED_PROJECTION,
                },
                correlation_id=None,
                _details=_freeze_object({}, "error.details"),
            ),
        )

    def _causal_cycle(self, event: EventEnvelope) -> str | None:
        seen = {event.event_id}
        cursor = event.causation_id
        while cursor is not None:
            if cursor in seen:
                return "event causation must be acyclic"
            seen.add(cursor)
            ancestor = self._events.get(cursor)
            if ancestor is None:
                return None
            cursor = ancestor.causation_id
        return None

    def _causal_block(self, event: EventEnvelope) -> tuple[str, str, bool] | None:
        if event.causation_id is None:
            return None
        source = self._events.get(event.causation_id)
        external = self._external_causes.get(event.causation_id)
        if source is None and external is not None:
            mismatch = self._causal_context_error(
                event, external.scope, external.correlation_id
            )
            if mismatch is not None:
                return mismatch
            if _EVENT_RULES[event.event_type].adapter:
                return (
                    "ADAPTER_SOURCE_EVENT_REQUIRED",
                    "adapter events must reference an authoritative source event",
                    True,
                )
            if event.event_type == "task.retry_accepted" and (
                external.command_type != "task.retry"
                or event.payload.get("command_id") != external.command_id
                or external.target_ref != event.stream_ref
                or event.payload.get("retry_of_attempt_id")
                != external.payload.get("previous_attempt_id")
                or event.payload.get("previous_outcome")
                != external.payload.get("previous_outcome")
                or event.payload.get("attempt_number")
                != external.payload.get("attempt_number")
            ):
                return (
                    "TASK_RETRY_CAUSATION_MISMATCH",
                    "task.retry_accepted must bind the exact applied retry command",
                    True,
                )
            return None
        if source is None or source.event_id not in self._applied_ids:
            return (
                "CAUSATION_NOT_APPLIED",
                "causation_id must reference an already applied event",
                False,
            )
        mismatch = self._causal_context_error(
            event, source.scope, source.correlation_id
        )
        if mismatch is not None:
            return mismatch
        rule = _EVENT_RULES[event.event_type]
        if rule.adapter:
            if source.producer.authority == "adapter":
                return (
                    "ADAPTER_SOURCE_NOT_AUTHORITATIVE",
                    "adapter events cannot establish authority for another adapter event",
                    True,
                )
            if rule.progress:
                progress = WorkProgressEventV2.from_dict(
                    event.payload, scope=event.scope
                )
                source_outcome = source.payload.get("outcome")
                if (
                    progress.source.event_id != source.event_id
                    or progress.source.authority.value != source.producer.authority
                    or progress.source.source_work_ref != source.stream_ref
                    or progress.state.value != source.payload.get("state")
                    or (None if progress.outcome is None else progress.outcome.value)
                    != source_outcome
                ):
                    return (
                        "PROGRESS_SOURCE_MISMATCH",
                        "WorkProgress must preserve source identity, authority, state, and outcome",
                        True,
                    )
                expected_progress_seq = self._next_progress_seq.get(
                    (event.scope, progress.work_ref.kind, progress.work_ref.id), 0
                )
                if progress.seq != expected_progress_seq:
                    if progress.seq > expected_progress_seq:
                        return (
                            "PROGRESS_SEQUENCE_GAP",
                            "WorkProgress projection sequence is waiting for an earlier event",
                            False,
                        )
                    return (
                        "PROGRESS_SEQUENCE_REUSED",
                        "WorkProgress projection sequence was already consumed",
                        True,
                    )
                if source.event_id in self._projected_sources:
                    return (
                        "PROGRESS_SOURCE_ALREADY_PROJECTED",
                        "one authoritative source event can produce only one WorkProgress projection",
                        True,
                    )
                source_queue = self._progress_source_queues.get(
                    source.progress_source_key
                )
                if source_queue is None or not source_queue:
                    return (
                        "PROGRESS_SOURCE_ORDER_MISMATCH",
                        "WorkProgress source has no pending authoritative position",
                        True,
                    )
                if source_queue[0] != source.event_id:
                    return (
                        "PROGRESS_SOURCE_ORDER_MISMATCH",
                        "WorkProgress must preserve authoritative source application order",
                        True,
                    )
                if (
                    progress.summary.knowledge is Knowledge.KNOWN
                    or progress.blocking_question.knowledge is Knowledge.KNOWN
                    or progress.artifact_refs.knowledge is Knowledge.KNOWN
                    or progress.urgency is not WorkUrgency.UNKNOWN
                    or progress.speakability is not Speakability.NOT_SPEAKABLE
                ):
                    return (
                        "PROGRESS_DETAIL_UNPROVEN",
                        "current source event schema cannot prove WorkProgress detail or notification hints",
                        True,
                    )
            else:
                source_type = event.payload["source_event_type"]
                if source_type != source.event_type:
                    return (
                        "ADAPTER_SOURCE_TYPE_MISMATCH",
                        "adapter source_event_type must match the causal source event",
                        True,
                    )
        return None

    @staticmethod
    def _causal_context_error(
        event: EventEnvelope, source_scope: ScopeRef, source_correlation_id: str
    ) -> tuple[str, str, bool] | None:
        if event.scope != source_scope:
            return (
                "CAUSATION_SCOPE_MISMATCH",
                "a derived event must have the same scope as its immediate cause",
                True,
            )
        if event.correlation_id != source_correlation_id:
            return (
                "CAUSATION_CORRELATION_MISMATCH",
                "a derived event must have the same correlation_id as its immediate cause",
                True,
            )
        return None

    def _lifecycle_error(self, event: EventEnvelope) -> ContractError | None:
        if not _EVENT_RULES[event.event_type].lifecycle:
            return None
        initial = _INITIAL_LIFECYCLE_STATES.get(event.stream_ref.kind)
        if initial is None:
            return None
        object_key = (event.stream_ref.kind, event.stream_ref.id)
        object_scope = self._scope_by_object.get(object_key)
        if object_scope is not None and object_scope != event.scope:
            return _violation(
                "LIFECYCLE_SCOPE_MISMATCH",
                "lifecycle identity cannot change scope",
                code=ErrorCode.PROTOCOL_VIOLATION,
            ).error
        state = event.payload.get("state")
        assert isinstance(state, str)
        outcome = event.payload.get("outcome")
        assert outcome is None or isinstance(outcome, str)
        current_state = self._lifecycle_by_object.get(object_key)
        if current_state is None:
            if state == initial and event.event_type != "task.retry_accepted":
                return None
            return _violation(
                "INVALID_INITIAL_LIFECYCLE_STATE",
                f"{event.stream_ref.kind.value} must begin at {initial!r}",
                code=ErrorCode.PROTOCOL_VIOLATION,
            ).error
        if event.event_type == "task.retry_accepted":
            previous_outcome = event.payload.get("previous_outcome")
            attempt_number = event.payload.get("attempt_number")
            if (
                current_state != "terminal"
                or previous_outcome
                != self._task_terminal_outcome_by_object.get(object_key)
                or attempt_number
                != self._task_attempt_number_by_object.get(object_key, 1) + 1
            ):
                return _violation(
                    "TASK_RETRY_PRECONDITION_STALE",
                    "task.retry_accepted does not continue the exact terminal epoch",
                    code=ErrorCode.PROTOCOL_VIOLATION,
                ).error
            return None
        try:
            validate_transition(
                LifecycleKind(event.stream_ref.kind.value),
                current_state,
                state,
                outcome=outcome,
            )
        except ContractViolation as error:
            return ContractError(
                code=ErrorCode.PROTOCOL_VIOLATION,
                reason=error.error.reason,
                message=error.error.message,
                retriable=False,
                correlation_id=event.correlation_id,
                _details=_freeze_object(error.error.details, "error.details"),
            )
        return None

    def _apply_and_drain(self) -> list[str]:
        applied: list[str] = []
        made_progress = True
        while made_progress:
            made_progress = False
            for _key, stream in tuple(self._streams.items()):
                if stream.next_seq in stream.poisoned_seq:
                    continue
                candidate = stream.quarantined_by_seq.get(stream.next_seq)
                if candidate is None:
                    continue
                causal_error = self._causal_block(candidate)
                if causal_error is not None:
                    if causal_error[2]:
                        del stream.quarantined_by_seq[stream.next_seq]
                        stream.poisoned_seq.add(stream.next_seq)
                        self._results[candidate.event_id] = self._error_result(
                            (
                                EventApplyStatus.REJECTED_PROJECTION
                                if causal_error[0] in _PROJECTION_ERROR_REASONS
                                else EventApplyStatus.REJECTED_CAUSATION
                            ),
                            causal_error[0],
                            causal_error[1],
                        )
                    continue
                lifecycle_error = self._lifecycle_error(candidate)
                if lifecycle_error is not None:
                    del stream.quarantined_by_seq[stream.next_seq]
                    stream.poisoned_seq.add(stream.next_seq)
                    self._results[candidate.event_id] = EventApplyResult(
                        EventApplyStatus.REJECTED_LIFECYCLE,
                        lifecycle_error,
                    )
                    continue
                del stream.quarantined_by_seq[stream.next_seq]
                stream.applied_by_seq[stream.next_seq] = candidate
                stream.next_seq += 1
                state = candidate.payload.get("state")
                if _EVENT_RULES[candidate.event_type].lifecycle and isinstance(
                    state, str
                ):
                    object_key = (
                        candidate.stream_ref.kind,
                        candidate.stream_ref.id,
                    )
                    self._lifecycle_by_object[object_key] = state
                    self._scope_by_object[object_key] = candidate.scope
                    if candidate.stream_ref.kind is IdentityKind.TASK:
                        if candidate.event_type == "task.accepted":
                            self._task_attempt_number_by_object[object_key] = 1
                        elif candidate.event_type == "task.retry_accepted":
                            retry_number = candidate.payload.get("attempt_number")
                            assert isinstance(retry_number, int)
                            self._task_attempt_number_by_object[object_key] = (
                                retry_number
                            )
                            self._task_terminal_outcome_by_object.pop(object_key, None)
                        elif candidate.event_type == "task.terminal":
                            task_outcome = candidate.payload.get("outcome")
                            assert isinstance(task_outcome, str)
                            self._task_terminal_outcome_by_object[object_key] = (
                                task_outcome
                            )
                    if candidate.stream_ref.kind in {
                        IdentityKind.ROUND,
                        IdentityKind.TASK,
                        IdentityKind.ATTEMPT,
                    }:
                        self._progress_source_queues.setdefault(
                            candidate.progress_source_key, deque()
                        ).append(candidate.event_id)
                if _EVENT_RULES[candidate.event_type].progress:
                    progress = WorkProgressEventV2.from_dict(
                        candidate.payload, scope=candidate.scope
                    )
                    progress_key = (
                        candidate.scope,
                        progress.work_ref.kind,
                        progress.work_ref.id,
                    )
                    self._next_progress_seq[progress_key] = progress.seq + 1
                    source_event = self._events[progress.source.event_id]
                    source_queue = self._progress_source_queues[
                        source_event.progress_source_key
                    ]
                    source_event_id = source_queue.popleft()
                    assert source_event_id == progress.source.event_id
                    self._projected_sources.add(source_event_id)
                self._applied_ids.add(candidate.event_id)
                self._results[candidate.event_id] = EventApplyResult(
                    EventApplyStatus.APPLIED,
                    applied_event_ids=(candidate.event_id,),
                )
                applied.append(candidate.event_id)
                made_progress = True
        return applied


def classify_contract(payload: object) -> str:
    data = _strict_object(payload, field_name="contract")
    version = data.get("contract_version")
    if version == CONTRACT_VERSION:
        return "v2"
    if version == V1_CONTRACT_VERSION:
        return "v1"
    raise _violation(
        "UNSUPPORTED_CONTRACT_VERSION",
        "payload is neither the v1 nor v2 contract",
        code=ErrorCode.UNSUPPORTED,
    )


def parse_v2_envelope(
    payload: object,
    *,
    identities: IdentityRegistry | None = None,
    commits: TurnCommitLedger | None = None,
) -> CommandEnvelope | QueryEnvelope | ResultEnvelope | EventEnvelope:
    data = _strict_object(payload, field_name="envelope")
    if data.get("contract_version") != CONTRACT_VERSION:
        raise _violation(
            "UNSUPPORTED_CONTRACT_VERSION",
            f"expected {CONTRACT_VERSION}",
            code=ErrorCode.UNSUPPORTED,
        )
    if "command_type" in data:
        return CommandEnvelope.from_dict(data, identities=identities, commits=commits)
    if "query_type" in data:
        return QueryEnvelope.from_dict(data, identities=identities)
    if "event_type" in data:
        return EventEnvelope.from_dict(data, identities=identities)
    if "ok" in data:
        return ResultEnvelope.from_dict(data)
    raise _violation("UNKNOWN_ENVELOPE_KIND", "cannot identify v2 envelope kind")


__all__ = [
    "Assurance",
    "Availability",
    "CancelScope",
    "CapabilityDescriptor",
    "CapabilityRegistry",
    "CommandEnvelope",
    "CommandResultLedger",
    "ConnectionEpochRef",
    "ContextRedaction",
    "ContextRef",
    "ContextRevision",
    "ContextRevisionKind",
    "CONTRACT_VERSION",
    "ContractError",
    "ContractViolation",
    "ErrorCode",
    "EventApplyResult",
    "EventApplyStatus",
    "EventEnvelope",
    "EventSequenceTracker",
    "IdentityKind",
    "IdentityRecord",
    "IdentityRef",
    "IdentityRegistry",
    "InputCommitState",
    "Knowledge",
    "KnownFact",
    "LifecycleKind",
    "MAX_SAFE_INTEGER",
    "OriginRef",
    "ProducerRef",
    "QueryEnvelope",
    "ResponseFence",
    "ResponseRef",
    "ResultEnvelope",
    "ScopeRef",
    "SideEffectTarget",
    "TerminalOutcome",
    "TurnCommit",
    "TurnCommitLedger",
    "V1_CONTRACT_VERSION",
    "Speakability",
    "WorkProgressEventV2",
    "WorkProgressSource",
    "WorkSourceAuthority",
    "WorkState",
    "WorkUrgency",
    "canonical_json",
    "canonical_json_bytes",
    "classify_contract",
    "default_barge_in_scopes",
    "dispatch_cancel",
    "dispatch_committed_input",
    "parse_v2_envelope",
    "validate_transition",
]


_EXPECTED_PARENT_KINDS: Final = MappingProxyType(
    {
        IdentityKind.CONNECTION: frozenset(),
        IdentityKind.MEDIA_SESSION: frozenset({IdentityKind.INTERACTION}),
        IdentityKind.TRACK: frozenset({IdentityKind.MEDIA_SESSION}),
        IdentityKind.INTERACTION: frozenset(),
        IdentityKind.TURN: frozenset({IdentityKind.INTERACTION}),
        IdentityKind.RESPONSE: frozenset({IdentityKind.INTERACTION, IdentityKind.TURN}),
        IdentityKind.ROUND: frozenset(),
        IdentityKind.TASK: frozenset(),
        IdentityKind.ATTEMPT: frozenset({IdentityKind.TASK}),
        IdentityKind.COMMAND: frozenset(),
        IdentityKind.REQUEST: frozenset(),
        IdentityKind.EVENT: frozenset(),
    }
)


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    ref: IdentityRef
    scope: ScopeRef
    parents: tuple[IdentityRef, ...] = ()
    connection_epoch_ref: ConnectionEpochRef | None = None


class IdentityRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[tuple[IdentityKind, str], IdentityRecord] = {}
        self._kind_by_id: dict[str, IdentityKind] = {}

    def register(self, record: IdentityRecord) -> IdentityRecord:
        connection_epoch_ref = record.connection_epoch_ref
        if connection_epoch_ref is not None:
            if not isinstance(connection_epoch_ref, ConnectionEpochRef):
                raise _violation(
                    "INVALID_CONNECTION_EPOCH_BINDING",
                    "identity_record.connection_epoch_ref must be a ConnectionEpochRef",
                )
            connection_epoch_ref = ConnectionEpochRef(
                connection_id=_required_text(
                    connection_epoch_ref.connection_id,
                    "identity_record.connection_epoch_ref.connection_id",
                ),
                connection_epoch=_uint(
                    connection_epoch_ref.connection_epoch,
                    "identity_record.connection_epoch_ref.connection_epoch",
                ),
            )
        record = IdentityRecord(
            ref=IdentityRef(
                kind=_enum(IdentityKind, record.ref.kind, "identity_record.ref.kind"),
                id=_required_text(record.ref.id, "identity_record.ref.id"),
            ),
            scope=ScopeRef(
                subject_id=_required_text(
                    record.scope.subject_id, "identity_record.scope.subject_id"
                ),
                project_id=_optional_id(
                    record.scope.project_id, "identity_record.scope.project_id"
                ),
                session_id=_optional_id(
                    record.scope.session_id, "identity_record.scope.session_id"
                ),
                assurance=_enum(
                    Assurance,
                    record.scope.assurance,
                    "identity_record.scope.assurance",
                ),
            ),
            parents=tuple(
                IdentityRef(
                    kind=_enum(
                        IdentityKind,
                        parent.kind,
                        "identity_record.parents.kind",
                    ),
                    id=_required_text(parent.id, "identity_record.parents.id"),
                )
                for parent in record.parents
            ),
            connection_epoch_ref=connection_epoch_ref,
        )
        parent_kinds = frozenset(parent.kind for parent in record.parents)
        if len(parent_kinds) != len(record.parents):
            raise _violation(
                "DUPLICATE_PARENT_KIND",
                "an identity may have at most one parent per kind",
            )
        expected = _EXPECTED_PARENT_KINDS[record.ref.kind]
        if parent_kinds != expected:
            raise _violation(
                "IDENTITY_PARENT_MISMATCH",
                f"{record.ref.kind.value} requires parent kinds "
                f"{sorted(kind.value for kind in expected)}",
            )
        if (
            record.ref.kind in {IdentityKind.CONNECTION, IdentityKind.MEDIA_SESSION}
            and connection_epoch_ref is None
        ):
            raise _violation(
                "CONNECTION_EPOCH_BINDING_REQUIRED",
                f"{record.ref.kind.value} requires connection_epoch_ref",
            )
        if (
            record.ref.kind not in {IdentityKind.CONNECTION, IdentityKind.MEDIA_SESSION}
            and connection_epoch_ref is not None
        ):
            raise _violation(
                "CONNECTION_EPOCH_BINDING_FORBIDDEN",
                f"{record.ref.kind.value} forbids connection_epoch_ref",
            )
        if (
            record.ref.kind is IdentityKind.CONNECTION
            and connection_epoch_ref is not None
            and connection_epoch_ref.connection_id != record.ref.id
        ):
            raise _violation(
                "CONNECTION_EPOCH_BINDING_MISMATCH",
                "connection binding must name the registered connection",
            )
        with self._lock:
            existing_kind = self._kind_by_id.get(record.ref.id)
            if existing_kind is not None and existing_kind is not record.ref.kind:
                raise _violation(
                    "IDENTITY_KIND_MISMATCH",
                    f"identity {record.ref.id!r} is already {existing_kind.value}",
                )
            for parent in record.parents:
                parent_record = self._records.get((parent.kind, parent.id))
                if parent_record is None:
                    raise _violation(
                        "IDENTITY_PARENT_NOT_FOUND",
                        f"parent {parent.kind.value}:{parent.id} is not registered",
                    )
                if parent_record.scope != record.scope:
                    raise _violation(
                        "IDENTITY_SCOPE_MISMATCH",
                        "child and parent scope must match exactly",
                    )
            if (
                record.ref.kind is IdentityKind.MEDIA_SESSION
                and connection_epoch_ref is not None
            ):
                connection = self._records.get(
                    (IdentityKind.CONNECTION, connection_epoch_ref.connection_id)
                )
                if connection is None:
                    raise _violation(
                        "IDENTITY_CONNECTION_NOT_FOUND",
                        "the media session connection is not registered",
                    )
                if connection.scope != record.scope:
                    raise _violation(
                        "IDENTITY_SCOPE_MISMATCH",
                        "media session and connection scope must match exactly",
                    )
                if connection.connection_epoch_ref != connection_epoch_ref:
                    raise _violation(
                        "CONNECTION_EPOCH_BINDING_MISMATCH",
                        "media session must use the active connection epoch binding",
                    )
            parent_map = {parent.kind: parent for parent in record.parents}
            if record.ref.kind is IdentityKind.RESPONSE:
                turn = self._records[
                    (IdentityKind.TURN, parent_map[IdentityKind.TURN].id)
                ]
                turn_interaction = next(
                    parent
                    for parent in turn.parents
                    if parent.kind is IdentityKind.INTERACTION
                )
                if turn_interaction != parent_map[IdentityKind.INTERACTION]:
                    raise _violation(
                        "IDENTITY_PARENT_MISMATCH",
                        "response interaction must own its initiating turn",
                    )
            key = (record.ref.kind, record.ref.id)
            existing = self._records.get(key)
            if existing is not None:
                if existing != record:
                    raise _violation(
                        "IDENTITY_CONFLICT", "identity registration is immutable"
                    )
                return existing
            self._records[key] = record
            self._kind_by_id[record.ref.id] = record.ref.kind
            return record

    def require(
        self,
        ref: IdentityRef,
        *,
        scope: ScopeRef | None = None,
        parent: IdentityRef | None = None,
    ) -> IdentityRecord:
        with self._lock:
            record = self._records.get((ref.kind, ref.id))
            if record is None:
                known_kind = self._kind_by_id.get(ref.id)
                if known_kind is not None:
                    raise _violation(
                        "IDENTITY_KIND_MISMATCH",
                        f"identity {ref.id!r} is {known_kind.value}, not {ref.kind.value}",
                    )
                raise _violation(
                    "IDENTITY_NOT_FOUND",
                    f"identity {ref.kind.value}:{ref.id} is unknown",
                )
            if scope is not None and record.scope != scope:
                raise _violation(
                    "IDENTITY_SCOPE_MISMATCH", "identity scope does not match"
                )
            if parent is not None and parent not in record.parents:
                raise _violation(
                    "IDENTITY_PARENT_MISMATCH",
                    f"{parent.kind.value}:{parent.id} does not own "
                    f"{ref.kind.value}:{ref.id}",
                )
            return record


@dataclass(frozen=True, slots=True)
class TurnCommit:
    commit_id: str
    turn_id: str
    interaction_id: str
    text: str
    committed_at: str
    scope: ScopeRef
    context_refs: tuple[ContextRef, ...]
    _hypothesis_provenance: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def hypothesis_provenance(self) -> dict[str, object]:
        return _thaw_object(self._hypothesis_provenance)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        identities: IdentityRegistry | None = None,
    ) -> TurnCommit:
        data = _strict_object(payload, field_name="turn_commit")
        _require_exact_keys(
            data,
            required={
                "contract_version",
                "commit_id",
                "turn_id",
                "interaction_id",
                "text",
                "hypothesis_provenance",
                "scope",
                "context_refs",
                "committed_at",
            },
            field_name="turn_commit",
        )
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        scope = ScopeRef.from_dict(data["scope"])
        turn_id = _required_text(data["turn_id"], "turn_commit.turn_id")
        interaction_id = _required_text(
            data["interaction_id"], "turn_commit.interaction_id"
        )
        if identities is not None:
            interaction = IdentityRef(IdentityKind.INTERACTION, interaction_id)
            identities.require(interaction, scope=scope)
            identities.require(
                IdentityRef(IdentityKind.TURN, turn_id),
                scope=scope,
                parent=interaction,
            )
        return cls(
            commit_id=_required_text(data["commit_id"], "turn_commit.commit_id"),
            turn_id=turn_id,
            interaction_id=interaction_id,
            text=_required_text(data["text"], "turn_commit.text"),
            committed_at=_timestamp(data["committed_at"], "turn_commit.committed_at"),
            scope=scope,
            context_refs=_context_refs(
                data["context_refs"], "turn_commit.context_refs", scope=scope
            ),
            _hypothesis_provenance=_freeze_object(
                data["hypothesis_provenance"],
                "turn_commit.hypothesis_provenance",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "commit_id": self.commit_id,
            "turn_id": self.turn_id,
            "interaction_id": self.interaction_id,
            "text": self.text,
            "hypothesis_provenance": self.hypothesis_provenance,
            "scope": self.scope.to_dict(),
            "context_refs": [ref.to_dict() for ref in self.context_refs],
            "committed_at": self.committed_at,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


class TurnCommitLedger:
    """Atomic, once-only commit ownership for a turn and commit identifier."""

    def __init__(self, *, capacity: int = 128) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 65_536:
            raise _violation(
                "INVALID_TURN_COMMIT_CAPACITY",
                "turn commit capacity must be a bounded positive integer",
                code=ErrorCode.INVALID_ARGUMENT,
            )
        self._lock = threading.RLock()
        self._capacity = capacity
        self._by_commit_id: dict[str, TurnCommit] = {}
        self._by_turn_id: dict[str, TurnCommit] = {}

    def accept(self, commit: TurnCommit) -> bool:
        with self._lock:
            existing_id = self._by_commit_id.get(commit.commit_id)
            existing_turn = self._by_turn_id.get(commit.turn_id)
            existing = existing_id or existing_turn
            if existing is not None:
                if existing.canonical_bytes() == commit.canonical_bytes():
                    return False
                raise _violation(
                    "TURN_COMMIT_CONFLICT",
                    "commit_id and turn_id are immutable and may commit only once",
                    code=ErrorCode.CONFLICT,
                )
            if len(self._by_commit_id) >= self._capacity:
                raise _violation(
                    "TURN_COMMIT_LEDGER_FULL",
                    "bounded turn commit authority is full",
                    code=ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            self._by_commit_id[commit.commit_id] = commit
            self._by_turn_id[commit.turn_id] = commit
            return True

    def require_origin(self, origin: OriginRef, scope: ScopeRef) -> TurnCommit:
        if origin.kind != "committed_turn":
            raise _violation(
                "COMMITTED_ORIGIN_REQUIRED", "origin must identify a committed turn"
            )
        with self._lock:
            commit = self._by_commit_id.get(origin.commit_id or "")
            if (
                commit is None
                or commit.turn_id != origin.turn_id
                or commit.scope != scope
            ):
                raise _violation(
                    "TURN_COMMIT_NOT_ACCEPTED",
                    "origin does not match an accepted commit in the exact scope",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            return commit

    def release_origin(self, origin: OriginRef, scope: ScopeRef) -> bool:
        """Release one exact downstream-only origin after use or route close."""

        with self._lock:
            commit = self._by_commit_id.get(origin.commit_id or "")
            if (
                origin.kind != "committed_turn"
                or commit is None
                or commit.turn_id != origin.turn_id
                or commit.scope != scope
            ):
                return False
            self._by_commit_id.pop(commit.commit_id, None)
            self._by_turn_id.pop(commit.turn_id, None)
            return True

    def dispatch(
        self,
        commit: TurnCommit,
        target: SideEffectTarget | str,
        effect: Callable[[TurnCommit], _ValueT],
    ) -> tuple[bool, _ValueT | None]:
        _enum(SideEffectTarget, target, "input.target")
        with self._lock:
            if not self.accept(commit):
                return False, None
            return True, effect(commit)
