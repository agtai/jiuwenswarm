# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Real SDK callback and model-window seam; controlled LLM, no Provider calls."""

import pytest
from openjiuwen.core.context_engine import ContextEngineConfig
from openjiuwen.core.context_engine.context.context import SessionModelContext
from openjiuwen.core.foundation.llm import AssistantMessage, UserMessage
from openjiuwen.core.single_agent.agents.react_agent import ReActAgent, ReActAgentConfig, AgentCard
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentCallbackEvent

from jiuwenswarm.agents.harness.common.rails.stream_event_rail import JiuSwarmStreamEventRail
from jiuwenswarm.server.runtime.agent_adapter.background_task_checkpoint import (
    background_task_checkpoint, current_background_task_checkpoint,
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
