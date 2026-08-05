# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure critical-kernel primitives for ``live-voice.contract.v2``."""

from __future__ import annotations

import json
import math
import re
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Generic, TypeAlias, TypeVar


CONTRACT_VERSION: Final = "live-voice.contract.v2"
V1_CONTRACT_VERSION: Final = "live-voice.contract.v1"
MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNSUPPORTED = "UNSUPPORTED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    INTERNAL = "INTERNAL"


class Assurance(StrEnum):
    REQUEST_ASSERTED = "request_asserted"
    AUTHENTICATED = "authenticated"


class IdentityKind(StrEnum):
    CONNECTION = "connection"
    MEDIA_SESSION = "media_session"
    TRACK = "track"
    INTERACTION = "interaction"
    TURN = "turn"
    RESPONSE = "response"
    ROUND = "round"
    TASK = "task"
    ATTEMPT = "attempt"
    COMMAND = "command"
    REQUEST = "request"
    EVENT = "event"


class CancelScope(StrEnum):
    PLAYBACK_STOP = "playback.stop"
    RESPONSE_CANCEL = "response.cancel"
    ROUND_CANCEL = "round.cancel"
    TASK_CANCEL = "task.cancel"


class InputCommitState(StrEnum):
    PARTIAL = "partial"
    UNCOMMITTED = "uncommitted"
    COMMITTED = "committed"


class SideEffectTarget(StrEnum):
    AGENT = "agent"
    TOOL = "tool"
    TASK = "task"


class LifecycleKind(StrEnum):
    INTERACTION = "interaction"
    TURN = "turn"
    RESPONSE = "response"
    ROUND = "round"
    TASK = "task"
    ATTEMPT = "attempt"


class TerminalOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Knowledge(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class ContextRevisionKind(StrEnum):
    VERSION = "version"
    SNAPSHOT = "snapshot"
    UNVERSIONED = "unversioned"


class WorkState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    BLOCKED = "blocked"
    DECISION_REQUIRED = "decision_required"
    TERMINAL = "terminal"


class WorkSourceAuthority(StrEnum):
    HARNESS = "harness"
    TASK_CORE = "task_core"
    EXECUTOR = "executor"


class WorkUrgency(StrEnum):
    NORMAL = "normal"
    ATTENTION = "attention"
    URGENT = "urgent"
    UNKNOWN = "unknown"


class Speakability(StrEnum):
    NOT_SPEAKABLE = "not_speakable"
    ELIGIBLE = "eligible"
    ATTENTION_REQUESTED = "attention_requested"


class EventApplyStatus(StrEnum):
    APPLIED = "applied"
    DUPLICATE_APPLIED = "duplicate_applied"
    QUARANTINED_GAP = "quarantined_gap"
    QUARANTINED_CAUSATION = "quarantined_causation"
    QUARANTINED_PROJECTION = "quarantined_projection"
    DUPLICATE_QUARANTINED = "duplicate_quarantined"
    REJECTED_CONFLICT = "rejected_conflict"
    REJECTED_CAUSATION = "rejected_causation"
    REJECTED_PROJECTION = "rejected_projection"
    REJECTED_LIFECYCLE = "rejected_lifecycle"


@dataclass(frozen=True, slots=True)
class _FrozenObject:
    items: tuple[tuple[str, FrozenJson], ...]


@dataclass(frozen=True, slots=True)
class _FrozenArray:
    items: tuple[FrozenJson, ...]


FrozenJson: TypeAlias = None | bool | int | float | str | _FrozenObject | _FrozenArray


@dataclass(frozen=True, slots=True)
class ContractError:
    code: ErrorCode
    reason: str | None
    message: str
    retriable: bool
    correlation_id: str | None
    _details: _FrozenObject = field(repr=False)

    @property
    def details(self) -> dict[str, object]:
        return _thaw_object(self._details)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "reason": self.reason,
            "message": self.message,
            "retriable": self.retriable,
            "correlation_id": self.correlation_id,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ContractError:
        data = _strict_object(payload, field_name="error")
        _require_exact_keys(
            data,
            required={
                "code",
                "reason",
                "message",
                "retriable",
                "correlation_id",
                "details",
            },
            field_name="error",
        )
        return cls(
            code=_enum(ErrorCode, data["code"], "error.code"),
            reason=_optional_stable_reason(data["reason"], "error.reason"),
            message=_required_text(data["message"], "error.message"),
            retriable=_bool(data["retriable"], "error.retriable"),
            correlation_id=_optional_id(data["correlation_id"], "error.correlation_id"),
            _details=_freeze_object(data["details"], "error.details"),
        )


class ContractViolation(ValueError):
    def __init__(
        self,
        code: ErrorCode,
        reason: str,
        message: str,
        *,
        correlation_id: str | None = None,
        details: Mapping[str, object] | None = None,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error = ContractError(
            code=code,
            reason=reason,
            message=message,
            retriable=retriable,
            correlation_id=correlation_id,
            _details=_freeze_object(dict(details or {}), "error.details"),
        )

    @property
    def code(self) -> ErrorCode:
        return self.error.code

    @property
    def reason(self) -> str:
        assert self.error.reason is not None
        return self.error.reason


_EnumT = TypeVar("_EnumT", bound=StrEnum)
_ValueT = TypeVar("_ValueT")
_FactT = TypeVar("_FactT")
_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)+$")
_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_CONTEXT_WHITESPACE: Final = frozenset(
    {
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
        0xFEFF,
    }
)


def _violation(
    reason: str,
    message: str,
    *,
    code: ErrorCode = ErrorCode.INVALID_ARGUMENT,
    details: Mapping[str, object] | None = None,
) -> ContractViolation:
    return ContractViolation(code, reason, message, details=details)


def _validate_unicode(value: str, field_name: str) -> str:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise _violation(
            "INVALID_UNICODE_SCALAR",
            f"{field_name} contains an unpaired surrogate",
        )
    return value


def _required_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise _violation(
            "INVALID_REQUIRED_TEXT", f"{field_name} must be a non-empty string"
        )
    return _validate_unicode(value, field_name)


def _context_required_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise _violation(
            "INVALID_REQUIRED_TEXT", f"{field_name} must be a non-empty string"
        )
    normalized = _validate_unicode(value, field_name)
    if not any(
        ord(char) > 0x20
        and not 0x7F <= ord(char) <= 0x9F
        and ord(char) not in _CONTEXT_WHITESPACE
        for char in normalized
    ):
        raise _violation(
            "INVALID_REQUIRED_TEXT", f"{field_name} must be a non-empty string"
        )
    return normalized


def _context_uri(value: object) -> str:
    uri = _context_required_text(value, "context_ref.uri")
    scheme = _URI_SCHEME_RE.match(uri)
    if (
        scheme is None
        or scheme.end() == len(uri)
        or any(
            ord(char) <= 0x20
            or 0x7F <= ord(char) <= 0x9F
            or ord(char) in _CONTEXT_WHITESPACE
            for char in uri
        )
    ):
        raise _violation(
            "INVALID_CONTEXT_URI",
            "context_ref.uri must be a non-empty absolute URI without whitespace or controls",
        )
    return uri


def _optional_id(value: object, field_name: str) -> str | None:
    return None if value is None else _required_text(value, field_name)


def _optional_stable_reason(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    reason = _required_text(value, field_name)
    if not _REASON_RE.fullmatch(reason):
        raise _violation(
            "INVALID_ERROR_REASON",
            f"{field_name} must use stable UPPER_SNAKE_CASE",
        )
    return reason


def _enum(enum_type: type[_EnumT], value: object, field_name: str) -> _EnumT:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise _violation("INVALID_ENUM", f"{field_name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise _violation("INVALID_ENUM", f"unknown {field_name} {value!r}") from exc


def _bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise _violation("INVALID_BOOLEAN", f"{field_name} must be a boolean")
    return value


def _uint(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0 or value > MAX_SAFE_INTEGER:
        raise _violation(
            "INVALID_SAFE_INTEGER",
            f"{field_name} must be an integer between 0 and {MAX_SAFE_INTEGER}",
        )
    return value


def _timestamp(value: object, field_name: str) -> str:
    text = _required_text(value, field_name)
    if not _UTC_RE.fullmatch(text):
        raise _violation(
            "INVALID_UTC_TIMESTAMP", f"{field_name} must be an RFC3339 UTC timestamp"
        )
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise _violation(
            "INVALID_UTC_TIMESTAMP", f"{field_name} must be an RFC3339 UTC timestamp"
        ) from exc
    return text


def _namespaced(value: object, field_name: str) -> str:
    text = _required_text(value, field_name)
    if not _NAMESPACE_RE.fullmatch(text):
        raise _violation(
            "INVALID_NAMESPACED_VALUE",
            f"{field_name} must be a lower-case namespaced string",
        )
    return text


def _strict_object(value: object, *, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _violation(
            "INVALID_JSON_OBJECT", f"{field_name} must be a plain JSON object"
        )
    for key in value:
        if type(key) is not str:
            raise _violation("INVALID_JSON_KEY", f"{field_name} keys must be strings")
        _validate_unicode(key, f"{field_name} key")
    return value


def _strict_array(value: object, *, field_name: str) -> list[object]:
    if type(value) is not list:
        raise _violation("INVALID_JSON_ARRAY", f"{field_name} must be a JSON array")
    return value


def _require_exact_keys(
    data: Mapping[str, object],
    *,
    required: set[str],
    field_name: str,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    keys = set(data)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing:
        raise _violation(
            "MISSING_REQUIRED_FIELD",
            f"{field_name} is missing: {', '.join(missing)}",
        )
    if unknown:
        raise _violation(
            "UNKNOWN_FIELD", f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _freeze_json(
    value: object,
    field_name: str,
    active: set[int] | None = None,
) -> FrozenJson:
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        return _validate_unicode(value, field_name)
    if type(value) is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise _violation(
                "INVALID_SAFE_INTEGER",
                f"{field_name} integer exceeds the cross-language safe range",
            )
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _violation("NON_FINITE_NUMBER", f"{field_name} must be finite")
        if value.is_integer() and abs(value) > MAX_SAFE_INTEGER:
            raise _violation(
                "INVALID_SAFE_INTEGER",
                f"{field_name} integer exceeds the cross-language safe range",
            )
        return value
    if type(value) not in {dict, list}:
        raise _violation(
            "INVALID_JSON_VALUE",
            f"{field_name} contains non-JSON value {type(value).__name__}",
        )

    active = set() if active is None else active
    identity = id(value)
    if identity in active:
        raise _violation("CYCLIC_JSON", f"{field_name} contains a cycle")
    active.add(identity)
    try:
        if type(value) is list:
            return _FrozenArray(
                tuple(
                    _freeze_json(item, f"{field_name}[{index}]", active)
                    for index, item in enumerate(value)
                )
            )
        data = _strict_object(value, field_name=field_name)
        return _FrozenObject(
            tuple(
                sorted(
                    (
                        (key, _freeze_json(item, f"{field_name}.{key}", active))
                        for key, item in data.items()
                    ),
                    key=lambda item: item[0].encode("utf-16-be"),
                )
            )
        )
    finally:
        active.remove(identity)


def _freeze_object(value: object, field_name: str) -> _FrozenObject:
    frozen = _freeze_json(value, field_name)
    if not isinstance(frozen, _FrozenObject):
        raise _violation("INVALID_JSON_OBJECT", f"{field_name} must be an object")
    return frozen


def _thaw_json(value: FrozenJson) -> object:
    if isinstance(value, _FrozenObject):
        return {key: _thaw_json(item) for key, item in value.items}
    if isinstance(value, _FrozenArray):
        return [_thaw_json(item) for item in value.items]
    return value


def _thaw_object(value: _FrozenObject) -> dict[str, object]:
    thawed = _thaw_json(value)
    assert isinstance(thawed, dict)
    return thawed


def _canonical_number(value: int | float) -> str:
    if type(value) is int:
        return str(value)
    if value == 0:
        return "0"
    text = repr(value).lower()
    if "e" not in text:
        return text[:-2] if text.endswith(".0") else text
    mantissa, exponent_text = text.split("e")
    exponent = int(exponent_text)
    sign = ""
    if mantissa.startswith("-"):
        sign, mantissa = "-", mantissa[1:]
    digits = mantissa.replace(".", "")
    decimal_position = 1 + exponent
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        if decimal_position <= 0:
            return sign + "0." + "0" * (-decimal_position) + digits
        if decimal_position >= len(digits):
            return sign + digits + "0" * (decimal_position - len(digits))
        return sign + digits[:decimal_position] + "." + digits[decimal_position:]
    normalized = digits[0]
    if len(digits) > 1:
        normalized += "." + digits[1:].rstrip("0")
        normalized = normalized.rstrip(".")
    exponent_sign = "+" if exponent >= 0 else ""
    return f"{sign}{normalized}e{exponent_sign}{exponent}"


def _canonical_frozen(value: FrozenJson) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _canonical_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, _FrozenArray):
        return "[" + ",".join(_canonical_frozen(item) for item in value.items) + "]"
    assert isinstance(value, _FrozenObject)
    return (
        "{"
        + ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + _canonical_frozen(item)
            for key, item in value.items
        )
        + "}"
    )


def canonical_json(value: object) -> str:
    return _canonical_frozen(_freeze_json(value, "$"))


def canonical_json_bytes(value: object) -> bytes:
    return canonical_json(value).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ScopeRef:
    subject_id: str
    project_id: str | None
    session_id: str | None
    assurance: Assurance

    @classmethod
    def from_dict(cls, payload: object) -> ScopeRef:
        data = _strict_object(payload, field_name="scope")
        _require_exact_keys(
            data,
            required={"subject_id", "project_id", "session_id", "assurance"},
            field_name="scope",
        )
        return cls(
            subject_id=_required_text(data["subject_id"], "scope.subject_id"),
            project_id=_optional_id(data["project_id"], "scope.project_id"),
            session_id=_optional_id(data["session_id"], "scope.session_id"),
            assurance=_enum(Assurance, data["assurance"], "scope.assurance"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "assurance": self.assurance.value,
        }


@dataclass(frozen=True, slots=True)
class ContextRevision:
    kind: ContextRevisionKind
    value: str | None

    @classmethod
    def from_dict(cls, payload: object) -> ContextRevision:
        data = _strict_object(payload, field_name="context_ref.revision")
        kind = _enum(
            ContextRevisionKind,
            data.get("kind"),
            "context_ref.revision.kind",
        )
        required = (
            {"kind"}
            if kind is ContextRevisionKind.UNVERSIONED
            else {
                "kind",
                "value",
            }
        )
        _require_exact_keys(
            data,
            required=required,
            field_name="context_ref.revision",
        )
        return cls(
            kind=kind,
            value=(
                None
                if kind is ContextRevisionKind.UNVERSIONED
                else _context_required_text(data["value"], "context_ref.revision.value")
            ),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind.value}
        if self.value is not None:
            result["value"] = self.value
        return result


@dataclass(frozen=True, slots=True)
class ContextRedaction:
    policy_id: str
    redacted: bool
    fields: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: object) -> ContextRedaction:
        data = _strict_object(payload, field_name="context_ref.redaction")
        _require_exact_keys(
            data,
            required={"policy_id", "redacted", "fields"},
            field_name="context_ref.redaction",
        )
        fields: list[str] = []
        for index, item in enumerate(
            _strict_array(data["fields"], field_name="context_ref.redaction.fields")
        ):
            fields.append(
                _context_required_text(item, f"context_ref.redaction.fields[{index}]")
            )
        return cls(
            policy_id=_context_required_text(
                data["policy_id"], "context_ref.redaction.policy_id"
            ),
            redacted=_bool(data["redacted"], "context_ref.redaction.redacted"),
            fields=tuple(fields),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "redacted": self.redacted,
            "fields": list(self.fields),
        }


@dataclass(frozen=True, slots=True)
class ContextRef:
    source: str
    stable_id: str
    uri: str
    revision: ContextRevision
    scope: ScopeRef
    permissions: tuple[str, ...]
    expires_at: str | None
    redaction: ContextRedaction
    _extensions: _FrozenObject = field(repr=False)

    @property
    def extensions(self) -> dict[str, object]:
        return _thaw_object(self._extensions)

    @classmethod
    def from_dict(cls, payload: object) -> ContextRef:
        data = _strict_object(payload, field_name="context_ref")
        _require_exact_keys(
            data,
            required={
                "source",
                "stable_id",
                "uri",
                "revision",
                "scope",
                "permissions",
                "expires_at",
                "redaction",
                "extensions",
            },
            field_name="context_ref",
        )
        uri = _context_uri(data["uri"])
        permissions: list[str] = []
        for index, item in enumerate(
            _strict_array(data["permissions"], field_name="context_ref.permissions")
        ):
            permissions.append(_namespaced(item, f"context_ref.permissions[{index}]"))
        expires_at = data["expires_at"]
        return cls(
            source=_namespaced(data["source"], "context_ref.source"),
            stable_id=_context_required_text(
                data["stable_id"], "context_ref.stable_id"
            ),
            uri=uri,
            revision=ContextRevision.from_dict(data["revision"]),
            scope=ScopeRef.from_dict(data["scope"]),
            permissions=tuple(permissions),
            expires_at=(
                None
                if expires_at is None
                else _timestamp(expires_at, "context_ref.expires_at")
            ),
            redaction=ContextRedaction.from_dict(data["redaction"]),
            _extensions=_extensions(data["extensions"], "context_ref.extensions"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "stable_id": self.stable_id,
            "uri": self.uri,
            "revision": self.revision.to_dict(),
            "scope": self.scope.to_dict(),
            "permissions": list(self.permissions),
            "expires_at": self.expires_at,
            "redaction": self.redaction.to_dict(),
            "extensions": self.extensions,
        }


@dataclass(frozen=True, slots=True)
class IdentityRef:
    kind: IdentityKind
    id: str

    @classmethod
    def from_dict(
        cls, payload: object, *, expected_kind: IdentityKind | None = None
    ) -> IdentityRef:
        data = _strict_object(payload, field_name="identity_ref")
        _require_exact_keys(data, required={"kind", "id"}, field_name="identity_ref")
        ref = cls(
            kind=_enum(IdentityKind, data["kind"], "identity_ref.kind"),
            id=_required_text(data["id"], "identity_ref.id"),
        )
        if expected_kind is not None and ref.kind is not expected_kind:
            raise _violation(
                "IDENTITY_KIND_MISMATCH",
                f"expected {expected_kind.value}, got {ref.kind.value}",
            )
        return ref

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "id": self.id}


@dataclass(frozen=True, slots=True)
class ConnectionEpochRef:
    connection_id: str
    connection_epoch: int

    @classmethod
    def from_dict(cls, payload: object) -> ConnectionEpochRef:
        data = _strict_object(payload, field_name="connection_epoch_ref")
        _require_exact_keys(
            data,
            required={"connection_id", "connection_epoch"},
            field_name="connection_epoch_ref",
        )
        return cls(
            connection_id=_required_text(
                data["connection_id"], "connection_epoch_ref.connection_id"
            ),
            connection_epoch=_uint(
                data["connection_epoch"], "connection_epoch_ref.connection_epoch"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "connection_id": self.connection_id,
            "connection_epoch": self.connection_epoch,
        }


@dataclass(frozen=True, slots=True)
class OriginRef:
    kind: str
    turn_id: str | None
    commit_id: str | None

    @classmethod
    def from_dict(cls, payload: object) -> OriginRef:
        data = _strict_object(payload, field_name="origin")
        _require_exact_keys(
            data, required={"kind", "turn_id", "commit_id"}, field_name="origin"
        )
        kind = data["kind"]
        if kind not in {"structured", "committed_turn"}:
            raise _violation("INVALID_ORIGIN", f"unknown origin.kind {kind!r}")
        turn_id = _optional_id(data["turn_id"], "origin.turn_id")
        commit_id = _optional_id(data["commit_id"], "origin.commit_id")
        if kind == "structured" and (turn_id is not None or commit_id is not None):
            raise _violation(
                "INVALID_ORIGIN", "structured origin forbids turn_id and commit_id"
            )
        if kind == "committed_turn" and (turn_id is None or commit_id is None):
            raise _violation(
                "INVALID_ORIGIN", "committed_turn origin requires turn_id and commit_id"
            )
        return cls(kind=kind, turn_id=turn_id, commit_id=commit_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "turn_id": self.turn_id,
            "commit_id": self.commit_id,
        }


@dataclass(frozen=True, slots=True)
class ProducerRef:
    component: str
    instance_id: str
    authority: str

    @classmethod
    def from_dict(cls, payload: object) -> ProducerRef:
        data = _strict_object(payload, field_name="producer")
        _require_exact_keys(
            data,
            required={"component", "instance_id", "authority"},
            field_name="producer",
        )
        return cls(
            component=_required_text(data["component"], "producer.component"),
            instance_id=_required_text(data["instance_id"], "producer.instance_id"),
            authority=_required_text(data["authority"], "producer.authority"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "component": self.component,
            "instance_id": self.instance_id,
            "authority": self.authority,
        }


_EXPECTED_PARENT_KINDS: Final = MappingProxyType(
    {
        IdentityKind.CONNECTION: frozenset(),
        IdentityKind.MEDIA_SESSION: frozenset({IdentityKind.INTERACTION}),
        IdentityKind.TRACK: frozenset({IdentityKind.MEDIA_SESSION}),
        IdentityKind.INTERACTION: frozenset(),
        IdentityKind.TURN: frozenset({IdentityKind.INTERACTION}),
        IdentityKind.RESPONSE: frozenset({IdentityKind.INTERACTION, IdentityKind.TURN}),
        IdentityKind.ROUND: frozenset(),
        IdentityKind.TASK: frozenset(),
        IdentityKind.ATTEMPT: frozenset({IdentityKind.TASK}),
        IdentityKind.COMMAND: frozenset(),
        IdentityKind.REQUEST: frozenset(),
        IdentityKind.EVENT: frozenset(),
    }
)


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    ref: IdentityRef
    scope: ScopeRef
    parents: tuple[IdentityRef, ...] = ()
    connection_epoch_ref: ConnectionEpochRef | None = None


class IdentityRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[tuple[IdentityKind, str], IdentityRecord] = {}
        self._kind_by_id: dict[str, IdentityKind] = {}

    def register(self, record: IdentityRecord) -> IdentityRecord:
        connection_epoch_ref = record.connection_epoch_ref
        if connection_epoch_ref is not None:
            if not isinstance(connection_epoch_ref, ConnectionEpochRef):
                raise _violation(
                    "INVALID_CONNECTION_EPOCH_BINDING",
                    "identity_record.connection_epoch_ref must be a ConnectionEpochRef",
                )
            connection_epoch_ref = ConnectionEpochRef(
                connection_id=_required_text(
                    connection_epoch_ref.connection_id,
                    "identity_record.connection_epoch_ref.connection_id",
                ),
                connection_epoch=_uint(
                    connection_epoch_ref.connection_epoch,
                    "identity_record.connection_epoch_ref.connection_epoch",
                ),
            )
        record = IdentityRecord(
            ref=IdentityRef(
                kind=_enum(IdentityKind, record.ref.kind, "identity_record.ref.kind"),
                id=_required_text(record.ref.id, "identity_record.ref.id"),
            ),
            scope=ScopeRef(
                subject_id=_required_text(
                    record.scope.subject_id, "identity_record.scope.subject_id"
                ),
                project_id=_optional_id(
                    record.scope.project_id, "identity_record.scope.project_id"
                ),
                session_id=_optional_id(
                    record.scope.session_id, "identity_record.scope.session_id"
                ),
                assurance=_enum(
                    Assurance,
                    record.scope.assurance,
                    "identity_record.scope.assurance",
                ),
            ),
            parents=tuple(
                IdentityRef(
                    kind=_enum(
                        IdentityKind,
                        parent.kind,
                        "identity_record.parents.kind",
                    ),
                    id=_required_text(parent.id, "identity_record.parents.id"),
                )
                for parent in record.parents
            ),
            connection_epoch_ref=connection_epoch_ref,
        )
        parent_kinds = frozenset(parent.kind for parent in record.parents)
        if len(parent_kinds) != len(record.parents):
            raise _violation(
                "DUPLICATE_PARENT_KIND",
                "an identity may have at most one parent per kind",
            )
        expected = _EXPECTED_PARENT_KINDS[record.ref.kind]
        if parent_kinds != expected:
            raise _violation(
                "IDENTITY_PARENT_MISMATCH",
                f"{record.ref.kind.value} requires parent kinds "
                f"{sorted(kind.value for kind in expected)}",
            )
        if (
            record.ref.kind in {IdentityKind.CONNECTION, IdentityKind.MEDIA_SESSION}
            and connection_epoch_ref is None
        ):
            raise _violation(
                "CONNECTION_EPOCH_BINDING_REQUIRED",
                f"{record.ref.kind.value} requires connection_epoch_ref",
            )
        if (
            record.ref.kind not in {IdentityKind.CONNECTION, IdentityKind.MEDIA_SESSION}
            and connection_epoch_ref is not None
        ):
            raise _violation(
                "CONNECTION_EPOCH_BINDING_FORBIDDEN",
                f"{record.ref.kind.value} forbids connection_epoch_ref",
            )
        if (
            record.ref.kind is IdentityKind.CONNECTION
            and connection_epoch_ref is not None
            and connection_epoch_ref.connection_id != record.ref.id
        ):
            raise _violation(
                "CONNECTION_EPOCH_BINDING_MISMATCH",
                "connection binding must name the registered connection",
            )
        with self._lock:
            existing_kind = self._kind_by_id.get(record.ref.id)
            if existing_kind is not None and existing_kind is not record.ref.kind:
                raise _violation(
                    "IDENTITY_KIND_MISMATCH",
                    f"identity {record.ref.id!r} is already {existing_kind.value}",
                )
            for parent in record.parents:
                parent_record = self._records.get((parent.kind, parent.id))
                if parent_record is None:
                    raise _violation(
                        "IDENTITY_PARENT_NOT_FOUND",
                        f"parent {parent.kind.value}:{parent.id} is not registered",
                    )
                if parent_record.scope != record.scope:
                    raise _violation(
                        "IDENTITY_SCOPE_MISMATCH",
                        "child and parent scope must match exactly",
                    )
            if (
                record.ref.kind is IdentityKind.MEDIA_SESSION
                and connection_epoch_ref is not None
            ):
                connection = self._records.get(
                    (IdentityKind.CONNECTION, connection_epoch_ref.connection_id)
                )
                if connection is None:
                    raise _violation(
                        "IDENTITY_CONNECTION_NOT_FOUND",
                        "the media session connection is not registered",
                    )
                if connection.scope != record.scope:
                    raise _violation(
                        "IDENTITY_SCOPE_MISMATCH",
                        "media session and connection scope must match exactly",
                    )
                if connection.connection_epoch_ref != connection_epoch_ref:
                    raise _violation(
                        "CONNECTION_EPOCH_BINDING_MISMATCH",
                        "media session must use the active connection epoch binding",
                    )
            parent_map = {parent.kind: parent for parent in record.parents}
            if record.ref.kind is IdentityKind.RESPONSE:
                turn = self._records[
                    (IdentityKind.TURN, parent_map[IdentityKind.TURN].id)
                ]
                turn_interaction = next(
                    parent
                    for parent in turn.parents
                    if parent.kind is IdentityKind.INTERACTION
                )
                if turn_interaction != parent_map[IdentityKind.INTERACTION]:
                    raise _violation(
                        "IDENTITY_PARENT_MISMATCH",
                        "response interaction must own its initiating turn",
                    )
            key = (record.ref.kind, record.ref.id)
            existing = self._records.get(key)
            if existing is not None:
                if existing != record:
                    raise _violation(
                        "IDENTITY_CONFLICT", "identity registration is immutable"
                    )
                return existing
            self._records[key] = record
            self._kind_by_id[record.ref.id] = record.ref.kind
            return record

    def require(
        self,
        ref: IdentityRef,
        *,
        scope: ScopeRef | None = None,
        parent: IdentityRef | None = None,
    ) -> IdentityRecord:
        with self._lock:
            record = self._records.get((ref.kind, ref.id))
            if record is None:
                known_kind = self._kind_by_id.get(ref.id)
                if known_kind is not None:
                    raise _violation(
                        "IDENTITY_KIND_MISMATCH",
                        f"identity {ref.id!r} is {known_kind.value}, not {ref.kind.value}",
                    )
                raise _violation(
                    "IDENTITY_NOT_FOUND",
                    f"identity {ref.kind.value}:{ref.id} is unknown",
                )
            if scope is not None and record.scope != scope:
                raise _violation(
                    "IDENTITY_SCOPE_MISMATCH", "identity scope does not match"
                )
            if parent is not None and parent not in record.parents:
                raise _violation(
                    "IDENTITY_PARENT_MISMATCH",
                    f"{parent.kind.value}:{parent.id} does not own "
                    f"{ref.kind.value}:{ref.id}",
                )
            return record


_COMMAND_TARGETS: Final = MappingProxyType(
    {
        "task.create": IdentityKind.TASK,
        CancelScope.PLAYBACK_STOP.value: IdentityKind.RESPONSE,
        CancelScope.RESPONSE_CANCEL.value: IdentityKind.RESPONSE,
        CancelScope.ROUND_CANCEL.value: IdentityKind.ROUND,
        CancelScope.TASK_CANCEL.value: IdentityKind.TASK,
    }
)
_QUERY_TARGETS: Final = MappingProxyType(
    {
        "task.get": IdentityKind.TASK,
        "task.list": IdentityKind.TASK,
        "task.status": IdentityKind.TASK,
        "task.events": IdentityKind.TASK,
    }
)
_CORE_CAPABILITIES: Final = frozenset(
    {
        *_COMMAND_TARGETS,
        *_QUERY_TARGETS,
        "event.replay",
        "recognize.batch",
        "recognize.stream",
        "synthesize.batch",
        "synthesize.stream",
        "cancel.ack",
    }
)


def _extensions(value: object, field_name: str) -> _FrozenObject:
    data = _strict_object(value, field_name=field_name)
    for key in data:
        _namespaced(key, f"{field_name} key")
    return _freeze_object(data, field_name)


def _context_refs(
    value: object, field_name: str, *, scope: ScopeRef
) -> tuple[ContextRef, ...]:
    parsed: list[ContextRef] = []
    for index, item in enumerate(_strict_array(value, field_name=field_name)):
        ref = ContextRef.from_dict(item)
        if ref.scope != scope:
            raise _violation(
                "CONTEXT_SCOPE_MISMATCH",
                f"{field_name}[{index}] does not match the enclosing scope",
                code=ErrorCode.PERMISSION_DENIED,
            )
        parsed.append(ref)
    return tuple(parsed)


def _capability_list(value: object, field_name: str) -> tuple[str, ...]:
    values = _strict_array(value, field_name=field_name)
    parsed: list[str] = []
    for index, item in enumerate(values):
        capability = _namespaced(item, f"{field_name}[{index}]")
        if capability not in _CORE_CAPABILITIES:
            raise _violation(
                "UNKNOWN_REQUIRED_CAPABILITY",
                f"unknown required capability {capability!r}",
                code=ErrorCode.UNSUPPORTED,
            )
        if capability in parsed:
            raise _violation(
                "DUPLICATE_REQUIRED_CAPABILITY",
                f"duplicate required capability {capability!r}",
            )
        parsed.append(capability)
    return tuple(parsed)


def _command_payload(command_type: str, value: object) -> _FrozenObject:
    data = _strict_object(value, field_name="command.payload")
    if command_type in {
        CancelScope.PLAYBACK_STOP.value,
        CancelScope.RESPONSE_CANCEL.value,
    }:
        _require_exact_keys(
            data,
            required={"interaction_id", "response_generation"},
            field_name="command.payload",
        )
        _required_text(data["interaction_id"], "command.payload.interaction_id")
        _uint(data["response_generation"], "command.payload.response_generation")
    elif command_type in {
        CancelScope.ROUND_CANCEL.value,
        CancelScope.TASK_CANCEL.value,
    }:
        _require_exact_keys(data, required=set(), field_name="command.payload")
    return _freeze_object(data, "command.payload")


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    request_id: str
    command_id: str
    command_type: str
    issued_at: str
    scope: ScopeRef
    correlation_id: str
    causation_id: str | None
    origin: OriginRef
    target_ref: IdentityRef
    context_refs: tuple[ContextRef, ...]
    required_capabilities: tuple[str, ...]
    _payload: _FrozenObject = field(repr=False)
    _extensions: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def payload(self) -> dict[str, object]:
        return _thaw_object(self._payload)

    @property
    def extensions(self) -> dict[str, object]:
        return _thaw_object(self._extensions)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        identities: IdentityRegistry | None = None,
        commits: TurnCommitLedger | None = None,
    ) -> CommandEnvelope:
        data = _strict_object(payload, field_name="command")
        required = {
            "contract_version",
            "request_id",
            "command_id",
            "command_type",
            "issued_at",
            "scope",
            "correlation_id",
            "causation_id",
            "origin",
            "target_ref",
            "context_refs",
            "required_capabilities",
            "payload",
            "extensions",
        }
        _require_exact_keys(data, required=required, field_name="command")
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        command_type = _namespaced(data["command_type"], "command.command_type")
        expected_kind = _COMMAND_TARGETS.get(command_type)
        if expected_kind is None:
            raise _violation(
                "UNSUPPORTED_COMMAND_TYPE",
                f"unsupported command type {command_type!r}",
                code=ErrorCode.UNSUPPORTED,
            )
        scope = ScopeRef.from_dict(data["scope"])
        origin = OriginRef.from_dict(data["origin"])
        target_ref = IdentityRef.from_dict(
            data["target_ref"], expected_kind=expected_kind
        )
        result = cls(
            request_id=_required_text(data["request_id"], "command.request_id"),
            command_id=_required_text(data["command_id"], "command.command_id"),
            command_type=command_type,
            issued_at=_timestamp(data["issued_at"], "command.issued_at"),
            scope=scope,
            correlation_id=_required_text(
                data["correlation_id"], "command.correlation_id"
            ),
            causation_id=_optional_id(data["causation_id"], "command.causation_id"),
            origin=origin,
            target_ref=target_ref,
            context_refs=_context_refs(
                data["context_refs"], "command.context_refs", scope=scope
            ),
            required_capabilities=_capability_list(
                data["required_capabilities"], "command.required_capabilities"
            ),
            _payload=_command_payload(command_type, data["payload"]),
            _extensions=_extensions(data["extensions"], "command.extensions"),
        )
        if identities is not None:
            if command_type != "task.create":
                identities.require(target_ref, scope=scope)
            if command_type in {
                CancelScope.PLAYBACK_STOP.value,
                CancelScope.RESPONSE_CANCEL.value,
            }:
                interaction = IdentityRef(
                    IdentityKind.INTERACTION,
                    str(result.payload["interaction_id"]),
                )
                identities.require(interaction, scope=scope)
                identities.require(target_ref, scope=scope, parent=interaction)
            if origin.kind == "committed_turn":
                identities.require(
                    IdentityRef(IdentityKind.TURN, origin.turn_id or ""), scope=scope
                )
        if origin.kind == "committed_turn" and commits is not None:
            commits.require_origin(origin, scope)
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "request_id": self.request_id,
            "command_id": self.command_id,
            "command_type": self.command_type,
            "issued_at": self.issued_at,
            "scope": self.scope.to_dict(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "origin": self.origin.to_dict(),
            "target_ref": self.target_ref.to_dict(),
            "context_refs": [ref.to_dict() for ref in self.context_refs],
            "required_capabilities": list(self.required_capabilities),
            "payload": self.payload,
            "extensions": self.extensions,
        }

    def fingerprint(self) -> bytes:
        payload = self.to_dict()
        del payload["request_id"]
        return canonical_json_bytes(payload)


@dataclass(frozen=True, slots=True)
class QueryEnvelope:
    request_id: str
    query_type: str
    issued_at: str
    scope: ScopeRef
    correlation_id: str
    causation_id: str | None
    target_ref: IdentityRef
    context_refs: tuple[ContextRef, ...]
    required_capabilities: tuple[str, ...]
    _payload: _FrozenObject = field(repr=False)
    _extensions: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def payload(self) -> dict[str, object]:
        return _thaw_object(self._payload)

    @property
    def extensions(self) -> dict[str, object]:
        return _thaw_object(self._extensions)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        identities: IdentityRegistry | None = None,
    ) -> QueryEnvelope:
        data = _strict_object(payload, field_name="query")
        required = {
            "contract_version",
            "request_id",
            "query_type",
            "issued_at",
            "scope",
            "correlation_id",
            "causation_id",
            "target_ref",
            "context_refs",
            "required_capabilities",
            "payload",
            "extensions",
        }
        _require_exact_keys(data, required=required, field_name="query")
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        query_type = _namespaced(data["query_type"], "query.query_type")
        expected_kind = _QUERY_TARGETS.get(query_type)
        if expected_kind is None:
            raise _violation(
                "UNSUPPORTED_QUERY_TYPE",
                f"unsupported read-only query {query_type!r}",
                code=ErrorCode.UNSUPPORTED,
            )
        scope = ScopeRef.from_dict(data["scope"])
        target_ref = IdentityRef.from_dict(
            data["target_ref"], expected_kind=expected_kind
        )
        result = cls(
            request_id=_required_text(data["request_id"], "query.request_id"),
            query_type=query_type,
            issued_at=_timestamp(data["issued_at"], "query.issued_at"),
            scope=scope,
            correlation_id=_required_text(
                data["correlation_id"], "query.correlation_id"
            ),
            causation_id=_optional_id(data["causation_id"], "query.causation_id"),
            target_ref=target_ref,
            context_refs=_context_refs(
                data["context_refs"], "query.context_refs", scope=scope
            ),
            required_capabilities=_capability_list(
                data["required_capabilities"], "query.required_capabilities"
            ),
            _payload=_freeze_object(data["payload"], "query.payload"),
            _extensions=_extensions(data["extensions"], "query.extensions"),
        )
        if identities is not None:
            identities.require(target_ref, scope=scope)
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "request_id": self.request_id,
            "query_type": self.query_type,
            "issued_at": self.issued_at,
            "scope": self.scope.to_dict(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "target_ref": self.target_ref.to_dict(),
            "context_refs": [ref.to_dict() for ref in self.context_refs],
            "required_capabilities": list(self.required_capabilities),
            "payload": self.payload,
            "extensions": self.extensions,
        }


@dataclass(frozen=True, slots=True)
class ResultEnvelope:
    request_id: str
    command_id: str | None
    ok: bool
    _result: _FrozenObject | None
    error: ContractError | None
    observed_at: str
    _extensions: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def result(self) -> dict[str, object] | None:
        return None if self._result is None else _thaw_object(self._result)

    @property
    def extensions(self) -> dict[str, object]:
        return _thaw_object(self._extensions)

    @classmethod
    def success(
        cls,
        *,
        owner: CommandEnvelope | QueryEnvelope,
        result: Mapping[str, object],
        observed_at: str,
        extensions: Mapping[str, object] | None = None,
    ) -> ResultEnvelope:
        return cls(
            request_id=owner.request_id,
            command_id=(
                owner.command_id if isinstance(owner, CommandEnvelope) else None
            ),
            ok=True,
            _result=_freeze_object(dict(result), "result.result"),
            error=None,
            observed_at=_timestamp(observed_at, "result.observed_at"),
            _extensions=_extensions(dict(extensions or {}), "result.extensions"),
        )

    @classmethod
    def failure(
        cls,
        *,
        owner: CommandEnvelope | QueryEnvelope,
        error: ContractError,
        observed_at: str,
        extensions: Mapping[str, object] | None = None,
    ) -> ResultEnvelope:
        return cls(
            request_id=owner.request_id,
            command_id=(
                owner.command_id if isinstance(owner, CommandEnvelope) else None
            ),
            ok=False,
            _result=None,
            error=error,
            observed_at=_timestamp(observed_at, "result.observed_at"),
            _extensions=_extensions(dict(extensions or {}), "result.extensions"),
        )

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        owner: CommandEnvelope | QueryEnvelope | None = None,
    ) -> ResultEnvelope:
        data = _strict_object(payload, field_name="result")
        _require_exact_keys(
            data,
            required={
                "contract_version",
                "request_id",
                "command_id",
                "ok",
                "result",
                "error",
                "observed_at",
                "extensions",
            },
            field_name="result",
        )
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        ok = _bool(data["ok"], "result.ok")
        result_value = (
            None
            if data["result"] is None
            else _freeze_object(data["result"], "result.result")
        )
        error_value = (
            None if data["error"] is None else ContractError.from_dict(data["error"])
        )
        if ok and (result_value is None or error_value is not None):
            raise _violation(
                "INVALID_RESULT_EXCLUSIVITY",
                "ok result requires result and forbids error",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
        if not ok and (result_value is not None or error_value is None):
            raise _violation(
                "INVALID_RESULT_EXCLUSIVITY",
                "failed result requires error and forbids result",
                code=ErrorCode.PROTOCOL_VIOLATION,
            )
        result = cls(
            request_id=_required_text(data["request_id"], "result.request_id"),
            command_id=_optional_id(data["command_id"], "result.command_id"),
            ok=ok,
            _result=result_value,
            error=error_value,
            observed_at=_timestamp(data["observed_at"], "result.observed_at"),
            _extensions=_extensions(data["extensions"], "result.extensions"),
        )
        if owner is not None:
            expected_command_id = (
                owner.command_id if isinstance(owner, CommandEnvelope) else None
            )
            if (
                result.request_id != owner.request_id
                or result.command_id != expected_command_id
            ):
                raise _violation(
                    "RESULT_OWNER_MISMATCH",
                    "result request_id/command_id does not match its owner",
                    code=ErrorCode.PROTOCOL_VIOLATION,
                )
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "request_id": self.request_id,
            "command_id": self.command_id,
            "ok": self.ok,
            "result": self.result,
            "error": None if self.error is None else self.error.to_dict(),
            "observed_at": self.observed_at,
            "extensions": self.extensions,
        }

    def for_request(self, request_id: str) -> ResultEnvelope:
        return ResultEnvelope(
            request_id=_required_text(request_id, "result.request_id"),
            command_id=self.command_id,
            ok=self.ok,
            _result=self._result,
            error=self.error,
            observed_at=self.observed_at,
            _extensions=self._extensions,
        )


@dataclass(frozen=True, slots=True)
class KnownFact(Generic[_FactT]):
    knowledge: Knowledge
    value: _FactT | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.knowledge, Knowledge):
            raise _violation(
                "INVALID_ENUM",
                "known_fact.knowledge must be known or unknown",
            )
        if self.knowledge is Knowledge.KNOWN and self.value is None:
            raise _violation(
                "KNOWN_FACT_VALUE_REQUIRED", "a known fact requires a value"
            )
        if self.knowledge is Knowledge.UNKNOWN and self.value is not None:
            raise _violation(
                "UNKNOWN_FACT_VALUE_FORBIDDEN", "an unknown fact forbids a value"
            )


def _known_fact(
    payload: object,
    field_name: str,
    parser: Callable[[object], _FactT],
) -> KnownFact[_FactT]:
    data = _strict_object(payload, field_name=field_name)
    knowledge = _enum(Knowledge, data.get("knowledge"), f"{field_name}.knowledge")
    required = {"knowledge", "value"} if knowledge is Knowledge.KNOWN else {"knowledge"}
    _require_exact_keys(data, required=required, field_name=field_name)
    return KnownFact(
        knowledge,
        None if knowledge is Knowledge.UNKNOWN else parser(data["value"]),
    )


def _fact_text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise _violation("INVALID_FACT_TEXT", f"{field_name} must be a string")
    return _validate_unicode(value, field_name)


@dataclass(frozen=True, slots=True)
class WorkProgressSource:
    authority: WorkSourceAuthority
    event_id: str
    source_work_ref: IdentityRef
    adapter: str | None

    @classmethod
    def from_dict(cls, payload: object) -> WorkProgressSource:
        data = _strict_object(payload, field_name="work_progress.source")
        _require_exact_keys(
            data,
            required={"authority", "event_id", "source_work_ref", "adapter"},
            field_name="work_progress.source",
        )
        source_work_ref = IdentityRef.from_dict(data["source_work_ref"])
        if source_work_ref.kind not in {
            IdentityKind.ROUND,
            IdentityKind.TASK,
            IdentityKind.ATTEMPT,
        }:
            raise _violation(
                "INVALID_PROGRESS_SOURCE_KIND",
                "source_work_ref must identify a round, task, or attempt",
            )
        authority = _enum(
            WorkSourceAuthority,
            data["authority"],
            "work_progress.source.authority",
        )
        expected_kind = {
            WorkSourceAuthority.HARNESS: IdentityKind.ROUND,
            WorkSourceAuthority.TASK_CORE: IdentityKind.TASK,
            WorkSourceAuthority.EXECUTOR: IdentityKind.ATTEMPT,
        }[authority]
        if source_work_ref.kind is not expected_kind:
            raise _violation(
                "PROGRESS_SOURCE_AUTHORITY_MISMATCH",
                f"{authority.value} progress requires {expected_kind.value} source_work_ref",
                code=ErrorCode.PERMISSION_DENIED,
            )
        return cls(
            authority=authority,
            event_id=_required_text(data["event_id"], "work_progress.source.event_id"),
            source_work_ref=source_work_ref,
            adapter=_optional_id(data["adapter"], "work_progress.source.adapter"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "authority": self.authority.value,
            "event_id": self.event_id,
            "source_work_ref": self.source_work_ref.to_dict(),
            "adapter": self.adapter,
        }


@dataclass(frozen=True, slots=True)
class WorkProgressEventV2:
    work_ref: IdentityRef
    source: WorkProgressSource
    seq: int
    state: WorkState
    outcome: TerminalOutcome | None
    summary: KnownFact[str]
    blocking_question: KnownFact[str]
    artifact_refs: KnownFact[tuple[ContextRef, ...]]
    urgency: WorkUrgency
    speakability: Speakability

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        scope: ScopeRef | None = None,
        identities: IdentityRegistry | None = None,
    ) -> WorkProgressEventV2:
        data = _strict_object(payload, field_name="work_progress")
        _require_exact_keys(
            data,
            required={
                "work_ref",
                "source",
                "seq",
                "state",
                "outcome",
                "summary",
                "blocking_question",
                "artifact_refs",
                "urgency",
                "speakability",
            },
            field_name="work_progress",
        )
        work_ref = IdentityRef.from_dict(data["work_ref"])
        if work_ref.kind not in {IdentityKind.ROUND, IdentityKind.TASK}:
            raise _violation(
                "INVALID_WORK_REF_KIND", "work_ref must identify a round or task"
            )
        source = WorkProgressSource.from_dict(data["source"])
        if source.source_work_ref.kind in {IdentityKind.ROUND, IdentityKind.TASK}:
            if source.source_work_ref != work_ref:
                raise _violation(
                    "PROGRESS_SOURCE_WORK_MISMATCH",
                    "round/task source_work_ref must equal work_ref",
                )
        elif work_ref.kind is not IdentityKind.TASK:
            raise _violation(
                "PROGRESS_ATTEMPT_PARENT_MISMATCH",
                "an attempt source can project only to a task",
            )
        if scope is not None and identities is not None:
            identities.require(work_ref, scope=scope)
            identities.require(
                source.source_work_ref,
                scope=scope,
                parent=(
                    work_ref
                    if source.source_work_ref.kind is IdentityKind.ATTEMPT
                    else None
                ),
            )
        state = _enum(WorkState, data["state"], "work_progress.state")
        outcome = (
            None
            if data["outcome"] is None
            else _enum(TerminalOutcome, data["outcome"], "work_progress.outcome")
        )
        if state is WorkState.TERMINAL and outcome is None:
            raise _violation(
                "TERMINAL_OUTCOME_REQUIRED",
                "terminal WorkProgress requires an outcome",
            )
        if state is not WorkState.TERMINAL and outcome is not None:
            raise _violation(
                "NON_TERMINAL_OUTCOME_FORBIDDEN",
                "non-terminal WorkProgress forbids an outcome",
            )

        def parse_artifacts(value: object) -> tuple[ContextRef, ...]:
            values = _strict_array(
                value, field_name="work_progress.artifact_refs.value"
            )
            refs = tuple(ContextRef.from_dict(item) for item in values)
            if scope is not None:
                for ref in refs:
                    if ref.scope != scope:
                        raise _violation(
                            "CONTEXT_SCOPE_MISMATCH",
                            "artifact context scope must match WorkProgress scope",
                            code=ErrorCode.PERMISSION_DENIED,
                        )
            return refs

        return cls(
            work_ref=work_ref,
            source=source,
            seq=_uint(data["seq"], "work_progress.seq"),
            state=state,
            outcome=outcome,
            summary=_known_fact(
                data["summary"],
                "work_progress.summary",
                lambda value: _fact_text(value, "work_progress.summary.value"),
            ),
            blocking_question=_known_fact(
                data["blocking_question"],
                "work_progress.blocking_question",
                lambda value: _fact_text(
                    value, "work_progress.blocking_question.value"
                ),
            ),
            artifact_refs=_known_fact(
                data["artifact_refs"],
                "work_progress.artifact_refs",
                parse_artifacts,
            ),
            urgency=_enum(WorkUrgency, data["urgency"], "work_progress.urgency"),
            speakability=_enum(
                Speakability, data["speakability"], "work_progress.speakability"
            ),
        )

    @staticmethod
    def _fact_dict(
        fact: KnownFact[_FactT], serializer: Callable[[_FactT], object]
    ) -> dict[str, object]:
        if fact.knowledge is Knowledge.UNKNOWN:
            return {"knowledge": Knowledge.UNKNOWN.value}
        assert fact.value is not None
        return {
            "knowledge": Knowledge.KNOWN.value,
            "value": serializer(fact.value),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "work_ref": self.work_ref.to_dict(),
            "source": self.source.to_dict(),
            "seq": self.seq,
            "state": self.state.value,
            "outcome": None if self.outcome is None else self.outcome.value,
            "summary": self._fact_dict(self.summary, lambda value: value),
            "blocking_question": self._fact_dict(
                self.blocking_question, lambda value: value
            ),
            "artifact_refs": self._fact_dict(
                self.artifact_refs,
                lambda value: [ref.to_dict() for ref in value],
            ),
            "urgency": self.urgency.value,
            "speakability": self.speakability.value,
        }


@dataclass(frozen=True, slots=True)
class _EventRule:
    stream_kind: IdentityKind | tuple[IdentityKind, ...]
    authority: str
    state: str | None = None
    terminal: bool = False
    adapter: bool = False
    lifecycle: bool = True
    progress: bool = False


_EVENT_RULES: Final = MappingProxyType(
    {
        "interaction.opened": _EventRule(
            IdentityKind.INTERACTION, "conversation_runtime", "open"
        ),
        "interaction.closing": _EventRule(
            IdentityKind.INTERACTION, "conversation_runtime", "closing"
        ),
        "interaction.closed": _EventRule(
            IdentityKind.INTERACTION, "conversation_runtime", "closed"
        ),
        "turn.capturing": _EventRule(
            IdentityKind.TURN, "conversation_runtime", "capturing"
        ),
        "turn.committed": _EventRule(
            IdentityKind.TURN, "conversation_runtime", "committed"
        ),
        "turn.cancelled": _EventRule(
            IdentityKind.TURN, "conversation_runtime", "cancelled"
        ),
        "response.accepted": _EventRule(
            IdentityKind.RESPONSE, "conversation_runtime", "accepted"
        ),
        "response.generating": _EventRule(
            IdentityKind.RESPONSE, "conversation_runtime", "generating"
        ),
        "response.speaking": _EventRule(
            IdentityKind.RESPONSE, "conversation_runtime", "speaking"
        ),
        "response.terminal": _EventRule(
            IdentityKind.RESPONSE,
            "conversation_runtime",
            "terminal",
            terminal=True,
        ),
        "round.accepted": _EventRule(IdentityKind.ROUND, "harness", "accepted"),
        "round.running": _EventRule(IdentityKind.ROUND, "harness", "running"),
        "round.blocked": _EventRule(IdentityKind.ROUND, "harness", "blocked"),
        "round.decision_required": _EventRule(
            IdentityKind.ROUND, "harness", "decision_required"
        ),
        "round.terminal": _EventRule(
            IdentityKind.ROUND, "harness", "terminal", terminal=True
        ),
        "task.accepted": _EventRule(IdentityKind.TASK, "task_core", "accepted"),
        "task.running": _EventRule(IdentityKind.TASK, "task_core", "running"),
        "task.blocked": _EventRule(IdentityKind.TASK, "task_core", "blocked"),
        "task.decision_required": _EventRule(
            IdentityKind.TASK, "task_core", "decision_required"
        ),
        "task.terminal": _EventRule(
            IdentityKind.TASK, "task_core", "terminal", terminal=True
        ),
        "attempt.accepted": _EventRule(IdentityKind.ATTEMPT, "executor", "accepted"),
        "attempt.running": _EventRule(IdentityKind.ATTEMPT, "executor", "running"),
        "attempt.terminal": _EventRule(
            IdentityKind.ATTEMPT, "executor", "terminal", terminal=True
        ),
        "adapter.observed": _EventRule(IdentityKind.EVENT, "adapter", adapter=True),
        "work.progress": _EventRule(
            (IdentityKind.ROUND, IdentityKind.TASK),
            "adapter",
            adapter=True,
            lifecycle=False,
            progress=True,
        ),
    }
)


def _validate_event_payload(
    event_type: str, data: Mapping[str, object], rule: _EventRule
) -> _FrozenObject:
    if rule.progress:
        progress = WorkProgressEventV2.from_dict(dict(data))
        return _freeze_object(progress.to_dict(), "event.payload")
    if rule.adapter:
        _require_exact_keys(
            data,
            required={"source_event_type"},
            field_name="event.payload",
        )
        _namespaced(data["source_event_type"], "event.payload.source_event_type")
        return _freeze_object(dict(data), "event.payload")
    required = {"state", "outcome"} if rule.terminal else {"state"}
    _require_exact_keys(data, required=required, field_name="event.payload")
    if data["state"] != rule.state:
        raise _violation(
            "EVENT_STATE_MISMATCH",
            f"{event_type} requires payload.state={rule.state!r}",
        )
    if rule.terminal:
        _enum(TerminalOutcome, data["outcome"], "event.payload.outcome")
    return _freeze_object(dict(data), "event.payload")


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    producer: ProducerRef
    stream_ref: IdentityRef
    seq: int
    occurred_at: str
    scope: ScopeRef
    correlation_id: str
    causation_id: str | None
    required_capabilities: tuple[str, ...]
    _payload: _FrozenObject = field(repr=False)
    _extensions: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def payload(self) -> dict[str, object]:
        return _thaw_object(self._payload)

    @property
    def extensions(self) -> dict[str, object]:
        return _thaw_object(self._extensions)

    @property
    def stream_key(self) -> tuple[str, str, IdentityKind, str]:
        return (
            self.producer.component,
            self.producer.instance_id,
            self.stream_ref.kind,
            self.stream_ref.id,
        )

    @property
    def progress_source_key(self) -> tuple[ScopeRef, IdentityKind, str]:
        """Logical source identity that survives an authority instance restart."""

        return (self.scope, self.stream_ref.kind, self.stream_ref.id)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        identities: IdentityRegistry | None = None,
    ) -> EventEnvelope:
        data = _strict_object(payload, field_name="event")
        _require_exact_keys(
            data,
            required={
                "contract_version",
                "event_id",
                "event_type",
                "producer",
                "stream_ref",
                "seq",
                "occurred_at",
                "scope",
                "correlation_id",
                "causation_id",
                "required_capabilities",
                "payload",
                "extensions",
            },
            field_name="event",
        )
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        event_type = _namespaced(data["event_type"], "event.event_type")
        rule = _EVENT_RULES.get(event_type)
        if rule is None:
            raise _violation(
                "UNKNOWN_EVENT_TYPE",
                f"unknown event type {event_type!r}",
                code=ErrorCode.UNSUPPORTED,
            )
        producer = ProducerRef.from_dict(data["producer"])
        if producer.authority != rule.authority:
            raise _violation(
                "EVENT_AUTHORITY_MISMATCH",
                f"{event_type} requires authority {rule.authority!r}",
                code=ErrorCode.PERMISSION_DENIED,
            )
        stream_ref = IdentityRef.from_dict(data["stream_ref"])
        allowed_stream_kinds = (
            rule.stream_kind
            if isinstance(rule.stream_kind, tuple)
            else (rule.stream_kind,)
        )
        if stream_ref.kind not in allowed_stream_kinds:
            expected = ", ".join(kind.value for kind in allowed_stream_kinds)
            raise _violation(
                "IDENTITY_KIND_MISMATCH",
                f"expected one of {expected}, got {stream_ref.kind.value}",
            )
        causation_id = _optional_id(data["causation_id"], "event.causation_id")
        if rule.adapter and causation_id is None:
            raise _violation(
                "ADAPTER_CAUSATION_REQUIRED",
                "adapter events must reference their authoritative source event",
            )
        scope = ScopeRef.from_dict(data["scope"])
        event_payload = _strict_object(data["payload"], field_name="event.payload")
        result = cls(
            event_id=_required_text(data["event_id"], "event.event_id"),
            event_type=event_type,
            producer=producer,
            stream_ref=stream_ref,
            seq=_uint(data["seq"], "event.seq"),
            occurred_at=_timestamp(data["occurred_at"], "event.occurred_at"),
            scope=scope,
            correlation_id=_required_text(
                data["correlation_id"], "event.correlation_id"
            ),
            causation_id=causation_id,
            required_capabilities=_capability_list(
                data["required_capabilities"], "event.required_capabilities"
            ),
            _payload=_validate_event_payload(event_type, event_payload, rule),
            _extensions=_extensions(data["extensions"], "event.extensions"),
        )
        if rule.progress:
            progress = WorkProgressEventV2.from_dict(
                result.payload, scope=scope, identities=identities
            )
            if (
                progress.source.source_work_ref.kind is IdentityKind.ATTEMPT
                and identities is None
            ):
                raise _violation(
                    "PROGRESS_ATTEMPT_PARENT_UNVERIFIED",
                    "attempt-to-task WorkProgress requires an IdentityRegistry parent binding",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            if progress.work_ref != stream_ref:
                raise _violation(
                    "PROGRESS_ENVELOPE_MISMATCH",
                    "work.progress stream_ref must match its projection work_ref",
                )
            if progress.source.event_id != causation_id:
                raise _violation(
                    "PROGRESS_CAUSATION_MISMATCH",
                    "work.progress causation_id must equal source.event_id",
                )
        if identities is not None:
            identities.require(stream_ref, scope=scope)
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "producer": self.producer.to_dict(),
            "stream_ref": self.stream_ref.to_dict(),
            "seq": self.seq,
            "occurred_at": self.occurred_at,
            "scope": self.scope.to_dict(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "required_capabilities": list(self.required_capabilities),
            "payload": self.payload,
            "extensions": self.extensions,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    component: str
    contract_major: str
    supported_operations: tuple[str, ...]
    supported_event_types: tuple[str, ...]
    batch_modes: tuple[str, ...]
    stream_modes: tuple[str, ...]
    supports_cancel_ack: bool
    supports_replay: bool
    _declared_limits: _FrozenObject = field(repr=False)
    fallback_identity: str | None
    availability: Availability

    @property
    def declared_limits(self) -> dict[str, object]:
        return _thaw_object(self._declared_limits)

    @staticmethod
    def _unique_namespaced(value: object, field_name: str) -> tuple[str, ...]:
        items = _strict_array(value, field_name=field_name)
        parsed = tuple(
            _namespaced(item, f"{field_name}[{index}]")
            for index, item in enumerate(items)
        )
        if len(parsed) != len(set(parsed)):
            raise _violation("DUPLICATE_CAPABILITY", f"{field_name} has duplicates")
        return parsed

    @staticmethod
    def _unique_modes(
        value: object, field_name: str, allowed: frozenset[str]
    ) -> tuple[str, ...]:
        items = _strict_array(value, field_name=field_name)
        parsed: list[str] = []
        for index, item in enumerate(items):
            mode = _required_text(item, f"{field_name}[{index}]")
            if mode not in allowed:
                raise _violation("INVALID_CAPABILITY_MODE", f"unknown mode {mode!r}")
            if mode in parsed:
                raise _violation(
                    "DUPLICATE_CAPABILITY_MODE", f"duplicate mode {mode!r}"
                )
            parsed.append(mode)
        return tuple(parsed)

    @classmethod
    def from_dict(cls, payload: object) -> CapabilityDescriptor:
        data = _strict_object(payload, field_name="capability")
        _require_exact_keys(
            data,
            required={
                "component",
                "contract_major",
                "supported_operations",
                "supported_event_types",
                "batch_modes",
                "stream_modes",
                "supports_cancel_ack",
                "supports_replay",
                "declared_limits",
                "fallback_identity",
                "availability",
            },
            field_name="capability",
        )
        if data["contract_major"] != "v2":
            raise _violation(
                "UNSUPPORTED_CONTRACT_MAJOR",
                "capability.contract_major must be 'v2'",
                code=ErrorCode.UNSUPPORTED,
            )
        return cls(
            component=_required_text(data["component"], "capability.component"),
            contract_major="v2",
            supported_operations=cls._unique_namespaced(
                data["supported_operations"], "capability.supported_operations"
            ),
            supported_event_types=cls._unique_namespaced(
                data["supported_event_types"], "capability.supported_event_types"
            ),
            batch_modes=cls._unique_modes(
                data["batch_modes"],
                "capability.batch_modes",
                frozenset({"batch"}),
            ),
            stream_modes=cls._unique_modes(
                data["stream_modes"],
                "capability.stream_modes",
                frozenset({"stream"}),
            ),
            supports_cancel_ack=_bool(
                data["supports_cancel_ack"], "capability.supports_cancel_ack"
            ),
            supports_replay=_bool(
                data["supports_replay"], "capability.supports_replay"
            ),
            _declared_limits=_freeze_object(
                data["declared_limits"], "capability.declared_limits"
            ),
            fallback_identity=_optional_id(
                data["fallback_identity"], "capability.fallback_identity"
            ),
            availability=_enum(
                Availability, data["availability"], "capability.availability"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "component": self.component,
            "contract_major": self.contract_major,
            "supported_operations": list(self.supported_operations),
            "supported_event_types": list(self.supported_event_types),
            "batch_modes": list(self.batch_modes),
            "stream_modes": list(self.stream_modes),
            "supports_cancel_ack": self.supports_cancel_ack,
            "supports_replay": self.supports_replay,
            "declared_limits": self.declared_limits,
            "fallback_identity": self.fallback_identity,
            "availability": self.availability.value,
        }


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._descriptors: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        with self._lock:
            existing = self._descriptors.get(descriptor.component)
            if existing is not None and existing != descriptor:
                raise _violation(
                    "CAPABILITY_DESCRIPTOR_CONFLICT",
                    f"component {descriptor.component!r} changed descriptor",
                    code=ErrorCode.CONFLICT,
                )
            self._descriptors[descriptor.component] = descriptor

    def require(self, component: str, operation: str) -> None:
        parsed_component = _required_text(component, "capability.component")
        parsed_operation = _namespaced(operation, "capability.operation")
        with self._lock:
            descriptor = self._descriptors.get(parsed_component)
            if (
                descriptor is None
                or parsed_operation not in descriptor.supported_operations
            ):
                raise _violation(
                    "CAPABILITY_UNSUPPORTED",
                    f"{parsed_component!r} does not support {parsed_operation!r}",
                    code=ErrorCode.UNSUPPORTED,
                )
            if descriptor.availability is Availability.UNAVAILABLE:
                raise _violation(
                    "CAPABILITY_TEMPORARILY_UNAVAILABLE",
                    f"{parsed_component!r} is temporarily unavailable",
                    code=ErrorCode.UNAVAILABLE,
                )


_LIFECYCLE_TRANSITIONS: Final = MappingProxyType(
    {
        LifecycleKind.INTERACTION: MappingProxyType(
            {
                "open": frozenset({"closing", "closed"}),
                "closing": frozenset({"closed"}),
            }
        ),
        LifecycleKind.TURN: MappingProxyType(
            {"capturing": frozenset({"committed", "cancelled"})}
        ),
        LifecycleKind.RESPONSE: MappingProxyType(
            {
                "accepted": frozenset({"generating", "terminal"}),
                "generating": frozenset({"speaking", "terminal"}),
                "speaking": frozenset({"terminal"}),
            }
        ),
        LifecycleKind.ROUND: MappingProxyType(
            {
                "accepted": frozenset(
                    {"running", "blocked", "decision_required", "terminal"}
                ),
                "running": frozenset({"blocked", "decision_required", "terminal"}),
                "blocked": frozenset({"running", "decision_required", "terminal"}),
                "decision_required": frozenset({"running", "blocked", "terminal"}),
            }
        ),
        LifecycleKind.TASK: MappingProxyType(
            {
                "accepted": frozenset(
                    {"running", "blocked", "decision_required", "terminal"}
                ),
                "running": frozenset({"blocked", "decision_required", "terminal"}),
                "blocked": frozenset({"running", "decision_required", "terminal"}),
                "decision_required": frozenset({"running", "blocked", "terminal"}),
            }
        ),
        LifecycleKind.ATTEMPT: MappingProxyType(
            {"accepted": frozenset({"running"}), "running": frozenset({"terminal"})}
        ),
    }
)


def validate_transition(
    kind: LifecycleKind | str,
    current: str,
    next_state: str,
    *,
    outcome: TerminalOutcome | str | None = None,
) -> None:
    lifecycle = _enum(LifecycleKind, kind, "lifecycle.kind")
    current_state = _required_text(current, "lifecycle.current")
    target_state = _required_text(next_state, "lifecycle.next")
    allowed = _LIFECYCLE_TRANSITIONS[lifecycle].get(current_state, frozenset())
    if target_state not in allowed:
        raise _violation(
            "INVALID_LIFECYCLE_TRANSITION",
            f"{lifecycle.value} cannot transition from {current_state!r} "
            f"to {target_state!r}",
            code=ErrorCode.CONFLICT,
        )
    if target_state == "terminal":
        if outcome is None:
            raise _violation(
                "TERMINAL_OUTCOME_REQUIRED", "terminal transitions require an outcome"
            )
        _enum(TerminalOutcome, outcome, "lifecycle.outcome")
    elif outcome is not None:
        raise _violation(
            "NON_TERMINAL_OUTCOME_FORBIDDEN",
            "outcome is only valid for terminal transitions",
        )


@dataclass(frozen=True, slots=True)
class TurnCommit:
    commit_id: str
    turn_id: str
    interaction_id: str
    text: str
    committed_at: str
    scope: ScopeRef
    context_refs: tuple[ContextRef, ...]
    _hypothesis_provenance: _FrozenObject = field(repr=False)
    contract_version: str = CONTRACT_VERSION

    @property
    def hypothesis_provenance(self) -> dict[str, object]:
        return _thaw_object(self._hypothesis_provenance)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        identities: IdentityRegistry | None = None,
    ) -> TurnCommit:
        data = _strict_object(payload, field_name="turn_commit")
        _require_exact_keys(
            data,
            required={
                "contract_version",
                "commit_id",
                "turn_id",
                "interaction_id",
                "text",
                "hypothesis_provenance",
                "scope",
                "context_refs",
                "committed_at",
            },
            field_name="turn_commit",
        )
        if data["contract_version"] != CONTRACT_VERSION:
            raise _violation(
                "UNSUPPORTED_CONTRACT_VERSION",
                f"expected {CONTRACT_VERSION}",
                code=ErrorCode.UNSUPPORTED,
            )
        scope = ScopeRef.from_dict(data["scope"])
        turn_id = _required_text(data["turn_id"], "turn_commit.turn_id")
        interaction_id = _required_text(
            data["interaction_id"], "turn_commit.interaction_id"
        )
        if identities is not None:
            interaction = IdentityRef(IdentityKind.INTERACTION, interaction_id)
            identities.require(interaction, scope=scope)
            identities.require(
                IdentityRef(IdentityKind.TURN, turn_id),
                scope=scope,
                parent=interaction,
            )
        return cls(
            commit_id=_required_text(data["commit_id"], "turn_commit.commit_id"),
            turn_id=turn_id,
            interaction_id=interaction_id,
            text=_required_text(data["text"], "turn_commit.text"),
            committed_at=_timestamp(data["committed_at"], "turn_commit.committed_at"),
            scope=scope,
            context_refs=_context_refs(
                data["context_refs"], "turn_commit.context_refs", scope=scope
            ),
            _hypothesis_provenance=_freeze_object(
                data["hypothesis_provenance"],
                "turn_commit.hypothesis_provenance",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "commit_id": self.commit_id,
            "turn_id": self.turn_id,
            "interaction_id": self.interaction_id,
            "text": self.text,
            "hypothesis_provenance": self.hypothesis_provenance,
            "scope": self.scope.to_dict(),
            "context_refs": [ref.to_dict() for ref in self.context_refs],
            "committed_at": self.committed_at,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


class TurnCommitLedger:
    """Atomic, once-only commit ownership for a turn and commit identifier."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_commit_id: dict[str, TurnCommit] = {}
        self._by_turn_id: dict[str, TurnCommit] = {}

    def accept(self, commit: TurnCommit) -> bool:
        with self._lock:
            existing_id = self._by_commit_id.get(commit.commit_id)
            existing_turn = self._by_turn_id.get(commit.turn_id)
            existing = existing_id or existing_turn
            if existing is not None:
                if existing.canonical_bytes() == commit.canonical_bytes():
                    return False
                raise _violation(
                    "TURN_COMMIT_CONFLICT",
                    "commit_id and turn_id are immutable and may commit only once",
                    code=ErrorCode.CONFLICT,
                )
            self._by_commit_id[commit.commit_id] = commit
            self._by_turn_id[commit.turn_id] = commit
            return True

    def require_origin(self, origin: OriginRef, scope: ScopeRef) -> TurnCommit:
        if origin.kind != "committed_turn":
            raise _violation(
                "COMMITTED_ORIGIN_REQUIRED", "origin must identify a committed turn"
            )
        with self._lock:
            commit = self._by_commit_id.get(origin.commit_id or "")
            if (
                commit is None
                or commit.turn_id != origin.turn_id
                or commit.scope != scope
            ):
                raise _violation(
                    "TURN_COMMIT_NOT_ACCEPTED",
                    "origin does not match an accepted commit in the exact scope",
                    code=ErrorCode.PERMISSION_DENIED,
                )
            return commit

    def dispatch(
        self,
        commit: TurnCommit,
        target: SideEffectTarget | str,
        effect: Callable[[TurnCommit], _ValueT],
    ) -> tuple[bool, _ValueT | None]:
        _enum(SideEffectTarget, target, "input.target")
        with self._lock:
            if not self.accept(commit):
                return False, None
            return True, effect(commit)


def dispatch_committed_input(
    state: InputCommitState | str,
    target: SideEffectTarget | str,
    effect: Callable[[], _ValueT],
) -> _ValueT:
    commit_state = _enum(InputCommitState, state, "input.state")
    _enum(SideEffectTarget, target, "input.target")
    if commit_state is not InputCommitState.COMMITTED:
        raise _violation(
            "INPUT_NOT_COMMITTED",
            "partial or uncommitted input cannot invoke Agent, Tool, or Task",
            code=ErrorCode.PERMISSION_DENIED,
        )
    return effect()


@dataclass(frozen=True, slots=True)
class ResponseRef:
    interaction_id: str
    response_id: str
    response_generation: int

    def __post_init__(self) -> None:
        _required_text(self.interaction_id, "response_ref.interaction_id")
        _required_text(self.response_id, "response_ref.response_id")
        _uint(self.response_generation, "response_ref.response_generation")


@dataclass(slots=True)
class _ResponseState:
    ref: ResponseRef
    fenced: bool = False
    terminal: bool = False


class ResponseFence:
    """Accepts effects only for the exact active response tuple."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_interaction: dict[str, _ResponseState] = {}
        self._seen_ids: set[str] = set()
        self._last_generation: dict[str, int] = {}

    def begin(self, ref: ResponseRef) -> None:
        with self._lock:
            last = self._last_generation.get(ref.interaction_id, -1)
            if ref.response_id in self._seen_ids:
                raise _violation(
                    "RESPONSE_ID_REUSED",
                    "every replacement response requires a new response_id",
                    code=ErrorCode.CONFLICT,
                )
            if ref.response_generation <= last:
                raise _violation(
                    "RESPONSE_GENERATION_NOT_INCREASING",
                    "response_generation must strictly increase per interaction",
                    code=ErrorCode.STALE,
                )
            prior = self._by_interaction.get(ref.interaction_id)
            if prior is not None:
                prior.fenced = True
            self._seen_ids.add(ref.response_id)
            self._last_generation[ref.interaction_id] = ref.response_generation
            self._by_interaction[ref.interaction_id] = _ResponseState(ref)

    def cancel(self, ref: ResponseRef) -> None:
        with self._lock:
            state = self._require_exact(ref)
            state.fenced = True

    def terminal(self, ref: ResponseRef) -> None:
        with self._lock:
            state = self._require_exact(ref)
            state.fenced = True
            state.terminal = True

    def apply_if_current(
        self, ref: ResponseRef, effect: Callable[[], _ValueT]
    ) -> _ValueT:
        with self._lock:
            state = self._by_interaction.get(ref.interaction_id)
            if state is None or state.ref != ref or state.fenced or state.terminal:
                raise _violation(
                    "STALE_RESPONSE_OUTPUT",
                    "output does not match the exact active response tuple",
                    code=ErrorCode.STALE,
                )
            return effect()

    def _require_exact(self, ref: ResponseRef) -> _ResponseState:
        state = self._by_interaction.get(ref.interaction_id)
        if state is None or state.ref != ref:
            raise _violation(
                "STALE_RESPONSE_REFERENCE",
                "operation does not match the exact active response tuple",
                code=ErrorCode.STALE,
            )
        return state


def default_barge_in_scopes(
    *, cancel_response: bool = False
) -> tuple[CancelScope, ...]:
    cancel_response = _bool(cancel_response, "barge_in.cancel_response")
    scopes = [CancelScope.PLAYBACK_STOP]
    if cancel_response:
        scopes.append(CancelScope.RESPONSE_CANCEL)
    return tuple(scopes)


def dispatch_cancel(
    command: CommandEnvelope,
    handlers: Mapping[CancelScope, Callable[[CommandEnvelope], _ValueT]],
) -> _ValueT:
    try:
        scope = CancelScope(command.command_type)
    except ValueError as error:
        raise _violation(
            "NOT_A_CANCEL_COMMAND", "command is not an explicit cancel operation"
        ) from error
    handler = handlers.get(scope)
    if handler is None:
        raise _violation(
            "CANCEL_HANDLER_UNAVAILABLE",
            f"no handler is available for {scope.value}",
            code=ErrorCode.CAPABILITY_UNAVAILABLE,
        )
    return handler(command)


@dataclass(slots=True)
class _CommandExecution:
    fingerprint: bytes
    result: ResultEnvelope | None = None
    pending: bool = True


class CommandResultLedger:
    """Thread-safe command idempotency with cached owner-bound results."""

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._entries: dict[str, _CommandExecution] = {}

    def execute(
        self,
        command: CommandEnvelope,
        *,
        observed_at: str,
        handler: Callable[[CommandEnvelope], ResultEnvelope],
    ) -> ResultEnvelope:
        observed_at = _timestamp(observed_at, "result.observed_at")
        fingerprint = command.fingerprint()
        with self._condition:
            entry = self._entries.get(command.command_id)
            if entry is not None and entry.fingerprint != fingerprint:
                return ResultEnvelope.failure(
                    owner=command,
                    error=ContractError(
                        code=ErrorCode.CONFLICT,
                        reason="IDEMPOTENCY_CONFLICT",
                        message="command_id was reused with different content",
                        retriable=False,
                        correlation_id=command.correlation_id,
                        _details=_freeze_object({}, "error.details"),
                    ),
                    observed_at=observed_at,
                )
            if entry is not None:
                while entry.pending:
                    self._condition.wait()
                assert entry.result is not None
                return entry.result.for_request(command.request_id)
            entry = _CommandExecution(fingerprint=fingerprint)
            self._entries[command.command_id] = entry

        try:
            result = handler(command)
            ResultEnvelope.from_dict(result.to_dict(), owner=command)
        except ContractViolation as error:
            result = ResultEnvelope.failure(
                owner=command, error=error.error, observed_at=observed_at
            )
        except Exception:
            result = ResultEnvelope.failure(
                owner=command,
                error=ContractError(
                    code=ErrorCode.INTERNAL,
                    reason="COMMAND_HANDLER_FAILED",
                    message="command handler failed",
                    retriable=False,
                    correlation_id=command.correlation_id,
                    _details=_freeze_object({}, "error.details"),
                ),
                observed_at=observed_at,
            )
        with self._condition:
            entry.result = result
            entry.pending = False
            self._condition.notify_all()
        return result


@dataclass(frozen=True, slots=True)
class EventApplyResult:
    status: EventApplyStatus
    error: ContractError | None = None
    applied_event_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class _EventStreamState:
    next_seq: int = 0
    applied_by_seq: dict[int, EventEnvelope] = field(default_factory=dict)
    quarantined_by_seq: dict[int, EventEnvelope] = field(default_factory=dict)
    poisoned_seq: set[int] = field(default_factory=set)


_INITIAL_LIFECYCLE_STATES: Final = MappingProxyType(
    {
        IdentityKind.INTERACTION: "open",
        IdentityKind.TURN: "capturing",
        IdentityKind.RESPONSE: "accepted",
        IdentityKind.ROUND: "accepted",
        IdentityKind.TASK: "accepted",
        IdentityKind.ATTEMPT: "accepted",
    }
)
_PROJECTION_ERROR_REASONS: Final = frozenset(
    {
        "PROGRESS_SEQUENCE_GAP",
        "PROGRESS_SEQUENCE_REUSED",
        "PROGRESS_SOURCE_ALREADY_PROJECTED",
        "PROGRESS_SOURCE_ORDER_MISMATCH",
        "PROGRESS_DETAIL_UNPROVEN",
    }
)


class EventSequenceTracker:
    """Orders producer streams and resolves only applied causal ancestry."""

    def __init__(self, identities: IdentityRegistry | None = None) -> None:
        self._lock = threading.RLock()
        self._identities = identities
        self._streams: dict[tuple[str, str, IdentityKind, str], _EventStreamState] = {}
        self._events: dict[str, EventEnvelope] = {}
        self._results: dict[str, EventApplyResult] = {}
        self._applied_ids: set[str] = set()
        self._external_causes: dict[str, tuple[ScopeRef, str]] = {}
        self._lifecycle_by_object: dict[tuple[IdentityKind, str], str] = {}
        self._scope_by_object: dict[tuple[IdentityKind, str], ScopeRef] = {}
        self._next_progress_seq: dict[tuple[ScopeRef, IdentityKind, str], int] = {}
        self._progress_source_queues: dict[
            tuple[ScopeRef, IdentityKind, str], deque[str]
        ] = {}
        self._projected_sources: set[str] = set()

    def register_applied_cause(self, command: CommandEnvelope) -> tuple[str, ...]:
        with self._lock:
            normalized = CommandEnvelope.from_dict(command.to_dict())
            cause_id = normalized.command_id
            if cause_id in self._events:
                raise _violation(
                    "CAUSATION_ID_KIND_CONFLICT",
                    "an event_id cannot also be an external command cause",
                    code=ErrorCode.PROTOCOL_VIOLATION,
                )
            metadata = (normalized.scope, normalized.correlation_id)
            existing = self._external_causes.get(cause_id)
            if existing is not None and existing != metadata:
                raise _violation(
                    "CAUSATION_SOURCE_CONFLICT",
                    "an applied command cause cannot change scope or correlation",
                    code=ErrorCode.PROTOCOL_VIOLATION,
                )
            self._external_causes[cause_id] = metadata
            return tuple(self._apply_and_drain())

    def accept(self, event: EventEnvelope) -> EventApplyResult:
        with self._lock:
            event = EventEnvelope.from_dict(
                event.to_dict(), identities=self._identities
            )
            if event.event_id in self._external_causes:
                return self._error_result(
                    EventApplyStatus.REJECTED_CONFLICT,
                    "CAUSATION_ID_KIND_CONFLICT",
                    "an external command cause cannot also be an event_id",
                )
            existing = self._events.get(event.event_id)
            if existing is not None:
                prior = self._results[event.event_id]
                if existing.canonical_bytes() != event.canonical_bytes():
                    result = self._error_result(
                        EventApplyStatus.REJECTED_CONFLICT,
                        "EVENT_ID_CONFLICT",
                        "event_id was reused with different content",
                    )
                    if event.event_id not in self._applied_ids:
                        existing_stream = self._streams.get(existing.stream_key)
                        if existing_stream is not None:
                            existing_stream.quarantined_by_seq.pop(existing.seq, None)
                            existing_stream.poisoned_seq.add(existing.seq)
                        self._results[event.event_id] = result
                    return result
                duplicate_status = (
                    EventApplyStatus.DUPLICATE_APPLIED
                    if event.event_id in self._applied_ids
                    else EventApplyStatus.DUPLICATE_QUARANTINED
                )
                return EventApplyResult(duplicate_status, prior.error)

            self._events[event.event_id] = event
            cycle_error = self._causal_cycle(event)
            if cycle_error is not None:
                result = self._error_result(
                    EventApplyStatus.REJECTED_CAUSATION,
                    "CAUSATION_CYCLE",
                    cycle_error,
                )
                self._results[event.event_id] = result
                return result

            stream = self._streams.setdefault(event.stream_key, _EventStreamState())
            prior_at_seq = stream.applied_by_seq.get(event.seq)
            prior_at_seq = prior_at_seq or stream.quarantined_by_seq.get(event.seq)
            if prior_at_seq is not None:
                stream.quarantined_by_seq.pop(event.seq, None)
                stream.poisoned_seq.add(event.seq)
                result = self._error_result(
                    EventApplyStatus.REJECTED_CONFLICT,
                    "EVENT_SEQUENCE_CONFLICT",
                    "two different events claim the same producer stream sequence",
                )
                self._results[event.event_id] = result
                return result
            if event.seq < stream.next_seq or event.seq in stream.poisoned_seq:
                result = self._error_result(
                    EventApplyStatus.REJECTED_CONFLICT,
                    "EVENT_SEQUENCE_REUSED",
                    "producer stream sequence was already consumed or poisoned",
                )
                self._results[event.event_id] = result
                return result

            stream.quarantined_by_seq[event.seq] = event
            if event.seq > stream.next_seq:
                result = self._error_result(
                    EventApplyStatus.QUARANTINED_GAP,
                    "EVENT_SEQUENCE_GAP",
                    f"expected sequence {stream.next_seq}, received {event.seq}",
                )
                self._results[event.event_id] = result
                return result

            causal_error = self._causal_block(event)
            if causal_error is not None:
                if causal_error[2]:
                    del stream.quarantined_by_seq[event.seq]
                    stream.poisoned_seq.add(event.seq)
                    result = self._error_result(
                        (
                            EventApplyStatus.REJECTED_PROJECTION
                            if causal_error[0] in _PROJECTION_ERROR_REASONS
                            else EventApplyStatus.REJECTED_CAUSATION
                        ),
                        causal_error[0],
                        causal_error[1],
                    )
                    self._results[event.event_id] = result
                    return result
                result = self._error_result(
                    (
                        EventApplyStatus.QUARANTINED_PROJECTION
                        if causal_error[0] == "PROGRESS_SEQUENCE_GAP"
                        else EventApplyStatus.QUARANTINED_CAUSATION
                    ),
                    causal_error[0],
                    causal_error[1],
                )
                self._results[event.event_id] = result
                return result

            lifecycle_error = self._lifecycle_error(event)
            if lifecycle_error is not None:
                del stream.quarantined_by_seq[event.seq]
                stream.poisoned_seq.add(event.seq)
                result = EventApplyResult(
                    EventApplyStatus.REJECTED_LIFECYCLE, lifecycle_error
                )
                self._results[event.event_id] = result
                return result

            applied = self._apply_and_drain()
            current = self._results.get(event.event_id)
            if event.event_id not in self._applied_ids and current is not None:
                return current
            result = EventApplyResult(
                EventApplyStatus.APPLIED, applied_event_ids=tuple(applied)
            )
            self._results[event.event_id] = result
            return result

    @staticmethod
    def _error_result(
        status: EventApplyStatus, reason: str, message: str
    ) -> EventApplyResult:
        return EventApplyResult(
            status,
            ContractError(
                code=ErrorCode.PROTOCOL_VIOLATION,
                reason=reason,
                message=message,
                retriable=status
                in {
                    EventApplyStatus.QUARANTINED_GAP,
                    EventApplyStatus.QUARANTINED_CAUSATION,
                    EventApplyStatus.QUARANTINED_PROJECTION,
                },
                correlation_id=None,
                _details=_freeze_object({}, "error.details"),
            ),
        )

    def _causal_cycle(self, event: EventEnvelope) -> str | None:
        seen = {event.event_id}
        cursor = event.causation_id
        while cursor is not None:
            if cursor in seen:
                return "event causation must be acyclic"
            seen.add(cursor)
            ancestor = self._events.get(cursor)
            if ancestor is None:
                return None
            cursor = ancestor.causation_id
        return None

    def _causal_block(self, event: EventEnvelope) -> tuple[str, str, bool] | None:
        if event.causation_id is None:
            return None
        source = self._events.get(event.causation_id)
        external = self._external_causes.get(event.causation_id)
        if source is None and external is not None:
            source_scope, source_correlation_id = external
            mismatch = self._causal_context_error(
                event, source_scope, source_correlation_id
            )
            if mismatch is not None:
                return mismatch
            if _EVENT_RULES[event.event_type].adapter:
                return (
                    "ADAPTER_SOURCE_EVENT_REQUIRED",
                    "adapter events must reference an authoritative source event",
                    True,
                )
            return None
        if source is None or source.event_id not in self._applied_ids:
            return (
                "CAUSATION_NOT_APPLIED",
                "causation_id must reference an already applied event",
                False,
            )
        mismatch = self._causal_context_error(
            event, source.scope, source.correlation_id
        )
        if mismatch is not None:
            return mismatch
        rule = _EVENT_RULES[event.event_type]
        if rule.adapter:
            if source.producer.authority == "adapter":
                return (
                    "ADAPTER_SOURCE_NOT_AUTHORITATIVE",
                    "adapter events cannot establish authority for another adapter event",
                    True,
                )
            if rule.progress:
                progress = WorkProgressEventV2.from_dict(
                    event.payload, scope=event.scope
                )
                source_outcome = source.payload.get("outcome")
                if (
                    progress.source.event_id != source.event_id
                    or progress.source.authority.value != source.producer.authority
                    or progress.source.source_work_ref != source.stream_ref
                    or progress.state.value != source.payload.get("state")
                    or (None if progress.outcome is None else progress.outcome.value)
                    != source_outcome
                ):
                    return (
                        "PROGRESS_SOURCE_MISMATCH",
                        "WorkProgress must preserve source identity, authority, state, and outcome",
                        True,
                    )
                expected_progress_seq = self._next_progress_seq.get(
                    (event.scope, progress.work_ref.kind, progress.work_ref.id), 0
                )
                if progress.seq != expected_progress_seq:
                    if progress.seq > expected_progress_seq:
                        return (
                            "PROGRESS_SEQUENCE_GAP",
                            "WorkProgress projection sequence is waiting for an earlier event",
                            False,
                        )
                    return (
                        "PROGRESS_SEQUENCE_REUSED",
                        "WorkProgress projection sequence was already consumed",
                        True,
                    )
                if source.event_id in self._projected_sources:
                    return (
                        "PROGRESS_SOURCE_ALREADY_PROJECTED",
                        "one authoritative source event can produce only one WorkProgress projection",
                        True,
                    )
                source_queue = self._progress_source_queues.get(
                    source.progress_source_key
                )
                if source_queue is None or not source_queue:
                    return (
                        "PROGRESS_SOURCE_ORDER_MISMATCH",
                        "WorkProgress source has no pending authoritative position",
                        True,
                    )
                if source_queue[0] != source.event_id:
                    return (
                        "PROGRESS_SOURCE_ORDER_MISMATCH",
                        "WorkProgress must preserve authoritative source application order",
                        True,
                    )
                if (
                    progress.summary.knowledge is Knowledge.KNOWN
                    or progress.blocking_question.knowledge is Knowledge.KNOWN
                    or progress.artifact_refs.knowledge is Knowledge.KNOWN
                    or progress.urgency is not WorkUrgency.UNKNOWN
                    or progress.speakability is not Speakability.NOT_SPEAKABLE
                ):
                    return (
                        "PROGRESS_DETAIL_UNPROVEN",
                        "current source event schema cannot prove WorkProgress detail or notification hints",
                        True,
                    )
            else:
                source_type = event.payload["source_event_type"]
                if source_type != source.event_type:
                    return (
                        "ADAPTER_SOURCE_TYPE_MISMATCH",
                        "adapter source_event_type must match the causal source event",
                        True,
                    )
        return None

    @staticmethod
    def _causal_context_error(
        event: EventEnvelope, source_scope: ScopeRef, source_correlation_id: str
    ) -> tuple[str, str, bool] | None:
        if event.scope != source_scope:
            return (
                "CAUSATION_SCOPE_MISMATCH",
                "a derived event must have the same scope as its immediate cause",
                True,
            )
        if event.correlation_id != source_correlation_id:
            return (
                "CAUSATION_CORRELATION_MISMATCH",
                "a derived event must have the same correlation_id as its immediate cause",
                True,
            )
        return None

    def _lifecycle_error(self, event: EventEnvelope) -> ContractError | None:
        if not _EVENT_RULES[event.event_type].lifecycle:
            return None
        initial = _INITIAL_LIFECYCLE_STATES.get(event.stream_ref.kind)
        if initial is None:
            return None
        object_key = (event.stream_ref.kind, event.stream_ref.id)
        object_scope = self._scope_by_object.get(object_key)
        if object_scope is not None and object_scope != event.scope:
            return _violation(
                "LIFECYCLE_SCOPE_MISMATCH",
                "lifecycle identity cannot change scope",
                code=ErrorCode.PROTOCOL_VIOLATION,
            ).error
        state = event.payload.get("state")
        assert isinstance(state, str)
        outcome = event.payload.get("outcome")
        assert outcome is None or isinstance(outcome, str)
        current_state = self._lifecycle_by_object.get(object_key)
        if current_state is None:
            if state == initial:
                return None
            return _violation(
                "INVALID_INITIAL_LIFECYCLE_STATE",
                f"{event.stream_ref.kind.value} must begin at {initial!r}",
                code=ErrorCode.PROTOCOL_VIOLATION,
            ).error
        try:
            validate_transition(
                LifecycleKind(event.stream_ref.kind.value),
                current_state,
                state,
                outcome=outcome,
            )
        except ContractViolation as error:
            return ContractError(
                code=ErrorCode.PROTOCOL_VIOLATION,
                reason=error.error.reason,
                message=error.error.message,
                retriable=False,
                correlation_id=event.correlation_id,
                _details=_freeze_object(error.error.details, "error.details"),
            )
        return None

    def _apply_and_drain(self) -> list[str]:
        applied: list[str] = []
        made_progress = True
        while made_progress:
            made_progress = False
            for _key, stream in tuple(self._streams.items()):
                if stream.next_seq in stream.poisoned_seq:
                    continue
                candidate = stream.quarantined_by_seq.get(stream.next_seq)
                if candidate is None:
                    continue
                causal_error = self._causal_block(candidate)
                if causal_error is not None:
                    if causal_error[2]:
                        del stream.quarantined_by_seq[stream.next_seq]
                        stream.poisoned_seq.add(stream.next_seq)
                        self._results[candidate.event_id] = self._error_result(
                            (
                                EventApplyStatus.REJECTED_PROJECTION
                                if causal_error[0] in _PROJECTION_ERROR_REASONS
                                else EventApplyStatus.REJECTED_CAUSATION
                            ),
                            causal_error[0],
                            causal_error[1],
                        )
                    continue
                lifecycle_error = self._lifecycle_error(candidate)
                if lifecycle_error is not None:
                    del stream.quarantined_by_seq[stream.next_seq]
                    stream.poisoned_seq.add(stream.next_seq)
                    self._results[candidate.event_id] = EventApplyResult(
                        EventApplyStatus.REJECTED_LIFECYCLE,
                        lifecycle_error,
                    )
                    continue
                del stream.quarantined_by_seq[stream.next_seq]
                stream.applied_by_seq[stream.next_seq] = candidate
                stream.next_seq += 1
                state = candidate.payload.get("state")
                if _EVENT_RULES[candidate.event_type].lifecycle and isinstance(
                    state, str
                ):
                    object_key = (
                        candidate.stream_ref.kind,
                        candidate.stream_ref.id,
                    )
                    self._lifecycle_by_object[object_key] = state
                    self._scope_by_object[object_key] = candidate.scope
                    if candidate.stream_ref.kind in {
                        IdentityKind.ROUND,
                        IdentityKind.TASK,
                        IdentityKind.ATTEMPT,
                    }:
                        self._progress_source_queues.setdefault(
                            candidate.progress_source_key, deque()
                        ).append(candidate.event_id)
                if _EVENT_RULES[candidate.event_type].progress:
                    progress = WorkProgressEventV2.from_dict(
                        candidate.payload, scope=candidate.scope
                    )
                    progress_key = (
                        candidate.scope,
                        progress.work_ref.kind,
                        progress.work_ref.id,
                    )
                    self._next_progress_seq[progress_key] = progress.seq + 1
                    source_event = self._events[progress.source.event_id]
                    source_queue = self._progress_source_queues[
                        source_event.progress_source_key
                    ]
                    source_event_id = source_queue.popleft()
                    assert source_event_id == progress.source.event_id
                    self._projected_sources.add(source_event_id)
                self._applied_ids.add(candidate.event_id)
                self._results[candidate.event_id] = EventApplyResult(
                    EventApplyStatus.APPLIED,
                    applied_event_ids=(candidate.event_id,),
                )
                applied.append(candidate.event_id)
                made_progress = True
        return applied


def classify_contract(payload: object) -> str:
    data = _strict_object(payload, field_name="contract")
    version = data.get("contract_version")
    if version == CONTRACT_VERSION:
        return "v2"
    if version == V1_CONTRACT_VERSION:
        return "v1"
    raise _violation(
        "UNSUPPORTED_CONTRACT_VERSION",
        "payload is neither the v1 nor v2 contract",
        code=ErrorCode.UNSUPPORTED,
    )


def parse_v2_envelope(
    payload: object,
    *,
    identities: IdentityRegistry | None = None,
    commits: TurnCommitLedger | None = None,
) -> CommandEnvelope | QueryEnvelope | ResultEnvelope | EventEnvelope:
    data = _strict_object(payload, field_name="envelope")
    if data.get("contract_version") != CONTRACT_VERSION:
        raise _violation(
            "UNSUPPORTED_CONTRACT_VERSION",
            f"expected {CONTRACT_VERSION}",
            code=ErrorCode.UNSUPPORTED,
        )
    if "command_type" in data:
        return CommandEnvelope.from_dict(data, identities=identities, commits=commits)
    if "query_type" in data:
        return QueryEnvelope.from_dict(data, identities=identities)
    if "event_type" in data:
        return EventEnvelope.from_dict(data, identities=identities)
    if "ok" in data:
        return ResultEnvelope.from_dict(data)
    raise _violation("UNKNOWN_ENVELOPE_KIND", "cannot identify v2 envelope kind")


__all__ = [
    "Assurance",
    "Availability",
    "CancelScope",
    "CapabilityDescriptor",
    "CapabilityRegistry",
    "CommandEnvelope",
    "CommandResultLedger",
    "ConnectionEpochRef",
    "ContextRedaction",
    "ContextRef",
    "ContextRevision",
    "ContextRevisionKind",
    "CONTRACT_VERSION",
    "ContractError",
    "ContractViolation",
    "ErrorCode",
    "EventApplyResult",
    "EventApplyStatus",
    "EventEnvelope",
    "EventSequenceTracker",
    "IdentityKind",
    "IdentityRecord",
    "IdentityRef",
    "IdentityRegistry",
    "InputCommitState",
    "Knowledge",
    "KnownFact",
    "LifecycleKind",
    "MAX_SAFE_INTEGER",
    "OriginRef",
    "ProducerRef",
    "QueryEnvelope",
    "ResponseFence",
    "ResponseRef",
    "ResultEnvelope",
    "ScopeRef",
    "SideEffectTarget",
    "TerminalOutcome",
    "TurnCommit",
    "TurnCommitLedger",
    "V1_CONTRACT_VERSION",
    "Speakability",
    "WorkProgressEventV2",
    "WorkProgressSource",
    "WorkSourceAuthority",
    "WorkState",
    "WorkUrgency",
    "canonical_json",
    "canonical_json_bytes",
    "classify_contract",
    "default_barge_in_scopes",
    "dispatch_cancel",
    "dispatch_committed_input",
    "parse_v2_envelope",
    "validate_transition",
]
