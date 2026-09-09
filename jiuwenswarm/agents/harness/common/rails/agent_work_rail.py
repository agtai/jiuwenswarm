# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Actual work authority before other rails and again before execution."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openjiuwen.core.single_agent.rail.base import AgentCallbackContext
from openjiuwen.harness.rails.base import DeepAgentRail

if TYPE_CHECKING:
    from jiuwenswarm.agents.harness.common.rails.stream_event_rail import JiuSwarmStreamEventRail


class AgentWorkRail(DeepAgentRail):
    """Two thin checkpoints sharing the existing stream owner's resolver.

    Construct ``prepare`` above the highest existing rail priority and ``last``
    below the lowest. SDK callbacks execute higher priorities first. Prepare
    applies runtime at invoke and actual task entry, before SDK tool snapshots. Each
    model preparation refreshes tools after runtime adoption; last revalidates
    after permission/pause/checkpoint waits and filters the final model tools
    or validates the actual tool call.
    """

    def __init__(self, stream_rail: JiuSwarmStreamEventRail, *,
                 phase: Literal["prepare", "last"], priority: int):
        super().__init__()
        if phase not in {"prepare", "last"} or type(priority) is not int:
            raise ValueError("AGENT_WORK_RAIL_PHASE_OR_PRIORITY_INVALID")
        self.priority = priority
        self._stream_rail = stream_rail
        self._prepare = phase == "prepare"

    async def before_invoke(self, ctx: AgentCallbackContext) -> None:
        # ReAct.stream calls invoke inside its actual executing task. Deep
        # routes this event to its outer actual-round entry before ReAct runs.
        if self._prepare:
            await self._stream_rail._adopt_execution_work(ctx, model_call=True, prepare=True, invoke=True)

    async def before_task_iteration(self, ctx: AgentCallbackContext) -> None:
        # Deep's BEFORE_INVOKE stays on the outer round. The scheduler invokes
        # ReAct directly on a separate task that needs its own permissions.
        if self._prepare:
            await self._stream_rail._adopt_execution_work(ctx, model_call=True, prepare=True, task_iteration=True)

    async def before_model_call(self, ctx: AgentCallbackContext) -> None:
        await self._stream_rail._adopt_execution_work(ctx, model_call=True, prepare=self._prepare)

    async def before_tool_call(self, ctx: AgentCallbackContext) -> None:
        await self._stream_rail._adopt_execution_work(ctx, model_call=False, prepare=self._prepare)
