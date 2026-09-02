# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import replace
import base64
import hashlib
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
    MediaAck,
    MediaAudioFrame,
    MediaDetach,
    MediaDetachReason,
    MediaTransportViolation,
    deserialize_media_control,
    encode_audio_frame,
    serialize_media_control,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_registration import (
    DedicatedMediaProductRegistry,
    MEDIA_AUTH_CONTRACT_VERSION,
    MEDIA_ACTIVATE_METHOD,
    MEDIA_PREFETCH_CAPABILITY_METHOD,
    register_dedicated_media_rpc_handlers,
    handle_registered_media_socket,
)
from jiuwenswarm.gateway.live_voice.dedicated_media_route import (
    DedicatedMediaSocketLeafResult,
)
from jiuwenswarm.gateway.live_voice import dedicated_media_registration
from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_connect import (
    WebChannel,
    WebChannelConfig,
)
from jiuwenswarm.gateway.channel_manager.web import web_connect
from jiuwenswarm.server.live_voice.batch_speech import (
    BatchSpeechProvider,
    FormalBatchSpeechService,
    ProviderCapability,
    ProviderRecognitionRequest,
    ProviderRecognitionResult,
    ProviderSynthesisRequest,
    ProviderSynthesisResult,
    RECOGNIZE_OPERATION,
    SYNTHESIZE_OPERATION,
    SpeechAuthorizationBinding,
    SpeechRpcContext,
)
from jiuwenswarm.server.live_voice.latency_measurement import L0Milestone


ORIGIN = "https://voice.example.test"


def _wav(sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * 320)
    return output.getvalue()


class _CountingBatchSpeechProvider(BatchSpeechProvider):
    def __init__(self) -> None:
        self.synthesize_calls = 0

    def capability(self) -> ProviderCapability:
        return ProviderCapability("counting", True, True, True)

    async def recognize(
        self, request: ProviderRecognitionRequest
    ) -> ProviderRecognitionResult:
        del request
        raise AssertionError("recognition is outside this speech-authority test")

    async def synthesize(
        self, request: ProviderSynthesisRequest
    ) -> ProviderSynthesisResult:
        self.synthesize_calls += 1
        return ProviderSynthesisResult(
            _wav(request.required_sample_rate_hz), "counting-tts", "counting-voice"
        )


def _params(**updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "session_id": "session-1",
        "interaction_id": "interaction-1",
        "correlation_id": "correlation-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
        "capture_id": "capture-1",
        "capture_generation": 0,
        "track_id": "track-1",
        "sample_rate_hz": 16_000,
        "locale": "zh-CN",
    }
    result.update(updates)
    return result


@pytest.fixture(autouse=True)
def _allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "voice.example.test")


def _active_registry() -> DedicatedMediaProductRegistry:
    registry = DedicatedMediaProductRegistry(enabled=True)
    registry.set_provider_available(True)
    return registry


def _media_ticket(descriptor: dict[str, object]) -> str:
    assert descriptor["endpoint_path"] == "/ws/live-voice/media"
    ticket = descriptor["media_ticket"]
    assert isinstance(ticket, str)
    return ticket


def _pending_record(registry: DedicatedMediaProductRegistry, ticket: str) -> object:
    return registry._records[registry._pending_tickets[ticket]]


def _media_auth_frame(descriptor: dict[str, object]) -> str:
    return json.dumps(
        {
            "type": "media.auth",
            "contract_version": MEDIA_AUTH_CONTRACT_VERSION,
            "media_ticket": _media_ticket(descriptor),
            "binding": descriptor["binding"],
        },
        separators=(",", ":"),
    )


class _AuthOnlySocket:
    subprotocol = "live-voice.media.v1"
    request_headers = {"Origin": ORIGIN}

    def __init__(self, descriptor: dict[str, object]) -> None:
        self._auth_frame = _media_auth_frame(descriptor)

    async def recv(self) -> str:
        return self._auth_frame

    async def close(self, _code: int = 1000, _reason: str = "") -> None:
        return None


def _formal_p2_manifest() -> dict[str, object]:
    return {
        "contract_version": "live-voice.product-composition.gate0.v1",
        "enabled": True,
        "routes": [
            {
                "segment": "p2.agent_interaction",
                "truth": "formal",
                "reason_id": "FORMAL_ROUTE_OBSERVED",
                "evidence_ids": [
                    "TRUSTED_AUTHORITY_RESOLVED",
                    "FORMAL_ACTIVATION_LEASE_OPEN",
                    "RUNTIME_PATH_OBSERVED",
                    "P2_NOTIFICATION_BACKPRESSURE_CLOSED",
                ],
                "formal_runtime_observed": True,
            }
        ],
    }


def _trust_product_activation(
    registry: DedicatedMediaProductRegistry,
    params: dict[str, object],
    *,
    user_id: str | None = "user-1",
    connection_id: str = "connection-1",
) -> None:
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "active",
                "session_id": params["session_id"],
                "correlation_id": params["correlation_id"],
                "interaction_id": params["interaction_id"],
                "activation_id": params["activation_id"],
                "activation_generation": params["activation_generation"],
            },
            "product_composition": _formal_p2_manifest(),
        },
        routed_session_id=str(params["session_id"]),
        user_id=user_id,
        connection_id=connection_id,
        request_method="live_voice.composition.p2.activate",
    )


def _activate(
    registry: DedicatedMediaProductRegistry,
    *,
    params: dict[str, object],
    request_origin: str | None,
    connection_id: str,
    user_id: str | None = "user-1",
) -> dict[str, object]:
    _trust_product_activation(
        registry, params, user_id=user_id, connection_id=connection_id
    )
    return registry.activate(
        params=params,
        request_origin=request_origin,
        connection_id=connection_id,
        user_id=user_id,
    )


def test_feature_off_and_provider_off_create_no_route() -> None:
    disabled = DedicatedMediaProductRegistry(enabled=False)
    assert disabled.activate(
        params={}, request_origin=None, connection_id="connection-1"
    ) == {"status": "disabled", "reason_id": "MEDIA_FEATURE_DISABLED"}

    unavailable = DedicatedMediaProductRegistry(enabled=True)
    assert unavailable.activate(
        params={}, request_origin=None, connection_id="connection-1"
    ) == {
        "status": "unavailable",
        "reason_id": "MEDIA_PROVIDER_UNAVAILABLE",
    }


@pytest.mark.asyncio
async def test_prefetch_capability_negotiation_binds_exact_activation() -> None:
    registry = _active_registry()
    params = _params()
    _activate(
        registry,
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )

    class _Owner:
        async def parked_pause_available(self) -> bool:
            return True

    registry._streaming_synthesis_owner = _Owner()  # type: ignore[assignment]
    selected = await registry.negotiate_prefetch_promotion(
        params={
            "session_id": "session-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
            "offered": ["live-voice.media.prefetch-promotion.v1"],
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id=None,
    )
    assert selected == {"selected": "live-voice.media.prefetch-promotion.v1"}

    unavailable = await registry.negotiate_prefetch_promotion(
        params={
            "session_id": "session-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
            "offered": [],
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    assert unavailable == {"selected": None}
    registered: dict[str, object] = {}

    class _Channel:
        def register_method(self, name: str, handler: object) -> None:
            registered[name] = handler

    register_dedicated_media_rpc_handlers(_Channel(), registry=registry)
    assert MEDIA_PREFETCH_CAPABILITY_METHOD in registered


def test_websocket_transport_debug_cannot_persist_binary_media(
    tmp_path: Path,
) -> None:
    path = tmp_path / "websocket-transport.log"
    sink = logging.FileHandler(path, encoding="utf-8")
    transport_logger = web_connect._websocket_transport_logger
    previous_level = transport_logger.level
    transport_logger.setLevel(logging.DEBUG)
    transport_logger.addHandler(sink)
    marker = "PRIVATE_BINARY_PCM_MARKER"
    try:
        transport_logger.debug("< BINARY %s", marker)
        transport_logger.info("transport lifecycle only")
        sink.flush()
    finally:
        transport_logger.removeHandler(sink)
        sink.close()
        transport_logger.setLevel(previous_level)

    rendered = path.read_text("utf-8")
    assert marker not in rendered
    assert "transport lifecycle only" in rendered


@pytest.mark.parametrize(
    ("params", "origin"),
    [
        ({**_params(), "unknown": True}, ORIGIN),
        ({key: value for key, value in _params().items() if key != "track_id"}, ORIGIN),
        (_params(sample_rate_hz=15_999), ORIGIN),
        (_params(locale="fr-FR"), ORIGIN),
        (_params(), "https://other.example.test"),
        (_params(), None),
    ],
)
def test_activation_rejects_unclosed_or_untrusted_inputs(
    params: dict[str, object], origin: str | None
) -> None:
    with pytest.raises(MediaTransportViolation):
        _active_registry().activate(
            params=params, request_origin=origin, connection_id="connection-1"
        )


def test_ticket_is_single_use_and_exact_origin_bound() -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)

    assert (
        registry.consume_ticket(ticket, request_origin="https://other.example.test")
        is None
    )
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is None


def test_stock_web_empty_identity_uses_connection_owned_p2_authority() -> None:
    registry = _active_registry()
    params = _params()
    _trust_product_activation(
        registry,
        params,
        user_id=None,
        connection_id="stock-web-connection",
    )

    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="stock-web-connection",
        user_id=None,
    )

    assert activation["status"] == "active"
    assert activation["reason_id"] == "MEDIA_ROUTE_TICKET_ISSUED"
    assert activation["binding"]["connection_id"] == "stock-web-connection"
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    context = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="stock-web-connection"),
        {"scope": {"subject_id": activation["subject_id"]}},
        "session-1",
        None,
    )
    assert context.assurance is Assurance.AUTHENTICATED


def test_browser_identity_claim_cannot_mint_or_transfer_media_authority() -> None:
    registry = _active_registry()
    params = _params()
    with pytest.raises(MediaTransportViolation) as untrusted:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="browser-static-claim",
        )
    assert untrusted.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._records == {}
    assert registry._subjects == {}

    _trust_product_activation(
        registry,
        params,
        user_id="browser-static-claim",
        connection_id="connection-1",
    )
    with pytest.raises(MediaTransportViolation) as foreign:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-foreign",
            user_id="browser-static-claim",
        )
    assert foreign.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._records == {}
    assert registry._subjects == {}

    scope = ScopeRef("browser-static-claim", None, "session-1", Assurance.AUTHENTICATED)
    unauthorized_speech = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="forged-browser-recognition",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256="a" * 64,
    )
    assert registry.authorize(unauthorized_speech) is None

    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="changed-browser-claim",
    )
    assert activation["status"] == "active"
    assert activation["binding"]["connection_id"] == "connection-1"
    assert "browser-static-claim" not in repr(activation)
    assert "changed-browser-claim" not in repr(activation)


def test_partial_capture_never_authorizes_speech() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    record.recognition_content_sha256 = "a" * 64
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    binding = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-partial",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256="a" * 64,
    )

    assert registry.authorize(binding) is None


def test_expired_unconsumed_ticket_releases_capacity_before_authority_ttl() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        ticket_ttl_seconds=1,
        authority_ttl_seconds=100,
        capacity=1,
    )
    registry.set_provider_available(True)
    _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    now = 2.0

    replacement = _activate(
        registry,
        params=_params(
            capture_id="capture-2",
            track_id="track-2",
            activation_id="activation-2",
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )

    assert replacement["status"] == "active"
    assert len(registry._records) == 1


def test_consumed_downlink_survives_ticket_ttl_until_authority_terminal() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        ticket_ttl_seconds=1,
        authority_ttl_seconds=100,
    )
    registry.set_provider_available(True)
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None

    now = 2.0
    assert registry.consume_ticket("Z" * 43, request_origin=ORIGIN) is None
    assert record in registry._records.values()
    assert record.ticket_consumed is True


def test_exact_media_close_is_idempotent_and_revokes_all_speech_authority() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.recognition_content_sha256 = "a" * 64
    close = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }

    first = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )
    replay = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )

    assert first == replay
    assert registry._records == {}
    assert record.recognition_content_sha256 is None
    assert record.synthesis_content_sha256 == {}
    with pytest.raises(MediaTransportViolation) as forged:
        registry.revoke(
            params=close,
            routed_session_id="session-1",
            connection_id="connection-forged",
            user_id="user-1",
        )
    assert forged.value.reason_id == "MEDIA_CLOSE_BINDING_MISMATCH"


def test_product_activation_expiry_retains_exact_media_close_tombstone() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-owner")
    now = 9.0
    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-owner",
        user_id="user-1",
    )
    ticket = _media_ticket(activation)
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is not None
    close = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }

    # The media authority itself is still live, but pruning the older P2
    # activation revokes it first. The browser's later exact close must remain
    # idempotent instead of becoming permanently cleanup_pending.
    now = 11.0
    first = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )
    replay = registry.revoke(
        params=close,
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )

    assert first == replay
    assert first["reason_id"] == "MEDIA_ROUTE_REVOKED"
    assert registry._records == {}
    with pytest.raises(MediaTransportViolation) as forged:
        registry.revoke(
            params=close,
            routed_session_id="session-1",
            connection_id="connection-forged",
            user_id="user-1",
        )
    assert forged.value.reason_id == "MEDIA_CLOSE_BINDING_MISMATCH"


def test_media_authority_expiry_retains_exact_media_close_tombstone() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-owner")
    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-owner",
        user_id="user-1",
    )
    ticket = _media_ticket(activation)
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is not None

    now = 11.0
    close = registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": activation["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-owner",
        user_id="user-1",
    )

    assert close["reason_id"] == "MEDIA_ROUTE_REVOKED"
    assert registry._records == {}


def test_exact_final_notification_renews_live_product_media_trust() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")
    now = 9.0
    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True

    now = 9.5
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "authoritative response",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    now = 11.0
    context = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="connection-1"),
        {"scope": {"subject_id": activation["subject_id"]}},
        "session-1",
        "user-1",
    )
    assert context.assurance is Assurance.AUTHENTICATED
    assert registry._records


def test_expired_product_activation_cannot_be_revived_by_late_notification() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")

    now = 11.0
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-late",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "late response",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-late"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert registry._product_activations == {}
    with pytest.raises(MediaTransportViolation) as rejected:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert rejected.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"


def test_exact_p2_activation_replay_reestablishes_expired_media_trust() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")

    now = 11.0
    with pytest.raises(MediaTransportViolation) as expired:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert expired.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"

    # The browser's explicit Start first replays this exact authoritative P2
    # activation. The observed AgentServer response may establish a new short-
    # lived media authority; no client-only binding can do so.
    _trust_product_activation(registry, params, connection_id="connection-1")
    activated = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )

    assert activated["status"] == "active"
    assert activated["binding"]["interaction_id"] == "interaction-1"


def test_cross_session_route_notification_cannot_renew_product_activation() -> None:
    now = 0.0
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now,
        authority_ttl_seconds=10,
    )
    registry.set_provider_available(True)
    params = _params()
    _trust_product_activation(registry, params, connection_id="connection-1")

    now = 9.0
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-cross-session",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "cross-session response",
                },
                "presentation_unit": {
                    "surface": "text",
                    "unit_id": "unit-cross-session",
                },
            },
        },
        routed_session_id="session-foreign",
        user_id="user-1",
        connection_id="connection-1",
    )

    now = 11.0
    with pytest.raises(MediaTransportViolation) as rejected:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert rejected.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._product_activations == {}


def test_speech_context_requires_the_exact_activation_connection() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    params = {"scope": {"subject_id": activation["subject_id"]}}

    owner = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="connection-owner"),
        params,
        "session-1",
        "user-1",
    )
    foreign = registry.context_for(
        SimpleNamespace(_jiuwen_ws_id="connection-foreign"),
        params,
        "session-1",
        "user-1",
    )

    assert owner.assurance is Assurance.AUTHENTICATED
    assert foreign.assurance is Assurance.REQUEST_ASSERTED


@pytest.mark.asyncio
async def test_activation_handler_rejects_a_forged_session_before_allocation() -> None:
    registry = _active_registry()
    registered: dict[str, object] = {}
    responses: list[dict[str, object]] = []

    class Channel:
        def register_method(self, name: str, handler: object) -> None:
            registered[name] = handler

        async def send_response(
            self,
            _ws: object,
            _req_id: str,
            *,
            ok: bool,
            payload: object = None,
            error: object = None,
            code: object = None,
        ) -> None:
            responses.append(
                {"ok": ok, "payload": payload, "error": error, "code": code}
            )

    channel = Channel()
    register_dedicated_media_rpc_handlers(channel, registry=registry)
    handler = registered[MEDIA_ACTIVATE_METHOD]
    await handler(  # type: ignore[operator]
        SimpleNamespace(
            _jiuwen_ws_id="connection-owner",
            request_headers={"Origin": ORIGIN},
        ),
        "request-1",
        _params(session_id="session-forged"),
        "session-dispatcher",
        None,
    )

    assert responses == [
        {
            "ok": False,
            "payload": None,
            "error": "media activation must target the dispatcher-owned session",
            "code": "MEDIA_SESSION_MISMATCH",
        }
    ]
    assert registry._records == {}


@pytest.mark.asyncio
async def test_exceptional_media_socket_exit_clears_every_raw_audio_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)

    async def fail_after_frame(*_args: object, **kwargs: object) -> object:
        callback = kwargs["on_audio_frame"]
        callback(  # type: ignore[operator]
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
        )
        raise RuntimeError("socket leaf failed")

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        fail_after_frame,
    )
    ws = _AuthOnlySocket(activation)

    with pytest.raises(RuntimeError, match="socket leaf failed"):
        await handle_registered_media_socket(registry, ws, endpoint_path)

    assert record.route_completed is True
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is None


def test_uplink_consumer_failure_logs_safe_callback_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    record = _pending_record(registry, _media_ticket(activation))
    frame = MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
    observed: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        dedicated_media_registration._LOGGER,
        "warning",
        lambda template, *args: observed.append((template, *args)),
    )

    dedicated_media_registration._log_uplink_consumer_failure(
        record,
        frame,
        phase="streaming_frame",
        error=RuntimeError("streaming consumer failed"),
    )

    assert len(observed) == 1
    template, *args = observed[0]
    message = str(template) % tuple(args)
    assert "live_voice_uplink_consumer_failed phase=streaming_frame" in message
    assert f"session_id={record.binding.session_id}" in message
    assert "frame_seq=0" in message
    assert "error_type=RuntimeError" in message
    assert "streaming consumer failed" not in message


@pytest.mark.asyncio
async def test_completed_media_socket_retains_recognition_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)

    async def complete_after_frame(*_args: object, **kwargs: object) -> object:
        kwargs["on_audio_frame"](  # type: ignore[operator]
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
        )
        result = SimpleNamespace(activated=True, accepted_frames=1)
        kwargs["on_complete"](result)  # type: ignore[operator]
        return result

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        complete_after_frame,
    )
    ws = _AuthOnlySocket(activation)

    assert await handle_registered_media_socket(registry, ws, endpoint_path)

    assert record.route_completed is True
    assert record.recognition_content_sha256 is not None


def test_production_gateway_completion_emits_content_free_l0_ack_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, object]] = []
    monkeypatch.setattr(
        dedicated_media_registration,
        "emit_runtime_l0_milestone",
        lambda **kwargs: emitted.append(kwargs) or True,
    )
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    record = _pending_record(registry, _media_ticket(activation))
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    registry.observe_uplink_ack_sent(
        record,
        MediaAck(record.binding.lease_id, record.binding.generation.value, 0),
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),
    )

    assert [item["milestone"] for item in emitted] == [
        L0Milestone.LAST_FRAME_ACKED,
        L0Milestone.UPLINK_CLOSED,
    ]
    assert emitted[0]["binding"].session_id == "session-1"
    assert emitted[0]["binding"].activation_generation == 1
    assert emitted[0]["duration_ms"] >= 0
    assert emitted[0]["observed_at"] == record.last_uplink_ack_observed_at
    assert emitted[0]["monotonic_ms"] == record.last_uplink_ack_monotonic_ms
    assert "samples" not in repr(emitted)
    assert "pcm" not in repr(emitted).lower()


def test_optional_l0_binding_never_rejects_wider_product_media_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, object]] = []
    monkeypatch.setattr(
        dedicated_media_registration,
        "emit_runtime_l0_milestone",
        lambda **kwargs: emitted.append(kwargs) or True,
    )
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(correlation_id="correlation with space"),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    record = _pending_record(registry, _media_ticket(activation))
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    registry.observe_uplink_ack_sent(
        record,
        MediaAck(record.binding.lease_id, record.binding.generation.value, 0),
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),
    )

    assert record.route_completed is True
    assert [item["binding"] for item in emitted] == [None, None]


def test_first_frame_diagnostics_hash_scope_and_record_accept_then_ack_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics: list[object] = []
    monkeypatch.setattr(
        dedicated_media_registration._MEDIA_FIRST_FRAME_DIAGNOSTIC_WORKER,
        "submit",
        lambda item: diagnostics.append(item) or True,
    )
    registry = DedicatedMediaProductRegistry(enabled=True, monotonic=lambda: 10.25)
    registry.set_provider_available(True)
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    record = _pending_record(registry, _media_ticket(activation))
    registry.accept_frame(
        record,
        MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
    )
    acknowledgement = MediaAck(
        record.binding.lease_id,
        record.binding.generation.value,
        0,
    )

    registry.observe_uplink_frame_accepted(record, acknowledgement, 10.25)
    registry.observe_uplink_ack_sent(record, acknowledgement)

    expected_scope = hashlib.sha256(
        "\x1f".join(
            (
                record.binding.session_id,
                record.binding.interaction_id,
                record.binding.correlation_id,
                record.binding.media_session_id,
                record.binding.track_id,
                record.binding.lease_id,
                record.binding.generation.kind.value,
                record.binding.generation.id,
                str(record.binding.generation.value),
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    assert len(diagnostics) == 2
    assert [item.stage for item in diagnostics] == [
        "gateway_frame_accepted",
        "gateway_ack_sent",
    ]
    assert all(item.scope_sha256 == expected_scope for item in diagnostics)
    assert all(
        item.capture_generation == 0 and item.frame_seq == 0
        for item in diagnostics
    )
    assert all(item.outcome == "success" for item in diagnostics)
    assert diagnostics[0].monotonic_ms == 10_250.0
    assert diagnostics[0].elapsed_ms == 0.0
    assert diagnostics[0].reason == "MEDIA_FRAME_ACCEPTED"
    assert diagnostics[1].reason == "MEDIA_ACK_SEND_SUCCEEDED"
    serialized = repr(diagnostics)
    assert "session-1" not in serialized
    assert "interaction-1" not in serialized
    assert "correlation-1" not in serialized
    assert record.binding.lease_id not in serialized

    successor_activation = _activate(
        registry,
        params=_params(capture_id="capture-2", track_id="track-2"),
        request_origin=ORIGIN,
        connection_id="connection-owner",
    )
    successor = _pending_record(registry, _media_ticket(successor_activation))
    assert (
        registry._first_frame_scope_sha256(successor)
        != registry._first_frame_scope_sha256(record)
    )


@pytest.mark.asyncio
async def test_media_socket_success_without_completion_callback_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)

    async def omit_completion(*_args: object, **kwargs: object) -> object:
        kwargs["on_audio_frame"](  # type: ignore[operator]
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
        )
        return SimpleNamespace(activated=True, accepted_frames=1)

    monkeypatch.setattr(
        dedicated_media_registration,
        "run_dedicated_media_socket_leaf",
        omit_completion,
    )
    ws = _AuthOnlySocket(activation)

    with pytest.raises(
        MediaTransportViolation, match="completion callback was not retained"
    ):
        await handle_registered_media_socket(registry, ws, endpoint_path)

    assert record.route_completed is True
    assert record.recognition_content_sha256 is None
    assert record.pcm == bytearray()


@pytest.mark.asyncio
async def test_uplink_registry_authority_is_visible_before_socket_close() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)
    frame = MediaAudioFrame(
        seq=0,
        sample_cursor=0,
        samples=(0.25,) * record.binding.frame_format.samples_per_channel,
    )
    peer_detach = MediaDetach(
        lease_id=record.binding.lease_id,
        generation=record.binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )
    close_observations: list[tuple[bool, bool]] = []
    receipt_observations: list[tuple[bool, bool]] = []

    class _OrderedSocket:
        subprotocol = "live-voice.media.v1"
        request_headers = {"Origin": ORIGIN}

        def __init__(self) -> None:
            self.incoming = [
                _media_auth_frame(activation),
                encode_audio_frame(record.binding, frame),
                serialize_media_control(peer_detach),
            ]
            self.sent: list[str | bytes] = []

        async def recv(self) -> str | bytes:
            return self.incoming.pop(0)

        async def send(self, message: str | bytes) -> None:
            self.sent.append(message)
            if isinstance(message, str) and isinstance(
                deserialize_media_control(message), MediaDetach
            ):
                receipt_observations.append(
                    (
                        record.route_completed,
                        record.recognition_content_sha256 is not None,
                    )
                )

        async def close(self, code: int = 1000, reason: str = "") -> None:
            assert code == 1000
            assert reason == "live-voice media leaf closed"
            close_observations.append(
                (
                    record.route_completed,
                    record.recognition_content_sha256 is not None,
                )
            )

    assert await handle_registered_media_socket(
        registry, _OrderedSocket(), endpoint_path
    )
    assert record.route_completed is True
    assert receipt_observations == [(True, True)]
    assert close_observations == [(True, True)]


@pytest.mark.asyncio
async def test_uplink_completion_is_not_aborted_when_close_wait_is_cancelled() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    endpoint_path = str(activation["endpoint_path"])
    ticket = _media_ticket(activation)
    record = _pending_record(registry, ticket)
    frame = MediaAudioFrame(
        seq=0,
        sample_cursor=0,
        samples=(0.25,) * record.binding.frame_format.samples_per_channel,
    )
    peer_detach = MediaDetach(
        lease_id=record.binding.lease_id,
        generation=record.binding.generation.value,
        reason_id=MediaDetachReason.PEER_CLOSE,
        through_seq=0,
    )
    close_started = asyncio.Event()

    class _BlockingCloseSocket:
        subprotocol = "live-voice.media.v1"
        request_headers = {"Origin": ORIGIN}

        def __init__(self) -> None:
            self.incoming = [
                _media_auth_frame(activation),
                encode_audio_frame(record.binding, frame),
                serialize_media_control(peer_detach),
            ]

        async def recv(self) -> str | bytes:
            return self.incoming.pop(0)

        async def send(self, _message: str | bytes) -> None:
            return None

        async def close(self, _code: int = 1000, _reason: str = "") -> None:
            close_started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(
        handle_registered_media_socket(registry, _BlockingCloseSocket(), endpoint_path)
    )
    await asyncio.wait_for(close_started.wait(), timeout=1)
    retained_hash = record.recognition_content_sha256
    assert record.route_completed is True
    assert retained_hash is not None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert record.route_completed is True
    assert record.recognition_content_sha256 == retained_hash


@pytest.mark.asyncio
async def test_media_handshake_rejects_wrong_origin_even_when_general_check_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())

    response = await channel._process_request(
        "/ws/live-voice/media",
        {"Origin": "https://attacker.example.test"},
    )

    assert response is not None
    assert int(response[0]) == 403


@pytest.mark.asyncio
async def test_media_handshake_rejects_missing_origin_even_when_general_check_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())

    response = await channel._process_request(
        "/ws/live-voice/media",
        {},
    )

    assert response is not None
    assert int(response[0]) == 403


@pytest.mark.asyncio
async def test_dispatcher_routes_only_the_fixed_media_path_to_the_media_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    channel.live_voice_media_registry = _active_registry()
    routed: list[str] = []
    closed: list[tuple[int, str]] = []

    async def fake_leaf(_registry: object, _ws: object, path: str) -> bool:
        routed.append(path)
        return True

    monkeypatch.setattr(
        dedicated_media_registration, "handle_registered_media_socket", fake_leaf
    )

    async def record_close(code: int = 1000, reason: str = "") -> None:
        closed.append((code, reason))

    request_path = "/ws/live-voice/media"
    socket = SimpleNamespace(close=record_close, path=request_path)

    assert (await channel._process_request(request_path, {"Origin": ORIGIN})) is None
    await channel._connection_handler(socket, request_path)

    assert routed == [request_path]
    assert closed == []


@pytest.mark.asyncio
async def test_ticket_like_media_path_is_not_route_authority_or_registry_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    registry = _active_registry()
    channel.live_voice_media_registry = registry
    routed: list[str] = []
    closed: list[tuple[int, str]] = []

    async def fake_leaf(_registry: object, _ws: object, path: str) -> bool:
        routed.append(path)
        return True

    monkeypatch.setattr(
        dedicated_media_registration, "handle_registered_media_socket", fake_leaf
    )

    async def record_close(code: int = 1000, reason: str = "") -> None:
        closed.append((code, reason))

    request_path = "/ws/live-voice/media/private-ticket"
    before = (len(registry._records), len(registry._pending_tickets))
    socket = SimpleNamespace(close=record_close, path=request_path)

    assert (await channel._process_request(request_path, {"Origin": ORIGIN})) is None
    await channel._connection_handler(socket, request_path)

    assert routed == []
    assert closed == [(1008, "unsupported path: /ws/live-voice/media/<redacted>")]
    assert "private-ticket" not in repr(closed)
    assert (len(registry._records), len(registry._pending_tickets)) == before


@pytest.mark.asyncio
async def test_media_handler_rejects_ticket_path_before_any_effect() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    before = (len(registry._records), len(registry._pending_tickets))

    class _PoisonSocket:
        @property
        def subprotocol(self) -> str:
            raise AssertionError("rejected path must not inspect the socket")

        async def recv(self) -> object:
            raise AssertionError("rejected path must not read credentials")

        async def close(self, _code: int = 1000, _reason: str = "") -> None:
            raise AssertionError("rejected path is not an accepted media socket")

    assert not await handle_registered_media_socket(
        registry,
        _PoisonSocket(),
        f"/ws/live-voice/media/{ticket}",
    )
    assert (len(registry._records), len(registry._pending_tickets)) == before
    assert registry.consume_ticket(ticket, request_origin=ORIGIN) is not None


@pytest.mark.asyncio
async def test_media_handshake_never_logs_the_authority_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ticket = "private-media-authority-ticket"
    logged: list[tuple[object, ...]] = []
    monkeypatch.setattr(web_connect.logger, "info", lambda *args: logged.append(args))

    assert (
        await channel._process_request(
            f"/ws/live-voice/media/{ticket}", {"Origin": ORIGIN}
        )
        is None
    )

    rendered = repr(logged)
    assert ticket not in rendered
    assert "/ws/live-voice/media/<redacted>" in rendered


def test_completed_route_authorizes_only_exact_independent_capture_and_no_disk(
    tmp_path: Path,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    registry.accept_frame(
        record,
        MediaAudioFrame(
            seq=0,
            sample_cursor=0,
            samples=tuple(0.25 if index % 2 else -0.25 for index in range(320)),
        ),
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),  # type: ignore[arg-type]
    )
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    assert before == after == []
    assert record.pcm == bytearray()
    scope = ScopeRef(
        subject_id=str(activation["subject_id"]),
        project_id=None,
        session_id="session-1",
        assurance=Assurance.AUTHENTICATED,
    )
    exact = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-1",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256=str(record.recognition_content_sha256),
    )
    assert registry.authorize(exact) == exact
    forged = replace(exact, content_sha256="0" * 64)
    assert registry.authorize(forged) is None


def test_agent_notification_authorizes_only_exact_agent_text_render_plan() -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    response = {
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
    }
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": response,
                "agent_event": {"event_type": "chat.final", "text": "正式 Agent 文本"},
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    ref = ResponseRef("interaction-1", "response-1", 0)
    expected = record.synthesis_content_sha256[(ref, "unit-1")]
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    exact = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id="synthesize-1",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=ref,
        unit_id="unit-1",
        content_sha256=expected,
    )
    assert registry.authorize(exact) == exact
    assert (
        registry.authorize(replace(exact, correlation_id="correlation-other")) is None
    )
    wrong = SpeechAuthorizationBinding(
        subject_id=exact.subject_id,
        scope=exact.scope,
        operation=exact.operation,
        operation_id=exact.operation_id,
        correlation_id=exact.correlation_id,
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=exact.response,
        unit_id=exact.unit_id,
        content_sha256="f" * 64,
    )
    assert registry.authorize(wrong) is None


def test_c2_audio_segment_notification_authorizes_its_exact_spoken_text() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    response = {
        "interaction_id": "interaction-1",
        "response_id": "response-c2-prefix",
        "response_generation": 0,
    }

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": response,
                "agent_event": {"event_type": "chat.delta", "text": "ignored"},
                "presentation_unit": {
                    "surface": "audio",
                    "unit_id": "unit-c2-prefix",
                    "seq": 0,
                    "projection_role": "audio_segment",
                },
                "presentation_text": "First stable sentence.",
                "presentation_delivery": "speak_only",
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    ref = ResponseRef("interaction-1", "response-c2-prefix", 0)
    expected = record.synthesis_content_sha256[(ref, "unit-c2-prefix")]
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    exact = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id="synthesize-c2-prefix",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=ref,
        unit_id="unit-c2-prefix",
        content_sha256=expected,
    )
    assert registry.authorize(exact) == exact


def test_c2_display_only_text_root_grants_zero_synthesis_authority() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    ref = ResponseRef("interaction-1", "response-c2-root", 0)

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": ref.interaction_id,
                    "response_id": ref.response_id,
                    "response_generation": ref.response_generation,
                },
                "agent_event": {"event_type": "chat.final", "text": "Complete final."},
                "presentation_unit": {
                    "surface": "text",
                    "unit_id": "unit-c2-root",
                    "projection_role": "authoritative_text_root",
                },
                "presentation_text": "Complete final.",
                "presentation_delivery": "display_only",
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert (ref, "unit-c2-root") not in record.synthesis_content_sha256


def _observe_task_notification(
    registry: DedicatedMediaProductRegistry,
    *,
    response_id: str = "response-task-progress-1",
    unit_id: str = "unit-1",
    text: str = "Task progress notification",
    response_generation: int = 0,
    surface: str = "text",
    source_provenance: str | None = None,
) -> ResponseRef:
    agent_event = {"event_type": "chat.final", "text": text}
    if source_provenance is not None:
        agent_event["source_provenance"] = source_provenance
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": response_id,
                    "response_generation": response_generation,
                },
                "agent_event": agent_event,
                "presentation_unit": {"surface": surface, "unit_id": unit_id},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    return ResponseRef("interaction-1", response_id, response_generation)


def _task_synthesis_request(
    *,
    subject_id: str,
    response: ResponseRef,
    unit_id: str = "unit-1",
    request_id: str = "request-task-progress",
    operation_id: str = "operation-task-progress",
    locale: str = "zh-CN",
    sample_rate_hz: int = 16_000,
    text: str = "Task progress notification",
    session_id: str = "session-1",
) -> dict[str, object]:
    return {
        "contract_version": "live-voice.contract.v2",
        "request_id": request_id,
        "operation_id": operation_id,
        "operation": SYNTHESIZE_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": session_id,
        "scope": {
            "subject_id": subject_id,
            "project_id": None,
            "session_id": session_id,
            "assurance": Assurance.AUTHENTICATED.value,
        },
        "timeout_ms": 1_000,
        "response": {
            "interaction_id": response.interaction_id,
            "response_id": response.response_id,
            "response_generation": response.response_generation,
        },
        "unit_id": unit_id,
        "render_plan": {
            "display_text": text,
            "spoken_text": text,
            "transforms": [],
        },
        "authoritative_agent_text": True,
        "locale": locale,
        "voice": None,
        "required_sample_rate_hz": sample_rate_hz,
    }


def test_task_notification_speech_authority_hands_off_to_rotated_media_owner() -> None:
    registry = _active_registry()
    initial = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    original = registry.consume_ticket(_media_ticket(initial), request_origin=ORIGIN)
    assert original is not None
    original.route_completed = True
    response = {
        "interaction_id": "interaction-1",
        "response_id": "response-task-progress-1",
        "response_generation": 0,
    }
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": response,
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "Task progress notification",
                    "source_provenance": "server.task_notification",
                },
                "presentation_unit": {"surface": "audio", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    ref = ResponseRef("interaction-1", "response-task-progress-1", 0)
    expected = original.synthesis_content_sha256[(ref, "unit-1")]

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": initial["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    successor = registry.activate(
        params=_params(capture_id="capture-2", track_id="track-2"),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    current = registry.consume_ticket(_media_ticket(successor), request_origin=ORIGIN)
    assert current is not None
    current.route_completed = True
    scope = ScopeRef(
        str(successor["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    binding = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=SYNTHESIZE_OPERATION,
        operation_id="synthesize-task-progress-after-rotation",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=ref,
        unit_id="unit-1",
        content_sha256=expected,
    )

    assert registry.authorize(binding) == binding


@pytest.mark.parametrize(
    "source_provenance", [None, "server.foreground_agent"]
)
def test_non_task_audio_notification_never_retains_speech_authority(
    source_provenance: str | None,
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True

    response = _observe_task_notification(
        registry,
        response_id="response-untrusted-audio",
        unit_id="unit-untrusted-audio",
        surface="audio",
        source_provenance=source_provenance,
    )

    assert (response, "unit-untrusted-audio") not in record.synthesis_content_sha256
    authority = registry._product_activations[
        ("session-1", "connection-1", "interaction-1")
    ]
    assert not any(
        key[0] == response and key[1] == "unit-untrusted-audio"
        for key in authority.synthesis_content_sha256
    )


@pytest.mark.asyncio
async def test_task_notification_speech_transfer_claims_one_successor_operation() -> (
    None
):
    registry = _active_registry()
    initial = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    original = registry.consume_ticket(_media_ticket(initial), request_origin=ORIGIN)
    assert original is not None
    original.route_completed = True
    response = _observe_task_notification(registry)
    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": initial["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    provider = _CountingBatchSpeechProvider()
    service = FormalBatchSpeechService(provider, authorization_resolver=registry)
    no_owner = _task_synthesis_request(
        subject_id=str(initial["subject_id"]), response=response
    )
    no_owner_result = await service.synthesize(
        no_owner,
        SpeechRpcContext(
            str(initial["subject_id"]), "session-1", Assurance.AUTHENTICATED
        ),
    )
    assert no_owner_result["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert provider.synthesize_calls == 0

    successor = registry.activate(
        params=_params(capture_id="capture-2", track_id="track-2"),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    current = registry.consume_ticket(_media_ticket(successor), request_origin=ORIGIN)
    assert current is not None
    current.route_completed = True
    request = _task_synthesis_request(
        subject_id=str(successor["subject_id"]), response=response
    )
    context = SpeechRpcContext(
        str(successor["subject_id"]), "session-1", Assurance.AUTHENTICATED
    )
    first = await service.synthesize(request, context)
    assert first["ok"] is True
    assert provider.synthesize_calls == 1
    retry = await service.synthesize(request, context)
    assert retry["ok"] is True
    assert provider.synthesize_calls == 1

    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": successor["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    later = registry.activate(
        params=_params(capture_id="capture-3", track_id="track-3"),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    later_record = registry.consume_ticket(_media_ticket(later), request_origin=ORIGIN)
    assert later_record is not None
    later_record.route_completed = True
    replay = await service.synthesize(
        _task_synthesis_request(
            subject_id=str(later["subject_id"]),
            response=response,
            request_id="request-later",
            operation_id="operation-later",
        ),
        SpeechRpcContext(
            str(later["subject_id"]), "session-1", Assurance.AUTHENTICATED
        ),
    )
    assert replay["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert provider.synthesize_calls == 1


@pytest.mark.asyncio
async def test_task_notification_reobservation_authorizes_late_media_owner() -> None:
    registry = _active_registry()
    params = _params()
    _trust_product_activation(registry, params)
    response = _observe_task_notification(registry)

    activation = registry.activate(
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    current = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert current is not None
    current.route_completed = True
    provider = _CountingBatchSpeechProvider()
    service = FormalBatchSpeechService(provider, authorization_resolver=registry)
    context = SpeechRpcContext(
        str(activation["subject_id"]), "session-1", Assurance.AUTHENTICATED
    )

    before_reobservation = await service.synthesize(
        _task_synthesis_request(
            subject_id=str(activation["subject_id"]),
            response=response,
            request_id="request-before-reobservation",
            operation_id="operation-before-reobservation",
        ),
        context,
    )
    assert before_reobservation["error"]["reason"] == "SPEECH_OPERATION_NOT_AUTHORIZED"
    assert provider.synthesize_calls == 0

    assert _observe_task_notification(registry) == response
    after_reobservation = await service.synthesize(
        _task_synthesis_request(
            subject_id=str(activation["subject_id"]),
            response=response,
            request_id="request-after-reobservation",
            operation_id="operation-after-reobservation",
        ),
        context,
    )
    assert after_reobservation["ok"] is True
    assert provider.synthesize_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "no_owner",
        "wrong_subject",
        "wrong_session",
        "wrong_connection",
        "activation_generation",
        "locale",
        "sample_rate",
        "stale_response",
        "stale_unit",
    ],
)
async def test_task_notification_speech_authority_failures_never_call_provider(
    failure: str,
) -> None:
    registry = _active_registry()
    initial = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    original = registry.consume_ticket(_media_ticket(initial), request_origin=ORIGIN)
    assert original is not None
    original.route_completed = True
    response = _observe_task_notification(registry)
    registry.revoke(
        params={
            "session_id": "session-1",
            "subject_id": initial["subject_id"],
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
    )
    subject_id = str(initial["subject_id"])
    locale = "zh-CN"
    sample_rate_hz = 16_000
    if failure != "no_owner":
        successor_params = _params(capture_id="capture-2", track_id="track-2")
        if failure == "locale":
            successor_params["locale"] = "en-US"
            locale = "en-US"
        if failure == "sample_rate":
            successor_params["sample_rate_hz"] = 48_000
            sample_rate_hz = 48_000
        successor = registry.activate(
            params=successor_params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
        successor_record = registry.consume_ticket(
            _media_ticket(successor), request_origin=ORIGIN
        )
        assert successor_record is not None
        successor_record.route_completed = True
        subject_id = str(successor["subject_id"])
    if failure == "wrong_subject":
        subject_id = "subject-foreign"
    request_response = (
        ResponseRef("interaction-1", "response-stale", 1)
        if failure == "stale_response"
        else response
    )
    unit_id = "unit-stale" if failure == "stale_unit" else "unit-1"
    session_id = "session-other" if failure == "wrong_session" else "session-1"
    request = _task_synthesis_request(
        subject_id=subject_id,
        response=request_response,
        unit_id=unit_id,
        request_id=f"request-{failure}",
        operation_id=f"operation-{failure}",
        locale=locale,
        sample_rate_hz=sample_rate_hz,
        session_id=session_id,
    )
    context = SpeechRpcContext(subject_id, session_id, Assurance.AUTHENTICATED)
    if failure == "wrong_connection":
        context = registry.context_for(
            SimpleNamespace(_jiuwen_ws_id="connection-other"),
            request,
            "session-1",
            "user-1",
        )
    if failure == "activation_generation":
        _trust_product_activation(
            registry,
            _params(activation_id="activation-2", activation_generation=2),
        )
    provider = _CountingBatchSpeechProvider()
    result = await FormalBatchSpeechService(
        provider, authorization_resolver=registry
    ).synthesize(request, context)
    assert result["ok"] is False
    assert provider.synthesize_calls == 0


def test_task_notification_transfer_ledger_has_deterministic_capacity_and_expiry() -> (
    None
):
    now = [0.0]
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now[0],
        authority_ttl_seconds=1.0,
    )
    registry.set_provider_available(True)
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    for index in range(17):
        _observe_task_notification(
            registry,
            response_id=f"response-capacity-{index}",
            unit_id=f"unit-capacity-{index}",
            text=f"Task progress {index}",
            response_generation=index,
        )
    authority = registry._product_activations[
        ("session-1", "connection-1", "interaction-1")
    ]
    assert len(authority.synthesis_content_sha256) == 16
    assert (
        ResponseRef("interaction-1", "response-capacity-0", 0),
        "unit-capacity-0",
        "zh-CN",
        16_000,
    ) not in authority.synthesis_content_sha256

    now[0] = 2.0
    assert (
        registry.authorize(
            SpeechAuthorizationBinding(
                subject_id=str(activation["subject_id"]),
                scope=ScopeRef(
                    str(activation["subject_id"]),
                    None,
                    "session-1",
                    Assurance.AUTHENTICATED,
                ),
                operation=SYNTHESIZE_OPERATION,
                operation_id="operation-expired",
                correlation_id="correlation-1",
                capture_id=None,
                capture_generation=None,
                track_id=None,
                response=ResponseRef("interaction-1", "response-capacity-16", 16),
                unit_id="unit-capacity-16",
                content_sha256="0" * 64,
            )
        )
        is None
    )
    assert registry._product_activations == {}
    assert authority.synthesis_content_sha256 == {}


def test_task_notification_transfer_expiry_is_not_renewed_by_later_notifications() -> (
    None
):
    now = [0.0]
    registry = DedicatedMediaProductRegistry(
        enabled=True,
        monotonic=lambda: now[0],
        authority_ttl_seconds=1.0,
    )
    registry.set_provider_available(True)
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    first_response = _observe_task_notification(registry, response_id="response-first")
    digest = record.synthesis_content_sha256[(first_response, "unit-1")]
    now[0] = 0.5
    _observe_task_notification(registry, response_id="response-later")
    now[0] = 1.1
    binding = SpeechAuthorizationBinding(
        subject_id=str(activation["subject_id"]),
        scope=ScopeRef(
            str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
        ),
        operation=SYNTHESIZE_OPERATION,
        operation_id="operation-expired-transfer",
        correlation_id="correlation-1",
        capture_id=None,
        capture_generation=None,
        track_id=None,
        response=first_response,
        unit_id="unit-1",
        content_sha256=digest,
    )
    assert registry.authorize(binding) is None
    authority = registry._product_activations[
        ("session-1", "connection-1", "interaction-1")
    ]
    assert (
        first_response,
        "unit-1",
        "zh-CN",
        16_000,
    ) not in authority.synthesis_content_sha256


def test_mismatched_notification_batch_has_zero_partial_speech_authority() -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    valid_final = {
        "status": "notification",
        "kind": "agent.output",
        "request_id": "request-valid",
        "round_id": "round-valid",
        **binding,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-valid",
            "response_generation": 0,
        },
        "agent_event": {"event_type": "chat.final", "text": "valid first item"},
        "source_event": None,
        "progress_event": None,
        "presentation_unit": {"surface": "text", "unit_id": "unit-valid"},
        "error_reason": None,
        "publish_seq": 0,
    }
    mismatched_final = {
        **valid_final,
        "activation_generation": 2,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-mismatched",
            "response_generation": 1,
        },
        "agent_event": {
            "event_type": "chat.final",
            "text": "mismatched second item",
        },
        "presentation_unit": {
            "surface": "text",
            "unit_id": "unit-mismatched",
        },
        "publish_seq": 1,
    }

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification_batch",
                "notifications": [valid_final, mismatched_final],
                **binding,
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert record.synthesis_content_sha256 == {}


def test_c2_batch_retains_audio_segment_speech_authority() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    record = registry.consume_ticket(_media_ticket(activation), request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    prefix = {
        "status": "notification",
        "kind": "agent.output",
        "request_id": "request-c2-prefix",
        "round_id": "round-c2-prefix",
        **binding,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-c2-prefix-batch",
            "response_generation": 0,
        },
        "agent_event": {"event_type": "chat.delta", "text": "ignored"},
        "source_event": None,
        "progress_event": None,
        "presentation_unit": {
            "surface": "audio",
            "unit_id": "unit-c2-prefix-batch",
            "seq": 0,
            "projection_role": "audio_segment",
        },
        "presentation_text": "First stable sentence.",
        "presentation_delivery": "speak_only",
        "error_reason": None,
        "publish_seq": 0,
    }

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification_batch",
                "notifications": [prefix],
                **binding,
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    ref = ResponseRef("interaction-1", "response-c2-prefix-batch", 0)
    assert (ref, "unit-c2-prefix-batch") in record.synthesis_content_sha256


def test_same_binding_final_before_invalid_batch_tail_has_zero_speech_authority() -> (
    None
):
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    binding = {
        "session_id": "session-1",
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "activation_id": "activation-1",
        "activation_generation": 1,
    }
    valid_final = {
        "status": "notification",
        "kind": "agent.output",
        "request_id": "request-valid",
        "round_id": "round-valid",
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-valid",
            "response_generation": 0,
        },
        "agent_event": {"event_type": "chat.final", "text": "valid first item"},
        "source_event": None,
        "progress_event": None,
        "presentation_unit": {"surface": "text", "unit_id": "unit-valid"},
        "error_reason": None,
        "publish_seq": 0,
        **binding,
    }
    invalid_tail = {
        "status": "notification",
        "kind": "transport.keepalive",
        "request_id": "request-invalid-tail",
        "round_id": None,
        "response": None,
        "agent_event": None,
        "source_event": None,
        "progress_event": None,
        "presentation_unit": None,
        "error_reason": None,
        "publish_seq": 1,
        **binding,
    }

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification_batch",
                "notifications": [valid_final, invalid_tail],
                **binding,
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert record.synthesis_content_sha256 == {}


def test_playout_receipt_requires_exact_authenticated_media_and_synthesis_flow() -> (
    None
):
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True
    record.accepted_frames = 3
    ref = ResponseRef("interaction-1", "response-1", 0)
    record.synthesis_content_sha256[(ref, "unit-1")] = "a" * 64
    params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
        "unit_id": "unit-1",
        "capture_frames_acked": 3,
        "rendered_chunks": 300,
        "rendered_through_seq": 299,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 256,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }

    with pytest.raises(MediaTransportViolation) as missing:
        registry.acknowledge_playout(
            params=params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert missing.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    record.downlink_results[(ref, "unit-1")] = {
        "complete": False,
        "sent_frames": 300,
        "acknowledged_through_seq": 299,
        "overlap_observed": True,
        "content_sha256": "a" * 64,
    }
    with pytest.raises(MediaTransportViolation) as incomplete:
        registry.acknowledge_playout(
            params=params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
    assert incomplete.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
    record.downlink_results[(ref, "unit-1")] = {
        "complete": True,
        "sent_frames": 300,
        "acknowledged_through_seq": 299,
        "overlap_observed": True,
        "content_sha256": "a" * 64,
    }

    accepted = registry.acknowledge_playout(
        params=params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert accepted["status"] == "media_playout_acknowledged"
    assert accepted["receipt_id"].startswith("media-playout-")
    assert (
        registry.acknowledge_playout(
            params=params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
        == accepted
    )
    for updates in (
        {"capture_frames_acked": 2},
        {"response_id": "response-forged"},
        {"rendered_chunks": 299, "rendered_through_seq": 298},
        {"playout_peak_depth": 257},
    ):
        with pytest.raises(MediaTransportViolation):
            registry.acknowledge_playout(
                params={**params, **updates},
                routed_session_id="session-1",
                connection_id="connection-1",
                user_id="user-1",
                request_origin=ORIGIN,
            )
    assert tuple(record.playout_receipts) == ((ref, "unit-1"),)


@pytest.mark.parametrize(
    ("successor_frame_timing", "expected_duplex"),
    (
        ("none", False),
        ("before_downlink_complete", True),
        ("after_downlink_complete", False),
    ),
)
def test_synthesis_downlink_receipt_reports_early_duplex_without_rejecting_playout(
    successor_frame_timing: str, expected_duplex: bool
) -> None:
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    parent_ticket = _media_ticket(activation)
    parent = registry.consume_ticket(parent_ticket, request_origin=ORIGIN)
    assert parent is not None
    parent.route_completed = True
    parent.accepted_frames = 3
    ref = ResponseRef("interaction-1", "response-1", 0)
    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "formal Agent text",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )
    expected_content = parent.synthesis_content_sha256[(ref, "unit-1")]
    speech_params = {
        "contract_version": "live-voice.contract.v2",
        "request_id": "request-1",
        "operation_id": "operation-1",
        "operation": SYNTHESIZE_OPERATION,
        "correlation_id": "correlation-1",
        "session_id": "session-1",
        "scope": {
            "subject_id": activation["subject_id"],
            "project_id": None,
            "session_id": "session-1",
            "assurance": "authenticated",
        },
        "timeout_ms": 2_000,
        "response": {
            "interaction_id": "interaction-1",
            "response_id": "response-1",
            "response_generation": 0,
        },
        "unit_id": "unit-1",
        "render_plan": {
            "display_text": "formal Agent text",
            "spoken_text": "formal Agent text",
            "transforms": [],
        },
        "authoritative_agent_text": True,
        "locale": "zh-CN",
        "voice": None,
        "required_sample_rate_hz": 16_000,
    }
    speech_result = {
        "ok": True,
        "result": {
            "operation": SYNTHESIZE_OPERATION,
            "response": speech_params["response"],
            "unit_id": "unit-1",
            "audio": {
                "format": "wav_pcm16_mono",
                "sample_rate_hz": 16_000,
                "channel_count": 1,
                "data_base64": base64.b64encode(
                    dedicated_media_registration._wav_bytes(b"\x00\x00" * 320, 16_000)
                ).decode("ascii"),
            },
            "provider": {"provider_id": "provider-1"},
            "presented": False,
        },
    }
    transformed = registry.prepare_synthesis_downlink(
        SYNTHESIZE_OPERATION,
        speech_params,
        SpeechRpcContext(
            str(activation["subject_id"]), "session-1", Assurance.AUTHENTICATED
        ),
        speech_result,
        "session-1",
    )
    audio = transformed["result"]["audio"]  # type: ignore[index]
    assert isinstance(audio, dict)
    assert audio["delivery"] == "dedicated_media_downlink"
    assert "data_base64" not in audio
    assert audio["frame_count"] == 1
    downlink_ticket = _media_ticket(audio)
    downlink = registry.consume_ticket(downlink_ticket, request_origin=ORIGIN)
    assert downlink is not None
    assert downlink.downlink_content_sha256 == expected_content

    next_activation = registry.activate(
        params=_params(
            capture_id="capture-2",
            capture_generation=1,
            track_id="track-2",
        ),
        request_origin=ORIGIN,
        connection_id="connection-1",
        user_id="user-1",
    )
    next_ticket = _media_ticket(next_activation)
    next_uplink = registry.consume_ticket(next_ticket, request_origin=ORIGIN)
    assert next_uplink is not None
    assert parent.barge_in_capture is False
    assert next_uplink.barge_in_capture is True
    registry.mark_downlink_started(downlink)
    assert downlink.downlink_overlap_record_id == next_uplink.record_id
    assert downlink.downlink_overlap_observed is False
    if successor_frame_timing == "before_downlink_complete":
        registry.accept_frame(
            next_uplink,
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
        )
    assert registry.complete_downlink(
        downlink,
        DedicatedMediaSocketLeafResult(
            activated=True,
            socket_touched=True,
            attach_sent=True,
            accepted_frames=0,
            close_result=None,
            reason_id=MediaDetachReason.LOCAL_CLOSE,
            sent_frames=1,
            acknowledged_through_seq=0,
            configured_max_pending_frames=8,
            configured_max_pending_bytes=131_072,
            peak_pending_frames=1,
            peak_pending_bytes=1_320,
        ),
    )
    if successor_frame_timing == "after_downlink_complete":
        registry.accept_frame(
            next_uplink,
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
        )
    assert downlink.downlink_overlap_observed is expected_duplex
    receipt_params = {
        "session_id": "session-1",
        "subject_id": activation["subject_id"],
        "correlation_id": "correlation-1",
        "interaction_id": "interaction-1",
        "response_id": "response-1",
        "response_generation": 0,
        "unit_id": "unit-1",
        "capture_frames_acked": 3,
        "rendered_chunks": 1,
        "rendered_through_seq": 0,
        "playout_queue_capacity": 256,
        "playout_peak_depth": 1,
        "capture_control_ack": "capture_flush_acked",
        "playout_state": "render_completed",
    }
    receipt = registry.acknowledge_playout(
        params=receipt_params,
        routed_session_id="session-1",
        connection_id="connection-1",
        user_id="user-1",
        request_origin=ORIGIN,
    )
    assert receipt["duplex_media_observed"] is expected_duplex
    assert tuple(parent.playout_receipts) == ((ref, "unit-1"),)
    assert next_uplink.route_completed is False


def test_agent_notification_from_another_p2_activation_has_zero_speech_authority() -> (
    None
):
    registry = _active_registry()
    activation = _activate(
        registry, params=_params(), request_origin=ORIGIN, connection_id="connection-1"
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.route_completed = True

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "notification",
                "kind": "agent.output",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "activation_id": "activation-forged",
                "activation_generation": 1,
                "response": {
                    "interaction_id": "interaction-1",
                    "response_id": "response-1",
                    "response_generation": 0,
                },
                "agent_event": {
                    "event_type": "chat.final",
                    "text": "cross-activation text",
                },
                "presentation_unit": {"surface": "text", "unit_id": "unit-1"},
            },
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert record.synthesis_content_sha256 == {}


@pytest.mark.parametrize(
    ("request_method", "manifest", "connection_id"),
    [
        ("agent.chat", True, "connection-1"),
        ("live_voice.composition.p2.activate", False, "connection-1"),
        ("live_voice.composition.p2.activate", True, None),
    ],
)
def test_generic_shape_or_disconnected_response_cannot_mint_media_authority(
    request_method: str, manifest: bool, connection_id: str | None
) -> None:
    registry = _active_registry()
    params = _params()
    payload: dict[str, object] = {
        "ok": True,
        "result": {
            "status": "active",
            "session_id": "session-1",
            "correlation_id": "correlation-1",
            "interaction_id": "interaction-1",
            "activation_id": "activation-1",
            "activation_generation": 1,
        },
    }
    if manifest:
        payload["product_composition"] = _formal_p2_manifest()
    registry.observe_agent_response(
        payload,
        routed_session_id="session-1",
        user_id="user-1",
        connection_id=connection_id,
        request_method=request_method,
    )

    with pytest.raises(MediaTransportViolation) as rejected:
        registry.activate(
            params=params,
            request_origin=ORIGIN,
            connection_id="connection-1",
            user_id="user-1",
        )
    assert rejected.value.reason_id == "MEDIA_PRODUCT_ACTIVATION_UNTRUSTED"
    assert registry._records == {}


def test_p2_close_revokes_media_and_leaves_zero_speech_provider_effect() -> None:
    registry = _active_registry()
    params = _params()
    activation = _activate(
        registry,
        params=params,
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    registry.accept_frame(
        record, MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320)
    )
    registry.complete_route(
        record,
        SimpleNamespace(activated=True, accepted_frames=1),  # type: ignore[arg-type]
    )
    record.synthesis_content_sha256[
        (ResponseRef("interaction-1", "response-1", 0), "unit-1")
    ] = "b" * 64
    prior_digest = str(record.recognition_content_sha256)
    scope = ScopeRef(
        str(activation["subject_id"]), None, "session-1", Assurance.AUTHENTICATED
    )
    recognize = SpeechAuthorizationBinding(
        subject_id=scope.subject_id,
        scope=scope,
        operation=RECOGNIZE_OPERATION,
        operation_id="recognize-after-close",
        correlation_id="correlation-1",
        capture_id="capture-1",
        capture_generation=0,
        track_id="track-1",
        response=None,
        unit_id=None,
        content_sha256=prior_digest,
    )

    registry.observe_agent_response(
        {
            "ok": True,
            "result": {
                "status": "closed",
                "session_id": "session-1",
                "correlation_id": "correlation-1",
                "interaction_id": "interaction-1",
                "activation_id": "activation-1",
                "activation_generation": 1,
            },
            "product_composition": _formal_p2_manifest(),
        },
        routed_session_id="session-1",
        user_id="user-1",
        connection_id="connection-1",
        request_method="live_voice.composition.p2.close",
    )

    assert registry._records == {}
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is None
    assert record.synthesis_content_sha256 == {}
    assert registry.authorize(recognize) is None


def test_replacing_p2_activation_revokes_old_media_before_new_provider_use() -> None:
    registry = _active_registry()
    activation = _activate(
        registry,
        params=_params(),
        request_origin=ORIGIN,
        connection_id="connection-1",
    )
    ticket = _media_ticket(activation)
    record = registry.consume_ticket(ticket, request_origin=ORIGIN)
    assert record is not None
    record.pcm.extend(b"private-pcm")
    record.recognition_content_sha256 = "a" * 64
    record.synthesis_content_sha256[
        (ResponseRef("interaction-1", "response-1", 0), "unit-1")
    ] = "b" * 64

    replacement = _params(activation_id="activation-2", activation_generation=2)
    _trust_product_activation(registry, replacement)

    assert registry._records == {}
    assert record.pcm == bytearray()
    assert record.recognition_content_sha256 is None
    assert record.synthesis_content_sha256 == {}
