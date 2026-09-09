"""Exact SwarmFlow reply admission at the shared application/SDK seam."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from openjiuwen.agent_teams.interaction.payload import DeliverResult
from jiuwenswarm.agents.harness.team import team_manager as team_module
from jiuwenswarm.server.runtime.team_workflow_capabilities import reply_swarmflow


@pytest.fixture
def owner(monkeypatch):
    manager = team_module.TeamManager()
    manager.commit_runtime_ready("session-a", "team-a")
    manager.wait_for_resumable_runtime = AsyncMock(side_effect=AssertionError("must not restore"))
    manager.interact = AsyncMock(side_effect=AssertionError("must not use legacy publish"))
    monkeypatch.setattr(team_module, "_team_manager", manager)
    return manager


@pytest.fixture
def sdk_reply(monkeypatch):
    reply = AsyncMock(return_value=DeliverResult.success())
    monkeypatch.setattr(team_module.Runner, "reply_swarmflow_human", reply, raising=False)
    return reply


def arguments(**updates):
    values = dict(session_id="session-a", run_id="w123", correlation_id="phase:human:0", answer=" Yes\n")
    values.update(updates)
    return values


@pytest.mark.parametrize("field,value", [
    ("session_id", ""), ("session_id", " session-a"), ("session_id", None),
    ("run_id", ""), ("run_id", "w123 "), ("run_id", 123), ("run_id", "w:123"),
    ("correlation_id", ""), ("correlation_id", " phase:human:0"),
    ("correlation_id", "bad\x00id"), ("correlation_id", "\ud800"),
    ("answer", ""), ("answer", None), ("answer", {"answer": "yes"}),
    ("answer", "bad\x00answer"), ("answer", "\ud800"),
])
async def test_invalid_target_or_answer_never_reads_or_invokes_owner(monkeypatch, field, value):
    lookup = Mock(side_effect=AssertionError("invalid request must not read owner"))
    monkeypatch.setattr(team_module, "get_existing_team_manager", lookup, raising=False)
    authority = Mock()
    assert await reply_swarmflow(**arguments(**{field: value}), before_effect=authority) == (
        False, "invalid_swarmflow_reply")
    lookup.assert_not_called()
    authority.assert_not_called()


async def test_absent_owner_is_not_created(monkeypatch, sdk_reply):
    monkeypatch.setattr(team_module, "_team_manager", None)
    create = Mock(side_effect=AssertionError("must not create owner"))
    monkeypatch.setattr(team_module, "get_team_manager", create)
    assert await reply_swarmflow(**arguments()) == (False, "not_active")
    assert team_module._team_manager is None
    create.assert_not_called()
    sdk_reply.assert_not_awaited()


async def test_other_session_rejects_without_restoration_or_delivery(owner, sdk_reply):
    authority = Mock()
    assert await reply_swarmflow(**arguments(session_id="session-b"), before_effect=authority) == (
        False, "not_active")
    sdk_reply.assert_not_awaited()
    authority.assert_not_called()
    owner.wait_for_resumable_runtime.assert_not_awaited()
    owner.interact.assert_not_awaited()


async def test_both_channels_forward_exact_target_and_guard_to_same_owner(owner, sdk_reply):
    authority = Mock()
    for channel in ("web", "live_voice"):
        assert await reply_swarmflow(**arguments(), channel_id=channel, before_effect=authority) == (True, None)
        sdk_reply.assert_awaited_with(**arguments(), team_name="team-a", before_effect=authority)
    # SDK owns the only effect guard invocation, after validating the pending Future.
    authority.assert_not_called()
    owner.wait_for_resumable_runtime.assert_not_awaited()
    owner.interact.assert_not_awaited()


@pytest.mark.parametrize("reason", ["not_active", "run_not_found", "input_not_pending", "gate_closed"])
async def test_sdk_delivery_rejection_remains_rejection(owner, sdk_reply, reason):
    sdk_reply.return_value = DeliverResult.failure(reason)
    assert await reply_swarmflow(**arguments()) == (False, reason)
    owner.wait_for_resumable_runtime.assert_not_awaited()
    owner.interact.assert_not_awaited()


async def test_callback_failure_propagates_without_success_receipt(owner, sdk_reply):
    authority = Mock(side_effect=PermissionError("grant revoked"))

    async def admit(**kwargs):
        kwargs["before_effect"]()
        raise AssertionError("revoked authority cannot reach effect")

    sdk_reply.side_effect = admit
    with pytest.raises(PermissionError, match="grant revoked"):
        await reply_swarmflow(**arguments(), before_effect=authority)
    authority.assert_called_once_with()


async def test_transport_failure_is_not_converted_to_delivered(owner, sdk_reply):
    sdk_reply.side_effect = RuntimeError("owner failed")
    with pytest.raises(RuntimeError, match="owner failed"):
        await reply_swarmflow(**arguments())


async def test_missing_sdk_exact_api_fails_closed(owner, monkeypatch):
    monkeypatch.setattr(team_module, "Runner", SimpleNamespace())
    assert await reply_swarmflow(**arguments()) == (False, "swarmflow_reply_unavailable")
    owner.wait_for_resumable_runtime.assert_not_awaited()
    owner.interact.assert_not_awaited()


@asynccontextmanager
async def _real_pending_owner(monkeypatch, owner):
    """Use the real SDK receipt chain and bus; omit only LLM answer formatting."""
    from openjiuwen.agent_teams.harness.async_tools import AsyncToolRecord, AsyncToolRuntime
    from openjiuwen.agent_teams.harness.team_harness import TeamHarness
    from openjiuwen.agent_teams.interaction.payload import HumanAgentMessage
    from openjiuwen.agent_teams.messager import inprocess
    from openjiuwen.agent_teams.runtime.background_task_controller import SwarmflowRunHandle
    from openjiuwen.agent_teams.runtime.manager import TeamRuntimeManager
    from openjiuwen.agent_teams.runtime.pool import ActiveTeam
    from openjiuwen.agent_teams.schema.team import TeamRole
    from openjiuwen.agent_teams.workflow.backends.avatar_session_backend import _SessionState
    from openjiuwen.agent_teams.workflow.backends.budget_rail import SwarmflowBudgetRail
    from openjiuwen.agent_teams.workflow.backends.team_worker_backend import TeamWorkerBackend
    from openjiuwen.core.runner import team_runner

    monkeypatch.setattr(inprocess, "_bus", None)
    messager = inprocess.InProcessMessager()
    ready = asyncio.Event()
    backend = TeamWorkerBackend(
        model=None, team_name="team-a", session_id="session-a", run_id="w123",
        messager=messager, on_human_prompt=lambda *_: ready.set(),
    )
    avatar = backend._sessions()
    state = _SessionState("human", None, None, "human", SwarmflowBudgetRail(avatar._budget))
    avatar._sessions["human"] = state

    async def raw_turn(state, prompt, opts, schema_json, correlation_id):
        return await avatar._await_human_reply(state, prompt, opts, correlation_id)

    monkeypatch.setattr(avatar, "_human_turn", raw_turn)
    await avatar._ensure_reply_subscription()
    wait = asyncio.create_task(avatar.send_turn("human", "approve?", {}, None, correlation_id="phase:human:0"))
    await asyncio.wait_for(ready.wait(), 1)
    record = AsyncToolRecord("task-a", "swarmflow", "pending human input")
    inject = AsyncMock(side_effect=AssertionError("input receipt must not inject task completion"))
    runtime = AsyncToolRuntime(inject=inject, registry={record.task_id: record})
    native = SimpleNamespace(async_tool_runtime=runtime)
    harness = TeamHarness(None, None, native, role=TeamRole.LEADER, member_name="leader")
    # Exercise the production leader's default owner, with no embedder override.
    controller = harness.background_task_controller
    assert controller is not None
    assert native.background_task_controller is controller
    controller.register(SwarmflowRunHandle(record.task_id, asyncio.Event(), backend, native, lambda: pytest.fail("relaunch")))
    agent = SimpleNamespace(harness=harness, team_backend=SimpleNamespace(messager=messager))
    entry = ActiveTeam("team-a", agent, "session-a")
    manager = TeamRuntimeManager()
    await manager.pool.add(entry)
    manager.bind_swarmflow_human_reply_admission(agent)
    impl = team_runner._TeamRunnerMixin()
    impl._team_runtime_manager = manager
    monkeypatch.setattr(team_runner, "_global_runner", lambda: impl)

    async def legacy(answer="legacy"):
        return await team_module.Runner.interact_agent_team(
            HumanAgentMessage(sender="user", target="swarmflow:w123:phase:human:0", body=answer),
            team_name="team-a", session_id="session-a",
        )

    async def delayed_legacy():
        # A transport may already have accepted the publication before closing.
        # Deliver that event at the real bus handler after the lifecycle fence.
        from openjiuwen.agent_teams.schema.events import EventMessage, TeamEvent, swarmflow_human_reply_topic

        await messager.publish(
            swarmflow_human_reply_topic("session-a", "team-a", "w123"),
            EventMessage(event_type=TeamEvent.WORKFLOW_HUMAN_REPLY,
                         payload={"correlation_id": "phase:human:0", "answer": "delayed legacy"},
                         sender_id="user"),
        )

    pending = SimpleNamespace(
        avatar=avatar, state=state, backend=backend, entry=entry, manager=manager, wait=wait,
        future=avatar._pending_human["phase:human:0"], legacy=legacy, delayed_legacy=delayed_legacy,
    )
    try:
        yield pending
    finally:
        wait.cancel()
        await asyncio.gather(wait, return_exceptions=True)
        await backend.aclose()
        owner.wait_for_resumable_runtime.assert_not_awaited()
        owner.interact.assert_not_awaited()
        inject.assert_not_awaited()


@pytest.mark.parametrize("legacy_first", [False, True])
async def test_real_web_native_and_legacy_share_one_pending_input(monkeypatch, owner, legacy_first):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        effects = []

        def authorize(channel):
            assert not pending.future.done()
            effects.append(channel)

        if legacy_first:
            await pending.legacy()
        calls = [reply_swarmflow(**arguments(answer=channel), channel_id=channel,
                                before_effect=lambda channel=channel: authorize(channel))
                 for channel in ("web", "live_voice")]
        if not legacy_first:
            calls.append(pending.legacy())
        results = await asyncio.gather(*calls)
        accepted = [result for result in results[:2] if result[0]]
        assert len(accepted) == (0 if legacy_first else 1)
        assert len(effects) == len(accepted)
        assert await pending.wait == ("legacy" if legacy_first else effects[0])
        assert await reply_swarmflow(**arguments(), before_effect=lambda: pytest.fail("duplicate guard")) == (
            False, "no_pending_human_reply")


@pytest.mark.parametrize("wrong", ["session", "team", "run", "correlation"])
async def test_real_app_wrong_owner_has_zero_input_effect(monkeypatch, owner, wrong):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        changes = {}
        if wrong == "session":
            pending.entry.current_session_id = "other-session"
        elif wrong == "team":
            owner.commit_runtime_ready("session-a", "other-team")
        else:
            changes["run_id" if wrong == "run" else "correlation_id"] = "other"
        result = await reply_swarmflow(**arguments(**changes), before_effect=lambda: pytest.fail("wrong-owner guard"))
        assert not result[0]
        assert not pending.future.done()
        assert pending.avatar._pending_human["phase:human:0"] is pending.future
        assert await pending.manager.pool.get("team-a") is pending.entry


async def test_real_app_revocation_preserves_same_future_for_authorized_retry(monkeypatch, owner):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        calls = []

        def reject():
            assert not pending.future.done()
            calls.append("revoked")
            raise PermissionError("scope grant revoked")

        with pytest.raises(PermissionError, match="scope grant revoked"):
            await reply_swarmflow(**arguments(), before_effect=reject)
        assert calls == ["revoked"] and not pending.future.done()

        def accept():
            assert not pending.future.done()
            calls.append("accepted")

        assert await reply_swarmflow(**arguments(), before_effect=accept) == (True, None)
        assert pending.future.result() == arguments()["answer"]
        assert await pending.wait == arguments()["answer"]
        assert calls == ["revoked", "accepted"]


@pytest.mark.parametrize("operation", ["pause", "stop_team", "finalize"])
async def test_real_lifecycle_early_fence_blocks_app_and_legacy_input(monkeypatch, owner, operation):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        entered, release = asyncio.Event(), asyncio.Event()

        async def teardown():
            entered.set()
            await release.wait()
            return False

        pending.entry.agent.pause_coordination = teardown
        pending.entry.agent.stop_coordination = teardown
        pending.entry.agent.is_shutdown_requested = teardown
        pending.entry.agent.lifecycle = "persistent"
        closing = asyncio.create_task(getattr(pending.manager, operation)(team_name="team-a", session_id="session-a"))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not (await reply_swarmflow(**arguments(), before_effect=lambda: pytest.fail("closing guard")))[0]
            await pending.legacy()
            await pending.delayed_legacy()
            assert not pending.future.done() or pending.future.cancelled()
        finally:
            release.set()
            await closing


async def test_real_avatar_close_fences_both_inputs_before_waiting_for_turn_lock(monkeypatch, owner):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        assert pending.state.lock.locked()
        closing = asyncio.create_task(pending.avatar.close_session("human"))
        try:
            await asyncio.sleep(0)
            assert not (await reply_swarmflow(**arguments(), before_effect=lambda: pytest.fail("closed guard")))[0]
            await pending.legacy()
            await asyncio.wait_for(closing, 1)
            assert pending.future.cancelled()
            assert pending.wait.cancelled()
            assert "human" not in pending.avatar._sessions
        finally:
            closing.cancel()
            await asyncio.gather(closing, return_exceptions=True)


def _web_reply_boundary():
    from jiuwenswarm.common.schema.agent import AgentRequest
    from jiuwenswarm.common.schema.message import ReqMethod
    from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm

    facade = JiuWenSwarm.__new__(JiuWenSwarm)
    facade._ensure_adapter = Mock(side_effect=AssertionError("reply cannot construct an Agent adapter"))
    request = AgentRequest(
        request_id="web-human-input", channel_id="web", session_id="session-a",
        req_method=ReqMethod.CHAT_SWARMFLOW_REPLY,
        params={"run_id": "w123", "correlation_id": "phase:human:0", "answer": "Web answer"},
    )
    return facade, request


def _native_reply_boundary():
    from jiuwenswarm.common.schema.live_voice_contract_v2 import Assurance, ScopeRef
    from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction
    from jiuwenswarm.server.live_voice.native_business_router import NativeBusinessRouter

    scope = ScopeRef("user", "project", "session-a", Assurance.AUTHENTICATED)
    current = SimpleNamespace(context=SimpleNamespace(require_usable=Mock()))
    route = SimpleNamespace(binding=SimpleNamespace(scope=scope),
                            native_p3_authority=SimpleNamespace(principal=SimpleNamespace(require_usable=Mock())))
    router = NativeBusinessRouter(SimpleNamespace(_p3_composition=SimpleNamespace(_clock=lambda: "now")))
    router._require_context_authority = AsyncMock(return_value=current)
    router._require_work_authority = AsyncMock(return_value=current)
    router._recheck_context_authority = Mock()
    delegate = SimpleNamespace(source_identity="native-human-input", business=NativeBusinessAction(
        "workflow.reply", "a" * 64, "w123", None, None, "Native answer", None, input_id="phase:human:0"))
    return router, route, delegate, current


@pytest.mark.parametrize("native_first", [False, True])
async def test_actual_web_and_native_entrypoints_compete_for_the_same_sdk_future(monkeypatch, owner, native_first):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        facade, request = _web_reply_boundary()
        router, route, delegate, current = _native_reply_boundary()
        # The actual Native route supplies this guard to the actual Future owner.
        router._recheck_context_authority.side_effect = lambda *_: (
            None if not pending.future.done() else pytest.fail("guard after input consumption"))
        calls = [facade.process_message(request), router._workflow(route, delegate)]
        results = await asyncio.gather(*(reversed(calls) if native_first else calls))
        web, native = tuple(reversed(results)) if native_first else results
        assert web.ok is not native_first
        assert native["status"] == ("input_accepted" if native_first else "rejected")
        if web.ok:
            assert web.payload == {"ok": True, "status": "input_accepted"}
        assert await pending.wait == ("Native answer" if native_first else "Web answer")
        assert router._recheck_context_authority.call_count == int(native_first)
        assert current.context.require_usable.call_count == int(native_first)
        facade._ensure_adapter.assert_not_called()
        assert router._work_owner is None
        # Replays through both adapters cannot consume or authorize a second time.
        assert not (await facade.process_message(request)).ok
        assert (await router._workflow(route, delegate))["status"] == "rejected"
        assert router._recheck_context_authority.call_count == int(native_first)


async def test_actual_native_guard_revocation_after_pool_wait_has_zero_delivery(monkeypatch, owner):
    from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessViolation

    async with _real_pending_owner(monkeypatch, owner) as pending:
        router, route, delegate, current = _native_reply_boundary()
        authority_read = asyncio.Event()

        async def read_authority(_route):
            authority_read.set()
            return current

        router._require_work_authority = AsyncMock(side_effect=read_authority)
        # Hold the actual SDK pool lock, after Native preflight but before the
        # original owner can validate/consume the pending Future.
        lock = pending.manager.pool._lock
        await lock.acquire()
        reply = asyncio.create_task(router._workflow(route, delegate))
        try:
            await asyncio.wait_for(authority_read.wait(), 1)
            router._recheck_context_authority.assert_not_called()
            router._recheck_context_authority.side_effect = NativeBusinessViolation("ACTIVATION_RETIRED")
        finally:
            lock.release()
        with pytest.raises(NativeBusinessViolation, match="ACTIVATION_RETIRED"):
            await reply
        router._recheck_context_authority.assert_called_once_with(route, current)
        current.context.require_usable.assert_not_called()
        route.native_p3_authority.principal.require_usable.assert_not_called()
        assert not pending.future.done()
        assert pending.avatar._pending_human["phase:human:0"] is pending.future
        assert router._work_owner is None
        # The rejected reply leaves the exact input available to a valid Web reply.
        facade, request = _web_reply_boundary()
        assert (await facade.process_message(request)).ok
        assert await pending.wait == "Web answer"


async def test_actual_web_scope_override_rejects_before_sdk_consumption(monkeypatch, owner):
    async with _real_pending_owner(monkeypatch, owner) as pending:
        facade, request = _web_reply_boundary()
        request.params["session_id"] = "other-session"
        result = await facade.process_message(request)
        assert not result.ok
        assert result.payload["error"] == "swarmflow_reply_session_mismatch"
        facade._ensure_adapter.assert_not_called()
        assert not pending.future.done()
        assert pending.avatar._pending_human["phase:human:0"] is pending.future
