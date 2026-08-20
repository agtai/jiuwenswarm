# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    ContractViolation,
    QueryEnvelope,
    ResponseRef,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.formal_task_models import TaskResultArtifact
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.presentation_ledger import (
    PresentationAck,
    PresentationSurface,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.presentation_ack_oracle_harness import (
    DeliveryAttempt,
    PresentationAttemptHarness,
    PresentationOracleViolation,
    text_adoption_ack,
)
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW,
    _create,
    _events,
    _Executor,
    _grant,
    _observations,
    _scope,
    _wave2_command,
)


def _create_task(store: SqliteTaskStore, tmp_path: Path, *, suffix: str) -> str:
    invocation = _create(tmp_path, identity_suffix=suffix)
    result = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert result.ok and result.result is not None
    return str(result.result["task_id"])


def _complete_task(
    store: SqliteTaskStore,
    tmp_path: Path,
    task_id: str,
    *,
    outcome: TerminalOutcome,
) -> None:
    item = store.claim_outbox(f"worker-{task_id}")
    assert item is not None
    if outcome is TerminalOutcome.COMPLETED:
        artifact_path = tmp_path / f"{item.attempt_id}-presentation-result.txt"
        artifact_bytes = b"immutable presentation oracle result\n"
        artifact_path.write_bytes(artifact_bytes)
        artifacts = (
            TaskResultArtifact(
                relative_path=artifact_path.name,
                sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            ),
        )
        result_text = "completed presentation oracle result"
    else:
        artifacts = ()
        result_text = None
    observations = _observations(
        item,
        outcome=outcome,
        result_text=result_text,
        result_artifacts=artifacts,
    )
    base_time = datetime.fromisoformat(NOW[:-1] + "+00:00")
    observations = tuple(
        replace(
            observation,
            occurred_at=(base_time + timedelta(seconds=index + 1))
            .isoformat()
            .replace("+00:00", "Z"),
        )
        for index, observation in enumerate(observations)
    )
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )


def _query(
    task_id: str,
    scope: ScopeRef,
    query_type: str,
    payload: dict[str, object],
    *,
    request_id: str,
) -> QueryEnvelope:
    raw = _events(task_id, -1).envelope.to_dict()
    raw.update(
        {
            "request_id": request_id,
            "query_type": query_type,
            "scope": scope.to_dict(),
            "required_capabilities": [query_type],
            "payload": payload,
        }
    )
    return QueryEnvelope.from_dict(raw)


def _grant_in_scope(
    operation: str,
    scope: ScopeRef,
    *,
    command_id: str | None,
    task_id: str,
):
    return replace(
        _grant(operation, command_id=command_id, target=task_id),
        principal_id=scope.subject_id,
        scope=scope,
    )


def _unread(
    core: PersistentTaskCore,
    task_id: str,
    scope: ScopeRef,
    presentation_class: str,
    *,
    request_id: str,
    limit: int = 500,
) -> dict[str, object]:
    result = core.query(
        _query(
            task_id,
            scope,
            "task.unread_events",
            {"presentation_class": presentation_class, "limit": limit},
            request_id=request_id,
        ),
        _grant_in_scope(
            "task.unread_events",
            scope,
            command_id=None,
            task_id=task_id,
        ),
        now=NOW,
    )
    assert result.ok and result.result is not None
    return dict(result.result)


def _task_result(
    core: PersistentTaskCore,
    task_id: str,
    scope: ScopeRef,
    *,
    request_id: str,
) -> dict[str, object]:
    result = core.query(
        _query(task_id, scope, "task.result", {}, request_id=request_id),
        _grant_in_scope("task.result", scope, command_id=None, task_id=task_id),
        now=NOW,
    )
    assert result.ok and result.result is not None
    return dict(result.result)


def _delivery(
    core: PersistentTaskCore,
    page: dict[str, object],
    scope: ScopeRef,
    *,
    interaction_id: str,
    response_id: str,
    generation: int,
    delivery_id: str,
) -> DeliveryAttempt:
    events = page["events"]
    assert isinstance(events, list) and events
    event = events[-1]
    assert isinstance(event, dict)
    result_source_event_id: str | None = None
    if event["event_type"] == "task.terminal":
        event_scope = ScopeRef.from_dict(event["scope"])
        result = _task_result(
            core,
            str(page["task_id"]),
            event_scope,
            request_id=f"request-result-{delivery_id}",
        )
        if event["outcome"] == TerminalOutcome.COMPLETED.value:
            assert result["availability"] == "available"
            task_result = result["task_result"]
            assert isinstance(task_result, dict)
            assert task_result["task_id"] == event["task_id"]
            assert task_result["attempt_id"] == event["attempt_id"]
            assert task_result["source_event_id"] == event["source_event_id"]
            result_source_event_id = str(task_result["source_event_id"])
        else:
            assert result["task_result"] is None
    return DeliveryAttempt(
        scope=scope,
        presentation_class=str(page["presentation_class"]),
        task_id=str(page["task_id"]),
        attempt_id=str(event["attempt_id"]),
        event_id=str(event["event_id"]),
        event_seq=int(event["seq"]),
        expected_event_head=int(page["head_seq"]),
        result_source_event_id=result_source_event_id,
        response_ref=ResponseRef(interaction_id, response_id, generation),
        delivery_id=delivery_id,
        unit_id=f"unit-{delivery_id}",
    )


def _accept_presentation(
    harness: PresentationAttemptHarness,
    delivery: DeliveryAttempt,
) -> None:
    assert harness.publish(delivery) is True
    if delivery.presentation_class == "text":
        assert harness.accept_text(text_adoption_ack(delivery)) is True
    else:
        assert (
            harness.accept_voice(
                delivery,
                PresentationAck(
                    ref=delivery.response_ref,
                    surface=PresentationSurface.AUDIO,
                    unit_id=delivery.unit_id,
                    contiguous_cursor=0,
                    presented_at="2026-08-19T12:00:01Z",
                ),
            )
            is True
        )
    assert harness.presentation_accepted(delivery)


def _consumer_rows(database: Path) -> list[tuple[object, ...]]:
    with sqlite3.connect(database) as connection:
        return connection.execute(
            """SELECT subject_id, project_id, task_id, presentation_class,
                      acked_through_seq, acked_event_id
               FROM task_event_consumption
               ORDER BY subject_id, project_id, task_id, presentation_class"""
        ).fetchall()


def _authority_rows(
    database: Path, *, include_consumption: bool
) -> dict[str, list[tuple[object, ...]]]:
    tables = [
        "tasks",
        "attempts",
        "task_events",
        "executor_events",
        "task_results",
        "outbox",
        "current_background_tasks",
    ]
    if include_consumption:
        tables.extend(("commands", "task_event_consumption"))
    with sqlite3.connect(database) as connection:
        return {
            table: connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall()
            for table in tables
        }


def _after(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    return (parsed + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")


def _ack_inputs(
    delivery: DeliveryAttempt,
    *,
    command_id: str,
) -> tuple[CommandEnvelope, object]:
    base, _unused_grant = _wave2_command(
        delivery.task_id,
        "task.ack_events",
        {
            "presentation_class": delivery.presentation_class,
            "acked_through_seq": delivery.event_seq,
            "acked_event_id": delivery.event_id,
            "expected_event_head": delivery.expected_event_head,
        },
        command_id=command_id,
    )
    raw = base.to_dict()
    raw["scope"] = delivery.scope.to_dict()
    command = CommandEnvelope.from_dict(raw)
    return (
        command,
        _grant_in_scope(
            "task.ack_events",
            delivery.scope,
            command_id=command.command_id,
            task_id=delivery.task_id,
        ),
    )


def _terminal_delivery(
    core: PersistentTaskCore,
    page: dict[str, object],
    scope: ScopeRef,
    **identity: object,
) -> DeliveryAttempt:
    events = page["events"]
    if not isinstance(events, list) or not events:
        raise PresentationOracleViolation(
            "TERMINAL_EVENT_REQUIRED", "terminal delivery requires one event"
        )
    event = events[-1]
    if (
        not isinstance(event, dict)
        or event.get("event_type") != "task.terminal"
        or event.get("state") != "terminal"
        or event.get("outcome") not in {outcome.value for outcome in TerminalOutcome}
    ):
        raise PresentationOracleViolation(
            "TERMINAL_EVENT_REQUIRED",
            "terminal notification identity must be the canonical terminal TaskEvent",
        )
    return _delivery(core, page, scope, **identity)  # type: ignore[arg-type]


@pytest.mark.parametrize("presentation_class", ("text", "voice"))
def test_unacked_presentation_replays_across_every_precommit_crash_boundary(
    tmp_path: Path,
    presentation_class: str,
) -> None:
    database = tmp_path / f"presentation-precommit-{presentation_class}.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(
        setup, tmp_path, suffix=f"-presentation-precommit-{presentation_class}"
    )
    _complete_task(setup, tmp_path, task_id, outcome=TerminalOutcome.COMPLETED)
    expected_event_ids = [event.event_id for event in setup.events(task_id, _scope())]
    executor = _Executor()

    def reopened(
        session_id: str, request_id: str
    ) -> tuple[PersistentTaskCore, ScopeRef, dict[str, object]]:
        scope = ScopeRef(
            _scope().subject_id,
            _scope().project_id,
            session_id,
            Assurance.AUTHENTICATED,
        )
        core = PersistentTaskCore(SqliteTaskStore(database), executor)
        return (
            core,
            scope,
            _unread(
                core,
                task_id,
                scope,
                presentation_class,
                request_id=request_id,
            ),
        )

    # No active interaction: no response, presentation, or durable consumption.
    core, scope, page = reopened("session-no-active", "request-no-active")
    assert [event["event_id"] for event in page["events"]] == expected_event_ids
    assert _consumer_rows(database) == []

    # Crash after reservation but before publish.
    reserved = _delivery(
        core,
        page,
        scope,
        interaction_id="interaction-before-publish",
        response_id="response-before-publish",
        generation=1,
        delivery_id="delivery-before-publish",
    )
    before_publish = PresentationAttemptHarness()
    before_publish.reserve(reserved)
    assert before_publish.effects().external_effects == 0
    del before_publish
    core, scope, page = reopened("session-after-reserve", "request-after-reserve")
    assert [event["event_id"] for event in page["events"]] == expected_event_ids

    # DOM adoption/audio playout occurred, but no presentation ACK was accepted.
    published = _delivery(
        core,
        page,
        scope,
        interaction_id="interaction-before-presentation-ack",
        response_id="response-before-presentation-ack",
        generation=1,
        delivery_id="delivery-before-presentation-ack",
    )
    before_presentation_ack = PresentationAttemptHarness()
    before_presentation_ack.reserve(published)
    assert before_presentation_ack.publish(published) is True
    assert before_presentation_ack.effects().legal_presentation_effects == 1
    del before_presentation_ack
    core, scope, page = reopened(
        "session-after-presentation", "request-after-presentation"
    )
    assert [event["event_id"] for event in page["events"]] == expected_event_ids

    # Presentation ACK was accepted, but the durable consumption Port was not called.
    acknowledged = _delivery(
        core,
        page,
        scope,
        interaction_id="interaction-before-consumption",
        response_id="response-before-consumption",
        generation=1,
        delivery_id="delivery-before-consumption",
    )
    before_consumption = PresentationAttemptHarness()
    before_consumption.reserve(acknowledged)
    _accept_presentation(before_consumption, acknowledged)
    del before_consumption

    for restart in range(3):
        _core, _scope_at_restart, replay = reopened(
            f"session-restart-{restart}", f"request-restart-{restart}"
        )
        assert [event["event_id"] for event in replay["events"]] == expected_event_ids
        assert replay["watermark"] == -1
        assert _consumer_rows(database) == []

    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_consumption_commit_survives_response_loss_and_repeated_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "presentation-response-loss.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-presentation-response-loss")
    _complete_task(store, tmp_path, task_id, outcome=TerminalOutcome.COMPLETED)
    scope = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-consumption",
        Assurance.AUTHENTICATED,
    )
    executor = _Executor()
    core = PersistentTaskCore(SqliteTaskStore(database), executor)
    page = _unread(
        core,
        task_id,
        scope,
        "text",
        request_id="request-response-loss",
    )
    delivery = _terminal_delivery(
        core,
        page,
        scope,
        interaction_id="interaction-response-loss",
        response_id="response-response-loss",
        generation=3,
        delivery_id="delivery-response-loss",
    )
    presentation = PresentationAttemptHarness()
    presentation.reserve(delivery)
    _accept_presentation(presentation, delivery)
    command, grant = _ack_inputs(delivery, command_id="command-response-loss")
    before_nonconsumption = _authority_rows(database, include_consumption=False)
    event = page["events"][-1]
    assert isinstance(event, dict)

    # The caller loses this successful response after commit.
    lost_response = core.execute(command, grant, now=_after(str(event["occurred_at"])))
    assert lost_response.ok
    assert _authority_rows(database, include_consumption=False) == before_nonconsumption
    committed_authority = _authority_rows(database, include_consumption=True)

    # Reissuing the exact command after process restarts returns the original result.
    for _restart in range(3):
        replay = PersistentTaskCore(SqliteTaskStore(database), executor).execute(
            command, grant, now=_after(str(event["occurred_at"]))
        )
        assert replay == lost_response
        assert (
            _authority_rows(database, include_consumption=True) == committed_authority
        )

    refreshed_scope = ScopeRef(
        scope.subject_id,
        scope.project_id,
        "session-after-consumption",
        Assurance.AUTHENTICATED,
    )
    refreshed = PersistentTaskCore(SqliteTaskStore(database), executor)
    text_page = _unread(
        refreshed,
        task_id,
        refreshed_scope,
        "text",
        request_id="request-text-consumed",
    )
    voice_page = _unread(
        refreshed,
        task_id,
        refreshed_scope,
        "voice",
        request_id="request-voice-independent",
    )
    assert text_page["events"] == []
    assert text_page["watermark"] == delivery.event_seq
    assert [event["event_id"] for event in voice_page["events"]]
    assert voice_page["watermark"] == -1
    assert _consumer_rows(database) == [
        (
            scope.subject_id,
            scope.project_id,
            task_id,
            "text",
            delivery.event_seq,
            delivery.event_id,
        )
    ]

    for foreign_scope in (
        ScopeRef(
            "foreign-subject",
            scope.project_id,
            "session-foreign",
            Assurance.AUTHENTICATED,
        ),
        ScopeRef(
            scope.subject_id,
            "foreign-project",
            "session-foreign",
            Assurance.AUTHENTICATED,
        ),
    ):
        denied = refreshed.query(
            _query(
                task_id,
                foreign_scope,
                "task.unread_events",
                {"presentation_class": "text", "limit": 500},
                request_id=f"request-foreign-{foreign_scope.subject_id}",
            ),
            _grant_in_scope(
                "task.unread_events",
                foreign_scope,
                command_id=None,
                task_id=task_id,
            ),
            now=NOW,
        )
        assert not denied.ok and denied.error is not None
        assert denied.error.reason == "TASK_NOT_FOUND"
        assert (
            _authority_rows(database, include_consumption=True) == committed_authority
        )

    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.parametrize("presentation_class", ("text", "voice"))
def test_ack_transaction_crash_after_presentation_is_zero_effect_and_retryable(
    tmp_path: Path,
    presentation_class: str,
) -> None:
    database = tmp_path / f"presentation-ack-crash-{presentation_class}.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(
        setup, tmp_path, suffix=f"-presentation-ack-crash-{presentation_class}"
    )
    _complete_task(setup, tmp_path, task_id, outcome=TerminalOutcome.COMPLETED)
    scope = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        f"session-ack-crash-{presentation_class}",
        Assurance.AUTHENTICATED,
    )
    executor = _Executor()
    read_core = PersistentTaskCore(SqliteTaskStore(database), executor)
    page = _unread(
        read_core,
        task_id,
        scope,
        presentation_class,
        request_id=f"request-ack-crash-{presentation_class}",
    )
    delivery = _terminal_delivery(
        read_core,
        page,
        scope,
        interaction_id=f"interaction-ack-crash-{presentation_class}",
        response_id=f"response-ack-crash-{presentation_class}",
        generation=1,
        delivery_id=f"delivery-ack-crash-{presentation_class}",
    )
    presentation = PresentationAttemptHarness()
    presentation.reserve(delivery)
    _accept_presentation(presentation, delivery)
    command, grant = _ack_inputs(
        delivery, command_id=f"command-ack-crash-{presentation_class}"
    )
    event = page["events"][-1]
    assert isinstance(event, dict)
    before = _authority_rows(database, include_consumption=True)

    def failpoint(name: str) -> None:
        if name == "ack_events.before_commit":
            raise RuntimeError("injected ACK commit crash")

    crashing_core = PersistentTaskCore(
        SqliteTaskStore(database, failpoint=failpoint), executor
    )
    with pytest.raises(RuntimeError, match="injected ACK commit crash"):
        crashing_core.execute(command, grant, now=_after(str(event["occurred_at"])))

    assert _authority_rows(database, include_consumption=True) == before
    reopened = PersistentTaskCore(SqliteTaskStore(database), executor)
    replay = _unread(
        reopened,
        task_id,
        scope,
        presentation_class,
        request_id=f"request-after-ack-crash-{presentation_class}",
    )
    assert [item["event_id"] for item in replay["events"]]
    assert replay["watermark"] == -1

    applied = reopened.execute(command, grant, now=_after(str(event["occurred_at"])))
    assert applied.ok and applied.result is not None
    assert applied.result["advanced"] is True
    assert _authority_rows(database, include_consumption=False) == {
        key: value
        for key, value in before.items()
        if key
        not in {
            "commands",
            "task_event_consumption",
        }
    }
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_wrong_delivery_tuple_stale_generation_and_cross_class_ack_are_zero_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "presentation-identity.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-presentation-identity")
    _complete_task(store, tmp_path, task_id, outcome=TerminalOutcome.COMPLETED)
    scope = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-presentation-identity",
        Assurance.AUTHENTICATED,
    )
    executor = _Executor()
    core = PersistentTaskCore(SqliteTaskStore(database), executor)
    text_page = _unread(
        core,
        task_id,
        scope,
        "text",
        request_id="request-presentation-identity-text",
    )
    text_delivery = _terminal_delivery(
        core,
        text_page,
        scope,
        interaction_id="interaction-presentation-identity",
        response_id="response-presentation-identity-1",
        generation=1,
        delivery_id="delivery-presentation-identity-1",
    )
    harness = PresentationAttemptHarness()
    harness.reserve(text_delivery)
    assert harness.publish(text_delivery) is True
    before_ack_effects = harness.effects()
    before_authority = _authority_rows(database, include_consumption=True)
    valid_text_ack = text_adoption_ack(text_delivery)
    assert valid_text_ack.result_source_event_id is not None

    wrong_scope = ScopeRef(
        "foreign-subject",
        scope.project_id,
        "session-foreign",
        Assurance.AUTHENTICATED,
    )
    wrong_session = ScopeRef(
        scope.subject_id,
        scope.project_id,
        "session-foreign",
        Assurance.AUTHENTICATED,
    )
    wrong_acks = (
        replace(valid_text_ack, scope=wrong_scope),
        replace(valid_text_ack, scope=wrong_session),
        replace(valid_text_ack, presentation_class="voice"),
        replace(valid_text_ack, task_id="task-foreign"),
        replace(valid_text_ack, attempt_id="attempt-foreign"),
        replace(valid_text_ack, event_id="event-foreign"),
        replace(valid_text_ack, event_seq=valid_text_ack.event_seq - 1),
        replace(
            valid_text_ack,
            expected_event_head=valid_text_ack.expected_event_head + 1,
        ),
        replace(valid_text_ack, result_source_event_id="result-source-foreign"),
        replace(
            valid_text_ack,
            response_ref=ResponseRef(
                "interaction-foreign",
                valid_text_ack.response_ref.response_id,
                valid_text_ack.response_ref.response_generation,
            ),
        ),
        replace(
            valid_text_ack,
            response_ref=ResponseRef(
                valid_text_ack.response_ref.interaction_id,
                "response-foreign",
                valid_text_ack.response_ref.response_generation,
            ),
        ),
        replace(
            valid_text_ack,
            response_ref=ResponseRef(
                valid_text_ack.response_ref.interaction_id,
                valid_text_ack.response_ref.response_id,
                valid_text_ack.response_ref.response_generation + 1,
            ),
        ),
        replace(valid_text_ack, delivery_id="delivery-foreign"),
        replace(valid_text_ack, unit_id="unit-foreign"),
    )
    for wrong_ack in wrong_acks:
        with pytest.raises(PresentationOracleViolation):
            harness.accept_text(wrong_ack)
        assert harness.effects() == before_ack_effects
        assert _authority_rows(database, include_consumption=True) == before_authority

    assert harness.accept_text(valid_text_ack) is True
    assert harness.presentation_accepted(text_delivery)
    newer_text = replace(
        text_delivery,
        response_ref=ResponseRef(
            text_delivery.response_ref.interaction_id,
            "response-presentation-identity-2",
            2,
        ),
        delivery_id="delivery-presentation-identity-2",
        unit_id="unit-delivery-presentation-identity-2",
    )
    harness.reserve(newer_text)
    with pytest.raises(ContractViolation) as stale_publish:
        harness.publish(text_delivery)
    assert stale_publish.value.reason == "STALE_RESPONSE_OUTPUT"
    with pytest.raises(ContractViolation) as stale_ack:
        harness.accept_text(valid_text_ack)
    assert stale_ack.value.reason == "STALE_RESPONSE_OUTPUT"
    assert _authority_rows(database, include_consumption=True) == before_authority

    voice_page = _unread(
        core,
        task_id,
        scope,
        "voice",
        request_id="request-presentation-identity-voice",
    )
    voice_delivery = _terminal_delivery(
        core,
        voice_page,
        scope,
        interaction_id="interaction-presentation-identity-voice",
        response_id="response-presentation-identity-voice",
        generation=1,
        delivery_id="delivery-presentation-identity-voice",
    )
    voice_harness = PresentationAttemptHarness()
    voice_harness.reserve(voice_delivery)
    assert voice_harness.publish(voice_delivery) is True
    with pytest.raises(PresentationOracleViolation):
        voice_harness.accept_text(text_adoption_ack(voice_delivery))
    for wrong_ack in (
        PresentationAck(
            ref=voice_delivery.response_ref,
            surface=PresentationSurface.TEXT,
            unit_id=voice_delivery.unit_id,
            contiguous_cursor=0,
            presented_at="2026-08-19T12:00:01Z",
        ),
        PresentationAck(
            ref=voice_delivery.response_ref,
            surface=PresentationSurface.AUDIO,
            unit_id="unit-foreign",
            contiguous_cursor=0,
            presented_at="2026-08-19T12:00:01Z",
        ),
        PresentationAck(
            ref=voice_delivery.response_ref,
            surface=PresentationSurface.AUDIO,
            unit_id=voice_delivery.unit_id,
            contiguous_cursor=1,
            presented_at="2026-08-19T12:00:01Z",
        ),
    ):
        with pytest.raises(ValueError):
            voice_harness.accept_voice(voice_delivery, wrong_ack)
        assert not voice_harness.presentation_accepted(voice_delivery)
        assert _authority_rows(database, include_consumption=True) == before_authority

    assert voice_harness.accept_voice(
        voice_delivery,
        PresentationAck(
            ref=voice_delivery.response_ref,
            surface=PresentationSurface.AUDIO,
            unit_id=voice_delivery.unit_id,
            contiguous_cursor=0,
            presented_at="2026-08-19T12:00:01Z",
        ),
    )
    assert voice_harness.presentation_accepted(voice_delivery)
    assert harness.effects().external_effects == 0
    assert voice_harness.effects().external_effects == 0
    assert _authority_rows(database, include_consumption=True) == before_authority
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.parametrize("outcome", tuple(TerminalOutcome))
def test_terminal_notification_uses_canonical_event_and_legal_result_truth(
    tmp_path: Path,
    outcome: TerminalOutcome,
) -> None:
    database = tmp_path / f"presentation-terminal-{outcome.value}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(
        store, tmp_path, suffix=f"-presentation-terminal-{outcome.value}"
    )
    _complete_task(store, tmp_path, task_id, outcome=outcome)
    scope = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        f"session-terminal-{outcome.value}",
        Assurance.AUTHENTICATED,
    )
    executor = _Executor()
    core = PersistentTaskCore(SqliteTaskStore(database), executor)
    page = _unread(
        core,
        task_id,
        scope,
        "text",
        request_id=f"request-terminal-{outcome.value}",
    )
    delivery = _terminal_delivery(
        core,
        page,
        scope,
        interaction_id=f"interaction-terminal-{outcome.value}",
        response_id=f"response-terminal-{outcome.value}",
        generation=1,
        delivery_id=f"delivery-terminal-{outcome.value}",
    )
    terminal = page["events"][-1]
    assert isinstance(terminal, dict)
    assert terminal["event_type"] == "task.terminal"
    assert terminal["event_id"] == delivery.event_id
    assert terminal["attempt_id"] == delivery.attempt_id
    assert terminal["outcome"] == outcome.value
    original_scope = ScopeRef.from_dict(terminal["scope"])
    result = _task_result(
        core,
        task_id,
        original_scope,
        request_id=f"request-terminal-result-{outcome.value}",
    )
    if outcome is TerminalOutcome.COMPLETED:
        assert result["availability"] == "available"
        task_result = result["task_result"]
        assert isinstance(task_result, dict)
        assert task_result["task_id"] == delivery.task_id
        assert task_result["attempt_id"] == delivery.attempt_id
        assert task_result["source_event_id"] == delivery.result_source_event_id
    else:
        assert result["availability"] != "available"
        assert result["task_result"] is None
        assert delivery.result_source_event_id is None
    assert _consumer_rows(database) == []
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_nonterminal_or_forged_state_cannot_become_terminal_notification(
    tmp_path: Path,
) -> None:
    database = tmp_path / "presentation-nonterminal.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-presentation-nonterminal")
    scope = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-nonterminal",
        Assurance.AUTHENTICATED,
    )
    executor = _Executor()
    core = PersistentTaskCore(SqliteTaskStore(database), executor)
    accepted_page = _unread(
        core,
        task_id,
        scope,
        "text",
        request_id="request-accepted-not-terminal",
    )
    before = _authority_rows(database, include_consumption=True)
    identity = {
        "interaction_id": "interaction-not-terminal",
        "response_id": "response-not-terminal",
        "generation": 1,
        "delivery_id": "delivery-not-terminal",
    }
    with pytest.raises(PresentationOracleViolation) as accepted:
        _terminal_delivery(core, accepted_page, scope, **identity)
    assert accepted.value.reason == "TERMINAL_EVENT_REQUIRED"

    for forged_state in ("queued", "running", "applied"):
        forged_page = dict(accepted_page)
        forged_events = [dict(event) for event in accepted_page["events"]]
        forged_events[-1]["event_type"] = "task.terminal"
        forged_events[-1]["state"] = forged_state
        forged_events[-1]["outcome"] = None
        forged_page["events"] = forged_events
        with pytest.raises(PresentationOracleViolation) as forged:
            _terminal_delivery(core, forged_page, scope, **identity)
        assert forged.value.reason == "TERMINAL_EVENT_REQUIRED"

    assert _authority_rows(database, include_consumption=True) == before
    assert _consumer_rows(database) == []
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
