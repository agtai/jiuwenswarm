"""Real serialized Native admission and existing SQLite Task policy seam."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessProposal, NATIVE_BUSINESS_CONTRACT_VERSION
from jiuwenswarm.server.live_voice.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.server.live_voice.native_interaction_config import InteractionEngineKind
from jiuwenswarm.server.live_voice.product_composition_registry import AgentServerProductCompositionRegistry, ProductCompositionSettings
from jiuwenswarm.server.live_voice.p3_confirmation import BoundedP3ConfirmationOwner
from jiuwenswarm.server.live_voice.p3_product_confirmation import ProductP3ConfirmationForwarder
from tests.unit_tests.live_voice.test_native_agent_model import _model_harness, TOKEN
from tests.unit_tests.live_voice.test_product_composition_registry import (
    _AgentManager, _native_turn_proposal, _native_speak_proposal, _native_propose_params, _native_delegate_proposal,
    _native_input_transcript_proposal,
)
from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.common.e2a.wire_codec import parse_agent_server_wire_unary
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import GatewayNativeInteractionRuntimeClient, NativeRuntimeClientError
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import NativeEngineEvent


async def make_registry(tmp_path, monkeypatch, *, input_text="Perform the requested project work."):
    h, catalog, builds, confirmed, authority = await _model_harness(tmp_path)
    now = datetime.now(UTC)
    expiry = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    h.composition._clock = lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    h.composition._authenticator._principal = replace(h.composition._authenticator._principal, expires_at=expiry)
    h.authority.contexts = {key:replace(value,expires_at=expiry) for key,value in h.authority.contexts.items()}
    owner = BoundedP3ConfirmationOwner(h.database, enabled=True)
    async def push(event): return True
    manager = _AgentManager()
    registry = AgentServerProductCompositionRegistry(
        settings=ProductCompositionSettings(p2_enabled=True, p3_text_enabled=True, p3_mutation_enabled=True,
            interaction_engine=InteractionEngineKind.OPENAI_REALTIME_NATIVE),
        p3_composition=h.composition, agent_manager=manager, push_text_event=push,
        p3_confirmation_owner=owner, p3_confirmation_forwarder=ProductP3ConfirmationForwarder(owner))
    monkeypatch.setattr('jiuwenswarm.server.live_voice.native_business_router.load_history_records', lambda sid: [])
    params = {"auth_token": TOKEN, "session_id":"session-1", "correlation_id":"native-model",
        "interaction_id":"interaction-1", "activation_id":"activation-1", "activation_generation":1,
        "interaction_engine":"openai-realtime-native",
        "agent_model_selection":{"contract_version":"live-voice.agent-model-selection.v1", "model_name":"Selected Agent"}}
    active = await registry.handle_p2_activate(params=params, request_id="activate", session_id="session-1", channel_id="web")
    assert active.ok, active.payload
    descriptor = active.payload["result"]["_native_gateway"]
    binding, capability = NativeInteractionBinding.from_dict(descriptor["binding"]), descriptor["capability"]
    assert descriptor["business_contract_version"] == NATIVE_BUSINESS_CONTRACT_VERSION
    assert active.payload["result"]["agent_model_selection"]["model_identity"] == confirmed.model_identity
    proposals = [("turn", _native_turn_proposal(binding))]
    if input_text is not None:
        transcript = _native_input_transcript_proposal(binding)
        proposals.append(("input-transcript", replace(transcript,
            input_transcript=replace(transcript.input_transcript, transcript=input_text))))
    proposals.append(("speak", _native_speak_proposal(binding)))
    for rid, proposal in proposals:
        output = await registry.handle_native_propose(params=_native_propose_params(binding, capability, proposal), request_id=rid, session_id="session-1")
        assert output.ok, output.payload
    source = ResponseRef(**output.payload["result"]["response"])
    class WireClient:
        async def send_request(self, envelope):
            from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
            sent = []
            async def send(payload): sent.append(json.loads(payload))
            request = AgentRequest(request_id=envelope.request_id, channel_id=envelope.channel,
                session_id=envelope.session_id, req_method=ReqMethod(envelope.method),
                params=json.loads(json.dumps(envelope.params)))
            await AgentWebSocketServer._handle_live_voice_native_request(
                SimpleNamespace(_live_voice_product_composition=registry), SimpleNamespace(send=send), request, asyncio.Lock())
            assert len(sent) == 1
            return parse_agent_server_wire_unary(sent[0])
    client = GatewayNativeInteractionRuntimeClient(WireClient(), native_model="gpt-realtime-2")
    client.observe_activation_response(dict(active.payload), routed_session_id="session-1",
        connection_id="business-wire", request_method=ReqMethod.LIVE_VOICE_COMPOSITION_P2_ACTIVATE.value)
    return SimpleNamespace(registry=registry, harness=h, binding=binding, capability=capability, source=source,
        params=params, catalog=catalog, manager=manager, client=client)


async def context(env):
    response = await env.registry.handle_native_propose(params={"contract_version":NATIVE_BUSINESS_CONTRACT_VERSION,
        "binding":env.binding.to_dict(), "capability":env.capability, "context":True}, request_id="context", session_id="session-1")
    assert response.ok, response.payload
    return response.payload["result"]["context"]


async def call(env, operation, *, stem="call", text="Read project notes", **values):
    facts = await context(env)
    old = _native_delegate_proposal(env.binding, env.source, request_text=text)
    original = old.delegate
    action = NativeBusinessAction.from_dict({"operation":operation, "context_id":facts["context_id"],
        "target_id":None, "expected_revision":None, "name":None, "instruction":None, "adjustment":None, **values})
    delegate = NativeBusinessProposal(**{key:getattr(original,key) for key in original.__dataclass_fields__ if key not in {
        "provider_event_id","provider_call_id","provider_item_id"}},
        provider_event_id=stem+"-event", provider_call_id=stem+"-call", provider_item_id=stem+"-item", business=action)
    proposal = replace(old, delegate=delegate, action=replace(old.action, action_id=stem+"-action",
        payload=(("provider_call_id",delegate.provider_call_id),("turn_id",delegate.turn_id))))
    params = json.loads(json.dumps(_native_propose_params(env.binding,env.capability,proposal)))
    result = await env.client.propose(binding=env.binding, capability=env.capability,
        event=NativeEngineEvent(action=proposal.action,delegate=proposal.delegate), request_id=stem)
    return json.loads(result["canonical_text"]), params


@pytest.mark.asyncio
async def test_two_real_tasks_adjust_and_cancel_only_exact_observed_target(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    try:
        a,_ = await call(env,"task.create",stem="a",name="Report A",instruction="Write report A")
        b,_ = await call(env,"task.create",stem="b",name="Report B",instruction="Write report B")
        await env.harness.composition.reconcile_once()
        store = env.harness.composition._core.store
        untouched = store.get_task(b["task_id"],env.binding.scope)
        facts = await context(env)
        target = next(task for task in facts["tasks"] if task["task_id"] == a["task_id"])
        adjusted,_ = await call(env,"task.adjust",stem="adjust",target_id=a["task_id"],
            expected_revision=target["revision_number"],adjustment="Keep report A concise")
        assert adjusted["status"] == "dispatched", adjusted
        facts = await context(env)
        target = next(task for task in facts["tasks"] if task["task_id"] == a["task_id"])
        cancelled,_ = await call(env,"task.cancel",stem="cancel",target_id=a["task_id"],expected_revision=target["revision_number"])
        assert cancelled["status"] == "dispatched", cancelled
        assert store.get_task(b["task_id"],env.binding.scope) == untouched
        assert store.get_task(a["task_id"],env.binding.scope).cancel_requested
        assert any(event.event_type == "task.adjust_requested" for event in store.events(a["task_id"],env.binding.scope,after_seq=-1))
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_long_work_detail_keeps_complete_tail_and_refreshes_context_separately(tmp_path, monkeypatch):
    from tests.unit_tests.live_voice.test_native_work_runtime import admission, terminal
    env = await make_registry(tmp_path,monkeypatch)
    owner = env.registry._native_business.works()
    async def runner(control): return "x" * (131072 - 4) + "TAIL"
    try:
        works = []
        for index in range(32):
            values = admission(runner,request=f"size-{index}",input_id=f"size-input-{index}",current_scope=env.binding.scope)
            values["instruction"] = "i" * 4096
            work = await owner.start(**values)
            works.append(await terminal(owner,work))
        detail,params = await call(env,"work.get",target_id=works[-1].work_id)
        assert detail["work"]["result_text"] == "x" * (131072 - 4) + "TAIL"
        assert "context" not in detail
        assert detail["context_refresh_reason"] == "NATIVE_BUSINESS_CONTEXT_REQUIRES_REFRESH"
        replay = await env.registry.handle_native_propose(params=params,request_id="call",session_id="session-1")
        assert json.loads(replay.payload["result"]["canonical_text"]) == detail
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_creation_projection_write_failure_recovers_from_durable_receipt_without_reexecution(tmp_path,monkeypatch):
    from jiuwenswarm.server.live_voice.native_work_journal import SqliteNativeWorkJournal
    env = await make_registry(tmp_path,monkeypatch)
    router = env.registry._native_business
    router.works()
    original = router._work_journal.record_task_origin
    def failed(*args): raise OSError("temporary persistence failure")
    monkeypatch.setattr(router._work_journal,"record_task_origin",failed)
    try:
        created,_ = await call(env,"task.create",name="Recovery report",instruction="Create report")
        assert created["status"] == "dispatched" and created["task_origin_reason"] == "NATIVE_TASK_ORIGIN_UNAVAILABLE"
        task_id = created["task_id"]
        assert router._work_journal.task_origins(env.binding.scope) == ()
        before = env.harness.composition._core.store.counts()
        # A new journal owner represents loss of the process-local retry state.
        restored = SqliteNativeWorkJournal(router._work_journal.database_path)
        restored.recover_task_origins(env.binding.scope)
        assert restored.task_origins(env.binding.scope) == (task_id,)
        monkeypatch.setattr(router._work_journal,"record_task_origin",original)
        env.registry._voice_task_origins.clear()
        await context(env)
        assert task_id in env.registry._voice_task_origins
        assert env.harness.composition._core.store.counts() == before
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_work_update_then_cancel_preserves_task_store_and_retires_old_result(tmp_path, monkeypatch):
    from tests.unit_tests.live_voice.test_native_work_runtime import terminal
    env = await make_registry(tmp_path,monkeypatch)
    starts = asyncio.Queue()
    release = asyncio.Event()
    async def agent(execution):
        starts.put_nowait(execution)
        await release.wait()
        yield AgentResponseChunk(request_id=execution.request_id,channel_id=execution.channel_id,
            payload={"event_type":"chat.final","content":"Late cancelled result"},is_complete=True)
    monkeypatch.setattr(env.manager.agent,"process_formal_live_voice_stream",agent)
    try:
        before = env.harness.composition._core.store.counts()
        first,_ = await call(env,"work.start",stem="first",instruction="Read notes")
        await asyncio.wait_for(starts.get(),2)
        owner = env.registry._native_business.works()
        updated,_ = await call(env,"work.update",stem="update",target_id=first["work"]["work_id"],
            expected_revision=1,instruction="Read notes and compare alternatives")
        assert updated["work"]["revision"] == 2, updated
        await asyncio.wait_for(starts.get(),2)
        cancelled,_ = await call(env,"work.cancel",stem="cancel",target_id=first["work"]["work_id"],expected_revision=2)
        assert cancelled["work"]["state"] in {"cancelling","cancelled"},cancelled
        release.set()
        final = await terminal(owner,owner.query(scope=env.binding.scope,work_id=first["work"]["work_id"]))
        assert final.state.value == "cancelled" and final.result_text is None
        assert owner.query(scope=env.binding.scope,work_id=final.work_id,revision=1).state.value == "superseded"
        assert env.harness.composition._core.store.counts() == before
    finally:
        release.set()
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_structured_task_create_and_read_use_real_receipts_without_semantic_or_agent(tmp_path, monkeypatch):
    env = await make_registry(tmp_path,monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError("semantic/Agent path must not execute")
    monkeypatch.setattr(env.registry,"_resolve_task_semantics",forbidden,raising=False)
    monkeypatch.setattr(env.registry,"_run_unified_submit",forbidden)
    try:
        receipt, params = await call(env,"task.create", name="Project report", instruction="Read project notes and save a report")
        assert receipt["status"] == "dispatched", receipt
        task_id = receipt["task_id"]
        assert receipt["receipt"]["state"] == "accepted"
        replay = await env.registry.handle_native_propose(params=params,request_id="call",session_id="session-1")
        assert json.loads(replay.payload["result"]["canonical_text"])["task_id"] == task_id
        status, _ = await call(env,"task.status", stem="status", target_id=task_id)
        assert status["status"] == "dispatched", status
        assert env.manager.agent.executions == []
        assert env.registry._native_business.task_origins(env.binding.scope) == (task_id,)
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_model_replay_omission_retains_choice_and_changed_choice_has_zero_new_effects(tmp_path, monkeypatch):
    env = await make_registry(tmp_path,monkeypatch)
    try:
        params = {key:value for key,value in env.params.items() if key != "agent_model_selection"}
        replay = await env.registry.handle_p2_activate(params=params,request_id="replay",session_id="session-1",channel_id="web")
        assert replay.ok and replay.payload["result"]["agent_model_selection"]["model_name"] == "Selected Agent"
        changed = {**env.params, "agent_model_selection":{"contract_version":"live-voice.agent-model-selection.v1","model_name":"Default"}}
        conflict = await env.registry.handle_p2_activate(params=changed,request_id="conflict",session_id="session-1",channel_id="web")
        assert not conflict.ok and conflict.payload["error"]["reason"] == "NATIVE_AGENT_MODEL_REPLAY_CONFLICT"
        assert len(env.manager.get_calls) == 1
    finally:
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_readonly_refund_work_returns_before_completion_and_survives_p2_disconnect(tmp_path, monkeypatch):
    env = await make_registry(tmp_path,monkeypatch)
    started, release = asyncio.Event(), asyncio.Event()
    executions = []
    async def agent(execution):
        executions.append(execution)
        started.set()
        await release.wait()
        yield AgentResponseChunk(request_id=execution.request_id, channel_id="web",
            payload={"event_type":"chat.final", "content":"Verified refund explanation"}, is_complete=True)
    monkeypatch.setattr(env.manager.agent,"process_formal_live_voice_stream",agent)
    try:
        task, _ = await call(env,"task.create",stem="task",name="Report",instruction="Prepare a report")
        task_id = task["task_id"]
        before = env.harness.composition._core.store.get_task(task_id, env.binding.scope)
        receipt, _ = await call(env,"work.start",stem="refund",text="Explain the refund; leave the report unchanged",
            instruction="Read project refund terms and explain them; do not modify any task")
        work_id = receipt["work"]["work_id"]
        assert receipt["work"]["state"] == "accepted"
        await asyncio.wait_for(started.wait(),1)
        assert executions[0].read_only_tools is True
        assert executions[0].model_identity == "selected#0"
        assert executions[0].commit.text == "Explain the refund; leave the report unchanged"
        await env.registry.close_active_routes()
        owner = env.registry._native_business.works()
        assert owner.query(scope=env.binding.scope,work_id=work_id).state.value == "running"
        assert not release.is_set()
        after = env.harness.composition._core.store.get_task(task_id, env.binding.scope)
        assert after == before
        release.set()
        for _ in range(100):
            snapshot = owner.query(scope=env.binding.scope,work_id=work_id)
            if snapshot.state.value == "completed": break
            await asyncio.sleep(.01)
        assert snapshot.result_text == "Verified refund explanation"
        params = {**env.params,"activation_id":"activation-2","activation_generation":2}
        again = await env.registry.handle_p2_activate(params=params,request_id="reconnect",session_id="session-1",channel_id="web")
        assert again.ok, again.payload
        assert task_id in again.payload["result"]["voice_task_ids"]
        assert owner.query(scope=env.binding.scope,work_id=work_id).result_text == snapshot.result_text
    finally:
        release.set()
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_project_rebound_while_agent_resource_waits_has_zero_work_or_agent_effect(tmp_path, monkeypatch):
    env = await make_registry(tmp_path,monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    original = env.manager.get_agent
    async def blocked(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    monkeypatch.setattr(env.manager,"get_agent",blocked)
    pending = None
    try:
        pending = asyncio.create_task(call(env,"work.start",instruction="Read project notes"))
        await asyncio.wait_for(entered.wait(),1)
        env.harness.authority.contexts["session-1"] = replace(env.harness.authority.contexts["session-1"], uri=(tmp_path/"rebound").as_uri())
        release.set()
        with pytest.raises(NativeRuntimeClientError) as rejected:
            await pending
        assert rejected.value.reason == "EXECUTION_CONTEXT_SCOPE_MISMATCH"
        assert env.registry._native_business.works().list(scope=env.binding.scope) == ()
        assert env.manager.agent.executions == []
    finally:
        release.set()
        if pending: await asyncio.gather(pending,return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()
