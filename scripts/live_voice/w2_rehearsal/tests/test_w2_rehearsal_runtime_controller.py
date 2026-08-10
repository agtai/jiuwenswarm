from __future__ import annotations

import json
import subprocess
import sys
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
        "staging_root": str(tmp_path / "staging"),
        "leaf_key_root": str(tmp_path / "keys"),
        "principal_id": "principal-1",
        "project_id": "project-1",
        "ports": {
            "agentserver": 18092,
            "web": 19000,
            "gateway": 19001,
            "vite": 15173,
            "chrome_debug": 19223,
        },
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


def _private_payload(config: dict[str, object]) -> dict[str, object]:
    speech = config["speech"]
    assert isinstance(speech, dict)
    return {
        "schema": "machine-private.live-voice-no-evidence-smoke.v1",
        "agent": {
            "provider": "OpenAI",
            "api_base": "https://agent.example.invalid/v1",
            "api_key": "private-agent-key",
            "model": "agent-model",
        },
        "speech": {
            "provider": speech["provider"],
            "api_base": speech["api_base"],
            "api_key": "private-speech-key",
            "stt_model": speech["stt_model"],
            "tts_model": speech["tts_model"],
            "voice": speech["voice"],
        },
    }


def _write_private_config(tmp_path: Path, config: dict[str, object]) -> Path:
    path = (tmp_path / "machine-private.json").resolve()
    path.write_text(json.dumps(_private_payload(config)), encoding="utf-8")
    return path


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
        "EMBED_KEY": "legacy-embed-secret",
        "GOOGLE_APPLICATION_CREDENTIALS": "google-credential-path",
        "AZURE_STORAGE_CONNECTION_STRING": "azure-connection-secret",
        "DATABASE_URL": "database-url-secret",
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


def test_private_config_is_strict_and_routes_values_only_to_the_owned_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    path = _write_private_config(tmp_path, config)
    for name, value in {
        "API_KEY": "stale-parent-agent-key",
        "API_BASE": "https://stale-parent.invalid/v1",
        "MODEL_NAME": "stale-parent-model",
        "MODEL_PROVIDER": "stale-parent-provider",
        "LIVE_VOICE_SPEECH_API_KEY": "stale-parent-speech-key",
    }.items():
        monkeypatch.setenv(name, value)

    private = controller._load_private_config(path, config)
    agent_env = controller._agent_provider_env(private)
    common = _base_env(config)
    gateway = _slot_env(
        config,
        _slot(pair=1, sequence=1, producer="gateway"),
        p3_token="p3-token",
        speech_key=private.speech.api_key,
        agent_env=agent_env,
    )
    agentserver = _slot_env(
        config,
        _slot(pair=1),
        p3_token="p3-token",
        speech_key=private.speech.api_key,
        agent_env=agent_env,
    )

    private_values = {
        "OpenAI",
        "https://agent.example.invalid/v1",
        "private-agent-key",
        "agent-model",
        "private-speech-key",
    }
    assert private_values.isdisjoint(common.values())
    assert gateway["LIVE_VOICE_SPEECH_API_KEY"] == "private-speech-key"
    assert all(name not in gateway for name in controller._AGENT_RUNTIME_ENV_NAMES)
    assert agentserver["MODEL_PROVIDER"] == "OpenAI"
    assert agentserver["API_BASE"] == "https://agent.example.invalid/v1"
    assert agentserver["API_KEY"] == "private-agent-key"
    assert agentserver["MODEL_NAME"] == "agent-model"
    assert "LIVE_VOICE_SPEECH_API_KEY" not in agentserver
    assert private_values.isdisjoint(
        value
        for value in (
            str(config),
            "python runner agentserver --port 18092",
        )
    )
    output = capsys.readouterr()
    assert all(value not in output.out and value not in output.err for value in private_values)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.__setitem__("schema", "foreign"),
        lambda value: value.__setitem__("extra", True),
        lambda value: value["agent"].pop("model"),
        lambda value: value["agent"].__setitem__("api_key", ""),
        lambda value: value["agent"].__setitem__("provider", 1),
        lambda value: value["speech"].__setitem__("extra", "closed"),
        lambda value: value["speech"].__setitem__("api_key", "x" * 4097),
        lambda value: value["agent"].__setitem__(
            "api_key", "do-not-leak-\ud800"
        ),
    ),
)
def test_private_config_rejects_open_incomplete_or_unbounded_content_without_leak(
    tmp_path: Path,
    mutate: object,
) -> None:
    config = _config(tmp_path)
    value = _private_payload(config)
    mutate(value)
    path = (tmp_path / "invalid-private.json").resolve()
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(RuntimeError) as raised:
        controller._load_private_config(path, config)

    assert "private-agent-key" not in str(raised.value)
    assert "private-speech-key" not in str(raised.value)
    assert "do-not-leak" not in str(raised.value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("provider", "foreign-provider"),
        ("api_base", "https://foreign.invalid/v1"),
        ("stt_model", "foreign-stt"),
        ("tts_model", "foreign-tts"),
        ("voice", "foreign-voice"),
    ),
)
def test_private_speech_metadata_must_exactly_match_runtime_config(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    config = _config(tmp_path)
    value = _private_payload(config)
    value["speech"][field] = replacement
    path = (tmp_path / "mismatched-private.json").resolve()
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(RuntimeError, match="speech metadata"):
        controller._load_private_config(path, config)


@pytest.mark.parametrize("root_field", ("candidate_root", "evidence_root", "log"))
def test_private_config_must_be_absolute_regular_and_outside_runtime_roots(
    tmp_path: Path,
    root_field: str,
) -> None:
    config = _config(tmp_path)
    root = (
        Path(str(config["staging_root"])) / "rehearsal-runtime-logs"
        if root_field == "log"
        else Path(str(config[root_field]))
    )
    root.mkdir(parents=True)
    path = (root / "private.json").resolve()
    path.write_text(json.dumps(_private_payload(config)), encoding="utf-8")

    with pytest.raises(RuntimeError, match="outside candidate, evidence, and log roots"):
        controller._load_private_config(path, config)

    with pytest.raises(RuntimeError, match="absolute regular file"):
        controller._load_private_config(Path("relative-private.json"), config)


def test_private_config_skips_hidden_prompt_and_never_enters_runtime_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    evidence_root = Path(str(config["evidence_root"]))
    evidence_root.mkdir()
    path = _write_private_config(tmp_path, config)
    config_path = (tmp_path / "runtime.json").resolve()
    config_path.write_text(json.dumps(config), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeController:
        processes: dict[str, object] = {}

        def __init__(
            self,
            loaded: dict[str, object],
            slots: list[Slot],
            speech_key: str,
            agent_env: dict[str, str],
        ) -> None:
            self.speech_key = speech_key
            self.agent_env = dict(agent_env)
            captured.update(
                loaded=loaded,
                slots=slots,
                speech_key=speech_key,
                agent_env=dict(agent_env),
            )

    monkeypatch.setattr(controller, "_load", lambda _path: config)
    monkeypatch.setattr(controller, "_slots", lambda _config: [])
    monkeypatch.setattr(controller, "_policy_preflight", lambda *_args: None)
    monkeypatch.setattr(controller, "_assert_port_free", lambda _port: None)
    monkeypatch.setattr(controller, "_loop", lambda _controller: None)
    monkeypatch.setattr(controller, "Controller", FakeController)
    monkeypatch.setattr(
        controller.getpass,
        "getpass",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("private config must skip hidden prompt")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "controller",
            "--config",
            str(config_path),
            "--private-config",
            str(path),
        ],
    )

    assert controller.main() == 0
    assert captured["speech_key"] == "private-speech-key"
    assert captured["agent_env"] == {
        "MODEL_PROVIDER": "OpenAI",
        "API_BASE": "https://agent.example.invalid/v1",
        "API_KEY": "private-agent-key",
        "MODEL_NAME": "agent-model",
    }
    output = capsys.readouterr()
    for value in (
        "private-speech-key",
        "private-agent-key",
        "https://agent.example.invalid/v1",
        "agent-model",
    ):
        assert value not in output.out
        assert value not in output.err


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


@pytest.mark.parametrize(
    "name", ("API_KEY", "API_BASE", "MODEL_NAME", "MODEL_PROVIDER", "OPENAI_API_KEY")
)
def test_shared_dotenv_rejects_agent_provider_runtime_names(
    tmp_path: Path, name: str
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        f"{name}=agent-only\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Agent/provider credential name"):
        _assert_shared_dotenv_secret_boundary(tmp_path)


@pytest.mark.parametrize(
    "name",
    (
        "GITHUB_TOKEN",
        "EMBED_KEY",
        "MEM0_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AZURE_STORAGE_CONNECTION_STRING",
        "DATABASE_URL",
    ),
)
def test_shared_dotenv_rejects_generic_secret_names(tmp_path: Path, name: str) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        f"{name}=must-not-cross-child-boundaries\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="forbidden secret credential name"):
        _assert_shared_dotenv_secret_boundary(tmp_path)


def test_shared_dotenv_allows_nonsecret_config_and_commented_secret_names(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / ".env").write_text(
        "SAFE_RUNTIME_CONFIG=enabled\n# LIVE_VOICE_SPEECH_API_KEY=disabled\n",
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


class _FakeProcess:
    def __init__(self, return_code: int | None) -> None:
        self.return_code = return_code

    def poll(self) -> int | None:
        return self.return_code

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.return_code is None:
            raise AssertionError("live fake process must not be waited")
        return self.return_code


class _FakeHandle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _TimeoutProcess(_FakeProcess):
    def __init__(self) -> None:
        super().__init__(None)

    def wait(self, timeout: float | None = None) -> int:
        raise subprocess.TimeoutExpired("fault-runner", timeout)


def _runtime_controller(tmp_path: Path) -> controller.Controller:
    config = _config(tmp_path)
    config.update(
        {
            "python": sys.executable,
            "frontend_root": str(tmp_path / "frontend"),
        }
    )
    return controller.Controller(
        config,
        [
            _slot(pair=pair, producer=producer)
            for pair in (1, 2, 3)
            for producer in ("agentserver", "gateway")
        ],
        "speech-secret",
        {"API_KEY": "agent-secret"},
    )


def test_fault_runner_starts_with_public_authority_and_no_child_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AZURE_STORAGE_CONNECTION_STRING",
        "DATABASE_URL",
    ):
        monkeypatch.setenv(name, f"secret-{name}")
    runtime = _runtime_controller(tmp_path)
    runtime.processes.update(
        {
            "vite": _FakeProcess(None),
            "agentserver-1": _FakeProcess(None),
            "gateway-1": _FakeProcess(None),
        }
    )
    captured: dict[str, object] = {}

    def capture_start(
        name: str,
        argv: list[str],
        env: dict[str, str],
        *,
        cwd: Path | None = None,
    ) -> None:
        captured.update(name=name, argv=argv, env=env, cwd=cwd)

    monkeypatch.setattr(runtime, "_start", capture_start)
    monkeypatch.setattr(controller, "_wait_port", lambda *_args, **_kwargs: None)

    runtime.start_fault_runner(1)

    assert captured["name"] == "fault-runner-1"
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv[0] == sys.executable
    assert Path(argv[1]).name == "w2_fault_runner.py"
    assert argv[argv.index("--policy-id") + 1] == "policy-1"
    assert argv[argv.index("--candidate-sha") + 1] == "a" * 40
    assert argv[argv.index("--evidence-set-id") + 1] == "evidence-set-1"
    assert argv[argv.index("--pair") + 1] == "1"
    assert argv[argv.index("--gateway-url") + 1] == "ws://127.0.0.1:19000/ws"
    assert argv[argv.index("--origin") + 1] == "http://127.0.0.1:15173"
    assert argv[argv.index("--cdp-url") + 1] == "http://127.0.0.1:19223"
    assert argv[argv.index("--timeout") + 1] == "300"
    assert "speech-secret" not in argv
    assert "agent-secret" not in argv
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_ENABLED"] == "false"
    assert "LIVE_VOICE_SPEECH_API_KEY" not in env
    assert "API_KEY" not in env
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in env
    assert "AZURE_STORAGE_CONNECTION_STRING" not in env
    assert "DATABASE_URL" not in env
    assert runtime.p3_token not in env.values()


def test_pair_stop_refuses_live_runner_then_requires_exact_pass_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_controller(tmp_path)
    log_dir = Path(str(runtime.config["staging_root"])) / "rehearsal-runtime-logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "fault-runner-1.log"
    log_path.write_text("runner is still active\n", encoding="utf-8")
    runtime.processes.update(
        {
            "agentserver-1": _FakeProcess(None),
            "gateway-1": _FakeProcess(None),
            "fault-runner-1": _FakeProcess(None),
        }
    )
    runtime.log_handles["fault-runner-1"] = _FakeHandle()
    runtime.log_paths["fault-runner-1"] = log_path
    stopped: list[str] = []
    monkeypatch.setattr(runtime, "_signal_and_wait", lambda name, **_kwargs: stopped.append(name))
    monkeypatch.setattr(controller, "_wait_port", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_verify_sealed", lambda slot: None)

    with pytest.raises(RuntimeError, match="still running"):
        runtime.stop_pair(1)
    assert stopped == []

    runtime.processes["fault-runner-1"] = _FakeProcess(0)
    log_path.write_text(
        "W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS pair=1 faults=3 routes=closed\n",
        encoding="utf-8",
    )
    runtime.wait_fault_runner(1)
    runtime.stop_pair(1)

    assert stopped == ["gateway-1", "agentserver-1"]


def test_failed_fault_runner_allows_graceful_cleanup_but_invalidates_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_controller(tmp_path)
    log_dir = Path(str(runtime.config["staging_root"])) / "rehearsal-runtime-logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "fault-runner-2.log"
    log_path.write_text("foreign or missing marker\n", encoding="utf-8")
    runtime.processes.update(
        {
            "agentserver-2": _FakeProcess(None),
            "gateway-2": _FakeProcess(None),
            "fault-runner-2": _FakeProcess(2),
        }
    )
    runtime.log_handles["fault-runner-2"] = _FakeHandle()
    runtime.log_paths["fault-runner-2"] = log_path
    stopped: list[str] = []
    monkeypatch.setattr(runtime, "_signal_and_wait", lambda name, **_kwargs: stopped.append(name))
    monkeypatch.setattr(controller, "_wait_port", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_verify_sealed", lambda slot: None)

    with pytest.raises(RuntimeError, match="product fault runner did not pass"):
        runtime.stop_pair(2)

    assert stopped == ["gateway-2", "agentserver-2"]


def test_fault_runner_timeout_retains_process_and_log_ownership_for_retry(
    tmp_path: Path,
) -> None:
    runtime = _runtime_controller(tmp_path)
    log_dir = Path(str(runtime.config["staging_root"])) / "rehearsal-runtime-logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "fault-runner-3.log"
    log_path.write_text("still waiting for stock closure\n", encoding="utf-8")
    process = _TimeoutProcess()
    handle = _FakeHandle()
    runtime.processes["fault-runner-3"] = process
    runtime.log_handles["fault-runner-3"] = handle
    runtime.log_paths["fault-runner-3"] = log_path

    with pytest.raises(RuntimeError, match="still running"):
        runtime.wait_fault_runner(3)

    assert runtime.processes["fault-runner-3"] is process
    assert runtime.log_handles["fault-runner-3"] is handle
    assert runtime.log_paths["fault-runner-3"] == log_path
    assert handle.closed is False
    assert 3 not in runtime.fault_passed_pairs


@pytest.mark.parametrize(
    "lines",
    (
        ["wrong marker"],
        [
            "W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS pair=1 faults=3 routes=closed",
            "W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS pair=1 faults=3 routes=closed",
        ],
        [
            "W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS pair=1 faults=3 routes=closed",
            "unexpected trailing output",
        ],
    ),
)
def test_zero_exit_requires_one_exact_final_fault_runner_marker(
    tmp_path: Path, lines: list[str]
) -> None:
    runtime = _runtime_controller(tmp_path)
    log_dir = Path(str(runtime.config["staging_root"])) / "rehearsal-runtime-logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "fault-runner-1.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    handle = _FakeHandle()
    runtime.processes["fault-runner-1"] = _FakeProcess(0)
    runtime.log_handles["fault-runner-1"] = handle
    runtime.log_paths["fault-runner-1"] = log_path

    with pytest.raises(RuntimeError, match="did not pass"):
        runtime.wait_fault_runner(1)

    assert "fault-runner-1" not in runtime.processes
    assert "fault-runner-1" not in runtime.log_handles
    assert "fault-runner-1" not in runtime.log_paths
    assert handle.closed is True
    assert 1 not in runtime.fault_passed_pairs
