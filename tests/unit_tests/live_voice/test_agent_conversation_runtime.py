# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentResponseChunk
from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    ResponseRef,
    ScopeRef,
    TurnCommit,
    WorkProgressEventV2,
)
from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    AgentConversationNotification,
    AgentConversationRuntime,
    AgentConversationRuntimeViolation,
    AgentConversationShutdownStatus,
)
from jiuwenswarm.server.live_voice.agent_bridge_runtime import (
    AgentBridgeRuntime,
    AgentBridgeRuntimeViolation,
)
from jiuwenswarm.server.live_voice.conversation_runtime_loop import (
    ConversationRuntimeLoopViolation,
)
from jiuwenswarm.server.live_voice.conversation_runtime import (
    ConversationRuntimeViolation,
)
from jiuwenswarm.server.live_voice.jiuwenswarm_round_harness import (
    HarnessReservationState,
    HarnessRoundBinding,
    HarnessRoundViolation,
    JiuWenSwarmRoundHarness,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
)
from jiuwenswarm.server.runtime.agent_adapter.formal_live_voice import (
    FormalContextSnapshot,
)
from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm


def scope(*, session_id: str = "session-formal") -> ScopeRef:
    return ScopeRef("subject-1", "project-1", session_id, Assurance.AUTHENTICATED)


def commit(
    *,
    turn_id: str = "turn-1",
    commit_id: str = "commit-1",
    interaction_id: str = "interaction-1",
    text: str = "hello",
) -> TurnCommit:
    return TurnCommit.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "commit_id": commit_id,
            "turn_id": turn_id,
            "interaction_id": interaction_id,
            "text": text,
            "hypothesis_provenance": {"provider": "test.sr"},
            "scope": scope().to_dict(),
            "context_refs": [],
            "committed_at": "2026-08-05T08:00:00Z",
        }
    )


class LowerFormalAdapter:
    _is_session_scoped_adapter = False

    def __init__(
        self,
        *,
        final: str | None = "formal answer",
        release: asyncio.Event | None = None,
        terminal_release: asyncio.Event | None = None,
        cancel_cleanup_release: asyncio.Event | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.final = final
        self.release = release
        self.terminal_release = terminal_release
        self.cancel_cleanup_release = cancel_cleanup_release
        self.error = error
        self.calls = 0
        self.legacy_calls = 0
        self.started = asyncio.Event()
        self.requests = []
        self.inputs = []

    async def process_formal_live_voice_stream_impl(
        self, request, inputs
    ) -> AsyncIterator[AgentResponseChunk]:
        self.calls += 1
        self.requests.append(request)
        self.inputs.append(inputs)
        self.started.set()
        try:
            if self.release is not None:
                await self.release.wait()
            if self.error is not None:
                raise self.error
            if self.final is not None:
                yield AgentResponseChunk(
                    request_id=request.request_id,
                    channel_id=request.channel_id,
                    payload={"event_type": "chat.final", "content": self.final},
                    is_complete=True,
                )
            if self.terminal_release is not None:
                await self.terminal_release.wait()
        except asyncio.CancelledError:
            if self.cancel_cleanup_release is not None:
                await self.cancel_cleanup_release.wait()
            raise

    async def process_message_stream_impl(self, *_args, **_kwargs):
        self.legacy_calls += 1
        raise AssertionError("legacy Chat stream must not run")
        yield  # pragma: no cover


class RecordingHistoryWriter:
    def __init__(self, *, fail_assistant_once: bool = False) -> None:
        self.users = []
        self.assistant_intents = []
        self.fail_assistant_once = fail_assistant_once

    async def persist_user(self, current_commit, *, channel_id: str) -> bool:
        self.users.append((current_commit, channel_id))
        return True

    async def persist_assistant(
        self, intent, *, session_id: str, channel_id: str
    ) -> tuple[bool, ...]:
        self.assistant_intents.append((intent, session_id, channel_id))
        if self.fail_assistant_once:
            self.fail_assistant_once = False
            raise OSError("history unavailable")
        return tuple(True for _ in intent.contents)


class BlockingHistoryWriter(RecordingHistoryWriter):
    def __init__(self) -> None:
        super().__init__()
        self.assistant_started = asyncio.Event()
        self.assistant_release = asyncio.Event()

    async def persist_assistant(
        self, intent, *, session_id: str, channel_id: str
    ) -> tuple[bool, ...]:
        self.assistant_started.set()
        await self.assistant_release.wait()
        return await super().persist_assistant(
            intent, session_id=session_id, channel_id=channel_id
        )


class AlwaysFailAssistantHistoryWriter(RecordingHistoryWriter):
    async def persist_assistant(
        self, intent, *, session_id: str, channel_id: str
    ) -> tuple[bool, ...]:
        self.assistant_intents.append((intent, session_id, channel_id))
        raise OSError("history remains unavailable")


def facade(lower: LowerFormalAdapter) -> JiuWenSwarm:
    real = JiuWenSwarm()
    real._adapter = lower  # type: ignore[assignment]
    return real


def id_factory():
    counter = 0

    def allocate() -> str:
        nonlocal counter
        counter += 1
        return f"opaque-{counter}"

    return allocate


def runtime(
    lower: LowerFormalAdapter,
    history: RecordingHistoryWriter,
    *,
    enabled: bool = True,
    max_active_rounds: int = 4,
    max_requests: int = 256,
    notification_capacity: int = 64,
    bridge: AgentBridgeRuntime | None = None,
) -> AgentConversationRuntime:
    harness = JiuWenSwarmRoundHarness(
        instance_id="real-harness-1",
        enabled=enabled,
        max_active_rounds=max_active_rounds,
        id_factory=id_factory(),
    )
    return AgentConversationRuntime(
        scope(),
        instance_id="composition-1",
        facade=facade(lower),
        enabled=enabled,
        max_requests=max_requests,
        notification_capacity=notification_capacity,
        history_writer=history,
        harness=harness,
        bridge=bridge,
    )


async def prepare(
    current: AgentConversationRuntime, turn: TurnCommit | None = None
) -> TurnCommit:
    selected = turn or commit()
    await current.start()
    await current.open_interaction(selected.interaction_id)
    await current.start_turn(selected.interaction_id, selected.turn_id)
    await current.commit_turn(selected)
    return selected


async def dispatch(
    current: AgentConversationRuntime,
    selected: TurnCommit,
    *,
    request_id: str = "request-1",
    response_id: str = "response-1",
):
    return await current.dispatch_committed_turn(
        request_id=request_id,
        response_id=response_id,
        correlation_id=f"correlation-{request_id}",
        commit=selected,
        context=FormalContextSnapshot(selected.scope),
    )


def cancel_command(
    handle,
    selected: TurnCommit,
    *,
    command_id: str,
    request_id: str | None = None,
    target_round_id: str | None = None,
    current_scope: ScopeRef | None = None,
) -> CommandEnvelope:
    return CommandEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "request_id": request_id or handle.request_id,
            "command_id": command_id,
            "command_type": "round.cancel",
            "issued_at": "2026-08-05T08:00:01Z",
            "scope": (current_scope or selected.scope).to_dict(),
            "correlation_id": f"correlation-{handle.request_id}",
            "causation_id": None,
            "origin": {
                "kind": "committed_turn",
                "turn_id": selected.turn_id,
                "commit_id": selected.commit_id,
            },
            "target_ref": {
                "kind": "round",
                "id": target_round_id or handle.round_id,
            },
            "context_refs": [],
            "required_capabilities": ["round.cancel"],
            "payload": {},
            "extensions": {},
        }
    )


@pytest.mark.asyncio
async def test_real_facade_round_truth_reaches_cr_and_text_ack_history() -> None:
    terminal_release = asyncio.Event()
    lower = LowerFormalAdapter(terminal_release=terminal_release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)

    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(3)
    ]
    progress = [item for item in notifications if item.progress_event is not None]
    assert [
        WorkProgressEventV2.from_dict(item.progress_event.payload).state.value
        for item in progress
    ] == ["accepted", "running"]
    assert all(item.source_event.producer.authority == "harness" for item in progress)
    final = next(item for item in notifications if item.presentation_unit is not None)
    assert final.presentation_unit is not None
    assert lower.calls == 1
    assert lower.legacy_calls == 0
    assert lower.requests[0].session_id.startswith("lv-formal-")
    assert lower.inputs[0]["enable_memory"] is False

    before_ack = current.snapshot()
    response = next(
        item
        for item in before_ack.conversation.conversation.responses
        if item.ref == handle.response_ref
    )
    assert response.state.value == "generating"
    assert not history.assistant_intents

    ack = PresentationAck(
        ref=handle.response_ref,
        surface=PresentationSurface.TEXT,
        unit_id=final.presentation_unit.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-05T08:00:02Z",
    )
    result = await current.acknowledge_presentation(ack)
    assert result.accepted is True
    assert result.history_records_written == 1
    assert history.assistant_intents[0][0].contents[0].content_utf8 == b"formal answer"
    replay = await current.acknowledge_presentation(ack)
    assert replay.replayed is True
    assert len(history.assistant_intents) == 1
    terminal_release.set()
    terminal = await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (
        WorkProgressEventV2.from_dict(terminal.progress_event.payload).state.value
        == "terminal"
    )
    response = next(
        item
        for item in current.snapshot().conversation.conversation.responses
        if item.ref == handle.response_ref
    )
    assert response.state.value == "terminal"
    assert response.outcome.value == "completed"
    await asyncio.wait_for(history_wait(history), timeout=1)
    assert len(history.users) == 1
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


async def history_wait(history: RecordingHistoryWriter) -> None:
    while not history.users:
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_source_terminal_permanently_invalidates_unacked_final() -> None:
    lower = LowerFormalAdapter()
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(4)
    ]
    final = next(item for item in notifications if item.presentation_unit is not None)
    response = next(
        item
        for item in current.snapshot().conversation.conversation.responses
        if item.ref == handle.response_ref
    )
    assert response.state.value == "terminal"
    assert response.fenced is True
    with pytest.raises(ConversationRuntimeLoopViolation) as stale:
        await current.acknowledge_presentation(
            PresentationAck(
                ref=handle.response_ref,
                surface=PresentationSurface.TEXT,
                unit_id=final.presentation_unit.unit_id,
                contiguous_cursor=0,
                presented_at="2026-08-05T08:00:03Z",
            )
        )
    assert stale.value.reason == "STALE_RESPONSE_OUTPUT"
    assert not history.assistant_intents
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


async def call_wait(lower: LowerFormalAdapter, expected: int) -> None:
    while lower.calls < expected:
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_exact_cancel_rejects_wrong_bindings_and_ack_is_not_terminal() -> None:
    release = asyncio.Event()
    lower = LowerFormalAdapter(final=None, release=release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)

    wrong_scope = scope(session_id="other-session")
    rejected = await current.close_interaction(
        cancel_command(
            handle,
            selected,
            command_id="cancel-wrong-scope",
            current_scope=wrong_scope,
        )
    )
    assert rejected.accepted is False
    assert rejected.reason == "ROUND_CANCEL_SCOPE_MISMATCH"
    wrong_request = await current.close_interaction(
        cancel_command(
            handle,
            selected,
            command_id="cancel-wrong-request",
            request_id="other-request",
        )
    )
    assert wrong_request.accepted is False
    with pytest.raises(AgentConversationRuntimeViolation) as wrong_round:
        await current.close_interaction(
            cancel_command(
                handle,
                selected,
                command_id="cancel-wrong-round",
                target_round_id="round-not-owned",
            )
        )
    assert wrong_round.value.reason == "ROUND_NOT_FOUND"
    assert current.snapshot().harness.cancel_effects == 0

    command = cancel_command(handle, selected, command_id="cancel-exact")
    accepted = await current.close_interaction(command)
    assert accepted.accepted is True
    assert accepted.terminal_observed is False
    assert current.snapshot().harness.cancel_effects == 1
    second_command = await current.close_interaction(
        cancel_command(handle, selected, command_id="cancel-exact-second")
    )
    assert second_command.accepted is False
    assert second_command.reason in {
        "ROUND_CANCEL_ALREADY_REQUESTED",
        "ROUND_ALREADY_TERMINAL",
    }
    assert current.snapshot().harness.cancel_effects == 1
    terminal = await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (
        WorkProgressEventV2.from_dict(terminal.progress_event.payload).outcome.value
        == "cancelled"
    )
    replay = await current.close_interaction(command)
    assert replay.accepted is True
    assert replay.replayed is True
    assert current.snapshot().harness.cancel_effects == 1
    with pytest.raises(HarnessRoundViolation) as idempotency_conflict:
        await current.close_interaction(
            cancel_command(
                handle,
                selected,
                command_id="cancel-exact",
                request_id="changed-request",
            )
        )
    assert idempotency_conflict.value.reason == "IDEMPOTENCY_CONFLICT"
    stale = await current.close_interaction(
        cancel_command(handle, selected, command_id="cancel-after-terminal")
    )
    assert stale.accepted is False
    assert stale.reason == "ROUND_ALREADY_TERMINAL"
    assert current.snapshot().harness.cancel_effects == 1
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_immediate_exact_cancel_cannot_lose_harness_terminal() -> None:
    release = asyncio.Event()
    lower = LowerFormalAdapter(final=None, release=release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)

    accepted = await current.close_interaction(
        cancel_command(handle, selected, command_id="cancel-immediate")
    )
    assert accepted.accepted is True
    terminal_progress = None
    while terminal_progress is None:
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.progress_event is None:
            continue
        progress = WorkProgressEventV2.from_dict(notification.progress_event.payload)
        if progress.state.value == "terminal":
            terminal_progress = progress
    assert terminal_progress.outcome.value == "cancelled"
    assert (await handle.completion).terminal_outcome == terminal_progress.outcome
    assert current.snapshot().harness.active_rounds == ()
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_capacity_one_unsubscribed_round_can_cancel_and_close() -> None:
    lower = LowerFormalAdapter(final=None, release=asyncio.Event())
    real_facade = facade(lower)
    harness = JiuWenSwarmRoundHarness(
        instance_id="capacity-one-cancel-harness",
        output_capacity=1,
        id_factory=id_factory(),
    )
    selected = commit()
    binding = HarnessRoundBinding(
        request_id="request-capacity-one",
        response_id="response-capacity-one",
        correlation_id="correlation-request-capacity-one",
        commit=selected,
    )
    reservation = harness.reserve_round(binding, facade=real_facade)
    assert harness.begin_round_commit(reservation) is True
    handle = harness.commit_round(
        reservation,
        response_ref=ResponseRef(
            interaction_id=selected.interaction_id,
            response_id=binding.response_id,
            response_generation=0,
        ),
        context=FormalContextSnapshot(selected.scope),
        facade=real_facade,
    )

    result = handle.cancel(
        cancel_command(
            SimpleNamespace(
                request_id=binding.request_id,
                round_id=reservation.round_id,
            ),
            selected,
            command_id="cancel-capacity-one",
        )
    )
    assert result.accepted is True

    async def wait_for_terminal():
        while handle.terminal_event is None:
            await asyncio.sleep(0)
        return handle.terminal_event

    terminal = await asyncio.wait_for(wait_for_terminal(), timeout=1)
    assert terminal is not None
    assert terminal.payload == {"state": "terminal", "outcome": "cancelled"}
    assert lower.calls == 0
    assert harness.snapshot().cancel_effects == 1
    assert harness.snapshot().active_rounds == ()
    await asyncio.wait_for(harness.close(), timeout=1)
    assert harness.snapshot().closed is True


@pytest.mark.asyncio
async def test_capacity_one_unsubscribed_composition_reaches_terminal_and_closes() -> (
    None
):
    lower = LowerFormalAdapter()
    history = RecordingHistoryWriter()
    current = runtime(
        lower,
        history,
        max_requests=1,
        notification_capacity=1,
    )
    selected = await prepare(current)
    handle = await dispatch(current, selected)

    await asyncio.wait_for(handle.completion, timeout=1)
    closed = await current.close(timeout_seconds=1)

    assert closed.status is AgentConversationShutdownStatus.CLOSED
    snapshot = current.snapshot()
    response = next(
        item
        for item in snapshot.conversation.conversation.responses
        if item.ref == handle.response_ref
    )
    assert response.state.value == "terminal"
    assert snapshot.queued_notifications == 3
    assert snapshot.queued_observer_notifications == 1
    assert snapshot.queued_critical_notifications == 2
    assert snapshot.notification_observer_capacity == 1
    assert snapshot.notification_critical_capacity == 2
    assert snapshot.dropped_observer_notifications == 1
    assert snapshot.published_notifications == 4
    assert snapshot.published_notifications == (
        snapshot.delivered_notifications
        + snapshot.dropped_observer_notifications
        + snapshot.queued_notifications
    )
    assert snapshot.notification_stream_closed is True
    assert snapshot.critical_notification_invariant_failures == 0

    notifications = [await current.next_notification() for _ in range(3)]
    assert [item.publish_seq for item in notifications] == [1, 2, 3]
    assert notifications[1].presentation_unit is not None
    terminal = WorkProgressEventV2.from_dict(notifications[2].progress_event.payload)
    assert terminal.state.value == "terminal"
    with pytest.raises(AgentConversationRuntimeViolation) as drained:
        await current.next_notification()
    assert drained.value.reason == "NOTIFICATION_STREAM_CLOSED"
    drained_snapshot = current.snapshot()
    assert drained_snapshot.published_notifications == (
        drained_snapshot.delivered_notifications
        + drained_snapshot.dropped_observer_notifications
        + drained_snapshot.queued_notifications
    )
    assert drained_snapshot.last_notification_delivered_seq == 3


@pytest.mark.asyncio
async def test_observer_overflow_is_lossy_but_ordered_critical_notifications_survive() -> (
    None
):
    class BurstFormalAdapter(LowerFormalAdapter):
        async def process_formal_live_voice_stream_impl(
            self, request, inputs
        ) -> AsyncIterator[AgentResponseChunk]:
            self.calls += 1
            self.requests.append(request)
            self.inputs.append(inputs)
            self.started.set()
            for index in range(2):
                yield AgentResponseChunk(
                    request_id=request.request_id,
                    channel_id=request.channel_id,
                    payload={
                        "event_type": "chat.delta",
                        "content": f"partial-{index}",
                    },
                    is_complete=False,
                )
            yield AgentResponseChunk(
                request_id=request.request_id,
                channel_id=request.channel_id,
                payload={"event_type": "chat.final", "content": "formal answer"},
                is_complete=True,
            )

    lower = BurstFormalAdapter()
    current = runtime(
        lower,
        RecordingHistoryWriter(),
        max_requests=1,
        notification_capacity=1,
    )
    selected = await prepare(current)
    handle = await dispatch(current, selected)

    await asyncio.wait_for(handle.completion, timeout=1)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )
    snapshot = current.snapshot()
    assert snapshot.queued_notifications == 3
    assert snapshot.queued_observer_notifications == 1
    assert snapshot.queued_critical_notifications == 2
    assert snapshot.dropped_observer_notifications == 3
    assert snapshot.published_notifications == 6
    assert snapshot.last_notification_publish_seq == 5
    assert snapshot.published_notifications == (
        snapshot.delivered_notifications
        + snapshot.dropped_observer_notifications
        + snapshot.queued_notifications
    )

    retained = [await current.next_notification() for _ in range(3)]
    assert [item.publish_seq for item in retained] == [3, 4, 5]
    assert retained[0].agent_event.event_type == "chat.delta"
    assert retained[0].agent_event.seq == 1
    assert retained[1].presentation_unit is not None
    terminal = WorkProgressEventV2.from_dict(retained[2].progress_event.payload)
    assert terminal.state.value == "terminal"


@pytest.mark.asyncio
async def test_composition_enforces_its_request_bound_with_larger_injected_runtimes() -> (
    None
):
    lower = LowerFormalAdapter()
    bridge = AgentBridgeRuntime(instance_id="larger-injected-bridge", max_requests=2)
    current = runtime(
        lower,
        RecordingHistoryWriter(),
        max_requests=1,
        bridge=bridge,
    )
    first = await prepare(current)
    first_handle = await dispatch(current, first)
    await asyncio.wait_for(first_handle.completion, timeout=1)

    second = commit(
        turn_id="turn-capacity-2",
        commit_id="commit-capacity-2",
        interaction_id="interaction-capacity-2",
        text="second",
    )
    await current.open_interaction(second.interaction_id)
    await current.start_turn(second.interaction_id, second.turn_id)
    await current.commit_turn(second)
    responses_before = current.snapshot().conversation.conversation.responses

    with pytest.raises(AgentConversationRuntimeViolation) as full:
        await dispatch(
            current,
            second,
            request_id="request-capacity-2",
            response_id="response-capacity-2",
        )
    assert full.value.reason == "COMPOSITION_REQUEST_LEDGER_FULL"
    assert current.snapshot().conversation.conversation.responses == responses_before
    assert current.snapshot().retained_admissions == 1
    assert lower.calls == 1
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_close_wakes_empty_notification_waiter_with_stable_closed_error() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    assert await current.start() is True
    waiter = asyncio.create_task(current.next_notification())
    await asyncio.sleep(0)

    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )
    with pytest.raises(AgentConversationRuntimeViolation) as closed:
        await asyncio.wait_for(waiter, timeout=1)
    assert closed.value.reason == "NOTIFICATION_STREAM_CLOSED"
    with pytest.raises(AgentConversationRuntimeViolation) as stable:
        await current.next_notification()
    assert stable.value.reason == "NOTIFICATION_STREAM_CLOSED"


@pytest.mark.asyncio
async def test_cancelled_waiter_consumes_nothing_and_concurrent_waiters_are_unique() -> (
    None
):
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter())
    selected = await prepare(current)
    cancelled = asyncio.create_task(current.next_notification())
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    waiters = [asyncio.create_task(current.next_notification()) for _ in range(3)]
    await asyncio.sleep(0)
    handle = await dispatch(current, selected)
    first = await asyncio.wait_for(asyncio.gather(*waiters), timeout=1)
    await asyncio.wait_for(handle.completion, timeout=1)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )
    tail = await current.next_notification()

    assert sorted(item.publish_seq for item in (*first, tail)) == [0, 1, 2, 3]
    assert current.snapshot().delivered_notifications == 4


def test_invalid_composition_notification_bounds_fail_before_runtime_effects() -> None:
    lower = LowerFormalAdapter()
    for kwargs in (
        {"max_requests": True},
        {"max_requests": 0},
        {"notification_capacity": True},
        {"notification_capacity": 0},
    ):
        with pytest.raises(AgentConversationRuntimeViolation) as invalid:
            AgentConversationRuntime(
                scope(),
                instance_id="invalid-notification-bounds",
                facade=facade(lower),
                **kwargs,
            )
        assert invalid.value.reason == "INVALID_COMPOSITION_CAPACITY"
    assert lower.calls == 0


def test_duplicate_or_exhausted_critical_reserve_fails_closed_without_growth() -> None:
    current = runtime(LowerFormalAdapter(), RecordingHistoryWriter(), max_requests=1)
    notification = AgentConversationNotification(
        kind="work.progress",
        request_id="request-critical",
        round_id="round-critical",
        response_ref=ResponseRef("interaction-critical", "response-critical", 0),
    )

    current._publish(  # noqa: SLF001 - invariant-level regression
        notification,
        critical_key=("terminal", notification.request_id),
    )
    with pytest.raises(AgentConversationRuntimeViolation) as duplicate:
        current._publish(  # noqa: SLF001 - invariant-level regression
            notification,
            critical_key=("terminal", notification.request_id),
        )
    assert duplicate.value.reason == "DUPLICATE_CRITICAL_NOTIFICATION"
    current._publish(  # noqa: SLF001 - invariant-level regression
        AgentConversationNotification(
            kind="agent.output",
            request_id=notification.request_id,
            round_id=notification.round_id,
            response_ref=notification.response_ref,
        ),
        critical_key=("presentation", notification.request_id),
    )
    with pytest.raises(AgentConversationRuntimeViolation) as exhausted:
        current._publish(  # noqa: SLF001 - invariant-level regression
            AgentConversationNotification(
                kind="work.progress",
                request_id="request-over-capacity",
                round_id="round-over-capacity",
                response_ref=ResponseRef(
                    "interaction-over-capacity", "response-over-capacity", 0
                ),
            ),
            critical_key=("terminal", "request-over-capacity"),
        )
    assert exhausted.value.reason == "CRITICAL_NOTIFICATION_RESERVE_EXHAUSTED"
    snapshot = current.snapshot()
    assert snapshot.queued_critical_notifications == 2
    assert snapshot.published_notifications == 2
    assert snapshot.critical_notification_invariant_failures == 2


@pytest.mark.asyncio
async def test_cancel_ack_does_not_precede_authoritative_cleanup_terminal() -> None:
    release = asyncio.Event()
    cleanup_release = asyncio.Event()
    lower = LowerFormalAdapter(
        final=None,
        release=release,
        cancel_cleanup_release=cleanup_release,
    )
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)
    await asyncio.wait_for(lower.started.wait(), timeout=1)

    accepted = await current.close_interaction(
        cancel_command(handle, selected, command_id="cancel-cleanup-retained")
    )
    assert accepted.accepted is True
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(current.next_notification(), timeout=0.02)
    assert handle.completion.done() is False
    assert current.snapshot().harness.active_rounds == (handle.round_id,)

    cleanup_release.set()
    terminal = await asyncio.wait_for(current.next_notification(), timeout=1)
    progress = WorkProgressEventV2.from_dict(terminal.progress_event.payload)
    assert progress.state.value == "terminal"
    assert progress.outcome.value == "cancelled"
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_interaction_close_rejects_replaced_round_without_cancel_effect() -> None:
    release = asyncio.Event()
    lower = LowerFormalAdapter(final=None, release=release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    first = await prepare(current)
    first_handle = await dispatch(current, first)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)

    second = commit(turn_id="turn-2", commit_id="commit-2", text="second")
    await current.start_turn(second.interaction_id, second.turn_id)
    await current.commit_turn(second)
    await dispatch(
        current,
        second,
        request_id="request-2",
        response_id="response-2",
    )
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)
    with pytest.raises(AgentConversationRuntimeViolation) as stale:
        await current.close_interaction(
            cancel_command(first_handle, first, command_id="cancel-replaced")
        )
    assert stale.value.reason == "INTERACTION_CLOSE_ROUND_STALE"
    assert current.snapshot().harness.cancel_effects == 0

    release.set()
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_completion_cancel_race_converges_on_harness_terminal_truth() -> None:
    release = asyncio.Event()
    lower = LowerFormalAdapter(final="race final", release=release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)

    cancel = asyncio.create_task(
        current.close_interaction(
            cancel_command(handle, selected, command_id="cancel-race")
        )
    )
    release.set()
    cancel_result = await cancel
    terminal_progress = None
    while terminal_progress is None:
        notification = await asyncio.wait_for(current.next_notification(), timeout=1)
        if notification.progress_event is not None:
            progress = WorkProgressEventV2.from_dict(
                notification.progress_event.payload
            )
            if progress.state.value == "terminal":
                terminal_progress = progress
    completion = await handle.completion
    assert terminal_progress.outcome == completion.terminal_outcome
    assert completion.terminal_outcome.value in {"completed", "cancelled"}
    if cancel_result.accepted:
        assert cancel_result.terminal_observed is False
    assert current.snapshot().harness.cancel_effects == int(cancel_result.accepted)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_concurrent_replay_dispatches_once_and_conflict_does_not_mutate_cr() -> (
    None
):
    lower = LowerFormalAdapter()
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    one, replay = await asyncio.gather(
        dispatch(current, selected),
        dispatch(current, selected),
    )
    assert one is replay
    await asyncio.wait_for(call_wait(lower, 1), timeout=1)
    assert lower.calls == 1
    responses_before = current.snapshot().conversation.conversation.responses
    with pytest.raises(AgentConversationRuntimeViolation) as conflict:
        await current.dispatch_committed_turn(
            request_id="request-1",
            response_id="changed-response",
            correlation_id="correlation-request-1",
            commit=selected,
            context=FormalContextSnapshot(selected.scope),
        )
    assert conflict.value.reason == "COMPOSITION_REQUEST_ID_CONFLICT"
    assert current.snapshot().conversation.conversation.responses == responses_before
    for _ in range(4):
        await asyncio.wait_for(current.next_notification(), timeout=1)
    replay_snapshot = current.snapshot()
    assert replay_snapshot.published_notifications == 4
    assert replay_snapshot.critical_notification_invariant_failures == 0
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_uncommitted_and_feature_off_have_zero_authority_effects() -> None:
    lower = LowerFormalAdapter()
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    await current.start()
    selected = commit()
    before = current.snapshot()
    with pytest.raises(AgentConversationRuntimeViolation) as uncommitted:
        await dispatch(current, selected)
    assert uncommitted.value.reason == "UNCOMMITTED_TURN"
    after = current.snapshot()
    assert after.conversation == before.conversation
    assert after.harness.retained_rounds == 0
    assert lower.calls == 0
    assert not history.users and not history.assistant_intents
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )

    disabled_lower = LowerFormalAdapter()
    disabled_history = RecordingHistoryWriter()
    disabled = runtime(disabled_lower, disabled_history, enabled=False)
    assert await disabled.start() is False
    with pytest.raises(AgentConversationRuntimeViolation) as off:
        await disabled.dispatch_committed_turn(
            request_id="request-off",
            response_id="response-off",
            correlation_id="correlation-off",
            commit=selected,
            context=FormalContextSnapshot(selected.scope),
        )
    assert off.value.reason == "FEATURE_DISABLED"
    snapshot = disabled.snapshot()
    assert snapshot.started is False
    assert snapshot.bridge.started is False
    assert snapshot.harness.retained_rounds == 0
    assert snapshot.notification_stream_closed is True
    assert snapshot.published_notifications == 0
    assert snapshot.delivered_notifications == 0
    assert snapshot.dropped_observer_notifications == 0
    assert disabled_lower.calls == 0
    assert (await disabled.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )

    unavailable = AgentConversationRuntime(
        scope(), instance_id="composition-no-facade", facade=None
    )
    assert await unavailable.start() is False
    unavailable_snapshot = unavailable.snapshot()
    assert unavailable_snapshot.started is False
    assert unavailable_snapshot.conversation.started is False
    assert unavailable_snapshot.bridge.started is False
    assert unavailable_snapshot.harness.retained_rounds == 0
    with pytest.raises(AgentConversationRuntimeViolation) as no_facade:
        await unavailable.open_interaction("interaction-no-facade")
    assert no_facade.value.reason == "FORMAL_AGENT_FACADE_UNAVAILABLE"

    code_lower = LowerFormalAdapter()
    code_lower._is_code_agent = True
    code_history = RecordingHistoryWriter()
    capability_off = runtime(code_lower, code_history)
    assert await capability_off.start() is False
    capability_snapshot = capability_off.snapshot()
    assert capability_snapshot.started is False
    assert capability_snapshot.conversation.started is False
    assert capability_snapshot.bridge.started is False
    assert capability_snapshot.harness.retained_rounds == 0
    assert code_lower.calls == 0
    assert not code_history.users and not code_history.assistant_intents


@pytest.mark.asyncio
async def test_history_failure_is_observable_retryable_and_fenced_ack_writes_zero() -> (
    None
):
    terminal_release = asyncio.Event()
    lower = LowerFormalAdapter(terminal_release=terminal_release)
    history = RecordingHistoryWriter(fail_assistant_once=True)
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(3)
    ]
    unit = next(
        item.presentation_unit
        for item in notifications
        if item.presentation_unit is not None
    )
    ack = PresentationAck(
        ref=handle.response_ref,
        surface=PresentationSurface.TEXT,
        unit_id=unit.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-05T08:00:02Z",
    )
    result = await current.acknowledge_presentation(ack)
    assert result.history_pending is True
    assert current.snapshot().pending_history_intents == 1
    assert await current.retry_history(handle.response_ref, contiguous_cursor=0) == (
        True,
    )
    assert current.snapshot().pending_history_intents == 0
    terminal_release.set()
    await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )

    terminal_release_two = asyncio.Event()
    lower_two = LowerFormalAdapter(terminal_release=terminal_release_two)
    history_two = RecordingHistoryWriter()
    second = runtime(lower_two, history_two)
    selected_two = await prepare(second)
    handle_two = await dispatch(second, selected_two)
    notifications_two = [
        await asyncio.wait_for(second.next_notification(), timeout=1) for _ in range(3)
    ]
    unit_two = next(
        item.presentation_unit
        for item in notifications_two
        if item.presentation_unit is not None
    )
    await second.request_response_cancel("response-cancel-1", handle_two.response_ref)
    with pytest.raises(ConversationRuntimeLoopViolation) as stale:
        await second.acknowledge_presentation(
            PresentationAck(
                ref=handle_two.response_ref,
                surface=PresentationSurface.TEXT,
                unit_id=unit_two.unit_id,
                contiguous_cursor=0,
                presented_at="2026-08-05T08:00:03Z",
            )
        )
    assert stale.value.reason == "STALE_RESPONSE_OUTPUT"
    assert not history_two.assistant_intents
    terminal_release_two.set()
    await asyncio.wait_for(second.next_notification(), timeout=1)
    assert (await second.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )

    release = asyncio.Event()
    late_lower = LowerFormalAdapter(final="late final", release=release)
    late_history = RecordingHistoryWriter()
    late = runtime(late_lower, late_history)
    late_commit = await prepare(late)
    late_handle = await dispatch(late, late_commit)
    for _ in range(2):
        await asyncio.wait_for(late.next_notification(), timeout=1)
    await late.request_response_cancel("response-cancel-late", late_handle.response_ref)
    release.set()
    rejected = await asyncio.wait_for(late.next_notification(), timeout=1)
    assert rejected.presentation_unit is None
    assert rejected.agent_event is None
    assert rejected.error_reason == "STALE_RESPONSE_OUTPUT"
    await asyncio.wait_for(late.next_notification(), timeout=1)
    assert not late_history.assistant_intents
    assert late.snapshot().conversation.presentation.records == ()
    assert (await late.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_concurrent_exact_ack_writes_history_once_and_replays() -> None:
    terminal_release = asyncio.Event()
    lower = LowerFormalAdapter(terminal_release=terminal_release)
    history = BlockingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(3)
    ]
    final = next(item for item in notifications if item.presentation_unit is not None)
    assert final.presentation_unit is not None
    current_ack = PresentationAck(
        ref=handle.response_ref,
        surface=PresentationSurface.TEXT,
        unit_id=final.presentation_unit.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-05T08:00:02Z",
    )
    first = asyncio.create_task(current.acknowledge_presentation(current_ack))
    await asyncio.wait_for(history.assistant_started.wait(), timeout=1)
    replay = asyncio.create_task(current.acknowledge_presentation(current_ack))
    await asyncio.sleep(0)
    assert not replay.done()
    history.assistant_release.set()
    first_result, replay_result = await asyncio.gather(first, replay)
    assert first_result.accepted is True
    assert first_result.replayed is False
    assert replay_result.accepted is True
    assert replay_result.replayed is True
    assert len(history.assistant_intents) == 1
    terminal_release.set()
    await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_ack_history_before_closed() -> None:
    terminal_release = asyncio.Event()
    lower = LowerFormalAdapter(terminal_release=terminal_release)
    history = BlockingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(3)
    ]
    final = next(item for item in notifications if item.presentation_unit is not None)
    ack = PresentationAck(
        ref=handle.response_ref,
        surface=PresentationSurface.TEXT,
        unit_id=final.presentation_unit.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-05T08:00:02Z",
    )
    ack_task = asyncio.create_task(current.acknowledge_presentation(ack))
    await asyncio.wait_for(history.assistant_started.wait(), timeout=1)
    terminal_release.set()
    await asyncio.wait_for(current.next_notification(), timeout=1)

    pending = await current.close(timeout_seconds=0.01)
    assert pending.status is AgentConversationShutdownStatus.PENDING
    assert current.snapshot().closed is False
    history.assistant_release.set()
    assert (await ack_task).history_records_written == 1
    closed = await current.close(timeout_seconds=1)
    assert closed.status is AgentConversationShutdownStatus.CLOSED
    assert current.snapshot().closed is True


@pytest.mark.asyncio
async def test_shutdown_history_failure_never_claims_closed() -> None:
    terminal_release = asyncio.Event()
    lower = LowerFormalAdapter(terminal_release=terminal_release)
    history = AlwaysFailAssistantHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(3)
    ]
    final = next(item for item in notifications if item.presentation_unit is not None)
    result = await current.acknowledge_presentation(
        PresentationAck(
            ref=handle.response_ref,
            surface=PresentationSurface.TEXT,
            unit_id=final.presentation_unit.unit_id,
            contiguous_cursor=0,
            presented_at="2026-08-05T08:00:02Z",
        )
    )
    assert result.history_pending is True
    terminal_release.set()
    await asyncio.wait_for(current.next_notification(), timeout=1)

    failed = await current.close(timeout_seconds=1)
    assert failed.status is AgentConversationShutdownStatus.FAILED
    assert failed.detail == "history_write_intents_pending"
    snapshot = current.snapshot()
    assert snapshot.closed is False
    assert snapshot.closing is True
    assert snapshot.pending_history_intents == 1


@pytest.mark.asyncio
async def test_cancelled_close_waiter_retains_pending_shutdown_without_implicit_cancel() -> (
    None
):
    release = asyncio.Event()
    lower = LowerFormalAdapter(final=None, release=release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)

    waiter = asyncio.create_task(current.close(timeout_seconds=5))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    pending = await current.close(timeout_seconds=0.01)
    assert pending.status is AgentConversationShutdownStatus.PENDING
    assert current.snapshot().closed is False
    assert current.snapshot().harness.cancel_effects == 0

    accepted = await current.close_interaction(
        cancel_command(handle, selected, command_id="cancel-for-close")
    )
    assert accepted.accepted is True
    await asyncio.wait_for(current.next_notification(), timeout=1)
    closed = await current.close(timeout_seconds=1)
    assert closed.status is AgentConversationShutdownStatus.CLOSED
    assert current.snapshot().closed is True
    assert await current.close(timeout_seconds=1) == closed


@pytest.mark.asyncio
async def test_empty_final_preserves_round_unknown_and_produces_no_presentation() -> (
    None
):
    lower = LowerFormalAdapter(final="")
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(4)
    ]
    assert all(item.presentation_unit is None for item in notifications)
    terminal = next(
        item
        for item in notifications
        if item.progress_event is not None
        and WorkProgressEventV2.from_dict(item.progress_event.payload).state.value
        == "terminal"
    )
    assert (
        WorkProgressEventV2.from_dict(terminal.progress_event.payload).outcome.value
        == "unknown"
    )
    response = next(
        item
        for item in current.snapshot().conversation.conversation.responses
        if item.ref == handle.response_ref
    )
    assert response.outcome.value == "unknown"
    assert not history.assistant_intents
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_adapter_exception_emits_only_harness_failed_terminal() -> None:
    lower = LowerFormalAdapter(error=RuntimeError("adapter failed"))
    history = RecordingHistoryWriter()
    current = runtime(lower, history)
    selected = await prepare(current)
    handle = await dispatch(current, selected)
    notifications = [
        await asyncio.wait_for(current.next_notification(), timeout=1) for _ in range(3)
    ]
    assert all(item.presentation_unit is None for item in notifications)
    terminal = notifications[-1]
    progress = WorkProgressEventV2.from_dict(terminal.progress_event.payload)
    assert progress.state.value == "terminal"
    assert progress.outcome.value == "failed"
    completion = await handle.completion
    assert completion.terminal_outcome.value == "failed"
    assert current.snapshot().conversation.presentation.records == ()
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_reservation_expiry_is_stable_and_absent_states_are_unsupported() -> None:
    now = [0.0]
    harness = JiuWenSwarmRoundHarness(
        instance_id="expiry-harness",
        reservation_ttl_seconds=1,
        monotonic=lambda: now[0],
        id_factory=id_factory(),
    )
    selected = commit()
    binding = HarnessRoundBinding(
        request_id="request-expiry",
        response_id="response-expiry",
        correlation_id="correlation-expiry",
        commit=selected,
    )
    reservation = harness.reserve_round(binding)
    assert "round.blocked" not in reservation.capabilities
    assert "round.decision_required" not in reservation.capabilities
    assert harness.snapshot().retained_rounds == 0
    now[0] = 2.0
    assert harness.snapshot().reservations == (
        ("request-expiry", HarnessReservationState.EXPIRED),
    )
    assert harness.reserve_round(binding) is reservation
    with pytest.raises(HarnessRoundViolation) as expired:
        harness.begin_round_commit(reservation)
    assert expired.value.reason == "HARNESS_RESERVATION_NOT_COMMITTABLE"
    assert harness.snapshot().cancel_effects == 0
    await harness.close()


@pytest.mark.asyncio
async def test_expired_reservation_releases_capacity_for_different_request() -> None:
    now = [0.0]
    harness = JiuWenSwarmRoundHarness(
        instance_id="expiry-capacity-harness",
        max_active_rounds=1,
        reservation_ttl_seconds=1,
        monotonic=lambda: now[0],
        id_factory=id_factory(),
    )
    first = commit()
    harness.reserve_round(
        HarnessRoundBinding(
            request_id="request-expired-a",
            response_id="response-expired-a",
            correlation_id="correlation-expired-a",
            commit=first,
        )
    )
    now[0] = 2.0
    second = commit(turn_id="turn-2", commit_id="commit-2")
    reservation = harness.reserve_round(
        HarnessRoundBinding(
            request_id="request-after-expiry-b",
            response_id="response-after-expiry-b",
            correlation_id="correlation-after-expiry-b",
            commit=second,
        )
    )
    assert reservation.binding.request_id == "request-after-expiry-b"
    assert dict(harness.snapshot().reservations)["request-expired-a"] is (
        HarnessReservationState.EXPIRED
    )
    await harness.close()


@pytest.mark.asyncio
async def test_bridge_queue_full_and_cr_accept_failure_leave_no_partial_response() -> (
    None
):
    release = asyncio.Event()
    lower = LowerFormalAdapter(final=None, release=release)
    history = RecordingHistoryWriter()
    bridge = AgentBridgeRuntime(
        instance_id="bounded-bridge",
        dispatch_capacity=1,
        max_concurrency=1,
    )
    current = runtime(lower, history, bridge=bridge)
    first = await prepare(current)
    first_handle = await dispatch(current, first)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)

    second = commit(turn_id="turn-2", commit_id="commit-2", text="second")
    await current.start_turn(second.interaction_id, second.turn_id)
    await current.commit_turn(second)
    second_handle = await dispatch(
        current,
        second,
        request_id="request-2",
        response_id="response-2",
    )
    third = commit(turn_id="turn-3", commit_id="commit-3", text="third")
    await current.start_turn(third.interaction_id, third.turn_id)
    await current.commit_turn(third)
    # Harness execution is admitted independently of the Bridge consumer's
    # concurrency lane.  Stabilize the two accepted Agent effects so this
    # assertion measures only the rejected third dispatch.
    await asyncio.wait_for(call_wait(lower, 2), timeout=1)
    responses_before = current.snapshot().conversation.conversation.responses
    with pytest.raises(AgentBridgeRuntimeViolation) as full:
        await dispatch(
            current,
            third,
            request_id="request-3",
            response_id="response-3",
        )
    assert full.value.reason == "DISPATCH_QUEUE_FULL"
    assert current.snapshot().conversation.conversation.responses == responses_before
    assert lower.calls == 2

    release.set()
    for _ in range(4):
        await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (await first_handle.completion).terminal_outcome.value == "unknown"
    assert (await second_handle.completion).terminal_outcome.value == "unknown"

    fourth = commit(turn_id="turn-4", commit_id="commit-4", text="fourth")
    await current.start_turn(fourth.interaction_id, fourth.turn_id)
    await current.commit_turn(fourth)
    with pytest.raises(ConversationRuntimeViolation) as reused:
        await dispatch(
            current,
            fourth,
            request_id="request-4",
            response_id="response-1",
        )
    assert reused.value.reason == "RESPONSE_ID_REUSED"
    assert len(current.snapshot().conversation.conversation.responses) == 2
    states = dict(current.snapshot().harness.reservations)
    assert states["request-3"] is HarnessReservationState.ABORTED
    assert states["request-4"] is HarnessReservationState.ABORTED
    assert lower.calls == 2
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )


@pytest.mark.asyncio
async def test_harness_capacity_failure_precedes_cr_mutation_and_agent_effect() -> None:
    release = asyncio.Event()
    lower = LowerFormalAdapter(final=None, release=release)
    history = RecordingHistoryWriter()
    current = runtime(lower, history, max_active_rounds=1)
    first = await prepare(current)
    await dispatch(current, first)
    for _ in range(2):
        await asyncio.wait_for(current.next_notification(), timeout=1)
    await asyncio.wait_for(call_wait(lower, 1), timeout=1)

    second = commit(turn_id="turn-2", commit_id="commit-2", text="second")
    await current.start_turn(second.interaction_id, second.turn_id)
    await current.commit_turn(second)
    responses_before = current.snapshot().conversation.conversation.responses
    with pytest.raises(AgentConversationRuntimeViolation) as invalid_channel:
        await current.dispatch_committed_turn(
            request_id="request-invalid-channel",
            response_id="response-invalid-channel",
            correlation_id="correlation-invalid-channel",
            commit=second,
            context=FormalContextSnapshot(second.scope),
            channel_id="",
        )
    assert invalid_channel.value.reason == "INVALID_DISPATCH_CHANNEL"
    assert current.snapshot().conversation.conversation.responses == responses_before
    assert current.snapshot().harness.retained_rounds == 1
    with pytest.raises(HarnessRoundViolation) as full:
        await dispatch(
            current,
            second,
            request_id="request-2",
            response_id="response-2",
        )
    assert full.value.reason == "HARNESS_ADMISSION_FULL"
    after = current.snapshot()
    assert after.conversation.conversation.responses == responses_before
    assert after.queued_notifications == 0
    assert after.harness.retained_rounds == 1
    assert lower.calls == 1

    release.set()
    await asyncio.wait_for(current.next_notification(), timeout=1)
    assert (await current.close(timeout_seconds=1)).status is (
        AgentConversationShutdownStatus.CLOSED
    )
