# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import importlib
from types import ModuleType

import pytest


def _module(name: str) -> ModuleType:
    try:
        return importlib.import_module(f"jiuwenswarm.server.live_voice.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"P3-8A contract module is missing: {name}")


def _privacy_rules(
    module: ModuleType,
    *,
    raw_audio: object | None = None,
) -> tuple[object, ...]:
    override = raw_audio or module.TelemetryDisposition.PROHIBIT
    return tuple(
        module.TelemetryPrivacyRule(
            data_class=data_class,
            disposition=(
                override
                if data_class is module.TelemetryDataClass.RAW_AUDIO
                else disposition
            ),
        )
        for data_class, disposition in module.REQUIRED_TELEMETRY_DISPOSITIONS.items()
    )


def test_default_privacy_profile_is_complete_and_declaration_only() -> None:
    module = _module("telemetry_privacy_contract")

    readiness = module.evaluate_telemetry_privacy_profile(
        module.default_telemetry_privacy_profile(), enabled=True
    )

    assert readiness.declaration_ready is True
    assert readiness.reason is module.TelemetryPrivacyReason.DECLARATION_READY
    assert readiness.declaration_only is True
    assert readiness.runtime_scanned is False
    assert readiness.exporter_called is False
    assert readiness.persistence_changed is False
    assert readiness.business_result_changed is False


def test_privacy_profile_rejects_raw_audio_round_up_to_allowed() -> None:
    module = _module("telemetry_privacy_contract")
    profile = module.TelemetryPrivacyProfile(
        contract_version=module.TELEMETRY_PRIVACY_CONTRACT_VERSION,
        profile_id="p3.telemetry.unsafe",
        rules=_privacy_rules(
            module, raw_audio=module.TelemetryDisposition.ALLOW_CLOSED_FIELD
        ),
    )

    readiness = module.evaluate_telemetry_privacy_profile(profile, enabled=True)

    assert readiness.declaration_ready is False
    assert readiness.reason is module.TelemetryPrivacyReason.UNSAFE_DISPOSITION
    assert readiness.runtime_scanned is False


def test_privacy_profile_requires_every_unique_data_class() -> None:
    module = _module("telemetry_privacy_contract")
    complete = _privacy_rules(module)

    with pytest.raises(ValueError, match="every telemetry data class"):
        module.TelemetryPrivacyProfile(
            contract_version=module.TELEMETRY_PRIVACY_CONTRACT_VERSION,
            profile_id="p3.telemetry.missing",
            rules=complete[:-1],
        )
    with pytest.raises(ValueError, match="must be unique"):
        module.TelemetryPrivacyProfile(
            contract_version=module.TELEMETRY_PRIVACY_CONTRACT_VERSION,
            profile_id="p3.telemetry.duplicate",
            rules=complete[:-1] + (complete[0],),
        )


def test_privacy_feature_off_does_not_touch_candidate() -> None:
    module = _module("telemetry_privacy_contract")

    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off touched {name}")

    readiness = module.evaluate_telemetry_privacy_profile(Poison(), enabled=False)

    assert readiness.reason is module.TelemetryPrivacyReason.FEATURE_DISABLED
    assert readiness.declaration_ready is False


def test_forged_privacy_profile_is_revalidated() -> None:
    module = _module("telemetry_privacy_contract")
    profile = module.default_telemetry_privacy_profile()
    object.__setattr__(profile, "rules", (object(),))

    readiness = module.evaluate_telemetry_privacy_profile(profile, enabled=True)

    assert readiness.reason is module.TelemetryPrivacyReason.INVALID_PROFILE
    assert readiness.declaration_ready is False
    with pytest.raises(ValueError, match="only a ready declaration"):
        module.TelemetryPrivacyReadiness(
            declaration_ready=True,
            reason=module.TelemetryPrivacyReason.INVALID_PROFILE,
        )


def _latency_target(module: ModuleType) -> object:
    return module.SliWindowTarget(
        window_id="latency.runtime.turn",
        kind=module.SliSampleKind.LATENCY_MS,
        start_ms=1_000,
        end_ms=2_000,
        expected_count=4,
        percentile_millis=750,
    )


def _latency_sample(module: ModuleType, sequence: int, value: float) -> object:
    return module.SliWindowSample(
        window_id="latency.runtime.turn",
        kind=module.SliSampleKind.LATENCY_MS,
        sequence=sequence,
        observed_at_ms=1_100 + sequence,
        value=value,
    )


def test_sli_latency_window_is_order_independent_and_replay_idempotent() -> None:
    module = _module("sli_window_contract")
    samples = (
        _latency_sample(module, 3, 40.0),
        _latency_sample(module, 1, 20.0),
        _latency_sample(module, 0, 10.0),
        _latency_sample(module, 1, 20.0),
        _latency_sample(module, 2, 30.0),
    )
    target = _latency_target(module)

    result = module.calculate_sli_window(target, samples, enabled=True)

    assert result.state is module.SliWindowState.COMPLETE
    assert result.reason is module.SliWindowReason.COMPLETE
    assert result.window_id == "latency.runtime.turn"
    assert result.kind is module.SliSampleKind.LATENCY_MS
    assert result.accepted_count == 4
    assert result.value == 30.0
    assert result.slo_pass_claimed is False
    assert result.alert_triggered is False
    assert result.exporter_called is False
    assert module.validate_sli_window_measurement(
        result, target=target, samples=samples
    )


def test_sli_ratio_window_uses_exact_boolean_members() -> None:
    module = _module("sli_window_contract")
    target = module.SliWindowTarget(
        window_id="ratio.task.success",
        kind=module.SliSampleKind.SUCCESS_RATIO_MEMBER,
        start_ms=0,
        end_ms=100,
        expected_count=4,
    )
    samples = tuple(
        module.SliWindowSample(
            window_id=target.window_id,
            kind=target.kind,
            sequence=index,
            observed_at_ms=index,
            value=success,
        )
        for index, success in enumerate((True, False, True, True))
    )

    result = module.calculate_sli_window(target, samples, enabled=True)

    assert result.state is module.SliWindowState.COMPLETE
    assert result.value == 0.75
    with pytest.raises(ValueError, match="exact bool"):
        module.SliWindowSample(
            window_id=target.window_id,
            kind=target.kind,
            sequence=0,
            observed_at_ms=0,
            value=1.0,
        )


def test_sli_incomplete_conflicting_and_out_of_window_samples_fail_closed() -> None:
    module = _module("sli_window_contract")
    target = _latency_target(module)
    incomplete = module.calculate_sli_window(
        target,
        (
            _latency_sample(module, 0, 10.0),
            _latency_sample(module, 1, 20.0),
        ),
        enabled=True,
    )
    conflicting = module.calculate_sli_window(
        target,
        (
            _latency_sample(module, 0, 10.0),
            _latency_sample(module, 0, 11.0),
        ),
        enabled=True,
    )
    outside = _latency_sample(module, 0, 10.0)
    object.__setattr__(outside, "observed_at_ms", 2_000)
    out_of_window = module.calculate_sli_window(target, (outside,), enabled=True)

    assert incomplete.state is module.SliWindowState.INCOMPLETE
    assert incomplete.reason is module.SliWindowReason.MISSING_SEQUENCE
    assert incomplete.missing_count == 2
    assert conflicting.reason is module.SliWindowReason.SAMPLE_CONFLICT
    assert out_of_window.reason is module.SliWindowReason.SAMPLE_OUT_OF_WINDOW
    assert all(
        result.value is None for result in (incomplete, conflicting, out_of_window)
    )


def test_sli_feature_off_touches_no_target_or_samples() -> None:
    module = _module("sli_window_contract")

    class Poison:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(f"feature-off touched {name}")

    result = module.calculate_sli_window(Poison(), Poison(), enabled=False)

    assert result.state is module.SliWindowState.DISABLED
    assert result.reason is module.SliWindowReason.FEATURE_DISABLED
    assert result.lifecycle_authority_exercised is False
    assert result.business_result_changed is False
    with pytest.raises(ValueError, match="state and reason"):
        module.SliWindowMeasurement(
            state=module.SliWindowState.COMPLETE,
            reason=module.SliWindowReason.INVALID_SAMPLE,
            window_id="latency.runtime.turn",
            kind=module.SliSampleKind.LATENCY_MS,
            accepted_count=1,
            missing_count=0,
            value=1.0,
        )


def test_sli_rejects_unbounded_replay_input_before_iteration() -> None:
    module = _module("sli_window_contract")
    samples = (_latency_sample(module, 0, 10.0),) * 20_001

    result = module.calculate_sli_window(_latency_target(module), samples, enabled=True)

    assert result.state is module.SliWindowState.REJECTED
    assert result.reason is module.SliWindowReason.INVALID_SAMPLE
    assert result.window_id == "latency.runtime.turn"
    assert result.accepted_count == 0


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    (
        ("window_id", "latency.other"),
        ("value", 2.0),
        ("exporter_called", 0),
    ),
)
def test_sli_measurement_validation_rejects_forged_result(
    field_name: str,
    forged_value: object,
) -> None:
    module = _module("sli_window_contract")
    target = module.SliWindowTarget(
        window_id="ratio.task.success",
        kind=module.SliSampleKind.SUCCESS_RATIO_MEMBER,
        start_ms=0,
        end_ms=100,
        expected_count=1,
    )
    samples = (
        module.SliWindowSample(
            window_id=target.window_id,
            kind=target.kind,
            sequence=0,
            observed_at_ms=0,
            value=True,
        ),
    )
    result = module.calculate_sli_window(target, samples, enabled=True)
    object.__setattr__(result, field_name, forged_value)

    assert (
        module.validate_sli_window_measurement(result, target=target, samples=samples)
        is False
    )
