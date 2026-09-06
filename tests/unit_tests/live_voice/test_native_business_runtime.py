"""Business outputs and independent work use the real Native presentation ledger."""

import pytest

from jiuwenswarm.server.live_voice.native_business_contract import NativeBusinessAction, NativeBusinessProposal
from jiuwenswarm.server.live_voice.native_interaction_runtime import NativeInteractionRuntimeError
from jiuwenswarm.server.live_voice.voice_task_bridge import UnifiedCommittedInputRoute
from tests.unit_tests.live_voice.test_native_interaction_runtime import (
    active_owner, delegate_proposal, done, audio, ack_for, turn_commit,
)


def business(response, call):
    legacy = delegate_proposal(response)
    return NativeBusinessProposal(**{key: getattr(legacy, key) for key in legacy.__dataclass_fields__
        if key not in {"provider_call_id", "provider_event_id", "provider_item_id"}},
        provider_call_id=call, provider_event_id=call+"-event", provider_item_id=call+"-item",
        business=NativeBusinessAction("context.get", None, None, None, None, None, None))


@pytest.mark.asyncio
async def test_multiple_business_outputs_share_one_successor_and_only_heard_text_enters_history():
    owner, runtime = await active_owner()
    try:
        source = await owner.accept_provider_response("source", "runtime-source")
        admissions = []
        for call in ("call-a", "call-b"):
            _, admission = await owner.admit_delegate(business(source.response, call), committed_at="2026-09-06T00:00:00Z")
            admissions.append(admission)
            await owner.prepare_delegate_result(admission, canonical_text='{"operation":"context.get","private":"not spoken"}',
                route=UnifiedCommittedInputRoute.DIALOGUE, allow_interrupted=True)
        assert admissions[0].turn_commit.commit_id != admissions[1].turn_commit.commit_id
        await owner.accept_provider_done(done(source.response, source.provider_response_id, transcript=None))
        first = await owner.accept_delegate_provider_response("successor", "call-a", "native-turn-1")
        assert not owner.foreground_busy()
        assert (await owner.accept_delegate_provider_response("successor", "call-b", "native-turn-1")) == first
        before = runtime.snapshot()
        with pytest.raises(NativeInteractionRuntimeError):
            await owner.accept_delegate_provider_response("duplicate-successor", "call-b", "native-turn-1")
        assert runtime.snapshot() == before
        await owner.accept_audio(audio(first.response, "successor", 0))
        await owner.accept_provider_done(done(first.response, "successor", transcript="The two operations were accepted."))
        assert owner.snapshot().history_count == 0
        heard = await owner.acknowledge_audio(ack_for(runtime, first.response, 0))
        assert heard.transcript == "The two operations were accepted."
        assert await owner.presented_agent_analysis(first.response) is None
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_interrupted_business_settles_real_result_but_cannot_resume_source_speech():
    owner, runtime = await active_owner()
    try:
        source = await owner.accept_provider_response("source", "runtime-source")
        _, admission = await owner.admit_delegate(business(source.response, "call"), committed_at="2026-09-06T00:00:00Z")
        await owner.interrupt_delegate_source(action_id="user-stop", response=source.response)
        before = runtime.snapshot()
        result = await owner.prepare_delegate_result(admission, canonical_text='{"work":{"state":"running"}}',
            route=UnifiedCommittedInputRoute.DIALOGUE, allow_interrupted=True)
        assert result.canonical_text == '{"work":{"state":"running"}}'
        assert runtime.snapshot() == before
        with pytest.raises(NativeInteractionRuntimeError, match="Interrupted"):
            await owner.accept_delegate_provider_response("old-result", "call", "native-turn-1")
        assert runtime.snapshot() == before
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_work_result_waits_for_actual_audio_ack_and_current_turn_then_replays_without_effect():
    owner, runtime = await active_owner()
    try:
        source = await owner.accept_provider_response("source", "runtime-source")
        await owner.accept_audio(audio(source.response, "source", 0))
        await owner.accept_provider_done(done(source.response, "source"))
        before = runtime.snapshot()
        with pytest.raises(NativeInteractionRuntimeError) as rejected:
            await owner.accept_work_provider_response("work", "runtime-work", turn_id="native-turn-1")
        assert rejected.value.reason == "NATIVE_RESPONSE_PRESENTATION_BUSY"
        assert runtime.snapshot() == before
        await owner.acknowledge_audio(ack_for(runtime, source.response, 0))
        await owner.accept_turn(turn_commit(2))
        before = runtime.snapshot()
        with pytest.raises(NativeInteractionRuntimeError) as rejected:
            await owner.accept_work_provider_response("work", "runtime-work", turn_id="native-turn-1")
        assert rejected.value.reason == "NATIVE_WORK_RESPONSE_TURN_STALE"
        assert runtime.snapshot() == before
        work = await owner.accept_work_provider_response("work", "runtime-work", turn_id="native-turn-2")
        before = runtime.snapshot()
        assert await owner.accept_work_provider_response("work", "runtime-work", turn_id="native-turn-2") == work
        assert runtime.snapshot() == before
    finally:
        await owner.close()
