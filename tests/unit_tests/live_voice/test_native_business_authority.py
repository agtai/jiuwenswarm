import asyncio
import json
import threading
from dataclasses import replace

import pytest

from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessProposal, NATIVE_BUSINESS_CONTRACT_VERSION
from jiuwenswarm.server.live_voice.native_business_context import select_conversation_history
from jiuwenswarm.server.live_voice.voice_task_bridge import UnifiedCommittedInputRoute
from tests.unit_tests.live_voice.test_native_business_registry import make_registry, call, context
from tests.unit_tests.live_voice.test_product_composition_registry import _native_delegate_proposal, _native_propose_params
from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.server.live_voice.native_interaction_runtime import NativeInteractionRuntimeError
from tests.unit_tests.live_voice.test_native_interaction_runtime import active_owner, delegate_proposal, done


@pytest.mark.asyncio
async def test_context_revalidates_project_after_history_await_before_disclosure(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    def delayed_history(_session_id):
        entered.set()
        assert release.wait(5)
        return [{"role": "user", "content": "old-project-private-context"}]
    monkeypatch.setattr('jiuwenswarm.server.live_voice.native_business_router.load_history_records', delayed_history)
    pending = None
    try:
        pending = asyncio.create_task(env.registry.handle_native_propose(params={
            "contract_version": NATIVE_BUSINESS_CONTRACT_VERSION,
            "binding": env.binding.to_dict(), "capability": env.capability,
            "context": True,
        }, request_id="review-context", session_id="session-1"))
        assert await asyncio.to_thread(entered.wait, 3)
        env.harness.authority.contexts["session-1"] = replace(
            env.harness.authority.contexts["session-1"], uri=(tmp_path / "rebound").as_uri())
        release.set()
        result = await pending
        assert not result.ok, result.payload
        assert "old-project-private-context" not in str(result.payload)
        assert env.manager.agent.executions == []
    finally:
        release.set()
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()


@pytest.mark.asyncio
async def test_work_response_exact_replay_is_checked_before_busy_guard():
    owner, _runtime = await active_owner()
    try:
        first = await owner.accept_work_provider_response("provider-work", "work-response", turn_id="native-turn-1")
        replay = await owner.accept_work_provider_response("provider-work", "work-response", turn_id="native-turn-1")
        assert replay == first
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_business_siblings_wait_for_all_results_then_bind_one_immutable_response():
    owner, _runtime = await active_owner()
    try:
        source = await owner.accept_provider_response("function-source", "function-source")
        base = delegate_proposal(source.response)
        action = NativeBusinessAction("context.get", None, None, None, None, None, None)
        first = NativeBusinessProposal(**{name: getattr(base, name) for name in base.__dataclass_fields__}, business=action)
        second = replace(first, provider_call_id="call-b", provider_event_id="event-b", provider_item_id="item-b")
        _, admission_a = await owner.admit_delegate(first, committed_at="2026-09-06T10:00:00Z")
        _, admission_b = await owner.admit_delegate(second, committed_at="2026-09-06T10:00:00Z")
        await owner.accept_provider_done(done(source.response, source.provider_response_id))
        await owner.prepare_delegate_result(admission_a, canonical_text="result-a", route=UnifiedCommittedInputRoute.DIALOGUE, allow_interrupted=True)
        with pytest.raises(NativeInteractionRuntimeError) as pending:
            await owner.accept_delegate_provider_response("answer-a", first.provider_call_id, first.turn_id)
        assert pending.value.reason == "NATIVE_BUSINESS_GROUP_PENDING"
        await owner.prepare_delegate_result(admission_b, canonical_text="result-b", route=UnifiedCommittedInputRoute.DIALOGUE, allow_interrupted=True)
        response_a = await owner.accept_delegate_provider_response("answer-a", first.provider_call_id, first.turn_id)
        response_b = await owner.accept_delegate_provider_response("answer-a", second.provider_call_id, second.turn_id)
        assert response_a == response_b
        with pytest.raises(NativeInteractionRuntimeError):
            await owner.accept_delegate_provider_response("answer-b", second.provider_call_id, second.turn_id)
        replay_a = await owner.accept_delegate_provider_response("answer-a", first.provider_call_id, first.turn_id)
        assert replay_a == response_a
    finally:
        await owner.close()


def test_oversized_latest_assistant_does_not_erase_prior_user_requirements():
    result = select_conversation_history([
        {"role": "user", "content": "Preserve requirement A"},
        {"role": "assistant", "content": "long result " * 2000},
    ])
    assert any(item["content"] == "Preserve requirement A" for item in result)


@pytest.mark.asyncio
async def test_work_cancel_revalidates_authority_after_durable_input_admission(tmp_path, monkeypatch):
    env = await make_registry(tmp_path, monkeypatch)
    started, release_agent = asyncio.Event(), asyncio.Event()
    entered, release_admission = threading.Event(), threading.Event()
    pending = None
    async def agent(execution):
        started.set()
        await release_agent.wait()
        yield AgentResponseChunk(request_id=execution.request_id, channel_id=execution.channel_id,
            payload={"event_type": "chat.final", "content": "original analysis"}, is_complete=True)
    monkeypatch.setattr(env.manager.agent, "process_formal_live_voice_stream", agent)
    try:
        accepted, _ = await call(env, "work.start", instruction="Read notes", stem="original-work")
        work_id = accepted["work"]["work_id"]
        await asyncio.wait_for(started.wait(), 2)
        journal = env.registry._unified_journal
        original_admit = journal.admit
        observed = await context(env)
        old = _native_delegate_proposal(env.binding, env.source, request_text="Cancel that analysis")
        original = old.delegate
        business = NativeBusinessAction("work.cancel", observed["context_id"], work_id, 1, None, None, None)
        delegate = NativeBusinessProposal(**{key: getattr(original, key) for key in original.__dataclass_fields__ if key not in {
            "provider_event_id", "provider_call_id", "provider_item_id"}},
            provider_event_id="cancel-event", provider_call_id="cancel-call", provider_item_id="cancel-item", business=business)
        proposal = replace(old, delegate=delegate, action=replace(old.action, action_id="cancel-action",
            payload=(("provider_call_id", delegate.provider_call_id), ("turn_id", delegate.turn_id))))
        params = json.loads(json.dumps(_native_propose_params(env.binding, env.capability, proposal)))
        def delayed_admit(**kwargs):
            entered.set()
            assert release_admission.wait(5)
            return original_admit(**kwargs)
        monkeypatch.setattr(journal, "admit", delayed_admit)
        pending = asyncio.create_task(env.registry.handle_native_propose(params=params, request_id="cancel-work", session_id="session-1"))
        assert await asyncio.to_thread(entered.wait, 3)
        env.harness.authority.contexts["session-1"] = replace(
            env.harness.authority.contexts["session-1"], uri=(tmp_path / "rebound").as_uri())
        release_admission.set()
        result = await pending
        assert not result.ok, result.payload
        assert result.payload["error"]["reason"] == "EXECUTION_CONTEXT_SCOPE_MISMATCH"
        assert env.registry._native_business.works().query(scope=env.binding.scope, work_id=work_id).state.value == "running"
    finally:
        release_admission.set()
        release_agent.set()
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        await env.registry.stop()
        await env.harness.composition.stop()
