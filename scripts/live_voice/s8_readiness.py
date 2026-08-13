# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Unsigned, fail-closed operator support for Live Voice S8 readiness.

This module consumes an S7 automation report and an S7-04 handoff.  It does not
freeze a candidate, rerun S7, perform human observations, or produce Alpha PASS.
Private paths and values are accepted only through explicit arguments or the
process environment and are never copied into a generated report.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import signal
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlparse


S7_REPORT_SCHEMA = "live-voice.s7-automation-report.v1"
S7_HANDOFF_SCHEMA = "live-voice.s7-a3-handoff.v1"
PREFLIGHT_REPORT_SCHEMA = "live-voice.s8-preflight-report.v1"
SESSION_SCHEMA = "live-voice.s8-observation-session.v1"
FIXTURE_MARKER_SCHEMA = "live-voice.s8-disposable-fixture.v1"
EFFECT_PLAN_SCHEMA = "live-voice.s8-fixture-effect-plan.v1"
PRODUCT_TRACE_SCHEMA = "live-voice.s8-product-trace.v1"
TRACE_MANIFEST_SCHEMA = "live-voice.s8-trace-manifest.v1"
PRODUCT_BINDING_SCHEMA = "live-voice.s8-product-binding.v1"

REQUIRED_REAL_CHECKS = frozenset(
    {
        "speech-media",
        "agent-executor",
        "benchmark-fault",
        "secure-deployment",
        "privacy",
    }
)
SERVICE_PORT_ENV: Mapping[str, str] = {
    "agentserver": "AGENT_SERVER_PORT",
    "webchannel": "WEB_PORT",
    "gateway": "GATEWAY_PORT",
    "frontend": "FRONTEND_PORT",
}
RUNTIME_ENV_BY_LABEL: Mapping[str, str] = {
    "agent_provider": "S8_AGENT_PROVIDER",
    "browser": "S8_BROWSER_LABEL",
    "operating_system": "S8_OS_LABEL",
    "input_device": "S8_INPUT_DEVICE_REF",
    "output_device": "S8_OUTPUT_DEVICE_REF",
    "network_profile": "S8_NETWORK_REF",
    "speech_provider": "S8_SPEECH_PROVIDER",
    "speech_api_origin": "S8_SPEECH_API_ORIGIN",
    "speech_fallback": "S8_SPEECH_FALLBACK",
    "stt_model": "S8_STT_MODEL",
    "tts_model": "S8_TTS_MODEL",
    "tts_voice": "S8_TTS_VOICE",
    "executor": "S8_EXECUTOR",
    "deployment_topology": "S8_DEPLOYMENT_TOPOLOGY",
}
PRIVATE_PRESENCE_ENV = (
    "LIVE_VOICE_SPEECH_API_KEY",
    "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN",
)
IDENTITY_KINDS = ("task", "attempt", "response", "round", "work")

_OBSERVATION_IDENTITIES: Mapping[str, tuple[str, ...]] = {
    "S8-01.TEXT_TOOL_SMOKE": ("response", "round"),
    "S8-01.PROVIDER_DEVICE_PROBE": ("response", "round"),
    "S8-02.PLATFORM.PERMISSION_GRANT": (),
    "S8-02.PLATFORM.PERMISSION_DENIAL": (),
    "S8-02.PLATFORM.PERMISSION_REVOCATION": (),
    "S8-02.PLATFORM.DEVICE_RECOVERY": (),
    "S8-02.PLATFORM.AUTOPLAY_USER_ACTIVATION": (),
    "S8-02.PLATFORM.BACKGROUND_RESUME": ("response", "round"),
    "S8-02.PLATFORM.REFRESH_RECONNECT": ("task", "response", "round"),
    "S8-02.P1.CRITICAL_COMMIT": ("response", "round"),
    "S8-02.P1.PARTIAL_ZERO_EFFECT": ("response", "round"),
    "S8-02.P1.HEARD_PLAYOUT": ("response", "round"),
    "S8-02.P1.EXACT_STOP": ("response", "round"),
    "S8-02.P2.READ_ONLY_TOOL": ("response", "round"),
    "S8-02.P2.MULTI_TURN": ("response", "round"),
    "S8-02.P2.INTERRUPT_REVISION": ("response", "round"),
    "S8-02.P2.HISTORY_TRUTH": ("response", "round"),
    "S8-02.P3.STRUCTURED_CREATE_GET_LIST": ("task", "attempt", "work"),
    "S8-02.P3.STRUCTURED_STATUS_EVENTS_CANCEL": ("task", "attempt", "work"),
    "S8-02.P3.AMBIGUOUS_ZERO_MUTATION": ("response", "round"),
    "S8-02.P3.NATURAL_CREATE": ("task", "attempt", "response", "round", "work"),
    "S8-02.P3.NATURAL_STATUS_CANCEL": ("task", "attempt", "response", "round", "work"),
    "S8-02.P3.RESTART_RECONCILIATION": ("task", "attempt", "work"),
    "S8-02.P3.FULL_P3_UNSUPPORTED": ("task", "attempt", "work"),
    "S8-02.JOINT.SLOW_CONVERSATION_DETACHED_TASK": (
        "task",
        "attempt",
        "response",
        "round",
        "work",
    ),
    "S8-02.JOINT.TARGET_ISOLATION": (
        "task",
        "attempt",
        "response",
        "round",
        "work",
    ),
    "S8-02.DEGRADATION.SPEECH_ROUTE": ("response", "round"),
    "S8-02.DEGRADATION.EXECUTOR_TRUTH": ("task", "attempt", "work"),
    "S8-02.PRIVACY.SURFACES": (
        "task",
        "attempt",
        "response",
        "round",
        "work",
    ),
    "S8-03.LIVE_VOICE_STOPPED": ("response", "round"),
    "S8-03.TASK_STATE_SETTLED": (),
    "S8-03.PROJECT_EFFECT": (),
    "S8-03.SERVICES_RELEASED": (),
    "S8-03.WORKTREE_UNCHANGED": (),
    "S8-03.PRIVATE_ARTIFACTS_HANDLED": (),
}

_OBSERVATION_SCOPES: Mapping[str, str] = {
    check_id: check_id.casefold().replace("s8-02.", "").replace("s8-01.", "")
    for check_id in _OBSERVATION_IDENTITIES
}
_OBSERVATION_SCOPES = {
    **_OBSERVATION_SCOPES,
    "S8-02.P3.STRUCTURED_CREATE_GET_LIST": "p3.structured",
    "S8-02.P3.STRUCTURED_STATUS_EVENTS_CANCEL": "p3.structured",
    "S8-02.P3.NATURAL_CREATE": "p3.natural",
    "S8-02.P3.NATURAL_STATUS_CANCEL": "p3.natural",
    "S8-02.JOINT.SLOW_CONVERSATION_DETACHED_TASK": "joint",
    "S8-02.JOINT.TARGET_ISOLATION": "joint",
}
_SCOPE_START_SEQUENCE: Mapping[str, int] = {
    scope: min(
        sequence
        for sequence, check_id in enumerate(_OBSERVATION_IDENTITIES, start=1)
        if _OBSERVATION_SCOPES[check_id] == scope
    )
    for scope in set(_OBSERVATION_SCOPES.values())
}

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,95}$")
_SESSION_ID = re.compile(r"^s8-[a-z0-9][a-z0-9-]{2,63}$")
_IDENTITY_ALIAS = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_IDENTITY_REF = re.compile(
    r"^(?:task|attempt|response|round|work)_ref:sha256-[0-9a-f]{32,64}$"
)
_RESOURCE_REF = re.compile(
    r"^(?:disposable_git|data|artifact|process)_ref:sha256-[0-9a-f]{32,64}"
    r"(?::no_remote)?$"
)
_TRACE_RECORD_REF = re.compile(r"^trace_record_ref:sha256-[0-9a-f]{64}$")
_PRODUCT_CONTEXT_REF = re.compile(
    r"^product_(?:session|correlation)_ref:sha256-[0-9a-f]{64}$"
)
_PRODUCT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_PRIVATE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/(?:home|Users)/[^/\s]+/)",
    re.IGNORECASE,
)
_ABSOLUTE_PATH = re.compile(r"(?:^[A-Za-z]:[\\/]|^/(?!/))")
_SECRET = re.compile(
    r"(?:(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,})",
    re.IGNORECASE,
)

_TRACE_SCOPE_RULES: Mapping[str, tuple[str, str, frozenset[str], frozenset[str]]] = {
    "text_tool_smoke": (
        "segment.completed",
        "agent.dispatch",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "provider_device_probe": (
        "speech.capture_state",
        "speech.capture",
        frozenset({"audio.browser", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "platform.background_resume": (
        "segment.started",
        "runtime.response",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "platform.refresh_reconnect": (
        "segment.started",
        "runtime.turn",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p1.critical_commit": (
        "segment.completed",
        "runtime.response",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p1.partial_zero_effect": (
        "segment.started",
        "speech.recognition",
        frozenset({"audio.browser", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p1.heard_playout": (
        "segment.completed",
        "speech.playout",
        frozenset({"audio.browser", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p1.exact_stop": (
        "cancel.terminal",
        "speech.playout",
        frozenset({"audio.browser", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p2.read_only_tool": (
        "segment.completed",
        "agent.progress",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p2.multi_turn": (
        "segment.started",
        "agent.progress",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p2.interrupt_revision": (
        "cancel.terminal",
        "runtime.response",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p2.history_truth": (
        "segment.completed",
        "runtime.presentation",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p3.structured": (
        "task.dispatch_outbox_observed",
        "task.queue",
        frozenset({"task.core"}),
        frozenset({"formal"}),
    ),
    "p3.ambiguous_zero_mutation": (
        "segment.completed",
        "runtime.turn",
        frozenset({"agent.bridge", "route.telemetry"}),
        frozenset({"formal"}),
    ),
    "p3.natural": (
        "segment.completed",
        "task.command",
        frozenset({"route.telemetry", "task.core"}),
        frozenset({"formal"}),
    ),
    "p3.restart_reconciliation": (
        "task.state_observed",
        "task.progress",
        frozenset({"task.core"}),
        frozenset({"formal"}),
    ),
    "p3.full_p3_unsupported": (
        "segment.started",
        "task.command",
        frozenset({"route.telemetry"}),
        frozenset({"unsupported"}),
    ),
    "joint": (
        "segment.started",
        "task.attempt",
        frozenset({"task.core"}),
        frozenset({"formal"}),
    ),
    "degradation.speech_route": (
        "degradation.activated",
        "system.degradation",
        frozenset({"route.telemetry"}),
        frozenset({"fallback"}),
    ),
    "degradation.executor_truth": (
        "segment.failed",
        "task.attempt",
        frozenset({"task.core"}),
        frozenset({"formal"}),
    ),
    "privacy.surfaces": (
        "segment.completed",
        "task.progress",
        frozenset({"task.core"}),
        frozenset({"formal"}),
    ),
    "s8-03.live_voice_stopped": (
        "speech.playout_state",
        "speech.playout",
        frozenset({"audio.browser"}),
        frozenset({"formal"}),
    ),
}
_FIXTURE_NAME = re.compile(r"^live-voice-s8-fixture-[a-z0-9][a-z0-9-]{2,63}$")
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_OUTPUT_BYTES = 1024 * 1024
_MAX_FIXTURE_FILE_BYTES = 64 * 1024 * 1024
_MAX_FIXTURE_TOTAL_BYTES = 256 * 1024 * 1024
_GENERATED_ARTIFACT_PATHS = (
    "jiuwenswarm/channels/web/frontend/dist",
    "jiuwenswarm/channels/web/frontend/node_modules/.cache",
)


class ReadinessError(RuntimeError):
    """A content-free reason code safe to include in an operator report."""

    def __init__(self, reason_code: str) -> None:
        if _SAFE_ID.fullmatch(reason_code) is None:
            reason_code = "UNSAFE_FAILURE_DETAIL_REDACTED"
        super().__init__(reason_code)
        self.reason_code = reason_code


class SafeArgumentParser(argparse.ArgumentParser):
    """Reject unknown/private argv without reflecting its contents."""

    def error(self, _message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "S8_READINESS_BLOCKED CLI_ARGUMENT_INVALID\n")


@dataclass(frozen=True, slots=True)
class ProcessResult:
    exit_code: int
    output: str
    output_bytes: bytes
    timed_out: bool
    cancelled: bool
    truncated: bool


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            process.kill()
        return
    try:
        import psutil

        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        for child in reversed(descendants):
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            parent.terminate()
        except psutil.Error:
            pass
        _, alive = psutil.wait_procs([*descendants, parent], timeout=2)
        for item in alive:
            try:
                item.kill()
            except psutil.Error:
                pass
    except (ImportError, Exception):  # noqa: BLE001 - fallback is content-free
        if os.name == "nt" and process.poll() is None:
            subprocess.run(
                ("taskkill", "/PID", str(process.pid), "/T", "/F"),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
    if process.poll() is None:
        process.kill()


def _remove_owned_tree(path: Path) -> None:
    def remove_readonly(
        function: Callable[[str], object], target: str, _error: BaseException
    ) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onexc=remove_readonly)


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
        raise ReadinessError("PROCESS_TREE_ISOLATION_UNAVAILABLE")
    information = ExtendedLimitInformation()
    information.basic_limit_information.limit_flags = 0x00002000
    if not kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(information), ctypes.sizeof(information)
    ):
        kernel32.CloseHandle(job)
        raise ReadinessError("PROCESS_TREE_ISOLATION_UNAVAILABLE")
    try:
        handle = wintypes.HANDLE(int(getattr(process, "_handle")))
    except (AttributeError, TypeError, ValueError) as error:
        kernel32.CloseHandle(job)
        raise ReadinessError("PROCESS_TREE_ISOLATION_UNAVAILABLE") from error
    if not kernel32.AssignProcessToJobObject(job, handle):
        kernel32.CloseHandle(job)
        raise ReadinessError("PROCESS_TREE_ISOLATION_UNAVAILABLE")
    return job


def _resume_windows_process(process: subprocess.Popen[bytes]) -> None:
    if os.name != "nt":
        return
    try:
        import psutil

        psutil.Process(process.pid).resume()
    except Exception as error:  # noqa: BLE001 - content-free boundary
        raise ReadinessError("PROCESS_TREE_ISOLATION_UNAVAILABLE") from error


def _close_windows_job(job: object | None) -> None:
    if os.name != "nt" or job is None:
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(job)


def _run_bounded_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = 30,
    cancel_event: threading.Event | None = None,
) -> ProcessResult:
    if not argv or timeout_seconds <= 0:
        raise ReadinessError("BOUNDED_PROCESS_ARGUMENT_INVALID")
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=None if env is None else dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004 if os.name == "nt" else 0
        ),
        start_new_session=os.name != "nt",
    )
    windows_job: object | None = None
    try:
        windows_job = _create_windows_kill_job(process)
        _resume_windows_process(process)
    except ReadinessError:
        _terminate_process_tree(process)
        process.wait(timeout=5)
        _close_windows_job(windows_job)
        raise
    capture = bytearray()
    truncated = False

    def read_output() -> None:
        nonlocal truncated
        assert process.stdout is not None
        while chunk := process.stdout.read(64 * 1024):
            capture.extend(chunk)
            if len(capture) > _MAX_OUTPUT_BYTES:
                del capture[: len(capture) - _MAX_OUTPUT_BYTES]
                truncated = True

    reader = threading.Thread(target=read_output, name="s8-output-reader", daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    cancelled = False
    try:
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                _terminate_process_tree(process)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                _terminate_process_tree(process)
                break
            time.sleep(0.02)
        process.wait(timeout=5)
    except KeyboardInterrupt:
        _terminate_process_tree(process)
        process.wait(timeout=5)
        raise
    finally:
        _close_windows_job(windows_job)
        reader.join(timeout=5)
        if reader.is_alive():
            _terminate_process_tree(process)
            reader.join(timeout=2)
    output_bytes = bytes(capture)
    return ProcessResult(
        exit_code=process.returncode,
        output=output_bytes.decode("utf-8", errors="replace"),
        output_bytes=output_bytes,
        timed_out=timed_out,
        cancelled=cancelled,
        truncated=truncated,
    )


def _git(repo: Path, *args: str) -> str:
    result = _run_bounded_process(("git", *args), cwd=repo)
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.truncated
    ):
        raise ReadinessError("GIT_INSPECTION_FAILED")
    return result.output.strip()


def resolve_repo(value: str | Path | None = None) -> Path:
    candidate = (
        Path(value) if value is not None else Path(__file__).resolve().parents[2]
    ).resolve()
    try:
        root = Path(_git(candidate, "rev-parse", "--show-toplevel")).resolve()
    except OSError as error:
        raise ReadinessError("CANDIDATE_GIT_UNAVAILABLE") from error
    if root != candidate:
        raise ReadinessError("REPO_ROOT_REQUIRED")
    return root


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReadinessError("FILE_HASH_UNAVAILABLE") from error
    return f"sha256:{digest.hexdigest()}"


def _canonical_json_sha(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _runtime_declaration_sha(payload: Mapping[str, object]) -> str:
    return _canonical_json_sha(
        {"schema_version": "live-voice.s7-candidate-runtime.v1", **payload}
    )


def _product_context_ref(kind: str, value: object) -> str:
    if kind not in {"session", "correlation"}:
        raise ReadinessError("PRODUCT_CONTEXT_KIND_INVALID")
    if type(value) is not str or _PRODUCT_ID.fullmatch(value) is None:
        raise ReadinessError("PRODUCT_CONTEXT_ID_INVALID")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"product_{kind}_ref:sha256-{digest}"


def _validate_product_scope_correlations(values: object) -> dict[str, str]:
    if type(values) is not dict or set(values) != set(_TRACE_SCOPE_RULES):
        raise ReadinessError("PRODUCT_SCOPE_CORRELATIONS_INVALID")
    refs = {
        scope: _product_context_ref("correlation", values[scope])
        for scope in sorted(_TRACE_SCOPE_RULES)
    }
    if len(set(refs.values())) != len(refs):
        raise ReadinessError("PRODUCT_SCOPE_CORRELATIONS_REUSED")
    return refs


def create_product_binding(
    *, session_id: str, product_session_id: object
) -> dict[str, object]:
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    product_session_ref = _product_context_ref("session", product_session_id)
    correlations = {
        scope: f"{session_id}-{secrets.token_hex(16)}"
        for scope in sorted(_TRACE_SCOPE_RULES)
    }
    return {
        "schema_version": PRODUCT_BINDING_SCHEMA,
        "session_id": session_id,
        "product_session_ref": product_session_ref,
        "correlations": correlations,
    }


def _load_product_binding(
    path: Path, *, repo: Path, session_id: str
) -> tuple[str, dict[str, str], bytes]:
    binding, binding_bytes = _load_json_bytes(path, repo, PRODUCT_BINDING_SCHEMA)
    _exact_object(
        binding,
        {
            "schema_version",
            "session_id",
            "product_session_ref",
            "correlations",
        },
        "PRODUCT_BINDING_FIELDS_INVALID",
    )
    product_session_ref = binding["product_session_ref"]
    if (
        binding["session_id"] != session_id
        or type(product_session_ref) is not str
        or _PRODUCT_CONTEXT_REF.fullmatch(product_session_ref) is None
        or not product_session_ref.startswith("product_session_ref:")
    ):
        raise ReadinessError("PRODUCT_BINDING_IDENTITY_MISMATCH")
    refs = _validate_product_scope_correlations(binding["correlations"])
    return product_session_ref, refs, binding_bytes


def _path_ref(prefix: str, path: Path, *, no_remote: bool = False) -> str:
    normalized = str(path.resolve()).replace("\\", "/").casefold().encode("utf-8")
    suffix = ":no_remote" if no_remote else ""
    return f"{prefix}_ref:sha256-{hashlib.sha256(normalized).hexdigest()}{suffix}"


def _ensure_external(path: Path, repo: Path, *, must_exist: bool) -> Path:
    try:
        resolved = path.resolve(strict=must_exist)
    except OSError as error:
        raise ReadinessError("PRIVATE_FILE_UNAVAILABLE") from error
    try:
        resolved.relative_to(repo)
    except ValueError:
        return resolved
    raise ReadinessError("PRIVATE_FILE_INSIDE_CANDIDATE")


def _load_json_bytes(
    path: Path, repo: Path, schema: str
) -> tuple[dict[str, object], bytes]:
    resolved = _ensure_external(path, repo, must_exist=True)
    if not resolved.is_file():
        raise ReadinessError("PRIVATE_INPUT_NOT_FILE")
    try:
        with resolved.open("rb") as stream:
            raw = stream.read(_MAX_JSON_BYTES + 1)
        if not 0 < len(raw) <= _MAX_JSON_BYTES:
            raise ReadinessError("PRIVATE_INPUT_SIZE_INVALID")
        payload = json.loads(raw.decode("utf-8"))
    except ReadinessError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReadinessError("PRIVATE_INPUT_INVALID_JSON") from error
    if type(payload) is not dict or payload.get("schema_version") != schema:
        raise ReadinessError("PRIVATE_INPUT_SCHEMA_MISMATCH")
    return payload, raw


def _load_json(path: Path, repo: Path, schema: str) -> dict[str, object]:
    return _load_json_bytes(path, repo, schema)[0]


def _write_json(path: Path, repo: Path, payload: object, *, overwrite: bool) -> None:
    resolved = _ensure_external(path, repo, must_exist=False)
    if resolved.exists() and not overwrite:
        raise ReadinessError("PRIVATE_OUTPUT_ALREADY_EXISTS")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    resolved.write_text(rendered, encoding="utf-8")


def _exact_object(value: object, fields: set[str], reason: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ReadinessError(reason)
    return value


def _safe_string(value: object, reason: str, *, maximum: int = 128) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value.strip() != value
        or not value.isprintable()
        or _PRIVATE_PATH.search(value)
        or _ABSOLUTE_PATH.search(value)
        or _SECRET.search(value)
    ):
        raise ReadinessError(reason)
    return value


def _validate_s7_report(payload: dict[str, object]) -> dict[str, object]:
    _exact_object(
        payload,
        {
            "schema_version",
            "generated_at",
            "not_a_gate",
            "candidate",
            "runtime_declaration",
            "automation_status",
            "real_path_status",
            "s7_readiness",
            "checks",
        },
        "S7_REPORT_FIELDS_INVALID",
    )
    if payload["not_a_gate"] is not True:
        raise ReadinessError("S7_REPORT_GATE_SEMANTICS_INVALID")
    if payload["automation_status"] != "PASS":
        raise ReadinessError("S7_AUTOMATION_INCOMPLETE")
    if payload["real_path_status"] != "VERIFY":
        raise ReadinessError("S7_REAL_PATH_INCOMPLETE")
    if payload["s7_readiness"] != "READY_FOR_S7_CUMULATIVE_REVIEW":
        raise ReadinessError("S7_READINESS_INCOMPLETE")
    candidate = _exact_object(
        payload["candidate"],
        {
            "head",
            "branch",
            "comparison_base",
            "upstream",
            "upstream_head",
            "ahead",
            "behind",
            "clean",
            "dependency_sha256",
            "generated_artifact_state",
            "python",
            "node",
            "npm",
            "uv",
            "platform",
        },
        "S7_CANDIDATE_FIELDS_INVALID",
    )
    if (
        type(candidate["head"]) is not str
        or _FULL_SHA.fullmatch(candidate["head"]) is None
        or type(candidate["comparison_base"]) is not str
        or _FULL_SHA.fullmatch(candidate["comparison_base"]) is None
        or candidate["clean"] is not True
        or type(candidate["branch"]) is not str
        or not candidate["branch"]
        or type(candidate["upstream"]) is not str
        or not candidate["upstream"]
        or type(candidate["upstream_head"]) is not str
        or _FULL_SHA.fullmatch(candidate["upstream_head"]) is None
        or type(candidate["ahead"]) is not int
        or type(candidate["behind"]) is not int
        or candidate["behind"] != 0
    ):
        raise ReadinessError("S7_CANDIDATE_IDENTITY_INVALID")
    dependencies = candidate["dependency_sha256"]
    if type(dependencies) is not dict or not dependencies:
        raise ReadinessError("S7_DEPENDENCY_IDENTITY_INVALID")
    for relative, digest in dependencies.items():
        if (
            type(relative) is not str
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or type(digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ReadinessError("S7_DEPENDENCY_IDENTITY_INVALID")
    generated = _exact_object(
        candidate["generated_artifact_state"],
        {"policy", "tracked_count", "tracked_sha256"},
        "S7_GENERATED_ARTIFACT_STATE_INVALID",
    )
    if (
        generated["policy"] != "generated-output-excluded-from-candidate"
        or type(generated["tracked_count"]) is not str
        or not generated["tracked_count"].isdecimal()
        or type(generated["tracked_sha256"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", generated["tracked_sha256"]) is None
    ):
        raise ReadinessError("S7_GENERATED_ARTIFACT_STATE_INVALID")
    runtime = _exact_object(
        payload["runtime_declaration"],
        {"candidate_head", "comparison_base", "feature_flags", "runtime_labels"},
        "S7_RUNTIME_DECLARATION_INVALID",
    )
    if (
        runtime["candidate_head"] != candidate["head"]
        or runtime["comparison_base"] != candidate["comparison_base"]
        or type(runtime["feature_flags"]) is not dict
        or not runtime["feature_flags"]
        or type(runtime["runtime_labels"]) is not dict
        or not runtime["runtime_labels"]
    ):
        raise ReadinessError("S7_RUNTIME_DECLARATION_INVALID")
    for name, value in runtime["feature_flags"].items():
        if (
            type(name) is not str
            or not name
            or len(name) > 128
            or type(value) is not str
            or value not in {"true", "false", "unset"}
        ):
            raise ReadinessError("S7_FLAG_DECLARATION_INVALID")
    for name, value in runtime["runtime_labels"].items():
        if type(name) is not str or not name or len(name) > 64:
            raise ReadinessError("S7_RUNTIME_DECLARATION_INVALID")
        _safe_string(value, "S7_RUNTIME_LABEL_PRIVATE", maximum=128)
    checks = payload["checks"]
    if type(checks) is not list:
        raise ReadinessError("S7_CHECK_SET_INVALID")
    verified_real: set[str] = set()
    for raw in checks:
        if type(raw) is not dict:
            raise ReadinessError("S7_CHECK_SET_INVALID")
        if raw.get("category") == "real-path" and raw.get("status") == "VERIFY":
            check_id = raw.get("check_id")
            if type(check_id) is str:
                verified_real.add(check_id)
    if verified_real != REQUIRED_REAL_CHECKS:
        raise ReadinessError("S7_REAL_CHECK_SET_INCOMPLETE")
    return {"candidate": candidate, "runtime": runtime}


def _validate_handoff(
    payload: dict[str, object],
    *,
    report_bytes: bytes,
    candidate: Mapping[str, object],
    runtime: Mapping[str, object],
) -> None:
    _exact_object(
        payload,
        {
            "schema_version",
            "candidate_head",
            "comparison_base",
            "s7_report_sha256",
            "runtime_declaration_sha256",
            "s7_03_review",
            "s7_04_status",
            "known_deviation_ids",
            "reused_human_observation_ids",
        },
        "S7_HANDOFF_FIELDS_INVALID",
    )
    if (
        payload["candidate_head"] != candidate["head"]
        or payload["comparison_base"] != candidate["comparison_base"]
        or payload["s7_report_sha256"] != _sha256_bytes(report_bytes)
        or payload["runtime_declaration_sha256"] != _runtime_declaration_sha(runtime)
    ):
        raise ReadinessError("S7_HANDOFF_BINDING_MISMATCH")
    if payload["s7_03_review"] != "PASS" or payload["s7_04_status"] != "FROZEN_FOR_A3":
        raise ReadinessError("S7_HANDOFF_NOT_FROZEN")
    for field in ("known_deviation_ids", "reused_human_observation_ids"):
        values = payload[field]
        if type(values) is not list or len(values) > 64:
            raise ReadinessError("S7_HANDOFF_REFERENCE_SET_INVALID")
        seen: set[str] = set()
        for value in values:
            safe = _safe_string(value, "S7_HANDOFF_REFERENCE_INVALID", maximum=96)
            if _SAFE_ID.fullmatch(safe) is None or safe in seen:
                raise ReadinessError("S7_HANDOFF_REFERENCE_INVALID")
            seen.add(safe)


def _candidate_snapshot(
    repo: Path, candidate: Mapping[str, object]
) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    upstream = _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}")
    upstream_head = _git(repo, "rev-parse", "@{upstream}")
    counts = _git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    try:
        ahead_text, behind_text = counts.split()
        ahead, behind = int(ahead_text), int(behind_text)
    except (ValueError, TypeError) as error:
        raise ReadinessError("CANDIDATE_UPSTREAM_RELATION_INVALID") from error
    dependencies = candidate["dependency_sha256"]
    assert isinstance(dependencies, dict)
    observed_hashes: dict[str, str] = {}
    for relative in dependencies:
        path = (repo / str(relative)).resolve()
        try:
            path.relative_to(repo)
        except ValueError as error:
            raise ReadinessError("DEPENDENCY_PATH_ESCAPES_CANDIDATE") from error
        if not path.is_file():
            raise ReadinessError("CANDIDATE_DEPENDENCY_MISSING")
        observed_hashes[str(relative)] = _sha256_file(path).removeprefix("sha256:")
    tracked = sorted(
        value
        for value in _git(
            repo, "ls-files", "--", *_GENERATED_ARTIFACT_PATHS
        ).splitlines()
        if value
    )
    generated_digest = hashlib.sha256()
    for relative in tracked:
        generated_digest.update(relative.encode("utf-8"))
        generated_digest.update(b"\0")
        generated_digest.update(bytes.fromhex(_sha256_file(repo / relative)[7:]))
    snapshot = {
        "head": head,
        "branch": branch,
        "upstream": upstream,
        "upstream_head": upstream_head,
        "ahead": ahead,
        "behind": behind,
        "clean": not status,
        "dependency_sha256": observed_hashes,
        "generated_artifact_state": {
            "policy": "generated-output-excluded-from-candidate",
            "tracked_count": str(len(tracked)),
            "tracked_sha256": generated_digest.hexdigest(),
        },
    }
    expected = {name: candidate[name] for name in snapshot}
    if snapshot != expected:
        raise ReadinessError("CANDIDATE_IDENTITY_MISMATCH")
    return snapshot


def _validate_flags(runtime: Mapping[str, object], env: Mapping[str, str]) -> None:
    flags = runtime["feature_flags"]
    assert isinstance(flags, dict)
    for name, expected in flags.items():
        if (
            type(name) is not str
            or type(expected) is not str
            or expected not in {"true", "false", "unset"}
        ):
            raise ReadinessError("S7_FLAG_DECLARATION_INVALID")
        if expected == "unset":
            if name in env:
                raise ReadinessError("FEATURE_FLAG_MISMATCH")
        elif env.get(name) != expected:
            raise ReadinessError("FEATURE_FLAG_MISMATCH")


def _private_origin_ref(raw: str) -> str:
    try:
        parsed = urlparse(raw)
        port = parsed.port or 443
    except ValueError as error:
        raise ReadinessError("PRIVATE_ORIGIN_INVALID") from error
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or hostname != hostname.lower()
        or not hostname.isascii()
        or not raw.isascii()
        or hostname in {"localhost", "127.0.0.1", "::1"}
        or hostname.endswith(".localhost")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port != 443
        or parsed.netloc != hostname
        or "." not in hostname
    ):
        raise ReadinessError("PRIVATE_ORIGIN_INVALID")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ReadinessError("PRIVATE_ORIGIN_INVALID")
    return (
        f"private_origin_ref:sha256-{hashlib.sha256(raw.encode('ascii')).hexdigest()}"
    )


def _validate_private_origin_addresses(raw: str) -> None:
    hostname = urlparse(raw).hostname
    if hostname is None:
        raise ReadinessError("PRIVATE_ORIGIN_INVALID")
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as error:
        raise ReadinessError("PRIVATE_ORIGIN_DNS_UNAVAILABLE") from error
    if not addresses or any(
        not address.is_private
        or address.is_multicast
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        for address in addresses
    ):
        raise ReadinessError("PUBLIC_ORIGIN_REJECTED")


def _validate_runtime_environment(
    runtime: Mapping[str, object], env: Mapping[str, str]
) -> None:
    labels = runtime["runtime_labels"]
    assert isinstance(labels, dict)
    for label, env_name in RUNTIME_ENV_BY_LABEL.items():
        if label not in labels or env.get(env_name) != labels[label]:
            raise ReadinessError("RUNTIME_ROUTE_MISMATCH")
    origin = env.get("S7_PRIVATE_ORIGIN", "")
    if labels.get("origin") != _private_origin_ref(origin):
        raise ReadinessError("PRIVATE_ORIGIN_MISMATCH")
    _validate_private_origin_addresses(origin)
    for name in PRIVATE_PRESENCE_ENV:
        value = env.get(name)
        if type(value) is not str or not 8 <= len(value) <= 4096:
            raise ReadinessError("REQUIRED_PRIVATE_INPUT_MISSING")


def _is_broad_or_protected(path: Path, repo: Path) -> bool:
    resolved = path.resolve()
    repo = repo.resolve()
    home = Path.home().resolve()
    protected = {repo, home, Path(resolved.anchor).resolve()}
    if resolved in protected:
        return True
    return (
        resolved in repo.parents or resolved in home.parents or repo in resolved.parents
    )


def _fixture_marker(root: Path) -> dict[str, object]:
    marker = root / ".live-voice-s8-fixture.json"
    if not marker.is_file():
        raise ReadinessError("FIXTURE_MARKER_MISSING")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReadinessError("FIXTURE_MARKER_INVALID") from error
    return _exact_object(
        payload,
        {"schema_version", "session_id", "fixture_ref", "creation_ref"},
        "FIXTURE_MARKER_INVALID",
    )


def _validate_fixture(
    root: Path,
    *,
    repo: Path,
    session_id: str,
    expected_ref: object,
    require_clean: bool,
) -> dict[str, object]:
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise ReadinessError("FIXTURE_UNAVAILABLE") from error
    if not root.is_dir() or _is_broad_or_protected(root, repo):
        raise ReadinessError("FIXTURE_TARGET_REJECTED")
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    except ReadinessError as error:
        raise ReadinessError("FIXTURE_NOT_GIT_ROOT") from error
    if top != root or _git(root, "remote"):
        raise ReadinessError("FIXTURE_NOT_DISPOSABLE_NO_REMOTE")
    candidate_common = Path(_git(repo, "rev-parse", "--git-common-dir"))
    fixture_common = Path(_git(root, "rev-parse", "--git-common-dir"))
    if not candidate_common.is_absolute():
        candidate_common = (repo / candidate_common).resolve()
    if not fixture_common.is_absolute():
        fixture_common = (root / fixture_common).resolve()
    if candidate_common.resolve() == fixture_common.resolve():
        raise ReadinessError("FIXTURE_USES_CANDIDATE_GIT")
    fixture_ref = _path_ref("disposable_git", root, no_remote=True)
    if fixture_ref != expected_ref:
        raise ReadinessError("FIXTURE_REFERENCE_MISMATCH")
    marker = _fixture_marker(root)
    if (
        marker["schema_version"] != FIXTURE_MARKER_SCHEMA
        or marker["session_id"] != session_id
        or marker["fixture_ref"] != fixture_ref
        or type(marker["creation_ref"]) is not str
        or _SHA256.fullmatch(marker["creation_ref"]) is None
    ):
        raise ReadinessError("FIXTURE_MARKER_MISMATCH")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if require_clean and status:
        raise ReadinessError("FIXTURE_INITIAL_STATE_DIRTY")
    return {
        "root": root,
        "fixture_ref": fixture_ref,
        "creation_ref": marker["creation_ref"],
    }


def _validate_isolated_state(
    runtime: Mapping[str, object],
    env: Mapping[str, str],
    *,
    repo: Path,
    session_id: str,
    require_clean_fixture: bool,
) -> dict[str, object]:
    labels = runtime["runtime_labels"]
    assert isinstance(labels, dict)
    data_raw = env.get("JIUWENSWARM_DATA_DIR")
    store_raw = env.get("S8_TASK_STORE_PATH")
    fixture_raw = env.get("S8_DISPOSABLE_PROJECT_ROOT")
    if not data_raw or not store_raw or not fixture_raw:
        raise ReadinessError("ISOLATED_STATE_INPUT_MISSING")
    data = Path(data_raw)
    store = Path(store_raw)
    fixture = Path(fixture_raw)
    if not data.is_absolute() or not store.is_absolute() or not fixture.is_absolute():
        raise ReadinessError("ISOLATED_STATE_PATH_NOT_ABSOLUTE")
    try:
        data = data.resolve(strict=True)
        store = store.resolve(strict=True)
    except OSError as error:
        raise ReadinessError("ISOLATED_STATE_UNAVAILABLE") from error
    if not data.is_dir() or not store.is_file() or _is_broad_or_protected(data, repo):
        raise ReadinessError("ISOLATED_STATE_TARGET_REJECTED")
    try:
        store.relative_to(data)
    except ValueError as error:
        raise ReadinessError("TASK_STORE_NOT_ISOLATED") from error
    if _path_ref("data", data) != labels.get("data_fixture"):
        raise ReadinessError("DATA_REFERENCE_MISMATCH")
    fixture_info = _validate_fixture(
        fixture,
        repo=repo,
        session_id=session_id,
        expected_ref=labels.get("project_fixture"),
        require_clean=require_clean_fixture,
    )
    return {"data": data, "store": store, **fixture_info}


def _port_from_env(env: Mapping[str, str], name: str) -> int:
    raw = env.get(name)
    if type(raw) is not str or not raw.isascii() or not raw.isdecimal():
        raise ReadinessError("SERVICE_PORT_DECLARATION_MISSING")
    port = int(raw)
    if not 1024 <= port <= 65535:
        raise ReadinessError("SERVICE_PORT_DECLARATION_INVALID")
    return port


def _port_open(host: str, port: int, *, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _receive_private_connection_ack(origin: str) -> None:
    try:
        import websockets
    except ImportError as error:
        raise ReadinessError("PRIVATE_ROUTE_DIAGNOSTIC_UNAVAILABLE") from error

    websocket_url = origin.replace("https://", "wss://", 1) + "/ws"
    try:
        async with websockets.connect(
            websocket_url,
            origin=origin,
            open_timeout=5,
            close_timeout=2,
            max_size=_MAX_JSON_BYTES,
        ) as connection:
            raw = await asyncio.wait_for(connection.recv(), timeout=5)
    except Exception as error:  # noqa: BLE001 - no endpoint detail is exposed
        raise ReadinessError("PRIVATE_ROUTE_CONNECTION_ACK_MISSING") from error
    if type(raw) is not str or len(raw.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ReadinessError("PRIVATE_ROUTE_CONNECTION_ACK_INVALID")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ReadinessError("PRIVATE_ROUTE_CONNECTION_ACK_INVALID") from error
    if (
        type(payload) is not dict
        or payload.get("type") != "event"
        or payload.get("event") != "connection.ack"
    ):
        raise ReadinessError("PRIVATE_ROUTE_CONNECTION_ACK_INVALID")


def _csp_allows_private_websocket(csp: str, hostname: str) -> bool:
    connect_sources: set[str] | None = None
    for raw_directive in csp.split(";"):
        parts = raw_directive.strip().split()
        if not parts or parts[0].casefold() != "connect-src":
            continue
        if connect_sources is not None:
            return False
        connect_sources = {part.casefold() for part in parts[1:]}
    if not connect_sources or "'none'" in connect_sources or "*" in connect_sources:
        return False
    host = hostname.casefold()
    return bool(
        {"'self'", "wss:", f"wss://{host}", f"wss://{host}:443"} & connect_sources
    )


def _validate_private_route(origin: str) -> None:
    parsed = urlparse(origin)
    hostname = parsed.hostname
    if hostname is None:
        raise ReadinessError("PRIVATE_ORIGIN_INVALID")
    connection = http.client.HTTPSConnection(
        hostname, 443, timeout=5, context=ssl.create_default_context()
    )
    try:
        connection.request("GET", "/", headers={"Accept": "text/html"})
        response = connection.getresponse()
        response.read(1024)
        csp = response.getheader("Content-Security-Policy", "")
        allow_origin = response.getheader("Access-Control-Allow-Origin", "")
    except (OSError, ssl.SSLError, http.client.HTTPException) as error:
        raise ReadinessError("PRIVATE_HTTPS_ROUTE_UNAVAILABLE") from error
    finally:
        connection.close()
    if not 200 <= response.status < 400:
        raise ReadinessError("PRIVATE_HTTPS_ROUTE_UNAVAILABLE")
    if not _csp_allows_private_websocket(csp, hostname) or allow_origin.strip() == "*":
        raise ReadinessError("PRIVATE_ROUTE_SECURITY_HEADERS_INVALID")
    try:
        asyncio.run(_receive_private_connection_ack(origin))
    except RuntimeError as error:
        raise ReadinessError("PRIVATE_ROUTE_DIAGNOSTIC_UNAVAILABLE") from error


def _validate_services(
    env: Mapping[str, str], *, expect_open: bool
) -> list[dict[str, object]]:
    services: list[dict[str, object]] = []
    for service, env_name in SERVICE_PORT_ENV.items():
        port = _port_from_env(env, env_name)
        opened = _port_open("127.0.0.1", port)
        if opened is not expect_open:
            raise ReadinessError(
                "SERVICE_NOT_READY" if expect_open else "SERVICE_NOT_RELEASED"
            )
        services.append({"service": service, "port": port, "open": opened})
    if expect_open:
        origin = env.get("S7_PRIVATE_ORIGIN", "")
        hostname = urlparse(origin).hostname
        if not hostname or not _port_open(hostname, 443):
            raise ReadinessError("PRIVATE_ORIGIN_NOT_READY")
        _validate_private_route(origin)
    return services


def _process_ref(pid: int) -> str:
    try:
        import psutil

        process = psutil.Process(pid)
        material = json.dumps(
            {
                "pid": pid,
                "created": f"{process.create_time():.6f}",
                "name": process.name(),
                "executable": process.exe(),
                "cwd": process.cwd(),
                "command": process.cmdline(),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except Exception as error:  # noqa: BLE001 - no private exception is exposed
        raise ReadinessError("PROCESS_IDENTITY_UNAVAILABLE") from error
    return f"process_ref:sha256-{hashlib.sha256(material).hexdigest()}"


def _capture_service_processes(
    env: Mapping[str, str], *, repo: Path, candidate_head: str
) -> list[dict[str, object]]:
    try:
        import psutil

        listeners = psutil.net_connections(kind="tcp")
    except Exception as error:  # noqa: BLE001
        raise ReadinessError("PROCESS_LISTENER_INSPECTION_UNAVAILABLE") from error
    result: list[dict[str, object]] = []
    for service, env_name in SERVICE_PORT_ENV.items():
        port = _port_from_env(env, env_name)
        pids = {
            item.pid
            for item in listeners
            if item.status == "LISTEN"
            and item.laddr
            and item.laddr.port == port
            and item.pid
        }
        if len(pids) != 1:
            raise ReadinessError("SERVICE_PROCESS_IDENTITY_AMBIGUOUS")
        pid = pids.pop()
        try:
            process = psutil.Process(pid)
            cwd = Path(process.cwd()).resolve()
            cwd.relative_to(repo)
        except (OSError, ValueError, psutil.Error) as error:
            raise ReadinessError("SERVICE_PROCESS_OUTSIDE_CANDIDATE") from error
        result.append(
            {
                "service": service,
                "port": port,
                "pid": pid,
                "process_ref": _process_ref(pid),
                "candidate_head": candidate_head,
            }
        )
    return result


def _load_bound_inputs(
    repo: Path, s7_report_path: Path, handoff_path: Path
) -> tuple[dict[str, object], dict[str, object], dict[str, object], bytes]:
    report, report_bytes = _load_json_bytes(s7_report_path, repo, S7_REPORT_SCHEMA)
    context = _validate_s7_report(report)
    handoff = _load_json(handoff_path, repo, S7_HANDOFF_SCHEMA)
    _validate_handoff(
        handoff,
        report_bytes=report_bytes,
        candidate=context["candidate"],
        runtime=context["runtime"],
    )
    return report, handoff, context, report_bytes


def draft_handoff(*, repo: Path, s7_report_path: Path) -> dict[str, object]:
    report, report_bytes = _load_json_bytes(s7_report_path, repo, S7_REPORT_SCHEMA)
    context = _validate_s7_report(report)
    candidate = context["candidate"]
    runtime = context["runtime"]
    assert isinstance(candidate, dict) and isinstance(runtime, dict)
    return {
        "schema_version": S7_HANDOFF_SCHEMA,
        "candidate_head": candidate["head"],
        "comparison_base": candidate["comparison_base"],
        "s7_report_sha256": _sha256_bytes(report_bytes),
        "runtime_declaration_sha256": _runtime_declaration_sha(runtime),
        "s7_03_review": "BLOCKED",
        "s7_04_status": "NOT_FROZEN",
        "known_deviation_ids": [],
        "reused_human_observation_ids": [],
    }


def resource_refs(
    *, repo: Path, session_id: str, env: Mapping[str, str]
) -> dict[str, str]:
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    data_raw = env.get("JIUWENSWARM_DATA_DIR")
    fixture_raw = env.get("S8_DISPOSABLE_PROJECT_ROOT")
    if not data_raw or not fixture_raw:
        raise ReadinessError("ISOLATED_STATE_INPUT_MISSING")
    data = Path(data_raw)
    fixture = Path(fixture_raw)
    if not data.is_absolute() or not fixture.is_absolute():
        raise ReadinessError("ISOLATED_STATE_PATH_NOT_ABSOLUTE")
    try:
        data = data.resolve(strict=True)
    except OSError as error:
        raise ReadinessError("ISOLATED_STATE_UNAVAILABLE") from error
    if not data.is_dir() or _is_broad_or_protected(data, repo):
        raise ReadinessError("ISOLATED_STATE_TARGET_REJECTED")
    fixture_ref = _path_ref("disposable_git", fixture, no_remote=True)
    _validate_fixture(
        fixture,
        repo=repo,
        session_id=session_id,
        expected_ref=fixture_ref,
        require_clean=True,
    )
    return {
        "data_fixture": _path_ref("data", data),
        "project_fixture": fixture_ref,
    }


def run_preflight(
    *,
    repo: Path,
    s7_report_path: Path,
    handoff_path: Path,
    session_id: str,
    env: Mapping[str, str],
) -> dict[str, object]:
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    checks: list[dict[str, object]] = []
    before: dict[str, object] | None = None
    context: dict[str, object] | None = None
    try:
        _, handoff, context, _ = _load_bound_inputs(repo, s7_report_path, handoff_path)
        checks.append({"id": "s7-handoff-binding", "status": "VERIFY"})
        candidate = context["candidate"]
        runtime = context["runtime"]
        assert isinstance(candidate, dict) and isinstance(runtime, dict)
        before = _candidate_snapshot(repo, candidate)
        checks.append({"id": "candidate-identity-before", "status": "VERIFY"})
        _validate_flags(runtime, env)
        checks.append({"id": "candidate-feature-flags", "status": "VERIFY"})
        _validate_runtime_environment(runtime, env)
        checks.append({"id": "runtime-route-and-private-presence", "status": "VERIFY"})
        _validate_isolated_state(
            runtime,
            env,
            repo=repo,
            session_id=session_id,
            require_clean_fixture=True,
        )
        checks.append({"id": "isolated-runtime-store-project", "status": "VERIFY"})
        services = _validate_services(env, expect_open=True)
        processes = _capture_service_processes(
            env, repo=repo, candidate_head=str(candidate["head"])
        )
        checks.append(
            {
                "id": "service-and-route-listeners",
                "status": "VERIFY",
                "listener_count": len(services) + 1,
                "candidate_process_count": len(processes),
            }
        )
        after = _candidate_snapshot(repo, candidate)
        if after != before:
            raise ReadinessError("CANDIDATE_CHANGED_AFTER_CHECK")
        checks.append({"id": "candidate-identity-after", "status": "VERIFY"})
        return {
            "schema_version": PREFLIGHT_REPORT_SCHEMA,
            "not_alpha_acceptance": True,
            "session_id": session_id,
            "candidate_head": handoff["candidate_head"],
            "runtime_declaration_sha256": handoff["runtime_declaration_sha256"],
            "status": "AUTOMATED_PREFLIGHT_VERIFIED",
            "checks": checks,
            "operator_required": [
                "S8-01.TEXT_TOOL_SMOKE",
                "S8-01.PROVIDER_DEVICE_PROBE",
                "S8-02.COMPLETE_HUMAN_SHOWCASE",
                "S8-03.USER_DECISION",
            ],
        }
    except ReadinessError as error:
        checks.append(
            {
                "id": "preflight-fail-closed",
                "status": "BLOCKED",
                "reason": error.reason_code,
            }
        )
        candidate_head = None
        runtime_sha = None
        if context is not None:
            candidate = context.get("candidate")
            runtime = context.get("runtime")
            if isinstance(candidate, dict):
                candidate_head = candidate.get("head")
            if isinstance(runtime, dict):
                runtime_sha = _runtime_declaration_sha(runtime)
        return {
            "schema_version": PREFLIGHT_REPORT_SCHEMA,
            "not_alpha_acceptance": True,
            "session_id": session_id,
            "candidate_head": candidate_head,
            "runtime_declaration_sha256": runtime_sha,
            "status": "BLOCKED",
            "checks": checks,
            "operator_required": [],
        }


def init_fixture(*, repo: Path, root: Path, session_id: str, execute: bool) -> str:
    if not execute:
        raise ReadinessError("FIXTURE_INIT_REQUIRES_EXECUTE")
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    if not root.is_absolute() or _FIXTURE_NAME.fullmatch(root.name) is None:
        raise ReadinessError("FIXTURE_TARGET_REJECTED")
    root = root.resolve()
    if root.exists() or not root.parent.is_dir() or _is_broad_or_protected(root, repo):
        raise ReadinessError("FIXTURE_TARGET_REJECTED")
    created = False
    try:
        root.mkdir()
        created = True
        (root / "notes.txt").write_text("baseline\n", encoding="utf-8")
        marker_path = root / ".live-voice-s8-fixture.json"
        fixture_ref = _path_ref("disposable_git", root, no_remote=True)
        marker = {
            "schema_version": FIXTURE_MARKER_SCHEMA,
            "session_id": session_id,
            "fixture_ref": fixture_ref,
            "creation_ref": _sha256_bytes(
                f"{session_id}|{fixture_ref}".encode("utf-8")
            ),
        }
        marker_path.write_text(
            json.dumps(marker, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _git(root, "init", "--initial-branch=main")
        _git(root, "add", "notes.txt", ".live-voice-s8-fixture.json")
        _git(
            root,
            "-c",
            "user.name=Live Voice Fixture",
            "-c",
            "user.email=live-voice-fixture.invalid",
            "commit",
            "-m",
            "chore: initialize disposable Live Voice fixture",
        )
        if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ReadinessError("FIXTURE_INIT_NOT_CLEAN")
        return fixture_ref
    except Exception:
        if created and root.exists():
            _remove_owned_tree(root)
        raise


def _fixture_git_bytes(root: Path, *args: str) -> bytes:
    result = _run_bounded_process(("git", *args), cwd=root)
    if (
        result.exit_code != 0
        or result.timed_out
        or result.cancelled
        or result.truncated
    ):
        raise ReadinessError("FIXTURE_EFFECT_UNAVAILABLE")
    return result.output_bytes


def _fixture_changed_paths(root: Path) -> list[str]:
    raw_paths = [
        *_fixture_git_bytes(root, "diff", "--name-only", "-z", "HEAD", "--").split(
            b"\0"
        ),
        *_fixture_git_bytes(
            root, "ls-files", "--others", "--exclude-standard", "-z", "--"
        ).split(b"\0"),
    ]
    paths: set[str] = set()
    for raw in raw_paths:
        if not raw:
            continue
        try:
            value = raw.decode("utf-8")
        except UnicodeError as error:
            raise ReadinessError("FIXTURE_PATH_ENCODING_INVALID") from error
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or not value.isprintable():
            raise ReadinessError("FIXTURE_PROJECT_PATH_INVALID")
        paths.add(value.replace("\\", "/"))
        if len(paths) > 32:
            raise ReadinessError("FIXTURE_EFFECT_TOO_LARGE")
    return sorted(paths)


def _fixture_diff_sha(root: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"tracked\0")
    digest.update(
        _fixture_git_bytes(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    )
    untracked = _fixture_git_bytes(
        root, "ls-files", "--others", "--exclude-standard", "-z", "--"
    ).split(b"\0")
    untracked = [value for value in untracked if value]
    if len(untracked) > 32:
        raise ReadinessError("FIXTURE_EFFECT_TOO_LARGE")
    total_bytes = 0
    for raw in sorted(untracked):
        try:
            relative = raw.decode("utf-8")
        except UnicodeError as error:
            raise ReadinessError("FIXTURE_PATH_ENCODING_INVALID") from error
        path = (root / relative).resolve(strict=False)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ReadinessError("FIXTURE_PROJECT_PATH_INVALID") from error
        digest.update(b"untracked\0")
        digest.update(raw)
        digest.update(b"\0")
        source = root / relative
        if source.is_symlink():
            try:
                digest.update(b"symlink\0")
                digest.update(os.readlink(source).encode("utf-8"))
            except (OSError, UnicodeError) as error:
                raise ReadinessError("FIXTURE_EFFECT_UNAVAILABLE") from error
        elif source.is_file():
            try:
                size = source.stat().st_size
                total_bytes += size
                if (
                    size > _MAX_FIXTURE_FILE_BYTES
                    or total_bytes > _MAX_FIXTURE_TOTAL_BYTES
                ):
                    raise ReadinessError("FIXTURE_FILE_TOO_LARGE")
                digest.update(b"file\0")
                with source.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except ReadinessError:
                raise
            except OSError as error:
                raise ReadinessError("FIXTURE_EFFECT_UNAVAILABLE") from error
        else:
            raise ReadinessError("FIXTURE_EFFECT_UNAVAILABLE")
    return f"sha256:{digest.hexdigest()}"


def _validated_project_paths(value: object) -> list[str]:
    if type(value) is not list or len(value) > 32:
        raise ReadinessError("SESSION_PROJECT_EFFECT_INVALID")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if (
            type(raw) is not str
            or raw in seen
            or len(raw) > 512
            or not raw.isprintable()
            or Path(raw).is_absolute()
            or ".." in Path(raw).parts
            or not raw
        ):
            raise ReadinessError("SESSION_PROJECT_PATH_INVALID")
        normalized = raw.replace("\\", "/")
        if normalized != raw:
            raise ReadinessError("SESSION_PROJECT_PATH_INVALID")
        seen.add(raw)
        result.append(raw)
    return sorted(result)


def plan_fixture_effect(
    *,
    repo: Path,
    session_id: str,
    expected_changed_paths: Sequence[str],
    env: Mapping[str, str],
) -> dict[str, object]:
    expected = _validated_project_paths(list(expected_changed_paths))
    fixture_raw = env.get("S8_DISPOSABLE_PROJECT_ROOT")
    if not fixture_raw or not Path(fixture_raw).is_absolute():
        raise ReadinessError("ISOLATED_STATE_INPUT_MISSING")
    fixture = Path(fixture_raw)
    fixture_ref = _path_ref("disposable_git", fixture, no_remote=True)
    state = _validate_fixture(
        fixture,
        repo=repo,
        session_id=session_id,
        expected_ref=fixture_ref,
        require_clean=True,
    )
    return {
        "schema_version": EFFECT_PLAN_SCHEMA,
        "session_id": session_id,
        "fixture_ref": state["fixture_ref"],
        "base_head": _git(state["root"], "rev-parse", "HEAD"),
        "expected_changed_paths": expected,
        "declared_before_mutation": True,
    }


def _load_effect_plan(
    path: Path, *, repo: Path, session_id: str, fixture_ref: object
) -> tuple[dict[str, object], bytes]:
    plan, plan_bytes = _load_json_bytes(path, repo, EFFECT_PLAN_SCHEMA)
    _exact_object(
        plan,
        {
            "schema_version",
            "session_id",
            "fixture_ref",
            "base_head",
            "expected_changed_paths",
            "declared_before_mutation",
        },
        "FIXTURE_EFFECT_PLAN_INVALID",
    )
    if (
        plan["session_id"] != session_id
        or plan["fixture_ref"] != fixture_ref
        or type(plan["base_head"]) is not str
        or _FULL_SHA.fullmatch(plan["base_head"]) is None
        or plan["declared_before_mutation"] is not True
    ):
        raise ReadinessError("FIXTURE_EFFECT_PLAN_INVALID")
    if (
        _validated_project_paths(plan["expected_changed_paths"])
        != plan["expected_changed_paths"]
    ):
        raise ReadinessError("FIXTURE_EFFECT_PLAN_INVALID")
    return plan, plan_bytes


def inspect_fixture_effect(
    *, repo: Path, session_id: str, env: Mapping[str, str]
) -> dict[str, object]:
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    fixture_raw = env.get("S8_DISPOSABLE_PROJECT_ROOT")
    if not fixture_raw or not Path(fixture_raw).is_absolute():
        raise ReadinessError("ISOLATED_STATE_INPUT_MISSING")
    fixture = Path(fixture_raw)
    fixture_ref = _path_ref("disposable_git", fixture, no_remote=True)
    state = _validate_fixture(
        fixture,
        repo=repo,
        session_id=session_id,
        expected_ref=fixture_ref,
        require_clean=False,
    )
    return {
        "fixture_ref": state["fixture_ref"],
        "observed_head": _git(state["root"], "rev-parse", "HEAD"),
        "observed_changed_paths": _fixture_changed_paths(state["root"]),
        "diff_sha256": _fixture_diff_sha(state["root"]),
    }


def capture_trace_manifest(
    *,
    repo: Path,
    s7_report_path: Path,
    handoff_path: Path,
    product_binding_path: Path,
    record_path: Path,
    product_trace_path: Path,
) -> dict[str, object]:
    _, handoff, _context, _ = _load_bound_inputs(repo, s7_report_path, handoff_path)
    record = _load_json(record_path, repo, SESSION_SCHEMA)
    _validate_session_record(
        record,
        expected_candidate=str(handoff["candidate_head"]),
        expected_runtime_sha=str(handoff["runtime_declaration_sha256"]),
        final=False,
    )
    if record["s7_handoff_sha256"] != _canonical_json_sha(handoff):
        raise ReadinessError("SESSION_HANDOFF_BINDING_MISMATCH")
    product_session_ref, scope_refs, binding_bytes = _load_product_binding(
        product_binding_path,
        repo=repo,
        session_id=str(record["session_id"]),
    )
    if (
        record["product_binding_sha256"] != _sha256_bytes(binding_bytes)
        or record["product_session_ref"] != product_session_ref
        or record["product_scope_correlation_refs"] != scope_refs
    ):
        raise ReadinessError("SESSION_PRODUCT_BINDING_MISMATCH")
    trace, trace_bytes = _load_json_bytes(
        product_trace_path, repo, PRODUCT_TRACE_SCHEMA
    )
    _exact_object(
        trace,
        {
            "schema_version",
            "candidate_head",
            "runtime_declaration_sha256",
            "session_id",
            "product_session_id",
            "records",
        },
        "PRODUCT_TRACE_FIELDS_INVALID",
    )
    session_id = trace["session_id"]
    if (
        trace["candidate_head"] != handoff["candidate_head"]
        or trace["runtime_declaration_sha256"] != handoff["runtime_declaration_sha256"]
        or session_id != record["session_id"]
        or type(session_id) is not str
        or _SESSION_ID.fullmatch(session_id) is None
        or _product_context_ref("session", trace["product_session_id"])
        != record["product_session_ref"]
    ):
        raise ReadinessError("PRODUCT_TRACE_BINDING_MISMATCH")
    records = trace["records"]
    identity_scopes = {
        _OBSERVATION_SCOPES[check_id]: set(kinds)
        for check_id, kinds in _OBSERVATION_IDENTITIES.items()
        if kinds
    }
    if type(records) is not list or len(records) > len(identity_scopes):
        raise ReadinessError("PRODUCT_TRACE_RECORD_SET_INVALID")
    identities: dict[str, dict[str, object]] = {}
    seen_scopes: set[str] = set()
    seen_raw: set[str] = set()
    previous_scope_sequence = 0
    previous_monotonic_ms = -1.0
    for raw in records:
        item = _exact_object(
            raw,
            {"scope", "observation"},
            "PRODUCT_TRACE_RECORD_INVALID",
        )
        scope = item["scope"]
        if (
            type(scope) is not str
            or scope not in identity_scopes
            or scope in seen_scopes
            or _SCOPE_START_SEQUENCE[scope] <= previous_scope_sequence
        ):
            raise ReadinessError("PRODUCT_TRACE_RECORD_ORDER_INVALID")
        try:
            from jiuwenswarm.server.live_voice.observability import (
                create_observation,
            )

            observation = create_observation(item["observation"])
        except Exception as error:  # noqa: BLE001 - product errors stay private
            raise ReadinessError("PRODUCT_TRACE_OBSERVATION_INVALID") from error
        if observation.to_dict() != item["observation"]:
            raise ReadinessError("PRODUCT_TRACE_OBSERVATION_INVALID")
        if observation.monotonic_ms <= previous_monotonic_ms:
            raise ReadinessError("PRODUCT_TRACE_RECORD_ORDER_INVALID")
        rule = _TRACE_SCOPE_RULES.get(scope)
        if rule is None:
            raise ReadinessError("PRODUCT_TRACE_SCOPE_UNSUPPORTED")
        event_name, segment_name, source_components, route_classes = rule
        if (
            observation.event_name != event_name
            or observation.segment_name != segment_name
            or observation.source_component not in source_components
            or observation.route.implementation_class not in route_classes
        ):
            raise ReadinessError("PRODUCT_TRACE_SCOPE_SEMANTICS_MISMATCH")
        expected_correlations = record["product_scope_correlation_refs"]
        assert isinstance(expected_correlations, dict)
        if (
            _product_context_ref("correlation", observation.binding.correlation_id)
            != expected_correlations[scope]
        ):
            raise ReadinessError("PRODUCT_TRACE_CORRELATION_MISMATCH")
        values = {
            "task": observation.binding.task_id,
            "attempt": observation.binding.attempt_id,
            "response": observation.binding.response_id,
            "round": observation.binding.round_id,
            "work": observation.source_record_id or observation.source_event_id,
        }
        if any(values[kind] is None for kind in identity_scopes[scope]):
            raise ReadinessError("PRODUCT_TRACE_IDENTITY_SET_INVALID")
        source_sequence = observation.source_seq
        if source_sequence is None:
            raise ReadinessError("PRODUCT_TRACE_SOURCE_SEQUENCE_MISSING")
        observation_bytes = json.dumps(
            item["observation"],
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        source_ref = (
            "trace_record_ref:sha256-" + hashlib.sha256(observation_bytes).hexdigest()
        )
        for kind in sorted(identity_scopes[scope]):
            value = _safe_string(
                values[kind], "PRODUCT_TRACE_IDENTITY_INVALID", maximum=256
            )
            if value in seen_raw:
                raise ReadinessError("PRODUCT_TRACE_IDENTITY_REUSED")
            seen_raw.add(value)
            alias = f"{scope}.{kind}"
            digest = hashlib.sha256(
                (
                    f"{session_id}|{handoff['candidate_head']}|"
                    f"{source_ref}|{source_sequence}|{scope}|{kind}|{value}"
                ).encode("utf-8")
            ).hexdigest()
            identities[alias] = {
                "kind": kind,
                "ref": f"{kind}_ref:sha256-{digest}",
                "scope": scope,
                "captured_sequence": _SCOPE_START_SEQUENCE[scope],
                "source_sequence": source_sequence,
                "source": "PRODUCT_TRACE",
                "source_record_ref": source_ref,
            }
        seen_scopes.add(scope)
        previous_scope_sequence = _SCOPE_START_SEQUENCE[scope]
        previous_monotonic_ms = observation.monotonic_ms
    return {
        "schema_version": TRACE_MANIFEST_SCHEMA,
        "candidate_head": handoff["candidate_head"],
        "runtime_declaration_sha256": handoff["runtime_declaration_sha256"],
        "session_id": session_id,
        "product_session_ref": record["product_session_ref"],
        "product_scope_correlation_refs": record["product_scope_correlation_refs"],
        "source_trace_sha256": _sha256_bytes(trace_bytes),
        "identities": dict(sorted(identities.items())),
    }


def _load_trace_manifest(
    *,
    repo: Path,
    s7_report_path: Path,
    handoff_path: Path,
    product_binding_path: Path,
    record_path: Path,
    product_trace_path: Path,
    trace_manifest_path: Path,
) -> dict[str, object]:
    expected = capture_trace_manifest(
        repo=repo,
        s7_report_path=s7_report_path,
        handoff_path=handoff_path,
        product_binding_path=product_binding_path,
        record_path=record_path,
        product_trace_path=product_trace_path,
    )
    manifest = _load_json(trace_manifest_path, repo, TRACE_MANIFEST_SCHEMA)
    if manifest != expected:
        raise ReadinessError("TRACE_MANIFEST_BINDING_MISMATCH")
    return manifest


def _new_observations() -> dict[str, object]:
    return {
        check_id: {
            "sequence": sequence,
            "status": "BLOCKED",
            "observer": "USER",
            "reason_code": "USER_OBSERVATION_REQUIRED",
            "identity_bindings": {kind: "" for kind in identity_kinds},
        }
        for sequence, (check_id, identity_kinds) in enumerate(
            _OBSERVATION_IDENTITIES.items(), start=1
        )
    }


def init_session_record(
    *,
    repo: Path,
    s7_report_path: Path,
    handoff_path: Path,
    effect_plan_path: Path,
    product_binding_path: Path,
    session_id: str,
    env: Mapping[str, str],
) -> dict[str, object]:
    if _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    _, handoff, context, _ = _load_bound_inputs(repo, s7_report_path, handoff_path)
    candidate = context["candidate"]
    runtime = context["runtime"]
    assert isinstance(candidate, dict) and isinstance(runtime, dict)
    before = _candidate_snapshot(repo, candidate)
    _validate_flags(runtime, env)
    _validate_runtime_environment(runtime, env)
    state = _validate_isolated_state(
        runtime,
        env,
        repo=repo,
        session_id=session_id,
        require_clean_fixture=True,
    )
    effect_plan, effect_plan_bytes = _load_effect_plan(
        effect_plan_path,
        repo=repo,
        session_id=session_id,
        fixture_ref=state["fixture_ref"],
    )
    if effect_plan["base_head"] != _git(state["root"], "rev-parse", "HEAD"):
        raise ReadinessError("FIXTURE_EFFECT_PLAN_STALE")
    _validate_services(env, expect_open=True)
    processes = _capture_service_processes(
        env, repo=repo, candidate_head=str(candidate["head"])
    )
    product_session_ref, product_scope_correlation_refs, product_binding_bytes = (
        _load_product_binding(
            product_binding_path,
            repo=repo,
            session_id=session_id,
        )
    )
    if _candidate_snapshot(repo, candidate) != before:
        raise ReadinessError("CANDIDATE_CHANGED_AFTER_CHECK")
    return {
        "schema_version": SESSION_SCHEMA,
        "not_acceptance_authority": True,
        "session_id": session_id,
        "candidate_head": handoff["candidate_head"],
        "runtime_declaration_sha256": handoff["runtime_declaration_sha256"],
        "s7_handoff_sha256": _canonical_json_sha(handoff),
        "fixture_effect_plan_sha256": _sha256_bytes(effect_plan_bytes),
        "product_binding_sha256": _sha256_bytes(product_binding_bytes),
        "product_session_ref": product_session_ref,
        "product_scope_correlation_refs": product_scope_correlation_refs,
        "identities": {},
        "observations": _new_observations(),
        "processes": processes,
        "project_effect": {
            "fixture_ref": state["fixture_ref"],
            "base_head": effect_plan["base_head"],
            "expected_changed_paths": effect_plan["expected_changed_paths"],
            "diff_sha256": _fixture_diff_sha(state["root"]),
            "cleanup_action": "PRESERVE",
        },
        "task_settle": [],
        "private_artifacts": [],
        "decision": {
            "outcome": "BLOCKED",
            "decided_by": "USER",
            "reason_codes": ["USER_OBSERVATION_REQUIRED"],
        },
    }


def _validate_session_record(
    payload: dict[str, object],
    *,
    expected_candidate: str | None = None,
    expected_runtime_sha: str | None = None,
    trace_identities: Mapping[str, object] | None = None,
    final: bool,
) -> None:
    _exact_object(
        payload,
        {
            "schema_version",
            "not_acceptance_authority",
            "session_id",
            "candidate_head",
            "runtime_declaration_sha256",
            "s7_handoff_sha256",
            "fixture_effect_plan_sha256",
            "product_binding_sha256",
            "product_session_ref",
            "product_scope_correlation_refs",
            "identities",
            "observations",
            "processes",
            "project_effect",
            "task_settle",
            "private_artifacts",
            "decision",
        },
        "SESSION_RECORD_FIELDS_INVALID",
    )
    if payload["not_acceptance_authority"] is not True:
        raise ReadinessError("SESSION_AUTHORITY_SEMANTICS_INVALID")
    session_id = payload["session_id"]
    if type(session_id) is not str or _SESSION_ID.fullmatch(session_id) is None:
        raise ReadinessError("SESSION_ID_INVALID")
    candidate_head = payload["candidate_head"]
    runtime_sha = payload["runtime_declaration_sha256"]
    if (
        type(candidate_head) is not str
        or _FULL_SHA.fullmatch(candidate_head) is None
        or type(runtime_sha) is not str
        or _SHA256.fullmatch(runtime_sha) is None
        or type(payload["s7_handoff_sha256"]) is not str
        or _SHA256.fullmatch(payload["s7_handoff_sha256"]) is None
        or type(payload["fixture_effect_plan_sha256"]) is not str
        or _SHA256.fullmatch(payload["fixture_effect_plan_sha256"]) is None
        or type(payload["product_binding_sha256"]) is not str
        or _SHA256.fullmatch(payload["product_binding_sha256"]) is None
        or type(payload["product_session_ref"]) is not str
        or _PRODUCT_CONTEXT_REF.fullmatch(payload["product_session_ref"]) is None
        or not str(payload["product_session_ref"]).startswith("product_session_ref:")
        or (expected_candidate is not None and candidate_head != expected_candidate)
        or (expected_runtime_sha is not None and runtime_sha != expected_runtime_sha)
    ):
        raise ReadinessError("SESSION_CANDIDATE_BINDING_MISMATCH")
    scope_refs = payload["product_scope_correlation_refs"]
    if type(scope_refs) is not dict or set(scope_refs) != set(_TRACE_SCOPE_RULES):
        raise ReadinessError("SESSION_PRODUCT_SCOPE_BINDING_INVALID")
    if any(
        type(value) is not str
        or _PRODUCT_CONTEXT_REF.fullmatch(value) is None
        or not value.startswith("product_correlation_ref:")
        for value in scope_refs.values()
    ) or len(set(scope_refs.values())) != len(scope_refs):
        raise ReadinessError("SESSION_PRODUCT_SCOPE_BINDING_INVALID")
    identities = payload["identities"]
    if type(identities) is not dict or len(identities) > 128:
        raise ReadinessError("SESSION_IDENTITIES_INVALID")
    identities_by_kind: dict[str, set[str]] = {kind: set() for kind in IDENTITY_KINDS}
    identity_records: dict[str, dict[str, object]] = {}
    seen_identity_refs: set[str] = set()
    for alias, raw in identities.items():
        if type(alias) is not str or _IDENTITY_ALIAS.fullmatch(alias) is None:
            raise ReadinessError("SESSION_IDENTITY_ALIAS_INVALID")
        item = _exact_object(
            raw,
            {
                "kind",
                "ref",
                "scope",
                "captured_sequence",
                "source_sequence",
                "source",
                "source_record_ref",
            },
            "SESSION_IDENTITY_REF_INVALID",
        )
        kind = item["kind"]
        value = item["ref"]
        if (
            type(kind) is not str
            or kind not in IDENTITY_KINDS
            or type(value) is not str
            or _IDENTITY_REF.fullmatch(value) is None
            or not value.startswith(f"{kind}_ref:")
            or value in seen_identity_refs
            or type(item["scope"]) is not str
            or item["scope"] not in set(_OBSERVATION_SCOPES.values())
            or type(item["captured_sequence"]) is not int
            or item["captured_sequence"] != _SCOPE_START_SEQUENCE[item["scope"]]
            or type(item["source_sequence"]) is not int
            or item["source_sequence"] < 0
            or item["source"] != "PRODUCT_TRACE"
            or type(item["source_record_ref"]) is not str
            or _TRACE_RECORD_REF.fullmatch(item["source_record_ref"]) is None
        ):
            raise ReadinessError("SESSION_IDENTITY_REF_INVALID")
        identities_by_kind[str(kind)].add(value)
        identity_records[alias] = item
        seen_identity_refs.add(value)
    if trace_identities is not None and identities != trace_identities:
        raise ReadinessError("SESSION_TRACE_IDENTITY_MISMATCH")
    if final and trace_identities is None:
        raise ReadinessError("TRACE_MANIFEST_REQUIRED")
    observations = _exact_object(
        payload["observations"],
        set(_OBSERVATION_IDENTITIES),
        "SESSION_OBSERVATION_SET_INVALID",
    )
    statuses: list[str] = []
    used_aliases: set[str] = set()
    required_settle_pairs: set[tuple[str, str]] = set()
    for expected_sequence, (check_id, required_kinds) in enumerate(
        _OBSERVATION_IDENTITIES.items(), start=1
    ):
        item = _exact_object(
            observations[check_id],
            {"sequence", "status", "observer", "reason_code", "identity_bindings"},
            "SESSION_OBSERVATION_INVALID",
        )
        if item["sequence"] != expected_sequence:
            raise ReadinessError("SESSION_OBSERVATION_SEQUENCE_INVALID")
        status = item["status"]
        observer = item["observer"]
        if type(status) is not str or status not in {
            "PASS",
            "FAIL",
            "BLOCKED",
            "NOT_APPLICABLE",
        }:
            raise ReadinessError("SESSION_OBSERVATION_STATUS_INVALID")
        if type(observer) is not str or observer not in {"USER", "AUTOMATION"}:
            raise ReadinessError("SESSION_OBSERVER_INVALID")
        if status == "PASS" and observer != "USER":
            raise ReadinessError("HUMAN_OBSERVATION_CANNOT_BE_AUTOMATED")
        reason = item["reason_code"]
        if type(reason) is not str or _SAFE_ID.fullmatch(reason) is None:
            raise ReadinessError("SESSION_REASON_CODE_INVALID")
        bindings = _exact_object(
            item["identity_bindings"],
            set(required_kinds),
            "SESSION_OBSERVATION_IDENTITY_SET_INVALID",
        )
        for kind in required_kinds:
            alias = bindings[kind]
            if type(alias) is not str:
                raise ReadinessError("STALE_OBSERVATION_IDENTITY")
            if final and status in {"PASS", "FAIL"} and not alias:
                raise ReadinessError("SESSION_IDENTITY_REQUIRED")
            if not alias:
                continue
            bound = identities.get(alias)
            if (
                _IDENTITY_ALIAS.fullmatch(alias) is None
                or type(bound) is not dict
                or bound.get("kind") != kind
                or bound.get("scope") != _OBSERVATION_SCOPES[check_id]
                or not isinstance(bound.get("captured_sequence"), int)
                or int(bound["captured_sequence"]) > expected_sequence
            ):
                raise ReadinessError("STALE_OBSERVATION_IDENTITY")
            used_aliases.add(alias)
        if "task" in required_kinds and "attempt" in required_kinds:
            task_alias = bindings["task"]
            attempt_alias = bindings["attempt"]
            if task_alias and attempt_alias:
                task_record = identity_records.get(task_alias)
                attempt_record = identity_records.get(attempt_alias)
                if task_record is None or attempt_record is None:
                    raise ReadinessError("STALE_OBSERVATION_IDENTITY")
                required_settle_pairs.add(
                    (str(task_record["ref"]), str(attempt_record["ref"]))
                )
        statuses.append(str(status))
    if used_aliases != set(identities):
        raise ReadinessError("SESSION_UNUSED_IDENTITY")
    processes = payload["processes"]
    if type(processes) is not list or len(processes) != len(SERVICE_PORT_ENV):
        raise ReadinessError("SESSION_PROCESS_SET_INVALID")
    seen_services: set[str] = set()
    for raw in processes:
        item = _exact_object(
            raw,
            {"service", "port", "pid", "process_ref", "candidate_head"},
            "SESSION_PROCESS_INVALID",
        )
        service = item["service"]
        if (
            type(service) is not str
            or service not in SERVICE_PORT_ENV
            or service in seen_services
        ):
            raise ReadinessError("SESSION_PROCESS_SET_INVALID")
        if (
            type(item["port"]) is not int
            or not 1024 <= item["port"] <= 65535
            or type(item["pid"]) is not int
            or item["pid"] <= 0
            or type(item["process_ref"]) is not str
            or _RESOURCE_REF.fullmatch(item["process_ref"]) is None
            or item["candidate_head"] != candidate_head
        ):
            raise ReadinessError("SESSION_PROCESS_INVALID")
        seen_services.add(str(service))
    effect = _exact_object(
        payload["project_effect"],
        {
            "fixture_ref",
            "base_head",
            "expected_changed_paths",
            "diff_sha256",
            "cleanup_action",
        },
        "SESSION_PROJECT_EFFECT_INVALID",
    )
    if (
        type(effect["fixture_ref"]) is not str
        or _RESOURCE_REF.fullmatch(effect["fixture_ref"]) is None
        or type(effect["base_head"]) is not str
        or _FULL_SHA.fullmatch(effect["base_head"]) is None
        or type(effect["diff_sha256"]) is not str
        or _SHA256.fullmatch(effect["diff_sha256"]) is None
        or type(effect["cleanup_action"]) is not str
        or effect["cleanup_action"] not in {"PRESERVE", "DELETE"}
    ):
        raise ReadinessError("SESSION_PROJECT_EFFECT_INVALID")
    _validated_project_paths(effect["expected_changed_paths"])
    settle = payload["task_settle"]
    if type(settle) is not list or len(settle) > 32:
        raise ReadinessError("SESSION_TASK_SETTLE_INVALID")
    observed_settle_pairs: set[tuple[str, str]] = set()
    for raw in settle:
        item = _exact_object(
            raw,
            {
                "task_ref",
                "attempt_ref",
                "terminal_state",
                "outbox_state",
                "owner_state",
                "lease_state",
            },
            "SESSION_TASK_SETTLE_INVALID",
        )
        terminal_state = item["terminal_state"]
        if (
            type(item["task_ref"]) is not str
            or type(item["attempt_ref"]) is not str
            or item["task_ref"] not in identities_by_kind["task"]
            or item["attempt_ref"] not in identities_by_kind["attempt"]
            or type(terminal_state) is not str
            or terminal_state
            not in {
                "completed",
                "cancelled",
                "failed",
                "interrupted",
                "unknown",
                "pending",
            }
            or item["outbox_state"] != "settled"
            or item["owner_state"] != "released"
            or item["lease_state"] != "released"
        ):
            raise ReadinessError("SESSION_TASK_NOT_SETTLED")
        pair = (str(item["task_ref"]), str(item["attempt_ref"]))
        if pair in observed_settle_pairs:
            raise ReadinessError("SESSION_TASK_SETTLE_INVALID")
        observed_settle_pairs.add(pair)
    if observed_settle_pairs != required_settle_pairs:
        raise ReadinessError("SESSION_TASK_SETTLE_REQUIRED")
    artifacts = payload["private_artifacts"]
    if type(artifacts) is not list or len(artifacts) > 64:
        raise ReadinessError("SESSION_ARTIFACT_LIST_INVALID")
    seen_artifacts: set[str] = set()
    for raw in artifacts:
        item = _exact_object(
            raw, {"artifact_ref", "action"}, "SESSION_ARTIFACT_INVALID"
        )
        ref = item["artifact_ref"]
        if (
            type(ref) is not str
            or _RESOURCE_REF.fullmatch(ref) is None
            or not ref.startswith("artifact_ref:")
            or ref in seen_artifacts
            or type(item["action"]) is not str
            or item["action"] not in {"PRESERVE", "DELETE_MANUALLY"}
        ):
            raise ReadinessError("SESSION_ARTIFACT_INVALID")
        seen_artifacts.add(ref)
    decision = _exact_object(
        payload["decision"],
        {"outcome", "decided_by", "reason_codes"},
        "SESSION_DECISION_INVALID",
    )
    if (
        decision["decided_by"] != "USER"
        or type(decision["outcome"]) is not str
        or decision["outcome"] not in {"PASS", "PARTIAL", "BLOCKED", "FAIL"}
    ):
        raise ReadinessError("SESSION_DECISION_INVALID")
    reasons = decision["reason_codes"]
    if type(reasons) is not list or not reasons or len(reasons) > 64:
        raise ReadinessError("SESSION_DECISION_INVALID")
    for reason in reasons:
        if type(reason) is not str or _SAFE_ID.fullmatch(reason) is None:
            raise ReadinessError("SESSION_DECISION_INVALID")
    if final:
        outcome = decision["outcome"]
        if "FAIL" in statuses and outcome != "FAIL":
            raise ReadinessError("SESSION_DECISION_INCONSISTENT")
        if outcome == "PASS" and any(status != "PASS" for status in statuses):
            raise ReadinessError("SESSION_PASS_REQUIREMENTS_INCOMPLETE")
        if outcome == "PASS" and reasons != ["USER_ACCEPTED_COMPLETE_SHOWCASE"]:
            raise ReadinessError("SESSION_PASS_REASON_INVALID")


def _load_bound_session(
    *,
    repo: Path,
    s7_report_path: Path,
    handoff_path: Path,
    effect_plan_path: Path,
    product_binding_path: Path,
    product_trace_path: Path,
    trace_manifest_path: Path,
    record_path: Path,
    final: bool,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    _, handoff, context, _ = _load_bound_inputs(repo, s7_report_path, handoff_path)
    record = _load_json(record_path, repo, SESSION_SCHEMA)
    manifest = _load_trace_manifest(
        repo=repo,
        s7_report_path=s7_report_path,
        handoff_path=handoff_path,
        product_binding_path=product_binding_path,
        record_path=record_path,
        product_trace_path=product_trace_path,
        trace_manifest_path=trace_manifest_path,
    )
    if manifest["session_id"] != record["session_id"]:
        raise ReadinessError("SESSION_TRACE_BINDING_MISMATCH")
    trace_identities = manifest["identities"]
    assert isinstance(trace_identities, dict)
    _validate_session_record(
        record,
        expected_candidate=str(handoff["candidate_head"]),
        expected_runtime_sha=str(handoff["runtime_declaration_sha256"]),
        trace_identities=trace_identities,
        final=final,
    )
    if record["s7_handoff_sha256"] != _canonical_json_sha(handoff):
        raise ReadinessError("SESSION_HANDOFF_BINDING_MISMATCH")
    effect = record["project_effect"]
    assert isinstance(effect, dict)
    plan, plan_bytes = _load_effect_plan(
        effect_plan_path,
        repo=repo,
        session_id=str(record["session_id"]),
        fixture_ref=effect["fixture_ref"],
    )
    if (
        record["fixture_effect_plan_sha256"] != _sha256_bytes(plan_bytes)
        or effect["base_head"] != plan["base_head"]
        or effect["expected_changed_paths"] != plan["expected_changed_paths"]
    ):
        raise ReadinessError("SESSION_EFFECT_PLAN_BINDING_MISMATCH")
    return record, handoff, context, trace_identities


def _validate_processes_released(processes: object) -> None:
    assert isinstance(processes, list)
    try:
        import psutil
    except ImportError as error:
        raise ReadinessError("PROCESS_INSPECTION_UNAVAILABLE") from error
    for raw in processes:
        assert isinstance(raw, dict)
        pid = int(raw["pid"])
        if psutil.pid_exists(pid):
            if _process_ref(pid) != raw["process_ref"]:
                raise ReadinessError("PROCESS_IDENTITY_MISMATCH")
            raise ReadinessError("SESSION_PROCESS_STILL_RUNNING")


def _validate_project_effect(
    root: Path, effect: Mapping[str, object], *, require_complete: bool
) -> None:
    if _git(root, "rev-parse", "HEAD") != effect["base_head"]:
        raise ReadinessError("FIXTURE_HEAD_CHANGED")
    actual = _fixture_changed_paths(root)
    expected = set(effect["expected_changed_paths"])
    if (require_complete and set(actual) != expected) or not set(actual).issubset(
        expected
    ):
        raise ReadinessError("FIXTURE_EFFECT_MISMATCH")
    if _fixture_diff_sha(root) != effect["diff_sha256"]:
        raise ReadinessError("FIXTURE_DIFF_MISMATCH")


def run_cleanup(
    *,
    repo: Path,
    s7_report_path: Path,
    handoff_path: Path,
    effect_plan_path: Path,
    product_binding_path: Path,
    product_trace_path: Path,
    trace_manifest_path: Path,
    record_path: Path,
    env: Mapping[str, str],
    execute: bool,
) -> dict[str, object]:
    record, _handoff, context, trace_identities = _load_bound_session(
        repo=repo,
        s7_report_path=s7_report_path,
        handoff_path=handoff_path,
        effect_plan_path=effect_plan_path,
        product_binding_path=product_binding_path,
        product_trace_path=product_trace_path,
        trace_manifest_path=trace_manifest_path,
        record_path=record_path,
        final=False,
    )
    decision = record["decision"]
    assert isinstance(decision, dict)
    passing = decision["outcome"] == "PASS"
    if passing:
        _validate_session_record(
            record,
            expected_candidate=str(record["candidate_head"]),
            expected_runtime_sha=str(record["runtime_declaration_sha256"]),
            trace_identities=trace_identities,
            final=True,
        )
    candidate = context["candidate"]
    runtime = context["runtime"]
    assert isinstance(candidate, dict) and isinstance(runtime, dict)
    before = _candidate_snapshot(repo, candidate)
    _validate_flags(runtime, env)
    _validate_runtime_environment(runtime, env)
    state = _validate_isolated_state(
        runtime,
        env,
        repo=repo,
        session_id=str(record["session_id"]),
        require_clean_fixture=False,
    )
    effect = record["project_effect"]
    assert isinstance(effect, dict)
    _validate_project_effect(state["root"], effect, require_complete=passing)
    _validate_processes_released(record["processes"])
    services = _validate_services(env, expect_open=False)
    after = _candidate_snapshot(repo, candidate)
    if after != before:
        raise ReadinessError("CANDIDATE_CHANGED_AFTER_CHECK")
    deleted = False
    if execute:
        if effect["cleanup_action"] != "DELETE":
            raise ReadinessError("FIXTURE_DELETE_NOT_DECLARED")
        root = state["root"]
        if (
            not isinstance(root, Path)
            or _FIXTURE_NAME.fullmatch(root.name) is None
            or _is_broad_or_protected(root, repo)
            or effect["fixture_ref"]
            != _path_ref("disposable_git", root, no_remote=True)
        ):
            raise ReadinessError("DESTRUCTIVE_TARGET_REJECTED")
        marker = _fixture_marker(root)
        if marker["session_id"] != record["session_id"]:
            raise ReadinessError("DESTRUCTIVE_TARGET_IDENTITY_MISMATCH")
        _remove_owned_tree(root)
        deleted = True
    return {
        "schema_version": "live-voice.s8-cleanup-report.v1",
        "not_alpha_acceptance": True,
        "session_id": record["session_id"],
        "candidate_head": record["candidate_head"],
        "status": "CLEANUP_VERIFIED",
        "service_count": len(services),
        "fixture_action": "DELETED" if deleted else "DRY_RUN_PRESERVED",
        "private_artifact_count": len(record["private_artifacts"]),
        "manual_artifact_cleanup_required": any(
            isinstance(item, dict) and item.get("action") == "DELETE_MANUALLY"
            for item in record["private_artifacts"]
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        description=(
            "Prepare and validate unsigned Live Voice S8 operator inputs. "
            "This tool cannot produce Alpha acceptance."
        )
    )
    parser.add_argument("--repo", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    fixture = commands.add_parser("init-fixture")
    fixture.add_argument("--root", type=Path, required=True)
    fixture.add_argument("--session-id", required=True)
    fixture.add_argument("--execute", action="store_true")

    handoff = commands.add_parser("draft-handoff")
    handoff.add_argument("--s7-report", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)

    refs = commands.add_parser("resource-refs")
    refs.add_argument("--session-id", required=True)

    effect = commands.add_parser("fixture-effect")
    effect.add_argument("--session-id", required=True)

    effect_plan = commands.add_parser("plan-fixture-effect")
    effect_plan.add_argument("--session-id", required=True)
    effect_plan.add_argument("--expected-path", action="append", default=[])
    effect_plan.add_argument("--output", type=Path, required=True)

    scope_correlations = commands.add_parser("init-scope-correlations")
    scope_correlations.add_argument("--session-id", required=True)
    scope_correlations.add_argument("--output", type=Path, required=True)

    trace = commands.add_parser("capture-trace")
    trace.add_argument("--s7-report", type=Path, required=True)
    trace.add_argument("--handoff", type=Path, required=True)
    trace.add_argument("--product-binding", type=Path, required=True)
    trace.add_argument("--record", type=Path, required=True)
    trace.add_argument("--product-trace", type=Path, required=True)
    trace.add_argument("--output", type=Path, required=True)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--s7-report", type=Path, required=True)
    preflight.add_argument("--handoff", type=Path, required=True)
    preflight.add_argument("--session-id", required=True)
    preflight.add_argument("--report", type=Path, required=True)

    session = commands.add_parser("init-session")
    session.add_argument("--s7-report", type=Path, required=True)
    session.add_argument("--handoff", type=Path, required=True)
    session.add_argument("--effect-plan", type=Path, required=True)
    session.add_argument("--product-binding", type=Path, required=True)
    session.add_argument("--session-id", required=True)
    session.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser("validate-session")
    validate.add_argument("--s7-report", type=Path, required=True)
    validate.add_argument("--handoff", type=Path, required=True)
    validate.add_argument("--effect-plan", type=Path, required=True)
    validate.add_argument("--product-binding", type=Path, required=True)
    validate.add_argument("--product-trace", type=Path, required=True)
    validate.add_argument("--trace-manifest", type=Path, required=True)
    validate.add_argument("--record", type=Path, required=True)
    validate.add_argument("--draft", action="store_true")

    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--s7-report", type=Path, required=True)
    cleanup.add_argument("--handoff", type=Path, required=True)
    cleanup.add_argument("--effect-plan", type=Path, required=True)
    cleanup.add_argument("--product-binding", type=Path, required=True)
    cleanup.add_argument("--product-trace", type=Path, required=True)
    cleanup.add_argument("--trace-manifest", type=Path, required=True)
    cleanup.add_argument("--record", type=Path, required=True)
    cleanup.add_argument("--report", type=Path, required=True)
    cleanup.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        repo = resolve_repo(args.repo)
        if args.command == "init-fixture":
            fixture_ref = init_fixture(
                repo=repo,
                root=args.root,
                session_id=args.session_id,
                execute=args.execute,
            )
            print(f"S8_FIXTURE_CREATED {fixture_ref}")
            return 0
        if args.command == "draft-handoff":
            handoff = draft_handoff(repo=repo, s7_report_path=args.s7_report)
            _write_json(args.output, repo, handoff, overwrite=False)
            print("S8_HANDOFF_DRAFT_CREATED_NOT_FROZEN")
            return 0
        if args.command == "resource-refs":
            print(
                json.dumps(
                    resource_refs(
                        repo=repo, session_id=args.session_id, env=os.environ
                    ),
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "fixture-effect":
            print(
                json.dumps(
                    inspect_fixture_effect(
                        repo=repo, session_id=args.session_id, env=os.environ
                    ),
                    ensure_ascii=True,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "plan-fixture-effect":
            plan = plan_fixture_effect(
                repo=repo,
                session_id=args.session_id,
                expected_changed_paths=args.expected_path,
                env=os.environ,
            )
            _write_json(args.output, repo, plan, overwrite=False)
            print("S8_FIXTURE_EFFECT_PLAN_CREATED")
            return 0
        if args.command == "init-scope-correlations":
            values = create_product_binding(
                session_id=args.session_id,
                product_session_id=os.environ.get("S8_PRODUCT_SESSION_ID"),
            )
            _write_json(args.output, repo, values, overwrite=False)
            print("S8_PRIVATE_SCOPE_CORRELATIONS_CREATED")
            return 0
        if args.command == "capture-trace":
            manifest = capture_trace_manifest(
                repo=repo,
                s7_report_path=args.s7_report,
                handoff_path=args.handoff,
                product_binding_path=args.product_binding,
                record_path=args.record,
                product_trace_path=args.product_trace,
            )
            _write_json(args.output, repo, manifest, overwrite=False)
            print("S8_TRACE_MANIFEST_CAPTURED")
            return 0
        if args.command == "preflight":
            report = run_preflight(
                repo=repo,
                s7_report_path=args.s7_report,
                handoff_path=args.handoff,
                session_id=args.session_id,
                env=os.environ,
            )
            _write_json(args.report, repo, report, overwrite=True)
            print(f"S8_PREFLIGHT_{report['status']}")
            return 0 if report["status"] == "AUTOMATED_PREFLIGHT_VERIFIED" else 2
        if args.command == "init-session":
            record = init_session_record(
                repo=repo,
                s7_report_path=args.s7_report,
                handoff_path=args.handoff,
                effect_plan_path=args.effect_plan,
                product_binding_path=args.product_binding,
                session_id=args.session_id,
                env=os.environ,
            )
            _write_json(args.output, repo, record, overwrite=False)
            print("S8_SESSION_TEMPLATE_CREATED")
            return 0
        if args.command == "validate-session":
            _record, _handoff, _context, _identities = _load_bound_session(
                repo=repo,
                s7_report_path=args.s7_report,
                handoff_path=args.handoff,
                effect_plan_path=args.effect_plan,
                product_binding_path=args.product_binding,
                product_trace_path=args.product_trace,
                trace_manifest_path=args.trace_manifest,
                record_path=args.record,
                final=not args.draft,
            )
            print("S8_SESSION_RECORD_VALID")
            return 0
        if args.command == "cleanup":
            report = run_cleanup(
                repo=repo,
                s7_report_path=args.s7_report,
                handoff_path=args.handoff,
                effect_plan_path=args.effect_plan,
                product_binding_path=args.product_binding,
                product_trace_path=args.product_trace,
                trace_manifest_path=args.trace_manifest,
                record_path=args.record,
                env=os.environ,
                execute=args.execute,
            )
            _write_json(args.report, repo, report, overwrite=True)
            print("S8_CLEANUP_VERIFIED")
            return 0
    except (OSError, ValueError, ReadinessError) as error:
        reason = (
            error.reason_code
            if isinstance(error, ReadinessError)
            else "UNEXPECTED_INPUT_FAILURE"
        )
        print(f"S8_READINESS_BLOCKED {reason}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
