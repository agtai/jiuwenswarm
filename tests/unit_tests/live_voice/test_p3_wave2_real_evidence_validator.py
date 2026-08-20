# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jiuwenswarm.server.live_voice.project_code_executor import (
    DirectStreamObservation,
)
from scripts.live_voice.p3_wave2_real_evidence_producer import (
    ObservationCollector,
    ScenarioSummary,
    build_evidence_document,
)
from scripts.live_voice.p3_wave2_real_evidence_validator import (
    EvidenceValidationError,
    SCHEMA_PATH,
    observation_counts,
    validate_evidence_bytes,
)


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64


def _valid_document(tmp_path: Path) -> dict[str, object]:
    output = tmp_path / "private.json"
    collector = ObservationCollector(capacity=8)
    for task_label, stream_kind in (
        ("A1", "initial"),
        ("A2", "initial"),
        ("A2", "adjustment"),
        ("B1", "initial"),
    ):
        common = {
            "task_ref": f"task-{task_label}",
            "attempt_ref": f"attempt-{task_label}",
            "run_ref": f"run-{task_label}-{stream_kind}",
            "stream_kind": stream_kind,
            "file_tool_kind": "write",
            "tool_name_digest": SHA_A,
            "call_id_digest": SHA_B,
            "observed_at": "2026-08-20T10:00:00Z",
        }
        collector(
            DirectStreamObservation(
                sequence=1,
                event_kind="tool_call",
                result_status="not_applicable",
                **common,
            )
        )
        collector(
            DirectStreamObservation(
                sequence=2,
                event_kind="tool_result",
                result_status="success",
                **common,
            )
        )
    summary = ScenarioSummary(
        run_id="wave2-run-1",
        source_sha256=SHA_C,
        private_output_basename=output.name,
        data_dir_basename="private-data",
        database_basename="wave2.sqlite3",
        project_basenames=("project-a", "project-b"),
        task_refs=("task-A1", "task-A2", "task-B1"),
        attempt_refs=("attempt-A1", "attempt-A2", "attempt-B1"),
        profile_sha256=SHA_A,
        requirements_sha256=SHA_B,
        production_factory_used=True,
        production_registration_used=True,
        profile_persisted=True,
        requirements_persisted=True,
        two_projects_concurrent=True,
        a2_busy_queued=True,
        a2_zero_pre_release_effect=True,
        same_attempt_dequeued=True,
        adjustment_applied=True,
        cancel_a1_exact=True,
        cancel_b1_exact=True,
        reopen_matched=True,
        cleanup_complete=True,
        source_untouched=True,
        real_agent_observed=True,
        real_tool_observed=True,
    )
    return build_evidence_document(summary, collector)


def _assert_every_object_is_closed(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False
        for value in schema.values():
            _assert_every_object_is_closed(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_every_object_is_closed(value)


def test_schema_closes_every_object_and_validator_accepts_exact_document(
    tmp_path: Path,
) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    _assert_every_object_is_closed(schema)
    document = _valid_document(tmp_path)

    aggregate = validate_evidence_bytes(
        json.dumps(document, separators=(",", ":")).encode("utf-8")
    )

    assert aggregate["ok"] is True
    assert set(aggregate) == {
        "ok",
        "observation_count",
        "paired_file_tool_count",
        "write_edit_pair_count",
    }


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda value: value.update({"PRIVATE_SENTINEL": "secret"}), "EVIDENCE_SCHEMA_INVALID"),
        (
            lambda value: value["counts"].update({"observer_failures": 1}),
            "EVIDENCE_OBSERVER_FAILURE",
        ),
        (
            lambda value: value["checks"].update({"real_tool_observed": False}),
            "EVIDENCE_REAL_BOUNDARY_UNPROVEN",
        ),
        (
            lambda value: value["observations"][1].update({"sequence": 3}),
            "EVIDENCE_SEQUENCE_GAP",
        ),
        (
            lambda value: value["observations"][1].update(
                {"call_id_digest": SHA_C}
            ),
            "EVIDENCE_TOOL_PAIRING_INVALID",
        ),
    ],
)
def test_validator_returns_only_closed_reasons(
    tmp_path: Path,
    mutate,
    reason: str,
) -> None:
    document = _valid_document(tmp_path)
    mutate(document)

    with pytest.raises(EvidenceValidationError) as raised:
        validate_evidence_bytes(
            json.dumps(document, separators=(",", ":")).encode("utf-8")
        )

    assert raised.value.reason == reason
    assert raised.value.args == (reason,)
    assert "PRIVATE_SENTINEL" not in str(raised.value)


def test_validator_rejects_oversize_before_json_and_cli_prints_one_safe_line(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvidenceValidationError) as oversized:
        validate_evidence_bytes(b"PRIVATE_SENTINEL" * 5000)
    assert oversized.value.reason == "EVIDENCE_TOO_LARGE"

    private_dir = tmp_path / "PRIVATE_PATH_SENTINEL"
    private_dir.mkdir()
    source = private_dir / "private-input.json"
    source.write_text('{"PRIVATE_CONTENT_SENTINEL":', encoding="utf-8")
    script = Path("scripts/live_voice/p3_wave2_real_evidence_validator.py").resolve()
    completed = subprocess.run(
        [sys.executable, str(script), "--input", str(source)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).parents[3],
    )

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert completed.stdout.count("\n") == 1
    payload = json.loads(completed.stdout)
    assert payload == {"ok": False, "reason": "EVIDENCE_JSON_INVALID"}
    rendered = completed.stdout + completed.stderr
    assert "PRIVATE_PATH_SENTINEL" not in rendered
    assert "PRIVATE_CONTENT_SENTINEL" not in rendered


def test_validator_rejects_observation_outside_exact_a1_a2_b1_bindings(
    tmp_path: Path,
) -> None:
    document = _valid_document(tmp_path)
    document["observations"][0]["task_ref"] = "task-outside-scenario"

    with pytest.raises(EvidenceValidationError) as raised:
        validate_evidence_bytes(
            json.dumps(document, separators=(",", ":")).encode("utf-8")
        )

    assert raised.value.reason == "EVIDENCE_SCENARIO_BINDING_MISMATCH"


def test_validator_requires_real_initial_pairs_and_a2_adjustment_pair(
    tmp_path: Path,
) -> None:
    document = _valid_document(tmp_path)
    document["observations"] = [
        item
        for item in document["observations"]
        if not (
            item["task_ref"] == "task-A2"
            and item["stream_kind"] == "adjustment"
        )
    ]
    document["counts"] = observation_counts(document["observations"])
    document["counts"].update(
        {"observer_failures": 0, "dropped_observations": 0}
    )

    with pytest.raises(EvidenceValidationError) as raised:
        validate_evidence_bytes(
            json.dumps(document, separators=(",", ":")).encode("utf-8")
        )

    assert raised.value.reason == "EVIDENCE_SCENARIO_OBSERVATION_INCOMPLETE"
