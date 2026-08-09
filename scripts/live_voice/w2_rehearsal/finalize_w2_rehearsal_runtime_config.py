from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root is not an object: {path}")
    return value


def _run(argv: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{64}", args.expected_root_sha256) is None:
        raise RuntimeError("expected root SHA-256 is not canonical lowercase hex")
    scaffold_path = args.scaffold.resolve(strict=True)
    scaffold = _read(scaffold_path)
    if scaffold.get("schema") != "machine-private.w2-attempt-scaffold.v1":
        raise RuntimeError("attempt scaffold schema is unsupported")
    candidate = Path(scaffold["candidate_root"]).resolve(strict=True)
    staging = Path(scaffold["staging_root"]).resolve(strict=True)
    policy = staging / "rehearsal-trust-policy.unsigned.json"
    signature = staging / "rehearsal-trust-policy.signature"
    root_public = Path(scaffold["external_root"]) / "root.public"
    for path in (policy, signature, root_public):
        if not path.is_file():
            raise RuntimeError(f"signed rehearsal input is missing: {path}")
    root_hex = root_public.read_text(encoding="ascii", errors="strict").strip()
    if re.fullmatch(r"[0-9a-f]{64}", root_hex) is None:
        raise RuntimeError("external root public key is not canonical")
    actual_root_sha256 = hashlib.sha256(bytes.fromhex(root_hex)).hexdigest()
    if actual_root_sha256 != args.expected_root_sha256:
        raise RuntimeError("expected root SHA-256 does not match the public key")
    if (
        _run(["git", "rev-parse", "HEAD"], cwd=candidate, env=os.environ.copy())
        != scaffold["candidate_sha"]
    ):
        raise RuntimeError("candidate SHA changed")
    if _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=candidate,
        env=os.environ.copy(),
    ):
        raise RuntimeError("candidate checkout is dirty")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(candidate)
    validated = json.loads(
        _run(
            [
                scaffold["python"],
                "-m",
                "jiuwenswarm.server.live_voice.w2_gate_cli",
                "validate-policy",
                "--trust-policy",
                str(policy),
                "--trust-policy-signature",
                str(signature),
                "--root-public-key",
                str(root_public),
                "--expected-root-sha256",
                args.expected_root_sha256,
            ],
            cwd=candidate,
            env=env,
        )
    )
    if validated.get("status") != "VALID":
        raise RuntimeError("signed rehearsal policy did not validate")

    config = {
        "schema": "machine-private.w2-rehearsal-runtime-config.v2",
        "candidate_root": scaffold["candidate_root"],
        "candidate_sha": scaffold["candidate_sha"],
        "python": scaffold["python"],
        "node": scaffold["node"],
        "frontend_root": scaffold["frontend_root"],
        "prepared_wav": scaffold["prepared_wav"],
        "chrome": scaffold["chrome"],
        "chrome_profile": scaffold["chrome_profile"],
        "data_dir": scaffold["data_dir"],
        "evidence_root": scaffold["rehearsal_root"],
        "staging_root": scaffold["staging_root"],
        "trust_policy": str(policy),
        "trust_policy_signature": str(signature),
        "root_public_key": str(root_public),
        "expected_root_sha256": args.expected_root_sha256,
        "leaf_key_root": str(Path(scaffold["key_root"]) / "rehearsal"),
        "environment_id": scaffold["environment_id"],
        "evidence_set_id": scaffold["evidence_set_id"],
        "session_id": scaffold["session_id"],
        "mode_id": "integrated-formal",
        "project_id": scaffold["project_id"],
        "project_dir": scaffold["project_dir"],
        "principal_id": "w2-rehearsal-principal",
        "ports": scaffold["ports"],
        "speech": scaffold["speech"],
        "p3_databases": scaffold["p3_databases"],
        "fault_request_ids": scaffold["fault_request_ids"],
        "runtime_slots": [
            {
                "artifact_id": slot["artifact_id"],
                "sequence": slot["artifact_sequence"],
                "producer": slot["producer_id"],
                "epoch": slot["process_epoch"],
                "predecessor": slot["predecessor_artifact_id"],
                "showcase_run": slot["showcase_run"],
            }
            for slot in scaffold["runtime_slots"]
        ],
    }
    output = args.output.resolve(strict=False)
    if not output.is_absolute() or output.parent != staging or output.exists():
        raise RuntimeError(
            "runtime config output must be a fresh file in the staging root"
        )
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(_canonical(config))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            output.unlink(missing_ok=True)
        finally:
            raise
    return {
        "status": "REHEARSAL_RUNTIME_CONFIG_READY",
        "output": str(output),
        "candidate_sha": scaffold["candidate_sha"],
        "expected_root_sha256": args.expected_root_sha256,
        "runtime_slots": len(config["runtime_slots"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scaffold", required=True, type=Path)
    parser.add_argument("--expected-root-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(finalize(args), separators=(",", ":"), sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - machine-private stable boundary
        print(f"finalize-w2-rehearsal-runtime-config: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
