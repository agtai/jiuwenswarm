# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import jiuwenswarm.channels.web.live_voice_deployment_observer as deployment_observer


_CANDIDATE = "a" * 40
_RUNTIME = "sha256:" + ("b" * 64)


def _load_module() -> ModuleType:
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "live_voice"
        / "s7_real_probe_support.py"
    )
    spec = importlib.util.spec_from_file_location("s7_real_probe_support", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


s7_probe = _load_module()


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _fixture(path: Path) -> tuple[Path, str]:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "s7@example.invalid")
    _git(path, "config", "user.name", "S7 Probe")
    (path / "notes.txt").write_text("baseline\n", encoding="utf-8")
    _git(path, "add", "notes.txt")
    _git(path, "commit", "-m", "fixture")
    return path, _git(path, "rev-parse", "HEAD")


def _diff_sha(path: Path) -> str:
    completed = subprocess.run(
        ("git", "diff", "--binary", "--no-ext-diff", "--"),
        cwd=path,
        check=True,
        stdout=subprocess.PIPE,
    )
    return "sha256:" + hashlib.sha256(completed.stdout).hexdigest()


def _speech_payload() -> dict[str, object]:
    rounds = []
    for index in range(5):
        rounds.append(
            {
                "round_ref": f"round:{index:064x}",
                "media_frames": 227,
                "media_acks": 227,
                "media_attached": True,
                "endpoint_detector": "server_vad",
                "timing_basis": "provider_time",
                "recognition_status": "completed",
                "recognition_degradation": None,
                "synthesis_streaming": True,
                "synthesis_degradation": None,
                "playout_receipt_accepted": True,
                "browser_credential_hits": 0,
                "forbidden_effect_count": 0,
                "stt_final_ms": 400 + index,
                "tts_first_chunk_ms": 900 + index,
                "end_to_end_ms": 10_000 + index,
            }
        )
    return {
        "schema_version": s7_probe.SPEECH_MEDIA_SCHEMA,
        "candidate_head": _CANDIDATE,
        "runtime_declaration_sha256": _RUNTIME,
        "capture_source": "controlled_private_route_v1",
        "capture_complete": True,
        "provider": {
            "id": "openai-streaming-speech",
            "origin": "https://api.openai.com/v1",
            "stt_model": "gpt-4o-mini-transcribe-2025-12-15",
            "tts_model": "gpt-4o-mini-tts-2025-12-15",
            "voice": "marin",
        },
        "rounds": rounds,
    }


def test_speech_media_probe_validates_real_route_shape_and_computes_latency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = _write_json(tmp_path / "speech.json", _speech_payload())
    monkeypatch.setenv("S7_SPEECH_MEDIA_OBSERVATION", str(observation))

    result = s7_probe.evaluate_speech_media(Path.cwd(), _CANDIDATE, _RUNTIME)

    assert result.sample_count == 5
    assert result.p50_ms == 10_002
    assert result.p95_ms == 10_004
    assert result.max_ms == 10_004


def test_speech_media_probe_fails_closed_on_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _speech_payload()
    rounds = payload["rounds"]
    assert isinstance(rounds, list)
    rounds[0]["recognition_degradation"] = "batch"
    observation = _write_json(tmp_path / "speech.json", payload)
    monkeypatch.setenv("S7_SPEECH_MEDIA_OBSERVATION", str(observation))

    with pytest.raises(s7_probe.ProbeFailure, match="SPEECH_RECOGNITION_DEGRADED"):
        s7_probe.evaluate_speech_media(Path.cwd(), _CANDIDATE, _RUNTIME)


def test_observation_must_bind_exact_runtime_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = _write_json(tmp_path / "speech.json", _speech_payload())
    monkeypatch.setenv("S7_SPEECH_MEDIA_OBSERVATION", str(observation))

    with pytest.raises(s7_probe.ProbeFailure, match="OBSERVATION_RUNTIME_MISMATCH"):
        s7_probe.evaluate_speech_media(Path.cwd(), _CANDIDATE, "sha256:" + ("c" * 64))


def _agent_payload(
    completion: Path,
    completion_head: str,
    cancellation_head: str,
) -> dict[str, object]:
    empty_diff = "sha256:" + hashlib.sha256(b"").hexdigest()
    return {
        "schema_version": s7_probe.AGENT_EXECUTOR_SCHEMA,
        "candidate_head": _CANDIDATE,
        "runtime_declaration_sha256": _RUNTIME,
        "capture_source": "controlled_private_route_v1",
        "capture_complete": True,
        "agent_provider": "jiuwenswarm",
        "task_authority": "persistent_task_core",
        "executor": "direct_project_code",
        "formal_routes": {
            "structured_create_status_cancel": True,
            "committed_natural_language_create_status_cancel": True,
            "task_event_lifecycle_truth": True,
            "exact_scope_isolation": True,
            "replay_rejected": True,
        },
        "completion": {
            "run_ref": "taskrun:" + ("1" * 64),
            "base_head": completion_head,
            "terminal_state": "terminal",
            "outcome": "completed",
            "outbox_delivered": True,
            "cancel_requested": False,
            "forbidden_effect_count": 0,
            "changed_paths": ["notes.txt"],
            "diff_sha256": _diff_sha(completion),
        },
        "cancellation": {
            "run_ref": "taskrun:" + ("2" * 64),
            "base_head": cancellation_head,
            "terminal_state": "terminal",
            "outcome": "cancelled",
            "outbox_delivered": True,
            "cancel_requested": True,
            "forbidden_effect_count": 0,
            "changed_paths": [],
            "diff_sha256": empty_diff,
        },
    }


def test_agent_executor_probe_inspects_two_disposable_no_remote_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completion, completion_head = _fixture(tmp_path / "completion")
    cancellation, cancellation_head = _fixture(tmp_path / "cancellation")
    (completion / "notes.txt").write_text(
        "baseline\nalpha-s7-agent-executor-marker\n", encoding="utf-8"
    )
    payload = _agent_payload(completion, completion_head, cancellation_head)
    observation = _write_json(tmp_path / "agent.json", payload)
    monkeypatch.setenv("S7_AGENT_EXECUTOR_OBSERVATION", str(observation))
    monkeypatch.setenv("S7_EXECUTOR_COMPLETION_FIXTURE_ROOT", str(completion))
    monkeypatch.setenv("S7_EXECUTOR_CANCELLATION_FIXTURE_ROOT", str(cancellation))

    result = s7_probe.evaluate_agent_executor(Path.cwd(), _CANDIDATE, _RUNTIME)

    assert result.sample_count == 2


def test_agent_executor_probe_rejects_cancelled_fixture_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completion, completion_head = _fixture(tmp_path / "completion")
    cancellation, cancellation_head = _fixture(tmp_path / "cancellation")
    (completion / "notes.txt").write_text(
        "baseline\nalpha-s7-agent-executor-marker\n", encoding="utf-8"
    )
    payload = _agent_payload(completion, completion_head, cancellation_head)
    observation = _write_json(tmp_path / "agent.json", payload)
    (cancellation / "notes.txt").write_text("baseline\nforbidden\n", encoding="utf-8")
    monkeypatch.setenv("S7_AGENT_EXECUTOR_OBSERVATION", str(observation))
    monkeypatch.setenv("S7_EXECUTOR_COMPLETION_FIXTURE_ROOT", str(completion))
    monkeypatch.setenv("S7_EXECUTOR_CANCELLATION_FIXTURE_ROOT", str(cancellation))

    with pytest.raises(
        s7_probe.ProbeFailure, match="EXECUTOR_CANCELLATION_EFFECT_OBSERVED"
    ):
        s7_probe.evaluate_agent_executor(Path.cwd(), _CANDIDATE, _RUNTIME)


def _benchmark_payload() -> dict[str, object]:
    return {
        "schema_version": s7_probe.BENCHMARK_FAULT_SCHEMA,
        "candidate_head": _CANDIDATE,
        "runtime_declaration_sha256": _RUNTIME,
        "capture_source": "controlled_private_route_v1",
        "capture_complete": True,
        "targets": [
            {
                "id": target,
                "samples_ms": [10, 11, 12, 13, 14],
                "failure_count": 0,
            }
            for target in s7_probe.BENCHMARK_TARGETS
        ],
        "faults": [
            {
                "id": fault_id,
                "outcome": outcome,
                "passed": True,
                "forbidden_effect_count": 0,
            }
            for fault_id, outcome in s7_probe.FAULT_OUTCOMES.items()
        ],
    }


def test_benchmark_fault_probe_requires_complete_targets_and_faults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = _write_json(tmp_path / "benchmark.json", _benchmark_payload())
    monkeypatch.setenv("S7_BENCHMARK_FAULT_OBSERVATION", str(observation))

    result = s7_probe.evaluate_benchmark_fault(Path.cwd(), _CANDIDATE, _RUNTIME)

    assert result.sample_count == 65
    assert result.p50_ms == 12
    assert result.p95_ms == 14
    assert result.max_ms == 14


def test_benchmark_fault_probe_rejects_zero_effect_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _benchmark_payload()
    faults = payload["faults"]
    assert isinstance(faults, list)
    faults[0]["forbidden_effect_count"] = 1
    observation = _write_json(tmp_path / "benchmark.json", payload)
    monkeypatch.setenv("S7_BENCHMARK_FAULT_OBSERVATION", str(observation))

    with pytest.raises(s7_probe.ProbeFailure, match="BENCHMARK_FAULT_FORBIDDEN_EFFECT"):
        s7_probe.evaluate_benchmark_fault(Path.cwd(), _CANDIDATE, _RUNTIME)


def _deployment_result(*, satisfied: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        real_runtime_observed=True,
        runtime_checks_satisfied=satisfied,
        facts=SimpleNamespace(request_count=3),
    )


def test_secure_deployment_probe_uses_exact_private_origin_and_real_observer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def observe(**kwargs: object) -> SimpleNamespace:
        seen.update(kwargs)
        return _deployment_result()

    monkeypatch.setenv("S7_PRIVATE_ORIGIN", "https://voice.private.internal")
    monkeypatch.setattr(s7_probe, "observe_live_voice_deployment_runtime", observe)

    result = s7_probe.evaluate_secure_deployment(Path.cwd(), _CANDIDATE, _RUNTIME)

    assert result.sample_count == 3
    assert seen["enabled"] is True
    assert seen["request"].websocket_path == "/ws/live-voice/media"
    assert deployment_observer._validate_request(seen["request"]) is not None


def test_secure_deployment_probe_rejects_localhost_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S7_PRIVATE_ORIGIN", "https://live-voice.localhost")

    with pytest.raises(s7_probe.ProbeFailure, match="SECURE_RUNTIME_UNOBSERVED"):
        s7_probe.evaluate_secure_deployment(Path.cwd(), _CANDIDATE, _RUNTIME)


def _privacy_manifest(capture_root: Path) -> dict[str, object]:
    surfaces = []
    for index, surface in enumerate(s7_probe.ALPHA_PRIVACY_SURFACES):
        name = f"surface-{index}.txt"
        (capture_root / name).write_text("sanitized observation\n", encoding="utf-8")
        surfaces.append({"surface": surface.value, "files": [name]})
    return {
        "schema_version": s7_probe.PRIVACY_CAPTURE_SCHEMA,
        "candidate_head": _CANDIDATE,
        "runtime_declaration_sha256": _RUNTIME,
        "capture_source": "controlled_private_route_v1",
        "capture_complete": True,
        "surfaces": surfaces,
    }


def test_privacy_probe_scans_every_closed_surface_for_real_secrets_and_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    manifest = _write_json(tmp_path / "privacy.json", _privacy_manifest(capture))
    monkeypatch.setenv("S7_PRIVACY_SURFACE_MANIFEST", str(manifest))
    monkeypatch.setenv("S7_PRIVACY_CAPTURE_ROOT", str(capture))
    monkeypatch.setenv("LIVE_VOICE_SPEECH_API_KEY", "speech-private-token")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", "p3-private-token")

    result = s7_probe.evaluate_privacy(Path.cwd(), _CANDIDATE, _RUNTIME)

    assert result.sample_count == len(s7_probe.ALPHA_PRIVACY_SURFACES)


@pytest.mark.parametrize(
    "representation",
    ["pcm16_raw", "pcm16_base64", "pcm_f32le_raw", "pcm_f32le_base64"],
)
def test_privacy_probe_rejects_later_media_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, representation: str
) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    manifest = _write_json(tmp_path / "privacy.json", _privacy_manifest(capture))
    audio_fixture = (
        Path.cwd()
        / "scripts"
        / "live_voice"
        / "w2_rehearsal"
        / "assets"
        / "voice-command-48k-mono-pcm16.wav"
    )
    with wave.open(str(audio_fixture), "rb") as source:
        pcm = source.readframes(source.getnframes())
    if representation.startswith("pcm16"):
        start = 19_200 if representation.endswith("base64") else 19_202
        later_frame = pcm[start : start + 960]
        assert len(later_frame) == 960
    else:
        start = 19_200 if representation.endswith("base64") else 19_202
        later_pcm16_frame = pcm[start : start + 1_920]
        signed = struct.unpack("<960h", later_pcm16_frame)
        later_frame = struct.pack(
            "<960f",
            *(value / (32_768 if value < 0 else 32_767) for value in signed),
        )
        assert len(later_frame) == 3_840
    persisted = (
        base64.b64encode(later_frame)
        if representation.endswith("base64")
        else later_frame
    )
    (capture / "surface-0.txt").write_bytes(b"prefix:" + persisted + b":suffix")
    monkeypatch.setenv("S7_PRIVACY_SURFACE_MANIFEST", str(manifest))
    monkeypatch.setenv("S7_PRIVACY_CAPTURE_ROOT", str(capture))
    monkeypatch.setenv("LIVE_VOICE_SPEECH_API_KEY", "speech-private-token")
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", "p3-private-token")

    with pytest.raises(
        s7_probe.ProbeFailure, match="PRIVACY_FORBIDDEN_PATTERN_OBSERVED"
    ):
        s7_probe.evaluate_privacy(Path.cwd(), _CANDIDATE, _RUNTIME)


def test_privacy_probe_rejects_split_boundary_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    payload = _privacy_manifest(capture)
    manifest = _write_json(tmp_path / "privacy.json", payload)
    secret = "speech-private-token"
    (capture / "surface-0.txt").write_bytes(b"prefix" + secret.encode("utf-8"))
    monkeypatch.setenv("S7_PRIVACY_SURFACE_MANIFEST", str(manifest))
    monkeypatch.setenv("S7_PRIVACY_CAPTURE_ROOT", str(capture))
    monkeypatch.setenv("LIVE_VOICE_SPEECH_API_KEY", secret)
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", "p3-private-token")

    with pytest.raises(
        s7_probe.ProbeFailure, match="PRIVACY_FORBIDDEN_PATTERN_OBSERVED"
    ):
        s7_probe.evaluate_privacy(Path.cwd(), _CANDIDATE, _RUNTIME)


def test_privacy_probe_rejects_secret_in_capture_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    payload = _privacy_manifest(capture)
    secret = "speech-private-token"
    original = capture / "surface-0.txt"
    private_name = f"surface-{secret}.txt"
    original.rename(capture / private_name)
    surfaces = payload["surfaces"]
    assert isinstance(surfaces, list)
    assert isinstance(surfaces[0], dict)
    surfaces[0]["files"] = [private_name]
    manifest = _write_json(tmp_path / "privacy.json", payload)
    monkeypatch.setenv("S7_PRIVACY_SURFACE_MANIFEST", str(manifest))
    monkeypatch.setenv("S7_PRIVACY_CAPTURE_ROOT", str(capture))
    monkeypatch.setenv("LIVE_VOICE_SPEECH_API_KEY", secret)
    monkeypatch.setenv("JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN", "p3-private-token")

    with pytest.raises(s7_probe.ProbeFailure, match="PRIVACY_FORBIDDEN_PATH_OBSERVED"):
        s7_probe.evaluate_privacy(Path.cwd(), _CANDIDATE, _RUNTIME)


def test_main_for_redacts_unexpected_private_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        s7_probe,
        "_runtime_binding",
        lambda _check: (Path.cwd(), _CANDIDATE, _RUNTIME),
    )
    monkeypatch.setitem(
        s7_probe._EVALUATORS,
        "privacy",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("private-path-and-secret")),
    )

    assert s7_probe.main_for("privacy") == 1
    output = capsys.readouterr().out
    assert output.strip() == "S7_PROBE_FAILURE UNEXPECTED_PROBE_FAILURE"
    assert "private-path" not in output


def test_probe_required_environment_sets_are_fixed() -> None:
    assert set(s7_probe.REQUIRED_ENV_BY_CHECK) == {
        "speech-media",
        "agent-executor",
        "benchmark-fault",
        "secure-deployment",
        "privacy",
    }
    assert "LIVE_VOICE_SPEECH_API_KEY" in s7_probe.PRIVACY_REQUIRED_ENV
    assert all(s7_probe.REQUIRED_ENV_BY_CHECK.values())
