# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def close(self, *, abort_active_round: bool) -> None:
        self.closed_with.append(abort_active_round)
        if self.close_release is not None:
            await self.close_release.wait()
        if self.close_error is not None:
            raise self.close_error


class FormalInstance:
    def __init__(self, lease: OutputLease) -> None:
        self.lease = lease
        self.sent = []

    async def attach_output(self):
        return self.lease

    async def send_input(self, request) -> None:
        self.sent.append(request)


def formal_request(*, params_extra: dict | None = None) -> tuple[AgentRequest, dict]:
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
    seen = []

    async def update(config) -> None:
        seen.append(config)

    adapter._update_runtime_config = update
    adapter.formal_runtime_configs = seen
    return adapter


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
async def test_formal_output_cleanup_retains_ownership_across_bounded_waits(
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
    monkeypatch.setattr(interface_deep, "_FORMAL_OUTPUT_CLOSE_TIMEOUT_SECONDS", 0.01)

    async def consume():
        return [
            chunk
            async for chunk in adapter.process_formal_live_voice_stream_impl(
                request, inputs
            )
        ]

    consumer = asyncio.create_task(consume())
    while not lease.closed_with:
        await asyncio.sleep(0)
    await asyncio.sleep(0.03)
    assert consumer.done() is False
    close_release.set()
    chunks = await asyncio.wait_for(consumer, timeout=1)
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
    monkeypatch.setattr(interface_deep, "_FORMAL_OUTPUT_CLOSE_TIMEOUT_SECONDS", 0.01)
    request, inputs = formal_request()

    async def consume():
        return [
            chunk
            async for chunk in root.process_formal_live_voice_stream_impl(
                request, inputs
            )
        ]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)
    await asyncio.sleep(0.03)
    assert consumer.done() is False
    cleanup_release.set()
    chunks = await asyncio.wait_for(consumer, timeout=1)
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
