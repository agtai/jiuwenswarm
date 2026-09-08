"""Only durable Task acceptance can bypass optional full-context reads."""
import asyncio
import json

import pytest

from jiuwenswarm.server.live_voice.native_business_observation import is_task_acceptance_receipt, canonical_native_receipt
from tests.unit_tests.live_voice import test_openai_realtime_native_engine as f
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call, context


def accepted_receipt():
    return {"contract_version": "live-voice.native-business.v1", "operation": "task.create",
            "status": "dispatched", "task_id": "actual-task",
            "receipt": {"task_id": "actual-task", "state": "accepted"}}


@pytest.mark.parametrize("defect", ["pending", "rejected", "query", "wrong_id", "completed", "missing", "wrong_contract"])
def test_only_exact_acceptance_receipt_is_eligible(defect):
    receipt = accepted_receipt()
    assert is_task_acceptance_receipt(receipt)
    if defect == "pending": receipt["status"] = "pending"
    elif defect == "rejected": receipt["status"] = "rejected"
    elif defect == "query": receipt["operation"] = "task.status"
    elif defect == "wrong_id": receipt["receipt"]["task_id"] = "foreign-task"
    elif defect == "completed": receipt["receipt"]["state"] = "completed"
    elif defect == "missing": del receipt["receipt"]
    else: receipt["contract_version"] = "unknown"
    assert not is_task_acceptance_receipt(receipt)


@pytest.mark.asyncio
async def test_real_task_and_journal_receipt_return_before_blocked_optional_context(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    task_accepted, release = asyncio.Event(), asyncio.Event()
    original_task, original_context = router._task, router.context
    async def task(*args):
        result = await original_task(*args)
        assert result["status"] == "dispatched", result
        task_accepted.set()
        return result
    async def slow_context(*args):
        if task_accepted.is_set():
            await release.wait()
        return await original_context(*args)
    monkeypatch.setattr(router, "_task", task)
    monkeypatch.setattr(router, "context", slow_context)
    create = asyncio.create_task(call(env, "task.create", name="Actual receipt",
        instruction="Read project notes and write a report"))
    try:
        await asyncio.wait_for(task_accepted.wait(), 2)
        receipt, params = await asyncio.wait_for(asyncio.shield(create), .7)
        assert is_task_acceptance_receipt(receipt), receipt
        store = env.harness.composition._core.store
        actual = store.get_task(receipt["task_id"], env.binding.scope)
        assert actual.state.value == "accepted"
        before = store.counts()
        replay = await env.registry.handle_native_propose(params=params, request_id="call", session_id="session-1")
        assert json.loads(replay.payload["result"]["canonical_text"]) == receipt
        assert store.counts() == before
        assert not release.is_set()
        release.set()
        refreshed = await context(env)
        assert any(task["task_id"] == receipt["task_id"] for task in refreshed["tasks"])
        assert router.task_origins(env.binding.scope) == (receipt["task_id"],)
    finally:
        release.set()
        await asyncio.gather(create, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("continuation", ["forbidden_mutation", "fresh_context"])
async def test_acceptance_speech_does_not_wait_and_dependent_steps_require_fresh_context(continuation):
    refresh_entered, release = asyncio.Event(), asyncio.Event()
    async def refresh():
        refresh_entered.set()
        await release.wait()
        return {"context": f.business_context(), "work_events": []}
    function = f.business_function("f1", "p1", "call1")
    function["name"] = "jiuwen_task_create"
    function["arguments"] = json.dumps({"request_text": "Write report", "context_id": "a" * 64,
        "name": "Report", "instruction": "Read notes and write a report"})
    engine, socket, _ = f.active_engine(f.speech_started("s1", "u1", 0),
        f.speech_stopped("e1", "u1", 500), f.input_committed("c1", "u1"),
        f.response_created("r1", "p1"), function, f.response_done("d1", "p1"))
    engine.configure_business_context(f.business_context(), refresh=refresh,
        receipt_projection=True, continuation_preparation=True)
    await engine.start()
    try:
        _, _, commit = await f.accept_basic_turn(engine)
        await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
        await engine.next_event()
        await engine.admit_response("p1", f.response_ref(1))
        assert (await engine.next_event()).delegate.business.operation == "task.create"
        await engine.next_event()
        canonical = canonical_native_receipt(accepted_receipt())
        result = await asyncio.wait_for(engine.send_delegate_result("call1", f.response_ref(1), canonical), .3)
        assert result[1] is not None and not refresh_entered.is_set()
        requests = [event for event in socket.sent if event["type"] == "response.create"]
        assert len(requests) == 2 and requests[-1]["response"]["tool_choice"] == "auto"
        assert [tool["name"] for tool in requests[-1]["response"]["tools"]] == ["jiuwen_context_get"]
        assert "one brief natural sentence" in requests[-1]["response"]["instructions"]
        before = tuple(socket.sent)
        assert await engine.send_delegate_result("call1", f.response_ref(1), canonical) == result
        assert tuple(socket.sent) == before
        socket.push(f.response_created("r2", "p2"))
        await engine.next_event()
        await engine.admit_response("p2", f.response_ref(2))
        before = engine.snapshot().delegate_count
        followup = f.business_function("followup", "p2", "call2")
        if continuation == "forbidden_mutation":
            followup["name"] = "jiuwen_task_create"
            followup["arguments"] = function["arguments"]
            socket.push(followup)
            with pytest.raises(f.OpenAIRealtimeNativeInteractionError) as rejected:
                await engine.next_event()
            assert rejected.value.reason == "NATIVE_RECEIPT_TOOL_FORBIDDEN"
            assert engine.snapshot().delegate_count == before
        else:
            followup["name"] = "jiuwen_context_get"
            followup["arguments"] = json.dumps({"request_text": "Continue the user's dependent steps", "context_id": None})
            socket.push(followup)
            assert (await engine.next_event()).delegate.business.operation == "context.get"
            socket.push(f.response_done("d2", "p2"))
            await engine.next_event()
            release.set()
            await engine.send_delegate_result("call2", f.response_ref(2), canonical_native_receipt({
                "contract_version": "live-voice.native-business.v1", "operation": "context.get",
                "status": "observed", "context": f.business_context()}))
            assert refresh_entered.is_set()
            request = [event for event in socket.sent if event["type"] == "response.create"][-1]
            assert request["response"]["tool_choice"] == "auto"
            assert "tools" not in request["response"]  # Restores session's complete tool set.
    finally:
        release.set()
        await engine.close()
