# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Product-consumable Agent Bridge + Conversation Runtime composition seam."""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CommandEnvelope,
    ErrorCode,
    EventEnvelope,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    WorkProgressEventV2,
    WorkState,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent
from jiuwenswarm.server.live_voice.agent_bridge_runtime import (
    AgentBridgeCompletionHandle,
    AgentBridgeDispatchReservation,
    AgentBridgeRuntime,
    AgentBridgeRuntimeSnapshot,
    AgentBridgeRuntimeViolation,
    AgentEventDelivery,
    WorkProgressDelivery,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    ConversationRuntimeViolation,
    InteractionState,
    ResponseState,
    TurnState,
)
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    BargeInResult,
    ConversationEffect,
    ConversationRuntimeLoop,
    ConversationRuntimeLoopSnapshot,
    ConversationRuntimeLoopViolation,
    PresentationHistoryIntent,
    ResponseCancelResult,
)
from jiuwenswarm.server.live_voice.formal_history_writer import (
    SessionFormalHistoryWriter,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_agent_adapter import (
    JiuWenSwarmAgentAdapter,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    FormalAgentFacade,
    HarnessRoundBinding,
    HarnessRoundHandle,
    HarnessRoundReservation,
    HarnessRoundSnapshot,
    HarnessRoundViolation,
    JiuWenSwarmRoundHarness,
    RoundCancelResult,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationState,
    PresentationSurface,
    PresentationUnit,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressNotificationIntent,
    TaskProgressOriginKind,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)


_MAX_NOTIFICATION_CONSUMER_ID_CHARS = 256
_MAX_NOTIFICATION_CONSUMER_ID_UTF8_BYTES = 1024
_MAX_EFFECT_ID_CHARS = 256
_MAX_EFFECT_ID_UTF8_BYTES = 512
_MAX_EFFECTS_PER_REQUEST = 3


class AgentConversationRuntimeViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class AgentConversationShutdownStatus(StrEnum):
    CLOSED = "closed"
    PENDING = "pending"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentConversationHandle:
    request_id: str
    round_id: str
    response_ref: ResponseRef
    completion: AgentBridgeCompletionHandle


@dataclass(frozen=True, slots=True)
class AgentConversationNotification:
    kind: str
    request_id: str
    round_id: str
    response_ref: ResponseRef
    agent_event: AgentEvent | None = None
    source_event: EventEnvelope | None = None
    progress_event: EventEnvelope | None = None
    presentation_unit: PresentationUnit | None = None
    error_reason: str | None = None
    publish_seq: int | None = None


@dataclass(frozen=True, slots=True)
class AgentConversationNotificationLease:
    """Exact infrastructure subscription lease for one transport generation."""

    owner_instance_id: str
    consumer_id: str
    connection_epoch: int
    lease_id: str


@dataclass(frozen=True, slots=True)
class AgentConversationEffectClaim:
    """Retained exact-consumer delivery of declarative conversation effects."""

    claim_id: str
    consumer_id: str
    connection_epoch: int
    effects: tuple[ConversationEffect, ...]
    replayed: bool
    acknowledged: bool


@dataclass(frozen=True, slots=True)
class AgentConversationEffectAckResult:
    """Exact acknowledgement of one retained effect-delivery claim."""

    claim_id: str
    effect_ids: tuple[str, ...]
    accepted: bool
    replayed: bool


@dataclass(frozen=True, slots=True)
class _QueuedNotification:
    publish_seq: int
    notification: AgentConversationNotification


class _NotificationBufferClosed(RuntimeError):
    pass


class _NotificationConsumerDetached(RuntimeError):
    pass


class _BoundedNotificationBuffer:
    """Lossy observer lane plus a bounded, non-blocking critical reserve."""

    def __init__(self, *, observer_capacity: int, critical_capacity: int) -> None:
        self._observer_capacity = observer_capacity
        self._critical_capacity = critical_capacity
        self._observer: deque[_QueuedNotification] = deque()
        self._critical: deque[_QueuedNotification] = deque()
        self._critical_keys: set[tuple[str, str]] = set()
        self._ready = asyncio.Event()
        self._next_publish_seq = 0
        self._delivered_total = 0
        self._dropped_observer_total = 0
        self._last_delivered_seq: int | None = None
        self._critical_invariant_failures = 0
        self._closed = False

    def publish(
        self,
        notification: AgentConversationNotification,
        *,
        critical_key: tuple[str, str] | None = None,
    ) -> None:
        if self._closed:
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_STREAM_CLOSED",
                "notification publication cannot continue after producer shutdown",
                ErrorCode.CONFLICT,
            )
        if critical_key is not None:
            if critical_key in self._critical_keys:
                self._critical_invariant_failures += 1
                raise AgentConversationRuntimeViolation(
                    "DUPLICATE_CRITICAL_NOTIFICATION",
                    "a retained presentation or terminal notification must be unique",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if len(self._critical_keys) >= self._critical_capacity:
                self._critical_invariant_failures += 1
                raise AgentConversationRuntimeViolation(
                    "CRITICAL_NOTIFICATION_RESERVE_EXHAUSTED",
                    "the bounded critical notification reserve is exhausted",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
        publish_seq = self._next_publish_seq
        self._next_publish_seq += 1
        queued = _QueuedNotification(
            publish_seq=publish_seq,
            notification=replace(notification, publish_seq=publish_seq),
        )
        if critical_key is not None:
            self._critical_keys.add(critical_key)
            self._critical.append(queued)
        else:
            if len(self._observer) >= self._observer_capacity:
                self._observer.popleft()
                self._dropped_observer_total += 1
            self._observer.append(queued)
        self._ready.set()

    async def get(
        self,
        *,
        lease_active: Callable[[], bool] | None = None,
        detached: asyncio.Event | None = None,
    ) -> AgentConversationNotification:
        while True:
            if lease_active is not None and not lease_active():
                raise _NotificationConsumerDetached
            queued = self._pop_next()
            if queued is not None:
                self._delivered_total += 1
                self._last_delivered_seq = queued.publish_seq
                return queued.notification
            if self._closed:
                raise _NotificationBufferClosed
            if detached is None:
                await self._ready.wait()
                continue
            ready_wait = asyncio.create_task(self._ready.wait())
            detached_wait = asyncio.create_task(detached.wait())
            try:
                await asyncio.wait(
                    (ready_wait, detached_wait),
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for waiter in (ready_wait, detached_wait):
                    if not waiter.done():
                        waiter.cancel()
                await asyncio.gather(
                    ready_wait,
                    detached_wait,
                    return_exceptions=True,
                )

    def close(self) -> None:
        self._closed = True
        self._ready.set()

    def discard_pending_presentations(self) -> int:
        """Remove output notices invalidated by retained CR shutdown."""

        retained = deque(
            queued
            for queued in self._critical
            if queued.notification.presentation_unit is None
        )
        discarded = len(self._critical) - len(retained)
        self._critical = retained
        if not self._observer and not self._critical:
            self._ready.clear()
        return discarded

    def qsize(self) -> int:
        return len(self._observer) + len(self._critical)

    @property
    def queued_observer(self) -> int:
        return len(self._observer)

    @property
    def queued_critical(self) -> int:
        return len(self._critical)

    @property
    def observer_capacity(self) -> int:
        return self._observer_capacity

    @property
    def critical_capacity(self) -> int:
        return self._critical_capacity

    @property
    def published_total(self) -> int:
        return self._next_publish_seq

    @property
    def delivered_total(self) -> int:
        return self._delivered_total

    @property
    def dropped_observer_total(self) -> int:
        return self._dropped_observer_total

    @property
    def last_publish_seq(self) -> int | None:
        if self._next_publish_seq == 0:
            return None
        return self._next_publish_seq - 1

    @property
    def last_delivered_seq(self) -> int | None:
        return self._last_delivered_seq

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def critical_invariant_failures(self) -> int:
        return self._critical_invariant_failures

    def _pop_next(self) -> _QueuedNotification | None:
        queued: _QueuedNotification | None
        if self._observer and self._critical:
            if self._observer[0].publish_seq < self._critical[0].publish_seq:
                queued = self._observer.popleft()
            else:
                queued = self._critical.popleft()
        elif self._observer:
            queued = self._observer.popleft()
        elif self._critical:
            queued = self._critical.popleft()
        else:
            self._ready.clear()
            return None
        if not self._observer and not self._critical:
            self._ready.clear()
        return queued


@dataclass(frozen=True, slots=True)
class PresentationAckResult:
    ack: PresentationAck
    accepted: bool
    replayed: bool
    history_records_written: int
    history_pending: bool


@dataclass(frozen=True, slots=True)
class AgentConversationShutdownResult:
    status: AgentConversationShutdownStatus
    detail: str
    final_drain_lease: AgentConversationNotificationLease | None = None


@dataclass(frozen=True, slots=True)
class AgentConversationRuntimeSnapshot:
    enabled: bool
    started: bool
    accepting: bool
    closed: bool
    closing: bool
    retained_admissions: int
    active_requests: tuple[str, ...]
    queued_notifications: int
    notification_observer_capacity: int
    notification_critical_capacity: int
    queued_observer_notifications: int
    queued_critical_notifications: int
    published_notifications: int
    delivered_notifications: int
    dropped_observer_notifications: int
    last_notification_publish_seq: int | None
    last_notification_delivered_seq: int | None
    notification_stream_closed: bool
    active_notification_consumer: tuple[str, int] | None
    notification_leases_attached: int
    notification_leases_detached: int
    discarded_invalidated_presentations: int
    critical_notification_invariant_failures: int
    pending_conversation_effects: int
    unacknowledged_effect_claims: int
    pending_history_intents: int
    conversation: ConversationRuntimeLoopSnapshot
    bridge: AgentBridgeRuntimeSnapshot
    harness: HarnessRoundSnapshot


class FormalHistoryWriter(Protocol):
    async def persist_user(self, commit: TurnCommit, *, channel_id: str) -> bool: ...

    async def persist_assistant(
        self,
        intent: PresentationHistoryIntent,
        *,
        session_id: str,
        channel_id: str,
    ) -> tuple[bool, ...]: ...


@dataclass(slots=True)
class _AdmissionOutcome:
    handle: AgentConversationHandle | None = None
    error: BaseException | None = None


@dataclass(slots=True)
class _AdmissionEntry:
    fingerprint: bytes
    harness_reservation: HarnessRoundReservation
    bridge_reservation: AgentBridgeDispatchReservation
    outcome: asyncio.Future[_AdmissionOutcome]
    coordinator: asyncio.Task[None] | None


@dataclass(slots=True)
class _CommittedTurnSubmissionEntry:
    fingerprint: bytes
    commit: TurnCommit
    outcome: asyncio.Future[_AdmissionOutcome]
    coordinator: asyncio.Task[None] | None


@dataclass(slots=True)
class _PresentationAckEntry:
    ack: PresentationAck
    outcome: asyncio.Future[BaseException | None]
    coordinator: asyncio.Task[None] | None


@dataclass(slots=True)
class _NotificationLeaseRecord:
    lease: AgentConversationNotificationLease
    detached: asyncio.Event
    active: bool = True
    drain_after_close: bool = False


@dataclass(slots=True)
class _ConversationEffectClaimEntry:
    claim_id: str
    lease_id: str
    limit: int | None
    outcome: asyncio.Future[BaseException | None]
    coordinator: asyncio.Task[None] | None
    effects: tuple[ConversationEffect, ...] = ()
    acknowledged: bool = False
    superseded: bool = False


@dataclass(frozen=True, slots=True)
class _TurnIdentityClaim:
    interaction_id: str
    turn_id: str
    commit: TurnCommit | None
    product_request_id: str | None


@dataclass(slots=True)
class _ResponseOutputState:
    request_id: str
    commit: TurnCommit
    channel_id: str
    handle: HarnessRoundHandle
    unit_contents: dict[str, bytes]
    total_utf8: int = 0
    usable_finals: int = 0
    terminal_outcome: TerminalOutcome | None = None
    terminal_event: EventEnvelope | None = None


class AgentConversationRuntime:
    """Strict two-phase composition without exposing raw mutable authorities."""

    def __init__(
        self,
        scope: ScopeRef,
        *,
        instance_id: str,
        facade: FormalAgentFacade | None,
        enabled: bool = True,
        dispatch_capacity: int = 32,
        output_capacity: int = 64,
        max_concurrency: int = 4,
        max_requests: int = 256,
        notification_capacity: int = 64,
        reservation_ttl_seconds: float = 5.0,
        history_writer: FormalHistoryWriter | None = None,
        harness: JiuWenSwarmRoundHarness | None = None,
        bridge: AgentBridgeRuntime | None = None,
        response_generation_owner: Callable[[str, int], int] | None = None,
    ) -> None:
        if not isinstance(scope, ScopeRef):
            raise AgentConversationRuntimeViolation(
                "INVALID_COMPOSITION_SCOPE",
                "composition requires a canonical ScopeRef",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise AgentConversationRuntimeViolation(
                "INVALID_COMPOSITION_INSTANCE",
                "instance_id must be non-empty",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(enabled) is not bool:
            raise AgentConversationRuntimeViolation(
                "INVALID_FEATURE_FLAG",
                "enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        for name, value in (
            ("max_requests", max_requests),
            ("notification_capacity", notification_capacity),
        ):
            if type(value) is not int or value <= 0:
                raise AgentConversationRuntimeViolation(
                    "INVALID_COMPOSITION_CAPACITY",
                    f"{name} must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
        self._scope = scope
        self._instance_id = instance_id
        self._facade = facade
        self._enabled = enabled
        self._cr = ConversationRuntimeLoop(
            scope,
            enabled=enabled,
            response_generation_owner=response_generation_owner,
        )
        self._bridge = bridge or AgentBridgeRuntime(
            instance_id=f"{instance_id}.bridge",
            enabled=enabled,
            dispatch_capacity=dispatch_capacity,
            output_capacity=output_capacity,
            max_concurrency=max_concurrency,
            max_requests=max_requests,
        )
        self._harness = harness or JiuWenSwarmRoundHarness(
            instance_id=f"{instance_id}.harness",
            enabled=enabled,
            max_reservations=max_requests,
            max_active_rounds=max_concurrency,
            output_capacity=output_capacity,
            reservation_ttl_seconds=reservation_ttl_seconds,
        )
        self._history_writer = history_writer or SessionFormalHistoryWriter()
        self._max_requests = max_requests
        self._notifications = _BoundedNotificationBuffer(
            observer_capacity=notification_capacity,
            critical_capacity=2 * max_requests,
        )
        self._commits: dict[str, TurnCommit] = {}
        self._turn_identity_claims: dict[str, _TurnIdentityClaim] = {}
        self._commit_identity_claims: dict[str, _TurnIdentityClaim] = {}
        self._committed_turn_submissions: dict[str, _CommittedTurnSubmissionEntry] = {}
        self._submitted_turn_bindings: dict[tuple[str, str], str] = {}
        self._admissions: dict[str, _AdmissionEntry] = {}
        self._handles: dict[str, AgentConversationHandle] = {}
        self._round_handles: dict[str, HarnessRoundHandle] = {}
        self._outputs: dict[ResponseRef, _ResponseOutputState] = {}
        self._ack_results: dict[
            tuple[ResponseRef, PresentationSurface, int],
            tuple[PresentationAck, PresentationAckResult],
        ] = {}
        self._ack_entries: dict[
            tuple[ResponseRef, PresentationSurface, int],
            _PresentationAckEntry,
        ] = {}
        self._pending_history: dict[
            tuple[ResponseRef, PresentationSurface, int],
            tuple[PresentationHistoryIntent, str, str],
        ] = {}
        self._pending_user_history: dict[str, tuple[TurnCommit, str]] = {}
        self._history_tasks: set[asyncio.Task[None]] = set()
        self._notification_consumer_epochs: dict[str, int] = {}
        self._active_notification_lease: _NotificationLeaseRecord | None = None
        self._final_notification_drain_lease: _NotificationLeaseRecord | None = None
        self._notification_leases_attached = 0
        self._notification_leases_detached = 0
        self._notification_final_drain_leases_issued = 0
        self._discarded_invalidated_presentations = 0
        self._effect_backlog: deque[ConversationEffect] = deque()
        self._effect_backlog_ids: set[str] = set()
        self._effect_claims: dict[str, _ConversationEffectClaimEntry] = {}
        self._max_effect_claims = 4 * max_requests
        self._max_effect_batch = _MAX_EFFECTS_PER_REQUEST * max_requests
        self._start_lock = asyncio.Lock()
        self._identity_claim_lock = asyncio.Lock()
        self._close_requested = False
        self._ack_lock = asyncio.Lock()
        self._effect_lock = asyncio.Lock()
        self._closing_interactions: set[str] = set()
        self._consumer: asyncio.Task[None] | None = None
        self._shutdown: asyncio.Task[AgentConversationShutdownResult] | None = None
        self._started = False
        self._accepting = False
        self._closed = not enabled
        if self._closed:
            self._notifications.close()

    async def start(self) -> bool:
        async with self._start_lock:
            if not self._enabled:
                return False
            if not self._facade_available():
                return False
            if self._closed:
                raise AgentConversationRuntimeViolation(
                    "COMPOSITION_CLOSED",
                    "a closed composition cannot restart",
                    ErrorCode.CONFLICT,
                )
            if self._shutdown is not None:
                raise AgentConversationRuntimeViolation(
                    "COMPOSITION_CLOSING",
                    "a composition with retained teardown cannot restart",
                    ErrorCode.CONFLICT,
                )
            if self._started:
                return False
            try:
                await self._cr.start()
                await self._bridge.start()
                self._consumer = asyncio.create_task(
                    self._consume_bridge(), name="live-voice-agent-cr-consumer"
                )
            except BaseException:  # noqa: BLE001
                self._accepting = False
                self._shutdown = asyncio.create_task(
                    self._shutdown_coordinator(),
                    name="live-voice-agent-cr-startup-rollback",
                )
                try:
                    await asyncio.shield(self._shutdown)
                except BaseException:  # noqa: BLE001
                    # A second caller cancellation must not consume rollback
                    # ownership.  The retained coordinator remains observable
                    # through close().
                    pass
                raise
            if self._close_requested:
                self._shutdown = asyncio.create_task(
                    self._shutdown_coordinator(),
                    name="live-voice-agent-cr-startup-close",
                )
                await asyncio.shield(self._shutdown)
                raise AgentConversationRuntimeViolation(
                    "COMPOSITION_CLOSING",
                    "composition close was requested during startup",
                    ErrorCode.CONFLICT,
                )
            self._started = True
            self._accepting = True
            return True

    async def open_interaction(self, interaction_id: str) -> None:
        self._require_admission()
        await self._cr.open_interaction(interaction_id)

    async def start_turn(self, interaction_id: str, turn_id: str) -> None:
        self._require_admission()
        async with self._identity_claim_lock:
            if turn_id in self._turn_identity_claims:
                raise AgentConversationRuntimeViolation(
                    "TURN_IDENTITY_ALREADY_CLAIMED",
                    "turn_id is already owned by another admitted turn",
                    ErrorCode.CONFLICT,
                )
            claim = _TurnIdentityClaim(
                interaction_id=interaction_id,
                turn_id=turn_id,
                commit=None,
                product_request_id=None,
            )
            self._turn_identity_claims[turn_id] = claim
            try:
                await self._cr.start_turn(interaction_id, turn_id)
            except asyncio.CancelledError:
                # CR loop writes are cancellation-shielded after posting.  Keep
                # the claim so a product admission cannot race the retained write.
                raise
            except BaseException:
                if self._turn_identity_claims.get(turn_id) is claim:
                    self._turn_identity_claims.pop(turn_id, None)
                raise

    async def commit_turn(self, commit: TurnCommit) -> bool:
        self._require_admission()
        async with self._identity_claim_lock:
            self._validate_turn_commit(commit)
            prior_turn = self._turn_identity_claims.get(commit.turn_id)
            if (
                prior_turn is None
                or prior_turn.product_request_id is not None
                or prior_turn.interaction_id != commit.interaction_id
                or (
                    prior_turn.commit is not None
                    and prior_turn.commit.canonical_bytes() != commit.canonical_bytes()
                )
            ):
                raise AgentConversationRuntimeViolation(
                    "TURN_COMMIT_CONFLICT",
                    "legacy commit must match its exact start_turn identity claim",
                    ErrorCode.CONFLICT,
                )
            prior_commit = self._commit_identity_claims.get(commit.commit_id)
            if prior_commit is not None and prior_commit.turn_id != commit.turn_id:
                raise AgentConversationRuntimeViolation(
                    "TURN_COMMIT_CONFLICT",
                    "commit_id is already owned by another admitted turn",
                    ErrorCode.CONFLICT,
                )
            upgraded = _TurnIdentityClaim(
                interaction_id=commit.interaction_id,
                turn_id=commit.turn_id,
                commit=commit,
                product_request_id=None,
            )
            self._turn_identity_claims[commit.turn_id] = upgraded
            self._commit_identity_claims[commit.commit_id] = upgraded
            try:
                accepted, _event = await self._cr.commit_turn(commit)
            except asyncio.CancelledError:
                # The posted CR commit remains authoritative even if this waiter
                # leaves.  Retaining both claims prevents cross-path reuse.
                raise
            except BaseException:
                self._turn_identity_claims[commit.turn_id] = prior_turn
                if prior_commit is None:
                    self._commit_identity_claims.pop(commit.commit_id, None)
                else:
                    self._commit_identity_claims[commit.commit_id] = prior_commit
                raise
            self._commits[commit.turn_id] = commit
            return accepted

    async def _commit_admitted_turn(
        self, commit: TurnCommit, *, request_id: str
    ) -> bool:
        """Commit a registered product turn under its retained identity claim."""

        async with self._identity_claim_lock:
            self._validate_turn_commit(commit)
            claim = self._turn_identity_claims.get(commit.turn_id)
            if (
                claim is None
                or claim.product_request_id != request_id
                or claim.commit is None
                or claim.commit.canonical_bytes() != commit.canonical_bytes()
                or self._commit_identity_claims.get(commit.commit_id) is not claim
            ):
                raise AgentConversationRuntimeViolation(
                    "PRODUCT_TURN_IDENTITY_LOST",
                    "registered product turn lost its exact identity claim",
                    ErrorCode.INTERNAL,
                )
            await self._cr.start_turn(commit.interaction_id, commit.turn_id)
            accepted, _event = await self._cr.commit_turn(commit)
            self._commits[commit.turn_id] = commit
            return accepted

    def _validate_turn_commit(self, commit: TurnCommit) -> None:
        if not isinstance(commit, TurnCommit) or commit.scope != self._scope:
            raise AgentConversationRuntimeViolation(
                "INVALID_COMMITTED_TURN",
                "TurnCommit must match the exact composition scope",
                ErrorCode.PERMISSION_DENIED,
            )

    def _claim_product_identity(
        self, commit: TurnCommit, *, request_id: str
    ) -> _TurnIdentityClaim:
        prior_turn = self._turn_identity_claims.get(commit.turn_id)
        prior_commit = self._commit_identity_claims.get(commit.commit_id)
        if prior_turn is not None or prior_commit is not None:
            raise AgentConversationRuntimeViolation(
                "TURN_COMMIT_CONFLICT",
                "turn_id or commit_id is already owned by another admitted turn",
                ErrorCode.CONFLICT,
            )
        claim = _TurnIdentityClaim(
            interaction_id=commit.interaction_id,
            turn_id=commit.turn_id,
            commit=commit,
            product_request_id=request_id,
        )
        self._turn_identity_claims[commit.turn_id] = claim
        self._commit_identity_claims[commit.commit_id] = claim
        return claim

    def _release_product_identity(self, claim: _TurnIdentityClaim) -> None:
        if self._turn_identity_claims.get(claim.turn_id) is claim:
            self._turn_identity_claims.pop(claim.turn_id, None)
        if (
            claim.commit is not None
            and self._commit_identity_claims.get(claim.commit.commit_id) is claim
        ):
            self._commit_identity_claims.pop(claim.commit.commit_id, None)

    async def submit_committed_turn(
        self,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str = "web",
    ) -> AgentConversationHandle:
        """Own one retained product submission from TurnCommit through dispatch.

        The request is registered before the first CR write.  Exact concurrent
        replay observes one retained outcome, while caller cancellation cannot
        cancel the coordinator or consume that outcome.  The existing
        Bridge/Harness admission and CR response-acceptance machinery is reused
        after the turn becomes committed.
        """

        if not isinstance(commit, TurnCommit) or commit.scope != self._scope:
            raise AgentConversationRuntimeViolation(
                "INVALID_COMMITTED_TURN",
                "TurnCommit must match the exact composition scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if not isinstance(context, FormalContextSnapshot):
            raise AgentConversationRuntimeViolation(
                "INVALID_FORMAL_CONTEXT",
                "formal Agent context must be an immutable snapshot",
                ErrorCode.INVALID_ARGUMENT,
            )
        context.validate_for(commit)
        self._validate_dispatch_channel(channel_id)
        # This side-effect-free construction validates all reservation identity
        # fields before start_turn can mutate CR.
        HarnessRoundBinding(
            request_id=request_id,
            response_id=response_id,
            correlation_id=correlation_id,
            commit=commit,
        )
        fingerprint = self._admission_fingerprint(
            request_id=request_id,
            response_id=response_id,
            correlation_id=correlation_id,
            commit=commit,
            context=context,
            channel_id=channel_id,
        )
        product_entry = self._committed_turn_submissions.get(request_id)
        if product_entry is not None:
            if product_entry.fingerprint != fingerprint:
                raise AgentConversationRuntimeViolation(
                    "COMMITTED_TURN_REQUEST_CONFLICT",
                    "request_id cannot change its product TurnCommit binding",
                    ErrorCode.CONFLICT,
                )
            return self._unwrap_admission(await asyncio.shield(product_entry.outcome))

        async with self._identity_claim_lock:
            # A replay may have registered while this caller waited for the
            # admission fence.  Replays never reopen admission and therefore
            # remain observable throughout retained close/closed states.
            product_entry = self._committed_turn_submissions.get(request_id)
            if product_entry is not None:
                if product_entry.fingerprint != fingerprint:
                    raise AgentConversationRuntimeViolation(
                        "COMMITTED_TURN_REQUEST_CONFLICT",
                        "request_id cannot change its product TurnCommit binding",
                        ErrorCode.CONFLICT,
                    )
                outcome = product_entry.outcome
            else:
                self._require_admission()
                existing_admission = self._admissions.get(request_id)
                if existing_admission is not None:
                    # A legacy dispatch already owns the exact committed CR
                    # identity and reservations.  Product replay may attach to
                    # that retained outcome without allocating another claim.
                    outcome = self._register_committed_turn_submission(
                        request_id=request_id,
                        response_id=response_id,
                        correlation_id=correlation_id,
                        commit=commit,
                        context=context,
                        channel_id=channel_id,
                        fingerprint=fingerprint,
                    )
                else:
                    turn_key = (commit.interaction_id, commit.turn_id)
                    bound_request = self._submitted_turn_bindings.get(turn_key)
                    if bound_request is not None and bound_request != request_id:
                        raise AgentConversationRuntimeViolation(
                            "COMMITTED_TURN_ALREADY_SUBMITTED",
                            "one product TurnCommit cannot be rebound to another request",
                            ErrorCode.CONFLICT,
                        )
                    # One fence owns identity preflight, claim registration,
                    # reservation, and product ledger writes.  Legacy start and
                    # commit operations use this same fence and claim registry.
                    claim = self._claim_product_identity(commit, request_id=request_id)
                    try:
                        outcome = self._register_committed_turn_submission(
                            request_id=request_id,
                            response_id=response_id,
                            correlation_id=correlation_id,
                            commit=commit,
                            context=context,
                            channel_id=channel_id,
                            fingerprint=fingerprint,
                        )
                    except BaseException:
                        self._release_product_identity(claim)
                        raise

        return self._unwrap_admission(await asyncio.shield(outcome))

    async def accept_task_origin(
        self,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
    ) -> ResponseRef:
        """Commit one Task-bound turn and return its canonical CR response fence.

        This path deliberately creates no Harness round, Agent dispatch,
        presentation unit, history write, Tool call, or Task mutation.  The
        Conversation Runtime remains the sole response-generation authority.
        """

        self._require_admission()
        self._validate_turn_commit(commit)
        HarnessRoundBinding(
            request_id=request_id,
            response_id=response_id,
            correlation_id=correlation_id,
            commit=commit,
        )
        async with self._identity_claim_lock:
            snapshot = self._cr.snapshot().conversation
            if any(item.turn_id == commit.turn_id for item in snapshot.turns) or any(
                item.ref.response_id == response_id for item in snapshot.responses
            ):
                raise AgentConversationRuntimeViolation(
                    "TASK_ORIGIN_IDENTITY_CONFLICT",
                    "Task-origin turn or response identity is already owned",
                    ErrorCode.CONFLICT,
                )
            claim = self._claim_product_identity(commit, request_id=request_id)
            response_ref: ResponseRef | None = None
            try:
                await self._cr.start_turn(commit.interaction_id, commit.turn_id)
                accepted, _event = await self._cr.commit_turn(commit)
                if accepted is not True:
                    raise AgentConversationRuntimeViolation(
                        "TASK_ORIGIN_COMMIT_REJECTED",
                        "Task-origin turn was not accepted exactly once",
                        ErrorCode.CONFLICT,
                    )
                response_ref, _event = await self._cr.accept_response(
                    commit.turn_id,
                    response_id,
                    history_policy=HistorySurfacePolicy.TEXT,
                )
                await self._cr.transition_response(
                    response_ref,
                    ResponseState.TERMINAL,
                    outcome=TerminalOutcome.COMPLETED,
                )
                self._commits[commit.turn_id] = commit
                return response_ref
            except BaseException:
                # All caller-controlled conflicts are checked before the first
                # CR write. Retain a claim after an unexpected partial CR
                # failure so no other path can reuse that identity.  A transport
                # or wrapper may raise after the CR has durably reached its exact
                # terminal result, so reconcile that authority before reporting
                # RESULT_UNKNOWN.
                snapshot = self._cr.snapshot().conversation
                exact_turn = next(
                    (
                        item
                        for item in snapshot.turns
                        if item.turn_id == commit.turn_id
                        and item.interaction_id == commit.interaction_id
                        and item.commit_id == commit.commit_id
                    ),
                    None,
                )
                exact_response = next(
                    (
                        item
                        for item in snapshot.responses
                        if item.ref.response_id == response_id
                        and item.ref.interaction_id == commit.interaction_id
                        and item.turn_id == commit.turn_id
                    ),
                    None,
                )
                if (
                    exact_turn is not None
                    and exact_turn.state is TurnState.COMMITTED
                    and exact_response is not None
                    and exact_response.state is ResponseState.TERMINAL
                    and exact_response.outcome is TerminalOutcome.COMPLETED
                ):
                    self._commits[commit.turn_id] = commit
                    return exact_response.ref
                partial_write = response_ref is not None or exact_turn is not None
                if not partial_write:
                    self._release_product_identity(claim)
                    raise
                raise AgentConversationRuntimeViolation(
                    "TASK_ORIGIN_RESULT_UNKNOWN",
                    "Task-origin CR write did not reach a provable terminal result",
                    ErrorCode.RESULT_UNKNOWN,
                )

    async def accept_task_progress_notification(
        self,
        intent: TaskProgressNotificationIntent,
        *,
        response_ref: ResponseRef,
    ) -> bool:
        """Admit one arbiter-owned Task progress intent into CR observation.

        This method deliberately emits no TTS command, presentation unit,
        history write, response/round cancellation, or Task command.  The
        active Conversation Runtime merely owns the exact notification and its
        current response-generation correlation for the product consumer.
        """

        self._require_admission()
        if not isinstance(intent, TaskProgressNotificationIntent):
            raise AgentConversationRuntimeViolation(
                "INVALID_TASK_PROGRESS_NOTIFICATION",
                "Conversation Runtime requires a canonical progress intent",
                ErrorCode.INVALID_ARGUMENT,
            )
        origin = intent.origin
        if (
            origin.origin_kind is not TaskProgressOriginKind.VOICE
            or origin.scope != self._scope
            or origin.session_id != self._scope.session_id
            or origin.origin_id == ""
        ):
            raise AgentConversationRuntimeViolation(
                "TASK_PROGRESS_ORIGIN_MISMATCH",
                "voice progress must bind this exact Conversation Runtime scope",
                ErrorCode.PERMISSION_DENIED,
            )
        snapshot = self._cr.snapshot().conversation
        interaction = next(
            (
                item
                for item in snapshot.interactions
                if item.interaction_id == origin.origin_id
            ),
            None,
        )
        if interaction is None or interaction.state is not InteractionState.OPEN:
            raise AgentConversationRuntimeViolation(
                "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE",
                "voice progress has no exact live origin interaction",
                ErrorCode.UNAVAILABLE,
            )
        if (
            not isinstance(response_ref, ResponseRef)
            or response_ref.interaction_id != origin.origin_id
        ):
            raise AgentConversationRuntimeViolation(
                "TASK_PROGRESS_RESPONSE_MISMATCH",
                "voice progress must bind its exact canonical origin response",
                ErrorCode.PERMISSION_DENIED,
            )
        response = next(
            (item for item in snapshot.responses if item.ref == response_ref),
            None,
        )
        successor_exists = any(
            item.ref.interaction_id == origin.origin_id
            and item.ref.response_generation > response_ref.response_generation
            for item in snapshot.responses
        )
        if response is None or successor_exists:
            raise AgentConversationRuntimeViolation(
                (
                    "TASK_PROGRESS_RESPONSE_SUPERSEDED"
                    if successor_exists
                    else "TASK_PROGRESS_VOICE_ORIGIN_UNAVAILABLE"
                ),
                (
                    "voice progress response has a canonical successor"
                    if successor_exists
                    else "voice progress has no canonical response generation"
                ),
                ErrorCode.UNAVAILABLE,
            )
        progress = WorkProgressEventV2.from_dict(
            intent.progress_event.payload, scope=intent.progress_event.scope
        )
        self._publish(
            AgentConversationNotification(
                kind="task.progress.notification",
                request_id=intent.evidence_id,
                round_id=f"task:{origin.task_id}",
                response_ref=response_ref,
                source_event=intent.source_event,
                progress_event=intent.progress_event,
            ),
            critical_key=(
                ("task-progress-terminal", intent.evidence_id)
                if progress.state is WorkState.TERMINAL
                else None
            ),
        )
        return True

    def _register_committed_turn_submission(
        self,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str,
        fingerprint: bytes,
    ) -> asyncio.Future[_AdmissionOutcome]:
        """Register one preflighted submission while admission fence is held."""

        turn_key = (commit.interaction_id, commit.turn_id)
        bound_request = self._submitted_turn_bindings.get(turn_key)
        if bound_request is not None and bound_request != request_id:
            raise AgentConversationRuntimeViolation(
                "COMMITTED_TURN_ALREADY_SUBMITTED",
                "one product TurnCommit cannot be rebound to another request",
                ErrorCode.CONFLICT,
            )
        if len(self._committed_turn_submissions) >= self._max_requests:
            raise AgentConversationRuntimeViolation(
                "COMMITTED_TURN_LEDGER_FULL",
                "bounded product TurnCommit ledger is full for this runtime session",
                ErrorCode.UNAVAILABLE,
            )

        existing_admission = self._admissions.get(request_id)
        if existing_admission is not None:
            if existing_admission.fingerprint != fingerprint:
                raise AgentConversationRuntimeViolation(
                    "COMPOSITION_REQUEST_ID_CONFLICT",
                    "request_id cannot change its formal dispatch binding",
                    ErrorCode.CONFLICT,
                )
            self._submitted_turn_bindings[turn_key] = request_id
            self._committed_turn_submissions[request_id] = (
                _CommittedTurnSubmissionEntry(
                    fingerprint=fingerprint,
                    commit=commit,
                    outcome=existing_admission.outcome,
                    coordinator=existing_admission.coordinator,
                )
            )
            return existing_admission.outcome
        if len(self._admissions) >= self._max_requests:
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_REQUEST_LEDGER_FULL",
                "bounded composition request ledger is full for this runtime session",
                ErrorCode.UNAVAILABLE,
            )

        # Reserve every bounded execution resource before start_turn mutates CR.
        # Reservation is not round acceptance and has zero Agent/Tool/Task/history
        # effect; a capacity or facade failure therefore leaves CR unchanged.
        harness_reservation: HarnessRoundReservation | None = None
        bridge_reservation: AgentBridgeDispatchReservation | None = None
        try:
            assert self._facade is not None
            harness_reservation = self._harness.reserve_round(
                HarnessRoundBinding(
                    request_id=request_id,
                    response_id=response_id,
                    correlation_id=correlation_id,
                    commit=commit,
                ),
                facade=self._facade,
            )
            bridge_reservation = self._bridge.reserve_dispatch(
                request_id=request_id,
                round_id=harness_reservation.round_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
                adapter_id=JiuWenSwarmAgentAdapter.adapter_id,
            )
            self._harness.begin_round_commit(harness_reservation)
            self._bridge.begin_dispatch_commit(bridge_reservation)
        except BaseException:
            if bridge_reservation is not None:
                self._bridge.abort_dispatch(
                    bridge_reservation, reason="product_submission_admission_failed"
                )
            if harness_reservation is not None:
                self._harness.abort_round_reservation(
                    harness_reservation,
                    reason="product_submission_admission_failed",
                )
            raise

        assert harness_reservation is not None
        assert bridge_reservation is not None
        running = asyncio.get_running_loop()
        outcome: asyncio.Future[_AdmissionOutcome] = running.create_future()
        admission_entry = _AdmissionEntry(
            fingerprint=fingerprint,
            harness_reservation=harness_reservation,
            bridge_reservation=bridge_reservation,
            outcome=outcome,
            coordinator=None,
        )
        product_entry = _CommittedTurnSubmissionEntry(
            fingerprint=fingerprint,
            commit=commit,
            outcome=outcome,
            coordinator=None,
        )
        self._admissions[request_id] = admission_entry
        self._committed_turn_submissions[request_id] = product_entry
        self._submitted_turn_bindings[turn_key] = request_id
        coordinator = running.create_task(
            self._complete_committed_turn_submission(
                admission_entry,
                commit=commit,
                context=context,
                channel_id=channel_id,
            ),
            name=f"live-voice-product-turn:{request_id}",
        )
        product_entry.coordinator = coordinator
        admission_entry.coordinator = coordinator
        return outcome

    async def dispatch_committed_turn(
        self,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str = "web",
    ) -> AgentConversationHandle:
        self._require_admission()
        self._require_exact_commit(commit)
        self._validate_dispatch_channel(channel_id)
        if self._facade is None:
            raise AgentConversationRuntimeViolation(
                "FORMAL_AGENT_FACADE_UNAVAILABLE",
                "formal Agent facade is not configured",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        context.validate_for(commit)
        fingerprint = self._admission_fingerprint(
            request_id=request_id,
            response_id=response_id,
            correlation_id=correlation_id,
            commit=commit,
            context=context,
            channel_id=channel_id,
        )

        async with self._identity_claim_lock:
            existing = self._admissions.get(request_id)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise AgentConversationRuntimeViolation(
                        "COMPOSITION_REQUEST_ID_CONFLICT",
                        "request_id cannot change its formal dispatch binding",
                        ErrorCode.CONFLICT,
                    )
                outcome = existing.outcome
            else:
                self._require_exact_commit(commit)
                turn_key = (commit.interaction_id, commit.turn_id)
                bound_request = self._submitted_turn_bindings.get(turn_key)
                identity_claim = self._turn_identity_claims.get(commit.turn_id)
                if (bound_request is not None and bound_request != request_id) or (
                    identity_claim is not None
                    and identity_claim.product_request_id is not None
                    and identity_claim.product_request_id != request_id
                ):
                    raise AgentConversationRuntimeViolation(
                        "COMMITTED_TURN_ALREADY_SUBMITTED",
                        "request-bound TurnCommit cannot dispatch under another request",
                        ErrorCode.CONFLICT,
                    )
                outcome = self._register_legacy_dispatch(
                    request_id=request_id,
                    response_id=response_id,
                    correlation_id=correlation_id,
                    commit=commit,
                    context=context,
                    channel_id=channel_id,
                    fingerprint=fingerprint,
                )

        return self._unwrap_admission(await asyncio.shield(outcome))

    def _register_legacy_dispatch(
        self,
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str,
        fingerprint: bytes,
    ) -> asyncio.Future[_AdmissionOutcome]:
        """Register one fenced legacy dispatch without changing turn ownership."""

        if len(self._admissions) >= self._max_requests:
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_REQUEST_LEDGER_FULL",
                "bounded composition request ledger is full for this runtime session",
                ErrorCode.UNAVAILABLE,
            )

        harness_reservation: HarnessRoundReservation | None = None
        bridge_reservation: AgentBridgeDispatchReservation | None = None
        try:
            harness_reservation = self._harness.reserve_round(
                HarnessRoundBinding(
                    request_id=request_id,
                    response_id=response_id,
                    correlation_id=correlation_id,
                    commit=commit,
                ),
                facade=self._facade,
            )
            bridge_reservation = self._bridge.reserve_dispatch(
                request_id=request_id,
                round_id=harness_reservation.round_id,
                response_id=response_id,
                correlation_id=correlation_id,
                commit=commit,
                adapter_id=JiuWenSwarmAgentAdapter.adapter_id,
            )
            self._harness.begin_round_commit(harness_reservation)
            self._bridge.begin_dispatch_commit(bridge_reservation)
        except BaseException:
            if bridge_reservation is not None:
                self._bridge.abort_dispatch(
                    bridge_reservation, reason="composition_admission_failed"
                )
            if harness_reservation is not None:
                self._harness.abort_round_reservation(
                    harness_reservation, reason="composition_admission_failed"
                )
            raise

        running = asyncio.get_running_loop()
        outcome: asyncio.Future[_AdmissionOutcome] = running.create_future()
        entry = _AdmissionEntry(
            fingerprint=fingerprint,
            harness_reservation=harness_reservation,
            bridge_reservation=bridge_reservation,
            outcome=outcome,
            coordinator=None,
        )
        self._admissions[request_id] = entry
        self._submitted_turn_bindings[(commit.interaction_id, commit.turn_id)] = (
            request_id
        )
        coordinator = running.create_task(
            self._complete_admission(
                entry,
                context=context,
                channel_id=channel_id,
            ),
            name=f"live-voice-agent-admission:{request_id}",
        )
        entry.coordinator = coordinator
        return outcome

    async def next_notification(self) -> AgentConversationNotification:
        """Read lossy observations plus retained presentation/terminal notices.

        Notifications never own round or response lifecycle. Observer entries may
        have publish-sequence gaps when a slow consumer exceeds its bounded lane.
        """
        if not self._enabled:
            raise AgentConversationRuntimeViolation(
                "FEATURE_DISABLED",
                "formal Agent composition is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if self._notification_leases_attached > 0:
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_CONSUMER_LEASE_REQUIRED",
                "unleased reads are disabled after exact lease ownership begins",
                ErrorCode.PERMISSION_DENIED,
            )
        try:
            return await self._notifications.get()
        except _NotificationBufferClosed as error:
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_STREAM_CLOSED",
                "the notification producer is closed and its retained buffer is empty",
                ErrorCode.UNAVAILABLE,
            ) from error

    def attach_notification_consumer(
        self, *, consumer_id: str, connection_epoch: int
    ) -> AgentConversationNotificationLease:
        """Fence an infrastructure notification consumer to one exact epoch.

        Attaching a newer transport generation detaches the previous waiter but
        never cancels a response, Harness round, Agent, Tool, or Task. Buffered
        notifications remain owned by this runtime and are available to the new
        exact lease.
        """

        self._require_started()
        if (
            self._close_requested
            or self._shutdown is not None
            or self._notifications.closed
        ):
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_CLOSING",
                "notification ownership cannot change after retained shutdown",
                ErrorCode.CONFLICT,
            )
        self._validate_notification_consumer(consumer_id, connection_epoch)
        current = self._active_notification_lease
        if current is not None and current.active:
            if (
                current.lease.consumer_id == consumer_id
                and current.lease.connection_epoch == connection_epoch
            ):
                return current.lease
        retained_epoch = self._notification_consumer_epochs.get(consumer_id)
        if retained_epoch is not None and connection_epoch <= retained_epoch:
            raise AgentConversationRuntimeViolation(
                "STALE_NOTIFICATION_CONSUMER",
                "notification consumer epoch must strictly increase on reconnect",
                ErrorCode.STALE,
            )
        if (
            retained_epoch is None
            and len(self._notification_consumer_epochs) >= self._max_requests
        ):
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_CONSUMER_LEDGER_FULL",
                "bounded notification consumer ledger is full for this runtime",
                ErrorCode.UNAVAILABLE,
            )
        if current is not None and current.active:
            self._detach_notification_record(current)
        self._notification_leases_attached += 1
        lease = AgentConversationNotificationLease(
            owner_instance_id=self._instance_id,
            consumer_id=consumer_id,
            connection_epoch=connection_epoch,
            lease_id=f"notification-lease:{self._notification_leases_attached}",
        )
        record = _NotificationLeaseRecord(lease=lease, detached=asyncio.Event())
        self._notification_consumer_epochs[consumer_id] = connection_epoch
        self._final_notification_drain_lease = None
        self._active_notification_lease = record
        return lease

    def detach_notification_consumer(
        self, lease: AgentConversationNotificationLease
    ) -> bool:
        """Detach the exact transport and reserve distinct close-drain ownership."""

        record = self._require_notification_lease(lease, require_active=False)
        if not record.active:
            return False
        self._detach_notification_record(record)
        self._reserve_final_notification_drain(record)
        return True

    async def next_notification_for(
        self, lease: AgentConversationNotificationLease
    ) -> AgentConversationNotification:
        """Read without allowing a stale transport generation to consume data."""

        record = self._require_notification_lease(
            lease,
            require_active=not (
                self._notifications.closed
                and self._active_notification_lease is not None
                and self._active_notification_lease.drain_after_close
            ),
        )
        try:
            return await self._notifications.get(
                lease_active=lambda: (
                    self._active_notification_lease is record
                    and (
                        record.active
                        or (self._notifications.closed and record.drain_after_close)
                    )
                ),
                detached=record.detached,
            )
        except _NotificationConsumerDetached as error:
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_CONSUMER_DETACHED",
                "notification consumer lease is detached or superseded",
                ErrorCode.STALE,
            ) from error
        except _NotificationBufferClosed as error:
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_STREAM_CLOSED",
                "the notification producer is closed and its retained buffer is empty",
                ErrorCode.UNAVAILABLE,
            ) from error

    async def claim_conversation_effects(
        self,
        lease: AgentConversationNotificationLease,
        *,
        claim_id: str,
        limit: int | None = None,
    ) -> AgentConversationEffectClaim:
        """Retain one exact-consumer effect batch until its explicit ACK.

        CR effects remain declarative and retain their exact ResponseRef.  This
        hook neither executes nor widens playback, response, round, or task
        cancellation.  Caller cancellation cannot cancel the retained claim.
        """

        record = self._require_effect_lease(lease)
        self._validate_effect_claim_id(claim_id)
        if limit is not None and (
            type(limit) is not int or not 0 <= limit <= self._max_effect_batch
        ):
            raise AgentConversationRuntimeViolation(
                "INVALID_EFFECT_LIMIT",
                "effect claim limit exceeds the bounded non-negative range",
                ErrorCode.INVALID_ARGUMENT,
            )
        async with self._effect_lock:
            entry = self._effect_claims.get(claim_id)
            replayed = entry is not None
            if entry is not None:
                if entry.lease_id != lease.lease_id or entry.limit != limit:
                    raise AgentConversationRuntimeViolation(
                        "EFFECT_CLAIM_CONFLICT",
                        "an effect claim identifier cannot change owner or limit",
                        ErrorCode.CONFLICT,
                    )
                if entry.superseded:
                    raise AgentConversationRuntimeViolation(
                        "EFFECT_CLAIM_SUPERSEDED",
                        "an unacknowledged effect claim was returned to the outbox",
                        ErrorCode.STALE,
                    )
            else:
                if len(self._effect_claims) >= self._max_effect_claims:
                    raise AgentConversationRuntimeViolation(
                        "EFFECT_CLAIM_LEDGER_FULL",
                        "the bounded effect claim ledger is full",
                        ErrorCode.UNAVAILABLE,
                    )
                running = asyncio.get_running_loop()
                entry = _ConversationEffectClaimEntry(
                    claim_id=claim_id,
                    lease_id=lease.lease_id,
                    limit=limit,
                    outcome=running.create_future(),
                    coordinator=None,
                )
                self._effect_claims[claim_id] = entry
                entry.coordinator = running.create_task(
                    self._complete_effect_claim(entry, record),
                    name=f"live-voice-effect-claim:{claim_id}",
                )
        error = await asyncio.shield(entry.outcome)
        if error is not None:
            raise error
        async with self._effect_lock:
            self._require_effect_lease(lease)
            self._prune_invalid_output_effects()
            if entry.superseded:
                raise AgentConversationRuntimeViolation(
                    "EFFECT_CLAIM_SUPERSEDED",
                    "an invalidated effect claim was returned to the outbox",
                    ErrorCode.STALE,
                )
        return AgentConversationEffectClaim(
            claim_id=claim_id,
            consumer_id=lease.consumer_id,
            connection_epoch=lease.connection_epoch,
            effects=entry.effects,
            replayed=replayed,
            acknowledged=entry.acknowledged,
        )

    async def acknowledge_conversation_effects(
        self,
        lease: AgentConversationNotificationLease,
        *,
        claim_id: str,
        effect_ids: tuple[str, ...],
    ) -> AgentConversationEffectAckResult:
        """ACK only the exact retained batch owned by the current consumer."""

        self._require_effect_lease(lease)
        self._validate_effect_claim_id(claim_id)
        self._validate_effect_ack_ids(effect_ids)
        async with self._effect_lock:
            self._require_effect_lease(lease)
            entry = self._effect_claims.get(claim_id)
            if entry is None or entry.lease_id != lease.lease_id or entry.superseded:
                raise AgentConversationRuntimeViolation(
                    "UNKNOWN_EFFECT_CLAIM",
                    "effect acknowledgement requires the exact active claim",
                    ErrorCode.STALE,
                )
        error = await asyncio.shield(entry.outcome)
        if error is not None:
            raise error
        async with self._effect_lock:
            self._require_effect_lease(lease)
            self._prune_invalid_output_effects()
            if entry.superseded:
                raise AgentConversationRuntimeViolation(
                    "UNKNOWN_EFFECT_CLAIM",
                    "effect acknowledgement requires the exact active claim",
                    ErrorCode.STALE,
                )
            retained_ids = tuple(effect.effect_id for effect in entry.effects)
            if effect_ids != retained_ids:
                raise AgentConversationRuntimeViolation(
                    "EFFECT_ACK_CONFLICT",
                    "effect acknowledgement cannot change the retained batch",
                    ErrorCode.CONFLICT,
                )
            replayed = entry.acknowledged
            entry.acknowledged = True
            return AgentConversationEffectAckResult(
                claim_id=claim_id,
                effect_ids=effect_ids,
                accepted=True,
                replayed=replayed,
            )

    async def acknowledge_presentation(
        self, ack: PresentationAck
    ) -> PresentationAckResult:
        if not isinstance(ack, PresentationAck):
            raise AgentConversationRuntimeViolation(
                "INVALID_PRESENTATION_ACK",
                "acknowledgement has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        key = (ack.ref, ack.surface, ack.contiguous_cursor)
        entry = self._ack_entries.get(key)
        replayed = entry is not None
        if entry is not None:
            self._require_exact_ack(entry, ack)
            return await self._await_presentation_ack(key, entry, replayed=True)

        self._require_started()
        async with self._ack_lock:
            entry = self._ack_entries.get(key)
            if entry is not None:
                self._require_exact_ack(entry, ack)
                replayed = True
            else:
                if self._shutdown is not None:
                    raise AgentConversationRuntimeViolation(
                        "COMPOSITION_CLOSING",
                        "a new presentation ACK cannot start after retained shutdown",
                        ErrorCode.CONFLICT,
                    )
                state = self._outputs.get(ack.ref)
                if state is None or state.handle.response_ref != ack.ref:
                    raise AgentConversationRuntimeViolation(
                        "UNKNOWN_AGENT_RESPONSE",
                        "ACK requires the exact active Agent response generation",
                        ErrorCode.STALE,
                    )
                running = asyncio.get_running_loop()
                entry = _PresentationAckEntry(
                    ack=ack,
                    outcome=running.create_future(),
                    coordinator=None,
                )
                self._ack_entries[key] = entry
                entry.coordinator = running.create_task(
                    self._complete_presentation_ack(key, entry, state),
                    name=(
                        "live-voice-presentation-ack:"
                        f"{ack.ref.response_id}:{ack.contiguous_cursor}"
                    ),
                )
        return await self._await_presentation_ack(key, entry, replayed=replayed)

    async def _complete_presentation_ack(
        self,
        key: tuple[ResponseRef, PresentationSurface, int],
        entry: _PresentationAckEntry,
        state: _ResponseOutputState,
    ) -> None:
        try:
            async with self._ack_lock:
                result = await self._apply_presentation_ack(entry.ack, key, state)
                self._ack_results[key] = (entry.ack, result)
        except BaseException as error:  # noqa: BLE001
            if self._ack_entries.get(key) is entry:
                self._ack_entries.pop(key, None)
            if not entry.outcome.done():
                entry.outcome.set_result(error)
        else:
            if not entry.outcome.done():
                entry.outcome.set_result(None)

    async def _apply_presentation_ack(
        self,
        ack: PresentationAck,
        key: tuple[ResponseRef, PresentationSurface, int],
        state: _ResponseOutputState,
    ) -> PresentationAckResult:
        def resolve(unit: PresentationUnit) -> bytes:
            content = state.unit_contents.get(unit.unit_id)
            if content is None:
                raise AgentConversationRuntimeViolation(
                    "HISTORY_CONTENT_NOT_FOUND",
                    "presentation content is not retained by its owner",
                    ErrorCode.RESULT_UNKNOWN,
                )
            return content

        accepted, intent = await self._cr.acknowledge_presentation_with_history(
            ack, resolve
        )
        written = 0
        history_pending = False
        if intent is not None:
            session_id = state.commit.scope.session_id
            assert isinstance(session_id, str)
            try:
                results = await self._history_writer.persist_assistant(
                    intent,
                    session_id=session_id,
                    channel_id=state.channel_id,
                )
                written = sum(results)
            except BaseException:  # noqa: BLE001
                self._pending_history[key] = (
                    intent,
                    session_id,
                    state.channel_id,
                )
                history_pending = True
        result = PresentationAckResult(
            ack=ack,
            accepted=accepted,
            replayed=False,
            history_records_written=written,
            history_pending=history_pending,
        )
        return result

    async def _await_presentation_ack(
        self,
        key: tuple[ResponseRef, PresentationSurface, int],
        entry: _PresentationAckEntry,
        *,
        replayed: bool,
    ) -> PresentationAckResult:
        error = await asyncio.shield(entry.outcome)
        if error is not None:
            raise error
        retained = self._ack_results.get(key)
        if retained is None or retained[0] != entry.ack:
            raise AgentConversationRuntimeViolation(
                "PRESENTATION_ACK_OUTCOME_MISSING",
                "a completed presentation ACK lost its retained outcome",
                ErrorCode.INTERNAL,
            )
        return replace(retained[1], replayed=replayed)

    @staticmethod
    def _require_exact_ack(entry: _PresentationAckEntry, ack: PresentationAck) -> None:
        if entry.ack != ack:
            raise AgentConversationRuntimeViolation(
                "PRESENTATION_ACK_CONFLICT",
                "an exact ACK cursor cannot change its binding",
                ErrorCode.CONFLICT,
            )

    async def retry_history(
        self, ref: ResponseRef, *, contiguous_cursor: int
    ) -> tuple[bool, ...]:
        self._require_started()
        async with self._ack_lock:
            return await self._retry_history(ref, contiguous_cursor=contiguous_cursor)

    async def _retry_history(
        self, ref: ResponseRef, *, contiguous_cursor: int
    ) -> tuple[bool, ...]:
        key = (ref, PresentationSurface.TEXT, contiguous_cursor)
        pending = self._pending_history.get(key)
        if pending is None:
            return ()
        intent, session_id, channel_id = pending
        results = await self._history_writer.persist_assistant(
            intent, session_id=session_id, channel_id=channel_id
        )
        self._pending_history.pop(key, None)
        prior = self._ack_results.get(key)
        if prior is not None:
            ack, result = prior
            self._ack_results[key] = (
                ack,
                replace(
                    result,
                    history_records_written=(
                        result.history_records_written + sum(results)
                    ),
                    history_pending=False,
                ),
            )
        return results

    async def retry_user_history(self, commit_id: str) -> bool:
        pending = self._pending_user_history.get(commit_id)
        if pending is None:
            return False
        commit, channel_id = pending
        written = await self._history_writer.persist_user(commit, channel_id=channel_id)
        self._pending_user_history.pop(commit_id, None)
        return written

    async def request_response_cancel(
        self, command_id: str, ref: ResponseRef
    ) -> ResponseCancelResult:
        self._require_started()
        return await self._cr.request_response_cancel(command_id, ref)

    async def barge_in(
        self,
        action_id: str,
        ref: ResponseRef,
        *,
        cancel_response: bool = False,
    ) -> BargeInResult:
        self._require_started()
        return await self._cr.barge_in(action_id, ref, cancel_response=cancel_response)

    async def close_interaction(self, command: CommandEnvelope) -> RoundCancelResult:
        self._require_started()
        if not isinstance(command, CommandEnvelope):
            raise AgentConversationRuntimeViolation(
                "INVALID_INTERACTION_CLOSE",
                "interaction close requires an exact round.cancel command",
                ErrorCode.INVALID_ARGUMENT,
            )
        handle = self._round_handles.get(command.target_ref.id)
        if handle is None:
            raise AgentConversationRuntimeViolation(
                "ROUND_NOT_FOUND",
                "interaction close target is not an owned conversational round",
                ErrorCode.NOT_FOUND,
            )
        response_records = tuple(
            record
            for record in self._cr.snapshot().conversation.responses
            if record.ref.interaction_id == handle.response_ref.interaction_id
        )
        active = max(
            response_records,
            key=lambda record: record.ref.response_generation,
            default=None,
        )
        if active is None or active.ref != handle.response_ref:
            raise AgentConversationRuntimeViolation(
                "INTERACTION_CLOSE_ROUND_STALE",
                "interaction close must target its latest conversational round",
                ErrorCode.STALE,
            )
        result = handle.cancel(command)
        if result.accepted or result.reason == "ROUND_ALREADY_TERMINAL":
            interaction_id = handle.response_ref.interaction_id
            snapshot = self._cr.snapshot().conversation
            interaction = next(
                item
                for item in snapshot.interactions
                if item.interaction_id == interaction_id
            )
            if interaction.state is InteractionState.OPEN:
                await self._cr.transition_interaction(
                    interaction_id, InteractionState.CLOSING
                )
            self._closing_interactions.add(interaction_id)
            if handle.terminal_event is not None:
                await self._close_interaction_after_terminal(interaction_id)
        return result

    async def close(self, *, timeout_seconds: float) -> AgentConversationShutdownResult:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise AgentConversationRuntimeViolation(
                "INVALID_SHUTDOWN_TIMEOUT",
                "shutdown timeout must be positive and finite",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not self._enabled:
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.CLOSED, "feature_disabled"
            )
        timeout = float(timeout_seconds)
        deadline = asyncio.get_running_loop().time() + timeout
        self._close_requested = True
        try:
            # ``wait_for(lock.acquire())`` can swallow an external cancellation
            # when lock acquisition wins the same event-loop turn on Python
            # 3.11.  The timeout context keeps its own deadline cancellation
            # distinguishable while preserving caller cancellation exactly.
            async with asyncio.timeout(timeout):
                await self._start_lock.acquire()
        except TimeoutError:
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.PENDING,
                "startup_transition_still_running",
            )
        try:
            if self._shutdown is None:
                self._accepting = False
                active_notification_lease = self._active_notification_lease
                if (
                    active_notification_lease is not None
                    and active_notification_lease.active
                ):
                    self._reserve_final_notification_drain(active_notification_lease)
                    self._detach_notification_record(active_notification_lease)
                if self._started:
                    closed_detail = "teardown_complete"
                elif not self._facade_available():
                    closed_detail = "formal_agent_unavailable"
                else:
                    closed_detail = "not_started"
                self._shutdown = asyncio.create_task(
                    self._shutdown_coordinator(closed_detail=closed_detail),
                    name="live-voice-agent-cr-close",
                )
            shutdown = self._shutdown
        finally:
            self._start_lock.release()
        assert shutdown is not None
        if shutdown.done():
            return await asyncio.shield(shutdown)
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.PENDING,
                "retained_teardown_still_running",
            )
        try:
            return await asyncio.wait_for(asyncio.shield(shutdown), timeout=remaining)
        except TimeoutError:
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.PENDING,
                "retained_teardown_still_running",
            )

    def snapshot(self) -> AgentConversationRuntimeSnapshot:
        active_notification_lease = self._active_notification_lease
        return AgentConversationRuntimeSnapshot(
            enabled=self._enabled,
            started=self._started,
            accepting=self._accepting,
            closed=self._closed,
            closing=(self._shutdown is not None or self._close_requested)
            and not self._closed,
            retained_admissions=len(self._admissions),
            active_requests=tuple(
                state.request_id
                for state in self._outputs.values()
                if state.terminal_event is None
            ),
            queued_notifications=self._notifications.qsize(),
            notification_observer_capacity=self._notifications.observer_capacity,
            notification_critical_capacity=self._notifications.critical_capacity,
            queued_observer_notifications=self._notifications.queued_observer,
            queued_critical_notifications=self._notifications.queued_critical,
            published_notifications=self._notifications.published_total,
            delivered_notifications=self._notifications.delivered_total,
            dropped_observer_notifications=(self._notifications.dropped_observer_total),
            last_notification_publish_seq=self._notifications.last_publish_seq,
            last_notification_delivered_seq=(self._notifications.last_delivered_seq),
            notification_stream_closed=self._notifications.closed,
            active_notification_consumer=(
                None
                if active_notification_lease is None
                or not active_notification_lease.active
                else (
                    active_notification_lease.lease.consumer_id,
                    active_notification_lease.lease.connection_epoch,
                )
            ),
            notification_leases_attached=self._notification_leases_attached,
            notification_leases_detached=self._notification_leases_detached,
            discarded_invalidated_presentations=(
                self._discarded_invalidated_presentations
            ),
            critical_notification_invariant_failures=(
                self._notifications.critical_invariant_failures
            ),
            pending_conversation_effects=len(self._effect_backlog),
            unacknowledged_effect_claims=sum(
                not entry.acknowledged and not entry.superseded
                for entry in self._effect_claims.values()
            ),
            pending_history_intents=(
                len(self._pending_history) + len(self._pending_user_history)
            ),
            conversation=self._cr.snapshot(),
            bridge=self._bridge.snapshot(),
            harness=self._harness.snapshot(),
        )

    async def _complete_admission(
        self,
        entry: _AdmissionEntry,
        *,
        context: FormalContextSnapshot,
        channel_id: str,
    ) -> None:
        reservation = entry.harness_reservation
        bridge_reservation = entry.bridge_reservation
        facade = self._facade
        assert facade is not None
        response_ref: ResponseRef | None = None
        try:
            response_ref, _event = await self._cr.accept_response(
                reservation.binding.commit.turn_id,
                reservation.binding.response_id,
                history_policy=HistorySurfacePolicy.TEXT,
            )
            round_handle = self._harness.commit_round(
                reservation,
                response_ref=response_ref,
                context=context,
                facade=facade,
                channel_id=channel_id,
            )
            adapter = JiuWenSwarmAgentAdapter(round_handle)
            submission = self._bridge.commit_dispatch(
                bridge_reservation,
                response_ref=response_ref,
                adapter=adapter,
            )
            handle = AgentConversationHandle(
                request_id=reservation.binding.request_id,
                round_id=reservation.round_id,
                response_ref=response_ref,
                completion=submission.completion,
            )
            self._handles[handle.request_id] = handle
            self._round_handles[handle.round_id] = round_handle
            self._outputs[handle.response_ref] = _ResponseOutputState(
                request_id=handle.request_id,
                commit=reservation.binding.commit,
                channel_id=channel_id,
                handle=round_handle,
                unit_contents={},
            )
            history_task = asyncio.create_task(
                self._persist_user_history(reservation.binding.commit, channel_id),
                name=f"live-voice-formal-user-history:{handle.request_id}",
            )
            self._history_tasks.add(history_task)
            history_task.add_done_callback(self._history_tasks.discard)
            entry.outcome.set_result(_AdmissionOutcome(handle=handle))
        except BaseException as error:  # noqa: BLE001
            try:
                self._bridge.abort_dispatch(
                    bridge_reservation, reason="composition_commit_failed"
                )
            except (AgentBridgeRuntimeViolation, RuntimeError):
                pass
            try:
                self._harness.abort_round_reservation(
                    reservation, reason="composition_commit_failed"
                )
            except (HarnessRoundViolation, RuntimeError):
                pass
            if response_ref is not None:
                try:
                    await self._cr.transition_response(
                        response_ref,
                        ResponseState.TERMINAL,
                        outcome=TerminalOutcome.UNKNOWN,
                    )
                except (ConversationRuntimeLoopViolation, ConversationRuntimeViolation):
                    pass
            if not entry.outcome.done():
                entry.outcome.set_result(_AdmissionOutcome(error=error))

    async def _complete_committed_turn_submission(
        self,
        entry: _AdmissionEntry,
        *,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str,
    ) -> None:
        try:
            await self._commit_admitted_turn(
                commit,
                request_id=entry.harness_reservation.binding.request_id,
            )
            await self._complete_admission(
                entry,
                context=context,
                channel_id=channel_id,
            )
        except BaseException as error:  # noqa: BLE001 - retained outcome truth
            try:
                self._bridge.abort_dispatch(
                    entry.bridge_reservation,
                    reason="product_turn_commit_failed",
                )
            except (AgentBridgeRuntimeViolation, RuntimeError):
                pass
            try:
                self._harness.abort_round_reservation(
                    entry.harness_reservation,
                    reason="product_turn_commit_failed",
                )
            except (HarnessRoundViolation, RuntimeError):
                pass
            if not entry.outcome.done():
                entry.outcome.set_result(_AdmissionOutcome(error=error))

    async def _persist_user_history(self, commit: TurnCommit, channel_id: str) -> None:
        try:
            await self._history_writer.persist_user(commit, channel_id=channel_id)
        except BaseException:
            self._pending_user_history[commit.commit_id] = (commit, channel_id)

    async def _consume_bridge(self) -> None:
        while True:
            try:
                delivery = await self._bridge.next_delivery()
            except AgentBridgeRuntimeViolation as error:
                if error.reason == "BRIDGE_RUNTIME_CLOSED":
                    return
                raise
            if isinstance(delivery, AgentEventDelivery):
                await self._consume_agent_event(delivery)
            else:
                assert isinstance(delivery, WorkProgressDelivery)
                await self._consume_progress(delivery)

    async def _consume_agent_event(self, delivery: AgentEventDelivery) -> None:
        request = delivery.request
        event = delivery.event
        state = self._outputs.get(request.response_ref)
        if state is None:
            return
        presentation: PresentationUnit | None = None
        error_reason: str | None = None
        consumable_event: AgentEvent | None = event
        if event.event_type == "chat.final":
            text = event.text
            if not isinstance(text, str) or not text.strip():
                error_reason = "EMPTY_AGENT_FINAL"
            elif state.usable_finals:
                error_reason = "DUPLICATE_AGENT_FINAL"
            else:
                content = text.encode("utf-8")
                digest = hashlib.sha256(content).hexdigest()
                seq = state.usable_finals
                presentation = PresentationUnit(
                    ref=request.response_ref,
                    surface=PresentationSurface.TEXT,
                    unit_id=f"agent-final:{request.request_id.encode('utf-8').hex()}:{seq}",
                    seq=seq,
                    source_start_utf8=state.total_utf8,
                    source_end_utf8=state.total_utf8 + len(content),
                    content_ref=f"sha256:{digest}",
                )
                state.unit_contents[presentation.unit_id] = content
                try:
                    await self._cr.produce_unit(presentation)
                    await self._cr.enqueue_unit(
                        presentation.ref,
                        presentation.surface,
                        presentation.unit_id,
                    )
                except (
                    ConversationRuntimeLoopViolation,
                    ConversationRuntimeViolation,
                ) as error:
                    state.unit_contents.pop(presentation.unit_id, None)
                    presentation = None
                    error_reason = error.reason
                else:
                    state.usable_finals += 1
                    state.total_utf8 += len(content)
            if presentation is None:
                consumable_event = None
        self._publish(
            AgentConversationNotification(
                kind="agent.output",
                request_id=request.request_id,
                round_id=request.round_id,
                response_ref=request.response_ref,
                agent_event=consumable_event,
                presentation_unit=presentation,
                error_reason=error_reason,
            ),
            critical_key=(
                ("presentation", request.request_id)
                if presentation is not None
                else None
            ),
        )

    async def _consume_progress(self, delivery: WorkProgressDelivery) -> None:
        request = delivery.request
        state = self._outputs.get(request.response_ref)
        if state is None:
            return
        progress = WorkProgressEventV2.from_dict(
            delivery.progress_event.payload, scope=delivery.progress_event.scope
        )
        error_reason: str | None = None
        if progress.state is WorkState.ACCEPTED:
            try:
                await self._cr.transition_response(
                    request.response_ref, ResponseState.GENERATING
                )
            except (
                ConversationRuntimeLoopViolation,
                ConversationRuntimeViolation,
            ) as error:
                error_reason = error.reason
        elif progress.state is WorkState.TERMINAL:
            assert progress.outcome is not None
            state.terminal_outcome = progress.outcome
            state.terminal_event = delivery.source_event
            response_outcome = (
                TerminalOutcome.UNKNOWN
                if progress.outcome is TerminalOutcome.COMPLETED
                and state.usable_finals == 0
                else progress.outcome
            )
            try:
                await self._cr.transition_response(
                    request.response_ref,
                    ResponseState.TERMINAL,
                    outcome=response_outcome,
                )
            except (
                ConversationRuntimeLoopViolation,
                ConversationRuntimeViolation,
            ) as error:
                error_reason = error.reason
            if request.response_ref.interaction_id in self._closing_interactions:
                await self._close_interaction_after_terminal(
                    request.response_ref.interaction_id
                )
        self._publish(
            AgentConversationNotification(
                kind="work.progress",
                request_id=request.request_id,
                round_id=request.round_id,
                response_ref=request.response_ref,
                source_event=delivery.source_event,
                progress_event=delivery.progress_event,
                error_reason=error_reason,
            ),
            critical_key=(
                ("terminal", request.request_id)
                if progress.state is WorkState.TERMINAL
                else None
            ),
        )

    async def _close_interaction_after_terminal(self, interaction_id: str) -> None:
        snapshot = self._cr.snapshot().conversation
        interaction = next(
            item
            for item in snapshot.interactions
            if item.interaction_id == interaction_id
        )
        if interaction.state is InteractionState.CLOSING:
            await self._cr.transition_interaction(
                interaction_id, InteractionState.CLOSED
            )
        self._closing_interactions.discard(interaction_id)

    def _publish(
        self,
        notification: AgentConversationNotification,
        *,
        critical_key: tuple[str, str] | None = None,
    ) -> None:
        self._notifications.publish(notification, critical_key=critical_key)

    async def _shutdown_coordinator(
        self, *, closed_detail: str = "teardown_complete"
    ) -> AgentConversationShutdownResult:
        final_drain_lease = self._final_notification_drain_lease
        try:
            submission_tasks = tuple(
                entry.coordinator
                for entry in self._committed_turn_submissions.values()
                if entry.coordinator is not None
            )
            if submission_tasks:
                await asyncio.shield(
                    asyncio.gather(*submission_tasks, return_exceptions=True)
                )
            admission_tasks = tuple(
                entry.coordinator
                for entry in self._admissions.values()
                if entry.coordinator is not None and not entry.coordinator.done()
            )
            if admission_tasks:
                await asyncio.shield(
                    asyncio.gather(*admission_tasks, return_exceptions=True)
                )
            await self._bridge.close()
            if self._consumer is not None:
                await asyncio.shield(self._consumer)
            await self._harness.close()
            ack_tasks = tuple(
                entry.coordinator
                for entry in self._ack_entries.values()
                if entry.coordinator is not None and not entry.coordinator.done()
            )
            if ack_tasks:
                await asyncio.shield(asyncio.gather(*ack_tasks, return_exceptions=True))
            async with self._ack_lock:
                history_tasks = tuple(self._history_tasks)
                if history_tasks:
                    await asyncio.shield(
                        asyncio.gather(*history_tasks, return_exceptions=True)
                    )
            shutdown_effects = await self._cr.close()
            async with self._effect_lock:
                self._retain_effects(shutdown_effects)
                self._prune_invalid_output_effects()
            self._discarded_invalidated_presentations += (
                self._notifications.discard_pending_presentations()
            )
            if final_drain_lease is not None:
                final_drain_lease.drain_after_close = True
                self._active_notification_lease = final_drain_lease
            self._notifications.close()
            final_drain_capability = (
                None if final_drain_lease is None else final_drain_lease.lease
            )
            if self._pending_history or self._pending_user_history:
                return AgentConversationShutdownResult(
                    AgentConversationShutdownStatus.FAILED,
                    "history_write_intents_pending",
                    final_drain_capability,
                )
            self._closed = True
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.CLOSED,
                closed_detail,
                final_drain_capability,
            )
        except BaseException as error:  # noqa: BLE001
            self._notifications.close()
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.FAILED,
                f"teardown_failed:{type(error).__name__}",
                (
                    None
                    if final_drain_lease is None
                    or not final_drain_lease.drain_after_close
                    else final_drain_lease.lease
                ),
            )

    def _response_record(self, ref: ResponseRef):
        for record in self._cr.snapshot().conversation.responses:
            if record.ref == ref:
                return record
        raise AgentConversationRuntimeViolation(
            "UNKNOWN_AGENT_RESPONSE",
            "response is not owned by this composition",
            ErrorCode.NOT_FOUND,
        )

    def _require_exact_commit(self, commit: TurnCommit) -> None:
        if not isinstance(commit, TurnCommit):
            raise AgentConversationRuntimeViolation(
                "UNCOMMITTED_TURN",
                "Agent dispatch requires a canonical committed TurnCommit",
                ErrorCode.PERMISSION_DENIED,
            )
        retained = self._commits.get(commit.turn_id)
        snapshot = self._cr.snapshot().conversation
        turn = next(
            (item for item in snapshot.turns if item.turn_id == commit.turn_id),
            None,
        )
        if (
            retained is None
            or retained.canonical_bytes() != commit.canonical_bytes()
            or turn is None
            or turn.state is not TurnState.COMMITTED
            or turn.commit_id != commit.commit_id
        ):
            raise AgentConversationRuntimeViolation(
                "UNCOMMITTED_TURN",
                "only the exact CR-committed turn may dispatch",
                ErrorCode.PERMISSION_DENIED,
            )

    def _require_admission(self) -> None:
        self._require_started()
        if not self._accepting:
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_CLOSING",
                "formal Agent composition is not accepting work",
                ErrorCode.CONFLICT,
            )

    def _require_started(self) -> None:
        if not self._enabled:
            raise AgentConversationRuntimeViolation(
                "FEATURE_DISABLED",
                "formal Agent composition is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if not self._facade_available():
            raise AgentConversationRuntimeViolation(
                "FORMAL_AGENT_FACADE_UNAVAILABLE",
                "formal Agent facade capability is unavailable",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if not self._started or self._closed:
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_NOT_STARTED",
                "formal Agent composition is not active",
                ErrorCode.CONFLICT,
            )

    def _require_notification_lease(
        self,
        lease: AgentConversationNotificationLease,
        *,
        require_active: bool,
    ) -> _NotificationLeaseRecord:
        current = self._active_notification_lease
        if (
            not isinstance(lease, AgentConversationNotificationLease)
            or lease.owner_instance_id != self._instance_id
            or current is None
            or current.lease is not lease
        ):
            raise AgentConversationRuntimeViolation(
                "UNTRUSTED_NOTIFICATION_CONSUMER",
                "notification lease does not match the runtime registry",
                ErrorCode.PERMISSION_DENIED,
            )
        if require_active and not current.active:
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_CONSUMER_DETACHED",
                "notification consumer lease is detached or superseded",
                ErrorCode.STALE,
            )
        return current

    def _detach_notification_record(
        self,
        record: _NotificationLeaseRecord,
        *,
        drain_after_close: bool = False,
    ) -> None:
        if not record.active:
            return
        record.active = False
        record.drain_after_close = drain_after_close
        self._notification_leases_detached += 1
        record.detached.set()
        self._supersede_effect_claims(record)

    def _reserve_final_notification_drain(
        self, record: _NotificationLeaseRecord
    ) -> None:
        self._notification_final_drain_leases_issued += 1
        drain_lease = AgentConversationNotificationLease(
            owner_instance_id=self._instance_id,
            consumer_id=record.lease.consumer_id,
            connection_epoch=record.lease.connection_epoch,
            lease_id=(
                "notification-final-drain:"
                f"{self._notification_final_drain_leases_issued}"
            ),
        )
        self._final_notification_drain_lease = _NotificationLeaseRecord(
            lease=drain_lease,
            detached=asyncio.Event(),
            active=False,
        )

    def _require_effect_lease(
        self, lease: AgentConversationNotificationLease
    ) -> _NotificationLeaseRecord:
        record = self._require_notification_lease(lease, require_active=False)
        if record.active and self._close_requested:
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_CLOSING",
                "effect delivery is fenced while retained shutdown starts",
                ErrorCode.CONFLICT,
            )
        if not (
            record.active or (self._notifications.closed and record.drain_after_close)
        ):
            raise AgentConversationRuntimeViolation(
                "NOTIFICATION_CONSUMER_DETACHED",
                "effect delivery requires the exact active or final-drain lease",
                ErrorCode.STALE,
            )
        return record

    async def _complete_effect_claim(
        self,
        entry: _ConversationEffectClaimEntry,
        record: _NotificationLeaseRecord,
    ) -> None:
        error: BaseException | None = None
        try:
            async with self._effect_lock:
                if self._shutdown is None and not self._notifications.closed:
                    self._retain_effects(await self._cr.claim_effects())
                self._prune_invalid_output_effects()
                if (
                    entry.superseded
                    or self._active_notification_lease is not record
                    or not (
                        record.active
                        or (self._notifications.closed and record.drain_after_close)
                    )
                ):
                    raise AgentConversationRuntimeViolation(
                        "EFFECT_CLAIM_SUPERSEDED",
                        "effect claim ownership changed before delivery",
                        ErrorCode.STALE,
                    )
                selected: list[ConversationEffect] = []
                if entry.limit != 0:
                    while self._effect_backlog and (
                        entry.limit is None or len(selected) < entry.limit
                    ):
                        effect = self._effect_backlog.popleft()
                        self._effect_backlog_ids.remove(effect.effect_id)
                        selected.append(effect)
                entry.effects = tuple(selected)
        except BaseException as caught:  # noqa: BLE001 - retained outcome truth
            error = caught
        if not entry.outcome.done():
            entry.outcome.set_result(error)

    def _retain_effects(self, effects: tuple[ConversationEffect, ...]) -> None:
        assigned_ids = {
            retained.effect_id
            for entry in self._effect_claims.values()
            if not entry.superseded
            for retained in entry.effects
        }
        for effect in effects:
            if effect.effect_id in self._effect_backlog_ids:
                continue
            if effect.effect_id in assigned_ids:
                continue
            self._effect_backlog.append(effect)
            self._effect_backlog_ids.add(effect.effect_id)

    def _supersede_effect_claims(self, record: _NotificationLeaseRecord) -> None:
        requeued: list[ConversationEffect] = []
        for entry in self._effect_claims.values():
            if (
                entry.lease_id != record.lease.lease_id
                or entry.acknowledged
                or entry.superseded
            ):
                continue
            entry.superseded = True
            requeued.extend(entry.effects)
        self._requeue_effects_in_order(requeued)

    def _prune_invalid_output_effects(self) -> None:
        presentation = self._cr.snapshot().presentation
        deliverable_outputs = {
            (
                record.unit.ref,
                record.unit.surface,
                record.unit.unit_id,
                record.unit.seq,
            )
            for record in presentation.records
            if record.state is PresentationState.ENQUEUED
        }

        def deliverable(effect: ConversationEffect) -> bool:
            return (
                effect.effect_type not in {"ui.render", "audio.enqueue"}
                or (
                    effect.ref,
                    effect.surface,
                    effect.unit_id,
                    effect.unit_seq,
                )
                in deliverable_outputs
            )

        requeued: list[ConversationEffect] = []
        for entry in self._effect_claims.values():
            if entry.superseded or all(deliverable(effect) for effect in entry.effects):
                continue
            if not entry.acknowledged:
                requeued.extend(
                    effect for effect in entry.effects if deliverable(effect)
                )
            entry.superseded = True
        self._requeue_effects_in_order(requeued)
        retained = deque(
            effect for effect in self._effect_backlog if deliverable(effect)
        )
        self._effect_backlog = retained
        self._effect_backlog_ids = {effect.effect_id for effect in retained}

    def _requeue_effects_in_order(self, effects: list[ConversationEffect]) -> None:
        if not effects:
            return
        retained = {effect.effect_id: effect for effect in self._effect_backlog}
        for effect in effects:
            retained.setdefault(effect.effect_id, effect)
        ordered = sorted(retained.values(), key=lambda effect: effect.seq)
        self._effect_backlog = deque(ordered)
        self._effect_backlog_ids = set(retained)

    def _validate_effect_ack_ids(self, effect_ids: tuple[str, ...]) -> None:
        if type(effect_ids) is not tuple or len(effect_ids) > self._max_effect_batch:
            raise AgentConversationRuntimeViolation(
                "INVALID_EFFECT_ACK",
                "effect acknowledgement requires a bounded identifier tuple",
                ErrorCode.INVALID_ARGUMENT,
            )
        unique_ids: set[str] = set()
        for effect_id in effect_ids:
            if (
                type(effect_id) is not str
                or not effect_id
                or len(effect_id) > _MAX_EFFECT_ID_CHARS
                or effect_id != effect_id.strip()
            ):
                raise AgentConversationRuntimeViolation(
                    "INVALID_EFFECT_ACK",
                    "effect identifiers must be canonical bounded strings",
                    ErrorCode.INVALID_ARGUMENT,
                )
            try:
                encoded_effect_id = effect_id.encode("utf-8")
            except UnicodeEncodeError as error:
                raise AgentConversationRuntimeViolation(
                    "INVALID_EFFECT_ACK",
                    "effect identifiers must contain Unicode scalar values",
                    ErrorCode.INVALID_ARGUMENT,
                ) from error
            if (
                len(encoded_effect_id) > _MAX_EFFECT_ID_UTF8_BYTES
                or effect_id in unique_ids
            ):
                raise AgentConversationRuntimeViolation(
                    "INVALID_EFFECT_ACK",
                    "effect identifiers must be UTF-8 bounded and unique",
                    ErrorCode.INVALID_ARGUMENT,
                )
            unique_ids.add(effect_id)

    @staticmethod
    def _validate_effect_claim_id(claim_id: str) -> None:
        if (
            type(claim_id) is not str
            or not claim_id
            or len(claim_id) > _MAX_NOTIFICATION_CONSUMER_ID_CHARS
            or claim_id != claim_id.strip()
        ):
            raise AgentConversationRuntimeViolation(
                "INVALID_EFFECT_CLAIM",
                "claim_id must be a canonical bounded string",
                ErrorCode.INVALID_ARGUMENT,
            )
        try:
            encoded_claim_id = claim_id.encode("utf-8")
        except UnicodeEncodeError as error:
            raise AgentConversationRuntimeViolation(
                "INVALID_EFFECT_CLAIM",
                "claim_id must contain Unicode scalar values",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        if len(encoded_claim_id) > _MAX_NOTIFICATION_CONSUMER_ID_UTF8_BYTES:
            raise AgentConversationRuntimeViolation(
                "INVALID_EFFECT_CLAIM",
                "claim_id exceeds the bounded UTF-8 identity size",
                ErrorCode.INVALID_ARGUMENT,
            )

    @staticmethod
    def _validate_notification_consumer(
        consumer_id: str, connection_epoch: int
    ) -> None:
        if (
            type(consumer_id) is not str
            or not consumer_id
            or len(consumer_id) > _MAX_NOTIFICATION_CONSUMER_ID_CHARS
            or consumer_id != consumer_id.strip()
        ):
            raise AgentConversationRuntimeViolation(
                "INVALID_NOTIFICATION_CONSUMER",
                "consumer_id must be a canonical bounded string",
                ErrorCode.INVALID_ARGUMENT,
            )
        try:
            encoded_consumer_id = consumer_id.encode("utf-8")
        except UnicodeEncodeError as error:
            raise AgentConversationRuntimeViolation(
                "INVALID_NOTIFICATION_CONSUMER",
                "consumer_id must contain Unicode scalar values",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        if len(encoded_consumer_id) > _MAX_NOTIFICATION_CONSUMER_ID_UTF8_BYTES:
            raise AgentConversationRuntimeViolation(
                "INVALID_NOTIFICATION_CONSUMER",
                "consumer_id exceeds the bounded UTF-8 identity size",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            type(connection_epoch) is not int
            or connection_epoch < 0
            or connection_epoch > 9_007_199_254_740_991
        ):
            raise AgentConversationRuntimeViolation(
                "INVALID_NOTIFICATION_CONSUMER",
                "connection_epoch must be a non-negative safe integer",
                ErrorCode.INVALID_ARGUMENT,
            )

    def _facade_available(self) -> bool:
        capability = getattr(self._facade, "supports_formal_live_voice", None)
        return bool(
            callable(capability)
            and capability()
            and callable(
                getattr(self._facade, "process_formal_live_voice_stream", None)
            )
        )

    @staticmethod
    def _validate_dispatch_channel(channel_id: str) -> None:
        if not isinstance(channel_id, str) or not channel_id.strip():
            raise AgentConversationRuntimeViolation(
                "INVALID_DISPATCH_CHANNEL",
                "formal Agent channel_id must be non-empty",
                ErrorCode.INVALID_ARGUMENT,
            )
        try:
            channel_id.encode("utf-8")
        except UnicodeEncodeError as error:
            raise AgentConversationRuntimeViolation(
                "INVALID_DISPATCH_CHANNEL",
                "formal Agent channel_id must contain Unicode scalar values",
                ErrorCode.INVALID_ARGUMENT,
            ) from error

    @staticmethod
    def _unwrap_admission(outcome: _AdmissionOutcome) -> AgentConversationHandle:
        if outcome.error is not None:
            raise outcome.error
        assert outcome.handle is not None
        return outcome.handle

    @staticmethod
    def _admission_fingerprint(
        *,
        request_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        context: FormalContextSnapshot,
        channel_id: str,
    ) -> bytes:
        return canonical_json_bytes(
            {
                "request_id": request_id,
                "response_id": response_id,
                "correlation_id": correlation_id,
                "commit": commit.to_dict(),
                "context": [
                    {
                        "ref": entry.ref.to_dict(),
                        "content": entry.content,
                    }
                    for entry in context.entries
                ],
                "channel_id": channel_id,
            }
        )
