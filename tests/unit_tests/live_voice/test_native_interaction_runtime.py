# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ResponseRef,
    ScopeRef,
    TurnCommit,
)
from jiuwenswarm.server.live_voice import (
    native_interaction_runtime as native_runtime_module,
)
from jiuwenswarm.server.live_voice.conversation_runtime import CancelState
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    ConversationRuntimeLoop,
    EffectState,
)
from jiuwenswarm.server.live_voice.native_interaction_contract import (
    NATIVE_INTERACTION_CONTRACT_VERSION,
    NativeAudioObservation,
    NativeDelegateProposal,
    NativeInteractionBinding,
    NativePresentationCursor,
    NativeTurnCommit,
)
from jiuwenswarm.server.live_voice.native_interaction_runtime import (
    NativeHistoryAdmission,
    NativeInteractionRuntimeError,
    NativeInteractionRuntimeOwner,
)
from jiuwenswarm.server.live_voice.openai_realtime_native_engine import (
    MAX_NATIVE_AUDIO_DELTA_BYTES,
    NativeAudioOutput,
    NativeProviderDone,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationSurface,
)
from jiuwenswarm.server.live_voice.voice_task_bridge import (
    UnifiedCommittedInputRoute,
)


_SCOPE = ScopeRef(
    "subject-native", "project-native", "session-native", Assurance.AUTHENTICATED
)


def binding() -> NativeInteractionBinding:
    return NativeInteractionBinding(
        scope=_SCOPE,
        interaction_id="native-interaction-1",
        activation_id="native-activation-1",
        activation_generation=1,
        correlation_id="native-correlation-1",
    )


def turn_commit(turn_number: int = 1) -> NativeTurnCommit:
    return NativeTurnCommit(
        contract_version=NATIVE_INTERACTION_CONTRACT_VERSION,
        commit_id=f"native-commit-{turn_number}",
        binding=binding(),
        turn_id=f"native-turn-{turn_number}",
        provider_session_id="provider-session-1",
        provider_item_id=f"provider-user-item-{turn_number}",
        provider_event_id=f"provider-commit-event-{turn_number}",
        causation_id=f"provider-speech-event-{turn_number}",
        input_audio_start_ms=(turn_number - 1) * 20,
        input_audio_end_ms=turn_number * 20,
        committed_audio_ms=20,
    )


def audio(
    response: ResponseRef,
    provider_response_id: str,
    sequence: int,
    *,
    pcm16: bytes = b"\x00\x00" * 480,
) -> NativeAudioOutput:
    return NativeAudioOutput(
        provider_event_id=f"provider-audio-event-{provider_response_id}-{sequence}",
        provider_response_id=provider_response_id,
        provider_item_id=f"provider-assistant-item-{provider_response_id}",
        content_index=0,
        sequence=sequence,
        pcm16=pcm16,
        response=response,
    )


def done(
    response: ResponseRef,
    provider_response_id: str,
    *,
    transcript: str | None = "Canonical answer.",
    completed: bool = True,
) -> NativeProviderDone:
    return NativeProviderDone(
        provider_event_id=f"provider-done-event-{provider_response_id}",
        provider_response_id=provider_response_id,
        response=response,
        completed=completed,
        transcript=transcript,
        transcript_event_id=(
            None
            if transcript is None
            else f"provider-transcript-{provider_response_id}"
        ),
    )


async def active_owner() -> tuple[
    NativeInteractionRuntimeOwner, ConversationRuntimeLoop
]:
    runtime = ConversationRuntimeLoop(_SCOPE)
    owner = NativeInteractionRuntimeOwner(binding(), runtime=runtime)
    assert await owner.start() is True
    assert await owner.accept_turn(turn_commit()) is True
    return owner, runtime


def delegate_proposal(response: ResponseRef) -> NativeDelegateProposal:
    return NativeDelegateProposal(
        binding=binding(),
        turn_id="native-turn-1",
        response_generation=response.response_generation,
        provider_event_id="provider-function-event-1",
        provider_call_id="provider-call-1",
        provider_item_id="provider-function-item-1",
        request_text="Use the weather tool for Paris",
    )


@pytest.mark.asyncio
async def test_delegate_converts_to_standard_commit_then_admits_new_response() -> None:
    owner, runtime = await active_owner()
    source = await owner.accept_provider_response(
        "provider-response-function", "native-response-function"
    )
    proposal = delegate_proposal(source.response)

    accepted, admission = await owner.admit_delegate(
        proposal, committed_at="2026-08-25T10:00:00Z"
    )

    assert accepted is True
    assert isinstance(admission.turn_commit, TurnCommit)
    assert admission.source_response == source.response
    assert admission.turn_commit.scope == binding().scope
    assert admission.turn_commit.interaction_id == binding().interaction_id
    assert admission.turn_commit.text == "Use the weather tool for Paris"
    assert admission.turn_commit.turn_id != proposal.turn_id
    assert admission.turn_commit.context_refs == ()
    assert admission.turn_commit.committed_at == "2026-08-25T10:00:00Z"
    assert admission.turn_commit.hypothesis_provenance == {
        "source": "openai_realtime_native_delegate",
        "contract_version": NATIVE_INTERACTION_CONTRACT_VERSION,
        "activation_id": binding().activation_id,
        "activation_generation": binding().activation_generation,
        "correlation_id": binding().correlation_id,
        "native_turn_id": proposal.turn_id,
        "provider_event_id": proposal.provider_event_id,
        "provider_call_id": proposal.provider_call_id,
        "provider_item_id": proposal.provider_item_id,
        "source_response_generation": proposal.response_generation,
    }
    replay_accepted, replay = await owner.admit_delegate(
        proposal, committed_at="2026-08-25T10:00:00Z"
    )
    assert replay_accepted is False
    assert replay == admission

    result = await owner.accept_delegate_result(
        admission,
        canonical_text="The weather tool returned a canonical result.",
        route=UnifiedCommittedInputRoute.DIALOGUE,
    )

    assert result.turn_commit == admission.turn_commit
    assert result.canonical_text == "The weather tool returned a canonical result."
    assert result.route is UnifiedCommittedInputRoute.DIALOGUE
    assert result.response.interaction_id == binding().interaction_id
    assert result.response.response_generation > source.response.response_generation
    assert runtime.snapshot().presentation.records == ()
    assert [record.effect.effect_type for record in runtime.snapshot().effects] == [
        "playback.stop"
    ]
    assert (
        await owner.accept_delegate_result(
            admission,
            canonical_text="The weather tool returned a canonical result.",
            route=UnifiedCommittedInputRoute.DIALOGUE,
        )
        == result
    )
    bound = await owner.bind_delegate_provider_response(
        "provider-response-delegate-result",
        result.response,
    )
    assert bound.response == result.response
    assert (
        await owner.accept_audio(
            audio(
                result.response,
                "provider-response-delegate-result",
                0,
            )
        )
        is True
    )
    await owner.close()


@pytest.mark.asyncio
async def test_stale_or_changed_delegate_has_zero_runtime_effect() -> None:
    owner, runtime = await active_owner()
    source = await owner.accept_provider_response(
        "provider-response-function", "native-response-function"
    )
    proposal = delegate_proposal(source.response)
    before = runtime.snapshot()

    with pytest.raises(NativeInteractionRuntimeError) as stale:
        await owner.admit_delegate(
            replace(
                proposal, response_generation=source.response.response_generation + 1
            ),
            committed_at="2026-08-25T10:00:00Z",
        )
    assert stale.value.reason == "NATIVE_DELEGATE_RESPONSE_STALE"
    assert runtime.snapshot() == before

    accepted, admission = await owner.admit_delegate(
        proposal, committed_at="2026-08-25T10:00:00Z"
    )
    assert accepted is True
    after_admission = runtime.snapshot()
    with pytest.raises(NativeInteractionRuntimeError) as changed:
        await owner.admit_delegate(
            replace(proposal, request_text="Changed request"),
            committed_at="2026-08-25T10:00:00Z",
        )
    assert changed.value.reason == "NATIVE_DELEGATE_CALL_CONFLICT"
    assert runtime.snapshot() == after_admission

    with pytest.raises(NativeInteractionRuntimeError) as unsafe_result:
        await owner.accept_delegate_result(
            admission,
            canonical_text="unsafe\nresult",
            route=UnifiedCommittedInputRoute.DIALOGUE,
        )
    assert unsafe_result.value.reason == "NATIVE_DELEGATE_RESULT_INVALID"
    assert runtime.snapshot() == after_admission

    with pytest.raises(NativeInteractionRuntimeError) as oversized_result:
        await owner.accept_delegate_result(
            admission,
            canonical_text="x" * 65_537,
            route=UnifiedCommittedInputRoute.DIALOGUE,
        )
    assert oversized_result.value.reason == "NATIVE_DELEGATE_RESULT_INVALID"
    assert runtime.snapshot() == after_admission
    await owner.close()


@pytest.mark.asyncio
async def test_attached_owner_uses_existing_runtime_and_never_closes_shared_loop() -> (
    None
):
    runtime = ConversationRuntimeLoop(_SCOPE)
    assert await runtime.start() is True
    await runtime.open_interaction(binding().interaction_id)
    owner = NativeInteractionRuntimeOwner(
        binding(), runtime=runtime, owns_runtime=False
    )

    assert await owner.start() is True
    assert await owner.accept_turn(turn_commit()) is True
    await owner.close()

    assert owner.snapshot().closed is True
    assert runtime.snapshot().closed is False
    assert runtime.snapshot().accepting is True
    await runtime.close()


def ack_for(
    runtime: ConversationRuntimeLoop,
    response: ResponseRef,
    sequence: int,
    *,
    presented_at: str = "2026-08-25T10:00:01Z",
) -> PresentationAck:
    record = next(
        item
        for item in runtime.snapshot().presentation.records
        if item.unit.ref == response and item.unit.seq == sequence
    )
    return PresentationAck(
        ref=response,
        surface=PresentationSurface.AUDIO,
        unit_id=record.unit.unit_id,
        contiguous_cursor=sequence,
        presented_at=presented_at,
    )


@pytest.mark.asyncio
async def test_native_turn_response_audio_done_and_history_positive_journey() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response(
        "provider-response-1", "native-response-1"
    )
    assert admission.response.response_generation == 1
    assert (
        await owner.accept_audio(
            audio(admission.response, admission.provider_response_id, 0)
        )
        is True
    )
    snapshot = runtime.snapshot()
    assert snapshot.presentation.policies == (
        (admission.response, HistorySurfacePolicy.NATIVE_AUDIO),
    )
    assert [record.effect.effect_type for record in snapshot.effects] == [
        "audio.enqueue"
    ]
    assert (
        await owner.accept_provider_done(
            done(admission.response, admission.provider_response_id)
        )
        is True
    )
    history = await owner.acknowledge_audio(ack_for(runtime, admission.response, 0))

    assert history == NativeHistoryAdmission(
        response=admission.response,
        transcript="Canonical answer.",
        presented_at="2026-08-25T10:00:01Z",
    )
    assert all(
        record.effect.effect_type != "history.append"
        for record in runtime.snapshot().effects
    )
    await owner.close()


@pytest.mark.asyncio
async def test_metadata_only_audio_observation_returns_runtime_presentation_unit() -> (
    None
):
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response(
        "provider-response-metadata", "native-response-metadata"
    )
    observation = NativeAudioObservation(
        provider_event_id="provider-audio-metadata-0",
        provider_response_id=admission.provider_response_id,
        provider_item_id="provider-assistant-item-metadata",
        content_index=0,
        sequence=0,
        sample_count=480,
        content_sha256=hashlib.sha256(b"\x12\x34" * 480).hexdigest(),
        response=admission.response,
    )

    admission_result = await owner.accept_audio_observation(observation)

    assert admission_result is not None
    assert admission_result.accepted is True
    unit = admission_result.unit
    assert unit.ref == admission.response
    assert unit.surface is PresentationSurface.AUDIO
    assert unit.seq == 0
    assert unit.source_start_utf8 == 0
    assert unit.source_end_utf8 == 480
    assert unit.content_ref == f"sha256:{observation.content_sha256}"
    replay = await owner.accept_audio_observation(observation)
    assert replay is not None
    assert replay.accepted is False
    assert replay.unit == unit
    assert [record.effect.effect_type for record in runtime.snapshot().effects] == [
        "audio.enqueue"
    ]
    await owner.close()


@pytest.mark.asyncio
async def test_one_provider_event_can_cause_multiple_sequential_audio_units() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response(
        "provider-response-shared-event", "native-response-shared-event"
    )
    first = replace(
        audio(admission.response, admission.provider_response_id, 0),
        provider_event_id="provider-audio-shared-event",
    )
    second = replace(
        audio(admission.response, admission.provider_response_id, 1),
        provider_event_id="provider-audio-shared-event",
    )

    assert await owner.accept_audio(first) is True
    assert await owner.accept_audio(second) is True

    snapshot = owner.snapshot()
    assert snapshot.audio_count == 2
    assert [record.effect.effect_type for record in runtime.snapshot().effects] == [
        "audio.enqueue",
        "audio.enqueue",
    ]
    await owner.close()


@pytest.mark.asyncio
async def test_replacement_fences_stale_audio_done_ack_and_history() -> None:
    owner, runtime = await active_owner()
    old = await owner.accept_provider_response("provider-response-1", "native-r1")
    current = await owner.accept_provider_response("provider-response-2", "native-r2")
    before = runtime.snapshot()

    assert (
        await owner.accept_audio(audio(old.response, "provider-response-1", 0)) is False
    )
    assert (
        await owner.accept_provider_done(done(old.response, "provider-response-1"))
        is False
    )
    stale_ack = PresentationAck(
        ref=old.response,
        surface=PresentationSurface.AUDIO,
        unit_id="missing-old-unit",
        contiguous_cursor=0,
        presented_at="2026-08-25T10:00:01Z",
    )
    assert await owner.acknowledge_audio(stale_ack) is None

    after = runtime.snapshot()
    assert after.effects == before.effects
    assert after.presentation.records == before.presentation.records == ()
    assert current.response.response_generation > old.response.response_generation
    await owner.close()


@pytest.mark.asyncio
async def test_partial_ack_and_missing_transcript_never_admit_history() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    for sequence in range(2):
        assert (
            await owner.accept_audio(
                audio(admission.response, admission.provider_response_id, sequence)
            )
            is True
        )
    assert (
        await owner.accept_provider_done(
            done(admission.response, admission.provider_response_id, transcript=None)
        )
        is True
    )

    assert (
        await owner.acknowledge_audio(ack_for(runtime, admission.response, 0)) is None
    )
    assert (
        await owner.acknowledge_audio(
            ack_for(
                runtime,
                admission.response,
                1,
                presented_at="2026-08-25T10:00:02Z",
            )
        )
        is None
    )
    assert runtime.snapshot().presentation.completed_surfaces == (
        (admission.response, PresentationSurface.AUDIO),
    )
    await owner.close()


@pytest.mark.asyncio
async def test_final_ack_before_done_becomes_eligible_on_exact_ack_replay() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    assert (
        await owner.accept_audio(
            audio(admission.response, admission.provider_response_id, 0)
        )
        is True
    )
    ack = ack_for(runtime, admission.response, 0)

    assert await owner.acknowledge_audio(ack) is None
    assert (
        await owner.accept_provider_done(
            done(admission.response, admission.provider_response_id)
        )
        is True
    )
    assert await owner.acknowledge_audio(ack) == NativeHistoryAdmission(
        admission.response,
        "Canonical answer.",
        "2026-08-25T10:00:01Z",
    )
    await owner.close()


@pytest.mark.asyncio
async def test_exact_barge_is_idempotent_and_changed_cursor_has_zero_new_effect() -> (
    None
):
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    output = audio(admission.response, admission.provider_response_id, 0)
    assert await owner.accept_audio(output) is True
    cursor = NativePresentationCursor(
        response=admission.response,
        provider_item_id=output.provider_item_id,
        content_index=0,
        audio_end_ms=10,
    )

    first = await owner.barge_in(
        action_id="native-stop-1", response=admission.response, cursor=cursor
    )
    effect_count = len(runtime.snapshot().effects)
    replay = await owner.barge_in(
        action_id="native-stop-1", response=admission.response, cursor=cursor
    )

    assert first == replay
    assert first.applied is True
    assert len(runtime.snapshot().effects) == effect_count
    response_record = runtime.snapshot().conversation.responses[-1]
    assert response_record.cancel_state is CancelState.REQUESTED
    assert response_record.fenced is True
    with pytest.raises(NativeInteractionRuntimeError) as changed:
        await owner.barge_in(
            action_id="native-stop-1",
            response=admission.response,
            cursor=NativePresentationCursor(
                response=admission.response,
                provider_item_id=output.provider_item_id,
                content_index=0,
                audio_end_ms=9,
            ),
        )
    assert changed.value.reason == "NATIVE_BARGE_ACTION_CONFLICT"
    assert len(runtime.snapshot().effects) == effect_count
    await owner.close()


@pytest.mark.asyncio
async def test_barge_requires_received_audio_and_exact_confirmed_cursor() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    before_audio = runtime.snapshot()
    missing_audio_cursor = NativePresentationCursor(
        response=admission.response,
        provider_item_id="provider-assistant-item-provider-response-1",
        content_index=0,
        audio_end_ms=0,
    )

    with pytest.raises(NativeInteractionRuntimeError) as missing:
        await owner.barge_in(
            action_id="native-stop-before-audio",
            response=admission.response,
            cursor=missing_audio_cursor,
        )
    assert missing.value.reason == "NATIVE_BARGE_CURSOR_MISMATCH"
    assert runtime.snapshot() == before_audio

    output = audio(admission.response, admission.provider_response_id, 0)
    assert await owner.accept_audio(output) is True
    after_audio = runtime.snapshot()
    with pytest.raises(NativeInteractionRuntimeError) as ahead:
        await owner.barge_in(
            action_id="native-stop-ahead",
            response=admission.response,
            cursor=NativePresentationCursor(
                response=admission.response,
                provider_item_id=output.provider_item_id,
                content_index=output.content_index,
                audio_end_ms=21,
            ),
        )
    assert ahead.value.reason == "NATIVE_BARGE_CURSOR_AHEAD"
    assert runtime.snapshot() == after_audio
    await owner.close()


@pytest.mark.asyncio
async def test_cancelled_response_rejects_late_audio_done_and_ack() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    output = audio(admission.response, admission.provider_response_id, 0)
    assert await owner.accept_audio(output) is True
    ack = ack_for(runtime, admission.response, 0)
    await owner.barge_in(
        action_id="native-stop-1",
        response=admission.response,
        cursor=NativePresentationCursor(
            response=admission.response,
            provider_item_id=output.provider_item_id,
            content_index=0,
            audio_end_ms=10,
        ),
    )
    before = runtime.snapshot()

    assert await owner.accept_audio(output) is False
    assert (
        await owner.accept_provider_done(
            done(admission.response, admission.provider_response_id)
        )
        is False
    )
    assert await owner.acknowledge_audio(ack) is None

    after = runtime.snapshot()
    assert after.effects == before.effects
    assert sum(record.state is EffectState.PENDING for record in after.effects) == sum(
        record.state is EffectState.PENDING for record in before.effects
    )
    await owner.close()


@pytest.mark.asyncio
async def test_provider_done_wins_race_and_late_barge_has_zero_cancel_effect() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    output = audio(admission.response, admission.provider_response_id, 0)
    assert await owner.accept_audio(output) is True
    assert (
        await owner.accept_provider_done(
            done(admission.response, admission.provider_response_id)
        )
        is True
    )
    before = runtime.snapshot()

    with pytest.raises(NativeInteractionRuntimeError) as stale:
        await owner.barge_in(
            action_id="native-stop-after-done",
            response=admission.response,
            cursor=NativePresentationCursor(
                response=admission.response,
                provider_item_id=output.provider_item_id,
                content_index=output.content_index,
                audio_end_ms=10,
            ),
        )

    assert stale.value.reason == "NATIVE_BARGE_RESPONSE_STALE"
    assert runtime.snapshot() == before
    assert all(
        record.effect.effect_type != "response.cancel" for record in before.effects
    )
    await owner.close()


@pytest.mark.asyncio
async def test_concurrent_exact_audio_and_done_are_at_most_once() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    output = audio(admission.response, admission.provider_response_id, 0)

    audio_results = await asyncio.gather(
        owner.accept_audio(output), owner.accept_audio(output)
    )
    done_value = done(admission.response, admission.provider_response_id)
    done_results = await asyncio.gather(
        owner.accept_provider_done(done_value), owner.accept_provider_done(done_value)
    )

    assert sorted(audio_results) == [False, True]
    assert sorted(done_results) == [False, True]
    assert [record.effect.effect_type for record in runtime.snapshot().effects].count(
        "audio.enqueue"
    ) == 1
    await owner.close()


@pytest.mark.asyncio
async def test_invalid_done_provenance_fails_before_terminal_or_history_effect() -> (
    None
):
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    assert (
        await owner.accept_audio(
            audio(admission.response, admission.provider_response_id, 0)
        )
        is True
    )
    before = runtime.snapshot()
    invalid = NativeProviderDone(
        provider_event_id="provider-done-invalid",
        provider_response_id=admission.provider_response_id,
        response=admission.response,
        completed=True,
        transcript="Canonical answer.",
        transcript_event_id=None,
    )

    with pytest.raises(NativeInteractionRuntimeError) as raised:
        await owner.accept_provider_done(invalid)

    assert raised.value.reason == "NATIVE_TRANSCRIPT_PROVENANCE_INVALID"
    assert runtime.snapshot() == before
    await owner.close()


@pytest.mark.asyncio
async def test_audio_event_identity_cannot_be_reused_across_responses() -> None:
    owner, runtime = await active_owner()
    first = await owner.accept_provider_response("provider-response-1", "native-r1")
    first_output = audio(first.response, first.provider_response_id, 0)
    assert await owner.accept_audio(first_output) is True
    second = await owner.accept_provider_response("provider-response-2", "native-r2")
    reused = replace(
        audio(second.response, second.provider_response_id, 0),
        provider_event_id=first_output.provider_event_id,
    )
    before = runtime.snapshot()

    with pytest.raises(NativeInteractionRuntimeError) as raised:
        await owner.accept_audio(reused)

    assert raised.value.reason == "NATIVE_AUDIO_REPLAY_CONFLICT"
    assert runtime.snapshot() == before
    await owner.close()


@pytest.mark.asyncio
async def test_oversized_audio_fails_before_runtime_or_media_effect() -> None:
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    oversized = audio(
        admission.response,
        admission.provider_response_id,
        0,
        pcm16=b"\x00\x00" * (MAX_NATIVE_AUDIO_DELTA_BYTES // 2 + 1),
    )
    before = runtime.snapshot()

    with pytest.raises(NativeInteractionRuntimeError) as raised:
        await owner.accept_audio(oversized)

    assert raised.value.reason == "NATIVE_AUDIO_INVALID"
    assert runtime.snapshot() == before
    await owner.close()


@pytest.mark.asyncio
async def test_audio_ledger_capacity_fails_before_runtime_or_media_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_runtime_module, "_MAX_NATIVE_RUNTIME_RECORDS", 1)
    owner, runtime = await active_owner()
    admission = await owner.accept_provider_response("provider-response-1", "native-r1")
    assert (
        await owner.accept_audio(
            audio(admission.response, admission.provider_response_id, 0)
        )
        is True
    )
    before = runtime.snapshot()

    with pytest.raises(NativeInteractionRuntimeError) as raised:
        await owner.accept_audio(
            audio(admission.response, admission.provider_response_id, 1)
        )

    assert raised.value.reason == "NATIVE_AUDIO_LEDGER_FULL"
    assert runtime.snapshot() == before
    await owner.close()
