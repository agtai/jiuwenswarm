from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.live_voice.l0_browser_capture import (
    SESSION_VERSION,
    _browser_round_complete,
    _correlated_success_counts,
    _labels,
    _load_session,
    _scenario_matrix_complete,
    _select_cases,
)
from jiuwenswarm.server.live_voice.latency_measurement import (
    L0_RUN_LABELS_VERSION,
    load_l0_corpus_manifest,
)


CORPUS = Path("scripts/live_voice/l0_fixed_corpus.json")


def _session(tmp_path: Path, **updates: object) -> Path:
    path = tmp_path / "browser-session.json"
    value: dict[str, object] = {
        "schema_version": SESSION_VERSION,
        "source_head": "c31e85ade1a69e934d05bfb9c277568a1238663c",
        "runtime_profile": "formal-web-validation",
        "evidence_directory": str(tmp_path),
        "run_labels_file": str(tmp_path / "run-labels.json"),
        "browser_endpoint": "http://127.0.0.1:9223",
        "physical_evidence": "pending-user-run",
        "raw_audio_retained": False,
        "transcript_retained": False,
    }
    value.update(updates)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_capture_session_is_loopback_closed_and_cannot_escape_evidence_directory(
    tmp_path: Path,
) -> None:
    session = _load_session(_session(tmp_path))
    assert session["browser_endpoint"] == "http://127.0.0.1:9223"

    with pytest.raises(ValueError, match="loopback"):
        _load_session(
            _session(tmp_path, browser_endpoint="http://example.test:9223")
        )
    with pytest.raises(ValueError, match="escaped"):
        _load_session(
            _session(tmp_path, run_labels_file=str(tmp_path.parent / "labels.json"))
        )
    with pytest.raises(ValueError, match="closed shape"):
        _load_session(_session(tmp_path, credential="forbidden"))


def test_default_physical_cases_exclude_injected_and_degraded_profiles() -> None:
    manifest, _ = load_l0_corpus_manifest(CORPUS)
    selected = _select_cases(manifest, [])
    categories = {str(item["category"]) for item in selected}
    assert {"short_no_tool", "long_answer", "real_tool", "task_create"} <= categories
    assert "provider_slow" not in categories
    assert "provider_failure" not in categories
    assert "degraded_network" not in categories
    assert all(item["expected_classification"] == "success" for item in selected)

    with pytest.raises(ValueError, match="non-injected nominal success"):
        _select_cases(manifest, ["provider-failure-zh"])


def test_dynamic_labels_have_no_free_form_or_private_fields() -> None:
    labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature="warm",
    )
    assert labels == {
        "schema_version": L0_RUN_LABELS_VERSION,
        "profile_id": "physical-formal-web-warm",
        "scenario_id": "short-no-tool-zh",
        "sample_index": 3,
        "temperature": "warm",
        "evidence_source": "physical",
    }


def test_browser_round_requires_exact_labels_no_drops_and_one_success_terminal() -> None:
    labels = _labels(
        profile_id="physical-formal-web-warm",
        scenario_id="short-no-tool-zh",
        sample_index=3,
        temperature="warm",
    )
    browser_labels = dict(labels)
    browser_labels.pop("schema_version")
    records = [
        {
            **browser_labels,
            "milestone": "browser_eot_receipt",
            "classification": "unknown",
        },
        {
            **browser_labels,
            "milestone": "playout_completed",
            "classification": "success",
        },
    ]
    snapshot = {
        "enabled": True,
        "configured": True,
        "accepted_records": 2,
        "dropped_records": 0,
        "records": records,
    }
    assert _browser_round_complete(snapshot, browser_labels)

    dropped = {**snapshot, "dropped_records": 1}
    assert not _browser_round_complete(dropped, browser_labels)
    partial = {**snapshot, "accepted_records": 1, "records": records[:1]}
    assert not _browser_round_complete(partial, browser_labels)
    wrong = {
        **snapshot,
        "records": [{**records[0], "sample_index": 4}, records[1]],
    }
    assert not _browser_round_complete(wrong, browser_labels)
    fallback = {
        **snapshot,
        "accepted_records": 3,
        "records": [
            *records,
            {
                **browser_labels,
                "milestone": "fallback",
                "classification": "fallback",
            },
        ],
    }
    assert not _browser_round_complete(fallback, browser_labels)


def test_correlated_success_count_intersects_operator_browser_and_aggregate() -> None:
    report = {
        "rounds": [
            {
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "short-no-tool-zh",
                "sample_index": 1,
                "success_eligible": True,
            },
            {
                "profile_id": "physical-formal-web-warm",
                "scenario_id": "long-answer-zh",
                "sample_index": 2,
                "success_eligible": True,
            },
        ]
    }
    accepted = {
        ("physical-formal-web-warm", "short-no-tool-zh", 1),
        ("physical-formal-web-warm", "task-status-zh", 3),
    }
    assert _correlated_success_counts(
        report,
        accepted,
        {"short-no-tool-zh", "task-status-zh"},
    ) == {"short-no-tool-zh": 1, "task-status-zh": 0}


def test_physical_profile_requires_target_total_and_every_selected_scenario() -> None:
    assert not _scenario_matrix_complete(
        {"short-no-tool-zh": 20, "task-status-zh": 0},
        20,
    )
    assert _scenario_matrix_complete(
        {"short-no-tool-zh": 19, "task-status-zh": 1},
        20,
    )
