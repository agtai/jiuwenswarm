# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Agent generation-time interruption: fence, replacement and scope limits.

These tests exercise the real Harness, Bridge and Conversation Runtime.  Only
the lowest formal Agent adapter is a double, and it is written against the same
``process_formal_live_voice_stream_impl`` contract the product adapter uses so a
fenced round still observes its own cancellation.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CancelScope,
    CommandEnvelope,
    IdentityKind,
    ResponseRef,
)
from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    AgentConversationRuntime,
    AgentConversationRuntimeViolation,
    AgentConversationShutdownStatus,
    GenerationInterruptionFenceStatus,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    InteractionState,
    ResponseState,
)
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    _MAX_RETAINED_GENERATION_INTERRUPTS,
    ConversationRuntimeLoop,
    ConversationRuntimeLoopViolation,
    GenerationInterruptionResult,
    _RetainedGenerationInterrupt,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessRoundHandle,
    JiuWenSwarmRoundHarness,
    RoundCancelResult,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)

from tests.unit_tests.live_voice.test_agent_conversation_runtime import (
    RecordingHistoryWriter,
    commit,
    facade,
    id_factory,
    scope,
)


class SequencedFormalAdapter:
    """One formal adapter whose rounds are released independently.

    ``opening_delta`` emits a partial token before the gate so a test can
    interrupt a round that has already produced visible output.  ``hold_final``
    keeps the stream open after the final so the response stays non-terminal
    and an interruption still has a live generation to fence.
    """

    _is_session_scoped_adapter = False

    def __init__(
        self,
        rounds: int = 2,
        *,
        final: str = "formal answer",
        opening_delta: bool = False,
        hold_final: bool = False,
    ) -> None:
        self.gates = [asyncio.Event() for _ in range(rounds)]
        self.entered = [asyncio.Event() for _ in range(rounds)]
        self.tails = [asyncio.Event() for _ in range(rounds)]
        self.delta_emitted = [asyncio.Event() for _ in range(rounds)]
        self.finals = [f"{final} {index + 1}" for index in range(rounds)]
        self.deltas = [f"partial {index + 1}" for index in range(rounds)]
        self.opening_delta = opening_delta
        self.hold_final = hold_final
        self.calls = 0
        self.legacy_calls = 0
        self.cancelled_requests: list[str] = []
        self.requests: list[object] = []

    async def process_formal_live_voice_stream_impl(
        self, request, inputs
    ) -> AsyncIterator[AgentResponseChunk]:
        index = self.calls
        self.calls += 1
        self.requests.append(request)
        self.entered[index].set()
        try:
            if self.opening_delta:
                yield AgentResponseChunk(
                    request_id=request.request_id,
                    channel_id=request.channel_id,
                    payload={
                        "event_type": "chat.delta",
                        "content": self.deltas[index],
                    },
                    is_complete=False,
                )
                self.delta_emitted[index].set()
            await self.gates[index].wait()
            if self.opening_delta:
                yield AgentResponseChunk(
                    request_id=request.request_id,
                    channel_id=request.channel_id,
                    payload={
                        "event_type": "chat.delta",
                        "content": f"{self.deltas[index]} tail",
                    },
                    is_complete=False,
                )
            yield AgentResponseChunk(
                request_id=request.request_id,
                channel_id=request.channel_id,
                payload={
                    "event_type": "chat.final",
                    "content": self.finals[index],
                },
                is_complete=True,
            )
            if self.hold_final:
                await self.tails[index].wait()
        except asyncio.CancelledError:
            self.cancelled_requests.append(request.request_id)
            raise

    async def process_message_stream_impl(self, *_args, **_kwargs):
        self.legacy_calls += 1
        raise AssertionError("legacy Chat stream must not run")
        yield  # pragma: no cover


class CancelRecordingHarness(JiuWenSwarmRoundHarness):
    """Observes the exact cancellation command a fence is allowed to issue."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cancel_commands: list[CommandEnvelope] = []

    def cancel_round(
        self, handle: HarnessRoundHandle, command: CommandEnvelope
    ) -> RoundCancelResult:
        self.cancel_commands.append(command)
        return super().cancel_round(handle, command)


def build_runtime(
    lower: SequencedFormalAdapter,
    history: RecordingHistoryWriter,
) -> tuple[AgentConversationRuntime, CancelRecordingHarness]:
    harness = CancelRecordingHarness(
        instance_id="generation-interrupt-harness",
        enabled=True,
        max_active_rounds=4,
        id_factory=id_factory(),
    )
    current = AgentConversationRuntime(
        scope(),
        instance_id="generation-interrupt-composition",
        facade=facade(lower),
        enabled=True,
        history_writer=history,
        harness=harness,
    )
    return current, harness


async def open_runtime(current: AgentConversationRuntime) -> None:
    assert await current.start() is True
    await current.open_interaction("interaction-1")


async def submit_turn(
    current: AgentConversationRuntime,
    *,
    index: int,
    supersedes: ResponseRef | None = None,
    text: str = "hello",
):
    return await current.submit_committed_turn(
        request_id=f"request-{index}",
        response_id=f"response-{index}",
        correlation_id=f"correlation-request-{index}",
        commit=commit(
            turn_id=f"turn-{index}",
            commit_id=f"commit-{index}",
            text=text,
        ),
        context=FormalContextSnapshot(scope()),
        supersedes=supersedes,
    )


def response_record(current: AgentConversationRuntime, ref: ResponseRef):
    return next(
        item
        for item in current.snapshot().conversation.conversation.responses
        if item.ref == ref
    )


async def drain_until_generating(
    current: AgentConversationRuntime, ref: ResponseRef
) -> None:
    """Consume progress until CR owns the exact response as GENERATING."""

    for _ in range(8):
        record = next(
            (
                item
                for item in current.snapshot().conversation.conversation.responses
                if item.ref == ref
            ),
            None,
        )
        if record is not None and record.state is ResponseState.GENERATING:
            return
        await asyncio.wait_for(current.next_notification(), timeout=1)
    raise AssertionError("response never reached GENERATING")


async def shutdown(current: AgentConversationRuntime) -> None:
    result = await current.close(timeout_seconds=5)
    assert result.status is AgentConversationShutdownStatus.CLOSED


@pytest.mark.asyncio
async def test_generation_fence_blocks_final_tts_ack_and_history() -> None:
    lower = SequencedFormalAdapter(rounds=1)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    interruption = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert interruption.fence_status is GenerationInterruptionFenceStatus.FENCED
    assert interruption.fence is not None
    assert interruption.fence.interrupted_state is ResponseState.GENERATING
    assert interruption.fence.cancel_requested is True
    assert response_record(current, handle.response_ref).fenced is True

    # The still-running round now tries to deliver its answer.
    lower.gates[0].set()
    await asyncio.sleep(0)
    presented = []
    for _ in range(6):
        try:
            notification = await asyncio.wait_for(
                current.next_notification(), timeout=0.2
            )
        except TimeoutError:
            break
        if notification.presentation_unit is not None:
            presented.append(notification.presentation_unit)
    assert presented == []

    # No fenced UI/TTS effect may remain claimable.
    effects = current.snapshot().conversation.effects
    output = [
        record
        for record in effects
        if record.effect.ref == handle.response_ref
        and record.effect.effect_type in {"ui.render", "audio.enqueue"}
        and record.state.value == "pending"
    ]
    assert output == []
    assert any(
        record.effect.effect_type == "playback.stop"
        and record.effect.ref == handle.response_ref
        for record in effects
    )

    with pytest.raises(Exception) as ack_error:
        await current.acknowledge_presentation(
            PresentationAck(
                ref=handle.response_ref,
                surface=PresentationSurface.TEXT,
                unit_id="agent-final:unknown:0",
                contiguous_cursor=0,
                presented_at="2026-08-23T08:00:00Z",
            )
        )
    assert getattr(ack_error.value, "reason", None) is not None
    assert history.assistant_intents == []
    # The committed turn the speaker already produced stays durable truth.
    assert [entry[0].commit_id for entry in history.users] == ["commit-1"]
    await shutdown(current)


@pytest.mark.asyncio
async def test_fence_invalidates_already_enqueued_output_ack_and_history() -> None:
    """Interrupt after the answer is enqueued but before it is acknowledged."""

    lower = SequencedFormalAdapter(rounds=1, hold_final=True)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)
    lower.gates[0].set()

    unit = None
    for _ in range(12):
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.presentation_unit is not None:
            unit = notification.presentation_unit
            break
    assert unit is not None

    def pending_output():
        return [
            record
            for record in current.snapshot().conversation.effects
            if record.effect.ref == handle.response_ref
            and record.effect.effect_type in {"ui.render", "audio.enqueue"}
            and record.state.value == "pending"
        ]

    # The rendered/TTS effect is genuinely claimable before the interruption.
    assert len(pending_output()) == 1

    interruption = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert interruption.fence_status is GenerationInterruptionFenceStatus.FENCED

    # The same effect is now invalidated, so no TTS or UI can still consume it.
    assert pending_output() == []
    invalidated = [
        record
        for record in current.snapshot().conversation.effects
        if record.effect.ref == handle.response_ref
        and record.effect.effect_type == "ui.render"
        and record.state.value == "invalidated"
    ]
    assert len(invalidated) == 1
    assert invalidated[0].invalidated_reason == "generation_interrupt"

    # An exact, otherwise valid ACK for that unit is refused, so no assistant
    # history row can be projected from the interrupted answer.
    with pytest.raises(Exception) as stale:
        await current.acknowledge_presentation(
            PresentationAck(
                ref=handle.response_ref,
                surface=PresentationSurface.TEXT,
                unit_id=unit.unit_id,
                contiguous_cursor=unit.seq,
                presented_at="2026-08-23T08:00:00Z",
            )
        )
    assert getattr(stale.value, "reason", None) == "STALE_RESPONSE_OUTPUT"
    assert history.assistant_intents == []

    lower.tails[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_fence_stops_further_agent_tokens_from_reaching_the_consumer() -> None:
    lower = SequencedFormalAdapter(rounds=1, opening_delta=True, hold_final=True)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await asyncio.wait_for(lower.delta_emitted[0].wait(), timeout=1)

    # Drain until the first partial token has genuinely reached the consumer.
    opening = None
    for _ in range(12):
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.agent_event is not None and notification.agent_event.text:
            opening = notification.agent_event
            break
    assert opening is not None
    assert opening.text == "partial 1"

    interruption = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert interruption.fence_status is GenerationInterruptionFenceStatus.FENCED

    lower.gates[0].set()
    delivered_text = []
    for _ in range(10):
        try:
            notification = await asyncio.wait_for(
                current.next_notification(), timeout=0.2
            )
        except TimeoutError:
            break
        if notification.agent_event is not None and notification.agent_event.text:
            delivered_text.append(notification.agent_event.text)
    assert delivered_text == []

    lower.tails[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_replaced_round_without_round_cancel_still_delivers_no_token() -> None:
    """A round that CR replaced keeps running; the fence alone must silence it.

    No ``round.cancel`` is issued here, so the still-live predecessor really
    does emit more output.  Only the generation fence can keep that output away
    from the consumer, which makes this the exact case a missing fence breaks.
    """

    lower = SequencedFormalAdapter(rounds=2, opening_delta=True, hold_final=True)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    first = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await asyncio.wait_for(lower.delta_emitted[0].wait(), timeout=1)
    opening = None
    for _ in range(12):
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.agent_event is not None and notification.agent_event.text:
            opening = notification
            break
    assert opening is not None
    assert opening.response_ref == first.response_ref
    assert opening.agent_event is not None
    assert opening.agent_event.text == "partial 1"

    # Replacement without an explicit fence request: CR alone supersedes it.
    second = await submit_turn(current, index=2)
    assert second.superseded is None
    assert harness.cancel_commands == []
    assert response_record(current, first.response_ref).fenced is True

    lower.gates[0].set()
    predecessor_text = []
    predecessor_notices = 0
    for _ in range(16):
        try:
            notification = await asyncio.wait_for(
                current.next_notification(), timeout=0.2
            )
        except TimeoutError:
            break
        if notification.response_ref != first.response_ref:
            continue
        if notification.agent_event is not None and notification.agent_event.text:
            predecessor_text.append(notification.agent_event.text)
        if notification.error_reason == "STALE_RESPONSE_OUTPUT":
            predecessor_notices += 1
    assert predecessor_text == []
    assert predecessor_notices == 1
    assert history.assistant_intents == []

    lower.gates[1].set()
    lower.tails[0].set()
    lower.tails[1].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_generation_fence_issues_round_cancel_and_never_task_cancel() -> None:
    lower = SequencedFormalAdapter(rounds=1)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    interruption = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert interruption.cancel_scope == CancelScope.ROUND_CANCEL.value
    assert interruption.round_cancel is not None
    assert interruption.round_cancel.accepted is True
    assert interruption.round_id == handle.round_id

    assert len(harness.cancel_commands) == 1
    issued = harness.cancel_commands[0]
    assert issued.command_type == CancelScope.ROUND_CANCEL.value
    assert issued.command_type != CancelScope.TASK_CANCEL.value
    assert issued.target_ref.kind is IdentityKind.ROUND
    assert issued.target_ref.id == handle.round_id
    assert issued.required_capabilities == (CancelScope.ROUND_CANCEL.value,)
    assert issued.origin.turn_id == "turn-1"

    lower.gates[0].set()
    await asyncio.sleep(0)
    assert current.snapshot().harness.cancel_effects == 1
    await shutdown(current)


@pytest.mark.asyncio
async def test_replacement_turn_supersedes_exact_round_and_answers() -> None:
    lower = SequencedFormalAdapter(rounds=2)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    first = await submit_turn(current, index=1, text="what is the weather")
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, first.response_ref)

    second = await submit_turn(
        current,
        index=2,
        supersedes=first.response_ref,
        text="actually tell me a joke",
    )
    assert second.superseded is not None
    assert second.superseded.fence_status is GenerationInterruptionFenceStatus.FENCED
    assert second.superseded.response_ref == first.response_ref
    assert second.superseded.cancel_scope == CancelScope.ROUND_CANCEL.value
    assert second.superseded.round_cancel is not None
    assert second.superseded.round_cancel.accepted is True
    assert (
        second.response_ref.response_generation
        > first.response_ref.response_generation
    )
    assert response_record(current, first.response_ref).fenced is True

    lower.gates[0].set()
    await asyncio.wait_for(lower.entered[1].wait(), timeout=1)
    lower.gates[1].set()

    unit = None
    for _ in range(12):
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.presentation_unit is not None:
            assert notification.response_ref == second.response_ref
            unit = notification.presentation_unit
            break
    assert unit is not None

    accepted = await current.acknowledge_presentation(
        PresentationAck(
            ref=second.response_ref,
            surface=PresentationSurface.TEXT,
            unit_id=unit.unit_id,
            contiguous_cursor=unit.seq,
            presented_at="2026-08-23T08:00:01Z",
        )
    )
    assert accepted.accepted is True
    assert accepted.history_records_written == 1
    assert len(history.assistant_intents) == 1
    assert (
        history.assistant_intents[0][0].contents[0].content_utf8
        == b"formal answer 2"
    )
    assert [entry[0].commit_id for entry in history.users] == [
        "commit-1",
        "commit-2",
    ]
    await shutdown(current)


@pytest.mark.asyncio
async def test_settled_generation_still_admits_the_speech_as_next_turn() -> None:
    lower = SequencedFormalAdapter(rounds=2)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    first = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    lower.gates[0].set()
    for _ in range(12):
        if (
            response_record(current, first.response_ref).state
            is ResponseState.TERMINAL
        ):
            break
        await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (
        response_record(current, first.response_ref).state is ResponseState.TERMINAL
    )

    second = await submit_turn(current, index=2, supersedes=first.response_ref)
    assert second.superseded is not None
    assert (
        second.superseded.fence_status
        is GenerationInterruptionFenceStatus.ALREADY_SETTLED
    )
    assert second.superseded.fence_reason == "RESPONSE_ALREADY_TERMINAL"
    # A settled target has no fence to accompany, so nothing may be cancelled.
    assert second.superseded.round_cancel is None
    assert second.superseded.round_cancel_reason == "GENERATION_ALREADY_SETTLED"
    assert harness.cancel_commands == []
    assert current.snapshot().harness.cancel_effects == 0

    await asyncio.wait_for(lower.entered[1].wait(), timeout=1)
    lower.gates[1].set()
    delivered = False
    for _ in range(12):
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.presentation_unit is not None:
            assert notification.response_ref == second.response_ref
            delivered = True
            break
    assert delivered is True
    await shutdown(current)


@pytest.mark.asyncio
async def test_task_notification_still_speaks_after_a_generation_interruption() -> None:
    """A fenced conversational round must not silence background Task truth."""

    lower = SequencedFormalAdapter(rounds=1, hold_final=True)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1, text="帮我在后台创建行程")
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    interruption = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert interruption.fence_status is GenerationInterruptionFenceStatus.FENCED
    assert interruption.cancel_scope == CancelScope.ROUND_CANCEL.value

    notification = await current.present_authoritative_text(
        request_id="task-notification-after-interrupt",
        response_id="response-task-notification-after-interrupt",
        correlation_id="correlation-task-notification-after-interrupt",
        commit=commit(
            turn_id="turn-task-notification",
            commit_id="commit-task-notification",
            text="Task notification for task-1",
        ),
        text="后台任务已完成，结果已经准备好。",
        channel_id="web",
        _persist_user_history=False,
        _source_provenance="server.task_notification",
    )
    unit = None
    for _ in range(12):
        published = await asyncio.wait_for(current.next_notification(), timeout=1)
        if (
            published.presentation_unit is not None
            and published.response_ref == notification.response_ref
        ):
            unit = published.presentation_unit
            break
    assert unit is not None

    accepted = await current.acknowledge_presentation(
        PresentationAck(
            ref=notification.response_ref,
            surface=PresentationSurface.TEXT,
            unit_id=unit.unit_id,
            contiguous_cursor=unit.seq,
            presented_at="2026-08-23T08:00:02Z",
        )
    )
    assert accepted.accepted is True
    assert accepted.history_records_written == 1
    assert [
        item[0].contents[0].content_utf8 for item in history.assistant_intents
    ] == ["后台任务已完成，结果已经准备好。".encode("utf-8")]
    # Only the conversational round was cancelled.
    assert len(harness.cancel_commands) == 1
    assert harness.cancel_commands[0].command_type == CancelScope.ROUND_CANCEL.value

    lower.tails[0].set()
    lower.gates[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_stale_target_cancels_nothing_and_leaves_its_successor_running() -> None:
    """Speech aimed at an already replaced answer must not touch any round.

    The predecessor is already fenced by CR, and the successor is the answer the
    speaker is actually waiting for.  Cancelling either one would be a cancel
    nobody asked for, so a stale target is admitted as an ordinary next turn
    with zero cancellation effect.
    """

    lower = SequencedFormalAdapter(rounds=2, hold_final=True)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    first = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, first.response_ref)

    # No supersedes: CR replaces the predecessor on its own, so the first
    # response becomes stale rather than settled.
    second = await submit_turn(current, index=2)
    assert second.superseded is None
    assert response_record(current, first.response_ref).fenced is True
    assert response_record(current, first.response_ref).state is not ResponseState.TERMINAL

    interruption = await current.interrupt_generation(
        action_id="interrupt-stale", ref=first.response_ref
    )
    assert (
        interruption.fence_status is GenerationInterruptionFenceStatus.ALREADY_SETTLED
    )
    assert interruption.fence_reason == "STALE_RESPONSE_OUTPUT"
    assert interruption.fence is None
    assert interruption.round_cancel is None
    assert interruption.round_cancel_reason == "GENERATION_ALREADY_SETTLED"
    assert harness.cancel_commands == []
    assert current.snapshot().harness.cancel_effects == 0

    # The successor was never cancelled and still answers normally.
    await asyncio.wait_for(lower.entered[1].wait(), timeout=1)
    lower.gates[1].set()
    unit = None
    for _ in range(12):
        published = await asyncio.wait_for(current.next_notification(), timeout=1)
        if (
            published.presentation_unit is not None
            and published.response_ref == second.response_ref
        ):
            unit = published.presentation_unit
            break
    assert unit is not None
    accepted = await current.acknowledge_presentation(
        PresentationAck(
            ref=second.response_ref,
            surface=PresentationSurface.TEXT,
            unit_id=unit.unit_id,
            contiguous_cursor=unit.seq,
            presented_at="2026-08-23T08:00:03Z",
        )
    )
    assert accepted.accepted is True
    assert lower.cancelled_requests == []

    lower.gates[0].set()
    lower.tails[0].set()
    lower.tails[1].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_interruption_replay_is_exact_and_conflicting_target_is_refused() -> None:
    lower = SequencedFormalAdapter(rounds=1)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    first = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    replay = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert replay.replayed is True
    assert replay.fence_status is first.fence_status
    assert replay.round_id == first.round_id
    assert len(harness.cancel_commands) == 1
    assert current.snapshot().harness.cancel_effects == 1

    with pytest.raises(AgentConversationRuntimeViolation) as conflict:
        await current.interrupt_generation(
            action_id="interrupt-1",
            ref=ResponseRef("interaction-1", "response-other", 99),
        )
    assert conflict.value.reason == "GENERATION_INTERRUPT_ACTION_CONFLICT"
    lower.gates[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_exit_owns_the_interaction_and_refuses_a_later_interruption() -> None:
    lower = SequencedFormalAdapter(rounds=1)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    await current._cr.transition_interaction(
        "interaction-1", InteractionState.CLOSING
    )
    with pytest.raises(AgentConversationRuntimeViolation) as closed:
        await current.interrupt_generation(
            action_id="interrupt-after-exit", ref=handle.response_ref
        )
    assert closed.value.reason == "INTERACTION_NOT_OPEN"
    assert harness.cancel_commands == []
    lower.gates[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_supersedes_must_name_a_real_prior_response_of_this_interaction() -> None:
    lower = SequencedFormalAdapter(rounds=1)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    with pytest.raises(AgentConversationRuntimeViolation) as mismatch:
        await submit_turn(
            current,
            index=1,
            supersedes=ResponseRef("interaction-other", "response-0", 0),
        )
    assert mismatch.value.reason == "SUPERSEDED_RESPONSE_INTERACTION_MISMATCH"

    with pytest.raises(AgentConversationRuntimeViolation) as self_ref:
        await submit_turn(
            current,
            index=1,
            supersedes=ResponseRef("interaction-1", "response-1", 0),
        )
    assert self_ref.value.reason == "SUPERSEDED_RESPONSE_SELF_REFERENCE"

    with pytest.raises(Exception) as unknown:
        await submit_turn(
            current,
            index=1,
            supersedes=ResponseRef("interaction-1", "response-unknown", 0),
        )
    assert getattr(unknown.value, "reason", None) == "STALE_RESPONSE_REFERENCE"
    assert lower.calls == 0
    await shutdown(current)


@pytest.mark.asyncio
async def test_interruption_replay_ledger_stays_bounded() -> None:
    """One turn can carry one interruption, so the ledger cannot grow freely."""

    loop = ConversationRuntimeLoop(scope())
    assert await loop.start() is True
    await loop.open_interaction("interaction-1")
    attempts = _MAX_RETAINED_GENERATION_INTERRUPTS + 40
    for index in range(attempts):
        with pytest.raises(ConversationRuntimeLoopViolation) as unknown:
            await loop.interrupt_generation(
                f"action-{index}", ResponseRef("interaction-1", f"response-{index}", index)
            )
        assert unknown.value.reason == "STALE_RESPONSE_REFERENCE"
    # The private ledger is asserted directly: it has no product surface, and
    # an unbounded one is exactly the defect this guards.
    assert (
        len(loop._retained_generation_interrupts)
        <= _MAX_RETAINED_GENERATION_INTERRUPTS
    )
    # The most recent action is still replayable.
    with pytest.raises(ConversationRuntimeLoopViolation):
        await loop.interrupt_generation(
            f"action-{attempts - 1}",
            ResponseRef("interaction-1", f"response-{attempts - 1}", attempts - 1),
        )
    await loop.close()


@pytest.mark.asyncio
async def test_bounded_ledger_skips_a_pending_action_without_exceeding_its_bound() -> None:
    """An unresolved oldest action must not let settled ones grow past the bound.

    Eviction has two obligations that have to hold together: never destroy an
    action whose future is still pending, and never exceed the bound. Stopping
    the sweep at the first pending entry satisfies only the first, so the
    ledger is asserted here on both at once.
    """

    loop = ConversationRuntimeLoop(scope())
    running = asyncio.get_running_loop()
    ref = ResponseRef("interaction-1", "response-pending", 0)
    pending_future: asyncio.Future[GenerationInterruptionResult] = running.create_future()
    loop._retained_generation_interrupts["pending-oldest"] = (
        _RetainedGenerationInterrupt(ref=ref, future=pending_future)
    )
    for index in range(_MAX_RETAINED_GENERATION_INTERRUPTS + 8):
        action_id = f"settled-{index}"
        settled_ref = ResponseRef("interaction-1", f"response-{index}", index + 1)
        loop._retained_generation_interrupts[action_id] = _RetainedGenerationInterrupt(
            ref=settled_ref,
            result=GenerationInterruptionResult(
                action_id=action_id,
                ref=settled_ref,
                applied=True,
                replayed=False,
                interrupted_state=ResponseState.GENERATING,
                cancel_requested=True,
                effect_ids=(),
            ),
        )

    loop._evict_retained_generation_interrupts()

    assert pending_future.done() is False
    assert "pending-oldest" in loop._retained_generation_interrupts
    assert (
        len(loop._retained_generation_interrupts)
        <= _MAX_RETAINED_GENERATION_INTERRUPTS
    )
    # The retained order keeps its oldest-first shape around the skipped entry.
    assert next(iter(loop._retained_generation_interrupts)) == "pending-oldest"
    pending_future.cancel()


@pytest.mark.asyncio
async def test_generation_interrupt_identity_capacity_includes_pending_actions() -> None:
    """Pending and settled actions share one total replay-identity bound."""

    loop = ConversationRuntimeLoop(
        scope(), control_capacity=_MAX_RETAINED_GENERATION_INTERRUPTS + 1
    )
    assert await loop.start() is True
    await loop.open_interaction("interaction-1")
    pending = [
        loop.post_generation_interrupt(
            f"pending-{index}",
            ResponseRef("interaction-1", f"pending-response-{index}", index),
        )
        for index in range(_MAX_RETAINED_GENERATION_INTERRUPTS)
    ]
    try:
        assert len(loop._retained_generation_interrupts) == (
            _MAX_RETAINED_GENERATION_INTERRUPTS
        )
        for index, future in enumerate(pending):
            assert (
                loop._retained_generation_interrupts[f"pending-{index}"].future
                is future
            )
        with pytest.raises(ConversationRuntimeLoopViolation) as full:
            loop.post_generation_interrupt(
                "pending-over-capacity",
                ResponseRef("interaction-1", "pending-response-over-capacity", 0),
            )
        assert full.value.reason == "GENERATION_INTERRUPT_LEDGER_FULL"
        assert len(loop._retained_generation_interrupts) == (
            _MAX_RETAINED_GENERATION_INTERRUPTS
        )
    finally:
        await asyncio.gather(*pending, return_exceptions=True)
        await loop.close()


@pytest.mark.asyncio
async def test_interrupt_after_barge_in_still_stops_the_running_round() -> None:
    """A target already fenced by barge-in still needs its round cancelled.

    Barge-in closes AUDIO and cancels the response, but it never touches the
    Harness: the Agent round keeps generating. When speech then arrives, CR has
    no new effect to apply -- the fence reports ``applied=False`` -- yet the
    round is exactly what the speaker is asking to stop. The cancellation is
    therefore tied to *having a fenceable live target*, not to this call being
    the one that produced the fencing effects.
    """

    lower = SequencedFormalAdapter(rounds=1, hold_final=True)
    history = RecordingHistoryWriter()
    current, harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    barge = await current.barge_in(
        "barge-1", handle.response_ref, cancel_response=True
    )
    assert barge.applied is True
    assert harness.cancel_commands == [], "barge-in must not cancel the round"
    assert current.snapshot().harness.cancel_effects == 0

    interruption = await current.interrupt_generation(
        action_id="interrupt-after-barge", ref=handle.response_ref
    )
    # The target is still the latest live response, so this is a real fence
    # application even though barge-in already produced its effects.
    assert interruption.fence_status is GenerationInterruptionFenceStatus.FENCED
    assert interruption.fence is not None
    assert interruption.fence.applied is False
    assert interruption.fence.cancel_requested is False
    # The round the speaker asked to stop is stopped exactly once.
    assert interruption.round_cancel is not None
    assert interruption.round_cancel.accepted is True
    assert interruption.cancel_scope == CancelScope.ROUND_CANCEL.value
    assert len(harness.cancel_commands) == 1
    assert harness.cancel_commands[0].command_type == CancelScope.ROUND_CANCEL.value
    assert current.snapshot().harness.cancel_effects == 1

    lower.gates[0].set()
    lower.tails[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_interruption_seam_exposes_no_cancellation_scope_argument() -> None:
    """The absence of a scope parameter is the guarantee, so assert it directly.

    Signatures are checked rather than source text: a source-text assertion
    reads whatever `linecache` has, which is not a property of the code under
    test. The scope the runtime actually issues is asserted by
    `test_generation_fence_issues_round_cancel_and_never_task_cancel`, and the
    product handler refusing a client-supplied scope is asserted by
    `test_product_p2_generation_interrupt_reaches_the_runtime_round`.
    """

    import inspect

    from jiuwenswarm.server.live_voice.product_composition_registry import (
        AgentServerProductCompositionRegistry,
    )
    from jiuwenswarm.server.live_voice.product_p2_interaction_adapter import (
        P2ActivationLease,
    )

    forbidden = {"scope", "cancel_scope", "cancellation_scope", "cancel_response"}
    for owner in (
        AgentConversationRuntime.interrupt_generation,
        P2ActivationLease.interrupt_generation,
        AgentServerProductCompositionRegistry.handle_p2_interrupt_generation,
    ):
        names = set(inspect.signature(owner).parameters)
        assert not forbidden & names, f"{owner.__qualname__} exposes a cancellation scope"


@pytest.mark.asyncio
async def test_failed_supersede_fence_leaves_no_replacement_turn() -> None:
    """The fence precedes the replacement commit, so a failed fence commits nothing.

    Committing first and fencing afterwards would leave a committed turn for a
    round that was never fenced -- two live responses for one interaction, which
    is exactly the state the ordering exists to prevent.  This asserts the
    ordering through its only externally visible consequence: CR holds no turn
    for a replacement whose fence failed.
    """

    lower = SequencedFormalAdapter(rounds=1)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    first = await submit_turn(current, index=1)
    await drain_until_generating(current, first.response_ref)

    with pytest.raises(Exception) as unfenceable:
        await submit_turn(
            current,
            index=2,
            supersedes=ResponseRef("interaction-1", "response-unknown", 0),
        )
    assert getattr(unfenceable.value, "reason", None) == "STALE_RESPONSE_REFERENCE"

    turns = current.snapshot().conversation.conversation.turns
    assert [record.turn_id for record in turns] == ["turn-1"]
    assert all(record.turn_id != "turn-2" for record in turns)
    lower.gates[0].set()
    await shutdown(current)


@pytest.mark.asyncio
async def test_fence_drops_a_presentation_already_waiting_in_the_delivery_queue() -> None:
    """A queued notice is output too: a fenced response must present nothing.

    Invalidating the effect is not enough on its own.  A presentation that was
    enqueued before the fence is still sitting in the delivery queue, and every
    authenticated consumer of that queue would render or speak it.  The Web
    client happens to refuse it by response identity, but that refusal is the
    client's; this boundary has to hold for any consumer.
    """

    lower = SequencedFormalAdapter(rounds=1, hold_final=True)
    history = RecordingHistoryWriter()
    current, _harness = build_runtime(lower, history)
    await open_runtime(current)

    handle = await submit_turn(current, index=1)
    await asyncio.wait_for(lower.entered[0].wait(), timeout=1)
    await drain_until_generating(current, handle.response_ref)

    # Drain everything produced before the answer, so what queues next is the
    # presentation itself.
    while current.snapshot().queued_notifications > 0:
        await asyncio.wait_for(current.next_notification(), timeout=1)

    # Release the answer but never consume it: it stays queued for delivery.
    lower.gates[0].set()
    for _ in range(200):
        if current.snapshot().queued_notifications > 0:
            break
        await asyncio.sleep(0)
    assert current.snapshot().queued_notifications > 0

    interruption = await current.interrupt_generation(
        action_id="interrupt-1", ref=handle.response_ref
    )
    assert interruption.fence_status is GenerationInterruptionFenceStatus.FENCED

    delivered = []
    while current.snapshot().queued_notifications > 0:
        delivered.append(await asyncio.wait_for(current.next_notification(), timeout=1))
    presented = [
        notification
        for notification in delivered
        if notification.presentation_unit is not None
        and notification.response_ref == handle.response_ref
    ]
    assert presented == []
    assert history.assistant_intents == []

    lower.tails[0].set()
    await shutdown(current)
