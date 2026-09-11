"""Real Native Registry/SQLite receipts retain exact as-of adjustment facts."""
import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from jiuwenswarm.server.runtime.formal_tasks.formal_task_models import TerminalOutcome
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call, context
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import NativeRuntimeClientError
from tests.unit_tests.live_voice.test_p3_authenticated_composition import _observations


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["pending", "applied", "terminal", "unavailable", "wrong-task", "wrong-attempt", "unknown", "bool-head", "overflow-head"])
async def test_adjustment_observation_is_exact_and_sealed_once(tmp_path, monkeypatch, outcome):
    env = await make_registry(tmp_path, monkeypatch)
    core = env.harness.composition._core
    dispatched = []
    dispatch = env.harness.executor.dispatch
    async def record_dispatch(item):
        dispatched.append(item)
        return await dispatch(item)
    monkeypatch.setattr(env.harness.executor, "dispatch", record_dispatch)
    try:
        a, _ = await call(env, "task.create", stem="a", name="Report A", instruction="Write report A")
        b, _ = await call(env, "task.create", stem="b", name="Report B", instruction="Write report B")
        await core.drain_outbox()
        unchanged = core.store.get_task(b["task_id"], env.binding.scope)
        calls = []
        settlement_errors = []
        entered, release, second_arrived = asyncio.Event(), asyncio.Event(), asyncio.Event()
        first_text = []
        read = env.harness.composition.read_task_control_snapshot
        async def settle_then_read(**kwargs):
            calls.append(kwargs)
            entered.set()
            await asyncio.wait_for(release.wait(), 5)
            assert kwargs["task_id"] == a["task_id"]
            assert kwargs["native_authority"] is env.registry._p2_routes[("session-1", "interaction-1")].native_p3_authority
            if outcome == "applied":
                await core.drain_outbox()
                await core.drain_inflight_adjustments()
            if outcome == "terminal":
                item = next(item for item in dispatched if item.task_id == a["task_id"])
                terminal = _observations(item, outcome=TerminalOutcome.COMPLETED)[-1]
                try:
                    core.store.apply_observations((terminal,))
                except Exception as error:
                    settlement_errors.append((type(error).__name__, getattr(error, "reason", str(error))))
                    raise
            if outcome == "unavailable":
                raise OSError("private diagnostic must not reach receipt")
            facts = await read(**kwargs)
            if outcome == "wrong-task": facts["task_id"] = b["task_id"]
            if outcome == "wrong-attempt": facts["attempt_id"] = "other-attempt"
            if outcome == "unknown": facts["requested_adjustment_state"] = "unknown"
            if outcome == "bool-head": facts["event_head"] = True
            if outcome == "overflow-head": facts["event_head"] = 9_007_199_254_740_992
            return facts
        monkeypatch.setattr(env.harness.composition, "read_task_control_snapshot", settle_then_read)
        target = next(t for t in (await context(env))["tasks"] if t["task_id"] == a["task_id"])
        handle = env.registry.handle_native_propose
        async def observe_second(**kwargs):
            if entered.is_set() and not release.is_set(): second_arrived.set()
            return await handle(**kwargs)
        monkeypatch.setattr(env.registry, "handle_native_propose", observe_second)
        propose = env.client.propose
        async def duplicate_during_observation(**kwargs):
            first = asyncio.create_task(propose(**kwargs))
            second = None
            try:
                await asyncio.wait_for(entered.wait(), 5)
                second = asyncio.create_task(propose(**kwargs))
                await asyncio.wait_for(second_arrived.wait(), 5)
                release.set()
                outputs = await asyncio.gather(first, second)
                assert outputs[0]["canonical_text"] == outputs[1]["canonical_text"]
                first_text.append(outputs[0]["canonical_text"])
                return outputs[0]
            finally:
                release.set()
                await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)
        monkeypatch.setattr(env.client, "propose", duplicate_during_observation)
        adjusted, params = await call(env, "task.adjust", stem="adjust", target_id=a["task_id"],
            expected_revision=target["revision_number"], adjustment="Add internal review marker")
        assert adjusted["status"] == "dispatched"
        assert not settlement_errors
        assert adjusted["receipt"]["adjustment_state"] == "pending"
        observation = adjusted["adjustment_observation"]
        expected = {"applied": "applied", "terminal": "rejected", "pending": "pending"}.get(outcome, "unknown")
        assert observation["state"] == expected
        assert all(observation[k] == adjusted["receipt"][k] for k in ("task_id", "attempt_id", "adjustment_id"))
        if outcome == "terminal":
            assert observation["reason"] == "TASK_TERMINAL_BEFORE_ADJUSTMENT"
            assert core.store.get_task(a["task_id"], env.binding.scope).outcome is TerminalOutcome.COMPLETED
            assert env.harness.executor.adjustments == []
        if outcome == "applied":
            assert env.harness.executor.adjustments == [adjusted["receipt"]["adjustment_id"]]
        assert len(calls) == 1 and calls[0]["adjustment_id"] == observation["adjustment_id"]
        assert "private diagnostic" not in json.dumps(adjusted)
        before = core.store.counts()
        replay = await env.registry.handle_native_propose(params=params, request_id="adjust", session_id="session-1")
        assert replay.ok, replay.payload
        assert replay.payload["result"]["canonical_text"] == first_text[0]
        assert json.loads(replay.payload["result"]["canonical_text"]) == adjusted
        assert len(calls) == 1 and core.store.counts() == before
        assert core.store.get_task(b["task_id"], env.binding.scope) == unchanged
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_adjustment_observation_cancellation_is_not_an_unknown_receipt(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    try:
        async def cancelled(**kwargs): raise asyncio.CancelledError
        monkeypatch.setattr(env.harness.composition, "read_task_control_snapshot", cancelled)
        route = env.registry._p2_routes[("session-1", "interaction-1")]
        result = {"task_id": "task-a", "receipt": {"task_id": "task-a", "attempt_id": "attempt-a", "adjustment_id": "adjust-a"}}
        before = env.harness.composition._core.store.counts()
        with pytest.raises(asyncio.CancelledError):
            await env.registry._native_business._adjustment_observation(route, result)
        assert env.harness.composition._core.store.counts() == before
        assert not env.manager.agent.executions
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("settled", ["applied", "rejected"])
async def test_unknown_observation_preserves_confirmed_original_receipt(tmp_path, monkeypatch, settled):
    env = await make_registry(tmp_path, monkeypatch)
    try:
        result = {"task_id": "task-a", "status": "dispatched", "receipt": {
            "task_id": "task-a", "attempt_id": "attempt-a", "adjustment_id": "adjust-a", "adjustment_state": settled}}
        original = deepcopy(result)
        async def unknown(**kwargs):
            return {"task_id": "task-a", "attempt_id": "attempt-a", "requested_adjustment_state": "unknown", "event_head": 100}
        monkeypatch.setattr(env.harness.composition, "read_task_control_snapshot", unknown)
        route = env.registry._p2_routes[("session-1", "interaction-1")]
        observation = await env.registry._native_business._adjustment_observation(route, result)
        assert observation["state"] == "unknown" and result == original
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("retirement", ["close", "rebind"])
async def test_observation_wait_cannot_publish_after_authority_retirement(tmp_path, monkeypatch, retirement):
    env = await make_registry(tmp_path, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    pending = None
    try:
        task, _ = await call(env, "task.create", name="Report", instruction="Write report")
        await env.harness.composition._core.drain_outbox()
        route = env.registry._p2_routes[("session-1", "interaction-1")]
        owner = route.native_runtime_owner
        read = env.harness.composition.read_task_control_snapshot
        async def stale_read(**kwargs):
            facts = await read(**kwargs)
            entered.set()
            await asyncio.wait_for(release.wait(), 5)
            return facts
        monkeypatch.setattr(env.harness.composition, "read_task_control_snapshot", stale_read)
        target = next(t for t in (await context(env))["tasks"] if t["task_id"] == task["task_id"])
        pending = asyncio.create_task(call(env, "task.adjust", stem="adjust-retired", target_id=task["task_id"],
            expected_revision=target["revision_number"], adjustment="Add internal marker"))
        await asyncio.wait_for(entered.wait(), 5)
        before = owner.snapshot()
        counts = env.harness.composition._core.store.counts()
        if retirement == "close":
            await asyncio.wait_for(env.registry.close_active_routes(), 3)
        else:
            authority = env.harness.authority
            authority.contexts["session-1"] = replace(authority.contexts["session-1"], uri=(tmp_path / "rebound").as_uri())
        release.set()
        with pytest.raises(NativeRuntimeClientError):
            await asyncio.wait_for(pending, 5)
        after = owner.snapshot()
        assert (after.audio_count, after.history_count, after.response_count) == (before.audio_count, before.history_count, before.response_count)
        assert env.harness.composition._core.store.counts() == counts
        assert env.harness.executor.adjustments == [] and env.manager.agent.executions == []
    finally:
        release.set()
        if pending is not None: await asyncio.gather(pending, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()
