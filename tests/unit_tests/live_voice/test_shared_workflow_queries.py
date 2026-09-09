"""The Native adapter reads the same session owner as the existing text RPC."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessViolation
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.runtime.workflow_queries import query_workflows


def request(session="session", **params):
    return AgentRequest(request_id="text-query", channel_id="web", session_id=session,
                        req_method=ReqMethod.COMMAND_WORKFLOWS, params=params)


@pytest.fixture
def owner(monkeypatch):
    reads = []
    snapshots = {"session": [{"id": "workflow-a", "name": "Report", "status": "completed"}],
                 "other": [{"id": "workflow-b", "name": "Other report", "status": "running"}]}
    def handler(session):
        reads.append(session)
        return SimpleNamespace(get_workflow_snapshot=lambda: snapshots[session])
    manager = SimpleNamespace(get_workflow_handler=handler)
    monkeypatch.setattr("jiuwenswarm.agents.harness.team.get_team_manager", lambda channel: manager)
    return reads


@pytest.mark.asyncio
async def test_native_and_text_read_same_workflow_owner_with_no_executor(owner):
    router = NativeBusinessRouter(SimpleNamespace())
    router._require_context_authority = AsyncMock()
    route = SimpleNamespace(binding=SimpleNamespace(scope=ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)))
    for operation, target in (("list", None), ("get", "workflow-a")):
        delegate = SimpleNamespace(source_identity="native-query",
            business=NativeBusinessAction("workflow." + operation, "a" * 64, target, None, None, None, None))
        voice = await router._workflow(route, delegate)
        text = await query_workflows(request(action=operation, workflow_id=target))
        assert text.ok and voice == text.payload
    assert owner == ["session"] * 4
    assert router._work_owner is None
    assert router._require_context_authority.await_count == 4
    rejected = await query_workflows(request("other", action="get", workflow_id="workflow-a"))
    assert not rejected.ok and "workflow not found" in rejected.payload["error"]


@pytest.mark.asyncio
async def test_native_authority_rejection_has_zero_reads_and_rechecks_after_read(owner):
    router = NativeBusinessRouter(SimpleNamespace())
    route = SimpleNamespace(binding=SimpleNamespace(scope=ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)))
    delegate = SimpleNamespace(source_identity="native-query",
        business=NativeBusinessAction("workflow.list", "a" * 64, None, None, None, None, None))
    router._require_context_authority = AsyncMock(side_effect=NativeBusinessViolation("RETIRED"))
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await router._workflow(route, delegate)
    assert owner == [] and router._work_owner is None
    router._require_context_authority = AsyncMock(side_effect=[None, NativeBusinessViolation("RETIRED")])
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await router._workflow(route, delegate)
    assert owner == ["session"] and router._work_owner is None


@pytest.mark.asyncio
async def test_checkpoint_read_runs_off_event_loop_and_failure_is_truthful(monkeypatch):
    monkeypatch.setattr("jiuwenswarm.agents.harness.team.get_team_manager",
                        lambda channel: SimpleNamespace(get_workflow_handler=lambda session: None))
    def restore(session, *, strict):
        assert strict
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        raise OSError("unavailable checkpoint")
    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_adapter.team_helpers.restore_workflow_runs", restore)
    result = await query_workflows(request(action="list"))
    assert not result.ok
    assert result.payload["error"] == "WORKFLOW_OBSERVATION_UNAVAILABLE"
    assert "workflows" not in result.payload


@pytest.mark.asyncio
@pytest.mark.parametrize("req", [request(session=""), request(action="execute"), request(action="get")])
async def test_invalid_query_does_not_touch_workflow_owner(owner, req):
    result = await query_workflows(req)
    assert not result.ok and owner == []


@pytest.fixture
def checkpoint(monkeypatch, tmp_path):
    from jiuwenswarm.server.runtime.session import session_metadata as metadata
    monkeypatch.setattr("jiuwenswarm.agents.harness.team.get_team_manager",
        lambda channel: SimpleNamespace(get_workflow_handler=lambda session: None))
    monkeypatch.setattr(metadata, "get_agent_sessions_dir", lambda: tmp_path)
    write = Mock(side_effect=AssertionError("observation wrote checkpoint"))
    monkeypatch.setattr(metadata, "_write_metadata_sync", write)
    directory = tmp_path / "session"
    directory.mkdir()
    path = directory / "metadata.json"
    path.write_text(json.dumps({"workflow_runs": {"run-a": {
        "id": "run-a", "name": "Report", "status": "completed", "result": "saved"}}}), encoding="utf-8")
    return path, write


@pytest.mark.asyncio
async def test_real_checkpoint_query_returns_workflow_and_does_not_write(checkpoint):
    path, write = checkpoint
    before = path.read_bytes()
    result = await query_workflows(request(action="list"))
    assert result.ok and result.payload["workflows"][0]["id"] == "run-a"
    detail = await query_workflows(request(action="get", workflow_id="run-a"))
    assert detail.ok and "saved" in json.dumps(detail.payload)
    assert path.read_bytes() == before
    write.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["", "{broken", "[]", '{"workflow_runs": []}', '{"workflow_runs": null}', '{"workflow_runs": {"bad": 4}}'],
    ids=["empty", "corrupt-json", "nonobject", "invalid-inventory", "null-inventory", "invalid-record"])
async def test_real_corrupt_checkpoint_is_unavailable_with_zero_repairs(checkpoint, raw):
    path, write = checkpoint
    path.write_text(raw, encoding="utf-8")
    before = path.read_bytes()
    result = await query_workflows(request(action="list"))
    assert not result.ok and result.payload["error"] == "WORKFLOW_OBSERVATION_UNAVAILABLE"
    assert "workflows" not in result.payload
    assert path.read_bytes() == before
    write.assert_not_called()


@pytest.mark.asyncio
async def test_real_checkpoint_io_failure_is_unavailable_and_legacy_restore_stays_compatible(checkpoint, monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.team_helpers import restore_workflow_runs
    path, write = checkpoint
    original = Path.read_text
    def unavailable(target, *args, **kwargs):
        if target == path:
            raise PermissionError("checkpoint unavailable")
        return original(target, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", unavailable)
    result = await query_workflows(request(action="list"))
    assert not result.ok and result.payload["error"] == "WORKFLOW_OBSERVATION_UNAVAILABLE"
    assert restore_workflow_runs("session") is None
    write.assert_not_called()


@pytest.mark.asyncio
async def test_missing_checkpoint_is_empty_without_creating_session_directory(checkpoint):
    path, write = checkpoint
    result = await query_workflows(request("absent", action="list"))
    assert result.ok and result.payload["workflows"] == []
    assert not (path.parent.parent / "absent").exists()
    write.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt_root", [False, True])
async def test_file_instead_of_session_directory_is_unavailable(checkpoint, monkeypatch, corrupt_root):
    from jiuwenswarm.server.runtime.session import session_metadata as metadata
    path, write = checkpoint
    corrupted = path.parent.parent / "corrupted"
    corrupted.write_text("not a directory", encoding="utf-8")
    if corrupt_root:
        monkeypatch.setattr(metadata, "get_agent_sessions_dir", lambda: corrupted)
    result = await query_workflows(request("corrupted", action="list"))
    assert not result.ok and result.payload["error"] == "WORKFLOW_OBSERVATION_UNAVAILABLE"
    assert corrupted.read_text(encoding="utf-8") == "not a directory"
    write.assert_not_called()
