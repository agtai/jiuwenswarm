# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Priority event loop and declarative effect outbox for Live Voice CR-B."""

from __future__ import annotations

import asyncio
import hashlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeVar, cast

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    CancelState,
    ConversationRuntime,
    ConversationSnapshot,
    InteractionState,
    ResponseRecord,
    ResponseState,
    RuntimeEvent,
    TurnState,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationLedger,
    PresentationLedgerSnapshot,
    PresentationSurface,
    PresentationUnit,
    PresentedHistorySpan,
)


# One hands-free turn can carry one generation interruption, so its replay
# ledger is bounded by conversation length rather than by user control actions.
_MAX_RETAINED_GENERATION_INTERRUPTS = 256


@dataclass
class _RetainedGenerationInterrupt:
    """One interruption action from admission through retained replay."""

    ref: ResponseRef
    future: asyncio.Future[GenerationInterruptionResult] | None = None
    result: GenerationInterruptionResult | None = None
    error: Exception | None = None


class ConversationRuntimeLoopViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class EffectState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    INVALIDATED = "invalidated"


@dataclass(frozen=True, slots=True)
class ConversationEffect:
    effect_id: str
    seq: int
    effect_type: str
    scope: ScopeRef
    ref: ResponseRef
    surface: PresentationSurface | None = None
    unit_id: str | None = None
    unit_seq: int | None = None
    content_ref: str | None = None
    action_id: str | None = None


@dataclass(frozen=True, slots=True)
class EffectRecord:
    effect: ConversationEffect
    state: EffectState
    invalidated_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BargeInResult:
    action_id: str
    applied: bool
    replayed: bool
    effect_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerationInterruptionResult:
    """One exact generation-time fence over an unfinished response.

    Unlike barge-in, which closes only AUDIO so a still-useful answer can keep
    rendering, this fence closes every presentation surface of the exact target
    and cancels it once.  It therefore owns the complete token/final/TTS/ACK/
    history boundary a replacement turn needs, and it never names a Task.
    """

    action_id: str
    ref: ResponseRef
    applied: bool
    replayed: bool
    interrupted_state: ResponseState
    cancel_requested: bool
    effect_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResponseCancelResult:
    command_id: str
    applied: bool
    replayed: bool
    event: RuntimeEvent
    effect_id: str


@dataclass(frozen=True, slots=True)
class PresentedHistoryContent:
    unit: PresentationUnit
    content_utf8: bytes


@dataclass(frozen=True, slots=True)
class PresentationHistoryIntent:
    ref: ResponseRef
    surface: PresentationSurface
    contiguous_cursor: int
    presented_at: str
    contents: tuple[PresentedHistoryContent, ...]


@dataclass(frozen=True, slots=True)
class ConversationRuntimeLoopSnapshot:
    started: bool
    accepting: bool
    closed: bool
    worker_running: bool
    pending_normal: int
    pending_observation: int
    pending_control: int
    conversation: ConversationSnapshot
    presentation: PresentationLedgerSnapshot
    effects: tuple[EffectRecord, ...]


@dataclass(slots=True)
class _QueuedOperation:
    ingress_seq: int
    callback: Callable[[], object]
    future: asyncio.Future[object]


_ValueT = TypeVar("_ValueT")


class ConversationRuntimeLoop:
    """Serializes CR-A writes without waiting for external owners or upstreams."""

    _OUTPUT_EFFECTS = frozenset({"ui.render", "audio.enqueue"})

    def __init__(
        self,
        scope: ScopeRef,
        *,
        enabled: bool = True,
        normal_capacity: int = 64,
        control_capacity: int = 16,
        response_generation_owner: Callable[[str, int], int] | None = None,
    ) -> None:
        if type(enabled) is not bool:
            raise ConversationRuntimeLoopViolation(
                "INVALID_FEATURE_FLAG",
                "enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._validate_capacity(normal_capacity, "normal_capacity")
        self._validate_capacity(control_capacity, "control_capacity")
        self._scope = scope
        self._enabled = enabled
        self._normal_capacity = normal_capacity
        self._control_capacity = control_capacity
        self._runtime = ConversationRuntime(
            scope,
            enabled=enabled,
            response_generation_owner=response_generation_owner,
        )
        self._presentation = PresentationLedger()
        self._normal: deque[_QueuedOperation] = deque()
        self._observation: deque[_QueuedOperation] = deque()
        self._control: deque[_QueuedOperation] = deque()
        self._next_ingress_seq = 1
        self._wake: asyncio.Event | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._worker: asyncio.Task[None] | None = None
        self._shutdown_future: asyncio.Future[tuple[ConversationEffect, ...]] | None = (
            None
        )
        self._shutdown_result_delivered = False
        self._started = False
        self._accepting = False
        self._closed = False
        self._effects: list[EffectRecord] = []
        self._barge_fingerprints: dict[str, tuple[ResponseRef, bool]] = {}
        self._barge_results: dict[str, BargeInResult] = {}
        self._barge_errors: dict[str, Exception] = {}
        self._pending_barge: dict[
            str, tuple[tuple[ResponseRef, bool], asyncio.Future[BargeInResult]]
        ] = {}
        self._cancel_fingerprints: dict[str, ResponseRef] = {}
        self._cancel_results: dict[str, ResponseCancelResult] = {}
        self._cancel_errors: dict[str, Exception] = {}
        self._pending_cancel: dict[
            str, tuple[ResponseRef, asyncio.Future[ResponseCancelResult]]
        ] = {}
        self._playback_stopped: set[ResponseRef] = set()
        # One entry per action, in insertion order, owns the exact target,
        # pending future and settled result/error.  Admission and replay share
        # the same bound, so an event-loop scheduling burst cannot grow a
        # second pending identity table outside the retained ledger.
        self._retained_generation_interrupts: dict[str, _RetainedGenerationInterrupt] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self) -> bool:
        if not self._enabled:
            return False
        if self._closed:
            raise ConversationRuntimeLoopViolation(
                "RUNTIME_LOOP_CLOSED",
                "a closed conversation runtime loop cannot restart",
                ErrorCode.CONFLICT,
            )
        running = asyncio.get_running_loop()
        if self._worker is not None:
            self._require_owner_loop(running)
            return False
        self._owner_loop = running
        self._wake = asyncio.Event()
        self._accepting = True
        self._started = True
        self._worker = running.create_task(
            self._run(), name="live-voice-conversation-runtime"
        )
        return True

    async def close(self) -> tuple[ConversationEffect, ...]:
        if not self._enabled:
            self._closed = True
            return ()
        if self._closed and self._shutdown_future is None:
            return ()
        running = asyncio.get_running_loop()
        if self._worker is None or self._wake is None:
            self._closed = True
            self._accepting = False
            return ()
        self._require_owner_loop(running)
        if self._shutdown_future is None:
            self._accepting = False
            self._shutdown_future = running.create_future()
            self._wake.set()
        assert self._shutdown_future is not None
        effects = await asyncio.shield(self._shutdown_future)
        assert self._worker is not None
        await asyncio.shield(self._worker)
        if self._shutdown_result_delivered:
            return ()
        self._shutdown_result_delivered = True
        return effects

    async def open_interaction(self, interaction_id: str) -> RuntimeEvent:
        return await self._submit(
            lambda: self._runtime.open_interaction(interaction_id)
        )

    async def transition_interaction(
        self, interaction_id: str, target: InteractionState
    ) -> RuntimeEvent:
        if not isinstance(target, InteractionState):
            raise ConversationRuntimeLoopViolation(
                "INVALID_INTERACTION_STATE",
                "interaction target must be a canonical interaction state",
                ErrorCode.INVALID_ARGUMENT,
            )
        control = target in {InteractionState.CLOSING, InteractionState.CLOSED}

        def apply() -> RuntimeEvent:
            records = self._response_records(interaction_id)
            event = self._runtime.transition_interaction(interaction_id, target)
            if control:
                for record in records:
                    self._fence_presentation(
                        record.ref, reason=f"interaction_{target.value}"
                    )
                    if record.state is not ResponseState.TERMINAL:
                        self._emit_playback_stop_once(record.ref)
            return event

        return await self._submit(apply, control=control)

    async def start_turn(self, interaction_id: str, turn_id: str) -> RuntimeEvent:
        return await self._submit(
            lambda: self._runtime.start_turn(interaction_id, turn_id)
        )

    async def commit_turn(self, commit: TurnCommit) -> tuple[bool, RuntimeEvent | None]:
        def apply() -> tuple[bool, RuntimeEvent | None]:
            if not isinstance(commit, TurnCommit):
                raise ConversationRuntimeLoopViolation(
                    "INVALID_TURN_COMMIT",
                    "turn commit has an unsupported type",
                    ErrorCode.INVALID_ARGUMENT,
                )
            snapshot = self._runtime.snapshot()
            turn = next(
                (item for item in snapshot.turns if item.turn_id == commit.turn_id),
                None,
            )
            if turn is not None and turn.state is TurnState.CAPTURING:
                interaction = next(
                    (
                        item
                        for item in snapshot.interactions
                        if item.interaction_id == turn.interaction_id
                    ),
                    None,
                )
                if (
                    interaction is not None
                    and interaction.state is not InteractionState.OPEN
                ):
                    raise ConversationRuntimeLoopViolation(
                        "INTERACTION_NOT_OPEN",
                        "a new turn commit requires an open interaction",
                        ErrorCode.CONFLICT,
                    )
            return self._runtime.commit_turn(commit)

        return await self._submit(apply)

    async def cancel_turn(self, turn_id: str) -> RuntimeEvent:
        return await self._submit(lambda: self._runtime.cancel_turn(turn_id))

    async def accept_response(
        self,
        turn_id: str,
        response_id: str,
        *,
        history_policy: HistorySurfacePolicy = HistorySurfacePolicy.TEXT,
        response_generation: int | None = None,
    ) -> tuple[ResponseRef, RuntimeEvent]:
        def apply() -> tuple[ResponseRef, RuntimeEvent]:
            policy = self._history_policy(history_policy)
            turn = next(
                (
                    item
                    for item in self._runtime.snapshot().turns
                    if item.turn_id == turn_id
                ),
                None,
            )
            prior = (
                None
                if turn is None
                else self._latest_response_record(turn.interaction_id)
            )
            ref, event = self._runtime.accept_response(
                turn_id,
                response_id,
                response_generation=response_generation,
            )
            self._presentation.begin_response(ref, policy)
            if prior is not None:
                self._fence_presentation(prior.ref, reason="response_replaced")
                if prior.state is not ResponseState.TERMINAL:
                    self._emit_playback_stop_once(prior.ref)
            return ref, event

        return await self._submit(apply, control=True)

    async def transition_response(
        self,
        ref: ResponseRef,
        target: ResponseState,
        *,
        outcome: TerminalOutcome | None = None,
    ) -> RuntimeEvent:
        if not isinstance(target, ResponseState):
            raise ConversationRuntimeLoopViolation(
                "INVALID_RESPONSE_STATE",
                "response target must be a canonical response state",
                ErrorCode.INVALID_ARGUMENT,
            )
        if outcome is not None and not isinstance(outcome, TerminalOutcome):
            raise ConversationRuntimeLoopViolation(
                "INVALID_TERMINAL_OUTCOME",
                "response outcome must be a canonical terminal outcome",
                ErrorCode.INVALID_ARGUMENT,
            )

        def apply() -> RuntimeEvent:
            record = self._response_record(ref)
            if target is not ResponseState.TERMINAL and record.fenced:
                raise ConversationRuntimeLoopViolation(
                    "FENCED_RESPONSE_NONTERMINAL_TRANSITION",
                    "a fenced response may receive only an authoritative terminal transition",
                    ErrorCode.STALE,
                )
            event = self._runtime.transition_response(ref, target, outcome=outcome)
            if (
                target is ResponseState.TERMINAL
                and outcome is not TerminalOutcome.COMPLETED
            ):
                self._fence_presentation(ref, reason="response_terminal")
            return event

        return await self._submit(apply, control=target is ResponseState.TERMINAL)

    async def request_response_cancel(
        self, command_id: str, ref: ResponseRef
    ) -> ResponseCancelResult:
        return await self._await_future(self.post_response_cancel(command_id, ref))

    def post_response_cancel(
        self, command_id: str, ref: ResponseRef
    ) -> asyncio.Future[ResponseCancelResult]:
        command_id = self._require_id(command_id, "command_id")
        running = self._require_admission()
        pending = self._pending_cancel.get(command_id)
        if pending is not None:
            prior_ref, future = pending
            if prior_ref != ref:
                raise ConversationRuntimeLoopViolation(
                    "RESPONSE_CANCEL_COMMAND_CONFLICT",
                    "a response cancel command identifier cannot change target",
                    ErrorCode.CONFLICT,
                )
            return future
        prior_ref = self._cancel_fingerprints.get(command_id)
        if prior_ref is not None:
            if prior_ref != ref:
                raise ConversationRuntimeLoopViolation(
                    "RESPONSE_CANCEL_COMMAND_CONFLICT",
                    "a response cancel command identifier cannot change target",
                    ErrorCode.CONFLICT,
                )
            error = self._cancel_errors.get(command_id)
            if error is not None:
                return self._failed_future(running, error)
            return self._resolved_future(
                running, replace(self._cancel_results[command_id], replayed=True)
            )
        future = self._post(
            lambda: self._request_response_cancel(command_id, ref), control=True
        )
        self._pending_cancel[command_id] = (ref, future)
        future.add_done_callback(
            lambda completed: self._clear_pending_cancel(command_id, completed)
        )
        return future

    async def acknowledge_response_cancel(
        self, ref: ResponseRef
    ) -> RuntimeEvent | None:
        return await self._submit(
            lambda: self._runtime.acknowledge_response_cancel(ref), control=True
        )

    async def mark_response_cancel_unknown(
        self, ref: ResponseRef
    ) -> RuntimeEvent | None:
        return await self._submit(
            lambda: self._runtime.mark_response_cancel_unknown(ref), control=True
        )

    def post_produce_unit(self, unit: PresentationUnit) -> asyncio.Future[bool]:
        return self._post(lambda: self._produce_unit(unit), control=False)

    async def produce_unit(self, unit: PresentationUnit) -> bool:
        return await self._await_future(self.post_produce_unit(unit))

    def post_enqueue_unit(
        self, ref: ResponseRef, surface: PresentationSurface, unit_id: str
    ) -> asyncio.Future[tuple[bool, ConversationEffect | None]]:
        return self._post(
            lambda: self._enqueue_unit(ref, surface, unit_id), control=False
        )

    async def enqueue_unit(
        self, ref: ResponseRef, surface: PresentationSurface, unit_id: str
    ) -> tuple[bool, ConversationEffect | None]:
        return await self._await_future(self.post_enqueue_unit(ref, surface, unit_id))

    def post_presentation_ack(self, ack: PresentationAck) -> asyncio.Future[bool]:
        return self._post(
            lambda: self._acknowledge_presentation(ack),
            control=False,
            ordered_observation=True,
        )

    async def acknowledge_presentation(self, ack: PresentationAck) -> bool:
        return await self._await_future(self.post_presentation_ack(ack))

    def post_presentation_ack_with_history(
        self,
        ack: PresentationAck,
        content_resolver: Callable[[PresentationUnit], bytes],
    ) -> asyncio.Future[tuple[bool, PresentationHistoryIntent | None]]:
        if not callable(content_resolver):
            running = self._require_admission()
            return self._failed_future(
                running,
                ConversationRuntimeLoopViolation(
                    "INVALID_HISTORY_CONTENT_RESOLVER",
                    "history content resolver must be callable",
                    ErrorCode.INVALID_ARGUMENT,
                ),
            )
        return self._post(
            lambda: self._acknowledge_presentation_with_history(ack, content_resolver),
            control=False,
            ordered_observation=True,
        )

    async def acknowledge_presentation_with_history(
        self,
        ack: PresentationAck,
        content_resolver: Callable[[PresentationUnit], bytes],
    ) -> tuple[bool, PresentationHistoryIntent | None]:
        return await self._await_future(
            self.post_presentation_ack_with_history(ack, content_resolver)
        )

    def post_barge_in(
        self,
        action_id: str,
        ref: ResponseRef,
        *,
        cancel_response: bool = False,
    ) -> asyncio.Future[BargeInResult]:
        action_id = self._require_id(action_id, "action_id")
        if type(cancel_response) is not bool:
            raise ConversationRuntimeLoopViolation(
                "INVALID_BARGE_IN_POLICY",
                "cancel_response must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        running = self._require_admission()
        fingerprint = (ref, cancel_response)
        pending = self._pending_barge.get(action_id)
        if pending is not None:
            pending_fingerprint, future = pending
            if pending_fingerprint != fingerprint:
                raise ConversationRuntimeLoopViolation(
                    "BARGE_IN_ACTION_CONFLICT",
                    "a barge-in action identifier cannot change target or policy",
                    ErrorCode.CONFLICT,
                )
            return future
        prior_fingerprint = self._barge_fingerprints.get(action_id)
        if prior_fingerprint is not None:
            if prior_fingerprint != fingerprint:
                raise ConversationRuntimeLoopViolation(
                    "BARGE_IN_ACTION_CONFLICT",
                    "a barge-in action identifier cannot change target or policy",
                    ErrorCode.CONFLICT,
                )
            error = self._barge_errors.get(action_id)
            if error is not None:
                return self._failed_future(running, error)
            return self._resolved_future(
                running, replace(self._barge_results[action_id], replayed=True)
            )
        future = self._post(
            lambda: self._barge_in(action_id, ref, cancel_response), control=True
        )
        self._pending_barge[action_id] = (fingerprint, future)
        future.add_done_callback(
            lambda completed: self._clear_pending_barge(action_id, completed)
        )
        return future

    async def barge_in(
        self,
        action_id: str,
        ref: ResponseRef,
        *,
        cancel_response: bool = False,
    ) -> BargeInResult:
        return await self._await_future(
            self.post_barge_in(action_id, ref, cancel_response=cancel_response)
        )

    def post_generation_interrupt(
        self, action_id: str, ref: ResponseRef
    ) -> asyncio.Future[GenerationInterruptionResult]:
        action_id = self._require_id(action_id, "action_id")
        running = self._require_admission()
        retained = self._require_same_generation_interrupt_target(action_id, ref)
        if retained is not None:
            if retained.future is not None:
                return retained.future
            if retained.error is not None:
                return self._failed_future(running, retained.error)
            assert retained.result is not None
            return self._resolved_future(
                running, replace(retained.result, replayed=True)
            )
        self._evict_retained_generation_interrupts(reserve=1)
        if len(self._retained_generation_interrupts) >= _MAX_RETAINED_GENERATION_INTERRUPTS:
            raise ConversationRuntimeLoopViolation(
                "GENERATION_INTERRUPT_LEDGER_FULL",
                "bounded generation interruption ledger is full",
                ErrorCode.UNAVAILABLE,
            )
        entry = _RetainedGenerationInterrupt(ref=ref)
        future = self._post(
            lambda: self._generation_interrupt(action_id, entry), control=True
        )
        entry.future = future
        self._retained_generation_interrupts[action_id] = entry
        future.add_done_callback(
            lambda completed: self._settle_generation_interrupt(
                action_id, completed
            )
        )
        return future

    async def interrupt_generation(
        self, action_id: str, ref: ResponseRef
    ) -> GenerationInterruptionResult:
        return await self._await_future(
            self.post_generation_interrupt(action_id, ref)
        )

    async def claim_effects(
        self, *, limit: int | None = None
    ) -> tuple[ConversationEffect, ...]:
        def apply() -> tuple[ConversationEffect, ...]:
            if limit is not None and (type(limit) is not int or limit < 0):
                raise ConversationRuntimeLoopViolation(
                    "INVALID_EFFECT_LIMIT",
                    "effect claim limit must be a non-negative integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            if limit == 0:
                return ()
            selected: list[ConversationEffect] = []
            for index, record in enumerate(self._effects):
                if record.state is not EffectState.PENDING:
                    continue
                self._effects[index] = replace(record, state=EffectState.CLAIMED)
                selected.append(record.effect)
                if limit is not None and len(selected) >= limit:
                    break
            return tuple(selected)

        return await self._submit(apply)

    async def presented_history(
        self, ref: ResponseRef
    ) -> tuple[PresentedHistorySpan, ...]:
        return await self._submit(lambda: self._presentation.presented_history(ref))

    async def invalidate_presentation(self, ref: ResponseRef, *, reason: str) -> int:
        """Fence one exact response presentation without inventing an ACK."""

        reason = self._require_id(reason, "reason")

        def apply() -> int:
            self._response_record(ref)
            invalidated = self._presentation.invalidate_response(ref, reason=reason)
            self._invalidate_pending_output(
                ref,
                set(PresentationSurface),
                reason=reason,
            )
            return len(invalidated)

        return await self._submit(apply, control=True)

    def response_fence_state(
        self, ref: ResponseRef
    ) -> tuple[bool, ResponseState] | None:
        """Expose the exact CR-A response fence for output admission checks."""

        return self._runtime.response_fence_state(ref)

    def snapshot(self) -> ConversationRuntimeLoopSnapshot:
        worker_running = self._worker is not None and not self._worker.done()
        return ConversationRuntimeLoopSnapshot(
            started=self._started,
            accepting=self._accepting,
            closed=self._closed,
            worker_running=worker_running,
            pending_normal=len(self._normal),
            pending_observation=len(self._observation),
            pending_control=len(self._control),
            conversation=self._runtime.snapshot(),
            presentation=self._presentation.snapshot(),
            effects=tuple(self._effects),
        )

    def _produce_unit(self, unit: PresentationUnit) -> bool:
        if not isinstance(unit, PresentationUnit):
            raise ConversationRuntimeLoopViolation(
                "INVALID_PRESENTATION_UNIT",
                "presentation unit has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_current_output(unit.ref)
        return self._presentation.produce(unit)

    def _enqueue_unit(
        self, ref: ResponseRef, surface: PresentationSurface, unit_id: str
    ) -> tuple[bool, ConversationEffect | None]:
        self._require_current_output(ref)
        accepted, record = self._presentation.enqueue(ref, surface, unit_id)
        if not accepted:
            return False, None
        effect_type = (
            "ui.render"
            if record.unit.surface is PresentationSurface.TEXT
            else "audio.enqueue"
        )
        self._runtime.apply_output(ref, effect_type)
        effect = self._emit_effect(
            effect_type,
            ref,
            surface=record.unit.surface,
            unit=record.unit,
        )
        return True, effect

    def _acknowledge_presentation(self, ack: PresentationAck) -> bool:
        if not isinstance(ack, PresentationAck):
            raise ConversationRuntimeLoopViolation(
                "INVALID_PRESENTATION_ACK",
                "presentation acknowledgement has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_acknowledgeable_output(ack.ref)
        accepted, _ = self._presentation.acknowledge(ack)
        if accepted:
            self._mark_effect_presented(ack)
        return accepted

    def _acknowledge_presentation_with_history(
        self,
        ack: PresentationAck,
        content_resolver: Callable[[PresentationUnit], bytes],
    ) -> tuple[bool, PresentationHistoryIntent | None]:
        if not isinstance(ack, PresentationAck):
            raise ConversationRuntimeLoopViolation(
                "INVALID_PRESENTATION_ACK",
                "presentation acknowledgement has an unsupported type",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._require_acknowledgeable_output(ack.ref)
        prepared: list[PresentedHistoryContent] = []
        if ack.surface is PresentationSurface.TEXT:
            snapshot = self._presentation.snapshot()
            prior_cursor = next(
                (
                    cursor
                    for ref, surface, cursor in snapshot.cursors
                    if ref == ack.ref and surface is ack.surface
                ),
                -1,
            )
            records = sorted(
                (
                    record
                    for record in snapshot.records
                    if record.unit.ref == ack.ref
                    and record.unit.surface is ack.surface
                    and prior_cursor < record.unit.seq <= ack.contiguous_cursor
                ),
                key=lambda record: record.unit.seq,
            )
            for record in records:
                unit = record.unit
                content = content_resolver(unit)
                if not isinstance(content, bytes):
                    raise ConversationRuntimeLoopViolation(
                        "INVALID_HISTORY_CONTENT",
                        "history resolver must return immutable UTF-8 bytes",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                expected_length = unit.source_end_utf8 - unit.source_start_utf8
                digest = hashlib.sha256(content).hexdigest()
                if (
                    len(content) != expected_length
                    or unit.content_ref != f"sha256:{digest}"
                ):
                    raise ConversationRuntimeLoopViolation(
                        "HISTORY_CONTENT_BINDING_MISMATCH",
                        "resolved history bytes do not match the presentation unit",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ConversationRuntimeLoopViolation(
                        "INVALID_HISTORY_CONTENT",
                        "history content must be valid UTF-8",
                        ErrorCode.PROTOCOL_VIOLATION,
                    ) from error
                prepared.append(PresentedHistoryContent(unit, content))

        accepted, records = self._presentation.acknowledge(ack)
        if not accepted:
            return False, None
        self._mark_effect_presented(ack)
        if ack.surface is not PresentationSurface.TEXT:
            return True, None
        if tuple(item.unit for item in prepared) != tuple(
            record.unit for record in records
        ):
            raise ConversationRuntimeLoopViolation(
                "HISTORY_ACK_SERIALIZATION_MISMATCH",
                "history intent did not match the serialized ACK mutation",
                ErrorCode.INTERNAL,
            )
        return True, PresentationHistoryIntent(
            ref=ack.ref,
            surface=ack.surface,
            contiguous_cursor=ack.contiguous_cursor,
            presented_at=ack.presented_at,
            contents=tuple(prepared),
        )

    def _barge_in(
        self, action_id: str, ref: ResponseRef, cancel_response: bool
    ) -> BargeInResult:
        action_id = self._require_id(action_id, "action_id")
        if type(cancel_response) is not bool:
            raise ConversationRuntimeLoopViolation(
                "INVALID_BARGE_IN_POLICY",
                "cancel_response must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        fingerprint = (ref, cancel_response)
        prior_fingerprint = self._barge_fingerprints.get(action_id)
        if prior_fingerprint is not None:
            if prior_fingerprint != fingerprint:
                raise ConversationRuntimeLoopViolation(
                    "BARGE_IN_ACTION_CONFLICT",
                    "a barge-in action identifier cannot change target or policy",
                    ErrorCode.CONFLICT,
                )
            prior_error = self._barge_errors.get(action_id)
            if prior_error is not None:
                raise prior_error
            prior = self._barge_results[action_id]
            return replace(prior, replayed=True)

        self._barge_fingerprints[action_id] = fingerprint
        try:
            result = self._apply_new_barge_in(action_id, ref, cancel_response)
        except Exception as error:
            self._barge_errors[action_id] = error
            raise
        self._barge_results[action_id] = result
        return result

    def _request_response_cancel(
        self, command_id: str, ref: ResponseRef
    ) -> ResponseCancelResult:
        command_id = self._require_id(command_id, "command_id")
        prior_ref = self._cancel_fingerprints.get(command_id)
        if prior_ref is not None:
            if prior_ref != ref:
                raise ConversationRuntimeLoopViolation(
                    "RESPONSE_CANCEL_COMMAND_CONFLICT",
                    "a response cancel command identifier cannot change target",
                    ErrorCode.CONFLICT,
                )
            prior_error = self._cancel_errors.get(command_id)
            if prior_error is not None:
                raise prior_error
            return replace(self._cancel_results[command_id], replayed=True)

        self._cancel_fingerprints[command_id] = ref
        try:
            event, _ = self._runtime.request_response_cancel(ref)
            self._fence_presentation(ref, reason="response_cancel_requested")
            effect = self._emit_effect("response.cancel", ref, action_id=command_id)
            result = ResponseCancelResult(
                command_id=command_id,
                applied=True,
                replayed=False,
                event=event,
                effect_id=effect.effect_id,
            )
        except Exception as error:
            self._cancel_errors[command_id] = error
            raise
        self._cancel_results[command_id] = result
        return result

    def _generation_interrupt(
        self, action_id: str, entry: _RetainedGenerationInterrupt
    ) -> GenerationInterruptionResult:
        action_id = self._require_id(action_id, "action_id")
        if self._retained_generation_interrupts.get(action_id) is not entry:
            raise ConversationRuntimeLoopViolation(
                "GENERATION_INTERRUPT_ACTION_MISSING",
                "generation interruption lost its admitted ledger identity",
                ErrorCode.INTERNAL,
            )
        try:
            entry.result = self._apply_new_generation_interrupt(action_id, entry.ref)
        except Exception as error:
            entry.error = error
            raise
        return entry.result

    def _require_same_generation_interrupt_target(
        self, action_id: str, ref: ResponseRef
    ) -> _RetainedGenerationInterrupt | None:
        """Return the retained action, refusing one that changed its target."""

        retained = self._retained_generation_interrupts.get(action_id)
        if retained is not None and retained.ref != ref:
            raise ConversationRuntimeLoopViolation(
                "GENERATION_INTERRUPT_ACTION_CONFLICT",
                "a generation interrupt action identifier cannot change target",
                ErrorCode.CONFLICT,
            )
        return retained

    def _evict_retained_generation_interrupts(self, *, reserve: int = 0) -> None:
        """Bound the replay ledger across a long hands-free conversation.

        Every turn can carry one interruption, so this ledger grows with the
        conversation rather than with a user control action.  Eviction is
        oldest-first and never touches an action whose future is still pending:
        a pending action is skipped and kept in its original position rather
        than ending the sweep, so one unresolved oldest entry cannot let every
        settled entry behind it accumulate past the bound.
        """

        if reserve < 0 or reserve > _MAX_RETAINED_GENERATION_INTERRUPTS:
            raise AssertionError("generation interruption reserve is invalid")
        evictable = len(self._retained_generation_interrupts) - (
            _MAX_RETAINED_GENERATION_INTERRUPTS - reserve
        )
        if evictable <= 0:
            return
        for action_id, entry in list(self._retained_generation_interrupts.items()):
            if evictable <= 0:
                break
            if entry.future is not None and not entry.future.done():
                continue
            del self._retained_generation_interrupts[action_id]
            evictable -= 1

    def _apply_new_generation_interrupt(
        self, action_id: str, ref: ResponseRef
    ) -> GenerationInterruptionResult:
        record = self._response_record(ref)
        interaction = next(
            (
                item
                for item in self._runtime.snapshot().interactions
                if item.interaction_id == ref.interaction_id
            ),
            None,
        )
        if interaction is None or interaction.state is not InteractionState.OPEN:
            # Exit already owns this interaction.  A later speech interrupt
            # must not reopen or mutate that closing decision.
            raise ConversationRuntimeLoopViolation(
                "INTERACTION_NOT_OPEN",
                "generation interruption requires an open interaction",
                ErrorCode.CONFLICT,
            )
        latest = self._latest_response_record(ref.interaction_id)
        if latest is None or latest.ref != ref:
            raise ConversationRuntimeLoopViolation(
                "STALE_RESPONSE_OUTPUT",
                "generation interruption must target the latest exact response",
                ErrorCode.STALE,
            )
        if record.state is ResponseState.TERMINAL:
            raise ConversationRuntimeLoopViolation(
                "RESPONSE_ALREADY_TERMINAL",
                "a terminal response has no live generation to interrupt",
                ErrorCode.CONFLICT,
            )

        effects: list[ConversationEffect] = []
        # One fence closes TEXT and AUDIO together.  Every later produce,
        # enqueue, ACK and history projection of this exact tuple is refused by
        # _require_current_output / _require_acknowledgeable_output.
        self._fence_presentation(ref, reason="generation_interrupt")
        stop = self._emit_playback_stop_once(ref, action_id=action_id)
        if stop is not None:
            effects.append(stop)
        cancel_requested = False
        if record.cancel_state is CancelState.NONE:
            self._runtime.request_response_cancel(ref)
            cancel_requested = True
            effects.append(
                self._emit_effect("response.cancel", ref, action_id=action_id)
            )
        return GenerationInterruptionResult(
            action_id=action_id,
            ref=ref,
            applied=bool(effects),
            replayed=False,
            interrupted_state=record.state,
            cancel_requested=cancel_requested,
            effect_ids=tuple(effect.effect_id for effect in effects),
        )

    def _settle_generation_interrupt(
        self, action_id: str, completed: asyncio.Future[GenerationInterruptionResult]
    ) -> None:
        entry = self._retained_generation_interrupts.get(action_id)
        if entry is None or entry.future is not completed:
            return
        if entry.result is None and entry.error is None:
            if completed.cancelled():
                entry.error = ConversationRuntimeLoopViolation(
                    "GENERATION_INTERRUPT_ACTION_CANCELLED",
                    "generation interruption was cancelled before settlement",
                    ErrorCode.CANCELLED,
                )
            else:
                error = completed.exception()
                if error is None:
                    entry.result = completed.result()
                elif isinstance(error, Exception):
                    entry.error = error
                else:
                    entry.error = ConversationRuntimeLoopViolation(
                        "GENERATION_INTERRUPT_ACTION_FAILED",
                        "generation interruption failed outside the runtime contract",
                        ErrorCode.INTERNAL,
                    )
        entry.future = None

    def _clear_pending_barge(
        self, action_id: str, completed: asyncio.Future[BargeInResult]
    ) -> None:
        pending = self._pending_barge.get(action_id)
        if pending is not None and pending[1] is completed:
            del self._pending_barge[action_id]

    def _clear_pending_cancel(
        self, command_id: str, completed: asyncio.Future[ResponseCancelResult]
    ) -> None:
        pending = self._pending_cancel.get(command_id)
        if pending is not None and pending[1] is completed:
            del self._pending_cancel[command_id]

    def _apply_new_barge_in(
        self, action_id: str, ref: ResponseRef, cancel_response: bool
    ) -> BargeInResult:
        record = self._response_record(ref)
        if (
            record.state is not ResponseState.TERMINAL
            and cancel_response
            and record.cancel_state is CancelState.NONE
            and record.fenced
        ):
            raise ConversationRuntimeLoopViolation(
                "STALE_RESPONSE_OUTPUT",
                "a replaced response cannot acquire a new cancel request",
                ErrorCode.STALE,
            )

        effects: list[ConversationEffect] = []
        self._presentation.close_surface(
            ref, PresentationSurface.AUDIO, reason="barge_in"
        )
        self._invalidate_pending_output(
            ref, {PresentationSurface.AUDIO}, reason="barge_in"
        )
        stop = self._emit_playback_stop_once(ref, action_id=action_id)
        if stop is not None:
            effects.append(stop)

        # Agent generation and downstream playout have independent lifecycles.
        # A completed response may still be audible, so terminal state suppresses
        # only response cancellation; it never suppresses the exact playback stop.
        if (
            cancel_response
            and record.state is not ResponseState.TERMINAL
            and record.cancel_state is CancelState.NONE
        ):
            self._runtime.request_response_cancel(ref)
            self._fence_presentation(ref, reason="barge_in_response_cancel")
            effects.append(
                self._emit_effect("response.cancel", ref, action_id=action_id)
            )

        result = BargeInResult(
            action_id=action_id,
            applied=bool(effects),
            replayed=False,
            effect_ids=tuple(effect.effect_id for effect in effects),
        )
        return result

    def _fence_presentation(self, ref: ResponseRef, *, reason: str) -> None:
        self._presentation.invalidate_response(ref, reason=reason)
        self._invalidate_pending_output(ref, set(PresentationSurface), reason=reason)

    def _emit_playback_stop_once(
        self, ref: ResponseRef, *, action_id: str | None = None
    ) -> ConversationEffect | None:
        if ref in self._playback_stopped:
            return None
        self._playback_stopped.add(ref)
        return self._emit_effect(
            "playback.stop",
            ref,
            surface=PresentationSurface.AUDIO,
            action_id=action_id,
        )

    def _emit_effect(
        self,
        effect_type: str,
        ref: ResponseRef,
        *,
        surface: PresentationSurface | None = None,
        unit: PresentationUnit | None = None,
        action_id: str | None = None,
    ) -> ConversationEffect:
        seq = len(self._effects) + 1
        effect = ConversationEffect(
            effect_id=f"conversation-effect-{seq}",
            seq=seq,
            effect_type=effect_type,
            scope=self._scope,
            ref=ref,
            surface=surface,
            unit_id=None if unit is None else unit.unit_id,
            unit_seq=None if unit is None else unit.seq,
            content_ref=None if unit is None else unit.content_ref,
            action_id=action_id,
        )
        self._effects.append(EffectRecord(effect, EffectState.PENDING))
        return effect

    def _invalidate_pending_output(
        self,
        ref: ResponseRef,
        surfaces: set[PresentationSurface],
        *,
        reason: str,
    ) -> None:
        for index, record in enumerate(self._effects):
            effect = record.effect
            if (
                record.state is EffectState.PENDING
                and effect.effect_type in self._OUTPUT_EFFECTS
                and effect.ref == ref
                and effect.surface in surfaces
            ):
                self._effects[index] = replace(
                    record,
                    state=EffectState.INVALIDATED,
                    invalidated_reason=reason,
                )

    def _mark_effect_presented(self, ack: PresentationAck) -> None:
        for index, record in enumerate(self._effects):
            effect = record.effect
            if (
                record.state is EffectState.PENDING
                and effect.effect_type in self._OUTPUT_EFFECTS
                and effect.ref == ack.ref
                and effect.surface is ack.surface
                and effect.unit_seq is not None
                and effect.unit_seq <= ack.contiguous_cursor
            ):
                self._effects[index] = replace(record, state=EffectState.CLAIMED)

    def _require_current_output(self, ref: ResponseRef) -> ResponseRecord:
        record = self._response_record(ref)
        if record.fenced or record.state is ResponseState.TERMINAL:
            raise ConversationRuntimeLoopViolation(
                "STALE_RESPONSE_OUTPUT",
                "output does not match an active response generation",
                ErrorCode.STALE,
            )
        if record.state not in {ResponseState.GENERATING, ResponseState.SPEAKING}:
            raise ConversationRuntimeLoopViolation(
                "RESPONSE_OUTPUT_NOT_ACTIVE",
                "presentation output requires a generating or speaking response",
                ErrorCode.CONFLICT,
            )
        return record

    def _require_acknowledgeable_output(self, ref: ResponseRef) -> ResponseRecord:
        record = self._response_record(ref)
        interaction = next(
            (
                item
                for item in self._runtime.snapshot().interactions
                if item.interaction_id == ref.interaction_id
            ),
            None,
        )
        if interaction is None or interaction.state is not InteractionState.OPEN:
            raise ConversationRuntimeLoopViolation(
                "STALE_RESPONSE_OUTPUT",
                "presentation acknowledgement requires an open interaction",
                ErrorCode.STALE,
            )
        if record.state is not ResponseState.TERMINAL:
            return self._require_current_output(ref)
        latest = self._latest_response_record(ref.interaction_id)
        if latest is None or latest.ref != ref:
            raise ConversationRuntimeLoopViolation(
                "STALE_RESPONSE_OUTPUT",
                "presentation acknowledgement requires the latest exact response",
                ErrorCode.STALE,
            )
        # Terminal fences all future output through _require_current_output and
        # ResponseFence.  PresentationLedger remains the narrower authority for
        # an exact pre-terminal ENQUEUED unit on an open, non-invalidated surface.
        return record

    def _response_record(self, ref: ResponseRef) -> ResponseRecord:
        for record in self._runtime.snapshot().responses:
            if record.ref == ref:
                return record
        raise ConversationRuntimeLoopViolation(
            "STALE_RESPONSE_REFERENCE",
            "response operation requires the exact known response tuple",
            ErrorCode.STALE,
        )

    def _response_records(self, interaction_id: str) -> tuple[ResponseRecord, ...]:
        return tuple(
            record
            for record in self._runtime.snapshot().responses
            if record.ref.interaction_id == interaction_id
        )

    def _latest_response_record(self, interaction_id: str) -> ResponseRecord | None:
        records = self._response_records(interaction_id)
        if not records:
            return None
        return max(records, key=lambda item: item.ref.response_generation)

    async def _submit(
        self, callback: Callable[[], _ValueT], *, control: bool = False
    ) -> _ValueT:
        return await self._await_future(self._post(callback, control=control))

    def _post(
        self,
        callback: Callable[[], _ValueT],
        *,
        control: bool,
        ordered_observation: bool = False,
    ) -> asyncio.Future[_ValueT]:
        running = self._require_admission()
        if control and ordered_observation:
            raise AssertionError("an operation cannot use two runtime lanes")
        if control:
            lane = self._control
            capacity = self._control_capacity
            reason = "CONTROL_QUEUE_FULL"
        elif ordered_observation:
            lane = self._observation
            capacity = self._normal_capacity
            reason = "OBSERVATION_QUEUE_FULL"
        else:
            lane = self._normal
            capacity = self._normal_capacity
            reason = "NORMAL_QUEUE_FULL"
        if len(lane) >= capacity:
            raise ConversationRuntimeLoopViolation(
                reason,
                "bounded conversation runtime lane is full",
                ErrorCode.UNAVAILABLE,
            )
        future: asyncio.Future[object] = running.create_future()
        lane.append(
            _QueuedOperation(
                self._next_ingress_seq,
                cast(Callable[[], object], callback),
                future,
            )
        )
        self._next_ingress_seq += 1
        assert self._wake is not None
        self._wake.set()
        return cast(asyncio.Future[_ValueT], future)

    def _require_admission(self) -> asyncio.AbstractEventLoop:
        if not self._enabled:
            raise ConversationRuntimeLoopViolation(
                "FEATURE_DISABLED",
                "conversation runtime is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )
        running = asyncio.get_running_loop()
        if self._worker is None or self._wake is None or not self._accepting:
            reason = (
                "RUNTIME_LOOP_CLOSED" if self._closed else "RUNTIME_LOOP_NOT_STARTED"
            )
            raise ConversationRuntimeLoopViolation(
                reason,
                "conversation runtime loop is not accepting operations",
                ErrorCode.CONFLICT,
            )
        self._require_owner_loop(running)
        return running

    @staticmethod
    async def _await_future(future: asyncio.Future[_ValueT]) -> _ValueT:
        return await asyncio.shield(future)

    @staticmethod
    def _resolved_future(
        running: asyncio.AbstractEventLoop, result: _ValueT
    ) -> asyncio.Future[_ValueT]:
        future: asyncio.Future[_ValueT] = running.create_future()
        future.set_result(result)
        return future

    @staticmethod
    def _failed_future(
        running: asyncio.AbstractEventLoop, error: Exception
    ) -> asyncio.Future[_ValueT]:
        future: asyncio.Future[_ValueT] = running.create_future()
        future.set_exception(error)
        return future

    async def _run(self) -> None:
        assert self._wake is not None
        try:
            while True:
                await self._wake.wait()
                while True:
                    operation = self._next_operation()
                    if operation is None:
                        if self._shutdown_future is not None:
                            try:
                                effects = self._shutdown_state()
                            except Exception as error:
                                if not self._shutdown_future.done():
                                    self._shutdown_future.set_exception(error)
                            else:
                                if not self._shutdown_future.done():
                                    self._shutdown_future.set_result(effects)
                            return
                        self._wake.clear()
                        break
                    self._apply_operation(operation)
                    await asyncio.sleep(0)
        finally:
            self._accepting = False
            self._closed = True
            self._fail_pending(
                ConversationRuntimeLoopViolation(
                    "RUNTIME_LOOP_CLOSED",
                    "conversation runtime loop closed before the operation ran",
                    ErrorCode.CANCELLED,
                )
            )

    def _next_operation(self) -> _QueuedOperation | None:
        if self._control:
            if (
                self._observation
                and self._observation[0].ingress_seq < self._control[0].ingress_seq
            ):
                return self._observation.popleft()
            return self._control.popleft()
        if self._observation and self._normal:
            if self._observation[0].ingress_seq < self._normal[0].ingress_seq:
                return self._observation.popleft()
            return self._normal.popleft()
        if self._observation:
            return self._observation.popleft()
        if self._normal:
            return self._normal.popleft()
        return None

    @staticmethod
    def _apply_operation(operation: _QueuedOperation) -> None:
        try:
            result = operation.callback()
        except Exception as error:
            if not operation.future.done():
                operation.future.set_exception(error)
        else:
            if not operation.future.done():
                operation.future.set_result(result)

    def _shutdown_state(self) -> tuple[ConversationEffect, ...]:
        for record in self._runtime.snapshot().responses:
            self._fence_presentation(record.ref, reason="runtime_loop_shutdown")
            if record.state is not ResponseState.TERMINAL:
                self._emit_playback_stop_once(record.ref)
        claimed: list[ConversationEffect] = []
        for index, effect_record in enumerate(self._effects):
            if effect_record.state is not EffectState.PENDING:
                continue
            self._effects[index] = replace(effect_record, state=EffectState.CLAIMED)
            claimed.append(effect_record.effect)
        return tuple(claimed)

    def _fail_pending(self, error: BaseException) -> None:
        for lane in (self._control, self._observation, self._normal):
            while lane:
                operation = lane.popleft()
                if not operation.future.done():
                    operation.future.set_exception(error)

    def _require_owner_loop(self, running: asyncio.AbstractEventLoop) -> None:
        if self._owner_loop is not running:
            raise ConversationRuntimeLoopViolation(
                "RUNTIME_EVENT_LOOP_MISMATCH",
                "conversation runtime operations must use the owning event loop",
                ErrorCode.CONFLICT,
            )

    @staticmethod
    def _history_policy(value: HistorySurfacePolicy) -> HistorySurfacePolicy:
        if not isinstance(value, HistorySurfacePolicy):
            raise ConversationRuntimeLoopViolation(
                "INVALID_HISTORY_SURFACE_POLICY",
                "history policy must be text, audio, or union",
                ErrorCode.INVALID_ARGUMENT,
            )
        return value

    @staticmethod
    def _require_id(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ConversationRuntimeLoopViolation(
                "INVALID_ID",
                f"{name} must be non-empty",
                ErrorCode.INVALID_ARGUMENT,
            )
        return value

    @staticmethod
    def _validate_capacity(value: int, name: str) -> None:
        if type(value) is not int or value <= 0:
            raise ConversationRuntimeLoopViolation(
                "INVALID_QUEUE_CAPACITY",
                f"{name} must be a positive integer",
                ErrorCode.INVALID_ARGUMENT,
            )
