from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "live_voice" / "c019_gap_report.py"


def _record(
    milestone: str,
    *,
    monotonic_ms: float,
    unit_seq: int | None,
    response_id: str = "response-1",
    response_generation: int = 1,
    unit_id: str | None = None,
    session_id: str = "session-1",
    interaction_id: str = "interaction-1",
    activation_id: str = "activation-1",
    activation_generation: int = 1,
) -> dict[str, object]:
    return {
        "schema_version": "live-voice.l0-measurement-envelope.v1",
        "milestone": milestone,
        "binding": {
            "correlation_id": "correlation-1",
            "session_id": session_id,
            "interaction_id": interaction_id,
            "activation_id": activation_id,
            "activation_generation": activation_generation,
            "response_id": response_id,
            "response_generation": response_generation,
            "unit_id": unit_id
            if unit_id is not None
            else (None if unit_seq is None else f"unit-{unit_seq}"),
            "unit_seq": unit_seq,
            "turn_id": None,
            "round_id": None,
            "task_id": None,
            "attempt_id": None,
        },
        "observation": {
            "monotonic_ms": monotonic_ms,
            "reason_code": None,
        },
        "profile_id": "c019-physical",
        "scenario_id": "c019_long",
        "sample_index": 0,
        "temperature": "warm",
        "classification": "unknown",
        "evidence_source": "physical",
    }


def _snapshot(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "enabled": True,
        "configured": True,
        "accepted_records": len(records),
        "dropped_records": 0,
        "records": records,
    }


def _run(
    tmp_path: Path, payload: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--json", str(snapshot)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_c019_gap_report_separates_prefetch_tts_playout_and_inter_unit_gap(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=100.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=200.0, unit_seq=0),
        _record("unit_tts_requested", monotonic_ms=400.0, unit_seq=1),
        _record("successor_tts_requested", monotonic_ms=400.0, unit_seq=1),
        _record("successor_downlink_attached", monotonic_ms=600.0, unit_seq=1),
        _record("successor_first_frame_buffered", monotonic_ms=700.0, unit_seq=1),
        _record("unit_playout_completed", monotonic_ms=1_000.0, unit_seq=0),
        _record("successor_promoted_to_playout", monotonic_ms=1_010.0, unit_seq=1),
        _record("unit_playout_started", monotonic_ms=1_050.0, unit_seq=1),
        _record("unit_tts_requested", monotonic_ms=1_200.0, unit_seq=2),
        _record("successor_tts_requested", monotonic_ms=1_200.0, unit_seq=2),
        _record("successor_downlink_attached", monotonic_ms=1_300.0, unit_seq=2),
        _record("successor_first_frame_buffered", monotonic_ms=1_400.0, unit_seq=2),
        _record("unit_playout_completed", monotonic_ms=1_600.0, unit_seq=1),
        _record("successor_promoted_to_playout", monotonic_ms=1_610.0, unit_seq=2),
        _record("unit_playout_started", monotonic_ms=1_650.0, unit_seq=2),
        _record("unit_playout_completed", monotonic_ms=2_000.0, unit_seq=2),
    ]

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["schema_version"] == "live-voice.c019-gap-report.v1"
    assert report["eligible"] is True
    assert report["response"] == {
        "response_id": "response-1",
        "response_generation": 1,
    }
    assert report["units"] == [
        {
            "unit_seq": 0,
            "tts_requested_ms": 100.0,
            "playout_started_ms": 200.0,
            "playout_completed_ms": 1_000.0,
            "tts_to_start_ms": 100.0,
            "playout_duration_ms": 800.0,
            "previous_to_start_gap_ms": None,
            "preparation_overlap_ms": None,
            "successor_tts_requested_ms": None,
            "successor_downlink_attached_ms": None,
            "successor_first_frame_buffered_ms": None,
            "successor_promoted_to_playout_ms": None,
            "tts_to_first_buffer_ms": None,
            "predecessor_overlap_ms": None,
            "local_handoff_ms": None,
            "promotion_to_webaudio_ms": None,
        },
        {
            "unit_seq": 1,
            "tts_requested_ms": 400.0,
            "playout_started_ms": 1_050.0,
            "playout_completed_ms": 1_600.0,
            "tts_to_start_ms": 650.0,
            "playout_duration_ms": 550.0,
            "previous_to_start_gap_ms": 50.0,
            "preparation_overlap_ms": 600.0,
            "successor_tts_requested_ms": 400.0,
            "successor_downlink_attached_ms": 600.0,
            "successor_first_frame_buffered_ms": 700.0,
            "successor_promoted_to_playout_ms": 1_010.0,
            "tts_to_first_buffer_ms": 300.0,
            "predecessor_overlap_ms": 300.0,
            "local_handoff_ms": 10.0,
            "promotion_to_webaudio_ms": 40.0,
        },
        {
            "unit_seq": 2,
            "tts_requested_ms": 1_200.0,
            "playout_started_ms": 1_650.0,
            "playout_completed_ms": 2_000.0,
            "tts_to_start_ms": 450.0,
            "playout_duration_ms": 350.0,
            "previous_to_start_gap_ms": 50.0,
            "preparation_overlap_ms": 400.0,
            "successor_tts_requested_ms": 1_200.0,
            "successor_downlink_attached_ms": 1_300.0,
            "successor_first_frame_buffered_ms": 1_400.0,
            "successor_promoted_to_playout_ms": 1_610.0,
            "tts_to_first_buffer_ms": 200.0,
            "predecessor_overlap_ms": 200.0,
            "local_handoff_ms": 10.0,
            "promotion_to_webaudio_ms": 40.0,
        },
    ]


def test_c019_gap_report_accepts_exact_parked_transition_family(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=0.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=10.0, unit_seq=0),
        _record("successor_tts_requested", monotonic_ms=20.0, unit_seq=1),
        _record("unit_tts_requested", monotonic_ms=20.0, unit_seq=1),
        _record("successor_downlink_attached", monotonic_ms=30.0, unit_seq=1),
        _record("successor_first_frame_buffered", monotonic_ms=40.0, unit_seq=1),
        _record("successor_park_requested", monotonic_ms=50.0, unit_seq=1),
        _record("successor_parked", monotonic_ms=60.0, unit_seq=1),
        _record("unit_playout_completed", monotonic_ms=100.0, unit_seq=0),
        _record("successor_promotion_requested", monotonic_ms=101.0, unit_seq=1),
        _record("successor_promoted", monotonic_ms=102.0, unit_seq=1),
        _record("successor_promoted_to_playout", monotonic_ms=103.0, unit_seq=1),
        _record("unit_playout_started", monotonic_ms=104.0, unit_seq=1),
        _record("unit_playout_completed", monotonic_ms=150.0, unit_seq=1),
    ]
    for record in records:
        record["profile_id"] = "c019-physical-prefetch-v1"

    completed = _run(tmp_path, _snapshot(records))
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["eligible"] is True
    assert report["units"][1]["successor_parked_ms"] == 60.0
    assert report["units"][1]["successor_promoted_ms"] == 102.0


def test_c019_gap_report_rejects_selected_profile_without_transition_family(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=0.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=10.0, unit_seq=0),
        _record("unit_playout_completed", monotonic_ms=100.0, unit_seq=0),
        _record("unit_tts_requested", monotonic_ms=20.0, unit_seq=1),
        _record("successor_tts_requested", monotonic_ms=20.0, unit_seq=1),
        _record("successor_downlink_attached", monotonic_ms=30.0, unit_seq=1),
        _record("successor_first_frame_buffered", monotonic_ms=40.0, unit_seq=1),
        _record("successor_promoted_to_playout", monotonic_ms=101.0, unit_seq=1),
        _record("unit_playout_started", monotonic_ms=102.0, unit_seq=1),
        _record("unit_playout_completed", monotonic_ms=150.0, unit_seq=1),
    ]
    for record in records:
        record["profile_id"] = "c019-physical-prefetch-v1"

    completed = _run(tmp_path, _snapshot(records))
    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert "successor_transition_family_incomplete" in report["reasons"]


def test_c019_gap_report_rejects_incomplete_or_failed_physical_evidence(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=100.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=200.0, unit_seq=0),
        _record("unit_playout_completed", monotonic_ms=1_000.0, unit_seq=0),
        _record("unit_tts_requested", monotonic_ms=1_100.0, unit_seq=1),
        _record("browser_failure", monotonic_ms=1_120.0, unit_seq=None),
    ]

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["eligible"] is False
    assert report["reasons"] == [
        "browser_failure_present",
        "unit_milestones_incomplete",
    ]
    assert report["units"][1]["previous_to_start_gap_ms"] is None


def test_c019_gap_report_rejects_duplicate_milestones_and_mixed_responses(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=100.0, unit_seq=0),
        _record("unit_tts_requested", monotonic_ms=101.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=200.0, unit_seq=0),
        _record("unit_playout_completed", monotonic_ms=1_000.0, unit_seq=0),
        _record(
            "unit_tts_requested",
            monotonic_ms=1_100.0,
            unit_seq=0,
            response_id="response-2",
        ),
    ]

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["eligible"] is False
    assert report["reasons"] == [
        "duplicate_unit_milestone",
        "mixed_response_population",
        "mixed_identity_population",
    ]


def test_c019_gap_report_rejects_successor_promotion_before_predecessor_completion(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=10.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=20.0, unit_seq=0),
        _record("unit_playout_completed", monotonic_ms=100.0, unit_seq=0),
        _record("unit_tts_requested", monotonic_ms=30.0, unit_seq=1),
        _record("successor_tts_requested", monotonic_ms=30.0, unit_seq=1),
        _record("successor_downlink_attached", monotonic_ms=40.0, unit_seq=1),
        _record("successor_first_frame_buffered", monotonic_ms=50.0, unit_seq=1),
        _record("successor_promoted_to_playout", monotonic_ms=80.0, unit_seq=1),
        _record("unit_playout_started", monotonic_ms=90.0, unit_seq=1),
        _record("unit_playout_completed", monotonic_ms=120.0, unit_seq=1),
    ]

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["eligible"] is False
    assert "successor_predecessor_order_invalid" in report["reasons"]


def test_c019_gap_report_rejects_mixed_scope_and_unit_identity(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=10.0, unit_seq=0),
        _record(
            "unit_playout_started",
            monotonic_ms=20.0,
            unit_seq=0,
            session_id="foreign-session",
            interaction_id="foreign-interaction",
            unit_id="foreign-unit",
        ),
        _record("unit_playout_completed", monotonic_ms=100.0, unit_seq=0),
    ]

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["eligible"] is False
    assert "mixed_identity_population" in report["reasons"]
    assert "mixed_unit_identity" in report["reasons"]


def test_c019_gap_report_rejects_mixed_activation_identity(tmp_path: Path) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=10.0, unit_seq=0),
        _record(
            "unit_playout_started",
            monotonic_ms=20.0,
            unit_seq=0,
            activation_id="foreign-activation",
        ),
        _record("unit_playout_completed", monotonic_ms=100.0, unit_seq=0),
    ]

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["eligible"] is False
    assert "mixed_identity_population" in report["reasons"]


def test_c019_gap_report_keeps_legacy_v1_identity_gaps_diagnostic(
    tmp_path: Path,
) -> None:
    records = [
        _record("unit_tts_requested", monotonic_ms=10.0, unit_seq=0),
        _record("unit_playout_started", monotonic_ms=20.0, unit_seq=0),
        _record("unit_playout_completed", monotonic_ms=100.0, unit_seq=0),
    ]
    for record in records:
        record["binding"].pop("activation_id")
        record["binding"].pop("unit_id")

    completed = _run(tmp_path, _snapshot(records))

    assert completed.returncode == 2
    report = json.loads(completed.stdout)
    assert report["eligible"] is False
    assert "activation_identity_incomplete" in report["reasons"]
    assert "unit_identity_incomplete" in report["reasons"]
    assert report["units"][0]["playout_duration_ms"] == 80.0
