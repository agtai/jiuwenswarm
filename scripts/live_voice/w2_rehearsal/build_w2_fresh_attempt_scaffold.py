from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any


_ROLES = (
    "runtime-gateway",
    "runtime-agentserver",
    "automated",
    "independent-review",
    "fault-injection",
    "human-observation",
)


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


def _exclusive_write(path: Path, content: bytes) -> None:
    if not path.is_absolute() or not path.parent.is_dir():
        raise RuntimeError(
            f"output parent is not an existing absolute directory: {path}"
        )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def _run(argv: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _public_key(path: Path) -> str:
    value = path.read_text(encoding="ascii", errors="strict").strip()
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RuntimeError(f"public key is not canonical lowercase hex: {path}")
    return value


def _signers(key_root: Path, *, rehearsal: bool, suffix: str) -> list[dict[str, Any]]:
    scope = "rehearsal" if rehearsal else "formal"
    prefix = "rehearsal-" if rehearsal else ""
    roles = {
        "runtime-gateway": ("real_runtime", "gateway"),
        "runtime-agentserver": ("real_runtime", "agentserver"),
        "automated": ("automated_conformance", None),
        "independent-review": ("independent_review", None),
        "fault-injection": ("fault_injection", None),
        "human-observation": ("human_observation", None),
    }
    result: list[dict[str, Any]] = []
    for role in _ROLES:
        evidence_role, producer = roles[role]
        result.append(
            {
                "signer_id": prefix + role,
                "principal_id": f"{prefix}w2-{role}-{suffix}",
                "public_key_hex": _public_key(key_root / scope / f"{role}.public"),
                "role": evidence_role,
                "producer_id": producer,
            }
        )
    return result


def _runtime_slots(*, rehearsal: bool, suffix: str) -> list[dict[str, Any]]:
    prefix = f"w2-rehearsal-{suffix}" if rehearsal else f"w2-{suffix}"
    signer_prefix = "rehearsal-" if rehearsal else ""
    slots: list[dict[str, Any]] = []
    previous: dict[str, str | None] = {"gateway": None, "agentserver": None}
    sequence = 1
    for run in (1, 2, 3):
        for producer in ("gateway", "agentserver"):
            artifact_id = f"{prefix}-{producer}-showcase-{run}"
            slots.append(
                {
                    "logical_slot": f"showcase-{run}-{producer}",
                    "artifact_id": artifact_id,
                    "artifact_sequence": sequence,
                    "producer_id": producer,
                    "process_epoch": f"{prefix}-{producer}-epoch-{run}",
                    "predecessor_artifact_id": previous[producer],
                    "showcase_run": run,
                    "signer_id": signer_prefix + f"runtime-{producer}",
                }
            )
            previous[producer] = artifact_id
            sequence += 1
    slots.append(
        {
            "logical_slot": "restart-successor-agentserver",
            "artifact_id": f"{prefix}-agentserver-restart-successor",
            "artifact_sequence": 7,
            "producer_id": "agentserver",
            "process_epoch": f"{prefix}-agentserver-epoch-4",
            "predecessor_artifact_id": previous["agentserver"],
            "showcase_run": None,
            "signer_id": signer_prefix + "runtime-agentserver",
        }
    )
    return slots


def _policy_runtime_slot(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        name: slot[name]
        for name in (
            "artifact_id",
            "artifact_sequence",
            "producer_id",
            "process_epoch",
            "predecessor_artifact_id",
            "showcase_run",
        )
    }


def _ps_literal(value: Path | str) -> str:
    text = str(value)
    if "'" in text or "\r" in text or "\n" in text:
        raise RuntimeError("PowerShell literal contains a forbidden character")
    return "'" + text + "'"


def build(args: argparse.Namespace) -> dict[str, Any]:
    candidate = args.candidate_root.resolve(strict=True)
    staging = args.staging_root.resolve(strict=True)
    rehearsal_root = args.rehearsal_root.resolve(strict=True)
    formal_root = args.formal_evidence_root.resolve(strict=True)
    key_root = args.key_root.resolve(strict=True)
    chrome_profile = args.chrome_profile.resolve(strict=False)
    external_root = args.external_root.resolve(strict=False)
    node = args.node.resolve(strict=True)
    chrome = args.chrome.resolve(strict=True)
    for root in (staging, rehearsal_root, formal_root, key_root):
        if not root.is_dir():
            raise RuntimeError(f"required fresh root is missing: {root}")
    for fresh_root in (chrome_profile, external_root):
        if not fresh_root.is_absolute() or not fresh_root.parent.is_dir():
            raise RuntimeError(
                f"fresh output parent is not an existing absolute directory: {fresh_root}"
            )
        if fresh_root.exists():
            raise RuntimeError(f"fresh output path already exists: {fresh_root}")
    if _run(["git", "rev-parse", "HEAD"], cwd=candidate) != args.candidate_sha:
        raise RuntimeError("candidate SHA does not match its checkout")
    if _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=candidate
    ):
        raise RuntimeError("candidate checkout is dirty")
    if not args.session_id.startswith("sess_"):
        raise RuntimeError("session ID is not a persisted product Session label")
    session_metadata = (
        args.data_dir.resolve(strict=True)
        / "agent"
        / "sessions"
        / args.session_id
        / "metadata.json"
    )
    if not session_metadata.is_file():
        raise RuntimeError("persisted Session metadata is missing")
    if _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=args.project_dir.resolve(strict=True),
    ):
        raise RuntimeError("bound project is dirty")

    suffix = args.candidate_sha[:10]
    formal_slots = _runtime_slots(rehearsal=False, suffix=suffix)
    rehearsal_slots = _runtime_slots(rehearsal=True, suffix=suffix)
    formal_signers = _signers(key_root, rehearsal=False, suffix=suffix)
    rehearsal_signers = _signers(key_root, rehearsal=True, suffix=suffix)

    incomplete = {
        "schema": "machine-private.w2-next-attempt-plan.v1",
        "policy_id": f"w2-policy-{args.label}",
        "repository_path": str(candidate),
        "candidate": {
            "candidate_sha": args.candidate_sha,
            "environment_id": f"w2-local-windows-chrome-{args.label}",
            "session_id": args.session_id,
            "mode_id": "integrated-formal",
        },
        "evidence_set_id": f"w2-evidence-{args.label}",
        "runtime_slots": formal_slots,
        "non_runtime_artifact_slots": [],
        "signers": formal_signers,
    }

    rehearsal_policy = {
        "schema": "live-voice.w2-trust-policy.v2",
        "policy_id": f"w2-rehearsal-policy-{args.label}",
        "repository_path": str(candidate),
        "candidate": {
            "candidate_sha": args.candidate_sha,
            "environment_id": f"w2-rehearsal-windows-chrome-{args.label}",
            "session_id": args.session_id,
            "mode_id": "integrated-formal",
        },
        "evidence_set_id": f"w2-rehearsal-evidence-{args.label}",
        "runtime_slots": [_policy_runtime_slot(slot) for slot in rehearsal_slots],
        "artifact_slots": [
            {
                "artifact_id": slot["artifact_id"],
                "artifact_sequence": slot["artifact_sequence"],
                "evidence_kind": "real_runtime",
                "signer_id": slot["signer_id"],
                "source_label": None,
                "expected_subjects": ["runtime:rehearsal-placeholder"],
            }
            for slot in rehearsal_slots
        ],
        "signers": rehearsal_signers,
    }

    rehearsal_import = {
        "schema": "machine-private.w2-rehearsal-import.v1",
        "rehearsal_root": str(rehearsal_root),
        "runtime_imports": [
            {
                "logical_slot": slot["logical_slot"],
                "artifact_id": slot["artifact_id"],
                "content_file": f"{slot['artifact_id']}.jsonl",
                "signature_file": f"{slot['artifact_id']}.signature",
                "expected_subjects_sha256": None,
            }
            for slot in rehearsal_slots
        ],
    }

    policy = staging / "rehearsal-trust-policy.unsigned.json"
    signature = staging / "rehearsal-trust-policy.signature"
    sign_script = f"""$ErrorActionPreference = 'Stop'

$candidateSha = {_ps_literal(args.candidate_sha)}
$candidateRoot = {_ps_literal(candidate)}
$python = {_ps_literal(args.python.resolve(strict=True))}
$policy = {_ps_literal(policy)}
$signature = {_ps_literal(signature)}
$rootDirectory = {_ps_literal(external_root)}
$rootPrivate = Join-Path $rootDirectory 'root.private'
$rootPublic = Join-Path $rootDirectory 'root.public'

Set-Location -LiteralPath $candidateRoot
if ((git rev-parse HEAD).Trim() -ne $candidateSha) {{ throw 'Candidate HEAD changed' }}
if (git status --porcelain=v1 --untracked-files=all) {{ throw 'Candidate is not clean' }}
if (-not (Test-Path -LiteralPath $policy -PathType Leaf)) {{ throw 'Unsigned rehearsal policy is missing' }}
if (Test-Path -LiteralPath $signature) {{ throw 'Rehearsal policy signature already exists; refusing to overwrite' }}

$previousPythonPath = $env:PYTHONPATH
try {{
    $env:PYTHONPATH = $candidateRoot
    $loadedSource = (& $python -c "import pathlib; import jiuwenswarm.server.live_voice.w2_demo_gate as g; print(pathlib.Path(g.__file__).resolve())").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $loadedSource.StartsWith($candidateRoot, [System.StringComparison]::OrdinalIgnoreCase)) {{ throw 'Gate implementation was not loaded from the candidate root' }}
    if (Test-Path -LiteralPath $rootDirectory) {{ throw 'Fresh external-root directory already exists' }}
    New-Item -ItemType Directory -Path $rootDirectory | Out-Null
    & $python -m jiuwenswarm.server.live_voice.w2_gate_cli keygen --private-key $rootPrivate --public-key $rootPublic
    if ($LASTEXITCODE -ne 0) {{ throw 'External root key generation failed' }}
    $expectedRootSha256 = (& $python -c "import hashlib,pathlib; p=pathlib.Path(r'$rootPublic'); print(hashlib.sha256(bytes.fromhex(p.read_text(encoding='ascii').strip())).hexdigest())").Trim()
    if ($LASTEXITCODE -ne 0 -or $expectedRootSha256 -notmatch '^[0-9a-f]{{64}}$') {{ throw 'External root fingerprint calculation failed' }}
    Write-Host ''
    Write-Host 'External root public-key SHA-256:' -ForegroundColor Yellow
    Write-Host $expectedRootSha256 -ForegroundColor Cyan
    Write-Host 'Record and independently acknowledge this public fingerprint before continuing.' -ForegroundColor Yellow
    $acknowledged = Read-Host 'Type the complete 64-character fingerprint to acknowledge'
    if ($acknowledged -cne $expectedRootSha256) {{ throw 'Expected-root acknowledgement did not match' }}
    & $python -m jiuwenswarm.server.live_voice.w2_gate_cli sign --private-key $rootPrivate --input $policy --signature $signature
    if ($LASTEXITCODE -ne 0) {{ throw 'Rehearsal policy signing failed' }}
    & $python -m jiuwenswarm.server.live_voice.w2_gate_cli validate-policy --trust-policy $policy --trust-policy-signature $signature --root-public-key $rootPublic --expected-root-sha256 $expectedRootSha256
    if ($LASTEXITCODE -ne 0) {{ throw 'Rehearsal policy validation failed' }}
    $policySha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $policy).Hash.ToLowerInvariant()
    Write-Host ''
    Write-Host 'W2_REHEARSAL_POLICY_READY' -ForegroundColor Green
    Write-Host "candidate_sha=$candidateSha"
    Write-Host "policy_sha256=$policySha256"
    Write-Host "expected_root_sha256=$expectedRootSha256"
    Write-Host 'Keep this window open and send Codex only the three non-secret lines above.'
    Read-Host 'Press Enter only after Codex has acknowledged the result'
}} finally {{
    $env:PYTHONPATH = $previousPythonPath
}}
"""

    metadata = {
        "schema": "machine-private.w2-attempt-scaffold.v1",
        "label": args.label,
        "candidate_root": str(candidate),
        "candidate_sha": args.candidate_sha,
        "staging_root": str(staging),
        "rehearsal_root": str(rehearsal_root),
        "formal_evidence_root": str(formal_root),
        "key_root": str(key_root),
        "external_root": str(external_root),
        "chrome_profile": str(chrome_profile),
        "data_dir": str(args.data_dir.resolve(strict=True)),
        "python": str(args.python.resolve(strict=True)),
        "node": str(node),
        "chrome": str(chrome),
        "frontend_root": str(
            candidate / "jiuwenswarm" / "channels" / "web" / "frontend"
        ),
        "prepared_wav": str(args.prepared_wav.resolve(strict=True)),
        "session_id": args.session_id,
        "project_id": args.project_id,
        "project_dir": str(args.project_dir.resolve(strict=True)),
        "environment_id": rehearsal_policy["candidate"]["environment_id"],
        "evidence_set_id": rehearsal_policy["evidence_set_id"],
        "ports": {
            "agentserver": 18092,
            "web": 19000,
            "gateway": 19001,
            "vite": 5173,
            "chrome_debug": 9223,
        },
        "speech": {
            "provider": "openai-compatible",
            "api_base": "https://api.openai.com/v1",
            "stt_model": "gpt-4o-mini-transcribe",
            "tts_model": "gpt-4o-mini-tts",
            "voice": "marin",
        },
        "p3_databases": {
            str(pair): str(
                args.data_dir.resolve(strict=True)
                / "live_voice"
                / "p3alpha"
                / f"w2-rehearsal-{args.label}-pair{pair}.sqlite3"
            )
            for pair in (1, 2, 3)
        },
        "fault_request_ids": {
            "p2_retriable": f"w2-{suffix}-p2-retriable-{secrets.token_hex(8)}",
            "p3_stale": f"w2-{suffix}-p3-stale-{secrets.token_hex(8)}",
        },
        "runtime_slots": rehearsal_slots,
    }

    outputs = {
        staging / "candidate-plan.incomplete.json": _canonical(incomplete),
        policy: _canonical(rehearsal_policy),
        staging / "rehearsal-import.json": _canonical(rehearsal_import),
        staging / "attempt-scaffold.json": _canonical(metadata),
        staging / "sign-rehearsal-policy.ps1": sign_script.encode("utf-8"),
    }
    for path in outputs:
        if path.exists():
            raise RuntimeError(f"scaffold output already exists: {path}")
    for database in metadata["p3_databases"].values():
        if Path(database).exists():
            raise RuntimeError(f"fresh P3 database path already exists: {database}")
    for path, content in outputs.items():
        _exclusive_write(path, content)
    return {
        "status": "FRESH_SCAFFOLD_READY",
        "candidate_sha": args.candidate_sha,
        "runtime_slots": len(rehearsal_slots),
        "outputs": sorted(str(path) for path in outputs),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--staging-root", required=True, type=Path)
    parser.add_argument("--rehearsal-root", required=True, type=Path)
    parser.add_argument("--formal-evidence-root", required=True, type=Path)
    parser.add_argument("--key-root", required=True, type=Path)
    parser.add_argument("--external-root", required=True, type=Path)
    parser.add_argument("--chrome-profile", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--chrome", required=True, type=Path)
    parser.add_argument("--prepared-wav", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), separators=(",", ":"), sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - machine-private stable boundary
        print(f"build-w2-fresh-attempt-scaffold: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
