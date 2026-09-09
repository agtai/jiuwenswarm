"""Native Goal router/service/SDK control seam, using a controlled lower facade.

No model/provider or production Deep/rails cutover is credited by these tests.
"""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from openjiuwen.core.session.agent import create_agent_session
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.inmemory import InMemoryCheckpointer
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from openjiuwen.harness.deep_agent import DeepAgent
from openjiuwen.harness.goal.manager import GoalManager
from openjiuwen.harness.goal.schema import GoalOperationError
from openjiuwen.harness.goal.store import SessionGoalStore

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.live_voice.native_business_contract import (
    NativeBusinessAction, NativeBusinessProposal, NativeBusinessViolation,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.runtime.execution_context import AgentExecutionPolicy
from jiuwenswarm.server.runtime.session_execution import (
    SessionExecutionService, current_output_observer, prepare_current_work,
)

pytestmark = pytest.mark.asyncio


class ControlledGoalFacade:
    def __init__(self, sdk):
        self.sdk = sdk
        self.requests = []
        self.works = []
        self.errors = []
        self.entered = asyncio.Event()

    async def process_message_stream(self, request):
        self.requests.append(deepcopy(request))
        _, work = prepare_current_work(sdk_agent=self.sdk, session_id="session",
            apply_runtime=Mock(return_value=None))
        self.works.append(work)
        stream = None
        self.entered.set()
        try:
            if request.params.get("action") == "attach":
                stream = await self.sdk.attach_output(on_output_ready=current_output_observer(self.sdk))
                yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
                    payload={"event_type": "chat.delta", "content": "text reader"})
            else:
                controls = {key: request.params[key] for key in (
                    "expected_goal_id", "expected_control_revision", "overwrite_confirmed") if key in request.params}
                controls.update(before_effect=work.policy.before_effect, run_context=work.run_context(),
                    on_output_ready=current_output_observer(self.sdk))
                if request.params["action"] == "set":
                    record, stream = await self.sdk.set_goal(request.params["objective"], **controls)
                else:
                    # Match the production adapter's ACTIVE-resume behavior:
                    # retain its current binding rather than replacing it.
                    current = self.sdk.goal_manager.peek()
                    if current is not None and current.status.value == "active":
                        controls.pop("run_context")
                    record, stream = await self.sdk.resume_goal(**controls)
                snapshot = record.to_dict()
                snapshot.pop("run_context", None)
                yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
                    payload={"event_type": "goal.snapshot", "goal": snapshot})
            if stream is not None:
                async for payload in stream:
                    yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id, payload=payload)
        except (GoalOperationError, NativeBusinessViolation, PermissionError) as error:
            yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
                payload={"event_type": "chat.error", "code": getattr(error, "code", None) or str(error)})
        except Exception as error:
            self.errors.append(repr(error))
            raise
        finally:
            if stream is not None:
                await stream.close(abort_active_round=False)


@pytest_asyncio.fixture
async def boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(CheckpointerFactory, "_default_checkpointer", InMemoryCheckpointer())
    card = AgentCard(id="controlled-goal", name="Goal owner", description="fixture")
    sdk = DeepAgent(card)
    sdk._interaction_started = True
    session = create_agent_session(session_id="session", card=card)
    await session.pre_run()
    sdk._cancel_active_round = AsyncMock()
    sdk._notify_work = Mock()
    sdk._emit_interaction_event = Mock()
    sdk.goal_manager = GoalManager(store=SessionGoalStore(session), event_manager=sdk._event_manager,
        control_lock=sdk._interaction_control_lock, has_output_stream=sdk.has_output_stream,
        cancel_active_round=sdk._cancel_active_round, notify_work=sdk._notify_work,
        emit_event=sdk._emit_interaction_event)
    facade = ControlledGoalFacade(sdk)
    project = str(tmp_path / "project")
    manager = SimpleNamespace(find_agent_exact=Mock(return_value=facade), pin_agent=Mock(), unpin_agent=Mock(),
        get_agent=AsyncMock(side_effect=AssertionError("must never construct a Native Goal agent")))
    manager.executions = SessionExecutionService(manager)
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata",
        lambda *args, **kwargs: {"project_dir": project, "work_mode": "code", "mode": "agent.plan"})
    scope = ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)
    context = SimpleNamespace(file_path=project, require_usable=Mock())
    current = SimpleNamespace(context=context)
    model = Mock(return_value=None)
    registry = SimpleNamespace(_agent_manager=manager,
        _p3_composition=SimpleNamespace(_model_resolver=SimpleNamespace(resolve=model), _clock=lambda: "now"))
    router = NativeBusinessRouter(registry)
    selection = router.contexts.select(scope=scope, history=[], tasks=[], works=[], model={})
    state = SimpleNamespace(revoked=False, drift=False, carrier_closed=False)
    route = SimpleNamespace(binding=SimpleNamespace(scope=scope, session_id=scope.session_id),
        native_p3_authority=SimpleNamespace(context=context, model_identity="model#0", model_config_version="v1",
            principal=SimpleNamespace(require_usable=Mock())))

    async def require_authority(_route):
        if state.revoked:
            raise PermissionError("grant revoked")
        return current

    def recheck(_route, _current):
        if state.carrier_closed:
            raise NativeBusinessViolation("ACTIVATION_RETIRED")

    def resolve_model(*args, **kwargs):
        if state.drift:
            raise PermissionError("model drift")

    model.side_effect = resolve_model
    router._require_context_authority = AsyncMock(side_effect=require_authority)
    router._require_work_authority = AsyncMock(side_effect=require_authority)
    router._recheck_context_authority = Mock(side_effect=recheck)
    bundle = SimpleNamespace(router=router, route=route, sdk=sdk, session=session, facade=facade,
        manager=manager, scope=scope, selection=selection, state=state, model=model, project=project)
    yield bundle
    assert await manager.executions.close(timeout=2)
    await asyncio.sleep(0)
    await session.post_run()


def delegate(boundary, operation="goal.set", *, target=None, revision=None, identity="native-create"):
    action = NativeBusinessAction(operation, boundary.selection.context_id, target, revision,
        None, "Investigate the explicit source requirements." if operation == "goal.set" else None, None)
    assert boundary.router.contexts.require(boundary.scope, action) is boundary.selection
    return NativeBusinessProposal(binding=NativeInteractionBinding(boundary.scope,
        "interaction", "activation", 1, "correlation"), turn_id="turn", response_generation=1,
        provider_event_id="event", provider_call_id=identity, provider_item_id="item",
        request_text="Investigate the explicit source requirements.", business=action)


def effects(boundary):
    sdk = boundary.sdk
    record = sdk.goal_manager.peek()
    return (None if record is None else record.to_dict(), deepcopy(boundary.session.get_state()),
        sdk._notify_work.call_count, sdk._emit_interaction_event.call_count,
        sdk._cancel_active_round.await_count, sdk._interaction_output.current_token(),
        sdk._event_manager.has_pending_work())


async def test_native_goal_uses_stored_code_owner_and_returns_control_receipt_not_completion(boundary):
    b = boundary
    result = await b.router._goal(b.route, delegate(b))
    assert result["status"] == "accepted", (result, b.facade.errors)
    assert result["goal"]["status"] == "active"
    assert "completed" not in result and "result_text" not in result
    assert b.sdk._event_manager.has_pending_work()
    entry = next(iter(b.manager.executions._records.values()))
    assert not entry.task.done() and entry.retained
    req = b.facade.requests[0]
    assert req.params["mode"] == "code.plan" and req.params["work_mode"] == "code"
    assert req.params["project_dir"] == b.project and req.params["model_name"] == "model#0"
    assert req.metadata == {"enable_memory": False, "skip_a2ui": True}
    assert isinstance(entry.policy, AgentExecutionPolicy)
    assert entry.policy.origin == "native" and entry.policy.tool_policy == "read_only"
    assert entry.policy.model_config_version == "v1"
    b.manager.find_agent_exact.assert_called_once_with(channel_id="web", mode="code",
        project_dir=b.project, sub_mode="plan")
    b.manager.get_agent.assert_not_awaited()
    b.model.assert_called_once_with("model#0", expected_identity="model#0",
        expected_config_version="v1", instantiate=False)
    again = await b.router._goal(b.route, delegate(b))
    assert again["status"] == "accepted"
    assert len(b.facade.requests) == 1


@pytest.mark.parametrize("failure", ["wrong_id", "stale_revision", "create_over_existing"])
async def test_rejected_goal_target_has_zero_sdk_mutation(boundary, failure):
    b = boundary
    result = await b.router._goal(b.route, delegate(b))
    goal = result["goal"]
    before = effects(b)
    target = "wrong-goal" if failure == "wrong_id" else goal["goal_id"]
    revision = goal["control_revision"] + (1 if failure == "stale_revision" else 0)
    if failure == "create_over_existing":
        target = revision = None
    rejected = await b.router._goal(b.route, delegate(b, target=target, revision=revision, identity="rejected"))
    assert rejected["status"] == "rejected"
    assert effects(b) == before


async def test_exact_goal_replacement_reuses_reader_and_replaces_sdk_objective(boundary):
    b = boundary
    created = await b.router._goal(b.route, delegate(b))
    original = next(iter(b.manager.executions._records.values()))
    token = b.sdk._interaction_output.current_token()
    old_goal = created["goal"]
    command = delegate(b, target=old_goal["goal_id"], revision=old_goal["control_revision"], identity="replace")
    result = await b.router._goal(b.route, command)
    assert result["status"] == "accepted"
    assert result["goal"]["goal_id"] != old_goal["goal_id"]
    assert b.sdk._interaction_output.current_token() == token
    newest = list(b.manager.executions._records.values())[-1]
    await asyncio.wait_for(newest.task, 2)
    assert newest.output_owner is original and original.retained and not original.task.done()
    b.sdk._cancel_active_round.assert_awaited_once_with(expected_run_kind="goal",
        expected_goal_id=old_goal["goal_id"], reason="goal_overwrite")


@pytest.mark.parametrize("failure", ["wrong_project", "absent_configured_owner"])
async def test_unavailable_configured_owner_never_creates_sdk_goal_or_service_record(boundary, failure):
    from jiuwenswarm.server.runtime.agent_resolution import SessionAgentUnavailable

    b = boundary
    before = effects(b)
    if failure == "wrong_project":
        b.route.native_p3_authority.context.file_path += "-different"
    else:
        b.manager.find_agent_exact.return_value = None
    with pytest.raises(SessionAgentUnavailable):
        await b.router._goal(b.route, delegate(b))
    assert effects(b) == before
    assert not b.manager.executions._records
    assert b.facade.requests == []
    b.manager.get_agent.assert_not_awaited()


async def test_resume_uses_exact_control_revision_and_preserves_actual_output_owner(boundary):
    b = boundary
    result = await b.router._goal(b.route, delegate(b))
    goal = result["goal"]
    paused = await b.sdk.goal_manager.pause(expected_goal_id=goal["goal_id"],
        expected_control_revision=goal["control_revision"])
    original = next(iter(b.manager.executions._records.values()))
    before = effects(b)
    rejected = await b.router._goal(b.route, delegate(b, "goal.resume", target=paused.goal_id,
        revision=paused.control_revision + 1, identity="stale-resume"))
    assert rejected["status"] == "rejected" and effects(b) == before
    resumed = await b.router._goal(b.route, delegate(b, "goal.resume", target=paused.goal_id,
        revision=paused.control_revision, identity="resume"))
    assert resumed["status"] == "accepted" and resumed["goal"]["status"] == "active"
    newest = list(b.manager.executions._records.values())[-1]
    await asyncio.wait_for(newest.task, 2)
    assert newest.output_owner is original and not original.task.done()
    assert b.sdk._event_manager.has_pending_work()


async def test_active_resume_receipt_explicitly_preserves_original_model_and_policy_binding(boundary):
    b = boundary
    first = await b.router._goal(b.route, delegate(b))
    previous_context = deepcopy(b.sdk.goal_manager.peek().run_context)
    original_entry = next(iter(b.manager.executions._records.values()))
    b.route.native_p3_authority = SimpleNamespace(**{**vars(b.route.native_p3_authority),
        "model_identity": "different-model#1", "model_config_version": "v2"})
    command = delegate(b, "goal.resume", target=first["goal"]["goal_id"],
        revision=first["goal"]["control_revision"], identity="resume-already-active")
    result = await b.router._goal(b.route, command)
    assert result["status"] == "accepted"
    assert result["execution_binding"] == "preserved"
    assert b.sdk.goal_manager.peek().run_context == previous_context
    assert result["goal"]["control_revision"] == first["goal"]["control_revision"]
    assert "model_identity" not in result and "tool_policy" not in result
    assert await b.router._goal(b.route, command) == result
    await original_entry.prepared_work.before_effect(SimpleNamespace(), model_call=True)
    b.model.assert_called_with("model#0", expected_identity="model#0", expected_config_version="v1", instantiate=False)


async def test_unadmitted_snapshot_cannot_become_accepted_on_first_call_or_replay(boundary):
    b = boundary
    async def unadmitted(request):
        prepare_current_work(sdk_agent=b.sdk, session_id="session", apply_runtime=Mock(return_value=None))
        yield AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
            payload={"event_type": "goal.snapshot", "goal": {"goal_id": "fabricated", "status": "active"}})
    b.facade.process_message_stream = unadmitted
    for _ in range(2):
        result = await b.router._goal(b.route, delegate(b))
        assert result["status"] == "unknown"
        assert result["reason"] == "GOAL_CONTROL_ADMISSION_UNOBSERVED"
    assert b.sdk.goal_manager.peek() is None
    assert not b.sdk._event_manager.has_pending_work()


@pytest.mark.parametrize("failure", ["revoked", "drift", "carrier_closed"])
async def test_control_lock_wait_rechecks_revocation_and_model_before_any_goal_effect(boundary, failure):
    b = boundary
    await b.sdk._interaction_control_lock.acquire()
    before = effects(b)
    operation = asyncio.create_task(b.router._goal(b.route, delegate(b)))
    await asyncio.wait_for(b.facade.entered.wait(), 2)
    setattr(b.state, failure, True)
    b.sdk._interaction_control_lock.release()
    result = await asyncio.wait_for(operation, 2)
    assert result["status"] == "rejected"
    assert effects(b) == before


async def test_text_reader_retains_native_goal_after_carrier_disconnect(boundary):
    b = boundary
    req = AgentRequest(request_id="earlier-text", channel_id="web", session_id="session",
        params={"action": "attach", "mode": "code.plan", "work_mode": "code", "project_dir": b.project})
    reader = b.manager.executions.start(b.facade, req)
    async def output_ready():
        while reader.output_owner is None:
            await asyncio.sleep(0)
    await asyncio.wait_for(output_ready(), 2)
    result = await b.router._goal(b.route, delegate(b))
    assert result["status"] == "accepted"
    native_entry = list(b.manager.executions._records.values())[-1]
    await asyncio.wait_for(native_entry.task, 2)
    assert native_entry.output_owner is reader and reader.retained
    b.state.carrier_closed = True
    b.manager.executions.disconnect(channel_id="web", session_id="session")
    assert not reader.cancellation_requested and not reader.task.done()
    # The admitted work's grant/model guard remains usable after carrier loss.
    await native_entry.prepared_work.before_effect(SimpleNamespace(), model_call=True)
    assert b.sdk.goal_manager.peek().status.value == "active"
    assert b.sdk._event_manager.has_pending_work()
    b.state.revoked = True
    with pytest.raises(PermissionError):
        await native_entry.prepared_work.before_effect(SimpleNamespace(), model_call=True)


async def test_workflow_reply_passes_real_context_store_then_exact_sdk_pending_owner(boundary, monkeypatch):
    from jiuwenswarm.agents.harness.team import team_manager as team_module
    from tests.unit_tests.agentserver.test_shared_team_workflow_capabilities import _real_pending_owner

    b = boundary
    owner = team_module.TeamManager()
    owner.commit_runtime_ready("session-a", "team-a")
    owner.wait_for_resumable_runtime = AsyncMock(side_effect=AssertionError("no runtime restoration"))
    owner.interact = AsyncMock(side_effect=AssertionError("no legacy delivery"))
    monkeypatch.setattr(team_module, "_team_manager", owner)
    scope = ScopeRef("user", "project", "session-a", Assurance.AUTHENTICATED)
    b.route.binding.scope = scope
    selection = b.router.contexts.select(scope=scope, history=[], tasks=[], works=[], model={})
    async with _real_pending_owner(monkeypatch, owner) as pending:
        for run_id, input_id in [("wrong-run", "phase:human:0"), ("w123", "wrong-input")]:
            action = NativeBusinessAction("workflow.reply", selection.context_id, run_id, None,
                None, "answer", None, input_id=input_id)
            assert b.router.contexts.require(scope, action) is selection
            result = await b.router._workflow(b.route, SimpleNamespace(business=action))
            assert result["status"] == "rejected" and not pending.future.done()
        action = NativeBusinessAction("workflow.reply", selection.context_id, "w123", None,
            None, "exact answer", None, input_id="phase:human:0")
        assert b.router.contexts.require(scope, action) is selection
        result = await b.router._workflow(b.route, SimpleNamespace(business=action))
        assert result["status"] == "input_accepted"
        assert await pending.wait == "exact answer"
        assert b.router._work_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["expire", "stop"])
async def test_detached_goal_checks_authority_after_resolver_wait(boundary, transition):
    b = boundary
    receipt = await b.router._goal(b.route, delegate(b))
    assert receipt["status"] == "accepted"
    entry = next(iter(b.manager.executions._records.values()))
    clock = {"value": 0}
    composition = b.router.registry._p3_composition
    b.router.registry._stopped = False
    composition._accepting = True
    composition._clock = lambda: clock["value"]

    def require_usable(*, now, **_kwargs):
        if now >= 1:
            raise PermissionError("grant expired during authority read")

    current = SimpleNamespace(context=SimpleNamespace(
        file_path=b.project, require_usable=require_usable))
    b.route.native_p3_authority.principal.require_usable = require_usable

    def resolve(*_args, **kwargs):
        assert kwargs["now"] == 0
        if transition == "expire":
            clock["value"] = 1
        else:
            b.router.registry._stopped = True
            composition._accepting = False
        return current

    composition._resolve_native_activation_authority = resolve
    b.router._require_work_authority = NativeBusinessRouter._require_work_authority.__get__(b.router)
    effects = []
    try:
        await entry.prepared_work.before_effect(SimpleNamespace(), model_call=True)
        effects.append("inference admitted after authority transition")
    except (PermissionError, ValueError):
        pass
    assert effects == []


@pytest.mark.asyncio
async def test_closed_output_owner_rejects_detached_goal_work(boundary):
    b = boundary
    receipt = await b.router._goal(b.route, delegate(b))
    assert receipt["status"] == "accepted"
    entry = next(iter(b.manager.executions._records.values()))
    b.manager.executions._cancel(entry)
    with pytest.raises(ValueError, match="AGENT_WORK_BINDING_CLOSED"):
        await entry.prepared_work.before_effect(SimpleNamespace(), model_call=True)
