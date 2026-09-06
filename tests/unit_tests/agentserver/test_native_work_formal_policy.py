# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openjiuwen.core.runner.callback import AsyncCallbackFramework, AbortError
from openjiuwen.core.single_agent.rail.base import ToolCallInputs
from openjiuwen.harness.tools.filesystem import (
    ReadFileTool,
    ListDirTool,
    GlobTool,
    GrepTool,
)

from jiuwenswarm.agents.harness.common.rails.stream_event_rail import (
    JiuSwarmStreamEventRail,
    NATIVE_READ_ONLY_TOOL_NAMES,
)
from jiuwenswarm.server.runtime.agent_adapter import interface_deep
from jiuwenswarm.server.live_voice.p3_model_resolution import ServerModelCatalogResolver
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from tests.unit_tests.agentserver.test_formal_live_voice_adapter import (
    FormalInstance,
    OutputLease,
    RawChunk,
    adapter_with,
    formal_request,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    [
        "write_file",
        "edit_file",
        "bash",
        "task_tool",
        "task",
        "web_fetch",
        "send_file",
        "unknown",
        "Read_File",
    ],
)
async def test_native_read_only_policy_aborts_actual_sdk_callback_before_tool_effect(
    tool_name,
):
    rail = JiuSwarmStreamEventRail()
    session = "lv-formal-native-work"
    capture = rail.open_formal_tool_event_capture(session, read_only_tools=True)
    framework = AsyncCallbackFramework()
    await framework.register("before-tool", rail.before_tool_call)
    call = SimpleNamespace(
        id="tool-1",
        name=tool_name,
        arguments={"path": "protected.txt", "tool": "read_file"},
    )
    context = SimpleNamespace(
        inputs=ToolCallInputs(
            tool_call=call, tool_name=tool_name, tool_args=call.arguments
        ),
        session=AsyncMock(),
        extra={rail._SID_KEY: session},
    )
    forbidden_effects = []

    @framework.emit_before("before-tool")
    async def invoke(_context):
        forbidden_effects.append(tool_name)

    with pytest.raises(AbortError) as raised:
        await invoke(context)
    assert raised.value.reason == "FORMAL_READ_ONLY_TOOL_FORBIDDEN"
    assert forbidden_effects == [] and capture.drain() == ()
    assert rail._inflight_tool_calls == {}
    rail.close_formal_tool_event_capture(session, capture, abort=True)
    assert not rail._formal_read_only_sessions


@pytest.mark.asyncio
async def test_exact_sdk_read_tools_remain_available_and_no_tool_override_stays_closed():
    registered = [
        tool(operation=SimpleNamespace())
        for tool in (ReadFileTool, ListDirTool, GlobTool, GrepTool)
    ]
    assert {tool.card.name for tool in registered} == NATIVE_READ_ONLY_TOOL_NAMES
    rail = JiuSwarmStreamEventRail()
    session = "lv-formal-native-work"
    capture = rail.open_formal_tool_event_capture(session, read_only_tools=True)
    model_input = SimpleNamespace(
        tools=[
            SimpleNamespace(name=name)
            for name in sorted(
                NATIVE_READ_ONLY_TOOL_NAMES | {"task_tool", "bash", "write_file"}
            )
        ]
    )
    await rail.before_model_call(
        SimpleNamespace(
            inputs=model_input,
            session=None,
            context=None,
            extra={rail._SID_KEY: session},
        )
    )
    assert {tool.name for tool in model_input.tools} == NATIVE_READ_ONLY_TOOL_NAMES
    for index, name in enumerate(sorted(NATIVE_READ_ONLY_TOOL_NAMES)):
        call = SimpleNamespace(
            id=f"tool-{index}", name=name, arguments={"path": "fixture.txt"}
        )
        await rail.before_tool_call(
            SimpleNamespace(
                inputs=ToolCallInputs(
                    tool_call=call, tool_name=name, tool_args=call.arguments
                ),
                session=AsyncMock(),
                extra={rail._SID_KEY: session},
            )
        )
    assert len(capture.drain()) == 8
    rail.close_formal_tool_event_capture(session, capture, abort=True)

    capture = rail.open_formal_tool_event_capture(
        session, allow_tools=False, read_only_tools=True
    )
    call = SimpleNamespace(id="blocked-read", name="read_file", arguments={})
    with pytest.raises(AbortError):
        await rail.before_tool_call(
            SimpleNamespace(
                inputs=ToolCallInputs(
                    tool_call=call, tool_name="read_file", tool_args={}
                ),
                session=AsyncMock(),
                extra={rail._SID_KEY: session},
            )
        )
    assert capture.drain() == ()
    rail.close_formal_tool_event_capture(session, capture, abort=True)


def catalog():
    return [
        {
            "alias": "First",
            "is_default": True,
            "model_client_config": {
                "model_name": "first-model",
                "api_key": "test-only",
            },
            "model_config_obj": {"temperature": 0.2},
        },
        {
            "alias": "Second",
            "is_default": True,
            "model_client_config": {
                "model_name": "second-model",
                "api_key": "test-only",
            },
            "model_config_obj": {"temperature": 0.4},
        },
    ]


def model(name):
    return SimpleNamespace(
        model_config=interface_deep.ModelRequestConfig(model=name, temperature=0.4),
        model_client_config=interface_deep.ModelClientConfig(
            client_provider="OpenAI",
            api_base="https://test.invalid",
            api_key="test-only",
        ),
    )


@pytest.mark.asyncio
async def test_native_model_uses_same_catalog_binding_as_task_and_fixed_isolated_clone(
    monkeypatch,
):
    entries = catalog()
    builds = []

    def build(client, config):
        builds.append(client["model_name"])
        return model(client["model_name"])

    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: entries, model_builder=build
    )
    accepted = resolver.resolve("Second", instantiate=False)
    assert accepted.identity == "second-model#0"
    instance = FormalInstance(
        OutputLease([RawChunk("answer", {"output": {"output": "Verified answer."}})])
    )
    applied = []
    instance._react_agent = SimpleNamespace(
        set_llm=applied.append, _config=SimpleNamespace()
    )
    adapter = adapter_with(instance)
    original = model("first-model")
    adapter._model = original
    monkeypatch.setattr(adapter, "_formal_model_resolver", lambda: resolver)
    monkeypatch.setattr(
        interface_deep, "Model", lambda **values: SimpleNamespace(**values)
    )
    request, inputs = formal_request()
    request.metadata.update(
        {
            "formal_live_voice_read_only_tools": True,
            "formal_live_voice_model_identity": accepted.identity,
            "formal_live_voice_model_config_version": accepted.config_version,
        }
    )
    root = object.__new__(interface_deep.JiuWenSwarmDeepAdapter)
    root._is_session_scoped_adapter = False
    root._model = original
    root._get_or_create_session_adapter = AsyncMock(return_value=adapter)
    root.cleanup_session_adapter = AsyncMock(return_value=True)

    def forbid_shared_model_mutation(_model):
        pytest.fail("formal Native work mutated the shared facade model")

    root._apply_model_to_react_agent = forbid_shared_model_mutation
    chunks = [
        chunk
        async for chunk in root.process_formal_live_voice_stream_impl(request, inputs)
    ]
    assert chunks[-1].payload["content"] == "Verified answer."
    assert builds == ["second-model"] and len(instance.sent) == 1
    assert applied[0].model_config.model_name == "second-model"
    assert len(applied) == 2 and applied[1] is original
    assert original.model_config.model_name == "first-model"
    assert root._model is original
    root._get_or_create_session_adapter.assert_awaited_once_with(request.session_id)
    root.cleanup_session_adapter.assert_awaited_once_with(request.session_id)
    assert adapter._stream_event_rail._formal_read_only_sessions == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["model", "version", "missing_policy_field"])
async def test_native_model_drift_unknown_or_incomplete_binding_fails_before_model_tool_or_input(
    monkeypatch, change
):
    entries = catalog()
    builds = []
    resolver = ServerModelCatalogResolver(
        catalog_reader=lambda: entries, model_builder=lambda *args: builds.append(args)
    )
    accepted = resolver.resolve("Second")
    instance = FormalInstance(OutputLease([]))
    adapter = adapter_with(instance)
    monkeypatch.setattr(adapter, "_formal_model_resolver", lambda: resolver)
    request, inputs = formal_request()
    request.metadata.update(
        {
            "formal_live_voice_read_only_tools": True,
            "formal_live_voice_model_identity": accepted.identity,
            "formal_live_voice_model_config_version": accepted.config_version,
        }
    )
    if change == "model":
        request.metadata["formal_live_voice_model_identity"] = "unknown-model#0"
    elif change == "version":
        entries[1]["model_config_obj"]["temperature"] = 0.9
    else:
        del request.metadata["formal_live_voice_model_config_version"]
    with pytest.raises((FormalTaskViolation, RuntimeError)):
        _ = [
            chunk
            async for chunk in adapter.process_formal_live_voice_stream_impl(
                request, inputs
            )
        ]
    assert builds == [] and instance.sent == [] and adapter.formal_runtime_configs == []
    assert adapter._stream_event_rail._formal_tool_event_captures == {}
