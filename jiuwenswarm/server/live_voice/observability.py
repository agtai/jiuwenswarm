# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Fail-safe correlated observability primitives for Live Voice.

This module is an evidence plane, never a lifecycle or mutation authority.  Its
closed records have no content/audio/credential/URL fields or arbitrary attribute
maps. Opaque ID slots use a bounded carrier, but content safety still requires
callers to project authoritative public identity fields rather than user text.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from types import MappingProxyType
from typing import Final, TypeAlias


OBSERVABILITY_SCHEMA_VERSION: Final = "live-voice.observability.v1"
LIVE_VOICE_CONTRACT_VERSION: Final = "live-voice.contract.v2"
MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991
DEFAULT_COLLECTOR_CAPACITY: Final = 2_048
IDENTITY_MAX_LENGTH: Final = 128

ROUTE_IMPLEMENTATION_CLASSES: Final = (
    "formal",
    "fallback",
    "demo_substitute",
    "unsupported",
    "unknown",
)

CANCEL_SCOPES: Final = (
    "playback.stop",
    "response.cancel",
    "round.cancel",
    "task.cancel",
)

SEGMENT_NAMES: Final = (
    "speech.capture",
    "speech.recognition",
    "speech.synthesis",
    "speech.playout",
    "runtime.turn",
    "runtime.response",
    "runtime.presentation",
    "runtime.queue",
    "agent.dispatch",
    "agent.progress",
    "agent.queue",
    "task.command",
    "task.attempt",
    "task.progress",
    "task.queue",
    "route.fallback",
    "system.degradation",
)

EVENT_NAMES: Final = (
    "route.selected",
    "segment.started",
    "segment.completed",
    "segment.failed",
    "speech.capture_state",
    "speech.playout_state",
    "speech.device_change",
    "queue.pressure",
    "cancel.requested",
    "cancel.acknowledged",
    "cancel.terminal",
    "cancel.result_unknown",
    "fence.stale_dropped",
    "task.state_observed",
    "task.dispatch_outbox_observed",
    "task.cancel_outbox_observed",
    "degradation.activated",
    "degradation.recovered",
    "failure.observed",
)

OBSERVED_STATES: Final = (
    "idle",
    "starting",
    "active",
    "stopping",
    "stopped",
    "locked",
    "ready",
    "playing",
    "closed",
    "pending",
    "claimed",
    "delivered",
    "suppressed",
    "accepted",
    "running",
    "blocked",
    "decision_required",
    "terminal",
    "failed",
)

TERMINAL_OUTCOMES: Final = (
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "unknown",
)

ERROR_CODES: Final = (
    "INVALID_ARGUMENT",
    "UNSUPPORTED",
    "UNAUTHENTICATED",
    "PERMISSION_DENIED",
    "NOT_FOUND",
    "CONFLICT",
    "STALE",
    "CAPABILITY_UNAVAILABLE",
    "UNAVAILABLE",
    "TIMEOUT",
    "CANCELLED",
    "PROTOCOL_VIOLATION",
    "RESULT_UNKNOWN",
    "INTERNAL",
)

REASON_CODES: Final = (
    "ROUTE_FALLBACK",
    "DEMO_SUBSTITUTE",
    "UNSUPPORTED_CAPABILITY",
    "UNKNOWN_PROVENANCE",
    "QUEUE_CAPACITY",
    "CANCEL_REQUESTED",
    "CANCEL_ACKNOWLEDGED",
    "CANCEL_TERMINAL",
    "CANCEL_RESULT_UNKNOWN",
    "STALE_GENERATION",
    "PROVIDER_FAILURE",
    "AGENT_FAILURE",
    "TASK_FAILURE",
    "TIMEOUT",
    "UNAVAILABLE",
    "PROTOCOL_REJECTED",
    "DEGRADED",
    "RECOVERED",
    "DEVICE_CHANGED",
    "DEVICE_ENUMERATION_FAILED",
)

METRIC_DEFINITIONS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "live_voice.segment_latency_ms": ("histogram", "milliseconds"),
        "live_voice.queue_depth": ("gauge", "items"),
        "live_voice.queue_wait_ms": ("histogram", "milliseconds"),
        "live_voice.cancel_total": ("counter", "count"),
        "live_voice.stale_fence_total": ("counter", "count"),
        "live_voice.task_total": ("counter", "count"),
        "live_voice.failure_total": ("counter", "count"),
        "live_voice.degradation_total": ("counter", "count"),
    }
)

_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_OPAQUE_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_SENSITIVE_IDENTITY_MARKER = re.compile(
    r"(?:^|[._:@-])(?:api[_-]?key|authorization|bearer|credential|password|passwd|secret|token|transcript)(?:$|[._:@-])",
    re.IGNORECASE,
)
_UTC_TIMESTAMP = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?Z$"
)
_PRIVATE_SCHEME_URL = re.compile(r"[a-z][a-z0-9+.-]{0,31}://", re.IGNORECASE)
_PRIVATE_SCHEME_VALUE = re.compile(r"^[a-z][a-z0-9+.-]{0,31}:", re.IGNORECASE)
_PRIVATE_NON_HIERARCHICAL_URL = re.compile(
    r"\b(?:blob|data|file|javascript|mailto|sftp|ssh|tel|urn):", re.IGNORECASE
)
_PRIVATE_CONTENT_PATTERN = re.compile(
    r"\bbearer\s+[a-z0-9._~+/-]+"
    r"|\b(?:sk|ghp|glpat)-?[a-z0-9_-]{8,}\b"
    r"|\beyj[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+\b"
    r"|(?:^|[._:@/-])(?:transcript|raw[-_]?audio|audio[-_]?bytes|data[-_]?base64"
    r"|authorization|credential|password|passwd|secret|api[-_]?key"
    r"|device[-_]?id|hardware[-_]?id|microphone[-_]?id)(?:$|[._:@/=?#-])",
    re.IGNORECASE,
)
_ROUTE_REASON = {
    "fallback": "ROUTE_FALLBACK",
    "demo_substitute": "DEMO_SUBSTITUTE",
    "unsupported": "UNSUPPORTED_CAPABILITY",
    "unknown": "UNKNOWN_PROVENANCE",
}
_FAILURE_REASONS = {
    "PROVIDER_FAILURE",
    "AGENT_FAILURE",
    "TASK_FAILURE",
    "TIMEOUT",
    "UNAVAILABLE",
    "PROTOCOL_REJECTED",
}
_QUEUE_SEGMENTS = {"runtime.queue", "agent.queue", "task.queue"}
_SOURCE_FACTS = (
    "source_event_id",
    "source_record_id",
    "source_occurred_at",
    "source_seq",
)
_EVENT_FACTS = _SOURCE_FACTS + (
    "state",
    "outcome",
    "reason_code",
    "error_code",
    "duration_ms",
    "queue_depth",
    "queue_capacity",
    "cancel_scope",
)
_METRIC_DIMENSIONS = ("outcome", "reason_code", "error_code", "cancel_scope")
_LIFECYCLE_SEGMENTS = (
    "speech.capture",
    "speech.recognition",
    "speech.synthesis",
    "speech.playout",
    "runtime.turn",
    "runtime.response",
    "runtime.presentation",
    "runtime.queue",
    "agent.dispatch",
    "agent.progress",
    "agent.queue",
    "task.command",
    "task.attempt",
    "task.progress",
    "task.queue",
)
_LATENCY_SEGMENTS = tuple(
    segment
    for segment in _LIFECYCLE_SEGMENTS
    if segment not in {"runtime.queue", "agent.queue", "task.queue"}
)
_CANCEL_SEGMENTS = (
    "speech.playout",
    "runtime.response",
    "agent.progress",
    "task.command",
)
_FAILURE_SEGMENTS = (
    "speech.capture",
    "speech.recognition",
    "speech.synthesis",
    "speech.playout",
    "runtime.turn",
    "runtime.response",
    "runtime.presentation",
    "agent.dispatch",
    "agent.progress",
    "task.command",
    "task.attempt",
    "task.progress",
    "task.queue",
)
FAILURE_ERROR_MATRIX: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "PROVIDER_FAILURE": tuple(
            code
            for code in ERROR_CODES
            if code not in {"STALE", "CANCELLED", "RESULT_UNKNOWN"}
        ),
        "AGENT_FAILURE": tuple(
            code
            for code in ERROR_CODES
            if code not in {"STALE", "CANCELLED", "RESULT_UNKNOWN"}
        ),
        "TASK_FAILURE": tuple(
            code
            for code in ERROR_CODES
            if code not in {"STALE", "CANCELLED", "RESULT_UNKNOWN"}
        ),
        "TIMEOUT": ("TIMEOUT",),
        "UNAVAILABLE": ("CAPABILITY_UNAVAILABLE", "UNAVAILABLE"),
        "PROTOCOL_REJECTED": (
            "INVALID_ARGUMENT",
            "UNSUPPORTED",
            "CONFLICT",
            "STALE",
            "PROTOCOL_VIOLATION",
        ),
    }
)
FAILURE_SEGMENT_MATRIX: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "PROVIDER_FAILURE": tuple(
            segment for segment in _FAILURE_SEGMENTS if segment.startswith("speech.")
        ),
        "AGENT_FAILURE": ("agent.dispatch", "agent.progress"),
        "TASK_FAILURE": tuple(
            segment for segment in _FAILURE_SEGMENTS if segment.startswith("task.")
        ),
        "TIMEOUT": _FAILURE_SEGMENTS,
        "UNAVAILABLE": _FAILURE_SEGMENTS,
        "PROTOCOL_REJECTED": _FAILURE_SEGMENTS,
    }
)


def _semantic_rule(
    *,
    segments: tuple[str, ...],
    required: tuple[str, ...] = (),
    allowed: tuple[str, ...] = (),
    bindings: tuple[str, ...] = (),
    source_kind: str = "optional",
    states: tuple[str, ...] = (),
    outcomes: tuple[str, ...] = (),
    reasons: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    cancel_scopes: tuple[str, ...] = (),
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "segments": segments,
            "required_facts": required,
            "allowed_facts": allowed,
            "required_bindings": bindings,
            "source_kind": source_kind,
            "states": states,
            "outcomes": outcomes,
            "reasons": reasons,
            "errors": errors,
            "cancel_scopes": cancel_scopes,
        }
    )


EVENT_SEMANTIC_MATRIX: Final[Mapping[str, Mapping[str, object]]] = MappingProxyType(
    {
        "route.selected": _semantic_rule(
            segments=SEGMENT_NAMES,
            allowed=("source_record_id", "reason_code"),
            source_kind="optional",
            reasons=(
                "ROUTE_FALLBACK",
                "DEMO_SUBSTITUTE",
                "UNSUPPORTED_CAPABILITY",
                "UNKNOWN_PROVENANCE",
            ),
        ),
        "segment.started": _semantic_rule(
            segments=_LIFECYCLE_SEGMENTS,
            allowed=_SOURCE_FACTS,
        ),
        "segment.completed": _semantic_rule(
            segments=_LIFECYCLE_SEGMENTS,
            required=("outcome", "duration_ms"),
            allowed=_SOURCE_FACTS + ("state", "outcome", "duration_ms"),
            states=("terminal",),
            outcomes=("completed",),
        ),
        "segment.failed": _semantic_rule(
            segments=_LIFECYCLE_SEGMENTS,
            required=("outcome", "reason_code", "error_code", "duration_ms"),
            allowed=_SOURCE_FACTS
            + ("state", "outcome", "reason_code", "error_code", "duration_ms"),
            states=("terminal", "failed"),
            outcomes=("failed",),
            reasons=tuple(sorted(_FAILURE_REASONS)),
            errors=ERROR_CODES,
        ),
        "speech.capture_state": _semantic_rule(
            segments=("speech.capture",),
            required=("state",),
            allowed=_SOURCE_FACTS + ("state", "reason_code", "error_code"),
            states=("idle", "starting", "active", "stopping", "stopped", "failed"),
            reasons=("UNAVAILABLE",),
            errors=("UNAVAILABLE",),
        ),
        "speech.playout_state": _semantic_rule(
            segments=("speech.playout",),
            required=("state",),
            allowed=_SOURCE_FACTS + ("state", "reason_code", "error_code"),
            states=("locked", "ready", "playing", "stopped", "failed", "closed"),
            reasons=("UNAVAILABLE",),
            errors=("UNAVAILABLE",),
        ),
        "speech.device_change": _semantic_rule(
            segments=("speech.capture",),
            required=("reason_code",),
            allowed=_SOURCE_FACTS + ("reason_code", "error_code"),
            reasons=("DEVICE_CHANGED", "DEVICE_ENUMERATION_FAILED"),
            errors=("UNAVAILABLE",),
        ),
        "queue.pressure": _semantic_rule(
            segments=("runtime.queue", "agent.queue", "task.queue"),
            required=("reason_code", "queue_depth", "queue_capacity"),
            allowed=_SOURCE_FACTS + ("reason_code", "queue_depth", "queue_capacity"),
            reasons=("QUEUE_CAPACITY",),
        ),
        "cancel.requested": _semantic_rule(
            segments=_CANCEL_SEGMENTS,
            required=("reason_code", "cancel_scope"),
            allowed=_SOURCE_FACTS + ("reason_code", "cancel_scope"),
            reasons=("CANCEL_REQUESTED",),
            cancel_scopes=CANCEL_SCOPES,
        ),
        "cancel.acknowledged": _semantic_rule(
            segments=_CANCEL_SEGMENTS,
            required=("reason_code", "cancel_scope"),
            allowed=_SOURCE_FACTS + ("reason_code", "cancel_scope"),
            reasons=("CANCEL_ACKNOWLEDGED",),
            cancel_scopes=CANCEL_SCOPES,
        ),
        "cancel.terminal": _semantic_rule(
            segments=_CANCEL_SEGMENTS,
            required=("outcome", "reason_code", "cancel_scope"),
            allowed=_SOURCE_FACTS + ("outcome", "reason_code", "cancel_scope"),
            outcomes=("cancelled",),
            reasons=("CANCEL_TERMINAL",),
            cancel_scopes=CANCEL_SCOPES,
        ),
        "cancel.result_unknown": _semantic_rule(
            segments=_CANCEL_SEGMENTS,
            required=("outcome", "reason_code", "error_code", "cancel_scope"),
            allowed=_SOURCE_FACTS
            + ("outcome", "reason_code", "error_code", "cancel_scope"),
            outcomes=("unknown",),
            reasons=("CANCEL_RESULT_UNKNOWN",),
            errors=("RESULT_UNKNOWN",),
            cancel_scopes=CANCEL_SCOPES,
        ),
        "fence.stale_dropped": _semantic_rule(
            segments=("runtime.presentation",),
            required=("reason_code", "error_code"),
            allowed=_SOURCE_FACTS + ("reason_code", "error_code"),
            bindings=("response_id",),
            reasons=("STALE_GENERATION",),
            errors=("STALE",),
        ),
        "task.state_observed": _semantic_rule(
            segments=("task.progress",),
            required=(
                "source_event_id",
                "source_occurred_at",
                "source_seq",
                "state",
            ),
            allowed=(
                "source_event_id",
                "source_occurred_at",
                "source_seq",
                "state",
                "outcome",
                "reason_code",
            ),
            bindings=("task_id", "attempt_id"),
            source_kind="event",
            states=("accepted", "running", "blocked", "decision_required", "terminal"),
            outcomes=TERMINAL_OUTCOMES,
            reasons=("TASK_FAILURE", "CANCEL_TERMINAL"),
        ),
        "task.dispatch_outbox_observed": _semantic_rule(
            segments=("task.queue",),
            required=("source_record_id", "source_seq", "state"),
            allowed=("source_record_id", "source_seq", "state"),
            bindings=("task_id", "attempt_id"),
            source_kind="record",
            states=("pending", "claimed", "delivered", "suppressed"),
        ),
        "task.cancel_outbox_observed": _semantic_rule(
            segments=("task.queue",),
            required=("source_record_id", "source_seq", "state"),
            allowed=("source_record_id", "source_seq", "state"),
            bindings=("task_id", "attempt_id"),
            source_kind="record",
            states=("pending", "claimed", "delivered", "suppressed"),
        ),
        "degradation.activated": _semantic_rule(
            segments=("system.degradation",),
            required=("reason_code",),
            allowed=_SOURCE_FACTS + ("reason_code",),
            reasons=("DEGRADED",),
        ),
        "degradation.recovered": _semantic_rule(
            segments=("system.degradation",),
            required=("reason_code",),
            allowed=_SOURCE_FACTS + ("reason_code",),
            reasons=("RECOVERED",),
        ),
        "failure.observed": _semantic_rule(
            segments=_FAILURE_SEGMENTS,
            required=("reason_code", "error_code"),
            allowed=_SOURCE_FACTS + ("reason_code", "error_code"),
            reasons=tuple(sorted(_FAILURE_REASONS)),
            errors=ERROR_CODES,
        ),
    }
)


def _metric_rule(
    *,
    segments: tuple[str, ...],
    required: tuple[str, ...] = (),
    allowed: tuple[str, ...] = (),
    bindings: tuple[str, ...] = (),
    outcomes: tuple[str, ...] = (),
    reasons: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    cancel_scopes: tuple[str, ...] = (),
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "segments": segments,
            "required_dimensions": required,
            "allowed_dimensions": allowed,
            "required_bindings": bindings,
            "outcomes": outcomes,
            "reasons": reasons,
            "errors": errors,
            "cancel_scopes": cancel_scopes,
        }
    )


METRIC_SEMANTIC_MATRIX: Final[Mapping[str, Mapping[str, object]]] = MappingProxyType(
    {
        "live_voice.segment_latency_ms": _metric_rule(
            segments=_LATENCY_SEGMENTS,
            required=("outcome",),
            allowed=("outcome",),
            outcomes=("completed",),
        ),
        "live_voice.queue_depth": _metric_rule(
            segments=("runtime.queue", "agent.queue", "task.queue"),
        ),
        "live_voice.queue_wait_ms": _metric_rule(
            segments=("runtime.queue", "agent.queue", "task.queue"),
        ),
        "live_voice.cancel_total": _metric_rule(
            segments=_CANCEL_SEGMENTS,
            required=("reason_code", "cancel_scope"),
            allowed=("outcome", "reason_code", "error_code", "cancel_scope"),
            outcomes=("cancelled", "unknown"),
            reasons=(
                "CANCEL_REQUESTED",
                "CANCEL_ACKNOWLEDGED",
                "CANCEL_TERMINAL",
                "CANCEL_RESULT_UNKNOWN",
            ),
            errors=("RESULT_UNKNOWN",),
            cancel_scopes=CANCEL_SCOPES,
        ),
        "live_voice.stale_fence_total": _metric_rule(
            segments=("runtime.presentation",),
            required=("reason_code", "error_code"),
            allowed=("reason_code", "error_code"),
            bindings=("response_id",),
            reasons=("STALE_GENERATION",),
            errors=("STALE",),
        ),
        "live_voice.task_total": _metric_rule(
            segments=("task.progress",),
            required=("outcome",),
            allowed=("outcome", "reason_code", "error_code"),
            bindings=("task_id",),
            outcomes=("completed", "failed", "cancelled"),
            reasons=("TASK_FAILURE", "CANCEL_TERMINAL"),
            errors=ERROR_CODES,
        ),
        "live_voice.failure_total": _metric_rule(
            segments=_FAILURE_SEGMENTS,
            required=("reason_code", "error_code"),
            allowed=("reason_code", "error_code"),
            reasons=tuple(sorted(_FAILURE_REASONS)),
            errors=ERROR_CODES,
        ),
        "live_voice.degradation_total": _metric_rule(
            segments=("system.degradation",),
            required=("reason_code",),
            allowed=("reason_code",),
            reasons=("DEGRADED", "RECOVERED"),
        ),
    }
)

IDENTITY_POLICY: Final[Mapping[str, object]] = MappingProxyType(
    {
        "max_length": IDENTITY_MAX_LENGTH,
        "allowed_pattern": r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$",
        "blocked_markers": (
            "api_key",
            "authorization",
            "bearer",
            "credential",
            "password",
            "passwd",
            "secret",
            "token",
            "transcript",
        ),
        "trusted_source_boundary": "authoritative_public_identity_fields_only",
    }
)


class ObservabilityViolation(ValueError):
    """A stable validation failure for the closed observability schema."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _violation(reason: str, message: str) -> ObservabilityViolation:
    return ObservabilityViolation(reason, message)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _violation(
            "INVALID_REQUIRED_TEXT", f"{field_name} must be non-empty text"
        )
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise _violation(
            "INVALID_UNICODE_SCALAR", f"{field_name} contains invalid Unicode"
        ) from error
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _opaque_identity(value: object, field_name: str) -> str:
    """Validate a bounded carrier, not the meaning of an ACG-owned opaque ID.

    Privacy still depends on callers projecting authoritative public identity
    fields.  This envelope blocks free-text channels and obvious secret labels;
    it cannot classify an arbitrary token as intrinsically non-secret.
    """

    result = _required_text(value, field_name)
    if (
        len(result) > IDENTITY_MAX_LENGTH
        or _OPAQUE_IDENTITY.fullmatch(result) is None
        or _SENSITIVE_IDENTITY_MARKER.search(result) is not None
    ):
        raise _violation(
            "INVALID_OPAQUE_IDENTITY",
            f"{field_name} must be a bounded opaque ID from a trusted identity field",
        )
    return result


def _optional_identity(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _opaque_identity(value, field_name)


def contains_private_observability_content(
    value: object,
    *,
    field_name: str | None = None,
) -> bool:
    """Apply the product observability owner's closed private-carrier policy."""

    if isinstance(value, str):
        return (
            any(delimiter in value for delimiter in ("=", "?", "#"))
            or _PRIVATE_SCHEME_URL.search(value) is not None
            or _PRIVATE_NON_HIERARCHICAL_URL.search(value) is not None
            or (
                field_name == "contract_version"
                and _PRIVATE_SCHEME_VALUE.search(value) is not None
            )
            or _PRIVATE_CONTENT_PATTERN.search(value) is not None
        )
    if isinstance(value, Mapping):
        return any(
            contains_private_observability_content(key)
            or contains_private_observability_content(
                item,
                field_name=key if isinstance(key, str) else None,
            )
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_private_observability_content(item) for item in value)
    return False


def _token(value: object, field_name: str) -> str:
    result = _required_text(value, field_name)
    if _TOKEN.fullmatch(result) is None:
        raise _violation(
            "INVALID_STABLE_TOKEN",
            f"{field_name} must be a bounded stable identifier",
        )
    return result


def _utc_timestamp(value: object, field_name: str) -> str:
    result = _required_text(value, field_name)
    match = _UTC_TIMESTAMP.fullmatch(result)
    if match is None:
        raise _violation(
            "INVALID_UTC_TIMESTAMP", f"{field_name} must be an RFC 3339 UTC timestamp"
        )
    try:
        year, month, day, hour, minute, second = map(int, match.groups())
        if year == 0:
            raise ValueError("year zero is not supported")
        datetime(year, month, day, hour, minute, second)
    except ValueError as error:
        raise _violation(
            "INVALID_UTC_TIMESTAMP", f"{field_name} must be an RFC 3339 UTC timestamp"
        ) from error
    return result


def validate_observability_timestamp(value: object) -> str:
    """Validate one backend-visible timestamp with the canonical owner rules."""

    return _utc_timestamp(value, "observability_timestamp")


def _nonnegative_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _violation("INVALID_NUMBER", f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise _violation(
            "INVALID_NUMBER", f"{field_name} must be finite and non-negative"
        )
    return result


def _uint(value: object, field_name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_SAFE_INTEGER
    ):
        raise _violation(
            "INVALID_SAFE_INTEGER", f"{field_name} must be a non-negative safe integer"
        )
    return value


def _optional_member(
    value: object, allowed: tuple[str, ...], field_name: str
) -> str | None:
    if value is None:
        return None
    result = _required_text(value, field_name)
    if result not in allowed:
        raise _violation(
            "INVALID_VOCABULARY", f"{field_name} is not in the stable vocabulary"
        )
    return result


def _closed_dict(
    value: object,
    *,
    field_name: str,
    allowed: frozenset[str],
    required: frozenset[str],
) -> dict[str, object]:
    if type(value) is not dict:
        raise _violation("INVALID_JSON_OBJECT", f"{field_name} must be a plain object")
    result = value
    if any(not isinstance(key, str) for key in result):
        raise _violation("INVALID_OBJECT_KEY", f"{field_name} keys must be strings")
    unknown = set(result).difference(allowed)
    if unknown:
        raise _violation(
            "UNKNOWN_FIELD", f"{field_name} has unknown fields: {sorted(unknown)[0]}"
        )
    missing = required.difference(result)
    if missing:
        raise _violation(
            "MISSING_REQUIRED_FIELD",
            f"{field_name} is missing: {sorted(missing)[0]}",
        )
    return result


@dataclass(frozen=True, slots=True)
class TraceBinding:
    correlation_id: str
    interaction_id: str | None = None
    turn_id: str | None = None
    response_id: str | None = None
    response_generation: int | None = None
    round_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self) -> None:
        _opaque_identity(self.correlation_id, "binding.correlation_id")
        for field_name in (
            "interaction_id",
            "turn_id",
            "response_id",
            "round_id",
            "task_id",
            "attempt_id",
        ):
            _optional_identity(getattr(self, field_name), f"binding.{field_name}")
        if self.turn_id is not None and self.interaction_id is None:
            raise _violation(
                "TURN_INTERACTION_BINDING_REQUIRED", "turn_id requires interaction_id"
            )
        response_fields = (self.response_id, self.response_generation)
        if any(value is not None for value in response_fields):
            if self.interaction_id is None or any(
                value is None for value in response_fields
            ):
                raise _violation(
                    "RESPONSE_BINDING_INCOMPLETE",
                    "response binding requires interaction_id, response_id, and generation",
                )
            _uint(self.response_generation, "binding.response_generation")
        if self.attempt_id is not None and self.task_id is None:
            raise _violation(
                "ATTEMPT_TASK_BINDING_REQUIRED", "attempt_id requires task_id"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "interaction_id": self.interaction_id,
            "turn_id": self.turn_id,
            "response_id": self.response_id,
            "response_generation": self.response_generation,
            "round_id": self.round_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
        }


_BINDING_KEYS = frozenset(TraceBinding.__dataclass_fields__)


def create_trace_binding(value: TraceBinding | object) -> TraceBinding:
    if isinstance(value, TraceBinding):
        value = value.to_dict()
    data = _closed_dict(
        value,
        field_name="binding",
        allowed=_BINDING_KEYS,
        required=frozenset({"correlation_id"}),
    )
    return TraceBinding(**data)  # type: ignore[arg-type]


def _validate_cancel_target(cancel_scope: str, binding: TraceBinding) -> None:
    if cancel_scope in {"playback.stop", "response.cancel"}:
        if binding.response_id is None:
            raise _violation(
                "CANCEL_TARGET_BINDING_REQUIRED",
                f"{cancel_scope} requires the exact response tuple",
            )
    elif cancel_scope == "round.cancel":
        if binding.round_id is None:
            raise _violation(
                "CANCEL_TARGET_BINDING_REQUIRED",
                "round.cancel requires round_id",
            )
    elif cancel_scope == "task.cancel" and binding.task_id is None:
        raise _violation(
            "CANCEL_TARGET_BINDING_REQUIRED",
            "task.cancel requires task_id",
        )


def _validate_failure_target(
    reason_code: str, binding: TraceBinding, route: RouteDescriptor
) -> None:
    if reason_code == "PROVIDER_FAILURE" and route.capability_provider is None:
        raise _violation(
            "FAILURE_TARGET_BINDING_REQUIRED",
            "Provider failure requires exact route provider provenance",
        )
    if reason_code == "AGENT_FAILURE" and binding.round_id is None:
        raise _violation(
            "FAILURE_TARGET_BINDING_REQUIRED",
            "Agent failure requires round_id",
        )
    if reason_code == "TASK_FAILURE" and binding.task_id is None:
        raise _violation(
            "FAILURE_TARGET_BINDING_REQUIRED",
            "Task failure requires task_id",
        )


def _validate_failure_pair(reason_code: str, error_code: str) -> None:
    allowed = FAILURE_ERROR_MATRIX.get(reason_code)
    if allowed is None or error_code not in allowed:
        raise _violation(
            "FAILURE_ERROR_MISMATCH",
            "failure reason and error code do not describe the same governed failure",
        )


def _validate_failure_segment(reason_code: str, segment_name: str) -> None:
    allowed = FAILURE_SEGMENT_MATRIX.get(reason_code)
    if allowed is None or segment_name not in allowed:
        raise _violation(
            "FAILURE_SEGMENT_MISMATCH",
            "failure reason cannot describe this segment",
        )


def _validate_required_bindings(
    required: object, binding: TraceBinding, *, owner: str
) -> None:
    if not isinstance(required, tuple):
        raise _violation("INVALID_SEMANTIC_MATRIX", f"{owner} binding rule is invalid")
    for field_name in required:
        if (
            not isinstance(field_name, str)
            or getattr(binding, field_name, None) is None
        ):
            raise _violation(
                "SEMANTIC_TARGET_BINDING_REQUIRED",
                f"{owner} requires binding.{field_name}",
            )


SEGMENT_BINDING_MATRIX: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "speech.capture": ("interaction_id",),
        "speech.recognition": ("interaction_id",),
        "speech.synthesis": ("response_id",),
        "speech.playout": ("response_id",),
        "runtime.turn": ("turn_id",),
        "runtime.response": ("response_id",),
        "runtime.presentation": ("response_id",),
        "runtime.queue": (),
        "agent.dispatch": ("round_id",),
        "agent.progress": ("round_id",),
        "agent.queue": ("round_id",),
        "task.command": ("task_id",),
        "task.attempt": ("task_id", "attempt_id"),
        "task.progress": ("task_id",),
        "task.queue": ("task_id",),
    }
)


def _validate_segment_target(
    segment_name: str, binding: TraceBinding, *, owner: str
) -> None:
    _validate_required_bindings(
        SEGMENT_BINDING_MATRIX.get(segment_name, ()), binding, owner=owner
    )


CANCEL_TARGET_SEGMENT_MATRIX: Final[Mapping[str, str]] = MappingProxyType(
    {
        "playback.stop": "speech.playout",
        "response.cancel": "runtime.response",
        "round.cancel": "agent.progress",
        "task.cancel": "task.command",
    }
)


@dataclass(frozen=True, slots=True)
class RouteDescriptor:
    implementation_class: str
    owner_module: str | None
    capability_provider: str | None
    contract_version: str | None
    reason_code: str | None

    def __post_init__(self) -> None:
        if self.implementation_class not in ROUTE_IMPLEMENTATION_CLASSES:
            raise _violation(
                "INVALID_ROUTE_CLASS",
                "implementation_class is not in the route vocabulary",
            )
        if self.owner_module is not None:
            _token(self.owner_module, "route.owner_module")
        if self.capability_provider is not None:
            _token(self.capability_provider, "route.capability_provider")
        _optional_text(self.contract_version, "route.contract_version")
        _optional_member(self.reason_code, REASON_CODES, "route.reason_code")
        if self.implementation_class == "formal":
            if (
                self.owner_module is None
                or self.capability_provider is None
                or self.contract_version != LIVE_VOICE_CONTRACT_VERSION
                or self.reason_code is not None
            ):
                raise _violation(
                    "MISSING_FORMAL_PROVENANCE",
                    "formal route requires owner, provider, v2 contract, and no reason",
                )
        else:
            expected = _ROUTE_REASON[self.implementation_class]
            if self.reason_code != expected:
                raise _violation(
                    "INVALID_ROUTE_REASON",
                    "non-formal route requires its stable redacted reason code",
                )
            if self.implementation_class != "unknown" and self.owner_module is None:
                raise _violation(
                    "MISSING_ROUTE_OWNER",
                    "known non-formal route requires owner_module",
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "implementation_class": self.implementation_class,
            "owner_module": self.owner_module,
            "capability_provider": self.capability_provider,
            "contract_version": self.contract_version,
            "reason_code": self.reason_code,
        }


_ROUTE_KEYS = frozenset(RouteDescriptor.__dataclass_fields__)


def create_route_descriptor(value: RouteDescriptor | object) -> RouteDescriptor:
    if isinstance(value, RouteDescriptor):
        value = value.to_dict()
    data = _closed_dict(
        value,
        field_name="route",
        allowed=_ROUTE_KEYS,
        required=frozenset(
            {
                "implementation_class",
                "owner_module",
                "capability_provider",
                "contract_version",
                "reason_code",
            }
        ),
    )
    return RouteDescriptor(**data)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class LiveVoiceObservation:
    schema_version: str
    event_id: str
    event_name: str
    segment_name: str
    observed_at: str
    monotonic_ms: float
    binding: TraceBinding
    route: RouteDescriptor
    source_component: str
    source_event_id: str | None = None
    source_record_id: str | None = None
    source_occurred_at: str | None = None
    source_seq: int | None = None
    state: str | None = None
    outcome: str | None = None
    reason_code: str | None = None
    error_code: str | None = None
    duration_ms: float | None = None
    queue_depth: int | None = None
    queue_capacity: int | None = None
    cancel_scope: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVABILITY_SCHEMA_VERSION:
            raise _violation(
                "INVALID_SCHEMA_VERSION", "unsupported observability schema"
            )
        _opaque_identity(self.event_id, "observation.event_id")
        if self.event_name not in EVENT_NAMES:
            raise _violation("INVALID_EVENT_NAME", "event_name is not stable")
        if self.segment_name not in SEGMENT_NAMES:
            raise _violation("INVALID_SEGMENT_NAME", "segment_name is not stable")
        _utc_timestamp(self.observed_at, "observation.observed_at")
        _nonnegative_number(self.monotonic_ms, "observation.monotonic_ms")
        if not isinstance(self.binding, TraceBinding) or not isinstance(
            self.route, RouteDescriptor
        ):
            raise _violation(
                "INVALID_NESTED_RECORD", "binding and route must be validated"
            )
        _token(self.source_component, "observation.source_component")
        _optional_identity(self.source_event_id, "observation.source_event_id")
        _optional_identity(self.source_record_id, "observation.source_record_id")
        if self.source_occurred_at is not None:
            _utc_timestamp(self.source_occurred_at, "observation.source_occurred_at")
        if self.source_seq is not None:
            _uint(self.source_seq, "observation.source_seq")
        if self.source_event_id is not None and self.source_record_id is not None:
            raise _violation(
                "SOURCE_KIND_CONFLICT",
                "one observation cannot label a source as both Event and record",
            )
        if self.source_occurred_at is not None and self.source_event_id is None:
            raise _violation(
                "SOURCE_EVENT_REQUIRED",
                "source occurrence time requires source_event_id",
            )
        if (
            self.source_seq is not None
            and self.source_event_id is None
            and self.source_record_id is None
        ):
            raise _violation(
                "SOURCE_ID_REQUIRED", "source sequence requires an exact source ID"
            )
        _optional_member(self.state, OBSERVED_STATES, "observation.state")
        _optional_member(self.outcome, TERMINAL_OUTCOMES, "observation.outcome")
        _optional_member(self.reason_code, REASON_CODES, "observation.reason_code")
        _optional_member(self.error_code, ERROR_CODES, "observation.error_code")
        if self.duration_ms is not None:
            _nonnegative_number(self.duration_ms, "observation.duration_ms")
        if self.queue_depth is not None:
            _uint(self.queue_depth, "observation.queue_depth")
        if self.queue_capacity is not None:
            _uint(self.queue_capacity, "observation.queue_capacity")
        _optional_member(self.cancel_scope, CANCEL_SCOPES, "observation.cancel_scope")
        self._validate_event_semantics()

    def _validate_event_semantics(self) -> None:
        rule = EVENT_SEMANTIC_MATRIX[self.event_name]
        segments = rule["segments"]
        if not isinstance(segments, tuple) or self.segment_name not in segments:
            raise _violation(
                "EVENT_SEGMENT_MISMATCH",
                "event_name cannot describe this segment",
            )

        allowed = rule["allowed_facts"]
        required = rule["required_facts"]
        if not isinstance(allowed, tuple) or not isinstance(required, tuple):
            raise _violation("INVALID_SEMANTIC_MATRIX", "event fact rule is invalid")
        populated = {
            field_name
            for field_name in _EVENT_FACTS
            if getattr(self, field_name) is not None
        }
        forbidden = populated.difference(allowed)
        if forbidden:
            raise _violation(
                "EVENT_FACT_FORBIDDEN",
                f"{self.event_name} forbids {sorted(forbidden)[0]}",
            )
        missing = set(required).difference(populated)
        if missing:
            raise _violation(
                "EVENT_FACT_REQUIRED",
                f"{self.event_name} requires {sorted(missing)[0]}",
            )
        _validate_required_bindings(
            rule["required_bindings"], self.binding, owner=self.event_name
        )

        for field_name, rule_name in (
            ("state", "states"),
            ("outcome", "outcomes"),
            ("reason_code", "reasons"),
            ("error_code", "errors"),
            ("cancel_scope", "cancel_scopes"),
        ):
            value = getattr(self, field_name)
            allowed_values = rule[rule_name]
            if value is not None and (
                not isinstance(allowed_values, tuple) or value not in allowed_values
            ):
                raise _violation(
                    "EVENT_VALUE_MISMATCH",
                    f"{self.event_name} forbids {field_name}={value}",
                )

        if (
            self.event_name == "route.selected"
            and self.reason_code != self.route.reason_code
        ):
            raise _violation(
                "ROUTE_REASON_MISMATCH",
                "route event reason must match route provenance",
            )

        if self.event_name.startswith("segment."):
            _validate_segment_target(
                self.segment_name, self.binding, owner=self.event_name
            )

        if self.event_name in {"speech.capture_state", "speech.playout_state"}:
            failed = self.state == "failed"
            has_failure = self.reason_code is not None or self.error_code is not None
            if failed != has_failure or (
                failed
                and (
                    self.reason_code != "UNAVAILABLE"
                    or self.error_code != "UNAVAILABLE"
                )
            ):
                raise _violation(
                    "AUDIO_STATE_FACT_MISMATCH",
                    "only failed audio state carries UNAVAILABLE reason and error",
                )

        if self.event_name == "speech.device_change":
            expected_error = (
                "UNAVAILABLE"
                if self.reason_code == "DEVICE_ENUMERATION_FAILED"
                else None
            )
            if self.error_code != expected_error:
                raise _violation(
                    "DEVICE_FACT_MISMATCH",
                    "device reason and error code must describe the same event",
                )

        if self.event_name == "queue.pressure":
            if (
                self.queue_depth is None
                or self.queue_capacity is None
                or self.queue_capacity == 0
                or self.queue_depth < self.queue_capacity
            ):
                raise _violation(
                    "QUEUE_PRESSURE_INCOMPLETE",
                    "queue pressure requires a full bounded queue",
                )
            _validate_segment_target(
                self.segment_name, self.binding, owner=self.event_name
            )

        if self.event_name.startswith("cancel."):
            if self.cancel_scope is None:
                raise _violation("EVENT_FACT_REQUIRED", "cancel scope is required")
            if CANCEL_TARGET_SEGMENT_MATRIX[self.cancel_scope] != self.segment_name:
                raise _violation(
                    "CANCEL_SEGMENT_MISMATCH",
                    "cancel scope must name its exact target segment",
                )
            _validate_cancel_target(self.cancel_scope, self.binding)

        if self.event_name in {"segment.failed", "failure.observed"}:
            if self.reason_code is None or self.error_code is None:
                raise _violation("EVENT_FACT_REQUIRED", "failure facts are required")
            _validate_failure_pair(self.reason_code, self.error_code)
            _validate_failure_target(self.reason_code, self.binding, self.route)
            _validate_segment_target(
                self.segment_name, self.binding, owner=self.event_name
            )
            _validate_failure_segment(self.reason_code, self.segment_name)

        if self.event_name == "task.state_observed":
            if self.state == "terminal":
                if self.outcome is None:
                    raise _violation(
                        "TASK_TERMINAL_FACT_MISMATCH",
                        "terminal task evidence requires outcome",
                    )
                expected_reason = {
                    "failed": "TASK_FAILURE",
                    "cancelled": "CANCEL_TERMINAL",
                }.get(self.outcome)
                if self.reason_code != expected_reason:
                    raise _violation(
                        "TASK_TERMINAL_FACT_MISMATCH",
                        "task outcome and reason must describe the same terminal fact",
                    )
            elif self.outcome is not None or self.reason_code is not None:
                raise _violation(
                    "TASK_NONTERMINAL_FACT_FORBIDDEN",
                    "nonterminal task evidence cannot carry terminal facts",
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_name": self.event_name,
            "segment_name": self.segment_name,
            "observed_at": self.observed_at,
            "monotonic_ms": self.monotonic_ms,
            "binding": self.binding.to_dict(),
            "route": self.route.to_dict(),
            "source_component": self.source_component,
            "source_event_id": self.source_event_id,
            "source_record_id": self.source_record_id,
            "source_occurred_at": self.source_occurred_at,
            "source_seq": self.source_seq,
            "state": self.state,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "queue_depth": self.queue_depth,
            "queue_capacity": self.queue_capacity,
            "cancel_scope": self.cancel_scope,
        }


_OBSERVATION_KEYS = frozenset(LiveVoiceObservation.__dataclass_fields__)
_OBSERVATION_REQUIRED = frozenset(
    {
        "schema_version",
        "event_id",
        "event_name",
        "segment_name",
        "observed_at",
        "monotonic_ms",
        "binding",
        "route",
        "source_component",
    }
)


def create_observation(value: LiveVoiceObservation | object) -> LiveVoiceObservation:
    if isinstance(value, LiveVoiceObservation):
        value = value.to_dict()
    data = _closed_dict(
        value,
        field_name="observation",
        allowed=_OBSERVATION_KEYS,
        required=_OBSERVATION_REQUIRED,
    ).copy()
    data["binding"] = create_trace_binding(data["binding"])
    data["route"] = create_route_descriptor(data["route"])
    return LiveVoiceObservation(**data)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class LiveVoiceMetric:
    schema_version: str
    measurement_id: str
    metric_name: str
    metric_kind: str
    unit: str
    value: float
    observed_at: str
    binding: TraceBinding
    route: RouteDescriptor
    segment_name: str
    implementation_class: str
    outcome: str | None = None
    reason_code: str | None = None
    error_code: str | None = None
    cancel_scope: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVABILITY_SCHEMA_VERSION:
            raise _violation(
                "INVALID_SCHEMA_VERSION", "unsupported observability schema"
            )
        _opaque_identity(self.measurement_id, "metric.measurement_id")
        definition = METRIC_DEFINITIONS.get(self.metric_name)
        if definition is None:
            raise _violation("INVALID_METRIC_NAME", "metric_name is not stable")
        if (self.metric_kind, self.unit) != definition:
            raise _violation(
                "METRIC_DEFINITION_MISMATCH", "metric kind or unit is incorrect"
            )
        numeric = _nonnegative_number(self.value, "metric.value")
        if self.metric_kind == "counter" and (
            not numeric.is_integer() or numeric > MAX_SAFE_INTEGER
        ):
            raise _violation(
                "INVALID_COUNTER", "counter values must be safe whole numbers"
            )
        if self.metric_name == "live_voice.queue_depth" and (
            not numeric.is_integer() or numeric > MAX_SAFE_INTEGER
        ):
            raise _violation(
                "INVALID_ITEM_GAUGE", "queue depth values must be safe whole numbers"
            )
        _utc_timestamp(self.observed_at, "metric.observed_at")
        if not isinstance(self.binding, TraceBinding) or not isinstance(
            self.route, RouteDescriptor
        ):
            raise _violation(
                "INVALID_NESTED_RECORD", "metric binding and route must be validated"
            )
        if self.segment_name not in SEGMENT_NAMES:
            raise _violation("INVALID_SEGMENT_NAME", "segment_name is not stable")
        if self.implementation_class not in ROUTE_IMPLEMENTATION_CLASSES:
            raise _violation(
                "INVALID_ROUTE_CLASS", "implementation_class is not stable"
            )
        if self.implementation_class != self.route.implementation_class:
            raise _violation(
                "METRIC_ROUTE_CLASS_MISMATCH",
                "metric implementation class must match validated route provenance",
            )
        _optional_member(self.outcome, TERMINAL_OUTCOMES, "metric.outcome")
        _optional_member(self.reason_code, REASON_CODES, "metric.reason_code")
        _optional_member(self.error_code, ERROR_CODES, "metric.error_code")
        _optional_member(self.cancel_scope, CANCEL_SCOPES, "metric.cancel_scope")
        self._validate_metric_semantics()

    def _validate_metric_semantics(self) -> None:
        rule = METRIC_SEMANTIC_MATRIX[self.metric_name]
        segments = rule["segments"]
        if not isinstance(segments, tuple) or self.segment_name not in segments:
            raise _violation(
                "METRIC_SEGMENT_MISMATCH",
                "metric_name cannot describe this segment",
            )
        allowed = rule["allowed_dimensions"]
        required = rule["required_dimensions"]
        if not isinstance(allowed, tuple) or not isinstance(required, tuple):
            raise _violation("INVALID_SEMANTIC_MATRIX", "metric rule is invalid")
        populated = {
            field_name
            for field_name in _METRIC_DIMENSIONS
            if getattr(self, field_name) is not None
        }
        forbidden = populated.difference(allowed)
        if forbidden:
            raise _violation(
                "METRIC_DIMENSION_FORBIDDEN",
                f"{self.metric_name} forbids {sorted(forbidden)[0]}",
            )
        missing = set(required).difference(populated)
        if missing:
            raise _violation(
                "METRIC_DIMENSION_REQUIRED",
                f"{self.metric_name} requires {sorted(missing)[0]}",
            )
        _validate_required_bindings(
            rule["required_bindings"], self.binding, owner=self.metric_name
        )
        for field_name, rule_name in (
            ("outcome", "outcomes"),
            ("reason_code", "reasons"),
            ("error_code", "errors"),
            ("cancel_scope", "cancel_scopes"),
        ):
            value = getattr(self, field_name)
            allowed_values = rule[rule_name]
            if value is not None and (
                not isinstance(allowed_values, tuple) or value not in allowed_values
            ):
                raise _violation(
                    "METRIC_VALUE_MISMATCH",
                    f"{self.metric_name} forbids {field_name}={value}",
                )

        if self.metric_name == "live_voice.segment_latency_ms":
            _validate_segment_target(
                self.segment_name, self.binding, owner=self.metric_name
            )
        if self.metric_name in {"live_voice.queue_depth", "live_voice.queue_wait_ms"}:
            _validate_segment_target(
                self.segment_name, self.binding, owner=self.metric_name
            )
        if self.metric_name == "live_voice.cancel_total":
            if self.cancel_scope is None or self.reason_code is None:
                raise _violation(
                    "METRIC_DIMENSION_REQUIRED", "cancel target and reason are required"
                )
            if CANCEL_TARGET_SEGMENT_MATRIX[self.cancel_scope] != self.segment_name:
                raise _violation(
                    "CANCEL_SEGMENT_MISMATCH",
                    "cancel scope must name its exact target segment",
                )
            _validate_cancel_target(self.cancel_scope, self.binding)
            expected_terminal = {
                "CANCEL_REQUESTED": (None, None),
                "CANCEL_ACKNOWLEDGED": (None, None),
                "CANCEL_TERMINAL": ("cancelled", None),
                "CANCEL_RESULT_UNKNOWN": ("unknown", "RESULT_UNKNOWN"),
            }[self.reason_code]
            if (self.outcome, self.error_code) != expected_terminal:
                raise _violation(
                    "CANCEL_METRIC_FACT_MISMATCH",
                    "cancel reason, outcome, and error must describe one phase",
                )
        if self.metric_name == "live_voice.task_total":
            expected = {
                "completed": (None, None),
                "failed": ("TASK_FAILURE", None),
                "cancelled": ("CANCEL_TERMINAL", "CANCELLED"),
            }
            if self.outcome is None:
                raise _violation(
                    "METRIC_DIMENSION_REQUIRED", "task outcome is required"
                )
            expected_reason, exact_error = expected[self.outcome]
            if self.reason_code != expected_reason:
                raise _violation(
                    "TASK_METRIC_FACT_MISMATCH",
                    "task outcome and reason must describe one terminal fact",
                )
            if self.outcome == "failed":
                if self.error_code is None:
                    raise _violation(
                        "TASK_METRIC_FACT_MISMATCH",
                        "failed task metric requires governed error code",
                    )
                _validate_failure_pair("TASK_FAILURE", self.error_code)
            elif self.error_code != exact_error:
                raise _violation(
                    "TASK_METRIC_FACT_MISMATCH",
                    "task outcome and error must describe one terminal fact",
                )
        if self.metric_name == "live_voice.failure_total":
            if self.reason_code is None or self.error_code is None:
                raise _violation(
                    "METRIC_DIMENSION_REQUIRED", "failure facts are required"
                )
            _validate_failure_pair(self.reason_code, self.error_code)
            _validate_failure_target(self.reason_code, self.binding, self.route)
            _validate_segment_target(
                self.segment_name, self.binding, owner=self.metric_name
            )
            _validate_failure_segment(self.reason_code, self.segment_name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "measurement_id": self.measurement_id,
            "metric_name": self.metric_name,
            "metric_kind": self.metric_kind,
            "unit": self.unit,
            "value": self.value,
            "observed_at": self.observed_at,
            "binding": self.binding.to_dict(),
            "route": self.route.to_dict(),
            "segment_name": self.segment_name,
            "implementation_class": self.implementation_class,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "error_code": self.error_code,
            "cancel_scope": self.cancel_scope,
        }


_METRIC_KEYS = frozenset(LiveVoiceMetric.__dataclass_fields__)
_METRIC_REQUIRED = frozenset(
    {
        "schema_version",
        "measurement_id",
        "metric_name",
        "metric_kind",
        "unit",
        "value",
        "observed_at",
        "binding",
        "route",
        "segment_name",
        "implementation_class",
    }
)


def create_metric(value: LiveVoiceMetric | object) -> LiveVoiceMetric:
    if isinstance(value, LiveVoiceMetric):
        value = value.to_dict()
    data = _closed_dict(
        value,
        field_name="metric",
        allowed=_METRIC_KEYS,
        required=_METRIC_REQUIRED,
    ).copy()
    data["binding"] = create_trace_binding(data["binding"])
    data["route"] = create_route_descriptor(data["route"])
    return LiveVoiceMetric(**data)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class CollectorStats:
    accepted_observations: int
    duplicate_observations: int
    rejected_observations: int
    accepted_metrics: int
    duplicate_metrics: int
    rejected_metrics: int
    sink_failures: int


ObservationSink: TypeAlias = Callable[[LiveVoiceObservation], None]
MetricSink: TypeAlias = Callable[[LiveVoiceMetric], None]


class LiveVoiceObservabilityCollector:
    """In-memory deterministic collector with isolated optional sinks."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        observation_sink: ObservationSink | None = None,
        metric_sink: MetricSink | None = None,
        max_observations: int = DEFAULT_COLLECTOR_CAPACITY,
        max_metrics: int = DEFAULT_COLLECTOR_CAPACITY,
    ) -> None:
        if type(enabled) is not bool:
            raise _violation("INVALID_BOOLEAN", "enabled must be a boolean")
        if observation_sink is not None and not callable(observation_sink):
            raise _violation("INVALID_SINK", "observation_sink must be callable")
        if metric_sink is not None and not callable(metric_sink):
            raise _violation("INVALID_SINK", "metric_sink must be callable")
        _uint(max_observations, "max_observations")
        _uint(max_metrics, "max_metrics")
        if max_observations == 0 or max_metrics == 0:
            raise _violation(
                "INVALID_CAPACITY", "collector capacities must be positive"
            )
        self.enabled = enabled
        self._observation_sink = observation_sink
        self._metric_sink = metric_sink
        self._max_observations = max_observations
        self._max_metrics = max_metrics
        self._lock = Lock()
        self._observations: list[LiveVoiceObservation] = []
        self._observation_by_id: dict[str, LiveVoiceObservation] = {}
        self._metrics: list[LiveVoiceMetric] = []
        self._metric_by_id: dict[str, LiveVoiceMetric] = {}
        self._accepted_observations = 0
        self._duplicate_observations = 0
        self._rejected_observations = 0
        self._accepted_metrics = 0
        self._duplicate_metrics = 0
        self._rejected_metrics = 0
        self._sink_failures = 0

    def emit_observation(self, value: LiveVoiceObservation | object) -> bool:
        if not self.enabled:
            return False
        try:
            observation = create_observation(value)
        except Exception:
            with self._lock:
                self._rejected_observations += 1
            return False
        with self._lock:
            previous = self._observation_by_id.get(observation.event_id)
            if previous is not None:
                if previous == observation:
                    self._duplicate_observations += 1
                    return True
                self._rejected_observations += 1
                return False
            if len(self._observations) >= self._max_observations:
                self._rejected_observations += 1
                return False
            self._observation_by_id[observation.event_id] = observation
            self._observations.append(observation)
            self._accepted_observations += 1
        self._deliver_observation(observation)
        return True

    def emit_metric(self, value: LiveVoiceMetric | object) -> bool:
        if not self.enabled:
            return False
        try:
            metric = create_metric(value)
        except Exception:
            with self._lock:
                self._rejected_metrics += 1
            return False
        with self._lock:
            previous = self._metric_by_id.get(metric.measurement_id)
            if previous is not None:
                if previous == metric:
                    self._duplicate_metrics += 1
                    return True
                self._rejected_metrics += 1
                return False
            if len(self._metrics) >= self._max_metrics:
                self._rejected_metrics += 1
                return False
            self._metric_by_id[metric.measurement_id] = metric
            self._metrics.append(metric)
            self._accepted_metrics += 1
        self._deliver_metric(metric)
        return True

    def observations(self) -> tuple[LiveVoiceObservation, ...]:
        with self._lock:
            return tuple(self._observations)

    def metrics(self) -> tuple[LiveVoiceMetric, ...]:
        with self._lock:
            return tuple(self._metrics)

    def by_correlation(self, correlation_id: str) -> tuple[LiveVoiceObservation, ...]:
        exact = _opaque_identity(correlation_id, "correlation_id")
        with self._lock:
            return tuple(
                event
                for event in self._observations
                if event.binding.correlation_id == exact
            )

    def stats(self) -> CollectorStats:
        with self._lock:
            return CollectorStats(
                accepted_observations=self._accepted_observations,
                duplicate_observations=self._duplicate_observations,
                rejected_observations=self._rejected_observations,
                accepted_metrics=self._accepted_metrics,
                duplicate_metrics=self._duplicate_metrics,
                rejected_metrics=self._rejected_metrics,
                sink_failures=self._sink_failures,
            )

    def _deliver_observation(self, observation: LiveVoiceObservation) -> None:
        if self._observation_sink is None:
            return
        try:
            self._observation_sink(observation)
        except Exception:
            with self._lock:
                self._sink_failures += 1

    def _deliver_metric(self, metric: LiveVoiceMetric) -> None:
        if self._metric_sink is None:
            return
        try:
            self._metric_sink(metric)
        except Exception:
            with self._lock:
                self._sink_failures += 1


def route_descriptor_from_route_record(record: Mapping[str, object]) -> RouteDescriptor:
    """Redact W1-X1 free-text reasons while preserving truthful route class."""

    if type(record) is not dict:
        raise _violation("INVALID_JSON_OBJECT", "route record must be a plain object")
    implementation_class = _required_text(
        record.get("implementation_class"), "route_record.implementation_class"
    )
    reason_code = _ROUTE_REASON.get(implementation_class)
    return create_route_descriptor(
        {
            "implementation_class": implementation_class,
            "owner_module": record.get("owner_module"),
            "capability_provider": record.get("capability_provider"),
            "contract_version": record.get("contract_version"),
            "reason_code": reason_code,
        }
    )


def observation_from_task_event(
    event: object,
    *,
    observation_id: str,
    observed_at: str,
    monotonic_ms: float,
    route: RouteDescriptor | object,
) -> LiveVoiceObservation:
    """Project a public PersistentTaskEvent without copying its free-text details."""

    from jiuwenswarm.server.live_voice.formal_task_models import PersistentTaskEvent

    if not isinstance(event, PersistentTaskEvent):
        raise _violation("INVALID_TASK_EVENT", "event must be PersistentTaskEvent")
    state = event.state if event.state in OBSERVED_STATES else None
    if state is None:
        raise _violation("INVALID_VOCABULARY", "task event state is not observable")
    outcome = event.outcome
    reason_code = None
    if state == "terminal" and outcome == "failed":
        reason_code = "TASK_FAILURE"
    elif state == "terminal" and outcome == "cancelled":
        reason_code = "CANCEL_TERMINAL"
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": observation_id,
            "event_name": "task.state_observed",
            "segment_name": "task.progress",
            "observed_at": observed_at,
            "monotonic_ms": monotonic_ms,
            "binding": {
                "correlation_id": event.correlation_id,
                "task_id": event.task_id,
                "attempt_id": event.attempt_id,
            },
            "route": route.to_dict() if isinstance(route, RouteDescriptor) else route,
            "source_component": "task.core",
            "source_event_id": event.event_id,
            "source_occurred_at": event.occurred_at,
            "source_seq": event.seq,
            "state": state,
            "outcome": outcome,
            "reason_code": reason_code,
        }
    )


def observation_from_task_outbox(
    item: object,
    task: object,
    *,
    observation_id: str,
    observed_at: str,
    monotonic_ms: float,
    route: RouteDescriptor | object,
) -> LiveVoiceObservation:
    """Observe a durable outbox item without copying its task spec or instruction."""

    from jiuwenswarm.server.live_voice.formal_task_models import (
        OutboxKind,
        OutboxState,
        PersistentOutboxItem,
        PersistentTaskRecord,
    )

    if not isinstance(item, PersistentOutboxItem) or not isinstance(
        task, PersistentTaskRecord
    ):
        raise _violation(
            "INVALID_TASK_OUTBOX", "item and task must use formal persistent models"
        )
    if not isinstance(item.kind, OutboxKind) or not isinstance(item.state, OutboxState):
        raise _violation(
            "INVALID_TASK_OUTBOX", "outbox kind and state must use formal vocabulary"
        )
    if (
        item.task_id != task.task_id
        or item.attempt_id != task.attempt_id
        or item.scope != task.scope
    ):
        raise _violation(
            "TASK_OUTBOX_BINDING_MISMATCH",
            "outbox item must bind the exact task, attempt, and scope",
        )
    event_name = (
        "task.dispatch_outbox_observed"
        if item.kind is OutboxKind.ATTEMPT_DISPATCH
        else "task.cancel_outbox_observed"
    )
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": observation_id,
            "event_name": event_name,
            "segment_name": "task.queue",
            "observed_at": observed_at,
            "monotonic_ms": monotonic_ms,
            "binding": {
                "correlation_id": task.correlation_id,
                "task_id": task.task_id,
                "attempt_id": task.attempt_id,
            },
            "route": route.to_dict() if isinstance(route, RouteDescriptor) else route,
            "source_component": "task.core",
            "source_record_id": item.outbox_id,
            "source_seq": item.source_seq,
            "state": item.state.value,
        }
    )


def create_queue_metric(
    *,
    measurement_id: str,
    binding: TraceBinding | object,
    route: RouteDescriptor | object,
    observed_at: str,
    segment_name: str,
    depth: int,
) -> LiveVoiceMetric:
    """Create a bounded queue gauge from a public runtime/Agent/Task snapshot."""

    descriptor = create_route_descriptor(route)
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": measurement_id,
            "metric_name": "live_voice.queue_depth",
            "metric_kind": "gauge",
            "unit": "items",
            "value": depth,
            "observed_at": observed_at,
            "binding": (
                binding.to_dict() if isinstance(binding, TraceBinding) else binding
            ),
            "route": descriptor.to_dict(),
            "segment_name": segment_name,
            "implementation_class": descriptor.implementation_class,
        }
    )


__all__ = [
    "CANCEL_SCOPES",
    "CANCEL_TARGET_SEGMENT_MATRIX",
    "DEFAULT_COLLECTOR_CAPACITY",
    "ERROR_CODES",
    "EVENT_SEMANTIC_MATRIX",
    "EVENT_NAMES",
    "FAILURE_ERROR_MATRIX",
    "FAILURE_SEGMENT_MATRIX",
    "IDENTITY_MAX_LENGTH",
    "IDENTITY_POLICY",
    "LIVE_VOICE_CONTRACT_VERSION",
    "METRIC_DEFINITIONS",
    "METRIC_SEMANTIC_MATRIX",
    "OBSERVABILITY_SCHEMA_VERSION",
    "OBSERVED_STATES",
    "REASON_CODES",
    "ROUTE_IMPLEMENTATION_CLASSES",
    "SEGMENT_NAMES",
    "SEGMENT_BINDING_MATRIX",
    "TERMINAL_OUTCOMES",
    "CollectorStats",
    "LiveVoiceMetric",
    "LiveVoiceObservation",
    "LiveVoiceObservabilityCollector",
    "ObservabilityViolation",
    "RouteDescriptor",
    "TraceBinding",
    "contains_private_observability_content",
    "create_metric",
    "create_observation",
    "create_queue_metric",
    "create_route_descriptor",
    "create_trace_binding",
    "observation_from_task_event",
    "observation_from_task_outbox",
    "route_descriptor_from_route_record",
    "validate_observability_timestamp",
]
