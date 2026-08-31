# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""F13: build-contract v2 binds every compile-time Vite input.

The pure contract functions live in scripts/live_voice/build_contract.psm1 and
are exercised through a PowerShell probe so the exact production module (the
one the launcher imports) is what gets verified, JSON-roundtrip included.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "live_voice" / "build_contract.psm1"
PROBE_PATH = Path(__file__).with_name("live_voice_build_contract_probe.ps1")

_POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def _run_probe() -> dict[str, object]:
    assert _POWERSHELL is not None, "PowerShell is required for the launcher contract"
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("VITE_")
    }
    completed = subprocess.run(
        [
            _POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROBE_PATH),
            "-ModulePath",
            str(MODULE_PATH),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def probe() -> dict[str, object]:
    return _run_probe()


def test_same_vite_inputs_allow_reuse(probe: dict[str, object]) -> None:
    assert probe["same"] is None


def test_flag_flip_invalidates_reuse_before_service_start(
    probe: dict[str, object],
) -> None:
    for scenario in ("flip_true_to_false", "recorded_input_missing"):
        reason = probe[scenario]
        assert isinstance(reason, str) and reason.startswith(
            "BUILD_CONTRACT_VITE_INPUTS_CHANGED"
        ), f"{scenario}: {reason!r}"


def test_unknown_new_vite_input_invalidates_older_contract(
    probe: dict[str, object],
) -> None:
    reason = probe["unknown_new_input"]
    assert isinstance(reason, str)
    assert reason.startswith("BUILD_CONTRACT_VITE_INPUTS_CHANGED")
    assert "VITE_NEW_UNKNOWN_FLAG" in reason


def test_digest_bindings_still_enforced(probe: dict[str, object]) -> None:
    assert str(probe["lock_mismatch"]).startswith("BUILD_CONTRACT_LOCKFILE_MISMATCH")
    assert str(probe["source_mismatch"]).startswith("BUILD_CONTRACT_SOURCE_MISMATCH")


def test_legacy_schema_is_rejected(probe: dict[str, object]) -> None:
    assert str(probe["legacy_schema"]).startswith("BUILD_CONTRACT_SCHEMA_UNSUPPORTED")


def test_runtime_flags_derive_from_the_verified_contract(
    probe: dict[str, object],
) -> None:
    assert probe["contract_flag_value"] == "true"
