# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Source-backed formal Task progress return without lifecycle authority.

The default ``TaskEventSubscription`` is live-only while the notification arbiter
requires a complete, contiguous lifecycle stream. Voice therefore activates only
with the concrete SQLite-authority source defined here, which validates an atomic
prefix/cursor before following the durable suffix. Product composition does not
yet construct or register that source, so formal product voice remains fail-closed.
Text-origin delivery can continue to consume the authorized live-only subscription
directly because it does not enter the arbiter and preserves canonical sequences.

A prepared lease is an injection seam for a future Task/CR owner and for bounded
package-contract tests.  It is not implemented by the current product composition.
The bridge validates every delivered canonical TaskEvent again, projects only its
source-backed facts, and routes the result to either a notification-intent sink or
a Chat/UI-event sink.  It has no TTS, history, Agent, Tool, Task mutation, or cancel
effect port.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CONTRACT_VERSION,
    ContractViolation,
    ErrorCode,
    EventEnvelope,
    IdentityKind,
    IdentityRef,
    ProducerRef,
    ScopeRef,
    TerminalOutcome,
    WorkProgressEventV2,
    WorkSourceAuthority,
    canonical_json_bytes,
)

from .formal_task_models import (
    FormalTaskViolation,
    PersistentTaskEvent,
    TaskAuthorizationGrant,
    utc_now,
)
from .progress_notification_arbiter import (
    ForegroundSnapshot,
    NoProjectionAdvanceDisposition,
    NotificationDecision,
    NotificationDisposition,
    ProgressNotificationArbiter,
    ProgressNotificationBinding,
    _mint_verified_attempt_epoch_baseline,
    _mint_verified_no_projection_advance,
)
from .task_event_subscription import TaskEventSubscription
from .task_store import SqliteTaskStore

_EVENTS_CAPABILITY = frozenset({"task.events"})
_PROJECTABLE_EVENTS = {
    "task.accepted": "accepted",
    "task.retry_accepted": "accepted",
    "task.running": "running",
    "task.blocked": "blocked",
    "task.decision_required": "decision_required",
    "task.terminal": "terminal",
}
_NO_PROJECTION_EVENTS = frozenset(
    {
        "attempt.accepted",
        "attempt.running",
        "attempt.terminal",
        "task.cancel_requested",
    }
)
_TASK_EVENT_PRODUCERS = {
    "task.accepted": frozenset({"task_core"}),
    "task.retry_accepted": frozenset({"task_core"}),
    "task.running": frozenset({"task_core"}),
    "task.blocked": frozenset({"task_core"}),
    "task.decision_required": frozenset({"task_core"}),
    "task.terminal": frozenset(
        {"task_core", "task_core.delivery", "task_core.reconciliation"}
    ),
}
_SOURCE_EXTENSION = "jiuwenswarm.task_progress_return"
_PROGRESS_EVENT_PREFIX = "task-progress-return:"


class TaskProgressReturnViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class TaskProgressOriginKind(StrEnum):
    VOICE = "voice"
    TEXT = "text"


class TaskProgressHandoffKind(StrEnum):
    """Evidence class for the injected source handoff.

    ``PACKAGE_CONTRACT_TEST`` is accepted only when the constructor's explicit
    test-evidence switch is true.  It can never be mistaken for product evidence.
    ``AUTHORITY_ATOMIC`` identifies the concrete Task Store prefix/cursor source;
    product activation still requires the future IO/CR-owned composition seam.
    """

    PACKAGE_CONTRACT_TEST = "package_contract_test"
    AUTHORITY_ATOMIC = "authority_atomic"


class TaskProgressReturnReason(StrEnum):
    ACTIVATED = "TASK_PROGRESS_RETURN_ACTIVATED"
    FEATURE_DISABLED = "TASK_PROGRESS_FEATURE_DISABLED"
    AUTHORIZATION_REJECTED = "TASK_PROGRESS_AUTHORIZATION_REJECTED"
    INVALID_BINDING = "TASK_PROGRESS_INVALID_BINDING"
    STALE_GENERATION = "TASK_PROGRESS_STALE_GENERATION"
    STALE_ATTEMPT = "TASK_PROGRESS_STALE_ATTEMPT"
    AUTHORITY_HANDOFF_UNAVAILABLE = "TASK_PROGRESS_AUTHORITY_HANDOFF_UNAVAILABLE"
    HANDOFF_REJECTED = "TASK_PROGRESS_HANDOFF_REJECTED"
    SOURCE_EXHAUSTED = "TASK_PROGRESS_SOURCE_EXHAUSTED"
    SOURCE_FAILED = "TASK_PROGRESS_SOURCE_FAILED"
    SOURCE_PROTOCOL_VIOLATION = "TASK_PROGRESS_SOURCE_PROTOCOL_VIOLATION"
    SOURCE_EVENT_NOT_PROJECTABLE = "TASK_PROGRESS_SOURCE_EVENT_NOT_PROJECTABLE"
    ARBITER_REJECTED = "TASK_PROGRESS_ARBITER_REJECTED"
    ARBITER_BACKPRESSURE = "TASK_PROGRESS_ARBITER_BACKPRESSURE"
    ARBITER_FEATURE_DISABLED = "TASK_PROGRESS_ARBITER_FEATURE_DISABLED"
    ARBITER_ACK_FAILED = "TASK_PROGRESS_ARBITER_ACK_FAILED"
    VOICE_SINK_FAILED = "TASK_PROGRESS_VOICE_SINK_FAILED"
    TEXT_SINK_FAILED = "TASK_PROGRESS_TEXT_SINK_FAILED"
    CONSUMER_DETACHED = "TASK_PROGRESS_CONSUMER_DETACHED"
    TERMINAL_DELIVERED = "TASK_PROGRESS_TERMINAL_DELIVERED"
    CLOSED_BEFORE_ACTIVATION = "TASK_PROGRESS_CLOSED_BEFORE_ACTIVATION"
    ALREADY_SETTLED = "TASK_PROGRESS_ALREADY_SETTLED"


class TaskProgressReturnState(StrEnum):
    NEW = "new"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    ACTIVE = "active"
    DETACHING = "detaching"
    CLOSED = "closed"
    FAILED = "failed"


class TaskProgressSourceDecision(StrEnum):
    PROJECTED = "TASK_PROGRESS_SOURCE_PROJECTED"
    UNPROJECTED_ADVANCE = "TASK_PROGRESS_SOURCE_UNPROJECTED_ADVANCE"
    DUPLICATE_IGNORED = "TASK_PROGRESS_SOURCE_DUPLICATE_IGNORED"
    SEQUENCE_GAP = "TASK_PROGRESS_SOURCE_SEQUENCE_GAP"
    SEQUENCE_OUT_OF_ORDER = "TASK_PROGRESS_SOURCE_SEQUENCE_OUT_OF_ORDER"
    EVENT_ID_CONFLICT = "TASK_PROGRESS_SOURCE_EVENT_ID_CONFLICT"
    SEQUENCE_CONFLICT = "TASK_PROGRESS_SOURCE_SEQUENCE_CONFLICT"
    BINDING_REJECTED = "TASK_PROGRESS_SOURCE_BINDING_REJECTED"
    INVALID_EVENT = "TASK_PROGRESS_SOURCE_INVALID_EVENT"
    STALE_GENERATION = "TASK_PROGRESS_SOURCE_STALE_GENERATION"
    STALE_ATTEMPT = "TASK_PROGRESS_SOURCE_STALE_ATTEMPT"
    NOT_PROJECTABLE = "TASK_PROGRESS_SOURCE_NOT_PROJECTABLE"


@dataclass(frozen=True, slots=True, repr=False)
class TaskProgressOriginBinding:
    """Exact product binding retained on every origin-surface output."""

    scope: ScopeRef
    task_id: str
    session_id: str
    project_id: str
    correlation_id: str
    origin_kind: TaskProgressOriginKind
    origin_id: str
    generation_kind: str
    generation_id: str
    generation: int
    source_instance_id: str
    progress_producer: ProducerRef
    progress_adapter: str


@dataclass(frozen=True, slots=True)
class TaskProgressProjection:
    task_event: PersistentTaskEvent
    source_event: EventEnvelope
    progress_event: EventEnvelope
    notification_binding: ProgressNotificationBinding


@dataclass(frozen=True, slots=True)
class TaskProgressNotificationIntent:
    """A CR-owned notification intent, never a TTS command."""

    origin: TaskProgressOriginBinding
    task_event: PersistentTaskEvent
    source_event: EventEnvelope
    progress_event: EventEnvelope
    decision: NotificationDecision
    evidence_id: str


@dataclass(frozen=True, slots=True)
class TaskProgressTextEvent:
    """A Chat/UI event, never a Chat-history write."""

    origin: TaskProgressOriginBinding
    task_event: PersistentTaskEvent
    source_event: EventEnvelope
    progress_event: EventEnvelope
    evidence_id: str


@dataclass(frozen=True, slots=True)
class TaskProgressReturnSnapshot:
    enabled: bool
    state: TaskProgressReturnState
    reason_id: TaskProgressReturnReason | None
    handoff_kind: TaskProgressHandoffKind | None
    handoff_evidence_id: str | None
    worker_pending: bool
    source_events: int
    projected_events: int
    unprojected_events: int
    duplicate_events: int
    gap_events: int
    out_of_order_events: int
    conflict_events: int
    voice_intents: int
    pending_voice_intents: int
    voice_drains: int
    text_events: int
    rejected_events: int
    last_task_event_id: str | None
    last_task_event_seq: int | None
    last_progress_event_id: str | None
    last_source_decision_id: TaskProgressSourceDecision | None
    last_source_evidence_id: str | None
    arbiter_reason: str | None


class PreparedTaskProgressSource(Protocol):
    """Atomic authority handoff or explicitly labeled package-contract evidence."""

    subscription: TaskEventSubscription
    handoff_kind: TaskProgressHandoffKind
    evidence_id: str

    async def start(self) -> bool: ...

    async def next_event(self) -> PersistentTaskEvent: ...

    async def close(self) -> None: ...


class TaskEventAuthorityProgressSource:
    """Concrete Store-owned atomic prefix/cursor source for formal voice progress."""

    __slots__ = (
        "_authorization_fingerprint",
        "_evidence_id",
        "_scope",
        "_subscription",
        "_task_id",
    )

    def __init__(
        self,
        *,
        store: SqliteTaskStore,
        authorization: TaskAuthorizationGrant,
        scope: ScopeRef,
        task_id: str,
        queue_capacity: int = 256,
        validation_capacity: int = 4096,
        poll_interval: float = 0.05,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        if type(store) is not SqliteTaskStore:
            raise _violation(
                "INVALID_TASK_PROGRESS_AUTHORITY_SOURCE",
                "formal voice progress requires the concrete SQLite Task authority",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(authorization) is not TaskAuthorizationGrant:
            raise _violation(
                "INVALID_TASK_PROGRESS_AUTHORITY_SOURCE",
                "formal voice progress requires trusted TaskEvent authorization",
                ErrorCode.UNAUTHENTICATED,
            )
        self._scope = scope
        self._task_id = task_id
        self._authorization_fingerprint = _authorization_fingerprint(authorization)
        self._subscription = TaskEventSubscription(
            source=store,
            authorization=authorization,
            scope=scope,
            task_id=task_id,
            enabled=True,
            queue_capacity=queue_capacity,
            validation_capacity=validation_capacity,
            poll_interval=poll_interval,
            authority_atomic_replay=True,
            clock=clock,
        )
        scope_fingerprint = hashlib.sha256(
            canonical_json_bytes(scope.to_dict())
        ).hexdigest()
        self._evidence_id = (
            f"task-event-authority:{task_id}:{scope_fingerprint}:pending"
        )

    @property
    def subscription(self) -> TaskEventSubscription:
        return self._subscription

    @property
    def handoff_kind(self) -> TaskProgressHandoffKind:
        return TaskProgressHandoffKind.AUTHORITY_ATOMIC

    @property
    def evidence_id(self) -> str:
        return self._evidence_id

    async def start(self) -> bool:
        started = await self._subscription.start()
        snapshot = self._subscription.snapshot()
        if (
            not started
            or snapshot.live_only
            or not snapshot.cursor_replay_supported
            or snapshot.start_head_seq is None
        ):
            return False
        self._evidence_id = (
            f"task-event-authority:{self._task_id}:cursor:{snapshot.start_head_seq}"
        )
        return True

    async def next_event(self) -> PersistentTaskEvent:
        return await self._subscription.next_event()

    async def close(self) -> None:
        await self._subscription.close()


GenerationIsCurrent = Callable[[TaskProgressOriginBinding], bool]
ForegroundSupplier = Callable[[], ForegroundSnapshot]
VoiceIntentSink = Callable[[TaskProgressNotificationIntent], Awaitable[None]]
TextEventSink = Callable[[TaskProgressTextEvent], Awaitable[None]]


def _violation(
    reason: str, message: str, code: ErrorCode = ErrorCode.PROTOCOL_VIOLATION
) -> TaskProgressReturnViolation:
    return TaskProgressReturnViolation(reason, message, code)


def _authorization_fingerprint(authorization: TaskAuthorizationGrant) -> bytes:
    return canonical_json_bytes(
        {
            "principal_id": authorization.principal_id,
            "scope": authorization.scope.to_dict(),
            "operation": authorization.operation,
            "command_id": authorization.command_id,
            "target_task_id": authorization.target_task_id,
            "allowed_capabilities": sorted(authorization.allowed_capabilities),
            "confirmation_id": authorization.confirmation_id,
            "confirmed": authorization.confirmed,
            "expires_at": authorization.expires_at,
        }
    )


def _required_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise _violation(
            "INVALID_TASK_PROGRESS_BINDING",
            f"{field_name} must be a non-empty string",
            ErrorCode.INVALID_ARGUMENT,
        )
    return value


def _canonical_binding(binding: object) -> TaskProgressOriginBinding:
    if not isinstance(binding, TaskProgressOriginBinding):
        raise _violation(
            "INVALID_TASK_PROGRESS_BINDING",
            "task progress return requires an exact origin binding",
            ErrorCode.INVALID_ARGUMENT,
        )
    if not isinstance(binding.scope, ScopeRef):
        raise _violation(
            "INVALID_TASK_PROGRESS_BINDING",
            "task progress binding requires a canonical ScopeRef",
            ErrorCode.INVALID_ARGUMENT,
        )
    try:
        canonical_scope = ScopeRef.from_dict(binding.scope.to_dict())
        canonical_progress_producer = ProducerRef.from_dict(
            binding.progress_producer.to_dict()
        )
    except (AttributeError, ContractViolation, TypeError, ValueError) as error:
        raise _violation(
            "INVALID_TASK_PROGRESS_BINDING",
            "task progress binding contains non-canonical v2 values",
            ErrorCode.INVALID_ARGUMENT,
        ) from error
    for name, value in (
        ("task_id", binding.task_id),
        ("session_id", binding.session_id),
        ("project_id", binding.project_id),
        ("correlation_id", binding.correlation_id),
        ("origin_id", binding.origin_id),
        ("generation_kind", binding.generation_kind),
        ("generation_id", binding.generation_id),
        ("source_instance_id", binding.source_instance_id),
        ("progress_adapter", binding.progress_adapter),
    ):
        _required_text(value, name)
    if (
        canonical_scope != binding.scope
        or canonical_scope.assurance is not Assurance.AUTHENTICATED
        or canonical_scope.session_id != binding.session_id
        or canonical_scope.project_id != binding.project_id
        or canonical_progress_producer != binding.progress_producer
        or canonical_progress_producer.authority != "adapter"
        or not isinstance(binding.origin_kind, TaskProgressOriginKind)
        or type(binding.generation) is not int
        or binding.generation < 0
    ):
        raise _violation(
            "INVALID_TASK_PROGRESS_BINDING",
            "task progress binding is not exact, authenticated, and canonical",
            ErrorCode.PERMISSION_DENIED,
        )
    return binding


def _evidence_id(
    origin: TaskProgressOriginBinding,
    event: PersistentTaskEvent | None = None,
) -> str:
    identity = {
        "task_id": origin.task_id,
        "correlation_id": origin.correlation_id,
        "generation_kind": origin.generation_kind,
        "generation_id": origin.generation_id,
        "generation": origin.generation,
        "event": (
            "activation"
            if event is None
            else {"seq": event.seq, "event_id": event.event_id}
        ),
    }
    return _PROGRESS_EVENT_PREFIX + hashlib.sha256(
        canonical_json_bytes(identity)
    ).hexdigest()


def project_task_progress_event(
    event: object,
    origin: object,
) -> TaskProgressProjection:
    """Map one canonical task lifecycle event without adding business facts."""

    binding = _canonical_binding(origin)
    if not isinstance(event, PersistentTaskEvent):
        raise _violation(
            "INVALID_TASK_PROGRESS_SOURCE",
            "progress source must be a canonical PersistentTaskEvent",
        )
    expected_state = _PROJECTABLE_EVENTS.get(event.event_type)
    if expected_state is None:
        raise _violation(
            "TASK_PROGRESS_SOURCE_EVENT_NOT_PROJECTABLE",
            "attempt/control TaskEvents require a verified no-projection advance",
            ErrorCode.UNAVAILABLE,
        )
    if (
        event.task_id != binding.task_id
        or event.scope != binding.scope
        or event.correlation_id != binding.correlation_id
    ):
        raise _violation(
            "TASK_PROGRESS_SOURCE_BINDING_MISMATCH",
            "TaskEvent does not match the exact origin task/scope/correlation",
            ErrorCode.PERMISSION_DENIED,
        )
    if (
        event.state != expected_state
        or event.producer not in _TASK_EVENT_PRODUCERS[event.event_type]
        or (event.state == "terminal") != (event.outcome is not None)
        or (
            event.event_type == "task.retry_accepted"
            and (
                set(event.details)
                != {
                    "command_id",
                    "retry_of_attempt_id",
                    "previous_outcome",
                    "attempt_number",
                }
                or event.details.get("command_id") != event.causation_id
                or type(event.details.get("retry_of_attempt_id")) is not str
                or not str(event.details.get("retry_of_attempt_id")).strip()
                or event.details.get("retry_of_attempt_id") == event.attempt_id
                or event.details.get("attempt_number") not in {2, 3}
                or event.details.get("previous_outcome")
                not in {
                    TerminalOutcome.CANCELLED.value,
                    TerminalOutcome.COMPLETED.value,
                }
            )
        )
    ):
        raise _violation(
            "INVALID_TASK_PROGRESS_SOURCE",
            "TaskEvent lifecycle, producer, and outcome must agree",
        )

    source_producer = ProducerRef(
        component="task_core",
        instance_id=binding.source_instance_id,
        authority="task_core",
    )
    source_extensions = {
        _SOURCE_EXTENSION: {
            "persistent_event_seq": event.seq,
            "persistent_event_type": event.event_type,
            "persistent_event_producer": event.producer,
            "persistent_attempt_id": event.attempt_id,
            "persistent_source_event_id": event.source_event_id,
        }
    }
    source_payload: dict[str, object] = {"state": event.state}
    if event.state == "terminal":
        source_payload["outcome"] = event.outcome
    elif event.event_type == "task.retry_accepted":
        source_payload.update(
            {
                "command_id": event.details.get("command_id"),
                "retry_of_attempt_id": event.details.get("retry_of_attempt_id"),
                "previous_outcome": event.details.get("previous_outcome"),
                "attempt_number": event.details.get("attempt_number"),
            }
        )
    try:
        source_event = EventEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "producer": source_producer.to_dict(),
                "stream_ref": {"kind": "task", "id": event.task_id},
                "seq": event.seq,
                "occurred_at": event.occurred_at,
                "scope": event.scope.to_dict(),
                "correlation_id": event.correlation_id,
                "causation_id": event.causation_id,
                "required_capabilities": [],
                "payload": source_payload,
                "extensions": source_extensions,
            }
        )
    except ContractViolation as error:
        raise _violation(
            "INVALID_TASK_PROGRESS_SOURCE_ENVELOPE",
            "TaskEvent cannot be represented as a strict v2 source envelope",
            error.code,
        ) from error

    summary = event.details.get("summary")
    known_summary = type(summary) is str and bool(summary.strip())
    progress_payload = {
        "work_ref": {"kind": "task", "id": event.task_id},
        "source": {
            "authority": "task_core",
            "event_id": event.event_id,
            "source_work_ref": {"kind": "task", "id": event.task_id},
            "adapter": binding.progress_adapter,
        },
        "seq": event.seq,
        "state": event.state,
        "outcome": event.outcome,
        "summary": (
            {"knowledge": "known", "value": summary}
            if known_summary
            else {"knowledge": "unknown"}
        ),
        "blocking_question": {"knowledge": "unknown"},
        "artifact_refs": {"knowledge": "unknown"},
        "urgency": "unknown",
        "speakability": "not_speakable",
    }
    progress_id = f"{_PROGRESS_EVENT_PREFIX}{event.event_id}"
    try:
        progress = WorkProgressEventV2.from_dict(progress_payload, scope=event.scope)
        progress_event = EventEnvelope.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "event_id": progress_id,
                "event_type": "work.progress",
                "producer": binding.progress_producer.to_dict(),
                "stream_ref": {"kind": "task", "id": event.task_id},
                "seq": event.seq,
                "occurred_at": event.occurred_at,
                "scope": event.scope.to_dict(),
                "correlation_id": event.correlation_id,
                "causation_id": event.event_id,
                "required_capabilities": [],
                "payload": progress.to_dict(),
                "extensions": {_SOURCE_EXTENSION: {"persistent_event_seq": event.seq}},
            }
        )
    except ContractViolation as error:
        raise _violation(
            "INVALID_TASK_PROGRESS_PROJECTION",
            "TaskEvent cannot be represented as strict WorkProgress v2",
            error.code,
        ) from error
    notification_binding = ProgressNotificationBinding(
        scope=event.scope,
        work_ref=IdentityRef(IdentityKind.TASK, event.task_id),
        correlation_id=event.correlation_id,
        source_producer=source_event.producer,
        source_work_ref=source_event.stream_ref,
        source_authority=WorkSourceAuthority.TASK_CORE,
        progress_producer=progress_event.producer,
        progress_adapter=binding.progress_adapter,
    )
    return TaskProgressProjection(
        task_event=event,
        source_event=source_event,
        progress_event=progress_event,
        notification_binding=notification_binding,
    )


@dataclass(frozen=True, slots=True)
class TaskProgressReturnActivation:
    active: bool
    reason_id: TaskProgressReturnReason
    evidence_id: str | None
    handoff_kind: TaskProgressHandoffKind | None
    handoff_evidence_id: str | None
    lease: TaskProgressReturnLease | None


class TaskProgressReturnLease:
    """Bounded detach-only handle returned by successful activation."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: TaskProgressReturnBridge) -> None:
        self._bridge = bridge

    async def close(self) -> None:
        await self._bridge.close()

    async def drain_voice(self) -> int:
        """Deliver retained voice intents only after foreground becomes safe."""

        return await self._bridge.drain_voice()

    def snapshot(self) -> TaskProgressReturnSnapshot:
        return self._bridge.snapshot()


class TaskProgressReturnBridge:
    """Sequential VB-C projection and origin-return worker."""

    def __init__(
        self,
        *,
        enabled: bool,
        subscription: TaskEventSubscription,
        prepared_source: PreparedTaskProgressSource | None,
        authorization: TaskAuthorizationGrant | None,
        binding: TaskProgressOriginBinding,
        generation_is_current: GenerationIsCurrent,
        arbiter: ProgressNotificationArbiter,
        foreground: ForegroundSupplier,
        voice_sink: VoiceIntentSink,
        text_sink: TextEventSink,
        allow_package_contract_handoff: bool = False,
        validation_capacity: int = 256,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        if (
            type(enabled) is not bool
            or type(allow_package_contract_handoff) is not bool
        ):
            raise _violation(
                "INVALID_TASK_PROGRESS_FLAG",
                "task progress flags must be boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(validation_capacity) is not int or validation_capacity <= 0:
            raise _violation(
                "INVALID_TASK_PROGRESS_CAPACITY",
                "task progress validation capacity must be positive",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._enabled = enabled
        self._subscription = subscription
        self._prepared_source = prepared_source
        self._authorization = authorization
        self._binding = binding
        self._generation_is_current = generation_is_current
        self._arbiter = arbiter
        self._foreground = foreground
        self._voice_sink = voice_sink
        self._text_sink = text_sink
        self._allow_package_contract_handoff = allow_package_contract_handoff
        self._validation_capacity = validation_capacity
        self._clock = clock

        self._lifecycle_lock = asyncio.Lock()
        self._delivery_lock = asyncio.Lock()
        self._source_close_lock = asyncio.Lock()
        self._source_closed = False
        self._state = TaskProgressReturnState.NEW
        self._reason: TaskProgressReturnReason | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._lease: TaskProgressReturnLease | None = None
        self._close_requested = False
        self._source_events = 0
        self._projected_events = 0
        self._unprojected_events = 0
        self._duplicate_events = 0
        self._gap_events = 0
        self._out_of_order_events = 0
        self._conflict_events = 0
        self._voice_intents = 0
        self._voice_drains = 0
        self._text_events = 0
        self._rejected_events = 0
        self._seen_ids: dict[str, bytes] = {}
        self._seen_sequences: dict[int, bytes] = {}
        self._deferred_voice: dict[str, TaskProgressProjection] = {}
        self._next_seq: int | None = None
        self._authority_attempt_id: str | None = None
        self._authority_attempt_number: int | None = None
        self._last_task_event_id: str | None = None
        self._last_task_event_seq: int | None = None
        self._last_progress_event_id: str | None = None
        self._last_source_decision: TaskProgressSourceDecision | None = None
        self._last_source_evidence: str | None = None
        self._arbiter_reason: str | None = None

    async def activate(self) -> TaskProgressReturnActivation:
        async with self._lifecycle_lock:
            if self._close_requested:
                self._state = TaskProgressReturnState.CLOSED
                self._reason = TaskProgressReturnReason.CLOSED_BEFORE_ACTIVATION
                return self._inactive_activation()
            if not self._enabled:
                self._state = TaskProgressReturnState.DISABLED
                self._reason = TaskProgressReturnReason.FEATURE_DISABLED
                return self._inactive_activation()
            if self._state is not TaskProgressReturnState.NEW:
                return TaskProgressReturnActivation(
                    active=self._state is TaskProgressReturnState.ACTIVE,
                    reason_id=(
                        TaskProgressReturnReason.ACTIVATED
                        if self._state is TaskProgressReturnState.ACTIVE
                        else TaskProgressReturnReason.ALREADY_SETTLED
                    ),
                    evidence_id=(
                        _evidence_id(self._binding)
                        if isinstance(self._binding, TaskProgressOriginBinding)
                        else None
                    ),
                    handoff_kind=self._handoff_kind(),
                    handoff_evidence_id=self._handoff_evidence(),
                    lease=self._lease,
                )
            try:
                binding = _canonical_binding(self._binding)
            except TaskProgressReturnViolation:
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.INVALID_BINDING
                return self._inactive_activation()
            if not self._authorize(binding):
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.AUTHORIZATION_REJECTED
                return self._inactive_activation()
            if not self._generation_current(binding):
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.STALE_GENERATION
                return self._inactive_activation()
            if (
                binding.origin_kind is TaskProgressOriginKind.TEXT
                and not self._subscription_matches(binding)
            ):
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.INVALID_BINDING
                return self._inactive_activation()
            prepared = self._prepared_source
            if binding.origin_kind is TaskProgressOriginKind.VOICE and (
                prepared is None or not self._prepared_source_usable(prepared)
            ):
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
                return self._inactive_activation()

            self._owner_loop = asyncio.get_running_loop()
            try:
                started = await self._start_source(binding)
            except asyncio.CancelledError:
                await asyncio.shield(self._close_source(binding))
                raise
            except Exception:
                if self._close_requested:
                    await self._close_source(binding)
                    self._state = TaskProgressReturnState.CLOSED
                    self._reason = TaskProgressReturnReason.CONSUMER_DETACHED
                    return self._inactive_activation()
                self._state = TaskProgressReturnState.FAILED
                self._reason = (
                    TaskProgressReturnReason.HANDOFF_REJECTED
                    if binding.origin_kind is TaskProgressOriginKind.VOICE
                    else TaskProgressReturnReason.SOURCE_FAILED
                )
                await self._close_source(binding)
                return self._inactive_activation()
            if self._close_requested:
                await self._close_source(binding)
                self._state = TaskProgressReturnState.CLOSED
                self._reason = TaskProgressReturnReason.CONSUMER_DETACHED
                return self._inactive_activation()
            if not started:
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = (
                    TaskProgressReturnReason.HANDOFF_REJECTED
                    if binding.origin_kind is TaskProgressOriginKind.VOICE
                    else TaskProgressReturnReason.SOURCE_FAILED
                )
                await self._close_source(binding)
                return self._inactive_activation()
            if (
                binding.origin_kind is TaskProgressOriginKind.VOICE
                and self._uses_exact_authority_source()
            ):
                authority_snapshot = self._subscription.snapshot()
                if (
                    authority_snapshot.segment_start_seq is None
                    or authority_snapshot.attempt_id is None
                    or authority_snapshot.attempt_number is None
                ):
                    self._state = TaskProgressReturnState.FAILED
                    self._reason = TaskProgressReturnReason.HANDOFF_REJECTED
                    await self._close_source(binding)
                    return self._inactive_activation()
                self._next_seq = authority_snapshot.segment_start_seq
                self._authority_attempt_id = authority_snapshot.attempt_id
                self._authority_attempt_number = authority_snapshot.attempt_number
            if not self._authorize(binding):
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.AUTHORIZATION_REJECTED
                await self._close_source(binding)
                return self._inactive_activation()
            if not self._generation_current(binding):
                self._state = TaskProgressReturnState.UNAVAILABLE
                self._reason = TaskProgressReturnReason.STALE_GENERATION
                await self._close_source(binding)
                return self._inactive_activation()
            if self._close_requested:
                await self._close_source(binding)
                self._state = TaskProgressReturnState.CLOSED
                self._reason = TaskProgressReturnReason.CONSUMER_DETACHED
                return self._inactive_activation()

            self._state = TaskProgressReturnState.ACTIVE
            self._reason = TaskProgressReturnReason.ACTIVATED
            self._lease = TaskProgressReturnLease(self)
            assert self._owner_loop is not None
            self._worker = self._owner_loop.create_task(
                self._run(), name=f"live-voice-task-progress:{binding.task_id}"
            )
            return TaskProgressReturnActivation(
                active=True,
                reason_id=TaskProgressReturnReason.ACTIVATED,
                evidence_id=_evidence_id(binding),
                handoff_kind=self._handoff_kind(),
                handoff_evidence_id=self._handoff_evidence(),
                lease=self._lease,
            )

    async def close(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and current_loop is not self._owner_loop:
            raise _violation(
                "TASK_PROGRESS_LOOP_MISMATCH",
                "task progress lease belongs to another event loop",
                ErrorCode.CONFLICT,
            )
        # Preserve detach intent before any cancellable lock or source wait. An
        # activation already blocked in source.start() can then observe the flag,
        # while the retained cleanup task concurrently reaches source.close().
        self._close_requested = True
        if self._state in {
            TaskProgressReturnState.DISABLED,
            TaskProgressReturnState.UNAVAILABLE,
            TaskProgressReturnState.CLOSED,
            TaskProgressReturnState.FAILED,
        }:
            return
        if self._state is TaskProgressReturnState.NEW and self._owner_loop is None:
            self._state = TaskProgressReturnState.CLOSED
            self._reason = TaskProgressReturnReason.CLOSED_BEFORE_ACTIVATION
            return
        self._state = TaskProgressReturnState.DETACHING
        self._reason = TaskProgressReturnReason.CONSUMER_DETACHED
        if self._close_task is None:
            self._close_task = current_loop.create_task(
                self._close_impl(),
                name=f"live-voice-task-progress-close:{self._binding.task_id}",
            )
        close_task = self._close_task
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            # A cancelled waiter must not disturb cleanup that is still running.
            # If the owned task itself was cancelled, release the retry slot.
            if close_task.done():
                async with self._lifecycle_lock:
                    if self._close_task is close_task:
                        self._close_task = None
            raise
        except Exception:
            # Source detach can fail transiently. Preserve DETACHING truth while
            # allowing the exact lease owner to retry the same cleanup.
            async with self._lifecycle_lock:
                if self._close_task is close_task:
                    self._close_task = None
            raise

    async def drain_voice(self) -> int:
        current_loop = asyncio.get_running_loop()
        if self._owner_loop is not None and current_loop is not self._owner_loop:
            raise _violation(
                "TASK_PROGRESS_LOOP_MISMATCH",
                "task progress lease belongs to another event loop",
                ErrorCode.CONFLICT,
            )
        if (
            self._binding.origin_kind is not TaskProgressOriginKind.VOICE
            or self._state is not TaskProgressReturnState.ACTIVE
            or self._close_requested
        ):
            return 0
        async with self._delivery_lock:
            generation_current = self._generation_current(self._binding)
            if (
                self._state is not TaskProgressReturnState.ACTIVE
                or self._close_requested
                or not generation_current
            ):
                if (
                    self._state is TaskProgressReturnState.ACTIVE
                    and not generation_current
                ):
                    self._last_source_decision = (
                        TaskProgressSourceDecision.STALE_GENERATION
                    )
                    self._reject(TaskProgressReturnReason.STALE_GENERATION)
                return 0
            if not self._authorize(self._binding):
                self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
                await self._close_source(self._binding)
                return 0
            try:
                foreground = self._foreground()
                decisions = self._arbiter.drain(
                    self._binding.scope,
                    foreground,
                    max_items=1,
                )
            except Exception:
                self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return 0
            if not decisions:
                return 0
            decision = decisions[0]
            self._arbiter_reason = decision.reason
            if decision.disposition is not NotificationDisposition.DISPLAY_NOW:
                if decision.disposition is NotificationDisposition.REJECTED:
                    self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return 0
            event_id = decision.event_id
            projection = (
                self._deferred_voice.get(event_id) if type(event_id) is str else None
            )
            if projection is None:
                self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return 0
            generation_current = self._generation_current(self._binding)
            if (
                self._close_requested
                or self._state is not TaskProgressReturnState.ACTIVE
                or not generation_current
            ):
                if not generation_current:
                    self._last_source_decision = (
                        TaskProgressSourceDecision.STALE_GENERATION
                    )
                    self._reject(TaskProgressReturnReason.STALE_GENERATION)
                return 0
            if not self._authorize(self._binding):
                self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
                await self._close_source(self._binding)
                return 0
            if not await self._emit_voice_intent(projection, decision):
                return 0
            self._deferred_voice.pop(projection.progress_event.event_id, None)
            self._voice_drains += 1
            if projection.task_event.event_type == "task.terminal":
                self._settle(
                    TaskProgressReturnState.CLOSED,
                    TaskProgressReturnReason.TERMINAL_DELIVERED,
                )
            return 1

    def snapshot(self) -> TaskProgressReturnSnapshot:
        worker = self._worker
        return TaskProgressReturnSnapshot(
            enabled=self._enabled,
            state=self._state,
            reason_id=self._reason,
            handoff_kind=self._handoff_kind(),
            handoff_evidence_id=self._handoff_evidence(),
            worker_pending=worker is not None and not worker.done(),
            source_events=self._source_events,
            projected_events=self._projected_events,
            unprojected_events=self._unprojected_events,
            duplicate_events=self._duplicate_events,
            gap_events=self._gap_events,
            out_of_order_events=self._out_of_order_events,
            conflict_events=self._conflict_events,
            voice_intents=self._voice_intents,
            pending_voice_intents=len(self._deferred_voice),
            voice_drains=self._voice_drains,
            text_events=self._text_events,
            rejected_events=self._rejected_events,
            last_task_event_id=self._last_task_event_id,
            last_task_event_seq=self._last_task_event_seq,
            last_progress_event_id=self._last_progress_event_id,
            last_source_decision_id=self._last_source_decision,
            last_source_evidence_id=self._last_source_evidence,
            arbiter_reason=self._arbiter_reason,
        )

    async def _run(self) -> None:
        binding = self._binding
        try:
            while not self._close_requested:
                try:
                    event = await self._next_source_event(binding)
                except StopAsyncIteration:
                    if self._close_requested:
                        return
                    self._settle(
                        TaskProgressReturnState.CLOSED,
                        TaskProgressReturnReason.SOURCE_EXHAUSTED,
                    )
                    return
                except asyncio.CancelledError:
                    if self._close_requested:
                        return
                    self._settle(
                        TaskProgressReturnState.FAILED,
                        TaskProgressReturnReason.SOURCE_FAILED,
                    )
                    raise
                except (FormalTaskViolation, TaskProgressReturnViolation):
                    self._settle(
                        TaskProgressReturnState.FAILED,
                        TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION,
                    )
                    return
                except Exception:
                    self._settle(
                        TaskProgressReturnState.FAILED,
                        TaskProgressReturnReason.SOURCE_FAILED,
                    )
                    return
                if self._close_requested:
                    return
                if not self._authorize(binding):
                    self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
                    return
                if not await self._consume(event):
                    return
        finally:
            try:
                await self._close_source(binding)
            except Exception:
                if self._state not in {
                    TaskProgressReturnState.CLOSED,
                    TaskProgressReturnState.FAILED,
                }:
                    self._settle(
                        TaskProgressReturnState.FAILED,
                        TaskProgressReturnReason.SOURCE_FAILED,
                    )

    async def _consume(self, event: object) -> bool:
        binding = self._binding
        if not isinstance(event, PersistentTaskEvent):
            self._last_source_decision = TaskProgressSourceDecision.INVALID_EVENT
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        self._source_events += 1
        self._last_task_event_id = event.event_id
        self._last_task_event_seq = event.seq
        self._last_source_evidence = _evidence_id(binding, event)
        if (
            event.task_id != binding.task_id
            or event.scope != binding.scope
            or event.correlation_id != binding.correlation_id
        ):
            self._last_source_decision = TaskProgressSourceDecision.BINDING_REJECTED
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        if (
            binding.origin_kind is TaskProgressOriginKind.VOICE
            and self._uses_exact_authority_source()
            and event.attempt_id != self._authority_attempt_id
        ):
            self._last_source_decision = TaskProgressSourceDecision.STALE_ATTEMPT
            self._reject(TaskProgressReturnReason.STALE_ATTEMPT)
            return False
        if (
            binding.origin_kind is TaskProgressOriginKind.VOICE
            and self._uses_exact_authority_source()
            and event.event_type == "task.retry_accepted"
            and event.details.get("attempt_number") != self._authority_attempt_number
        ):
            self._last_source_decision = TaskProgressSourceDecision.INVALID_EVENT
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        try:
            fingerprint = canonical_json_bytes(event.to_dict())
        except (ContractViolation, TypeError, ValueError):
            self._last_source_decision = TaskProgressSourceDecision.INVALID_EVENT
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        known_id = self._seen_ids.get(event.event_id)
        if known_id is not None:
            if known_id == fingerprint:
                self._duplicate_events += 1
                self._last_source_decision = (
                    TaskProgressSourceDecision.DUPLICATE_IGNORED
                )
                return True
            self._conflict_events += 1
            self._last_source_decision = TaskProgressSourceDecision.EVENT_ID_CONFLICT
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        known_sequence = self._seen_sequences.get(event.seq)
        if known_sequence is not None:
            self._conflict_events += 1
            self._last_source_decision = TaskProgressSourceDecision.SEQUENCE_CONFLICT
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        if self._next_seq is None:
            expected_seq = (
                0 if binding.origin_kind is TaskProgressOriginKind.VOICE else event.seq
            )
        else:
            expected_seq = self._next_seq
        if event.seq != expected_seq:
            if event.seq > expected_seq:
                self._gap_events += 1
                self._last_source_decision = TaskProgressSourceDecision.SEQUENCE_GAP
            else:
                self._out_of_order_events += 1
                self._last_source_decision = (
                    TaskProgressSourceDecision.SEQUENCE_OUT_OF_ORDER
                )
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        if len(self._seen_ids) >= self._validation_capacity:
            self._last_source_decision = TaskProgressSourceDecision.INVALID_EVENT
            self._reject(TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION)
            return False
        if not self._generation_current(binding):
            self._last_source_decision = TaskProgressSourceDecision.STALE_GENERATION
            self._reject(TaskProgressReturnReason.STALE_GENERATION)
            return False
        if event.event_type not in _PROJECTABLE_EVENTS:
            if (
                binding.origin_kind is TaskProgressOriginKind.VOICE
                and not self._uses_exact_authority_source()
            ):
                self._last_source_decision = TaskProgressSourceDecision.NOT_PROJECTABLE
                self._reject(TaskProgressReturnReason.SOURCE_EVENT_NOT_PROJECTABLE)
                return False
            if (
                binding.origin_kind is TaskProgressOriginKind.VOICE
                and event.event_type not in _NO_PROJECTION_EVENTS
            ):
                self._last_source_decision = TaskProgressSourceDecision.NOT_PROJECTABLE
                self._reject(TaskProgressReturnReason.SOURCE_EVENT_NOT_PROJECTABLE)
                return False
            if binding.origin_kind is TaskProgressOriginKind.VOICE:
                if not await self._advance_voice_without_projection(event):
                    return False
            self._seen_ids[event.event_id] = fingerprint
            self._seen_sequences[event.seq] = fingerprint
            self._next_seq = event.seq + 1
            self._unprojected_events += 1
            self._last_source_decision = TaskProgressSourceDecision.UNPROJECTED_ADVANCE
            return True
        try:
            projection = project_task_progress_event(event, binding)
        except TaskProgressReturnViolation as error:
            reason = (
                TaskProgressReturnReason.SOURCE_EVENT_NOT_PROJECTABLE
                if error.reason == "TASK_PROGRESS_SOURCE_EVENT_NOT_PROJECTABLE"
                else TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION
            )
            self._last_source_decision = (
                TaskProgressSourceDecision.NOT_PROJECTABLE
                if reason is TaskProgressReturnReason.SOURCE_EVENT_NOT_PROJECTABLE
                else TaskProgressSourceDecision.INVALID_EVENT
            )
            self._reject(reason)
            return False

        self._seen_ids[event.event_id] = fingerprint
        self._seen_sequences[event.seq] = fingerprint
        self._next_seq = event.seq + 1
        self._projected_events += 1
        self._last_progress_event_id = projection.progress_event.event_id
        self._last_source_decision = TaskProgressSourceDecision.PROJECTED
        if binding.origin_kind is TaskProgressOriginKind.VOICE:
            if not await self._deliver_voice(projection):
                return False
        else:
            if not await self._deliver_text(projection):
                return False
        if event.event_type == "task.terminal":
            if (
                binding.origin_kind is TaskProgressOriginKind.VOICE
                and projection.progress_event.event_id in self._deferred_voice
            ):
                return False
            self._settle(
                TaskProgressReturnState.CLOSED,
                TaskProgressReturnReason.TERMINAL_DELIVERED,
            )
            return False
        return True

    async def _advance_voice_without_projection(
        self,
        event: PersistentTaskEvent,
    ) -> bool:
        async with self._delivery_lock:
            binding = self._binding
            if (
                self._close_requested
                or self._state is not TaskProgressReturnState.ACTIVE
                or not self._uses_exact_authority_source()
            ):
                return False
            if not self._authorize(binding):
                self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
                return False
            if not self._generation_current(binding):
                self._last_source_decision = TaskProgressSourceDecision.STALE_GENERATION
                self._reject(TaskProgressReturnReason.STALE_GENERATION)
                return False

            source_producer = ProducerRef(
                component="task_core",
                instance_id=binding.source_instance_id,
                authority="task_core",
            )
            work_ref = IdentityRef(IdentityKind.TASK, binding.task_id)
            notification_binding = ProgressNotificationBinding(
                scope=binding.scope,
                work_ref=work_ref,
                correlation_id=binding.correlation_id,
                source_producer=source_producer,
                source_work_ref=work_ref,
                source_authority=WorkSourceAuthority.TASK_CORE,
                progress_producer=binding.progress_producer,
                progress_adapter=binding.progress_adapter,
            )
            advance = _mint_verified_no_projection_advance(event, notification_binding)
            try:
                decision = self._arbiter._advance_without_projection(advance)
            except Exception:
                self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return False
            self._arbiter_reason = decision.reason
            if decision.disposition in {
                NoProjectionAdvanceDisposition.ADVANCED,
                NoProjectionAdvanceDisposition.DUPLICATE,
            }:
                return True
            if decision.disposition is NoProjectionAdvanceDisposition.BACKPRESSURE:
                self._reject(TaskProgressReturnReason.ARBITER_BACKPRESSURE)
                return False
            if decision.disposition is NoProjectionAdvanceDisposition.FEATURE_DISABLED:
                self._reject(TaskProgressReturnReason.ARBITER_FEATURE_DISABLED)
                return False
            self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
            return False

    async def _deliver_voice(self, projection: TaskProgressProjection) -> bool:
        async with self._delivery_lock:
            if (
                self._close_requested
                or self._state is not TaskProgressReturnState.ACTIVE
            ):
                return False
            binding = self._binding
            if not self._authorize(binding):
                self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
                return False
            try:
                if projection.task_event.event_type == "task.retry_accepted":
                    baseline = _mint_verified_attempt_epoch_baseline(
                        projection.task_event,
                        projection.notification_binding,
                    )
                    self._arbiter._begin_attempt_epoch(baseline)
                foreground = self._foreground()
                decision = self._arbiter.offer(
                    projection.source_event,
                    projection.progress_event,
                    foreground,
                    projection.notification_binding,
                )
            except Exception:
                self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return False
            self._arbiter_reason = decision.reason
            if decision.disposition is NotificationDisposition.DUPLICATE:
                self._duplicate_events += 1
                return True
            if decision.disposition is NotificationDisposition.REJECTED:
                self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return False
            if decision.disposition is NotificationDisposition.BACKPRESSURE:
                self._reject(TaskProgressReturnReason.ARBITER_BACKPRESSURE)
                return False
            if decision.disposition is NotificationDisposition.FEATURE_DISABLED:
                self._reject(TaskProgressReturnReason.ARBITER_FEATURE_DISABLED)
                return False
            if decision.disposition is NotificationDisposition.DEFERRED:
                retained_id = decision.retained_event_id
                if retained_id == projection.progress_event.event_id:
                    self._deferred_voice.clear()
                    self._deferred_voice[retained_id] = projection
                elif retained_id not in self._deferred_voice:
                    self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                    return False
                return True
            if decision.disposition is not NotificationDisposition.DISPLAY_NOW:
                self._reject(TaskProgressReturnReason.ARBITER_REJECTED)
                return False
            if not self._generation_current(binding):
                self._last_source_decision = TaskProgressSourceDecision.STALE_GENERATION
                self._reject(TaskProgressReturnReason.STALE_GENERATION)
                return False
            delivered = await self._emit_voice_intent(projection, decision)
            if delivered:
                self._deferred_voice.clear()
            return delivered

    async def _emit_voice_intent(
        self,
        projection: TaskProgressProjection,
        decision: NotificationDecision,
    ) -> bool:
        binding = self._binding
        if self._close_requested or self._state is not TaskProgressReturnState.ACTIVE:
            return False
        if not self._authorize(binding):
            self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
            return False
        if not self._generation_current(binding):
            self._last_source_decision = TaskProgressSourceDecision.STALE_GENERATION
            self._reject(TaskProgressReturnReason.STALE_GENERATION)
            return False
        intent = TaskProgressNotificationIntent(
            origin=binding,
            task_event=projection.task_event,
            source_event=projection.source_event,
            progress_event=projection.progress_event,
            decision=decision,
            evidence_id=_evidence_id(binding, projection.task_event),
        )
        try:
            await self._voice_sink(intent)
        except Exception:
            self._reject(TaskProgressReturnReason.VOICE_SINK_FAILED)
            return False
        if self._close_requested:
            return False
        if not self._authorize(binding):
            self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
            return False
        if not self._generation_current(binding):
            self._last_source_decision = TaskProgressSourceDecision.STALE_GENERATION
            self._reject(TaskProgressReturnReason.STALE_GENERATION)
            return False
        if not self._arbiter.acknowledge(
            binding.scope,
            projection.notification_binding.work_ref,
            projection.progress_event.event_id,
        ):
            self._reject(TaskProgressReturnReason.ARBITER_ACK_FAILED)
            return False
        self._voice_intents += 1
        return True

    async def _deliver_text(self, projection: TaskProgressProjection) -> bool:
        async with self._delivery_lock:
            binding = self._binding
            if (
                self._close_requested
                or self._state is not TaskProgressReturnState.ACTIVE
            ):
                return False
            if not self._authorize(binding):
                self._reject(TaskProgressReturnReason.AUTHORIZATION_REJECTED)
                return False
            if not self._generation_current(binding):
                self._last_source_decision = TaskProgressSourceDecision.STALE_GENERATION
                self._reject(TaskProgressReturnReason.STALE_GENERATION)
                return False
            event = TaskProgressTextEvent(
                origin=binding,
                task_event=projection.task_event,
                source_event=projection.source_event,
                progress_event=projection.progress_event,
                evidence_id=_evidence_id(binding, projection.task_event),
            )
            try:
                await self._text_sink(event)
            except Exception:
                self._reject(TaskProgressReturnReason.TEXT_SINK_FAILED)
                return False
            self._text_events += 1
            return True

    async def _close_impl(self) -> None:
        async with self._delivery_lock:
            pass
        await self._close_source(self._binding)
        worker = self._worker
        if worker is not None and worker is not asyncio.current_task():
            await asyncio.shield(worker)
        self._settle(
            TaskProgressReturnState.CLOSED,
            TaskProgressReturnReason.CONSUMER_DETACHED,
        )

    async def _start_source(self, binding: TaskProgressOriginBinding) -> bool:
        if binding.origin_kind is TaskProgressOriginKind.TEXT:
            return await self._subscription.start()
        prepared = self._prepared_source
        assert prepared is not None
        return await prepared.start()

    async def _next_source_event(
        self, binding: TaskProgressOriginBinding
    ) -> PersistentTaskEvent:
        if binding.origin_kind is TaskProgressOriginKind.TEXT:
            return await self._subscription.next_event()
        prepared = self._prepared_source
        assert prepared is not None
        return await prepared.next_event()

    async def _close_source(self, binding: TaskProgressOriginBinding) -> None:
        async with self._source_close_lock:
            if self._source_closed:
                return
            if binding.origin_kind is TaskProgressOriginKind.TEXT:
                await self._subscription.close()
                self._source_closed = True
                return
            prepared = self._prepared_source
            if prepared is not None:
                await prepared.close()
            self._source_closed = True

    def _authorize(self, binding: TaskProgressOriginBinding) -> bool:
        authorization = self._authorization
        if type(authorization) is not TaskAuthorizationGrant:
            return False
        try:
            authorization.authorize(
                scope=binding.scope,
                operation="task.events",
                command_id=None,
                target_task_id=binding.task_id,
                required_capabilities=_EVENTS_CAPABILITY,
                destructive=False,
                now=self._clock(),
            )
        except (FormalTaskViolation, TypeError, ValueError):
            return False
        return True

    def _generation_current(self, binding: TaskProgressOriginBinding) -> bool:
        try:
            return self._generation_is_current(binding) is True
        except Exception:
            return False

    def _prepared_source_usable(self, prepared: PreparedTaskProgressSource) -> bool:
        if prepared.__class__ is TaskEventAuthorityProgressSource:
            authorization = self._authorization
            return (
                prepared._subscription is self._subscription
                and type(prepared._evidence_id) is str
                and bool(prepared._evidence_id.strip())
                and prepared._task_id == self._binding.task_id
                and prepared._scope == self._binding.scope
                and type(authorization) is TaskAuthorizationGrant
                and prepared._authorization_fingerprint
                == _authorization_fingerprint(authorization)
            )
        try:
            same_subscription = prepared.subscription is self._subscription
            handoff_kind = prepared.handoff_kind
            evidence_id = prepared.evidence_id
        except Exception:
            return False
        if (
            not same_subscription
            or not isinstance(handoff_kind, TaskProgressHandoffKind)
            or type(evidence_id) is not str
            or not evidence_id.strip()
        ):
            return False
        return (
            handoff_kind is TaskProgressHandoffKind.PACKAGE_CONTRACT_TEST
            and self._allow_package_contract_handoff
        )

    def _uses_exact_authority_source(self) -> bool:
        prepared = self._prepared_source
        return (
            prepared is not None
            and prepared.__class__ is TaskEventAuthorityProgressSource
            and prepared._subscription is self._subscription
            and prepared._task_id == self._binding.task_id
            and prepared._scope == self._binding.scope
            and type(self._authorization) is TaskAuthorizationGrant
            and prepared._authorization_fingerprint
            == _authorization_fingerprint(self._authorization)
        )

    def _subscription_matches(self, binding: TaskProgressOriginBinding) -> bool:
        try:
            snapshot = self._subscription.snapshot()
            return snapshot.task_id == binding.task_id
        except Exception:
            return False

    def _inactive_activation(self) -> TaskProgressReturnActivation:
        evidence = (
            _evidence_id(self._binding)
            if isinstance(self._binding, TaskProgressOriginBinding)
            else None
        )
        assert self._reason is not None
        return TaskProgressReturnActivation(
            active=False,
            reason_id=self._reason,
            evidence_id=evidence,
            handoff_kind=self._handoff_kind(),
            handoff_evidence_id=self._handoff_evidence(),
            lease=None,
        )

    def _handoff_kind(self) -> TaskProgressHandoffKind | None:
        if (
            isinstance(self._binding, TaskProgressOriginBinding)
            and self._binding.origin_kind is TaskProgressOriginKind.TEXT
        ):
            return None
        prepared = self._prepared_source
        try:
            value = prepared.handoff_kind if prepared is not None else None
        except Exception:
            return None
        return value if isinstance(value, TaskProgressHandoffKind) else None

    def _handoff_evidence(self) -> str | None:
        if (
            isinstance(self._binding, TaskProgressOriginBinding)
            and self._binding.origin_kind is TaskProgressOriginKind.TEXT
        ):
            return None
        prepared = self._prepared_source
        try:
            value = prepared.evidence_id if prepared is not None else None
        except Exception:
            return None
        return value if type(value) is str and value.strip() else None

    def _reject(self, reason: TaskProgressReturnReason) -> None:
        self._rejected_events += 1
        self._settle(TaskProgressReturnState.FAILED, reason)

    def _settle(
        self, state: TaskProgressReturnState, reason: TaskProgressReturnReason
    ) -> None:
        if self._state is TaskProgressReturnState.CLOSED:
            return
        self._state = state
        self._reason = reason


__all__ = [
    "ForegroundSupplier",
    "GenerationIsCurrent",
    "PreparedTaskProgressSource",
    "TaskEventAuthorityProgressSource",
    "TaskProgressHandoffKind",
    "TaskProgressNotificationIntent",
    "TaskProgressOriginBinding",
    "TaskProgressOriginKind",
    "TaskProgressProjection",
    "TaskProgressReturnActivation",
    "TaskProgressReturnBridge",
    "TaskProgressReturnLease",
    "TaskProgressReturnReason",
    "TaskProgressReturnSnapshot",
    "TaskProgressReturnState",
    "TaskProgressReturnViolation",
    "TaskProgressSourceDecision",
    "TaskProgressTextEvent",
    "TextEventSink",
    "VoiceIntentSink",
    "project_task_progress_event",
]
