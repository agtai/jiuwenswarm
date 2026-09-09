# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Shared configured Agent resolution for text and Native capability callers.

This module selects existing application owners; it does not own execution or
replace the tool, project, interaction or session permission policies.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.mode_matrix import (
    ResolvedMode, TEAM_PLAN_CODE_MODE, TEAM_PLAN_NORMAL_MODE,
    canonicalize_mode_text, resolve_request_mode,
)

logger = logging.getLogger(__name__)
_SESSION_PREVIOUS_MODE_KEY = "_session_previous_mode"


class SessionAgentUnavailable(ValueError):
    """The authorized session has no matching configured owner."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SessionAgentOwner:
    agent: Any
    mode: str
    sub_mode: str | None
    canonical_mode: str
    work_mode: str
    project_dir: str
    project_id: str | None = None


async def resolve_owned_web_session(manager, request, *, before_effect, reason_prefix):
    """Retain current Gateway identity and the exact stored Web execution owner."""
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata

    def connection_guard():
        result = before_effect()
        if inspect.iscoroutine(result):
            result.close()
        if result is not None:
            raise PermissionError(f"{reason_prefix}_AUTHORITY_INVALID")

    connection_guard()
    metadata = await asyncio.to_thread(get_session_metadata, request.session_id,
                                       cache_bust=True, enable_writeback=False)
    if (metadata.get("session_id") != request.session_id or metadata.get("channel_id") != "web"
            or metadata.get("user_id", "") != request.user_id):
        raise PermissionError(f"{reason_prefix}_SESSION_MISMATCH")
    fields = ("session_id", "channel_id", "user_id", "project_id", "project_dir", "mode", "work_mode")
    snapshot = tuple(metadata.get(key, "" if key == "user_id" else None) for key in fields)
    if (metadata.get("work_mode") not in {"code", "work"}
            or not isinstance(metadata.get("mode"), str) or not metadata["mode"].strip()):
        raise PermissionError(f"{reason_prefix}_SESSION_MISMATCH")
    mode = resolve_request_runtime_mode(AgentRequest(request_id=request.request_id,
        channel_id="web", session_id=request.session_id, params={"mode": metadata.get("mode")}),
        work_mode=metadata.get("work_mode"))
    project_dir = metadata.get("project_dir")
    expected_owner = ("agent" if mode.manager_mode == "auto_harness" else mode.manager_mode,
        mode.sub_mode, mode.canonical_mode, metadata.get("work_mode"),
        project_dir.strip() if isinstance(project_dir, str) else None, metadata.get("project_id"))
    owner = await find_session_agent(manager, channel_id="web", session_id=request.session_id,
                                      project_dir=metadata.get("project_dir"))

    def guard():
        connection_guard()
        current = get_session_metadata(request.session_id, cache_bust=True, enable_writeback=False)
        if tuple(current.get(key, "" if key == "user_id" else None) for key in fields) != snapshot:
            raise PermissionError(f"{reason_prefix}_SESSION_MISMATCH")
        # A second lookup can observe B while storage changes A -> B -> A.
        # The selected owner must itself derive from the validated A snapshot.
        if (owner.mode, owner.sub_mode, owner.canonical_mode, owner.work_mode,
                owner.project_dir, owner.project_id) != expected_owner:
            raise PermissionError(f"{reason_prefix}_SESSION_MISMATCH")
        if manager.find_agent_exact(channel_id="web", mode=owner.mode,
                project_dir=owner.project_dir, sub_mode=owner.sub_mode) is not owner.agent:
            raise PermissionError(f"{reason_prefix}_OWNER_CHANGED")

    guard()
    return owner, guard


async def find_session_agent(
    agent_manager, *, channel_id: str, session_id: str, project_dir: str,
) -> SessionAgentOwner:
    """Observe the exact existing text owner of an already authorized session.

    Native calls cannot override the stored mode/project or create a second
    Agent to answer a query. An absent in-process owner means unavailable, not
    that a persisted Goal is absent. This performs no metadata or model writes.
    """
    from jiuwenswarm.server.runtime.session.session_history import is_valid_session_id
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata

    if (not isinstance(session_id, str) or not is_valid_session_id(session_id)
            or not isinstance(channel_id, str) or not channel_id.strip()
            or not isinstance(project_dir, str) or not project_dir.strip()):
        raise SessionAgentUnavailable("SESSION_AGENT_SCOPE_INVALID")
    metadata = await asyncio.to_thread(
        get_session_metadata, session_id, cache_bust=True, enable_writeback=False,
    )
    locked = metadata.get("project_dir") if isinstance(metadata, dict) else None
    if not isinstance(locked, str) or not locked.strip():
        raise SessionAgentUnavailable("SESSION_AGENT_PROJECT_UNAVAILABLE")
    def normalize(value):
        return os.path.normcase(os.path.abspath(os.path.expanduser(value.strip())))
    if normalize(locked) != normalize(project_dir):
        raise SessionAgentUnavailable("SESSION_AGENT_PROJECT_MISMATCH")
    work_mode, mode = metadata.get("work_mode"), metadata.get("mode")
    if work_mode not in {"code", "work"} or not isinstance(mode, str) or not mode.strip():
        raise SessionAgentUnavailable("SESSION_AGENT_MODE_UNAVAILABLE")
    request = AgentRequest(request_id="owner-query", channel_id=channel_id, session_id=session_id,
                           params={"work_mode": work_mode, "mode": mode})
    resolved = resolve_request_runtime_mode(request, work_mode=work_mode)
    manager_mode = "agent" if resolved.manager_mode == "auto_harness" else resolved.manager_mode
    agent = agent_manager.find_agent_exact(channel_id=channel_id, mode=manager_mode,
                                          project_dir=locked.strip(), sub_mode=resolved.sub_mode)
    if agent is None:
        raise SessionAgentUnavailable("SESSION_AGENT_OWNER_UNAVAILABLE")
    project_id = metadata.get("project_id")
    if project_id is not None and (type(project_id) is not str or not project_id or project_id.strip() != project_id):
        raise SessionAgentUnavailable("SESSION_AGENT_PROJECT_ID_INVALID")
    return SessionAgentOwner(agent, manager_mode, resolved.sub_mode, resolved.canonical_mode,
                             work_mode, locked.strip(), project_id)


def resolve_request_project_dir(request: AgentRequest) -> str | None:
    """Resolve the stable project identity for agent construction.

    New clients send ``project_dir`` separately from dynamic ``cwd``. Keep
    legacy fallbacks for older clients that only send cwd/trusted_dirs.
    """
    params = request.params or {}
    project_dir = params.get("project_dir")
    if isinstance(project_dir, str) and project_dir.strip():
        return project_dir.strip()
    metadata = request.metadata or {}
    metadata_project_dir = metadata.get("project_dir") if isinstance(metadata, dict) else None
    if isinstance(metadata_project_dir, str) and metadata_project_dir.strip():
        return metadata_project_dir.strip()
    cwd = params.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    metadata_cwd = metadata.get("cwd") if isinstance(metadata, dict) else None
    if isinstance(metadata_cwd, str) and metadata_cwd.strip():
        return metadata_cwd.strip()
    trusted_dirs = params.get("trusted_dirs")
    if isinstance(trusted_dirs, list) and trusted_dirs:
        first = trusted_dirs[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None


def resolve_agent_request_mode(
    raw_mode: Any,
    *,
    work_mode: Any = None,
) -> tuple[str, str | None, str]:
    """Resolve request params.mode into manager mode, sub_mode, and canonical value.

    plan / fast 已合并为单一 ``agent`` 模式：任何 ``agent`` / ``agent.plan`` /
    ``agent.fast`` 请求都归一到 ``agent``（sub_mode=None）。历史裸 ``plan`` /
    ``fast``（无 ``agent.`` 前缀，如旧 cron job 存量数据）同样归一到 ``agent``，
    与 CLI ``MODE_ALIASES``、记忆配置 ``_resolve_mode_memory`` 的裸 token 处理保持一致。
    """
    mode_text = canonicalize_mode_text(raw_mode)
    normalized_work_mode = (
        work_mode.strip().lower() if isinstance(work_mode, str) else ""
    )

    if mode_text in ("plan", "fast"):
        if normalized_work_mode == "code":
            return "code", "normal", "code.normal"
        return "agent", None, "agent"

    if mode_text == TEAM_PLAN_NORMAL_MODE:
        return "team", "plan", TEAM_PLAN_NORMAL_MODE
    if mode_text == TEAM_PLAN_CODE_MODE:
        return "code", "team", TEAM_PLAN_CODE_MODE

    parts = mode_text.split(".")
    mode = parts[0] or "agent"
    if mode == "agent":
        # 合并模式：忽略历史子模式（plan / fast），统一 canonical "agent"。
        if normalized_work_mode == "code":
            return "code", "normal", "code.normal"
        return "agent", None, "agent"
    if mode == "team":
        sub_mode = parts[1] if len(parts) > 1 and parts[1] else None
        if sub_mode not in {None}:
            sub_mode = None
        canonical_mode = f"team.{sub_mode}" if sub_mode else "team"
        return "team", sub_mode, canonical_mode

    default_sub_modes = {
        "code": "normal",
    }
    sub_mode = parts[1] if len(parts) > 1 and parts[1] else default_sub_modes.get(mode)
    if mode == "code" and sub_mode not in {"plan", "normal", "team"}:
        sub_mode = default_sub_modes.get(mode, "normal")
    canonical_mode = f"{mode}.{sub_mode}" if sub_mode else mode
    if canonical_mode in {"agent", "code", "code.normal"}:
        if normalized_work_mode == "code":
            return "code", "normal", "code.normal"
        if normalized_work_mode == "work":
            return "agent", None, "agent"
    return mode, sub_mode, canonical_mode


def resolve_request_runtime_mode(
    request: AgentRequest,
    *,
    work_mode: Any = None,
) -> ResolvedMode:
    """解析请求的运行模式（Web 组合 mode + work_mode；其余走历史解析）。"""
    params = request.params if isinstance(request.params, dict) else {}
    return resolve_request_mode(
        params,
        resolve_agent_request_mode,
        work_mode=work_mode,
    )


def _apply_resolved_mode_to_request(
    request: AgentRequest,
    *,
    work_mode: Any = None,
) -> tuple[str, str | None]:
    resolved = resolve_request_runtime_mode(request, work_mode=work_mode)
    if isinstance(request.params, dict):
        request.params["mode"] = resolved.canonical_mode
    return resolved.manager_mode, resolved.sub_mode



async def prepare_agent_request(
    agent_manager,
    request: AgentRequest,
    channel_id: str,
    *,
    sync_metadata: bool = True,
    metadata_sync: Callable | None = None,
) -> tuple[str, str | None, Any]:
    """Mode resolution and correct agent instance selection."""
    # [新增] 在 _apply_resolved_mode_to_request 把 canonical mode 写回 params 之前，
    # 先记录请求是否「显式」携带了 mode。下游 sync 用它做守卫：未显式携带则不覆盖
    # 磁盘已锁定的会话 mode（避免只读 RPC 用默认推断值腐蚀 team 等已锁定 mode）。
    # model 的显式与否由 _sync_chat_request_request_metadata 内部从 params 判断
    # （model_name 不会被规范化改写），故此处只捕获 mode 标志。
    # 注意：用与下游一致的严格判断——纯空白串 "   " 不算显式携带（bool("   ") 为 True
    # 会误判，导致空白 mode 走默认推断 agent.plan 并写盘腐蚀已锁定 mode）。
    params = request.params if isinstance(request.params, dict) else {}
    _raw_mode = params.get("mode")
    explicit_mode_provided = isinstance(_raw_mode, str) and bool(_raw_mode.strip())
    runtime_work_mode = None
    sid = str(request.session_id or "").strip()
    if sid:
        from jiuwenswarm.server.runtime.session.session_metadata import (
            get_session_metadata,
        )

        session_metadata = get_session_metadata(
            sid,
            cache_bust=True,
            enable_writeback=False,
        )
        stored_work_mode = (
            session_metadata.get("work_mode")
            if isinstance(session_metadata, dict)
            else None
        )
        # 下面的 sync 会把本轮 canonical mode 覆盖进 metadata，所以在覆盖前
        # 先把上一轮的值捎带给 _ensure_code_mode_state：它据此判断这个会话是
        # 不是可能还停在 plan 里（跨进程重启依然有效）。
        stored_session_mode = (
            session_metadata.get("mode")
            if isinstance(session_metadata, dict)
            else None
        )
        if isinstance(stored_session_mode, str) and stored_session_mode.strip():
            params[_SESSION_PREVIOUS_MODE_KEY] = stored_session_mode.strip()
        if isinstance(stored_work_mode, str) and stored_work_mode.strip().lower() in {
            "code",
            "work",
        }:
            runtime_work_mode = stored_work_mode.strip().lower()
    if runtime_work_mode is None:
        request_work_mode = params.get("work_mode")
        if isinstance(request_work_mode, str) and request_work_mode.strip().lower() in {
            "code",
            "work",
        }:
            runtime_work_mode = request_work_mode.strip().lower()
        else:
            from jiuwenswarm.server.runtime.session.work_mode import (
                default_work_mode_for_channel,
            )
            channel_id_for_default = request.channel_id or "web"
            runtime_work_mode = default_work_mode_for_channel(channel_id_for_default)
            logger.warning(
                "[_prepare_code_mode_chat_turn] work_mode missing in both session "
                "metadata and request params; defaulting to %r for channel=%s session=%s",
                runtime_work_mode,
                channel_id_for_default,
                request.session_id,
            )
    params["work_mode"] = runtime_work_mode
    mode, sub_mode = _apply_resolved_mode_to_request(
        request,
        work_mode=runtime_work_mode,
    )
    agent_mode = "agent" if mode == "auto_harness" else mode
    requested_project_dir = resolve_request_project_dir(request)
    # [改动] 写盘用 canonical mode（request.params["mode"]，已被规范化为
    # "agent.plan"/"team" 等），而非一级 mode（"agent"），使磁盘出现你期望的两类值。
    canonical_mode = (
        request.params.get("mode") if isinstance(request.params, dict) else None
    )
    if sync_metadata:
        if metadata_sync is None:
            raise ValueError("metadata synchronization owner is required")
        project_dir = metadata_sync(
            request,
            requested_project_dir,
            canonical_mode if canonical_mode else mode,
            explicit_mode_provided=explicit_mode_provided,
            user_id=str(getattr(request, "user_id", "") or "").strip(),
        )
    else:
        # Read-only path (e.g. command.goal get): never create/update
        # metadata.json. Prefer request project_dir, else locked disk value.
        project_dir = requested_project_dir
        if not (isinstance(project_dir, str) and project_dir.strip()):
            sid = str(request.session_id or "").strip()
            if sid:
                from jiuwenswarm.server.runtime.session.session_metadata import (
                    get_session_metadata,
                )

                meta = get_session_metadata(
                    sid, cache_bust=True, enable_writeback=False
                )
                locked = meta.get("project_dir") if isinstance(meta, dict) else None
                if isinstance(locked, str) and locked.strip():
                    project_dir = locked.strip()
    if isinstance(project_dir, str) and project_dir.strip():
        project_dir = project_dir.strip()
        request.params["project_dir"] = project_dir
        request.metadata = dict(request.metadata or {})
        request.metadata["project_dir"] = project_dir

    await agent_manager.wait_for_session_prewarm(request.session_id)
    agent = await agent_manager.get_agent(
        channel_id=channel_id,
        mode=agent_mode,
        project_dir=project_dir,
        sub_mode=sub_mode,
    )
    if agent is None:
        raise ValueError("Failed to get agent")

    return mode, sub_mode, agent
