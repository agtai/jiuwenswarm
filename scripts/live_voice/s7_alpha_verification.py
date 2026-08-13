# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from ipaddress import ip_address
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import unquote, urlparse


REPORT_SCHEMA_VERSION = "live-voice.s7-automation-report.v1"
REAL_CONFIG_SCHEMA_VERSION = "live-voice.s7-real-checks.v1"
CANDIDATE_RUNTIME_SCHEMA_VERSION = "live-voice.s7-candidate-runtime.v1"
S7_COMPARISON_BASE = "2a69c2b87d0ee080a4a30421cbcbcdf93183f340"
REQUIRED_REAL_CHECKS = frozenset(
    {
        "speech-media",
        "agent-executor",
        "benchmark-fault",
        "secure-deployment",
        "privacy",
    }
)
CANONICAL_REAL_PROBES: Mapping[str, tuple[str, frozenset[str]]] = {
    "speech-media": (
        "scripts/live_voice/s7_probe_speech_media.py",
        frozenset({"S7_SPEECH_MEDIA_OBSERVATION"}),
    ),
    "agent-executor": (
        "scripts/live_voice/s7_probe_agent_executor.py",
        frozenset(
            {
                "S7_AGENT_EXECUTOR_OBSERVATION",
                "S7_EXECUTOR_COMPLETION_FIXTURE_ROOT",
                "S7_EXECUTOR_CANCELLATION_FIXTURE_ROOT",
            }
        ),
    ),
    "benchmark-fault": (
        "scripts/live_voice/s7_probe_benchmark_fault.py",
        frozenset({"S7_BENCHMARK_FAULT_OBSERVATION"}),
    ),
    "secure-deployment": (
        "scripts/live_voice/s7_probe_secure_deployment.py",
        frozenset({"S7_PRIVATE_ORIGIN"}),
    ),
    "privacy": (
        "scripts/live_voice/s7_probe_privacy.py",
        frozenset(
            {
                "S7_PRIVACY_SURFACE_MANIFEST",
                "S7_PRIVACY_CAPTURE_ROOT",
                "LIVE_VOICE_SPEECH_API_KEY",
                "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN",
            }
        ),
    ),
}
REAL_LATENCY_CHECKS = frozenset({"speech-media", "benchmark-fault"})
REQUIRED_FEATURE_FLAGS = frozenset(
    {
        "JIUWENSWARM_LIVE_VOICE_CRITICAL_INPUT_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_P3_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED",
        "JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED",
        "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED",
        "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED",
        "VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1",
        "VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB",
        "VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION",
        "VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH",
        "VITE_FEATURE_LIVE_VOICE_TASK_DEMO",
    }
)
CANDIDATE_FEATURE_FLAG_VALUES = {
    name: (
        "unset"
        if name
        in {
            "VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH",
            "VITE_FEATURE_LIVE_VOICE_TASK_DEMO",
        }
        else "true"
    )
    for name in REQUIRED_FEATURE_FLAGS
}
REQUIRED_RUNTIME_LABELS = frozenset(
    {
        "agent_provider",
        "browser",
        "operating_system",
        "origin",
        "input_device",
        "output_device",
        "network_profile",
        "speech_provider",
        "speech_api_origin",
        "speech_fallback",
        "stt_model",
        "tts_model",
        "tts_voice",
        "executor",
        "project_fixture",
        "data_fixture",
        "deployment_topology",
    }
)
_PROCESS_ENV_ALLOWLIST = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    }
)
_AUTOMATION_ENV_ALLOWLIST = (
    _PROCESS_ENV_ALLOWLIST
    | REQUIRED_FEATURE_FLAGS
    | frozenset({"CI", "NO_COLOR", "PYTHONHASHSEED", "PYTHONWARNINGS", "TERM", "TZ"})
)
DEPENDENCY_INPUTS = (
    "pyproject.toml",
    "uv.lock",
    "jiuwenswarm/channels/web/frontend/package.json",
    "jiuwenswarm/channels/web/frontend/package-lock.json",
)
GENERATED_ARTIFACT_PATHS = (
    "jiuwenswarm/channels/web/frontend/dist",
    "jiuwenswarm/channels/web/frontend/node_modules/.cache",
)
BACKEND_ALPHA_PATHS = (
    "tests/unit_tests/live_voice",
    "tests/integration/live_voice",
)
BACKEND_REGRESSION_PATHS = (
    "tests/unit_tests/agentserver/test_formal_live_voice_adapter.py",
    "tests/unit_tests/agentserver/test_live_voice_p3_agent_profile.py",
    "tests/unit_tests/agentserver/test_live_voice_p3_route.py",
    "tests/unit_tests/channel/test_live_voice_deployment_observer.py",
    "tests/unit_tests/channel/test_live_voice_deployment_preflight.py",
    "tests/unit_tests/channel/test_web_channel_ws_sessions.py",
    "tests/unit_tests/gateway/test_app_gateway_acp.py",
    "tests/unit_tests/gateway/test_browser_gateway_media_transport.py",
    "tests/unit_tests/gateway/test_dedicated_live_voice_media_route.py",
    "tests/unit_tests/gateway/test_dedicated_media_registration.py",
    "tests/unit_tests/gateway/test_live_voice_speech_rpc.py",
    "tests/unit_tests/gateway/test_product_streaming_synthesis.py",
    "tests/unit_tests/gateway/test_streaming_speech_route.py",
    "tests/unit_tests/gateway/test_streaming_synthesis_route.py",
    "tests/unit_tests/auto_harness/test_schedule_task_service.py",
    "tests/unit_tests/common/test_live_voice_contract.py",
    "tests/unit_tests/common/test_live_voice_contract_v2.py",
    "tests/unit_tests/test_app_web_handlers.py",
    "tests/unit_tests/test_app_web_live_voice_privacy.py",
    "tests/unit_tests/test_app_web_raw_file.py",
)
REQUIRED_FRONTEND_COMPAT_SCRIPTS = {
    "test:speech-recognition-lifecycle": "speechRecognitionLifecycle.test.mjs",
    "test:tts-output-ownership": "ttsOutputOwnership.test.mjs",
    "test:chat-store-streaming": "chatStoreStreaming.test.mjs",
}
LATEST_S6_SOURCE_INVENTORY = (
    "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts",
    "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts",
    "jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts",
    "jiuwenswarm/gateway/live_voice/dedicated_media_registration.py",
    "jiuwenswarm/gateway/live_voice/streaming_speech_route.py",
    "jiuwenswarm/server/live_voice/streaming_speech.py",
)
LATEST_S6_REGRESSION_INVENTORY = (
    "jiuwenswarm/channels/web/frontend/tests/liveVoiceBrowserAudioIOAdapter.test.mjs",
    "jiuwenswarm/channels/web/frontend/tests/productP1VoiceRoute.test.mjs",
    "tests/unit_tests/gateway/test_streaming_speech_route.py",
    "tests/unit_tests/live_voice/test_openai_streaming_speech.py",
    "tests/unit_tests/live_voice/test_streaming_speech.py",
)
EXPECTED_S6_RUFF_DIAGNOSTICS = frozenset(
    {
        (
            "jiuwenswarm/channels/web/app_web.py",
            "E402",
            34,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/channels/web/app_web.py",
            "E402",
            35,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/channels/web/app_web.py",
            "E402",
            36,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/channels/web/app_web.py",
            "E402",
            37,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/channels/web/app_web.py",
            "E402",
            38,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/channels/web/app_web.py",
            "E402",
            41,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/channels/web/app_web.py",
            "F541",
            996,
            39,
            "f-string without any placeholders",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            39,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            40,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            45,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            46,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            47,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            48,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            49,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            50,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            58,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "E402",
            59,
            1,
            "Module level import not at top of file",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "F841",
            367,
            5,
            "Local variable `host` is assigned to but never used",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "F821",
            974,
            51,
            "Undefined name `RoutingTarget`",
        ),
        (
            "jiuwenswarm/gateway/app_gateway.py",
            "F841",
            1296,
            37,
            "Local variable `e` is assigned to but never used",
        ),
        (
            "jiuwenswarm/server/agent_ws_server.py",
            "E402",
            251,
            1,
            "Module level import not at top of file",
        ),
    }
)
S7_OWNED_PYTHON_PATHS = (
    "scripts/live_voice/s7_alpha_verification.py",
    "scripts/live_voice/s7_probe_agent_executor.py",
    "scripts/live_voice/s7_probe_benchmark_fault.py",
    "scripts/live_voice/s7_probe_privacy.py",
    "scripts/live_voice/s7_probe_secure_deployment.py",
    "scripts/live_voice/s7_probe_speech_media.py",
    "scripts/live_voice/s7_real_probe_support.py",
    "tests/unit_tests/live_voice/test_s7_alpha_verification.py",
    "tests/unit_tests/live_voice/test_s7_real_probes.py",
)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ENV_TOKEN = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
_CREDENTIAL_ARGUMENT = re.compile(
    r"(?:(?:api[-_]?key|token|secret|password)\s*=|"
    r"(?:^|[-_])(?:api[-_]?key|token|secret|password)$)",
    re.IGNORECASE,
)
_BEARER_OR_JWT = re.compile(
    r"(?:\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{4,}\."
    r"[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}(?![A-Za-z0-9_-]))",
    re.IGNORECASE,
)
_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_SECRET_VALUE = re.compile(
    r"(?:(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
    re.IGNORECASE,
)
_MACHINE_PRIVATE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/(?:home|Users)/[^/\s]+/)",
    re.IGNORECASE,
)
_ABSOLUTE_PATH_REFERENCE = re.compile(r"(?:^|[\s\[\(\{\"'=])(?:[A-Za-z]:[\\/]|/(?!/))")
_RUNTIME_LABEL_FORMATS = {
    "browser": re.compile(r"Chrome-\d+\.\d+\.\d+\.\d+"),
    "operating_system": re.compile(r"Windows-(?:10|11)-build-\d+(?:\.\d+)+"),
    "input_device": re.compile(r"(?:system_default|device_ref:sha256-[0-9a-f]{16,64})"),
    "output_device": re.compile(
        r"(?:system_default|device_ref:sha256-[0-9a-f]{16,64})"
    ),
    "network_profile": re.compile(r"network_ref:sha256-[0-9a-f]{16,64}"),
    "project_fixture": re.compile(
        r"disposable_git_ref:sha256-[0-9a-f]{16,64}:no_remote"
    ),
    "data_fixture": re.compile(r"data_ref:sha256-[0-9a-f]{16,64}"),
    "origin": re.compile(r"private_origin_ref:sha256-[0-9a-f]{64}"),
}
_PRIVATE_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_RAW_MEDIA_SUFFIXES = frozenset(
    {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".pcm", ".wav", ".webm"}
)
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256_REF = re.compile(r"^sha256:[0-9a-f]{64}$")


class VerificationError(RuntimeError):
    """Raised when the candidate or verification configuration is unsafe."""


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    VERIFY = "VERIFY"


@dataclass(frozen=True)
class CandidateIdentity:
    head: str
    branch: str
    comparison_base: str
    upstream: str | None
    upstream_head: str | None
    ahead: int | None
    behind: int | None
    clean: bool
    dependency_sha256: dict[str, str]
    generated_artifact_state: dict[str, str]
    python: str
    node: str | None
    npm: str | None
    uv: str | None
    platform: str


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    category: str
    argv: tuple[str, ...]
    cwd: str = "."
    required_env: tuple[str, ...] = ()
    real_path: bool = False


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    category: str
    status: CheckStatus
    duration_ms: int
    exit_code: int | None = None
    reason: str | None = None
    details: dict[str, int | float | str | bool] = field(default_factory=dict)
    command: tuple[str, ...] = ()
    cwd: str = "."


@dataclass(frozen=True)
class CandidateRuntimeDeclaration:
    candidate_head: str
    comparison_base: str
    feature_flags: dict[str, str]
    runtime_labels: dict[str, str]


@dataclass(frozen=True)
class VerificationReport:
    schema_version: str
    generated_at: str
    not_a_gate: bool
    candidate: CandidateIdentity
    runtime_declaration: CandidateRuntimeDeclaration | None
    automation_status: CheckStatus
    real_path_status: CheckStatus
    s7_readiness: str
    checks: tuple[CheckResult, ...]


def _run_text(
    argv: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> str:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(
            f"command failed ({completed.returncode}): {argv[0]}: {detail}"
        )
    return completed.stdout.strip()


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return _run_text(("git", *args), cwd=repo, check=check)


def resolve_repo(value: str | Path | None = None) -> Path:
    candidate = (
        Path(value) if value is not None else Path(__file__).resolve().parents[2]
    ).resolve()
    top = _git(candidate, "rev-parse", "--show-toplevel")
    repo = Path(top).resolve()
    if repo != candidate:
        raise VerificationError(f"--repo must be the Git root: {repo.name}")
    return repo


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generated_artifact_state(repo: Path) -> dict[str, str]:
    tracked = tuple(
        sorted(
            line
            for line in _git(
                repo, "ls-files", "--", *GENERATED_ARTIFACT_PATHS
            ).splitlines()
            if line
        )
    )
    digest = hashlib.sha256()
    for relative in tracked:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_hash_file(repo / relative)))
    return {
        "policy": "generated-output-excluded-from-candidate",
        "tracked_count": str(len(tracked)),
        "tracked_sha256": digest.hexdigest(),
    }


def require_s7_comparison_base(value: str) -> None:
    if value != S7_COMPARISON_BASE:
        raise VerificationError(
            "S7 comparison base must be the frozen full SHA " + S7_COMPARISON_BASE
        )


def _tool_version(repo: Path, *argv: str) -> str | None:
    try:
        return _run_text(argv, cwd=repo)
    except (FileNotFoundError, VerificationError):
        return None


def collect_candidate_identity(
    repo: Path,
    *,
    comparison_base: str,
    allow_no_upstream: bool = False,
    require_clean: bool = True,
) -> CandidateIdentity:
    head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise VerificationError("detached HEAD cannot be an S7 candidate")

    dirty = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty and require_clean:
        raise VerificationError("candidate worktree is not clean")
    ignored_dotenv = _git(
        repo,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--",
        ".env",
        ":(glob)**/.env",
        ":(glob)**/.env.*",
    )
    unsafe_dotenv = [
        path
        for path in ignored_dotenv.splitlines()
        if path
        and "/node_modules/" not in f"/{Path(path).as_posix()}"
        and not Path(path).as_posix().startswith(".venv/")
    ]
    if unsafe_dotenv:
        raise VerificationError(
            "candidate worktree contains an ignored dotenv file; automatic checks "
            "require a machine-private-config-free source tree"
        )

    base = _git(repo, "rev-parse", "--verify", f"{comparison_base}^{{commit}}")
    ancestor = subprocess.run(
        ("git", "merge-base", "--is-ancestor", base, head),
        cwd=repo,
        check=False,
        shell=False,
    )
    if ancestor.returncode != 0:
        raise VerificationError("comparison base is not an ancestor of HEAD")

    upstream = _git(
        repo,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    if not upstream:
        if not allow_no_upstream:
            raise VerificationError("candidate branch has no configured upstream")
        upstream_head = None
        ahead = None
        behind = None
    else:
        upstream_head = _git(repo, "rev-parse", "@{upstream}")
        counts = _git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        ahead_text, behind_text = counts.split()
        ahead = int(ahead_text)
        behind = int(behind_text)

    hashes: dict[str, str] = {}
    for relative in DEPENDENCY_INPUTS:
        path = repo / relative
        if not path.is_file():
            raise VerificationError(f"missing dependency identity input: {relative}")
        hashes[relative] = _hash_file(path)

    return CandidateIdentity(
        head=head,
        branch=branch,
        comparison_base=base,
        upstream=upstream or None,
        upstream_head=upstream_head,
        ahead=ahead,
        behind=behind,
        clean=not dirty,
        dependency_sha256=hashes,
        generated_artifact_state=_generated_artifact_state(repo),
        python=platform.python_version(),
        node=_tool_version(repo, "node", "--version"),
        npm=_tool_version(repo, "npm.cmd" if os.name == "nt" else "npm", "--version"),
        uv=_tool_version(repo, "uv", "--version"),
        platform=f"{platform.system()}-{platform.release()}",
    )


def require_project_python(repo: Path) -> None:
    relative = Path(
        ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    )
    expected = (repo / relative).resolve()
    if not expected.is_file() or Path(sys.executable).resolve() != expected:
        raise VerificationError(
            "run must use the candidate's locked Python environment; invoke it with "
            "uv run --frozen python"
        )


def _normalized_feature_flag(env: Mapping[str, str], name: str) -> str:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return "unset"
    if raw in {"1", "true", "yes", "on"}:
        return "true"
    if raw in {"0", "false", "no", "off"}:
        return "false"
    raise VerificationError(f"feature flag {name} has a non-boolean value")


def _validate_runtime_label(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or value.strip() != value
        or not value.isprintable()
    ):
        raise VerificationError(f"runtime label {name} is not a sanitized label")
    if (
        _SECRET_VALUE.search(value)
        or _CREDENTIAL_ARGUMENT.search(value)
        or _BEARER_OR_JWT.search(value)
        or _MACHINE_PRIVATE_PATH.search(value)
        or _ABSOLUTE_PATH_REFERENCE.search(value)
        or "password" in value.lower()
        or "secret" in value.lower()
    ):
        raise VerificationError(f"runtime label {name} contains private material")
    return value


def _private_origin_reference(env: Mapping[str, str]) -> str:
    raw = env.get("S7_PRIVATE_ORIGIN")
    if not isinstance(raw, str) or not raw or raw.strip() != raw:
        raise VerificationError(
            "S7_PRIVATE_ORIGIN is required for the candidate record"
        )
    try:
        parsed = urlparse(raw)
        port = parsed.port or 443
    except ValueError as error:
        raise VerificationError("S7_PRIVATE_ORIGIN is not canonical") from error
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or hostname != hostname.lower()
        or not hostname.isascii()
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path
        or port != 443
        or parsed.netloc != hostname
        or hostname == "localhost"
        or hostname.endswith(".localhost")
    ):
        raise VerificationError("S7_PRIVATE_ORIGIN is not a private HTTPS FQDN")
    try:
        ip_address(hostname)
    except ValueError:
        pass
    else:
        raise VerificationError("S7_PRIVATE_ORIGIN must use a private DNS name")
    labels = hostname.split(".")
    if (
        len(hostname) > 253
        or len(labels) < 2
        or any(_PRIVATE_DNS_LABEL.fullmatch(label) is None for label in labels)
        or not any(character.isalpha() for character in labels[-1])
    ):
        raise VerificationError("S7_PRIVATE_ORIGIN is not a private HTTPS FQDN")
    digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
    return f"private_origin_ref:sha256-{digest}"


def load_candidate_runtime(
    path: Path,
    *,
    repo: Path,
    identity: CandidateIdentity,
    env: Mapping[str, str],
) -> CandidateRuntimeDeclaration:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(repo)
    except ValueError:
        pass
    else:
        raise VerificationError(
            "candidate runtime record must be stored outside the source worktree"
        )
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VerificationError("candidate runtime record must be an object")
    unknown = set(payload) - {
        "schema_version",
        "candidate_head",
        "comparison_base",
        "feature_flags",
        "runtime_labels",
    }
    if unknown or payload.get("schema_version") != CANDIDATE_RUNTIME_SCHEMA_VERSION:
        raise VerificationError("unsupported candidate runtime record schema")
    if payload.get("candidate_head") != identity.head:
        raise VerificationError(
            "candidate runtime record HEAD does not match candidate"
        )
    if payload.get("comparison_base") != identity.comparison_base:
        raise VerificationError(
            "candidate runtime record comparison base does not match candidate"
        )
    flags = payload.get("feature_flags")
    labels = payload.get("runtime_labels")
    if not isinstance(flags, dict) or set(flags) != REQUIRED_FEATURE_FLAGS:
        raise VerificationError("candidate runtime record has an incomplete flag set")
    normalized_flags: dict[str, str] = {}
    for name in sorted(REQUIRED_FEATURE_FLAGS):
        value = flags[name]
        if value not in {"true", "false", "unset"}:
            raise VerificationError(f"candidate runtime flag {name} is invalid")
        raw_observed = env.get(name)
        observed = _normalized_feature_flag(env, name)
        if value != observed:
            raise VerificationError(
                f"candidate runtime flag {name} does not match the process environment"
            )
        expected = CANDIDATE_FEATURE_FLAG_VALUES[name]
        if value != expected:
            raise VerificationError(
                f"candidate runtime flag {name} must match the accepted candidate profile"
            )
        if (expected == "true" and raw_observed != "true") or (
            expected == "unset" and name in env
        ):
            raise VerificationError(
                f"candidate runtime flag {name} must use the exact process value"
            )
        normalized_flags[name] = value
    if not isinstance(labels, dict) or set(labels) != REQUIRED_RUNTIME_LABELS:
        raise VerificationError("candidate runtime record has an incomplete label set")
    sanitized_labels = {
        name: _validate_runtime_label(name, labels[name])
        for name in sorted(REQUIRED_RUNTIME_LABELS)
    }
    expected_labels = {
        "agent_provider": "jiuwenswarm",
        "speech_provider": "openai",
        "speech_api_origin": "https://api.openai.com/v1",
        "speech_fallback": "streaming-w2-batch-browser-text",
        "stt_model": "gpt-4o-mini-transcribe-2025-12-15",
        "tts_model": "gpt-4o-mini-tts-2025-12-15",
        "tts_voice": "marin",
        "executor": "DirectProjectCodeExecutorAdapter",
        "deployment_topology": "private-same-origin-https-wss",
    }
    for name, expected in expected_labels.items():
        if sanitized_labels[name] != expected:
            raise VerificationError(f"candidate runtime label {name} violates D-078")
    for name, pattern in _RUNTIME_LABEL_FORMATS.items():
        if pattern.fullmatch(sanitized_labels[name]) is None:
            raise VerificationError(
                f"candidate runtime label {name} is not an exact sanitized reference"
            )
    if sanitized_labels["origin"] != _private_origin_reference(env):
        raise VerificationError(
            "candidate origin reference does not match S7_PRIVATE_ORIGIN"
        )
    return CandidateRuntimeDeclaration(
        candidate_head=identity.head,
        comparison_base=identity.comparison_base,
        feature_flags=normalized_flags,
        runtime_labels=sanitized_labels,
    )


def candidate_runtime_sha256(declaration: CandidateRuntimeDeclaration) -> str:
    """Bind real observations to the exact sanitized S7 runtime declaration."""

    encoded = json.dumps(
        {
            "schema_version": CANDIDATE_RUNTIME_SCHEMA_VERSION,
            **asdict(declaration),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _changed_files(
    repo: Path,
    comparison_base: str,
    *,
    diff_filter: str = "ACMRT",
) -> tuple[str, ...]:
    output = _git(
        repo,
        "diff",
        "--name-only",
        f"--diff-filter={diff_filter}",
        f"{comparison_base}...HEAD",
    )
    return tuple(line for line in output.splitlines() if line)


def _python_files(paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(path for path in paths if path.endswith(".py"))


def verify_changed_python_ruff_baseline(repo: Path, comparison_base: str) -> int:
    """Reject any drift from the exact, pre-existing S6 Ruff diagnostic set."""

    changed_python = _python_files(_changed_files(repo, comparison_base))
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--extend-select",
            "W605",
            "--output-format",
            "json",
            "--exit-zero",
            *changed_python,
        ),
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    if completed.returncode != 0:
        print("S7_RUFF_BASELINE_UNAVAILABLE", flush=True)
        return 1
    try:
        payload = json.loads(completed.stdout)
        if not isinstance(payload, list):
            raise ValueError("Ruff JSON output is not a list")
        observed: set[tuple[str, str, int, int, str]] = set()
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Ruff diagnostic is not an object")
            location = item.get("location")
            if not isinstance(location, dict):
                raise ValueError("Ruff diagnostic location is missing")
            relative = (
                Path(str(item.get("filename"))).resolve().relative_to(repo).as_posix()
            )
            observed.add(
                (
                    relative,
                    str(item.get("code")),
                    int(location["row"]),
                    int(location["column"]),
                    str(item.get("message")),
                )
            )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        print("S7_RUFF_BASELINE_INVALID_OUTPUT", flush=True)
        return 1
    if observed != EXPECTED_S6_RUFF_DIAGNOSTICS:
        print(
            "S7_RUFF_BASELINE_MISMATCH "
            f"expected={len(EXPECTED_S6_RUFF_DIAGNOSTICS)} "
            f"observed={len(observed)}",
            flush=True,
        )
        return 1
    print(
        f"S7_RUFF_BASELINE_MATCH diagnostics={len(observed)}",
        flush=True,
    )
    return 0


def _frontend_scripts(repo: Path) -> tuple[str, ...]:
    package_path = repo / "jiuwenswarm/channels/web/frontend/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        raise VerificationError("frontend package scripts are missing")
    live_voice_names = {
        name
        for name, command in scripts.items()
        if isinstance(name, str)
        and name.startswith("test:live-voice-")
        and isinstance(command, str)
    }
    if not live_voice_names:
        raise VerificationError("no frontend Live Voice test scripts were discovered")
    invalid_compat = {
        name
        for name in REQUIRED_FRONTEND_COMPAT_SCRIPTS
        if not isinstance(scripts.get(name), str)
    }
    if invalid_compat:
        raise VerificationError(
            "frontend Live Voice compatibility scripts are missing: "
            + ", ".join(sorted(invalid_compat))
        )
    for name, expected_test in REQUIRED_FRONTEND_COMPAT_SCRIPTS.items():
        command = scripts[name]
        assert isinstance(command, str)
        referenced = set(re.findall(r"tests/([^\s\"']+\.test\.mjs)", command))
        if referenced != {expected_test}:
            raise VerificationError(
                f"frontend compatibility script {name} must run {expected_test}"
            )
        tracked = _git(
            repo,
            "ls-files",
            "--error-unmatch",
            "--",
            f"jiuwenswarm/channels/web/frontend/tests/{expected_test}",
            check=False,
        )
        if not tracked:
            raise VerificationError(
                f"frontend compatibility test is not tracked: {expected_test}"
            )
    names = sorted(live_voice_names | set(REQUIRED_FRONTEND_COMPAT_SCRIPTS))
    test_prefix = "jiuwenswarm/channels/web/frontend/tests/"
    tracked_output = _git(
        repo,
        "ls-files",
        "--",
        f"{test_prefix}liveVoice*.test.mjs",
    )
    tracked_tests = {
        Path(line).name
        for line in tracked_output.splitlines()
        if line and not line.endswith(".manual.test.mjs")
    }
    referenced_tests: set[str] = set()
    for name in live_voice_names:
        command = scripts[name]
        assert isinstance(command, str)
        referenced_tests.update(
            re.findall(r"tests/(liveVoice[^\s\"']+\.test\.mjs)", command)
        )
    if tracked_tests != referenced_tests:
        raise VerificationError(
            "frontend Live Voice package scripts do not cover the exact tracked "
            "automatic test set"
        )
    package_references = {
        match
        for name in live_voice_names
        for match in re.findall(r"tests/([^\s\"']+\.test\.mjs)", str(scripts[name]))
    }
    if "productP1VoiceRoute.test.mjs" not in package_references:
        raise VerificationError(
            "frontend Live Voice package scripts must cover productP1VoiceRoute.test.mjs"
        )
    return tuple(names)


def build_automation_specs(
    repo: Path,
    *,
    comparison_base: str,
) -> tuple[CheckSpec, ...]:
    missing_latest_s6 = [
        relative
        for relative in (*LATEST_S6_SOURCE_INVENTORY, *LATEST_S6_REGRESSION_INVENTORY)
        if not _git(repo, "ls-files", "--error-unmatch", "--", relative, check=False)
    ]
    if missing_latest_s6:
        raise VerificationError(
            "latest S6 source/regression inventory is incomplete: "
            + ", ".join(missing_latest_s6)
        )
    pytest_prefix = (
        "<python>",
        "-m",
        "pytest",
        "--asyncio-mode=auto",
        "-W",
        "ignore::SyntaxWarning",
        "-q",
    )
    specs: list[CheckSpec] = [
        CheckSpec(
            check_id="python-lock-synchronized",
            category="dependency",
            argv=("uv", "sync", "--frozen", "--check"),
        ),
        CheckSpec(
            check_id="python-environment-consistency",
            category="dependency",
            argv=("uv", "pip", "check"),
        ),
        CheckSpec(
            check_id="backend-alpha-matrix",
            category="backend",
            argv=(*pytest_prefix, *BACKEND_ALPHA_PATHS),
        ),
        CheckSpec(
            check_id="backend-related-regressions",
            category="backend",
            argv=(*pytest_prefix, *BACKEND_REGRESSION_PATHS),
        ),
    ]

    frontend_cwd = "jiuwenswarm/channels/web/frontend"
    npm = "npm.cmd" if os.name == "nt" else "npm"
    specs.append(
        CheckSpec(
            check_id="frontend-frozen-install",
            category="dependency",
            argv=(npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"),
            cwd=frontend_cwd,
        )
    )
    for script in _frontend_scripts(repo):
        specs.append(
            CheckSpec(
                check_id=f"frontend-{script.removeprefix('test:')}",
                category="frontend-test",
                argv=(npm, "run", script),
                cwd=frontend_cwd,
            )
        )
    specs.append(
        CheckSpec(
            check_id="frontend-production-build",
            category="frontend",
            argv=(npm, "run", "build"),
            cwd=frontend_cwd,
        )
    )

    changed_python = _python_files(_changed_files(repo, comparison_base))
    if changed_python:
        specs.extend(
            (
                CheckSpec(
                    check_id="changed-python-ruff",
                    category="static",
                    argv=(
                        "<python>",
                        "scripts/live_voice/s7_alpha_verification.py",
                        "ruff-baseline",
                        "--comparison-base",
                        comparison_base,
                    ),
                ),
                CheckSpec(
                    check_id="changed-python-compileall",
                    category="static",
                    argv=("<python>", "-m", "compileall", "-q", *changed_python),
                ),
            )
        )
    if changed_python:
        specs.append(
            CheckSpec(
                check_id="s7-owned-python-format",
                category="static",
                argv=(
                    "<python>",
                    "-m",
                    "ruff",
                    "format",
                    "--check",
                    *S7_OWNED_PYTHON_PATHS,
                ),
            )
        )
    specs.append(
        CheckSpec(
            check_id="git-diff-check",
            category="source",
            argv=("git", "diff", "--check", f"{comparison_base}...HEAD"),
        )
    )
    return tuple(specs)


def inspect_markdown_links(repo: Path) -> CheckResult:
    started = time.monotonic()
    checked = 0
    broken: list[str] = []
    root = repo / "live-voice"
    for markdown in sorted(root.rglob("*.md")):
        content = markdown.read_text(encoding="utf-8")
        for match in _MARKDOWN_LINK.finditer(content):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            target = target.split("#", 1)[0]
            if not target or re.match(r"^(?:https?://|mailto:|data:)", target):
                continue
            checked += 1
            resolved = (markdown.parent / unquote(target)).resolve()
            if not resolved.exists():
                broken.append(f"{markdown.relative_to(repo).as_posix()} -> {target}")
    duration = int((time.monotonic() - started) * 1000)
    return CheckResult(
        check_id="live-voice-markdown-links",
        category="documentation",
        status=CheckStatus.PASS if not broken else CheckStatus.FAIL,
        duration_ms=duration,
        reason=None if not broken else f"{len(broken)} local links do not resolve",
        details={"checked": checked, "broken": len(broken)},
        command=("internal:markdown-links",),
    )


def inspect_source_hygiene(repo: Path, comparison_base: str) -> CheckResult:
    started = time.monotonic()
    diff = _git(repo, "diff", "--unified=0", f"{comparison_base}...HEAD")
    suspect_lines = 0
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if _SECRET_VALUE.search(line) or _MACHINE_PRIVATE_PATH.search(line):
            suspect_lines += 1

    changed_files = _changed_files(repo, comparison_base)
    raw_media = sum(
        1 for path in changed_files if Path(path).suffix.lower() in _RAW_MEDIA_SUFFIXES
    )
    duration = int((time.monotonic() - started) * 1000)
    failed = suspect_lines > 0 or raw_media > 0
    return CheckResult(
        check_id="candidate-source-hygiene",
        category="privacy",
        status=CheckStatus.FAIL if failed else CheckStatus.PASS,
        duration_ms=duration,
        reason=(
            "candidate diff contains a secret-shaped value, machine-private path, or raw media"
            if failed
            else None
        ),
        details={"suspect_added_lines": suspect_lines, "raw_media_files": raw_media},
        command=("internal:source-hygiene", comparison_base, "HEAD"),
    )


def inspect_candidate_after_run(
    repo: Path,
    expected: CandidateIdentity,
) -> CheckResult:
    started = time.monotonic()
    try:
        observed = collect_candidate_identity(
            repo,
            comparison_base=expected.comparison_base,
            allow_no_upstream=expected.upstream is None,
        )
    except VerificationError as error:
        return CheckResult(
            check_id="candidate-identity-after-run",
            category="source",
            status=CheckStatus.FAIL,
            duration_ms=int((time.monotonic() - started) * 1000),
            reason=f"candidate identity changed during verification: {error}",
            command=("internal:candidate-identity-after-run",),
        )
    unchanged = observed == expected
    return CheckResult(
        check_id="candidate-identity-after-run",
        category="source",
        status=CheckStatus.PASS if unchanged else CheckStatus.FAIL,
        duration_ms=int((time.monotonic() - started) * 1000),
        reason=None if unchanged else "candidate identity changed during verification",
        details={
            "head_unchanged": observed.head == expected.head,
            "upstream_unchanged": observed.upstream_head == expected.upstream_head,
            "dependencies_unchanged": (
                observed.dependency_sha256 == expected.dependency_sha256
            ),
            "clean": observed.clean,
        },
        command=("internal:candidate-identity-after-run",),
    )


def _validate_real_token(token: str, required_env: frozenset[str]) -> None:
    placeholder = _ENV_TOKEN.fullmatch(token)
    if placeholder:
        raise VerificationError(
            "real-check argv cannot interpolate environment values; "
            "the candidate-owned probe must read required_env directly"
        )
    if _SECRET_VALUE.search(token):
        raise VerificationError("real-check argv contains a secret-shaped value")
    if _CREDENTIAL_ARGUMENT.search(token):
        raise VerificationError("real-check argv embeds a credential-like value")
    if _BEARER_OR_JWT.search(token):
        raise VerificationError("real-check argv embeds credential material")
    if _MACHINE_PRIVATE_PATH.search(token):
        raise VerificationError("real-check argv contains a machine-private path")
    if _ABSOLUTE_PATH_REFERENCE.search(token):
        raise VerificationError("real-check argv contains an absolute path")


def load_real_check_specs(path: Path, repo: Path) -> tuple[CheckSpec, ...]:
    resolved_config = path.resolve(strict=True)
    try:
        resolved_config.relative_to(repo)
    except ValueError:
        pass
    else:
        raise VerificationError(
            "real-check configuration must be stored outside the source worktree"
        )
    payload = json.loads(resolved_config.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != REAL_CONFIG_SCHEMA_VERSION
    ):
        raise VerificationError("unsupported S7 real-check configuration schema")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise VerificationError("real-check configuration must contain a checks list")

    specs: list[CheckSpec] = []
    seen: set[str] = set()
    for raw in checks:
        if not isinstance(raw, dict):
            raise VerificationError("each real check must be an object")
        unknown_fields = set(raw) - {"id", "argv", "cwd", "required_env"}
        if unknown_fields:
            raise VerificationError(
                "real check contains unsupported fields: "
                + ", ".join(sorted(unknown_fields))
            )
        check_id = raw.get("id")
        argv = raw.get("argv")
        cwd = raw.get("cwd", ".")
        required = raw.get("required_env", [])
        if check_id not in REQUIRED_REAL_CHECKS or check_id in seen:
            raise VerificationError("invalid or duplicate real check id")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(token, str) and token for token in argv)
        ):
            raise VerificationError(
                f"real check {check_id} requires a non-empty argv list"
            )
        if not isinstance(cwd, str) or not cwd:
            raise VerificationError(f"real check {check_id} has an invalid cwd")
        if not isinstance(required, list) or not all(
            isinstance(name, str) and _ENV_NAME.fullmatch(name) for name in required
        ):
            raise VerificationError(f"real check {check_id} has invalid required_env")
        required_names = frozenset(required)
        if len(required_names) != len(required):
            raise VerificationError(
                f"real check {check_id} repeats an environment name"
            )
        for token in argv:
            _validate_real_token(token, required_names)
        cwd_path = Path(cwd)
        if cwd_path.is_absolute():
            raise VerificationError(
                f"real check {check_id} cwd must be repository-relative"
            )
        resolved_cwd = (repo / cwd_path).resolve()
        try:
            resolved_cwd.relative_to(repo)
        except ValueError as error:
            raise VerificationError(
                f"real check {check_id} cwd escapes the repository"
            ) from error
        if not resolved_cwd.is_dir():
            raise VerificationError(f"real check {check_id} cwd does not exist")
        canonical_cwd = resolved_cwd.relative_to(repo).as_posix() or "."
        if canonical_cwd != ".":
            raise VerificationError(
                f"real check {check_id} cwd must be the repository root"
            )
        if len(argv) < 2 or argv[0] != "<python>":
            raise VerificationError(
                f"real check {check_id} must invoke a candidate-owned Python probe"
            )
        entrypoint = Path(argv[1])
        if entrypoint.is_absolute():
            raise VerificationError(
                f"real check {check_id} entrypoint must be repository-relative"
            )
        resolved_entrypoint = (repo / entrypoint).resolve()
        try:
            canonical_entrypoint = resolved_entrypoint.relative_to(repo).as_posix()
        except ValueError as error:
            raise VerificationError(
                f"real check {check_id} entrypoint escapes the repository"
            ) from error
        if (
            not canonical_entrypoint.startswith("scripts/live_voice/")
            or not canonical_entrypoint.endswith(".py")
            or not resolved_entrypoint.is_file()
        ):
            raise VerificationError(
                f"real check {check_id} requires a scripts/live_voice/*.py entrypoint"
            )
        tracked = _git(
            repo,
            "ls-files",
            "--error-unmatch",
            "--",
            canonical_entrypoint,
            check=False,
        )
        in_head = subprocess.run(
            ("git", "cat-file", "-e", f"HEAD:{canonical_entrypoint}"),
            cwd=repo,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        if not tracked or in_head.returncode != 0:
            raise VerificationError(
                f"real check {check_id} entrypoint must be tracked in candidate HEAD"
            )
        if len(argv) != 2:
            raise VerificationError(
                f"real check {check_id} cannot contain positional probe arguments; "
                "private inputs must use required_env"
            )
        canonical_probe, canonical_required_env = CANONICAL_REAL_PROBES[check_id]
        if canonical_entrypoint != canonical_probe:
            raise VerificationError(
                f"real check {check_id} must use its canonical candidate-owned entrypoint"
            )
        if required_names != canonical_required_env:
            raise VerificationError(
                f"real check {check_id} must declare its exact canonical environment"
            )
        normalized_argv = (argv[0], canonical_entrypoint)
        specs.append(
            CheckSpec(
                check_id=check_id,
                category="real-path",
                argv=tuple(normalized_argv),
                cwd=canonical_cwd,
                required_env=tuple(required),
                real_path=True,
            )
        )
        seen.add(check_id)

    missing = REQUIRED_REAL_CHECKS - seen
    if missing:
        raise VerificationError(
            "real-check configuration is incomplete: " + ", ".join(sorted(missing))
        )
    return tuple(specs)


def _expand_argv(spec: CheckSpec) -> tuple[str, ...]:
    expanded: list[str] = []
    for token in spec.argv:
        if token == "<python>":
            expanded.append(sys.executable)
            continue
        expanded.append(token)
    return tuple(expanded)


def _summarize_output(
    output: str,
    *,
    include_test_details: bool = True,
) -> dict[str, int | float | str | bool]:
    details: dict[str, int | float | str | bool] = {}
    count_patterns = {
        "passed": r"(?:^|\s)(\d+) passed(?:\s|,|$)",
        "failed": r"(?:^|\s)(\d+) failed(?:\s|,|$)",
        "skipped": r"(?:^|\s)(\d+) skipped(?:\s|,|$)",
        "errors": r"(?:^|\s)(\d+) errors?(?:\s|,|$)",
        "node_tests": r"^(?:#|ℹ) tests (\d+)\s*$",
        "node_passed": r"^(?:#|ℹ) pass (\d+)\s*$",
        "node_failed": r"^(?:#|ℹ) fail (\d+)\s*$",
        "vite_modules": r"(?:✓|built)\s+(\d+) modules transformed",
    }
    if include_test_details:
        for key, pattern in count_patterns.items():
            matches = re.findall(pattern, output, flags=re.MULTILINE)
            if matches:
                details[key] = int(matches[-1])

    failure_ids: list[str] = []
    redacted_failure_ids = 0
    sanitized_count = 0
    sanitized_invalid = False
    for line in output.splitlines():
        if include_test_details and line.startswith("FAILED "):
            candidate = line.removeprefix("FAILED ").split(" - ", 1)[0].strip()
            if (
                _SECRET_VALUE.search(candidate)
                or _MACHINE_PRIVATE_PATH.search(candidate)
                or _ABSOLUTE_PATH_REFERENCE.search(candidate)
                or _CREDENTIAL_ARGUMENT.search(candidate)
                or _BEARER_OR_JWT.search(candidate)
            ):
                redacted_failure_ids += 1
            else:
                failure_ids.append(candidate[:512])
        elif include_test_details and re.match(r"^not ok \d+ - ", line):
            candidate = re.sub(r"^not ok \d+ - ", "", line).strip()
            if (
                _SECRET_VALUE.search(candidate)
                or _MACHINE_PRIVATE_PATH.search(candidate)
                or _ABSOLUTE_PATH_REFERENCE.search(candidate)
                or _CREDENTIAL_ARGUMENT.search(candidate)
                or _BEARER_OR_JWT.search(candidate)
            ):
                redacted_failure_ids += 1
            else:
                failure_ids.append(candidate[:512])
        if line.startswith("S7_SANITIZED_RESULT "):
            sanitized_count += 1
            try:
                payload = json.loads(line.removeprefix("S7_SANITIZED_RESULT "))
            except json.JSONDecodeError:
                sanitized_invalid = True
                continue
            if not isinstance(payload, dict):
                sanitized_invalid = True
                continue
            unknown = set(payload) - {
                "candidate_head",
                "runtime_declaration_sha256",
                "check_id",
                "sample_count",
                "failure_count",
                "p50_ms",
                "p95_ms",
                "max_ms",
                "zero_forbidden_effects",
                "outcome",
            }
            if unknown:
                sanitized_invalid = True
            candidate_head = payload.get("candidate_head")
            if isinstance(candidate_head, str) and _FULL_SHA.fullmatch(candidate_head):
                details["probe_candidate_head"] = candidate_head
            else:
                sanitized_invalid = True
            runtime_sha = payload.get("runtime_declaration_sha256")
            if isinstance(runtime_sha, str) and _SHA256_REF.fullmatch(runtime_sha):
                details["probe_runtime_declaration_sha256"] = runtime_sha
            elif runtime_sha is not None:
                sanitized_invalid = True
            probe_check_id = payload.get("check_id")
            if (
                isinstance(probe_check_id, str)
                and probe_check_id in REQUIRED_REAL_CHECKS
            ):
                details["probe_check_id"] = probe_check_id
            else:
                sanitized_invalid = True
            for key in ("sample_count", "failure_count"):
                value = payload.get(key)
                if (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                ):
                    details[f"probe_{key}"] = value
                elif value is not None:
                    sanitized_invalid = True
            for key in ("p50_ms", "p95_ms", "max_ms"):
                value = payload.get(key)
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    and value >= 0
                ):
                    details[f"probe_{key}"] = value
                elif value is not None:
                    sanitized_invalid = True
            zero_effects = payload.get("zero_forbidden_effects")
            if isinstance(zero_effects, bool):
                details["probe_zero_forbidden_effects"] = zero_effects
            elif zero_effects is not None:
                sanitized_invalid = True
            outcome = payload.get("outcome")
            if outcome in {"PASS", "FAIL", "BLOCKED"}:
                details["probe_outcome"] = outcome
            elif outcome is not None:
                sanitized_invalid = True
    if failure_ids:
        details["failure_ids"] = ",".join(failure_ids[:50])
        details["failure_ids_truncated"] = len(failure_ids) > 50
    if redacted_failure_ids:
        details["failure_ids_redacted"] = redacted_failure_ids
    if sanitized_count:
        details["sanitized_result_count"] = sanitized_count
    if sanitized_invalid or sanitized_count > 1:
        details["sanitized_result_invalid"] = True
    return details


def _real_probe_contract_valid(
    check_id: str,
    candidate_head: str,
    details: Mapping[str, int | float | str | bool],
    runtime_declaration_sha256: str | None = None,
) -> bool:
    if details.get("output_truncated") is True:
        return False
    if details.get("sanitized_result_count") != 1:
        return False
    if details.get("sanitized_result_invalid") is True:
        return False
    if details.get("probe_outcome") != "PASS":
        return False
    if details.get("probe_check_id") != check_id:
        return False
    if details.get("probe_candidate_head") != candidate_head:
        return False
    if runtime_declaration_sha256 is not None and (
        details.get("probe_runtime_declaration_sha256") != runtime_declaration_sha256
    ):
        return False
    if details.get("probe_zero_forbidden_effects") is not True:
        return False
    sample_count = details.get("probe_sample_count")
    failure_count = details.get("probe_failure_count")
    if (
        not isinstance(sample_count, int)
        or isinstance(sample_count, bool)
        or sample_count < 1
    ):
        return False
    if (
        not isinstance(failure_count, int)
        or isinstance(failure_count, bool)
        or failure_count != 0
    ):
        return False
    if check_id in REAL_LATENCY_CHECKS:
        p50 = details.get("probe_p50_ms")
        p95 = details.get("probe_p95_ms")
        if not isinstance(p50, (int, float)) or isinstance(p50, bool):
            return False
        if not isinstance(p95, (int, float)) or isinstance(p95, bool):
            return False
        if p95 < p50:
            return False
        maximum = details.get("probe_max_ms")
        if maximum is not None and (
            not isinstance(maximum, (int, float))
            or isinstance(maximum, bool)
            or maximum < p95
        ):
            return False
    return True


def _automatic_output_contract_valid(
    spec: CheckSpec,
    details: Mapping[str, int | float | str | bool],
) -> bool:
    if spec.check_id == "frontend-production-build":
        modules = details.get("vite_modules")
        return (
            details.get("output_truncated") is not True
            and isinstance(modules, int)
            and not isinstance(modules, bool)
            and modules >= 1
        )
    if spec.category == "backend":
        passed = details.get("passed")
        failed = details.get("failed", 0)
        errors = details.get("errors", 0)
        return (
            details.get("output_truncated") is not True
            and isinstance(passed, int)
            and not isinstance(passed, bool)
            and passed >= 1
            and failed == 0
            and errors == 0
        )
    if spec.category != "frontend-test":
        return True
    tests = details.get("node_tests")
    passed = details.get("node_passed")
    failed = details.get("node_failed")
    return (
        isinstance(tests, int)
        and not isinstance(tests, bool)
        and tests >= 1
        and isinstance(passed, int)
        and not isinstance(passed, bool)
        and passed >= 1
        and isinstance(failed, int)
        and not isinstance(failed, bool)
        and failed == 0
    )


def _child_env(
    spec: CheckSpec,
    env: Mapping[str, str],
    *,
    candidate_head: str,
    runtime_declaration_sha256: str | None = None,
) -> dict[str, str]:
    if not spec.real_path:
        names = _AUTOMATION_ENV_ALLOWLIST
        child = {name: env[name] for name in names if name in env}
    else:
        names = (
            _PROCESS_ENV_ALLOWLIST
            | REQUIRED_FEATURE_FLAGS
            | frozenset(spec.required_env)
        )
        child = {name: env[name] for name in names if name in env}
        child["S7_CANDIDATE_HEAD"] = candidate_head
        child["S7_CHECK_ID"] = spec.check_id
        if runtime_declaration_sha256 is not None:
            child["S7_RUNTIME_DECLARATION_SHA256"] = runtime_declaration_sha256
    return child


def _isolate_user_directories(env: dict[str, str], root: Path) -> None:
    directories = {
        "HOME": root / "home",
        "USERPROFILE": root / "home",
        "APPDATA": root / "appdata",
        "LOCALAPPDATA": root / "localappdata",
        "TEMP": root / "tmp",
        "TMP": root / "tmp",
    }
    for path in set(directories.values()):
        path.mkdir(parents=True, exist_ok=True)
    for name, path in directories.items():
        env[name] = str(path)


def _create_windows_kill_job(process: subprocess.Popen[bytes]) -> object | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("per_process_user_time_limit", ctypes.c_longlong),
            ("per_job_user_time_limit", ctypes.c_longlong),
            ("limit_flags", wintypes.DWORD),
            ("minimum_working_set_size", ctypes.c_size_t),
            ("maximum_working_set_size", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("read_operation_count", ctypes.c_ulonglong),
            ("write_operation_count", ctypes.c_ulonglong),
            ("other_operation_count", ctypes.c_ulonglong),
            ("read_transfer_count", ctypes.c_ulonglong),
            ("write_transfer_count", ctypes.c_ulonglong),
            ("other_transfer_count", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("basic_limit_information", BasicLimitInformation),
            ("io_info", IoCounters),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory_used", ctypes.c_size_t),
            ("peak_job_memory_used", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise VerificationError("Windows process-tree isolation is unavailable")
    information = ExtendedLimitInformation()
    information.basic_limit_information.limit_flags = 0x00002000
    if not kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(information), ctypes.sizeof(information)
    ):
        kernel32.CloseHandle(job)
        raise VerificationError("Windows process-tree isolation is unavailable")
    process_handle = wintypes.HANDLE(int(getattr(process, "_handle")))
    if not kernel32.AssignProcessToJobObject(job, process_handle):
        kernel32.CloseHandle(job)
        raise VerificationError("Windows process-tree isolation is unavailable")
    return job


def _close_windows_job(job: object | None) -> None:
    if os.name != "nt" or job is None:
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(job)


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(
                ("taskkill", "/PID", str(process.pid), "/T", "/F"),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def _run_bounded_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
) -> tuple[int, str, bool, bool]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    try:
        windows_job = _create_windows_kill_job(process)
    except VerificationError:
        _terminate_process_tree(process)
        process.wait()
        raise
    capture = bytearray()
    truncated = False

    def read_output() -> None:
        nonlocal truncated
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                return
            capture.extend(chunk)
            if len(capture) > _MAX_CAPTURE_BYTES:
                del capture[: len(capture) - _MAX_CAPTURE_BYTES]
                truncated = True

    reader = threading.Thread(target=read_output, name="s7-output-reader", daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        process.wait()
    except KeyboardInterrupt:
        _terminate_process_tree(process)
        process.wait()
        raise
    finally:
        if os.name == "nt":
            _close_windows_job(windows_job)
            windows_job = None
        else:
            _terminate_process_tree(process)
        reader.join(timeout=10)
        if reader.is_alive():
            _terminate_process_tree(process)
            reader.join(timeout=5)
    output = bytes(capture).decode("utf-8", errors="replace")
    return process.returncode, output, timed_out, truncated


def _echo_automatic_output(output: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe_output = output.encode(encoding, errors="backslashreplace").decode(encoding)
    print(safe_output, end="" if safe_output.endswith("\n") else "\n", flush=True)


def run_check(
    spec: CheckSpec,
    *,
    repo: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    candidate_head: str,
    runtime_declaration_sha256: str | None = None,
) -> CheckResult:
    missing = tuple(name for name in spec.required_env if not env.get(name, "").strip())
    if missing:
        return CheckResult(
            check_id=spec.check_id,
            category=spec.category,
            status=CheckStatus.BLOCKED,
            duration_ms=0,
            reason="required environment is unavailable: " + ", ".join(missing),
            command=spec.argv,
            cwd=spec.cwd,
        )

    print(f"S7_CHECK_START {spec.check_id}", flush=True)
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="live-voice-s7-check-") as temp:
            child_env = _child_env(
                spec,
                env,
                candidate_head=candidate_head,
                runtime_declaration_sha256=runtime_declaration_sha256,
            )
            _isolate_user_directories(child_env, Path(temp))
            exit_code, output, timed_out, output_truncated = _run_bounded_process(
                _expand_argv(spec),
                cwd=(repo / spec.cwd).resolve(),
                env=child_env,
                timeout_seconds=timeout_seconds,
            )
    except (FileNotFoundError, VerificationError) as error:
        duration = int((time.monotonic() - started) * 1000)
        print(f"S7_CHECK_END {spec.check_id} FAIL", flush=True)
        return CheckResult(
            check_id=spec.check_id,
            category=spec.category,
            status=CheckStatus.FAIL,
            duration_ms=duration,
            reason=(
                "command not found"
                if isinstance(error, FileNotFoundError)
                else "process-tree isolation unavailable"
            ),
            command=spec.argv,
            cwd=spec.cwd,
        )
    if output and not spec.real_path:
        if output_truncated:
            print("S7_CHECK_OUTPUT_TRUNCATED", flush=True)
        _echo_automatic_output(output)
    duration = int((time.monotonic() - started) * 1000)
    details = _summarize_output(output, include_test_details=not spec.real_path)
    if output_truncated:
        details["output_truncated"] = True
    command_passed = exit_code == 0 and not timed_out
    probe_valid = not spec.real_path or _real_probe_contract_valid(
        spec.check_id,
        candidate_head,
        details,
        runtime_declaration_sha256,
    )
    automatic_valid = _automatic_output_contract_valid(spec, details)
    if command_passed and probe_valid and automatic_valid:
        status = CheckStatus.VERIFY if spec.real_path else CheckStatus.PASS
    else:
        status = CheckStatus.FAIL
    print(f"S7_CHECK_END {spec.check_id} {status}", flush=True)
    return CheckResult(
        check_id=spec.check_id,
        category=spec.category,
        status=status,
        duration_ms=duration,
        exit_code=exit_code,
        reason=(
            None
            if status in {CheckStatus.PASS, CheckStatus.VERIFY}
            else "check timed out and its process tree was terminated"
            if timed_out
            else "command returned non-zero"
            if not command_passed
            else "automatic check omitted or violated its result summary contract"
            if not automatic_valid
            else "real probe omitted or violated the sanitized result contract"
        ),
        details=details,
        command=spec.argv,
        cwd=spec.cwd,
    )


def _aggregate(results: Sequence[CheckResult]) -> CheckStatus:
    if not results:
        return CheckStatus.NOT_RUN
    statuses = {result.status for result in results}
    if CheckStatus.FAIL in statuses:
        return CheckStatus.FAIL
    if CheckStatus.BLOCKED in statuses:
        return CheckStatus.BLOCKED
    if statuses == {CheckStatus.PASS}:
        return CheckStatus.PASS
    if statuses == {CheckStatus.VERIFY}:
        return CheckStatus.VERIFY
    return CheckStatus.NOT_RUN


def build_report(
    *,
    identity: CandidateIdentity,
    results: Sequence[CheckResult],
    runtime_declaration: CandidateRuntimeDeclaration | None = None,
) -> VerificationReport:
    automation = tuple(result for result in results if result.category != "real-path")
    real = tuple(result for result in results if result.category == "real-path")
    automation_status = _aggregate(automation)
    real_status = _aggregate(real)
    if CheckStatus.FAIL in {automation_status, real_status}:
        readiness = "FAIL"
    elif (
        automation_status is CheckStatus.PASS
        and real_status is CheckStatus.VERIFY
        and runtime_declaration is not None
    ):
        readiness = "READY_FOR_S7_CUMULATIVE_REVIEW"
    elif CheckStatus.BLOCKED in {automation_status, real_status}:
        readiness = "BLOCKED"
    else:
        readiness = "PARTIAL_AUTOMATION_ONLY"
    if identity.upstream is None and readiness == "READY_FOR_S7_CUMULATIVE_REVIEW":
        readiness = "PREPARATION_ONLY_NO_UPSTREAM"
    elif identity.behind and readiness == "READY_FOR_S7_CUMULATIVE_REVIEW":
        readiness = "PREPARATION_ONLY_BEHIND_UPSTREAM"
    return VerificationReport(
        schema_version=REPORT_SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        not_a_gate=True,
        candidate=identity,
        runtime_declaration=runtime_declaration,
        automation_status=automation_status,
        real_path_status=real_status,
        s7_readiness=readiness,
        checks=tuple(results),
    )


def _report_json(report: VerificationReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=True, indent=2, sort_keys=True)


def report_exit_code(report: VerificationReport) -> int:
    if report.s7_readiness == "READY_FOR_S7_CUMULATIVE_REVIEW":
        return 0
    if report.s7_readiness == "FAIL":
        return 1
    if report.s7_readiness == "BLOCKED":
        return 2
    return 3


def write_report(report: VerificationReport, output: Path | None, repo: Path) -> None:
    rendered = _report_json(report)
    if output is None:
        print(rendered)
        return
    resolved = output.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError:
        pass
    else:
        raise VerificationError(
            "verification report must be written outside the source worktree"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(rendered + "\n", encoding="utf-8")
    print(f"S7_REPORT_WRITTEN {resolved.name}", flush=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the unsigned S7 Alpha verification matrix. This tool does not "
            "replace real-path or human acceptance."
        )
    )
    parser.add_argument("command", choices=("plan", "run", "ruff-baseline"))
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--comparison-base", required=True)
    parser.add_argument("--allow-no-upstream", action="store_true")
    parser.add_argument("--candidate-record", type=Path)
    parser.add_argument("--real-config", type=Path)
    parser.add_argument("--require-real", action="store_true")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.timeout_seconds <= 0:
            raise VerificationError("--timeout-seconds must be positive")
        require_s7_comparison_base(args.comparison_base)
        repo = resolve_repo(args.repo)
        if args.command == "ruff-baseline":
            return verify_changed_python_ruff_baseline(repo, args.comparison_base)
        if args.command == "run":
            require_project_python(repo)
        identity = collect_candidate_identity(
            repo,
            comparison_base=args.comparison_base,
            allow_no_upstream=args.allow_no_upstream,
        )
        specs = list(
            build_automation_specs(repo, comparison_base=identity.comparison_base)
        )
        runtime_declaration = None
        if args.candidate_record is not None:
            runtime_declaration = load_candidate_runtime(
                args.candidate_record,
                repo=repo,
                identity=identity,
                env=os.environ,
            )
        if args.real_config is not None:
            if runtime_declaration is None:
                raise VerificationError(
                    "--real-config requires an external --candidate-record"
                )
            specs.extend(
                load_real_check_specs(args.real_config.resolve(strict=True), repo)
            )
        elif args.require_real:
            raise VerificationError("--require-real needs a complete --real-config")
        runtime_declaration_sha = (
            candidate_runtime_sha256(runtime_declaration)
            if runtime_declaration is not None
            else None
        )
        if args.only:
            requested = frozenset(args.only)
            known = {spec.check_id for spec in specs}
            unknown = requested - known
            if unknown:
                raise VerificationError(
                    "unknown --only check: " + ", ".join(sorted(unknown))
                )
            if args.require_real and not REQUIRED_REAL_CHECKS.issubset(requested):
                raise VerificationError(
                    "--require-real cannot filter out any required real-path check"
                )
            specs = [spec for spec in specs if spec.check_id in requested]
            selected_subset = requested != known
        else:
            selected_subset = False

        if args.command == "plan":
            print(
                json.dumps(
                    {
                        "candidate": asdict(identity),
                        "runtime_declaration": (
                            asdict(runtime_declaration)
                            if runtime_declaration is not None
                            else None
                        ),
                        "runtime_declaration_sha256": runtime_declaration_sha,
                        "checks": [
                            {
                                "id": spec.check_id,
                                "category": spec.category,
                                "real_path": spec.real_path,
                                "required_env": list(spec.required_env),
                                "argv": list(spec.argv),
                                "cwd": spec.cwd,
                            }
                            for spec in specs
                        ],
                        "not_a_gate": True,
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        results: list[CheckResult] = [
            inspect_markdown_links(repo),
            inspect_source_hygiene(repo, identity.comparison_base),
        ]
        if selected_subset:
            results.append(
                CheckResult(
                    check_id="selected-check-filter",
                    category="source",
                    status=CheckStatus.NOT_RUN,
                    duration_ms=0,
                    reason="--only selected a subset; this run cannot establish S7 readiness",
                    command=("internal:selected-check-filter",),
                )
            )
        for spec in specs:
            results.append(
                run_check(
                    spec,
                    repo=repo,
                    env=os.environ,
                    timeout_seconds=args.timeout_seconds,
                    candidate_head=identity.head,
                    runtime_declaration_sha256=runtime_declaration_sha,
                )
            )
        results.append(inspect_candidate_after_run(repo, identity))
        report = build_report(
            identity=identity,
            results=results,
            runtime_declaration=runtime_declaration,
        )
        write_report(report, args.report, repo)
        return report_exit_code(report)
    except (OSError, ValueError, VerificationError, json.JSONDecodeError) as error:
        print(f"S7_VERIFICATION_ERROR {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
