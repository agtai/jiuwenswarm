"""Exercise media handshakes through the production ASGI router and adapter."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from jiuwenswarm.gateway.channel_manager.base import RobotMessageRouter
from jiuwenswarm.gateway.channel_manager.web.web_channel_app import build_web_channel_app
from jiuwenswarm.gateway.channel_manager.web.web_connect import WebChannel, WebChannelConfig


MEDIA_PATH = "/ws/live-voice/media"
PROTOCOL = "live-voice.media.v1"


async def exchange(channel, *, origin="http://127.0.0.1:5173", protocols=(PROTOCOL,), frames=()):
    headers = [] if origin is None else [(b"origin", origin.encode())]
    scope = {
        "type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws",
        "path": MEDIA_PATH, "raw_path": MEDIA_PATH.encode(), "query_string": b"",
        "headers": headers, "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 19000),
        "subprotocols": list(protocols), "extensions": {"websocket.http.response": {}},
    }
    inbound = iter([{"type": "websocket.connect"}, *frames,
                    {"type": "websocket.disconnect", "code": 1000}])
    outbound = []

    async def receive():
        return next(inbound)

    async def send(message):
        outbound.append(message)

    await asyncio.wait_for(build_web_channel_app(channel)(scope, receive, send), timeout=3)
    return outbound


@pytest.fixture
def channel(monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "0")
    monkeypatch.setenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS", "127.0.0.1,none")
    return WebChannel(WebChannelConfig(enabled=True, dual_protocol=True), RobotMessageRouter())


@pytest.mark.asyncio
async def test_media_asgi_negotiates_protocol_and_preserves_binary_frames(channel):
    observed = []

    async def handle(ws, path):
        observed.append((path, ws.subprotocol, ws.request_headers["origin"]))
        assert await ws.recv() == "authentication frame"
        assert await ws.recv() == b"\x00\x80\xff"
        await ws.send(b"\x01\x00")
        await ws.close()

    channel.handle_connection = handle
    messages = await exchange(channel, frames=[
        {"type": "websocket.receive", "text": "authentication frame"},
        {"type": "websocket.receive", "bytes": b"\x00\x80\xff"},
    ])
    assert observed == [(MEDIA_PATH, PROTOCOL, "http://127.0.0.1:5173")]
    assert messages[0] == {"type": "websocket.accept", "subprotocol": PROTOCOL, "headers": []}
    assert {"type": "websocket.send", "bytes": b"\x01\x00"} in messages


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [None, "https://evil.example"])
async def test_media_asgi_requires_allowed_origin_even_when_general_check_disabled(channel, origin):
    channel.handle_connection = AsyncMock()
    messages = await exchange(channel, origin=origin)
    channel.handle_connection.assert_not_awaited()
    assert not any(m["type"] == "websocket.accept" for m in messages)
    assert any(m.get("status") == 403 or m["type"] == "websocket.close" for m in messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("protocols", [(), ("wrong.protocol",)])
async def test_media_asgi_rejects_missing_protocol_without_dispatch(channel, protocols):
    channel.handle_connection = AsyncMock()
    messages = await exchange(channel, protocols=protocols)
    channel.handle_connection.assert_not_awaited()
    assert not any(m["type"] == "websocket.accept" for m in messages)


@pytest.mark.asyncio
async def test_media_asgi_reaches_real_authenticator_and_rejects_invalid_frame(channel):
    registry = MagicMock()
    channel.live_voice_media_registry = registry
    messages = await exchange(channel, frames=[{"type": "websocket.receive", "text": "{}"}])
    assert messages[0]["type"] == "websocket.accept"
    assert messages[-1]["type"] == "websocket.close"
    assert messages[-1]["code"] == 1008
    registry.consume_ticket.assert_not_called()
    registry.mark_downlink_started.assert_not_called()


@pytest.mark.asyncio
async def test_media_asgi_unavailable_registry_fails_closed(channel):
    messages = await exchange(channel)
    assert messages[0]["type"] == "websocket.accept"
    assert messages[-1]["code"] == 1008
    assert messages[-1]["reason"] == "live-voice media route unavailable"


def test_media_path_cannot_be_replaced_by_main_route(channel):
    channel.config.path = MEDIA_PATH
    with pytest.raises(ValueError, match="conflicts"):
        build_web_channel_app(channel)


def test_media_path_cannot_be_replaced_by_plugin(channel):
    from jiuwenswarm.extensions.sdk import WebSocketRouteContribution

    plugin = SimpleNamespace(
        plugin_id="test-plugin", metadata=SimpleNamespace(id="test-plugin"),
        is_enabled=lambda: True,
        websocket_routes=lambda: (WebSocketRouteContribution(path=MEDIA_PATH, endpoint=AsyncMock()),),
    )
    channel.application_plugin_registry = SimpleNamespace(get_application_plugins=lambda: (plugin,))
    with pytest.raises(ValueError, match="conflicts"):
        build_web_channel_app(channel)
