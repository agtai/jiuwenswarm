# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Fail-closed, candidate-bound S7 real-probe entrypoint support.

The five public entrypoints in this directory either observe the selected
private topology directly or validate a closed, sanitized observation captured
by the controlled private-route harness.  They never accept argv, persist
output, print private paths/content, or turn their own result into Alpha
acceptance.  A successful result is still only ``VERIFY`` input to S7-03.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence
from urllib.parse import quote

from jiuwenswarm.channels.web.live_voice_deployment_observer import (
    LiveVoiceDeploymentObservationRequest,
    observe_live_voice_deployment_runtime,
)
from jiuwenswarm.server.live_voice.alpha_privacy_conformance import (
    ALPHA_PRIVACY_SURFACES,
)


RESULT_PREFIX = "S7_SANITIZED_RESULT "
SPEECH_MEDIA_SCHEMA = "live-voice.s7-speech-media-observation.v1"
AGENT_EXECUTOR_SCHEMA = "live-voice.s7-agent-executor-observation.v1"
BENCHMARK_FAULT_SCHEMA = "live-voice.s7-benchmark-fault-observation.v1"
PRIVACY_CAPTURE_SCHEMA = "live-voice.s7-privacy-capture.v1"

_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_RUNTIME_SHA = re.compile(r"sha256:[0-9a-f]{64}")
_BOUND_REF = re.compile(r"[a-z][a-z0-9_.-]{0,31}:[0-9a-f]{64}")
_DIFF_SHA = re.compile(r"sha256:[0-9a-f]{64}")
_SAFE_RELATIVE = re.compile(r"[A-Za-z0-9._/-]{1,240}")
_MAX_OBSERVATION_BYTES = 4 * 1024 * 1024
_MAX_PRIVACY_FILE_BYTES = 16 * 1024 * 1024
_MAX_PRIVACY_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_PRIVACY_FILES = 512
_AUDIO_SUFFIXES = frozenset(
    {".wav", ".pcm", ".mp3", ".ogg", ".opus", ".webm", ".m4a", ".flac"}
)

SPEECH_MEDIA_REQUIRED_ENV = frozenset({"S7_SPEECH_MEDIA_OBSERVATION"})
AGENT_EXECUTOR_REQUIRED_ENV = frozenset(
    {
        "S7_AGENT_EXECUTOR_OBSERVATION",
        "S7_EXECUTOR_COMPLETION_FIXTURE_ROOT",
        "S7_EXECUTOR_CANCELLATION_FIXTURE_ROOT",
    }
)
BENCHMARK_FAULT_REQUIRED_ENV = frozenset({"S7_BENCHMARK_FAULT_OBSERVATION"})
SECURE_DEPLOYMENT_REQUIRED_ENV = frozenset({"S7_PRIVATE_ORIGIN"})
PRIVACY_REQUIRED_ENV = frozenset(
    {
        "S7_PRIVACY_SURFACE_MANIFEST",
        "S7_PRIVACY_CAPTURE_ROOT",
        "LIVE_VOICE_SPEECH_API_KEY",
        "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN",
    }
)

REQUIRED_ENV_BY_CHECK: Mapping[str, frozenset[str]] = {
    "speech-media": SPEECH_MEDIA_REQUIRED_ENV,
    "agent-executor": AGENT_EXECUTOR_REQUIRED_ENV,
    "benchmark-fault": BENCHMARK_FAULT_REQUIRED_ENV,
    "secure-deployment": SECURE_DEPLOYMENT_REQUIRED_ENV,
    "privacy": PRIVACY_REQUIRED_ENV,
}

BENCHMARK_TARGETS = (
    "p2.activate",
    "media.activate",
    "media.connect",
    "media.attach",
    "media.first_ack",
    "eot.detect",
    "recognition.final",
    "voice.commit",
    "agent.final",
    "synthesis.completed",
    "downlink.first_frame",
    "downlink.complete",
    "route.complete",
)

FAULT_OUTCOMES: Mapping[str, str] = {
    "sequence_gap": "MEDIA_SEQUENCE_GAP",
    "duplicate_or_out_of_order": "MEDIA_DUPLICATE_OR_OUT_OF_ORDER",
    "cursor_mismatch": "MEDIA_CURSOR_MISMATCH",
    "stale_generation": "MEDIA_STALE_GENERATION",
    "burst_backpressure": "ALL_FRAMES_ACKNOWLEDGED",
    "audio_before_auth": "MEDIA_AUTH_REQUIRED",
    "ticket_replay": "MEDIA_TICKET_REPLAY_REJECTED",
    "reconnect_after_detach": "MEDIA_RECONNECT_ACCEPTED",
    "streaming_off_batch_visible": "STREAMING_SPEECH_FEATURE_OFF",
    "speech_off_text_survives": "MEDIA_PROVIDER_UNAVAILABLE_TEXT_ACCEPTED",
    "media_off_text_survives": "MEDIA_FEATURE_DISABLED_TEXT_ACCEPTED",
    "slow_harness_nonblocking": "ROUND_ACCEPTED_WHILE_AGENT_RUNNING",
    "cancel_domain_fenced": "CROSS_DOMAIN_EFFECT_ZERO",
}


class ProbeFailure(RuntimeError):
    """A content-free, closed failure safe to expose to the operator."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ProbeResult:
    sample_count: int
    p50_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None

    def __post_init__(self) -> None:
        if type(self.sample_count) is not int or not 0 < self.sample_count <= 1_000_000:
            raise ProbeFailure("INVALID_SAMPLE_COUNT")
        values = tuple(
            value
            for value in (self.p50_ms, self.p95_ms, self.max_ms)
            if value is not None
        )
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ProbeFailure("INVALID_LATENCY_SUMMARY")
        if self.p50_ms is not None and self.p95_ms is not None:
            if self.p95_ms < self.p50_ms:
                raise ProbeFailure("INVALID_LATENCY_ORDER")
        if self.p95_ms is not None and self.max_ms is not None:
            if self.max_ms < self.p95_ms:
                raise ProbeFailure("INVALID_LATENCY_ORDER")


def _exact_object(value: object, fields: set[str], reason: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ProbeFailure(reason)
    return value


def _exact_bool(value: object, expected: bool, reason: str) -> None:
    if value is not expected:
        raise ProbeFailure(reason)


def _zero(value: object, reason: str) -> None:
    if type(value) is not int or value != 0:
        raise ProbeFailure(reason)


def _positive_int(value: object, reason: str, *, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise ProbeFailure(reason)
    return value


def _positive_ms(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbeFailure(reason)
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 < normalized <= 3_600_000:
        raise ProbeFailure(reason)
    return normalized


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _repo_root() -> Path:
    completed = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    if completed.returncode != 0:
        raise ProbeFailure("CANDIDATE_GIT_UNAVAILABLE")
    root = Path(completed.stdout.strip()).resolve()
    if Path.cwd().resolve() != root:
        raise ProbeFailure("CANDIDATE_CWD_MISMATCH")
    return root


def _runtime_binding(check_id: str) -> tuple[Path, str, str]:
    if len(sys.argv) != 1:
        raise ProbeFailure("POSITIONAL_ARGUMENT_REJECTED")
    observed_id = os.environ.get("S7_CHECK_ID")
    candidate = os.environ.get("S7_CANDIDATE_HEAD")
    runtime_sha = os.environ.get("S7_RUNTIME_DECLARATION_SHA256")
    if observed_id != check_id:
        raise ProbeFailure("CHECK_ID_MISMATCH")
    if candidate is None or _FULL_SHA.fullmatch(candidate) is None:
        raise ProbeFailure("CANDIDATE_HEAD_INVALID")
    if runtime_sha is None or _RUNTIME_SHA.fullmatch(runtime_sha) is None:
        raise ProbeFailure("RUNTIME_DECLARATION_BINDING_INVALID")
    root = _repo_root()
    head = _git_text(root, "rev-parse", "HEAD")
    if head != candidate:
        raise ProbeFailure("CANDIDATE_HEAD_MISMATCH")
    if _git_text(root, "status", "--porcelain", "--untracked-files=all"):
        raise ProbeFailure("CANDIDATE_NOT_CLEAN")
    return root, candidate, runtime_sha


def _external_file(root: Path, env_name: str, *, maximum: int) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        raise ProbeFailure("REQUIRED_ENV_MISSING")
    path = Path(raw)
    if not path.is_absolute():
        raise ProbeFailure("PRIVATE_INPUT_NOT_ABSOLUTE")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ProbeFailure("PRIVATE_INPUT_UNAVAILABLE") from error
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise ProbeFailure("PRIVATE_INPUT_INSIDE_CANDIDATE")
    if not resolved.is_file():
        raise ProbeFailure("PRIVATE_INPUT_NOT_FILE")
    try:
        size = resolved.stat().st_size
    except OSError as error:
        raise ProbeFailure("PRIVATE_INPUT_UNAVAILABLE") from error
    if not 0 < size <= maximum:
        raise ProbeFailure("PRIVATE_INPUT_SIZE_INVALID")
    return resolved


def _load_observation(
    root: Path,
    env_name: str,
    *,
    schema: str,
    candidate: str,
    runtime_sha: str,
) -> dict[str, object]:
    path = _external_file(root, env_name, maximum=_MAX_OBSERVATION_BYTES)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProbeFailure("OBSERVATION_INVALID_JSON") from error
    if type(payload) is not dict:
        raise ProbeFailure("OBSERVATION_INVALID")
    if payload.get("schema_version") != schema:
        raise ProbeFailure("OBSERVATION_SCHEMA_MISMATCH")
    if payload.get("candidate_head") != candidate:
        raise ProbeFailure("OBSERVATION_CANDIDATE_MISMATCH")
    if payload.get("runtime_declaration_sha256") != runtime_sha:
        raise ProbeFailure("OBSERVATION_RUNTIME_MISMATCH")
    return payload


def _bound_ref(value: object, prefix: str, reason: str) -> str:
    if type(value) is not str or _BOUND_REF.fullmatch(value) is None:
        raise ProbeFailure(reason)
    if not value.startswith(prefix + ":"):
        raise ProbeFailure(reason)
    return value


def evaluate_speech_media(root: Path, candidate: str, runtime_sha: str) -> ProbeResult:
    payload = _load_observation(
        root,
        "S7_SPEECH_MEDIA_OBSERVATION",
        schema=SPEECH_MEDIA_SCHEMA,
        candidate=candidate,
        runtime_sha=runtime_sha,
    )
    _exact_object(
        payload,
        {
            "schema_version",
            "candidate_head",
            "runtime_declaration_sha256",
            "capture_source",
            "capture_complete",
            "provider",
            "rounds",
        },
        "SPEECH_OBSERVATION_FIELDS_INVALID",
    )
    if payload["capture_source"] != "controlled_private_route_v1":
        raise ProbeFailure("SPEECH_CAPTURE_SOURCE_INVALID")
    _exact_bool(payload["capture_complete"], True, "SPEECH_CAPTURE_INCOMPLETE")
    provider = _exact_object(
        payload["provider"],
        {"id", "origin", "stt_model", "tts_model", "voice"},
        "SPEECH_PROVIDER_FIELDS_INVALID",
    )
    expected_provider = {
        "id": "openai-streaming-speech",
        "origin": "https://api.openai.com/v1",
        "stt_model": "gpt-4o-mini-transcribe-2025-12-15",
        "tts_model": "gpt-4o-mini-tts-2025-12-15",
        "voice": "marin",
    }
    if provider != expected_provider:
        raise ProbeFailure("SPEECH_PROVIDER_PROFILE_MISMATCH")
    rounds = payload["rounds"]
    if type(rounds) is not list or not 5 <= len(rounds) <= 20:
        raise ProbeFailure("SPEECH_SAMPLE_COUNT_INVALID")
    end_to_end: list[float] = []
    seen: set[str] = set()
    round_fields = {
        "round_ref",
        "media_frames",
        "media_acks",
        "media_attached",
        "endpoint_detector",
        "timing_basis",
        "recognition_status",
        "recognition_degradation",
        "synthesis_streaming",
        "synthesis_degradation",
        "playout_receipt_accepted",
        "browser_credential_hits",
        "forbidden_effect_count",
        "stt_final_ms",
        "tts_first_chunk_ms",
        "end_to_end_ms",
    }
    for raw_round in rounds:
        item = _exact_object(raw_round, round_fields, "SPEECH_ROUND_FIELDS_INVALID")
        round_ref = _bound_ref(item["round_ref"], "round", "SPEECH_ROUND_REF_INVALID")
        if round_ref in seen:
            raise ProbeFailure("SPEECH_ROUND_DUPLICATE")
        seen.add(round_ref)
        frames = _positive_int(item["media_frames"], "SPEECH_FRAME_COUNT_INVALID")
        acks = _positive_int(item["media_acks"], "SPEECH_ACK_COUNT_INVALID")
        if frames != acks:
            raise ProbeFailure("SPEECH_MEDIA_ACK_INCOMPLETE")
        _exact_bool(item["media_attached"], True, "SPEECH_MEDIA_NOT_ATTACHED")
        if item["endpoint_detector"] != "server_vad":
            raise ProbeFailure("SPEECH_EOT_PROFILE_MISMATCH")
        if item["timing_basis"] != "provider_time":
            raise ProbeFailure("SPEECH_TIMING_BASIS_MISMATCH")
        if item["recognition_status"] != "completed":
            raise ProbeFailure("SPEECH_RECOGNITION_INCOMPLETE")
        if item["recognition_degradation"] is not None:
            raise ProbeFailure("SPEECH_RECOGNITION_DEGRADED")
        _exact_bool(item["synthesis_streaming"], True, "SPEECH_SYNTHESIS_NOT_STREAMING")
        if item["synthesis_degradation"] is not None:
            raise ProbeFailure("SPEECH_SYNTHESIS_DEGRADED")
        _exact_bool(
            item["playout_receipt_accepted"],
            True,
            "SPEECH_PLAYOUT_RECEIPT_MISSING",
        )
        _zero(item["browser_credential_hits"], "SPEECH_BROWSER_CREDENTIAL_LEAK")
        _zero(item["forbidden_effect_count"], "SPEECH_FORBIDDEN_EFFECT")
        _positive_ms(item["stt_final_ms"], "SPEECH_STT_LATENCY_INVALID")
        _positive_ms(item["tts_first_chunk_ms"], "SPEECH_TTS_LATENCY_INVALID")
        end_to_end.append(
            _positive_ms(item["end_to_end_ms"], "SPEECH_ROUTE_LATENCY_INVALID")
        )
    return ProbeResult(
        sample_count=len(rounds),
        p50_ms=_percentile(end_to_end, 0.50),
        p95_ms=_percentile(end_to_end, 0.95),
        max_ms=max(end_to_end),
    )


def _git_text(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    if completed.returncode != 0:
        raise ProbeFailure("GIT_FIXTURE_INSPECTION_FAILED")
    return completed.stdout.strip()


def _git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    if completed.returncode != 0:
        raise ProbeFailure("GIT_FIXTURE_INSPECTION_FAILED")
    return completed.stdout


def _fixture_root(candidate_root: Path, env_name: str) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        raise ProbeFailure("EXECUTOR_FIXTURE_ENV_MISSING")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ProbeFailure("EXECUTOR_FIXTURE_NOT_ABSOLUTE")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ProbeFailure("EXECUTOR_FIXTURE_UNAVAILABLE") from error
    try:
        resolved.relative_to(candidate_root)
    except ValueError:
        pass
    else:
        raise ProbeFailure("EXECUTOR_FIXTURE_INSIDE_CANDIDATE")
    if not resolved.is_dir():
        raise ProbeFailure("EXECUTOR_FIXTURE_UNAVAILABLE")
    if Path(_git_text(resolved, "rev-parse", "--show-toplevel")).resolve() != resolved:
        raise ProbeFailure("EXECUTOR_FIXTURE_NOT_ROOT")
    if _git_text(resolved, "remote"):
        raise ProbeFailure("EXECUTOR_FIXTURE_HAS_REMOTE")
    return resolved


def _fixture_diff_sha(root: Path) -> str:
    payload = _git_bytes(root, "diff", "--binary", "--no-ext-diff", "--")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def evaluate_agent_executor(
    root: Path, candidate: str, runtime_sha: str
) -> ProbeResult:
    payload = _load_observation(
        root,
        "S7_AGENT_EXECUTOR_OBSERVATION",
        schema=AGENT_EXECUTOR_SCHEMA,
        candidate=candidate,
        runtime_sha=runtime_sha,
    )
    _exact_object(
        payload,
        {
            "schema_version",
            "candidate_head",
            "runtime_declaration_sha256",
            "capture_source",
            "capture_complete",
            "agent_provider",
            "task_authority",
            "executor",
            "formal_routes",
            "completion",
            "cancellation",
        },
        "AGENT_OBSERVATION_FIELDS_INVALID",
    )
    if payload["capture_source"] != "controlled_private_route_v1":
        raise ProbeFailure("AGENT_CAPTURE_SOURCE_INVALID")
    _exact_bool(payload["capture_complete"], True, "AGENT_CAPTURE_INCOMPLETE")
    if payload["agent_provider"] != "jiuwenswarm":
        raise ProbeFailure("AGENT_PROVIDER_MISMATCH")
    if payload["task_authority"] != "persistent_task_core":
        raise ProbeFailure("TASK_AUTHORITY_MISMATCH")
    if payload["executor"] != "direct_project_code":
        raise ProbeFailure("EXECUTOR_PROFILE_MISMATCH")
    formal = _exact_object(
        payload["formal_routes"],
        {
            "structured_create_status_cancel",
            "committed_natural_language_create_status_cancel",
            "task_event_lifecycle_truth",
            "exact_scope_isolation",
            "replay_rejected",
        },
        "AGENT_FORMAL_ROUTE_FIELDS_INVALID",
    )
    for value in formal.values():
        _exact_bool(value, True, "AGENT_FORMAL_ROUTE_INCOMPLETE")

    effect_fields = {
        "run_ref",
        "base_head",
        "terminal_state",
        "outcome",
        "outbox_delivered",
        "cancel_requested",
        "forbidden_effect_count",
        "changed_paths",
        "diff_sha256",
    }
    completion = _exact_object(
        payload["completion"], effect_fields, "AGENT_COMPLETION_FIELDS_INVALID"
    )
    cancellation = _exact_object(
        payload["cancellation"], effect_fields, "AGENT_CANCELLATION_FIELDS_INVALID"
    )
    _bound_ref(completion["run_ref"], "taskrun", "AGENT_RUN_REF_INVALID")
    _bound_ref(cancellation["run_ref"], "taskrun", "AGENT_RUN_REF_INVALID")
    if completion["run_ref"] == cancellation["run_ref"]:
        raise ProbeFailure("AGENT_RUN_REF_DUPLICATE")
    for item in (completion, cancellation):
        if (
            type(item["base_head"]) is not str
            or _FULL_SHA.fullmatch(item["base_head"]) is None
        ):
            raise ProbeFailure("EXECUTOR_FIXTURE_HEAD_INVALID")
        if (
            type(item["diff_sha256"]) is not str
            or _DIFF_SHA.fullmatch(item["diff_sha256"]) is None
        ):
            raise ProbeFailure("EXECUTOR_DIFF_DIGEST_INVALID")
        _exact_bool(item["outbox_delivered"], True, "AGENT_OUTBOX_INCOMPLETE")
        _zero(item["forbidden_effect_count"], "AGENT_FORBIDDEN_EFFECT")
    if (
        completion["terminal_state"] != "terminal"
        or completion["outcome"] != "completed"
        or completion["cancel_requested"] is not False
    ):
        raise ProbeFailure("AGENT_COMPLETION_OUTCOME_INVALID")
    if (
        cancellation["terminal_state"] != "terminal"
        or cancellation["outcome"] != "cancelled"
        or cancellation["cancel_requested"] is not True
    ):
        raise ProbeFailure("AGENT_CANCELLATION_OUTCOME_INVALID")

    completion_root = _fixture_root(root, "S7_EXECUTOR_COMPLETION_FIXTURE_ROOT")
    cancellation_root = _fixture_root(root, "S7_EXECUTOR_CANCELLATION_FIXTURE_ROOT")
    if completion_root == cancellation_root:
        raise ProbeFailure("EXECUTOR_FIXTURES_NOT_ISOLATED")
    if _git_text(completion_root, "rev-parse", "HEAD") != completion["base_head"]:
        raise ProbeFailure("EXECUTOR_COMPLETION_HEAD_MISMATCH")
    if _git_text(cancellation_root, "rev-parse", "HEAD") != cancellation["base_head"]:
        raise ProbeFailure("EXECUTOR_CANCELLATION_HEAD_MISMATCH")

    changed = completion["changed_paths"]
    if changed != ["notes.txt"]:
        raise ProbeFailure("EXECUTOR_CHANGED_PATHS_INVALID")
    status = _git_bytes(
        completion_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status != b" M notes.txt\0":
        raise ProbeFailure("EXECUTOR_COMPLETION_EFFECT_MISMATCH")
    actual_changed = tuple(
        line
        for line in _git_text(completion_root, "diff", "--name-only", "--").splitlines()
        if line
    )
    if actual_changed != tuple(changed):
        raise ProbeFailure("EXECUTOR_COMPLETION_EFFECT_MISMATCH")
    if _fixture_diff_sha(completion_root) != completion["diff_sha256"]:
        raise ProbeFailure("EXECUTOR_COMPLETION_DIFF_MISMATCH")
    try:
        completion_content = (completion_root / "notes.txt").read_text(encoding="utf-8")
        cancellation_content = (cancellation_root / "notes.txt").read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError) as error:
        raise ProbeFailure("EXECUTOR_FIXTURE_INSPECTION_FAILED") from error
    if completion_content != "baseline\nalpha-s7-agent-executor-marker\n":
        raise ProbeFailure("EXECUTOR_COMPLETION_CONTENT_MISMATCH")
    if cancellation["changed_paths"] != []:
        raise ProbeFailure("EXECUTOR_CANCELLATION_EFFECT_DECLARED")
    if _git_text(cancellation_root, "status", "--porcelain", "--untracked-files=all"):
        raise ProbeFailure("EXECUTOR_CANCELLATION_EFFECT_OBSERVED")
    if _fixture_diff_sha(cancellation_root) != cancellation["diff_sha256"]:
        raise ProbeFailure("EXECUTOR_CANCELLATION_DIFF_MISMATCH")
    if cancellation_content != "baseline\n":
        raise ProbeFailure("EXECUTOR_CANCELLATION_CONTENT_MISMATCH")
    return ProbeResult(sample_count=2)


def evaluate_benchmark_fault(
    root: Path, candidate: str, runtime_sha: str
) -> ProbeResult:
    payload = _load_observation(
        root,
        "S7_BENCHMARK_FAULT_OBSERVATION",
        schema=BENCHMARK_FAULT_SCHEMA,
        candidate=candidate,
        runtime_sha=runtime_sha,
    )
    _exact_object(
        payload,
        {
            "schema_version",
            "candidate_head",
            "runtime_declaration_sha256",
            "capture_source",
            "capture_complete",
            "targets",
            "faults",
        },
        "BENCHMARK_OBSERVATION_FIELDS_INVALID",
    )
    if payload["capture_source"] != "controlled_private_route_v1":
        raise ProbeFailure("BENCHMARK_CAPTURE_SOURCE_INVALID")
    _exact_bool(payload["capture_complete"], True, "BENCHMARK_CAPTURE_INCOMPLETE")
    targets = payload["targets"]
    if type(targets) is not list or len(targets) != len(BENCHMARK_TARGETS):
        raise ProbeFailure("BENCHMARK_TARGET_SET_INVALID")
    by_target: dict[str, list[float]] = {}
    total_samples = 0
    for raw_target in targets:
        target = _exact_object(
            raw_target,
            {"id", "samples_ms", "failure_count"},
            "BENCHMARK_TARGET_FIELDS_INVALID",
        )
        target_id = target["id"]
        if type(target_id) is not str or target_id not in BENCHMARK_TARGETS:
            raise ProbeFailure("BENCHMARK_TARGET_ID_INVALID")
        if target_id in by_target:
            raise ProbeFailure("BENCHMARK_TARGET_DUPLICATE")
        samples = target["samples_ms"]
        if type(samples) is not list or not 5 <= len(samples) <= 50:
            raise ProbeFailure("BENCHMARK_SAMPLE_COUNT_INVALID")
        normalized = [
            _positive_ms(value, "BENCHMARK_SAMPLE_INVALID") for value in samples
        ]
        _zero(target["failure_count"], "BENCHMARK_FAILURE_OBSERVED")
        by_target[target_id] = normalized
        total_samples += len(normalized)
    if set(by_target) != set(BENCHMARK_TARGETS):
        raise ProbeFailure("BENCHMARK_TARGET_SET_INVALID")

    faults = payload["faults"]
    if type(faults) is not list or len(faults) != len(FAULT_OUTCOMES):
        raise ProbeFailure("BENCHMARK_FAULT_SET_INVALID")
    seen_faults: set[str] = set()
    for raw_fault in faults:
        fault = _exact_object(
            raw_fault,
            {"id", "outcome", "passed", "forbidden_effect_count"},
            "BENCHMARK_FAULT_FIELDS_INVALID",
        )
        fault_id = fault["id"]
        if type(fault_id) is not str or fault_id not in FAULT_OUTCOMES:
            raise ProbeFailure("BENCHMARK_FAULT_ID_INVALID")
        if fault_id in seen_faults:
            raise ProbeFailure("BENCHMARK_FAULT_DUPLICATE")
        seen_faults.add(fault_id)
        if fault["outcome"] != FAULT_OUTCOMES[fault_id]:
            raise ProbeFailure("BENCHMARK_FAULT_OUTCOME_MISMATCH")
        _exact_bool(fault["passed"], True, "BENCHMARK_FAULT_FAILED")
        _zero(fault["forbidden_effect_count"], "BENCHMARK_FAULT_FORBIDDEN_EFFECT")
    if seen_faults != set(FAULT_OUTCOMES):
        raise ProbeFailure("BENCHMARK_FAULT_SET_INVALID")
    route = by_target["route.complete"]
    return ProbeResult(
        sample_count=total_samples,
        p50_ms=_percentile(route, 0.50),
        p95_ms=_percentile(route, 0.95),
        max_ms=max(route),
    )


def evaluate_secure_deployment(
    _root: Path, _candidate: str, _runtime_sha: str
) -> ProbeResult:
    origin = os.environ.get("S7_PRIVATE_ORIGIN")
    if not origin:
        raise ProbeFailure("SECURE_ORIGIN_MISSING")
    result = observe_live_voice_deployment_runtime(
        enabled=True,
        request=LiveVoiceDeploymentObservationRequest(
            https_url=origin,
            expected_origin=origin,
            websocket_path="/ws/live-voice/media",
            timeout_ms=5_000,
        ),
    )
    if not result.real_runtime_observed:
        raise ProbeFailure("SECURE_RUNTIME_UNOBSERVED")
    if not result.runtime_checks_satisfied:
        raise ProbeFailure("SECURE_RUNTIME_CHECK_FAILED")
    if result.facts.request_count != 3:
        raise ProbeFailure("SECURE_RUNTIME_CHECK_INCOMPLETE")
    return ProbeResult(sample_count=result.facts.request_count)


def _relative_capture_path(value: object) -> PurePosixPath:
    if type(value) is not str or _SAFE_RELATIVE.fullmatch(value) is None:
        raise ProbeFailure("PRIVACY_CAPTURE_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ProbeFailure("PRIVACY_CAPTURE_PATH_INVALID")
    return path


def _privacy_patterns(audio_fixture: Path) -> tuple[bytes, ...]:
    secrets: list[bytes] = []
    for name in ("LIVE_VOICE_SPEECH_API_KEY", "JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN"):
        raw = os.environ.get(name)
        if raw is None or not 8 <= len(raw) <= 4_096:
            raise ProbeFailure("PRIVACY_SECRET_INPUT_INVALID")
        encoded = raw.encode("utf-8")
        secrets.extend(
            (
                encoded,
                base64.b64encode(encoded),
                quote(raw, safe="").encode("ascii"),
            )
        )
    try:
        with wave.open(str(audio_fixture), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                raise ProbeFailure("PRIVACY_AUDIO_FIXTURE_INVALID")
            pcm = source.readframes(min(source.getnframes(), 2_048))
        raw_audio = audio_fixture.read_bytes()
    except (OSError, EOFError, wave.Error) as error:
        raise ProbeFailure("PRIVACY_AUDIO_FIXTURE_INVALID") from error
    if len(pcm) < 1_024 or len(raw_audio) < 44:
        raise ProbeFailure("PRIVACY_AUDIO_FIXTURE_INVALID")
    audio_sha = hashlib.sha256(raw_audio).hexdigest().encode("ascii")
    patterns = tuple(
        dict.fromkeys(
            (
                *secrets,
                pcm[:4_096],
                base64.b64encode(pcm[:1_024]),
                audio_sha,
            )
        )
    )
    if any(not pattern or len(pattern) > 8_192 for pattern in patterns):
        raise ProbeFailure("PRIVACY_PATTERN_INVALID")
    return patterns


def _file_contains_pattern(path: Path, patterns: tuple[bytes, ...]) -> bool:
    overlap = max(len(pattern) for pattern in patterns) - 1
    tail = b""
    try:
        with path.open("rb") as source:
            while chunk := source.read(64 * 1024):
                window = tail + chunk
                if any(pattern in window for pattern in patterns):
                    return True
                tail = window[-overlap:] if overlap else b""
    except OSError as error:
        raise ProbeFailure("PRIVACY_CAPTURE_READ_FAILED") from error
    return False


def evaluate_privacy(root: Path, candidate: str, runtime_sha: str) -> ProbeResult:
    payload = _load_observation(
        root,
        "S7_PRIVACY_SURFACE_MANIFEST",
        schema=PRIVACY_CAPTURE_SCHEMA,
        candidate=candidate,
        runtime_sha=runtime_sha,
    )
    _exact_object(
        payload,
        {
            "schema_version",
            "candidate_head",
            "runtime_declaration_sha256",
            "capture_source",
            "capture_complete",
            "surfaces",
        },
        "PRIVACY_MANIFEST_FIELDS_INVALID",
    )
    if payload["capture_source"] != "controlled_private_route_v1":
        raise ProbeFailure("PRIVACY_CAPTURE_SOURCE_INVALID")
    _exact_bool(payload["capture_complete"], True, "PRIVACY_CAPTURE_INCOMPLETE")
    capture_raw = os.environ.get("S7_PRIVACY_CAPTURE_ROOT")
    if not capture_raw:
        raise ProbeFailure("PRIVACY_CAPTURE_ROOT_MISSING")
    capture_root = Path(capture_raw)
    if not capture_root.is_absolute():
        raise ProbeFailure("PRIVACY_CAPTURE_ROOT_NOT_ABSOLUTE")
    try:
        capture_root = capture_root.resolve(strict=True)
    except OSError as error:
        raise ProbeFailure("PRIVACY_CAPTURE_ROOT_UNAVAILABLE") from error
    try:
        capture_root.relative_to(root)
    except ValueError:
        pass
    else:
        raise ProbeFailure("PRIVACY_CAPTURE_INSIDE_CANDIDATE")
    if not capture_root.is_dir():
        raise ProbeFailure("PRIVACY_CAPTURE_ROOT_UNAVAILABLE")

    audio_fixture = (
        root
        / "scripts"
        / "live_voice"
        / "w2_rehearsal"
        / "assets"
        / "voice-command-48k-mono-pcm16.wav"
    )
    if not audio_fixture.is_file():
        raise ProbeFailure("PRIVACY_AUDIO_FIXTURE_INVALID")
    patterns = _privacy_patterns(audio_fixture)
    surfaces = payload["surfaces"]
    if type(surfaces) is not list or len(surfaces) != len(ALPHA_PRIVACY_SURFACES):
        raise ProbeFailure("PRIVACY_SURFACE_SET_INVALID")
    expected_surfaces = {surface.value for surface in ALPHA_PRIVACY_SURFACES}
    observed_surfaces: set[str] = set()
    files: list[Path] = []
    for raw_surface in surfaces:
        surface = _exact_object(
            raw_surface, {"surface", "files"}, "PRIVACY_SURFACE_FIELDS_INVALID"
        )
        surface_id = surface["surface"]
        if type(surface_id) is not str or surface_id not in expected_surfaces:
            raise ProbeFailure("PRIVACY_SURFACE_ID_INVALID")
        if surface_id in observed_surfaces:
            raise ProbeFailure("PRIVACY_SURFACE_DUPLICATE")
        observed_surfaces.add(surface_id)
        raw_files = surface["files"]
        if type(raw_files) is not list or not raw_files or len(raw_files) > 64:
            raise ProbeFailure("PRIVACY_SURFACE_FILES_INVALID")
        for raw_file in raw_files:
            relative = _relative_capture_path(raw_file)
            if any(
                pattern in relative.as_posix().encode("utf-8") for pattern in patterns
            ):
                raise ProbeFailure("PRIVACY_FORBIDDEN_PATH_OBSERVED")
            resolved = (capture_root / Path(*relative.parts)).resolve()
            try:
                resolved.relative_to(capture_root)
            except ValueError as error:
                raise ProbeFailure("PRIVACY_CAPTURE_PATH_ESCAPES_ROOT") from error
            if not resolved.is_file():
                raise ProbeFailure("PRIVACY_CAPTURE_FILE_UNAVAILABLE")
            files.append(resolved)
    if observed_surfaces != expected_surfaces:
        raise ProbeFailure("PRIVACY_SURFACE_SET_INVALID")
    if len(files) > _MAX_PRIVACY_FILES or len(set(files)) != len(files):
        raise ProbeFailure("PRIVACY_CAPTURE_FILE_SET_INVALID")
    total_bytes = 0
    for path in files:
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ProbeFailure("PRIVACY_CAPTURE_READ_FAILED") from error
        if size > _MAX_PRIVACY_FILE_BYTES:
            raise ProbeFailure("PRIVACY_CAPTURE_FILE_TOO_LARGE")
        total_bytes += size
        if total_bytes > _MAX_PRIVACY_TOTAL_BYTES:
            raise ProbeFailure("PRIVACY_CAPTURE_TOTAL_TOO_LARGE")
        if path.suffix.lower() in _AUDIO_SUFFIXES:
            raise ProbeFailure("PRIVACY_AUDIO_FILE_PERSISTED")
        try:
            with path.open("rb") as source:
                header = source.read(12)
        except OSError as error:
            raise ProbeFailure("PRIVACY_CAPTURE_READ_FAILED") from error
        if len(header) == 12 and header[:4] == b"RIFF" and header[8:] == b"WAVE":
            raise ProbeFailure("PRIVACY_WAVE_PAYLOAD_PERSISTED")
        if _file_contains_pattern(path, patterns):
            raise ProbeFailure("PRIVACY_FORBIDDEN_PATTERN_OBSERVED")
    return ProbeResult(sample_count=len(files))


_EVALUATORS: Mapping[str, Callable[[Path, str, str], ProbeResult]] = {
    "speech-media": evaluate_speech_media,
    "agent-executor": evaluate_agent_executor,
    "benchmark-fault": evaluate_benchmark_fault,
    "secure-deployment": evaluate_secure_deployment,
    "privacy": evaluate_privacy,
}


def main_for(check_id: str) -> int:
    """Execute one fixed probe and emit only a sanitized aggregate."""

    try:
        root, candidate, runtime_sha = _runtime_binding(check_id)
        evaluator = _EVALUATORS.get(check_id)
        if evaluator is None:
            raise ProbeFailure("CHECK_ID_UNSUPPORTED")
        result = evaluator(root, candidate, runtime_sha)
        payload: dict[str, object] = {
            "candidate_head": candidate,
            "runtime_declaration_sha256": runtime_sha,
            "check_id": check_id,
            "sample_count": result.sample_count,
            "failure_count": 0,
            "zero_forbidden_effects": True,
            "outcome": "PASS",
        }
        if result.p50_ms is not None:
            payload["p50_ms"] = result.p50_ms
        if result.p95_ms is not None:
            payload["p95_ms"] = result.p95_ms
        if result.max_ms is not None:
            payload["max_ms"] = result.max_ms
        print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0
    except ProbeFailure as error:
        print(f"S7_PROBE_FAILURE {error.reason}")
        return 1
    except Exception:  # noqa: BLE001 - never expose private exception content
        print("S7_PROBE_FAILURE UNEXPECTED_PROBE_FAILURE")
        return 1


__all__ = [
    "AGENT_EXECUTOR_REQUIRED_ENV",
    "AGENT_EXECUTOR_SCHEMA",
    "BENCHMARK_FAULT_REQUIRED_ENV",
    "BENCHMARK_FAULT_SCHEMA",
    "BENCHMARK_TARGETS",
    "FAULT_OUTCOMES",
    "PRIVACY_CAPTURE_SCHEMA",
    "PRIVACY_REQUIRED_ENV",
    "ProbeFailure",
    "ProbeResult",
    "REQUIRED_ENV_BY_CHECK",
    "SECURE_DEPLOYMENT_REQUIRED_ENV",
    "SPEECH_MEDIA_REQUIRED_ENV",
    "SPEECH_MEDIA_SCHEMA",
    "evaluate_agent_executor",
    "evaluate_benchmark_fault",
    "evaluate_privacy",
    "evaluate_secure_deployment",
    "evaluate_speech_media",
    "main_for",
]
