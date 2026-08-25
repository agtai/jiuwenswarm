# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed JSON carrier values for Gateway-to-AgentServer Native proposals.

The carrier deliberately excludes Provider PCM.  Gateway retains raw audio;
AgentServer receives only authority-free actions, commits, completions and
delegate proposals that still require exact Runtime admission.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    ErrorCode,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.interaction_engine import (
    INTERACTION_ACTION_OPERATIONS,
    InteractionAction,
    InteractionEnginePort,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    MAX_NATIVE_TRANSCRIPT_UTF8_BYTES,
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    NativeEngineEvent,
    NativeProviderDone,
)


_PROPOSAL_KEYS = frozenset(
    {
        "contract_version",
        "binding",
        "action",
        "turn_commit",
        "delegate",
        "provider_done",
    }
)
_ACTION_KEYS = frozenset(
    {"action_id", "operation", "interaction_id", "scope", "payload"}
)
_ACTION_PAYLOAD_KEYS = frozenset({"name", "value"})
_DONE_KEYS = frozenset(
    {
        "provider_event_id",
        "provider_response_id",
        "response",
        "completed",
        "transcript",
        "transcript_event_id",
    }
)
_RESPONSE_KEYS = frozenset({"interaction_id", "response_id", "response_generation"})
_MAX_IDENTITY_CHARS = 256
_MAX_IDENTITY_BYTES = 1_024


class NativeCarrierViolation(ValueError):
    def __init__(
        self,
        reason: str,
        message: str,
        code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


def _closed(
    value: object, keys: frozenset[str], *, reason: str, field: str
) -> Mapping[str, object]:
    if (
        not isinstance(value, Mapping)
        or any(type(key) is not str for key in value)
        or set(value) != keys
    ):
        raise NativeCarrierViolation(
            reason, f"{field} fields must match the closed Native carrier"
        )
    return value


def _identity(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_IDENTITY_CHARS
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in value
        )
    ):
        raise NativeCarrierViolation(
            "NATIVE_CARRIER_IDENTITY_INVALID",
            f"{field} must be a bounded canonical identity",
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = b"x" * (_MAX_IDENTITY_BYTES + 1)
    if len(encoded) > _MAX_IDENTITY_BYTES:
        raise NativeCarrierViolation(
            "NATIVE_CARRIER_IDENTITY_INVALID",
            f"{field} must be a bounded canonical identity",
        )
    return value


def _response_to_dict(response: ResponseRef) -> dict[str, object]:
    return {
        "interaction_id": response.interaction_id,
        "response_id": response.response_id,
        "response_generation": response.response_generation,
    }


def _response_from_dict(value: object) -> ResponseRef:
    data = _closed(
        value,
        _RESPONSE_KEYS,
        reason="NATIVE_RESPONSE_REF_FIELDS_NOT_CLOSED",
        field="response",
    )
    generation = data["response_generation"]
    if type(generation) is not int or not 0 < generation <= MAX_SAFE_INTEGER:
        raise NativeCarrierViolation(
            "NATIVE_RESPONSE_GENERATION_INVALID",
            "response generation must be a positive safe integer",
        )
    return ResponseRef(
        _identity(data["interaction_id"], "response.interaction_id"),
        _identity(data["response_id"], "response.response_id"),
        generation,
    )


def _action_to_dict(action: InteractionAction) -> dict[str, object]:
    return {
        "action_id": action.action_id,
        "operation": action.operation,
        "interaction_id": action.interaction_id,
        "scope": action.scope.to_dict(),
        "payload": [{"name": name, "value": value} for name, value in action.payload],
    }


def _action_from_dict(
    value: object, binding: NativeInteractionBinding
) -> InteractionAction:
    data = _closed(
        value,
        _ACTION_KEYS,
        reason="NATIVE_ACTION_FIELDS_NOT_CLOSED",
        field="action",
    )
    raw_payload = data["payload"]
    if not isinstance(raw_payload, list) or len(raw_payload) > 32:
        raise NativeCarrierViolation(
            "NATIVE_ACTION_PAYLOAD_INVALID", "action payload must be a bounded list"
        )
    payload: list[tuple[str, str]] = []
    names: set[str] = set()
    for item in raw_payload:
        field = _closed(
            item,
            _ACTION_PAYLOAD_KEYS,
            reason="NATIVE_ACTION_PAYLOAD_FIELDS_NOT_CLOSED",
            field="action payload item",
        )
        name = _identity(field["name"], "action.payload.name")
        value_text = _identity(field["value"], "action.payload.value")
        if name in names:
            raise NativeCarrierViolation(
                "NATIVE_ACTION_PAYLOAD_DUPLICATE",
                "action payload names must be unique",
            )
        names.add(name)
        payload.append((name, value_text))
    try:
        scope = ScopeRef.from_dict(data["scope"])
        action = InteractionAction(
            action_id=_identity(data["action_id"], "action.action_id"),
            operation=_identity(data["operation"], "action.operation"),
            interaction_id=_identity(data["interaction_id"], "action.interaction_id"),
            scope=scope,
            payload=tuple(payload),
        )
        InteractionEnginePort(
            INTERACTION_ACTION_OPERATIONS,
            scope=binding.scope,
            max_actions=1,
        ).propose(action)
    except NativeCarrierViolation:
        raise
    except Exception as error:
        raise NativeCarrierViolation(
            "NATIVE_ACTION_INVALID", "action is not canonical"
        ) from error
    if action.interaction_id != binding.interaction_id:
        raise NativeCarrierViolation(
            "NATIVE_PROPOSAL_BINDING_MISMATCH",
            "action must match the exact Native binding",
            ErrorCode.PERMISSION_DENIED,
        )
    return action


def _done_to_dict(done: NativeProviderDone) -> dict[str, object]:
    return {
        "provider_event_id": done.provider_event_id,
        "provider_response_id": done.provider_response_id,
        "response": _response_to_dict(done.response),
        "completed": done.completed,
        "transcript": done.transcript,
        "transcript_event_id": done.transcript_event_id,
    }


def _done_from_dict(value: object) -> NativeProviderDone:
    data = _closed(
        value,
        _DONE_KEYS,
        reason="NATIVE_PROVIDER_DONE_FIELDS_NOT_CLOSED",
        field="provider completion",
    )
    completed = data["completed"]
    transcript = data["transcript"]
    provenance = data["transcript_event_id"]
    if type(completed) is not bool:
        raise NativeCarrierViolation(
            "NATIVE_PROVIDER_DONE_INVALID", "completion state must be boolean"
        )
    if transcript is not None:
        if (
            type(transcript) is not str
            or not transcript
            or transcript != transcript.strip()
        ):
            raise NativeCarrierViolation(
                "NATIVE_TRANSCRIPT_INVALID", "transcript must be canonical text"
            )
        try:
            size = len(transcript.encode("utf-8"))
        except UnicodeEncodeError:
            size = MAX_NATIVE_TRANSCRIPT_UTF8_BYTES + 1
        if size > MAX_NATIVE_TRANSCRIPT_UTF8_BYTES or any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in transcript
        ):
            raise NativeCarrierViolation(
                "NATIVE_TRANSCRIPT_INVALID", "transcript must be bounded text"
            )
    if (transcript is None) != (provenance is None):
        raise NativeCarrierViolation(
            "NATIVE_TRANSCRIPT_PROVENANCE_INVALID",
            "transcript and provenance must be both absent or present",
        )
    return NativeProviderDone(
        provider_event_id=_identity(data["provider_event_id"], "provider_event_id"),
        provider_response_id=_identity(
            data["provider_response_id"], "provider_response_id"
        ),
        response=_response_from_dict(data["response"]),
        completed=completed,
        transcript=transcript,
        transcript_event_id=(
            None if provenance is None else _identity(provenance, "transcript_event_id")
        ),
    )


@dataclass(frozen=True, slots=True)
class NativeInteractionProposal:
    binding: NativeInteractionBinding
    action: InteractionAction | None = None
    turn_commit: NativeTurnCommit | None = None
    delegate: NativeDelegateProposal | None = None
    provider_done: NativeProviderDone | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, NativeInteractionBinding):
            raise NativeCarrierViolation(
                "NATIVE_BINDING_INVALID", "proposal requires a canonical binding"
            )
        if all(
            item is None
            for item in (
                self.action,
                self.turn_commit,
                self.delegate,
                self.provider_done,
            )
        ):
            raise NativeCarrierViolation(
                "NATIVE_PROPOSAL_EMPTY", "proposal requires one Native observation"
            )
        if self.action is not None:
            _action_from_dict(_action_to_dict(self.action), self.binding)
        if self.turn_commit is not None and self.turn_commit.binding != self.binding:
            self._binding_mismatch()
        if self.delegate is not None and self.delegate.binding != self.binding:
            self._binding_mismatch()
        if (
            self.provider_done is not None
            and self.provider_done.response.interaction_id
            != self.binding.interaction_id
        ):
            self._binding_mismatch()

    @staticmethod
    def _binding_mismatch() -> None:
        raise NativeCarrierViolation(
            "NATIVE_PROPOSAL_BINDING_MISMATCH",
            "proposal values must match the exact activation binding",
            ErrorCode.PERMISSION_DENIED,
        )

    @classmethod
    def from_engine_event(
        cls,
        binding: NativeInteractionBinding,
        event: NativeEngineEvent,
    ) -> NativeInteractionProposal:
        if not isinstance(event, NativeEngineEvent):
            raise NativeCarrierViolation(
                "NATIVE_ENGINE_EVENT_INVALID", "event must use NativeEngineEvent"
            )
        if event.audio is not None:
            raise NativeCarrierViolation(
                "NATIVE_RAW_AUDIO_FORBIDDEN",
                "Provider PCM must remain in Gateway-owned media",
                ErrorCode.PERMISSION_DENIED,
            )
        return cls(
            binding=binding,
            action=event.action,
            turn_commit=event.turn_commit,
            delegate=event.delegate,
            provider_done=event.provider_done,
        )

    @classmethod
    def from_dict(cls, value: object) -> NativeInteractionProposal:
        data = _closed(
            value,
            _PROPOSAL_KEYS,
            reason="NATIVE_PROPOSAL_FIELDS_NOT_CLOSED",
            field="Native proposal",
        )
        if data["contract_version"] != NATIVE_INTERACTION_CONTRACT_VERSION:
            raise NativeCarrierViolation(
                "NATIVE_CONTRACT_VERSION_UNSUPPORTED",
                f"expected {NATIVE_INTERACTION_CONTRACT_VERSION}",
                ErrorCode.UNSUPPORTED,
            )
        try:
            binding = NativeInteractionBinding.from_dict(data["binding"])
            action = (
                None
                if data["action"] is None
                else _action_from_dict(data["action"], binding)
            )
            turn = (
                None
                if data["turn_commit"] is None
                else NativeTurnCommit.from_dict(data["turn_commit"])
            )
            delegate = (
                None
                if data["delegate"] is None
                else NativeDelegateProposal.from_dict(data["delegate"])
            )
            done = (
                None
                if data["provider_done"] is None
                else _done_from_dict(data["provider_done"])
            )
            return cls(binding, action, turn, delegate, done)
        except NativeCarrierViolation:
            raise
        except Exception as error:
            reason = getattr(error, "reason", "NATIVE_PROPOSAL_INVALID")
            raise NativeCarrierViolation(
                reason, "Native proposal is invalid"
            ) from error

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
            "binding": self.binding.to_dict(),
            "action": None if self.action is None else _action_to_dict(self.action),
            "turn_commit": (
                None if self.turn_commit is None else self.turn_commit.to_dict()
            ),
            "delegate": None if self.delegate is None else self.delegate.to_dict(),
            "provider_done": (
                None
                if self.provider_done is None
                else _done_to_dict(self.provider_done)
            ),
        }


__all__ = [
    "NativeCarrierViolation",
    "NativeInteractionProposal",
]
