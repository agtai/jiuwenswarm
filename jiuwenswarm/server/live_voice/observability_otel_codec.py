# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Pure OTel backend codec for current Live Voice observability facts.

The codec is owned by the existing observability record boundary. It validates
one current public fact, applies the same private-carrier policy as the product
adapter, and returns canonical bytes for a later injected OTel backend. It does
not collect, enqueue, export, persist, or change lifecycle/business authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from jiuwenswarm.server.live_voice.observability import (
    MAX_SAFE_INTEGER,
    ROUTE_IMPLEMENTATION_CLASSES,
    LiveVoiceMetric,
    LiveVoiceObservation,
    contains_private_observability_content,
    create_metric,
    create_observation,
    validate_observability_timestamp,
)


OTEL_BACKEND_SCHEMA_VERSION: Final = "live-voice.otel-backend.v1"

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_COMMON_ATTRIBUTE_KEYS: Final = frozenset(
    {
        "live_voice.correlation_id",
        "live_voice.interaction_id",
        "live_voice.turn_id",
        "live_voice.response_id",
        "live_voice.response_generation",
        "live_voice.round_id",
        "live_voice.task_id",
        "live_voice.attempt_id",
        "live_voice.segment_name",
        "live_voice.implementation_class",
        "live_voice.route.owner_module",
        "live_voice.route.capability_provider",
        "live_voice.route.contract_version",
        "live_voice.route.reason_code",
        "live_voice.outcome",
        "live_voice.reason_code",
        "live_voice.error_code",
        "live_voice.cancel_scope",
    }
)
_SPAN_ONLY_ATTRIBUTE_KEYS: Final = frozenset(
    {
        "live_voice.event_name",
        "live_voice.source_component",
        "live_voice.state",
    }
)
OTEL_BACKEND_ATTRIBUTE_KEYS: Final = _COMMON_ATTRIBUTE_KEYS | _SPAN_ONLY_ATTRIBUTE_KEYS
OTEL_SPAN_REQUIRED_ATTRIBUTES: Final = frozenset(
    {
        "live_voice.event_name",
        "live_voice.segment_name",
        "live_voice.implementation_class",
        "live_voice.source_component",
        "live_voice.correlation_id",
    }
)
OTEL_METRIC_REQUIRED_ATTRIBUTES: Final = frozenset(
    {
        "live_voice.segment_name",
        "live_voice.implementation_class",
        "live_voice.correlation_id",
    }
)
OTEL_BACKEND_ROUTE_REQUIRED_ATTRIBUTES: Final = MappingProxyType(
    {
        "formal": frozenset(
            {
                "live_voice.route.owner_module",
                "live_voice.route.capability_provider",
                "live_voice.route.contract_version",
            }
        ),
        "fallback": frozenset(
            {
                "live_voice.route.owner_module",
                "live_voice.route.reason_code",
            }
        ),
        "demo_substitute": frozenset(
            {
                "live_voice.route.owner_module",
                "live_voice.route.reason_code",
            }
        ),
        "unsupported": frozenset(
            {
                "live_voice.route.owner_module",
                "live_voice.route.reason_code",
            }
        ),
        "unknown": frozenset({"live_voice.route.reason_code"}),
    }
)


class OtelBackendSignalKind(StrEnum):
    SPAN_EVENT = "span_event"
    METRIC_POINT = "metric_point"


class OtelBackendCodecReason(StrEnum):
    READY = "ready"
    FEATURE_DISABLED = "feature_disabled"
    INVALID_FACT = "invalid_fact"
    INVALID_TRACE_CONTEXT = "invalid_trace_context"
    TRACE_BINDING_MISMATCH = "trace_binding_mismatch"
    PRIVATE_CONTENT_REJECTED = "private_content_rejected"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source_fingerprint(value: object) -> str:
    return _digest(_canonical_bytes(value))


def _closed_attribute(value: object) -> str | int | float | bool:
    if type(value) not in {str, int, float, bool}:
        raise ValueError("OTel attribute must be one closed scalar")
    if isinstance(value, str):
        if not value or len(value) > 128:
            raise ValueError("OTel string attribute is outside the bounded range")
    elif isinstance(value, int) and abs(value) > MAX_SAFE_INTEGER:
        raise ValueError("OTel integer attribute is outside the safe range")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("OTel float attribute must be finite")
    if contains_private_observability_content(value):
        raise ValueError("OTel attribute contains a private carrier")
    return value  # type: ignore[return-value]


def _decoded_payload(value: bytes) -> dict[str, object]:
    if type(value) is not bytes or not value or len(value) > 32_768:
        raise ValueError("canonical OTel payload is outside the bounded range")
    try:
        decoded = json.loads(value.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("canonical OTel payload is invalid") from error
    if type(decoded) is not dict or _canonical_bytes(decoded) != value:
        raise ValueError("OTel payload must use canonical JSON bytes")
    return decoded


def _validate_trace_id(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} has an invalid OTel identity")
    if set(value) == {"0"}:
        raise ValueError(f"{field_name} must not be all zero")
    return value


@dataclass(frozen=True, slots=True)
class OtelTraceContext:
    trace_id: str
    span_id: str
    correlation_id: str
    parent_span_id: str | None = None

    def __post_init__(self) -> None:
        _validate_trace_id(self.trace_id, "trace_id", _TRACE_ID)
        _validate_trace_id(self.span_id, "span_id", _SPAN_ID)
        if self.parent_span_id is not None:
            _validate_trace_id(self.parent_span_id, "parent_span_id", _SPAN_ID)
        if (
            type(self.correlation_id) is not str
            or not self.correlation_id
            or len(self.correlation_id) > 128
            or contains_private_observability_content(self.correlation_id)
        ):
            raise ValueError("trace correlation identity is invalid or private")


@dataclass(frozen=True, slots=True)
class OtelBackendRecord:
    signal_kind: OtelBackendSignalKind
    source_schema_version: str
    source_record_id: str
    source_fingerprint: str
    attribute_keys: tuple[str, ...]
    canonical_bytes: bytes
    payload_sha256: str

    def __post_init__(self) -> None:
        if type(self.signal_kind) is not OtelBackendSignalKind:
            raise ValueError("signal kind must use the closed OTel vocabulary")
        if (
            type(self.source_schema_version) is not str
            or not self.source_schema_version
        ):
            raise ValueError("source schema version is required")
        if type(self.source_record_id) is not str or not self.source_record_id:
            raise ValueError("source record identity is required")
        if (
            type(self.source_fingerprint) is not str
            or _SHA256.fullmatch(self.source_fingerprint) is None
        ):
            raise ValueError("source fingerprint must be lowercase SHA-256")
        if (
            type(self.payload_sha256) is not str
            or _SHA256.fullmatch(self.payload_sha256) is None
        ):
            raise ValueError("payload digest must be lowercase SHA-256")
        if type(self.canonical_bytes) is not bytes:
            raise ValueError("canonical payload must be immutable bytes")
        if _digest(self.canonical_bytes) != self.payload_sha256:
            raise ValueError("canonical payload digest does not match")
        payload = _decoded_payload(self.canonical_bytes)
        expected_top_level = {
            OtelBackendSignalKind.SPAN_EVENT: {
                "attributes",
                "name",
                "observed_at",
                "record_id",
                "schema_version",
                "signal_kind",
                "trace",
            },
            OtelBackendSignalKind.METRIC_POINT: {
                "attributes",
                "metric",
                "name",
                "observed_at",
                "record_id",
                "schema_version",
                "signal_kind",
            },
        }[self.signal_kind]
        if set(payload) != expected_top_level:
            raise ValueError("OTel payload has an invalid closed field set")
        if payload["schema_version"] != OTEL_BACKEND_SCHEMA_VERSION:
            raise ValueError("OTel payload schema version is unsupported")
        if payload["signal_kind"] != self.signal_kind.value:
            raise ValueError("OTel payload signal kind does not match")
        if payload["record_id"] != self.source_record_id:
            raise ValueError("OTel payload record identity does not match")
        if type(payload["name"]) is not str or not payload["name"]:
            raise ValueError("OTel payload name is invalid")
        validate_observability_timestamp(payload["observed_at"])
        attributes = payload["attributes"]
        if type(attributes) is not dict or any(
            type(key) is not str for key in attributes
        ):
            raise ValueError("OTel attributes must be one closed object")
        keys = frozenset(attributes)
        required = {
            OtelBackendSignalKind.SPAN_EVENT: OTEL_SPAN_REQUIRED_ATTRIBUTES,
            OtelBackendSignalKind.METRIC_POINT: OTEL_METRIC_REQUIRED_ATTRIBUTES,
        }[self.signal_kind]
        implementation_class = attributes.get("live_voice.implementation_class")
        if (
            type(implementation_class) is not str
            or implementation_class not in ROUTE_IMPLEMENTATION_CLASSES
        ):
            raise ValueError("OTel attribute set has an invalid route class")
        required = (
            required | OTEL_BACKEND_ROUTE_REQUIRED_ATTRIBUTES[implementation_class]
        )
        if not required.issubset(keys):
            raise ValueError("OTel attribute set is missing a required attribute")
        if not keys.issubset(OTEL_BACKEND_ATTRIBUTE_KEYS):
            raise ValueError("OTel attribute set contains an unknown attribute")
        if (
            self.signal_kind is OtelBackendSignalKind.METRIC_POINT
            and not keys.isdisjoint(_SPAN_ONLY_ATTRIBUTE_KEYS)
        ):
            raise ValueError("OTel metric attribute set contains span-only fields")
        if implementation_class == "formal" and "live_voice.route.reason_code" in keys:
            raise ValueError("OTel attribute set has a non-formal route reason")
        if type(self.attribute_keys) is not tuple or self.attribute_keys != tuple(
            sorted(keys)
        ):
            raise ValueError("OTel attribute set does not match record metadata")
        for value in attributes.values():
            _closed_attribute(value)
        if contains_private_observability_content(payload):
            raise ValueError("OTel payload contains a private carrier")
        if self.signal_kind is OtelBackendSignalKind.SPAN_EVENT:
            trace = payload["trace"]
            if type(trace) is not dict or set(trace) != {
                "parent_span_id",
                "span_id",
                "trace_id",
            }:
                raise ValueError("OTel trace context has an invalid field set")
            _validate_trace_id(trace["trace_id"], "trace_id", _TRACE_ID)
            _validate_trace_id(trace["span_id"], "span_id", _SPAN_ID)
            if trace["parent_span_id"] is not None:
                _validate_trace_id(trace["parent_span_id"], "parent_span_id", _SPAN_ID)
        else:
            metric = payload["metric"]
            if type(metric) is not dict or set(metric) != {"kind", "unit", "value"}:
                raise ValueError("OTel metric point has an invalid field set")
            if (
                type(metric["kind"]) is not str
                or not metric["kind"]
                or type(metric["unit"]) is not str
                or not metric["unit"]
                or type(metric["value"]) is not float
                or not math.isfinite(metric["value"])
                or metric["value"] < 0
            ):
                raise ValueError("OTel metric point is invalid")


@dataclass(frozen=True, slots=True)
class OtelBackendEncoding:
    ready_for_backend: bool
    reason: OtelBackendCodecReason
    record: OtelBackendRecord | None
    backend_called: bool = False
    network_changed: bool = False
    persistence_changed: bool = False
    lifecycle_authority_exercised: bool = False
    business_result_changed: bool = False

    def __post_init__(self) -> None:
        if type(self.ready_for_backend) is not bool:
            raise ValueError("ready_for_backend must be exact bool")
        if type(self.reason) is not OtelBackendCodecReason:
            raise ValueError("codec reason must use the closed vocabulary")
        if self.ready_for_backend != (self.record is not None):
            raise ValueError("codec readiness must match record presence")
        if self.ready_for_backend != (self.reason is OtelBackendCodecReason.READY):
            raise ValueError("only a ready encoding may carry a record")
        if self.record is not None and type(self.record) is not OtelBackendRecord:
            raise ValueError("codec record must be exact")
        authority = (
            self.backend_called,
            self.network_changed,
            self.persistence_changed,
            self.lifecycle_authority_exercised,
            self.business_result_changed,
        )
        if any(type(value) is not bool for value in authority):
            raise ValueError("codec authority facts must be exact bools")
        if any(value is not False for value in authority):
            raise ValueError("codec cannot claim backend or business authority")


def _rejection(reason: OtelBackendCodecReason) -> OtelBackendEncoding:
    return OtelBackendEncoding(
        ready_for_backend=False,
        reason=reason,
        record=None,
    )


def _binding_attributes(
    fact: LiveVoiceObservation | LiveVoiceMetric,
) -> tuple[tuple[str, object], ...]:
    binding = fact.binding
    return (
        ("live_voice.correlation_id", binding.correlation_id),
        ("live_voice.interaction_id", binding.interaction_id),
        ("live_voice.turn_id", binding.turn_id),
        ("live_voice.response_id", binding.response_id),
        ("live_voice.response_generation", binding.response_generation),
        ("live_voice.round_id", binding.round_id),
        ("live_voice.task_id", binding.task_id),
        ("live_voice.attempt_id", binding.attempt_id),
    )


def _route_attributes(
    fact: LiveVoiceObservation | LiveVoiceMetric,
) -> tuple[tuple[str, object], ...]:
    route = fact.route
    return (
        ("live_voice.implementation_class", route.implementation_class),
        ("live_voice.route.owner_module", route.owner_module),
        ("live_voice.route.capability_provider", route.capability_provider),
        ("live_voice.route.contract_version", route.contract_version),
        ("live_voice.route.reason_code", route.reason_code),
    )


def _attributes(values: tuple[tuple[str, object], ...]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if value is None:
            continue
        if key in result or key not in OTEL_BACKEND_ATTRIBUTE_KEYS:
            raise ValueError("OTel attribute key set is invalid")
        result[key] = _closed_attribute(value)
    return result


def _record(
    *,
    signal_kind: OtelBackendSignalKind,
    source_schema_version: str,
    source_record_id: str,
    source_value: object,
    payload: dict[str, object],
) -> OtelBackendRecord:
    canonical = _canonical_bytes(payload)
    attributes = payload["attributes"]
    if type(attributes) is not dict:
        raise ValueError("OTel attributes must be one object")
    return OtelBackendRecord(
        signal_kind=signal_kind,
        source_schema_version=source_schema_version,
        source_record_id=source_record_id,
        source_fingerprint=_source_fingerprint(source_value),
        attribute_keys=tuple(sorted(attributes)),
        canonical_bytes=canonical,
        payload_sha256=_digest(canonical),
    )


def _checked_trace(value: object) -> OtelTraceContext:
    if type(value) is not OtelTraceContext:
        raise ValueError("trace context must be exact")
    return OtelTraceContext(
        trace_id=value.trace_id,
        span_id=value.span_id,
        parent_span_id=value.parent_span_id,
        correlation_id=value.correlation_id,
    )


def encode_observation_for_otel_backend(
    observation: object,
    *,
    trace_context: object,
    enabled: bool,
) -> OtelBackendEncoding:
    """Encode one current observation without invoking a backend."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return _rejection(OtelBackendCodecReason.FEATURE_DISABLED)
    if type(observation) is not LiveVoiceObservation:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    try:
        raw = observation.to_dict()
    except Exception:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    if contains_private_observability_content(raw):
        return _rejection(OtelBackendCodecReason.PRIVATE_CONTENT_REJECTED)
    try:
        validated = create_observation(raw)
    except Exception:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    try:
        trace = _checked_trace(trace_context)
    except Exception:
        return _rejection(OtelBackendCodecReason.INVALID_TRACE_CONTEXT)
    if validated.binding.correlation_id != trace.correlation_id:
        return _rejection(OtelBackendCodecReason.TRACE_BINDING_MISMATCH)
    try:
        attributes = _attributes(
            (
                ("live_voice.event_name", validated.event_name),
                ("live_voice.segment_name", validated.segment_name),
                ("live_voice.source_component", validated.source_component),
                *_route_attributes(validated),
                *_binding_attributes(validated),
                ("live_voice.state", validated.state),
                ("live_voice.outcome", validated.outcome),
                ("live_voice.reason_code", validated.reason_code),
                ("live_voice.error_code", validated.error_code),
                ("live_voice.cancel_scope", validated.cancel_scope),
            )
        )
        payload: dict[str, object] = {
            "schema_version": OTEL_BACKEND_SCHEMA_VERSION,
            "signal_kind": OtelBackendSignalKind.SPAN_EVENT.value,
            "record_id": validated.event_id,
            "name": f"live_voice.{validated.event_name}",
            "observed_at": validated.observed_at,
            "attributes": attributes,
            "trace": {
                "trace_id": trace.trace_id,
                "span_id": trace.span_id,
                "parent_span_id": trace.parent_span_id,
            },
        }
        record = _record(
            signal_kind=OtelBackendSignalKind.SPAN_EVENT,
            source_schema_version=validated.schema_version,
            source_record_id=validated.event_id,
            source_value=validated.to_dict(),
            payload=payload,
        )
    except Exception:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    return OtelBackendEncoding(
        ready_for_backend=True,
        reason=OtelBackendCodecReason.READY,
        record=record,
    )


def encode_metric_for_otel_backend(
    metric: object,
    *,
    enabled: bool,
) -> OtelBackendEncoding:
    """Encode one current metric without invoking a backend."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return _rejection(OtelBackendCodecReason.FEATURE_DISABLED)
    if type(metric) is not LiveVoiceMetric:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    try:
        raw = metric.to_dict()
    except Exception:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    if contains_private_observability_content(raw):
        return _rejection(OtelBackendCodecReason.PRIVATE_CONTENT_REJECTED)
    try:
        validated = create_metric(raw)
        attributes = _attributes(
            (
                ("live_voice.segment_name", validated.segment_name),
                *_route_attributes(validated),
                *_binding_attributes(validated),
                ("live_voice.outcome", validated.outcome),
                ("live_voice.reason_code", validated.reason_code),
                ("live_voice.error_code", validated.error_code),
                ("live_voice.cancel_scope", validated.cancel_scope),
            )
        )
        payload: dict[str, object] = {
            "schema_version": OTEL_BACKEND_SCHEMA_VERSION,
            "signal_kind": OtelBackendSignalKind.METRIC_POINT.value,
            "record_id": validated.measurement_id,
            "name": validated.metric_name,
            "observed_at": validated.observed_at,
            "attributes": attributes,
            "metric": {
                "kind": validated.metric_kind,
                "unit": validated.unit,
                "value": float(validated.value),
            },
        }
        record = _record(
            signal_kind=OtelBackendSignalKind.METRIC_POINT,
            source_schema_version=validated.schema_version,
            source_record_id=validated.measurement_id,
            source_value=validated.to_dict(),
            payload=payload,
        )
    except Exception:
        return _rejection(OtelBackendCodecReason.INVALID_FACT)
    return OtelBackendEncoding(
        ready_for_backend=True,
        reason=OtelBackendCodecReason.READY,
        record=record,
    )


def validate_otel_backend_record(
    candidate: object,
    *,
    source_fact: object,
    trace_context: object = None,
) -> bool:
    """Recompute exact canonical bytes from the current authoritative fact."""

    if type(candidate) is not OtelBackendRecord:
        return False
    try:
        checked = OtelBackendRecord(
            signal_kind=candidate.signal_kind,
            source_schema_version=candidate.source_schema_version,
            source_record_id=candidate.source_record_id,
            source_fingerprint=candidate.source_fingerprint,
            attribute_keys=candidate.attribute_keys,
            canonical_bytes=candidate.canonical_bytes,
            payload_sha256=candidate.payload_sha256,
        )
    except Exception:
        return False
    if type(source_fact) is LiveVoiceObservation:
        expected = encode_observation_for_otel_backend(
            source_fact,
            trace_context=trace_context,
            enabled=True,
        )
    elif type(source_fact) is LiveVoiceMetric:
        if trace_context is not None:
            return False
        expected = encode_metric_for_otel_backend(source_fact, enabled=True)
    else:
        return False
    return expected.ready_for_backend and checked == expected.record


__all__ = [
    "OTEL_BACKEND_ATTRIBUTE_KEYS",
    "OTEL_BACKEND_ROUTE_REQUIRED_ATTRIBUTES",
    "OTEL_BACKEND_SCHEMA_VERSION",
    "OTEL_METRIC_REQUIRED_ATTRIBUTES",
    "OTEL_SPAN_REQUIRED_ATTRIBUTES",
    "OtelBackendCodecReason",
    "OtelBackendEncoding",
    "OtelBackendRecord",
    "OtelBackendSignalKind",
    "OtelTraceContext",
    "encode_metric_for_otel_backend",
    "encode_observation_for_otel_backend",
    "validate_otel_backend_record",
]
