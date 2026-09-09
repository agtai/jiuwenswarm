"""Cross-entry identity and read-only Goal access through the actual SDK owner."""
import asyncio
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from openjiuwen.harness.goal.manager import GoalManager
from openjiuwen.harness.deep_agent import DeepAgent
from openjiuwen.core.single_agent.schema.agent_card import AgentCard
from openjiuwen.harness.goal.schema import GoalRecord
from openjiuwen.harness.goal.store import SESSION_GOAL_RECORD_KEY, SessionGoalStore
from openjiuwen.harness.task_loop.event_manager import EventManager
from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
from jiuwenswarm.common.e2a.constants import E2A_CANCEL_SOURCE_CLIENT_DISCONNECT, E2A_INTERNAL_CANCEL_SOURCE_KEY
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
from jiuwenswarm.server.runtime.agent_manager import AgentManager, _make_agent_cache_key
from jiuwenswarm.server.runtime.agent_resolution import SessionAgentUnavailable
from jiuwenswarm.server.runtime.session_execution import SessionExecutionUnavailable, current_output_observer
from jiuwenswarm.server.runtime.session.session_manager import SessionManager
from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessViolation


@pytest.fixture
def owners(monkeypatch, tmp_path):
    project = str(tmp_path / "project")
    metadata = {"mode": "agent", "work_mode": "code", "project_dir": project}
    read = Mock(side_effect=lambda *args, **kwargs: deepcopy(metadata))
    write = Mock(side_effect=AssertionError("query wrote metadata"))
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.get_session_metadata", read)
    monkeypatch.setattr("jiuwenswarm.server.runtime.session.session_metadata.sync_session_request_metadata", write)
    goal = GoalRecord.create(session_id="session", objective="Finish the report")
    state = {SESSION_GOAL_RECORD_KEY: goal.to_dict()}
    session = SimpleNamespace(get_session_id=lambda: "session", get_state=state.get,
                             update_state=Mock(side_effect=AssertionError("query wrote Goal")))
    cancel, emit, notify = AsyncMock(), Mock(), Mock()
    goals = GoalManager(store=SessionGoalStore(session), event_manager=EventManager(),
        control_lock=asyncio.Lock(), has_output_stream=lambda: False,
        cancel_active_round=cancel, emit_event=emit, notify_work=notify)
    child = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    child._is_session_scoped_adapter, child._parent_session_id = True, "session"
    child._instance = SimpleNamespace(goal_manager=goals)
    child._active_session_ids = Counter()
    root = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    root._is_session_scoped_adapter = False
    root._session_adapters, root._session_adapter_initializing = {"session": child}, set()
    root._session_adapter_locks = {}
    root._get_or_create_session_adapter = AsyncMock(side_effect=AssertionError("query created child"))
    facade = JiuWenSwarm.__new__(JiuWenSwarm)
    facade._adapter = root
    manager = AgentManager()
    manager.agents = {"web": {_make_agent_cache_key("code", "normal", project): facade}}
    manager._create_agent = AsyncMock(side_effect=AssertionError("query created Agent"))
    manager.wait_for_session_prewarm = AsyncMock()
    route = SimpleNamespace(binding=SimpleNamespace(session_id="session", scope=ScopeRef("user", "project", "session", Assurance.AUTHENTICATED)),
        native_p3_authority=SimpleNamespace(context=SimpleNamespace(file_path=project)))
    router = NativeBusinessRouter(SimpleNamespace(_agent_manager=manager))
    router._require_context_authority = AsyncMock()
    return SimpleNamespace(**locals())


@pytest.mark.asyncio
async def test_text_and_native_resolve_same_owner_and_goal_with_zero_execution(owners):
    o = owners
    o.goal.run_context = {"extra": {"binding_id": "private-goal-binding"}}
    o.state[SESSION_GOAL_RECORD_KEY] = o.goal.to_dict()
    server = AgentWebSocketServer.__new__(AgentWebSocketServer)
    server._agent_manager = o.manager
    request = AgentRequest(request_id="text", channel_id="web", session_id="session",
                           params={"mode": "agent", "project_dir": o.project})
    mode, sub_mode, text_agent = await server._prepare_code_mode_chat_turn(request, "web", sync_metadata=False)
    assert (mode, sub_mode, text_agent) == ("code", "normal", o.facade)
    result = await o.router._goal(o.route)
    expected_public = o.goal.to_dict()
    expected_public.pop("run_context")
    assert result["goal"] == text_agent.peek_session_goal("session") == expected_public
    assert "run_context" not in result["goal"]
    assert o.goals.peek().run_context == o.goal.run_context
    result["goal"]["objective"] = "caller mutation"
    assert o.goals.peek().objective == "Finish the report"
    for forbidden in (o.write, o.session.update_state, o.cancel, o.emit, o.notify,
                      o.root._get_or_create_session_adapter, o.manager._create_agent):
        forbidden.assert_not_called()
    assert o.router._work_owner is None
    assert o.router._require_context_authority.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change,reason", [
    ({"project_dir": "elsewhere"}, "PROJECT_MISMATCH"),
    ({"mode": "team"}, "OWNER_UNAVAILABLE"),
    ({"work_mode": None}, "MODE_UNAVAILABLE"),
    ({"project_dir": None}, "PROJECT_UNAVAILABLE"),
])
async def test_native_missing_or_mismatched_owner_never_falls_back_or_creates(owners, change, reason):
    o = owners
    o.metadata.update(change)
    with pytest.raises(SessionAgentUnavailable, match=reason):
        await o.router._goal(o.route)
    o.manager._create_agent.assert_not_called()
    o.root._get_or_create_session_adapter.assert_not_called()
    o.write.assert_not_called()
    assert o.router._work_owner is None


@pytest.mark.asyncio
async def test_exact_cache_lookup_does_not_borrow_another_project_or_channel(owners):
    for project, channel in ((None, "web"), ("unrelated", "web"), (owners.project, "cli")):
        assert owners.manager.find_agent_exact(channel_id=channel, mode="code",
            project_dir=project, sub_mode="normal") is None
    owners.manager._create_agent.assert_not_called()


def agent_query(operation, target=None):
    return SimpleNamespace(business=NativeBusinessAction("agent." + operation, "a" * 64,
        target, None, None, None, None))


def install_interactive_goal_owner(o):
    """Keep the real shared manager/store; use the SDK's real output lifecycle."""
    instance = DeepAgent(AgentCard(name="shared-goal", description="test"))
    instance._interaction_started = True
    instance.goal_manager = o.goals
    instance._interaction_control_lock = o.goals._control_lock
    instance._event_manager = o.goals._event_manager
    instance._cancel_active_round = o.cancel
    o.goals._has_output_stream = instance.has_output_stream
    o.child._instance = instance
    o.session.update_state = Mock(side_effect=o.state.update)
    return instance


def shared_goal_producer(o, instance, *, cleanup_started=None, cleanup_release=None):
    """Real SDK and Goal adapter, replacing only model output for this seam."""
    async def produce(request):
        stream = None
        try:
            if request.req_method == "command.goal":
                result = await o.child.dispatch_goal_control(
                    session_id=request.session_id, with_output=True, **request.params)
                stream = result.pop("_output_stream", None)
                yield AgentResponseChunk(request.request_id, request.channel_id, result)
            else:
                stream = await instance.attach_output(on_output_ready=current_output_observer(instance))
                yield AgentResponseChunk(request.request_id, request.channel_id, {"text": "text connected"})
            if stream is not None:
                async for payload in stream:
                    yield AgentResponseChunk(request.request_id, request.channel_id, payload)
        finally:
            if stream is not None:
                if cleanup_started is not None:
                    cleanup_started.set()
                    await cleanup_release.wait()
                await stream.close(abort_active_round=True)
    return produce


def shared_goal_request(o, *, session_id="session", revision=None):
    return AgentRequest(request_id="retained-goal", channel_id="web", session_id=session_id,
        req_method="command.goal", is_stream=True, params={"action": "resume",
            "expected_goal_id": o.goal.goal_id,
            "expected_control_revision": revision or o.goal.control_revision})


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", [False, True])
async def test_shared_goal_keeps_actual_text_output_only_after_retained_admission(owners, retained):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    o.facade.process_message_stream = shared_goal_producer(o, instance)
    hub = o.manager.executions
    text = hub.stream(o.facade, AgentRequest("text-owner", channel_id="web", session_id="session"))
    await anext(text)
    original_token = instance._interaction_output.current_token()
    admitted = hub.start(o.facade, shared_goal_request(o), retained=retained)
    await asyncio.wait_for(asyncio.shield(admitted.task), 2)
    assert o.goals.peek().status.value == "active"
    fact = hub.observe(o.facade, session_id="session", execution_id="retained-goal")
    assert fact["output_execution_id"] == "text-owner"
    assert fact["stream_closed"] and not fact["output_stream_closed"]
    assert instance._interaction_output.current_token() == original_token
    server = AgentWebSocketServer.__new__(AgentWebSocketServer)
    server._agent_manager = o.manager
    o.facade.process_message = AsyncMock(side_effect=AssertionError("transport loss aborted the Agent"))
    disconnected = await server._handle_cancel(None,
        AgentRequest("disconnect", channel_id="web", session_id="session", params={"intent": "cancel"},
            metadata={E2A_INTERNAL_CANCEL_SOURCE_KEY: E2A_CANCEL_SOURCE_CLIENT_DISCONNECT}),
        asyncio.Lock(), send_response=False)
    assert disconnected.ok and disconnected.payload["success"]
    if retained:
        o.manager.cleanup_session_runtime = AsyncMock(side_effect=AssertionError("disposed retained work"))
        assert await server._cleanup_client_disconnect_session_runtime(
            AgentRequest("cleanup", channel_id="web", session_id="session"))
    await text.aclose()
    if retained:
        assert instance.has_output_stream()
        o.cancel.assert_not_awaited()
        await instance._interaction_output.emit({"text": "Goal after text disconnect"})
        actual_output = admitted.output_owner
        while actual_output.sequence < 2:
            await asyncio.wait_for(actual_output.changed.wait(), 2)
        native = await o.router._agent(o.route, agent_query("get", "retained-goal"))
        assert native["events"][-1]["payload"] == {"text": "Goal after text disconnect"}
        assert native["events"][-1]["request_id"] == "text-owner"
        assert native["business_completion"] == "consult_capability_owner"
    else:
        assert not instance.has_output_stream()
        o.cancel.assert_awaited_once_with(reason="output_detached")
    assert await hub.close()
    assert not hub._output_owners
    o.manager._create_agent.assert_not_called()


@pytest.mark.asyncio
async def test_detach_first_rejects_retained_goal_before_state_or_queue_effects(owners):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    cleanup_started, cleanup_release = asyncio.Event(), asyncio.Event()
    o.facade.process_message_stream = shared_goal_producer(o, instance,
        cleanup_started=cleanup_started, cleanup_release=cleanup_release)
    hub = o.manager.executions
    text = hub.stream(o.facade, AgentRequest("text-owner", channel_id="web", session_id="session"))
    await anext(text)
    disconnect = asyncio.create_task(text.aclose())
    await asyncio.wait_for(cleanup_started.wait(), 2)
    before = deepcopy(o.state)
    admitted = hub.start(o.facade, shared_goal_request(o), retained=True)
    await asyncio.wait_for(asyncio.shield(admitted.task), 2)
    assert admitted.stream_outcome == "failed"
    assert o.state == before and not instance._event_manager.has_pending_work()
    o.session.update_state.assert_not_called()
    o.cancel.assert_not_awaited()
    o.notify.assert_not_called()
    cleanup_release.set()
    await asyncio.wait_for(disconnect, 2)
    assert await hub.close()


@pytest.mark.asyncio
async def test_unmanaged_output_rejects_retained_goal_without_stealing_reader(owners):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    o.facade.process_message_stream = shared_goal_producer(o, instance)
    hub = o.manager.executions
    stream = await instance.attach_output()
    before = deepcopy(o.state)
    admitted = hub.start(o.facade, shared_goal_request(o), retained=True)
    await asyncio.wait_for(asyncio.shield(admitted.task), 2)
    assert admitted.stream_outcome == "failed" and o.state == before
    assert not instance._event_manager.has_pending_work()
    o.session.update_state.assert_not_called()
    o.cancel.assert_not_awaited()
    o.notify.assert_not_called()
    await instance._interaction_output.emit({"text": "legacy reader preserved"})
    assert await anext(stream) == {"text": "legacy reader preserved"}
    await stream.close(abort_active_round=False)
    assert await hub.close()


@pytest.mark.asyncio
async def test_gateway_loss_keeps_retained_child_and_cancels_unrelated_session(owners):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    o.facade.process_message_stream = shared_goal_producer(o, instance)
    o.facade._session_manager = SessionManager()
    other = JiuWenSwarmDeepAdapter.__new__(JiuWenSwarmDeepAdapter)
    other._is_session_scoped_adapter, other._parent_session_id = True, "unrelated"
    other._instance = SimpleNamespace(abort=AsyncMock())
    other._stream_event_rail = Mock()
    other._active_session_ids = Counter({"unrelated": 1})
    other._cancel_scheduler_running_tasks = Mock()
    o.root._session_adapters["unrelated"] = other
    ordinary = asyncio.create_task(asyncio.Event().wait())
    o.facade._session_manager._session_tasks["unrelated"] = ordinary
    await asyncio.sleep(0)
    hub = o.manager.executions
    text = hub.stream(o.facade, AgentRequest("text-owner", channel_id="web", session_id="session"))
    await anext(text)
    admitted = hub.start(o.facade, shared_goal_request(o), retained=True)
    await asyncio.wait_for(asyncio.shield(admitted.task), 2)
    assert hub.retained_sessions(o.facade) == frozenset({"session"})
    await o.manager.cancel_all_inflight_work("gateway connection lost")
    await text.aclose()
    o.cancel.assert_not_awaited()
    assert instance.has_output_stream() and not admitted.output_owner.task.done()
    assert ordinary.cancelled()
    other._instance.abort.assert_awaited_once()
    other._stream_event_rail.abort.assert_called_once_with("unrelated")
    assert await hub.close()
    assert not hub.retained_sessions(o.facade)


@pytest.mark.asyncio
async def test_agent_manager_public_stream_uses_same_observed_output_owner(owners):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    o.facade.process_message_stream = shared_goal_producer(o, instance)
    o.manager.get_agent = AsyncMock(return_value=o.facade)
    text = o.manager.process_message_stream(
        AgentRequest("manager-entry", channel_id="web", session_id="session"))
    await anext(text)
    observed = await o.router._agent(o.route, agent_query("get", "manager-entry"))
    assert observed["output_execution_id"] == "manager-entry"
    assert observed["events"][0]["payload"] == {"text": "text connected"}
    await text.aclose()
    assert not instance.has_output_stream()
    assert await o.manager.executions.close()


@pytest.mark.asyncio
async def test_gateway_finally_fences_queued_goal_before_route_cleanup_yields(owners, monkeypatch):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    o.facade.process_message_stream = shared_goal_producer(o, instance)
    hub = o.manager.executions
    server = AgentWebSocketServer.__new__(AgentWebSocketServer)
    server._agent_manager = SimpleNamespace(executions=hub, cancel_all_inflight_work=AsyncMock())
    server._gateway_connection_lifecycle_lock = asyncio.Lock()
    server._gateway_connection_generation = 0
    server._current_ws = server._current_ws_done = None
    server._session_stream_tasks = {}
    server._clear_ws_acp_client_capabilities = Mock()
    server._stop_scheduler = AsyncMock()
    connected, accepted = asyncio.Event(), []
    async def observe(*args):
        from contextlib import aclosing
        async with aclosing(hub.stream(o.facade,
                AgentRequest("text-owner", channel_id="web", session_id="session"))) as stream:
            async for _ in stream:
                connected.set()
    server._handle_message = observe
    async def close_routes():
        # The real registry closes routes under locks and may yield. The Goal
        # producer is already queued ahead of the cancelled observer's finally.
        await asyncio.sleep(0)
        await asyncio.wait_for(asyncio.shield(accepted[0].task), 2)
        assert o.goals.peek().status.value == "paused"
        o.session.update_state.assert_not_called()
        o.notify.assert_not_called()
        assert not instance._event_manager.has_pending_work()
    server._live_voice_product_composition = SimpleNamespace(close_active_routes=close_routes)
    monkeypatch.setattr("jiuwenswarm.agents.harness.team.cancel_all_team_stream_tasks_across_managers", AsyncMock())
    class ClosingSocket:
        remote_address = ("127.0.0.1", 12345)
        sent_first = False
        async def send(self, _):
            pass
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.sent_first:
                self.sent_first = True
                return "observe"
            await connected.wait()
            accepted.append(hub.start(o.facade, shared_goal_request(o), retained=True))
            raise StopAsyncIteration
    await server._connection_handler(ClosingSocket())
    assert len(accepted) == 1 and accepted[0].stream_outcome == "failed"
    # Also assert outside registry cleanup, whose production exception handler
    # deliberately logs failures and continues tearing down the connection.
    assert o.goals.peek().status.value == "paused"
    o.session.update_state.assert_not_called()
    assert not instance.has_output_stream()
    assert not hub._output_owners
    assert await hub.close()


@pytest.mark.asyncio
async def test_superseded_gateway_connection_cannot_fence_new_generation():
    server = AgentWebSocketServer.__new__(AgentWebSocketServer)
    fence, close_routes = Mock(), AsyncMock()
    server._agent_manager = SimpleNamespace(executions=SimpleNamespace(disconnect_all=fence),
        cancel_all_inflight_work=AsyncMock())
    server._gateway_connection_lifecycle_lock = asyncio.Lock()
    server._gateway_connection_generation = 0
    server._current_ws = server._current_ws_done = None
    server._session_stream_tasks = {}
    server._clear_ws_acp_client_capabilities = Mock()
    server._stop_scheduler = AsyncMock()
    server._live_voice_product_composition = SimpleNamespace(close_active_routes=close_routes)
    replacement = object()
    class SupersededSocket:
        remote_address = ("127.0.0.1", 12345)
        async def send(self, _):
            pass
        def __aiter__(self):
            return self
        async def __anext__(self):
            server._current_ws = replacement
            server._gateway_connection_generation += 1
            raise StopAsyncIteration
    await server._connection_handler(SupersededSocket())
    fence.assert_not_called()
    close_routes.assert_not_awaited()
    server._agent_manager.cancel_all_inflight_work.assert_not_awaited()
    server._stop_scheduler.assert_not_awaited()
    assert server._current_ws is replacement


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["session", "agent"])
async def test_borrowed_output_cannot_cross_configured_owner_or_session(owners, mismatch):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = "paused"
    instance = install_interactive_goal_owner(o)
    o.facade.process_message_stream = shared_goal_producer(o, instance)
    hub = o.manager.executions
    text = hub.stream(o.facade, AgentRequest("text-owner", channel_id="web", session_id="session"))
    await anext(text)
    hook_errors = []
    async def foreign_producer(request):
        try:
            await instance.resume_goal(expected_goal_id=o.goal.goal_id,
                expected_control_revision=o.goal.control_revision,
                on_output_ready=current_output_observer(instance))
        except SessionExecutionUnavailable as error:
            hook_errors.append(error.reason)
        yield AgentResponseChunk(request.request_id, request.channel_id)
    foreign = SimpleNamespace(process_message_stream=foreign_producer) if mismatch == "agent" else o.facade
    if mismatch == "session":
        o.facade.process_message_stream = foreign_producer
    entry = hub.start(foreign, shared_goal_request(o,
        session_id="other-session" if mismatch == "session" else "session"), retained=True)
    await asyncio.wait_for(asyncio.shield(entry.task), 2)
    assert hook_errors == ["AGENT_STREAM_OUTPUT_SCOPE_MISMATCH"]
    o.session.update_state.assert_not_called()
    o.cancel.assert_not_awaited()
    o.notify.assert_not_called()
    assert not instance._event_manager.has_pending_work()
    assert not hub.retains_session(channel_id="different-channel", session_id="session")
    assert not hub.disconnect(channel_id="different-channel", session_id="session")
    await text.aclose()
    assert not instance.has_output_stream()
    assert await hub.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_status", ["active", "completed"])
async def test_text_goal_execution_and_native_observation_use_same_sdk_output_owner(owners, previous_status):
    o = owners
    o.state[SESSION_GOAL_RECORD_KEY]["status"] = previous_status
    instance = install_interactive_goal_owner(o)
    result = await o.child.dispatch_goal_control(action="set", objective="New shared goal",
        overwrite_confirmed=True, expected_goal_id=o.goal.goal_id,
        expected_control_revision=o.goal.control_revision, session_id="session", with_output=True)
    assert result["result_type"] == "goal_stream"
    assert result["goal"]["goal_id"] != o.goal.goal_id
    stream = result.pop("_output_stream")
    assert stream is not None
    native = await o.router._goal(o.route)
    assert native["goal"] == result["goal"] == o.facade.peek_session_goal("session")
    work = instance._event_manager.next_work()
    assert work.context["goal_id"] == native["goal"]["goal_id"]
    assert instance._event_manager.next_work() is None
    await instance._interaction_output.emit({"text": "shared output"})
    assert await anext(stream) == {"text": "shared output"}
    o.manager._create_agent.assert_not_called()
    o.root._get_or_create_session_adapter.assert_not_called()
    o.write.assert_not_called()
    await stream.close(abort_active_round=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["set", "pause", "resume", "clear"])
async def test_text_stale_control_cannot_mutate_or_attach_to_current_native_goal(owners, action):
    o = owners
    instance = install_interactive_goal_owner(o)
    before = deepcopy(o.state)
    result = await o.child.dispatch_goal_control(action=action, objective="Forbidden",
        overwrite_confirmed=action == "set", expected_goal_id="replaced-goal",
        expected_control_revision=1, session_id="session", with_output=action in {"set", "resume"})
    assert result["result_type"] == "goal_error" and result["error_code"] == "stale_goal"
    assert result["goal"] == (await o.router._goal(o.route))["goal"]
    assert o.state == before and not instance.has_output_stream()
    assert not instance._event_manager.has_pending_work()
    for forbidden in (o.session.update_state, o.cancel, o.emit, o.notify, o.write,
                      o.root._get_or_create_session_adapter, o.manager._create_agent):
        forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_text_pause_captures_target_before_waiting_and_cannot_pause_replacement(owners):
    o = owners
    install_interactive_goal_owner(o)
    async with o.goals._control_lock:
        replacement = asyncio.create_task(o.goals.set("Replacement", overwrite_confirmed=True))
        await asyncio.sleep(0)
        pause = asyncio.create_task(o.child.handle_goal_command_structured({"action": "pause"}, "session"))
        await asyncio.sleep(0)
    created = await replacement
    result = await pause
    assert result["error_code"] == "stale_goal"
    assert result["goal"]["goal_id"] == created.goal_id
    assert o.goals.peek().status.value == "active"
    assert o.session.update_state.call_count == 1
    assert o.cancel.await_count == 1  # Only the admitted replacement cancelled its predecessor.
    assert not o.child._instance.has_output_stream()


@pytest.mark.asyncio
async def test_legacy_clear_without_observed_goal_cannot_delete_concurrent_creation(owners):
    o = owners
    instance = install_interactive_goal_owner(o)
    o.state.clear()
    async with o.goals._control_lock:
        creation = asyncio.create_task(o.goals.set("Created concurrently"))
        await asyncio.sleep(0)
        clear = asyncio.create_task(o.child.handle_goal_command_structured({"action": "clear"}, "session"))
        await asyncio.sleep(0)
    created = await creation
    result = await clear
    assert result["error_code"] == "no_goal"
    assert o.goals.peek().goal_id == created.goal_id
    assert o.session.update_state.call_count == 1
    assert not instance.has_output_stream()
    for forbidden in (o.cancel, o.emit, o.notify, o.write, o.root._get_or_create_session_adapter):
        forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_native_observes_same_running_text_output_without_creating_execution(owners):
    o = owners
    release, started = asyncio.Event(), asyncio.Event()
    calls = []
    async def produce(request):
        calls.append(request)
        yield AgentResponseChunk(request.request_id, "web", {"event_type": "chat.delta", "content": "working"})
        started.set()
        await release.wait()
        yield AgentResponseChunk(request.request_id, "web", {"event_type": "chat.final", "content": "done"}, True)
    o.facade.process_message_stream = produce
    request = AgentRequest("text-execution", "web", "session", params={"mode": "code.normal"})
    output = o.manager.executions.stream(o.facade, request)
    await anext(output)
    await asyncio.wait_for(started.wait(), 2)
    inventory = await o.router._agent(o.route, agent_query("list"))
    assert inventory["executions"][0]["execution_id"] == "text-execution"
    snapshot = await o.router._agent(o.route, agent_query("get", "text-execution"))
    assert snapshot["stream_closed"] is False
    assert snapshot["events"][0]["payload"]["content"] == "working"
    with pytest.raises(SessionExecutionUnavailable, match="NOT_OBSERVED"):
        await o.router._agent(o.route, agent_query("get", "other"))
    release.set()
    assert [event.payload["content"] async for event in output] == ["done"]
    final = await o.router._agent(o.route, agent_query("get", "text-execution"))
    assert final["stream_closed"] and final["stream_outcome"] == "ended"
    assert len(calls) == 1
    for forbidden in (o.write, o.session.update_state, o.cancel, o.emit, o.notify,
                      o.root._get_or_create_session_adapter, o.manager._create_agent):
        forbidden.assert_not_called()
    assert o.router._work_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["list", "get"])
async def test_native_revocation_blocks_shared_output_read_without_new_effects(owners, operation):
    o = owners
    o.manager.executions.list = Mock(side_effect=AssertionError("revoked output read"))
    o.manager.executions.observe = Mock(side_effect=AssertionError("revoked output read"))
    o.router._require_context_authority.side_effect = [None, NativeBusinessViolation("RETIRED")]
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await o.router._agent(o.route, agent_query(operation, "execution" if operation == "get" else None))
    for forbidden in (o.manager.executions.list, o.manager.executions.observe,
                      o.manager._create_agent, o.write, o.root._get_or_create_session_adapter):
        forbidden.assert_not_called()
    assert o.manager.executions._records == {} and o.router._work_owner is None


@pytest.mark.asyncio
async def test_revoked_native_query_never_reads_or_publishes_goal(owners):
    o = owners
    o.facade.peek_session_goal = Mock(side_effect=AssertionError("query read a revoked owner"))
    o.router._require_context_authority.side_effect = NativeBusinessViolation("RETIRED")
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await o.router._goal(o.route)
    o.read.assert_not_called()
    o.router._require_context_authority.side_effect = [None, NativeBusinessViolation("RETIRED")]
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await o.router._goal(o.route)
    o.facade.peek_session_goal.assert_not_called()
    o.manager._create_agent.assert_not_called()


@pytest.mark.parametrize("missing", ["facade_adapter", "child", "initializing", "goal_manager", "wrong_session"])
def test_unloaded_goal_owner_is_unavailable_not_absent(owners, missing):
    o = owners
    if missing == "facade_adapter":
        o.facade._adapter = None
    elif missing == "child":
        o.root._session_adapters.clear()
    elif missing == "initializing":
        o.root._session_adapter_initializing.add("session")
    elif missing == "goal_manager":
        o.child._instance = None
    else:
        o.child._parent_session_id = "other"
    with pytest.raises(SessionAgentUnavailable):
        o.facade.peek_session_goal("session")
    o.root._get_or_create_session_adapter.assert_not_called()
    o.session.update_state.assert_not_called()


def enable_controls(o):
    # Keep the SDK state, lifecycle and lock real; isolate external grant I/O.
    o.session.update_state = Mock(side_effect=o.state.update)
    current = SimpleNamespace(context=SimpleNamespace(require_usable=Mock(), file_path=o.project))
    o.router._require_work_authority = AsyncMock(return_value=current)
    o.router._recheck_context_authority = Mock()
    o.router.registry._p3_composition = SimpleNamespace(_clock=lambda: 100)
    o.route.native_p3_authority.principal = SimpleNamespace(require_usable=Mock())
    return current


def goal_control(operation, goal):
    return SimpleNamespace(business=NativeBusinessAction("goal." + operation, "a" * 64,
        goal["goal_id"], goal["control_revision"], None, None, None))


@pytest.mark.asyncio
async def test_native_goal_control_and_text_resume_share_sdk_identity_and_state(owners):
    o = owners
    enable_controls(o)
    initial = (await o.router._goal(o.route))["goal"]
    paused = await o.router._goal(o.route, goal_control("pause", initial))
    assert paused["goal"]["status"] == "paused"
    assert o.facade.peek_session_goal("session") == paused["goal"]
    assert paused["goal"]["revision"] == initial["revision"]
    await o.goals.resume()  # Existing text control uses this same owner.
    before = o.goals.peek().to_dict()
    writes = o.session.update_state.call_count
    rejected = await o.router._goal(o.route, goal_control("clear", initial))
    assert rejected["status"] == "rejected" and rejected["reason"] == "GOAL_STALE_GOAL"
    assert o.goals.peek().to_dict() == before
    assert o.session.update_state.call_count == writes
    o.cancel.assert_not_called()
    cleared = await o.router._goal(o.route, goal_control("clear", before))
    assert cleared["goal"] is None and cleared["cleared_goal"]["goal_id"] == initial["goal_id"]
    assert o.goals.peek() is None
    o.cancel.assert_awaited_once_with(expected_run_kind="goal", expected_goal_id=initial["goal_id"], reason="goal_clear")
    o.manager._create_agent.assert_not_called()
    o.root._get_or_create_session_adapter.assert_not_called()
    o.write.assert_not_called()
    assert o.router._work_owner is None


@pytest.mark.asyncio
async def test_native_control_rechecks_revocation_inside_sdk_lock_before_effect(owners):
    o = owners
    current = enable_controls(o)
    entered = asyncio.Event()
    async def grant(route):
        entered.set()
        return current
    o.router._require_work_authority.side_effect = grant
    before = o.goals.peek().to_dict()
    await o.goals._control_lock.acquire()
    pending = asyncio.create_task(o.router._goal(o.route, goal_control("clear", before)))
    await asyncio.wait_for(entered.wait(), timeout=2)
    await asyncio.sleep(0)
    assert not pending.done()
    assert o.child.is_session_active("session")
    def revoked(*args):
        assert o.goals._control_lock.locked()
        raise NativeBusinessViolation("RETIRED")
    o.router._recheck_context_authority.side_effect = revoked
    o.goals._control_lock.release()
    with pytest.raises(NativeBusinessViolation, match="RETIRED"):
        await pending
    assert o.goals.peek().to_dict() == before
    assert o.child._active_session_ids == {}
    for forbidden in (o.session.update_state, o.cancel, o.emit, o.notify, o.write, o.manager._create_agent):
        forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_goal_observation_and_control_reject_cleanup_already_in_progress(owners):
    o = owners
    enable_controls(o)
    entered = asyncio.Event()
    async def cleanup():
        entered.set()
        await asyncio.Future()
    o.child.cleanup = cleanup
    o.child.is_session_active = Mock(return_value=False)
    o.child.is_deep_agent_executing_for_session = Mock(return_value=False)
    closing = asyncio.create_task(o.root.cleanup_session_adapter("session"))
    await asyncio.wait_for(entered.wait(), timeout=2)
    try:
        assert o.root._session_adapter_locks["session"].locked()
        with pytest.raises(SessionAgentUnavailable):
            o.facade.peek_session_goal("session")
        with pytest.raises(SessionAgentUnavailable):
            await o.router._goal(o.route, goal_control("clear", o.goal.to_dict()))
        o.session.update_state.assert_not_called()
        o.cancel.assert_not_called()
        assert o.child._active_session_ids == {}
    finally:
        closing.cancel()
        await asyncio.gather(closing, return_exceptions=True)


@pytest.mark.asyncio
async def test_registry_is_reread_after_sdk_lock_wait_before_native_control(owners):
    o = owners
    current = enable_controls(o)
    composition = o.router.registry._p3_composition
    composition._accepting = True
    o.router.registry._stopped = False
    entered = asyncio.Event()
    hidden = False
    calls = []
    loop = asyncio.get_running_loop()
    def resolve(*args, **kwargs):
        calls.append(kwargs["operation"])
        if hidden:
            raise NativeBusinessViolation("PROJECT_HIDDEN")
        loop.call_soon_threadsafe(entered.set)
        return current
    composition._resolve_native_activation_authority = resolve
    o.router._require_work_authority = NativeBusinessRouter._require_work_authority.__get__(o.router)
    before = o.goal.to_dict()
    await o.goals._control_lock.acquire()
    pending = asyncio.create_task(o.router._goal(o.route, goal_control("clear", before)))
    await asyncio.wait_for(entered.wait(), timeout=2)
    hidden = True
    o.goals._control_lock.release()
    with pytest.raises(NativeBusinessViolation, match="PROJECT_HIDDEN"):
        await pending
    assert calls == ["agent.chat", "agent.chat"]
    assert o.goals.peek().to_dict() == before
    o.session.update_state.assert_not_called()
    o.cancel.assert_not_called()
    assert o.child._active_session_ids == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,failure", [("pause", "commit"), ("clear", "commit"), ("clear", "cancel")])
async def test_partial_goal_control_failure_is_unknown_and_preserves_actual_state(owners, operation, failure):
    o = owners
    enable_controls(o)
    if failure == "commit":
        o.session.commit = AsyncMock(side_effect=OSError("storage unavailable"))
    else:
        o.cancel.side_effect = RuntimeError("cancellation unavailable")
    result = await o.router._goal(o.route, goal_control(operation, o.goal.to_dict()))
    assert result["status"] == "unknown"
    assert result["reason"] == "GOAL_CONTROL_OUTCOME_UNKNOWN" and result["observation_required"]
    observed = o.facade.peek_session_goal("session")
    if operation == "pause":
        assert observed["status"] == "paused"
    else:
        assert observed is None
    assert o.session.update_state.call_count == 1
    if failure == "commit":
        o.cancel.assert_not_called()
    else:
        assert o.cancel.await_count == 1
    assert o.child._active_session_ids == {}
