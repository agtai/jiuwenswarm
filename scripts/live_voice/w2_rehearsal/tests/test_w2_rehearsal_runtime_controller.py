from __future__ import annotations

import json
from pathlib import Path

import pytest

from w2_rehearsal_runtime_controller import Slot, _load, _slot_env


def _config(tmp_path: Path) -> dict[str, object]:
    return {
        "candidate_root": str(tmp_path / "candidate"),
        "candidate_sha": "a" * 40,
        "data_dir": str(tmp_path / "data"),
        "environment_id": "environment-1",
        "session_id": "session-1",
        "mode_id": "integrated-formal",
        "evidence_set_id": "evidence-set-1",
        "evidence_root": str(tmp_path / "evidence"),
        "leaf_key_root": str(tmp_path / "keys"),
        "principal_id": "principal-1",
        "project_id": "project-1",
        "ports": {"agentserver": 18092, "web": 19000, "gateway": 19001},
        "p3_databases": {
            "1": str(tmp_path / "pair1.sqlite3"),
            "2": str(tmp_path / "pair2.sqlite3"),
            "3": str(tmp_path / "pair3.sqlite3"),
        },
        "fault_request_ids": {
            "p2_retriable": "request-p2-retriable",
            "p3_stale": "request-p3-stale",
        },
        "speech": {
            "provider": "openai-compatible",
            "api_base": "https://example.invalid/v1",
            "stt_model": "stt",
            "tts_model": "tts",
            "voice": "voice",
        },
    }


def _slot(*, pair: int | None, sequence: int = 2) -> Slot:
    return Slot(
        artifact_id=(
            f"agentserver-showcase-{pair}"
            if pair is not None
            else "agentserver-restart-successor"
        ),
        sequence=sequence,
        producer="agentserver",
        epoch=f"agentserver-epoch-{sequence}",
        predecessor=None,
        showcase_run=pair,
    )


@pytest.mark.parametrize(
    "faults",
    (
        {},
        {"p2_retriable": "request-1"},
        {"p2_retriable": "request-1", "p3_stale": "request-2", "extra": "x"},
        {"p2_retriable": "same", "p3_stale": "same"},
        {"p2_retriable": "bad request", "p3_stale": "request-2"},
    ),
)
def test_runtime_config_rejects_incomplete_ambiguous_or_unbounded_fault_ids(
    tmp_path: Path, faults: dict[str, str]
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema": "machine-private.w2-rehearsal-runtime-config.v2",
                "fault_request_ids": faults,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):
        _load(path)


def test_old_runtime_config_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema": "machine-private.w2-rehearsal-runtime-config.v1",
                "fault_request_ids": {
                    "p2_retriable": "request-1",
                    "p3_stale": "request-2",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unsupported"):
        _load(path)


def test_server_owned_fault_plans_are_scoped_to_exact_rehearsal_slots(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    p2_request_env = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_RETRIABLE_FAULT_REQUEST_ID"
    p3_request_env = "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_STALE_FAULT_REQUEST_ID"

    pair1 = _slot_env(
        config,
        _slot(pair=1),
        p3_token="p3-token",
        speech_key="speech-key",
    )
    pair2 = _slot_env(
        config,
        _slot(pair=2, sequence=4),
        p3_token="p3-token",
        speech_key="speech-key",
    )
    pair3 = _slot_env(
        config,
        _slot(pair=3, sequence=6),
        p3_token="p3-token",
        speech_key="speech-key",
    )
    successor = _slot_env(
        config,
        _slot(pair=None, sequence=7),
        p3_token="p3-token",
        speech_key="speech-key",
    )

    assert pair1[p2_request_env] == "request-p2-retriable"
    assert p3_request_env not in pair1
    assert p2_request_env not in pair2
    assert p3_request_env not in pair2
    assert p2_request_env not in pair3
    assert pair3[p3_request_env] == "request-p3-stale"
    assert p2_request_env not in successor
    assert p3_request_env not in successor
