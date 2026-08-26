# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openjiuwen.core.single_agent.rail.base import (
    AgentCallbackContext,
    ToolCallInputs,
)

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.agents.harness.common.tools.send_file_to_user import (
    SendFileToolkit,
    clear_sent_files_for_session,
)
from jiuwenswarm.server.runtime.agent_adapter import interface_deep
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import (
    JiuWenSwarmDeepAdapter,
)
from jiuwenswarm.server.runtime.session import session_history


@dataclass
class RawChunk:
    type: str
    payload: object


@dataclass
class ControllerType:
    value: str


@dataclass
class ControllerPayload:
    type: object
    data: list[object]


class OutputLease:
    def __init__(self, chunks, *, close_release=None, close_error=None) -> None:
        self._chunks = iter(chunks)
        self.close_release = close_release
        self.close_error = close_error
        self.closed_with: list[bool] = []
        self.close_started = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def close(self, *, abort_active_round: bool) -> None:
        self.closed_with.append(abort_active_round)
        self.close_started.set()
        if self.close_release is not None:
            await self.close_release.wait()
        if self.close_error is not None:
            raise self.close_error


class FormalInstance:
    def __init__(self, lease: OutputLease) -> None:
        self.lease = lease
        self.sent = []
        self.registered_rails = []

    async def attach_output(self):
        return self.lease

    async def send_input(self, request) -> None:
        self.sent.append(request)

    def is_registered_rail(self, rail) -> bool:
        return rail in self.registered_rails


def formal_request(
    *,
    params_extra: dict | None = None,
    tools_allowed: bool = True,
) -> tuple[AgentRequest, dict]:
    params = {
        "query": "/goal must remain plain committed text",
        "mode": "agent",
        "source": "live_voice.formal",
        "supports_user_interaction": False,
        **(params_extra or {}),
    }
    metadata = {
        "enable_memory": False,
        "skip_a2ui": True,
        "formal_live_voice": True,
        "formal_live_voice_tools_allowed": tools_allowed,
    }
    request = AgentRequest(
        request_id="formal-request-1",
        channel_id="web",
        session_id="lv-formal-opaque-1",
        req_method=ReqMethod.CHAT_SEND,
        params=params,
        metadata=metadata,
        enable_memory=False,
        is_stream=True,
    )
    inputs = {
        "conversation_id": request.session_id,
        "query": params["query"],
        "channel": "web",
        "language": "en",
        "supports_user_interaction": False,
        "enable_memory": False,
        "skip_a2ui": True,
    }
    return request, inputs


def adapter_with(instance: FormalInstance) -> JiuWenSwarmDeepAdapter:
    adapter = object.__new__(JiuWenSwarmDeepAdapter)
    adapter._is_session_scoped_adapter = True
    adapter._instance = instance
    adapter._stream_event_rail = interface_deep.JiuSwarmStreamEventRail()
    instance.registered_rails = [adapter._stream_event_rail]
    seen = []

    async def update(config) -> None:
        seen.append(config)

    adapter._update_runtime_config = update
    adapter.formal_runtime_configs = seen
    return adapter


@pytest.mark.asyncio
async def test_formal_task_result_policy_removes_and_hard_denies_tools() -> None:
    rail = interface_deep.JiuSwarmStreamEventRail()
    session_id = "lv-formal-no-tools-1"
    capture = rail.open_formal_tool_event_capture(
        session_id,
        allow_tools=False,
    )
    model_inputs = SimpleNamespace(tools=[SimpleNamespace(name="delete_file")])
    await rail.before_model_call(
        SimpleNamespace(
            inputs=model_inputs,
            session=AsyncMock(),
            context=None,
            extra={rail._SID_KEY: session_id},
        )
    )
    assert model_inputs.tools == []

    tool_call = SimpleNamespace(
        id="forbidden-tool-call",
        name="delete_file",
        arguments={"path": "private.txt"},
    )
    with pytest.raises(RuntimeError, match="FORMAL_TOOL_EXECUTION_FORBIDDEN"):
        await rail.before_tool_call(
            SimpleNamespace(
                inputs=ToolCallInputs(
                    tool_call=tool_call,
                    tool_name=tool_call.name,
                    tool_args=dict(tool_call.arguments),
                ),
                session=AsyncMock(),
                extra={rail._SID_KEY: session_id},
            )
        )
    rail.close_formal_tool_event_capture(session_id, capture, abort=True)


class CallbackFormalInstance(FormalInstance):
    def __init__(self, lease: OutputLease, rail) -> None:
        super().__init__(lease)
        self.rail = rail
        self.inner_session = AsyncMock()

    async def send_input(self, request) -> None:
        await super().send_input(request)
        tool_call = SimpleNamespace(
            id="tool-call-authoritative-1",
            name="read_file",
            arguments={"path": "fixture/README.md"},
        )
        inputs = ToolCallInputs(
            tool_call=tool_call,
            tool_name=tool_call.name,
            tool_args=dict(tool_call.arguments),
        )
        context = AgentCallbackContext(
            agent=MagicMock(),
            inputs=inputs,
            session=self.inner_session,
            extra={self.rail._SID_KEY: request.inputs["conversation_id"]},
        )
        await self.rail.before_tool_call(context)
        inputs.tool_result = {"content": "fixture tool result"}
        await self.rail.after_tool_call(context)


@pytest.mark.asyncio
async def test_formal_deep_seam_uses_narrow_dispatch_and_non_aborting_detach() -> None:
    lease = OutputLease([RawChunk("answer", {"output": {"output": "formal result"}})])
    instance = FormalInstance(lease)
    adapter = adapter_with(instance)
    request, inputs = formal_request()

    chunks = [
        chunk
        async for chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        )
    ]
    assert [chunk.payload for chunk in chunks] == [
        {"event_type": "chat.final", "content": "formal result"}
    ]
    assert len(instance.sent) == 1
    assert instance.sent[0].request_id == request.request_id
    assert instance.sent[0].mode is None
    assert instance.sent[0].inputs["query"].startswith("/goal")
    assert lease.closed_with == [False]
    assert adapter.formal_runtime_configs[0].mode == "agent"
    assert adapter.formal_runtime_configs[0].supports_user_interaction is False


@pytest.mark.asyncio
async def test_formal_deep_seam_drops_passive_runtime_events_around_tool_output() -> None:
    lease = OutputLease(
        [
            RawChunk("thinking", {}),
            RawChunk("context.usage", {"rate": 0.5}),
            RawChunk("todo.updated", {"todos": [{"content": "inspect"}]}),
            RawChunk("tool_call", {"tool_call": {"name": "bash"}}),
            RawChunk(
                "tool_result",
                {"tool_result": {"tool_name": "bash", "result": "clean"}},
            ),
            RawChunk("answer", {"output": {"output": "formal result"}}),
        ]
    )
    adapter = adapter_with(FormalInstance(lease))
    request, inputs = formal_request()

    chunks = [
        chunk
        async for chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        )
    ]

    assert [chunk.payload["event_type"] for chunk in chunks] == [
        "chat.tool_call",
        "chat.tool_result",
        "chat.final",
    ]
    assert lease.closed_with == [False]


@pytest.mark.asyncio
async def test_formal_deep_seam_bridges_real_tool_callbacks_before_final() -> None:
    rail = interface_deep.JiuSwarmStreamEventRail()
    rail._symphony_stream_handler = MagicMock()
    lease = OutputLease([RawChunk("answer", {"output": {"output": "formal result"}})])
    instance = CallbackFormalInstance(lease, rail)
    adapter = adapter_with(instance)
    adapter._stream_event_rail = rail
    instance.registered_rails = [rail]
    request, inputs = formal_request()

    chunks = [
        chunk
        async for chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        )
    ]

    assert [chunk.payload["event_type"] for chunk in chunks] == [
        "chat.tool_call",
        "chat.tool_update",
        "chat.tool_result",
        "chat.final",
    ]
    assert chunks[0].payload["tool_call"]["name"] == "read_file"
    assert chunks[0].payload["tool_call"]["arguments"] == {"path": "fixture/README.md"}
    assert chunks[0].payload["tool_call"]["tool_call_id"] == "tool-call-authoritative-1"
    assert chunks[0].payload["tool_call"]["display_name"]
    assert chunks[2].payload["tool_call_id"] == "tool-call-authoritative-1"
    assert chunks[2].payload["result"] == "{'content': 'fixture tool result'}"
    instance.inner_session.write_stream.assert_not_awaited()
    assert rail._formal_tool_event_captures == {}
    assert lease.closed_with == [False]


@pytest.mark.asyncio
async def test_formal_deep_seam_rejects_terminal_with_unfinished_tool_callback() -> None:
    rail = interface_deep.JiuSwarmStreamEventRail()
    rail._symphony_stream_handler = MagicMock()
    lease = OutputLease(
        [RawChunk("answer", {"output": {"output": "must not complete"}})]
    )
    instance = FormalInstance(lease)

    async def send_without_result(request) -> None:
        instance.sent.append(request)
        tool_call = SimpleNamespace(
            id="tool-call-pending-1",
            name="read_file",
            arguments={"path": "fixture/README.md"},
        )
        context = AgentCallbackContext(
            agent=MagicMock(),
            inputs=ToolCallInputs(
                tool_call=tool_call,
                tool_name=tool_call.name,
                tool_args=dict(tool_call.arguments),
            ),
            session=AsyncMock(),
            extra={rail._SID_KEY: request.inputs["conversation_id"]},
        )
        await rail.before_tool_call(context)

    instance.send_input = send_without_result
    adapter = adapter_with(instance)
    adapter._stream_event_rail = rail
    instance.registered_rails = [rail]
    request, inputs = formal_request()
    emitted = []

    with pytest.raises(RuntimeError, match="FORMAL_TOOL_EVENT_CAPTURE_INCOMPLETE"):
        async for chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        ):
            emitted.append(chunk.payload["event_type"])

    assert emitted == ["chat.tool_call", "chat.tool_update"]
    assert rail._formal_tool_event_captures == {}
    assert lease.closed_with == [True]


@pytest.mark.asyncio
async def test_formal_deep_seam_bridges_authoritative_tool_exception_once() -> None:
    rail = interface_deep.JiuSwarmStreamEventRail()
    rail._symphony_stream_handler = MagicMock()
    lease = OutputLease([RawChunk("answer", {"output": {"output": "formal recovery"}})])
    instance = FormalInstance(lease)

    async def send_with_tool_exception(request) -> None:
        instance.sent.append(request)
        tool_call = SimpleNamespace(
            id="tool-call-error-1",
            name="read_file",
            arguments={"path": "fixture/missing.md"},
        )
        context = AgentCallbackContext(
            agent=MagicMock(),
            inputs=ToolCallInputs(
                tool_call=tool_call,
                tool_name=tool_call.name,
                tool_args=dict(tool_call.arguments),
            ),
            session=AsyncMock(),
            extra={rail._SID_KEY: request.inputs["conversation_id"]},
            exception=RuntimeError("fixture read failed"),
        )
        await rail.before_tool_call(context)
        await rail.on_tool_exception(context)
        # The SDK may also run AFTER_TOOL_CALL for the same exception. It must
        # not duplicate the already captured authoritative result.
        await rail.after_tool_call(context)

    instance.send_input = send_with_tool_exception
    adapter = adapter_with(instance)
    adapter._stream_event_rail = rail
    instance.registered_rails = [rail]
    request, inputs = formal_request()

    chunks = [
        chunk
        async for chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        )
    ]

    assert [chunk.payload["event_type"] for chunk in chunks] == [
        "chat.tool_call",
        "chat.tool_update",
        "chat.tool_result",
        "chat.final",
    ]
    assert chunks[2].payload == {
        "event_type": "chat.tool_result",
        "tool_name": "read_file",
        "tool_call_id": "tool-call-error-1",
        "result": "fixture read failed",
        "success": False,
        "status": "error",
        "is_error": True,
    }
    assert rail._inflight_tool_calls == {}
    assert rail._formal_tool_event_captures == {}
    assert lease.closed_with == [False]


@pytest.mark.asyncio
async def test_formal_deep_seam_requires_tool_callback_authority_before_send() -> None:
    lease = OutputLease([RawChunk("answer", {"output": {"output": "must not run"}})])
    instance = FormalInstance(lease)
    adapter = adapter_with(instance)
    adapter._stream_event_rail = None
    request, inputs = formal_request()

    with pytest.raises(
        RuntimeError,
        match="FORMAL_TOOL_EVENT_AUTHORITY_UNAVAILABLE",
    ):
        async for _chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        ):
            pass

    assert instance.sent == []
    assert lease.closed_with == []


@pytest.mark.asyncio
async def test_formal_deep_seam_still_fails_closed_for_active_unsupported_event() -> None:
    lease = OutputLease([RawChunk("security.alert", {"reason": "blocked"})])
    adapter = adapter_with(FormalInstance(lease))
    request, inputs = formal_request()

    with pytest.raises(
        RuntimeError,
        match="FORMAL_EXECUTION_EVENT_UNSUPPORTED: 'security.alert'",
    ):
        async for _chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        ):
            pass

    assert lease.closed_with == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_chunk", "expected_event_type"),
    [
        (RawChunk("future_output", {"content": "must not leak"}), "future_output"),
        (RawChunk("future_output", {}), "future_output"),
        (RawChunk("security.alert", "malformed"), "security.alert"),
        (
            RawChunk(
                "controller_output",
                ControllerPayload(ControllerType("future_security_gate"), []),
            ),
            "controller_output",
        ),
        (RawChunk("controller_output", None), "controller_output"),
        ({"output": "untyped content must not leak"}, "<untyped>"),
    ],
)
async def test_formal_deep_seam_rejects_unknown_or_malformed_raw_events(
    raw_chunk: object,
    expected_event_type: str,
) -> None:
    lease = OutputLease([raw_chunk])
    adapter = adapter_with(FormalInstance(lease))
    request, inputs = formal_request()

    with pytest.raises(
        RuntimeError,
        match=f"FORMAL_EXECUTION_EVENT_UNSUPPORTED: {expected_event_type!r}",
    ):
        async for _chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        ):
            pass

    assert lease.closed_with == [True]


@pytest.mark.asyncio
async def test_formal_deep_seam_drops_agent_tracer_payload() -> None:
    lease = OutputLease(
        [
            RawChunk(
                "tracer_agent",
                {"event_type": "chat.tracer_agent", "content": "must not leak"},
            ),
            RawChunk("answer", {"output": {"output": "formal result"}}),
        ]
    )
    adapter = adapter_with(FormalInstance(lease))
    request, inputs = formal_request()

    chunks = [
        chunk
        async for chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        )
    ]

    assert [chunk.payload for chunk in chunks] == [
        {"event_type": "chat.final", "content": "formal result"}
    ]
    assert lease.closed_with == [False]


@pytest.mark.asyncio
async def test_formal_deep_seam_rejects_legacy_controls_before_agent_effect() -> None:
    lease = OutputLease([])
    instance = FormalInstance(lease)
    adapter = adapter_with(instance)
    request, inputs = formal_request(params_extra={"auto_harness": True})

    with pytest.raises(RuntimeError, match="FORMAL_EXECUTION_INPUT_REJECTED"):
        async for _chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        ):
            pass
    assert instance.sent == []
    assert lease.closed_with == []


@pytest.mark.asyncio
async def test_formal_output_cleanup_retains_ownership_until_settled(
    monkeypatch,
) -> None:
    close_release = asyncio.Event()
    lease = OutputLease(
        [RawChunk("answer", {"output": {"output": "formal result"}})],
        close_release=close_release,
    )
    instance = FormalInstance(lease)
    adapter = adapter_with(instance)
    request, inputs = formal_request()

    async def forbidden_slice(*_args, **_kwargs):
        raise AssertionError("formal cleanup must not start a second deadline slice")

    monkeypatch.setattr(interface_deep.asyncio, "wait_for", forbidden_slice)

    async def consume():
        return [
            chunk
            async for chunk in adapter.process_formal_live_voice_stream_impl(
                request, inputs
            )
        ]

    consumer = asyncio.create_task(consume())
    await lease.close_started.wait()
    await asyncio.sleep(0.03)
    assert consumer.done() is False
    close_release.set()
    chunks = await consumer
    assert [chunk.payload for chunk in chunks] == [
        {"event_type": "chat.final", "content": "formal result"}
    ]
    assert lease.closed_with == [False]


@pytest.mark.asyncio
async def test_formal_consumer_close_after_yield_aborts_active_round() -> None:
    lease = OutputLease(
        [
            RawChunk("delta", {"content": "partial"}),
            RawChunk("answer", {"output": {"output": "unreached final"}}),
        ]
    )
    instance = FormalInstance(lease)
    adapter = adapter_with(instance)
    request, inputs = formal_request()
    stream = adapter.process_formal_live_voice_stream_impl(request, inputs)

    first = await anext(stream)
    assert first.payload == {"event_type": "chat.delta", "content": "partial"}
    await stream.aclose()

    assert lease.closed_with == [True]


@pytest.mark.asyncio
async def test_formal_root_retains_dedicated_session_cleanup(monkeypatch) -> None:
    lease = OutputLease([RawChunk("answer", {"output": {"output": "done"}})])
    child = adapter_with(FormalInstance(lease))
    root = object.__new__(JiuWenSwarmDeepAdapter)
    root._is_session_scoped_adapter = False
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()

    async def get_child(_session_id):
        return child

    async def cleanup_child(_session_id):
        cleanup_started.set()
        await cleanup_release.wait()
        return True

    monkeypatch.setattr(root, "_get_or_create_session_adapter", get_child)
    monkeypatch.setattr(root, "cleanup_session_adapter", cleanup_child)

    async def forbidden_slice(*_args, **_kwargs):
        raise AssertionError("session cleanup must use the outer total deadline")

    monkeypatch.setattr(interface_deep.asyncio, "wait_for", forbidden_slice)
    request, inputs = formal_request()

    async def consume():
        return [
            chunk
            async for chunk in root.process_formal_live_voice_stream_impl(
                request, inputs
            )
        ]

    consumer = asyncio.create_task(consume())
    await cleanup_started.wait()
    await asyncio.sleep(0.03)
    assert consumer.done() is False
    cleanup_release.set()
    chunks = await consumer
    assert [chunk.payload for chunk in chunks] == [
        {"event_type": "chat.final", "content": "done"}
    ]


@pytest.mark.asyncio
async def test_real_send_file_tool_cannot_write_implicit_formal_history(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    deliverable = tmp_path / "formal-result.txt"
    deliverable.write_text("result", encoding="utf-8")
    session_id = "lv-formal-tool-history-guard"
    toolkit = SendFileToolkit(
        request_id="formal-tool-request",
        session_id=session_id,
        channel_id="web",
    )
    server = MagicMock()
    server.send_push = AsyncMock()
    download = {
        "size": deliverable.stat().st_size,
        "mime_type": "text/plain",
        "download_url": "/formal-result.txt",
        "download_token": "opaque-test-token",
    }
    session_history.register_formal_no_history_session(session_id)
    try:
        with (
            patch(
                "jiuwenswarm.server.agent_ws_server.AgentWebSocketServer.get_instance",
                return_value=server,
            ),
            patch(
                "jiuwenswarm.agents.harness.common.tools.web_file_download."
                "build_file_download_info",
                return_value=download,
            ),
        ):
            await toolkit.send_file(str(deliverable))
    finally:
        session_history.unregister_formal_no_history_session(session_id)
        clear_sent_files_for_session(session_id)

    server.send_push.assert_awaited_once()
    assert session_history.load_history_records(session_id) == []
    assert not (tmp_path / session_id).exists()


@pytest.mark.asyncio
async def test_failed_agent_cleanup_retains_no_history_guard(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    lease = OutputLease(
        [RawChunk("answer", {"output": {"output": "ambiguous"}})],
        close_error=OSError("cleanup failed"),
    )
    adapter = adapter_with(FormalInstance(lease))
    request, inputs = formal_request()

    with pytest.raises(OSError, match="cleanup failed"):
        async for _chunk in adapter.process_formal_live_voice_stream_impl(
            request, inputs
        ):
            pass
    try:
        session_history.append_history_record(
            session_id=request.session_id,
            request_id=request.request_id,
            channel_id=request.channel_id,
            role="assistant",
            content="late unsafe write",
            timestamp=1.0,
        )
        assert session_history.load_history_records(request.session_id) == []
        assert not (tmp_path / request.session_id).exists()
    finally:
        session_history.unregister_formal_no_history_session(request.session_id)
