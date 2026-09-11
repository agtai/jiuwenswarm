"""Shared read-only SwarmFlow queries for authenticated text and voice callers.

Callers authorize the session before entry. Queries use the existing Team
monitor/checkpoint owner and never create an execution or resume a workflow.
"""
from __future__ import annotations

import asyncio
import logging

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponse
from jiuwenswarm.server.wire_truncate import (
    _build_workflow_detail_payload,
    _build_workflow_human_prompt_payload,
    _build_workflow_list_payload,
    _json_wire_size,
)

logger = logging.getLogger(__name__)


async def query_workflows(request: AgentRequest) -> AgentResponse:
    """Read list/detail/human-input facts from the exact requested session."""
    from jiuwenswarm.agents.harness.team import get_team_manager

    session_id = request.session_id or ""
    channel_id = request.channel_id or "web"
    params = request.params if isinstance(request.params, dict) else {}
    action = str(params.get("action") or "list").strip().lower()
    workflow_id = params.get("workflow_id") or params.get("workflow_run_id")

    def response(payload, *, ok=True):
        return AgentResponse(request_id=request.request_id, channel_id=channel_id, ok=ok, payload=payload)

    if not isinstance(session_id, str) or not session_id.strip():
        return response({"error": "session_id is required"}, ok=False)
    if action not in {"list", "get", "get_human_prompt"}:
        return response({"error": "unsupported workflow query"}, ok=False)
    if action != "list" and (not isinstance(workflow_id, str) or not workflow_id.strip()):
        return response({"error": f"workflow_id is required for action={action}"}, ok=False)
    agent_id = params.get("agent_id")
    correlation_id = params.get("correlation_id")
    agent_id = agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None
    correlation_id = correlation_id.strip() if isinstance(correlation_id, str) and correlation_id.strip() else None
    if action == "get_human_prompt" and not agent_id and not correlation_id:
        return response({"error": "agent_id or correlation_id is required for action=get_human_prompt"}, ok=False)

    handler = get_team_manager(channel_id).get_workflow_handler(session_id)
    source = "live" if handler is not None else "checkpoint"
    try:
        if handler is None:
            from jiuwenswarm.server.runtime.agent_adapter.team_helpers import restore_workflow_runs

            restored = await asyncio.to_thread(restore_workflow_runs, session_id, strict=True)
            workflows = [run.to_workflow_run_dict() for run in restored.values()] if restored else []
        else:
            # Live monitor snapshots are read on their owning event loop.
            workflows = handler.get_workflow_snapshot()
    except Exception:
        logger.warning("Workflow observation unavailable: session_id=%s source=%s", session_id, source,
                       exc_info=True)
        return response({"error": "WORKFLOW_OBSERVATION_UNAVAILABLE", "source": source}, ok=False)

    if action == "list":
        payload = _build_workflow_list_payload(workflows, session_id=session_id)
    else:
        target = next((item for item in workflows if isinstance(item, dict)
                       and item.get("id") == workflow_id.strip()), None)
        if target is None:
            return response({"error": f"workflow not found: {workflow_id.strip()}"}, ok=False)
        if action == "get":
            payload = _build_workflow_detail_payload(target, session_id=session_id)
        else:
            payload = _build_workflow_human_prompt_payload(
                target, session_id=session_id, agent_id=agent_id, correlation_id=correlation_id,
            )
    ok = "error" not in payload
    logger.log(logging.INFO if ok and not payload.get("truncated") else logging.WARNING,
               "Workflow observation: session_id=%s action=%s source=%s count=%d payload_bytes=%d ok=%s truncated=%s",
               session_id, action, source, len(workflows), _json_wire_size(payload), ok, bool(payload.get("truncated")))
    return response(payload, ok=ok)
