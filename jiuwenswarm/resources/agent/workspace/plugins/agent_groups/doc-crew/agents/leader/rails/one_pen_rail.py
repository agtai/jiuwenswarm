# -*- coding: utf-8 -*-
"""One pen per team: this member does not write to shared cloud documents.

The doc-crew protocol concentrates every document write in the scribe, so
receipts carry a single executor and a revert has one clear target. For every
other member that discipline is code, not persona text: any clouddoc tool whose
declared effect class is a write (revertible or not) or a grant is refused here
with the reason, and the member is steered to route the change through the
leader to the scribe.

Blocking by effect class rather than by tool name is deliberate -- a write tool
added to the toolkit later is covered the day it declares its class, with no
list here to forget to update.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openjiuwen.core.foundation.llm import ToolMessage
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext
from openjiuwen.harness.rails.base import DeepAgentRail

logger = logging.getLogger(__name__)

_BLOCKED_CLASSES = frozenset({"revertible_write", "irreversible_write", "grant"})

_BLOCK_MSG = (
    "[DOC-CREW] 每队一支笔：本成员不直接写共享文档。"
    "需要修改时，把改动内容与目标区域交给 leader 分派给执笔专员（scribe）执行——"
    "写入集中在一支笔上，回执才有单一执行者，出错才能按回执整批回退。"
)


class OnePenRail(DeepAgentRail):
    """Refuse document-writing clouddoc tools for a non-scribe member."""

    def __init__(self) -> None:
        super().__init__()
        self._agent: Any | None = None

    def init(self, agent: Any) -> None:
        self._agent = agent

    def uninit(self, agent: Any) -> None:
        self._agent = None

    @staticmethod
    def _tool_call_data(ctx: AgentCallbackContext) -> tuple[str, dict[str, Any]]:
        inputs = ctx.inputs
        tool_name = str(getattr(inputs, "tool_name", "") or "")
        tool_call = getattr(inputs, "tool_call", None)
        raw_args = getattr(inputs, "tool_args", None)
        if raw_args is None and tool_call is not None:
            raw_args = getattr(tool_call, "arguments", None)
        args: dict[str, Any] = {}
        if isinstance(raw_args, dict):
            args = raw_args
        elif isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                args = parsed
        return tool_name, args

    @staticmethod
    def _reject(ctx: AgentCallbackContext, message: str) -> None:
        inputs = ctx.inputs
        tool_call = getattr(inputs, "tool_call", None)
        tool_call_id = getattr(tool_call, "id", "") if tool_call else ""
        ctx.extra["_skip_tool"] = True
        inputs.tool_result = message
        inputs.tool_msg = ToolMessage(content=message, tool_call_id=tool_call_id)
        logger.warning("[OnePenRail] blocked tool call: %s", message)

    async def before_tool_call(self, ctx: AgentCallbackContext) -> None:
        tool_name, _ = self._tool_call_data(ctx)
        if not tool_name.startswith("clouddoc_"):
            return
        try:
            from jiuwenswarm.agents.harness.common.tools.clouddoc.clouddoc_tools import (
                EFFECT_CLASSES,
            )
        except ImportError:
            # Outside the jiuwenswarm tree the toolkit is absent and so are its
            # tools; there is nothing to block.
            return
        # An unknown clouddoc tool is treated as a write: for a rail whose job
        # is subtraction, the safe reading of "no declaration" is refusal.
        if EFFECT_CLASSES.get(tool_name, "revertible_write") in _BLOCKED_CLASSES:
            self._reject(ctx, _BLOCK_MSG)
