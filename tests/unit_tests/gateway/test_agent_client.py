import asyncio
import hashlib
import json
import logging

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

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
    def __init__(self, exc: BaseException | None = None) -> None:
        self.recv_calls = 0
        self.exc = exc or ConnectionClosedError(None, None)

    async def recv(self) -> str:
        self.recv_calls += 1
        raise self.exc


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

    def get_unary_task_name_for_test(self, request_id: str) -> str:
        return self._unary_operations[request_id][3].get_name()

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


def test_agent_client_log_json_is_content_free_without_mutating_payload():
    class PrivateValue:
        def __str__(self) -> str:
            return "sentinel-private-object"

        def __repr__(self) -> str:
            return "sentinel-private-repr"

    private_value = PrivateValue()
    private_sequence = 9876543210123456789
    payload = {
        "type": "sentinel-private-type",
        "event": "sentinel-private-event",
        "protocol_version": "sentinel-private-version",
        "request_id": "sentinel-private-request-id",
        "response_id": "sentinel-private-response-id",
        "channel": "sentinel-private-channel",
        "channel_id": "sentinel-private-channel-id",
        "method": "sentinel-private-method",
        "status": "sentinel-private-status",
        "response_kind": "sentinel-private-response-kind",
        "is_stream": False,
        "ok": "sentinel-private-ok",
        "is_complete": "sentinel-private-complete",
        "sequence": private_sequence,
        "params": {
            "auth_token": "formal-route-secret",
            "Final-Text": "mixed-case-transcript",
            "nested-list": [
                {"AUTH TOKEN": "separator-secret"},
                {"raw_audio": "deep-audio-secret"},
            ],
        },
        "payload": private_value,
        "PAY-LOAD": {"spokenText": "unknown-top-level-secret"},
        "forces_string_conversion": PrivateValue(),
    }

    rendered = agent_client._to_json(payload)
    rendered_summary = json.loads(rendered)

    assert '"request_id_ref": "ref:' in rendered
    assert '"response_id_ref": "ref:' in rendered
    assert '"channel_ref": "ref:' in rendered
    assert '"channel_id_ref": "ref:' in rendered
    assert '"method_ref": "ref:' in rendered
    assert '"status_ref": "ref:' in rendered
    assert '"is_stream": false' in rendered
    assert '"ok": "[NON_BOOLEAN]"' in rendered
    assert '"is_complete": "[NON_BOOLEAN]"' in rendered
    assert rendered_summary["sequence_kind"] == "integer"
    for ref_key in (
        "type_ref",
        "event_ref",
        "protocol_version_ref",
        "request_id_ref",
        "response_id_ref",
        "channel_ref",
        "channel_id_ref",
        "method_ref",
        "status_ref",
        "response_kind_ref",
    ):
        assert rendered_summary[ref_key].startswith("ref:")
        assert len(rendered_summary[ref_key]) == 68
    assert "sha256:" not in rendered
    assert "sentinel-private-type" not in rendered
    assert "sentinel-private-event" not in rendered
    assert "sentinel-private-version" not in rendered
    assert "sentinel-private-request-id" not in rendered
    assert "sentinel-private-response-id" not in rendered
    assert "sentinel-private-channel" not in rendered
    assert "sentinel-private-channel-id" not in rendered
    assert "sentinel-private-method" not in rendered
    assert "sentinel-private-status" not in rendered
    assert "sentinel-private-response-kind" not in rendered
    assert "sentinel-private-ok" not in rendered
    assert "sentinel-private-complete" not in rendered
    assert str(private_sequence) not in rendered
    assert "formal-route-secret" not in rendered
    assert "mixed-case-transcript" not in rendered
    assert "separator-secret" not in rendered
    assert "deep-audio-secret" not in rendered
    assert "unknown-top-level-secret" not in rendered
    assert "sentinel-private-object" not in rendered
    assert "sentinel-private-repr" not in rendered
    assert payload["params"]["auth_token"] == "formal-route-secret"
    assert payload["params"]["Final-Text"] == "mixed-case-transcript"
    assert payload["params"]["nested-list"][0]["AUTH TOKEN"] == ("separator-secret")
    assert payload["params"]["nested-list"][1]["raw_audio"] == ("deep-audio-secret")
    assert payload["payload"] is private_value


def test_agent_client_log_refs_are_secret_keyed_and_sequence_is_shape_only():
    candidate = "1"
    public_digest = hashlib.sha256(
        b"request_id\0str\0" + candidate.encode("ascii")
    ).hexdigest()

    first = agent_client._content_hidden_log_ref("request_id", candidate)
    repeated = agent_client._content_hidden_log_ref("request_id", candidate)
    other_field = agent_client._content_hidden_log_ref("response_id", candidate)
    summary = json.loads(agent_client._to_json({"sequence": 9876543210123456789}))

    assert first.startswith("ref:")
    assert first == repeated
    assert first != other_field
    assert first != f"sha256:{public_digest}"
    assert first.removeprefix("ref:") != public_digest
    assert summary == {"field_count": 1, "sequence_kind": "integer"}


@pytest.mark.asyncio
async def test_agent_client_unary_and_stream_logs_never_include_payload_content(
    caplog, monkeypatch
):
    target_loggers = (
        logging.getLogger("jiuwenswarm.gateway.routing.agent_client"),
        logging.getLogger("jiuwenswarm.common.e2a.wire_codec"),
    )
    for target_logger in target_loggers:
        target_logger.addHandler(caplog.handler)
        caplog.set_level(logging.DEBUG, logger=target_logger.name)
    monkeypatch.setattr(agent_client, "_STREAM_TRAILING_MESSAGE_GRACE_SECONDS", 0.001)

    unary_success_params = {
        "FINAL_TEXT": "sentinel-unary-success-text",
        "nested-list": [{"Bearer-Token": "sentinel-unary-success-credential"}],
    }
    unary_error_params = {
        "spoken-text": "sentinel-unary-error-text",
        "deep": [{"RAW AUDIO": "sentinel-unary-error-audio"}],
    }
    stream_success_params = {
        "Transcript": "sentinel-stream-success-text",
        "deep": {"API_KEY": "sentinel-stream-success-credential"},
    }
    stream_error_params = {
        "raw_audio": "sentinel-stream-error-audio",
        "deep-list": [{"AUTH-TOKEN": "sentinel-stream-error-credential"}],
    }
    unary_success_request_id = "sentinel-private-unary-request-scalar"
    unary_success_channel = "sentinel-private-unary-channel-scalar"
    unary_success_method = "sentinel-private-unary-method-scalar"

    try:
        unary_client = AgentClientHarness()
        unary_ws = FakeWebSocket()
        unary_client.set_ws_for_test(unary_ws)
        unary_env = e2a_from_agent_fields(
            request_id=unary_success_request_id,
            channel_id=unary_success_channel,
            session_id="sess-private-unary-success",
            req_method=unary_success_method,
            params=unary_success_params,
            is_stream=False,
        )
        unary_task = asyncio.create_task(unary_client.send_request(unary_env))
        for _ in range(100):
            if unary_ws.sent_payloads:
                break
            await asyncio.sleep(0.001)
        assert unary_ws.sent_payloads
        unary_task_name = unary_client.get_unary_task_name_for_test(
            unary_success_request_id
        )
        unary_response_payload = {
            "Final-Text": "sentinel-unary-response-text",
            "nested": [{"credential": "sentinel-unary-response-credential"}],
        }
        await unary_client.get_message_queue_for_test(unary_success_request_id).put(
            encode_agent_response_for_wire(
                AgentResponse(
                    request_id=unary_success_request_id,
                    channel_id=unary_success_channel,
                    ok=True,
                    payload=unary_response_payload,
                ),
                response_id=unary_success_request_id,
            )
        )
        unary_response = await unary_task
        assert unary_response.payload == unary_response_payload
        assert json.loads(unary_ws.sent_payloads[0])["params"] == unary_success_params

        unary_error_client = AgentClientHarness()
        unary_error_client.set_ws_for_test(ClosingSendWebSocket())
        unary_error_env = e2a_from_agent_fields(
            request_id="rid-private-unary-error",
            channel_id="web",
            session_id="sess-private-unary-error",
            req_method="chat.send",
            params=unary_error_params,
            is_stream=False,
        )
        with pytest.raises(
            RuntimeError, match="AgentServer WebSocket connection closed"
        ):
            await unary_error_client.send_request(unary_error_env)

        stream_client = AgentClientHarness()
        stream_ws = FakeWebSocket()
        stream_client.set_ws_for_test(stream_ws)
        stream_env = e2a_from_agent_fields(
            request_id="rid-private-stream-success",
            channel_id="web",
            session_id="sess-private-stream-success",
            req_method="chat.send",
            params=stream_success_params,
            is_stream=True,
        )

        async def inject_stream_response():
            while not stream_client.has_message_queue_for_test(
                "rid-private-stream-success"
            ):
                await asyncio.sleep(0.001)
            stream_response_payload = {
                "event_type": "sentinel-stream-response-event",
                "Final-Text": "sentinel-stream-response-text",
                "deep": [{"AUTH TOKEN": "sentinel-stream-response-credential"}],
            }
            await stream_client.get_message_queue_for_test(
                "rid-private-stream-success"
            ).put(
                encode_agent_chunk_for_wire(
                    AgentResponseChunk(
                        request_id="rid-private-stream-success",
                        channel_id="web",
                        payload=stream_response_payload,
                        is_complete=True,
                    ),
                    response_id="rid-private-stream-success",
                    sequence=0,
                )
            )
            return stream_response_payload

        injector = asyncio.create_task(inject_stream_response())
        stream_chunks = [
            chunk async for chunk in stream_client.send_request_stream(stream_env)
        ]
        stream_response_payload = await injector
        assert [chunk.payload for chunk in stream_chunks] == [stream_response_payload]
        assert json.loads(stream_ws.sent_payloads[0])["params"] == stream_success_params

        stream_error_client = AgentClientHarness()
        stream_error_client.set_ws_for_test(ClosingSendWebSocket())
        stream_error_env = e2a_from_agent_fields(
            request_id="rid-private-stream-error",
            channel_id="web",
            session_id="sess-private-stream-error",
            req_method="chat.send",
            params=stream_error_params,
            is_stream=True,
        )
        with pytest.raises(
            RuntimeError, match="AgentServer WebSocket connection closed"
        ):
            async for _ in stream_error_client.send_request_stream(stream_error_env):
                pass
    finally:
        for target_logger in target_loggers:
            target_logger.removeHandler(caplog.handler)

    captured_logs = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name in {target_logger.name for target_logger in target_loggers}
    )
    private_sentinels = (
        "sentinel-unary-success-text",
        "sentinel-unary-success-credential",
        "sentinel-unary-error-text",
        "sentinel-unary-error-audio",
        "sentinel-stream-success-text",
        "sentinel-stream-success-credential",
        "sentinel-stream-error-audio",
        "sentinel-stream-error-credential",
        "sentinel-unary-response-text",
        "sentinel-unary-response-credential",
        "sentinel-stream-response-event",
        "sentinel-stream-response-text",
        "sentinel-stream-response-credential",
        unary_success_request_id,
        unary_success_channel,
        unary_success_method,
        "rid-private-unary-error",
        "rid-private-stream-success",
        "rid-private-stream-error",
    )
    assert not [sentinel for sentinel in private_sentinels if sentinel in captured_logs]
    assert "request_id_ref=ref:" in captured_logs
    assert "channel_ref=ref:" in captured_logs
    assert "method_ref=ref:" in captured_logs
    assert "sha256:" not in captured_logs
    assert unary_success_request_id not in unary_task_name
    assert "ref:" not in unary_task_name
    assert "sha256:" not in unary_task_name
    assert {record.name for record in caplog.records}.issuperset(
        {target_logger.name for target_logger in target_loggers}
    )
    assert not [
        record
        for record in caplog.records
        if record.name in {target_logger.name for target_logger in target_loggers}
        and record.exc_info is not None
    ]
    assert unary_success_params["FINAL_TEXT"] == "sentinel-unary-success-text"
    assert unary_error_params["spoken-text"] == "sentinel-unary-error-text"
    assert stream_success_params["Transcript"] == "sentinel-stream-success-text"
    assert stream_error_params["raw_audio"] == "sentinel-stream-error-audio"


@pytest.mark.asyncio
async def test_agent_client_transport_logs_hide_uri_peer_exception_and_close_reason(
    caplog, monkeypatch
):
    from websockets.legacy import client as legacy_client

    target_logger = logging.getLogger("jiuwenswarm.gateway.routing.agent_client")
    target_logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger=target_logger.name)
    private_uri = (
        "wss://sentinel-private-user:sentinel-private-password@"
        "sentinel-private-host/private-path?token=sentinel-private-query"
    )

    class AckThenBlockingWebSocket(FakeWebSocket):
        def __init__(self) -> None:
            super().__init__()
            self.recv_calls = 0
            self.release_recv = asyncio.Event()
            self.remote_address = ("sentinel-private-remote-address", 43123)
            self.local_address = ("sentinel-private-local-address", 43124)
            self.state = "sentinel-private-ws-state"

        def __repr__(self) -> str:
            return "sentinel-private-ws-repr"

        async def recv(self) -> str:
            self.recv_calls += 1
            if self.recv_calls == 1:
                return json.dumps(
                    {
                        "type": "event",
                        "event": "connection.ack",
                        "request_id": "sentinel-private-ack-id",
                        "metadata": {"AUTH TOKEN": "sentinel-private-ack-token"},
                    }
                )
            await self.release_recv.wait()
            raise asyncio.CancelledError

        async def close(self) -> None:
            self.release_recv.set()
            await super().close()

    connected_ws = AckThenBlockingWebSocket()

    async def fake_connect(uri, **kwargs):
        assert uri == private_uri
        assert kwargs["origin"].endswith("sentinel-private-host")
        return connected_ws

    monkeypatch.setattr(legacy_client, "connect", fake_connect)

    try:
        connected_client = AgentClientHarness()
        await connected_client.connect(private_uri)
        await connected_client.disconnect()

        close_exc = ConnectionClosedError(
            Close(4001, "sentinel-private-close-reason"),
            Close(4001, "sentinel-private-sent-reason"),
            True,
        )
        closing_ws = ClosingRecvWebSocket(close_exc)
        closing_ws.remote_address = ("sentinel-private-close-remote", 43125)
        closing_ws.local_address = ("sentinel-private-close-local", 43126)
        closing_client = AgentClientHarness()
        closing_client.set_uri_for_test(private_uri)
        closing_client.set_ws_for_test(closing_ws)
        closing_client.set_running_for_test(True)
        closing_client.set_server_ready_for_test(True)
        closing_client.set_message_queue_for_test(
            "sentinel-private-pending-id", asyncio.Queue()
        )
        await closing_client.run_message_receiver_loop_for_test()

        private_failure = type(
            "SentinelPrivateExceptionClass",
            (RuntimeError,),
            {},
        )

        class ExplodingWebSocket:
            def __init__(self) -> None:
                self.recv_calls = 0
                self.remote_address = ("sentinel-private-error-remote", 43127)
                self.local_address = ("sentinel-private-error-local", 43128)

            async def recv(self) -> str:
                self.recv_calls += 1
                if self.recv_calls == 1:
                    raise private_failure("sentinel-private-exception-message")
                raise asyncio.CancelledError

        error_client = AgentClientHarness()
        error_client.set_uri_for_test(private_uri)
        error_client.set_ws_for_test(ExplodingWebSocket())
        error_client.set_running_for_test(True)
        await error_client.run_message_receiver_loop_for_test()

        out_of_range_error = RuntimeError("sentinel-private-out-of-range-close-message")
        out_of_range_error.code = 9876543210123456789
        out_of_range_client = AgentClientHarness()
        out_of_range_client.set_uri_for_test(private_uri)
        out_of_range_client.set_ws_for_test(FakeWebSocket())
        await out_of_range_client.stop_receiver_after_fatal_error_for_test(
            out_of_range_error
        )

        class PrivateCloseCode:
            def __str__(self) -> str:
                return "sentinel-private-close-code-string"

            def __repr__(self) -> str:
                return "sentinel-private-close-code-repr"

        object_code_error = RuntimeError("sentinel-private-object-code-message")
        object_code_error.code = PrivateCloseCode()
        object_code_client = AgentClientHarness()
        object_code_client.set_uri_for_test(private_uri)
        object_code_client.set_ws_for_test(FakeWebSocket())
        await object_code_client.stop_receiver_after_fatal_error_for_test(
            object_code_error
        )
    finally:
        target_logger.removeHandler(caplog.handler)

    records = [record for record in caplog.records if record.name == target_logger.name]
    log_material = "\n".join(
        f"{record.getMessage()} args={record.args!r}" for record in records
    )
    private_sentinels = (
        private_uri,
        "sentinel-private-user",
        "sentinel-private-password",
        "sentinel-private-host",
        "sentinel-private-query",
        "sentinel-private-remote-address",
        "sentinel-private-local-address",
        "sentinel-private-ws-state",
        "sentinel-private-ws-repr",
        "sentinel-private-ack-id",
        "sentinel-private-ack-token",
        "sentinel-private-close-reason",
        "sentinel-private-sent-reason",
        "sentinel-private-close-remote",
        "sentinel-private-close-local",
        "sentinel-private-pending-id",
        "SentinelPrivateExceptionClass",
        "sentinel-private-exception-message",
        "sentinel-private-error-remote",
        "sentinel-private-error-local",
        "sentinel-private-out-of-range-close-message",
        "9876543210123456789",
        "sentinel-private-close-code-string",
        "sentinel-private-close-code-repr",
        "sentinel-private-object-code-message",
    )
    assert not [sentinel for sentinel in private_sentinels if sentinel in log_material]
    assert "ws_id=" not in log_material
    assert "close_code=4001" in log_material
    assert "exception_class=ConnectionClosedError" in log_material
    assert "exception_class=RuntimeError" in log_material
    assert not [record for record in records if record.exc_info is not None]


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
    ws = ClosingRecvWebSocket(
        ConnectionClosedError(
            Close(4001, "sentinel-private-close-reason"),
            Close(4001, "sentinel-private-sent-reason"),
            True,
        )
    )
    client.set_ws_for_test(ws)
    client.set_running_for_test(True)
    client.set_server_ready_for_test(True)
    client.set_message_queue_for_test("rid-pending", asyncio.Queue())

    try:
        await asyncio.wait_for(client.run_message_receiver_loop_for_test(), timeout=0.1)
    finally:
        target_logger.removeHandler(caplog.handler)

    assert "AgentServer WebSocket 已关闭" in caplog.text
    assert "exception_class=ConnectionClosedError" in caplog.text
    assert "sentinel-private-close-reason" not in caplog.text
    assert "sentinel-private-sent-reason" not in caplog.text
    assert "close_code=4001" in caplog.text
    assert "pending_requests=1" in caplog.text
    assert "server_ready=True" in caplog.text
    assert not [record for record in caplog.records if record.exc_info is not None]


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
