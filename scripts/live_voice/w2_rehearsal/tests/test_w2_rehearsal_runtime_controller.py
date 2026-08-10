from __future__ import annotations

import json
from pathlib import Path

import pytest

import w2_rehearsal_runtime_controller as controller
from jiuwenswarm.server.live_voice.w2_fault_plan import (
    P1_RETRIABLE_FAULT_OPERATION_ENV,
    P1_RETRIABLE_FAULT_REQUEST_ID_ENV,
    P2_RETRIABLE_FAULT_OPERATION_ENV,
    P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
    P2_STALE_FAULT_OPERATION_ENV,
    P2_STALE_FAULT_REQUEST_ID_ENV,
    P3_STALE_FAULT_OPERATION_ENV,
    P3_STALE_FAULT_REQUEST_ID_ENV,
    W2FaultClass,
    W2FaultPlane,
)
from w2_rehearsal_runtime_controller import (
    Slot,
    _assert_shared_dotenv_secret_boundary,
    _base_env,
    _load,
    _slot_env,
)
from w2_product_fault_binding import (
    derive_product_fault_plan_payload,
    require_product_fault,
)


def _config(tmp_path: Path) -> dict[str, object]:
    authority = {
        "policy_id": "policy-1",
        "candidate_sha": "a" * 40,
        "evidence_set_id": "evidence-set-1",
    }
    return {
        "schema": "machine-private.w2-rehearsal-runtime-config.v3",
        "candidate_root": str(tmp_path / "candidate"),
        "candidate_sha": authority["candidate_sha"],
        "data_dir": str(tmp_path / "data"),
        "environment_id": "environment-1",
        "session_id": "session-1",
        "mode_id": "integrated-formal",
        "evidence_set_id": authority["evidence_set_id"],
        "policy_id": authority["policy_id"],
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
        "product_fault_plan": derive_product_fault_plan_payload(**authority),
        "speech": {
            "provider": "openai-compatible",
            "api_base": "https://example.invalid/v1",
            "stt_model": "stt",
            "tts_model": "tts",
            "voice": "voice",
        },
    }


def _slot(
    *, pair: int | None, sequence: int = 2, producer: str = "agentserver"
) -> Slot:
    return Slot(
        artifact_id=(
            f"{producer}-showcase-{pair}"
            if pair is not None
            else f"{producer}-restart-successor"
        ),
        sequence=sequence,
        producer=producer,
        epoch=f"{producer}-epoch-{sequence}",
        predecessor=None,
        showcase_run=pair,
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.pop("product_fault_plan"),
        lambda value: value["product_fault_plan"]["items"].pop(),
        lambda value: value["product_fault_plan"]["items"][0].__setitem__(
            "request_id", "foreign"
        ),
        lambda value: value["product_fault_plan"].__setitem__("extra", True),
        lambda value: value.__setitem__("policy_id", "foreign-policy"),
        lambda value: value.__setitem__(
            "fault_request_ids", {"p2_retriable": "legacy-random"}
        ),
    ),
)
def test_runtime_config_rejects_missing_foreign_or_tampered_fault_plan(
    tmp_path: Path, mutate: object
) -> None:
    path = tmp_path / "config.json"
    config = _config(tmp_path)
    mutate(config)
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(RuntimeError):
        _load(path)


def test_old_runtime_config_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema": "machine-private.w2-rehearsal-runtime-config.v2",
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
    plan = config["product_fault_plan"]

    gateway1 = _slot_env(
        config,
        _slot(pair=1, sequence=1, producer="gateway"),
        p3_token="p3-token",
        speech_key="speech-key",
    )

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

    p1_retriable = require_product_fault(
        plan,
        pair=1,
        plane=W2FaultPlane.P1_SPEECH_MEDIA,
        fault_class=W2FaultClass.RETRIABLE,
    )
    p2_retriable = require_product_fault(
        plan,
        pair=1,
        plane=W2FaultPlane.P2_CONVERSATION,
        fault_class=W2FaultClass.RETRIABLE,
    )
    p2_stale = require_product_fault(
        plan,
        pair=3,
        plane=W2FaultPlane.P2_CONVERSATION,
        fault_class=W2FaultClass.ZERO_EFFECT,
    )
    p3_stale = require_product_fault(
        plan,
        pair=3,
        plane=W2FaultPlane.P3_TASK,
        fault_class=W2FaultClass.ZERO_EFFECT,
    )

    assert gateway1[P1_RETRIABLE_FAULT_REQUEST_ID_ENV] == p1_retriable["request_id"]
    assert gateway1[P1_RETRIABLE_FAULT_OPERATION_ENV] == p1_retriable["operation"]
    assert pair1[P2_RETRIABLE_FAULT_REQUEST_ID_ENV] == p2_retriable["request_id"]
    assert pair1[P2_RETRIABLE_FAULT_OPERATION_ENV] == p2_retriable["operation"]
    for name in (
        P1_RETRIABLE_FAULT_REQUEST_ID_ENV,
        P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
        P2_STALE_FAULT_REQUEST_ID_ENV,
        P3_STALE_FAULT_REQUEST_ID_ENV,
    ):
        assert name not in pair2
        assert name not in successor
    assert pair3[P2_STALE_FAULT_REQUEST_ID_ENV] == p2_stale["request_id"]
    assert pair3[P2_STALE_FAULT_OPERATION_ENV] == p2_stale["operation"]
    assert pair3[P3_STALE_FAULT_REQUEST_ID_ENV] == p3_stale["request_id"]
    assert pair3[P3_STALE_FAULT_OPERATION_ENV] == p3_stale["operation"]


def test_parent_secrets_are_scrubbed_and_reintroduced_only_to_the_right_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = {
        "LIVE_VOICE_SPEECH_API_KEY": "parent-speech-secret",
        "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY": "legacy-speech-secret",
        "OPENAI_API_KEY": "agent-provider-secret",
        "GITHUB_TOKEN": "unrelated-parent-secret",
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN": "stale-p3-secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    config = _config(tmp_path)

    common = _base_env(config)
    gateway = _slot_env(
        config,
        _slot(pair=1, sequence=1, producer="gateway"),
        p3_token="fresh-p3-secret",
        speech_key="fresh-speech-secret",
    )
    agentserver = _slot_env(
        config,
        _slot(pair=1),
        p3_token="fresh-p3-secret",
        speech_key="fresh-speech-secret",
    )

    assert all(secret not in common.values() for secret in values.values())
    assert gateway["LIVE_VOICE_SPEECH_API_KEY"] == "fresh-speech-secret"
    assert gateway["JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"] == "fresh-p3-secret"
    assert "OPENAI_API_KEY" not in gateway
    assert "GITHUB_TOKEN" not in gateway
    assert "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY" not in gateway
    assert agentserver["OPENAI_API_KEY"] == "agent-provider-secret"
    assert agentserver["JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"] == "fresh-p3-secret"
    assert "LIVE_VOICE_SPEECH_API_KEY" not in agentserver
    assert "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY" not in agentserver
    assert "GITHUB_TOKEN" not in agentserver
    output = capsys.readouterr()
    assert all(
        secret not in output.out and secret not in output.err
        for secret in (*values.values(), "fresh-p3-secret", "fresh-speech-secret")
    )


@pytest.mark.parametrize(
    "name",
    (
        "LIVE_VOICE_SPEECH_API_KEY",
        "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY",
        "live_voice_speech_api_key",
    ),
)
def test_shared_dotenv_rejects_real_and_legacy_speech_key_names(
    tmp_path: Path, name: str
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        f"# no value is surfaced\nexport {name}=private-value\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="forbidden Speech credential name"):
        _assert_shared_dotenv_secret_boundary(tmp_path)


def test_shared_dotenv_rejects_agent_provider_key(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        "OPENAI_API_KEY=agent-only\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Agent/provider credential name"):
        _assert_shared_dotenv_secret_boundary(tmp_path)


def test_shared_dotenv_allows_nonsecret_config_and_commented_secret_names(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        "MODEL_NAME=agent-model\n# LIVE_VOICE_SPEECH_API_KEY=disabled\n",
        encoding="utf-8",
    )

    _assert_shared_dotenv_secret_boundary(tmp_path)


@pytest.mark.parametrize(
    "changed",
    (
        {"policy_id": "foreign-policy"},
        {
            "candidate_binding": [
                "b" * 40,
                "environment-1",
                "session-1",
                "integrated-formal",
            ]
        },
        {"evidence_set_id": "foreign-evidence"},
        {"repository_path": "foreign-repository"},
    ),
)
def test_policy_preflight_rejects_foreign_public_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: dict[str, object]
) -> None:
    config = _config(tmp_path)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    config.update(
        {
            "python": "python",
            "trust_policy": str(tmp_path / "policy.json"),
            "trust_policy_signature": str(tmp_path / "policy.signature"),
            "root_public_key": str(tmp_path / "root.public"),
            "expected_root_sha256": "f" * 64,
        }
    )
    validated = {
        "status": "VALID",
        "policy_id": config["policy_id"],
        "repository_path": str(candidate.resolve()),
        "candidate_binding": [
            config["candidate_sha"],
            config["environment_id"],
            config["session_id"],
            config["mode_id"],
        ],
        "evidence_set_id": config["evidence_set_id"],
        **changed,
    }

    def run_checked(
        argv: list[str], *, cwd: Path, env: dict[str, str]
    ) -> str:
        del cwd, env
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            return str(config["candidate_sha"])
        if argv[:2] == ["git", "status"]:
            return ""
        if "validate-policy" in argv:
            return json.dumps(validated)
        if argv[1:2] == ["-c"]:
            return str(candidate / "jiuwenswarm" / "server" / "live_voice" / "w2_demo_gate.py")
        raise AssertionError(argv)

    monkeypatch.setattr(controller, "_run_checked", run_checked)

    with pytest.raises(RuntimeError, match="exactly match signed policy"):
        controller._policy_preflight(config, {})
