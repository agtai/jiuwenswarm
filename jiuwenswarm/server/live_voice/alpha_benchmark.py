# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Deterministic, evidence-bounded Live Voice Alpha benchmark summaries.

This module deliberately performs no I/O and grants no acceptance credit.  It
only summarizes already-validated public X-OBS metrics for one caller-declared
candidate/environment and one predeclared set of correlations.  Artifact
signing, candidate verification, real-path attribution, assisted observation,
and the Alpha Gate remain separate owners.
"""

from __future__ import annotations

import math
import re
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    create_metric,
)


_CANDIDATE_SHA = re.compile(r"[0-9a-f]{40}")
_SAFE_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:@/-]{0,126}[A-Za-z0-9])?")


class AlphaBenchmarkViolation(ValueError):
    """Raised when a benchmark boundary is ambiguous or mixes evidence."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class AlphaBenchmarkTargetReason(StrEnum):
    """Closed target outcomes; none of them is an Alpha Gate decision."""

    CORRELATION_COVERAGE_INCOMPLETE = "CORRELATION_COVERAGE_INCOMPLETE"
    SAMPLE_COUNT_INCOMPLETE = "SAMPLE_COUNT_INCOMPLETE"
    P50_TARGET_EXCEEDED = "P50_TARGET_EXCEEDED"
    P95_TARGET_EXCEEDED = "P95_TARGET_EXCEEDED"
    FAILURE_COUNT_EXCEEDED = "FAILURE_COUNT_EXCEEDED"
    FAILURE_COVERAGE_UNVERIFIED = "FAILURE_COVERAGE_UNVERIFIED"


def _safe_label(value: object, field_name: str) -> str:
    if type(value) is not str or _SAFE_LABEL.fullmatch(value) is None:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_LABEL", f"{field_name} must be one bounded safe label"
        )
    return value


def _positive_safe_integer(value: object, field_name: str) -> int:
    if type(value) is not int or not 0 < value <= 9_007_199_254_740_991:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_TARGET", f"{field_name} must be a positive safe integer"
        )
    return value


def _nonnegative_safe_integer(value: object, field_name: str) -> int:
    if type(value) is not int or not 0 <= value <= 9_007_199_254_740_991:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_TARGET",
            f"{field_name} must be a non-negative safe integer",
        )
    return value


def _positive_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_TARGET", f"{field_name} must be positive and finite"
        )
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        normalized = math.inf
    if not math.isfinite(normalized) or normalized <= 0:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_TARGET", f"{field_name} must be positive and finite"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkTarget:
    """One exact route target for latency samples and governed failures."""

    target_id: str
    segment_name: str
    implementation_class: str
    owner_module: str
    capability_provider: str
    min_sample_count: int
    max_failure_count: int = 0
    p50_max_ms: float | None = None
    p95_max_ms: float | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "target_id",
            "segment_name",
            "implementation_class",
            "owner_module",
            "capability_provider",
        ):
            _safe_label(getattr(self, field_name), field_name)
        if self.implementation_class != "formal":
            raise AlphaBenchmarkViolation(
                "NONFORMAL_TARGET",
                "an Alpha benchmark target cannot relabel fallback or substitute samples",
            )
        _positive_safe_integer(self.min_sample_count, "min_sample_count")
        _nonnegative_safe_integer(self.max_failure_count, "max_failure_count")
        if self.p50_max_ms is not None:
            object.__setattr__(
                self, "p50_max_ms", _positive_finite(self.p50_max_ms, "p50_max_ms")
            )
        if self.p95_max_ms is not None:
            object.__setattr__(
                self, "p95_max_ms", _positive_finite(self.p95_max_ms, "p95_max_ms")
            )
        if self.p50_max_ms is None and self.p95_max_ms is None:
            raise AlphaBenchmarkViolation(
                "MISSING_LATENCY_TARGET", "at least one latency target is required"
            )


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkPlan:
    """Immutable inputs that must be frozen before collecting report samples."""

    declared_candidate_sha: str
    declared_environment_id: str
    declared_evidence_set_id: str
    expected_correlations: tuple[str, ...]
    targets: tuple[AlphaBenchmarkTarget, ...]

    def __post_init__(self) -> None:
        if (
            type(self.declared_candidate_sha) is not str
            or _CANDIDATE_SHA.fullmatch(self.declared_candidate_sha) is None
        ):
            raise AlphaBenchmarkViolation(
                "INVALID_CANDIDATE_SHA",
                "declared_candidate_sha must be one lowercase full SHA",
            )
        _safe_label(self.declared_environment_id, "declared_environment_id")
        _safe_label(self.declared_evidence_set_id, "declared_evidence_set_id")
        if (
            type(self.expected_correlations) is not tuple
            or not self.expected_correlations
            or any(type(value) is not str for value in self.expected_correlations)
        ):
            raise AlphaBenchmarkViolation(
                "INVALID_CORRELATION_PLAN",
                "expected_correlations must be one non-empty immutable tuple",
            )
        for value in self.expected_correlations:
            _safe_label(value, "expected_correlation")
        if len(set(self.expected_correlations)) != len(self.expected_correlations):
            raise AlphaBenchmarkViolation(
                "DUPLICATE_CORRELATION", "expected correlations must be unique"
            )
        if (
            type(self.targets) is not tuple
            or not self.targets
            or any(type(target) is not AlphaBenchmarkTarget for target in self.targets)
        ):
            raise AlphaBenchmarkViolation(
                "INVALID_BENCHMARK_TARGETS", "targets must be a non-empty exact tuple"
            )
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise AlphaBenchmarkViolation(
                "DUPLICATE_BENCHMARK_TARGET", "target IDs must be unique"
            )
        route_keys = [_target_route_key(target) for target in self.targets]
        if len(set(route_keys)) != len(route_keys):
            raise AlphaBenchmarkViolation(
                "DUPLICATE_BENCHMARK_ROUTE",
                "one exact route can have only one benchmark target",
            )


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkTargetResult:
    target_id: str
    sample_count: int
    observed_failure_count: int
    observed_correlation_count: int
    expected_correlation_count: int
    p50_ms: float | None
    p95_ms: float | None
    provisional_latency_target_met: bool
    target_met: bool
    reason_codes: tuple[AlphaBenchmarkTargetReason, ...]
    failure_coverage_verified: bool = False


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkReport:
    enabled: bool
    plan: AlphaBenchmarkPlan | None
    plan_sha256: str | None
    measurement_count: int
    target_results: tuple[AlphaBenchmarkTargetResult, ...]
    all_provisional_latency_targets_met: bool
    all_automated_targets_met: bool
    binding_verified: bool = field(default=False, init=False)
    evidence_scope: str = field(
        default="unverified_automated_benchmark_only", init=False
    )
    alpha_gate_pass: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkCase:
    """One predeclared executable sample owned by an external test harness."""

    case_id: str
    target_id: str
    correlation_id: str
    operation: Callable[[], Awaitable[object]] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _safe_label(self.case_id, "case_id")
        _safe_label(self.target_id, "target_id")
        _safe_label(self.correlation_id, "correlation_id")
        if not callable(self.operation):
            raise AlphaBenchmarkViolation(
                "INVALID_BENCHMARK_CASE", "case operation must be callable"
            )


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkSample:
    case_id: str
    target_id: str
    correlation_id: str
    elapsed_ms: float
    failed: bool
    failure_class: str | None


@dataclass(frozen=True, slots=True)
class AlphaBenchmarkExecution:
    enabled: bool
    samples: tuple[AlphaBenchmarkSample, ...]
    report: AlphaBenchmarkReport


def _percentile(values: list[float], quantile: float) -> float:
    """Return a deterministic nearest-rank percentile for a non-empty sample."""

    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _same_route(metric: LiveVoiceMetric, target: AlphaBenchmarkTarget) -> bool:
    return (
        metric.segment_name == target.segment_name
        and metric.implementation_class == target.implementation_class
        and metric.route.owner_module == target.owner_module
        and metric.route.capability_provider == target.capability_provider
    )


def _target_route_key(target: AlphaBenchmarkTarget) -> tuple[str, str, str, str]:
    return (
        target.segment_name,
        target.implementation_class,
        target.owner_module,
        target.capability_provider,
    )


def _plan_sha256(plan: AlphaBenchmarkPlan) -> str:
    payload = {
        "declared_candidate_sha": plan.declared_candidate_sha,
        "declared_environment_id": plan.declared_environment_id,
        "declared_evidence_set_id": plan.declared_evidence_set_id,
        "expected_correlations": list(plan.expected_correlations),
        "targets": [
            {
                "target_id": target.target_id,
                "segment_name": target.segment_name,
                "implementation_class": target.implementation_class,
                "owner_module": target.owner_module,
                "capability_provider": target.capability_provider,
                "min_sample_count": target.min_sample_count,
                "max_failure_count": target.max_failure_count,
                "p50_max_ms": target.p50_max_ms,
                "p95_max_ms": target.p95_max_ms,
            }
            for target in plan.targets
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evaluate_target(
    target: AlphaBenchmarkTarget,
    metrics: tuple[LiveVoiceMetric, ...],
    expected_correlations: frozenset[str],
) -> AlphaBenchmarkTargetResult:
    latency = [
        metric
        for metric in metrics
        if metric.metric_name == "live_voice.segment_latency_ms"
        and _same_route(metric, target)
    ]
    failures = [
        metric
        for metric in metrics
        if metric.metric_name == "live_voice.failure_total"
        and _same_route(metric, target)
    ]
    values = [metric.value for metric in latency]
    correlations = frozenset(metric.binding.correlation_id for metric in latency)
    observed_failure_count = int(sum(metric.value for metric in failures))
    p50 = _percentile(values, 0.50) if values else None
    p95 = _percentile(values, 0.95) if values else None

    reasons: list[AlphaBenchmarkTargetReason] = []
    if correlations != expected_correlations:
        reasons.append(AlphaBenchmarkTargetReason.CORRELATION_COVERAGE_INCOMPLETE)
    if len(values) < target.min_sample_count:
        reasons.append(AlphaBenchmarkTargetReason.SAMPLE_COUNT_INCOMPLETE)
    if target.p50_max_ms is not None and (p50 is None or p50 > target.p50_max_ms):
        reasons.append(AlphaBenchmarkTargetReason.P50_TARGET_EXCEEDED)
    if target.p95_max_ms is not None and (p95 is None or p95 > target.p95_max_ms):
        reasons.append(AlphaBenchmarkTargetReason.P95_TARGET_EXCEEDED)
    if observed_failure_count > target.max_failure_count:
        reasons.append(AlphaBenchmarkTargetReason.FAILURE_COUNT_EXCEEDED)
    provisional_latency_target_met = not any(
        reason
        in {
            AlphaBenchmarkTargetReason.CORRELATION_COVERAGE_INCOMPLETE,
            AlphaBenchmarkTargetReason.SAMPLE_COUNT_INCOMPLETE,
            AlphaBenchmarkTargetReason.P50_TARGET_EXCEEDED,
            AlphaBenchmarkTargetReason.P95_TARGET_EXCEEDED,
        }
        for reason in reasons
    )
    # failure_total is an event delta, so absence is not evidence of zero.
    # This I/O-free summarizer has no authoritative collector-closure proof and
    # therefore cannot positively evaluate max_failure_count or target_met.
    reasons.append(AlphaBenchmarkTargetReason.FAILURE_COVERAGE_UNVERIFIED)
    return AlphaBenchmarkTargetResult(
        target_id=target.target_id,
        sample_count=len(values),
        observed_failure_count=observed_failure_count,
        observed_correlation_count=len(correlations),
        expected_correlation_count=len(expected_correlations),
        p50_ms=p50,
        p95_ms=p95,
        provisional_latency_target_met=provisional_latency_target_met,
        target_met=False,
        reason_codes=tuple(reasons),
    )


def _evaluate_executed_target(
    target: AlphaBenchmarkTarget,
    samples: tuple[AlphaBenchmarkSample, ...],
    expected_correlations: frozenset[str],
) -> AlphaBenchmarkTargetResult:
    selected = tuple(
        sample for sample in samples if sample.target_id == target.target_id
    )
    values = [sample.elapsed_ms for sample in selected]
    correlations = frozenset(sample.correlation_id for sample in selected)
    observed_failure_count = sum(sample.failed for sample in selected)
    p50 = _percentile(values, 0.50) if values else None
    p95 = _percentile(values, 0.95) if values else None
    reasons: list[AlphaBenchmarkTargetReason] = []
    if correlations != expected_correlations:
        reasons.append(AlphaBenchmarkTargetReason.CORRELATION_COVERAGE_INCOMPLETE)
    if len(values) < target.min_sample_count:
        reasons.append(AlphaBenchmarkTargetReason.SAMPLE_COUNT_INCOMPLETE)
    if target.p50_max_ms is not None and (p50 is None or p50 > target.p50_max_ms):
        reasons.append(AlphaBenchmarkTargetReason.P50_TARGET_EXCEEDED)
    if target.p95_max_ms is not None and (p95 is None or p95 > target.p95_max_ms):
        reasons.append(AlphaBenchmarkTargetReason.P95_TARGET_EXCEEDED)
    if observed_failure_count > target.max_failure_count:
        reasons.append(AlphaBenchmarkTargetReason.FAILURE_COUNT_EXCEEDED)
    target_met = not reasons
    return AlphaBenchmarkTargetResult(
        target_id=target.target_id,
        sample_count=len(values),
        observed_failure_count=observed_failure_count,
        observed_correlation_count=len(correlations),
        expected_correlation_count=len(expected_correlations),
        p50_ms=p50,
        p95_ms=p95,
        provisional_latency_target_met=not any(
            reason
            in {
                AlphaBenchmarkTargetReason.CORRELATION_COVERAGE_INCOMPLETE,
                AlphaBenchmarkTargetReason.SAMPLE_COUNT_INCOMPLETE,
                AlphaBenchmarkTargetReason.P50_TARGET_EXCEEDED,
                AlphaBenchmarkTargetReason.P95_TARGET_EXCEEDED,
            }
            for reason in reasons
        ),
        target_met=target_met,
        reason_codes=tuple(reasons),
        failure_coverage_verified=True,
    )


async def run_alpha_benchmark(
    *,
    enabled: bool = False,
    plan: object = None,
    cases: object = None,
    monotonic: Callable[[], float] | None = None,
) -> AlphaBenchmarkExecution:
    """Run exact declared cases sequentially and produce a closed failure count.

    The runner intentionally performs no candidate/environment verification and
    never grants Alpha acceptance.  A caller may bind real or deterministic
    fixture operations to the cases; the returned report distinguishes this
    closed automated execution from the separately required real-path evidence.
    """

    if type(enabled) is not bool:
        raise AlphaBenchmarkViolation("INVALID_ENABLED", "enabled must be boolean")
    if not enabled:
        return AlphaBenchmarkExecution(
            False,
            (),
            AlphaBenchmarkReport(False, None, None, 0, (), False, False),
        )
    if type(plan) is not AlphaBenchmarkPlan:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_PLAN", "enabled benchmark requires an exact plan"
        )
    if (
        type(cases) is not tuple
        or not cases
        or any(type(case) is not AlphaBenchmarkCase for case in cases)
    ):
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_CASES", "cases must be one non-empty exact tuple"
        )
    clock = monotonic
    if not callable(clock):
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_CLOCK", "enabled runner requires a monotonic clock"
        )
    target_ids = frozenset(target.target_id for target in plan.targets)
    expected_correlations = frozenset(plan.expected_correlations)
    case_ids: set[str] = set()
    for case in cases:
        if case.case_id in case_ids:
            raise AlphaBenchmarkViolation(
                "DUPLICATE_BENCHMARK_CASE", "case IDs cannot be reused"
            )
        if case.target_id not in target_ids:
            raise AlphaBenchmarkViolation(
                "UNDECLARED_BENCHMARK_TARGET", "case target is not declared"
            )
        if case.correlation_id not in expected_correlations:
            raise AlphaBenchmarkViolation(
                "UNDECLARED_CORRELATION", "case correlation is not declared"
            )
        case_ids.add(case.case_id)

    samples: list[AlphaBenchmarkSample] = []
    for case in cases:
        started = clock()
        if isinstance(started, bool) or not isinstance(started, (int, float)):
            raise AlphaBenchmarkViolation(
                "INVALID_BENCHMARK_CLOCK", "monotonic clock returned a non-number"
            )
        failed = False
        failure_class = None
        try:
            await case.operation()
        except Exception as exc:  # noqa: BLE001 - failure is a benchmark outcome
            failed = True
            failure_class = type(exc).__name__
        ended = clock()
        if (
            isinstance(ended, bool)
            or not isinstance(ended, (int, float))
            or not math.isfinite(float(started))
            or not math.isfinite(float(ended))
            or float(ended) < float(started)
        ):
            raise AlphaBenchmarkViolation(
                "INVALID_BENCHMARK_CLOCK", "monotonic clock regressed or overflowed"
            )
        samples.append(
            AlphaBenchmarkSample(
                case_id=case.case_id,
                target_id=case.target_id,
                correlation_id=case.correlation_id,
                elapsed_ms=(float(ended) - float(started)) * 1000,
                failed=failed,
                failure_class=failure_class,
            )
        )

    exact_samples = tuple(samples)
    results = tuple(
        _evaluate_executed_target(target, exact_samples, expected_correlations)
        for target in plan.targets
    )
    report = AlphaBenchmarkReport(
        enabled=True,
        plan=plan,
        plan_sha256=_plan_sha256(plan),
        measurement_count=len(exact_samples),
        target_results=results,
        all_provisional_latency_targets_met=all(
            result.provisional_latency_target_met for result in results
        ),
        all_automated_targets_met=all(result.target_met for result in results),
    )
    return AlphaBenchmarkExecution(True, exact_samples, report)


def build_alpha_benchmark_report(
    *,
    enabled: bool = False,
    plan: object = None,
    metrics: object = None,
) -> AlphaBenchmarkReport:
    """Summarize exact public metrics without I/O, fallback, or Gate claims.

    Feature-off returns before reading or iterating ``plan`` or ``metrics``.
    Enabled evaluation rejects undeclared correlations, duplicate measurement
    identities, non-public metric objects, and route mixing before reporting.
    """

    if type(enabled) is not bool:
        raise AlphaBenchmarkViolation("INVALID_ENABLED", "enabled must be boolean")
    if not enabled:
        return AlphaBenchmarkReport(False, None, None, 0, (), False, False)
    if type(plan) is not AlphaBenchmarkPlan:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_PLAN", "enabled benchmark requires an exact plan"
        )
    if type(metrics) is not tuple:
        raise AlphaBenchmarkViolation(
            "INVALID_BENCHMARK_METRICS", "metrics must be one immutable tuple"
        )

    expected_correlations = frozenset(plan.expected_correlations)
    validated: list[LiveVoiceMetric] = []
    measurement_ids: set[str] = set()
    for candidate in metrics:
        if type(candidate) is not LiveVoiceMetric:
            raise AlphaBenchmarkViolation(
                "INVALID_BENCHMARK_METRIC",
                "benchmark accepts exact public metrics only",
            )
        metric = create_metric(candidate)
        if metric.metric_name not in {
            "live_voice.segment_latency_ms",
            "live_voice.failure_total",
        }:
            raise AlphaBenchmarkViolation(
                "UNSUPPORTED_BENCHMARK_METRIC",
                "benchmark accepts only governed latency and failure metrics",
            )
        if metric.metric_name == "live_voice.failure_total" and metric.value != 1:
            raise AlphaBenchmarkViolation(
                "AMBIGUOUS_FAILURE_COUNTER",
                "failure_total must be a unit delta; cumulative snapshots are unsupported",
            )
        if not any(_same_route(metric, target) for target in plan.targets):
            raise AlphaBenchmarkViolation(
                "UNDECLARED_BENCHMARK_ROUTE",
                "a benchmark metric does not match one predeclared exact route",
            )
        if metric.measurement_id in measurement_ids:
            raise AlphaBenchmarkViolation(
                "DUPLICATE_MEASUREMENT", "measurement IDs cannot be reused"
            )
        if metric.binding.correlation_id not in expected_correlations:
            raise AlphaBenchmarkViolation(
                "UNDECLARED_CORRELATION",
                "a benchmark metric does not belong to the predeclared evidence set",
            )
        measurement_ids.add(metric.measurement_id)
        validated.append(metric)

    exact_metrics = tuple(validated)
    results = tuple(
        _evaluate_target(target, exact_metrics, expected_correlations)
        for target in plan.targets
    )
    return AlphaBenchmarkReport(
        enabled=True,
        plan=plan,
        plan_sha256=_plan_sha256(plan),
        measurement_count=len(exact_metrics),
        target_results=results,
        all_provisional_latency_targets_met=all(
            result.provisional_latency_target_met for result in results
        ),
        all_automated_targets_met=False,
    )


__all__ = [
    "AlphaBenchmarkCase",
    "AlphaBenchmarkExecution",
    "AlphaBenchmarkPlan",
    "AlphaBenchmarkReport",
    "AlphaBenchmarkSample",
    "AlphaBenchmarkTarget",
    "AlphaBenchmarkTargetReason",
    "AlphaBenchmarkTargetResult",
    "AlphaBenchmarkViolation",
    "build_alpha_benchmark_report",
    "run_alpha_benchmark",
]
