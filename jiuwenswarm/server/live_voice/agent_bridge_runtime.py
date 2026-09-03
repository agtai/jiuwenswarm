# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded non-blocking Agent Bridge runtime for authoritative round progress."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    EventApplyStatus,
    EventEnvelope,
    EventSequenceTracker,
    IdentityKind,
    Knowledge,
    KnownFact,
    ResponseRef,
    ScopeRef,
    Speakability,
    TerminalOutcome,
    TurnCommit,
    WorkProgressEventV2,
    WorkProgressSource,
    WorkSourceAuthority,
    WorkState,
    WorkUrgency,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.agent_bridge import AgentEvent

from .latency_measurement import (
    L0Milestone,
    L0RoundClassification,
    emit_runtime_l0_milestone,
    resolve_runtime_l0_binding,
)


logger = logging.getLogger(__name__)


class AgentBridgeRuntimeViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


def _validate_runtime_text(value: object, field_name: str, *, reason: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AgentBridgeRuntimeViolation(
            reason,
            f"{field_name} must be a non-empty string",
            ErrorCode.INVALID_ARGUMENT,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise AgentBridgeRuntimeViolation(
            reason,
            f"{field_name} must contain only Unicode scalar values",
            ErrorCode.INVALID_ARGUMENT,
        ) from error


class AgentBridgeCompletionStatus(StrEnum):
    TERMINAL_OBSERVED = "terminal_observed"
    STREAM_ENDED_WITHOUT_TERMINAL = "stream_ended_without_terminal"


class AgentBridgeReservationState(StrEnum):
    RESERVED = "reserved"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class AgentBridgeDispatchReservation:
    request_id: str
    round_id: str
    response_id: str
    correlation_id: str
    commit: TurnCommit
    adapter_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.commit, TurnCommit):
            raise AgentBridgeRuntimeViolation(
                "INVALID_AGENT_DISPATCH_RESERVATION",
                "dispatch reservation requires a canonical TurnCommit",
                ErrorCode.INVALID_ARGUMENT,
            )
        for name, value in (
            ("request_id", self.request_id),
            ("round_id", self.round_id),
            ("response_id", self.response_id),
            ("correlation_id", self.correlation_id),
            ("adapter_id", self.adapter_id),
        ):
            _validate_runtime_text(
                value, name, reason="INVALID_AGENT_DISPATCH_RESERVATION"
            )

    def fingerprint(self) -> bytes:
        return canonical_json_bytes(
            {
                "round_id": self.round_id,
                "response_id": self.response_id,
                "correlation_id": self.correlation_id,
                "commit": self.commit.to_dict(),
                "adapter_id": self.adapter_id,
            }
        )


@dataclass(frozen=True, slots=True)
class AgentRoundRequest:
    request_id: str
    round_id: str
    response_ref: ResponseRef
    correlation_id: str
    commit: TurnCommit
    adapter_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.response_ref, ResponseRef) or not isinstance(
            self.commit, TurnCommit
        ):
            raise AgentBridgeRuntimeViolation(
                "INVALID_AGENT_ROUND_REQUEST",
                "response_ref and commit must use canonical v2 types",
                ErrorCode.INVALID_ARGUMENT,
            )
        for name, value in (
            ("request_id", self.request_id),
            ("round_id", self.round_id),
            ("correlation_id", self.correlation_id),
            ("adapter_id", self.adapter_id),
        ):
            _validate_runtime_text(value, name, reason="INVALID_AGENT_ROUND_REQUEST")
        if self.response_ref.interaction_id != self.commit.interaction_id:
            raise AgentBridgeRuntimeViolation(
                "AGENT_RESPONSE_INTERACTION_MISMATCH",
                "response_ref must belong to the committed interaction",
                ErrorCode.PERMISSION_DENIED,
            )

    @property
    def source_provenance(self) -> str:
        return canonical_json_bytes(self.commit.hypothesis_provenance).decode("utf-8")

    def fingerprint(self) -> bytes:
        return canonical_json_bytes(
            {
                "round_id": self.round_id,
                "response_ref": {
                    "interaction_id": self.response_ref.interaction_id,
                    "response_id": self.response_ref.response_id,
                    "response_generation": self.response_ref.response_generation,
                },
                "correlation_id": self.correlation_id,
                "commit": self.commit.to_dict(),
                "adapter_id": self.adapter_id,
            }
        )


class AgentRoundAdapter(Protocol):
    def stream(
        self, request: AgentRoundRequest
    ) -> AsyncIterator[AgentEvent | EventEnvelope]: ...


@dataclass(frozen=True, slots=True)
class AgentBridgeCompletion:
    request_id: str
    status: AgentBridgeCompletionStatus
    agent_event_count: int
    source_event_count: int
    progress_event_count: int
    terminal_outcome: TerminalOutcome | None


class AgentBridgeCompletionHandle:
    """Read-only completion wait that cannot cancel the shared request result."""

    __slots__ = ("_future",)

    def __init__(self, future: asyncio.Future[AgentBridgeCompletion]) -> None:
        self._future = future

    def __await__(self) -> Generator[object, None, AgentBridgeCompletion]:
        return asyncio.shield(self._future).__await__()

    def done(self) -> bool:
        return self._future.done()

    def result(self) -> AgentBridgeCompletion:
        return self._future.result()

    def exception(self) -> BaseException | None:
        return self._future.exception()

    def _set_result(self, result: AgentBridgeCompletion) -> None:
        self._future.set_result(result)

    def _set_exception(self, error: BaseException) -> None:
        self._future.set_exception(error)

    def _cancel(self) -> None:
        self._future.cancel()


@dataclass(frozen=True, slots=True)
class AgentBridgeSubmission:
    request: AgentRoundRequest
    completion: AgentBridgeCompletionHandle


@dataclass(frozen=True, slots=True)
class AgentEventDelivery:
    request: AgentRoundRequest
    event: AgentEvent


@dataclass(frozen=True, slots=True)
class WorkProgressDelivery:
    request: AgentRoundRequest
    source_event: EventEnvelope
    progress_event: EventEnvelope


AgentBridgeDelivery = AgentEventDelivery | WorkProgressDelivery


@dataclass(frozen=True, slots=True)
class AgentBridgeRuntimeSnapshot:
    enabled: bool
    started: bool
    accepting: bool
    closed: bool
    pending_dispatches: int
    active_requests: tuple[str, ...]
    queued_outputs: int
    retained_requests: int
    reserved_requests: int


@dataclass(slots=True)
class _PendingDispatch:
    submission: AgentBridgeSubmission
    adapter: AgentRoundAdapter


_SOURCE_ACCEPTED = frozenset(
    {
        EventApplyStatus.APPLIED,
        EventApplyStatus.DUPLICATE_APPLIED,
        EventApplyStatus.QUARANTINED_GAP,
        EventApplyStatus.QUARANTINED_CAUSATION,
        EventApplyStatus.DUPLICATE_QUARANTINED,
    }
)


def project_round_work_progress(
    source_event: EventEnvelope,
    request: AgentRoundRequest,
    *,
    bridge_instance_id: str,
    envelope_seq: int,
    projection_seq: int,
) -> EventEnvelope:
    """Project one already-authoritative Harness round event without guessing detail."""

    _validate_runtime_text(
        bridge_instance_id,
        "bridge_instance_id",
        reason="INVALID_BRIDGE_INSTANCE",
    )
    if (
        source_event.producer.authority != WorkSourceAuthority.HARNESS.value
        or source_event.stream_ref.kind is not IdentityKind.ROUND
        or source_event.stream_ref.id != request.round_id
        or not source_event.event_type.startswith("round.")
        or source_event.scope != request.commit.scope
        or source_event.correlation_id != request.correlation_id
    ):
        raise AgentBridgeRuntimeViolation(
            "INVALID_ROUND_SOURCE",
            "round progress requires an exact authoritative Harness source event",
            ErrorCode.PERMISSION_DENIED,
        )
    raw_state = source_event.payload["state"]
    raw_outcome = source_event.payload.get("outcome")
    if type(raw_state) is not str or (
        raw_outcome is not None and type(raw_outcome) is not str
    ):
        raise AgentBridgeRuntimeViolation(
            "INVALID_ROUND_SOURCE",
            "authoritative round state and outcome must be canonical strings",
            ErrorCode.PROTOCOL_VIOLATION,
        )
    state = WorkState(raw_state)
    outcome = None if raw_outcome is None else TerminalOutcome(raw_outcome)
    progress = WorkProgressEventV2(
        work_ref=source_event.stream_ref,
        source=WorkProgressSource(
            authority=WorkSourceAuthority.HARNESS,
            event_id=source_event.event_id,
            source_work_ref=source_event.stream_ref,
            adapter=request.adapter_id,
        ),
        seq=projection_seq,
        state=state,
        outcome=outcome,
        summary=KnownFact(Knowledge.UNKNOWN),
        blocking_question=KnownFact(Knowledge.UNKNOWN),
        artifact_refs=KnownFact(Knowledge.UNKNOWN),
        urgency=WorkUrgency.UNKNOWN,
        speakability=Speakability.NOT_SPEAKABLE,
    )
    instance_token = bridge_instance_id.encode("utf-8").hex()
    request_token = request.request_id.encode("utf-8").hex()
    return EventEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "event_id": (
                f"agent.bridge:{instance_token}:{request_token}:"
                f"work-progress:{projection_seq}"
            ),
            "event_type": "work.progress",
            "producer": {
                "component": "agent.bridge",
                "instance_id": bridge_instance_id,
                "authority": "adapter",
            },
            "stream_ref": source_event.stream_ref.to_dict(),
            "seq": envelope_seq,
            "occurred_at": source_event.occurred_at,
            "scope": source_event.scope.to_dict(),
            "correlation_id": source_event.correlation_id,
            "causation_id": source_event.event_id,
            "required_capabilities": [],
            "payload": progress.to_dict(),
            "extensions": {},
        }
    )


class AgentBridgeRuntime:
    """Dispatches committed Agent work without waiting on the caller's hot path."""

    def __init__(
        self,
        *,
        instance_id: str,
        enabled: bool = True,
        dispatch_capacity: int = 32,
        output_capacity: int = 64,
        max_concurrency: int = 4,
        max_requests: int = 256,
        max_source_events_per_request: int = 256,
        adapter_close_timeout_seconds: float = 1.0,
    ) -> None:
        _validate_runtime_text(
            instance_id, "instance_id", reason="INVALID_BRIDGE_INSTANCE"
        )
        if type(enabled) is not bool:
            raise AgentBridgeRuntimeViolation(
                "INVALID_FEATURE_FLAG",
                "enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        for name, value in (
            ("dispatch_capacity", dispatch_capacity),
            ("output_capacity", output_capacity),
            ("max_concurrency", max_concurrency),
            ("max_requests", max_requests),
            ("max_source_events_per_request", max_source_events_per_request),
        ):
            if type(value) is not int or value <= 0:
                raise AgentBridgeRuntimeViolation(
                    "INVALID_RUNTIME_CAPACITY",
                    f"{name} must be a positive integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if (
            isinstance(adapter_close_timeout_seconds, bool)
            or not isinstance(adapter_close_timeout_seconds, (int, float))
            or not math.isfinite(adapter_close_timeout_seconds)
            or adapter_close_timeout_seconds <= 0
        ):
            raise AgentBridgeRuntimeViolation(
                "INVALID_RUNTIME_CAPACITY",
                "adapter_close_timeout_seconds must be a positive finite number",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._instance_id = instance_id
        self._enabled = enabled
        self._dispatch_capacity = dispatch_capacity
        self._max_concurrency = max_concurrency
        self._max_requests = max_requests
        self._max_source_events_per_request = max_source_events_per_request
        self._adapter_close_timeout_seconds = float(adapter_close_timeout_seconds)
        self._pending: deque[_PendingDispatch] = deque()
        self._outputs: asyncio.Queue[AgentBridgeDelivery] = asyncio.Queue(
            maxsize=output_capacity
        )
        self._submissions: dict[str, AgentBridgeSubmission] = {}
        self._fingerprints: dict[str, bytes] = {}
        self._reservations: dict[str, AgentBridgeDispatchReservation] = {}
        self._reservation_fingerprints: dict[str, bytes] = {}
        self._reservation_states: dict[str, AgentBridgeReservationState] = {}
        self._round_bindings: dict[tuple[ScopeRef, str], str] = {}
        self._source_event_fingerprints: dict[str, bytes] = {}
        self._active: dict[str, asyncio.Task[None]] = {}
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._output_ready: asyncio.Event | None = None
        self._closed_event: asyncio.Event | None = None
        self._dispatcher: asyncio.Task[None] | None = None
        self._started = False
        self._accepting = False
        self._closing = False
        self._closed = False

    async def start(self) -> bool:
        if not self._enabled:
            return False
        if self._closed:
            raise AgentBridgeRuntimeViolation(
                "BRIDGE_RUNTIME_CLOSED",
                "a closed Agent Bridge runtime cannot restart",
                ErrorCode.CONFLICT,
            )
        running = asyncio.get_running_loop()
        if self._dispatcher is not None:
            self._require_owner_loop(running)
            return False
        self._owner_loop = running
        self._wake = asyncio.Event()
        self._output_ready = asyncio.Event()
        self._closed_event = asyncio.Event()
        self._started = True
        self._accepting = True
        self._dispatcher = running.create_task(
            self._dispatch_loop(), name="live-voice-agent-bridge"
        )
        return True

    def submit(
        self,
        *,
        request_id: str,
        round_id: str,
        response_ref: ResponseRef,
        correlation_id: str,
        commit: TurnCommit,
        adapter_id: str,
        adapter: AgentRoundAdapter,
    ) -> AgentBridgeSubmission:
        # Preserve the original one-phase API's validation contract while the
        # formal composition uses reserve/commit directly.
        AgentRoundRequest(
            request_id=request_id,
            round_id=round_id,
            response_ref=response_ref,
            correlation_id=correlation_id,
            commit=commit,
            adapter_id=adapter_id,
        )
        reservation = self.reserve_dispatch(
            request_id=request_id,
            round_id=round_id,
            response_id=response_ref.response_id,
            correlation_id=correlation_id,
            commit=commit,
            adapter_id=adapter_id,
        )
        return self.commit_dispatch(
            reservation,
            response_ref=response_ref,
            adapter=adapter,
        )

    def reserve_dispatch(
        self,
        *,
        request_id: str,
        round_id: str,
        response_id: str,
        correlation_id: str,
        commit: TurnCommit,
        adapter_id: str,
    ) -> AgentBridgeDispatchReservation:
        self._require_admission()
        reservation = AgentBridgeDispatchReservation(
            request_id=request_id,
            round_id=round_id,
            response_id=response_id,
            correlation_id=correlation_id,
            commit=commit,
            adapter_id=adapter_id,
        )
        fingerprint = reservation.fingerprint()
        prior = self._reservations.get(request_id)
        if prior is not None:
            if self._reservation_fingerprints[request_id] == fingerprint:
                return prior
            raise AgentBridgeRuntimeViolation(
                "REQUEST_ID_CONFLICT",
                "request_id cannot change its reserved dispatch binding",
                ErrorCode.CONFLICT,
            )
        if len(self._reservations) >= self._max_requests:
            raise AgentBridgeRuntimeViolation(
                "REQUEST_LEDGER_FULL",
                "bounded request ledger is full for this runtime session",
                ErrorCode.UNAVAILABLE,
            )
        uncommitted = sum(
            state
            in {
                AgentBridgeReservationState.RESERVED,
                AgentBridgeReservationState.COMMITTING,
            }
            for state in self._reservation_states.values()
        )
        if len(self._pending) + uncommitted >= self._dispatch_capacity:
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_QUEUE_FULL",
                "bounded Agent dispatch queue is full",
                ErrorCode.UNAVAILABLE,
            )
        round_key = (commit.scope, round_id)
        bound_request = self._round_bindings.get(round_key)
        if bound_request is not None:
            raise AgentBridgeRuntimeViolation(
                "ROUND_ID_CONFLICT",
                "a scoped round_id can belong to only one Agent dispatch",
                ErrorCode.CONFLICT,
            )
        self._reservations[request_id] = reservation
        self._reservation_fingerprints[request_id] = fingerprint
        self._reservation_states[request_id] = AgentBridgeReservationState.RESERVED
        self._round_bindings[round_key] = request_id
        return reservation

    def begin_dispatch_commit(
        self, reservation: AgentBridgeDispatchReservation
    ) -> bool:
        self._require_admission()
        retained = self._reservations.get(reservation.request_id)
        if retained != reservation:
            raise AgentBridgeRuntimeViolation(
                "UNTRUSTED_DISPATCH_RESERVATION",
                "dispatch reservation does not match the Bridge ledger",
                ErrorCode.PERMISSION_DENIED,
            )
        state = self._reservation_states[reservation.request_id]
        if state in {
            AgentBridgeReservationState.COMMITTING,
            AgentBridgeReservationState.COMMITTED,
        }:
            return False
        if state is not AgentBridgeReservationState.RESERVED:
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_RESERVATION_ABORTED",
                "an aborted reservation cannot enter commit",
                ErrorCode.STALE,
            )
        self._reservation_states[reservation.request_id] = (
            AgentBridgeReservationState.COMMITTING
        )
        return True

    def commit_dispatch(
        self,
        reservation: AgentBridgeDispatchReservation,
        *,
        response_ref: ResponseRef,
        adapter: AgentRoundAdapter,
    ) -> AgentBridgeSubmission:
        running = self._require_admission()
        retained = self._reservations.get(reservation.request_id)
        if retained != reservation:
            raise AgentBridgeRuntimeViolation(
                "UNTRUSTED_DISPATCH_RESERVATION",
                "dispatch reservation does not match the Bridge ledger",
                ErrorCode.PERMISSION_DENIED,
            )
        state = self._reservation_states[reservation.request_id]
        if state is AgentBridgeReservationState.ABORTED:
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_RESERVATION_ABORTED",
                "an aborted reservation cannot dispatch",
                ErrorCode.STALE,
            )
        if state is AgentBridgeReservationState.RESERVED:
            self._reservation_states[reservation.request_id] = (
                AgentBridgeReservationState.COMMITTING
            )
        if (
            not isinstance(response_ref, ResponseRef)
            or response_ref.interaction_id != reservation.commit.interaction_id
            or response_ref.response_id != reservation.response_id
        ):
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_RESPONSE_BINDING_MISMATCH",
                "ResponseRef does not match the reserved dispatch",
                ErrorCode.PERMISSION_DENIED,
            )
        request = AgentRoundRequest(
            request_id=reservation.request_id,
            round_id=reservation.round_id,
            response_ref=response_ref,
            correlation_id=reservation.correlation_id,
            commit=reservation.commit,
            adapter_id=reservation.adapter_id,
        )
        fingerprint = request.fingerprint()
        request_id = reservation.request_id
        existing = self._submissions.get(request_id)
        if existing is not None:
            if self._fingerprints[request_id] == fingerprint:
                return existing
            raise AgentBridgeRuntimeViolation(
                "REQUEST_ID_CONFLICT",
                "request_id cannot change its committed dispatch binding",
                ErrorCode.CONFLICT,
            )
        completion: asyncio.Future[AgentBridgeCompletion] = running.create_future()
        submission = AgentBridgeSubmission(
            request, AgentBridgeCompletionHandle(completion)
        )
        self._submissions[reservation.request_id] = submission
        self._fingerprints[reservation.request_id] = fingerprint
        self._reservation_states[reservation.request_id] = (
            AgentBridgeReservationState.COMMITTED
        )
        self._pending.append(_PendingDispatch(submission, adapter))
        assert self._wake is not None
        self._wake.set()
        return submission

    def abort_dispatch(
        self, reservation: AgentBridgeDispatchReservation, *, reason: str
    ) -> bool:
        running = asyncio.get_running_loop()
        self._require_owner_loop(running)
        _validate_runtime_text(
            reason, "reason", reason="INVALID_DISPATCH_ABORT_REASON"
        )
        retained = self._reservations.get(reservation.request_id)
        if retained != reservation:
            raise AgentBridgeRuntimeViolation(
                "UNTRUSTED_DISPATCH_RESERVATION",
                "dispatch reservation does not match the Bridge ledger",
                ErrorCode.PERMISSION_DENIED,
            )
        state = self._reservation_states[reservation.request_id]
        if state is AgentBridgeReservationState.ABORTED:
            return False
        if state is AgentBridgeReservationState.COMMITTED:
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_ALREADY_COMMITTED",
                "a committed dispatch cannot be converted into an abort",
                ErrorCode.CONFLICT,
            )
        self._reservation_states[reservation.request_id] = (
            AgentBridgeReservationState.ABORTED
        )
        return True

    def rollback_undelivered_dispatch(
        self, reservation: AgentBridgeDispatchReservation, *, reason: str
    ) -> bool:
        """Revoke a committed dispatch while it is still in the local queue.

        This narrow rollback is used when the synchronous durable checkpoint
        immediately following ``commit_dispatch`` fails.  Because no await is
        permitted between commit and rollback, finding the exact request in
        ``_pending`` proves that no adapter/Agent work has started.
        """

        self._require_admission()
        _validate_runtime_text(
            reason, "reason", reason="INVALID_DISPATCH_ABORT_REASON"
        )
        retained = self._reservations.get(reservation.request_id)
        if retained != reservation:
            raise AgentBridgeRuntimeViolation(
                "UNTRUSTED_DISPATCH_RESERVATION",
                "dispatch reservation does not match the Bridge ledger",
                ErrorCode.PERMISSION_DENIED,
            )
        state = self._reservation_states[reservation.request_id]
        if state is AgentBridgeReservationState.ABORTED:
            return False
        if state is not AgentBridgeReservationState.COMMITTED:
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_NOT_ROLLBACKABLE",
                "only a committed, undelivered dispatch can be rolled back",
                ErrorCode.CONFLICT,
            )
        request_id = reservation.request_id
        retained_pending = next(
            (
                pending
                for pending in self._pending
                if pending.submission.request.request_id == request_id
            ),
            None,
        )
        if retained_pending is None or request_id in self._active:
            raise AgentBridgeRuntimeViolation(
                "DISPATCH_ALREADY_DELIVERED",
                "a delivered dispatch cannot be rolled back",
                ErrorCode.CONFLICT,
            )
        self._pending.remove(retained_pending)
        submission = self._submissions.pop(request_id, None)
        self._fingerprints.pop(request_id, None)
        self._reservation_states[request_id] = AgentBridgeReservationState.ABORTED
        if submission is not None and not submission.completion.done():
            submission.completion._cancel()
        return True

    async def next_delivery(self) -> AgentBridgeDelivery:
        if not self._enabled:
            raise AgentBridgeRuntimeViolation(
                "FEATURE_DISABLED",
                "Agent Bridge runtime is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        running = asyncio.get_running_loop()
        if self._owner_loop is None:
            reason = (
                "BRIDGE_RUNTIME_CLOSED"
                if self._closed
                else "BRIDGE_RUNTIME_NOT_STARTED"
            )
            raise AgentBridgeRuntimeViolation(
                reason,
                "Agent Bridge runtime has no delivery owner",
                ErrorCode.CONFLICT,
            )
        self._require_owner_loop(running)
        assert self._output_ready is not None
        assert self._closed_event is not None
        while True:
            if not self._outputs.empty():
                result = self._outputs.get_nowait()
                if self._outputs.empty():
                    self._output_ready.clear()
                return result
            if self._closed:
                raise AgentBridgeRuntimeViolation(
                    "BRIDGE_RUNTIME_CLOSED",
                    "closed Agent Bridge runtime has no queued delivery",
                    ErrorCode.CONFLICT,
                )
            ready = asyncio.create_task(self._output_ready.wait())
            closed = asyncio.create_task(self._closed_event.wait())
            try:
                await asyncio.wait({ready, closed}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for waiter in (ready, closed):
                    if not waiter.done():
                        waiter.cancel()
                await asyncio.gather(ready, closed, return_exceptions=True)

    async def close(self) -> None:
        if not self._enabled:
            self._closed = True
            return
        if self._closed:
            return
        running = asyncio.get_running_loop()
        if self._dispatcher is None or self._wake is None:
            self._closed = True
            self._accepting = False
            return
        self._require_owner_loop(running)
        self._accepting = False
        self._closing = True
        self._wake.set()
        await asyncio.shield(self._dispatcher)

    def snapshot(self) -> AgentBridgeRuntimeSnapshot:
        return AgentBridgeRuntimeSnapshot(
            enabled=self._enabled,
            started=self._started,
            accepting=self._accepting,
            closed=self._closed,
            pending_dispatches=len(self._pending),
            active_requests=tuple(self._active),
            queued_outputs=self._outputs.qsize(),
            retained_requests=len(self._submissions),
            reserved_requests=sum(
                state
                in {
                    AgentBridgeReservationState.RESERVED,
                    AgentBridgeReservationState.COMMITTING,
                }
                for state in self._reservation_states.values()
            ),
        )

    async def _dispatch_loop(self) -> None:
        assert self._wake is not None
        try:
            while True:
                await self._wake.wait()
                self._wake.clear()
                while self._pending and len(self._active) < self._max_concurrency:
                    pending = self._pending.popleft()
                    request_id = pending.submission.request.request_id
                    task = asyncio.create_task(
                        self._run_request(pending),
                        name=f"live-voice-agent-round:{request_id}",
                    )
                    self._active[request_id] = task

                    def on_done(
                        _task: asyncio.Task[None], rid: str = request_id
                    ) -> None:
                        self._request_finished(rid)

                    task.add_done_callback(on_done)
                if self._closing and not self._pending and not self._active:
                    return
        finally:
            self._accepting = False
            self._closed = True
            if self._closed_event is not None:
                self._closed_event.set()

    def _request_finished(self, request_id: str) -> None:
        self._active.pop(request_id, None)
        if self._wake is not None:
            self._wake.set()

    async def _run_request(self, pending: _PendingDispatch) -> None:
        submission = pending.submission
        request = submission.request
        tracker = EventSequenceTracker()
        retained_sources: dict[str, EventEnvelope] = {}
        projected_sources: set[str] = set()
        agent_event_count = 0
        source_event_count = 0
        progress_event_count = 0
        expected_agent_seq = 0
        envelope_seq = 0
        projection_seq = 0
        terminal_outcome: TerminalOutcome | None = None
        stream: AsyncIterator[AgentEvent | EventEnvelope] | None = None
        measurement_binding = resolve_runtime_l0_binding(
            correlation_id=request.correlation_id,
            interaction_id=request.response_ref.interaction_id,
            response_id=request.response_ref.response_id,
            response_generation=request.response_ref.response_generation,
        )
        request_started = time.monotonic()
        measurement_failure_emitted = False

        def emit_measurement_failure() -> None:
            nonlocal measurement_failure_emitted
            if measurement_binding is None or measurement_failure_emitted:
                return
            measurement_failure_emitted = True
            emit_runtime_l0_milestone(
                component="agent",
                milestone=L0Milestone.FAILURE,
                binding=measurement_binding,
                classification=L0RoundClassification.FAILURE,
                duration_ms=(time.monotonic() - request_started) * 1_000.0,
                event_nonce=request.request_id,
            )

        first_delta_observed = False
        tool_call_observed = False
        tool_result_succeeded = False
        stable_sentence_observed = False
        if measurement_binding is not None:
            emit_runtime_l0_milestone(
                component="agent",
                milestone=L0Milestone.AGENT_REQUEST_START,
                binding=measurement_binding,
                event_nonce=request.request_id,
            )
        try:
            stream = pending.adapter.stream(request)
            async for item in stream:
                if isinstance(item, AgentEvent):
                    self._validate_agent_event(
                        request, item, expected_seq=expected_agent_seq
                    )
                    expected_agent_seq += 1
                    agent_event_count += 1
                    if agent_event_count == 1 or item.event_type in {
                        "chat.final",
                        "chat.error",
                    }:
                        logger.info(
                            "live_voice_agent_output_trace %s",
                            {
                                "stage": "bridge_agent_event_received",
                                "request_id": request.request_id,
                                "response_id": request.response_ref.response_id,
                                "response_generation": (
                                    request.response_ref.response_generation
                                ),
                                "event_seq": item.seq,
                                "event_type": item.event_type,
                            },
                        )
                    if (
                        measurement_binding is not None
                        and not first_delta_observed
                        and item.event_type == "chat.delta"
                    ):
                        first_delta_observed = True
                        emit_runtime_l0_milestone(
                            component="agent",
                            milestone=L0Milestone.FIRST_DELTA,
                            binding=measurement_binding,
                            event_nonce=f"{request.request_id}:{item.seq}",
                        )
                    if (
                        measurement_binding is not None
                        and not tool_call_observed
                        and item.event_type == "chat.tool_call"
                    ):
                        tool_call_observed = True
                        emit_runtime_l0_milestone(
                            component="agent",
                            milestone=L0Milestone.TOOL_CALL_OBSERVED,
                            binding=measurement_binding,
                            event_nonce=f"{request.request_id}:{item.seq}:tool-call",
                        )
                    if (
                        measurement_binding is not None
                        and tool_call_observed
                        and not tool_result_succeeded
                        and item.event_type == "chat.tool_result"
                        and item.tool_result_succeeded is True
                    ):
                        tool_result_succeeded = True
                        emit_runtime_l0_milestone(
                            component="agent",
                            milestone=L0Milestone.TOOL_RESULT_SUCCEEDED,
                            binding=measurement_binding,
                            duration_ms=(time.monotonic() - request_started) * 1_000.0,
                            event_nonce=f"{request.request_id}:{item.seq}:tool-result",
                        )
                    if (
                        measurement_binding is not None
                        and not stable_sentence_observed
                        and item.event_type == "chat.final"
                        and isinstance(item.text, str)
                        and bool(item.text.strip())
                    ):
                        stable_sentence_observed = True
                        elapsed_ms = (time.monotonic() - request_started) * 1_000.0
                        emit_runtime_l0_milestone(
                            component="agent",
                            milestone=(
                                L0Milestone.FIRST_STABLE_SPEAKABLE_SENTENCE
                            ),
                            binding=measurement_binding,
                            duration_ms=elapsed_ms,
                            event_nonce=f"{request.request_id}:{item.seq}:stable",
                        )
                        emit_runtime_l0_milestone(
                            component="agent",
                            milestone=L0Milestone.CHAT_FINAL,
                            binding=measurement_binding,
                            duration_ms=elapsed_ms,
                            event_nonce=f"{request.request_id}:{item.seq}:final",
                        )
                    await self._put_output(AgentEventDelivery(request, item))
                    continue
                if not isinstance(item, EventEnvelope):
                    raise AgentBridgeRuntimeViolation(
                        "INVALID_ADAPTER_ITEM",
                        "Agent Adapter must emit AgentEvent or EventEnvelope",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                source_event_count += 1
                if source_event_count > self._max_source_events_per_request:
                    raise AgentBridgeRuntimeViolation(
                        "SOURCE_EVENT_LIMIT_EXCEEDED",
                        "authoritative source event limit exceeded",
                        ErrorCode.UNAVAILABLE,
                    )
                self._validate_round_source(request, item)
                source_fingerprint = item.canonical_bytes()
                prior_source = self._source_event_fingerprints.get(item.event_id)
                if prior_source is not None and prior_source != source_fingerprint:
                    raise AgentBridgeRuntimeViolation(
                        "EVENT_ID_CONFLICT",
                        "source event_id was reused with different content",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                self._source_event_fingerprints.setdefault(
                    item.event_id, source_fingerprint
                )
                retained_sources.setdefault(item.event_id, item)
                applied = tracker.accept(item)
                if applied.status not in _SOURCE_ACCEPTED:
                    reason = (
                        "INVALID_ROUND_SOURCE"
                        if applied.error is None or applied.error.reason is None
                        else applied.error.reason
                    )
                    raise AgentBridgeRuntimeViolation(
                        reason,
                        "authoritative round event failed closed",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                for event_id in applied.applied_event_ids:
                    source = retained_sources.get(event_id)
                    if source is None or event_id in projected_sources:
                        continue
                    progress = project_round_work_progress(
                        source,
                        request,
                        bridge_instance_id=self._instance_id,
                        envelope_seq=envelope_seq,
                        projection_seq=projection_seq,
                    )
                    projection_result = tracker.accept(progress)
                    if projection_result.status is not EventApplyStatus.APPLIED:
                        reason = (
                            "INVALID_WORK_PROGRESS_PROJECTION"
                            if projection_result.error is None
                            or projection_result.error.reason is None
                            else projection_result.error.reason
                        )
                        raise AgentBridgeRuntimeViolation(
                            reason,
                            "source-backed WorkProgress failed closed",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    projected_sources.add(event_id)
                    envelope_seq += 1
                    projection_seq += 1
                    progress_event_count += 1
                    parsed = WorkProgressEventV2.from_dict(
                        progress.payload, scope=progress.scope
                    )
                    if parsed.state is WorkState.TERMINAL:
                        terminal_outcome = parsed.outcome
                        unresolved = set(retained_sources) - projected_sources
                        if unresolved:
                            raise AgentBridgeRuntimeViolation(
                                "SOURCE_STREAM_AFTER_TERMINAL",
                                "authoritative terminal cannot bypass buffered source events",
                                ErrorCode.PROTOCOL_VIOLATION,
                            )
                    await self._put_output(
                        WorkProgressDelivery(request, source, progress)
                    )
                    if terminal_outcome is not None:
                        if terminal_outcome is TerminalOutcome.FAILED:
                            emit_measurement_failure()
                        if not submission.completion.done():
                            submission.completion._set_result(
                                AgentBridgeCompletion(
                                    request_id=request.request_id,
                                    status=AgentBridgeCompletionStatus.TERMINAL_OBSERVED,
                                    agent_event_count=agent_event_count,
                                    source_event_count=source_event_count,
                                    progress_event_count=progress_event_count,
                                    terminal_outcome=terminal_outcome,
                                )
                            )
                        closing_stream = stream
                        stream = None
                        await self._best_effort_close_adapter_stream(closing_stream)
                        return
            unresolved = set(retained_sources) - projected_sources
            if unresolved:
                raise AgentBridgeRuntimeViolation(
                    "SOURCE_STREAM_INCOMPLETE",
                    "round source stream ended with unresolved gap or causation",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if not submission.completion.done():
                submission.completion._set_result(
                    AgentBridgeCompletion(
                        request_id=request.request_id,
                        status=AgentBridgeCompletionStatus.STREAM_ENDED_WITHOUT_TERMINAL,
                        agent_event_count=agent_event_count,
                        source_event_count=source_event_count,
                        progress_event_count=progress_event_count,
                        terminal_outcome=terminal_outcome,
                    )
                )
            logger.info(
                "live_voice_agent_output_trace %s",
                {
                    "stage": "bridge_stream_exhausted",
                    "request_id": request.request_id,
                    "response_id": request.response_ref.response_id,
                    "response_generation": request.response_ref.response_generation,
                    "agent_event_count": agent_event_count,
                    "source_event_count": source_event_count,
                    "progress_event_count": progress_event_count,
                },
            )
            closing_stream = stream
            stream = None
            await self._best_effort_close_adapter_stream(closing_stream)
        except Exception as error:
            logger.error(
                "live_voice_agent_output_trace %s",
                {
                    "stage": "bridge_stream_failed",
                    "request_id": request.request_id,
                    "response_id": request.response_ref.response_id,
                    "response_generation": request.response_ref.response_generation,
                    "agent_event_count": agent_event_count,
                    "error_type": type(error).__name__,
                    "error_reason": getattr(error, "reason", None),
                },
            )
            emit_measurement_failure()
            if not submission.completion.done():
                submission.completion._set_exception(error)
            if stream is not None:
                await self._best_effort_close_adapter_stream(stream)

    async def _put_output(self, delivery: AgentBridgeDelivery) -> None:
        await self._outputs.put(delivery)
        assert self._output_ready is not None
        self._output_ready.set()

    async def _best_effort_close_adapter_stream(
        self,
        stream: AsyncIterator[AgentEvent | EventEnvelope],
    ) -> None:
        closer = getattr(stream, "aclose", None)
        if closer is None:
            return
        try:
            cleanup = asyncio.ensure_future(closer())
        except Exception:
            return
        done, _pending = await asyncio.wait(
            {cleanup}, timeout=self._adapter_close_timeout_seconds
        )
        if cleanup in done:
            try:
                cleanup.result()
            except (asyncio.CancelledError, Exception):
                pass
            return
        cleanup.cancel()
        cleanup.add_done_callback(self._consume_cleanup_result)

    @staticmethod
    def _consume_cleanup_result(cleanup: asyncio.Future[object]) -> None:
        try:
            cleanup.result()
        except (asyncio.CancelledError, Exception):
            pass

    @staticmethod
    def _validate_agent_event(
        request: AgentRoundRequest, event: AgentEvent, *, expected_seq: int
    ) -> None:
        if (
            event.request_id != request.request_id
            or event.interaction_id != request.commit.interaction_id
            or event.turn_id != request.commit.turn_id
            or event.commit_id != request.commit.commit_id
            or type(event.seq) is not int
            or event.seq != expected_seq
            or event.source_provenance != request.source_provenance
        ):
            raise AgentBridgeRuntimeViolation(
                "INVALID_AGENT_EVENT_PROVENANCE",
                "Agent events must preserve request, commit, provenance, and sequence",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    @staticmethod
    def _validate_round_source(
        request: AgentRoundRequest, event: EventEnvelope
    ) -> None:
        if (
            event.producer.authority != WorkSourceAuthority.HARNESS.value
            or event.stream_ref.kind is not IdentityKind.ROUND
            or event.stream_ref.id != request.round_id
            or not event.event_type.startswith("round.")
            or event.scope != request.commit.scope
            or event.correlation_id != request.correlation_id
        ):
            raise AgentBridgeRuntimeViolation(
                "INVALID_ROUND_SOURCE",
                "Adapter cannot fabricate or widen authoritative round facts",
                ErrorCode.PERMISSION_DENIED,
            )

    def _require_admission(self) -> asyncio.AbstractEventLoop:
        if not self._enabled:
            raise AgentBridgeRuntimeViolation(
                "FEATURE_DISABLED",
                "Agent Bridge runtime is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        running = asyncio.get_running_loop()
        if self._dispatcher is None or self._wake is None or not self._accepting:
            reason = (
                "BRIDGE_RUNTIME_CLOSED"
                if self._closed
                else "BRIDGE_RUNTIME_NOT_STARTED"
            )
            raise AgentBridgeRuntimeViolation(
                reason,
                "Agent Bridge runtime is not accepting dispatches",
                ErrorCode.CONFLICT,
            )
        self._require_owner_loop(running)
        return running

    def _require_owner_loop(self, running: asyncio.AbstractEventLoop) -> None:
        if self._owner_loop is not running:
            raise AgentBridgeRuntimeViolation(
                "BRIDGE_EVENT_LOOP_MISMATCH",
                "Agent Bridge operations must use the owning event loop",
                ErrorCode.CONFLICT,
            )


__all__ = [
    "AgentBridgeCompletion",
    "AgentBridgeCompletionHandle",
    "AgentBridgeCompletionStatus",
    "AgentBridgeDispatchReservation",
    "AgentBridgeDelivery",
    "AgentBridgeReservationState",
    "AgentBridgeRuntime",
    "AgentBridgeRuntimeSnapshot",
    "AgentBridgeRuntimeViolation",
    "AgentBridgeSubmission",
    "AgentEventDelivery",
    "AgentRoundAdapter",
    "AgentRoundRequest",
    "WorkProgressDelivery",
    "project_round_work_progress",
]
