# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Content-free SLI window arithmetic for P3 diagnostics.

The calculator owns no SLO threshold, alert, exporter, lifecycle, or business
authority. It accepts only already-redacted numeric or boolean samples.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum


_WINDOW_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_MAX_INPUT_SAMPLES = 20_000


class SliSampleKind(StrEnum):
    LATENCY_MS = "latency_ms"
    SUCCESS_RATIO_MEMBER = "success_ratio_member"


class SliWindowState(StrEnum):
    DISABLED = "disabled"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class SliWindowReason(StrEnum):
    FEATURE_DISABLED = "feature_disabled"
    INVALID_TARGET = "invalid_target"
    INVALID_SAMPLE = "invalid_sample"
    SAMPLE_CONFLICT = "sample_conflict"
    SAMPLE_OUT_OF_WINDOW = "sample_out_of_window"
    MISSING_SEQUENCE = "missing_sequence"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class SliWindowTarget:
    window_id: str
    kind: SliSampleKind
    start_ms: int
    end_ms: int
    expected_count: int
    percentile_millis: int = 950

    def __post_init__(self) -> None:
        if (
            type(self.window_id) is not str
            or _WINDOW_ID.fullmatch(self.window_id) is None
        ):
            raise ValueError("window_id must be a bounded identifier")
        if type(self.kind) is not SliSampleKind:
            raise ValueError("kind must use the closed vocabulary")
        if type(self.start_ms) is not int or self.start_ms < 0:
            raise ValueError("start_ms must be a non-negative integer")
        if type(self.end_ms) is not int or self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        if (
            type(self.expected_count) is not int
            or not 1 <= self.expected_count <= 10_000
        ):
            raise ValueError("expected_count is outside the bounded range")
        if (
            type(self.percentile_millis) is not int
            or not 1 <= self.percentile_millis <= 1_000
        ):
            raise ValueError("percentile_millis is outside the bounded range")
        if (
            self.kind is SliSampleKind.SUCCESS_RATIO_MEMBER
            and self.percentile_millis != 950
        ):
            raise ValueError("ratio windows do not accept a percentile override")


@dataclass(frozen=True, slots=True)
class SliWindowSample:
    window_id: str
    kind: SliSampleKind
    sequence: int
    observed_at_ms: int
    value: float | bool

    def __post_init__(self) -> None:
        if (
            type(self.window_id) is not str
            or _WINDOW_ID.fullmatch(self.window_id) is None
        ):
            raise ValueError("sample window_id must be a bounded identifier")
        if type(self.kind) is not SliSampleKind:
            raise ValueError("sample kind must use the closed vocabulary")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sample sequence must be a non-negative integer")
        if type(self.observed_at_ms) is not int or self.observed_at_ms < 0:
            raise ValueError("sample timestamp must be a non-negative integer")
        if self.kind is SliSampleKind.LATENCY_MS:
            if (
                type(self.value) is not float
                or not math.isfinite(self.value)
                or self.value < 0
            ):
                raise ValueError("latency sample must be a non-negative finite float")
        elif type(self.value) is not bool:
            raise ValueError("ratio sample must be exact bool")


@dataclass(frozen=True, slots=True)
class SliWindowMeasurement:
    state: SliWindowState
    reason: SliWindowReason
    window_id: str | None
    kind: SliSampleKind | None
    accepted_count: int
    missing_count: int
    value: float | None
    slo_pass_claimed: bool = False
    alert_triggered: bool = False
    exporter_called: bool = False
    lifecycle_authority_exercised: bool = False
    business_result_changed: bool = False

    def __post_init__(self) -> None:
        if type(self.state) is not SliWindowState:
            raise ValueError("state must use the closed vocabulary")
        if type(self.reason) is not SliWindowReason:
            raise ValueError("reason must use the closed vocabulary")
        if (self.window_id is None) != (self.kind is None):
            raise ValueError("measurement identity must be fully bound or absent")
        if self.window_id is not None and (
            type(self.window_id) is not str
            or _WINDOW_ID.fullmatch(self.window_id) is None
            or type(self.kind) is not SliSampleKind
        ):
            raise ValueError("measurement identity is invalid")
        if type(self.accepted_count) is not int or self.accepted_count < 0:
            raise ValueError("accepted_count must be non-negative")
        if type(self.missing_count) is not int or self.missing_count < 0:
            raise ValueError("missing_count must be non-negative")
        if self.value is not None and (
            type(self.value) is not float
            or not math.isfinite(self.value)
            or self.value < 0
        ):
            raise ValueError("measurement value must be a non-negative finite float")
        if (self.state is SliWindowState.COMPLETE) != (self.value is not None):
            raise ValueError("only a complete window may carry a measurement")
        allowed_reasons = {
            SliWindowState.DISABLED: (SliWindowReason.FEATURE_DISABLED,),
            SliWindowState.REJECTED: (
                SliWindowReason.INVALID_TARGET,
                SliWindowReason.INVALID_SAMPLE,
                SliWindowReason.SAMPLE_CONFLICT,
                SliWindowReason.SAMPLE_OUT_OF_WINDOW,
            ),
            SliWindowState.INCOMPLETE: (SliWindowReason.MISSING_SEQUENCE,),
            SliWindowState.COMPLETE: (SliWindowReason.COMPLETE,),
        }
        if self.reason not in allowed_reasons[self.state]:
            raise ValueError("measurement state and reason must describe one outcome")
        if self.state in (SliWindowState.INCOMPLETE, SliWindowState.COMPLETE) and (
            self.window_id is None
        ):
            raise ValueError("accepted measurements must retain the target identity")
        if self.state is SliWindowState.INCOMPLETE and self.missing_count == 0:
            raise ValueError("an incomplete window must report missing samples")
        if self.state is SliWindowState.COMPLETE and (
            self.accepted_count == 0 or self.missing_count != 0
        ):
            raise ValueError("a complete window requires accepted samples and no gaps")
        if (
            self.state is SliWindowState.COMPLETE
            and self.kind is SliSampleKind.SUCCESS_RATIO_MEMBER
            and self.value is not None
            and not 0.0 <= self.value <= 1.0
        ):
            raise ValueError("a success-ratio measurement must be between zero and one")
        authority = (
            self.slo_pass_claimed,
            self.alert_triggered,
            self.exporter_called,
            self.lifecycle_authority_exercised,
            self.business_result_changed,
        )
        if any(type(value) is not bool for value in authority):
            raise ValueError("SLI authority facts must be exact bools")
        if any(value is not False for value in authority):
            raise ValueError("SLI measurement cannot claim product or SLO authority")


def _measurement(
    *,
    state: SliWindowState,
    reason: SliWindowReason,
    window_id: str | None = None,
    kind: SliSampleKind | None = None,
    accepted_count: int = 0,
    missing_count: int = 0,
    value: float | None = None,
) -> SliWindowMeasurement:
    return SliWindowMeasurement(
        state=state,
        reason=reason,
        window_id=window_id,
        kind=kind,
        accepted_count=accepted_count,
        missing_count=missing_count,
        value=value,
    )


def _validated_target(target: SliWindowTarget) -> SliWindowTarget:
    return SliWindowTarget(
        window_id=target.window_id,
        kind=target.kind,
        start_ms=target.start_ms,
        end_ms=target.end_ms,
        expected_count=target.expected_count,
        percentile_millis=target.percentile_millis,
    )


def _validated_sample(sample: SliWindowSample) -> SliWindowSample:
    return SliWindowSample(
        window_id=sample.window_id,
        kind=sample.kind,
        sequence=sample.sequence,
        observed_at_ms=sample.observed_at_ms,
        value=sample.value,
    )


def calculate_sli_window(
    target: object,
    samples: object,
    *,
    enabled: bool,
) -> SliWindowMeasurement:
    """Calculate one deterministic complete window without external effects."""

    if type(enabled) is not bool:
        raise ValueError("enabled must be exact bool")
    if not enabled:
        return _measurement(
            state=SliWindowState.DISABLED,
            reason=SliWindowReason.FEATURE_DISABLED,
        )
    if type(target) is not SliWindowTarget or type(samples) is not tuple:
        return _measurement(
            state=SliWindowState.REJECTED,
            reason=SliWindowReason.INVALID_TARGET,
        )
    try:
        checked_target = _validated_target(target)
    except Exception:
        return _measurement(
            state=SliWindowState.REJECTED,
            reason=SliWindowReason.INVALID_TARGET,
        )
    identity = {"window_id": checked_target.window_id, "kind": checked_target.kind}
    if len(samples) > _MAX_INPUT_SAMPLES:
        return _measurement(
            state=SliWindowState.REJECTED,
            reason=SliWindowReason.INVALID_SAMPLE,
            **identity,
        )
    by_sequence: dict[int, SliWindowSample] = {}
    for candidate in samples:
        if type(candidate) is not SliWindowSample:
            return _measurement(
                state=SliWindowState.REJECTED,
                reason=SliWindowReason.INVALID_SAMPLE,
                accepted_count=len(by_sequence),
                **identity,
            )
        try:
            sample = _validated_sample(candidate)
        except Exception:
            return _measurement(
                state=SliWindowState.REJECTED,
                reason=SliWindowReason.INVALID_SAMPLE,
                accepted_count=len(by_sequence),
                **identity,
            )
        if (
            sample.window_id != checked_target.window_id
            or sample.kind is not checked_target.kind
            or sample.sequence >= checked_target.expected_count
        ):
            return _measurement(
                state=SliWindowState.REJECTED,
                reason=SliWindowReason.INVALID_SAMPLE,
                accepted_count=len(by_sequence),
                **identity,
            )
        if not checked_target.start_ms <= sample.observed_at_ms < checked_target.end_ms:
            return _measurement(
                state=SliWindowState.REJECTED,
                reason=SliWindowReason.SAMPLE_OUT_OF_WINDOW,
                accepted_count=len(by_sequence),
                **identity,
            )
        previous = by_sequence.get(sample.sequence)
        if previous is not None and previous != sample:
            return _measurement(
                state=SliWindowState.REJECTED,
                reason=SliWindowReason.SAMPLE_CONFLICT,
                accepted_count=len(by_sequence),
                **identity,
            )
        by_sequence[sample.sequence] = sample
    missing = checked_target.expected_count - len(by_sequence)
    if missing:
        return _measurement(
            state=SliWindowState.INCOMPLETE,
            reason=SliWindowReason.MISSING_SEQUENCE,
            accepted_count=len(by_sequence),
            missing_count=missing,
            **identity,
        )
    ordered = tuple(
        by_sequence[index] for index in range(checked_target.expected_count)
    )
    if checked_target.kind is SliSampleKind.SUCCESS_RATIO_MEMBER:
        value = sum(sample.value is True for sample in ordered) / len(ordered)
    else:
        values = sorted(float(sample.value) for sample in ordered)
        rank = max(
            0,
            math.ceil(checked_target.percentile_millis * len(values) / 1_000) - 1,
        )
        value = values[rank]
    return _measurement(
        state=SliWindowState.COMPLETE,
        reason=SliWindowReason.COMPLETE,
        accepted_count=len(ordered),
        value=float(value),
        **identity,
    )


def validate_sli_window_measurement(
    candidate: object,
    *,
    target: object,
    samples: object,
) -> bool:
    """Recompute one untrusted measurement from its exact target and samples."""

    if type(candidate) is not SliWindowMeasurement:
        return False
    try:
        checked = SliWindowMeasurement(
            state=candidate.state,
            reason=candidate.reason,
            window_id=candidate.window_id,
            kind=candidate.kind,
            accepted_count=candidate.accepted_count,
            missing_count=candidate.missing_count,
            value=candidate.value,
            slo_pass_claimed=candidate.slo_pass_claimed,
            alert_triggered=candidate.alert_triggered,
            exporter_called=candidate.exporter_called,
            lifecycle_authority_exercised=candidate.lifecycle_authority_exercised,
            business_result_changed=candidate.business_result_changed,
        )
        expected = calculate_sli_window(target, samples, enabled=True)
    except Exception:
        return False
    return checked == expected


__all__ = [
    "SliSampleKind",
    "SliWindowMeasurement",
    "SliWindowReason",
    "SliWindowSample",
    "SliWindowState",
    "SliWindowTarget",
    "calculate_sli_window",
    "validate_sli_window_measurement",
]
