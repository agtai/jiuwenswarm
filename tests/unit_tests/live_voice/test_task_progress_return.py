# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, replace
from typing import cast

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ProducerRef,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    PersistentTaskEvent,
    TaskAuthorizationGrant,
)
from jiuwenswarm.server.live_voice.progress_notification_arbiter import (
    ForegroundFact,
    ForegroundSnapshot,
    ProgressNotificationArbiter,
    SpeechPolicy,
)
from jiuwenswarm.server.live_voice.task_event_subscription import (
    TaskEventSubscription,
)
from jiuwenswarm.server.live_voice.task_progress_return import (
    TaskProgressHandoffKind,
    TaskProgressNotificationIntent,
    TaskProgressOriginBinding,
    TaskProgressOriginKind,
    TaskProgressReturnBridge,
    TaskProgressReturnReason,
    TaskProgressReturnState,
    TaskProgressSourceDecision,
    TaskProgressTextEvent,
    project_task_progress_event,
)

NOW = "2026-08-06T10:00:00Z"
EXPIRY = "2026-08-06T11:00:00Z"
_DEFAULT_AUTHORIZATION = object()


def _scope(
    *,
    subject_id: str = "subject-1",
    project_id: str = "project-1",
    session_id: str = "session-1",
) -> ScopeRef:
    return ScopeRef(
        subject_id,
        project_id,
        session_id,
        Assurance.AUTHENTICATED,
    )


def _grant(
    *,
    task_id: str = "task-1",
    scope: ScopeRef | None = None,
) -> TaskAuthorizationGrant:
    granted_scope = scope or _scope()
    return TaskAuthorizationGrant(
        principal_id=granted_scope.subject_id,
        scope=granted_scope,
        operation="task.events",
        command_id=None,
        target_task_id=task_id,
        allowed_capabilities=frozenset({"task.events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=EXPIRY,
    )


def _binding(
    origin_kind: TaskProgressOriginKind,
    *,
    task_id: str = "task-1",
    scope: ScopeRef | None = None,
    correlation_id: str = "correlation-1",
    generation: int = 7,
) -> TaskProgressOriginBinding:
    current_scope = scope or _scope()
    assert current_scope.project_id is not None
    assert current_scope.session_id is not None
    return TaskProgressOriginBinding(
        scope=current_scope,
        task_id=task_id,
        session_id=current_scope.session_id,
        project_id=current_scope.project_id,
        correlation_id=correlation_id,
        origin_kind=origin_kind,
        origin_id=f"{origin_kind.value}-origin-1",
        generation_kind="conversation_generation",
        generation_id="conversation-1",
        generation=generation,
        source_instance_id="task-core-1",
        progress_producer=ProducerRef(
            component="task_progress_return",
            instance_id="task-progress-return-1",
            authority="adapter",
        ),
        progress_adapter="task_progress_return.v1",
    )


def _event(
    seq: int,
    event_type: str,
    state: str,
    *,
    task_id: str = "task-1",
    scope: ScopeRef | None = None,
    correlation_id: str = "correlation-1",
    event_id: str | None = None,
    producer: str = "task_core",
    outcome: str | None = None,
    details: dict[str, object] | None = None,
) -> PersistentTaskEvent:
    return PersistentTaskEvent(
        event_id=event_id or f"event-{seq}",
        task_id=task_id,
        attempt_id="attempt-1",
        scope=scope or _scope(),
        seq=seq,
        event_type=event_type,
        state=state,
        outcome=outcome,
        producer=producer,
        source_event_id=None,
        causation_id=f"cause-{seq}",
        correlation_id=correlation_id,
        occurred_at=NOW,
        details=details or {},
    )


def _lifecycle_events(*, start_seq: int = 0) -> list[PersistentTaskEvent]:
    return [
        _event(start_seq, "task.accepted", "accepted"),
        _event(start_seq + 1, "task.running", "running"),
        _event(
            start_seq + 2,
            "task.terminal",
            "terminal",
            outcome="completed",
        ),
    ]


def _foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.SAFE,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


def _busy_foreground() -> ForegroundSnapshot:
    return ForegroundSnapshot(
        interaction=ForegroundFact.SAFE,
        response=ForegroundFact.BUSY,
        presentation=ForegroundFact.SAFE,
        speech_policy=SpeechPolicy.ALLOW_CANDIDATE,
    )


@dataclass(frozen=True, slots=True)
class _SubscriptionSnapshot:
    task_id: str


class _SubscriptionDouble:
    """Exact live subscription surface; no replay or fabricated prefix."""

    def __init__(
        self,
        events: list[PersistentTaskEvent] | None = None,
        *,
        task_id: str = "task-1",
        start_result: bool = True,
        close_gate: asyncio.Event | None = None,
        close_failures: int = 0,
    ) -> None:
        self.events = deque(events or [])
        self.task_id = task_id
        self.start_result = start_result
        self.start_calls = 0
        self.next_calls = 0
        self.close_calls = 0
        self.close_gate = close_gate
        self.close_failures = close_failures
        self._closed = asyncio.Event()

    def snapshot(self) -> _SubscriptionSnapshot:
        return _SubscriptionSnapshot(task_id=self.task_id)

    async def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    async def next_event(self) -> PersistentTaskEvent:
        self.next_calls += 1
        if self.events:
            return self.events.popleft()
        await self._closed.wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_failures:
            self.close_failures -= 1
            raise RuntimeError("injected subscription close failure")
        self._closed.set()


class _PreparedSourceDouble:
    """Package-contract evidence only; not a formal authority handoff."""

    handoff_kind = TaskProgressHandoffKind.PACKAGE_CONTRACT_TEST
    evidence_id = "package-contract:prepared-contiguous-projection:1"

    def __init__(
        self,
        subscription: _SubscriptionDouble,
        events: list[PersistentTaskEvent],
        *,
        start_result: bool = True,
    ) -> None:
        self.subscription = cast(TaskEventSubscription, subscription)
        self.events = deque(events)
        self.start_result = start_result
        self.start_calls = 0
        self.next_calls = 0
        self.close_calls = 0
        self._closed = asyncio.Event()
        self._changed = asyncio.Event()

    async def start(self) -> bool:
        self.start_calls += 1
        return self.start_result

    async def next_event(self) -> PersistentTaskEvent:
        self.next_calls += 1
        while True:
            if self.events:
                return self.events.popleft()
            if self._closed.is_set():
                raise StopAsyncIteration
            self._changed.clear()
            if self.events or self._closed.is_set():
                continue
            await self._changed.wait()

    def publish(self, event: PersistentTaskEvent) -> None:
        self.events.append(event)
        self._changed.set()

    async def close(self) -> None:
        self.close_calls += 1
        self._closed.set()
        self._changed.set()


async def _wait_settled(bridge: TaskProgressReturnBridge) -> None:
    for _ in range(200):
        if not bridge.snapshot().worker_pending:
            return
        await asyncio.sleep(0)
    raise AssertionError("task progress bridge did not settle")


async def _wait_until(predicate) -> None:
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


def _bridge(
    *,
    origin_kind: TaskProgressOriginKind,
    subscription: _SubscriptionDouble,
    prepared_source: _PreparedSourceDouble | None = None,
    enabled: bool = True,
    authorization: TaskAuthorizationGrant | None | object = _DEFAULT_AUTHORIZATION,
    binding: TaskProgressOriginBinding | None = None,
    generation_is_current=lambda _binding: True,
    arbiter: ProgressNotificationArbiter | None = None,
    voice_events: list[TaskProgressNotificationIntent] | None = None,
    text_events: list[TaskProgressTextEvent] | None = None,
    allow_package_contract_handoff: bool = False,
) -> TaskProgressReturnBridge:
    selected_binding = binding or _binding(origin_kind)
    selected_voice_events = voice_events if voice_events is not None else []
    selected_text_events = text_events if text_events is not None else []

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        selected_voice_events.append(intent)

    async def text_sink(event: TaskProgressTextEvent) -> None:
        selected_text_events.append(event)

    return TaskProgressReturnBridge(
        enabled=enabled,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared_source,
        authorization=(
            _grant()
            if authorization is _DEFAULT_AUTHORIZATION
            else cast(TaskAuthorizationGrant | None, authorization)
        ),
        binding=selected_binding,
        generation_is_current=generation_is_current,
        arbiter=arbiter or ProgressNotificationArbiter(),
        foreground=_foreground,
        voice_sink=voice_sink,
        text_sink=text_sink,
        allow_package_contract_handoff=allow_package_contract_handoff,
        clock=lambda: NOW,
    )


def test_projection_preserves_source_truth_and_omits_unknown_business_facts() -> None:
    binding = _binding(TaskProgressOriginKind.TEXT)
    task_event = _event(
        9,
        "task.running",
        "running",
        details={
            "summary": "Source supplied summary",
            "percent": 90,
            "error": "must not escape",
            "completed": True,
        },
    )

    projected = project_task_progress_event(task_event, binding)

    assert projected.source_event.event_id == task_event.event_id
    assert projected.source_event.seq == task_event.seq
    assert projected.source_event.producer.component == task_event.producer
    assert projected.source_event.correlation_id == task_event.correlation_id
    assert projected.progress_event.seq == task_event.seq
    assert projected.progress_event.causation_id == task_event.event_id
    assert projected.progress_event.correlation_id == task_event.correlation_id
    assert projected.progress_event.payload["state"] == "running"
    assert projected.progress_event.payload["outcome"] is None
    assert projected.progress_event.payload["summary"] == {
        "knowledge": "known",
        "value": "Source supplied summary",
    }
    assert projected.progress_event.payload["blocking_question"] == {
        "knowledge": "unknown"
    }
    assert projected.progress_event.payload["artifact_refs"] == {"knowledge": "unknown"}
    assert projected.progress_event.payload["speakability"] == "not_speakable"
    assert "percent" not in projected.progress_event.payload
    assert "error" not in projected.progress_event.payload
    assert "completed" not in projected.progress_event.payload


@pytest.mark.asyncio
async def test_voice_package_contract_routes_typed_intents_through_arbiter() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
        allow_package_contract_handoff=True,
    )

    activation = await bridge.activate()
    await _wait_settled(bridge)

    assert activation.active is True
    assert activation.handoff_kind is TaskProgressHandoffKind.PACKAGE_CONTRACT_TEST
    assert activation.handoff_evidence_id == prepared.evidence_id
    assert activation.lease is not None
    assert [intent.task_event.seq for intent in voice_events] == [0, 1, 2]
    assert all(
        intent.progress_event.payload["speakability"] == "not_speakable"
        for intent in voice_events
    )
    assert all(
        intent.origin.origin_kind is TaskProgressOriginKind.VOICE
        for intent in voice_events
    )
    assert all(intent.origin.origin_id == "voice-origin-1" for intent in voice_events)
    assert all(intent.origin.generation == 7 for intent in voice_events)
    assert text_events == []
    assert subscription.start_calls == 0
    assert prepared.start_calls == 1
    assert prepared.close_calls == 1
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert arbiter.snapshot().accepted_events == 3


@pytest.mark.asyncio
async def test_deferred_voice_waits_for_explicit_safe_drain_and_acks_once() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    foreground = _busy_foreground()

    def foreground_supplier() -> ForegroundSnapshot:
        return foreground

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        voice_events.append(intent)

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=foreground_supplier,
        voice_sink=voice_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_settled(bridge)

    assert voice_events == []
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().state is TaskProgressReturnState.ACTIVE
    assert arbiter.snapshot().pending_notifications == 1

    foreground = _foreground()
    assert await activation.lease.drain_voice() == 1
    assert len(voice_events) == 1
    assert voice_events[0].task_event.event_type == "task.terminal"
    assert voice_events[0].decision.reason.startswith("drain_")
    assert bridge.snapshot().voice_intents == 1
    assert bridge.snapshot().voice_drains == 1
    assert bridge.snapshot().pending_voice_intents == 0
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert arbiter.snapshot().pending_notifications == 0

    assert await activation.lease.drain_voice() == 0
    assert len(voice_events) == 1
    assert bridge.snapshot().voice_drains == 1
    await activation.lease.close()


@pytest.mark.asyncio
async def test_voice_drain_serializes_sink_against_source_delivery() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, [_lifecycle_events()[0]])
    arbiter = ProgressNotificationArbiter()
    foreground = _busy_foreground()
    first_sink_started = asyncio.Event()
    release_first_sink = asyncio.Event()
    sink_calls: list[int] = []
    active_sinks = 0
    maximum_active_sinks = 0

    def foreground_supplier() -> ForegroundSnapshot:
        return foreground

    async def voice_sink(intent: TaskProgressNotificationIntent) -> None:
        nonlocal active_sinks, maximum_active_sinks
        active_sinks += 1
        maximum_active_sinks = max(maximum_active_sinks, active_sinks)
        sink_calls.append(intent.task_event.seq)
        if len(sink_calls) == 1:
            first_sink_started.set()
            await release_first_sink.wait()
        active_sinks -= 1

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=foreground_supplier,
        voice_sink=voice_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_until(lambda: bridge.snapshot().pending_voice_intents == 1)
    foreground = _foreground()
    drain = asyncio.create_task(activation.lease.drain_voice())
    await first_sink_started.wait()

    prepared.publish(_event(1, "task.running", "running"))
    await _wait_until(lambda: bridge.snapshot().projected_events == 2)
    assert sink_calls == [0]
    assert active_sinks == 1

    release_first_sink.set()
    assert await drain == 1
    await _wait_until(lambda: bridge.snapshot().voice_intents == 2)

    assert sink_calls == [0, 1]
    assert maximum_active_sinks == 1
    assert arbiter.snapshot().pending_notifications == 0
    await activation.lease.close()


@pytest.mark.asyncio
async def test_text_live_route_preserves_raw_sequence_and_skips_control_event() -> None:
    control = _event(
        8,
        "attempt.running",
        "running",
        producer="executor-1",
    )
    running = _event(9, "task.running", "running")
    terminal = _event(10, "task.terminal", "terminal", outcome="completed")
    subscription = _SubscriptionDouble([control, running, terminal])
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        arbiter=arbiter,
        voice_events=voice_events,
        text_events=text_events,
    )

    activation = await bridge.activate()
    await _wait_settled(bridge)

    assert activation.active is True
    assert activation.handoff_kind is None
    assert [event.task_event.seq for event in text_events] == [9, 10]
    assert [event.source_event.event_id for event in text_events] == [
        running.event_id,
        terminal.event_id,
    ]
    assert [event.progress_event.seq for event in text_events] == [9, 10]
    assert all(
        event.origin.origin_kind is TaskProgressOriginKind.TEXT for event in text_events
    )
    assert voice_events == []
    assert subscription.start_calls == 1
    assert subscription.close_calls == 1
    snapshot = bridge.snapshot()
    assert snapshot.source_events == 3
    assert snapshot.projected_events == 2
    assert snapshot.unprojected_events == 1
    assert snapshot.reason_id is TaskProgressReturnReason.TERMINAL_DELIVERED
    assert snapshot.last_source_decision_id is TaskProgressSourceDecision.PROJECTED
    assert snapshot.last_source_evidence_id is not None
    assert arbiter.snapshot().accepted_events == 0


@pytest.mark.asyncio
async def test_voice_without_authority_handoff_is_unavailable_with_zero_effects() -> (
    None
):
    subscription = _SubscriptionDouble(_lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        voice_events=voice_events,
        text_events=text_events,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert activation.lease is None
    assert subscription.start_calls == 0
    assert subscription.next_calls == 0
    assert subscription.close_calls == 0
    assert voice_events == []
    assert text_events == []
    assert bridge.snapshot().worker_pending is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "authorization", "current", "reason"),
    [
        (False, _grant(), True, TaskProgressReturnReason.FEATURE_DISABLED),
        (True, None, True, TaskProgressReturnReason.AUTHORIZATION_REJECTED),
        (True, _grant(), False, TaskProgressReturnReason.STALE_GENERATION),
    ],
)
async def test_fail_closed_activation_has_zero_subscription_or_sink_effects(
    enabled: bool,
    authorization: TaskAuthorizationGrant | None,
    current: bool,
    reason: TaskProgressReturnReason,
) -> None:
    subscription = _SubscriptionDouble(_lifecycle_events())
    voice_events: list[TaskProgressNotificationIntent] = []
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        enabled=enabled,
        authorization=authorization,
        generation_is_current=lambda _binding: current,
        voice_events=voice_events,
        text_events=text_events,
    )
    activation = await bridge.activate()

    assert activation.active is False
    assert activation.reason_id is reason
    assert subscription.start_calls == 0
    assert subscription.next_calls == 0
    assert subscription.close_calls == 0
    assert voice_events == []
    assert text_events == []
    assert bridge.snapshot().worker_pending is False


@pytest.mark.asyncio
async def test_wrong_scope_and_wrong_subscription_task_reject_before_start() -> None:
    foreign_scope = _scope(subject_id="subject-2")
    for binding, authorization, task_id in (
        (_binding(TaskProgressOriginKind.TEXT), _grant(scope=foreign_scope), "task-1"),
        (_binding(TaskProgressOriginKind.TEXT), _grant(), "task-2"),
    ):
        subscription = _SubscriptionDouble(_lifecycle_events(), task_id=task_id)
        bridge = _bridge(
            origin_kind=TaskProgressOriginKind.TEXT,
            subscription=subscription,
            authorization=authorization,
            binding=binding,
        )

        activation = await bridge.activate()

        assert activation.active is False
        assert activation.reason_id in {
            TaskProgressReturnReason.AUTHORIZATION_REJECTED,
            TaskProgressReturnReason.INVALID_BINDING,
        }
        assert subscription.start_calls == 0
        assert subscription.next_calls == 0
        assert subscription.close_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_dimension", ["task", "scope", "correlation"])
async def test_cross_scope_events_fail_without_sink_output(
    foreign_dimension: str,
) -> None:
    event = _event(12, "task.running", "running")
    if foreign_dimension == "task":
        event = replace(event, task_id="task-2")
    elif foreign_dimension == "scope":
        event = replace(event, scope=_scope(subject_id="subject-2"))
    else:
        event = replace(event, correlation_id="correlation-2")
    subscription = _SubscriptionDouble([event])
    text_events: list[TaskProgressTextEvent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
        text_events=text_events,
    )

    activation = await bridge.activate()
    assert activation.active is True
    await _wait_settled(bridge)

    assert text_events == []
    assert bridge.snapshot().state is TaskProgressReturnState.FAILED
    assert (
        bridge.snapshot().reason_id
        is TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION
    )


@pytest.mark.asyncio
async def test_prepared_voice_cross_task_rejects_before_arbiter_or_sink() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(
        subscription,
        [_event(0, "task.accepted", "accepted", task_id="task-2")],
    )
    voice_events: list[TaskProgressNotificationIntent] = []
    arbiter = ProgressNotificationArbiter()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        arbiter=arbiter,
        voice_events=voice_events,
        allow_package_contract_handoff=True,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert voice_events == []
    assert arbiter.snapshot().accepted_events == 0
    assert (
        bridge.snapshot().last_source_decision_id
        is TaskProgressSourceDecision.BINDING_REJECTED
    )


@pytest.mark.asyncio
async def test_stale_generation_after_first_text_event_fences_later_sink() -> None:
    subscription = _SubscriptionDouble(_lifecycle_events(start_seq=20)[1:])
    current = True
    text_events: list[TaskProgressTextEvent] = []

    def generation_is_current(_binding: TaskProgressOriginBinding) -> bool:
        return current

    async def text_sink(event: TaskProgressTextEvent) -> None:
        nonlocal current
        text_events.append(event)
        current = False

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=None,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.TEXT),
        generation_is_current=generation_is_current,
        arbiter=ProgressNotificationArbiter(),
        foreground=_foreground,
        voice_sink=lambda _intent: _noop(),
        text_sink=text_sink,
        clock=lambda: NOW,
    )

    activation = await bridge.activate()
    assert activation.active is True
    await _wait_settled(bridge)

    assert [event.task_event.seq for event in text_events] == [21]
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.STALE_GENERATION
    assert bridge.snapshot().rejected_events == 1


async def _noop() -> None:
    return None


@pytest.mark.asyncio
async def test_duplicate_is_idempotent_but_gap_and_out_of_order_fail_closed() -> None:
    accepted = _event(30, "task.accepted", "accepted")
    running = _event(31, "task.running", "running")
    terminal = _event(32, "task.terminal", "terminal", outcome="completed")
    duplicate_subscription = _SubscriptionDouble(
        [accepted, accepted, running, terminal]
    )
    duplicate_events: list[TaskProgressTextEvent] = []
    duplicate_bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=duplicate_subscription,
        text_events=duplicate_events,
    )

    assert (await duplicate_bridge.activate()).active is True
    await _wait_settled(duplicate_bridge)

    assert [event.task_event.seq for event in duplicate_events] == [30, 31, 32]
    assert duplicate_bridge.snapshot().duplicate_events == 1

    for invalid in (
        _event(32, "task.running", "running"),
        _event(30, "task.running", "running", event_id="conflict-30"),
    ):
        subscription = _SubscriptionDouble([accepted, invalid])
        events: list[TaskProgressTextEvent] = []
        bridge = _bridge(
            origin_kind=TaskProgressOriginKind.TEXT,
            subscription=subscription,
            text_events=events,
        )

        assert (await bridge.activate()).active is True
        await _wait_settled(bridge)

        assert [event.task_event.seq for event in events] == [30]
        assert bridge.snapshot().state is TaskProgressReturnState.FAILED
        assert (
            bridge.snapshot().reason_id
            is TaskProgressReturnReason.SOURCE_PROTOCOL_VIOLATION
        )
        expected_decision = (
            TaskProgressSourceDecision.SEQUENCE_GAP
            if invalid.seq > accepted.seq
            else TaskProgressSourceDecision.SEQUENCE_CONFLICT
        )
        assert bridge.snapshot().last_source_decision_id is expected_decision


@pytest.mark.asyncio
async def test_voice_prepared_source_rejects_nonprojectable_advance() -> None:
    subscription = _SubscriptionDouble()
    control = _event(
        0,
        "attempt.accepted",
        "accepted",
        producer="executor-1",
    )
    prepared = _PreparedSourceDouble(subscription, [control])
    voice_events: list[TaskProgressNotificationIntent] = []
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        voice_events=voice_events,
        allow_package_contract_handoff=True,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert voice_events == []
    assert (
        bridge.snapshot().reason_id
        is TaskProgressReturnReason.SOURCE_EVENT_NOT_PROJECTABLE
    )
    assert prepared.close_calls == 1


@pytest.mark.asyncio
async def test_prepared_voice_test_lease_requires_explicit_package_test_switch() -> (
    None
):
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert prepared.start_calls == 0
    assert prepared.next_calls == 0
    assert prepared.close_calls == 0


@pytest.mark.asyncio
async def test_reserved_atomic_handoff_kind_cannot_claim_formal_voice_route() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, _lifecycle_events())
    prepared.handoff_kind = TaskProgressHandoffKind.AUTHORITY_ATOMIC
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.VOICE,
        subscription=subscription,
        prepared_source=prepared,
        allow_package_contract_handoff=True,
    )

    activation = await bridge.activate()

    assert activation.active is False
    assert (
        activation.reason_id is TaskProgressReturnReason.AUTHORITY_HANDOFF_UNAVAILABLE
    )
    assert activation.handoff_kind is TaskProgressHandoffKind.AUTHORITY_ATOMIC
    assert prepared.start_calls == 0
    assert prepared.next_calls == 0
    assert prepared.close_calls == 0


@pytest.mark.asyncio
async def test_detach_close_is_idempotent_and_has_no_business_cancel_port() -> None:
    subscription = _SubscriptionDouble()
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
    )

    activation = await bridge.activate()
    assert activation.active is True
    assert activation.lease is not None
    await activation.lease.close()
    await activation.lease.close()

    assert subscription.start_calls == 1
    assert subscription.close_calls == 1
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.CONSUMER_DETACHED
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().text_events == 0


@pytest.mark.asyncio
async def test_cancelled_close_waiter_does_not_cancel_detach_cleanup() -> None:
    close_gate = asyncio.Event()
    subscription = _SubscriptionDouble(close_gate=close_gate)
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
    )
    activation = await bridge.activate()
    assert activation.lease is not None
    first_waiter = asyncio.create_task(activation.lease.close())
    await asyncio.sleep(0)
    first_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_waiter

    close_gate.set()
    await activation.lease.close()

    assert subscription.close_calls == 1
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.CONSUMER_DETACHED


@pytest.mark.asyncio
async def test_failed_text_detach_remains_retryable_by_the_exact_lease() -> None:
    subscription = _SubscriptionDouble(close_failures=1)
    bridge = _bridge(
        origin_kind=TaskProgressOriginKind.TEXT,
        subscription=subscription,
    )
    activation = await bridge.activate()
    assert activation.lease is not None
    await _wait_until(lambda: subscription.next_calls == 1)

    with pytest.raises(RuntimeError, match="injected subscription close failure"):
        await activation.lease.close()

    assert bridge.snapshot().state is TaskProgressReturnState.DETACHING
    await activation.lease.close()

    assert subscription.close_calls == 2
    assert bridge.snapshot().state is TaskProgressReturnState.CLOSED
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.CONSUMER_DETACHED


@pytest.mark.asyncio
async def test_voice_sink_failure_is_not_acknowledged_or_retried() -> None:
    subscription = _SubscriptionDouble()
    prepared = _PreparedSourceDouble(subscription, [_lifecycle_events()[0]])
    calls = 0
    arbiter = ProgressNotificationArbiter()

    async def failing_sink(_intent: TaskProgressNotificationIntent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("notification-intent consumer unavailable")

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=prepared,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.VOICE),
        generation_is_current=lambda _binding: True,
        arbiter=arbiter,
        foreground=_foreground,
        voice_sink=failing_sink,
        text_sink=lambda _event: _noop(),
        allow_package_contract_handoff=True,
        clock=lambda: NOW,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert calls == 1
    assert bridge.snapshot().voice_intents == 0
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.VOICE_SINK_FAILED
    assert arbiter.snapshot().accepted_events == 1
    assert arbiter.snapshot().pending_notifications == 1


@pytest.mark.asyncio
async def test_sink_failure_settles_without_later_delivery() -> None:
    subscription = _SubscriptionDouble(_lifecycle_events(start_seq=40))
    calls = 0

    async def failing_sink(_event: TaskProgressTextEvent) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("sink unavailable")

    bridge = TaskProgressReturnBridge(
        enabled=True,
        subscription=cast(TaskEventSubscription, subscription),
        prepared_source=None,
        authorization=_grant(),
        binding=_binding(TaskProgressOriginKind.TEXT),
        generation_is_current=lambda _binding: True,
        arbiter=ProgressNotificationArbiter(),
        foreground=_foreground,
        voice_sink=lambda _intent: _noop(),
        text_sink=failing_sink,
        clock=lambda: NOW,
    )

    assert (await bridge.activate()).active is True
    await _wait_settled(bridge)

    assert calls == 1
    assert bridge.snapshot().text_events == 0
    assert bridge.snapshot().reason_id is TaskProgressReturnReason.TEXT_SINK_FAILED
