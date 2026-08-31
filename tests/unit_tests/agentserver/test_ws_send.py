import ast
import asyncio
import json
import logging
import traceback
from pathlib import Path

import pytest

from jiuwenswarm.common.e2a.constants import E2A_WIRE_SERVER_PUSH_KEY
from jiuwenswarm.common.e2a.wire_codec import (
    encode_agent_chunk_for_wire,
    encode_agent_response_for_wire,
    parse_agent_server_wire_chunk,
)
from jiuwenswarm.common.schema.agent import (
    AgentRequest,
    AgentResponse,
    AgentResponseChunk,
)
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server import agent_ws_server
from jiuwenswarm.server import ws_send
from jiuwenswarm.server.gateway_push.wire import build_server_push_wire


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_send_wire_payload_sends_small_wire_unchanged(monkeypatch):
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 1024)
    ws = FakeWebSocket()
    wire = {"request_id": "r1", "body": {"result": "ok"}}

    assert await ws_send.send_wire_payload(ws, wire) is True
    assert json.loads(ws.sent[0]) == wire


@pytest.mark.asyncio
async def test_send_wire_payload_counts_utf8_bytes(monkeypatch):
    wire = {"request_id": "r1", "body": {"result": "你" * 400}}
    character_size = len(json.dumps(wire, ensure_ascii=False))
    byte_size = len(json.dumps(wire, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 1200)
    ws = FakeWebSocket()

    assert character_size < 1200 < byte_size
    assert await ws_send.send_wire_payload(ws, wire) is False
    assert len(ws.sent[0].encode("utf-8")) <= 1200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "private_location", ("request_id", "nested_key", "nested_value")
)
async def test_send_wire_payload_rejects_lone_surrogate_with_static_error(
    private_location,
    caplog,
):
    marker = f"sentinel-direct-ws-surrogate-{private_location}"
    private_text = f"{marker}\udfff-private"
    wire = {"request_id": "safe-request", "body": {"result": "ordinary"}}
    if private_location == "request_id":
        wire["request_id"] = private_text
    elif private_location == "nested_key":
        wire["body"] = {private_text: "ordinary"}
    else:
        wire["body"] = {"private": private_text}

    send_logger = logging.getLogger("jiuwenswarm.server.ws_send")
    consumer_logger = logging.getLogger("tests.direct_ws_surrogate_consumer")
    for target_logger in (send_logger, consumer_logger):
        target_logger.addHandler(caplog.handler)
        caplog.set_level(logging.DEBUG, logger=target_logger.name)
    ws = FakeWebSocket()
    try:
        with pytest.raises(ValueError) as raised:
            await ws_send.send_wire_payload(ws, wire)
        formatted = "".join(traceback.format_exception(raised.value))
        try:
            raise raised.value
        except ValueError:
            consumer_logger.exception("direct ws send rejected")
    finally:
        for target_logger in (send_logger, consumer_logger):
            target_logger.removeHandler(caplog.handler)

    assert raised.value.args == ("invalid AgentServer wire payload",)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert ws.sent == []
    diagnostics = f"{formatted}\n{caplog.text}"
    assert marker not in diagnostics


@pytest.mark.asyncio
async def test_oversized_unary_sends_e2a_error(monkeypatch):
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 2048)
    source = encode_agent_response_for_wire(
        AgentResponse(
            request_id="r-unary",
            channel_id="web",
            ok=True,
            payload={"content": "x" * 4096},
            agent_ref={"mode": "code", "id": "default"},
        ),
        response_id="r-unary",
    )
    source["session_id"] = "session-1"
    ws = FakeWebSocket()

    assert await ws_send.send_wire_payload(ws, source) is False

    fallback = json.loads(ws.sent[0])
    assert fallback["response_kind"] == "e2a.error"
    assert fallback["request_id"] == "r-unary"
    assert fallback["session_id"] == "session-1"
    assert fallback["agent_ref"] == {"mode": "code", "id": "default"}
    assert fallback["body"]["details"]["code"] == "response_too_large"
    assert fallback["body"]["details"]["actual_bytes"] > 2048
    assert fallback["body"]["details"]["max_bytes"] == 2048
    assert len(ws.sent[0].encode("utf-8")) <= 2048


@pytest.mark.asyncio
async def test_oversized_stream_sends_final_error_chunk(monkeypatch):
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 2048)
    source = encode_agent_chunk_for_wire(
        AgentResponseChunk(
            request_id="r-stream",
            channel_id="web",
            payload={"event_type": "chat.tool_result", "result": "x" * 4096},
            is_complete=False,
            agent_ref={"mode": "team", "id": "team-1"},
        ),
        response_id="r-stream",
        sequence=7,
    )
    ws = FakeWebSocket()

    assert await ws_send.send_wire_payload(ws, source) is False

    raw_fallback = json.loads(ws.sent[0])
    fallback = parse_agent_server_wire_chunk(raw_fallback)
    assert raw_fallback["sequence"] == 7
    assert raw_fallback["agent_ref"] == {"mode": "team", "id": "team-1"}
    assert fallback.is_complete is True
    assert fallback.payload["event_type"] == "chat.error"
    assert fallback.payload["code"] == "response_too_large"
    assert len(ws.sent[0].encode("utf-8")) <= 2048


@pytest.mark.asyncio
async def test_oversized_server_push_preserves_push_marker(monkeypatch):
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 2048)
    source = build_server_push_wire(
        {
            "request_id": "push-1",
            "channel_id": "web",
            "session_id": "session-push",
            "payload": {"result": "x" * 4096},
        }
    )
    ws = FakeWebSocket()

    assert await ws_send.send_wire_payload(ws, source) is False

    fallback = json.loads(ws.sent[0])
    assert fallback["metadata"][E2A_WIRE_SERVER_PUSH_KEY] is True
    assert fallback["session_id"] == "session-push"
    assert len(ws.sent[0].encode("utf-8")) <= 2048


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ("unary", "chunk"))
async def test_oversized_real_wire_logs_only_content_free_bounds(
    form,
    caplog,
    monkeypatch,
):
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 2048)
    private_request = f"sentinel-oversized-{form}-request"
    private_channel = f"sentinel-oversized-{form}-channel"
    private_response = f"sentinel-oversized-{form}-response"
    private_payload = f"sentinel-oversized-{form}-payload"
    if form == "unary":
        source = encode_agent_response_for_wire(
            AgentResponse(
                request_id=private_request,
                channel_id=private_channel,
                payload={"secret": private_payload + "x" * 4096},
            ),
            response_id=private_response,
        )
    else:
        source = encode_agent_chunk_for_wire(
            AgentResponseChunk(
                request_id=private_request,
                channel_id=private_channel,
                payload={"secret": private_payload + "x" * 4096},
            ),
            response_id=private_response,
            sequence=43,
        )

    target_logger = logging.getLogger("jiuwenswarm.server.ws_send")
    target_logger.addHandler(caplog.handler)
    caplog.set_level(logging.ERROR, logger=target_logger.name)
    ws = FakeWebSocket()
    try:
        assert await ws_send.send_wire_payload(ws, source) is False
    finally:
        target_logger.removeHandler(caplog.handler)

    assert len(ws.sent) == 1
    sent = json.loads(ws.sent[0])
    assert sent["response_kind"] == "e2a.error"
    assert sent["request_id"] == private_request
    assert sent["response_id"] == private_response
    assert sent["channel"] == private_channel
    assert sent["body"]["details"]["code"] == "response_too_large"
    assert "stage=oversized" in caplog.text
    assert "actual_bytes=" in caplog.text
    assert "max_bytes=2048" in caplog.text
    assert "field_count=" in caplog.text
    diagnostics = caplog.text
    forbidden = (
        private_request,
        private_channel,
        private_response,
        private_payload,
        "request_id=",
        "session_id=",
        "channel=",
        "response_kind=",
        "preview=",
    )
    assert not [marker for marker in forbidden if marker in diagnostics]
    assert not [record for record in caplog.records if record.exc_info is not None]


@pytest.mark.asyncio
async def test_oversized_fallback_sanitizes_hostile_scalar_subclasses_without_hooks(
    caplog,
    monkeypatch,
):
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 2048)
    hooks: list[str] = []

    class HostileStr(str):
        def __str__(self):
            hooks.append("__str__")
            raise AssertionError("sentinel-ws-hostile-str")

        def __repr__(self):
            hooks.append("__repr__")
            raise AssertionError("sentinel-ws-hostile-repr")

        def __getattribute__(self, name):
            if name == "__class__":
                hooks.append("__class__")
                raise AssertionError("sentinel-ws-hostile-class")
            return str.__getattribute__(self, name)

    source = encode_agent_response_for_wire(
        AgentResponse(
            request_id="ordinary-request",
            channel_id="ordinary-channel",
            payload={"content": "x" * 4096},
        ),
        response_id="ordinary-response",
    )
    source["request_id"] = HostileStr("sentinel-ws-request-value")
    source["response_id"] = HostileStr("sentinel-ws-response-value")
    source["channel"] = HostileStr("sentinel-ws-channel-value")
    target_logger = logging.getLogger("jiuwenswarm.server.ws_send")
    target_logger.addHandler(caplog.handler)
    caplog.set_level(logging.ERROR, logger=target_logger.name)
    ws = FakeWebSocket()
    try:
        assert await ws_send.send_wire_payload(ws, source) is False
    finally:
        target_logger.removeHandler(caplog.handler)

    assert hooks == []
    fallback = json.loads(ws.sent[0])
    assert fallback["request_id"] == ""
    assert fallback["response_id"] == ""
    assert fallback["channel"] is None
    diagnostics = f"{caplog.text}\n{ws.sent[0]}"
    assert "sentinel-ws" not in diagnostics


@pytest.mark.asyncio
async def test_agentserver_send_push_returns_observable_delivery_fact(monkeypatch):
    server = agent_ws_server.AgentWebSocketServer.__new__(
        agent_ws_server.AgentWebSocketServer
    )
    server._current_ws = FakeWebSocket()
    server._current_send_lock = asyncio.Lock()
    message = {
        "request_id": "push-delivery",
        "channel_id": "web",
        "session_id": "session-1",
        "payload": {"event_type": "live_voice.task.progress"},
    }

    assert await server.send_push(message) is True

    async def replace_with_oversized_error(_ws, _wire):
        return False

    monkeypatch.setattr(
        agent_ws_server,
        "send_wire_payload",
        replace_with_oversized_error,
    )
    assert await server.send_push(message) is False


@pytest.mark.asyncio
async def test_agentserver_send_push_reports_missing_gateway_as_not_delivered():
    server = agent_ws_server.AgentWebSocketServer.__new__(
        agent_ws_server.AgentWebSocketServer
    )
    server._current_ws = None
    server._current_send_lock = None

    assert await server.send_push({"payload": {}}) is False


@pytest.mark.asyncio
async def test_stream_stops_after_oversized_chunk_is_replaced(monkeypatch):
    class FakeAgent:
        async def process_message_stream(self, request):
            for index in range(2):
                yield AgentResponseChunk(
                    request_id=request.request_id,
                    channel_id=request.channel_id,
                    payload={"content": str(index)},
                    is_complete=False,
                )

    server = agent_ws_server.AgentWebSocketServer.__new__(
        agent_ws_server.AgentWebSocketServer
    )
    server._session_stream_tasks = {}
    server._is_stateless_method_request = lambda request: True

    class ForegroundManager:
        def __init__(self):
            self.events = []

        async def begin_foreground_chat(self):
            self.events.append("begin")

        async def end_foreground_chat(self):
            self.events.append("end")

    foreground_manager = ForegroundManager()
    server._agent_manager = foreground_manager

    async def get_agent(channel_id):
        return FakeAgent()

    async def no_plan_exit_check(request, agent):
        return None

    send_count = 0

    async def replace_with_oversized_error(ws, wire):
        nonlocal send_count
        send_count += 1
        return False

    server._get_stateless_agent = get_agent
    server._check_post_process_plan_exit = no_plan_exit_check
    monkeypatch.setattr(
        agent_ws_server,
        "send_wire_payload",
        replace_with_oversized_error,
    )
    request = AgentRequest(
        request_id="stream-too-large",
        channel_id="web",
        session_id="session-1",
        req_method=ReqMethod.CHAT_SEND,
        params={},
        is_stream=True,
    )

    await server._handle_stream(FakeWebSocket(), request, asyncio.Lock())

    assert send_count == 1
    assert foreground_manager.events == ["begin", "end"]


def test_agent_ws_server_has_no_direct_websocket_send_calls():
    path = Path(agent_ws_server.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    direct_sends = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "send"
    ]

    assert direct_sends == []


@pytest.mark.asyncio
async def test_send_wire_payload_refuses_non_finite_floats(monkeypatch):
    """NaN/Infinity anywhere in the payload must never produce a frame."""
    monkeypatch.setattr(ws_send, "AGENT_WS_SEND_BUDGET_BYTES", 1024)
    ws = FakeWebSocket()
    for poison in (float("nan"), float("inf"), float("-inf")):
        wire = {"request_id": "r1", "body": {"metric": poison}}
        with pytest.raises(ValueError):
            await ws_send.send_wire_payload(ws, wire)
    nested = {"request_id": "r1", "body": {"rows": [{"v": [1.0, float("nan")]}]}}
    with pytest.raises(ValueError):
        await ws_send.send_wire_payload(ws, nested)
    assert ws.sent == []

    healthy = {"request_id": "r1", "body": {"metric": 1.5}}
    assert await ws_send.send_wire_payload(ws, healthy) is True
    assert json.loads(ws.sent[0]) == healthy
