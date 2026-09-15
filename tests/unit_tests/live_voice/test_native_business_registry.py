"""Real serialized Native admission and existing SQLite Task policy seam."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from types import SimpleNamespace

import pytest

from jiuwenswarm.channels.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessProposal, NATIVE_BUSINESS_CONTRACT_VERSION
from jiuwenswarm.common.schema.native_interaction_contract import NativeInteractionBinding
from jiuwenswarm.channels.live_voice.native_interaction_config import InteractionEngineKind
from jiuwenswarm.channels.live_voice.product_composition_registry import AgentServerProductCompositionRegistry, ProductCompositionSettings
from jiuwenswarm.server.runtime.formal_tasks.p3_confirmation import BoundedP3ConfirmationOwner
from jiuwenswarm.server.runtime.formal_tasks.p3_product_confirmation import ProductP3ConfirmationForwarder
from tests.unit_tests.live_voice.test_native_agent_model import _model_harness, TOKEN
from tests.unit_tests.live_voice.test_product_composition_registry import (
    _AgentManager, _native_turn_proposal, _native_speak_proposal, _native_propose_params, _native_delegate_proposal,
    _native_input_transcript_proposal, _shared_test_runtime,
)
from jiuwenswarm.common.schema.live_voice_contract_v2 import ResponseRef
from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.common.e2a.wire_codec import parse_agent_server_wire_unary
from jiuwenswarm.gateway.live_voice.native_interaction_runtime_client import GatewayNativeInteractionRuntimeClient, NativeRuntimeClientError
from jiuwenswarm.channels.live_voice.openai_realtime_native_engine import NativeEngineEvent


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
        p3_composition=h.composition, agent_manager=manager, runtime=_shared_test_runtime(manager), push_text_event=push,
        p3_confirmation_owner=owner, p3_confirmation_forwarder=ProductP3ConfirmationForwarder(owner))
    monkeypatch.setattr('jiuwenswarm.channels.live_voice.native_business_router.load_history_records', lambda sid: [])
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
        await env.registry._runtime.close()
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
        await env.registry._runtime.close()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_failure", [False, True])
async def test_creation_origin_uses_accepted_task_without_secondary_writes(tmp_path,monkeypatch,receipt_failure):
    import sqlite3
    from jiuwenswarm.server.runtime.work.native_work_journal import SqliteNativeWorkJournal
    env = await make_registry(tmp_path,monkeypatch)
    router = env.registry._native_business
    router.works()
    original = env.registry._unified_journal.complete
    def complete(**kwargs):
        if receipt_failure and kwargs["result"].get("operation") == "task.create":
            raise OSError("receipt persistence unavailable")
        return original(**kwargs)
    monkeypatch.setattr(env.registry._unified_journal,"complete",complete)
    try:
        if receipt_failure:
            with pytest.raises(NativeRuntimeClientError):
                await call(env,"task.create",name="Recovery report",instruction="Create report")
        else:
            created,_ = await call(env,"task.create",name="Recovery report",instruction="Create report")
            assert created["status"] == "dispatched" and "task_origin_reason" not in created
        scope, tasks = await env.harness.composition.read_task_creation_origins(
            bearer_token=TOKEN,session_id="session-1")
        assert len(tasks) == 1
        task_id = tasks[0].task_id
        before = env.harness.composition._core.store.counts()
        restored = SqliteNativeWorkJournal(router._work_journal.database_path)
        assert restored.task_origins(scope) == (() if receipt_failure else (task_id,))
        env.registry._voice_task_origins.clear()
        await context(env)
        assert task_id in env.registry._voice_task_origins
        env.registry._voice_task_origins.clear()
        route = env.registry._p2_routes[("session-1", "interaction-1")]
        async with env.registry._lock:
            activation = await env.registry._restore_voice_task_origins(route, TOKEN)
        assert activation == {"voice_task_ids": [task_id]}
        assert env.registry._voice_task_origins[task_id].response_ref is None
        with sqlite3.connect(restored.database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM native_business_task_origin").fetchone()[0] == 0
        assert env.harness.composition._core.store.counts() == before
        assert env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.registry._runtime.close()
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
        await env.registry._runtime.close()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_structured_task_create_and_read_use_real_receipts_without_semantic_or_agent(tmp_path, monkeypatch):
    env = await make_registry(tmp_path,monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError("semantic/Agent path must not execute")
    monkeypatch.setattr(env.registry,"_resolve_task_semantics",forbidden,raising=False)
    monkeypatch.setattr(env.registry,"_run_unified_submit",forbidden)
    monkeypatch.setattr(env.registry,"_resolve_semantic_input",forbidden)
    admitted = []
    admission = env.registry._run_p3_production_intent
    async def observe_admission(**kwargs):
        admitted.append(kwargs["native_request"])
        return await admission(**kwargs)
    monkeypatch.setattr(env.registry, "_run_p3_production_intent", observe_admission)
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
        assert [request.proposal.operation for request in admitted] == ["task.create", "task.status"]
        task = env.harness.composition._core.store.get_task(task_id, env.binding.scope)
        assert task.create_command_id == admitted[0].command_id
        assert admitted[0].command_id.startswith("native-command.")
        assert task.spec.native_source == admitted[0].native_source
    finally:
        await env.registry.stop()
        await env.registry._runtime.close()
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
        await env.registry._runtime.close()
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
        await env.registry._runtime.close()
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
        await env.registry._runtime.close()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_native_completed_adjust_preserves_speech_and_exposes_final_saved_truth(tmp_path, monkeypatch):
    from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome
    from openjiuwen.core.application.tasks.formal_task_models import TaskResultArtifact
    import hashlib
    spoken = "第一晚牛肉火锅，第二晚烧烤；不得修改原件.md。"
    env = await make_registry(tmp_path, monkeypatch, input_text=spoken)
    executor = env.harness.executor
    executor.dispatch_outcome = TerminalOutcome.COMPLETED
    dispatch = executor.dispatch
    dispatch_items = []
    async def saved_dispatch(item):
        dispatch_items.append(item)
        delivered = await dispatch(item)
        text = "原始行程" if item.spec.native_source is not None else "原始行程；牛肉火锅；烧烤"
        return replace(delivered, observations=tuple(replace(obs, result_text=text,
            result_artifacts=(TaskResultArtifact("行程.md", hashlib.sha256(text.encode()).hexdigest()),))
            if obs.attempt_outcome is TerminalOutcome.COMPLETED else obs for obs in delivered.observations))
    monkeypatch.setattr(executor, "dispatch", saved_dispatch)
    try:
        original, _ = await call(env, "task.create", stem="original", name="行程", instruction="生成原始行程")
        core, store = env.harness.composition._core, env.harness.composition._core.store
        await core.drain_outbox_once()
        task = store.get_task(original["task_id"], env.binding.scope)
        assert task.outcome is TerminalOutcome.COMPLETED
        adjusted, _ = await call(env, "task.adjust", stem="meals", target_id=task.task_id,
            expected_revision=task.revision_number, adjustment=spoken, text=spoken)
        assert adjusted["status"] == "dispatched", adjusted
        assert adjusted["adjustment_observation"]["state"] == "pending"
        assert adjusted["adjustment_observation"]["execution_mode"] == "followup"
        assert await core.drain_outbox_once()
        await core.drain_outbox_once()
        latest = await context(env)
        fact = next(value for value in latest["tasks"] if value["task_id"] == task.task_id)
        assert fact["result_text"] == "原始行程"
        assert fact["adjustment_state"] == "applied"
        child = store.get_task(fact["followup_adjustment"]["continuation_task_id"], env.binding.scope)
        assert child.spec.instruction == spoken  # The bounded command stays compact.
        from openjiuwen.core.application.tasks.task_adjustment_queue import TaskAdjustmentQueue
        expanded = TaskAdjustmentQueue(store).execution_instruction(dispatch_items[-1])
        assert spoken in expanded and "retained_speech" in expanded
        assert child.spec.context == task.spec.context
        queried, _ = await call(env, "task.result", stem="result", target_id=task.task_id)
        assert queried["task_control"]["adjustment_state"] == "applied"
        assert len(queried["task_notifications"]) == 1
        activation = env.client.activation_for(session_id="session-1", interaction_id="interaction-1", connection_id="business-wire")
        observation = await env.client.business_context(activation, request_id="final-adjustment-observation")
        assert observation["work_events"] == queried["task_notifications"]
        assert store.get_task(task.task_id, env.binding.scope) == task
        assert len(executor.dispatches) == 2 and env.manager.agent.executions == []
    finally:
        await env.registry.stop()
        await env.registry._runtime.close()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("ack_before_done", [False, True])
async def test_queried_results_retire_notifications_only_at_canonical_played_history(tmp_path, monkeypatch, ack_before_done):
    from tests.unit_tests.live_voice import test_product_composition_registry as f
    from tests.unit_tests.live_voice.test_native_work_runtime import admission, terminal
    env = await make_registry(tmp_path, monkeypatch)
    router = env.registry._native_business
    route = env.registry._p2_routes[(env.binding.scope.session_id, env.binding.interaction_id)]
    history = f._HistoryWriter()
    route.activation_lease._runtime._history_writer = history
    async def send(proposal, request_id):
        result = await env.registry.handle_native_propose(
            params=f._native_propose_params(env.binding, env.capability, proposal),
            request_id=request_id, session_id=env.binding.scope.session_id)
        assert result.ok, result.payload
        return result.payload["result"]
    async def runner(control):
        return "Verified facts, with their source and limitations."
    try:
        works = []
        for index in range(3):
            work = await router.works().start(**admission(runner, current_scope=env.binding.scope,
                request=f"work-request-{index}", input_id=f"work-input-{index}"))
            works.append(await terminal(router.works(), work))
        for index in range(2):
            await call(env, "work.get", stem=f"query-{index}", target_id=works[index].work_id)
        ids = [router._work_event_id(work) for work in works]
        pending = lambda: [router._work_journal.presented(event, env.binding.scope) for event in ids]
        assert pending() == [False, False, False]
        ended = f._native_done_proposal(env.binding, env.source)
        await send(replace(ended, provider_done=replace(ended.provider_done,
            transcript=None, transcript_event_id=None)), "source-ended")
        speak = f._native_speak_proposal(env.binding)
        reply = await send(replace(speak, action=replace(speak.action, action_id="query-answer",
            payload=(("provider_response_id", "query-answer"), ("provider_call_id", "query-0-call"),
                     ("turn_id", "native-turn-1")))), "query-answer")
        ref = ResponseRef(**reply["response"])
        assert pending() == [False, False, False]
        pcm = f._native_audio_proposal(env.binding, ref)
        audio = await send(replace(pcm, audio_observation=replace(pcm.audio_observation,
            provider_response_id="query-answer")), "query-audio")
        terminal_proposal = f._native_done_proposal(env.binding, ref)
        terminal_proposal = replace(terminal_proposal, provider_done=replace(terminal_proposal.provider_done,
            provider_event_id="query-done", provider_response_id="query-answer",
            transcript="Both verified results, including their limitations."))
        if not ack_before_done:
            await send(terminal_proposal, "query-done")
        assert pending() == [False, False, False]
        params = f._native_ack_params(env.binding, env.capability, ref,
            unit_id=audio["presentation_unit"]["unit_id"])
        ack = await env.registry.handle_native_presentation_ack(params=params,
            request_id="query-heard", session_id=env.binding.scope.session_id)
        assert ack.ok, ack.payload
        if ack_before_done:
            assert pending() == [False, False, False]
            await send(terminal_proposal, "query-done")
        assert pending() == [True, True, False]
        await asyncio.wait_for(history.native_written.wait(), 1)
        assert len(history.native_assistants) == 1
        assert router.work_events(env.binding.scope)[0]["event_id"] == ids[2]
        assert not env.manager.agent.executions
    finally:
        await env.registry.stop()
        await env.registry._runtime.close()
        await env.harness.composition.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["capability", "confirmation", "ordinary", "store", "continuation"])
async def test_common_task_admission_preserves_native_rejection_receipt(tmp_path, monkeypatch, failure_stage):
    from jiuwenswarm.common.schema.live_voice_contract_v2 import ErrorCode
    from openjiuwen.core.application.tasks.formal_task_models import FormalTaskViolation
    env = await make_registry(tmp_path, monkeypatch)
    attempts = []
    def reject(*args, **kwargs):
        attempts.append(failure_stage)
        if failure_stage == "ordinary":
            raise RuntimeError("private backend diagnostic must not enter the receipt")
        raise FormalTaskViolation("TEST_TASK_ADMISSION_REJECTED", "rejected", ErrorCode.PERMISSION_DENIED)
    if failure_stage in {"capability", "ordinary"}:
        monkeypatch.setattr(env.harness.composition, "require_local_artifact_delegation_capability", reject)
    elif failure_stage == "confirmation":
        monkeypatch.setattr(env.registry._p3_confirmation_owner, "validate_for_forwarding", reject)
    elif failure_stage == "continuation":
        confirm = env.harness.composition.confirm_and_handle_production_request
        async def close_before_final_claim(**kwargs):
            claim = kwargs["claim_continuation"]
            async def lose_continuation():
                attempts.append(failure_stage)
                async with env.registry._lock:
                    env.registry._pending_production_task_intents.clear()
                await claim()
            return await confirm(**{**kwargs, "claim_continuation": lose_continuation})
        monkeypatch.setattr(env.harness.composition, "confirm_and_handle_production_request", close_before_final_claim)
    else:
        monkeypatch.setattr(env.harness.composition._core, "execute", reject)
    try:
        receipt, params = await call(env, "task.create", name="Rejected report", instruction="Save a report")
        assert receipt["status"] == "rejected", receipt
        if failure_stage == "store":
            assert receipt["error"]["reason"] == "TEST_TASK_ADMISSION_REJECTED"
            assert "reason" not in receipt
        else:
            assert receipt["reason"] == ("NATIVE_BUSINESS_EXECUTION_FAILED" if failure_stage == "ordinary"
                                          else "TASK_INTENT_CONTINUATION_UNAVAILABLE" if failure_stage == "continuation"
                                          else "TEST_TASK_ADMISSION_REJECTED")
            assert "error" not in receipt
        replay = await env.registry.handle_native_propose(params=params, request_id="call", session_id="session-1")
        assert json.loads(replay.payload["result"]["canonical_text"]) == receipt
        assert attempts == [failure_stage]
        assert env.manager.agent.executions == []
        assert env.harness.composition._core.store.list_tasks(env.binding.scope) == ()
    finally:
        await env.registry.stop()
        await env.registry._runtime.close()
        await env.harness.composition.stop()
