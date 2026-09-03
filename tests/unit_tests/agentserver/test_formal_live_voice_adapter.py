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
        self.registered_rails = []
        from openjiuwen.harness.prompts import SystemPromptBuilder
        self.system_prompt_builder = SystemPromptBuilder(language="en")
        self.observed_prompt = None

    async def attach_output(self):
        return self.lease

    async def send_input(self, request) -> None:
        self.observed_prompt = self.system_prompt_builder.build()
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
    from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
        FORMAL_VOICE_PRESENTATION_INSTRUCTIONS,
    )
    assert FORMAL_VOICE_PRESENTATION_INSTRUCTIONS in instance.observed_prompt
    assert FORMAL_VOICE_PRESENTATION_INSTRUCTIONS not in instance.system_prompt_builder.build()
    assert "/goal must remain plain committed text" not in instance.observed_prompt


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

    assert not adapter._instance.system_prompt_builder.has_section("formal_live_voice_presentation")


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
    assert instance.observed_prompt is None
    assert not instance.system_prompt_builder.has_section("formal_live_voice_presentation")


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
    assert instance.system_prompt_builder.has_section("formal_live_voice_presentation")
    close_release.set()
    chunks = await asyncio.wait_for(consumer, timeout=1)
    assert [chunk.payload for chunk in chunks] == [
        {"event_type": "chat.final", "content": "formal result"}
    ]
    assert lease.closed_with == [False]
    assert not instance.system_prompt_builder.has_section("formal_live_voice_presentation")


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
    assert not instance.system_prompt_builder.has_section("formal_live_voice_presentation")


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


@pytest.mark.asyncio
@pytest.mark.parametrize("tools_allowed", [False, True])
async def test_formal_voice_model_options_are_isolated_and_restored(monkeypatch, tools_allowed):
    from copy import deepcopy

    request_config = interface_deep.ModelRequestConfig(
        model="deepseek-v4-flash", extra_body={"thinking": {"type": "enabled"}, "provider_option": "keep"},
    )
    client_config = interface_deep.ModelClientConfig(
        client_provider="DeepSeek", api_base="https://api.deepseek.com", api_key="test-only",
    )
    original = SimpleNamespace(model_config=request_config, model_client_config=client_config)
    before = deepcopy(request_config.model_dump())
    applied = []
    instance = FormalInstance(OutputLease([RawChunk("answer", {"output": {"output": "Completed."}})]))
    from openjiuwen.harness.prompts import PromptSection
    original_output = PromptSection("output", {"en": "Original written deliverable instructions"}, priority=65)
    instance.system_prompt_builder.add_section(original_output)
    instance._react_agent = SimpleNamespace(set_llm=applied.append, _config=SimpleNamespace())
    adapter = adapter_with(instance)
    adapter._model = original
    monkeypatch.setattr(interface_deep, "Model", lambda **values: SimpleNamespace(**values))
    request, inputs = formal_request(tools_allowed=tools_allowed)
    chunks = [chunk async for chunk in adapter.process_formal_live_voice_stream_impl(request, inputs)]
    assert chunks[-1].payload["content"] == "Completed."
    assert "Original written deliverable instructions" not in instance.observed_prompt
    assert "Spoken response" in instance.observed_prompt
    assert instance.system_prompt_builder.get_section("output") is original_output
    assert original.model_config.model_dump() == before and adapter._model is original
    assert len(applied) == 2 and applied[-1] is original
    assert applied[0] is not original
    assert applied[0].model_config.extra_body == {"thinking": {"type": "disabled"}, "provider_option": "keep"}
    assert applied[0].model_client_config is client_config


@pytest.mark.asyncio
async def test_formal_facade_passes_committed_envelope_without_chat_clock_wrapper():
    from datetime import UTC, datetime
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef, TurnCommit
    from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import FormalAgentExecution, FormalContextSnapshot
    from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm

    scope = ScopeRef("subject", "project", "session", Assurance.AUTHENTICATED)
    commit = TurnCommit.from_dict({
        "contract_version": "live-voice.contract.v2", "commit_id": "commit", "turn_id": "turn",
        "interaction_id": "interaction", "text": "Analyze the project using its scenario clock.",
        "hypothesis_provenance": {"provider": "test"}, "scope": scope.to_dict(), "context_refs": [],
        "committed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    })
    execution = FormalAgentExecution("request", "web", "lv-formal-envelope", commit, FormalContextSnapshot(scope))
    observed = []

    async def stream(request, inputs):
        observed.append((request, inputs))
        if False:
            yield None

    facade = JiuWenSwarm()
    facade._adapter = SimpleNamespace(process_formal_live_voice_stream_impl=stream)
    facade._ensure_adapter = lambda **kwargs: facade._adapter
    facade._build_inputs = lambda request: ({
        "conversation_id": request.session_id, "enable_memory": False, "skip_a2ui": True,
        "query": "ordinary chat wrapper with machine timestamp",
    }, None, None)
    assert [chunk async for chunk in facade.process_formal_live_voice_stream(execution)] == []
    request, inputs = observed[0]
    assert inputs["query"] == execution.prompt_content()
    assert request.metadata["formal_live_voice"] is True
    assert inputs["enable_memory"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["cn", "en"])
async def test_response_rail_preserves_formal_spoken_output_then_resumes_ordinary_rules(monkeypatch, language):
    from openjiuwen.harness.prompts import PromptSection, SystemPromptBuilder
    from jiuwenswarm.agents.harness.common.rails.response_prompt_rail import ResponsePromptRail

    builder = SystemPromptBuilder(language=language)
    voice = PromptSection("output", {language: "spoken output owned by validated adapter"}, priority=65)
    builder.add_section(voice)
    builder.add_section(PromptSection("formal_live_voice_presentation", {language: "formal policy"}))
    rail = ResponsePromptRail()
    rail.system_prompt_builder = builder
    monkeypatch.setattr(rail, "_sync_a2ui_prompt_section", lambda *args, **kwargs: None)
    ctx = SimpleNamespace(inputs={}, extra={})
    for _ in range(2):
        await rail.before_model_call(ctx)
        assert builder.get_section("output") is voice
    builder.remove_section("formal_live_voice_presentation")
    await rail.before_model_call(ctx)
    assert builder.get_section("output") is not voice
    assert "spoken output owned by validated adapter" not in builder.build()
