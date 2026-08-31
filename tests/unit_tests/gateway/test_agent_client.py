import asyncio
import json
import logging

import pytest
from websockets.exceptions import ConnectionClosedError

from jiuwenswarm.common.ws_limits import AGENT_WS_MAX_MESSAGE_BYTES
from jiuwenswarm.common.e2a.gateway_normalize import e2a_from_agent_fields
from jiuwenswarm.common.e2a.gateway_normalize import message_to_e2a
from jiuwenswarm.common.e2a.wire_codec import (
    encode_agent_chunk_for_wire,
    encode_agent_response_for_wire,
)
from jiuwenswarm.gateway.routing import agent_client
from jiuwenswarm.gateway.routing.agent_client import WebSocketAgentServerClient
from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.schema.message import Message, ReqMethod


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent_payloads: list[dict] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent_payloads.append(data)

    async def close(self) -> None:
        self.closed = True


class ClosingSendWebSocket:
    async def send(self, data: str) -> None:
        raise ConnectionClosedError(None, None)


class ClosingRecvWebSocket:
    def __init__(self) -> None:
        self.recv_calls = 0

    async def recv(self) -> str:
        self.recv_calls += 1
        raise ConnectionClosedError(None, None)


class BlockingSendWebSocket(FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()

    async def send(self, data: str) -> None:
        self.send_started.set()
        await self.release_send.wait()
        await super().send(data)

    async def close(self) -> None:
        self.closed = True
        self.release_send.set()


class BlockingCloseWebSocket(FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def close(self) -> None:
        self.close_started.set()
        await self.release_close.wait()
        self.closed = True


class AgentClientHarness(WebSocketAgentServerClient):
    def set_ws_for_test(self, ws) -> None:
        self._ws = ws

    def set_uri_for_test(self, uri: str) -> None:
        self._uri = uri

    def set_running_for_test(self, running: bool) -> None:
        self._running = running

    def set_server_ready_for_test(self, ready: bool) -> None:
        self._server_ready = ready

    def is_running_for_test(self) -> bool:
        return self._running

    def get_ws_for_test(self):
        return self._ws

    def get_uri_for_test(self):
        return self._uri

    def is_disconnecting_for_test(self) -> bool:
        return self._disconnecting

    def has_message_queue_for_test(self, request_id: str) -> bool:
        return request_id in self._message_queues

    def get_message_queue_for_test(self, request_id: str):
        return self._message_queues[request_id]

    def has_unary_operation_for_test(self, request_id: str) -> bool:
        return request_id in self._unary_operations

    def set_message_queue_for_test(self, request_id: str, queue) -> None:
        self._message_queues[request_id] = queue

    def set_cancelled_marker_for_test(self, request_id: str, token: object) -> None:
        self._cancelled_request_ids[request_id] = token

    def get_cancelled_marker_for_test(self, request_id: str):
        return self._cancelled_request_ids.get(request_id)

    async def run_message_receiver_loop_for_test(self) -> None:
        await self._message_receiver_loop()

    async def stop_receiver_after_fatal_error_for_test(
        self, exc: BaseException
    ) -> None:
        await self._stop_receiver_after_fatal_error(exc)


class ReconnectingAgentClientHarness(AgentClientHarness):
    def __init__(self) -> None:
        super().__init__()
        self.connect_calls: list[str] = []
        self.reconnected_ws = FakeWebSocket()

    async def _connect_transport(self, uri: str) -> None:
        self.connect_calls.append(uri)
        self._uri = uri
        self._ws = self.reconnected_ws
        self._connection_generation += 1
        self._server_ready = True


class LifecycleAgentClientHarness(AgentClientHarness):
    def __init__(self) -> None:
        super().__init__()
        self.connect_started = asyncio.Event()
        self.reconnected_ws = FakeWebSocket()

    async def _connect_transport(self, uri: str) -> None:
        self.connect_started.set()
        self._uri = uri
        self._ws = self.reconnected_ws
        self._connection_generation += 1
        self._server_ready = True


class StaleAdmissionAgentClientHarness(LifecycleAgentClientHarness):
    def __init__(self) -> None:
        super().__init__()
        self.admission_captured = asyncio.Event()
        self.release_admission = asyncio.Event()

    async def _ensure_connected_for_request(self):
        connection = await super()._ensure_connected_for_request()
        self.admission_captured.set()
        await self.release_admission.wait()
        return connection


def test_agent_client_uses_shared_websocket_limit():
    assert not hasattr(agent_client, "_WS_MAX_SIZE")
    assert agent_client.AGENT_WS_MAX_MESSAGE_BYTES == AGENT_WS_MAX_MESSAGE_BYTES


def test_agent_client_log_json_redacts_auth_token_without_mutating_payload():
    class BrokenString:
        def __str__(self) -> str:
            raise RuntimeError("cannot serialize")

    payload = {
        "params": {
            "auth_token": "formal-route-secret",
            "nested": [{"AUTH_TOKEN": "second-secret"}],
        },
        "forces_safe_repr_fallback": BrokenString(),
    }

    rendered = agent_client._to_json(payload)

    assert "formal-route-secret" not in rendered
    assert "second-secret" not in rendered
    assert rendered.count("[REDACTED]") == 2
    assert payload["params"]["auth_token"] == "formal-route-secret"
    assert payload["params"]["nested"][0]["AUTH_TOKEN"] == "second-secret"


@pytest.mark.asyncio
async def test_send_request_logs_bounded_metadata_without_rendering_audio_payload(
    caplog,
    monkeypatch,
):
    target_logger = logging.getLogger(agent_client.__name__)
    previous_level = target_logger.level
    previous_propagate = target_logger.propagate
    target_logger.addHandler(caplog.handler)
    target_logger.setLevel(logging.DEBUG)
    target_logger.propagate = False
    client = AgentClientHarness()
    ws = FakeWebSocket()
    client.set_ws_for_test(ws)
    audio_sentinel = "AUDIO_BASE64_SENTINEL_" + ("A" * 20_000)
    env = e2a_from_agent_fields(
        request_id="rid-native-audio-log",
        channel_id="web",
        session_id="sess-native-audio-log",
        params={
            "content": audio_sentinel,
            "frame_count": 16,
            "auth_token": "formal-route-secret",
        },
        is_stream=False,
    )
    expected_wire_payload = env.to_dict()

    def reject_hot_path_log_serialization(_payload):
        raise AssertionError("unary send hot path must not render the E2A payload")

    monkeypatch.setattr(agent_client, "_to_json", reject_hot_path_log_serialization)

    try:
        request = asyncio.create_task(client.send_request(env))
        for _ in range(100):
            if ws.sent_payloads:
                break
            await asyncio.sleep(0.001)
        assert ws.sent_payloads

        queue = client.get_message_queue_for_test("rid-native-audio-log")
        await queue.put(
            encode_agent_response_for_wire(
                AgentResponse(
                    request_id="rid-native-audio-log",
                    channel_id="web",
                    ok=True,
                    payload={"status": "accepted"},
                ),
                response_id="rid-native-audio-log",
            )
        )
        response = await asyncio.wait_for(request, timeout=0.5)
    finally:
        target_logger.removeHandler(caplog.handler)
        target_logger.setLevel(previous_level)
        target_logger.propagate = previous_propagate

    assert response.payload == {"status": "accepted"}
    assert json.loads(ws.sent_payloads[0]) == expected_wire_payload
    assert "rid-native-audio-log" in caplog.text
    assert audio_sentinel not in caplog.text
    assert "formal-route-secret" not in caplog.text
    assert max(len(record.getMessage()) for record in caplog.records) < 512


@pytest.mark.asyncio
async def test_send_request_stream_keeps_tail_window_for_processing_status(monkeypatch):
    client = AgentClientHarness()
    client.set_ws_for_test(FakeWebSocket())

    monkeypatch.setattr(
        "jiuwenswarm.gateway.routing.agent_client._STREAM_TRAILING_MESSAGE_GRACE_SECONDS",
        0.05,
    )

    env = e2a_from_agent_fields(
        request_id="rid-tail",
        channel_id="acp",
        session_id="sess-tail",
        params={"content": "hello"},
        is_stream=True,
    )

    async def inject_frames():
        while not client.has_message_queue_for_test("rid-tail"):
            await asyncio.sleep(0.001)
        queue = client.get_message_queue_for_test("rid-tail")
        await queue.put(
            encode_agent_chunk_for_wire(
                AgentResponseChunk(
                    request_id="rid-tail",
                    channel_id="acp",
                    payload={"content": "partial", "event_type": "chat.delta"},
                    is_complete=False,
                ),
                response_id="rid-tail",
                sequence=0,
            )
        )
        await queue.put(
            encode_agent_chunk_for_wire(
                AgentResponseChunk(
                    request_id="rid-tail",
                    channel_id="acp",
                    payload={"is_complete": True},
                    is_complete=True,
                ),
                response_id="rid-tail",
                sequence=1,
            )
        )
        await asyncio.sleep(0.01)
        await queue.put(
            encode_agent_chunk_for_wire(
                AgentResponseChunk(
                    request_id="rid-tail",
                    channel_id="acp",
                    payload={
                        "event_type": "chat.processing_status",
                        "is_processing": False,
                    },
                    is_complete=False,
                ),
                response_id="rid-tail",
                sequence=2,
            )
        )

    injector = asyncio.create_task(inject_frames())
    chunks = []
    async for chunk in client.send_request_stream(env):
        chunks.append(chunk)
    await injector

    assert [chunk.payload for chunk in chunks] == [
        {"content": "partial", "event_type": "chat.delta"},
        {"is_complete": True},
        {"event_type": "chat.processing_status", "is_processing": False},
    ]
    assert client.has_message_queue_for_test("rid-tail") is False


@pytest.mark.asyncio
async def test_send_request_stream_absorbs_duplicate_complete_frames(monkeypatch):
    client = AgentClientHarness()
    client.set_ws_for_test(FakeWebSocket())

    monkeypatch.setattr(
        "jiuwenswarm.gateway.routing.agent_client._STREAM_TRAILING_MESSAGE_GRACE_SECONDS",
        0.05,
    )

    env = e2a_from_agent_fields(
        request_id="rid-complete",
        channel_id="acp",
        session_id="sess-complete",
        params={"content": "hello"},
        is_stream=True,
    )

    async def inject_frames():
        while not client.has_message_queue_for_test("rid-complete"):
            await asyncio.sleep(0.001)
        queue = client.get_message_queue_for_test("rid-complete")
        for seq in (0, 1):
            await queue.put(
                encode_agent_chunk_for_wire(
                    AgentResponseChunk(
                        request_id="rid-complete",
                        channel_id="acp",
                        payload={"is_complete": True},
                        is_complete=True,
                    ),
                    response_id="rid-complete",
                    sequence=seq,
                )
            )

    injector = asyncio.create_task(inject_frames())
    chunks = []
    async for chunk in client.send_request_stream(env):
        chunks.append(chunk)
    await injector

    assert len(chunks) == 2
    assert all(chunk.is_complete for chunk in chunks)
    assert client.has_message_queue_for_test("rid-complete") is False


@pytest.mark.asyncio
async def test_message_receiver_loop_stops_on_closed_websocket():
    client = AgentClientHarness()
    ws = ClosingRecvWebSocket()
    client.set_ws_for_test(ws)
    client.set_running_for_test(True)

    await asyncio.wait_for(client.run_message_receiver_loop_for_test(), timeout=0.1)

    assert client.is_running_for_test() is False
    assert ws.recv_calls == 1


@pytest.mark.asyncio
async def test_message_receiver_loop_logs_close_diagnostics(caplog):
    target_logger = logging.getLogger("jiuwenswarm.gateway.routing.agent_client")
    target_logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger=target_logger.name)

    client = AgentClientHarness()
    ws = ClosingRecvWebSocket()
    client.set_ws_for_test(ws)
    client.set_running_for_test(True)
    client.set_server_ready_for_test(True)
    client.set_message_queue_for_test("rid-pending", asyncio.Queue())

    try:
        await asyncio.wait_for(client.run_message_receiver_loop_for_test(), timeout=0.1)
    finally:
        target_logger.removeHandler(caplog.handler)

    assert "AgentServer WebSocket 已关闭" in caplog.text
    assert "exc_type='ConnectionClosedError'" in caplog.text
    assert "message='no close frame received or sent'" in caplog.text
    assert "close_code=1006" in caplog.text
    assert "pending_requests=1" in caplog.text
    assert "server_ready=True" in caplog.text


@pytest.mark.asyncio
async def test_send_request_fails_pending_request_when_receiver_stops():
    client = AgentClientHarness()
    ws = FakeWebSocket()
    client.set_ws_for_test(ws)

    env = e2a_from_agent_fields(
        request_id="rid-fatal-close",
        channel_id="acp",
        session_id="sess-fatal-close",
        params={"content": "hello"},
        is_stream=False,
    )

    task = asyncio.create_task(client.send_request(env))
    for _ in range(100):
        if ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    assert ws.sent_payloads

    await client.stop_receiver_after_fatal_error_for_test(
        ConnectionClosedError(None, None)
    )

    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(task, timeout=0.1)
    assert client.has_message_queue_for_test("rid-fatal-close") is False


@pytest.mark.asyncio
async def test_send_request_coalesces_exact_inflight_unary_replay():
    client = AgentClientHarness()
    ws = FakeWebSocket()
    client.set_ws_for_test(ws)
    first_env = message_to_e2a(
        Message(
            id="rid-exact-replay",
            type="req",
            channel_id="web",
            session_id="sess-exact-replay",
            params={"notification_sequence": 1},
            timestamp=1.0,
            ok=True,
            req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_NOTIFICATION_NEXT,
            metadata={"ws_id": "websocket-before-replay"},
        )
    )
    replay_env = message_to_e2a(
        Message(
            id="rid-exact-replay",
            type="req",
            channel_id="web",
            session_id="sess-exact-replay",
            params={"notification_sequence": 1},
            timestamp=2.0,
            ok=True,
            req_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_NOTIFICATION_NEXT,
            metadata={"ws_id": "websocket-after-replay"},
        )
    )

    first = asyncio.create_task(client.send_request(first_env))
    for _ in range(100):
        if ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    second = asyncio.create_task(client.send_request(replay_env))
    await asyncio.sleep(0)

    assert len(ws.sent_payloads) == 1
    queue = client.get_message_queue_for_test("rid-exact-replay")
    await queue.put(
        encode_agent_response_for_wire(
            AgentResponse(
                request_id="rid-exact-replay",
                channel_id="web",
                ok=True,
                payload={"status": "notification"},
            ),
            response_id="rid-exact-replay",
        )
    )

    first_response, second_response = await asyncio.gather(first, second)
    assert first_response.payload == {"status": "notification"}
    assert second_response.payload == first_response.payload
    assert client.has_message_queue_for_test("rid-exact-replay") is False


@pytest.mark.asyncio
async def test_disconnect_settles_retained_unary_and_allows_same_id_after_reconnect():
    client = ReconnectingAgentClientHarness()
    first_ws = FakeWebSocket()
    client.set_uri_for_test("ws://agent-server")
    client.set_ws_for_test(first_ws)
    env = e2a_from_agent_fields(
        request_id="rid-disconnect-replay",
        channel_id="web",
        session_id="sess-disconnect-replay",
        params={"notification_sequence": 1},
        is_stream=False,
    )

    stranded = asyncio.create_task(client.send_request(env))
    for _ in range(100):
        if first_ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    assert client.has_unary_operation_for_test("rid-disconnect-replay") is True

    await client.disconnect()

    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(stranded, timeout=0.1)
    assert first_ws.closed is True
    assert client.has_message_queue_for_test("rid-disconnect-replay") is False
    assert client.has_unary_operation_for_test("rid-disconnect-replay") is False

    await client.connect("ws://agent-server")
    replay = asyncio.create_task(client.send_request(env))
    for _ in range(100):
        if client.reconnected_ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    assert len(client.reconnected_ws.sent_payloads) == 1

    queue = client.get_message_queue_for_test("rid-disconnect-replay")
    await queue.put(
        encode_agent_response_for_wire(
            AgentResponse(
                request_id="rid-disconnect-replay",
                channel_id="web",
                ok=True,
                payload={"status": "reconnected"},
            ),
            response_id="rid-disconnect-replay",
        )
    )
    assert (await replay).payload == {"status": "reconnected"}


@pytest.mark.asyncio
async def test_disconnect_closes_transport_before_waiting_for_blocked_unary_send():
    client = AgentClientHarness()
    ws = BlockingSendWebSocket()
    client.set_uri_for_test("ws://agent-server")
    client.set_ws_for_test(ws)
    env = e2a_from_agent_fields(
        request_id="rid-blocked-send",
        channel_id="web",
        session_id="sess-blocked-send",
        params={"notification_sequence": 1},
        is_stream=False,
    )

    stranded = asyncio.create_task(client.send_request(env))
    await asyncio.wait_for(ws.send_started.wait(), timeout=0.1)

    await asyncio.wait_for(client.disconnect(), timeout=0.1)

    assert ws.closed is True
    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(stranded, timeout=0.1)
    assert client.has_message_queue_for_test("rid-blocked-send") is False
    assert client.has_unary_operation_for_test("rid-blocked-send") is False


@pytest.mark.asyncio
async def test_cancelled_disconnect_finishes_cleanup_before_concurrent_connect():
    client = LifecycleAgentClientHarness()
    ws = BlockingCloseWebSocket()
    client.set_uri_for_test("ws://old-agent-server")
    client.set_ws_for_test(ws)
    env = e2a_from_agent_fields(
        request_id="rid-cancelled-disconnect",
        channel_id="web",
        session_id="sess-cancelled-disconnect",
        params={"notification_sequence": 1},
        is_stream=False,
    )

    stranded = asyncio.create_task(client.send_request(env))
    for _ in range(100):
        if ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    assert ws.sent_payloads

    disconnect_task = asyncio.create_task(client.disconnect())
    await asyncio.wait_for(ws.close_started.wait(), timeout=0.1)
    disconnect_task.cancel()
    connect_task = asyncio.create_task(client.connect("ws://new-agent-server"))
    await asyncio.sleep(0)

    assert disconnect_task.done() is False
    assert client.connect_started.is_set() is False
    assert client.is_disconnecting_for_test() is True

    ws.release_close.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(disconnect_task, timeout=0.1)
    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(stranded, timeout=0.1)
    await asyncio.wait_for(connect_task, timeout=0.1)

    assert ws.closed is True
    assert client.is_disconnecting_for_test() is False
    assert client.has_message_queue_for_test("rid-cancelled-disconnect") is False
    assert client.has_unary_operation_for_test("rid-cancelled-disconnect") is False
    assert client.get_ws_for_test() is client.reconnected_ws
    assert client.get_uri_for_test() == "ws://new-agent-server"


@pytest.mark.asyncio
async def test_explicit_disconnect_wins_over_queued_automatic_reconnect():
    client = LifecycleAgentClientHarness()
    client.set_uri_for_test("ws://failed-agent-server")
    client.set_ws_for_test(None)
    env = e2a_from_agent_fields(
        request_id="rid-disconnect-reconnect-race",
        channel_id="web",
        session_id="sess-disconnect-reconnect-race",
        params={"notification_sequence": 1},
        is_stream=False,
    )

    await client._lifecycle_lock.acquire()
    disconnect_task = asyncio.create_task(client.disconnect())
    await asyncio.sleep(0)
    stale_reconnect = asyncio.create_task(client.send_request(env))
    await asyncio.sleep(0)
    client._lifecycle_lock.release()

    await asyncio.wait_for(disconnect_task, timeout=0.1)
    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(stale_reconnect, timeout=0.1)
    assert client.connect_started.is_set() is False
    assert client.get_ws_for_test() is None
    assert client.get_uri_for_test() is None
    assert client.has_message_queue_for_test("rid-disconnect-reconnect-race") is False
    assert client.has_unary_operation_for_test("rid-disconnect-reconnect-race") is False


@pytest.mark.asyncio
async def test_stale_unary_admission_cannot_cross_connection_generation():
    client = StaleAdmissionAgentClientHarness()
    old_ws = FakeWebSocket()
    client.set_uri_for_test("ws://old-agent-server")
    client.set_ws_for_test(old_ws)
    env = e2a_from_agent_fields(
        request_id="rid-stale-unary-admission",
        channel_id="web",
        session_id="sess-stale-unary-admission",
        params={"notification_sequence": 1},
        is_stream=False,
    )

    stale_request = asyncio.create_task(client.send_request(env))
    await asyncio.wait_for(client.admission_captured.wait(), timeout=0.1)
    await client.disconnect()
    await client.connect("ws://new-agent-server")
    client.release_admission.set()

    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(stale_request, timeout=0.1)
    assert old_ws.sent_payloads == []
    assert client.reconnected_ws.sent_payloads == []
    assert client.has_message_queue_for_test("rid-stale-unary-admission") is False
    assert client.has_unary_operation_for_test("rid-stale-unary-admission") is False


@pytest.mark.asyncio
async def test_stale_stream_admission_cannot_cross_connection_generation():
    client = StaleAdmissionAgentClientHarness()
    old_ws = FakeWebSocket()
    client.set_uri_for_test("ws://old-agent-server")
    client.set_ws_for_test(old_ws)
    env = e2a_from_agent_fields(
        request_id="rid-stale-stream-admission",
        channel_id="web",
        session_id="sess-stale-stream-admission",
        params={"content": "must not cross reconnect"},
        is_stream=True,
    )
    stream = client.send_request_stream(env)

    stale_request = asyncio.create_task(anext(stream))
    await asyncio.wait_for(client.admission_captured.wait(), timeout=0.1)
    await client.disconnect()
    await client.connect("ws://new-agent-server")
    client.release_admission.set()

    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await asyncio.wait_for(stale_request, timeout=0.1)
    assert old_ws.sent_payloads == []
    assert client.reconnected_ws.sent_payloads == []
    assert client.has_message_queue_for_test("rid-stale-stream-admission") is False


@pytest.mark.asyncio
async def test_old_stream_cleanup_cannot_remove_same_id_queue_after_reconnect():
    client = LifecycleAgentClientHarness()
    old_ws = FakeWebSocket()
    client.set_uri_for_test("ws://old-agent-server")
    client.set_ws_for_test(old_ws)
    env = e2a_from_agent_fields(
        request_id="rid-stream-generation-reuse",
        channel_id="web",
        session_id="sess-stream-generation-reuse",
        params={"content": "generation scoped"},
        is_stream=True,
    )

    old_stream = client.send_request_stream(env)
    old_first = asyncio.create_task(anext(old_stream))
    for _ in range(100):
        if old_ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    old_queue = client.get_message_queue_for_test("rid-stream-generation-reuse")
    await old_queue.put(
        encode_agent_chunk_for_wire(
            AgentResponseChunk(
                request_id="rid-stream-generation-reuse",
                channel_id="web",
                payload={"content": "old partial", "event_type": "chat.delta"},
                is_complete=False,
            ),
            response_id="rid-stream-generation-reuse",
            sequence=0,
        )
    )
    assert (await old_first).payload["content"] == "old partial"

    await client.disconnect()
    await client.connect("ws://new-agent-server")
    new_stream = client.send_request_stream(env)
    new_first = asyncio.create_task(anext(new_stream))
    for _ in range(100):
        if client.reconnected_ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    new_queue = client.get_message_queue_for_test("rid-stream-generation-reuse")
    assert new_queue is not old_queue

    await old_stream.aclose()
    assert client.get_message_queue_for_test("rid-stream-generation-reuse") is new_queue

    await new_queue.put(
        encode_agent_chunk_for_wire(
            AgentResponseChunk(
                request_id="rid-stream-generation-reuse",
                channel_id="web",
                payload={"content": "new partial", "event_type": "chat.delta"},
                is_complete=False,
            ),
            response_id="rid-stream-generation-reuse",
            sequence=0,
        )
    )
    assert (await new_first).payload["content"] == "new partial"
    await new_stream.aclose()
    assert client.has_message_queue_for_test("rid-stream-generation-reuse") is False


@pytest.mark.asyncio
async def test_old_delayed_marker_cleanup_cannot_clear_replacement_owner(monkeypatch):
    client = AgentClientHarness()
    old_token = object()
    replacement_token = object()
    client.set_cancelled_marker_for_test("rid-marker-reuse", replacement_token)

    async def no_delay(_seconds):
        return None

    monkeypatch.setattr(agent_client.asyncio, "sleep", no_delay)
    await client._delayed_cleanup_cancelled_request_id(
        "rid-marker-reuse",
        old_token,
    )
    assert client.get_cancelled_marker_for_test("rid-marker-reuse") is replacement_token

    await client._delayed_cleanup_cancelled_request_id(
        "rid-marker-reuse",
        replacement_token,
    )
    assert client.get_cancelled_marker_for_test("rid-marker-reuse") is None


@pytest.mark.asyncio
async def test_send_request_rejects_changed_inflight_unary_payload():
    client = AgentClientHarness()
    ws = FakeWebSocket()
    client.set_ws_for_test(ws)
    first_env = e2a_from_agent_fields(
        request_id="rid-replay-conflict",
        channel_id="web",
        session_id="sess-replay-conflict",
        params={"notification_sequence": 1},
        is_stream=False,
    )
    changed_env = e2a_from_agent_fields(
        request_id="rid-replay-conflict",
        channel_id="web",
        session_id="sess-replay-conflict",
        params={"notification_sequence": 2},
        is_stream=False,
    )

    first = asyncio.create_task(client.send_request(first_env))
    for _ in range(100):
        if ws.sent_payloads:
            break
        await asyncio.sleep(0.001)

    with pytest.raises(RuntimeError, match="changed its unary payload"):
        await client.send_request(changed_env)
    assert len(ws.sent_payloads) == 1

    queue = client.get_message_queue_for_test("rid-replay-conflict")
    await queue.put(
        encode_agent_response_for_wire(
            AgentResponse(
                request_id="rid-replay-conflict",
                channel_id="web",
                ok=True,
                payload={"status": "notification"},
            ),
            response_id="rid-replay-conflict",
        )
    )
    assert (await first).ok is True


@pytest.mark.asyncio
async def test_cancelled_unary_waiter_does_not_cancel_exact_replay_owner():
    client = AgentClientHarness()
    ws = FakeWebSocket()
    client.set_ws_for_test(ws)
    env = e2a_from_agent_fields(
        request_id="rid-cancelled-waiter",
        channel_id="web",
        session_id="sess-cancelled-waiter",
        params={"notification_sequence": 1},
        is_stream=False,
    )

    cancelled_waiter = asyncio.create_task(client.send_request(env))
    for _ in range(100):
        if ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter

    replay_waiter = asyncio.create_task(client.send_request(env))
    await asyncio.sleep(0)
    assert len(ws.sent_payloads) == 1
    queue = client.get_message_queue_for_test("rid-cancelled-waiter")
    await queue.put(
        encode_agent_response_for_wire(
            AgentResponse(
                request_id="rid-cancelled-waiter",
                channel_id="web",
                ok=True,
                payload={"status": "notification"},
            ),
            response_id="rid-cancelled-waiter",
        )
    )

    assert (await replay_waiter).payload == {"status": "notification"}
    assert client.has_message_queue_for_test("rid-cancelled-waiter") is False


@pytest.mark.asyncio
async def test_send_request_reconnects_before_new_request_after_disconnect():
    client = ReconnectingAgentClientHarness()
    client.set_uri_for_test("ws://agent-server")
    client.set_ws_for_test(None)

    env = e2a_from_agent_fields(
        request_id="rid-reconnect",
        channel_id="acp",
        session_id="sess-reconnect",
        params={"content": "hello"},
        is_stream=False,
    )

    task = asyncio.create_task(client.send_request(env))
    for _ in range(100):
        if client.reconnected_ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    assert client.connect_calls == ["ws://agent-server"]
    assert client.reconnected_ws.sent_payloads

    queue = client.get_message_queue_for_test("rid-reconnect")
    await queue.put(
        encode_agent_response_for_wire(
            AgentResponse(
                request_id="rid-reconnect",
                channel_id="acp",
                ok=True,
                payload={"status": "reconnected"},
            ),
            response_id="rid-reconnect",
        )
    )

    response = await asyncio.wait_for(task, timeout=0.1)

    assert response.ok is True
    assert response.payload == {"status": "reconnected"}
    assert client.has_message_queue_for_test("rid-reconnect") is False


@pytest.mark.asyncio
async def test_send_request_clears_connection_when_send_fails():
    client = ReconnectingAgentClientHarness()
    client.set_uri_for_test("ws://agent-server")
    client.set_ws_for_test(ClosingSendWebSocket())
    client.set_running_for_test(True)
    client.set_server_ready_for_test(True)

    failed_env = e2a_from_agent_fields(
        request_id="rid-send-close",
        channel_id="acp",
        session_id="sess-send-close",
        params={"content": "hello"},
        is_stream=False,
    )

    with pytest.raises(RuntimeError, match="AgentServer WebSocket connection closed"):
        await client.send_request(failed_env)

    assert client.get_ws_for_test() is None
    assert client.is_running_for_test() is False
    assert client.has_message_queue_for_test("rid-send-close") is False

    reconnect_env = e2a_from_agent_fields(
        request_id="rid-after-send-close",
        channel_id="acp",
        session_id="sess-send-close",
        params={"content": "again"},
        is_stream=False,
    )

    task = asyncio.create_task(client.send_request(reconnect_env))
    for _ in range(100):
        if client.reconnected_ws.sent_payloads:
            break
        await asyncio.sleep(0.001)
    assert client.connect_calls == ["ws://agent-server"]
    assert client.reconnected_ws.sent_payloads

    queue = client.get_message_queue_for_test("rid-after-send-close")
    await queue.put(
        encode_agent_response_for_wire(
            AgentResponse(
                request_id="rid-after-send-close",
                channel_id="acp",
                ok=True,
                payload={"status": "reconnected"},
            ),
            response_id="rid-after-send-close",
        )
    )

    response = await asyncio.wait_for(task, timeout=0.1)
    assert response.ok is True
    assert client.has_message_queue_for_test("rid-after-send-close") is False
