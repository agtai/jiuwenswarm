# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

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
    owner = TaskPresentationConsumptionOwner()
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
    result = owner.consume(delivery, command, grant, command_port)
    assert result.ok
    assert command_calls == [(command, grant)]


@pytest.mark.asyncio
async def test_voice_accepts_only_exact_runtime_audio_presentation_ack() -> None:
    owner = TaskPresentationConsumptionOwner()
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
    owner = TaskPresentationConsumptionOwner()
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
    owner = TaskPresentationConsumptionOwner()
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

    voice = TaskPresentationConsumptionOwner().reserve_next(
        _page(_event(0), presentation_class="voice"),
        scope=SCOPE,
        response_ref=RESPONSE,
        delivery_id="delivery-fallback",
        unit_id="unit-fallback",
    )
    with pytest.raises(TaskPresentationViolation) as fallback:
        TaskPresentationConsumptionOwner().mark_text_adopted(
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
    owner = TaskPresentationConsumptionOwner()
    delivery = owner.reserve_next(
        page,
        scope=scope,
        response_ref=ResponseRef("interaction-real", "response-real", 1),
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
    result = owner.consume(
        delivery,
        command,
        grant,
        lambda item, authorization: core.execute(item, authorization, now=observed_at),
    )
    assert result.ok and result.result is not None
    assert result.result["advanced"] is True
    after = store.get_task(task_id, _scope())
    assert after == before
    replay = store.unread_events_page(
        task_id, scope, presentation_class="text", limit=500
    )
    other_class = store.unread_events_page(
        task_id, scope, presentation_class="voice", limit=500
    )
    assert replay.watermark == delivery.event_seq
    assert other_class.watermark == -1
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
