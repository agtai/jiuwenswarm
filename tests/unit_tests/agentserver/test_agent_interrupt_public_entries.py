"""Public input admission uses exact stored scope before the actual shared service."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.agent_interrupt_requests import dispatch_agent_input_request
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService


@pytest_asyncio.fixture
async def boundary(monkeypatch, tmp_path):
    metadata = {"session_id": "session", "channel_id": "web", "user_id": "alice",
                "project_dir": str(tmp_path), "project_id": "project", "mode": "agent", "work_mode": "work"}
    reader = Mock(side_effect=lambda *args, **kwargs: deepcopy(metadata))
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata", reader)
    agent = object()
    manager = SimpleNamespace(find_agent_exact=Mock(return_value=agent), pin_agent=Mock(), unpin_agent=Mock())
    manager.executions = SessionExecutionService(manager)
    guard = Mock(return_value=None)

    def request(**changes):
        return AgentRequest(**dict({"request_id": "reply-rpc", "channel_id": "web", "session_id": "session",
            "user_id": "alice", "req_method": ReqMethod.COMMAND_AGENT_INPUT,
            "params": {"action": "list", "session_id": "session"}}, **changes))

    yield SimpleNamespace(**locals())
    # A rejected reply may retain its short RPC replay record. It must not
    # allocate Agent work or create an SDK/output owner.
    assert all(entry.control_only and entry.prepared_work is None and entry.output_owner is None
               for entry in manager.executions._records.values())
    assert await manager.executions.close()
    assert manager.pin_agent.call_args_list == manager.unpin_agent.call_args_list


@pytest.mark.asyncio
async def test_empty_web_directory_is_real_authorized_observation_without_owner_creation(boundary):
    b = boundary
    response = await dispatch_agent_input_request(b.manager, b.request(), before_effect=b.guard)
    assert response.ok and response.payload["pending"] == []
    assert b.guard.call_count >= 2
    assert b.manager.find_agent_exact.call_args.kwargs == {
        "channel_id": "web", "mode": "agent", "project_dir": b.metadata["project_dir"], "sub_mode": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["../foreign", "bad/session", "", "x\x00"])
async def test_invalid_session_rejects_before_any_metadata_io(boundary, session_id):
    b = boundary
    response = await dispatch_agent_input_request(b.manager, b.request(session_id=session_id,
        params={"action": "list", "session_id": session_id}), before_effect=b.guard)
    assert not response.ok
    b.reader.assert_not_called()
    b.manager.find_agent_exact.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"user_id": "bob"}, {"user_id": ""}, {"channel_id": "im"},
    {"params": {"action": "list", "session_id": "other"}},
    {"params": {"action": "list", "session_id": "session", "authorized": True}}])
async def test_foreign_identity_or_wire_authority_rejects_without_dispatch(boundary, changes):
    b = boundary
    response = await dispatch_agent_input_request(b.manager, b.request(**changes), before_effect=b.guard)
    assert not response.ok
    b.manager.find_agent_exact.assert_not_called()


@pytest.mark.asyncio
async def test_scope_read_wait_cannot_retain_revoked_connection_authority(boundary):
    b = boundary
    allowed = [True]
    def guard():
        if not allowed[0]:
            raise PermissionError("AGENT_INPUT_CONNECTION_CLOSED")
    def read(*args, **kwargs):
        allowed[0] = False
        return deepcopy(b.metadata)
    b.reader.side_effect = read
    response = await dispatch_agent_input_request(b.manager, b.request(), before_effect=guard)
    assert not response.ok and response.payload["reason"] == "AGENT_INPUT_CONNECTION_CLOSED"


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [{"user_id": "bob"}, {"channel_id": "im"}, {"mode": "team"}])
async def test_owner_lookup_wait_cannot_retain_old_stored_scope(boundary, monkeypatch, changed):
    from jiuwenswarm.server.runtime.agent_resolution import find_session_agent
    b = boundary
    async def lookup(*args, **kwargs):
        owner = await find_session_agent(*args, **kwargs)
        b.metadata.update(changed)
        return owner
    observe = Mock(side_effect=AssertionError("Stale authority must not read pending inputs"))
    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_resolution.find_session_agent", lookup)
    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_interrupt_execution.list_agent_interrupts", observe)
    response = await dispatch_agent_input_request(b.manager, b.request(), before_effect=b.guard)
    assert not response.ok and response.payload["reason"] == "AGENT_INPUT_SESSION_MISMATCH"
    observe.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [False, True, "allow"])
async def test_authority_callback_must_return_none(boundary, value):
    b = boundary
    response = await dispatch_agent_input_request(b.manager, b.request(), before_effect=lambda: value)
    assert not response.ok
    b.reader.assert_not_called()


@pytest.mark.asyncio
async def test_unobserved_reply_is_unavailable_without_new_work(boundary):
    b = boundary
    response = await dispatch_agent_input_request(b.manager, b.request(params={
        "action": "reply", "session_id": "session", "source_binding_id": "invented-binding",
        "source_task_id": "invented-task", "pending_token": "invented-token", "input_id": "invented-input",
        "answers": [{"selected_options": ["approve"]}],
    }), before_effect=b.guard)
    assert not response.ok and response.payload["accepted"] is False


@pytest.mark.asyncio
async def test_actual_web_handler_rejects_retired_connection_before_metadata(boundary, monkeypatch):
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
    b = boundary
    send = AsyncMock()
    monkeypatch.setattr("jiuwenswarm.server.agent_ws_server.send_wire_payload", send)
    server = AgentWebSocketServer.__new__(AgentWebSocketServer)
    server._agent_manager = b.manager
    server._current_ws = object()
    server._current_ws_done = asyncio.Event()
    await server._handle_command_agent_input(object(), b.request(), asyncio.Lock())
    b.reader.assert_not_called()
    wire = send.call_args.args[1]
    assert "AGENT_INPUT_CONNECTION_CLOSED" in str(wire)
