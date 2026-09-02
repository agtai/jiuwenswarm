import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts/live_voice/c019_streaming_tts_smoke.py"
)
_SPEC = importlib.util.spec_from_file_location("c019_streaming_tts_smoke", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_smoke_configuration_refuses_provider_construction_without_opt_in() -> None:
    result = _MODULE.validate_smoke_environment(
        {
            "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED": "1",
            "LIVE_VOICE_SPEECH_PROVIDER": "openai",
            "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
            "LIVE_VOICE_SPEECH_API_KEY": "private-test-key",
            "LIVE_VOICE_SPEECH_TTS_MODEL": "gpt-4o-mini-tts-2025-12-15",
            "LIVE_VOICE_SPEECH_TTS_VOICE": "marin",
        }
    )

    assert result == {
        "ok": False,
        "reason": "REAL_PROVIDER_SMOKE_NOT_OPTED_IN",
    }


def test_smoke_configuration_exposes_only_safe_provider_labels() -> None:
    result = _MODULE.validate_smoke_environment(
        {
            "LIVE_VOICE_C019_REAL_PROVIDER_SMOKE": "1",
            "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED": "1",
            "LIVE_VOICE_SPEECH_PROVIDER": "openai",
            "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
            "LIVE_VOICE_SPEECH_API_KEY": "private-test-key",
            "LIVE_VOICE_SPEECH_TTS_MODEL": "gpt-4o-mini-tts-2025-12-15",
            "LIVE_VOICE_SPEECH_TTS_VOICE": "marin",
        }
    )

    assert result == {
        "ok": True,
        "tts_model": "gpt-4o-mini-tts-2025-12-15",
        "tts_voice": "marin",
    }
    assert "private-test-key" not in repr(result)


@pytest.mark.asyncio
async def test_smoke_rethrows_process_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def cancelled_selection(**_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(_MODULE, "select_environment_streaming_speech", cancelled_selection)
    with pytest.raises(asyncio.CancelledError):
        await _MODULE.run_smoke(
            {
                "LIVE_VOICE_C019_REAL_PROVIDER_SMOKE": "1",
                "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED": "1",
                "LIVE_VOICE_SPEECH_PROVIDER": "openai",
                "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
                "LIVE_VOICE_SPEECH_API_KEY": "private-test-key",
                "LIVE_VOICE_SPEECH_TTS_MODEL": "gpt-4o-mini-tts-2025-12-15",
                "LIVE_VOICE_SPEECH_TTS_VOICE": "marin",
            }
        )


@pytest.mark.asyncio
async def test_smoke_reports_first_audio_and_completion_from_injected_provider() -> None:
    class FakeConformance:
        def activate_response(self, _response) -> None:
            return None

    class FakeProvider:
        def __init__(self) -> None:
            self.conformance = FakeConformance()
            self.events = [
                SimpleNamespace(kind=_MODULE.SynthesisEventKind.STARTED),
                SimpleNamespace(kind=_MODULE.SynthesisEventKind.CHUNK),
                SimpleNamespace(kind=_MODULE.SynthesisEventKind.COMPLETED),
            ]
            self.closed = False
            self.paused = 0
            self.resumed = 0

        async def open_synthesis(self, _request) -> None:
            return None

        async def next_synthesis_event(self, _ref, *, timeout_seconds: float):
            assert timeout_seconds == 12.0
            return self.events.pop(0)

        async def pause_synthesis(self, _ref) -> None:
            self.paused += 1

        async def resume_synthesis(self, _ref) -> None:
            self.resumed += 1

        async def close(self) -> None:
            self.closed = True

    provider = FakeProvider()

    async def selector(**_kwargs):
        return SimpleNamespace(
            tier=_MODULE.SpeechRouteTier.STREAMING,
            provider=provider,
            fact=None,
        )

    result = await _MODULE.run_smoke(
        {
            "LIVE_VOICE_C019_REAL_PROVIDER_SMOKE": "1",
            "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED": "1",
            "LIVE_VOICE_SPEECH_PROVIDER": "openai",
            "LIVE_VOICE_SPEECH_API_BASE": "https://api.openai.com/v1",
            "LIVE_VOICE_SPEECH_API_KEY": "private-test-key",
            "LIVE_VOICE_SPEECH_TTS_MODEL": "gpt-4o-mini-tts-2025-12-15",
            "LIVE_VOICE_SPEECH_TTS_VOICE": "marin",
        },
        selector=selector,
    )

    assert result["ok"] is True
    assert result["first_audio_received"] is True
    assert result["pause_acknowledged"] is True
    assert result["resume_requested"] is True
    assert result["event_kinds"] == ["started", "chunk", "completed"]
    assert provider.paused == provider.resumed == 1
    assert provider.closed is True
