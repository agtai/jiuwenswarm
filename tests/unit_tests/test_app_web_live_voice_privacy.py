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
        "display_text": "private display words",
        "spoken_text": "private spoken words",
        "text": "private agent response",
        "auth_token": "private-bearer-token",
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
    for private_value in (*secrets.values(), "private nested transcript", "private-access-token"):
        assert private_value not in rendered
    assert rendered.count("<redacted:live-voice-private>") == 9
