# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Priority event loop and declarative effect outbox for Live Voice CR-B."""

from __future__ import annotations

import asyncio
import hashlib
from collections import OrderedDict, deque
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
    ConversationRuntimeViolation,
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
    PresentationLedgerViolation,
    PresentationSurface,
    PresentationUnit,
    PresentedHistorySpan,
)

# A completed control command must not live for the loop's whole lifetime.  The
# lane capacities bound only work that is still waiting to run, so barge-in and
# response-cancel identities keep their own exact budget here.  Beyond it the
# oldest identity releases its fingerprint and outcome and keeps only a compact
# tombstone in the fail-closed replay fence below.
MAX_RETAINED_CONTROL_COMMANDS = 256
# The fence is a one-bit membership sketch whose bits are only ever set, so a
# digest collision can refuse an identifier that was never used and can never
# re-admit a retired one.  Four 8 KiB rows hold every retirement in 32 KiB for
# the loop's lifetime instead of growing with the session.
_CONTROL_REPLAY_FENCE_ROWS = 4
_CONTROL_REPLAY_FENCE_WIDTH = 1 << 13
_BARGE_CONTROL_SCOPE = "conversation.barge_in"
_CANCEL_CONTROL_SCOPE = "conversation.response_cancel"
# A retained failure keeps only a stable code, reason and message.  These caps
# bound that record and reject anything that is not the short, module-authored
# description these violation families are contracted to carry.
_MAX_CONTROL_FAILURE_REASON_CHARS = 128
_MAX_CONTROL_FAILURE_MESSAGE_CHARS = 256
_CONTROL_COMMAND_FAILURE_MESSAGE = "conversation runtime control command failed"


class ConversationRuntimeLoopViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


# Only these exact violation families carry a stable, module-authored reason and
# message.  Matching is by physical type identity, never `isinstance`, so a
# subclass or an untrusted caller object can never reach the branch that keeps
# its text.
_SAFE_CONTROL_FAILURE_TYPES: tuple[type[Exception], ...] = (
    ConversationRuntimeLoopViolation,
    ConversationRuntimeViolation,
    PresentationLedgerViolation,
)


@dataclass(frozen=True, slots=True)
class _ControlFailure:
    """A content-free description of one failed control command.

    It holds no exception object, traceback, exception chain or caller payload,
    only the exception family to rebuild and the stable code, reason and message
    a replaying caller still needs.
    """

    factory: Callable[[str, str, ErrorCode], Exception]
    reason: str
    message: str
    code: ErrorCode

    def rebuild(self) -> Exception:
        """Build a fresh failure so no caller inherits another's traceback."""

        return self.factory(self.reason, self.message, self.code)


def _control_failure(error: BaseException) -> _ControlFailure:
    """Project a control failure onto its stable, content-free facts.

    Classification never calls a hook on the failing object: an unrecognized
    exception keeps no text at all, so a hostile ``__str__``/``__repr__`` is
    never invoked and no transcript, payload or exception chain survives.
    """

    failure_type = type(error)
    for candidate in _SAFE_CONTROL_FAILURE_TYPES:
        if failure_type is not candidate:
            continue
        reason = getattr(error, "reason", None)
        code = getattr(error, "code", None)
        args = error.args
        message = args[0] if len(args) == 1 else None
        if (
            type(reason) is str
            and type(message) is str
            and type(code) is ErrorCode
            and len(reason) <= _MAX_CONTROL_FAILURE_REASON_CHARS
            and len(message) <= _MAX_CONTROL_FAILURE_MESSAGE_CHARS
        ):
            return _ControlFailure(candidate, reason, message, code)
        break
    return _ControlFailure(
        ConversationRuntimeLoopViolation,
        "CONTROL_COMMAND_FAILED",
        _CONTROL_COMMAND_FAILURE_MESSAGE,
        ErrorCode.INTERNAL,
    )


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
class _ControlCommandRecord:
    """One executed control command: its exact fingerprint and its outcome.

    ``fingerprint`` is the exact barge-in ``(ref, cancel_response)`` tuple or the
    exact response-cancel ``ResponseRef``, and ``result`` is the matching public
    result.  Exactly one of ``result`` and ``failure`` is set once the command
    has finished; a record with neither means the command's outcome is unknown.
    """

    fingerprint: object
    result: object | None = None
    failure: _ControlFailure | None = None


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
    retained_control_commands: int = 0
    fenced_control_commands: int = 0


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
        # One bounded exact ledger per control kind.  It replaces the separate
        # fingerprint, result and error maps that used to keep every executed
        # command for the loop's lifetime.
        self._barge_commands: OrderedDict[str, _ControlCommandRecord] = OrderedDict()
        self._cancel_commands: OrderedDict[str, _ControlCommandRecord] = OrderedDict()
        self._control_replay_fence = tuple(
            bytearray(_CONTROL_REPLAY_FENCE_WIDTH)
            for _ in range(_CONTROL_REPLAY_FENCE_ROWS)
        )
        self._fenced_control_commands = 0
        self._pending_barge: dict[
            str, tuple[tuple[ResponseRef, bool], asyncio.Future[BargeInResult]]
        ] = {}
        self._pending_cancel: dict[
            str, tuple[ResponseRef, asyncio.Future[ResponseCancelResult]]
        ] = {}
        self._playback_stopped: set[ResponseRef] = set()

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
        retained = self._cancel_commands.get(command_id)
        if retained is not None:
            if retained.fingerprint != ref:
                raise ConversationRuntimeLoopViolation(
                    "RESPONSE_CANCEL_COMMAND_CONFLICT",
                    "a response cancel command identifier cannot change target",
                    ErrorCode.CONFLICT,
                )
            error = self._replayed_control_failure(retained)
            if error is not None:
                return self._failed_future(running, error)
            return self._resolved_future(
                running,
                replace(cast(ResponseCancelResult, retained.result), replayed=True),
            )
        # Admission is the only fence gate: a command already accepted into a
        # lane must not be refused by a bit another identity set after it.
        if self._control_replay_fenced(_CANCEL_CONTROL_SCOPE, command_id):
            raise ConversationRuntimeLoopViolation(
                "RESPONSE_CANCEL_COMMAND_RETIRED",
                "a retired response cancel command identifier cannot be reused",
                ErrorCode.CONFLICT,
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
        retained = self._barge_commands.get(action_id)
        if retained is not None:
            if retained.fingerprint != fingerprint:
                raise ConversationRuntimeLoopViolation(
                    "BARGE_IN_ACTION_CONFLICT",
                    "a barge-in action identifier cannot change target or policy",
                    ErrorCode.CONFLICT,
                )
            error = self._replayed_control_failure(retained)
            if error is not None:
                return self._failed_future(running, error)
            return self._resolved_future(
                running, replace(cast(BargeInResult, retained.result), replayed=True)
            )
        # Admission is the only fence gate: a command already accepted into a
        # lane must not be refused by a bit another identity set after it.
        if self._control_replay_fenced(_BARGE_CONTROL_SCOPE, action_id):
            raise ConversationRuntimeLoopViolation(
                "BARGE_IN_ACTION_RETIRED",
                "a retired barge-in action identifier cannot be reused",
                ErrorCode.CONFLICT,
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
            retained_control_commands=len(self._barge_commands)
            + len(self._cancel_commands),
            fenced_control_commands=self._fenced_control_commands,
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
        retained = self._barge_commands.get(action_id)
        if retained is not None:
            if retained.fingerprint != fingerprint:
                raise ConversationRuntimeLoopViolation(
                    "BARGE_IN_ACTION_CONFLICT",
                    "a barge-in action identifier cannot change target or policy",
                    ErrorCode.CONFLICT,
                )
            prior_error = self._replayed_control_failure(retained)
            if prior_error is not None:
                raise prior_error
            return replace(cast(BargeInResult, retained.result), replayed=True)

        self._retain_control_command(
            self._barge_commands,
            _BARGE_CONTROL_SCOPE,
            action_id,
            _ControlCommandRecord(fingerprint),
        )
        try:
            result = self._apply_new_barge_in(action_id, ref, cancel_response)
        except Exception as error:
            self._retain_control_command(
                self._barge_commands,
                _BARGE_CONTROL_SCOPE,
                action_id,
                _ControlCommandRecord(fingerprint, failure=_control_failure(error)),
            )
            raise
        self._retain_control_command(
            self._barge_commands,
            _BARGE_CONTROL_SCOPE,
            action_id,
            _ControlCommandRecord(fingerprint, result=result),
        )
        return result

    def _request_response_cancel(
        self, command_id: str, ref: ResponseRef
    ) -> ResponseCancelResult:
        command_id = self._require_id(command_id, "command_id")
        retained = self._cancel_commands.get(command_id)
        if retained is not None:
            if retained.fingerprint != ref:
                raise ConversationRuntimeLoopViolation(
                    "RESPONSE_CANCEL_COMMAND_CONFLICT",
                    "a response cancel command identifier cannot change target",
                    ErrorCode.CONFLICT,
                )
            prior_error = self._replayed_control_failure(retained)
            if prior_error is not None:
                raise prior_error
            return replace(cast(ResponseCancelResult, retained.result), replayed=True)

        self._retain_control_command(
            self._cancel_commands,
            _CANCEL_CONTROL_SCOPE,
            command_id,
            _ControlCommandRecord(ref),
        )
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
            self._retain_control_command(
                self._cancel_commands,
                _CANCEL_CONTROL_SCOPE,
                command_id,
                _ControlCommandRecord(ref, failure=_control_failure(error)),
            )
            raise
        self._retain_control_command(
            self._cancel_commands,
            _CANCEL_CONTROL_SCOPE,
            command_id,
            _ControlCommandRecord(ref, result=result),
        )
        return result

    def _retain_control_command(
        self,
        ledger: OrderedDict[str, _ControlCommandRecord],
        scope: str,
        key: str,
        record: _ControlCommandRecord,
    ) -> None:
        """Keep one exact command and retire the oldest beyond the bound."""

        ledger[key] = record
        ledger.move_to_end(key)
        while len(ledger) > MAX_RETAINED_CONTROL_COMMANDS:
            retired, _ = ledger.popitem(last=False)
            for row, index in zip(
                self._control_replay_fence,
                self._control_fence_indices(scope, retired),
                strict=True,
            ):
                row[index] = 1
            self._fenced_control_commands += 1

    def _control_fence_indices(self, scope: str, key: str) -> tuple[int, ...]:
        digest = hashlib.sha256(f"{scope}\0{key}".encode()).digest()
        width = len(self._control_replay_fence[0])
        return tuple(
            int.from_bytes(digest[offset : offset + 4], "big") % width
            for offset in range(0, 4 * _CONTROL_REPLAY_FENCE_ROWS, 4)
        )

    def _control_replay_fenced(self, scope: str, key: str) -> bool:
        """Report whether this loop already retired the exact identifier."""

        return all(
            row[index]
            for row, index in zip(
                self._control_replay_fence,
                self._control_fence_indices(scope, key),
                strict=True,
            )
        )

    @staticmethod
    def _replayed_control_failure(
        record: _ControlCommandRecord,
    ) -> Exception | None:
        """Return the failure a replay must raise, or None for a kept result."""

        if record.failure is not None:
            # Rebuild per replay so the traceback one caller raises can never
            # become part of the record the next caller receives.
            return record.failure.rebuild()
        if record.result is None:
            return ConversationRuntimeLoopViolation(
                "CONTROL_COMMAND_RESULT_UNKNOWN",
                "a retained control command has no recorded outcome",
                ErrorCode.RESULT_UNKNOWN,
            )
        return None

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
        if record.state is ResponseState.TERMINAL:
            raise ConversationRuntimeLoopViolation(
                "RESPONSE_ALREADY_TERMINAL",
                "a terminal response has no live playback to interrupt",
                ErrorCode.CONFLICT,
            )
        if (
            cancel_response
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

        if cancel_response and record.cancel_state is CancelState.NONE:
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
