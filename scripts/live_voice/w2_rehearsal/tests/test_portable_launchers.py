from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import sys

from jiuwenswarm.server.live_voice import batch_speech
from scripts.live_voice import formal_web_runtime_probe
from scripts.live_voice.w2_rehearsal import w2_wav_speech_preflight


_BUNDLE = Path(__file__).resolve().parents[1]
_LIVE_VOICE_SCRIPTS = _BUNDLE.parent


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


def test_formal_web_validation_uses_the_controlled_runtime_profile() -> None:
    launcher = (_LIVE_VOICE_SCRIPTS / "start_hands_free_demo.ps1").read_text(
        encoding="utf-8-sig"
    )
    wrapper = (_LIVE_VOICE_SCRIPTS / "start_formal_web_validation.cmd").read_text(
        encoding="utf-8"
    )

    assert "'hands-free-demo', 'formal-web-validation'" in launcher
    assert "JIUWENSWARM_LIVE_VOICE_RUNTIME_PROFILE" in launcher
    assert "requiredRuntimeFlags" in launcher
    assert "$ExecutorProfile = 'live-voice.direct-project-code.d2.v1'" in launcher
    assert "executor_profile          = $ExecutorProfile" in launcher
    assert "必须选择精确的 Direct D2 Executor profile" in launcher
    assert "live_voice_runtime_contract.json" in launcher
    assert "Formal Web 验证要求干净源码" in launcher
    assert "Wait-HttpResponse" in launcher
    assert "external_channels" in launcher
    assert 'bundleUrl = "http://127.0.0.1:$FrontendPort${assetPath}' in launcher
    assert "-RuntimeProfile formal-web-validation -RestartExisting" in wrapper
    assert "P3_AUTH_TOKEN" not in wrapper
    assert "SPEECH_API_KEY" not in wrapper


def test_formal_web_runtime_probe_binds_critical_receipt_and_rejects_forgery(
    monkeypatch,
) -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.synthesize_calls = 0
            self.recognize_calls = 0

        def capability(self) -> batch_speech.ProviderCapability:
            return batch_speech.ProviderCapability("probe-fake", True, True, True)

        async def synthesize(
            self, request: batch_speech.ProviderSynthesisRequest
        ) -> batch_speech.ProviderSynthesisResult:
            self.synthesize_calls += 1
            assert request.spoken_text == formal_web_runtime_probe.PROBE_TEXT
            return batch_speech.ProviderSynthesisResult(b"probe-wav", "tts-test", "voice-test")

        async def recognize(
            self, request: batch_speech.ProviderRecognitionRequest
        ) -> batch_speech.ProviderRecognitionResult:
            self.recognize_calls += 1
            assert request.audio_wav == b"probe-wav"
            return batch_speech.ProviderRecognitionResult(
                formal_web_runtime_probe.PROBE_TEXT,
                "zh-CN",
                "stt-test",
            )

    monkeypatch.setenv(
        "JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED", "1"
    )
    provider = FakeProvider()
    result = asyncio.run(formal_web_runtime_probe.run_probe(provider))

    assert result["provider_round_trip"] == "passed"
    assert result["critical_token_count"] >= 1
    assert result["gateway_claim_policy"] == "trusted_demo_bypass"
    assert result["identity_mismatch"] == "rejected"
    assert result["forged_claim"] == "rejected"
    assert result["business_effects"] == 0
    assert provider.synthesize_calls == 1
    assert provider.recognize_calls == 1
