import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.native_business_tools import native_business_proposal_from_function_call, native_business_tools
from jiuwenswarm.server.live_voice.atlas_local_host import AtlasLocalHost
from tests.unit_tests.live_voice.test_native_business_tools import binding


def test_weather_tool_retains_explicit_query_and_current_user_turn():
    values = {"request_text": "帮我查巴黎明天天气", "location": "巴黎", "date": "tomorrow", "language": "zh"}
    proposal = native_business_proposal_from_function_call(name="jiuwen_bound_weather_get",
        arguments=json.dumps(values), server_context_id="a" * 64, **binding())
    assert proposal.business.operation == "weather.get"
    assert json.loads(proposal.business.instruction) == {k: values[k] for k in ("location", "date", "language")}
    assert proposal.request_text == values["request_text"]
    tool = next(tool for tool in native_business_tools(bound_context=True) if tool["name"] == "jiuwen_bound_weather_get")
    assert set(tool["parameters"]["required"]) == set(values)


@pytest.mark.asyncio
async def test_native_result_card_is_scoped_updates_in_place_and_uses_saved_result(tmp_path):
    host = AtlasLocalHost(tmp_path / "unused")
    b = SimpleNamespace(session_id="s", interaction_id="i")
    host.remember_result_origin(b, SimpleNamespace(request_text="Write a report", turn_id="t"), {"task_id": "task-1"})
    events = []
    async def callback(_binding, method, params):
        assert method == "result"
        events.append(params["resultEvent"])
        return {"published": True}
    host._call = callback
    running = {"task_id": "task-1", "name": "Report", "state": "running"}
    await host.publish_native_results(b, [running], [], [])
    await host.publish_native_results(b, [running], [], [])
    done = {**running, "state": "terminal", "outcome": "completed", "result_text": "Report saved.",
            "artifacts": [{"path": "report.md"}], "model_identity": "must-not-display"}
    await host.publish_native_results(b, [done], [], [])
    await host.publish_native_results(SimpleNamespace(session_id="other"), [done], [], [])
    assert len(events) == 2
    assert events[0]["card"]["id"] == events[1]["card"]["id"]
    assert events[1]["card"]["revision"] == 2
    assert events[1]["card"]["summary"] == "Report saved."
    assert "report.md" in events[1]["card"]["details"]
    assert "must-not-display" not in json.dumps(events)


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_weather_routes_through_bound_host_without_agent_or_task_creation(tmp_path, monkeypatch, fails):
    from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call
    env = await make_registry(tmp_path, monkeypatch)
    host = AtlasLocalHost(tmp_path / "unused")
    queries = []
    async def callback(_binding, method, params):
        if method == "context":
            return {"history": [], "calls": []}
        assert method == "weather"
        queries.append(params)
        if fails:
            raise TimeoutError("Weather unavailable")
        return {"status": "completed", "source": "Open-Meteo", "selected_date": "2026-09-16",
                "forecast": {"tMin": 10, "tMax": 20, "precip": 30}}
    host._call = callback
    env.registry._native_business._atlas_host = host
    before = env.harness.composition._core.store.counts()
    try:
        result, _ = await call(env, "weather.get", instruction=json.dumps({"location": "Paris", "date": "tomorrow", "language": "en"}))
        assert result["status"] == ("rejected" if fails else "completed")
        assert queries[0]["query"]["location"] == "Paris"
        assert env.manager.agent.executions == []
        assert env.registry._native_business._executors == {}
        assert env.harness.composition._core.store.counts() == before
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()
