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
