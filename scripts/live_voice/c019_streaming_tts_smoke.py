#!/usr/bin/env python3
"""One explicitly opted-in, content-free OpenAI streaming-TTS smoke."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections.abc import Mapping
from typing import Any

from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.server.live_voice.openai_streaming_speech import (
    SpeechRouteTier,
    select_environment_streaming_speech,
)
from jiuwenswarm.server.live_voice.speech_ports import SynthesisEventKind
from jiuwenswarm.server.live_voice.streaming_speech import (
    SynthesisStreamRef,
    SynthesisStreamRequest,
    TextSpan,
)


_LOGGER = logging.getLogger("jiuwenswarm.server.live_voice.openai_streaming_speech")
_OPT_IN_ENV = "LIVE_VOICE_C019_REAL_PROVIDER_SMOKE"
_SAFE_TEXT = "This is a short streaming speech diagnostic."
_SUBREASON = re.compile(r"\bprovider_subreason=([A-Z0-9_]+)\b")


class _SubreasonCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.value: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        match = _SUBREASON.search(record.getMessage())
        if match is not None:
            self.value = match.group(1)


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_smoke_environment(environ: Mapping[str, str]) -> dict[str, object]:
    """Validate the explicit real-call boundary without exposing a secret."""

    if not _enabled(environ.get(_OPT_IN_ENV)):
        return {"ok": False, "reason": "REAL_PROVIDER_SMOKE_NOT_OPTED_IN"}
    if not _enabled(environ.get("LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED")):
        return {"ok": False, "reason": "STREAMING_SPEECH_FEATURE_OFF"}
    if str(environ.get("LIVE_VOICE_SPEECH_PROVIDER") or "").strip().lower() != "openai":
        return {"ok": False, "reason": "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"}
    if not str(environ.get("LIVE_VOICE_SPEECH_API_BASE") or "").strip():
        return {"ok": False, "reason": "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"}
    if not str(environ.get("LIVE_VOICE_SPEECH_API_KEY") or "").strip():
        return {"ok": False, "reason": "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"}
    tts_model = str(environ.get("LIVE_VOICE_SPEECH_TTS_MODEL") or "").strip()
    tts_voice = str(environ.get("LIVE_VOICE_SPEECH_TTS_VOICE") or "").strip()
    if not tts_model or not tts_voice:
        return {"ok": False, "reason": "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"}
    return {"ok": True, "tts_model": tts_model, "tts_voice": tts_voice}


async def run_smoke(
    environ: Mapping[str, str],
    *,
    selector: Any | None = None,
) -> dict[str, object]:
    validated = validate_smoke_environment(environ)
    if validated["ok"] is not True:
        return validated
    started = time.monotonic()
    capture = _SubreasonCapture()
    _LOGGER.addHandler(capture)
    provider: Any = None
    pause_acknowledged = False
    resume_requested = False
    try:
        selected_provider = select_environment_streaming_speech if selector is None else selector
        selection = await selected_provider(
            environ=environ,
            batch_available=False,
        )
        if selection.tier is not SpeechRouteTier.STREAMING or selection.provider is None:
            return {
                "ok": False,
                "reason": (
                    selection.fact.reason.value
                    if selection.fact is not None
                    else "STREAMING_SPEECH_CONFIGURATION_UNAVAILABLE"
                ),
            }
        provider = selection.provider
        response = ResponseRef("c019-smoke", "c019-streaming-tts-smoke", 0)
        request = SynthesisStreamRequest(
            ref=SynthesisStreamRef("c019-streaming-tts-smoke", 0, response, "unit-0", 0),
            display_text="streaming diagnostic",
            spoken_text=_SAFE_TEXT,
            display_span=TextSpan(0, len("streaming diagnostic")),
            sample_rate_hz=48_000,
            event_timeout_seconds=10.0,
        )
        provider.conformance.activate_response(response)
        await provider.open_synthesis(request)
        await provider.pause_synthesis(request.ref)
        pause_acknowledged = True
        await asyncio.sleep(0.2)
        await provider.resume_synthesis(request.ref)
        resume_requested = True
        kinds: list[str] = []
        first_audio = False
        while True:
            event = await provider.next_synthesis_event(request.ref, timeout_seconds=12.0)
            kinds.append(event.kind.value)
            if event.kind is SynthesisEventKind.CHUNK:
                first_audio = True
            if event.kind is SynthesisEventKind.COMPLETED:
                return {
                    "ok": first_audio,
                    "reason": None if first_audio else "STREAMING_TTS_NO_AUDIO",
                    "tts_model": validated["tts_model"],
                    "tts_voice": validated["tts_voice"],
                    "first_audio_received": first_audio,
                    "pause_acknowledged": pause_acknowledged,
                    "resume_requested": resume_requested,
                    "event_kinds": kinds,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                }
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException:
        return {
            "ok": False,
            "reason": capture.value or "STREAMING_TTS_SMOKE_FAILED",
            "tts_model": validated["tts_model"],
            "tts_voice": validated["tts_voice"],
            "first_audio_received": False,
            "pause_acknowledged": pause_acknowledged,
            "resume_requested": resume_requested,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }
    finally:
        _LOGGER.removeHandler(capture)
        if provider is not None:
            await provider.close()


def main() -> int:
    result = asyncio.run(run_smoke(os.environ))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":
    sys.exit(main())
