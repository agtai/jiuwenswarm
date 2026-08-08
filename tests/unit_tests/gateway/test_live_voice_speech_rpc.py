# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import json
import base64
import io
import time
import wave
from typing import Any

import pytest

from jiuwenswarm.common.schema.message import Message
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
    _HANDLER_BEFORE_CALLBACK_METHODS,
    _LOCAL_HANDLER_ONLY_METHODS,
)
from jiuwenswarm.gateway.live_voice.speech_rpc import (
    CANCEL_METHOD,
    CAPABILITIES_METHOD,
    RECOGNIZE_BATCH_METHOD,
    SYNTHESIZE_BATCH_METHOD,
    register_speech_rpc_handlers,
)
from jiuwenswarm.server.live_voice.batch_speech import (
    BatchSpeechProvider,
    FormalBatchSpeechService,
    ProviderCapability,
    ProviderRecognitionRequest,
    ProviderRecognitionResult,
    ProviderSynthesisRequest,
    ProviderSynthesisResult,
    SpeechAuthorizationBinding,
    SpeechRpcContext,
    UnavailableBatchSpeechProvider,
)


def _wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 320)
    return output.getvalue()


class ExactAuthorizationResolver:
    def authorize(
        self, binding: SpeechAuthorizationBinding
    ) -> SpeechAuthorizationBinding:
        return binding


class CountingProvider(BatchSpeechProvider):
    def __init__(self) -> None:
        self.recognize_calls = 0

    def capability(self) -> ProviderCapability:
        return ProviderCapability("counting", True, True, True)

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        del request
        self.recognize_calls += 1
        return ProviderRecognitionResult("forbidden", "en", "stt")

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        del request
        raise AssertionError("synthesis must not run")


class FakeChannel:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.responses: list[dict[str, Any]] = []

    def register_method(self, method: str, handler: Any) -> None:
        self.handlers[method] = handler

    async def send_response(
        self,
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object],
    ) -> None:
        self.responses.append(
            {"ws": ws, "req_id": req_id, "ok": ok, "payload": payload}
        )


class SpyService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, SpeechRpcContext]] = []

    def capability_payload(self) -> dict[str, object]:
        return {"contract_version": "live-voice.contract.v2", "secret": False}

    async def recognize(
        self, payload: object, context: SpeechRpcContext
    ) -> dict[str, object]:
        self.calls.append(("recognize", payload, context))
        return {"ok": True, "result": {"route": "recognize"}}

    async def synthesize(
        self, payload: object, context: SpeechRpcContext
    ) -> dict[str, object]:
        self.calls.append(("synthesize", payload, context))
        return {"ok": True, "result": {"route": "synthesize"}}

    async def cancel(
        self, payload: object, context: SpeechRpcContext
    ) -> dict[str, object]:
        self.calls.append(("cancel", payload, context))
        return {"ok": True, "result": {"route": "cancel"}}


class SpyEvidenceObserver:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def observe_route(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return True


@pytest.mark.asyncio
async def test_rpc_registration_injects_exact_connection_identity_and_session() -> None:
    channel = FakeChannel()
    service = SpyService()
    registered = register_speech_rpc_handlers(channel, service=service)  # type: ignore[arg-type]

    assert registered is service
    assert set(channel.handlers) == {
        CAPABILITIES_METHOD,
        RECOGNIZE_BATCH_METHOD,
        SYNTHESIZE_BATCH_METHOD,
        CANCEL_METHOD,
    }
    payload = {"raw_audio_marker": "opaque-to-handler"}
    await channel.handlers[RECOGNIZE_BATCH_METHOD](
        "ws", "rpc-1", payload, "session-1", user_id="alice"
    )

    operation, seen_payload, context = service.calls[0]
    assert operation == "recognize"
    assert seen_payload is payload
    assert context == SpeechRpcContext("alice", "session-1")
    assert channel.responses == [
        {
            "ws": "ws",
            "req_id": "rpc-1",
            "ok": True,
            "payload": {"ok": True, "result": {"route": "recognize"}},
        }
    ]


@pytest.mark.asyncio
async def test_successful_speech_rpc_emits_only_exact_sanitized_p1_binding() -> None:
    channel = FakeChannel()
    service = SpyService()
    observer = SpyEvidenceObserver()
    register_speech_rpc_handlers(
        channel,
        service=service,  # type: ignore[arg-type]
        evidence_observer=observer,
        evidence_binding_factory=lambda _params, _session: {
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
        },
    )

    private_payload = {"audio": {"data_base64": "must-not-enter-evidence"}}
    await channel.handlers[RECOGNIZE_BATCH_METHOD](
        "ws", "rpc-evidence", private_payload, "session-1", user_id="alice"
    )

    assert observer.calls == [
        {
            "session_id": "session-1",
            "correlation_id": "correlation-1",
            "request_id": "rpc-evidence",
            "operation": "speech.recognize.batch",
            "result_ok": True,
            "interaction_id": "interaction-1",
            "response_id": None,
            "response_generation": None,
            "error_code": None,
        }
    ]
    assert "data_base64" not in json.dumps(observer.calls)


@pytest.mark.asyncio
async def test_result_transform_runs_before_evidence_and_response() -> None:
    channel = FakeChannel()
    service = SpyService()
    observer = SpyEvidenceObserver()
    transform_calls: list[tuple[object, ...]] = []

    def transform(
        operation: str,
        params: object,
        context: SpeechRpcContext,
        result: dict[str, object],
        session_id: str,
    ) -> dict[str, object]:
        transform_calls.append((operation, params, context, result, session_id))
        return {"ok": True, "result": {"route": "dedicated-downlink"}}

    register_speech_rpc_handlers(
        channel,
        service=service,  # type: ignore[arg-type]
        result_transform=transform,
        evidence_observer=observer,
        evidence_binding_factory=lambda _params, _session: {
            "correlation_id": "correlation-transform",
            "interaction_id": "interaction-transform",
        },
    )
    params = {"correlation_id": "correlation-transform"}

    await channel.handlers[SYNTHESIZE_BATCH_METHOD](
        "ws", "rpc-transform", params, "session-transform", user_id="alice"
    )

    assert transform_calls == [
        (
            "speech.synthesize.batch",
            params,
            SpeechRpcContext("alice", "session-transform"),
            {"ok": True, "result": {"route": "synthesize"}},
            "session-transform",
        )
    ]
    assert observer.calls[0]["result_ok"] is True
    assert channel.responses[0]["payload"] == {
        "ok": True,
        "result": {"route": "dedicated-downlink"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_result", [None, []])
async def test_result_transform_failure_is_closed_and_observed(
    invalid_result: object,
) -> None:
    channel = FakeChannel()
    service = SpyService()
    observer = SpyEvidenceObserver()
    register_speech_rpc_handlers(
        channel,
        service=service,  # type: ignore[arg-type]
        result_transform=lambda *_args: invalid_result,  # type: ignore[arg-type,return-value]
        evidence_observer=observer,
        evidence_binding_factory=lambda _params, _session: {
            "correlation_id": "correlation-transform-failure",
        },
    )

    await channel.handlers[SYNTHESIZE_BATCH_METHOD](
        "ws",
        "rpc-transform-failure",
        {"correlation_id": "correlation-transform-failure"},
        "session-transform",
        user_id="alice",
    )

    payload = channel.responses[0]["payload"]
    assert payload["ok"] is False
    assert payload["result"] is None
    assert payload["error"] == {
        "code": "CAPABILITY_UNAVAILABLE",
        "reason": "MEDIA_DOWNLINK_UNAVAILABLE",
        "message": "formal media downlink is unavailable",
        "retriable": False,
        "correlation_id": "correlation-transform-failure",
        "details": {},
    }
    assert observer.calls[0]["result_ok"] is False
    assert observer.calls[0]["error_code"] == "CAPABILITY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_missing_connection_subject_fails_before_provider_or_other_authority() -> (
    None
):
    channel = FakeChannel()
    service = FormalBatchSpeechService(UnavailableBatchSpeechProvider())
    register_speech_rpc_handlers(channel, service=service)
    payload = {
        "contract_version": "live-voice.contract.v2",
        "request_id": "request-1",
        "operation_id": "operation-1",
        "operation": "speech.recognize.batch",
        "correlation_id": "correlation-1",
        "session_id": "session-1",
        "scope": {
            "subject_id": "alice",
            "project_id": None,
            "session_id": "session-1",
            "assurance": "request_asserted",
        },
        "timeout_ms": 1000,
        "capture": {
            "capture_id": "capture-1",
            "capture_generation": 0,
            "track_id": "track-1",
            "final": True,
        },
        "audio": {
            "format": "wav_pcm16_mono",
            "sample_rate_hz": 16000,
            "channel_count": 1,
            "data_base64": "not-reached",
        },
        "locale": "en-US",
    }

    await channel.handlers[RECOGNIZE_BATCH_METHOD](
        "ws", "rpc-1", payload, "session-1", user_id=None
    )

    result = channel.responses[0]
    assert result["ok"] is True
    assert result["payload"]["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_forged_query_identity_cannot_authorize_real_provider_route() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    provider = CountingProvider()
    service = FormalBatchSpeechService(
        provider, authorization_resolver=ExactAuthorizationResolver()
    )
    register_speech_rpc_handlers(channel, service=service)
    callback_messages: list[object] = []
    responses: list[dict[str, object]] = []
    channel.on_message(lambda message: callback_messages.append(message))

    async def capture_response(
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> None:
        del ws, error, code
        responses.append({"req_id": req_id, "ok": ok, "payload": payload or {}})

    channel.send_response = capture_response  # type: ignore[method-assign]
    ws = type(
        "ForgedIdentityWebSocket",
        (),
        {"closed": False, "remote_address": ("127.0.0.1", 12345)},
    )()
    WebChannel._resolve_connection_user_id({"user_id": "forged-user"}, ws)
    params = {
        "contract_version": "live-voice.contract.v2",
        "request_id": "request-forged",
        "operation_id": "operation-forged",
        "operation": "speech.recognize.batch",
        "correlation_id": "correlation-forged",
        "session_id": "session-1",
        "scope": {
            "subject_id": "forged-user",
            "project_id": None,
            "session_id": "session-1",
            "assurance": "request_asserted",
        },
        "timeout_ms": 1000,
        "capture": {
            "capture_id": "capture-forged",
            "capture_generation": 1,
            "track_id": "track-1",
            "final": True,
        },
        "audio": {
            "format": "wav_pcm16_mono",
            "sample_rate_hz": 16_000,
            "channel_count": 1,
            "data_base64": base64.b64encode(_wav()).decode("ascii"),
        },
        "locale": "en-US",
    }

    await channel._handle_raw_message(
        ws,
        json.dumps(
            {
                "type": "req",
                "id": "rpc-forged",
                "method": RECOGNIZE_BATCH_METHOD,
                "params": params,
            }
        ),
        {"user_id": ["forged-user"]},
    )

    assert callback_messages == []
    assert provider.recognize_calls == 0
    assert responses[0]["payload"]["error"]["reason"] == (
        "SPEECH_AUTHENTICATED_IDENTITY_REQUIRED"
    )


def test_speech_methods_bypass_agent_callback_and_tool_task_authority() -> None:
    assert {
        CAPABILITIES_METHOD,
        RECOGNIZE_BATCH_METHOD,
        SYNTHESIZE_BATCH_METHOD,
        CANCEL_METHOD,
        "live_voice.media.activate",
        "live_voice.media.close",
        "live_voice.media.playout_receipt",
    } <= _HANDLER_BEFORE_CALLBACK_METHODS
    assert {
        CAPABILITIES_METHOD,
        RECOGNIZE_BATCH_METHOD,
        SYNTHESIZE_BATCH_METHOD,
        CANCEL_METHOD,
        "live_voice.media.activate",
        "live_voice.media.close",
        "live_voice.media.playout_receipt",
    } == _LOCAL_HANDLER_ONLY_METHODS


@pytest.mark.asyncio
async def test_web_channel_promotes_nested_product_error_without_dropping_reason() -> (
    None
):
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ws = type("ProductResponseWebSocket", (), {"closed": False})()
    channel._ws_by_id["ws-product"] = ws
    frames: list[dict[str, object]] = []
    channel._enqueue_send = lambda target, frame: frames.append(  # type: ignore[method-assign]
        {"target": target, **frame}
    )
    detail = {
        "code": "PERMISSION_DENIED",
        "reason": "TASK_CONTEXT_PERMISSION_MISSING",
        "message": "current product authority was revoked",
    }

    await channel.send(
        Message(
            id="request-product-error",
            type="res",
            channel_id="web",
            session_id="session-1",
            params={},
            timestamp=time.time(),
            ok=False,
            payload={"ok": False, "result": None, "error": detail},
            metadata={"ws_id": "ws-product"},
        )
    )

    assert frames == [
        {
            "target": ws,
            "type": "res",
            "id": "request-product-error",
            "ok": False,
            "payload": {"ok": False, "result": None, "error": detail},
            "error": "current product authority was revoked",
            "code": "PERMISSION_DENIED",
        }
    ]


@pytest.mark.asyncio
async def test_raw_speech_rpc_never_enters_agent_message_callback() -> None:
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    service = SpyService()
    register_speech_rpc_handlers(channel, service=service)  # type: ignore[arg-type]
    callback_messages: list[object] = []
    responses: list[dict[str, object]] = []
    channel.on_message(lambda message: callback_messages.append(message))

    async def capture_response(
        ws: Any,
        req_id: str,
        *,
        ok: bool,
        payload: dict[str, object] | None = None,
        error: str | None = None,
        code: str | None = None,
    ) -> None:
        del ws, error, code
        responses.append({"req_id": req_id, "ok": ok, "payload": payload or {}})

    channel.send_response = capture_response  # type: ignore[method-assign]
    ws = type(
        "SpeechWebSocket",
        (),
        {"closed": False, "remote_address": ("127.0.0.1", 12345)},
    )()
    WebChannel._resolve_connection_user_id({"user_id": "alice"}, ws)
    params = {"session_id": "session-1", "opaque": "speech-only"}

    await channel._handle_raw_message(
        ws,
        json.dumps(
            {
                "type": "req",
                "id": "rpc-raw",
                "method": RECOGNIZE_BATCH_METHOD,
                "params": params,
            }
        ),
        {"user_id": ["alice"]},
    )

    assert callback_messages == []
    assert service.calls[0][0] == "recognize"
    assert responses == [
        {
            "req_id": "rpc-raw",
            "ok": True,
            "payload": {"ok": True, "result": {"route": "recognize"}},
        }
    ]
