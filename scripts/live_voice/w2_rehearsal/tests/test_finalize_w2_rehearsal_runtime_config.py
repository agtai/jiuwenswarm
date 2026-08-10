from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

import finalize_w2_rehearsal_runtime_config as helper
from w2_product_fault_binding import validate_product_fault_plan_payload


_SHA = "a" * 40


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    validated_override: dict[str, object] | None = None,
) -> tuple[argparse.Namespace, Path]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    key_root = tmp_path / "keys"
    key_root.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rehearsal = tmp_path / "rehearsal"
    rehearsal.mkdir()
    policy = staging / "rehearsal-trust-policy.unsigned.json"
    policy.write_text("{}", encoding="utf-8")
    (staging / "rehearsal-trust-policy.signature").write_text(
        "0" * 128, encoding="ascii"
    )
    root_hex = "1" * 64
    (external / "root.public").write_text(root_hex, encoding="ascii")
    expected_root = hashlib.sha256(bytes.fromhex(root_hex)).hexdigest()
    scaffold = {
        "schema": "machine-private.w2-attempt-scaffold.v1",
        "candidate_root": str(candidate),
        "candidate_sha": _SHA,
        "staging_root": str(staging),
        "external_root": str(external),
        "key_root": str(key_root),
        "python": "python",
        "node": "node",
        "frontend_root": str(candidate / "frontend"),
        "prepared_wav": str(candidate / "prepared.wav"),
        "chrome": "chrome",
        "chrome_profile": str(tmp_path / "chrome-profile"),
        "data_dir": str(data_dir),
        "rehearsal_root": str(rehearsal),
        "environment_id": "environment-1",
        "policy_id": "policy-1",
        "evidence_set_id": "evidence-1",
        "session_id": "session-1",
        "project_id": "project-1",
        "project_dir": str(tmp_path / "project"),
        "ports": {"agentserver": 1, "web": 2, "gateway": 3},
        "speech": {"provider": "test"},
        "p3_databases": {"1": "one", "2": "two", "3": "three"},
        "runtime_slots": [],
    }
    scaffold_path = staging / "attempt-scaffold.json"
    scaffold_path.write_text(json.dumps(scaffold), encoding="utf-8")
    validated = {
        "status": "VALID",
        "policy_id": "policy-1",
        "repository_path": str(candidate.resolve()),
        "candidate_binding": [
            _SHA,
            "environment-1",
            "session-1",
            "integrated-formal",
        ],
        "evidence_set_id": "evidence-1",
        **(validated_override or {}),
    }

    def run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> str:
        del cwd, env
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return _SHA
        if argv[:2] == ["git", "status"]:
            return ""
        if "validate-policy" in argv:
            return json.dumps(validated)
        raise AssertionError(argv)

    monkeypatch.setattr(helper, "_run", run)
    output = staging / "runtime-config.json"
    return (
        argparse.Namespace(
            scaffold=scaffold_path,
            expected_root_sha256=expected_root,
            output=output,
        ),
        output,
    )


def test_finalize_derives_full_plan_only_after_signed_policy_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, output = _fixture(tmp_path, monkeypatch)

    result = helper.finalize(args)
    config = json.loads(output.read_text(encoding="utf-8"))

    assert result["status"] == "REHEARSAL_RUNTIME_CONFIG_READY"
    assert config["schema"] == "machine-private.w2-rehearsal-runtime-config.v3"
    assert config["policy_id"] == "policy-1"
    assert "fault_request_ids" not in config
    validate_product_fault_plan_payload(
        config["product_fault_plan"],
        policy_id="policy-1",
        candidate_sha=_SHA,
        evidence_set_id="evidence-1",
    )


@pytest.mark.parametrize(
    "changed",
    (
        {"policy_id": "foreign-policy"},
        {"candidate_binding": ["b" * 40, "environment-1", "session-1", "integrated-formal"]},
        {"evidence_set_id": "foreign-evidence"},
        {"repository_path": "foreign-repository"},
    ),
)
def test_finalize_rejects_foreign_validated_policy_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: dict[str, object],
) -> None:
    args, output = _fixture(
        tmp_path, monkeypatch, validated_override=changed
    )

    with pytest.raises(RuntimeError, match="differs from attempt scaffold"):
        helper.finalize(args)
    assert not output.exists()
