# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Shared exact-target input delivery to existing Team/SwarmFlow owners.

Callers supply their trusted session and authority guard. The SDK checks that
guard at the actual pending-input consumption boundary. This adapter never
creates or restores a runtime, and delivery does not mean workflow completion.
"""

from __future__ import annotations

from collections.abc import Callable
from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponse


async def reply_swarmflow_request(request: AgentRequest) -> AgentResponse:
    """Web/Text transport adapter; only the authenticated envelope selects scope."""
    params = request.params if isinstance(request.params, dict) else {}
    session_id = request.session_id
    if params.get("session_id") not in (None, session_id):
        ok, reason = False, "swarmflow_reply_session_mismatch"
    elif not session_id or not params.get("correlation_id") or not params.get("answer"):
        ok, reason = False, "missing session_id/correlation_id/answer"
    else:
        try:
            ok, reason = await reply_swarmflow(session_id=session_id,
                run_id=params.get("run_id"), correlation_id=params.get("correlation_id"),
                answer=params.get("answer"), channel_id=request.channel_id)
        except Exception:
            # An unexpected failure is not evidence that delivery was rejected.
            ok, reason = False, "swarmflow_reply_outcome_unknown"
    return AgentResponse(request_id=request.request_id, channel_id=request.channel_id,
        ok=ok, payload={"ok": True, "status": "input_accepted"} if ok else
        {"ok": False, "error": reason or "failed"}, metadata=request.metadata,
        agent_ref=request.agent_ref)


def _valid_text(value: object, *, identity: bool = False) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    if identity and (not value.strip() or value.strip() != value):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


async def reply_swarmflow(
    *,
    session_id: str,
    run_id: str,
    correlation_id: str,
    answer: str,
    channel_id: str = "web",
    before_effect: Callable[[], None] | None = None,
) -> tuple[bool, str | None]:
    """Deliver one exact pending human input; return acceptance, never completion.

    The session comes from the authenticated caller's scope, not an answer
    payload. IDs must be copied verbatim from the owner. Transport-specific
    payload limits remain with the caller; answer whitespace is preserved.
    """
    if (
        not all(_valid_text(value, identity=True) for value in (session_id, run_id, correlation_id))
        or ":" in run_id
        or not _valid_text(answer)
    ):
        return False, "invalid_swarmflow_reply"

    from jiuwenswarm.agents.harness.team.team_manager import get_existing_team_manager

    manager = get_existing_team_manager(channel_id)
    if manager is None:
        return False, "not_active"
    return await manager.reply_swarmflow(
        session_id=session_id,
        run_id=run_id,
        correlation_id=correlation_id,
        answer=answer,
        before_effect=before_effect,
    )
