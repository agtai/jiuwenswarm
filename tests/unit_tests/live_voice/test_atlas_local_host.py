import json
from types import SimpleNamespace

import pytest
from aiohttp import web

from jiuwenswarm.server.live_voice.atlas_local_host import AtlasLocalHost, VERSION
from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessViolation


@pytest.mark.asyncio
async def test_pair_scope_pin_and_acceptance_unknown_never_redispatch(tmp_path):
    calls = []
    async def callback(request):
        assert request.headers["Authorization"] == "Bearer " + "a" * 64
        assert "Origin" not in request.headers
        body = await request.json()
        calls.append(body)
        if body["method"] == "context":
            return web.json_response({"ok": True, "result": {"history": [], "calls": []}})
        return web.json_response({"ok": True, "result": {"turnId": "real-atlas-turn", "mandateId": "real-mandate"}})
    app = web.Application()
    app.router.add_post("/live-voice/business", callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    path = tmp_path / "pair.json"
    registration = {"version": VERSION, "endpoint": f"http://127.0.0.1:{port}/live-voice/business", "token": "a" * 64,
        "swarm_session_id": "swarm", "binding": {"sessionId": "atlas", "bindingId": "binding"}}
    path.write_text(json.dumps(registration), encoding="utf-8")
    host = AtlasLocalHost(path)
    binding = SimpleNamespace(session_id="swarm", interaction_id="i", activation_id="a", activation_generation=1)
    try:
        assert await host.context(binding) == {"history": [], "tasks": [], "works": [], "events": []}
        foreign = SimpleNamespace(**{**vars(binding), "session_id": "foreign"})
        with pytest.raises(NativeBusinessViolation):
            await host.context(foreign)
        assert len(calls) == 1
        delegate = SimpleNamespace(business=SimpleNamespace(operation="task.create", instruction=None),
            source_identity="provider-identity", request_text="Create a file", turn_id="native-turn")
        result = await host.execute(binding, delegate)
        assert result["receipt"]["state"] == "accepted"
        assert result["receipt"]["atlas_turn_id"] == "real-atlas-turn"
        assert calls[-1]["params"]["nativeTurnKey"] == '["i","native-turn"]'
        registration["binding"]["bindingId"] = "replacement"
        path.write_text(json.dumps(registration), encoding="utf-8")
        with pytest.raises(NativeBusinessViolation):
            await host.context(binding)
        assert len(calls) == 2
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_terminal_facts_and_explicit_ui_only_operations(tmp_path):
    host = AtlasLocalHost(tmp_path / "unused")
    async def observed(binding, method, params):
        return {"history": [], "calls": [{"callId": "task:c", "requestText": "Do work", "revision": 3,
            "status": phase, "turnId": "t", "mandateId": "m", "text": "actual result", "files": [], "textTruncated": False}]}
    host._call = observed
    binding = SimpleNamespace(session_id="s")
    for phase in ("accepted", "running", "waiting_for_user"):
        assert (await host.context(binding))["events"] == []
    phase = "completed"
    result = await host.context(binding)
    assert result["events"][0]["result_text"] == "actual result"
    assert result["events"][0]["state"] == "completed"
    delegate = SimpleNamespace(business=SimpleNamespace(operation="task.cancel"))
    assert (await host.execute(binding, delegate))["reason"] == "ATLAS_OPERATION_REQUIRES_EXISTING_ATLAS_UI"


@pytest.mark.asyncio
async def test_opted_in_router_does_not_create_swarm_executor(tmp_path, monkeypatch):
    from tests.unit_tests.live_voice.test_native_business_registry import make_registry, context, call
    env = await make_registry(tmp_path, monkeypatch)
    executions = []
    async def host_context(_binding):
        return {"history": [], "tasks": [], "works": [], "events": []}
    async def host_execute(_binding, delegate):
        executions.append(delegate.request_text)
        return {"status": "dispatched", "task_id": "atlas:task:c", "receipt": {"state": "accepted"}}
    env.registry._native_business._atlas_host = SimpleNamespace(context=host_context, execute=host_execute)
    try:
        await context(env)
        # The registry test's public helper exercises native admission and journal.
        result, _ = await call(env, "task.create", name="Atlas work", instruction="work")
        assert result["status"] == "dispatched"
        assert executions
        assert env.manager.agent.executions == []
        assert env.registry._native_business._executors == {}
        rejected = await env.registry.handle_unified_submit(params={}, request_id="legacy-text", session_id="session-1", channel_id="web")
        assert not rejected.ok
        assert rejected.payload["error"]["reason"] == "ATLAS_TEXT_REQUIRES_ATLAS_CHAT"
        assert len(executions) == 1
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()
