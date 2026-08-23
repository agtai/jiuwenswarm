# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    ResponseRef,
    ResultEnvelope,
    ScopeRef,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    PersistentTaskEvent,
    TaskAuthorizationGrant,
    TaskResultArtifact,
    TaskResultRecord,
    TaskUnreadPage,
)
from jiuwenswarm.server.live_voice.agent_conversation_runtime import (
    PresentationAckResult,
)
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
    TaskPresentationConsumptionOwner,
    TaskPresentationRuntimeReceipt,
    TaskPresentationViolation,
    TextPresentationAdoptionAck,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW,
    _Executor,
    _create,
    _grant,
    _scope,
)


SCOPE = ScopeRef("subject-1", "project-1", "session-new", Assurance.AUTHENTICATED)
RESPONSE = ResponseRef("interaction-1", "response-1", 1)


class _RuntimeAuthority:
    def __init__(self, *active: ResponseRef) -> None:
        self.active = set(active)
        self.calls: list[tuple[ResponseRef, str | None, str]] = []

    @staticmethod
    def reservation_id(ref: ResponseRef) -> str:
        return (
            f"runtime:{ref.interaction_id}:{ref.response_id}:{ref.response_generation}"
        )

    def __call__(
        self,
        ref: ResponseRef,
        reservation_id: str | None,
        phase: str,
    ) -> TaskPresentationRuntimeReceipt:
        self.calls.append((ref, reservation_id, phase))
        expected = self.reservation_id(ref)
        if phase == "reserve":
            if ref not in self.active or reservation_id is not None:
                raise TaskPresentationViolation(
                    "RUNTIME_PRESENTATION_STALE", "response is not current"
                )
            return TaskPresentationRuntimeReceipt(ref, expected, phase, True)
        if reservation_id != expected:
            raise TaskPresentationViolation(
                "RUNTIME_PRESENTATION_STALE", "reservation is not current"
            )
        if phase == "close":
            if ref in self.active:
                raise TaskPresentationViolation(
                    "RUNTIME_PRESENTATION_STALE", "response remains active"
                )
            return TaskPresentationRuntimeReceipt(ref, expected, phase, False)
        if ref not in self.active:
            raise TaskPresentationViolation(
                "RUNTIME_PRESENTATION_STALE", "response is not current"
            )
        return TaskPresentationRuntimeReceipt(ref, expected, phase, True)

    def close(self, ref: ResponseRef) -> None:
        if ref not in self.active:
            raise AssertionError("test Runtime response is already closed")
        self.active.remove(ref)


def _owner(
    *active: ResponseRef, capacity: int = 128
) -> tuple[TaskPresentationConsumptionOwner, _RuntimeAuthority]:
    authority = _RuntimeAuthority(*(active or (RESPONSE,)))
    return TaskPresentationConsumptionOwner(authority, capacity=capacity), authority


def _event(
    seq: int,
    *,
    event_type: str = "task.running",
    state: str = "running",
    outcome: str | None = None,
    source_event_id: str | None = "executor-event-1",
) -> PersistentTaskEvent:
    return PersistentTaskEvent(
        event_id=f"event-{seq}",
        task_id="task-1",
        attempt_id="attempt-1",
        scope=ScopeRef(
            SCOPE.subject_id,
            SCOPE.project_id,
            "session-original",
            Assurance.AUTHENTICATED,
        ),
        seq=seq,
        event_type=event_type,
        state=state,
        outcome=outcome,
        producer="task_core",
        source_event_id=source_event_id,
        causation_id="command-1",
        correlation_id="correlation-1",
        occurred_at="2026-08-20T12:00:00Z",
        details={},
    )


def _page(
    *events: PersistentTaskEvent, presentation_class: str = "text"
) -> TaskUnreadPage:
    return TaskUnreadPage(
        task_id="task-1",
        presentation_class=presentation_class,
        watermark=events[0].seq - 1,
        acked_event_id=None if events[0].seq == 0 else f"event-{events[0].seq - 1}",
        head_seq=events[-1].seq,
        events=events,
        next_after_seq=None,
        has_more=False,
    )


def _result(event: PersistentTaskEvent) -> TaskResultRecord:
    assert event.source_event_id is not None
    return TaskResultRecord(
        task_id=event.task_id,
        attempt_id=event.attempt_id,
        source_event_id=event.source_event_id,
        result_text="bounded canonical result",
        artifacts=(TaskResultArtifact("result.txt", "a" * 64),),
        completed_at="2026-08-20T12:00:01Z",
    )


def _ack_command(delivery, *, command_id: str = "command-ack"):
    command = CommandEnvelope.from_dict(
        {
            "contract_version": "live-voice.contract.v2",
            "request_id": f"request-{command_id}",
            "command_id": command_id,
            "command_type": "task.ack_events",
            "issued_at": "2026-08-20T12:00:03Z",
            "scope": delivery.scope.to_dict(),
            "correlation_id": "correlation-ack",
            "causation_id": delivery.event_id,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": delivery.task_id},
            "context_refs": [],
            "required_capabilities": ["task.ack_events"],
            "payload": {
                "presentation_class": delivery.presentation_class,
                "acked_through_seq": delivery.event_seq,
                "acked_event_id": delivery.event_id,
                "expected_event_head": delivery.expected_event_head,
            },
            "extensions": {},
        }
    )
    grant = TaskAuthorizationGrant(
        principal_id=delivery.scope.subject_id,
        scope=delivery.scope,
        operation="task.ack_events",
        command_id=command.command_id,
        target_task_id=delivery.task_id,
        allowed_capabilities=frozenset({"task.ack_events"}),
        confirmation_id=None,
        confirmed=False,
        expires_at="2026-08-20T13:00:00Z",
    )
    return command, grant


def _success(command: CommandEnvelope, delivery) -> ResultEnvelope:
    return ResultEnvelope.success(
        owner=command,
        result={
            "task_id": delivery.task_id,
            "presentation_class": delivery.presentation_class,
            "acked_through_seq": delivery.event_seq,
            "acked_event_id": delivery.event_id,
            "advanced": True,
        },
        observed_at="2026-08-20T12:00:04Z",
    )


def test_text_requires_exact_dom_adoption_before_consumption_command() -> None:
    owner, _runtime = _owner()
    event = _event(0)
    delivery = owner.reserve_next(
        _page(event),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-1",
        unit_id="unit-1",
    )
    command, grant = _ack_command(delivery)
    command_calls: list[tuple[CommandEnvelope, TaskAuthorizationGrant]] = []

    def command_port(item, authorization):
        command_calls.append((item, authorization))
        return _success(item, delivery)

    with pytest.raises(TaskPresentationViolation) as before_adoption:
        owner.consume(delivery, command, grant, command_port)
    assert before_adoption.value.reason == "PRESENTATION_ACK_REQUIRED"
    assert command_calls == []

    assert owner.mark_text_adopted(
        TextPresentationAdoptionAck.from_delivery(
            delivery, adopted_at="2026-08-20T12:00:02Z"
        )
    )
    stale_session_grant = replace(
        grant,
        scope=replace(delivery.scope, session_id="session-stale"),
    )
    with pytest.raises(TaskPresentationViolation) as stale_session:
        owner.consume(delivery, command, stale_session_grant, command_port)
    assert stale_session.value.reason == "CONSUMPTION_AUTHORIZATION_MISMATCH"
    assert command_calls == []
    result = owner.consume(delivery, command, grant, command_port)
    assert result.ok
    assert command_calls == [(command, grant)]


def test_reservation_skips_only_a_closed_nonpresentable_prefix() -> None:
    owner, runtime = _owner()
    page = _page(
        _event(
            1,
            event_type="attempt.accepted",
            state="accepted",
            source_event_id=None,
        ),
        _event(
            2,
            event_type="attempt.running",
            state="running",
            source_event_id="executor-attempt-running",
        ),
        _event(3, source_event_id="executor-task-running"),
    )
    delivery = owner.reserve_next(
        page,
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-after-nonpresentable-prefix",
        unit_id="unit-after-nonpresentable-prefix",
    )
    assert delivery.event_seq == 3
    assert delivery.event_id == "event-3"
    owner.mark_text_adopted(
        TextPresentationAdoptionAck.from_delivery(
            delivery,
            adopted_at="2026-08-20T12:00:02Z",
        )
    )
    command, grant = _ack_command(delivery)
    assert owner.consume(
        delivery,
        command,
        grant,
        lambda item, _authorization: _success(item, delivery),
    ).ok

    unknown = replace(page.events[0], event_type="task.unclassified_control")
    with pytest.raises(TaskPresentationViolation) as rejected:
        owner.reserve_next(
            _page(unknown, page.events[1], page.events[2]),
            scope=SCOPE,
            response_ref=ResponseRef("interaction-1", "response-unknown", 1),
            delivery_id="delivery-unknown-prefix",
            unit_id="unit-unknown-prefix",
        )
    assert rejected.value.reason == "PRESENTATION_EVENT_APPLICABILITY_UNKNOWN"
    assert (
        runtime.calls.count(
            (ResponseRef("interaction-1", "response-unknown", 1), None, "reserve")
        )
        == 0
    )


@pytest.mark.asyncio
async def test_voice_accepts_only_exact_runtime_audio_presentation_ack() -> None:
    owner, _runtime = _owner()
    delivery = owner.reserve_next(
        _page(_event(0), presentation_class="voice"),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-voice",
        unit_id="unit-voice",
    )
    calls: list[tuple[CommandEnvelope, TaskAuthorizationGrant]] = []

    def command_port(item, authorization):
        calls.append((item, authorization))
        return _success(item, delivery)

    with pytest.raises(TaskPresentationViolation):
        owner.mark_text_adopted(
            TextPresentationAdoptionAck.from_delivery(
                delivery, adopted_at="2026-08-20T12:00:02Z"
            )
        )
    runtime_calls: list[PresentationAck] = []

    async def runtime_ack_port(ack: PresentationAck) -> PresentationAckResult:
        runtime_calls.append(ack)
        return PresentationAckResult(ack, True, False, 1, False)

    with pytest.raises(TaskPresentationViolation):
        await owner.mark_voice_presented(
            delivery,
            PresentationAck(
                ref=delivery.response_ref,
                surface=PresentationSurface.TEXT,
                unit_id=delivery.unit_id,
                contiguous_cursor=0,
                presented_at="2026-08-20T12:00:02Z",
            ),
            runtime_ack_port,
        )
    assert runtime_calls == []
    assert calls == []

    audio_ack = PresentationAck(
        ref=delivery.response_ref,
        surface=PresentationSurface.AUDIO,
        unit_id=delivery.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-20T12:00:02Z",
    )
    assert await owner.mark_voice_presented(delivery, audio_ack, runtime_ack_port)
    assert runtime_calls == [audio_ack]
    command, grant = _ack_command(delivery, command_id="command-voice-ack")
    assert owner.consume(delivery, command, grant, command_port).ok
    assert calls == [(command, grant)]


def test_frozen_prefix_terminal_result_and_generation_fail_closed() -> None:
    owner, _runtime = _owner()
    terminal = _event(
        0,
        event_type="task.terminal",
        state="terminal",
        outcome="completed",
    )
    with pytest.raises(TaskPresentationViolation) as missing_result:
        owner.reserve_next(
            _page(terminal),
            scope=SCOPE,
            response_ref=RESPONSE,
            delivery_id="delivery-terminal",
            unit_id="unit-terminal",
        )
    assert missing_result.value.reason == "COMPLETED_RESULT_REQUIRED"

    delivery = owner.reserve_next(
        _page(terminal),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-terminal",
        unit_id="unit-terminal",
        result=_result(terminal),
    )
    assert delivery.consumer_key == (
        SCOPE.subject_id,
        SCOPE.project_id,
        "task-1",
        "text",
    )
    with pytest.raises(ValueError):
        owner.reserve_next(
            _page(_event(1)),
            scope=replace(SCOPE, session_id="session-refresh"),
            response_ref=ResponseRef("interaction-1", "response-stale", 1),
            delivery_id="delivery-stale",
            unit_id="unit-stale",
        )


def test_gap_wrong_scope_fallback_and_ack_rewrite_have_zero_command_effect() -> None:
    owner, _runtime = _owner()
    calls: list[object] = []
    event = _event(1)
    bad_page = TaskUnreadPage(
        task_id="task-1",
        presentation_class="text",
        watermark=-1,
        acked_event_id=None,
        head_seq=1,
        events=(_event(0), event),
        next_after_seq=None,
        has_more=False,
    )
    delivery = owner.reserve_next(
        bad_page,
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-prefix",
        unit_id="unit-prefix",
    )
    assert delivery.event_seq == 0
    ack = TextPresentationAdoptionAck.from_delivery(
        delivery, adopted_at="2026-08-20T12:00:02Z"
    )
    assert owner.mark_text_adopted(ack)
    assert not owner.mark_text_adopted(ack)
    with pytest.raises(TaskPresentationViolation):
        owner.mark_text_adopted(replace(ack, task_id="task-other"))
    assert calls == []

    voice_owner, _voice_runtime = _owner()
    voice = voice_owner.reserve_next(
        _page(_event(0), presentation_class="voice"),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-fallback",
        unit_id="unit-fallback",
    )
    with pytest.raises(TaskPresentationViolation) as fallback:
        voice_owner.mark_text_adopted(
            TextPresentationAdoptionAck.from_delivery(
                voice, adopted_at="2026-08-20T12:00:02Z"
            )
        )
    assert fallback.value.reason in {
        "PRESENTATION_DELIVERY_NOT_FOUND",
        "TEXT_PRESENTATION_CLASS_REQUIRED",
    }
    assert calls == []


def test_real_core_port_advances_only_the_exact_presented_text_prefix(
    tmp_path: Path,
) -> None:
    database = tmp_path / "product-presentation-owner.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path, identity_suffix="-product-presentation-owner")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    scope = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-product-presentation-owner",
        Assurance.AUTHENTICATED,
    )
    page = store.unread_events_page(
        task_id, scope, presentation_class="text", limit=500
    )
    response = ResponseRef("interaction-real", "response-real", 1)
    owner, _runtime = _owner(response)
    delivery = owner.reserve_next(
        page,
        scope=scope,
        response_ref=response,
        delivery_id="delivery-real",
        unit_id="unit-real",
    )
    command, _ = _ack_command(delivery, command_id="command-real-ack")
    grant = replace(
        _grant(
            "task.ack_events",
            command_id=command.command_id,
            target=task_id,
        ),
        principal_id=scope.subject_id,
        scope=scope,
    )
    before = store.get_task(task_id, _scope())
    assert owner.mark_text_adopted(
        TextPresentationAdoptionAck.from_delivery(
            delivery, adopted_at="2026-08-20T12:00:02Z"
        )
    )
    occurred = datetime.fromisoformat(page.events[0].occurred_at[:-1] + "+00:00")
    observed_at = (occurred + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    committed_results: list[ResultEnvelope] = []

    def commit_then_lose_response(item, authorization):
        committed_results.append(core.execute(item, authorization, now=observed_at))
        raise RuntimeError("simulated ACK response loss")

    with pytest.raises(RuntimeError, match="response loss"):
        owner.consume(delivery, command, grant, commit_then_lose_response)
    assert len(committed_results) == 1 and committed_results[0].ok
    reopened_core = PersistentTaskCore(SqliteTaskStore(database), executor)
    result = owner.consume(
        delivery,
        command,
        grant,
        lambda item, authorization: reopened_core.execute(
            item, authorization, now=observed_at
        ),
    )
    assert result.ok and result.result is not None
    assert result.result["advanced"] is True
    after = store.get_task(task_id, _scope())
    assert after == before
    reopened_store = SqliteTaskStore(database)
    replay = reopened_store.unread_events_page(
        task_id, scope, presentation_class="text", limit=500
    )
    other_class = reopened_store.unread_events_page(
        task_id, scope, presentation_class="voice", limit=500
    )
    assert replay.watermark == delivery.event_seq
    assert other_class.watermark == -1
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.asyncio
async def test_replayed_rejected_audio_ack_never_enables_consumption() -> None:
    owner, _runtime = _owner()
    delivery = owner.reserve_next(
        _page(_event(0), presentation_class="voice"),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-rejected-replay",
        unit_id="unit-rejected-replay",
    )
    ack = PresentationAck(
        ref=RESPONSE,
        surface=PresentationSurface.AUDIO,
        unit_id=delivery.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-20T12:00:02Z",
    )

    async def rejected_replay(item: PresentationAck) -> PresentationAckResult:
        return PresentationAckResult(item, False, True, 0, False)

    with pytest.raises(TaskPresentationViolation) as rejected:
        await owner.mark_voice_presented(delivery, ack, rejected_replay)
    assert rejected.value.reason == "RUNTIME_PRESENTATION_ACK_REJECTED"
    command, grant = _ack_command(delivery, command_id="command-rejected-replay")
    command_calls: list[object] = []
    with pytest.raises(TaskPresentationViolation) as not_presented:
        owner.consume(
            delivery,
            command,
            grant,
            lambda *_args: command_calls.append(_args),
        )
    assert not_presented.value.reason == "PRESENTATION_ACK_REQUIRED"
    assert command_calls == []


def test_runtime_close_fences_dom_and_consume_and_releases_capacity() -> None:
    owner, runtime = _owner(capacity=1)
    delivery = owner.reserve_next(
        _page(_event(0)),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-close",
        unit_id="unit-close",
    )
    ack = TextPresentationAdoptionAck.from_delivery(
        delivery, adopted_at="2026-08-20T12:00:02Z"
    )
    assert owner.mark_text_adopted(ack)
    runtime.close(RESPONSE)
    assert (
        owner.close_response(
            RESPONSE,
            reservation_id=delivery.runtime_reservation_id,
            reason="route_closed",
        )
        == 1
    )
    assert RESPONSE not in runtime.active
    command, grant = _ack_command(delivery, command_id="command-after-close")
    command_calls: list[object] = []
    for late in (
        lambda: owner.mark_text_adopted(ack),
        lambda: owner.consume(
            delivery,
            command,
            grant,
            lambda *_args: command_calls.append(_args),
        ),
    ):
        with pytest.raises(TaskPresentationViolation):
            late()
    assert command_calls == []


def test_runtime_close_recycles_one_slot_across_more_than_global_bound() -> None:
    responses = tuple(
        ResponseRef("interaction-capacity", f"response-{index}", 1)
        for index in range(257)
    )
    owner, runtime = _owner(*responses, capacity=1)

    for index, response in enumerate(responses):
        delivery = owner.reserve_next(
            _page(_event(index)),
            scope=SCOPE,
            response_ref=response,
            delivery_id=f"delivery-capacity-{index}",
            unit_id=f"unit-capacity-{index}",
        )
        runtime.close(response)
        assert (
            owner.close_response(
                response,
                reservation_id=delivery.runtime_reservation_id,
                reason="route_closed",
            )
            == 1
        )

    assert runtime.active == set()
    assert sum(phase == "reserve" for _, _, phase in runtime.calls) == 257
    assert sum(phase == "close" for _, _, phase in runtime.calls) == 257


@pytest.mark.asyncio
async def test_close_while_runtime_audio_ack_is_in_flight_has_zero_consumption() -> (
    None
):
    owner, runtime = _owner()
    delivery = owner.reserve_next(
        _page(_event(0), presentation_class="voice"),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-audio-close-race",
        unit_id="unit-audio-close-race",
    )
    ack = PresentationAck(
        ref=RESPONSE,
        surface=PresentationSurface.AUDIO,
        unit_id=delivery.unit_id,
        contiguous_cursor=0,
        presented_at="2026-08-20T12:00:02Z",
    )
    started = __import__("asyncio").Event()
    release = __import__("asyncio").Event()

    async def delayed_runtime_ack(item: PresentationAck) -> PresentationAckResult:
        started.set()
        await release.wait()
        return PresentationAckResult(item, True, False, 0, False)

    task = __import__("asyncio").create_task(
        owner.mark_voice_presented(delivery, ack, delayed_runtime_ack)
    )
    await started.wait()
    runtime.close(RESPONSE)
    assert (
        owner.close_response(
            RESPONSE,
            reservation_id=delivery.runtime_reservation_id,
            reason="route_closed",
        )
        == 1
    )
    release.set()
    with pytest.raises(TaskPresentationViolation) as late:
        await task
    assert late.value.reason == "PRESENTATION_DELIVERY_NOT_FOUND"


def test_duplicate_text_ack_is_single_winner_under_concurrency() -> None:
    owner, _runtime = _owner()
    delivery = owner.reserve_next(
        _page(_event(0)),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-concurrent-dom",
        unit_id="unit-concurrent-dom",
    )
    ack = TextPresentationAdoptionAck.from_delivery(
        delivery, adopted_at="2026-08-20T12:00:02Z"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(
            pool.map(lambda _index: owner.mark_text_adopted(ack), range(2))
        )
    assert sorted(outcomes) == [False, True]


def test_two_concurrent_commands_for_one_delivery_have_one_port_winner() -> None:
    runtime = _RuntimeAuthority(RESPONSE)
    consume_barrier = threading.Barrier(2)

    def authority_port(ref, reservation_id, phase):
        receipt = runtime(ref, reservation_id, phase)
        if phase == "consume":
            consume_barrier.wait(timeout=5)
        return receipt

    owner = TaskPresentationConsumptionOwner(authority_port)
    delivery = owner.reserve_next(
        _page(_event(0)),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-concurrent-consume",
        unit_id="unit-concurrent-consume",
    )
    assert owner.mark_text_adopted(
        TextPresentationAdoptionAck.from_delivery(
            delivery, adopted_at="2026-08-20T12:00:02Z"
        )
    )
    first = _ack_command(delivery, command_id="command-concurrent-a")
    second = _ack_command(delivery, command_id="command-concurrent-b")
    command_calls: list[str] = []

    def command_port(command, _authorization):
        command_calls.append(command.command_id)
        return _success(command, delivery)

    def consume(pair):
        try:
            return owner.consume(delivery, pair[0], pair[1], command_port)
        except TaskPresentationViolation as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(consume, (first, second)))
    assert sum(isinstance(item, ResultEnvelope) for item in outcomes) == 1
    assert [
        item.reason for item in outcomes if isinstance(item, TaskPresentationViolation)
    ] == ["CONSUMPTION_COMMAND_REWRITE"]
    assert len(command_calls) == 1


def test_runtime_close_linearizes_against_pending_reservation() -> None:
    runtime = _RuntimeAuthority(RESPONSE)
    reserve_started = threading.Event()
    release_reserve = threading.Event()

    def authority_port(ref, reservation_id, phase):
        receipt = runtime(ref, reservation_id, phase)
        if phase == "reserve" and ref == RESPONSE:
            reserve_started.set()
            assert release_reserve.wait(timeout=5)
        return receipt

    owner = TaskPresentationConsumptionOwner(authority_port, capacity=1)

    def reserve():
        return owner.reserve_next(
            _page(_event(0)),
            scope=SCOPE,
            response_ref=RESPONSE,
            delivery_id="delivery-close-reserve-race",
            unit_id="unit-close-reserve-race",
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reserve)
        assert reserve_started.wait(timeout=5)
        reservation_id = runtime.reservation_id(RESPONSE)
        runtime.close(RESPONSE)
        assert (
            owner.close_response(
                RESPONSE,
                reservation_id=reservation_id,
                reason="route_closed",
            )
            == 0
        )
        release_reserve.set()
        with pytest.raises(TaskPresentationViolation) as stale:
            future.result(timeout=5)
    assert stale.value.reason == "PRESENTATION_RESPONSE_CLOSED"

    successor = ResponseRef("interaction-1", "response-successor", 2)
    runtime.active.add(successor)
    delivery = owner.reserve_next(
        _page(_event(0)),
        scope=SCOPE,
        response_ref=successor,
        delivery_id="delivery-after-close-race",
        unit_id="unit-after-close-race",
    )
    assert delivery.response_ref == successor


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "interrupted", "unknown"])
def test_noncompleted_terminal_outcomes_forbid_result(
    outcome: str,
) -> None:
    owner, _runtime = _owner()
    terminal = _event(
        0,
        event_type="task.terminal",
        state="terminal",
        outcome=outcome,
    )
    delivery = owner.reserve_next(
        _page(terminal),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id=f"delivery-terminal-{outcome}",
        unit_id=f"unit-terminal-{outcome}",
    )
    assert delivery.result_source_event_id is None
    with pytest.raises(TaskPresentationViolation) as fabricated:
        owner.reserve_next(
            _page(terminal),
            scope=SCOPE,
            response_ref=RESPONSE,
            delivery_id=f"delivery-terminal-{outcome}-result",
            unit_id=f"unit-terminal-{outcome}-result",
            result=_result(terminal),
        )
    assert fabricated.value.reason == "UNEXPECTED_PRESENTATION_RESULT"
