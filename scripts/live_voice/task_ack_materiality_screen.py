"""Read-only opportunity screen; it never measures an early-ACK candidate gain."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Final, Sequence

from jiuwenswarm.server.live_voice.latency_probe import LatencyProbeViolation
from jiuwenswarm.server.live_voice.latency_probe_report import (
    LatencyRunReport,
    _load_report,
)


SCHEMA_VERSION: Final = "live-voice.task-ack-materiality.v1"
TASK_PROFILES: Final = ("task_create", "task_status", "task_cancel")
TARGET_SEGMENT: Final = "task_command_to_presentation"
_EXIT_CODES: Final = {
    "ELIGIBLE_FOR_TIER3_CANDIDATE": 0,
    "INVALID_INPUT": 2,
    "NO_MATERIAL_OPPORTUNITY": 3,
    "INSUFFICIENT_VALID_SAMPLES": 4,
    "INTEGRITY_REJECTED": 5,
}


@dataclass(frozen=True, slots=True)
class ProfileOpportunity:
    profile_id: str
    attempts: int
    successful_samples: int
    unknown: int
    failed: int
    cancelled: int
    fallback: int
    underrun: int
    rebuffer: int
    maximum_ack_opportunity_p50_ms: float
    maximum_ack_opportunity_p95_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "attempts": self.attempts,
            "successful_samples": self.successful_samples,
            "unknown": self.unknown,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "fallback": self.fallback,
            "underrun": self.underrun,
            "rebuffer": self.rebuffer,
            "maximum_ack_opportunity_p50_ms": (
                self.maximum_ack_opportunity_p50_ms
            ),
            "maximum_ack_opportunity_p95_ms": (
                self.maximum_ack_opportunity_p95_ms
            ),
        }


@dataclass(frozen=True, slots=True)
class TaskAckMaterialityResult:
    status: str
    reason: str | None
    run_id: str | None
    git_commit: str | None
    minimum_successful_samples: int
    minimum_p50_opportunity_ms: float
    profiles: tuple[ProfileOpportunity, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "reason": self.reason,
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "measurement_boundary": TARGET_SEGMENT,
            "interpretation": "MAXIMUM_CAUSAL_OPPORTUNITY_NOT_PREDICTED_GAIN",
            "candidate_gain_status": "UNMEASURED",
            "minimum_successful_samples": self.minimum_successful_samples,
            "minimum_p50_opportunity_ms": self.minimum_p50_opportunity_ms,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }


def _result(
    *,
    report: LatencyRunReport,
    status: str,
    reason: str | None,
    minimum_successful_samples: int,
    minimum_p50_opportunity_ms: float,
    profiles: list[ProfileOpportunity],
) -> TaskAckMaterialityResult:
    return TaskAckMaterialityResult(
        status=status,
        reason=reason,
        run_id=getattr(report.run, "run_id", None),
        git_commit=getattr(report.run, "git_commit", None),
        minimum_successful_samples=minimum_successful_samples,
        minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
        profiles=tuple(profiles),
    )


def evaluate_report(
    report: LatencyRunReport,
    *,
    minimum_successful_samples: int,
    minimum_p50_opportunity_ms: float,
) -> TaskAckMaterialityResult:
    if (
        minimum_successful_samples < 1
        or not math.isfinite(minimum_p50_opportunity_ms)
        or minimum_p50_opportunity_ms <= 0
    ):
        raise ValueError("materiality thresholds must be positive and finite")

    opportunities: list[ProfileOpportunity] = []
    summaries = []
    for profile_id in TASK_PROFILES:
        try:
            profile = report.profile(profile_id)
        except KeyError:
            return _result(
                report=report,
                status="INVALID_INPUT",
                reason=f"MISSING_{profile_id.upper()}_PROFILE",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )
        try:
            summary = profile.segment(TARGET_SEGMENT)
        except KeyError:
            return _result(
                report=report,
                status="INVALID_INPUT",
                reason=f"MISSING_{profile_id.upper()}_TARGET_SEGMENT",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )
        if summary.p50_ms is None or summary.p95_ms is None:
            return _result(
                report=report,
                status="INSUFFICIENT_VALID_SAMPLES",
                reason=f"{profile_id.upper()}_TIMING_UNKNOWN",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )
        opportunity = ProfileOpportunity(
            profile_id=profile_id,
            attempts=summary.attempts,
            successful_samples=summary.successful_samples,
            unknown=summary.unknown,
            failed=summary.failed,
            cancelled=summary.cancelled,
            fallback=summary.fallback,
            underrun=summary.underrun,
            rebuffer=summary.rebuffer,
            maximum_ack_opportunity_p50_ms=summary.p50_ms,
            maximum_ack_opportunity_p95_ms=summary.p95_ms,
        )
        opportunities.append(opportunity)
        summaries.append((profile_id, summary))

    for profile_id, summary in summaries:
        if any(
            (
                summary.failed,
                summary.cancelled,
                summary.fallback,
                summary.underrun,
                summary.rebuffer,
            )
        ):
            return _result(
                report=report,
                status="INTEGRITY_REJECTED",
                reason=f"{profile_id.upper()}_NONZERO_INTEGRITY_COUNTER",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )

    for profile_id, summary in summaries:
        if summary.unknown != 0:
            return _result(
                report=report,
                status="INSUFFICIENT_VALID_SAMPLES",
                reason=f"{profile_id.upper()}_UNKNOWN_TIMINGS",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )
        if (
            summary.successful_samples < minimum_successful_samples
            or summary.successful_samples != summary.attempts
        ):
            return _result(
                report=report,
                status="INSUFFICIENT_VALID_SAMPLES",
                reason=f"{profile_id.upper()}_DENOMINATOR_INCOMPLETE",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )

    for profile_id, summary in summaries:
        if summary.p50_ms < minimum_p50_opportunity_ms:
            return _result(
                report=report,
                status="NO_MATERIAL_OPPORTUNITY",
                reason=f"{profile_id.upper()}_BELOW_THRESHOLD",
                minimum_successful_samples=minimum_successful_samples,
                minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
                profiles=opportunities,
            )

    return _result(
        report=report,
        status="ELIGIBLE_FOR_TIER3_CANDIDATE",
        reason=None,
        minimum_successful_samples=minimum_successful_samples,
        minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
        profiles=opportunities,
    )


def write_result_exclusive(result: TaskAckMaterialityResult, output: Path) -> None:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(result.to_dict(), stream, indent=2, sort_keys=True)
            stream.write("\n")
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def _invalid_result(
    minimum_successful_samples: int,
    minimum_p50_opportunity_ms: float,
) -> TaskAckMaterialityResult:
    return TaskAckMaterialityResult(
        status="INVALID_INPUT",
        reason="CANONICAL_REPORT_REJECTED",
        run_id=None,
        git_commit=None,
        minimum_successful_samples=minimum_successful_samples,
        minimum_p50_opportunity_ms=minimum_p50_opportunity_ms,
        profiles=(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="task_ack_materiality_screen")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-successful-samples", type=int, default=5)
    parser.add_argument("--minimum-p50-opportunity-ms", type=float, default=500.0)
    args = parser.parse_args(argv)
    try:
        report = _load_report(args.report)
        result = evaluate_report(
            report,
            minimum_successful_samples=args.minimum_successful_samples,
            minimum_p50_opportunity_ms=args.minimum_p50_opportunity_ms,
        )
    except (LatencyProbeViolation, ValueError):
        result = _invalid_result(
            args.minimum_successful_samples,
            args.minimum_p50_opportunity_ms,
        )
    write_result_exclusive(result, args.output)
    print(f"status={result.status} run_id={result.run_id or 'unknown'}")
    return _EXIT_CODES[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
