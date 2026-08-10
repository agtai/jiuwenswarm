from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import build_w2_fresh_attempt_scaffold as helper


_SHA = "a" * 40


def test_scaffold_keeps_random_fault_ids_out_of_unsigned_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    rehearsal = tmp_path / "rehearsal"
    rehearsal.mkdir()
    formal = tmp_path / "formal"
    formal.mkdir()
    keys = tmp_path / "keys"
    for scope in ("formal", "rehearsal"):
        root = keys / scope
        root.mkdir(parents=True)
        for role in helper._ROLES:
            (root / f"{role}.public").write_text("1" * 64, encoding="ascii")
    data = tmp_path / "data"
    session = data / "agent" / "sessions" / "sess_test"
    session.mkdir(parents=True)
    (session / "metadata.json").write_text("{}", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    tools = {}
    for name in ("python", "node", "chrome", "prepared.wav"):
        path = tmp_path / name
        path.write_bytes(b"test")
        tools[name] = path

    def run(argv: list[str], *, cwd: Path) -> str:
        del cwd
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return _SHA
        if argv[:2] == ["git", "status"]:
            return ""
        raise AssertionError(argv)

    monkeypatch.setattr(helper, "_run", run)
    args = argparse.Namespace(
        label="test",
        candidate_root=candidate,
        candidate_sha=_SHA,
        staging_root=staging,
        rehearsal_root=rehearsal,
        formal_evidence_root=formal,
        key_root=keys,
        external_root=tmp_path / "external-root",
        chrome_profile=tmp_path / "chrome-profile",
        data_dir=data,
        session_id="sess_test",
        project_id="project-1",
        project_dir=project,
        python=tools["python"],
        node=tools["node"],
        chrome=tools["chrome"],
        prepared_wav=tools["prepared.wav"],
    )

    result = helper.build(args)
    scaffold = json.loads(
        (staging / "attempt-scaffold.json").read_text(encoding="utf-8")
    )
    policy = json.loads(
        (staging / "rehearsal-trust-policy.unsigned.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["status"] == "FRESH_SCAFFOLD_READY"
    assert "fault_request_ids" not in scaffold
    assert scaffold["policy_id"] == policy["policy_id"]
    assert scaffold["candidate_sha"] == policy["candidate"]["candidate_sha"]
    assert scaffold["evidence_set_id"] == policy["evidence_set_id"]
