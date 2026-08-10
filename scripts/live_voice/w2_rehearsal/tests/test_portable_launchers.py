from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import subprocess
import sys

from jiuwenswarm.server.live_voice import batch_speech
from scripts.live_voice.w2_rehearsal import w2_wav_speech_preflight


_BUNDLE = Path(__file__).resolve().parents[1]


def test_fresh_attempt_uses_candidate_bound_helpers_and_default_wav() -> None:
    script = (_BUNDLE / "new_w2_rehearsal_attempt.ps1").read_text(encoding="utf-8")

    assert "$candidateBundle = Join-Path $candidateRoot" in script
    assert "& $Python $candidateScaffoldScript" in script
    assert "& $Python $candidatePlanScript" in script
    assert (
        "Join-Path $candidateBundle 'assets\\voice-command-48k-mono-pcm16.wav'"
        in script
    )


def test_runtime_entrypoint_delegates_to_candidate_bound_python() -> None:
    script = (_BUNDLE / "start_w2_rehearsal.ps1").read_text(encoding="utf-8")

    assert "Join-Path ([string] $configValue.candidate_root)" in script
    assert "Join-Path $candidateBundle 'w2_rehearsal_runtime_controller.py'" in script
    assert "Join-Path $candidateBundle 'w2_wav_speech_preflight.py'" in script
    assert "machine-private.w2-rehearsal-runtime-config.v3" in script
    assert "machine-private.w2-rehearsal-runtime-config.v2" not in script


def test_runtime_entrypoint_forwards_only_the_private_config_reference() -> None:
    script = (_BUNDLE / "start_w2_rehearsal.ps1").read_text(encoding="utf-8")

    assert "[string] $PrivateConfig" in script
    assert "-PrivateConfig must be an absolute regular file" in script
    assert "@('--private-config', $privateConfigPath)" in script
    assert "$privateConfigValue" not in script
    assert "machine-private.live-voice-no-evidence-smoke.v1" not in script


def test_chrome_audio_modes_have_mutually_exclusive_argv_and_physical_has_no_wav_dependency() -> None:
    script = (_BUNDLE / "start_w2_rehearsal.ps1").read_text(encoding="utf-8")
    audio_modes = script.split("if ($PhysicalAudio) {", 1)[1]
    physical, prepared_tail = audio_modes.split("} else {", 1)
    prepared = prepared_tail.split("$process = Start-Process", 1)[0]
    fake_flags = (
        "--use-fake-device-for-media-stream",
        "--use-file-for-fake-audio-capture",
        "--use-fake-ui-for-media-stream",
    )

    assert "[switch] $PhysicalAudio" in script
    assert "$audioMode = 'physical'" in physical
    assert "Resolve-ExistingFile" not in physical
    assert all(flag not in physical for flag in fake_flags)
    assert "$audioMode = 'prepared_wav'" in prepared
    assert "Resolve-ExistingFile" in prepared
    assert all(flag in prepared for flag in fake_flags)
    assert "--autoplay-policy=no-user-gesture-required" in script
    assert "audio_mode=$audioMode" in script


def test_authoritative_runbooks_distinguish_prepared_and_physical_launches() -> None:
    toolkit = (_BUNDLE / "README.md").read_text(encoding="utf-8")
    e2e = (
        _BUNDLE.parents[2] / "live-voice" / "runbooks" / "E2E_RUNBOOK.md"
    ).read_text(encoding="utf-8")

    for document in (toolkit, e2e):
        assert "-PrivateConfig $privateConfig" in document
        assert "-Action Chrome -Config $config -PhysicalAudio" in document
        assert "audio_mode=physical" in document
        assert "start faults n" in document
        assert "wait faults n" in document
    assert "start faults 1" in toolkit
    assert "wait faults 3" in toolkit
    assert "Current diagnostic blockers" not in toolkit
    assert "machine-private.live-voice-no-evidence-smoke.v1" in toolkit
    assert "README.md#machine-private-provider-file" in e2e


def test_runtime_entrypoint_accepts_only_exact_v3_config_schema(
    tmp_path: Path,
) -> None:
    script = _BUNDLE / "start_w2_rehearsal.ps1"

    def invoke(schema: str) -> subprocess.CompletedProcess[str]:
        config = tmp_path / f"{schema.rsplit('.', 1)[-1]}.json"
        config.write_text(
            json.dumps(
                {
                    "schema": schema,
                    "candidate_root": str(tmp_path / "missing-candidate"),
                }
            ),
            encoding="utf-8",
        )
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Action",
                "Preflight",
                "-Config",
                str(config),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    legacy = invoke("machine-private.w2-rehearsal-runtime-config.v2")
    current = invoke("machine-private.w2-rehearsal-runtime-config.v3")

    assert legacy.returncode != 0
    assert "Runtime config schema is unsupported" in legacy.stderr
    assert current.returncode != 0
    assert "Runtime config schema is unsupported" not in current.stderr
    assert "Candidate-bound rehearsal toolkit is missing" in current.stderr


def test_wav_speech_preflight_emits_ascii_safe_json(monkeypatch) -> None:
    transcript = "语音联调成功"
    wav_path = _BUNDLE / "assets" / "voice-command-48k-mono-pcm16.wav"
    wav = wav_path.read_bytes()

    class FakeProvider:
        def __init__(self, config: object) -> None:
            del config

        async def recognize(
            self, request: batch_speech.ProviderRecognitionRequest
        ) -> batch_speech.ProviderRecognitionResult:
            del request
            return batch_speech.ProviderRecognitionResult(
                transcript,
                "zh-CN",
                "stt-test",
            )

        async def synthesize(
            self, request: batch_speech.ProviderSynthesisRequest
        ) -> batch_speech.ProviderSynthesisResult:
            del request
            return batch_speech.ProviderSynthesisResult(wav, "tts-test", "voice-test")

    raw_stdout = io.BytesIO()
    strict_cp1252 = io.TextIOWrapper(
        raw_stdout,
        encoding="cp1252",
        errors="strict",
        newline="\n",
    )
    monkeypatch.setenv("LIVE_VOICE_SPEECH_API_KEY", "test-only")
    monkeypatch.setattr(batch_speech, "OpenAICompatibleBatchSpeechProvider", FakeProvider)
    monkeypatch.setattr(sys, "stdout", strict_cp1252)

    assert asyncio.run(w2_wav_speech_preflight._run(wav_path)) == 0
    strict_cp1252.flush()
    raw = raw_stdout.getvalue()

    assert raw.isascii()
    prefix = b"W2_WAV_SPEECH_PREFLIGHT_RESULT "
    assert raw.startswith(prefix)
    payload = json.loads(raw.removeprefix(prefix))
    assert payload["ok"] is True
    assert payload["transcript"] == transcript
