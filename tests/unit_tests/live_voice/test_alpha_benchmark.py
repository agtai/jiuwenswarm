# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import replace

import pytest

from jiuwenswarm.server.live_voice.alpha_benchmark import (
    AlphaBenchmarkPlan,
    AlphaBenchmarkTarget,
    AlphaBenchmarkTargetReason,
    AlphaBenchmarkViolation,
    build_alpha_benchmark_report,
)
from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    RouteDescriptor,
    TraceBinding,
)


CANDIDATE = "a" * 40
ROUTE = RouteDescriptor(
    implementation_class="formal",
    owner_module="realtime_media",
    capability_provider="gateway_media_v1",
    contract_version="live-voice.contract.v2",
    reason_code=None,
)


def target(**overrides: object) -> AlphaBenchmarkTarget:
    values: dict[str, object] = {
        "target_id": "rm-ingress",
        "segment_name": "runtime.turn",
        "implementation_class": "formal",
        "owner_module": "realtime_media",
        "capability_provider": "gateway_media_v1",
        "min_sample_count": 3,
        "max_failure_count": 0,
        "p50_max_ms": 30.0,
        "p95_max_ms": 80.0,
    }
    values.update(overrides)
    return AlphaBenchmarkTarget(**values)  # type: ignore[arg-type]


def plan(
    *, targets: tuple[AlphaBenchmarkTarget, ...] | None = None
) -> AlphaBenchmarkPlan:
    return AlphaBenchmarkPlan(
        declared_candidate_sha=CANDIDATE,
        declared_environment_id="alpha-local-1",
        declared_evidence_set_id="alpha-evidence-1",
        expected_correlations=("correlation-1", "correlation-2", "correlation-3"),
        targets=targets or (target(),),
    )


def latency(measurement_id: str, correlation_id: str, value: float) -> LiveVoiceMetric:
    return LiveVoiceMetric(
        schema_version="live-voice.observability.v1",
        measurement_id=measurement_id,
        metric_name="live_voice.segment_latency_ms",
        metric_kind="histogram",
        unit="milliseconds",
        value=value,
        observed_at="2026-08-08T08:00:00Z",
        binding=TraceBinding(
            correlation_id=correlation_id,
            interaction_id=f"interaction-{correlation_id}",
            turn_id=f"turn-{correlation_id}",
        ),
        route=ROUTE,
        segment_name="runtime.turn",
        implementation_class="formal",
        outcome="completed",
    )


def failure(
    measurement_id: str, correlation_id: str, value: int = 1
) -> LiveVoiceMetric:
    return LiveVoiceMetric(
        schema_version="live-voice.observability.v1",
        measurement_id=measurement_id,
        metric_name="live_voice.failure_total",
        metric_kind="counter",
        unit="count",
        value=value,
        observed_at="2026-08-08T08:00:00Z",
        binding=TraceBinding(
            correlation_id=correlation_id,
            interaction_id=f"interaction-{correlation_id}",
            turn_id=f"turn-{correlation_id}",
        ),
        route=ROUTE,
        segment_name="runtime.turn",
        implementation_class="formal",
        reason_code="UNAVAILABLE",
        error_code="UNAVAILABLE",
    )


def unsupported_metric() -> LiveVoiceMetric:
    return LiveVoiceMetric(
        schema_version="live-voice.observability.v1",
        measurement_id="queue-depth-1",
        metric_name="live_voice.queue_depth",
        metric_kind="gauge",
        unit="items",
        value=1,
        observed_at="2026-08-08T08:00:00Z",
        binding=TraceBinding(correlation_id="correlation-1"),
        route=ROUTE,
        segment_name="runtime.queue",
        implementation_class="formal",
    )


def test_report_binds_candidate_environment_correlations_and_nearest_rank() -> None:
    report = build_alpha_benchmark_report(
        enabled=True,
        plan=plan(),
        metrics=(
            latency("metric-1", "correlation-1", 10.0),
            latency("metric-2", "correlation-2", 20.0),
            latency("metric-3", "correlation-3", 70.0),
        ),
    )

    assert report.enabled is True
    assert report.plan == plan()
    assert (
        report.plan_sha256
        == "fc8b6f853b6c76ab1afc0a11696b63dc3d6e814fe6fd7349f2bd404efae6ee95"
    )
    assert report.measurement_count == 3
    assert report.all_provisional_latency_targets_met is True
    assert report.all_automated_targets_met is False
    assert report.binding_verified is False
    assert report.evidence_scope == "unverified_automated_benchmark_only"
    assert report.alpha_gate_pass is False
    result = report.target_results[0]
    assert (result.sample_count, result.observed_failure_count) == (3, 0)
    assert (result.p50_ms, result.p95_ms) == (20.0, 70.0)
    assert result.target_met is False
    assert result.failure_coverage_verified is False
    assert result.reason_codes == (
        AlphaBenchmarkTargetReason.FAILURE_COVERAGE_UNVERIFIED,
    )


def test_declared_binding_is_never_promoted_to_verified_candidate_truth() -> None:
    metrics = tuple(
        latency(f"metric-{index}", f"correlation-{index}", float(index))
        for index in range(1, 4)
    )
    first = build_alpha_benchmark_report(enabled=True, plan=plan(), metrics=metrics)
    relabelled_plan = replace(
        plan(),
        declared_candidate_sha="b" * 40,
        declared_environment_id="alpha-other",
        declared_evidence_set_id="alpha-evidence-other",
    )
    second = build_alpha_benchmark_report(
        enabled=True,
        plan=relabelled_plan,
        metrics=metrics,
    )

    assert first.all_provisional_latency_targets_met is True
    assert second.all_provisional_latency_targets_met is True
    assert first.all_automated_targets_met is False
    assert second.all_automated_targets_met is False
    assert first.binding_verified is second.binding_verified is False
    assert first.plan_sha256 != second.plan_sha256
    assert not hasattr(first, "candidate_sha")
    assert first.alpha_gate_pass is second.alpha_gate_pass is False


def test_incomplete_coverage_target_excess_and_failures_remain_explicit() -> None:
    report = build_alpha_benchmark_report(
        enabled=True,
        plan=plan(),
        metrics=(
            latency("metric-1", "correlation-1", 90.0),
            latency("metric-2", "correlation-2", 100.0),
            failure("failure-1", "correlation-1"),
        ),
    )
    result = report.target_results[0]
    assert report.all_automated_targets_met is False
    assert result.target_met is False
    assert result.reason_codes == (
        AlphaBenchmarkTargetReason.CORRELATION_COVERAGE_INCOMPLETE,
        AlphaBenchmarkTargetReason.SAMPLE_COUNT_INCOMPLETE,
        AlphaBenchmarkTargetReason.P50_TARGET_EXCEEDED,
        AlphaBenchmarkTargetReason.P95_TARGET_EXCEEDED,
        AlphaBenchmarkTargetReason.FAILURE_COUNT_EXCEEDED,
        AlphaBenchmarkTargetReason.FAILURE_COVERAGE_UNVERIFIED,
    )


def test_omitted_failure_events_can_never_yield_a_met_target() -> None:
    report = build_alpha_benchmark_report(
        enabled=True,
        plan=plan(),
        metrics=tuple(
            latency(f"metric-{index}", f"correlation-{index}", 10.0)
            for index in range(1, 4)
        ),
    )

    result = report.target_results[0]
    assert result.observed_failure_count == 0
    assert result.provisional_latency_target_met is True
    assert result.failure_coverage_verified is False
    assert result.target_met is False
    assert AlphaBenchmarkTargetReason.FAILURE_COVERAGE_UNVERIFIED in result.reason_codes


def test_route_provenance_is_exact_and_fallback_cannot_satisfy_formal_target() -> None:
    fallback_route = RouteDescriptor(
        implementation_class="fallback",
        owner_module="realtime_media",
        capability_provider="browser_compatibility",
        contract_version=None,
        reason_code="ROUTE_FALLBACK",
    )
    metrics = tuple(
        replace(
            latency(f"metric-{index}", f"correlation-{index}", 1.0),
            route=fallback_route,
            implementation_class="fallback",
        )
        for index in range(1, 4)
    )
    with pytest.raises(AlphaBenchmarkViolation) as undeclared_route:
        build_alpha_benchmark_report(enabled=True, plan=plan(), metrics=metrics)
    assert undeclared_route.value.reason == "UNDECLARED_BENCHMARK_ROUTE"
    with pytest.raises(AlphaBenchmarkViolation, match="cannot relabel"):
        target(implementation_class="fallback")


@pytest.mark.parametrize(
    ("metrics", "reason"),
    [
        (
            (
                latency("same", "correlation-1", 1.0),
                latency("same", "correlation-2", 2.0),
            ),
            "DUPLICATE_MEASUREMENT",
        ),
        ((latency("metric", "foreign-correlation", 1.0),), "UNDECLARED_CORRELATION"),
        ((unsupported_metric(),), "UNSUPPORTED_BENCHMARK_METRIC"),
        ((object(),), "INVALID_BENCHMARK_METRIC"),
    ],
)
def test_mixed_or_untrusted_evidence_fails_closed(metrics: object, reason: str) -> None:
    with pytest.raises(AlphaBenchmarkViolation) as captured:
        build_alpha_benchmark_report(enabled=True, plan=plan(), metrics=metrics)
    assert captured.value.reason == reason


def test_feature_off_reads_no_plan_or_metrics_and_never_claims_gate_pass() -> None:
    class ExplodesOnAccess:
        def __getattribute__(self, name: str) -> object:
            raise AssertionError(name)

        def __iter__(self):
            raise AssertionError("iterated")

    report = build_alpha_benchmark_report(
        enabled=False,
        plan=ExplodesOnAccess(),
        metrics=ExplodesOnAccess(),
    )
    assert report.measurement_count == 0
    assert report.target_results == ()
    assert report.all_provisional_latency_targets_met is False
    assert report.all_automated_targets_met is False
    assert report.alpha_gate_pass is False


def test_cumulative_failure_counter_cannot_be_double_counted_as_delta_events() -> None:
    with pytest.raises(AlphaBenchmarkViolation) as ambiguous:
        build_alpha_benchmark_report(
            enabled=True,
            plan=plan(),
            metrics=(failure("failure-cumulative", "correlation-1", value=2),),
        )
    assert ambiguous.value.reason == "AMBIGUOUS_FAILURE_COUNTER"


def test_plan_rejects_duplicate_correlations_targets_and_non_full_sha() -> None:
    with pytest.raises(AlphaBenchmarkViolation) as duplicate_correlation:
        AlphaBenchmarkPlan(
            CANDIDATE,
            "alpha-local-1",
            "alpha-evidence-1",
            ("correlation-1", "correlation-1"),
            (target(),),
        )
    assert duplicate_correlation.value.reason == "DUPLICATE_CORRELATION"

    with pytest.raises(AlphaBenchmarkViolation) as duplicate_target:
        plan(targets=(target(), target()))
    assert duplicate_target.value.reason == "DUPLICATE_BENCHMARK_TARGET"

    with pytest.raises(AlphaBenchmarkViolation) as duplicate_route:
        plan(targets=(target(), target(target_id="same-route")))
    assert duplicate_route.value.reason == "DUPLICATE_BENCHMARK_ROUTE"

    with pytest.raises(AlphaBenchmarkViolation) as invalid_sha:
        AlphaBenchmarkPlan(
            "short",
            "alpha-local-1",
            "alpha-evidence-1",
            ("correlation-1",),
            (target(),),
        )
    assert invalid_sha.value.reason == "INVALID_CANDIDATE_SHA"


def test_plan_digest_canonicalizes_equal_numeric_targets_and_rejects_overflow() -> None:
    integer_target = target(p50_max_ms=30, p95_max_ms=80)
    float_target = target(p50_max_ms=30.0, p95_max_ms=80.0)
    integer_plan = plan(targets=(integer_target,))
    float_plan = plan(targets=(float_target,))

    assert integer_plan == float_plan
    integer_report = build_alpha_benchmark_report(
        enabled=True,
        plan=integer_plan,
        metrics=(),
    )
    float_report = build_alpha_benchmark_report(
        enabled=True,
        plan=float_plan,
        metrics=(),
    )
    assert integer_report.plan_sha256 == float_report.plan_sha256

    with pytest.raises(AlphaBenchmarkViolation) as overflow:
        target(p50_max_ms=10**10_000)
    assert overflow.value.reason == "INVALID_BENCHMARK_TARGET"
