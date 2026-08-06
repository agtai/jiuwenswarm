# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Product-consumable Agent Bridge + Conversation Runtime composition seam."""

from __future__ import annotations

import asyncio
import hashlib
import math
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
    PresentationSurface,
    PresentationUnit,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)


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
        if type(notification_capacity) is not int or notification_capacity <= 0:
            raise AgentConversationRuntimeViolation(
                "INVALID_COMPOSITION_CAPACITY",
                "notification_capacity must be a positive integer",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._scope = scope
        self._instance_id = instance_id
        self._facade = facade
        self._enabled = enabled
        self._cr = ConversationRuntimeLoop(scope, enabled=enabled)
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
        self._notifications: asyncio.Queue[AgentConversationNotification] = (
            asyncio.Queue(maxsize=notification_capacity)
        )
        self._commits: dict[str, TurnCommit] = {}
        self._admissions: dict[str, _AdmissionEntry] = {}
        self._handles: dict[str, AgentConversationHandle] = {}
        self._round_handles: dict[str, HarnessRoundHandle] = {}
        self._outputs: dict[ResponseRef, _ResponseOutputState] = {}
        self._ack_results: dict[
            tuple[ResponseRef, PresentationSurface, int],
            tuple[PresentationAck, PresentationAckResult],
        ] = {}
        self._pending_history: dict[
            tuple[ResponseRef, PresentationSurface, int],
            tuple[PresentationHistoryIntent, str, str],
        ] = {}
        self._pending_user_history: dict[str, tuple[TurnCommit, str]] = {}
        self._history_tasks: set[asyncio.Task[None]] = set()
        self._ack_lock = asyncio.Lock()
        self._closing_interactions: set[str] = set()
        self._consumer: asyncio.Task[None] | None = None
        self._shutdown: asyncio.Task[AgentConversationShutdownResult] | None = None
        self._started = False
        self._accepting = False
        self._closed = not enabled

    async def start(self) -> bool:
        if not self._enabled:
            return False
        if not self._facade_available():
            return False
        if self._started:
            return False
        if self._closed:
            raise AgentConversationRuntimeViolation(
                "COMPOSITION_CLOSED",
                "a closed composition cannot restart",
                ErrorCode.CONFLICT,
            )
        await self._cr.start()
        await self._bridge.start()
        self._consumer = asyncio.create_task(
            self._consume_bridge(), name="live-voice-agent-cr-consumer"
        )
        self._started = True
        self._accepting = True
        return True

    async def open_interaction(self, interaction_id: str) -> None:
        self._require_admission()
        await self._cr.open_interaction(interaction_id)

    async def start_turn(self, interaction_id: str, turn_id: str) -> None:
        self._require_admission()
        await self._cr.start_turn(interaction_id, turn_id)

    async def commit_turn(self, commit: TurnCommit) -> bool:
        self._require_admission()
        if not isinstance(commit, TurnCommit) or commit.scope != self._scope:
            raise AgentConversationRuntimeViolation(
                "INVALID_COMMITTED_TURN",
                "TurnCommit must match the exact composition scope",
                ErrorCode.PERMISSION_DENIED,
            )
        accepted, _event = await self._cr.commit_turn(commit)
        prior = self._commits.get(commit.turn_id)
        if prior is not None and prior.canonical_bytes() != commit.canonical_bytes():
            raise AgentConversationRuntimeViolation(
                "TURN_COMMIT_CONFLICT",
                "a committed turn cannot change its immutable bytes",
                ErrorCode.CONFLICT,
            )
        self._commits[commit.turn_id] = commit
        return accepted

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
        existing = self._admissions.get(request_id)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise AgentConversationRuntimeViolation(
                    "COMPOSITION_REQUEST_ID_CONFLICT",
                    "request_id cannot change its formal dispatch binding",
                    ErrorCode.CONFLICT,
                )
            return self._unwrap_admission(await asyncio.shield(existing.outcome))

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
        coordinator = running.create_task(
            self._complete_admission(
                entry,
                context=context,
                channel_id=channel_id,
            ),
            name=f"live-voice-agent-admission:{request_id}",
        )
        entry.coordinator = coordinator
        return self._unwrap_admission(await asyncio.shield(outcome))

    async def next_notification(self) -> AgentConversationNotification:
        if not self._enabled:
            raise AgentConversationRuntimeViolation(
                "FEATURE_DISABLED",
                "formal Agent composition is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        return await self._notifications.get()

    async def acknowledge_presentation(
        self, ack: PresentationAck
    ) -> PresentationAckResult:
        self._require_started()
        async with self._ack_lock:
            return await self._acknowledge_presentation(ack)

    async def _acknowledge_presentation(
        self, ack: PresentationAck
    ) -> PresentationAckResult:
        if not isinstance(ack, PresentationAck):
            raise AgentConversationRuntimeViolation(
                "INVALID_PRESENTATION_ACK",
                "acknowledgement has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        key = (ack.ref, ack.surface, ack.contiguous_cursor)
        prior = self._ack_results.get(key)
        if prior is not None:
            prior_ack, prior_result = prior
            if prior_ack != ack:
                raise AgentConversationRuntimeViolation(
                    "PRESENTATION_ACK_CONFLICT",
                    "an exact ACK cursor cannot change its binding",
                    ErrorCode.CONFLICT,
                )
            return replace(prior_result, replayed=True)
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
        self._ack_results[key] = (ack, result)
        return result

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
        if not self._started:
            self._accepting = False
            self._closed = True
            detail = (
                "formal_agent_unavailable"
                if not self._facade_available()
                else "not_started"
            )
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.CLOSED, detail
            )
        if self._shutdown is None:
            self._accepting = False
            self._shutdown = asyncio.create_task(
                self._shutdown_coordinator(), name="live-voice-agent-cr-close"
            )
        try:
            return await asyncio.wait_for(
                asyncio.shield(self._shutdown), timeout=float(timeout_seconds)
            )
        except TimeoutError:
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.PENDING,
                "retained_teardown_still_running",
            )

    def snapshot(self) -> AgentConversationRuntimeSnapshot:
        return AgentConversationRuntimeSnapshot(
            enabled=self._enabled,
            started=self._started,
            accepting=self._accepting,
            closed=self._closed,
            closing=self._shutdown is not None and not self._closed,
            retained_admissions=len(self._admissions),
            active_requests=tuple(
                state.request_id
                for state in self._outputs.values()
                if state.terminal_event is None
            ),
            queued_notifications=self._notifications.qsize(),
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
        await self._publish(
            AgentConversationNotification(
                kind="agent.output",
                request_id=request.request_id,
                round_id=request.round_id,
                response_ref=request.response_ref,
                agent_event=consumable_event,
                presentation_unit=presentation,
                error_reason=error_reason,
            )
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
        await self._publish(
            AgentConversationNotification(
                kind="work.progress",
                request_id=request.request_id,
                round_id=request.round_id,
                response_ref=request.response_ref,
                source_event=delivery.source_event,
                progress_event=delivery.progress_event,
                error_reason=error_reason,
            )
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

    async def _publish(self, notification: AgentConversationNotification) -> None:
        await self._notifications.put(notification)

    async def _shutdown_coordinator(self) -> AgentConversationShutdownResult:
        try:
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
            async with self._ack_lock:
                history_tasks = tuple(self._history_tasks)
                if history_tasks:
                    await asyncio.shield(
                        asyncio.gather(*history_tasks, return_exceptions=True)
                    )
            await self._cr.close()
            if self._pending_history or self._pending_user_history:
                return AgentConversationShutdownResult(
                    AgentConversationShutdownStatus.FAILED,
                    "history_write_intents_pending",
                )
            self._closed = True
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.CLOSED, "teardown_complete"
            )
        except BaseException as error:  # noqa: BLE001
            return AgentConversationShutdownResult(
                AgentConversationShutdownStatus.FAILED,
                f"teardown_failed:{type(error).__name__}",
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
