# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Closed, authority-free values for native Live Voice interactions.

The values in this module bind Provider observations to an already authorized
Live Voice activation.  They do not commit the shared text ``TurnCommit`` and
cannot dispatch Agent, Tool, Task, history, presentation, or audio effects.
"""

from __future__ import annotations

import json
import threading
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    MAX_SAFE_INTEGER,
    Assurance,
    ErrorCode,
    ResponseRef,
    ScopeRef,
    canonical_json_bytes,
)


NATIVE_INTERACTION_CONTRACT_VERSION = "live-voice.native-interaction.v1"
MAX_NATIVE_AUDIO_SAMPLE_COUNT = 48_000
MAX_NATIVE_DELEGATE_UTF8_BYTES = 16_384
MAX_NATIVE_TRANSCRIPT_UTF8_BYTES = 65_536
_MAX_IDENTITY_CHARS = 256
_MAX_IDENTITY_UTF8_BYTES = 1_024
_MAX_CONTRACT_LEDGER_CAPACITY = 4_096


class NativeInteractionContractViolation(ValueError):
    def __init__(
        self,
        reason: str,
        message: str,
        code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code


def _closed_mapping(
    value: object, *, keys: frozenset[str], reason: str, field: str
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise NativeInteractionContractViolation(
            reason, f"{field} fields must match the closed contract"
        )
    if any(type(key) is not str for key in value):
        raise NativeInteractionContractViolation(
            reason, f"{field} keys must be strings"
        )
    return value


def _utf8_length(value: str, *, reason: str, field: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise NativeInteractionContractViolation(
            reason, f"{field} must contain valid Unicode"
        ) from None


def _contains_control(value: str) -> bool:
    return any(
        unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
        for character in value
    )


def _identity(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_IDENTITY_CHARS
        or _contains_control(value)
        or _utf8_length(value, reason="NATIVE_IDENTITY_INVALID", field=field)
        > _MAX_IDENTITY_UTF8_BYTES
    ):
        raise NativeInteractionContractViolation(
            "NATIVE_IDENTITY_INVALID",
            f"{field} must be a bounded, trimmed, single-line identity",
        )
    return value


def _cursor(value: object, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise NativeInteractionContractViolation(
            "NATIVE_CURSOR_INVALID",
            f"{field} must be an unsigned safe integer",
        )
    return value


def _positive_generation(value: object, field: str) -> int:
    parsed = _cursor(value, field)
    if parsed == 0:
        raise NativeInteractionContractViolation(
            "NATIVE_GENERATION_INVALID", f"{field} must be positive"
        )
    return parsed


def _scope(value: object) -> ScopeRef:
    try:
        parsed = ScopeRef.from_dict(value)
    except Exception:
        raise NativeInteractionContractViolation(
            "NATIVE_SCOPE_INVALID", "scope must be a canonical ScopeRef"
        ) from None
    for name, identity in (
        ("scope.subject_id", parsed.subject_id),
        ("scope.project_id", parsed.project_id),
        ("scope.session_id", parsed.session_id),
    ):
        if identity is not None:
            _identity(identity, name)
    if parsed.assurance is not Assurance.AUTHENTICATED:
        raise NativeInteractionContractViolation(
            "NATIVE_SCOPE_NOT_AUTHENTICATED",
            "Native interaction scope must be authenticated",
            ErrorCode.PERMISSION_DENIED,
        )
    return parsed


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _optional_transcript(value: object) -> str | None:
    if value is None:
        return None
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _contains_control(value)
        or _utf8_length(
            value, reason="NATIVE_TRANSCRIPT_INVALID", field="audit_transcript"
        )
        > MAX_NATIVE_TRANSCRIPT_UTF8_BYTES
    ):
        raise NativeInteractionContractViolation(
            "NATIVE_TRANSCRIPT_INVALID",
            "audit_transcript must be a bounded, trimmed Unicode string",
        )
    return value


def _delegate_text(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _contains_control(value)
        or _utf8_length(
            value, reason="NATIVE_DELEGATE_REQUEST_INVALID", field="request_text"
        )
        > MAX_NATIVE_DELEGATE_UTF8_BYTES
    ):
        raise NativeInteractionContractViolation(
            "NATIVE_DELEGATE_REQUEST_INVALID",
            "request_text must be bounded, trimmed, and control-free",
        )
    return value


@dataclass(frozen=True, slots=True)
class NativeInteractionBinding:
    scope: ScopeRef
    interaction_id: str
    activation_id: str
    activation_generation: int
    correlation_id: str

    def __post_init__(self) -> None:
        canonical_scope = _scope(
            self.scope.to_dict() if isinstance(self.scope, ScopeRef) else self.scope
        )
        object.__setattr__(self, "scope", canonical_scope)
        _identity(self.interaction_id, "interaction_id")
        _identity(self.activation_id, "activation_id")
        _positive_generation(self.activation_generation, "activation_generation")
        _identity(self.correlation_id, "correlation_id")

    @classmethod
    def from_dict(cls, value: object) -> NativeInteractionBinding:
        data = _closed_mapping(
            value,
            keys=frozenset(
                {
                    "scope",
                    "interaction_id",
                    "activation_id",
                    "activation_generation",
                    "correlation_id",
                }
            ),
            reason="NATIVE_BINDING_FIELDS_NOT_CLOSED",
            field="native binding",
        )
        return cls(
            scope=_scope(data["scope"]),
            interaction_id=_identity(data["interaction_id"], "interaction_id"),
            activation_id=_identity(data["activation_id"], "activation_id"),
            activation_generation=_positive_generation(
                data["activation_generation"], "activation_generation"
            ),
            correlation_id=_identity(data["correlation_id"], "correlation_id"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.to_dict(),
            "interaction_id": self.interaction_id,
            "activation_id": self.activation_id,
            "activation_generation": self.activation_generation,
            "correlation_id": self.correlation_id,
        }


_AUDIO_OBSERVATION_KEYS = frozenset(
    {
        "provider_event_id",
        "provider_response_id",
        "provider_item_id",
        "content_index",
        "sequence",
        "sample_count",
        "content_sha256",
        "response",
    }
)
_RESPONSE_REF_KEYS = frozenset({"interaction_id", "response_id", "response_generation"})


@dataclass(frozen=True, slots=True)
class NativeAudioObservation:
    """Provider audio identity and digest without recoverable audio content."""

    provider_event_id: str
    provider_response_id: str
    provider_item_id: str
    content_index: int
    sequence: int
    sample_count: int
    content_sha256: str
    response: ResponseRef

    def __post_init__(self) -> None:
        _identity(self.provider_event_id, "provider_event_id")
        _identity(self.provider_response_id, "provider_response_id")
        _identity(self.provider_item_id, "provider_item_id")
        _cursor(self.content_index, "content_index")
        _cursor(self.sequence, "sequence")
        if (
            type(self.sample_count) is not int
            or not 0 < self.sample_count <= MAX_NATIVE_AUDIO_SAMPLE_COUNT
        ):
            raise NativeInteractionContractViolation(
                "NATIVE_AUDIO_SAMPLE_COUNT_INVALID",
                "sample_count must describe bounded non-empty PCM16",
            )
        if (
            type(self.content_sha256) is not str
            or len(self.content_sha256) != 64
            or any(
                character not in "0123456789abcdef" for character in self.content_sha256
            )
        ):
            raise NativeInteractionContractViolation(
                "NATIVE_AUDIO_DIGEST_INVALID",
                "content_sha256 must be one lowercase SHA-256 digest",
            )
        if not isinstance(self.response, ResponseRef):
            raise NativeInteractionContractViolation(
                "NATIVE_RESPONSE_REF_INVALID",
                "audio observation requires a canonical ResponseRef",
            )
        _identity(self.response.interaction_id, "response.interaction_id")
        _identity(self.response.response_id, "response.response_id")
        _positive_generation(
            self.response.response_generation, "response.response_generation"
        )

    @classmethod
    def from_dict(cls, value: object) -> NativeAudioObservation:
        data = _closed_mapping(
            value,
            keys=_AUDIO_OBSERVATION_KEYS,
            reason="NATIVE_AUDIO_OBSERVATION_FIELDS_NOT_CLOSED",
            field="native audio observation",
        )
        response = _closed_mapping(
            data["response"],
            keys=_RESPONSE_REF_KEYS,
            reason="NATIVE_RESPONSE_REF_FIELDS_NOT_CLOSED",
            field="native response ref",
        )
        try:
            ref = ResponseRef(
                interaction_id=_identity(
                    response["interaction_id"], "response.interaction_id"
                ),
                response_id=_identity(response["response_id"], "response.response_id"),
                response_generation=_positive_generation(
                    response["response_generation"], "response.response_generation"
                ),
            )
        except NativeInteractionContractViolation:
            raise
        except Exception:
            raise NativeInteractionContractViolation(
                "NATIVE_RESPONSE_REF_INVALID",
                "response must be a canonical ResponseRef",
            ) from None
        return cls(
            provider_event_id=data["provider_event_id"],  # type: ignore[arg-type]
            provider_response_id=data["provider_response_id"],  # type: ignore[arg-type]
            provider_item_id=data["provider_item_id"],  # type: ignore[arg-type]
            content_index=data["content_index"],  # type: ignore[arg-type]
            sequence=data["sequence"],  # type: ignore[arg-type]
            sample_count=data["sample_count"],  # type: ignore[arg-type]
            content_sha256=data["content_sha256"],  # type: ignore[arg-type]
            response=ref,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_event_id": self.provider_event_id,
            "provider_response_id": self.provider_response_id,
            "provider_item_id": self.provider_item_id,
            "content_index": self.content_index,
            "sequence": self.sequence,
            "sample_count": self.sample_count,
            "content_sha256": self.content_sha256,
            "response": {
                "interaction_id": self.response.interaction_id,
                "response_id": self.response.response_id,
                "response_generation": self.response.response_generation,
            },
        }


_COMMIT_KEYS = frozenset(
    {
        "contract_version",
        "commit_id",
        "binding",
        "turn_id",
        "provider_session_id",
        "provider_item_id",
        "provider_event_id",
        "causation_id",
        "input_audio_start_ms",
        "input_audio_end_ms",
        "committed_audio_ms",
        "audit_transcript",
        "audit_transcript_event_id",
    }
)


@dataclass(frozen=True, slots=True)
class NativeTurnCommit:
    contract_version: str
    commit_id: str
    binding: NativeInteractionBinding
    turn_id: str
    provider_session_id: str
    provider_item_id: str
    provider_event_id: str
    causation_id: str
    input_audio_start_ms: int
    input_audio_end_ms: int
    committed_audio_ms: int
    audit_transcript: str | None = None
    audit_transcript_event_id: str | None = None

    def __post_init__(self) -> None:
        if self.contract_version != NATIVE_INTERACTION_CONTRACT_VERSION:
            raise NativeInteractionContractViolation(
                "NATIVE_CONTRACT_VERSION_UNSUPPORTED",
                f"expected {NATIVE_INTERACTION_CONTRACT_VERSION}",
                ErrorCode.UNSUPPORTED,
            )
        if not isinstance(self.binding, NativeInteractionBinding):
            raise NativeInteractionContractViolation(
                "NATIVE_BINDING_INVALID",
                "binding must use NativeInteractionBinding",
            )
        for field, value in (
            ("commit_id", self.commit_id),
            ("turn_id", self.turn_id),
            ("provider_session_id", self.provider_session_id),
            ("provider_item_id", self.provider_item_id),
            ("provider_event_id", self.provider_event_id),
            ("causation_id", self.causation_id),
        ):
            _identity(value, field)
        start = _cursor(self.input_audio_start_ms, "input_audio_start_ms")
        end = _cursor(self.input_audio_end_ms, "input_audio_end_ms")
        committed = _cursor(self.committed_audio_ms, "committed_audio_ms")
        if end <= start or committed == 0 or committed != end - start:
            raise NativeInteractionContractViolation(
                "NATIVE_AUDIO_TIMING_INVALID",
                "committed audio timing must describe one positive exact interval",
            )
        transcript = _optional_transcript(self.audit_transcript)
        transcript_event = self.audit_transcript_event_id
        if (transcript is None) != (transcript_event is None):
            raise NativeInteractionContractViolation(
                "NATIVE_TRANSCRIPT_PROVENANCE_INVALID",
                "audit transcript and its Provider event must be both absent or present",
            )
        if transcript_event is not None:
            _identity(transcript_event, "audit_transcript_event_id")

    @classmethod
    def from_dict(cls, value: object) -> NativeTurnCommit:
        data = _closed_mapping(
            value,
            keys=_COMMIT_KEYS,
            reason="NATIVE_COMMIT_FIELDS_NOT_CLOSED",
            field="native turn commit",
        )
        return cls(
            contract_version=data["contract_version"],  # type: ignore[arg-type]
            commit_id=data["commit_id"],  # type: ignore[arg-type]
            binding=NativeInteractionBinding.from_dict(data["binding"]),
            turn_id=data["turn_id"],  # type: ignore[arg-type]
            provider_session_id=data["provider_session_id"],  # type: ignore[arg-type]
            provider_item_id=data["provider_item_id"],  # type: ignore[arg-type]
            provider_event_id=data["provider_event_id"],  # type: ignore[arg-type]
            causation_id=data["causation_id"],  # type: ignore[arg-type]
            input_audio_start_ms=data["input_audio_start_ms"],  # type: ignore[arg-type]
            input_audio_end_ms=data["input_audio_end_ms"],  # type: ignore[arg-type]
            committed_audio_ms=data["committed_audio_ms"],  # type: ignore[arg-type]
            audit_transcript=data["audit_transcript"],  # type: ignore[arg-type]
            audit_transcript_event_id=data["audit_transcript_event_id"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "commit_id": self.commit_id,
            "binding": self.binding.to_dict(),
            "turn_id": self.turn_id,
            "provider_session_id": self.provider_session_id,
            "provider_item_id": self.provider_item_id,
            "provider_event_id": self.provider_event_id,
            "causation_id": self.causation_id,
            "input_audio_start_ms": self.input_audio_start_ms,
            "input_audio_end_ms": self.input_audio_end_ms,
            "committed_audio_ms": self.committed_audio_ms,
            "audit_transcript": self.audit_transcript,
            "audit_transcript_event_id": self.audit_transcript_event_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


_DELEGATE_KEYS = frozenset(
    {
        "contract_version",
        "binding",
        "turn_id",
        "response_generation",
        "provider_event_id",
        "provider_call_id",
        "provider_item_id",
        "request_text",
    }
)


@dataclass(frozen=True, slots=True)
class NativeDelegateProposal:
    binding: NativeInteractionBinding
    turn_id: str
    response_generation: int
    provider_event_id: str
    provider_call_id: str
    provider_item_id: str
    request_text: str
    contract_version: str = NATIVE_INTERACTION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != NATIVE_INTERACTION_CONTRACT_VERSION:
            raise NativeInteractionContractViolation(
                "NATIVE_CONTRACT_VERSION_UNSUPPORTED",
                f"expected {NATIVE_INTERACTION_CONTRACT_VERSION}",
                ErrorCode.UNSUPPORTED,
            )
        if not isinstance(self.binding, NativeInteractionBinding):
            raise NativeInteractionContractViolation(
                "NATIVE_BINDING_INVALID",
                "binding must use NativeInteractionBinding",
            )
        _identity(self.turn_id, "turn_id")
        _positive_generation(self.response_generation, "response_generation")
        _identity(self.provider_event_id, "provider_event_id")
        _identity(self.provider_call_id, "provider_call_id")
        _identity(self.provider_item_id, "provider_item_id")
        _delegate_text(self.request_text)

    @classmethod
    def from_dict(cls, value: object) -> NativeDelegateProposal:
        data = _closed_mapping(
            value,
            keys=_DELEGATE_KEYS,
            reason="NATIVE_DELEGATE_FIELDS_NOT_CLOSED",
            field="native delegate proposal",
        )
        return cls(
            contract_version=data["contract_version"],  # type: ignore[arg-type]
            binding=NativeInteractionBinding.from_dict(data["binding"]),
            turn_id=data["turn_id"],  # type: ignore[arg-type]
            response_generation=data["response_generation"],  # type: ignore[arg-type]
            provider_event_id=data["provider_event_id"],  # type: ignore[arg-type]
            provider_call_id=data["provider_call_id"],  # type: ignore[arg-type]
            provider_item_id=data["provider_item_id"],  # type: ignore[arg-type]
            request_text=data["request_text"],  # type: ignore[arg-type]
        )

    @classmethod
    def from_function_call(
        cls,
        *,
        binding: NativeInteractionBinding,
        turn_id: str,
        response_generation: int,
        provider_event_id: str,
        provider_call_id: str,
        provider_item_id: str,
        arguments: object,
    ) -> NativeDelegateProposal:
        if type(arguments) is not str or len(arguments) > 65_536:
            raise NativeInteractionContractViolation(
                "NATIVE_DELEGATE_ARGUMENTS_INVALID",
                "function arguments must be bounded JSON text",
            )
        try:
            decoded = json.loads(arguments, object_pairs_hook=_unique_json_object)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise NativeInteractionContractViolation(
                "NATIVE_DELEGATE_ARGUMENTS_INVALID",
                "function arguments must be valid JSON",
            ) from None
        data = _closed_mapping(
            decoded,
            keys=frozenset({"request_text"}),
            reason="NATIVE_DELEGATE_ARGUMENTS_NOT_CLOSED",
            field="jiuwen_delegate arguments",
        )
        return cls(
            binding=binding,
            turn_id=turn_id,
            response_generation=response_generation,
            provider_event_id=provider_event_id,
            provider_call_id=provider_call_id,
            provider_item_id=provider_item_id,
            request_text=_delegate_text(data["request_text"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "binding": self.binding.to_dict(),
            "turn_id": self.turn_id,
            "response_generation": self.response_generation,
            "provider_event_id": self.provider_event_id,
            "provider_call_id": self.provider_call_id,
            "provider_item_id": self.provider_item_id,
            "request_text": self.request_text,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class NativePresentationCursor:
    response: ResponseRef
    provider_item_id: str
    content_index: int
    audio_end_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.response, ResponseRef):
            raise NativeInteractionContractViolation(
                "NATIVE_RESPONSE_REF_INVALID",
                "presentation cursor requires a canonical ResponseRef",
            )
        _identity(self.response.interaction_id, "response.interaction_id")
        _identity(self.response.response_id, "response.response_id")
        _positive_generation(
            self.response.response_generation, "response.response_generation"
        )
        _identity(self.provider_item_id, "provider_item_id")
        _cursor(self.content_index, "content_index")
        _cursor(self.audio_end_ms, "audio_end_ms")

    @classmethod
    def from_dict(cls, value: object) -> NativePresentationCursor:
        data = _closed_mapping(
            value,
            keys=frozenset(
                {"response", "provider_item_id", "content_index", "audio_end_ms"}
            ),
            reason="NATIVE_PRESENTATION_CURSOR_FIELDS_NOT_CLOSED",
            field="native presentation cursor",
        )
        response = _closed_mapping(
            data["response"],
            keys=frozenset({"interaction_id", "response_id", "response_generation"}),
            reason="NATIVE_RESPONSE_REF_FIELDS_NOT_CLOSED",
            field="native response ref",
        )
        try:
            ref = ResponseRef(
                interaction_id=_identity(
                    response["interaction_id"], "response.interaction_id"
                ),
                response_id=_identity(response["response_id"], "response.response_id"),
                response_generation=_positive_generation(
                    response["response_generation"], "response.response_generation"
                ),
            )
        except NativeInteractionContractViolation:
            raise
        except Exception:
            raise NativeInteractionContractViolation(
                "NATIVE_RESPONSE_REF_INVALID",
                "response must be a canonical ResponseRef",
            ) from None
        return cls(
            response=ref,
            provider_item_id=_identity(data["provider_item_id"], "provider_item_id"),
            content_index=_cursor(data["content_index"], "content_index"),
            audio_end_ms=_cursor(data["audio_end_ms"], "audio_end_ms"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "response": {
                "interaction_id": self.response.interaction_id,
                "response_id": self.response.response_id,
                "response_generation": self.response.response_generation,
            },
            "provider_item_id": self.provider_item_id,
            "content_index": self.content_index,
            "audio_end_ms": self.audio_end_ms,
        }


class NativeContractLedger:
    """Bounded replay/conflict fence for authority-free Native values."""

    def __init__(self, *, capacity: int = 256) -> None:
        if (
            type(capacity) is not int
            or not 0 < capacity <= _MAX_CONTRACT_LEDGER_CAPACITY
        ):
            raise NativeInteractionContractViolation(
                "NATIVE_CONTRACT_LEDGER_CAPACITY_INVALID",
                "ledger capacity must be a bounded positive integer",
            )
        self._capacity = capacity
        self._lock = threading.RLock()
        self._values: dict[str, NativeTurnCommit | NativeDelegateProposal] = {}

    @property
    def accepted_count(self) -> int:
        with self._lock:
            return len(self._values)

    def accept_commit(self, value: NativeTurnCommit) -> tuple[bool, NativeTurnCommit]:
        if not isinstance(value, NativeTurnCommit):
            raise NativeInteractionContractViolation(
                "NATIVE_COMMIT_INVALID", "commit must use NativeTurnCommit"
            )
        key = f"commit:{value.commit_id}"
        accepted, retained = self._accept(
            key,
            value,
            conflict_reason="NATIVE_COMMIT_ID_CONFLICT",
        )
        assert isinstance(retained, NativeTurnCommit)
        return accepted, retained

    def accept_delegate(
        self, value: NativeDelegateProposal
    ) -> tuple[bool, NativeDelegateProposal]:
        if not isinstance(value, NativeDelegateProposal):
            raise NativeInteractionContractViolation(
                "NATIVE_DELEGATE_INVALID",
                "delegate must use NativeDelegateProposal",
            )
        key = f"delegate:{value.provider_call_id}"
        accepted, retained = self._accept(
            key,
            value,
            conflict_reason="NATIVE_DELEGATE_CALL_ID_CONFLICT",
        )
        assert isinstance(retained, NativeDelegateProposal)
        return accepted, retained

    def _accept(
        self,
        key: str,
        value: NativeTurnCommit | NativeDelegateProposal,
        *,
        conflict_reason: str,
    ) -> tuple[bool, NativeTurnCommit | NativeDelegateProposal]:
        with self._lock:
            existing = self._values.get(key)
            if existing is not None:
                if existing == value:
                    return False, existing
                raise NativeInteractionContractViolation(
                    conflict_reason,
                    "a retained Native identity cannot change its meaning",
                    ErrorCode.CONFLICT,
                )
            if len(self._values) >= self._capacity:
                raise NativeInteractionContractViolation(
                    "NATIVE_CONTRACT_LEDGER_FULL",
                    "bounded Native contract ledger is full",
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                )
            self._values[key] = value
            return True, value


__all__ = [
    "MAX_NATIVE_AUDIO_SAMPLE_COUNT",
    "MAX_NATIVE_DELEGATE_UTF8_BYTES",
    "NATIVE_INTERACTION_CONTRACT_VERSION",
    "NativeContractLedger",
    "NativeAudioObservation",
    "NativeDelegateProposal",
    "NativeInteractionBinding",
    "NativeInteractionContractViolation",
    "NativePresentationCursor",
    "NativeTurnCommit",
]
