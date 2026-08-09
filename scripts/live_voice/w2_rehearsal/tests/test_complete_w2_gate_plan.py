from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_w2_fresh_attempt_scaffold as scaffold
import complete_w2_gate_plan as helper


def _source_plan(tmp_path: Path) -> Path:
    roles = {
        "runtime-gateway": "real_runtime",
        "runtime-agentserver": "real_runtime",
        "automated": "automated_conformance",
        "independent-review": "independent_review",
        "fault-injection": "fault_injection",
        "human-observation": "human_observation",
    }
    path = tmp_path / "candidate-plan.incomplete.json"
    path.write_text(
        json.dumps(
            {
                "schema": "machine-private.w2-next-attempt-plan.v1",
                "policy_id": "policy-1",
                "repository_path": str(tmp_path),
                "candidate": {
                    "candidate_sha": "a" * 40,
                    "environment_id": "environment-1",
                    "session_id": "session-1",
                    "mode_id": "integrated-formal",
                },
                "evidence_set_id": "evidence-set-1",
                "runtime_slots": scaffold._runtime_slots(
                    rehearsal=False, suffix="candidate1"
                ),
                "non_runtime_artifact_slots": [],
                "signers": [
                    {"signer_id": signer_id, "role": role}
                    for signer_id, role in roles.items()
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_completes_exact_static_artifact_plan(tmp_path: Path) -> None:
    output = tmp_path / "complete.json"
    result = helper.complete_plan(_source_plan(tmp_path), output)
    assert result == {
        "status": "STATIC_PLAN_COMPLETE",
        "runtime_slots": 7,
        "non_runtime_slots": 31,
        "first_non_runtime_sequence": 8,
        "last_sequence": 38,
        "output": str(output.resolve()),
    }
    plan = json.loads(output.read_text(encoding="ascii"))
    slots = plan["non_runtime_artifact_slots"]
    assert [item["artifact_sequence"] for item in slots] == list(range(8, 39))
    assert len({item["artifact_id"] for item in slots}) == 31
    assert sum(item["evidence_kind"] == "human_observation" for item in slots) == 12
    assert sum(item["evidence_kind"] == "fault_injection" for item in slots) == 14
    assert sum(item["evidence_kind"] == "automated_conformance" for item in slots) == 4
    automated = slots[0]
    assert len(automated["expected_subjects"]) == 24
    assert "ledger:cross.feature_off_text_regression" in automated["expected_subjects"]
    assert [item["expected_subjects"] for item in slots[1:4]] == [
        ["automated:observability-retriable"],
        ["automated:observability-non-retriable"],
        ["automated:observability-zero-effect"],
    ]
    assert slots[-1]["expected_subjects"] == ["ledger:cross.failure_degradation"]


def test_never_overwrites_or_recompletes(tmp_path: Path) -> None:
    output = tmp_path / "complete.json"
    output.write_text("keep", encoding="ascii")
    with pytest.raises(FileExistsError):
        helper.complete_plan(_source_plan(tmp_path), output)
    assert output.read_text(encoding="ascii") == "keep"

    plan = json.loads(_source_plan(tmp_path).read_text(encoding="utf-8"))
    plan["non_runtime_artifact_slots"] = [{"unexpected": True}]
    source = tmp_path / "already-complete.json"
    source.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(helper.PlanError, match="empty non-runtime"):
        helper.complete_plan(source, tmp_path / "unused.json")


def test_rejects_restart_successor_claimed_as_showcase(tmp_path: Path) -> None:
    plan = json.loads(_source_plan(tmp_path).read_text(encoding="utf-8"))
    plan["runtime_slots"][-1]["showcase_run"] = 3
    source = tmp_path / "bad-runtime.json"
    source.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(helper.PlanError, match="unscored fourth AgentServer"):
        helper.complete_plan(source, tmp_path / "unused.json")
