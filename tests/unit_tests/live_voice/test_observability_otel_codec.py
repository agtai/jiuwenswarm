# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import replace
from types import ModuleType

import pytest

from jiuwenswarm.server.live_voice.observability import (
    LIVE_VOICE_CONTRACT_VERSION,
    OBSERVABILITY_SCHEMA_VERSION,
    LiveVoiceMetric,
    LiveVoiceObservation,
    create_metric,
    create_observation,
)


CORRELATION_ID = "corr-p3-8a"


def _codec() -> ModuleType:
    try:
        return importlib.import_module(
            "jiuwenswarm.server.live_voice.observability_otel_codec"
        )
    except ModuleNotFoundError:
        pytest.fail("the current observability owner has no OTel backend codec")


def _route(
    *,
    implementation_class: str = "formal",
    contract_version: str | None = LIVE_VOICE_CONTRACT_VERSION,
) -> dict[str, object]:
    if implementation_class == "formal":
        return {
            "implementation_class": "formal",
            "owner_module": "runtime.conversation",
            "capability_provider": "jiuwenswarm-runtime",
            "contract_version": contract_version,
            "reason_code": None,
        }
    return {
        "implementation_class": "fallback",
        "owner_module": "route.compatibility",
        "capability_provider": None,
        "contract_version": contract_version,
        "reason_code": "ROUTE_FALLBACK",
    }


def _observation(
    *, contract_version: str = LIVE_VOICE_CONTRACT_VERSION
) -> LiveVoiceObservation:
    return create_observation(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "event_id": "event-p3-8a",
            "event_name": "segment.started",
            "segment_name": "runtime.turn",
            "observed_at": "2026-08-19T09:00:00Z",
            "monotonic_ms": 1_000.0,
            "binding": {
                "correlation_id": CORRELATION_ID,
                "interaction_id": "interaction-p3-8a",
                "turn_id": "turn-p3-8a",
            },
            "route": _route(contract_version=contract_version),
            "source_component": "runtime.observer",
        }
    )


def _fallback_observation(contract_version: str) -> LiveVoiceObservation:
    value = _observation().to_dict()
    value["route"] = _route(
        implementation_class="fallback", contract_version=contract_version
    )
    return create_observation(value)


def _metric() -> LiveVoiceMetric:
    return create_metric(
        {
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "measurement_id": "metric-p3-8a",
            "metric_name": "live_voice.queue_depth",
            "metric_kind": "gauge",
            "unit": "items",
            "value": 2,
            "observed_at": "2026-08-19T09:00:00Z",
            "binding": {"correlation_id": CORRELATION_ID},
            "route": _route(),
            "segment_name": "runtime.queue",
            "implementation_class": "formal",
        }
    )


def _trace(module: ModuleType, *, correlation_id: str = CORRELATION_ID) -> object:
    return module.OtelTraceContext(
        trace_id="1" * 32,
        span_id="2" * 16,
        parent_span_id="3" * 16,
        correlation_id=correlation_id,
    )


def _payload(record: object) -> dict[str, object]:
    value = json.loads(record.canonical_bytes)
    assert isinstance(value, dict)
    return value


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def test_observation_codec_emits_one_exact_closed_backend_payload() -> None:
    module = _codec()
    observation = _observation()
    trace = _trace(module)

    encoding = module.encode_observation_for_otel_backend(
        observation, trace_context=trace, enabled=True
    )

    assert encoding.reason is module.OtelBackendCodecReason.READY
    assert encoding.ready_for_backend is True
    assert encoding.record is not None
    payload = _payload(encoding.record)
    assert set(payload) == {
        "attributes",
        "name",
        "observed_at",
        "record_id",
        "schema_version",
        "signal_kind",
        "trace",
    }
    assert set(payload["attributes"]) == {
        "live_voice.correlation_id",
        "live_voice.event_name",
        "live_voice.implementation_class",
        "live_voice.interaction_id",
        "live_voice.route.capability_provider",
        "live_voice.route.contract_version",
        "live_voice.route.owner_module",
        "live_voice.segment_name",
        "live_voice.source_component",
        "live_voice.turn_id",
    }
    assert payload["trace"] == {
        "parent_span_id": "3" * 16,
        "span_id": "2" * 16,
        "trace_id": "1" * 32,
    }
    assert module.validate_otel_backend_record(
        encoding.record, source_fact=observation, trace_context=trace
    )
    assert encoding.backend_called is False
    assert encoding.network_changed is False
    assert encoding.persistence_changed is False
    assert encoding.business_result_changed is False


def test_metric_codec_emits_exact_metric_schema_without_trace() -> None:
    module = _codec()
    metric = _metric()

    encoding = module.encode_metric_for_otel_backend(metric, enabled=True)

    assert encoding.reason is module.OtelBackendCodecReason.READY
    assert encoding.record is not None
    payload = _payload(encoding.record)
    assert set(payload) == {
        "attributes",
        "metric",
        "name",
        "observed_at",
        "record_id",
        "schema_version",
        "signal_kind",
    }
    assert payload["metric"] == {
        "kind": "gauge",
        "unit": "items",
        "value": 2.0,
    }
    assert set(payload["attributes"]) == {
        "live_voice.correlation_id",
        "live_voice.implementation_class",
        "live_voice.route.capability_provider",
        "live_voice.route.contract_version",
        "live_voice.route.owner_module",
        "live_voice.segment_name",
    }
    assert module.validate_otel_backend_record(encoding.record, source_fact=metric)


@pytest.mark.parametrize(
    "carrier",
    (
        "ftp://telemetry.invalid/upload",
        "secret=value",
        "transcript=hello",
        "raw_audio=AAAA",
        "device_id=microphone-serial",
        "version?credential=value",
        "mailto:private@example.invalid",
        "data:audio/wav;base64,AAAA",
    ),
)
def test_codec_reuses_product_private_carrier_rejection(carrier: str) -> None:
    module = _codec()
    observation = _fallback_observation("route.compatibility.v1")
    # The public schema rejects these carriers before encoding. Mutate a valid
    # frozen value to keep the backend's defence-in-depth path covered.
    object.__setattr__(observation.route, "contract_version", carrier)

    encoding = module.encode_observation_for_otel_backend(
        observation,
        trace_context=_trace(module),
        enabled=True,
    )

    assert encoding.reason is module.OtelBackendCodecReason.PRIVATE_CONTENT_REJECTED
    assert encoding.ready_for_backend is False
    assert encoding.record is None


@pytest.mark.parametrize(
    "invalid_timestamp",
    (
        "2026-02-29T09:00:00Z",
        "2026-13-01T09:00:00Z",
        "2026-08-19T24:00:00Z",
        "0000-08-19T09:00:00Z",
    ),
)
def test_codec_revalidates_calendar_time_not_just_timestamp_shape(
    invalid_timestamp: str,
) -> None:
    module = _codec()
    observation = _observation()
    object.__setattr__(observation, "observed_at", invalid_timestamp)

    encoding = module.encode_observation_for_otel_backend(
        observation, trace_context=_trace(module), enabled=True
    )

    assert encoding.reason is module.OtelBackendCodecReason.INVALID_FACT
    assert encoding.record is None


@pytest.mark.parametrize(
    "required_attribute",
    (
        "live_voice.event_name",
        "live_voice.segment_name",
        "live_voice.implementation_class",
        "live_voice.source_component",
        "live_voice.correlation_id",
        "live_voice.route.owner_module",
        "live_voice.route.capability_provider",
        "live_voice.route.contract_version",
    ),
)
def test_backend_record_rejects_coherently_rehashed_missing_required_attribute(
    required_attribute: str,
) -> None:
    module = _codec()
    observation = _observation()
    trace = _trace(module)
    encoding = module.encode_observation_for_otel_backend(
        observation, trace_context=trace, enabled=True
    )
    assert encoding.record is not None
    payload = _payload(encoding.record)
    attributes = payload["attributes"]
    assert isinstance(attributes, dict)
    del attributes[required_attribute]
    tampered_bytes = _canonical_bytes(payload)

    with pytest.raises(ValueError, match="attribute set"):
        replace(
            encoding.record,
            canonical_bytes=tampered_bytes,
            payload_sha256=hashlib.sha256(tampered_bytes).hexdigest(),
            attribute_keys=tuple(sorted(attributes)),
        )


@pytest.mark.parametrize(
    "required_attribute",
    (
        "live_voice.route.owner_module",
        "live_voice.route.reason_code",
    ),
)
def test_backend_record_closes_non_formal_route_required_attributes(
    required_attribute: str,
) -> None:
    module = _codec()
    observation = _fallback_observation("route.compatibility.v1")
    trace = _trace(module)
    encoding = module.encode_observation_for_otel_backend(
        observation, trace_context=trace, enabled=True
    )
    assert encoding.record is not None
    payload = _payload(encoding.record)
    attributes = payload["attributes"]
    assert isinstance(attributes, dict)
    del attributes[required_attribute]
    tampered_bytes = _canonical_bytes(payload)

    with pytest.raises(ValueError, match="attribute set"):
        replace(
            encoding.record,
            canonical_bytes=tampered_bytes,
            payload_sha256=hashlib.sha256(tampered_bytes).hexdigest(),
            attribute_keys=tuple(sorted(attributes)),
        )


def test_backend_record_rejects_formal_route_reason_attribute() -> None:
    module = _codec()
    observation = _observation()
    trace = _trace(module)
    encoding = module.encode_observation_for_otel_backend(
        observation, trace_context=trace, enabled=True
    )
    assert encoding.record is not None
    payload = _payload(encoding.record)
    attributes = payload["attributes"]
    assert isinstance(attributes, dict)
    attributes["live_voice.route.reason_code"] = "ROUTE_FALLBACK"
    tampered_bytes = _canonical_bytes(payload)

    with pytest.raises(ValueError, match="attribute set"):
        replace(
            encoding.record,
            canonical_bytes=tampered_bytes,
            payload_sha256=hashlib.sha256(tampered_bytes).hexdigest(),
            attribute_keys=tuple(sorted(attributes)),
        )


def test_backend_record_rejects_coherently_rehashed_unknown_attribute() -> None:
    module = _codec()
    metric = _metric()
    encoding = module.encode_metric_for_otel_backend(metric, enabled=True)
    assert encoding.record is not None
    payload = _payload(encoding.record)
    attributes = payload["attributes"]
    assert isinstance(attributes, dict)
    attributes["dynamic.user_label"] = "safe-looking"
    tampered_bytes = _canonical_bytes(payload)

    with pytest.raises(ValueError, match="attribute set"):
        replace(
            encoding.record,
            canonical_bytes=tampered_bytes,
            payload_sha256=hashlib.sha256(tampered_bytes).hexdigest(),
            attribute_keys=tuple(sorted(attributes)),
        )


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    (
        ("source_fingerprint", "0" * 64),
        ("payload_sha256", "0" * 64),
        ("attribute_keys", ("live_voice.correlation_id",)),
        ("canonical_bytes", b"{}"),
    ),
)
def test_source_bound_validation_rejects_every_tampered_record_field(
    field_name: str,
    forged_value: object,
) -> None:
    module = _codec()
    metric = _metric()
    encoding = module.encode_metric_for_otel_backend(metric, enabled=True)
    assert encoding.record is not None
    object.__setattr__(encoding.record, field_name, forged_value)

    assert (
        module.validate_otel_backend_record(
            encoding.record,
            source_fact=metric,
        )
        is False
    )


def test_trace_binding_mismatch_and_wrong_source_fact_fail_closed() -> None:
    module = _codec()
    mismatch = module.encode_observation_for_otel_backend(
        _observation(),
        trace_context=_trace(module, correlation_id="corr-other"),
        enabled=True,
    )
    valid = module.encode_metric_for_otel_backend(_metric(), enabled=True)
    assert valid.record is not None

    assert mismatch.reason is module.OtelBackendCodecReason.TRACE_BINDING_MISMATCH
    assert (
        module.validate_otel_backend_record(
            valid.record,
            source_fact=_observation(),
            trace_context=_trace(module),
        )
        is False
    )


def test_otel_feature_off_touches_no_fact_or_trace() -> None:
    module = _codec()

    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off touched {name}")

    encoding = module.encode_observation_for_otel_backend(
        Poison(), trace_context=Poison(), enabled=False
    )

    assert encoding.reason is module.OtelBackendCodecReason.FEATURE_DISABLED
    assert encoding.ready_for_backend is False
    assert encoding.backend_called is False
