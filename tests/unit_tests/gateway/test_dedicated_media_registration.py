# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import replace
import base64
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
)
from jiuwenswarm.gateway.live_voice.browser_gateway_media_transport import (
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
    RECOGNIZE_OPERATION,
    SYNTHESIZE_OPERATION,
    SpeechAuthorizationBinding,
    SpeechRpcContext,
)


ORIGIN = "https://voice.example.test"


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
        "/ws/live-voice/media/private-ticket",
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
        "/ws/live-voice/media/private-ticket",
        {},
    )

    assert response is not None
    assert int(response[0]) == 403


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
    ("accept_real_frame", "expected_duplex"),
    ((False, False), (True, True)),
)
def test_synthesis_downlink_requires_real_overlapping_uplink_before_duplex_receipt(
    accept_real_frame: bool, expected_duplex: bool
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
    registry.mark_downlink_started(downlink)
    assert downlink.downlink_overlap_record_id == next_uplink.record_id
    assert downlink.downlink_overlap_observed is False
    if accept_real_frame:
        registry.accept_frame(
            next_uplink,
            MediaAudioFrame(seq=0, sample_cursor=0, samples=(0.25,) * 320),
        )
    assert (
        registry.complete_downlink(
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
        is expected_duplex
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
    if expected_duplex:
        receipt = registry.acknowledge_playout(
            params=receipt_params,
            routed_session_id="session-1",
            connection_id="connection-1",
            user_id="user-1",
            request_origin=ORIGIN,
        )
        assert receipt["duplex_media_observed"] is True
    else:
        with pytest.raises(MediaTransportViolation) as caught:
            registry.acknowledge_playout(
                params=receipt_params,
                routed_session_id="session-1",
                connection_id="connection-1",
                user_id="user-1",
                request_origin=ORIGIN,
            )
        assert caught.value.reason_id == "MEDIA_PLAYOUT_RECEIPT_UNTRUSTED"
        assert parent.playout_receipts == {}
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
