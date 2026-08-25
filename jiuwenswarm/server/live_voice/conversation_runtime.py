# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Canonical in-memory conversation state for the Live Voice formal path."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    LifecycleKind,
    MAX_SAFE_INTEGER,
    ResponseFence,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    canonical_json,
    validate_transition,
)


class ConversationRuntimeViolation(ValueError):
    def __init__(self, reason: str, message: str, code: ErrorCode) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


class InteractionState(StrEnum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class TurnState(StrEnum):
    CAPTURING = "capturing"
    COMMITTED = "committed"
    CANCELLED = "cancelled"


class ResponseState(StrEnum):
    ACCEPTED = "accepted"
    GENERATING = "generating"
    SPEAKING = "speaking"
    TERMINAL = "terminal"


class CancelState(StrEnum):
    NONE = "none"
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    RESULT_UNKNOWN = "result_unknown"


@dataclass(frozen=True, slots=True)
class InteractionRecord:
    interaction_id: str
    state: InteractionState


@dataclass(frozen=True, slots=True)
class TurnRecord:
    turn_id: str
    interaction_id: str
    state: TurnState
    commit_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    ref: ResponseRef
    turn_id: str
    state: ResponseState
    fenced: bool = False
    cancel_state: CancelState = CancelState.NONE
    outcome: TerminalOutcome | None = None


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    seq: int
    event_type: str
    scope: ScopeRef
    interaction_id: str
    turn_id: str | None = None
    response_id: str | None = None
    response_generation: int | None = None
    state: str | None = None
    cancel_state: str | None = None
    outcome: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "event_type": self.event_type,
            "scope": self.scope.to_dict(),
            "interaction_id": self.interaction_id,
            "turn_id": self.turn_id,
            "response_id": self.response_id,
            "response_generation": self.response_generation,
            "state": self.state,
            "cancel_state": self.cancel_state,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class RuntimeEffect:
    effect_type: str
    interaction_id: str
    response_id: str | None = None
    response_generation: int | None = None


@dataclass(frozen=True, slots=True)
class ConversationSnapshot:
    scope: ScopeRef
    interactions: tuple[InteractionRecord, ...]
    turns: tuple[TurnRecord, ...]
    responses: tuple[ResponseRecord, ...]
    last_seq: int


class ConversationRuntime:
    _OUTPUT_EFFECTS = frozenset({"ui.render", "history.append", "audio.enqueue"})

    def __init__(
        self,
        scope: ScopeRef,
        *,
        enabled: bool = True,
        response_generation_owner: Callable[[str, int], int] | None = None,
    ) -> None:
        if response_generation_owner is not None and not callable(
            response_generation_owner
        ):
            raise ConversationRuntimeViolation(
                "INVALID_RESPONSE_GENERATION_OWNER",
                "response generation owner must be callable",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._scope = scope
        self._enabled = enabled
        self._response_generation_owner = response_generation_owner
        self._lock = threading.RLock()
        self._interactions: dict[str, InteractionRecord] = {}
        self._turns: dict[str, TurnRecord] = {}
        self._responses: dict[str, ResponseRecord] = {}
        self._active_response: dict[str, str] = {}
        self._last_generation: dict[str, int] = {}
        self._commit_ledger = TurnCommitLedger()
        self._response_fence = ResponseFence()
        self._events: list[RuntimeEvent] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise ConversationRuntimeViolation(
                "FEATURE_DISABLED",
                "conversation runtime is disabled",
                ErrorCode.CAPABILITY_UNAVAILABLE,
            )

    @staticmethod
    def _require_id(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ConversationRuntimeViolation(
                "INVALID_ID", f"{name} must be non-empty", ErrorCode.INVALID_ARGUMENT
            )
        return value

    def _emit(
        self,
        event_type: str,
        interaction_id: str,
        *,
        turn_id: str | None = None,
        response: ResponseRecord | None = None,
        state: str | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            seq=len(self._events) + 1,
            event_type=event_type,
            scope=self._scope,
            interaction_id=interaction_id,
            turn_id=turn_id,
            response_id=None if response is None else response.ref.response_id,
            response_generation=(
                None if response is None else response.ref.response_generation
            ),
            state=state,
            cancel_state=(None if response is None else response.cancel_state.value),
            outcome=(
                None
                if response is None or response.outcome is None
                else response.outcome.value
            ),
        )
        self._events.append(event)
        return event

    def open_interaction(self, interaction_id: str) -> RuntimeEvent:
        with self._lock:
            self._require_enabled()
            interaction_id = self._require_id(interaction_id, "interaction_id")
            if interaction_id in self._interactions:
                raise ConversationRuntimeViolation(
                    "INTERACTION_ALREADY_EXISTS",
                    "interaction identifiers cannot be reused",
                    ErrorCode.CONFLICT,
                )
            record = InteractionRecord(interaction_id, InteractionState.OPEN)
            self._interactions[interaction_id] = record
            return self._emit(
                "interaction.opened", interaction_id, state=record.state.value
            )

    def transition_interaction(
        self, interaction_id: str, target: InteractionState
    ) -> RuntimeEvent:
        with self._lock:
            self._require_enabled()
            record = self._interaction(interaction_id)
            validate_transition(
                LifecycleKind.INTERACTION, record.state.value, target.value
            )
            updated = replace(record, state=target)
            self._interactions[interaction_id] = updated
            if target in {InteractionState.CLOSING, InteractionState.CLOSED}:
                active_id = self._active_response.get(interaction_id)
                if active_id is not None:
                    response = self._responses[active_id]
                    if not response.fenced:
                        self._response_fence.cancel(response.ref)
                        self._responses[active_id] = replace(response, fenced=True)
            return self._emit(
                f"interaction.{target.value}", interaction_id, state=target.value
            )

    def start_turn(self, interaction_id: str, turn_id: str) -> RuntimeEvent:
        with self._lock:
            self._require_enabled()
            interaction = self._interaction(interaction_id)
            if interaction.state is not InteractionState.OPEN:
                raise ConversationRuntimeViolation(
                    "INTERACTION_NOT_OPEN",
                    "turn capture requires an open interaction",
                    ErrorCode.CONFLICT,
                )
            turn_id = self._require_id(turn_id, "turn_id")
            if turn_id in self._turns:
                raise ConversationRuntimeViolation(
                    "TURN_ALREADY_EXISTS",
                    "turn identifiers cannot be reused",
                    ErrorCode.CONFLICT,
                )
            self._turns[turn_id] = TurnRecord(
                turn_id, interaction_id, TurnState.CAPTURING
            )
            return self._emit(
                "turn.started",
                interaction_id,
                turn_id=turn_id,
                state=TurnState.CAPTURING.value,
            )

    def commit_turn(self, commit: TurnCommit) -> tuple[bool, RuntimeEvent | None]:
        with self._lock:
            self._require_enabled()
            turn = self._turn(commit.turn_id)
            if (
                commit.scope != self._scope
                or commit.interaction_id != turn.interaction_id
            ):
                raise ConversationRuntimeViolation(
                    "TURN_COMMIT_SCOPE_MISMATCH",
                    "commit must match the exact runtime scope and interaction",
                    ErrorCode.PERMISSION_DENIED,
                )
            if turn.state is TurnState.COMMITTED:
                accepted = self._commit_ledger.accept(commit)
                return accepted, None
            validate_transition(
                LifecycleKind.TURN,
                turn.state.value,
                TurnState.COMMITTED.value,
            )
            accepted = self._commit_ledger.accept(commit)
            if not accepted:
                return False, None
            updated = replace(
                turn, state=TurnState.COMMITTED, commit_id=commit.commit_id
            )
            self._turns[turn.turn_id] = updated
            return True, self._emit(
                "turn.committed",
                turn.interaction_id,
                turn_id=turn.turn_id,
                state=TurnState.COMMITTED.value,
            )

    def commit_native_turn(
        self,
        *,
        turn_id: str,
        interaction_id: str,
        scope: ScopeRef,
        commit_id: str,
    ) -> tuple[bool, RuntimeEvent | None]:
        """Commit one Runtime-validated Native audio turn without forging text."""

        with self._lock:
            self._require_enabled()
            parsed_turn_id = self._require_id(turn_id, "turn_id")
            parsed_interaction_id = self._require_id(
                interaction_id, "interaction_id"
            )
            parsed_commit_id = self._require_id(commit_id, "commit_id")
            turn = self._turn(parsed_turn_id)
            if scope != self._scope or turn.interaction_id != parsed_interaction_id:
                raise ConversationRuntimeViolation(
                    "NATIVE_TURN_COMMIT_SCOPE_MISMATCH",
                    "Native commit must match the exact Runtime scope and interaction",
                    ErrorCode.PERMISSION_DENIED,
                )
            if turn.state is TurnState.COMMITTED:
                if turn.commit_id == parsed_commit_id:
                    return False, None
                raise ConversationRuntimeViolation(
                    "NATIVE_TURN_COMMIT_CONFLICT",
                    "a committed Native turn cannot change its commit identity",
                    ErrorCode.CONFLICT,
                )
            validate_transition(
                LifecycleKind.TURN,
                turn.state.value,
                TurnState.COMMITTED.value,
            )
            updated = replace(
                turn,
                state=TurnState.COMMITTED,
                commit_id=parsed_commit_id,
            )
            self._turns[turn.turn_id] = updated
            return True, self._emit(
                "turn.committed",
                turn.interaction_id,
                turn_id=turn.turn_id,
                state=TurnState.COMMITTED.value,
            )

    def cancel_turn(self, turn_id: str) -> RuntimeEvent:
        with self._lock:
            self._require_enabled()
            turn = self._turn(turn_id)
            validate_transition(
                LifecycleKind.TURN,
                turn.state.value,
                TurnState.CANCELLED.value,
            )
            updated = replace(turn, state=TurnState.CANCELLED)
            self._turns[turn_id] = updated
            return self._emit(
                "turn.cancelled",
                turn.interaction_id,
                turn_id=turn.turn_id,
                state=TurnState.CANCELLED.value,
            )

    def accept_response(
        self,
        turn_id: str,
        response_id: str,
        *,
        response_generation: int | None = None,
        minimum_generation: int = 0,
    ) -> tuple[ResponseRef, RuntimeEvent]:
        with self._lock:
            self._require_enabled()
            if (
                type(minimum_generation) is not int
                or not 0 <= minimum_generation <= MAX_SAFE_INTEGER
            ):
                raise ConversationRuntimeViolation(
                    "INVALID_MINIMUM_RESPONSE_GENERATION",
                    "minimum response generation must be a safe unsigned integer",
                    ErrorCode.INVALID_ARGUMENT,
                )
            turn = self._turn(turn_id)
            if turn.state is not TurnState.COMMITTED:
                raise ConversationRuntimeViolation(
                    "TURN_NOT_COMMITTED",
                    "a response requires an accepted turn commit",
                    ErrorCode.PERMISSION_DENIED,
                )
            if (
                self._interaction(turn.interaction_id).state
                is not InteractionState.OPEN
            ):
                raise ConversationRuntimeViolation(
                    "INTERACTION_NOT_OPEN",
                    "a new response requires an open interaction",
                    ErrorCode.CONFLICT,
                )
            response_id = self._require_id(response_id, "response_id")
            if response_id in self._responses:
                raise ConversationRuntimeViolation(
                    "RESPONSE_ID_REUSED",
                    "response identifiers cannot be reused",
                    ErrorCode.CONFLICT,
                )
            interaction_id = turn.interaction_id
            prior_generation = self._last_generation.get(interaction_id, -1)
            generation = response_generation
            if generation is None:
                generation = (
                    max(minimum_generation, prior_generation + 1)
                    if self._response_generation_owner is None
                    else self._response_generation_owner(
                        interaction_id, prior_generation
                    )
                )
            if (
                type(generation) is not int
                or generation <= prior_generation
                or generation < minimum_generation
                or generation > MAX_SAFE_INTEGER
            ):
                raise ConversationRuntimeViolation(
                    "INVALID_RESPONSE_GENERATION",
                    "response generation owner must return a strictly newer safe integer",
                    ErrorCode.CONFLICT,
                )
            prior_id = self._active_response.get(interaction_id)
            if prior_id is not None:
                prior = self._responses[prior_id]
                self._responses[prior_id] = replace(prior, fenced=True)
            ref = ResponseRef(interaction_id, response_id, generation)
            self._response_fence.begin(ref)
            record = ResponseRecord(ref, turn_id, ResponseState.ACCEPTED)
            self._responses[response_id] = record
            self._active_response[interaction_id] = response_id
            self._last_generation[interaction_id] = generation
            return ref, self._emit(
                "response.accepted",
                interaction_id,
                turn_id=turn_id,
                response=record,
                state=record.state.value,
            )

    def transition_response(
        self,
        ref: ResponseRef,
        target: ResponseState,
        *,
        outcome: TerminalOutcome | None = None,
    ) -> RuntimeEvent:
        with self._lock:
            self._require_enabled()
            record = self._response(ref)
            validate_transition(
                LifecycleKind.RESPONSE,
                record.state.value,
                target.value,
                outcome=outcome,
            )
            updated = replace(record, state=target, outcome=outcome)
            if target is ResponseState.TERMINAL:
                if self._active_response.get(ref.interaction_id) == ref.response_id:
                    self._response_fence.terminal(ref)
                updated = replace(updated, fenced=True)
            self._responses[ref.response_id] = updated
            return self._emit(
                f"response.{target.value}",
                ref.interaction_id,
                turn_id=record.turn_id,
                response=updated,
                state=target.value,
            )

    def request_response_cancel(
        self, ref: ResponseRef
    ) -> tuple[RuntimeEvent, RuntimeEffect]:
        with self._lock:
            self._require_enabled()
            record = self._response(ref)
            if record.state is ResponseState.TERMINAL:
                raise ConversationRuntimeViolation(
                    "RESPONSE_ALREADY_TERMINAL",
                    "a terminal response cannot be cancelled",
                    ErrorCode.CONFLICT,
                )
            if record.cancel_state is not CancelState.NONE:
                raise ConversationRuntimeViolation(
                    "CANCEL_ALREADY_REQUESTED",
                    "response cancellation is once-only",
                    ErrorCode.CONFLICT,
                )
            self._response_fence.cancel(ref)
            updated = replace(record, fenced=True, cancel_state=CancelState.REQUESTED)
            self._responses[ref.response_id] = updated
            event = self._emit(
                "response.cancel_requested",
                ref.interaction_id,
                turn_id=record.turn_id,
                response=updated,
                state=record.state.value,
            )
            effect = RuntimeEffect(
                "response.cancel",
                ref.interaction_id,
                ref.response_id,
                ref.response_generation,
            )
            return event, effect

    def acknowledge_response_cancel(self, ref: ResponseRef) -> RuntimeEvent | None:
        return self._set_cancel_state(ref, CancelState.ACKNOWLEDGED)

    def mark_response_cancel_unknown(self, ref: ResponseRef) -> RuntimeEvent | None:
        return self._set_cancel_state(ref, CancelState.RESULT_UNKNOWN)

    def _set_cancel_state(
        self, ref: ResponseRef, target: CancelState
    ) -> RuntimeEvent | None:
        with self._lock:
            self._require_enabled()
            record = self._response(ref)
            if record.cancel_state is CancelState.NONE:
                raise ConversationRuntimeViolation(
                    "CANCEL_NOT_REQUESTED",
                    "cancel acknowledgement requires a prior exact request",
                    ErrorCode.CONFLICT,
                )
            if record.cancel_state is target:
                return None
            if (
                record.cancel_state is CancelState.ACKNOWLEDGED
                and target is CancelState.RESULT_UNKNOWN
            ):
                return None
            if not (
                record.cancel_state is CancelState.REQUESTED
                or (
                    record.cancel_state is CancelState.RESULT_UNKNOWN
                    and target is CancelState.ACKNOWLEDGED
                )
            ):
                raise ConversationRuntimeViolation(
                    "INVALID_CANCEL_RECONCILIATION",
                    "cancel reconciliation cannot rewrite authoritative acknowledgement",
                    ErrorCode.CONFLICT,
                )
            updated = replace(record, cancel_state=target)
            self._responses[ref.response_id] = updated
            return self._emit(
                f"response.cancel_{target.value}",
                ref.interaction_id,
                turn_id=record.turn_id,
                response=updated,
                state=record.state.value,
            )

    def apply_output(self, ref: ResponseRef, effect_type: str) -> RuntimeEffect:
        with self._lock:
            self._require_enabled()
            effect_type = self._require_id(effect_type, "effect_type")
            if effect_type not in self._OUTPUT_EFFECTS:
                raise ConversationRuntimeViolation(
                    "UNSUPPORTED_OUTPUT_EFFECT",
                    "conversation output may select only UI, history, or audio effects",
                    ErrorCode.UNSUPPORTED,
                )
            self._response(ref)
            return self._response_fence.apply_if_current(
                ref,
                lambda: RuntimeEffect(
                    effect_type,
                    ref.interaction_id,
                    ref.response_id,
                    ref.response_generation,
                ),
            )

    def events(self) -> tuple[RuntimeEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def snapshot(self) -> ConversationSnapshot:
        with self._lock:
            return ConversationSnapshot(
                scope=self._scope,
                interactions=tuple(self._interactions.values()),
                turns=tuple(self._turns.values()),
                responses=tuple(self._responses.values()),
                last_seq=len(self._events),
            )

    def fingerprint(self) -> str:
        snapshot = self.snapshot()
        return canonical_json(
            {
                "scope": snapshot.scope.to_dict(),
                "interactions": [
                    {"id": item.interaction_id, "state": item.state.value}
                    for item in snapshot.interactions
                ],
                "turns": [
                    {
                        "id": item.turn_id,
                        "interaction_id": item.interaction_id,
                        "state": item.state.value,
                        "commit_id": item.commit_id,
                    }
                    for item in snapshot.turns
                ],
                "responses": [
                    {
                        "interaction_id": item.ref.interaction_id,
                        "response_id": item.ref.response_id,
                        "response_generation": item.ref.response_generation,
                        "turn_id": item.turn_id,
                        "state": item.state.value,
                        "fenced": item.fenced,
                        "cancel_state": item.cancel_state.value,
                        "outcome": (
                            None if item.outcome is None else item.outcome.value
                        ),
                    }
                    for item in snapshot.responses
                ],
                "last_seq": snapshot.last_seq,
            }
        )

    def _interaction(self, interaction_id: str) -> InteractionRecord:
        record = self._interactions.get(interaction_id)
        if record is None:
            raise ConversationRuntimeViolation(
                "INTERACTION_NOT_FOUND",
                "interaction does not exist",
                ErrorCode.NOT_FOUND,
            )
        return record

    def _turn(self, turn_id: str) -> TurnRecord:
        record = self._turns.get(turn_id)
        if record is None:
            raise ConversationRuntimeViolation(
                "TURN_NOT_FOUND", "turn does not exist", ErrorCode.NOT_FOUND
            )
        return record

    def _response(self, ref: ResponseRef) -> ResponseRecord:
        record = self._responses.get(ref.response_id)
        if record is None or record.ref != ref:
            raise ConversationRuntimeViolation(
                "STALE_RESPONSE_REFERENCE",
                "response operation requires the exact response tuple",
                ErrorCode.STALE,
            )
        return record
