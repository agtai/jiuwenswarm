from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.latency_probe_report import (
    FIXED_SEGMENTS,
    LatencyRunReport,
    ProfileLatencyReport,
    REPORT_SCHEMA_VERSION,
    SegmentSummary,
)
from scripts.live_voice.task_ack_materiality_screen import (
    _EXIT_CODES,
    evaluate_report,
    write_result_exclusive,
)


_TASK_PROFILES = ("task_create", "task_status", "task_cancel")
_SEGMENT = next(
    item for item in FIXED_SEGMENTS
    if item.segment_id == "task_command_to_presentation"
)


def _summary(
    p50_ms: float = 1500.0,
    *,
    attempts: int = 5,
    successful: int = 5,
    unknown: int = 0,
    failed: int = 0,
    cancelled: int = 0,
    fallback: int = 0,
    underrun: int = 0,
    rebuffer: int = 0,
) -> SegmentSummary:
    values = (p50_ms - 100.0, p50_ms, p50_ms + 200.0, p50_ms + 300.0)
    return SegmentSummary(
        _SEGMENT,
        attempts,
        successful,
        unknown,
        failed,
        cancelled,
        fallback,
        underrun,
        rebuffer,
        *values,
    )


def _report(**overrides: SegmentSummary) -> LatencyRunReport:
    profiles = tuple(
        ProfileLatencyReport(profile, (overrides.get(profile, _summary()),))
        for profile in _TASK_PROFILES
    )
    run = SimpleNamespace(run_id="task-ack-screen-a1", git_commit="abc123def")
    return LatencyRunReport(REPORT_SCHEMA_VERSION, run, profiles)  # type: ignore[arg-type]


def test_complete_material_population_is_eligible() -> None:
    result = evaluate_report(
        _report(), minimum_successful_samples=5, minimum_p50_opportunity_ms=500
    )

    assert result.status == "ELIGIBLE_FOR_TIER3_CANDIDATE"
    assert result.run_id == "task-ack-screen-a1"
    assert [item.profile_id for item in result.profiles] == list(_TASK_PROFILES)
    assert all(item.maximum_ack_opportunity_p50_ms == 1500.0 for item in result.profiles)


def test_terminal_statuses_have_exhaustive_exit_codes() -> None:
    assert set(_EXIT_CODES) == {
        "ELIGIBLE_FOR_TIER3_CANDIDATE",
        "INVALID_INPUT",
        "NO_MATERIAL_OPPORTUNITY",
        "INSUFFICIENT_VALID_SAMPLES",
        "INTEGRITY_REJECTED",
    }
    assert len(set(_EXIT_CODES.values())) == len(_EXIT_CODES)


def test_subthreshold_profile_rejects_materiality() -> None:
    result = evaluate_report(
        _report(task_status=_summary(499.0)),
        minimum_successful_samples=5,
        minimum_p50_opportunity_ms=500,
    )

    assert result.status == "NO_MATERIAL_OPPORTUNITY"
    assert result.reason == "TASK_STATUS_BELOW_THRESHOLD"


def test_integrity_failure_precedes_an_earlier_subthreshold_profile() -> None:
    result = evaluate_report(
        _report(
            task_create=_summary(100.0),
            task_status=_summary(failed=1),
        ),
        minimum_successful_samples=5,
        minimum_p50_opportunity_ms=500,
    )

    assert result.status == "INTEGRITY_REJECTED"
    assert result.reason == "TASK_STATUS_NONZERO_INTEGRITY_COUNTER"


@pytest.mark.parametrize(
    ("summary", "status"),
    [
        (_summary(attempts=5, successful=4, unknown=1), "INSUFFICIENT_VALID_SAMPLES"),
        (_summary(failed=1), "INTEGRITY_REJECTED"),
        (_summary(cancelled=1), "INTEGRITY_REJECTED"),
        (_summary(fallback=1), "INTEGRITY_REJECTED"),
        (_summary(underrun=1), "INTEGRITY_REJECTED"),
        (_summary(rebuffer=1), "INTEGRITY_REJECTED"),
    ],
)
def test_invalid_denominators_or_effects_fail_closed(
    summary: SegmentSummary,
    status: str,
) -> None:
    result = evaluate_report(
        _report(task_create=summary),
        minimum_successful_samples=5,
        minimum_p50_opportunity_ms=500,
    )

    assert result.status == status


def test_missing_task_profile_is_invalid() -> None:
    report = _report()
    incomplete = LatencyRunReport(
        report.schema_version,
        report.run,
        report.profiles[:-1],
    )

    result = evaluate_report(
        incomplete,
        minimum_successful_samples=5,
        minimum_p50_opportunity_ms=500,
    )

    assert result.status == "INVALID_INPUT"
    assert result.reason == "MISSING_TASK_CANCEL_PROFILE"


def test_output_is_private_exclusive_and_sanitized(tmp_path: Path) -> None:
    result = evaluate_report(
        _report(), minimum_successful_samples=5, minimum_p50_opportunity_ms=500
    )
    output = tmp_path / "materiality.json"

    write_result_exclusive(result, output)

    assert output.stat().st_mode & 0o777 == 0o600
    decoded = json.loads(output.read_text(encoding="utf-8"))
    assert decoded["schema_version"] == "live-voice.task-ack-materiality.v1"
    assert decoded["candidate_gain_status"] == "UNMEASURED"
    assert "transcript" not in output.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_result_exclusive(result, output)
