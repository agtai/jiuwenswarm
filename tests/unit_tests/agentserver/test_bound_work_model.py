# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Bound model entry after the real SDK's post-rail context/KV awaits."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from openjiuwen.core.context_engine.base import ContextWindow, ContextWindowChange
from openjiuwen.core.foundation.kv_cache import KVCacheAffinityConfig
from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
from openjiuwen.core.foundation.llm.schema.message import AssistantMessage, UserMessage
from openjiuwen.core.foundation.llm.schema.message_chunk import AssistantMessageChunk
from openjiuwen.core.foundation.tool import ToolInfo
from openjiuwen.core.runner import Runner
from openjiuwen.core.runner.callback import AsyncCallbackFramework
from openjiuwen.core.runner.callback.events import LLMCallEvents
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentCallbackEvent, ModelCallInputs
from openjiuwen.core.single_agent.schema.agent_card import AgentCard

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.agent_adapter.work_model import BoundAgentModel
from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy, PreparedAgentWork


def bound(model, work, *, before_call=None):
    return BoundAgentModel(model, work, before_call=before_call)


class RecordingClient:
    def __init__(self):
        self.calls = []
        self.chunks = [AssistantMessageChunk(content="ok", finish_reason="stop")]
        self.error = None
        self.kv_entered = asyncio.Event()
        self.kv_release = asyncio.Event()
        self.kv_wait = False
        self.stream_wait = False
        self.stream_entered = asyncio.Event()
        self.stream_closed = False

    async def invoke(self, **kwargs):
        self.calls.append(("invoke", kwargs))
        if self.error:
            raise self.error
        return AssistantMessage(content="ok")

    async def stream(self, **kwargs):
        self.calls.append(("stream", kwargs))
        try:
            for chunk in self.chunks:
                yield chunk
            if self.stream_wait:
                self.stream_entered.set()
                await asyncio.Event().wait()
            if self.error:
                raise self.error
        finally:
            self.stream_closed = True

    async def release(self, **_kwargs):
        if self.kv_wait:
            self.kv_entered.set()
            await self.kv_release.wait()
        return True

    def supports_kv_cache_affinity(self):
        return True

    def build_kv_cache_affinity_invoke_kwargs(self, **kwargs):
        return {"session_id": kwargs["session_id"]}


@pytest.fixture
def configured_model(monkeypatch):
    # Exercise the real SDK Model methods with one deterministic local client.
    # Runner never starts; callbacks and all mutable state are test-local.
    monkeypatch.setattr(Runner, "callback_framework", AsyncCallbackFramework())
    client = RecordingClient()
    creates = []

    def create_client(**kwargs):
        creates.append(kwargs)
        return client

    monkeypatch.setattr("openjiuwen.core.foundation.llm.model.create_model_client", create_client)
    model = Model(
        model_client_config=ModelClientConfig(client_provider="OpenAI", api_key="test-only",
                                              api_base="http://127.0.0.1:1",
                                              stream_first_chunk_timeout=None, stream_idle_timeout=None),
        model_config=ModelRequestConfig(model="selected-model"),
    )
    return model, client, creates


def prepared(*, policy="read_only"):
    state = {"live": True, "allowed": True, "checks": [], "runtime_applies": 0}

    def require_live():
        if not state["live"]:
            raise ValueError("AGENT_WORK_OWNER_RELEASED")

    async def check():
        state["checks"].append("policy")
        if not state["allowed"]:
            raise ValueError("AGENT_WORK_REVOKED")

    def apply_runtime(_ctx):
        state["runtime_applies"] += 1

    work = PreparedAgentWork(
        request=AgentRequest(request_id="request", channel_id="web", session_id="conversation"),
        policy=AgentExecutionPolicy(origin="text" if policy == "configured" else "native",
                                    tool_policy=policy, model_identity="selected-model",
                                    model_config_version="v1", before_effect=check),
        sdk_agent=object(), sdk_session_id="sdk-session", require_live=require_live,
        apply_runtime=apply_runtime,
    )
    return work, state


class WindowContext:
    def __init__(self, *, stage=None, tools=()):
        self.stage = stage
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.window = ContextWindow(context_messages=[UserMessage(content="hello")], tools=list(tools))

    def session_id(self):
        return "sdk-session"

    async def get_context_window(self, **_kwargs):
        if self.stage == "context":
            self.entered.set()
            await self.release.wait()
        return self.window

    def detect_context_window_change(self, _window):
        if self.stage == "kv":
            return ContextWindowChange(old_messages=[UserMessage(content="old")], msg_start=0, msg_end=1)
        return None


async def react_call(model, window_context, *, streaming=False):
    agent = ReActAgent(card=AgentCard(id=f"bound-model-test-{uuid4().hex}"))
    config = ReActAgentConfig()
    config.model_name = "selected-model"
    config.llm_return_token_ids = True
    config.kv_cache_affinity_config = KVCacheAffinityConfig(
        enable_kv_cache_release=window_context.stage == "kv"
    )
    agent.configure(config)
    agent.set_llm(model)
    before_rails = []

    async def observe_before(ctx):
        before_rails.append(ctx.inputs.tools)

    await agent.agent_callback_manager.register_callback(AgentCallbackEvent.BEFORE_MODEL_CALL, observe_before)
    frames = []

    async def write_stream(frame):
        frames.append(frame)

    ctx = AgentCallbackContext(
        agent=agent, context=window_context,
        session=SimpleNamespace(get_session_id=lambda: "sdk-session", write_stream=write_stream),
        inputs=ModelCallInputs(tools=[ToolInfo(name="read_file")]), extra={"_streaming": streaming},
    )
    try:
        result = await agent._railed_model_call(ctx)
        assert len(before_rails) == 1
        return result, frames
    finally:
        await agent.agent_callback_manager.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["context", "kv"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_real_react_post_rail_wait_revocation_prevents_underlying_model_entry(configured_model, stage, streaming):
    model, client, _creates = configured_model
    work, state = prepared()
    window = WindowContext(stage=stage)
    client.kv_wait = stage == "kv"
    pending = asyncio.create_task(react_call(bound(model, work), window, streaming=streaming))
    entered = window.entered if stage == "context" else client.kv_entered
    release = window.release if stage == "context" else client.kv_release
    await asyncio.wait_for(entered.wait(), 2)
    state["allowed"] = False
    release.set()
    with pytest.raises(ValueError, match="AGENT_WORK_REVOKED"):
        await pending
    assert client.calls == [] and state["runtime_applies"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["read_only", "none", "configured"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_real_react_final_window_tools_are_filtered_at_model_entry(configured_model, policy, streaming):
    model, client, creates = configured_model
    work, state = prepared(policy=policy)
    tools = [ToolInfo(name="read_file"), ToolInfo(name="write_file"), ToolInfo(name="task_tool")]
    window = WindowContext(tools=tools)
    result, frames = await react_call(bound(model, work), window, streaming=streaming)
    assert result.content == "ok"
    expected = tools if policy == "configured" else tools[:1] if policy == "read_only" else []
    assert (client.calls[0][1]["tools"] or []) == expected
    assert window.window.tools == tools
    assert len(creates) == 1 and state["runtime_applies"] == 0 and state["checks"] == ["policy", "policy"]
    assert client.calls[0][1]["return_token_ids"] is True
    assert bool(frames) is streaming


@pytest.mark.asyncio
async def test_async_catalog_check_then_final_work_guard_rejects_revocation(configured_model):
    model, client, _creates = configured_model
    work, state = prepared()
    entered, release = asyncio.Event(), asyncio.Event()

    async def before_call():
        state["checks"].append("catalog")
        entered.set()
        await release.wait()

    pending = asyncio.create_task(bound(model, work, before_call=before_call).invoke(messages=[]))
    await asyncio.wait_for(entered.wait(), 2)
    state["live"] = False
    release.set()
    with pytest.raises(ValueError, match="AGENT_WORK_OWNER_RELEASED"):
        await pending
    assert client.calls == [] and state["checks"] == ["catalog"]


@pytest.mark.asyncio
async def test_sync_catalog_and_policy_at_entry_and_final_client_preserve_original_options(configured_model):
    model, client, creates = configured_model
    work, state = prepared(policy="configured")
    tools = [{"type": "function", "function": {"name": "write_file", "parameters": {}}},
             {"type": "web_search_preview", "search_context_size": "low"}]
    options = {"model": "selected-model", "tools": tools, "temperature": 0.2,
               "max_tokens": 99, "stop": "END", "response_format": {"type": "json_object"},
               "metadata": {"sentinel": "original"}, "timeout": 17}
    proxy = bound(model, work, before_call=lambda: state["checks"].append("catalog"))
    result = await proxy.invoke([UserMessage(content="hello")], **options)
    assert result.content == "ok"
    assert state["checks"] == ["catalog", "policy", "catalog", "policy"] and len(creates) == 1
    for name, value in options.items():
        assert client.calls[0][1][name] == value
    assert client.calls[0][1]["tools"] is tools
    assert isinstance(proxy, Model)
    assert proxy.model_config is model.model_config and proxy.model_client_config is model.model_client_config
    assert proxy.supports_kv_cache_release() == model.supports_kv_cache_release()
    assert proxy.supports_kv_cache_affinity() == model.supports_kv_cache_affinity()
    assert proxy.build_kv_cache_affinity_invoke_kwargs(session_id="original") == {"session_id": "original"}
    with pytest.raises(AttributeError):
        proxy.model_config = ModelRequestConfig(model="replacement")
    assert model.model_config.model_name == "selected-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_native_canonical_dict_tools_filter_without_mutation(configured_model, streaming):
    model, client, _creates = configured_model
    work, _state = prepared()
    tools = [{"type": "function", "function": {"name": "read_file", "strict": True}},
             {"type": "function", "function": {"name": "write_file"}}, {"type": "web_search_preview"}]
    proxy = bound(model, work)
    if streaming:
        output = [chunk async for chunk in proxy.stream(messages=[], tools=tools)]
        assert output[0] is client.chunks[0]
    else:
        await proxy.invoke(messages=[], tools=tools)
    assert client.calls[0][1]["tools"] == tools[:1] and len(tools) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("policy", ["configured", "read_only", "none"])
async def test_responses_flat_function_tools_preserve_shape_and_policy(configured_model, streaming, policy):
    from jiuwenswarm.common.openai_responses_client import _tools

    model, client, _creates = configured_model
    work, _state = prepared(policy=policy)
    tools = [{"type": "function", "name": "read_file", "parameters": {"type": "object"}, "strict": True},
             {"type": "function", "name": "write_file", "parameters": {}}]
    assert _tools(tools)[0]["name"] == "read_file"
    proxy = bound(model, work)
    if streaming:
        assert [chunk async for chunk in proxy.stream(messages=[], tools=tools)] == client.chunks
    else:
        await proxy.invoke(messages=[], tools=tools)
    expected = tools if policy == "configured" else tools[:1] if policy == "read_only" else []
    assert client.calls[0][1]["tools"] == expected
    assert len(tools) == 2 and "function" not in tools[0]
    if policy == "configured":
        assert client.calls[0][1]["tools"] is tools


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [
    {"type": "function", "name": "read_file", "parameters": []},
    {"type": "function", "name": "read_file", "function": None},
    {"type": "function", "name": "read_file", "function": {"name": "write_file"}},
    {"type": "function", "parameters": {}, "function": {"name": "read_file", "parameters": {"type": "object"}}},
    {"type": "function", "strict": False, "function": {"name": "read_file", "strict": True}},
])
async def test_flat_and_nested_ambiguous_or_invalid_tools_have_zero_client_effects(configured_model, tool):
    model, client, _creates = configured_model
    work, _state = prepared(policy="configured")
    with pytest.raises(ValueError, match="AGENT_WORK_MODEL_TOOLS_INVALID"):
        await bound(model, work).invoke(messages=[], tools=[tool])
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [None, "fallback", " selected-model "])
async def test_mismatched_model_keyword_never_falls_back(configured_model, name):
    model, client, _creates = configured_model
    work, _state = prepared()
    with pytest.raises(ValueError, match="AGENT_WORK_MODEL_MISMATCH"):
        await bound(model, work).invoke(messages=[], model=name)
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", ["read_file", (), {}, [object()], [{}],
                                    [{"type": "function", "function": {}}],
                                    [{"type": "function", "name": "read_file",
                                      "function": {"name": "write_file"}}],
                                    [ToolInfo(name="read_file"), {"type": "web_search_preview"}]])
async def test_invalid_actual_tool_shapes_fail_before_model(configured_model, tools):
    model, client, _creates = configured_model
    work, _state = prepared()
    with pytest.raises(ValueError, match="AGENT_WORK_MODEL_TOOLS_INVALID"):
        await bound(model, work).invoke(messages=[], tools=tools)
    assert client.calls == []


@pytest.mark.asyncio
async def test_stream_error_and_cancellation_propagate_with_original_chunks(configured_model):
    model, client, _creates = configured_model
    work, _state = prepared()
    proxy = bound(model, work)
    failure = RuntimeError("original stream error")
    client.error = failure
    output = []
    with pytest.raises(RuntimeError) as caught:
        async for chunk in proxy.stream(messages=[], tools=None):
            output.append(chunk)
    assert caught.value is failure and output[0] is client.chunks[0]
    assert client.stream_closed

    client.error, client.stream_wait, client.stream_closed = None, True, False
    iterator = proxy.stream(messages=[], tools=None)
    assert await anext(iterator) is client.chunks[0]
    pending = asyncio.create_task(anext(iterator))
    await asyncio.wait_for(client.stream_entered.wait(), 2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert client.stream_closed
    await iterator.aclose()


async def inference(proxy, *, streaming=False, **kwargs):
    if streaming:
        return [chunk async for chunk in proxy.stream(messages=[], **kwargs)]
    return await proxy.invoke(messages=[], **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("revocation", ["allowed", "live"])
async def test_sdk_input_hook_wait_rechecks_authority_before_original_client(configured_model, streaming, revocation):
    model, client, _creates = configured_model
    if streaming:
        # Exercise Model's real wait_for child task as well as direct invoke.
        model.model_client_config.stream_first_chunk_timeout = 2
    work, state = prepared()
    entered, release = asyncio.Event(), asyncio.Event()

    async def hook(**_kwargs):
        entered.set()
        await release.wait()

    event = LLMCallEvents.LLM_STREAM_INPUT if streaming else LLMCallEvents.LLM_INVOKE_INPUT
    await Runner.callback_framework.register(event, hook)
    pending = asyncio.create_task(inference(bound(model, work), streaming=streaming))
    await asyncio.wait_for(entered.wait(), 2)
    state[revocation] = False
    release.set()
    outcome = await asyncio.gather(pending, return_exceptions=True)
    assert client.calls == [], outcome
    assert isinstance(outcome[0], ValueError)
    assert str(outcome[0]) == ("AGENT_WORK_REVOKED" if revocation == "allowed" else "AGENT_WORK_OWNER_RELEASED")


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("policy", ["configured", "read_only", "none"])
async def test_sdk_input_transform_tools_obey_final_work_policy(configured_model, streaming, policy):
    model, client, _creates = configured_model
    work, _state = prepared(policy=policy)
    transformed = [{"type": "function", "name": "read_file"}, {"type": "function", "name": "write_file"}]

    async def hook(*args, **kwargs):
        return args, {**kwargs, "tools": transformed}

    event = LLMCallEvents.LLM_STREAM_INPUT if streaming else LLMCallEvents.LLM_INVOKE_INPUT
    await Runner.callback_framework.register(event, hook, callback_type="transform")
    await inference(bound(model, work), streaming=streaming, tools=[])
    expected = transformed if policy == "configured" else transformed[:1] if policy == "read_only" else []
    assert client.calls[0][1]["tools"] == expected
    assert len(transformed) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_sdk_input_transform_cannot_change_bound_model(configured_model, streaming):
    model, client, _creates = configured_model
    work, _state = prepared()

    async def hook(*args, **kwargs):
        return args, {**kwargs, "model": "other-model"}

    event = LLMCallEvents.LLM_STREAM_INPUT if streaming else LLMCallEvents.LLM_INVOKE_INPUT
    await Runner.callback_framework.register(event, hook, callback_type="transform")
    outcome = await asyncio.gather(inference(bound(model, work), streaming=streaming), return_exceptions=True)
    assert client.calls == [], outcome
    assert isinstance(outcome[0], ValueError) and str(outcome[0]) == "AGENT_WORK_MODEL_MISMATCH"


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_two_works_share_original_model_without_guard_or_client_mutation(configured_model, streaming):
    model, client, creates = configured_model
    original_invoke, original_stream = client.invoke, client.stream
    revoked_work, revoked = prepared(policy="none")
    allowed_work, allowed = prepared(policy="configured")
    entered, release = asyncio.Event(), asyncio.Event()
    waiting = 0

    async def hook(**_kwargs):
        nonlocal waiting
        waiting += 1
        if waiting == 2:
            entered.set()
        await release.wait()

    event = LLMCallEvents.LLM_STREAM_INPUT if streaming else LLMCallEvents.LLM_INVOKE_INPUT
    await Runner.callback_framework.register(event, hook)
    tools = [ToolInfo(name="write_file")]
    rejected_call = asyncio.create_task(inference(bound(model, revoked_work), streaming=streaming, tools=tools))
    allowed_call = asyncio.create_task(inference(bound(model, allowed_work), streaming=streaming, tools=tools))
    await asyncio.wait_for(entered.wait(), 2)
    revoked["allowed"] = False
    release.set()
    outcomes = await asyncio.gather(rejected_call, allowed_call, return_exceptions=True)
    assert isinstance(outcomes[0], ValueError) and not isinstance(outcomes[1], BaseException)
    assert len(client.calls) == 1 and client.calls[0][1]["tools"] == tools
    assert allowed["checks"] == ["policy", "policy"]
    assert client.invoke is original_invoke and client.stream is original_stream and len(creates) == 1


@pytest.mark.asyncio
async def test_stream_yield_does_not_leak_guard_into_caller(configured_model):
    model, client, _creates = configured_model
    work, state = prepared()
    stream = bound(model, work).stream(messages=[])
    assert await anext(stream) is client.chunks[0]
    state["allowed"] = False
    # A caller outside this work can still use the retained original Model.
    assert (await model.invoke(messages=[])).content == "ok"
    await stream.aclose()
    assert len(client.calls) == 2
