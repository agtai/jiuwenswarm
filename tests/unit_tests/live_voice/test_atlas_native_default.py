import asyncio
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.server.live_voice.atlas_demo_routing import routes_to_atlas
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call, context as read_context


@pytest.mark.parametrize("operation,name,target,expected", [
    ("work.start", None, None, False),
    ("task.create", "Paris itinerary and coffee shops", None, False),
    ("task.create", "atlas:expense", None, True),
    ("task.create", "atlas:repurchase", None, True),
    ("task.approve", None, "atlas:task:coffee", True),
    ("task.result", None, "native-task", False),
])
def test_explicit_selection_not_keyword_classification(operation, name, target, expected):
    assert routes_to_atlas(SimpleNamespace(operation=operation, name=name, target_id=target)) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("demo_available", [True, False])
async def test_native_work_and_task_remain_real_with_demo_adapter(tmp_path, monkeypatch, demo_available):
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    demo_calls, native_calls, demo_tasks = [], [], []
    async def observe(_binding):
        if not demo_available:
            raise ConnectionError("Demo unavailable")
        return {"history": [], "tasks": demo_tasks, "works": [], "events": [],
                "capabilities": ["repurchase", "expense"]}
    async def execute(_binding, delegate, **kwargs):
        demo_calls.append(delegate.business.operation)
        target = "atlas:task:expense-1"
        if delegate.business.operation == "task.create":
            demo_tasks.append({"task_id": target, "revision_number": 1, "name": "Paris expense",
                               "state": "running", "supported_operations": ["task.result"]})
            return {"status": "dispatched", "task_id": target}
        return {"status": "observed", "task": demo_tasks[0]}
    async def agent(execution):
        native_calls.append(execution)
        yield AgentResponseChunk(request_id=execution.request_id, channel_id="web",
            payload={"event_type": "chat.final", "content": "Native lookup result"}, is_complete=True)
    router._atlas_host = SimpleNamespace(context=observe, execute=execute)
    monkeypatch.setattr(env.manager.agent, "process_formal_live_voice_stream", agent)
    try:
        task, _ = await call(env, "task.create", stem="trip", name="Paris itinerary", instruction="Prepare itinerary")
        assert task["status"] == "dispatched"
        assert not task["task_id"].startswith("atlas:")
        assert "native_origin" in task
        assert env.harness.composition._core.store.get_task(task["task_id"], env.binding.scope)
        work, _ = await call(env, "work.start", stem="weather", instruction="Look up tomorrow's Paris weather")
        assert work["work"]["state"] == "accepted"
        owner = router.works()
        for _ in range(100):
            snapshot = owner.query(scope=env.binding.scope, work_id=work["work"]["work_id"])
            if snapshot.execution_settled:
                break
            await asyncio.sleep(.01)
        assert snapshot.result_text == "Native lookup result"
        assert len(native_calls) == 1 and native_calls[0].read_only_tools
        assert demo_calls == []
        # Old Atlas text has no timestamps; it cannot replace newer native turns.
        monkeypatch.setattr("jiuwenswarm.server.live_voice.native_business_router.load_history_records",
                            lambda _: [{"role": "user", "content": "And tomorrow's temperature?"}])
        original_observe = observe
        async def old_demo_history(binding):
            facts = await original_observe(binding)
            return {**facts, "history": [{"role": "assistant", "content": "Old expense details"}] * 24}
        router._atlas_host.context = old_demo_history
        context = await read_context(env)
        assert context["history"][-1]["content"] == "And tomorrow's temperature?"
        demo, _ = await call(env, "task.create", stem="expense", name="atlas:expense", instruction="Expense the Paris trip")
        if demo_available:
            assert demo["task_id"].startswith("atlas:") and "native_origin" not in demo
            listed, _ = await call(env, "task.list", stem="list")
            assert {task["task_id"], demo["task_id"]} <= {item["task_id"] for item in listed["tasks"]}
            await call(env, "task.result", stem="detail", target_id=demo["task_id"])
            assert demo_calls == ["task.create", "task.result"]
            blocked, _ = await call(env, "task.create", stem="busy", name="atlas:repurchase", instruction="Reorder March coffee")
            assert blocked["reason"] == "ATLAS_DEMO_BUSY" and blocked["status"] == "rejected"
            assert demo_calls == ["task.create", "task.result"] and len(native_calls) == 1
            native, _ = await call(env, "task.create", stem="native-while-demo", name="Travel notes", instruction="Prepare notes")
            assert native["status"] == "dispatched" and not native["task_id"].startswith("atlas:")
        else:
            assert demo["status"] == "rejected" and demo["reason"] == "ATLAS_DEMO_UNAVAILABLE"
            assert demo_calls == [] and len(native_calls) == 1
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_slow_demo_context_is_bounded_and_cannot_supply_stale_capabilities(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    cancelled = asyncio.Event()
    async def stuck(_binding):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    env.registry._native_business._atlas_host = SimpleNamespace(context=stuck)
    try:
        observed = await asyncio.wait_for(read_context(env), 4)
        assert observed["capabilities"] == [] and cancelled.is_set()
        assert observed["tasks"] == [] and not env.manager.agent.executions
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()
