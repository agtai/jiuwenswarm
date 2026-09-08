"""Exact Task acceptance and nonterminal Work feedback bypass optional reads."""
import asyncio
import json

import pytest

from jiuwenswarm.server.live_voice.native_business_observation import (
    is_task_acceptance_receipt, is_nonterminal_work_start_receipt, canonical_native_receipt,
)
from tests.unit_tests.live_voice import test_openai_realtime_native_engine as f
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call, context


def accepted_receipt():
    return {"contract_version": "live-voice.native-business.v1", "operation": "task.create",
            "status": "dispatched", "task_id": "actual-task",
            "receipt": {"task_id": "actual-task", "state": "accepted"}}


def work_receipt():
    return {"contract_version": "live-voice.native-business.v1", "operation": "work.start",
            "work": {"work_id": "actual-work", "revision": 1, "sequence": 1,
                     "state": "accepted", "execution_settled": False, "reason": None}}


@pytest.mark.parametrize("defect", ["completed", "failed", "unknown", "cancelling", "cancelled", "superseded",
    "wrong_contract", "other_operation", "rejected", "reason", "missing_work", "bad_work", "bad_state",
    "missing_id", "bool_revision", "zero_sequence", "settled", "result"])
def test_work_feedback_requires_exact_unsettled_nonterminal_start(defect):
    receipt = work_receipt()
    assert is_nonterminal_work_start_receipt(receipt)
    assert not is_task_acceptance_receipt(receipt)
    receipt["work"]["state"] = "running"
    assert is_nonterminal_work_start_receipt(receipt)
    if defect in {"completed", "failed", "unknown", "cancelling", "cancelled", "superseded"}: receipt["work"]["state"] = defect
    elif defect == "wrong_contract": receipt["contract_version"] = "wrong"
    elif defect == "other_operation": receipt["operation"] = "work.get"
    elif defect == "rejected": receipt["status"] = "rejected"
    elif defect == "reason": receipt["work"]["reason"] = "error"
    elif defect == "missing_work": del receipt["work"]
    elif defect == "bad_work": receipt["work"] = []
    elif defect == "bad_state": receipt["work"]["state"] = {}
    elif defect == "missing_id": receipt["work"]["work_id"] = ""
    elif defect == "bool_revision": receipt["work"]["revision"] = True
    elif defect == "zero_sequence": receipt["work"]["sequence"] = 0
    elif defect == "settled": receipt["work"]["execution_settled"] = True
    elif defect == "result": receipt["work"]["result_text"] = "already complete"
    assert not is_nonterminal_work_start_receipt(receipt)


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
async def test_real_work_keeps_router_context_and_journal_without_task_mutation(tmp_path, monkeypatch):
    from jiuwenswarm.common.schema.agent import AgentResponseChunk
    from jiuwenswarm.server.live_voice.native_work_journal import SqliteNativeWorkJournal
    from tests.unit_tests.live_voice.test_native_work_runtime import terminal
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    admitted, release_context, release_agent = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_work, original_context = router._work, router.context
    executions = []
    async def agent(execution):
        executions.append(execution)
        await release_agent.wait()
        yield AgentResponseChunk(request_id=execution.request_id, channel_id=execution.channel_id,
                                 payload={"event_type": "chat.final", "content": "Verified lookup result"}, is_complete=True)
    async def work(*args):
        outcome = await original_work(*args)
        admitted.set()
        return outcome
    async def slow_context(*args):
        if admitted.is_set(): await release_context.wait()
        return await original_context(*args)
    monkeypatch.setattr(env.manager.agent, "process_formal_live_voice_stream", agent)
    monkeypatch.setattr(router, "_work", work)
    monkeypatch.setattr(router, "context", slow_context)
    before = env.harness.composition._core.store.counts()
    operation = asyncio.create_task(call(env, "work.start", instruction="Look up the current weather"))
    try:
        await asyncio.wait_for(admitted.wait(), 2)
        await asyncio.sleep(0)
        assert not operation.done()  # Router retains the full-context legacy contract.
        release_context.set()
        receipt, params = await asyncio.wait_for(asyncio.shield(operation), .7)
        assert is_nonterminal_work_start_receipt(receipt), receipt
        assert not is_task_acceptance_receipt(receipt)
        assert "context" in receipt
        work_id = receipt["work"]["work_id"]
        persisted = SqliteNativeWorkJournal(router._work_journal.database_path).restore()
        assert any(item.work_id == work_id and item.revision == 1 for item in persisted)
        # A replay is the exact journal receipt, with no second work execution.
        replay = await env.registry.handle_native_propose(params=params, request_id="call", session_id="session-1")
        assert json.loads(replay.payload["result"]["canonical_text"]) == receipt
        assert len(router.works().list(scope=env.binding.scope)) == 1
        assert len(executions) == 1
        assert env.harness.composition._core.store.counts() == before
        assert router.task_origins(env.binding.scope) == ()
        release_agent.set()
        completed = await terminal(router.works(), router.works().query(scope=env.binding.scope, work_id=work_id))
        assert completed.state.value == "completed" and completed.result_text == "Verified lookup result"
        assert env.harness.composition._core.store.counts() == before
    finally:
        release_context.set()
        release_agent.set()
        await asyncio.gather(operation, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("continuation", ["forbidden_mutation", "fresh_context"])
@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("kind", ["task", "work"])
async def test_acceptance_speech_does_not_wait_and_dependent_steps_require_fresh_context(continuation, bound, kind):
    refresh_entered, release = asyncio.Event(), asyncio.Event()
    async def refresh():
        refresh_entered.set()
        await release.wait()
        return {"context": f.business_context(), "work_events": []}
    function = f.business_function("f1", "p1", "call1")
    function["name"] = "jiuwen_task_create"
    function["arguments"] = json.dumps({"request_text": "Write report", "context_id": "a" * 64,
        "name": "Report", "instruction": "Read notes and write a report"})
    if kind == "work":
        function["name"] = "jiuwen_work_start"
        function["arguments"] = json.dumps({"request_text": "Look up tomorrow's weather", "context_id": "a" * 64,
                                           "instruction": "Look up tomorrow's weather"})
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
        assert (await engine.next_event()).delegate.business.operation == ("task.create" if kind == "task" else "work.start")
        await engine.next_event()
        canonical = canonical_native_receipt(accepted_receipt() if kind == "task" else work_receipt())
        result = await asyncio.wait_for(engine.send_delegate_result("call1", f.response_ref(1), canonical), .3)
        assert result[1] is not None and not refresh_entered.is_set()
        requests = [event for event in socket.sent if event["type"] == "response.create"]
        assert len(requests) == 2 and requests[-1]["response"]["tool_choice"] == "auto"
        assert [tool["name"] for tool in requests[-1]["response"]["tools"]] == ["jiuwen_bound_context_get"]
        if kind == "task":
            assert "one brief natural sentence" in requests[-1]["response"]["instructions"]
        else:
            assert "This is not durable Task" in requests[-1]["response"]["instructions"]
            assert "Do not poll work.get" in requests[-1]["response"]["instructions"]
        before = tuple(socket.sent)
        assert await engine.send_delegate_result("call1", f.response_ref(1), canonical) == result
        assert tuple(socket.sent) == before
        socket.push(f.response_created("r2", "p2"))
        await engine.next_event()
        await engine.admit_response("p2", f.response_ref(2))
        before = engine.snapshot().delegate_count
        followup = f.business_function("followup", "p2", "call2")
        if continuation == "forbidden_mutation":
            followup["name"] = "jiuwen_bound_task_create" if bound else "jiuwen_task_create"
            followup["arguments"] = (json.dumps({"request_text": "Read notes and write another report", "name": "Another report"})
                                     if bound else json.dumps({"request_text": "Read notes and write another report", "context_id": "a" * 64,
                                         "name": "Another report", "instruction": "Read notes and write another report"}))
            socket.push(followup)
            with pytest.raises(f.OpenAIRealtimeNativeInteractionError) as rejected:
                await engine.next_event()
            assert rejected.value.reason == "NATIVE_RECEIPT_TOOL_FORBIDDEN"
            assert engine.snapshot().delegate_count == before
        else:
            followup["name"] = "jiuwen_bound_context_get" if bound else "jiuwen_context_get"
            followup["arguments"] = json.dumps({"request_text": "Continue the user's dependent steps",
                                                **({} if bound else {"context_id": None})})
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


async def ready_work_receipt_engine(*, projection=True, refresh=None):
    function = f.function_done("f1", "p1", call_id="call1", item_id="item-call1", name="jiuwen_bound_work_start",
        arguments=json.dumps({"request_text": "Look up tomorrow's weather"}))
    engine, socket, _ = f.active_engine(f.speech_started("s1", "u1", 0), f.speech_stopped("e1", "u1", 500),
        f.input_committed("c1", "u1"), f.response_created("r1", "p1"), function, f.response_done("d1", "p1"))
    engine.configure_business_context(f.business_context(), refresh=refresh,
        receipt_projection=projection, continuation_preparation=True)
    await engine.start()
    _, _, commit = await f.accept_basic_turn(engine)
    await engine.acknowledge_business_turn(commit.turn_commit.turn_id)
    await engine.next_event()
    await engine.admit_response("p1", f.response_ref(1))
    assert (await engine.next_event()).delegate.business.operation == "work.start"
    await engine.next_event()
    return engine, socket


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["before_receipt", "send_lock"])
@pytest.mark.parametrize("state,revision", [("completed", 1), ("failed", 1), ("running", 2)])
async def test_known_work_terminal_or_new_revision_cannot_get_stale_feedback(when, state, revision):
    latest = {**f.business_context(), "context_id": "b" * 64,
              "works": [{"work_id": "actual-work", "revision": revision, "state": state,
                         "execution_settled": state != "running"}]}
    refreshes=[]
    async def refresh():
        refreshes.append(True)
        return {"context": latest, "work_events": []}
    engine, socket = await ready_work_receipt_engine(refresh=refresh)
    gate=asyncio.Event()
    original_send = engine._send_response_request
    async def gate_send(request):
        gate.set()
        return await original_send(request)
    operation=None
    try:
        if when == "before_receipt":
            engine._replace_business_context(latest, [])
        else:
            engine._send_response_request = gate_send
            # Receipt write must complete first. Acquire the lock only when its
            # output is sent, so the test targets response.create's lock wait.
            send = socket.send
            async def block_response(raw):
                await send(raw)
                event=json.loads(raw)
                if event.get("item",{}).get("type") == "function_call_output":
                    asyncio.get_running_loop().call_soon(lambda: asyncio.create_task(hold()))
            held=asyncio.Event(); release=asyncio.Event()
            async def hold():
                async with engine._business_send_lock:
                    held.set()
                    await release.wait()
            socket.send=block_response
        operation=asyncio.create_task(engine.send_delegate_result("call1", f.response_ref(1), canonical_native_receipt(work_receipt())))
        if when == "send_lock":
            await asyncio.wait_for(held.wait(), .5)
            await asyncio.wait_for(gate.wait(), .5)
            engine._replace_business_context(latest, [])
            release.set()
        await asyncio.wait_for(operation,.7)
        requests=[e for e in socket.sent if e["type"]=="response.create"]
        assert len(requests)==2 and refreshes
        assert "tools" not in requests[-1]["response"]
        assert "has been accepted or is running" not in requests[-1]["response"]["instructions"]
        assert engine._sent_business_context_id == "b"*64
        assert engine.snapshot().delegate_count == 1 and engine.snapshot().released_audio_count == 0
    finally:
        if when == "send_lock": release.set()
        if operation is not None: await asyncio.gather(operation,return_exceptions=True)
        await engine.close()


@pytest.mark.asyncio
async def test_work_feature_off_retains_actual_router_context_without_restricted_tools():
    async def refresh(): raise AssertionError("Legacy receipt already carries its context")
    engine,socket=await ready_work_receipt_engine(projection=False,refresh=refresh)
    try:
        receipt=work_receipt()
        receipt["context"]={**f.business_context(),"context_id":"b"*64,"works":[receipt["work"]]}
        await engine.send_delegate_result("call1",f.response_ref(1),canonical_native_receipt(receipt))
        requests=[e for e in socket.sent if e["type"]=="response.create"]
        assert "tools" not in requests[-1]["response"]
        assert engine._sent_business_context_id == "b"*64
        assert json.loads(f.function_outputs(socket)[0]["output"])["context"] == receipt["context"]
        assert engine.snapshot().released_audio_count == 0
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_work_feedback_stop_keeps_receipt_and_discards_late_audio_without_ack():
    async def refresh(): return {"context":f.business_context(),"work_events":[]}
    engine,socket=await ready_work_receipt_engine(refresh=refresh)
    try:
        canonical=canonical_native_receipt(work_receipt())
        outcome=await engine.send_delegate_result("call1",f.response_ref(1),canonical)
        socket.push(f.response_created("r2","p2")); await engine.next_event()
        await engine.admit_response("p2",f.response_ref(2))
        await engine.stop_foreground(f.response_ref(2))
        socket.push(f.output_audio_delta("late-audio","p2","late-item",0))
        assert await engine.next_event() == f.NativeEngineEvent()
        assert engine.snapshot().released_audio_count == 0
        assert not engine._responses["p2"].presentation_acknowledged
        assert await engine.send_delegate_result("call1",f.response_ref(1),canonical) == outcome
        assert len(f.function_outputs(socket)) == 1 and engine.snapshot().delegate_count == 1
    finally:
        await engine.close()
