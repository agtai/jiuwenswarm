# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ContractViolation,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    CancelState,
    InteractionState,
    ResponseState,
)
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    ConversationRuntimeLoop,
    ConversationRuntimeLoopViolation,
    EffectState,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    HistorySurfacePolicy,
    PresentationAck,
    PresentationLedgerViolation,
    PresentationState,
    PresentationSurface,
    PresentationUnit,
)


def scope() -> ScopeRef:
    return ScopeRef("subject-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def commit(
    *,
    turn_id: str = "turn-1",
    commit_id: str = "commit-1",
    text: str = "请解释 code/path",
) -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": commit_id,
            "turn_id": turn_id,
            "interaction_id": "interaction-1",
            "text": text,
            "hypothesis_provenance": {"provider": "fake-sr", "seq": 1},
            "scope": scope().to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-05T08:00:00Z",
        }
    )


@pytest.fixture
async def loop_factory() -> Callable[..., ConversationRuntimeLoop]:
    loops: list[ConversationRuntimeLoop] = []

    def create(**kwargs: object) -> ConversationRuntimeLoop:
        runtime = ConversationRuntimeLoop(scope(), **kwargs)
        loops.append(runtime)
        return runtime

    yield create
    for runtime in loops:
        if not runtime.snapshot().closed:
            await runtime.close()


async def prepared(
    factory: Callable[..., ConversationRuntimeLoop],
    *,
    policy: HistorySurfacePolicy = HistorySurfacePolicy.TEXT,
    **kwargs: object,
) -> tuple[ConversationRuntimeLoop, ResponseRef]:
    runtime = factory(**kwargs)
    assert await runtime.start() is True
    await runtime.open_interaction("interaction-1")
    await runtime.start_turn("interaction-1", "turn-1")
    accepted, _ = await runtime.commit_turn(commit())
    assert accepted is True
    ref, _ = await runtime.accept_response(
        "turn-1", "response-1", history_policy=policy
    )
    await runtime.transition_response(ref, ResponseState.GENERATING)
    return runtime, ref


def unit(
    ref: ResponseRef,
    surface: PresentationSurface,
    unit_id: str,
    seq: int,
    start: int,
    end: int,
    content_ref: str,
) -> PresentationUnit:
    return PresentationUnit(
        ref=ref,
        surface=surface,
        unit_id=unit_id,
        seq=seq,
        source_start_utf8=start,
        source_end_utf8=end,
        content_ref=content_ref,
    )


def ack(
    ref: ResponseRef,
    surface: PresentationSurface,
    unit_id: str,
    cursor: int,
    *,
    presented_at: str = "2026-08-05T08:00:01Z",
) -> PresentationAck:
    return PresentationAck(
        ref=ref,
        surface=surface,
        unit_id=unit_id,
        contiguous_cursor=cursor,
        presented_at=presented_at,
    )


async def produce_enqueue_ack(
    runtime: ConversationRuntimeLoop,
    item: PresentationUnit,
) -> None:
    assert await runtime.produce_unit(item) is True
    accepted, effect = await runtime.enqueue_unit(item.ref, item.surface, item.unit_id)
    assert accepted is True
    assert effect is not None
    claimed = await runtime.claim_effects()
    assert effect in claimed
    assert (
        await runtime.acknowledge_presentation(
            ack(item.ref, item.surface, item.unit_id, item.seq)
        )
        is True
    )


@pytest.mark.parametrize(
    ("policy", "expected_surfaces"),
    [
        (HistorySurfacePolicy.TEXT, (PresentationSurface.TEXT,)),
        (HistorySurfacePolicy.AUDIO, (PresentationSurface.AUDIO,)),
        (
            HistorySurfacePolicy.UNION,
            (PresentationSurface.AUDIO, PresentationSurface.TEXT),
        ),
    ],
)
async def test_presented_history_uses_only_exact_acked_selected_surface(
    loop_factory: Callable[..., ConversationRuntimeLoop],
    policy: HistorySurfacePolicy,
    expected_surfaces: tuple[PresentationSurface, ...],
) -> None:
    runtime, ref = await prepared(loop_factory, policy=policy)
    text = unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 6, "sha256:nihao")
    audio = unit(ref, PresentationSurface.AUDIO, "audio-0", 0, 0, 6, "sha256:nihao")

    assert await runtime.produce_unit(text) is True
    assert (await runtime.enqueue_unit(ref, text.surface, text.unit_id))[0] is True
    assert await runtime.presented_history(ref) == ()
    assert (
        await runtime.acknowledge_presentation(ack(ref, text.surface, text.unit_id, 0))
        is True
    )

    assert await runtime.produce_unit(audio) is True
    assert (await runtime.enqueue_unit(ref, audio.surface, audio.unit_id))[0] is True
    assert (
        await runtime.acknowledge_presentation(
            ack(ref, audio.surface, audio.unit_id, 0)
        )
        is True
    )

    history = await runtime.presented_history(ref)
    assert len(history) == 1
    assert history[0].source_start_utf8 == 0
    assert history[0].source_end_utf8 == 6
    assert history[0].content_ref == "sha256:nihao"
    assert history[0].surfaces == expected_surfaces
    assert all(
        item.effect.effect_type != "history.append"
        for item in runtime.snapshot().effects
    )


async def test_start_is_explicit_and_feature_off_has_zero_task_state_and_effect(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime = loop_factory()
    before = runtime.snapshot()
    assert before.started is False
    assert before.worker_running is False
    with pytest.raises(ConversationRuntimeLoopViolation) as raised:
        await runtime.open_interaction("interaction-1")
    assert raised.value.reason == "RUNTIME_LOOP_NOT_STARTED"
    assert runtime.snapshot() == before

    disabled = loop_factory(enabled=False)
    assert await disabled.start() is False
    with pytest.raises(ConversationRuntimeLoopViolation) as disabled_error:
        await disabled.open_interaction("interaction-1")
    assert disabled_error.value.reason == "FEATURE_DISABLED"
    snapshot = disabled.snapshot()
    assert snapshot.started is False
    assert snapshot.worker_running is False
    assert snapshot.conversation.last_seq == 0
    assert snapshot.presentation.records == ()
    assert snapshot.effects == ()

    with pytest.raises(ConversationRuntimeLoopViolation) as invalid_flag:
        ConversationRuntimeLoop(scope(), enabled=1)  # type: ignore[arg-type]
    assert invalid_flag.value.reason == "INVALID_FEATURE_FLAG"


async def test_output_before_generating_and_invalid_state_type_fail_closed(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime = loop_factory()
    await runtime.start()
    await runtime.open_interaction("interaction-1")
    await runtime.start_turn("interaction-1", "turn-1")
    await runtime.commit_turn(commit())
    ref, _ = await runtime.accept_response("turn-1", "response-1")
    before = runtime.snapshot()
    with pytest.raises(ConversationRuntimeLoopViolation) as inactive:
        await runtime.produce_unit(
            unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 3, "sha256:a")
        )
    assert inactive.value.reason == "RESPONSE_OUTPUT_NOT_ACTIVE"
    with pytest.raises(ConversationRuntimeLoopViolation) as invalid_state:
        await runtime.transition_response(ref, "terminal")  # type: ignore[arg-type]
    assert invalid_state.value.reason == "INVALID_RESPONSE_STATE"
    assert runtime.snapshot() == before
    await runtime.transition_response(ref, ResponseState.GENERATING)


async def test_interaction_close_rejects_new_commit_but_preserves_committed_replay(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime = loop_factory()
    await runtime.start()
    await runtime.open_interaction("interaction-1")
    await runtime.start_turn("interaction-1", "turn-1")
    await runtime.transition_interaction("interaction-1", InteractionState.CLOSED)
    before = runtime.snapshot()
    with pytest.raises(ConversationRuntimeLoopViolation) as closed:
        await runtime.commit_turn(commit())
    assert closed.value.reason == "INTERACTION_NOT_OPEN"
    assert runtime.snapshot() == before

    committed, _ = await prepared(loop_factory)
    await committed.transition_interaction("interaction-1", InteractionState.CLOSED)
    assert await committed.commit_turn(commit()) == (False, None)
    with pytest.raises(ContractViolation) as conflict:
        await committed.commit_turn(commit(text="changed"))
    assert conflict.value.reason == "TURN_COMMIT_CONFLICT"


async def test_invalid_unit_and_ack_fail_closed_and_worker_continues(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    first = unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 6, "sha256:a")
    second = unit(ref, PresentationSurface.TEXT, "text-1", 1, 6, 10, "sha256:b")
    assert await runtime.produce_unit(first) is True
    assert await runtime.produce_unit(second) is True
    assert (await runtime.enqueue_unit(ref, second.surface, second.unit_id))[0] is True
    before = runtime.snapshot()

    with pytest.raises(PresentationLedgerViolation) as raised:
        await runtime.acknowledge_presentation(
            ack(ref, second.surface, second.unit_id, 1)
        )
    assert raised.value.reason == "PRESENTATION_ACK_NOT_ENQUEUED"
    assert runtime.snapshot() == before

    gap = unit(ref, PresentationSurface.TEXT, "text-3", 3, 10, 12, "sha256:c")
    with pytest.raises(PresentationLedgerViolation) as gap_error:
        await runtime.produce_unit(gap)
    assert gap_error.value.reason == "NON_CONTIGUOUS_PRESENTATION_SEQUENCE"

    rewrite = unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 5, "changed")
    with pytest.raises(PresentationLedgerViolation) as rewrite_error:
        await runtime.produce_unit(rewrite)
    assert rewrite_error.value.reason == "PRESENTATION_UNIT_REWRITE"

    assert (await runtime.enqueue_unit(ref, first.surface, first.unit_id))[0] is True
    assert (
        await runtime.acknowledge_presentation(
            ack(ref, second.surface, second.unit_id, 1)
        )
        is True
    )
    assert len(await runtime.presented_history(ref)) == 2
    effects_after_ack = runtime.snapshot().effects
    assert (await runtime.enqueue_unit(ref, second.surface, second.unit_id)) == (
        False,
        None,
    )
    assert (
        await runtime.acknowledge_presentation(
            ack(ref, second.surface, second.unit_id, 1)
        )
        is False
    )
    assert runtime.snapshot().effects == effects_after_ack


@pytest.mark.parametrize("policy", tuple(HistorySurfacePolicy))
async def test_wrong_generation_ack_and_cross_surface_conflict_have_zero_effect(
    loop_factory: Callable[..., ConversationRuntimeLoop],
    policy: HistorySurfacePolicy,
) -> None:
    runtime, ref = await prepared(loop_factory, policy=policy)
    text = unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 6, "sha256:a")
    assert await runtime.produce_unit(text) is True
    effects_before = runtime.snapshot().effects
    stale = ResponseRef(
        ref.interaction_id, ref.response_id, ref.response_generation + 1
    )
    with pytest.raises(ConversationRuntimeLoopViolation) as stale_error:
        await runtime.acknowledge_presentation(
            ack(stale, PresentationSurface.TEXT, "text-0", 0)
        )
    assert stale_error.value.reason == "STALE_RESPONSE_REFERENCE"
    assert runtime.snapshot().effects == effects_before

    conflicting_audio = unit(
        ref, PresentationSurface.AUDIO, "audio-0", 0, 0, 6, "sha256:changed"
    )
    with pytest.raises(PresentationLedgerViolation) as surface_error:
        await runtime.produce_unit(conflicting_audio)
    assert surface_error.value.reason == "CROSS_SURFACE_CONTENT_CONFLICT"
    assert all(
        record.unit.surface is not PresentationSurface.AUDIO
        for record in runtime.snapshot().presentation.records
    )

    empty = unit(ref, PresentationSurface.AUDIO, "audio-empty", 0, 0, 0, "sha256:empty")
    with pytest.raises(PresentationLedgerViolation) as empty_error:
        await runtime.produce_unit(empty)
    assert empty_error.value.reason == "EMPTY_PRESENTATION_SOURCE_SPAN"


async def test_barge_in_stops_only_audio_then_optional_cancel_fences_text(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory, policy=HistorySurfacePolicy.UNION)
    for surface, prefix in (
        (PresentationSurface.TEXT, "text"),
        (PresentationSurface.AUDIO, "audio"),
    ):
        await produce_enqueue_ack(
            runtime,
            unit(ref, surface, f"{prefix}-0", 0, 0, 6, "sha256:a"),
        )
        tail = unit(ref, surface, f"{prefix}-1", 1, 6, 10, "sha256:b")
        assert await runtime.produce_unit(tail) is True
        assert (await runtime.enqueue_unit(ref, surface, tail.unit_id))[0] is True

    result = await runtime.barge_in("barge-1", ref)
    assert result.applied is True
    assert result.replayed is False
    effects_after_stop = runtime.snapshot().effects
    assert [
        item.effect.effect_type
        for item in effects_after_stop
        if item.effect.effect_id in result.effect_ids
    ] == ["playback.stop"]
    assert all(
        item.effect.effect_type not in {"round.cancel", "task.cancel"}
        for item in effects_after_stop
    )

    records = runtime.snapshot().presentation.records
    audio_states = [
        item.state for item in records if item.unit.surface is PresentationSurface.AUDIO
    ]
    text_states = [
        item.state for item in records if item.unit.surface is PresentationSurface.TEXT
    ]
    assert audio_states == [PresentationState.PRESENTED, PresentationState.INVALIDATED]
    assert text_states == [PresentationState.PRESENTED, PresentationState.ENQUEUED]

    assert (
        await runtime.acknowledge_presentation(
            ack(ref, PresentationSurface.TEXT, "text-1", 1)
        )
        is True
    )
    with pytest.raises(PresentationLedgerViolation) as late_audio:
        await runtime.acknowledge_presentation(
            ack(ref, PresentationSurface.AUDIO, "audio-1", 1)
        )
    assert late_audio.value.reason == "PRESENTATION_SURFACE_CLOSED"

    replay = await runtime.barge_in("barge-1", ref)
    assert replay.replayed is True
    assert replay.effect_ids == result.effect_ids
    assert runtime.snapshot().effects == effects_after_stop

    with pytest.raises(ConversationRuntimeLoopViolation) as conflict:
        await runtime.barge_in("barge-1", ref, cancel_response=True)
    assert conflict.value.reason == "BARGE_IN_ACTION_CONFLICT"
    assert runtime.snapshot().effects == effects_after_stop

    cancelled = await runtime.barge_in("barge-2", ref, cancel_response=True)
    assert cancelled.applied is True
    assert [
        item.effect.effect_type
        for item in runtime.snapshot().effects
        if item.effect.effect_id in cancelled.effect_ids
    ] == ["response.cancel"]
    response = runtime.snapshot().conversation.responses[0]
    assert response.cancel_state is CancelState.REQUESTED
    assert response.state is ResponseState.GENERATING
    history = await runtime.presented_history(ref)
    assert [(item.source_start_utf8, item.source_end_utf8) for item in history] == [
        (0, 6),
        (6, 10),
    ]


async def test_accepted_presentation_ack_linearizes_before_later_barge_in(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(
        loop_factory,
        policy=HistorySurfacePolicy.AUDIO,
        normal_capacity=1,
        control_capacity=1,
    )
    audio = unit(ref, PresentationSurface.AUDIO, "audio-0", 0, 0, 6, "sha256:a")
    await runtime.produce_unit(audio)
    accepted, effect = await runtime.enqueue_unit(ref, audio.surface, audio.unit_id)
    assert accepted is True and effect is not None
    assert effect in await runtime.claim_effects()

    ack_future = runtime.post_presentation_ack(
        ack(ref, audio.surface, audio.unit_id, 0)
    )
    barge_future = runtime.post_barge_in("barge-after-ack", ref)
    pending = runtime.snapshot()
    assert pending.pending_observation == 1
    assert pending.pending_control == 1
    barge_result = await barge_future
    assert await ack_future is True
    assert barge_result.applied is True
    history = await runtime.presented_history(ref)
    assert len(history) == 1
    assert history[0].content_ref == "sha256:a"
    assert (
        runtime.snapshot().presentation.records[0].state is PresentationState.PRESENTED
    )


async def test_ordered_ack_does_not_overtake_earlier_normal_enqueue(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory, policy=HistorySurfacePolicy.AUDIO)
    audio = unit(ref, PresentationSurface.AUDIO, "audio-0", 0, 0, 6, "sha256:a")
    assert await runtime.produce_unit(audio) is True

    enqueue_future = runtime.post_enqueue_unit(ref, audio.surface, audio.unit_id)
    ack_future = runtime.post_presentation_ack(
        ack(ref, audio.surface, audio.unit_id, 0)
    )

    accepted, effect = await enqueue_future
    assert accepted is True and effect is not None
    assert await ack_future is True


async def test_rejected_barge_action_is_replayed_and_cannot_change_target(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    stale = ResponseRef(ref.interaction_id, "missing", ref.response_generation)
    effects_before = runtime.snapshot().effects
    with pytest.raises(ConversationRuntimeLoopViolation) as first:
        await runtime.barge_in("rejected-barge", stale)
    assert first.value.reason == "STALE_RESPONSE_REFERENCE"
    with pytest.raises(ConversationRuntimeLoopViolation) as replay:
        await runtime.barge_in("rejected-barge", stale)
    assert replay.value.reason == "STALE_RESPONSE_REFERENCE"
    with pytest.raises(ConversationRuntimeLoopViolation) as conflict:
        await runtime.barge_in("rejected-barge", ref)
    assert conflict.value.reason == "BARGE_IN_ACTION_CONFLICT"
    assert runtime.snapshot().effects == effects_before


async def test_cancel_ack_or_unknown_after_terminal_never_infers_or_rewrites_terminal(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    first_cancel = await runtime.request_response_cancel("cancel-1", ref)
    effects_after_cancel = runtime.snapshot().effects
    replayed_cancel = await runtime.request_response_cancel("cancel-1", ref)
    assert first_cancel.applied is True
    assert replayed_cancel.replayed is True
    assert replayed_cancel.effect_id == first_cancel.effect_id
    assert runtime.snapshot().effects == effects_after_cancel
    await runtime.transition_response(
        ref, ResponseState.TERMINAL, outcome=TerminalOutcome.INTERRUPTED
    )
    event = await runtime.acknowledge_response_cancel(ref)
    record = runtime.snapshot().conversation.responses[0]
    assert event is not None
    assert event.event_type == "response.cancel_acknowledged"
    assert record.cancel_state is CancelState.ACKNOWLEDGED
    assert record.state is ResponseState.TERMINAL
    assert record.outcome is TerminalOutcome.INTERRUPTED

    second, second_ref = await prepared(loop_factory)
    await second.request_response_cancel("cancel-2", second_ref)
    await second.transition_response(
        second_ref, ResponseState.TERMINAL, outcome=TerminalOutcome.UNKNOWN
    )
    unknown_event = await second.mark_response_cancel_unknown(second_ref)
    assert unknown_event is not None
    unknown_record = second.snapshot().conversation.responses[0]
    assert unknown_event.event_type == "response.cancel_result_unknown"
    assert unknown_record.cancel_state is CancelState.RESULT_UNKNOWN
    assert unknown_record.state is ResponseState.TERMINAL
    assert unknown_record.outcome is TerminalOutcome.UNKNOWN
    late_ack = await second.acknowledge_response_cancel(second_ref)
    assert late_ack is not None
    assert late_ack.event_type == "response.cancel_acknowledged"
    assert await second.mark_response_cancel_unknown(second_ref) is None
    reconciled = second.snapshot().conversation.responses[0]
    assert reconciled.cancel_state is CancelState.ACKNOWLEDGED
    assert reconciled.state is ResponseState.TERMINAL
    assert reconciled.outcome is TerminalOutcome.UNKNOWN


async def test_response_cancel_command_id_cannot_change_generation(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, first = await prepared(loop_factory)
    await runtime.request_response_cancel("cancel-exact", first)
    second, _ = await runtime.accept_response("turn-1", "response-2")
    await runtime.transition_response(second, ResponseState.GENERATING)
    effects_before = runtime.snapshot().effects
    with pytest.raises(ConversationRuntimeLoopViolation) as conflict:
        await runtime.request_response_cancel("cancel-exact", second)
    assert conflict.value.reason == "RESPONSE_CANCEL_COMMAND_CONFLICT"
    assert runtime.snapshot().effects == effects_before


async def test_overlapping_response_cancel_reuses_one_control_slot_and_effect(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory, control_capacity=1)
    first = runtime.post_response_cancel("cancel-overlap", ref)
    assert runtime.post_response_cancel("cancel-overlap", ref) is first
    other_ref = ResponseRef(ref.interaction_id, "other", ref.response_generation + 1)
    with pytest.raises(ConversationRuntimeLoopViolation) as conflict:
        runtime.post_response_cancel("cancel-overlap", other_ref)
    assert conflict.value.reason == "RESPONSE_CANCEL_COMMAND_CONFLICT"
    with pytest.raises(ConversationRuntimeLoopViolation) as full:
        runtime.post_response_cancel("cancel-other", ref)
    assert full.value.reason == "CONTROL_QUEUE_FULL"

    result = await first
    assert result.applied is True
    assert [item.effect.effect_type for item in runtime.snapshot().effects] == [
        "response.cancel"
    ]


async def test_completed_control_replays_bypass_a_full_control_lane(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory, control_capacity=1)
    first_barge = await runtime.barge_in("barge-complete", ref)
    await asyncio.sleep(0)

    cancel_pending = runtime.post_response_cancel("cancel-complete", ref)
    barge_replay = runtime.post_barge_in("barge-complete", ref)
    assert barge_replay.done() is True
    replayed_barge = await barge_replay
    assert replayed_barge.replayed is True
    assert replayed_barge.effect_ids == first_barge.effect_ids
    first_cancel = await cancel_pending
    await asyncio.sleep(0)

    other_pending = runtime.post_barge_in("barge-other", ref)
    cancel_replay = runtime.post_response_cancel("cancel-complete", ref)
    assert cancel_replay.done() is True
    replayed_cancel = await cancel_replay
    assert replayed_cancel.replayed is True
    assert replayed_cancel.effect_id == first_cancel.effect_id
    await other_pending


async def test_new_generation_invalidates_unclaimed_old_output_and_late_callbacks(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, first = await prepared(loop_factory)
    old = unit(first, PresentationSurface.TEXT, "old-text-0", 0, 0, 3, "sha256:old")
    assert await runtime.produce_unit(old) is True
    accepted, old_effect = await runtime.enqueue_unit(first, old.surface, old.unit_id)
    assert accepted is True and old_effect is not None

    second, _ = await runtime.accept_response(
        "turn-1", "response-2", history_policy=HistorySurfacePolicy.TEXT
    )
    await runtime.transition_response(second, ResponseState.GENERATING)
    old_effect_record = next(
        item
        for item in runtime.snapshot().effects
        if item.effect.effect_id == old_effect.effect_id
    )
    assert old_effect_record.state is EffectState.INVALIDATED
    assert old_effect_record.invalidated_reason == "response_replaced"

    with pytest.raises(ConversationRuntimeLoopViolation) as old_output:
        await runtime.produce_unit(
            unit(first, PresentationSurface.TEXT, "old-text-1", 1, 3, 6, "late")
        )
    assert old_output.value.reason == "STALE_RESPONSE_OUTPUT"
    with pytest.raises(ConversationRuntimeLoopViolation) as old_ack:
        await runtime.acknowledge_presentation(
            ack(first, PresentationSurface.TEXT, "old-text-0", 0)
        )
    assert old_ack.value.reason == "STALE_RESPONSE_OUTPUT"

    before_late_state = runtime.snapshot()
    with pytest.raises(ConversationRuntimeLoopViolation) as old_nonterminal:
        await runtime.transition_response(first, ResponseState.SPEAKING)
    assert old_nonterminal.value.reason == "FENCED_RESPONSE_NONTERMINAL_TRANSITION"
    assert runtime.snapshot() == before_late_state

    before_terminal = runtime.snapshot().effects
    await runtime.transition_response(
        first, ResponseState.TERMINAL, outcome=TerminalOutcome.INTERRUPTED
    )
    snapshot = runtime.snapshot()
    assert snapshot.effects == before_terminal
    current = next(
        item for item in snapshot.conversation.responses if item.ref == second
    )
    old_record = next(
        item for item in snapshot.conversation.responses if item.ref == first
    )
    assert current.state is ResponseState.GENERATING
    assert current.fenced is False
    assert old_record.state is ResponseState.TERMINAL


async def test_claimed_old_effect_remains_auditable_with_exact_stale_tuple(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, first = await prepared(loop_factory)
    old = unit(first, PresentationSurface.TEXT, "old-text-0", 0, 0, 3, "sha256:old")
    await runtime.produce_unit(old)
    accepted, effect = await runtime.enqueue_unit(first, old.surface, old.unit_id)
    assert accepted is True and effect is not None
    assert await runtime.claim_effects(limit=1) == (effect,)

    second, _ = await runtime.accept_response("turn-1", "response-2")
    claimed = next(
        item
        for item in runtime.snapshot().effects
        if item.effect.effect_id == effect.effect_id
    )
    assert claimed.state is EffectState.CLAIMED
    assert claimed.effect.ref == first
    assert claimed.effect.ref != second


async def test_slow_fake_upstream_does_not_block_replacement_and_is_fenced_when_late(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, first = await prepared(loop_factory)
    release = asyncio.Event()

    async def slow_upstream() -> bool:
        await release.wait()
        return await runtime.produce_unit(
            unit(first, PresentationSurface.TEXT, "late", 0, 0, 4, "sha256:late")
        )

    delayed = asyncio.create_task(slow_upstream())
    second, _ = await runtime.accept_response("turn-1", "response-2")
    await runtime.transition_response(second, ResponseState.GENERATING)
    assert delayed.done() is False
    release.set()
    with pytest.raises(ConversationRuntimeLoopViolation) as late:
        await delayed
    assert late.value.reason == "STALE_RESPONSE_OUTPUT"
    assert all(
        item.unit.ref != first for item in runtime.snapshot().presentation.records
    )


async def test_control_lane_preempts_saturated_normal_output_lane(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory, normal_capacity=1, control_capacity=1)
    queued = runtime.post_produce_unit(
        unit(ref, PresentationSurface.AUDIO, "audio-0", 0, 0, 4, "sha256:a")
    )
    with pytest.raises(ConversationRuntimeLoopViolation) as full:
        runtime.post_produce_unit(
            unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 4, "sha256:a")
        )
    assert full.value.reason == "NORMAL_QUEUE_FULL"

    control = runtime.post_barge_in("barge-priority", ref)
    assert runtime.post_barge_in("barge-priority", ref) is control
    with pytest.raises(ConversationRuntimeLoopViolation) as conflict:
        runtime.post_barge_in("barge-priority", ref, cancel_response=True)
    assert conflict.value.reason == "BARGE_IN_ACTION_CONFLICT"
    with pytest.raises(ConversationRuntimeLoopViolation) as control_full:
        runtime.post_barge_in("barge-other", ref)
    assert control_full.value.reason == "CONTROL_QUEUE_FULL"
    pending = runtime.snapshot()
    assert pending.pending_normal == 1
    assert pending.pending_control == 1
    result = await control
    assert result.applied is True
    with pytest.raises(PresentationLedgerViolation) as fenced_output:
        await queued
    assert fenced_output.value.reason == "PRESENTATION_SURFACE_CLOSED"
    assert [item.effect.effect_type for item in runtime.snapshot().effects] == [
        "playback.stop"
    ]


async def test_interaction_close_and_loop_shutdown_never_cancel_round_or_task(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    audio = unit(ref, PresentationSurface.AUDIO, "audio-0", 0, 0, 4, "sha256:a")
    assert await runtime.produce_unit(audio) is True
    assert (await runtime.enqueue_unit(ref, audio.surface, audio.unit_id))[0] is True
    await runtime.transition_interaction("interaction-1", InteractionState.CLOSED)
    effects = runtime.snapshot().effects
    assert any(item.effect.effect_type == "playback.stop" for item in effects)
    assert all(
        item.effect.effect_type
        not in {"response.cancel", "round.cancel", "task.cancel"}
        for item in effects
    )
    with pytest.raises(ConversationRuntimeLoopViolation) as stale:
        await runtime.acknowledge_presentation(
            ack(ref, PresentationSurface.AUDIO, "audio-0", 0)
        )
    assert stale.value.reason == "STALE_RESPONSE_OUTPUT"

    await runtime.close()
    snapshot = runtime.snapshot()
    assert snapshot.closed is True
    assert snapshot.worker_running is False
    assert snapshot.pending_normal == 0
    assert snapshot.pending_observation == 0
    assert snapshot.pending_control == 0
    with pytest.raises(ConversationRuntimeLoopViolation) as closed:
        runtime.post_barge_in("after-close", ref)
    assert closed.value.reason == "RUNTIME_LOOP_CLOSED"


async def test_close_drains_accepted_future_and_fences_memory_only_state(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    queued = runtime.post_produce_unit(
        unit(ref, PresentationSurface.TEXT, "text-0", 0, 0, 4, "sha256:a")
    )
    close_task = asyncio.create_task(runtime.close())
    assert await queued is True
    shutdown_effects = await close_task
    assert [item.effect_type for item in shutdown_effects] == ["playback.stop"]
    snapshot = runtime.snapshot()
    assert snapshot.closed is True
    assert snapshot.worker_running is False
    assert snapshot.presentation.records[0].state is PresentationState.INVALIDATED
    assert all(
        item.effect_type not in {"response.cancel", "round.cancel", "task.cancel"}
        for item in shutdown_effects
    )

    restarted = loop_factory()
    assert await restarted.start() is True
    assert restarted.snapshot().presentation.records == ()
    assert restarted.snapshot().conversation.responses == ()


async def test_close_returns_existing_pending_control_effects(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    barge = await runtime.barge_in("barge-pending", ref)

    shutdown_effects = await runtime.close()

    assert barge.effect_ids == tuple(item.effect_id for item in shutdown_effects)
    assert [item.effect_type for item in shutdown_effects] == ["playback.stop"]
    assert all(item.state is EffectState.CLAIMED for item in runtime.snapshot().effects)

    runtime, ref = await prepared(loop_factory)
    cancel = await runtime.request_response_cancel("cancel-pending", ref)

    shutdown_effects = await runtime.close()

    assert cancel.effect_id in {item.effect_id for item in shutdown_effects}
    assert [item.effect_type for item in shutdown_effects] == [
        "response.cancel",
        "playback.stop",
    ]
    assert all(item.state is EffectState.CLAIMED for item in runtime.snapshot().effects)


async def test_cancelled_close_waiter_does_not_lose_the_single_shutdown_result(
    loop_factory: Callable[..., ConversationRuntimeLoop],
) -> None:
    runtime, ref = await prepared(loop_factory)
    barge = await runtime.barge_in("barge-before-cancelled-close", ref)

    close_task = asyncio.create_task(runtime.close())
    await asyncio.sleep(0)
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task

    recovered = await runtime.close()
    assert barge.effect_ids == tuple(item.effect_id for item in recovered)
    assert [item.effect_type for item in recovered] == ["playback.stop"]
    assert await runtime.close() == ()
