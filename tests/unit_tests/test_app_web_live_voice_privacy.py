# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
from types import SimpleNamespace

from jiuwenswarm.channels.web.app_web import _SpaStaticHandler


def test_web_proxy_log_omits_live_voice_audio_from_request_and_response() -> None:
    messages: list[tuple[object, ...]] = []
    handler = _SpaStaticHandler.__new__(_SpaStaticHandler)
    handler.logger = SimpleNamespace(info=lambda *args: messages.append(args))
    marker = "UklGRlBSSVZBVEVfUkFXX0FVRElPX01BUktFUg=="

    handler._log_ws_business_message(
        "frontend->backend",
        json.dumps(
            {
                "type": "req",
                "id": "request-1",
                "method": "live_voice.speech.recognize_batch",
                "params": {"audio": {"encoding": "wav", "data_base64": marker}},
            }
        ),
    )
    handler._log_ws_business_message(
        "backend->frontend",
        json.dumps(
            {
                "type": "res",
                "id": "request-1",
                "ok": True,
                "payload": {"chunks": [{"samples": [0.25, -0.25]}]},
            }
        ),
    )

    rendered = repr(messages)
    assert marker not in rendered
    assert "0.25" not in rendered
    assert rendered.count("<redacted:live-voice-private>") == 2


def test_web_proxy_log_omits_transcripts_credentials_and_media_capabilities() -> None:
    messages: list[tuple[object, ...]] = []
    handler = _SpaStaticHandler.__new__(_SpaStaticHandler)
    handler.logger = SimpleNamespace(info=lambda *args: messages.append(args))
    secrets = {
        "raw_text": "private recognized words",
        "final_text": "private final words",
        "display_text": "private display words",
        "spoken_text": "private spoken words",
        "text": "private agent response",
        "auth_token": "private-bearer-token",
        "media_ticket": "private-media-ticket",
        "voice_commit_receipt": "private-voice-commit-receipt",
        "subject_id": "live-voice-media:private-subject",
        "endpoint_path": "/ws/live-voice/media/private-ticket",
    }

    handler._log_ws_business_message(
        "backend->frontend",
        json.dumps(
            {
                "type": "res",
                "id": "request-privacy",
                "ok": True,
                "payload": {
                    **secrets,
                    "nested": {
                        "transcript": "private nested transcript",
                        "access_token": "private-access-token",
                    },
                },
            }
        ),
    )

    rendered = repr(messages)
    for private_value in (
        *secrets.values(),
        "private nested transcript",
        "private-access-token",
    ):
        assert private_value not in rendered
    assert rendered.count("<redacted:live-voice-private>") == 12


def test_web_proxy_log_redacts_json_wrapped_speech_key_variants_fail_closed() -> None:
    private_values = tuple(f"PRIVATE_SPEECH_VARIANT_{index}" for index in range(17))
    projected = _SpaStaticHandler._redact_ws_media_for_log(
        {
            "wrapped": json.dumps(
                {
                    "finalText": private_values[0],
                    "final_text": private_values[1],
                    "final-text": private_values[2],
                    "rawtext": private_values[3],
                    "rawText": private_values[4],
                    "voiceCommitReceipt": private_values[5],
                    "nested": json.dumps({"RAW-TEXT": private_values[6]}),
                }
            ),
            "malformedCamel": f'{{"voiceCommitReceipt":"{private_values[7]}"',
            "malformedCompact": f'{{"rawtext":"{private_values[8]}"',
            "malformedMixed": f'{{"final_-text":"{private_values[9]}"',
            "malformedMediaTicket": f'{{"media_ticket":"{private_values[10]}"',
            "malformedDataBase64": f'{{"data_base64":"{private_values[11]}"',
            "malformedAudioBase64": f'{{"audioBase64":"{private_values[12]}"',
            "malformedAudioBytes": f'{{"audio_bytes":"{private_values[13]}"',
            "malformedRawAudio": f'{{"raw-audio":"{private_values[14]}"',
            "malformedPcm": f'{{"pcm":"{private_values[15]}"',
            "malformedSamples": f'{{"samples":"{private_values[16]}"',
            "finalTextDigest": "safe-final-digest",
            "drawText": "safe-drawing-label",
            "voiceCommitmentReceipt": "safe-near-miss",
        }
    )

    rendered = json.dumps(projected)
    for private_value in private_values:
        assert private_value not in rendered
    wrapped = json.loads(projected["wrapped"])
    assert set(
        wrapped[key]
        for key in (
            "finalText",
            "final_text",
            "final-text",
            "rawtext",
            "rawText",
            "voiceCommitReceipt",
        )
    ) == {"<redacted:live-voice-private>"}
    assert json.loads(wrapped["nested"])["RAW-TEXT"] == (
        "<redacted:live-voice-private>"
    )
    assert projected["malformedCamel"] == "<redacted:live-voice-private>"
    assert projected["malformedCompact"] == "<redacted:live-voice-private>"
    assert projected["malformedMixed"] == "<redacted:live-voice-private>"
    assert projected["malformedMediaTicket"] == "<redacted:live-voice-private>"
    assert projected["malformedDataBase64"] == "<redacted:live-voice-private>"
    assert projected["malformedAudioBase64"] == "<redacted:live-voice-private>"
    assert projected["malformedAudioBytes"] == "<redacted:live-voice-private>"
    assert projected["malformedRawAudio"] == "<redacted:live-voice-private>"
    assert projected["malformedPcm"] == "<redacted:live-voice-private>"
    assert projected["malformedSamples"] == "<redacted:live-voice-private>"
    assert projected["finalTextDigest"] == "safe-final-digest"
    assert projected["drawText"] == "safe-drawing-label"
    assert projected["voiceCommitmentReceipt"] == "safe-near-miss"
