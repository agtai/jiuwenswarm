# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Harness-owned round reservation, lifecycle, and exact cancellation."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CancelScope,
    CommandEnvelope,
    ErrorCode,
    EventEnvelope,
    IdentityKind,
    ResponseRef,
    TerminalOutcome,
    TurnCommit,
    canonical_json_bytes,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalAgentExecution,
    FormalContextSnapshot,
)


_STREAM_CLOSE_WAIT_SLICE_SECONDS = 5.0
_ROUND_CONTROL_QUEUE_RESERVE = 4


class HarnessRoundViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HarnessRoundViolation(
            "INVALID_HARNESS_ROUND_INPUT",
            f"{field_name} must be a non-empty string",
            ErrorCode.INVALID_ARGUMENT,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise HarnessRoundViolation(
            "INVALID_HARNESS_ROUND_INPUT",
            f"{field_name} must contain only Unicode scalar values",
            ErrorCode.INVALID_ARGUMENT,
        ) from error
    return value


class HarnessReservationState(StrEnum):
    RESERVED = "reserved"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTED = "aborted"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class HarnessRoundBinding:
    request_id: str
    response_id: str
    correlation_id: str
    commit: TurnCommit

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_text(self.response_id, "response_id")
        _require_text(self.correlation_id, "correlation_id")
        if not isinstance(self.commit, TurnCommit):
            raise HarnessRoundViolation(
                "INVALID_HARNESS_ROUND_INPUT",
                "round binding requires a canonical TurnCommit",
                ErrorCode.INVALID_ARGUMENT,
            )

    def fingerprint(self) -> bytes:
        return canonical_json_bytes(
            {
                "request_id": self.request_id,
                "response_id": self.response_id,
                "correlation_id": self.correlation_id,
                "commit": self.commit.to_dict(),
            }
        )


@dataclass(frozen=True, slots=True)
class HarnessRoundReservation:
    owner_instance_id: str
    round_id: str
    reservation_token: str
    binding: HarnessRoundBinding
    capabilities: tuple[str, ...]
    expires_at_monotonic: float


@dataclass(frozen=True, slots=True)
class RoundCancelResult:
    command_id: str
    request_id: str
    round_id: str
    accepted: bool
    replayed: bool
    reason: str
    terminal_observed: bool


@dataclass(frozen=True, slots=True)
class HarnessRoundSnapshot:
    enabled: bool
    accepting: bool
    closed: bool
    reservations: tuple[tuple[str, HarnessReservationState], ...]
    active_rounds: tuple[str, ...]
    retained_rounds: int
    cancel_effects: int
    detached_subscriptions: int


class FormalAgentFacade(Protocol):
    def supports_formal_live_voice(self) -> bool: ...

    def process_formal_live_voice_stream(
        self, execution: FormalAgentExecution
    ) -> AsyncIterator[AgentResponseChunk]: ...


@dataclass(slots=True)
class _ReservationRecord:
    reservation: HarnessRoundReservation
    fingerprint: bytes
    state: HarnessReservationState
    facade: FormalAgentFacade | None = None
    abort_reason: str | None = None
    handle: HarnessRoundHandle | None = None


@dataclass(slots=True)
class _RoundRecord:
    reservation: HarnessRoundReservation
    response_ref: ResponseRef
    handle: HarnessRoundHandle
    task: asyncio.Task[None]
    started: asyncio.Event
    cancel_safe: asyncio.Event
    terminal_event: EventEnvelope | None = None
    execution_error: BaseException | None = None
    cancel_requested: bool = False
    cancel_observed: bool = False
    cancel_coordinator: asyncio.Task[None] | None = None


_END = object()


class HarnessRoundHandle:
    """Trusted handle for one exact Harness-owned round."""

    __slots__ = (
        "_harness",
        "_reservation",
        "_response_ref",
        "_queue",
        "_payload_slots",
        "_subscribed",
        "_detached",
        "_detached_event",
    )

    def __init__(
        self,
        harness: JiuWenSwarmRoundHarness,
        reservation: HarnessRoundReservation,
        response_ref: ResponseRef,
        *,
        output_capacity: int,
    ) -> None:
        self._harness = harness
        self._reservation = reservation
        self._response_ref = response_ref
        self._queue: asyncio.Queue[AgentResponseChunk | EventEnvelope | object] = (
            asyncio.Queue(maxsize=output_capacity + _ROUND_CONTROL_QUEUE_RESERVE)
        )
        self._payload_slots = asyncio.Semaphore(output_capacity)
        self._subscribed = False
        self._detached = False
        self._detached_event = asyncio.Event()

    @property
    def reservation(self) -> HarnessRoundReservation:
        return self._reservation

    @property
    def response_ref(self) -> ResponseRef:
        return self._response_ref

    @property
    def round_id(self) -> str:
        return self._reservation.round_id

    @property
    def terminal_event(self) -> EventEnvelope | None:
        return self._harness.terminal_event(self)

    async def events(self) -> AsyncIterator[AgentResponseChunk | EventEnvelope]:
        self._harness.require_handle(self)
        if self._subscribed:
            raise HarnessRoundViolation(
                "ROUND_SUBSCRIPTION_ALREADY_CLAIMED",
                "a round output subscription has one consumer",
                ErrorCode.CONFLICT,
            )
        self._subscribed = True
        try:
            while True:
                item = await self._queue.get()
                if item is _END:
                    return
                assert isinstance(item, (AgentResponseChunk, EventEnvelope))
                if isinstance(item, AgentResponseChunk):
                    self._payload_slots.release()
                yield item
        finally:
            self.detach()

    def cancel(self, command: CommandEnvelope) -> RoundCancelResult:
        return self._harness.cancel_round(self, command)

    def detach(self) -> bool:
        if self._detached:
            return False
        self._detached = True
        self._detached_event.set()
        self._harness.detach(self)
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(item, AgentResponseChunk):
                self._payload_slots.release()
        self._queue.put_nowait(_END)
        return True

    async def _put(self, item: AgentResponseChunk | EventEnvelope | object) -> bool:
        if self._detached:
            return False
        payload_slot = False
        if isinstance(item, AgentResponseChunk):
            if not await self._acquire_payload_slot():
                return False
            payload_slot = True
        try:
            # Payload slots bound Agent output independently from the four
            # Harness-owned control records.  With the accounting invariant in
            # place, publication itself cannot block the round/cancel loop.
            self._queue.put_nowait(item)
            return True
        except asyncio.QueueFull as error:
            if payload_slot:
                self._payload_slots.release()
            raise HarnessRoundViolation(
                "HARNESS_OUTPUT_ACCOUNTING_FAILURE",
                "reserved lifecycle output capacity was exhausted",
                ErrorCode.PROTOCOL_VIOLATION,
            ) from error

    async def _acquire_payload_slot(self) -> bool:
        acquire_task = asyncio.create_task(self._payload_slots.acquire())
        detached_task = asyncio.create_task(self._detached_event.wait())
        keep_slot = False
        try:
            done, _ = await asyncio.wait(
                (acquire_task, detached_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._detached or detached_task in done:
                return False
            await acquire_task
            keep_slot = True
            return True
        finally:
            for task in (acquire_task, detached_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                acquire_task,
                detached_task,
                return_exceptions=True,
            )
            acquired = (
                acquire_task.done()
                and not acquire_task.cancelled()
                and acquire_task.exception() is None
            )
            if acquired and not keep_slot:
                self._payload_slots.release()


class JiuWenSwarmRoundHarness:
    """Owns actual Agent round identity and lifecycle facts."""

    _CAPABILITIES = (
        "round.accepted",
        "round.running",
        "round.terminal",
        "round.cancel",
        "round.detach",
    )

    def __init__(
        self,
        *,
        instance_id: str,
        enabled: bool = True,
        max_reservations: int = 256,
        max_active_rounds: int = 4,
        output_capacity: int = 32,
        reservation_ttl_seconds: float = 5.0,
        monotonic: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        _require_text(instance_id, "instance_id")
        if type(enabled) is not bool:
            raise HarnessRoundViolation(
                "INVALID_HARNESS_CONFIGURATION",
                "enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        for name, value in (
            ("max_reservations", max_reservations),
            ("max_active_rounds", max_active_rounds),
            ("output_capacity", output_capacity),
        ):
            if type(value) is not int or value <= 0:
                raise HarnessRoundViolation(
                    "INVALID_HARNESS_CONFIGURATION",
                    f"{name} must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if (
            isinstance(reservation_ttl_seconds, bool)
            or not isinstance(reservation_ttl_seconds, (int, float))
            or not math.isfinite(reservation_ttl_seconds)
            or reservation_ttl_seconds <= 0
        ):
            raise HarnessRoundViolation(
                "INVALID_HARNESS_CONFIGURATION",
                "reservation_ttl_seconds must be positive and finite",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._instance_id = instance_id
        self._enabled = enabled
        self._max_reservations = max_reservations
        self._max_active_rounds = max_active_rounds
        self._output_capacity = output_capacity
        self._reservation_ttl_seconds = float(reservation_ttl_seconds)
        self._monotonic = monotonic
        self._id_factory = id_factory or (lambda: secrets.token_hex(16))
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._reservations: dict[str, _ReservationRecord] = {}
        self._rounds: dict[str, _RoundRecord] = {}
        self._round_tokens: dict[str, str] = {}
        self._cancel_results: dict[str, tuple[bytes, RoundCancelResult]] = {}
        self._accepting = enabled
        self._closed = not enabled
        self._close_task: asyncio.Task[None] | None = None
        self._cancel_effects = 0
        self._detached_subscriptions = 0

    def reserve_round(
        self,
        binding: HarnessRoundBinding,
        *,
        facade: FormalAgentFacade | None = None,
    ) -> HarnessRoundReservation:
        running = self._require_admission()
        if not isinstance(binding, HarnessRoundBinding):
            raise HarnessRoundViolation(
                "INVALID_HARNESS_ROUND_INPUT",
                "round reservation requires a canonical binding",
                ErrorCode.INVALID_ARGUMENT,
            )
        if facade is not None:
            self._require_formal_facade(facade)
        for retained in self._reservations.values():
            self._expire(retained)
        fingerprint = binding.fingerprint()
        existing = self._reservations.get(binding.request_id)
        if existing is not None:
            self._expire(existing)
            if existing.fingerprint != fingerprint:
                raise HarnessRoundViolation(
                    "HARNESS_REQUEST_ID_CONFLICT",
                    "request_id cannot change its Harness round binding",
                    ErrorCode.CONFLICT,
                )
            if existing.facade is not facade:
                raise HarnessRoundViolation(
                    "HARNESS_FACADE_BINDING_CONFLICT",
                    "request_id cannot change its formal Agent facade binding",
                    ErrorCode.CONFLICT,
                )
            return existing.reservation
        if len(self._reservations) >= self._max_reservations:
            raise HarnessRoundViolation(
                "HARNESS_RESERVATION_LEDGER_FULL",
                "the bounded Harness reservation ledger is full",
                ErrorCode.UNAVAILABLE,
            )
        active_or_reserved = sum(
            record.state
            in {
                HarnessReservationState.RESERVED,
                HarnessReservationState.COMMITTING,
            }
            or (
                record.state is HarnessReservationState.COMMITTED
                and record.handle is not None
                and self._rounds[record.handle.round_id].terminal_event is None
            )
            for record in self._reservations.values()
        )
        if active_or_reserved >= self._max_active_rounds:
            raise HarnessRoundViolation(
                "HARNESS_ADMISSION_FULL",
                "the bounded Harness round capacity is full",
                ErrorCode.UNAVAILABLE,
            )
        round_token = _require_text(self._id_factory(), "round token")
        round_id = f"round-{round_token}"
        if round_id in self._round_tokens:
            raise HarnessRoundViolation(
                "HARNESS_ROUND_ID_COLLISION",
                "Harness round allocation collided",
                ErrorCode.CONFLICT,
            )
        reservation_token = _require_text(self._id_factory(), "reservation token")
        reservation = HarnessRoundReservation(
            owner_instance_id=self._instance_id,
            round_id=round_id,
            reservation_token=reservation_token,
            binding=binding,
            capabilities=self._CAPABILITIES,
            expires_at_monotonic=(self._monotonic() + self._reservation_ttl_seconds),
        )
        self._owner_loop = running
        self._round_tokens[round_id] = reservation_token
        self._reservations[binding.request_id] = _ReservationRecord(
            reservation=reservation,
            fingerprint=fingerprint,
            state=HarnessReservationState.RESERVED,
            facade=facade,
        )
        return reservation

    def commit_round(
        self,
        reservation: HarnessRoundReservation,
        *,
        response_ref: ResponseRef,
        context: FormalContextSnapshot,
        facade: FormalAgentFacade,
        channel_id: str = "web",
        allow_tools: bool = True,
    ) -> HarnessRoundHandle:
        running = self._require_owner()
        record = self._require_reservation(reservation)
        self._expire(record)
        if record.state is HarnessReservationState.COMMITTED:
            assert record.handle is not None
            if record.handle.response_ref != response_ref:
                raise HarnessRoundViolation(
                    "HARNESS_COMMIT_CONFLICT",
                    "a committed round cannot change its ResponseRef",
                    ErrorCode.CONFLICT,
                )
            return record.handle
        if record.state is HarnessReservationState.RESERVED:
            record.state = HarnessReservationState.COMMITTING
        if record.state is not HarnessReservationState.COMMITTING:
            raise HarnessRoundViolation(
                "HARNESS_RESERVATION_NOT_COMMITTABLE",
                f"reservation is {record.state.value}",
                ErrorCode.STALE,
            )
        if not isinstance(response_ref, ResponseRef):
            raise HarnessRoundViolation(
                "INVALID_HARNESS_ROUND_INPUT",
                "round commit requires a canonical ResponseRef",
                ErrorCode.INVALID_ARGUMENT,
            )
        binding = reservation.binding
        if response_ref.interaction_id != binding.commit.interaction_id:
            raise HarnessRoundViolation(
                "HARNESS_RESPONSE_SCOPE_MISMATCH",
                "ResponseRef must belong to the committed interaction",
                ErrorCode.PERMISSION_DENIED,
            )
        if not isinstance(context, FormalContextSnapshot):
            raise HarnessRoundViolation(
                "INVALID_HARNESS_ROUND_INPUT",
                "round commit requires immutable selected context",
                ErrorCode.INVALID_ARGUMENT,
            )
        context.validate_for(binding.commit)
        _require_text(channel_id, "channel_id")
        if type(allow_tools) is not bool:
            raise HarnessRoundViolation(
                "INVALID_HARNESS_ROUND_INPUT",
                "round tool policy must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        if record.facade is not None and facade is not record.facade:
            raise HarnessRoundViolation(
                "HARNESS_FACADE_BINDING_CONFLICT",
                "a reserved round cannot change its formal Agent facade",
                ErrorCode.CONFLICT,
            )
        if record.facade is None:
            self._require_formal_facade(facade)
        handle = HarnessRoundHandle(
            self,
            reservation,
            response_ref,
            output_capacity=self._output_capacity,
        )
        execution = FormalAgentExecution(
            request_id=binding.request_id,
            channel_id=channel_id,
            internal_session_id=f"lv-formal-{reservation.reservation_token}",
            commit=binding.commit,
            context=context,
            allow_tools=allow_tools
            and not any(
                entry.ref.source == "live_voice.task_result"
                for entry in context.entries
            ),
        )
        started = asyncio.Event()
        cancel_safe = asyncio.Event()
        task = running.create_task(
            self._run_round(handle, execution, facade),
            name=f"live-voice-harness-round:{reservation.round_id}",
        )
        self._rounds[reservation.round_id] = _RoundRecord(
            reservation=reservation,
            response_ref=response_ref,
            handle=handle,
            task=task,
            started=started,
            cancel_safe=cancel_safe,
        )
        record.state = HarnessReservationState.COMMITTED
        record.handle = handle
        return handle

    def begin_round_commit(self, reservation: HarnessRoundReservation) -> bool:
        self._require_owner()
        record = self._require_reservation(reservation)
        self._expire(record)
        if record.state in {
            HarnessReservationState.COMMITTING,
            HarnessReservationState.COMMITTED,
        }:
            return False
        if record.state is not HarnessReservationState.RESERVED:
            raise HarnessRoundViolation(
                "HARNESS_RESERVATION_NOT_COMMITTABLE",
                f"reservation is {record.state.value}",
                ErrorCode.STALE,
            )
        record.state = HarnessReservationState.COMMITTING
        return True

    def abort_round_reservation(
        self, reservation: HarnessRoundReservation, *, reason: str
    ) -> bool:
        self._require_owner()
        record = self._require_reservation(reservation)
        _require_text(reason, "reason")
        self._expire(record)
        if record.state is HarnessReservationState.ABORTED:
            return False
        if record.state is HarnessReservationState.EXPIRED:
            return False
        if record.state is HarnessReservationState.COMMITTED:
            raise HarnessRoundViolation(
                "HARNESS_RESERVATION_ALREADY_COMMITTED",
                "a committed round cannot be converted into an abort",
                ErrorCode.CONFLICT,
            )
        record.state = HarnessReservationState.ABORTED
        record.abort_reason = reason
        return True

    def rollback_unstarted_round(
        self, reservation: HarnessRoundReservation, *, reason: str
    ) -> bool:
        """Synchronously revoke a just-committed round before it can run.

        ``commit_round`` schedules the task on this same event loop.  The
        composition owner may still need to persist a durable dispatch
        checkpoint before yielding control.  If that synchronous checkpoint
        fails, this method proves that the task has not entered ``_run_round``,
        cancels it, and removes the committed handle.  It must never be used
        after the event loop has had an opportunity to start the round.
        """

        self._require_owner()
        record = self._require_reservation(reservation)
        _require_text(reason, "reason")
        if record.state is HarnessReservationState.ABORTED:
            return False
        if record.state is not HarnessReservationState.COMMITTED:
            raise HarnessRoundViolation(
                "HARNESS_ROUND_NOT_ROLLBACKABLE",
                "only a committed, unstarted round can be rolled back",
                ErrorCode.CONFLICT,
            )
        handle = record.handle
        if handle is None:
            raise HarnessRoundViolation(
                "HARNESS_ROUND_NOT_ROLLBACKABLE",
                "committed round has no exact handle",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        round_record = self._rounds.get(handle.round_id)
        if round_record is None or round_record.started.is_set():
            raise HarnessRoundViolation(
                "HARNESS_ROUND_ALREADY_STARTED",
                "a started round cannot be rolled back",
                ErrorCode.CONFLICT,
            )
        round_record.task.cancel()
        self._rounds.pop(handle.round_id, None)
        record.state = HarnessReservationState.ABORTED
        record.abort_reason = reason
        record.handle = None
        return True

    def cancel_round(
        self, handle: HarnessRoundHandle, command: CommandEnvelope
    ) -> RoundCancelResult:
        self._require_owner()
        round_record = self._require_handle_record(handle)
        if not isinstance(command, CommandEnvelope):
            raise HarnessRoundViolation(
                "INVALID_ROUND_CANCEL",
                "round cancel requires a canonical CommandEnvelope",
                ErrorCode.INVALID_ARGUMENT,
            )
        fingerprint = canonical_json_bytes(command.to_dict())
        prior = self._cancel_results.get(command.command_id)
        if prior is not None:
            prior_fingerprint, prior_result = prior
            if prior_fingerprint != fingerprint:
                raise HarnessRoundViolation(
                    "IDEMPOTENCY_CONFLICT",
                    "command_id cannot change its exact round cancel binding",
                    ErrorCode.CONFLICT,
                )
            return RoundCancelResult(
                command_id=prior_result.command_id,
                request_id=prior_result.request_id,
                round_id=prior_result.round_id,
                accepted=prior_result.accepted,
                replayed=True,
                reason=prior_result.reason,
                terminal_observed=prior_result.terminal_observed,
            )

        reservation = round_record.reservation
        binding = reservation.binding
        rejection: str | None = None
        if command.command_type != CancelScope.ROUND_CANCEL.value:
            rejection = "WRONG_CANCEL_SCOPE"
        elif command.scope != binding.commit.scope:
            rejection = "ROUND_CANCEL_SCOPE_MISMATCH"
        elif command.request_id != binding.request_id:
            rejection = "ROUND_CANCEL_REQUEST_MISMATCH"
        elif command.target_ref.kind is not IdentityKind.ROUND:
            rejection = "ROUND_CANCEL_TARGET_KIND_MISMATCH"
        elif command.target_ref.id != reservation.round_id:
            rejection = "ROUND_CANCEL_TARGET_MISMATCH"
        elif command.correlation_id != binding.correlation_id:
            rejection = "ROUND_CANCEL_CORRELATION_MISMATCH"
        elif (
            command.origin.kind != "committed_turn"
            or command.origin.turn_id != binding.commit.turn_id
            or command.origin.commit_id != binding.commit.commit_id
        ):
            rejection = "ROUND_CANCEL_ORIGIN_MISMATCH"
        elif round_record.terminal_event is not None or round_record.task.done():
            rejection = "ROUND_ALREADY_TERMINAL"
        elif round_record.cancel_requested:
            rejection = "ROUND_CANCEL_ALREADY_REQUESTED"

        accepted = False
        if rejection is None:
            accepted = True
            round_record.cancel_requested = True
            self._cancel_effects += 1
            round_record.cancel_coordinator = asyncio.create_task(
                self._deliver_exact_cancel(round_record),
                name=f"live-voice-harness-cancel:{reservation.round_id}",
            )
        result = RoundCancelResult(
            command_id=command.command_id,
            request_id=command.request_id,
            round_id=reservation.round_id,
            accepted=accepted,
            replayed=False,
            reason="CANCEL_ACCEPTED" if accepted else rejection or "CANCEL_REJECTED",
            terminal_observed=round_record.terminal_event is not None,
        )
        self._cancel_results[command.command_id] = (fingerprint, result)
        return result

    def terminal_event(self, handle: HarnessRoundHandle) -> EventEnvelope | None:
        return self._require_handle_record(handle).terminal_event

    def require_handle(self, handle: HarnessRoundHandle) -> None:
        self._require_handle_record(handle)

    def detach(self, handle: HarnessRoundHandle) -> None:
        self._require_handle_record(handle)
        self._detached_subscriptions += 1

    async def close(self) -> None:
        if self._closed:
            return
        running = self._require_owner()
        self._accepting = False
        if self._close_task is None:
            self._close_task = running.create_task(
                self._close_coordinator(), name="live-voice-harness-close"
            )
        await asyncio.shield(self._close_task)

    def snapshot(self) -> HarnessRoundSnapshot:
        for record in self._reservations.values():
            self._expire(record)
        return HarnessRoundSnapshot(
            enabled=self._enabled,
            accepting=self._accepting,
            closed=self._closed,
            reservations=tuple(
                (request_id, record.state)
                for request_id, record in self._reservations.items()
            ),
            active_rounds=tuple(
                round_id
                for round_id, record in self._rounds.items()
                if record.terminal_event is None
            ),
            retained_rounds=len(self._rounds),
            cancel_effects=self._cancel_effects,
            detached_subscriptions=self._detached_subscriptions,
        )

    async def _run_round(
        self,
        handle: HarnessRoundHandle,
        execution: FormalAgentExecution,
        facade: FormalAgentFacade,
    ) -> None:
        record = self._require_handle_record(handle)
        seq = 0
        prior_event_id: str | None = None
        usable_final = False
        execution_reported_error = False
        outcome = TerminalOutcome.UNKNOWN
        source_stream: AsyncIterator[AgentResponseChunk] | None = None
        record.started.set()
        try:
            accepted = self._round_event(
                record.reservation, seq=seq, state="accepted", causation_id=None
            )
            prior_event_id = accepted.event_id
            seq += 1
            await handle._put(accepted)
            running = self._round_event(
                record.reservation,
                seq=seq,
                state="running",
                causation_id=prior_event_id,
            )
            prior_event_id = running.event_id
            seq += 1
            await handle._put(running)
            record.cancel_safe.set()
            if record.cancel_requested:
                record.cancel_observed = True
                raise asyncio.CancelledError
            source_stream = facade.process_formal_live_voice_stream(execution)
            async for chunk in source_stream:
                self._validate_chunk(chunk, execution)
                payload = chunk.payload if isinstance(chunk.payload, dict) else {}
                if payload.get("event_type") == "chat.final":
                    content = payload.get("content")
                    is_usable = isinstance(content, str) and bool(content.strip())
                    if usable_final and is_usable:
                        raise HarnessRoundViolation(
                            "DUPLICATE_AGENT_FINAL",
                            "formal Agent execution emitted more than one usable final",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    usable_final = usable_final or is_usable
                elif payload.get("event_type") == "chat.error":
                    execution_reported_error = True
                await handle._put(chunk)
            if execution_reported_error:
                outcome = TerminalOutcome.FAILED
            elif usable_final:
                outcome = TerminalOutcome.COMPLETED
            else:
                outcome = TerminalOutcome.UNKNOWN
        except asyncio.CancelledError:
            if not record.cancel_requested:
                raise
            record.cancel_observed = True
            outcome = TerminalOutcome.CANCELLED
        except BaseException as error:  # noqa: BLE001
            record.execution_error = error
            outcome = TerminalOutcome.FAILED
        finally:
            record.started.set()
            record.cancel_safe.set()
            close = getattr(source_stream, "aclose", None)
            if callable(close):
                cleanup = asyncio.create_task(
                    close(),
                    name=f"live-voice-harness-stream-close:{handle.round_id}",
                )
                try:
                    await self._await_retained_cleanup(cleanup)
                except BaseException as error:  # noqa: BLE001
                    record.execution_error = error
                    outcome = TerminalOutcome.FAILED
        terminal = self._round_event(
            record.reservation,
            seq=seq,
            state="terminal",
            outcome=outcome,
            causation_id=prior_event_id,
        )
        record.terminal_event = terminal
        await handle._put(terminal)
        await handle._put(_END)

    async def _deliver_exact_cancel(self, record: _RoundRecord) -> None:
        """Deliver one accepted cancel only after the owned task can settle it.

        Deferring ``Task.cancel`` until ``_run_round`` has entered and emitted
        accepted/running closes the create-task/immediate-cancel hole without
        interrupting canonical lifecycle order.  The task always retains
        cleanup and terminal ownership.  The ACK returned by ``cancel_round``
        remains distinct from the later terminal event, and normal completion
        may still win before this coordinator observes an active task.
        """

        await record.started.wait()
        await record.cancel_safe.wait()
        if (
            not record.cancel_observed
            and record.terminal_event is None
            and not record.task.done()
        ):
            record.task.cancel()

    @staticmethod
    async def _await_retained_cleanup(cleanup: asyncio.Task[None]) -> None:
        while not cleanup.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(cleanup),
                    timeout=_STREAM_CLOSE_WAIT_SLICE_SECONDS,
                )
            except TimeoutError:
                continue
        await asyncio.shield(cleanup)

    async def _close_coordinator(self) -> None:
        tasks = tuple(record.task for record in self._rounds.values())
        if tasks:
            await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
        cancel_coordinators = tuple(
            record.cancel_coordinator
            for record in self._rounds.values()
            if record.cancel_coordinator is not None
        )
        if cancel_coordinators:
            await asyncio.shield(
                asyncio.gather(*cancel_coordinators, return_exceptions=True)
            )
        self._closed = True

    def _round_event(
        self,
        reservation: HarnessRoundReservation,
        *,
        seq: int,
        state: str,
        causation_id: str | None,
        outcome: TerminalOutcome | None = None,
    ) -> EventEnvelope:
        payload: dict[str, object] = {"state": state}
        if state == "terminal":
            assert outcome is not None
            payload["outcome"] = outcome.value
        token = reservation.round_id.encode("utf-8").hex()
        return EventEnvelope.from_dict(
            {
                "contract_version": "live-voice.contract.v2",
                "event_id": f"harness:{self._instance_id}:{token}:{seq}",
                "event_type": f"round.{state}",
                "producer": {
                    "component": "jiuwenswarm.agent_harness",
                    "instance_id": self._instance_id,
                    "authority": "harness",
                },
                "stream_ref": {
                    "kind": IdentityKind.ROUND.value,
                    "id": reservation.round_id,
                },
                "seq": seq,
                "occurred_at": self._timestamp(),
                "scope": reservation.binding.commit.scope.to_dict(),
                "correlation_id": reservation.binding.correlation_id,
                "causation_id": causation_id,
                "required_capabilities": [],
                "payload": payload,
                "extensions": {},
            }
        )

    @staticmethod
    def _validate_chunk(
        chunk: AgentResponseChunk, execution: FormalAgentExecution
    ) -> None:
        if not isinstance(chunk, AgentResponseChunk):
            raise HarnessRoundViolation(
                "INVALID_FORMAL_AGENT_OUTPUT",
                "formal Agent facade emitted an unsupported item",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if (
            chunk.request_id != execution.request_id
            or chunk.channel_id != execution.channel_id
            or not isinstance(chunk.payload, dict)
        ):
            raise HarnessRoundViolation(
                "INVALID_FORMAL_AGENT_OUTPUT",
                "formal Agent output changed request provenance",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    @staticmethod
    def _require_formal_facade(facade: FormalAgentFacade) -> None:
        capability = getattr(facade, "supports_formal_live_voice", None)
        if (
            not callable(capability)
            or not capability()
            or not callable(getattr(facade, "process_formal_live_voice_stream", None))
        ):
            raise HarnessRoundViolation(
                "FORMAL_AGENT_FACADE_UNAVAILABLE",
                "Agent facade does not expose the formal no-history seam",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )

    def _require_admission(self) -> asyncio.AbstractEventLoop:
        if not self._enabled:
            raise HarnessRoundViolation(
                "FEATURE_DISABLED",
                "Harness round execution is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        if not self._accepting or self._closed:
            raise HarnessRoundViolation(
                "HARNESS_CLOSING",
                "Harness round execution is not accepting work",
                ErrorCode.CONFLICT,
            )
        return self._require_owner()

    def _require_owner(self) -> asyncio.AbstractEventLoop:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError as error:
            raise HarnessRoundViolation(
                "HARNESS_EVENT_LOOP_REQUIRED",
                "Harness round operations require a running event loop",
                ErrorCode.CONFLICT,
            ) from error
        if self._owner_loop is not None and running is not self._owner_loop:
            raise HarnessRoundViolation(
                "HARNESS_EVENT_LOOP_MISMATCH",
                "Harness round operations must stay on their owner loop",
                ErrorCode.CONFLICT,
            )
        if self._owner_loop is None:
            self._owner_loop = running
        return running

    def _require_reservation(
        self, reservation: HarnessRoundReservation
    ) -> _ReservationRecord:
        if not isinstance(reservation, HarnessRoundReservation):
            raise HarnessRoundViolation(
                "INVALID_HARNESS_RESERVATION",
                "reservation has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        record = self._reservations.get(reservation.binding.request_id)
        if (
            record is None
            or record.reservation != reservation
            or reservation.owner_instance_id != self._instance_id
            or self._round_tokens.get(reservation.round_id)
            != reservation.reservation_token
        ):
            raise HarnessRoundViolation(
                "UNTRUSTED_HARNESS_RESERVATION",
                "reservation does not match the trusted Harness registry",
                ErrorCode.PERMISSION_DENIED,
            )
        return record

    def _require_handle_record(self, handle: HarnessRoundHandle) -> _RoundRecord:
        if not isinstance(handle, HarnessRoundHandle) or handle._harness is not self:
            raise HarnessRoundViolation(
                "UNTRUSTED_ROUND_HANDLE",
                "round handle does not belong to this Harness",
                ErrorCode.PERMISSION_DENIED,
            )
        record = self._rounds.get(handle.round_id)
        if record is None or record.handle is not handle:
            raise HarnessRoundViolation(
                "UNTRUSTED_ROUND_HANDLE",
                "round handle does not match the trusted active registry",
                ErrorCode.PERMISSION_DENIED,
            )
        return record

    def _expire(self, record: _ReservationRecord) -> None:
        if (
            record.state is HarnessReservationState.RESERVED
            and self._monotonic() >= record.reservation.expires_at_monotonic
        ):
            record.state = HarnessReservationState.EXPIRED

    @staticmethod
    def _timestamp() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
