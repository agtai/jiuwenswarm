"""Real public adapters share one configured Core Workflow execution owner.

Trusted startup declarations and permission callbacks are controlled host
fixtures; service, provider registry, Workflow graph, checkpoint and Native
decoder are real. No business workflow or physical audio acceptance is claimed.
"""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from openjiuwen.core.runner import Runner
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.inmemory import InMemoryCheckpointer
from openjiuwen.core.workflow import End, Start, Workflow, WorkflowCard, WorkflowComponent

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.live_voice.native_business_tools import native_business_proposal_from_function_call
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.server.runtime.core_workflow_capabilities import CoreWorkflowCapabilities, CoreWorkflowScope
from jiuwenswarm.server.runtime.core_workflow_bootstrap import (
    CoreWorkflowBootstrap, CoreWorkflowDefinition, install_core_workflow_bootstrap,
)
from jiuwenswarm.server.runtime.core_workflow_requests import dispatch_core_workflow_request
from jiuwenswarm.server.runtime.session_execution import SessionExecutionService


@pytest_asyncio.fixture
async def boundary(monkeypatch, tmp_path):
    scope = ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)
    project = str(tmp_path / "project")
    metadata = {"session_id": "session", "channel_id": "web", "user_id": "",
                "project_id": "project", "project_dir": project, "mode": "agent", "work_mode": "work"}
    def read_metadata(*args, **kwargs):
        return deepcopy(metadata)
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata", read_metadata)
    facade, connection = object(), object()
    manager = SimpleNamespace(find_agent_exact=Mock(return_value=facade), pin_agent=Mock(), unpin_agent=Mock(),
                              core_workflow_capabilities=CoreWorkflowCapabilities())
    manager.executions = SessionExecutionService(manager)
    state = SimpleNamespace(web_allowed=True, native_allowed=True, connection_open=True,
                            scope_reads=0, effects=[], calls=[])

    def authorize(**kwargs):
        assert kwargs["connection"] is connection
        assert kwargs["request_user_id"] == ""
        assert kwargs["scope"] == CoreWorkflowScope("web", "session", "project", "agent")
        if not state.web_allowed:
            raise PermissionError("revoked")
        if kwargs["capability"] is None:
            state.scope_reads += 1
        else:
            state.effects.append(kwargs["capability"].required_permissions)
    def install(definitions=(), authorize_web=None):
        bootstrap = CoreWorkflowBootstrap(definitions=definitions,
            select=lambda scope: tuple(item.capability_id for item in definitions),
            authorize_web=authorize if authorize_web is None else authorize_web)
        return install_core_workflow_bootstrap(manager, bootstrap)

    def connection_guard():
        if not state.connection_open:
            raise PermissionError("CORE_WORKFLOW_CONNECTION_CLOSED")
    context = SimpleNamespace(file_path=project)

    def require_native(**kwargs):
        assert kwargs["scope"] == scope
        if not state.native_allowed:
            raise PermissionError("revoked")
    context.require_usable = Mock(side_effect=require_native)
    current = SimpleNamespace(context=context)
    registry = SimpleNamespace(_agent_manager=manager, _stopped=False,
        _p3_composition=SimpleNamespace(_accepting=True, _clock=lambda: "now"))
    router = NativeBusinessRouter(registry)
    router._require_current_context_route = Mock(return_value=None)
    router._require_context_authority = AsyncMock(return_value=current)
    router._require_work_authority = AsyncMock(return_value=current)
    binding = NativeInteractionBinding(scope, "interaction", "activation", 1, "correlation")
    route = SimpleNamespace(binding=binding, native_p3_authority=SimpleNamespace(
        context=context, principal=SimpleNamespace(require_usable=Mock(return_value=None))))
    checkpoint = InMemoryCheckpointer()
    monkeypatch.setattr(CheckpointerFactory, "_default_checkpointer", checkpoint)
    registered = []

    def register(*, interactive=False, authorize_web=None):
        card = WorkflowCard(id="public-entry-fixture", name="Fixture", version="1", input_params={
            "type": "object", "properties": {"text": {"type": "string"}},
            "required": ["text"], "additionalProperties": False})
        workflow = Workflow(card=card)
        workflow.set_start_comp("start", Start(), inputs_schema={"text": "${text}"})

        class Count(WorkflowComponent):
            async def invoke(self, inputs, session, context):
                state.calls.append("node")
                if interactive:
                    return {"text": await session.interact("Choose a value")}
                return {"text": "actual result"}

        workflow.add_workflow_comp("ask", Count())
        workflow.add_connection("start", "ask")
        workflow.set_end_comp("end", End(), inputs_schema={"text": "${ask.text}"})
        workflow.add_connection("ask", "end")
        provider = Mock(return_value=workflow)
        Runner.resource_mgr.add_workflow(card=card, workflow=provider)
        registered.append(card.id)
        install((CoreWorkflowDefinition(capability_id="fixture", card=card, registered_provider=provider,
            required_permissions=("task.execute",),
            continuation_schemas={"ask": {"type": "string", "minLength": 1}}),), authorize_web=authorize_web)
        return provider

    async def web(action, *, request_id="web-request", **params):
        request = AgentRequest(request_id=request_id, channel_id="web", session_id="session",
            req_method=ReqMethod.COMMAND_WORKFLOWS, params={"kind": "core", "action": action, **params})
        return await dispatch_core_workflow_request(manager, request,
            connection=connection, before_read=connection_guard)

    async def native(action, *, call="native-call", **params):
        proposal = native_business_proposal_from_function_call(
            name="jiuwen_core_workflow_" + action,
            arguments=json.dumps({"request_text": "Run the explicitly selected workflow", "context_id": "a" * 64, **params}),
            binding=binding, turn_id="turn", response_generation=1, provider_event_id="event",
            provider_call_id=call, provider_item_id="item")
        return await router._core_workflow(route, proposal)

    async def settle():
        # Original service tasks expose the actual completion, not a fixed sleep.
        entries = manager.executions.list_internal(facade, session_id="session", kind="core_workflow_run")
        await asyncio.gather(*(asyncio.shield(entry.task) for entry in entries), return_exceptions=True)
        await asyncio.sleep(0)

    yield SimpleNamespace(**locals())
    await manager.executions.close()
    for name in registered:
        Runner.resource_mgr.remove_workflow(name)


@pytest.mark.asyncio
async def test_empty_web_directory_still_requires_trusted_connection_scope_authority(boundary):
    b = boundary
    b.install()
    result = await b.web("list")
    assert result.ok and result.payload["capabilities"] == [] and b.state.scope_reads > 0
    b.manager.core_workflow_host = None
    result = await b.web("list")
    assert not result.ok and result.payload["reason"] == "CORE_WORKFLOW_AUTHORITY_UNAVAILABLE"
    assert b.manager.executions._records == {} and b.state.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["web", "native"])
async def test_both_entries_start_and_observe_same_real_run_without_replaying(origin, boundary):
    b = boundary
    provider = b.register()
    listing = await b.native("list")
    args = dict(epoch=listing["epoch"], capability_id="fixture", inputs={"text": "original"})
    if origin == "web":
        first = (await b.web("start", **args)).payload
    else:
        first = await b.native("start", **args)
    assert first["status"] == "accepted" and first["business_completion"] is False
    await b.settle()
    observed = await b.native("get", epoch=listing["epoch"], target_id=first["run_id"])
    web_observed = await b.web("get", epoch=listing["epoch"], run_id=first["run_id"])
    assert web_observed.ok and web_observed.payload == observed
    assert observed["business_completion"] is True and observed["sdk_state"] == "COMPLETED"
    assert observed["result"] == {"output": {"text": "actual result"}}
    replay = ((await b.web("start", **args)).payload if origin == "web" else await b.native("start", **args))
    assert replay == first and b.state.calls == ["node"]
    provider.assert_called_once()
    assert b.checkpoint._workflow_stores == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"epoch": "old-process"}, {"inputs": {"text": 4}}, {"capability_id": "guessed"},
    {"required_permissions": []}, {"inputs": {"text": "valid"}, "model_name": "override"},
])
async def test_invalid_web_start_has_zero_provider_node_and_checkpoint_effects(boundary, changes):
    b = boundary
    provider = b.register()
    values = dict(epoch=b.manager.executions.execution_epoch, capability_id="fixture", inputs={"text": "valid"})
    result = await b.web("start", **{**values, **changes})
    assert not result.ok and result.payload["status"] == "rejected"
    provider.assert_not_called()
    assert b.state.calls == [] and b.checkpoint._workflow_stores == {}
    assert b.manager.executions._records == {}


@pytest.mark.asyncio
async def test_native_wrong_stored_project_and_revoked_grant_do_not_start(boundary):
    b = boundary
    provider = b.register()
    args = dict(epoch=b.manager.executions.execution_epoch, capability_id="fixture", inputs={"text": "valid"})
    b.metadata["project_id"] = "other"
    with pytest.raises(ValueError, match="EXECUTION_CONTEXT_SCOPE_MISMATCH"):
        await b.native("start", **args)
    b.metadata["project_id"] = "project"
    b.state.native_allowed = False
    with pytest.raises(PermissionError):
        await b.native("start", **args)
    provider.assert_not_called()
    assert b.manager.executions._records == {} and b.state.calls == []


@pytest.mark.asyncio
async def test_revocation_after_admission_prevents_actual_provider_for_both_entries(boundary):
    b = boundary
    provider = b.register()
    result = await b.web("start", epoch=b.manager.executions.execution_epoch,
                         capability_id="fixture", inputs={"text": "valid"})
    assert result.ok
    b.state.web_allowed = False
    await b.settle()
    provider.assert_not_called()
    assert b.state.calls == [] and b.checkpoint._workflow_stores == {}
    observed = await b.native("get", epoch=b.manager.executions.execution_epoch, target_id=result.payload["run_id"])
    assert observed["failure_reason"] == "permission_denied" and not observed["business_completion"]


@pytest.mark.asyncio
@pytest.mark.parametrize("permission_retained", [True, False])
async def test_admitted_native_workflow_outlives_speech_but_keeps_current_grant(boundary, permission_retained):
    b = boundary
    provider = b.register()
    receipt = await b.native("start", epoch=b.manager.executions.execution_epoch,
                             capability_id="fixture", inputs={"text": "valid"})
    assert receipt["status"] == "accepted"
    b.router._require_current_context_route.side_effect = PermissionError("speech closed")
    b.state.native_allowed = permission_retained
    await b.settle()
    # Read through the still-authorized independent Web entry after the old
    # speech carrier closes. The actual registered Workflow remains its owner.
    result = await b.web("get", epoch=b.manager.executions.execution_epoch, run_id=receipt["run_id"])
    assert result.ok and result.payload["business_completion"] is permission_retained
    if permission_retained:
        provider.assert_called_once()
        assert b.state.calls == ["node"]
    else:
        provider.assert_not_called()
        assert b.state.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id", ["../private", "..\\private", "bad/session", None])
async def test_web_rejects_invalid_session_before_metadata_io(boundary, monkeypatch, session_id):
    b = boundary
    read = Mock(side_effect=AssertionError("invalid identity reached storage"))
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata", read)
    request = AgentRequest(request_id="bad", channel_id="web", session_id=session_id,
                           params={"kind": "core", "action": "list"})
    result = await dispatch_core_workflow_request(b.manager, request,
        connection=b.connection, before_read=b.connection_guard)
    assert not result.ok and result.payload["reason"] == "CORE_WORKFLOW_REQUEST_INVALID"
    read.assert_not_called()
    assert b.state.scope_reads == 0


@pytest.mark.asyncio
async def test_actual_web_handler_routes_core_and_rejects_unknown_family(boundary, monkeypatch):
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    b = boundary
    b.install()
    server = AgentWebSocketServer.__new__(AgentWebSocketServer)
    server._agent_manager = b.manager
    server._current_ws, server._current_ws_done = b.connection, asyncio.Event()
    sent = AsyncMock()
    legacy = AsyncMock(side_effect=AssertionError("Core/unknown family reached SwarmFlow"))
    monkeypatch.setattr("jiuwenswarm.server.runtime.workflow_queries.query_workflows", legacy)
    monkeypatch.setattr("jiuwenswarm.server.agent_ws_server.encode_agent_response_for_wire", lambda response, **kwargs: response)
    monkeypatch.setattr("jiuwenswarm.server.agent_ws_server.send_wire_payload", sent)
    for kind in ("core", "Core", "unknown", None):
        request = AgentRequest(request_id="route", channel_id="web", session_id="session",
            req_method=ReqMethod.COMMAND_WORKFLOWS, params={"kind": kind, "action": "list"})
        await server._handle_command_workflows(b.connection, request, asyncio.Lock())
        response = sent.await_args.args[1]
        assert response.ok is (kind == "core")
        if kind != "core":
            assert response.payload["reason"] == "WORKFLOW_KIND_INVALID"
    legacy.assert_not_awaited()
    assert b.state.scope_reads > 0 and b.manager.executions._records == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("start_origin", ["web", "native"])
async def test_actual_strict_resume_competition_between_web_and_native_consumes_one_answer(boundary, start_origin):
    b = boundary
    provider = b.register(interactive=True)
    epoch = b.manager.executions.execution_epoch
    args = dict(epoch=epoch, capability_id="fixture", inputs={"text": "question"})
    started = ((await b.web("start", **args)).payload if start_origin == "web" else await b.native("start", **args))
    entry, = b.manager.executions.list_internal(b.facade, session_id="session", kind="core_workflow_run")
    async with asyncio.timeout(2):
        while entry.capability_state.inbox is None:
            if entry.task.done():
                await entry.task
                pytest.fail("workflow ended before its actual pending input")
            await entry.changed.wait()
    pending = await b.native("get", epoch=epoch, target_id=started["run_id"])
    assert pending["sdk_state"] == "INPUT_REQUIRED" and pending["business_completion"] is False
    assert pending["pending"] == [{"id": "ask", "value": "Choose a value"}]
    answers = await asyncio.gather(
        b.web("resume", request_id="web-answer", epoch=epoch, run_id=started["run_id"],
              expected_revision=pending["revision"], answers={"ask": "from web"}),
        b.native("resume", call="native-answer", epoch=epoch, target_id=started["run_id"],
                 expected_revision=pending["revision"], answers={"ask": "from native"}),
        return_exceptions=True)
    accepted = [item for item in answers if (isinstance(item, dict) and item.get("status") == "accepted")
                or (getattr(item, "ok", False) and item.payload["status"] == "accepted")]
    assert len(accepted) == 1
    await b.settle()
    result = await b.native("get", epoch=epoch, target_id=started["run_id"])
    assert result["business_completion"] and result["result"]["output"]["text"] in {"from web", "from native"}
    # The interrupted component re-enters once to read its answer. The losing
    # answer and accepted-control replay cannot enter it a third time.
    assert b.state.calls == ["node", "node"]
    if getattr(answers[0], "ok", False):
        replay = await b.web("resume", request_id="web-answer", epoch=epoch, run_id=started["run_id"],
                             expected_revision=pending["revision"], answers={"ask": "from web"})
        assert replay.ok and replay.payload == answers[0].payload
    else:
        replay = await b.native("resume", call="native-answer", epoch=epoch, target_id=started["run_id"],
                                expected_revision=pending["revision"], answers={"ask": "from native"})
        assert replay == answers[1]
    assert b.state.calls == ["node", "node"]
    provider.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("session_id,accepted", [("session", True), ("other", False)])
async def test_web_envelope_and_explicit_session_parameter_must_agree(boundary, session_id, accepted):
    b = boundary
    b.install()
    result = await b.web("list", session_id=session_id)
    assert result.ok is accepted
    assert b.state.calls == []
    assert not b.manager.executions._records


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"user_id": "foreign"}, {"channel_id": "im"},
    {"project_id": "foreign"}, {"mode": "team"}, {"work_mode": "code"}])
async def test_web_owner_lookup_race_cannot_bind_or_execute_capability(boundary, monkeypatch, changes):
    from jiuwenswarm.server.runtime.agent_resolution import find_session_agent

    b = boundary
    provider = b.register()
    async def lookup(*args, **kwargs):
        owner = await find_session_agent(*args, **kwargs)
        b.metadata.update(changes)
        return owner
    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_resolution.find_session_agent", lookup)
    result = await b.web("start", epoch=b.manager.executions.execution_epoch,
                         capability_id="fixture", inputs={"text": "valid"})
    assert not result.ok and result.payload["reason"] == "CORE_WORKFLOW_SESSION_MISMATCH"
    provider.assert_not_called()
    assert b.manager.core_workflow_capabilities.list(CoreWorkflowScope("web", "session", "project", "agent")) == ()
    assert b.state.scope_reads == 0 and b.state.calls == []
    assert b.manager.executions._records == {} and b.checkpoint._workflow_stores == {}


@pytest.mark.asyncio
async def test_actual_server_bootstrap_shares_native_run_and_rejects_foreign_gateway_user(boundary, monkeypatch):
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    b = boundary
    provider = b.register()
    bootstrap = b.manager.core_workflow_host.bootstrap
    monkeypatch.setattr(AgentWebSocketServer, "_instance", None)
    server = AgentWebSocketServer.get_instance(core_workflow_bootstrap=bootstrap)
    assert AgentWebSocketServer.get_instance() is server
    assert AgentWebSocketServer.get_instance(core_workflow_bootstrap=bootstrap) is server
    other = CoreWorkflowBootstrap(definitions=(), select=lambda scope: (), authorize_web=b.authorize)
    with pytest.raises(ValueError, match="CORE_WORKFLOW_BOOTSTRAP_ALREADY_CREATED"):
        AgentWebSocketServer.get_instance(core_workflow_bootstrap=other)
    manager = server._agent_manager
    manager.find_agent_exact = Mock(return_value=b.facade)
    b.registry._agent_manager = manager
    server._current_ws, server._current_ws_done = b.connection, asyncio.Event()
    sent = AsyncMock()
    monkeypatch.setattr("jiuwenswarm.server.agent_ws_server.encode_agent_response_for_wire", lambda response, **kwargs: response)
    monkeypatch.setattr("jiuwenswarm.server.agent_ws_server.send_wire_payload", sent)
    async def web(action, *, user_id="", **params):
        request = AgentRequest(request_id="server-" + action, channel_id="web", session_id="session", user_id=user_id,
            req_method=ReqMethod.COMMAND_WORKFLOWS, params={"kind": "core", "action": action, **params})
        await server._handle_command_workflows(b.connection, request, asyncio.Lock())
        return sent.await_args.args[1]
    try:
        rejected = await web("list", user_id="foreign")
        assert not rejected.ok and rejected.payload["reason"] == "CORE_WORKFLOW_SESSION_MISMATCH"
        assert manager.core_workflow_capabilities.list(CoreWorkflowScope("web", "session", "project", "agent")) == ()
        listing = await web("list")
        assert listing.ok and [item["capability_id"] for item in listing.payload["capabilities"]] == ["fixture"]
        provider.assert_not_called()
        receipt = await b.native("start", epoch=listing.payload["epoch"], capability_id="fixture", inputs={"text": "actual"})
        entry, = manager.executions.list_internal(b.facade, session_id="session", kind="core_workflow_run")
        await asyncio.shield(entry.task)
        observed = await web("get", epoch=listing.payload["epoch"], run_id=receipt["run_id"])
        assert observed.ok and observed.payload["business_completion"]
        assert observed.payload["result"] == {"output": {"text": "actual result"}}
        provider.assert_called_once()
        server._current_ws_done.set()
        disconnected = await web("get", epoch=listing.payload["epoch"], run_id=receipt["run_id"])
        assert not disconnected.ok and disconnected.payload["reason"] == "CORE_WORKFLOW_CONNECTION_CLOSED"
        assert b.state.calls == ["node"]
    finally:
        await manager.cleanup()
    with pytest.raises(ValueError, match="bootstrap_revoked"):
        manager.core_workflow_host.guard(CoreWorkflowScope("web", "session", "project", "agent"), "list", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("middle", [{"mode": "code.normal", "work_mode": "code"},
    {"project_id": "foreign"}, {"mode": "team"}])
async def test_web_aba_metadata_cannot_select_intermediate_owner(boundary, monkeypatch, middle):
    b = boundary
    # A grant can cover multiple configured capabilities. It must not hide a
    # session-identity defect by rejecting the intermediate mode in this fixture.
    provider = b.register(authorize_web=lambda **kwargs: None)
    reads = 0
    def read(*args, **kwargs):
        nonlocal reads
        reads += 1
        return {**b.metadata, **(middle if reads == 2 else {})}
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata", read)
    result = await b.web("start", epoch=b.manager.executions.execution_epoch,
                         capability_id="fixture", inputs={"text": "valid"})
    assert not result.ok and result.payload["reason"] == "CORE_WORKFLOW_SESSION_MISMATCH"
    provider.assert_not_called()
    assert b.state.scope_reads == 0 and b.state.calls == []
    assert b.manager.core_workflow_capabilities._entries == {}
    assert b.manager.executions._records == {} and b.checkpoint._workflow_stores == {}
