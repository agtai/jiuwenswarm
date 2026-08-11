from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path


async def _run(wav_path: Path) -> int:
    from jiuwenswarm.server.live_voice.batch_speech import (
        BatchSpeechError,
        OpenAICompatibleBatchSpeechProvider,
        OpenAICompatibleSpeechConfig,
        ProviderRecognitionRequest,
        ProviderSynthesisRequest,
        inspect_pcm16_mono_wav,
    )

    api_key = os.environ.get("LIVE_VOICE_SPEECH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("hidden Speech key was not provided")
    audio = wav_path.read_bytes()
    source = inspect_pcm16_mono_wav(audio, expected_sample_rate_hz=48_000)
    provider = OpenAICompatibleBatchSpeechProvider(
        OpenAICompatibleSpeechConfig(
            os.environ.get("LIVE_VOICE_SPEECH_API_BASE", "https://api.openai.com/v1"),
            api_key,
            os.environ.get("LIVE_VOICE_SPEECH_STT_MODEL", "gpt-4o-mini-transcribe"),
            os.environ.get("LIVE_VOICE_SPEECH_TTS_MODEL", "gpt-4o-mini-tts"),
            os.environ.get("LIVE_VOICE_SPEECH_TTS_VOICE", "marin"),
        )
    )
    try:
        recognition = await provider.recognize(
            ProviderRecognitionRequest("w2-wav-stt", audio, "zh-CN")
        )
        synthesis = await provider.synthesize(
            ProviderSynthesisRequest(
                "w2-wav-tts",
                "语音联调成功",
                "zh-CN",
                None,
                48_000,
            )
        )
        rendered = inspect_pcm16_mono_wav(
            synthesis.audio_wav,
            expected_sample_rate_hz=48_000,
        )
    except BatchSpeechError as error:
        print(
            "W2_WAV_SPEECH_PREFLIGHT_RESULT "
            + json.dumps(
                {
                    "ok": False,
                    "code": error.error.code.value,
                    "reason": error.error.reason,
                    "retriable": error.error.retriable,
                }
            ),
            flush=True,
        )
        return 2
    print(
        "W2_WAV_SPEECH_PREFLIGHT_RESULT "
        + json.dumps(
            {
                "ok": True,
                "input_sha256": hashlib.sha256(audio).hexdigest(),
                "input_duration_ms": source.duration_ms,
                "input_sample_rate_hz": source.sample_rate_hz,
                "transcript": recognition.text,
                "observed_locale": recognition.observed_locale,
                "stt_model": recognition.model,
                "tts_model": synthesis.model,
                "voice": synthesis.voice,
                "output_wav_bytes": len(synthesis.audio_wav),
                "output_duration_ms": rendered.duration_ms,
                "output_sample_rate_hz": rendered.sample_rate_hz,
                "output_channels": rendered.channel_count,
                "output_sample_width_bytes": rendered.sample_width_bytes,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", type=Path, required=True)
    args = parser.parse_args()
    wav_path = args.wav.resolve(strict=True)
    return asyncio.run(_run(wav_path))


if __name__ == "__main__":
    sys.exit(main())
