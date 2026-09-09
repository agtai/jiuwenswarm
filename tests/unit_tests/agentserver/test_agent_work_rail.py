# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Actual SDK callback ordering for retained host work authority."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from openjiuwen.core.context_engine import ContextEngine
from openjiuwen.core.controller.config import ControllerConfig
from openjiuwen.core.controller.modules.event_queue import EventQueue
from openjiuwen.core.controller.modules.task_manager import TaskManager
from openjiuwen.core.controller.modules.task_scheduler import TaskExecutorDependencies
from openjiuwen.core.controller.schema.task import Task, TaskStatus
from openjiuwen.core.foundation.kv_cache import KVCacheAffinityConfig
from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
from openjiuwen.core.foundation.llm.schema.message import AssistantMessage
from openjiuwen.core.foundation.llm.schema.message_chunk import AssistantMessageChunk
from openjiuwen.core.foundation.tool import ToolInfo
from openjiuwen.core.runner import Runner
from openjiuwen.core.runner.callback import AbortError, AsyncCallbackFramework
from openjiuwen.core.session.agent import Session
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig
from openjiuwen.core.single_agent.rail.base import (
    AgentCallbackContext,
    AgentCallbackEvent,
    InvokeInputs,
    ModelCallInputs,
    RunContext,
    TaskIterationInputs,
    ToolCallInputs,
)
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from openjiuwen.harness.deep_agent import DeepAgent
from openjiuwen.harness.schema.interaction import RoundWorkItem
from openjiuwen.harness.task_loop.task_loop_event_executor import DEEP_TASK_TYPE, TaskLoopEventExecutor
from openjiuwen.harness.rails.security.tool_security_rail import PermissionInterruptRail
from openjiuwen.harness.security.host import ToolPermissionHost

from jiuwenswarm.agents.harness.common.rails.agent_work_rail import AgentWorkRail
from jiuwenswarm.agents.harness.common.rails.permissions.owner_scopes import (
    PermissionContext,
    TOOL_PERMISSION_CONTEXT,
)
from jiuwenswarm.agents.harness.common.rails.permissions.tool_permission_context import (
    TOOL_PERMISSION_CHANNEL_ID,
)
from jiuwenswarm.agents.harness.common.rails.stream_event_rail import (
    JiuSwarmStreamEventRail,
    NATIVE_READ_ONLY_TOOL_NAMES,
)
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy, PreparedAgentWork


@contextmanager
def authority_rejected():
    # SDK trigger() unwraps AbortError.cause only after stopping the chain.
    with pytest.raises(ValueError) as caught:
        yield
    abort = caught.value.__context__
    assert isinstance(abort, AbortError) and abort.reason == "AGENT_WORK_AUTHORITY_REJECTED"


def prepared(*, origin="native", tool_policy="read_only", mode="agent"):
    state = {"live": True, "allowed": True, "checks": 0, "applies": 0, "model": None,
             "runtime_permissions": []}
    sdk_agent = object()

    def require_live():
        if not state["live"]:
            raise ValueError("retained owner released")

    def check_policy():
        state["checks"] += 1
        if not state["allowed"]:
            raise ValueError("selection revoked")

    def apply_runtime(_ctx):
        state["applies"] += 1
        state["model"] = f"{origin}-model"
        permission = TOOL_PERMISSION_CONTEXT.get()
        state["runtime_permissions"].append(
            (permission.principal_user_id if permission else None, TOOL_PERMISSION_CHANNEL_ID.get())
        )

    work = PreparedAgentWork(
        request=AgentRequest(request_id=f"{origin}-request", channel_id=f"{origin}-channel",
                             session_id="conversation", params={"mode": mode}),
        policy=AgentExecutionPolicy(origin=origin, tool_policy=tool_policy,
                                    model_identity=f"{origin}-model", model_config_version="v1",
                                    before_effect=check_policy),
        sdk_agent=sdk_agent, sdk_session_id="sdk-session", require_live=require_live,
        apply_runtime=apply_runtime,
        permission_context=(PermissionContext(principal_user_id="native-owner")
                            if origin == "native" else None),
    )
    return work, state


def context(work=None, *, kind="model", tools=None):
    inputs = (ModelCallInputs(tools=tools or []) if kind == "model" else
              ToolCallInputs(tool_name="read_file", tool_args={},
                             tool_call=SimpleNamespace(id="call-1", name="read_file", arguments={})))
    ctx = AgentCallbackContext(agent=None, inputs=inputs, session=Session(session_id="sdk-session"),
                               extra={JiuSwarmStreamEventRail._SID_KEY: "sdk-session",
                                      "run_context": work.run_context() if work else None})

    async def list_tools():
        return list(ctx.inputs.tools or [])

    ctx.agent = SimpleNamespace(ability_manager=SimpleNamespace(list_tool_info=list_tools))
    return ctx


def bind(stream, work):
    failures = []

    def resolve(ctx):
        work.require_context(sdk_agent=work.sdk_agent, session_id="sdk-session",
                             run_context=ctx.extra.get("run_context"))
        return work

    async def failed(_ctx, error):
        failures.append(error)

    stream.execution_work_resolver = resolve
    stream.execution_work_failure = failed
    return failures


async def chain(stream, *, kind="model", intermediate=()):
    framework = AsyncCallbackFramework()
    hook_name = f"before_{kind}_call"
    await framework.register("effect", getattr(stream, hook_name), priority=stream.priority)
    for priority, callback in intermediate:
        await framework.register("effect", callback, priority=priority)
    priorities = [stream.priority, *(priority for priority, _callback in intermediate)]
    for phase, priority in (("prepare", max(priorities) + 1), ("last", min(priorities) - 1)):
        work_rail = AgentWorkRail(stream, phase=phase, priority=priority)
        await framework.register("effect", getattr(work_rail, hook_name), priority=work_rail.priority)
    effects = []

    @framework.emit_before("effect")
    async def invoke(ctx):
        effects.append(ctx.inputs)

    return invoke, effects


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["model", "tool"])
async def test_sdk_ordinary_callback_error_does_not_stop_effect(kind):
    async def ordinary_error(_ctx):
        raise ValueError("SDK intentionally ignores an ordinary callback error")

    invoke, effects = await chain(JiuSwarmStreamEventRail(), kind=kind,
                                  intermediate=[(90, ordinary_error)])
    await invoke(context(kind=kind))
    assert len(effects) == 1


@pytest.mark.asyncio
async def test_prepare_applies_model_and_task_permissions_before_other_rails_once():
    work, state = prepared(mode="code")
    stream = JiuSwarmStreamEventRail()
    bind(stream, work)
    TOOL_PERMISSION_CONTEXT.set(PermissionContext(principal_user_id="previous-owner"))
    TOOL_PERMISSION_CHANNEL_ID.set("previous-channel")
    observed = []

    async def earlier_rail(_ctx):
        observed.append((state["model"], TOOL_PERMISSION_CONTEXT.get().principal_user_id,
                         TOOL_PERMISSION_CHANNEL_ID.get()))

    invoke, effects = await chain(stream, intermediate=[(98, earlier_rail)])
    await invoke(context(work))
    assert observed == [("native-model", "native-owner", "native-channel")]
    assert state["applies"] == 1 and state["checks"] == 2
    assert len(effects) == 1 and work.request.params["mode"] == "code"


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["read_only", "none"])
async def test_last_filters_tools_reinserted_after_stream_checkpoint(policy):
    work, state = prepared(tool_policy=policy)
    stream = JiuSwarmStreamEventRail()
    bind(stream, work)

    async def add_tools(ctx):
        ctx.inputs.tools = [SimpleNamespace(name=name)
                            for name in sorted(NATIVE_READ_ONLY_TOOL_NAMES | {"write_file", "task_tool"})]

    invoke, effects = await chain(stream, intermediate=[(20, add_tools)])
    ctx = context(work)
    await invoke(ctx)
    expected = NATIVE_READ_ONLY_TOOL_NAMES if policy == "read_only" else set()
    assert {tool.name for tool in ctx.inputs.tools} == expected
    assert state["applies"] == 1 and len(effects) == 1


@pytest.mark.asyncio
async def test_actual_permission_wait_then_revocation_has_zero_tool_effect():
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    entered, release = asyncio.Event(), asyncio.Event()
    observed = []

    async def approve_after_wait(_inp):
        observed.append(TOOL_PERMISSION_CONTEXT.get().principal_user_id)
        entered.set()
        await release.wait()
        return ("approve",)

    permission = PermissionInterruptRail(host=ToolPermissionHost(permission_scene_hook=approve_after_wait))
    # An existing rail may wait after stream.priority; final authority must
    # follow all registered rails, including this real SDK permission rail.
    invoke, effects = await chain(stream, kind="tool", intermediate=[(20, permission.before_tool_call)])
    pending = asyncio.create_task(invoke(context(work, kind="tool")))
    await asyncio.wait_for(entered.wait(), 2)
    state["allowed"] = False
    release.set()
    with authority_rejected():
        await pending
    assert observed == ["native-owner"]
    assert effects == [] and len(failures) == 1 and state["applies"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", sorted(NATIVE_READ_ONLY_TOOL_NAMES) + ["write_file"])
async def test_allowed_native_reads_and_configured_text_tool_reach_effect(tool_name):
    native = tool_name != "write_file"
    work, state = prepared(origin="native" if native else "text",
                           tool_policy="read_only" if native else "configured")
    stream = JiuSwarmStreamEventRail()
    bind(stream, work)
    TOOL_PERMISSION_CONTEXT.set(PermissionContext(principal_user_id="stale-owner"))
    observed = []

    async def approve(inp):
        permission = TOOL_PERMISSION_CONTEXT.get()
        observed.append((inp.tool_call.name, permission.principal_user_id if permission else None,
                         TOOL_PERMISSION_CHANNEL_ID.get()))
        return ("approve",)

    permission = PermissionInterruptRail(host=ToolPermissionHost(permission_scene_hook=approve))
    invoke, effects = await chain(stream, kind="tool",
                                  intermediate=[(permission.priority, permission.before_tool_call)])
    ctx = context(work, kind="tool")
    ctx.inputs.tool_name = ctx.inputs.tool_call.name = tool_name
    await invoke(ctx)
    assert observed == [(tool_name, "native-owner" if native else None,
                         "native-channel" if native else "text-channel")]
    assert effects == [ctx.inputs] and state["checks"] == 2 and state["applies"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["model", "tool"])
async def test_released_owner_after_background_wait_has_zero_effect(kind):
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    entered, release = asyncio.Event(), asyncio.Event()

    async def checkpoint(_ctx):
        entered.set()
        await release.wait()

    setattr(stream, "background_model_checkpoint" if kind == "model" else "background_file_checkpoint", checkpoint)
    invoke, effects = await chain(stream, kind=kind)
    pending = asyncio.create_task(invoke(context(work, kind=kind)))
    await asyncio.wait_for(entered.wait(), 2)
    state["live"] = False
    release.set()
    with authority_rejected():
        await pending
    assert effects == [] and len(failures) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["call_name", "tool_name", "both_names", "wrong_inputs"])
async def test_final_tool_call_identity_rejects_late_mutations(mutation):
    work, _state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)

    async def mutate(ctx):
        if mutation == "wrong_inputs":
            ctx.inputs = SimpleNamespace(tool_name="read_file", tool_call=SimpleNamespace(name="read_file"))
            return
        if mutation in {"call_name", "both_names"}:
            ctx.inputs.tool_call.name = "write_file"
        if mutation in {"tool_name", "both_names"}:
            ctx.inputs.tool_name = "write_file"

    invoke, effects = await chain(stream, kind="tool", intermediate=[(20, mutate)])
    with authority_rejected():
        await invoke(context(work, kind="tool"))
    assert effects == [] and len(failures) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("descriptor", [None, {}, "invalid", {"binding_id": "retired"}])
@pytest.mark.parametrize("typed", [False, True])
async def test_bound_restart_without_resolver_aborts_before_effect(descriptor, typed):
    stream = JiuSwarmStreamEventRail()
    extra = {"jiuwenswarm_execution": descriptor}
    ctx = context()
    ctx.extra["run_context"] = RunContext(extra=extra) if typed else {"extra": extra}
    invoke, effects = await chain(stream)
    with authority_rejected():
        await invoke(ctx)
    assert effects == []


@pytest.mark.asyncio
async def test_no_tools_policy_stops_even_a_read_before_effect_and_failure_reporting_can_fail():
    work, _state = prepared(tool_policy="none")
    stream = JiuSwarmStreamEventRail()
    bind(stream, work)

    async def reporting_failed(_ctx, _error):
        raise RuntimeError("Goal assessment transport failed")

    stream.execution_work_failure = reporting_failed
    invoke, effects = await chain(stream, kind="tool")
    with authority_rejected():
        await invoke(context(work, kind="tool"))
    assert effects == []


@pytest.mark.asyncio
async def test_next_text_work_restores_own_runtime_and_permissions_in_same_sdk_task():
    native, native_state = prepared()
    text, text_state = prepared(origin="text", tool_policy="configured", mode="code")
    stream = JiuSwarmStreamEventRail()
    bind(stream, native)
    invoke, effects = await chain(stream)
    await invoke(context(native))
    assert TOOL_PERMISSION_CONTEXT.get().principal_user_id == "native-owner"
    bind(stream, text)
    ctx = context(text, tools=[SimpleNamespace(name="write_file")])
    await invoke(ctx)
    assert TOOL_PERMISSION_CONTEXT.get() is None
    assert TOOL_PERMISSION_CHANNEL_ID.get() == "text-channel"
    assert text_state["model"] == "text-model"
    assert native_state["applies"] == text_state["applies"] == 1
    assert [tool.name for tool in ctx.inputs.tools] == ["write_file"] and len(effects) == 2


@pytest.mark.asyncio
async def test_runtime_callback_itself_observes_current_native_then_text_permissions():
    native, native_state = prepared()
    text, text_state = prepared(origin="text", tool_policy="configured")
    stream = JiuSwarmStreamEventRail()
    invoke, _effects = await chain(stream)
    TOOL_PERMISSION_CONTEXT.set(PermissionContext(principal_user_id="stale-owner"))
    TOOL_PERMISSION_CHANNEL_ID.set("stale-channel")
    bind(stream, native)
    await invoke(context(native))
    bind(stream, text)
    await invoke(context(text))
    assert native_state["runtime_permissions"] == [("native-owner", "native-channel")]
    assert text_state["runtime_permissions"] == [(None, "text-channel")]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["model", "tool"])
async def test_policy_revoked_during_actual_pause_blocks_resumed_effect(kind):
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    pause_entered = asyncio.Event()

    class ObservedPause(asyncio.Event):
        async def wait(self):
            pause_entered.set()
            return await super().wait()

    pauses = stream._pause_events if kind == "model" else stream._tool_pause_events
    pauses["sdk-session"] = ObservedPause()
    invoke, effects = await chain(stream, kind=kind)
    pending = asyncio.create_task(invoke(context(work, kind=kind)))
    await asyncio.wait_for(pause_entered.wait(), 2)
    state["allowed"] = False
    (stream.resume if kind == "model" else stream.resume_tools)("sdk-session")
    with authority_rejected():
        await pending
    assert effects == [] and len(failures) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bound", [True, False])
async def test_resolver_without_work_cannot_downgrade_bound_round(bound):
    stream = JiuSwarmStreamEventRail()
    stream.execution_work_resolver = lambda _ctx: None
    work, _state = prepared()
    invoke, effects = await chain(stream)
    if bound:
        with authority_rejected():
            await invoke(context(work))
        assert effects == []
    else:
        await invoke(context())
        assert len(effects) == 1


@pytest.mark.asyncio
async def test_read_only_with_no_model_tools_is_valid():
    work, _state = prepared()
    stream = JiuSwarmStreamEventRail()
    bind(stream, work)
    ctx = context(work)
    ctx.inputs.tools = None  # Valid SDK ModelCallInputs default.
    invoke, effects = await chain(stream)
    await invoke(ctx)
    assert ctx.inputs.tools == [] and len(effects) == 1


@pytest.mark.asyncio
async def test_unbound_legacy_and_existing_formal_read_only_seam_stay_unchanged():
    stream = JiuSwarmStreamEventRail()
    invoke, effects = await chain(stream)
    ctx = context(tools=[SimpleNamespace(name="write_file")])
    await invoke(ctx)
    assert [tool.name for tool in ctx.inputs.tools] == ["write_file"]
    sid = "lv-formal-native-work"
    capture = stream.open_formal_tool_event_capture(sid, read_only_tools=True)
    ctx = context(tools=[SimpleNamespace(name=name) for name in ("read_file", "write_file")])
    ctx.extra[stream._SID_KEY] = sid
    await invoke(ctx)
    assert [tool.name for tool in ctx.inputs.tools] == ["read_file"] and len(effects) == 2
    tool_invoke, tool_effects = await chain(stream, kind="tool")
    ctx = context(kind="tool")
    ctx.extra[stream._SID_KEY] = sid
    ctx.inputs.tool_name = ctx.inputs.tool_call.name = "write_file"
    with pytest.raises(AbortError, match="FORMAL_READ_ONLY_TOOL_FORBIDDEN"):
        await tool_invoke(ctx)
    assert tool_effects == [] and capture.drain() == ()
    stream.close_formal_tool_event_capture(sid, capture, abort=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["invoke", "stream"])
@pytest.mark.parametrize("policy", ["configured", "read_only", "none"])
async def test_real_react_entry_applies_work_before_initial_snapshot_and_refreshes_each_round(
    monkeypatch, tmp_path, transport, policy,
):
    from jiuwenswarm.server.runtime.agent_adapter.work_model import BoundAgentModel

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Runner, "callback_framework", AsyncCallbackFramework())
    sid = f"work-entry-{uuid4().hex}"
    react = ReActAgent(card=AgentCard(id=sid))
    config = ReActAgentConfig()
    config.model_name = "mode-model"
    config.max_iterations = 3
    config.kv_cache_affinity_config = KVCacheAffinityConfig(
        enable_kv_cache_release=False, enable_kv_cache_affinity=False,
    )
    react.configure(config)
    trace, calls = [], []
    first = ["new_mode_only"] if policy == "configured" else ["read_file", "write_file"]
    second = ["later_loaded_tool"] if policy == "configured" else ["glob", "bash"]
    current_tools = [ToolInfo(name="old_mode_only")]
    steering = asyncio.Queue()

    class RecordingClient:
        def record(self, tools):
            calls.append([tool.name for tool in tools or []])
            if len(calls) == 1:
                current_tools[:] = [ToolInfo(name=name) for name in second]
                steering.put_nowait("continue with the newly loaded tools")

        async def invoke(self, messages=None, **kwargs):
            self.record(kwargs.get("tools"))
            return AssistantMessage(content="done")

        async def stream(self, messages=None, **kwargs):
            self.record(kwargs.get("tools"))
            yield AssistantMessageChunk(content="done", finish_reason="stop")

    runtime_tasks = set()
    client = RecordingClient()
    client_creations = []

    def create_client(**kwargs):
        client_creations.append(kwargs)
        return client

    monkeypatch.setattr("openjiuwen.core.foundation.llm.model.create_model_client", create_client)
    raw_model = Model(
        model_config=ModelRequestConfig(model="mode-model"),
        model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_key="test-only", api_base="http://127.0.0.1:1",
            stream_first_chunk_timeout=None, stream_idle_timeout=None,
        ),
    )

    async def apply_runtime(_ctx):
        task = asyncio.current_task()
        if task not in runtime_tasks:
            runtime_tasks.add(task)
            trace.append("apply_current_work")
            current_tools[:] = [ToolInfo(name=name) for name in first]
        react.set_llm(work.model)

    async def list_tools():
        trace.append("list_tools:" + ",".join(tool.name for tool in current_tools))
        return list(current_tools)

    monkeypatch.setattr(react.ability_manager, "list_tool_info", list_tools)
    work = PreparedAgentWork(
        request=AgentRequest(request_id="request", channel_id="web", session_id=sid,
                             params={"mode": "code.normal"}),
        policy=AgentExecutionPolicy(origin="text" if policy == "configured" else "native",
                                    tool_policy=policy, model_identity="mode-model",
                                    model_config_version="v1", before_effect=lambda: None),
        sdk_agent=react, sdk_session_id=sid, require_live=lambda: None, apply_runtime=apply_runtime,
    )
    work.model = BoundAgentModel(raw_model, work)
    stream = JiuSwarmStreamEventRail()

    def resolve(ctx):
        work.require_context(sdk_agent=react, session_id=ctx.session.get_session_id(),
                             run_context=ctx.extra.get("run_context"))
        return work

    stream.execution_work_resolver = resolve
    for phase, priority in (("prepare", 1000), ("last", -1000)):
        await react.register_rail(AgentWorkRail(stream, phase=phase, priority=priority))
    react.set_llm(raw_model)
    inputs = {"query": "hello", "conversation_id": sid, "run_context": work.run_context(),
              "_steering_queue": steering}
    try:
        if transport == "invoke":
            result = await react.invoke(inputs)
            assert result["output"] == "done"
        else:
            output = [chunk async for chunk in react.stream(inputs)]
            assert output
        expected = [first, second] if policy == "configured" else (
            [["read_file"], ["glob"]] if policy == "read_only" else [[], []]
        )
        assert calls == expected, {"trace": trace, "provider_tools": calls}
        assert len(client_creations) == 1 and raw_model._client is client
        assert trace[0] == "apply_current_work", trace
        assert trace.count("apply_current_work") == 1
        assert not any("old_mode_only" in item for item in trace)
    finally:
        await react.agent_callback_manager.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", ["absent", "same", "different", "none"])
async def test_invoke_inputs_context_adoption_does_not_replace_existing_binding(existing):
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    ctx = AgentCallbackContext(agent=None, session=Session(session_id="sdk-session"),
                               inputs=InvokeInputs(query="hello", run_context=work.run_context()))
    if existing == "same":
        ctx.extra["run_context"] = work.run_context()
    elif existing == "different":
        ctx.extra["run_context"] = {"extra": {"jiuwenswarm_execution": {"binding_id": "another"}}}
    elif existing == "none":
        ctx.extra["run_context"] = None
    framework = AsyncCallbackFramework()
    prepare_rail = AgentWorkRail(stream, phase="prepare", priority=1000)
    await framework.register("entry", prepare_rail.before_invoke)
    effects = []

    @framework.emit_before("entry")
    async def invoke(_ctx):
        effects.append("SDK invoke preparation")

    if existing in {"different", "none"}:
        with authority_rejected():
            await invoke(ctx)
        assert effects == [] and state["applies"] == 0 and len(failures) == 1
    else:
        await invoke(ctx)
        assert ctx.extra["run_context"] == work.run_context()
        assert effects == ["SDK invoke preparation"] and state["applies"] == 1
    assert not hasattr(ctx.inputs, "tools")


@pytest.mark.asyncio
async def test_revocation_while_refreshing_actual_tools_is_rechecked_before_model():
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    entered, release = asyncio.Event(), asyncio.Event()
    ctx = context(work)

    async def list_tools():
        entered.set()
        await release.wait()
        return [ToolInfo(name="read_file")]

    ctx.agent.ability_manager.list_tool_info = list_tools
    invoke, effects = await chain(stream)
    pending = asyncio.create_task(invoke(ctx))
    await asyncio.wait_for(entered.wait(), 2)
    state["allowed"] = False
    release.set()
    with authority_rejected():
        await pending
    assert effects == [] and len(failures) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["exception", "invalid_snapshot"])
async def test_tool_refresh_failures_abort_sdk_callback_before_model(failure_kind):
    work, _state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    ctx = context(work)

    async def list_tools():
        if failure_kind == "exception":
            raise RuntimeError("configured tool lookup failed")
        return None

    ctx.agent.ability_manager.list_tool_info = list_tools
    invoke, effects = await chain(stream)
    expected = RuntimeError if failure_kind == "exception" else ValueError
    with pytest.raises(expected) as caught:
        await invoke(ctx)
    assert isinstance(caught.value.__context__, AbortError)
    assert effects == [] and len(failures) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_policy", ["configured", "none"])
@pytest.mark.parametrize("revoked", [False, True])
async def test_real_deep_selective_task_entry_prepares_authority_before_other_rails_and_tools(
    monkeypatch, tmp_path, tool_policy, revoked,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Runner, "callback_framework", AsyncCallbackFramework())
    sid = uuid4().hex
    deep = DeepAgent(AgentCard(id=uuid4().hex, name="deep-selective"))
    react = ReActAgent(AgentCard(id=uuid4().hex, name="actual-react"))
    react.configure(ReActAgentConfig(model_name="model", max_iterations=1,
        kv_cache_affinity_config=KVCacheAffinityConfig(enable_kv_cache_release=False, enable_kv_cache_affinity=False)))
    deep.set_react_agent(react, initialized=True)
    trace, provider_tools = [], []
    tools = [ToolInfo(name="previous_work_tool")]
    allowed = True

    def observe(label):
        permission = TOOL_PERMISSION_CONTEXT.get()
        trace.append((label, asyncio.current_task().get_name(),
                      permission.principal_user_id if permission else None))

    class RecordingModel(Model):
        def __init__(self):
            self.model_config = ModelRequestConfig(model="model")
            self.model_client_config = ModelClientConfig(client_provider="OpenAI", api_key="unused",
                                                        api_base="http://127.0.0.1:1")

        async def stream(self, messages=None, **kwargs):
            observe("model")
            provider_tools.append([tool.name for tool in kwargs.get("tools") or []])
            yield AssistantMessageChunk(content="done", finish_reason="stop")

    model = RecordingModel()
    react.set_llm(model)

    def check_policy():
        if not allowed:
            raise ValueError("selection revoked before actual executor")

    async def apply_runtime(_ctx):
        observe("apply_runtime")
        tools[:] = [ToolInfo(name="current_work_tool")]
        react.set_llm(model)

    async def list_tools():
        observe("list_tools")
        return list(tools)

    monkeypatch.setattr(react.ability_manager, "list_tool_info", list_tools)
    work = PreparedAgentWork(request=AgentRequest(request_id="request", channel_id="web", session_id=sid),
        policy=AgentExecutionPolicy(origin="text" if tool_policy == "configured" else "native",
            tool_policy=tool_policy, model_identity="model", model_config_version="v1", before_effect=check_policy),
        sdk_agent=deep, sdk_session_id=sid, require_live=lambda: None, apply_runtime=apply_runtime,
        permission_context=PermissionContext(principal_user_id="actual-work"))
    stream = JiuSwarmStreamEventRail()

    def resolve(ctx):
        work.require_context(sdk_agent=deep, session_id=ctx.session.get_session_id(),
                             run_context=ctx.extra.get("run_context"))
        return work

    stream.execution_work_resolver = resolve
    for phase, priority in [("prepare", 1000), ("last", -1000)]:
        await deep._register_rail_selective(AgentWorkRail(stream, phase=phase, priority=priority))

    async def other_task_rail(_ctx):
        observe("other_task_rail")

    await deep.register_callback(AgentCallbackEvent.BEFORE_TASK_ITERATION, other_task_rail, 98)
    config = ControllerConfig()
    manager = TaskManager(config)
    deps = TaskExecutorDependencies(config, react.ability_manager, ContextEngine(), manager, EventQueue(config))
    executor = TaskLoopEventExecutor(deps, deep)
    ready = asyncio.Event()
    session = Session(session_id=sid)
    coordinator = SimpleNamespace(reset=lambda: None, current_iteration=0)
    monkeypatch.setattr(deep, "load_state", lambda _session: SimpleNamespace(task_plan=None))
    monkeypatch.setattr(deep, "save_state", lambda *_args: None)
    monkeypatch.setattr(deep, "clear_state", lambda *_args: None)
    monkeypatch.setattr(deep, "_build_interaction_next_work", lambda **_kwargs: None)
    monkeypatch.setattr(deep, "_write_round_result_to_stream", AsyncMock())
    deep._loop_coordinator = coordinator

    # The real scheduler predates later requests and creates executor tasks
    # from its own ContextVars, independently of run_one_round's outer task.
    async def existing_scheduler():
        await ready.wait()

        async def run_executor():
            return [chunk async for chunk in executor.execute_ability("actual-task", session)]

        return await asyncio.create_task(run_executor(), name="actual-executor")

    permission_token = TOOL_PERMISSION_CONTEXT.set(None)
    scheduler_task = asyncio.create_task(existing_scheduler(), name="existing-scheduler")
    TOOL_PERMISSION_CONTEXT.reset(permission_token)

    async def submit(_session, query, **kwargs):
        nonlocal allowed
        await manager.add_task(Task(task_id="actual-task", session_id=sid, task_type=DEEP_TASK_TYPE,
            description=query, status=TaskStatus.SUBMITTED, metadata={
                "run_kind": kwargs["run_kind"], "run_context": kwargs["run_context"]}))
        allowed = not revoked
        ready.set()

    async def wait_round(**_kwargs):
        await scheduler_task
        return {"output": "done"}

    controller = SimpleNamespace(submit_round=submit, wait_round_completion=wait_round)
    monkeypatch.setattr(deep, "prepare_interaction_task_loop", AsyncMock(return_value=(coordinator, controller)))
    scheduled = RoundWorkItem.user(request_id="request", inputs={"query": "hello", "run": {"context": work.run_context()}})
    try:
        outcome = await asyncio.create_task(deep.run_one_round(scheduled, "actual-task", session), name="outer-round")
        if revoked:
            assert outcome.error_code is not None and provider_tools == []
            assert trace == [("apply_runtime", "outer-round", "actual-work")], trace
        else:
            assert outcome.error_code is None, trace
            assert provider_tools == ([["current_work_tool"]] if tool_policy == "configured" else [[]]), trace
            assert trace[:3] == [("apply_runtime", "outer-round", "actual-work"),
                ("apply_runtime", "actual-executor", "actual-work"),
                ("other_task_rail", "actual-executor", "actual-work")], trace
            assert all(permission == "actual-work" for _label, _task, permission in trace)
    finally:
        if not scheduler_task.done():
            scheduler_task.cancel()
        await deep.agent_callback_manager.clear()
        await react.agent_callback_manager.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", ["absent", "same", "different", "none"])
async def test_task_iteration_context_adoption_rejects_conflict_before_other_rails(existing):
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    ctx = AgentCallbackContext(agent=None, session=Session(session_id="sdk-session"),
        inputs=TaskIterationInputs(iteration=1, loop_event=None, run_context=work.run_context()))
    if existing != "absent":
        ctx.extra["run_context"] = work.run_context() if existing == "same" else (
            None if existing == "none" else {"extra": {"jiuwenswarm_execution": {"binding_id": "another"}}})
    framework = AsyncCallbackFramework()
    rail = AgentWorkRail(stream, phase="prepare", priority=1000)
    await framework.register("entry", rail.before_task_iteration, priority=1000)
    effects = []

    @framework.emit_before("entry")
    async def invoke(_ctx):
        effects.append("actual task preparation")

    if existing in {"different", "none"}:
        with authority_rejected():
            await invoke(ctx)
        assert effects == [] and state["applies"] == 0 and len(failures) == 1
    else:
        await invoke(ctx)
        assert ctx.extra["run_context"] == work.run_context()
        assert effects == ["actual task preparation"] and state["applies"] == 1
    assert not hasattr(ctx.inputs, "tools")


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["before_invoke", "before_task_iteration"])
@pytest.mark.parametrize("bound", [False, True])
async def test_entry_missing_sdk_session_rejects_managed_and_preserves_legacy(event, bound):
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    run_context = work.run_context() if bound else None
    inputs = (InvokeInputs(query="hello", run_context=run_context) if event == "before_invoke" else
              TaskIterationInputs(iteration=1, loop_event=None, run_context=run_context))
    ctx = AgentCallbackContext(agent=None, inputs=inputs)
    framework = AsyncCallbackFramework()
    rail = AgentWorkRail(stream, phase="prepare", priority=1000)
    await framework.register("entry", getattr(rail, event), priority=1000)
    effects = []

    @framework.emit_before("entry")
    async def invoke(_ctx):
        effects.append("legacy SDK preparation")

    if bound:
        with authority_rejected():
            await invoke(ctx)
        assert effects == [] and len(failures) == 1
        assert str(failures[0]) == "AGENT_WORK_SESSION_UNAVAILABLE"
    else:
        await invoke(ctx)
        assert effects == ["legacy SDK preparation"] and failures == []
    assert state["applies"] == 0


@pytest.mark.asyncio
async def test_task_iteration_requires_sdk_typed_inputs():
    work, state = prepared()
    stream = JiuSwarmStreamEventRail()
    failures = bind(stream, work)
    ctx = AgentCallbackContext(agent=None, session=Session(session_id="sdk-session"),
        inputs=InvokeInputs(query="hello", run_context=work.run_context()))
    rail = AgentWorkRail(stream, phase="prepare", priority=1000)
    with pytest.raises(AbortError):
        await rail.before_task_iteration(ctx)
    assert state["applies"] == 0 and str(failures[0]) == "AGENT_WORK_CONTEXT_INVALID"
