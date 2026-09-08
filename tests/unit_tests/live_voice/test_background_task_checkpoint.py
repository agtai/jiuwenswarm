# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Real SDK callback and model-window seam; controlled LLM, no Provider calls."""

import json
import pytest
from openjiuwen.core.context_engine import ContextEngineConfig
from openjiuwen.core.context_engine.context.context import SessionModelContext
from openjiuwen.core.foundation.llm import AssistantMessage, UserMessage, ToolMessage, ToolCall
from openjiuwen.core.context_engine.schema.messages import OffloadToolMessage
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig, AgentCard
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentCallbackEvent

from jiuwenswarm.agents.harness.common.rails.stream_event_rail import JiuSwarmStreamEventRail
from jiuwenswarm.server.runtime.agent_adapter.background_task_checkpoint import (
    background_task_checkpoint, current_background_task_checkpoint,
    BackgroundReadProgress,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("reject", [False, True])
async def test_real_sdk_rebuilds_model_input_after_adoption_and_does_not_swallow_failure(reject):
    calls = []
    class Model:
        async def invoke(self, **kwargs):
            calls.append(kwargs)
            return AssistantMessage(content="controlled answer")
    agent = ReActAgent(AgentCard(id="checkpoint-root", name="Checkpoint root", description="test"))
    agent.configure(ReActAgentConfig(model_name="controlled"))
    agent._llm = Model()
    context = SessionModelContext("checkpoint-context", "formal-task-attempt", ContextEngineConfig(
        enable_openrouter_model_context_window_tokens=False,
    ), history_messages=[], processors=[])
    await context.add_messages(UserMessage(content="Original task."))
    rail = JiuSwarmStreamEventRail()
    async def adopt(ctx):
        if reject:
            raise RuntimeError("CONTROLLED_ADOPTION_REJECTED")
        await ctx.context.add_messages(UserMessage(content="New accepted requirement."))
    rail.background_model_checkpoint = adopt
    await agent.register_callback(AgentCallbackEvent.BEFORE_MODEL_CALL, rail.before_model_call)
    ctx = AgentCallbackContext(agent=agent, context=context, extra={rail._SID_KEY: "formal-task-attempt"})
    if reject:
        with pytest.raises(RuntimeError, match="CONTROLLED_ADOPTION_REJECTED"):
            await agent._call_model(ctx, context, [])
        assert calls == []
    else:
        await agent._call_model(ctx, context, [])
        assert len(calls) == 1
        assert [m.content for m in calls[0]["messages"]][-2:] == ["Original task.", "New accepted requirement."]


@pytest.mark.asyncio
async def test_process_local_checkpoint_is_exact_and_closed_after_stream():
    seen = []
    async def adopt(context):
        seen.append(context)
    assert current_background_task_checkpoint("task-a") is None
    with background_task_checkpoint("task-a", adopt):
        owner = current_background_task_checkpoint("task-a")
        assert owner is not None and not owner.closed
        with pytest.raises(RuntimeError, match="BINDING_MISMATCH"):
            current_background_task_checkpoint("task-b")
        await owner.adopt("exact context")
    assert owner.closed and seen == ["exact context"]
    assert current_background_task_checkpoint("task-a") is None


def model_context():
    return SessionModelContext("progress-context", "formal-task-attempt", ContextEngineConfig(
        enable_openrouter_model_context_window_tokens=False,
    ), history_messages=[], processors=[])


async def read_round(context, number, *, content="unchanged", tool="read_file", path="source.md", reverse=False):
    calls = [ToolCall(id=f"round-{number}-{i}", name=tool, type="function",
                      arguments=json.dumps({"file_path": path + str(i), "call_goal": f"read-{number}"}))
             for i in range(2)]
    await context.add_messages(AssistantMessage(content="", tool_calls=calls))
    for call in (reversed(calls) if reverse else calls):
        await context.add_messages(ToolMessage(tool_call_id=call.id, content=f"     1\t{content}\n     2\tend"))


@pytest.mark.asyncio
async def test_real_sdk_read_guard_stops_before_seventh_model_and_latches():
    calls = []
    class Model:
        async def invoke(self, **kwargs):
            calls.append(kwargs)
            return AssistantMessage(content="controlled answer")
    agent = ReActAgent(AgentCard(id="read-progress-root", name="Root", description="test"))
    agent.configure(ReActAgentConfig(model_name="controlled"))
    agent._llm = Model()
    context = model_context()
    await context.add_messages(UserMessage(content="Perform bounded file edit."))
    rail = JiuSwarmStreamEventRail()
    async def adopt(context):
        return None
    with background_task_checkpoint("formal-task-attempt", adopt):
        owner = current_background_task_checkpoint("formal-task-attempt")
        async def check(ctx):
            owner.check_model_progress(ctx.context)
        rail.background_model_checkpoint = check
        await agent.register_callback(AgentCallbackEvent.BEFORE_MODEL_CALL, rail.before_model_call)
        ctx = AgentCallbackContext(agent=agent, context=context, extra={rail._SID_KEY: "formal-task-attempt"})
        await agent._call_model(ctx, context, [])
        for number in range(1, 6):
            await read_round(context, number, reverse=number % 2 == 0)
            await agent._call_model(ctx, context, [])
            owner.check_model_progress(context)  # Exact callback replay is free.
        await read_round(context, 6)
        with pytest.raises(RuntimeError, match="BACKGROUND_TASK_READ_NO_PROGRESS"):
            await agent._call_model(ctx, context, [])
        assert len(calls) == 6
        assert owner.failure_reason == "BACKGROUND_TASK_READ_NO_PROGRESS"
        with pytest.raises(RuntimeError, match="BACKGROUND_TASK_READ_NO_PROGRESS"):
            owner.raise_if_failed()
    assert owner.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", ["write", "changed_result", "changed_args", "adjustment", "missing",
                                  "error", "offload", "compressed", "duplicate_id", "empty", "large"])
async def test_read_progress_resets_without_false_failure(reset):
    context = model_context()
    progress = BackgroundReadProgress()
    for number in range(1, 6):
        await read_round(context, number)
        assert not progress.stalled(context)
    await read_round(context, 6, tool="write_file" if reset == "write" else "read_file",
                     content="new" if reset == "changed_result" else "unchanged",
                     path="different.md" if reset == "changed_args" else "source.md")
    if reset == "adjustment":
        await context.add_messages(UserMessage(content="New accepted requirement."))
    elif reset == "missing":
        await context.add_messages(AssistantMessage(content="", tool_calls=[ToolCall(
            id="pending", name="read_file", type="function", arguments='{"file_path":"source.md"}')]))
    else:
        latest = context.get_messages()[-1]
        if reset == "error": latest.content = "[Tool execution interrupted] no result available."
        elif reset == "offload":
            # Exact subclasses are not raw-window evidence, even with a preview.
            original_messages = context.get_messages()
            context = type("Context", (), {"get_messages": lambda self, **kwargs: [
                *original_messages[:-1], OffloadToolMessage(tool_call_id=latest.tool_call_id,
                    content=latest.content, offload_type="filesystem", offload_handle="private")
            ]})()
        elif reset == "compressed": latest.metadata["compress_level"] = 1
        elif reset == "duplicate_id": latest.tool_call_id = context.get_messages()[-2].tool_call_id
        elif reset == "empty": latest.content = ""
        elif reset == "large": latest.content = "     1\t" + "x" * 1_048_577
    assert not progress.stalled(context)


@pytest.mark.asyncio
async def test_normal_reads_writes_verification_and_changed_results_never_accumulate():
    context = model_context()
    progress = BackgroundReadProgress()
    for number in range(30):
        await read_round(context, number, content=str(number), tool="write_file" if number % 3 == 0 else "read_file")
        assert not progress.stalled(context)
