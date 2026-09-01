"""Tool permission channel context.

The openjiuwen permission rail uses host callbacks that need to know which
channel is executing (web/acp/tui). We keep this as a ContextVar owned by
jiuwenswarm so request handlers can set/reset it without depending on the
legacy permissions implementation.
"""

from __future__ import annotations

import contextvars

# 当前 asyncio Task 的 channel_id（供工具权限/宿主确认判断）；由接口层在 run_agent 前 set、结束后 reset。
TOOL_PERMISSION_CHANNEL_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "jiuwenswarm_tool_permission_channel_id",
    default="",
)


# 当前 asyncio Task 的 chat_id（会话所在的具体对话，如 Slack 频道 ID）。
# Set beside TOOL_PERMISSION_CHANNEL_ID by the same call sites, and for the same
# reason: the ``scopes`` permissions section is matched on {channel, chat}, and
# the PermissionContext next door is built only for the digital-avatar scene, so
# an ordinary conversation has nothing else to be identified by here.
TOOL_PERMISSION_CHAT_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "jiuwenswarm_tool_permission_chat_id",
    default="",
)


# skills.rebuild 静默 follow-up：无 UI 审批，权限轨需自动放行。
SKILLS_REBUILD_SILENT: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "jiuwenswarm_skills_rebuild_silent",
    default=False,
)


__all__ = [
    "SKILLS_REBUILD_SILENT",
    "TOOL_PERMISSION_CHANNEL_ID",
    "TOOL_PERMISSION_CHAT_ID",
]
