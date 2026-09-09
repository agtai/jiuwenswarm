# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Tests for handle_swarmflow_reply — adapter-side early validation.

Happy-path delivery builds a HumanAgentMessage via agent-core helpers
(``format_swarmflow_human_reply_target`` / ``HumanAgentMessage``); those
symbols are version-sensitive and are not pinned here. This suite only
covers the missing-params short-circuit that stays inside jiuwenswarm.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from jiuwenswarm.common.schema.message import ReqMethod


def _make_handler() -> JiuWenSwarmDeepAdapter:
    """Bypass the heavy __init__; only the handler needs the session-scoped flag."""
    adapter = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    adapter._is_session_scoped_adapter = True
    return adapter


class _FakeTeamManager:
    """Captures the interact() call; returns a configurable (ok, reason)."""

    def __init__(self, ok: bool = True, reason: str | None = None) -> None:
        self.ok = ok
        self.reason = reason
        self.calls: list[tuple[str, object]] = []

    async def interact(self, session_id: str, user_input: object) -> tuple[bool, str | None]:
        self.calls.append((session_id, user_input))
        return self.ok, self.reason


def _req(**params) -> AgentRequest:
    return AgentRequest(
        request_id="req-1",
        channel_id="tui",
        session_id=params.get("session_id", "sess-1"),
        req_method=None,
        params=params,
    )


@pytest.mark.anyio
async def test_handle_swarmflow_reply_rejects_missing_fields():
    """Missing session_id / correlation_id / answer short-circuits with an error."""
    handler = _make_handler()
    tm = _FakeTeamManager()
    with patch(
        "jiuwenswarm.agents.harness.team.get_team_manager", return_value=tm
    ):
        # No answer -> no interact call, error payload.
        resp = await handler.handle_swarmflow_reply(_req(
            session_id="sess-1",
            run_id="run-1",
            correlation_id="review:host:0",
            answer="",
        ))
    assert resp.ok is False
    assert resp.payload == {"ok": False, "error": "missing session_id/correlation_id/answer"}
    assert tm.calls == []


@pytest.mark.asyncio
async def test_public_reply_uses_shared_exact_owner_without_initializing_agent(monkeypatch):
    reply = AsyncMock(return_value=(True, None))
    monkeypatch.setattr("jiuwenswarm.server.runtime.team_workflow_capabilities.reply_swarmflow", reply)
    agent = JiuWenSwarm()
    agent._ensure_adapter = Mock(side_effect=AssertionError("reply cannot initialize an Agent"))
    request = _req(session_id="sess-1", run_id="run-1", correlation_id="review:host:0", answer=" raw answer ")
    request.req_method = ReqMethod.CHAT_SWARMFLOW_REPLY
    response = await agent.process_message(request)
    assert response.ok and response.payload["ok"]
    assert response.payload["status"] == "input_accepted"
    reply.assert_awaited_once_with(session_id="sess-1", run_id="run-1",
        correlation_id="review:host:0", answer=" raw answer ", channel_id="tui")
    agent._ensure_adapter.assert_not_called()


@pytest.mark.asyncio
async def test_reply_payload_cannot_override_authenticated_session(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr("jiuwenswarm.server.runtime.team_workflow_capabilities.reply_swarmflow", reply)
    handler = _make_handler()
    request = _req(session_id="foreign", run_id="run-1", correlation_id="review:host:0", answer="answer")
    request.session_id = "authenticated-session"
    response = await handler.handle_swarmflow_reply(request)
    assert not response.ok and response.payload["error"] == "swarmflow_reply_session_mismatch"
    reply.assert_not_called()
