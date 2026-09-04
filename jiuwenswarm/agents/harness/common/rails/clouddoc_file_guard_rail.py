# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Execution-time guard for co-scribe's own files against generic file tools.

The mandate machinery is code standing at the cloud-document boundary; these
files are the machinery itself -- the receipts ledger, the watch registry and
its audit journal, the dedup state, the credential keys, and the working-style
file. A generic file tool can reach them like any path on the machine, and the
model has done so (observed live: the working-style file edited with the
generic editor, no ledger entry, a receipt number invented in the reply; and
the state file's earlier relocation out of the agent workspace exists for the
same reason). Enforcement must therefore stand at the host's tool boundary,
which is this rail: writes to these files through generic tools are refused
with the road back -- the working-style file has its own fenced tool, and the
ledgers are written only by the machinery they audit. Reads stay allowed; the
files are the owner's to inspect.
"""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Any

from openjiuwen.core.foundation.llm import ToolMessage
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext
from openjiuwen.harness.rails.base import DeepAgentRail

from jiuwenswarm.common.utils import logger

_FILE_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "write_text_file",
        "write",
        "create_file",
        "create",
        "edit_file",
        "edit",
        "search_replace",
        "str_replace",
        "delete_file",
        "remove_file",
    }
)

# The guarded family: exact names beside config.yaml, plus the key directory.
_GUARDED_PREFIX = "clouddoc-"
_GUARDED_DIR = "clouddoc-keys"

_DENIAL_MESSAGE = (
    "[CLOUDDOC_FILE_GUARDED] 这是 co-scribe 的机制文件，通用文件工具不可写入。"
    "工作方式文件请用 clouddoc_workmode_edit 修改；回执、授权、审计与状态文件"
    "只由机制本身写入，人工修改会破坏可回退性。读取不受限制。"
)


def _parse_tool_args(raw_args: Any) -> dict[str, Any]:
    import json

    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _is_guarded_path(raw_path: Any) -> bool:
    """Whether the path names one of co-scribe's own files.

    Judged by name shape rather than by resolving against the live config dir:
    the rail must not import the clouddoc package (it guards the machinery, it
    is not part of it), and the names are distinctive enough -- everything the
    machinery persists starts with ``clouddoc-`` (the state relocation settled
    that naming), so a legitimate user file is not plausibly caught.
    """
    if not isinstance(raw_path, (str, PurePath)):
        return False
    normalized = str(raw_path).strip().strip("\"'").replace("\\", "/")
    if not normalized:
        return False
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts:
        return False
    name = parts[-1].casefold()
    if name.startswith(_GUARDED_PREFIX):
        return True
    return _GUARDED_DIR in {p.casefold() for p in parts[:-1]}


class CloudDocFileGuardRail(DeepAgentRail):
    """Refuse generic-tool writes to co-scribe's ledgers, keys and style file."""

    priority: int = 100

    async def before_tool_call(self, ctx: AgentCallbackContext) -> None:
        inputs = ctx.inputs
        if isinstance(inputs, dict):
            tool_name = str(inputs.get("tool_name", "") or "").lower()
            raw_args = inputs.get("tool_args", {})
        else:
            tool_name = str(getattr(inputs, "tool_name", "") or "").lower()
            raw_args = getattr(inputs, "tool_args", {})
        if tool_name not in _FILE_WRITE_TOOLS:
            return
        tool_args = _parse_tool_args(raw_args)
        if not any(
            _is_guarded_path(tool_args.get(key))
            for key in ("file_path", "path", "filename", "target_path")
        ):
            return
        logger.warning(
            "[CloudDocFileGuardRail] blocked generic write to a co-scribe file: tool=%s",
            tool_name,
        )
        self._reject_tool(ctx)

    @staticmethod
    def _reject_tool(ctx: AgentCallbackContext) -> None:
        # Same reject shape as MemoryForbiddenRail: skip the tool, hand the model
        # a ToolMessage result naming the road back.
        inputs = ctx.inputs
        tool_call = (
            inputs.get("tool_call")
            if isinstance(inputs, dict)
            else getattr(inputs, "tool_call", None)
        )
        tool_call_id = getattr(tool_call, "id", "") if tool_call else ""
        ctx.extra["_skip_tool"] = True
        message = ToolMessage(content=_DENIAL_MESSAGE, tool_call_id=tool_call_id)
        if isinstance(inputs, dict):
            inputs["tool_result"] = _DENIAL_MESSAGE
            inputs["tool_msg"] = message
        else:
            inputs.tool_result = _DENIAL_MESSAGE
            inputs.tool_msg = message
