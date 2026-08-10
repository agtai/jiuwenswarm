from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

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
from w2_product_fault_binding import (
    require_product_fault,
    validate_product_fault_plan_payload,
)


CREATE_NEW_PROCESS_GROUP = 0x00000200
_LEGACY_SPEECH_API_KEY_ENV = "JIUWENSWARM_LIVE_VOICE_SPEECH_API_KEY"
_SPEECH_API_KEY_ENV = "LIVE_VOICE_SPEECH_API_KEY"
_PRIVATE_CONFIG_SCHEMA = "machine-private.live-voice-no-evidence-smoke.v1"
_PRIVATE_VALUE_MAX_CHARACTERS = 4_096
_PRIVATE_VALUE_MAX_UTF8_BYTES = 16_384
_FAULT_RUNNER_TIMEOUT_SECONDS = 300
_AGENT_RUNTIME_ENV_NAMES = frozenset(
    {"API_KEY", "API_BASE", "MODEL_NAME", "MODEL_PROVIDER"}
)
_AGENT_PROVIDER_SECRET_ENV_NAMES = frozenset(
    {
        "API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "AUDIO_API_KEY",
        "EMBED_API_KEY",
        "IMAGE_GEN_API_KEY",
        "TASK_MEMORY_API_KEY",
        "VIDEO_API_KEY",
        "VISION_API_KEY",
        "BOCHA_API_KEY",
        "PERPLEXITY_API_KEY",
        "SERPER_API_KEY",
        "JINA_API_KEY",
        "ACR_ACCESS_SECRET",
        "EMAIL_TOKEN",
        "MCP_TOKEN",
    }
)
_SAFE_PARENT_ENV_NAMES = frozenset(
    {
        "ALLUSERSPROFILE",
        "APPDATA",
        "COMMONPROGRAMFILES",
        "COMMONPROGRAMFILES(X86)",
        "COMPUTERNAME",
        "COMSPEC",
        "CURL_CA_BUNDLE",
        "DRIVERDATA",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "LOGONSERVER",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL",
        "PROCESSOR_REVISION",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PUBLIC",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        "PYTHONUTF8",
        "REQUESTS_CA_BUNDLE",
        "SESSIONNAME",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TZ",
        "USERDOMAIN",
        "USERDNSDOMAIN",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
    }
)
_SECRET_ENV_NAME = re.compile(
    r"(?:^|_)(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|"
    r"CREDENTIALS|AUTHORIZATION|PRIVATE_KEY|PRIVATE_KEY_PATH|"
    r"CONNECTION_STRING|DATABASE_URL)(?:$|_)",
)


@dataclass(frozen=True)
class Slot:
    artifact_id: str
    sequence: int
    producer: str
    epoch: str
    predecessor: str | None
    showcase_run: int | None


@dataclass(frozen=True, repr=False, slots=True)
class PrivateAgentConfig:
    provider: str
    api_base: str
    api_key: str
    model: str


@dataclass(frozen=True, repr=False, slots=True)
class PrivateSpeechConfig:
    provider: str
    api_base: str
    api_key: str
    stt_model: str
    tts_model: str
    voice: str


@dataclass(frozen=True, repr=False, slots=True)
class PrivateRuntimeConfig:
    agent: PrivateAgentConfig
    speech: PrivateSpeechConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control the signed, discarded W2 rehearsal runtime slots."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--private-config",
        type=Path,
        help=(
            "Absolute reference to the machine-private Agent/Speech config; "
            "the values never enter runtime config or child argv."
        ),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Validate all bindings without starting a process; a supplied private "
            "config is also validated without printing its values."
        ),
    )
    return parser


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "machine-private.w2-rehearsal-runtime-config.v3":
        raise RuntimeError("unsupported rehearsal runtime config")
    if "fault_request_ids" in value:
        raise RuntimeError("legacy random rehearsal fault IDs are forbidden")
    validate_product_fault_plan_payload(
        value.get("product_fault_plan"),
        policy_id=value.get("policy_id"),
        candidate_sha=value.get("candidate_sha"),
        evidence_set_id=value.get("evidence_set_id"),
    )
    return value


def _private_string(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _PRIVATE_VALUE_MAX_CHARACTERS
        or "\x00" in value
        or "\r" in value
        or "\n" in value
    ):
        raise RuntimeError(f"private runtime config {field} must be a bounded string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise RuntimeError(
            f"private runtime config {field} must contain Unicode scalar values"
        ) from None
    if len(encoded) > _PRIVATE_VALUE_MAX_UTF8_BYTES:
        raise RuntimeError(f"private runtime config {field} exceeds its byte limit")
    return value


def _exact_private_object(
    value: object, *, keys: frozenset[str], label: str
) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        raise RuntimeError(f"private runtime config {label} must use exact keys")
    return value


def _private_config_path(path: Path, config: Mapping[str, Any]) -> Path:
    if not path.is_absolute():
        raise RuntimeError("-PrivateConfig must be an absolute regular file")
    try:
        if path.is_symlink():
            raise RuntimeError("-PrivateConfig must be an absolute regular file")
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError("-PrivateConfig must be an absolute regular file") from exc
    if not resolved.is_file():
        raise RuntimeError("-PrivateConfig must be an absolute regular file")
    try:
        forbidden_roots = (
            Path(str(config["candidate_root"])).resolve(),
            Path(str(config["evidence_root"])).resolve(),
            (
                Path(str(config["staging_root"])) / "rehearsal-runtime-logs"
            ).resolve(),
        )
    except (KeyError, OSError) as exc:
        raise RuntimeError("runtime config does not define closed private roots") from exc
    if any(resolved == root or resolved.is_relative_to(root) for root in forbidden_roots):
        raise RuntimeError(
            "-PrivateConfig must remain outside candidate, evidence, and log roots"
        )
    return resolved


def _load_private_config(
    path: Path, config: Mapping[str, Any]
) -> PrivateRuntimeConfig:
    resolved = _private_config_path(path, config)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8-sig", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RuntimeError("private runtime config is not valid UTF-8 JSON") from None
    root = _exact_private_object(
        value,
        keys=frozenset({"schema", "agent", "speech"}),
        label="root",
    )
    if root["schema"] != _PRIVATE_CONFIG_SCHEMA:
        raise RuntimeError("private runtime config schema is unsupported")
    agent = _exact_private_object(
        root["agent"],
        keys=frozenset({"provider", "api_base", "api_key", "model"}),
        label="agent",
    )
    speech = _exact_private_object(
        root["speech"],
        keys=frozenset(
            {"provider", "api_base", "api_key", "stt_model", "tts_model", "voice"}
        ),
        label="speech",
    )
    private_agent = PrivateAgentConfig(
        provider=_private_string(agent["provider"], field="agent.provider"),
        api_base=_private_string(agent["api_base"], field="agent.api_base"),
        api_key=_private_string(agent["api_key"], field="agent.api_key"),
        model=_private_string(agent["model"], field="agent.model"),
    )
    private_speech = PrivateSpeechConfig(
        provider=_private_string(speech["provider"], field="speech.provider"),
        api_base=_private_string(speech["api_base"], field="speech.api_base"),
        api_key=_private_string(speech["api_key"], field="speech.api_key"),
        stt_model=_private_string(speech["stt_model"], field="speech.stt_model"),
        tts_model=_private_string(speech["tts_model"], field="speech.tts_model"),
        voice=_private_string(speech["voice"], field="speech.voice"),
    )
    runtime_speech = config.get("speech")
    if type(runtime_speech) is not dict or any(
        runtime_speech.get(field) != getattr(private_speech, field)
        for field in ("provider", "api_base", "stt_model", "tts_model", "voice")
    ):
        raise RuntimeError(
            "private speech metadata does not exactly match runtime config"
        )
    return PrivateRuntimeConfig(agent=private_agent, speech=private_speech)


def _run_checked(argv: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {message}")
    return completed.stdout.strip()


def _base_env(config: dict[str, Any]) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in _SAFE_PARENT_ENV_NAMES
    }
    candidate = str(config["candidate_root"])
    env["PYTHONPATH"] = candidate
    env["JIUWENSWARM_DATA_DIR"] = str(config["data_dir"])
    env["AGENT_SERVER_HOST"] = "127.0.0.1"
    env["AGENT_SERVER_PORT"] = str(config["ports"]["agentserver"])
    env["WEB_HOST"] = "127.0.0.1"
    env["WEB_PORT"] = str(config["ports"]["web"])
    env["GATEWAY_PORT"] = str(config["ports"]["gateway"])
    env["JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_ENABLED"] = "true"
    env["JIUWENSWARM_LIVE_VOICE_W2_CANDIDATE_SHA"] = str(config["candidate_sha"])
    env["JIUWENSWARM_LIVE_VOICE_W2_ENVIRONMENT_ID"] = str(config["environment_id"])
    env["JIUWENSWARM_LIVE_VOICE_W2_SESSION_ID"] = str(config["session_id"])
    env["JIUWENSWARM_LIVE_VOICE_W2_MODE_ID"] = str(config["mode_id"])
    env["JIUWENSWARM_LIVE_VOICE_W2_REPOSITORY_PATH"] = candidate
    env["JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_SET_ID"] = str(config["evidence_set_id"])
    return env


def _agent_provider_env(
    private_config: PrivateRuntimeConfig | None,
) -> dict[str, str]:
    if private_config is not None:
        agent = private_config.agent
        return {
            "MODEL_PROVIDER": agent.provider,
            "API_BASE": agent.api_base,
            "API_KEY": agent.api_key,
            "MODEL_NAME": agent.model,
        }
    return {
        name: value
        for name in (*_AGENT_RUNTIME_ENV_NAMES, *_AGENT_PROVIDER_SECRET_ENV_NAMES)
        if (value := os.environ.get(name))
    }


def _assert_shared_dotenv_secret_boundary(data_dir: Path) -> None:
    path = data_dir / "config" / ".env"
    if not path.exists():
        return
    if not path.is_file():
        raise RuntimeError("shared config/.env is not a regular file")
    for line in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        match = re.match(
            r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=",
            line,
        )
        if match is not None:
            name = match.group(1).upper()
            is_speech = name in {
                _SPEECH_API_KEY_ENV,
                _LEGACY_SPEECH_API_KEY_ENV,
            }
            is_agent = name in {
                *_AGENT_RUNTIME_ENV_NAMES,
                *_AGENT_PROVIDER_SECRET_ENV_NAMES,
            }
            if not (is_speech or is_agent or _SECRET_ENV_NAME.search(name)):
                continue
            label = (
                "Speech"
                if is_speech
                else "Agent/provider"
                if is_agent
                else "secret"
            )
            raise RuntimeError(
                f"shared config/.env contains a forbidden {label} credential name"
            )


def _assert_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"required port is already in use: {port}")


def _wait_port(port: int, *, open_state: bool, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            is_open = sock.connect_ex(("127.0.0.1", port)) == 0
        if is_open is open_state:
            return
        time.sleep(0.2)
    state = "open" if open_state else "closed"
    raise RuntimeError(f"port {port} did not become {state}")


def _policy_preflight(config: dict[str, Any], env: dict[str, str]) -> None:
    candidate = Path(config["candidate_root"]).resolve()
    python = str(config["python"])
    sha = _run_checked(["git", "rev-parse", "HEAD"], cwd=candidate, env=env)
    if sha != config["candidate_sha"]:
        raise RuntimeError("candidate HEAD mismatch")
    if _run_checked(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=candidate,
        env=env,
    ):
        raise RuntimeError("candidate checkout is dirty")
    _assert_shared_dotenv_secret_boundary(Path(config["data_dir"]))
    imported = _run_checked(
        [
            python,
            "-c",
            "from pathlib import Path; import jiuwenswarm.server.live_voice.w2_demo_gate as m; print(Path(m.__file__).resolve())",
        ],
        cwd=candidate,
        env=env,
    )
    if candidate not in Path(imported).parents:
        raise RuntimeError("W2 evaluator was not imported from candidate checkout")
    output = _run_checked(
        [
            python,
            "-m",
            "jiuwenswarm.server.live_voice.w2_gate_cli",
            "validate-policy",
            "--trust-policy",
            str(config["trust_policy"]),
            "--trust-policy-signature",
            str(config["trust_policy_signature"]),
            "--root-public-key",
            str(config["root_public_key"]),
            "--expected-root-sha256",
            str(config["expected_root_sha256"]),
        ],
        cwd=candidate,
        env=env,
    )
    result = json.loads(output)
    expected_binding = [
        config["candidate_sha"],
        config["environment_id"],
        config["session_id"],
        config["mode_id"],
    ]
    if (
        result.get("status") != "VALID"
        or result.get("policy_id") != config["policy_id"]
        or result.get("candidate_binding") != expected_binding
        or result.get("evidence_set_id") != config["evidence_set_id"]
        or Path(str(result.get("repository_path"))).resolve() != candidate
    ):
        raise RuntimeError("runtime config does not exactly match signed policy")
    data_dir = Path(config["data_dir"])
    session = data_dir / "agent" / "sessions" / config["session_id"] / "metadata.json"
    if not session.is_file():
        raise RuntimeError("policy-bound rehearsal session is not persisted")
    project = Path(config["project_dir"]).resolve()
    if not project.is_dir():
        raise RuntimeError("bound project is missing")
    if _run_checked(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=project,
        env=env,
    ):
        raise RuntimeError("bound project is dirty")
    if (
        _run_checked(
            ["git", "config", "--local", "core.autocrlf"], cwd=project, env=env
        )
        != "false"
    ):
        raise RuntimeError("bound project core.autocrlf must be false")


def _slots(config: dict[str, Any]) -> list[Slot]:
    slots = [Slot(**raw) for raw in config["runtime_slots"]]
    if [slot.sequence for slot in slots] != list(range(1, 8)):
        raise RuntimeError("runtime slot sequences are not exactly 1..7")
    policy = json.loads(Path(config["trust_policy"]).read_text(encoding="utf-8"))
    expected = [
        (
            raw["artifact_id"],
            raw["artifact_sequence"],
            raw["producer_id"],
            raw["process_epoch"],
            raw["predecessor_artifact_id"],
            raw["showcase_run"],
        )
        for raw in policy["runtime_slots"]
    ]
    actual = [
        (
            slot.artifact_id,
            slot.sequence,
            slot.producer,
            slot.epoch,
            slot.predecessor,
            slot.showcase_run,
        )
        for slot in slots
    ]
    if actual != expected:
        raise RuntimeError("runtime config does not exactly match signed policy")
    return slots


def _artifact_paths(config: dict[str, Any], slot: Slot) -> tuple[Path, Path]:
    root = Path(config["evidence_root"])
    return root / f"{slot.artifact_id}.jsonl", root / f"{slot.artifact_id}.signature"


def _slot_env(
    config: dict[str, Any],
    slot: Slot,
    *,
    p3_token: str,
    speech_key: str,
    agent_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = _base_env(config)
    for name in (
        P1_RETRIABLE_FAULT_REQUEST_ID_ENV,
        P1_RETRIABLE_FAULT_OPERATION_ENV,
        P2_RETRIABLE_FAULT_REQUEST_ID_ENV,
        P2_RETRIABLE_FAULT_OPERATION_ENV,
        P2_STALE_FAULT_REQUEST_ID_ENV,
        P2_STALE_FAULT_OPERATION_ENV,
        P3_STALE_FAULT_REQUEST_ID_ENV,
        P3_STALE_FAULT_OPERATION_ENV,
    ):
        env.pop(name, None)
    content, signature = _artifact_paths(config, slot)
    if content.exists() or signature.exists():
        raise RuntimeError(f"slot output already exists: {slot.artifact_id}")
    key_root = Path(config["leaf_key_root"])
    env["JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"] = p3_token
    env["JIUWENSWARM_LIVE_VOICE_W2_ARTIFACT_SEQUENCE"] = str(slot.sequence)
    if slot.predecessor is None:
        env.pop("JIUWENSWARM_LIVE_VOICE_W2_PREDECESSOR_ARTIFACT_ID", None)
        env.pop("JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_PREDECESSOR_ARTIFACT_ID", None)
    if slot.producer == "agentserver":
        pair = 3 if slot.showcase_run is None else slot.showcase_run
        fault_plan = config["product_fault_plan"]
        env.update(
            _agent_provider_env(None) if agent_env is None else dict(agent_env)
        )
        env.update(
            {
                "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_P3_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID": str(config["principal_id"]),
                "JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS": str(config["project_id"]),
                "JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT": (
                    datetime.now(timezone.utc) + timedelta(hours=8)
                ).isoformat(),
                "JIUWENSWARM_LIVE_VOICE_P3_DATABASE": str(
                    config["p3_databases"][str(pair)]
                ),
                "JIUWENSWARM_LIVE_VOICE_P3_RECONCILE_SECONDS": "1",
                "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_PATH": str(content),
                "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_PRIVATE_KEY_PATH": str(
                    key_root / "runtime-agentserver.private"
                ),
                "JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_SIGNATURE_PATH": str(signature),
                "JIUWENSWARM_LIVE_VOICE_W2_ARTIFACT_ID": slot.artifact_id,
                "JIUWENSWARM_LIVE_VOICE_W2_PROCESS_EPOCH": slot.epoch,
            }
        )
        if pair == 1 and slot.showcase_run == 1:
            fault = require_product_fault(
                fault_plan,
                pair=1,
                plane=W2FaultPlane.P2_CONVERSATION,
                fault_class=W2FaultClass.RETRIABLE,
            )
            env.update(
                {
                    P2_RETRIABLE_FAULT_REQUEST_ID_ENV: str(fault["request_id"]),
                    P2_RETRIABLE_FAULT_OPERATION_ENV: str(fault["operation"]),
                }
            )
        if pair == 3 and slot.showcase_run == 3:
            p2_fault = require_product_fault(
                fault_plan,
                pair=3,
                plane=W2FaultPlane.P2_CONVERSATION,
                fault_class=W2FaultClass.ZERO_EFFECT,
            )
            p3_fault = require_product_fault(
                fault_plan,
                pair=3,
                plane=W2FaultPlane.P3_TASK,
                fault_class=W2FaultClass.ZERO_EFFECT,
            )
            env.update(
                {
                    P2_STALE_FAULT_REQUEST_ID_ENV: str(p2_fault["request_id"]),
                    P2_STALE_FAULT_OPERATION_ENV: str(p2_fault["operation"]),
                    P3_STALE_FAULT_REQUEST_ID_ENV: str(p3_fault["request_id"]),
                    P3_STALE_FAULT_OPERATION_ENV: str(p3_fault["operation"]),
                }
            )
        if slot.predecessor is not None:
            env["JIUWENSWARM_LIVE_VOICE_W2_PREDECESSOR_ARTIFACT_ID"] = slot.predecessor
    else:
        speech = config["speech"]
        env.update(
            {
                "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED": "true",
                "LIVE_VOICE_SPEECH_PROVIDER": str(speech["provider"]),
                "LIVE_VOICE_SPEECH_API_BASE": str(speech["api_base"]),
                _SPEECH_API_KEY_ENV: speech_key,
                "LIVE_VOICE_SPEECH_STT_MODEL": str(speech["stt_model"]),
                "LIVE_VOICE_SPEECH_TTS_MODEL": str(speech["tts_model"]),
                "LIVE_VOICE_SPEECH_TTS_VOICE": str(speech["voice"]),
                "JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED": "true",
                "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_EVIDENCE_PATH": str(content),
                "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_EVIDENCE_PRIVATE_KEY_PATH": str(
                    key_root / "runtime-gateway.private"
                ),
                "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_EVIDENCE_SIGNATURE_PATH": str(
                    signature
                ),
                "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_ARTIFACT_ID": slot.artifact_id,
                "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_ARTIFACT_SEQUENCE": str(
                    slot.sequence
                ),
                "JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_PROCESS_EPOCH": slot.epoch,
            }
        )
        if slot.showcase_run == 1:
            fault = require_product_fault(
                config["product_fault_plan"],
                pair=1,
                plane=W2FaultPlane.P1_SPEECH_MEDIA,
                fault_class=W2FaultClass.RETRIABLE,
            )
            env.update(
                {
                    P1_RETRIABLE_FAULT_REQUEST_ID_ENV: str(fault["request_id"]),
                    P1_RETRIABLE_FAULT_OPERATION_ENV: str(fault["operation"]),
                }
            )
        if slot.predecessor is not None:
            env["JIUWENSWARM_LIVE_VOICE_W2_GATEWAY_PREDECESSOR_ARTIFACT_ID"] = (
                slot.predecessor
            )
    return env


class Controller:
    def __init__(
        self,
        config: dict[str, Any],
        slots: list[Slot],
        speech_key: str,
        agent_env: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self.slots = slots
        self.speech_key = speech_key
        self.agent_env = dict(
            _agent_provider_env(None) if agent_env is None else agent_env
        )
        self.p3_token = secrets.token_urlsafe(32)
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self.log_handles: dict[str, Any] = {}
        self.log_paths: dict[str, Path] = {}
        self.fault_passed_pairs: set[int] = set()

    def _start(
        self,
        name: str,
        argv: list[str],
        env: dict[str, str],
        *,
        cwd: Path | None = None,
    ) -> None:
        if name in self.processes:
            raise RuntimeError(f"process is already running: {name}")
        log_dir = Path(self.config["staging_root"]) / "rehearsal-runtime-logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"{name}.log"
        if log_path.exists():
            raise RuntimeError(f"log path already exists: {log_path}")
        handle = log_path.open("xb")
        process = subprocess.Popen(
            argv,
            cwd=str(cwd or Path(self.config["candidate_root"])),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NEW_PROCESS_GROUP,
        )
        self.processes[name] = process
        self.log_handles[name] = handle
        self.log_paths[name] = log_path
        print(f"STARTED {name} pid={process.pid} log={log_path}")

    def start_ui(self) -> None:
        _assert_port_free(self.config["ports"]["vite"])
        env = _base_env(self.config)
        env["VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB"] = "true"
        env["VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1"] = "true"
        env["VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION"] = "true"
        env.pop("VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH", None)
        env.pop("VITE_FEATURE_LIVE_VOICE_TASK_DEMO", None)
        frontend = Path(self.config["frontend_root"])
        vite_entrypoint = frontend / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite_entrypoint.is_file():
            dependency_frontend = (
                Path(self.config["python"]).resolve().parents[2]
                / "jiuwenswarm"
                / "channels"
                / "web"
                / "frontend"
            )
            vite_entrypoint = (
                dependency_frontend / "node_modules" / "vite" / "bin" / "vite.js"
            )
        if not vite_entrypoint.is_file():
            raise RuntimeError("Vite dependency entrypoint is unavailable")
        self._start(
            "vite",
            [
                str(self.config["node"]),
                str(vite_entrypoint),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.config["ports"]["vite"]),
                "--strictPort",
            ],
            env,
            cwd=frontend,
        )
        _wait_port(self.config["ports"]["vite"], open_state=True)
        print("UI_READY=http://127.0.0.1:5173")

    def stop_ui(self) -> None:
        if any(
            name.startswith("fault-runner-") and process.poll() is None
            for name, process in self.processes.items()
        ):
            raise RuntimeError(
                "a product fault runner is still running; close the stock UI routes "
                "and wait for its PASS marker before stopping UI"
            )
        self._signal_and_wait("vite", timeout=45.0)
        _wait_port(self.config["ports"]["vite"], open_state=False)

    def _signal_and_wait(self, name: str, timeout: float = 120.0) -> None:
        process = self.processes[name]
        handle = self.log_handles[name]
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{name} did not stop gracefully; do not hard-kill or reuse this attempt"
            ) from exc
        self.processes.pop(name)
        self.log_handles.pop(name)
        self.log_paths.pop(name, None)
        handle.close()
        if return_code not in (0, 130, 3221225786, -1073741510):
            raise RuntimeError(f"{name} exited unexpectedly: {return_code}")
        print(f"STOPPED {name} rc={return_code}")

    def _verify_sealed(self, slot: Slot) -> None:
        content, signature = _artifact_paths(self.config, slot)
        if not content.is_file() or not signature.is_file():
            raise RuntimeError(
                f"slot did not produce content and signature: {slot.artifact_id}"
            )
        lines = content.read_text(encoding="utf-8").splitlines()
        if len(lines) < 3:
            raise RuntimeError(f"slot JSONL is incomplete: {slot.artifact_id}")
        footer = json.loads(lines[-1])
        if footer.get("record_kind") != "footer" or footer.get("closed") is not True:
            raise RuntimeError(f"slot footer is not closed: {slot.artifact_id}")
        for key in ("rejected_invalid", "rejected_capacity", "failed_writes"):
            if footer.get(key) != 0:
                raise RuntimeError(f"slot footer reports {key}: {slot.artifact_id}")
        print(
            f"SEALED {slot.artifact_id} sha256={hashlib.sha256(content.read_bytes()).hexdigest()}"
        )

    def start_pair(self, pair: int) -> None:
        if pair not in (1, 2, 3):
            raise RuntimeError("pair must be 1, 2, or 3")
        for port in (
            self.config["ports"]["agentserver"],
            self.config["ports"]["web"],
            self.config["ports"]["gateway"],
        ):
            _assert_port_free(port)
        as_slot = next(
            s
            for s in self.slots
            if s.producer == "agentserver" and s.showcase_run == pair
        )
        gw_slot = next(
            s for s in self.slots if s.producer == "gateway" and s.showcase_run == pair
        )
        python = str(self.config["python"])
        runner = str(Path(__file__).with_name("w2_graceful_service_runner.py"))
        self._start(
            f"agentserver-{pair}",
            [
                python,
                runner,
                "agentserver",
                "--port",
                str(self.config["ports"]["agentserver"]),
            ],
            _slot_env(
                self.config,
                as_slot,
                p3_token=self.p3_token,
                speech_key=self.speech_key,
                agent_env=self.agent_env,
            ),
        )
        _wait_port(self.config["ports"]["agentserver"], open_state=True)
        self._start(
            f"gateway-{pair}",
            [
                python,
                runner,
                "gateway",
                "--agent-server-url",
                f"ws://127.0.0.1:{self.config['ports']['agentserver']}",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.config["ports"]["web"]),
            ],
            _slot_env(
                self.config,
                gw_slot,
                p3_token=self.p3_token,
                speech_key=self.speech_key,
                agent_env=self.agent_env,
            ),
        )
        _wait_port(self.config["ports"]["web"], open_state=True)
        _wait_port(self.config["ports"]["gateway"], open_state=True)
        print(f"PAIR_READY={pair}")

    def _require_live_process(self, name: str) -> None:
        process = self.processes.get(name)
        if process is None or process.poll() is not None:
            raise RuntimeError(f"required runtime process is not live: {name}")

    def start_fault_runner(self, pair: int) -> None:
        if pair not in (1, 2, 3):
            raise RuntimeError("pair must be 1, 2, or 3")
        if pair in self.fault_passed_pairs:
            raise RuntimeError(f"product fault runner already passed for pair {pair}")
        for name in ("vite", f"agentserver-{pair}", f"gateway-{pair}"):
            self._require_live_process(name)
        name = f"fault-runner-{pair}"
        if name in self.processes:
            raise RuntimeError(f"process is already running: {name}")
        _wait_port(self.config["ports"]["chrome_debug"], open_state=True)
        runner = Path(__file__).with_name("w2_fault_runner.py")
        if not runner.is_file():
            raise RuntimeError("candidate-bound W2 product fault runner is unavailable")
        env = _base_env(self.config)
        env["JIUWENSWARM_LIVE_VOICE_W2_EVIDENCE_ENABLED"] = "false"
        self._start(
            name,
            [
                str(self.config["python"]),
                str(runner),
                "--policy-id",
                str(self.config["policy_id"]),
                "--candidate-sha",
                str(self.config["candidate_sha"]),
                "--evidence-set-id",
                str(self.config["evidence_set_id"]),
                "--pair",
                str(pair),
                "--gateway-url",
                f"ws://127.0.0.1:{self.config['ports']['web']}/ws",
                "--origin",
                f"http://127.0.0.1:{self.config['ports']['vite']}",
                "--cdp-url",
                f"http://127.0.0.1:{self.config['ports']['chrome_debug']}",
                "--timeout",
                str(_FAULT_RUNNER_TIMEOUT_SECONDS),
            ],
            env,
        )
        print(f"FAULT_RUNNER_STARTED={pair}")

    def wait_fault_runner(self, pair: int) -> None:
        if pair not in (1, 2, 3):
            raise RuntimeError("pair must be 1, 2, or 3")
        name = f"fault-runner-{pair}"
        process = self.processes.get(name)
        if process is None:
            if pair in self.fault_passed_pairs:
                print(f"FAULT_RUNNER_ALREADY_PASSED={pair}")
                return
            raise RuntimeError(f"product fault runner was not started for pair {pair}")
        handle = self.log_handles[name]
        log_path = self.log_paths[name]
        try:
            return_code = process.wait(timeout=_FAULT_RUNNER_TIMEOUT_SECONDS + 10)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "product fault runner is still running; complete the stock UI "
                "journey and close its P2/P3 routes before retrying"
            ) from exc
        self.processes.pop(name)
        self.log_handles.pop(name)
        self.log_paths.pop(name)
        handle.close()
        expected = (
            "W2_FAULT_RUNNER_PRODUCT_FAULTS_PASS "
            f"pair={pair} faults=3 routes=closed"
        )
        try:
            lines = [
                line
                for line in log_path.read_text(
                    encoding="utf-8", errors="strict"
                ).splitlines()
                if line
            ]
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("product fault runner log is unreadable") from exc
        if return_code != 0 or not lines or lines[-1] != expected or lines.count(expected) != 1:
            raise RuntimeError(
                f"product fault runner did not pass for pair {pair}; attempt is invalid"
            )
        self.fault_passed_pairs.add(pair)
        print(f"FAULT_RUNNER_VERIFIED={pair}")

    def stop_pair(self, pair: int) -> None:
        runner_name = f"fault-runner-{pair}"
        runner = self.processes.get(runner_name)
        if runner is not None and runner.poll() is None:
            raise RuntimeError(
                "product fault runner is still running; gracefully close the stock "
                "UI P2/P3 routes and wait faults before stopping the pair"
            )
        runner_failure: RuntimeError | None = None
        if runner is not None:
            try:
                self.wait_fault_runner(pair)
            except RuntimeError as exc:
                runner_failure = exc
        self._signal_and_wait(f"gateway-{pair}")
        _wait_port(self.config["ports"]["web"], open_state=False)
        _wait_port(self.config["ports"]["gateway"], open_state=False)
        self._signal_and_wait(f"agentserver-{pair}")
        _wait_port(self.config["ports"]["agentserver"], open_state=False)
        for producer in ("gateway", "agentserver"):
            slot = next(
                s
                for s in self.slots
                if s.producer == producer and s.showcase_run == pair
            )
            self._verify_sealed(slot)
        if runner_failure is not None or pair not in self.fault_passed_pairs:
            raise RuntimeError(
                f"pair {pair} stopped cleanly but its product fault runner did not pass; "
                "attempt is invalid"
            ) from runner_failure

    def start_successor(self) -> None:
        _assert_port_free(self.config["ports"]["agentserver"])
        slot = next(
            s
            for s in self.slots
            if s.producer == "agentserver" and s.showcase_run is None
        )
        self._start(
            "agentserver-4",
            [
                str(self.config["python"]),
                str(Path(__file__).with_name("w2_graceful_service_runner.py")),
                "agentserver",
                "--port",
                str(self.config["ports"]["agentserver"]),
            ],
            _slot_env(
                self.config,
                slot,
                p3_token=self.p3_token,
                speech_key=self.speech_key,
                agent_env=self.agent_env,
            ),
        )
        _wait_port(self.config["ports"]["agentserver"], open_state=True)
        print("SUCCESSOR_READY=4")

    def stop_successor(self) -> None:
        self._signal_and_wait("agentserver-4")
        _wait_port(self.config["ports"]["agentserver"], open_state=False)
        slot = next(
            s
            for s in self.slots
            if s.producer == "agentserver" and s.showcase_run is None
        )
        self._verify_sealed(slot)


def _loop(controller: Controller) -> None:
    print(
        "Commands: start ui, stop ui, start 1|2|3, stop 1|2|3, "
        "start faults 1|2|3, wait faults 1|2|3, start 4, stop 4, status, quit"
    )
    while True:
        command = input("w2-rehearsal> ").strip().lower().split()
        if not command:
            continue
        try:
            if command == ["status"]:
                print(
                    {
                        name: process.poll()
                        for name, process in controller.processes.items()
                    }
                )
            elif command == ["start", "ui"]:
                controller.start_ui()
            elif command == ["stop", "ui"]:
                controller.stop_ui()
            elif (
                len(command) == 2
                and command[0] == "start"
                and command[1] in {"1", "2", "3"}
            ):
                controller.start_pair(int(command[1]))
            elif (
                len(command) == 2
                and command[0] == "stop"
                and command[1] in {"1", "2", "3"}
            ):
                controller.stop_pair(int(command[1]))
            elif (
                len(command) == 3
                and command[:2] == ["start", "faults"]
                and command[2] in {"1", "2", "3"}
            ):
                controller.start_fault_runner(int(command[2]))
            elif (
                len(command) == 3
                and command[:2] == ["wait", "faults"]
                and command[2] in {"1", "2", "3"}
            ):
                controller.wait_fault_runner(int(command[2]))
            elif command == ["start", "4"]:
                controller.start_successor()
            elif command == ["stop", "4"]:
                controller.stop_successor()
            elif command == ["quit"]:
                if controller.processes:
                    raise RuntimeError(
                        "refusing to quit while runtime processes are active"
                    )
                return
            else:
                print("Unknown command")
        except Exception as exc:
            print(f"COMMAND_FAILED={type(exc).__name__}: {exc}")
            print(
                "Controller remains active. Inspect status and stop every live "
                "process before quitting."
            )


def main() -> int:
    args = _parser().parse_args()
    config = _load(args.config.resolve())
    env = _base_env(config)
    slots = _slots(config)
    _policy_preflight(config, env)
    evidence_root = Path(config["evidence_root"])
    if any(evidence_root.iterdir()):
        raise RuntimeError(
            "rehearsal evidence root must be empty before controller start"
        )
    for path in config["p3_databases"].values():
        if Path(path).exists():
            raise RuntimeError(f"rehearsal database already exists: {path}")
    for port in config["ports"].values():
        _assert_port_free(int(port))
    private_config = (
        None
        if args.private_config is None
        else _load_private_config(args.private_config, config)
    )
    print("W2_REHEARSAL_RUNTIME_PREFLIGHT=PASS")
    if args.preflight_only:
        return 0
    if private_config is None:
        speech_key = getpass.getpass(
            "Enter Speech API key (hidden; process memory only): "
        ).strip()
        if not speech_key:
            raise RuntimeError("Speech API key is required")
    else:
        speech_key = private_config.speech.api_key
    agent_env = _agent_provider_env(private_config)
    controller = Controller(config, slots, speech_key, agent_env)
    try:
        _loop(controller)
    finally:
        speech_key = ""
        agent_env.clear()
        controller.speech_key = ""
        controller.agent_env.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
