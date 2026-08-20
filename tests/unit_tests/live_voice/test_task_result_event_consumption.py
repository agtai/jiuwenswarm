# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    CommandEnvelope,
    ErrorCode,
    QueryEnvelope,
    ScopeRef,
    TerminalOutcome,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    FormalTaskViolation,
    TaskResultArtifact,
    TaskResultAvailability,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW,
    _create,
    _Executor,
    _events,
    _grant,
    _observations,
    _scope,
    _wave2_command,
)


def _create_task(store: SqliteTaskStore, tmp_path: Path, *, suffix: str) -> str:
    invocation = _create(tmp_path, identity_suffix=suffix)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    return str(created.result["task_id"])


def _consumer_rows(database: Path) -> list[tuple[object, ...]]:
    with sqlite3.connect(database) as connection:
        return connection.execute(
            """SELECT subject_id, project_id, task_id, presentation_class,
                      acked_through_seq, acked_event_id, updated_at
               FROM task_event_consumption
               ORDER BY subject_id, project_id, task_id, presentation_class"""
        ).fetchall()


def _schema_identity(database: Path) -> tuple[object, ...]:
    with sqlite3.connect(database) as connection:
        return (
            connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone(),
            connection.execute(
                """SELECT type, name, tbl_name, sql FROM sqlite_master
                   WHERE name NOT LIKE 'sqlite_%'
                   ORDER BY type, name"""
            ).fetchall(),
        )


def _nonconsumption_authority(database: Path) -> dict[str, list[tuple[object, ...]]]:
    tables = (
        "tasks",
        "attempts",
        "task_events",
        "executor_events",
        "task_results",
        "outbox",
        "current_background_tasks",
    )
    with sqlite3.connect(database) as connection:
        return {
            table: connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall()
            for table in tables
        }


def _ack_command(
    task_id: str,
    *,
    presentation_class: str,
    acked_through_seq: int,
    acked_event_id: str,
    expected_event_head: int,
    command_id: str,
):
    return _wave2_command(
        task_id,
        "task.ack_events",
        {
            "presentation_class": presentation_class,
            "acked_through_seq": acked_through_seq,
            "acked_event_id": acked_event_id,
            "expected_event_head": expected_event_head,
        },
        command_id=command_id,
    )


def _command_in_scope(command: CommandEnvelope, scope: ScopeRef) -> CommandEnvelope:
    payload = command.to_dict()
    payload["scope"] = scope.to_dict()
    return CommandEnvelope.from_dict(payload)


def _unread_query(
    task_id: str,
    scope: ScopeRef,
    *,
    presentation_class: str,
    limit: int,
) -> QueryEnvelope:
    payload = _events(task_id, -1).envelope.to_dict()
    payload.update(
        {
            "request_id": f"request-unread-{presentation_class}-{scope.session_id}",
            "query_type": "task.unread_events",
            "scope": scope.to_dict(),
            "required_capabilities": ["task.unread_events"],
            "payload": {
                "presentation_class": presentation_class,
                "limit": limit,
            },
        }
    )
    return QueryEnvelope.from_dict(payload)


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


def test_unread_without_consumer_row_is_logical_minus_one_and_pure_read(
    tmp_path: Path,
) -> None:
    """Catches unread creating a sentinel row or silently acknowledging a page."""

    database = tmp_path / "unread-no-row.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-unread-no-row")
    before_bytes = database.read_bytes()
    before_schema = _schema_identity(database)

    page = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=1,
    )

    assert page.task_id == task_id
    assert page.presentation_class == "text"
    assert page.watermark == -1
    assert page.acked_event_id is None
    assert page.head_seq == 0
    assert [event.seq for event in page.events] == [0]
    assert page.next_after_seq is None
    assert page.has_more is False
    assert _consumer_rows(database) == []
    assert _schema_identity(database) == before_schema
    assert database.read_bytes() == before_bytes


def test_unread_consumer_identity_ignores_session_id(tmp_path: Path) -> None:
    """Catches transient Session identity splitting one durable consumer."""

    database = tmp_path / "unread-new-session.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-unread-new-session")
    new_session = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-2",
        Assurance.AUTHENTICATED,
    )
    before_bytes = database.read_bytes()

    page = store.unread_events_page(
        task_id,
        new_session,
        presentation_class="text",
        limit=500,
    )

    assert page.watermark == -1
    assert [event.seq for event in page.events] == [0]
    assert page.events[0].scope.session_id == _scope().session_id
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes


@pytest.mark.parametrize(
    "scope",
    (
        ScopeRef("other-user", "project-1", "session-2", Assurance.AUTHENTICATED),
        ScopeRef("user-1", "other-project", "session-2", Assurance.AUTHENTICATED),
    ),
)
def test_unread_rejects_foreign_consumer_scope_without_authority_writes(
    tmp_path: Path,
    scope: ScopeRef,
) -> None:
    """Catches session independence widening into subject/project disclosure."""

    database = tmp_path / f"unread-foreign-{scope.subject_id}-{scope.project_id}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-{scope.subject_id}")
    before_bytes = database.read_bytes()
    before_counts = store.counts()

    with pytest.raises(FormalTaskViolation) as denied:
        store.unread_events_page(
            task_id,
            scope,
            presentation_class="text",
            limit=10,
        )

    assert denied.value.reason == "TASK_NOT_FOUND"
    assert store.counts() == before_counts
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes


def test_unread_page_is_repeatable_without_ack_and_classes_share_events(
    tmp_path: Path,
) -> None:
    """Catches page metadata or query/display acting as a consumption cursor."""

    database = tmp_path / "unread-repeat.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-unread-repeat")
    item = store.claim_outbox("unread-repeat-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    before_bytes = database.read_bytes()

    first = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=2,
    )
    repeated = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=2,
    )
    voice = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    )

    assert first == repeated
    assert first.watermark == -1
    assert first.head_seq == 3
    assert [event.seq for event in first.events] == [0, 1]
    assert first.next_after_seq == 1
    assert first.has_more is True
    assert [event.seq for event in voice.events] == [0, 1, 2, 3]
    assert voice.next_after_seq is None
    assert voice.has_more is False
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes


def test_first_ack_persists_only_command_and_exact_class_watermark(
    tmp_path: Path,
) -> None:
    """Catches ACK mutating canonical Task truth or the other consumer class."""

    database = tmp_path / "ack-first.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-first")
    item = store.claim_outbox("ack-first-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    command, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-first",
    )
    before_counts = store.counts()
    before_authority = _nonconsumption_authority(database)
    before_schema = _schema_identity(database)

    result = store.ack_events(command, observed_at=NOW)

    assert result.ok and result.result == {
        "task_id": task_id,
        "presentation_class": "text",
        "acked_through_seq": 1,
        "acked_event_id": events[1].event_id,
        "advanced": True,
    }
    assert result.extensions == {
        "live_voice.command": {
            "disposition": "applied",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    after_counts = store.counts()
    assert after_counts == {**before_counts, "commands": before_counts["commands"] + 1}
    assert _nonconsumption_authority(database) == before_authority
    assert _schema_identity(database) == before_schema
    assert _consumer_rows(database) == [
        (
            _scope().subject_id,
            _scope().project_id,
            task_id,
            "text",
            1,
            events[1].event_id,
            NOW,
        )
    ]
    text_page = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    )
    voice_page = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    )
    assert text_page.watermark == 1
    assert [event.seq for event in text_page.events] == [2, 3]
    assert voice_page.watermark == -1
    assert [event.seq for event in voice_page.events] == [0, 1, 2, 3]


def test_ack_lower_equal_higher_and_exact_replay_are_monotonic(
    tmp_path: Path,
) -> None:
    """Catches a later Session regressing or touching an acknowledged prefix."""

    database = tmp_path / "ack-monotonic.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-monotonic")
    item = store.claim_outbox("ack-monotonic-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    first, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-monotonic-first",
    )
    first_result = store.ack_events(first, observed_at=NOW)
    assert first_result.ok
    first_row = _consumer_rows(database)
    stable_authority = _nonconsumption_authority(database)
    new_session = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-ack-2",
        Assurance.AUTHENTICATED,
    )

    lower_base, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=events[0].event_id,
        expected_event_head=3,
        command_id="command-ack-lower",
    )
    lower = _command_in_scope(lower_base, new_session)
    lower_result = store.ack_events(lower, observed_at="2026-08-05T12:00:01Z")
    assert lower_result.ok and lower_result.result == {
        "task_id": task_id,
        "presentation_class": "text",
        "acked_through_seq": 1,
        "acked_event_id": events[1].event_id,
        "advanced": False,
    }
    assert _consumer_rows(database) == first_row

    equal_base, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-equal",
    )
    equal = _command_in_scope(equal_base, new_session)
    equal_result = store.ack_events(equal, observed_at="2026-08-05T12:00:02Z")
    assert equal_result.ok and equal_result.result is not None
    assert equal_result.result["advanced"] is False
    assert _consumer_rows(database) == first_row

    higher_base, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-higher",
    )
    higher = _command_in_scope(higher_base, new_session)
    higher_result = store.ack_events(higher, observed_at="2026-08-05T12:00:03Z")
    assert higher_result.ok and higher_result.result is not None
    assert higher_result.result["advanced"] is True
    assert _consumer_rows(database) == [
        (
            _scope().subject_id,
            _scope().project_id,
            task_id,
            "text",
            3,
            events[3].event_id,
            "2026-08-05T12:00:03Z",
        )
    ]
    assert _nonconsumption_authority(database) == stable_authority
    commands_after_higher = store.counts()["commands"]
    before_replay_bytes = database.read_bytes()

    replay = store.ack_events(
        replace(higher, request_id="request-command-ack-higher-replay"),
        observed_at="2026-08-05T12:00:04Z",
    )

    assert replay == higher_result.for_request("request-command-ack-higher-replay")
    assert store.counts()["commands"] == commands_after_higher
    assert database.read_bytes() == before_replay_bytes

    changed_base, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=2,
        acked_event_id=events[2].event_id,
        expected_event_head=3,
        command_id="command-ack-higher",
    )
    changed = _command_in_scope(changed_base, new_session)
    before_conflict_bytes = database.read_bytes()
    with pytest.raises(FormalTaskViolation) as conflict:
        store.ack_events(changed, observed_at="2026-08-05T12:00:05Z")
    assert conflict.value.reason == "IDEMPOTENCY_CONFLICT"
    assert database.read_bytes() == before_conflict_bytes
    assert _consumer_rows(database)[0][4:6] == (3, events[3].event_id)


def test_committed_ack_reopens_with_exact_consumer_and_command_authority(
    tmp_path: Path,
) -> None:
    """Catches startup verification rejecting or silently losing a legal ACK."""

    database = tmp_path / "ack-reopen.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-reopen")
    event = store.events(task_id, _scope())[0]
    command, _grant = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id="command-ack-reopen",
    )
    committed = store.ack_events(command, observed_at=NOW)
    before_bytes = database.read_bytes()

    reopened = SqliteTaskStore(database)
    page = reopened.unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    )
    replay = reopened.ack_events(
        replace(command, request_id="request-command-ack-reopen-2"),
        observed_at="2026-08-05T12:00:01Z",
    )

    assert page.watermark == 0
    assert page.acked_event_id == event.event_id
    assert page.events == ()
    assert replay == committed.for_request("request-command-ack-reopen-2")
    assert database.read_bytes() == before_bytes


def test_task4_consumer_seed_accepts_a_first_noop_ack_and_reopens(
    tmp_path: Path,
) -> None:
    """Catches the first Task5 command invalidating a reviewed schema-v5 seed."""

    database = tmp_path / "ack-task4-seed.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-task4-seed")
    item = store.claim_outbox("ack-task4-seed-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'text', ?, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                1,
                events[1].event_id,
                NOW,
            ),
        )
        connection.commit()
    reopened = SqliteTaskStore(database)
    lower, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=events[0].event_id,
        expected_event_head=3,
        command_id="command-ack-task4-seed-lower",
    )

    result = reopened.ack_events(
        lower,
        observed_at="2026-08-05T12:00:01Z",
    )

    assert result.ok and result.result == {
        "task_id": task_id,
        "presentation_class": "text",
        "acked_through_seq": 1,
        "acked_event_id": events[1].event_id,
        "advanced": False,
    }
    assert _consumer_rows(database)[0][4:] == (1, events[1].event_id, NOW)
    assert SqliteTaskStore(database).unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    ).watermark == 1


@pytest.mark.parametrize(
    ("acked_seq", "expected_head", "event_source", "reason", "code"),
    (
        (1, 1, "missing", "TASK_ACK_PRECONDITION_STALE", ErrorCode.STALE),
        (1, 0, "missing", "TASK_ACK_PRECONDITION_STALE", ErrorCode.STALE),
        (0, 0, "missing", "TASK_ACK_EVENT_MISMATCH", ErrorCode.CONFLICT),
        (0, 0, "other_task", "TASK_ACK_EVENT_MISMATCH", ErrorCode.CONFLICT),
    ),
)
def test_authorized_ack_conflict_is_sanitized_replayable_and_zero_effect(
    tmp_path: Path,
    acked_seq: int,
    expected_head: int,
    event_source: str,
    reason: str,
    code: ErrorCode,
) -> None:
    """Catches closed ACK conflicts becoming transient or storing raw commands."""

    database = tmp_path / (
        f"ack-conflict-{acked_seq}-{expected_head}-{event_source}.sqlite"
    )
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-ack-conflict-{event_source}")
    other_task_id = _create_task(store, tmp_path, suffix=f"-ack-other-{event_source}")
    other_event = store.events(other_task_id, _scope())[0]
    acked_event_id = (
        other_event.event_id if event_source == "other_task" else "missing-event-id"
    )
    command, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=acked_seq,
        acked_event_id=acked_event_id,
        expected_event_head=expected_head,
        command_id=f"command-ack-conflict-{acked_seq}-{expected_head}-{event_source}",
    )
    before_counts = store.counts()
    before_authority = _nonconsumption_authority(database)
    before_schema = _schema_identity(database)

    rejected = store.ack_events(command, observed_at=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == reason
    assert rejected.error.code is code
    assert rejected.extensions == {
        "live_voice.command": {
            "disposition": "conflict",
            "admission_event_id": None,
            "settlement_event_id": None,
        }
    }
    assert store.counts() == {
        **before_counts,
        "commands": before_counts["commands"] + 1,
    }
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority
    assert _schema_identity(database) == before_schema
    with sqlite3.connect(database) as connection:
        fingerprint = connection.execute(
            """SELECT fingerprint FROM commands
               WHERE command_id=?""",
            (command.command_id,),
        ).fetchone()
    assert fingerprint is not None
    binding = json.loads(fingerprint[0])
    assert binding["binding_type"] == "live_voice.task_business_decision"
    assert binding["command_sha256"]
    assert b'"request_id"' not in fingerprint[0]

    reopened = SqliteTaskStore(database)
    before_replay_bytes = database.read_bytes()
    replay = reopened.ack_events(
        replace(command, request_id=f"{command.request_id}-replay"),
        observed_at="2026-08-05T12:00:01Z",
    )
    assert replay == rejected.for_request(f"{command.request_id}-replay")
    assert database.read_bytes() == before_replay_bytes

    changed, _grant = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=store.events(task_id, _scope())[0].event_id,
        expected_event_head=0,
        command_id=command.command_id,
    )
    before_changed_bytes = database.read_bytes()
    with pytest.raises(FormalTaskViolation) as conflict:
        reopened.ack_events(changed, observed_at="2026-08-05T12:00:02Z")
    assert conflict.value.reason == "IDEMPOTENCY_CONFLICT"
    assert database.read_bytes() == before_changed_bytes


def test_ack_conflict_replay_keeps_its_frozen_head_after_later_events(
    tmp_path: Path,
) -> None:
    """Catches a valid negative replay being reinterpreted at the current head."""

    database = tmp_path / "ack-conflict-historical-head.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-conflict-history")
    command, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id="event-not-yet-created",
        expected_event_head=1,
        command_id="command-ack-conflict-history",
    )
    rejected = store.ack_events(command, observed_at=NOW)
    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_ACK_PRECONDITION_STALE"

    item = store.claim_outbox("ack-conflict-history-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    assert store.get_task(task_id, _scope()).event_head == 3
    reopened = SqliteTaskStore(database)
    before_bytes = database.read_bytes()

    replay = reopened.ack_events(
        replace(command, request_id="request-ack-conflict-history-replay"),
        observed_at="2026-08-05T12:00:03Z",
    )

    assert replay == rejected.for_request("request-ack-conflict-history-replay")
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes


def test_cross_session_ack_command_id_collision_is_not_false_side_effect(
    tmp_path: Path,
) -> None:
    """Catches an unscoped causation lookup rejecting a legal Session ledger row."""

    database = tmp_path / "ack-command-id-collision.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-id-collision")
    with sqlite3.connect(database) as connection:
        create_command_id = connection.execute(
            "SELECT command_id FROM commands WHERE command_type='task.create'"
        ).fetchone()[0]
    base, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id="missing-event-id",
        expected_event_head=0,
        command_id=create_command_id,
    )
    new_session = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-ack-id-collision-2",
        Assurance.AUTHENTICATED,
    )
    command = _command_in_scope(base, new_session)

    rejected = store.ack_events(command, observed_at=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_ACK_EVENT_MISMATCH"
    assert _consumer_rows(database) == []
    reopened = SqliteTaskStore(database)
    replay = reopened.ack_events(
        replace(command, request_id="request-ack-id-collision-replay"),
        observed_at="2026-08-05T12:00:01Z",
    )
    assert replay == rejected.for_request("request-ack-id-collision-replay")


@pytest.mark.parametrize("scope_case", ("subject", "project", "task"))
def test_ack_rejects_unauthorized_consumer_scope_with_all_authority_unchanged(
    tmp_path: Path,
    scope_case: str,
) -> None:
    """Catches session independence widening into foreign consumer mutation."""

    database = tmp_path / f"ack-unauthorized-{scope_case}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-ack-denied-{scope_case}")
    event = store.events(task_id, _scope())[0]
    target_task_id = "task-not-authorized" if scope_case == "task" else task_id
    base, _grant = _ack_command(
        target_task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-denied-{scope_case}",
    )
    scope = {
        "subject": ScopeRef(
            "other-user", "project-1", "other-session", Assurance.AUTHENTICATED
        ),
        "project": ScopeRef(
            "user-1", "other-project", "other-session", Assurance.AUTHENTICATED
        ),
        "task": _scope(),
    }[scope_case]
    command = _command_in_scope(base, scope)
    before_counts = store.counts()
    before_bytes = database.read_bytes()
    before_authority = _nonconsumption_authority(database)

    with pytest.raises(FormalTaskViolation) as denied:
        store.ack_events(command, observed_at=NOW)

    assert denied.value.reason == "TASK_NOT_FOUND"
    assert store.counts() == before_counts
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority
    assert database.read_bytes() == before_bytes


@pytest.mark.parametrize("wire_case", ("class", "capability", "extra_key"))
def test_ack_rejects_noncanonical_wire_before_any_authority_write(
    tmp_path: Path,
    wire_case: str,
) -> None:
    """Catches Store helpers accepting forged envelopes that bypass shared parsing."""

    database = tmp_path / f"ack-wire-{wire_case}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-ack-wire-{wire_case}")
    event = store.events(task_id, _scope())[0]
    canonical, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-wire-{wire_case}",
    )
    if wire_case == "capability":
        forged = replace(canonical, required_capabilities=("task.update",))
    else:
        payload = canonical.payload
        if wire_case == "class":
            payload["presentation_class"] = "visual"
        else:
            payload["cursor"] = 0
        forged = replace(canonical, _payload=payload)
    before_counts = store.counts()
    before_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as invalid:
        store.ack_events(forged, observed_at=NOW)

    assert invalid.value.reason == "TASK_ACK_INVALID"
    assert store.counts() == before_counts
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes


def test_ack_requires_the_event_id_at_the_exact_sequence(tmp_path: Path) -> None:
    """Catches an event ID from another retained sequence advancing a watermark."""

    database = tmp_path / "ack-wrong-seq.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-wrong-seq")
    item = store.claim_outbox("ack-wrong-seq-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    command, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[2].event_id,
        expected_event_head=3,
        command_id="command-ack-wrong-seq",
    )
    before_authority = _nonconsumption_authority(database)

    rejected = store.ack_events(command, observed_at=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_ACK_EVENT_MISMATCH"
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority
    SqliteTaskStore(database)


@pytest.mark.parametrize("decision", ("applied", "conflict"))
def test_ack_failpoint_before_commit_rolls_back_every_effect(
    tmp_path: Path,
    decision: str,
) -> None:
    """Catches a crash persisting either half of consumer/command authority."""

    database = tmp_path / f"ack-failpoint-{decision}.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(setup, tmp_path, suffix=f"-ack-failpoint-{decision}")
    event = setup.events(task_id, _scope())[0]
    command, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=(event.event_id if decision == "applied" else "missing-event"),
        expected_event_head=0,
        command_id=f"command-ack-failpoint-{decision}",
    )

    def failpoint(name: str) -> None:
        if name == "ack_events.before_commit":
            raise RuntimeError("injected ACK crash")

    store = SqliteTaskStore(database, failpoint=failpoint)
    before_counts = store.counts()
    before_bytes = database.read_bytes()
    before_authority = _nonconsumption_authority(database)

    with pytest.raises(RuntimeError, match="injected ACK crash"):
        store.ack_events(command, observed_at=NOW)

    assert store.counts() == before_counts
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority
    assert database.read_bytes() == before_bytes
    SqliteTaskStore(database)


def test_two_store_ack_race_linearizes_to_the_greatest_exact_prefix(
    tmp_path: Path,
) -> None:
    """Catches a losing Store overwriting a later watermark or timestamp."""

    database = tmp_path / "ack-two-store-race.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(setup, tmp_path, suffix="-ack-two-store-race")
    item = setup.claim_outbox("ack-two-store-race-worker")
    assert item is not None
    setup.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = setup.events(task_id, _scope())
    lower, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-race-lower",
    )
    higher, _grant = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-race-higher",
    )
    lower_store = SqliteTaskStore(database)
    higher_store = SqliteTaskStore(database)
    barrier = Barrier(2)
    stable_authority = _nonconsumption_authority(database)

    def apply(
        store: SqliteTaskStore,
        command: CommandEnvelope,
        observed_at: str,
    ):
        barrier.wait(timeout=10)
        return store.ack_events(command, observed_at=observed_at)

    with ThreadPoolExecutor(max_workers=2) as pool:
        lower_future = pool.submit(
            apply, lower_store, lower, "2026-08-05T12:00:01Z"
        )
        higher_future = pool.submit(
            apply, higher_store, higher, "2026-08-05T12:00:02Z"
        )
        lower_result = lower_future.result(timeout=20)
        higher_result = higher_future.result(timeout=20)

    assert lower_result.ok and higher_result.ok
    assert higher_result.result is not None
    assert higher_result.result["advanced"] is True
    assert _consumer_rows(database) == [
        (
            _scope().subject_id,
            _scope().project_id,
            task_id,
            "text",
            3,
            events[3].event_id,
            "2026-08-05T12:00:02Z",
        )
    ]
    assert _nonconsumption_authority(database) == stable_authority
    voice = setup.unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    )
    assert voice.watermark == -1
    assert [event.seq for event in voice.events] == [0, 1, 2, 3]
    SqliteTaskStore(database)


def test_unread_freezes_consumer_head_and_events_in_one_read_snapshot(
    tmp_path: Path,
) -> None:
    """Catches one page mixing a pre-ACK row with a post-completion Task head."""

    database = tmp_path / "unread-frozen-snapshot.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(setup, tmp_path, suffix="-unread-frozen-snapshot")
    item = setup.claim_outbox("unread-frozen-snapshot-worker")
    assert item is not None
    paused = Event()
    resume = Event()

    def pause_after_consumer(name: str) -> None:
        if name == "unread_events_page.after_consumer":
            paused.set()
            if not resume.wait(timeout=20):
                raise RuntimeError("snapshot test writer did not finish")

    reader = SqliteTaskStore(database, failpoint=pause_after_consumer)
    writer = SqliteTaskStore(database)
    with ThreadPoolExecutor(max_workers=1) as pool:
        page_future = pool.submit(
            reader.unread_events_page,
            task_id,
            _scope(),
            presentation_class="text",
            limit=500,
        )
        assert paused.wait(timeout=10)
        writer.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=_observations(item),
        )
        events = writer.events(task_id, _scope())
        command, _grant = _ack_command(
            task_id,
            presentation_class="text",
            acked_through_seq=3,
            acked_event_id=events[3].event_id,
            expected_event_head=3,
            command_id="command-unread-frozen-snapshot",
        )
        writer.ack_events(command, observed_at=NOW)
        resume.set()
        page = page_future.result(timeout=20)

    assert page.watermark == -1
    assert page.acked_event_id is None
    assert page.head_seq == 0
    assert [event.seq for event in page.events] == [0]
    current = writer.unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    )
    assert current.watermark == 3
    assert current.head_seq == 3
    assert current.events == ()


def test_core_routes_unread_as_a_pure_new_session_query(tmp_path: Path) -> None:
    """Catches query routing adding a disposition or bypassing a fresh grant."""

    database = tmp_path / "core-unread.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    task_id = _create_task(store, tmp_path, suffix="-core-unread")
    new_session = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-core-unread-2",
        Assurance.AUTHENTICATED,
    )
    query = _unread_query(
        task_id,
        new_session,
        presentation_class="voice",
        limit=1,
    )
    grant = _grant_in_scope(
        "task.unread_events",
        new_session,
        command_id=None,
        task_id=task_id,
    )
    before_bytes = database.read_bytes()

    result = core.query(query, grant, now=NOW)

    assert result.ok and result.result == {
        "task_id": task_id,
        "presentation_class": "voice",
        "watermark": -1,
        "acked_event_id": None,
        "head_seq": 0,
        "events": [store.events(task_id, _scope())[0].to_dict()],
        "next_after_seq": None,
        "has_more": False,
    }
    assert result.extensions == {}
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes
    assert executor.dispatches == []
    assert executor.adjustments == []

    old_session_grant = _grant(
        "task.unread_events", command_id=None, target=task_id
    )
    denied = core.query(query, old_session_grant, now=NOW)
    assert not denied.ok and denied.error is not None
    assert denied.error.code is ErrorCode.PERMISSION_DENIED
    assert database.read_bytes() == before_bytes


def test_core_routes_ack_only_after_full_new_session_authorization(
    tmp_path: Path,
) -> None:
    """Catches Store consumer identity replacing per-call Core authorization."""

    database = tmp_path / "core-ack.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    task_id = _create_task(store, tmp_path, suffix="-core-ack")
    event = store.events(task_id, _scope())[0]
    base, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id="command-core-ack",
    )
    new_session = ScopeRef(
        _scope().subject_id,
        _scope().project_id,
        "session-core-ack-2",
        Assurance.AUTHENTICATED,
    )
    command = _command_in_scope(base, new_session)
    full_grant = _grant_in_scope(
        "task.ack_events",
        new_session,
        command_id=command.command_id,
        task_id=task_id,
    )
    before_bytes = database.read_bytes()

    denied = core.execute(command, None, now=NOW)
    assert not denied.ok and denied.error is not None
    assert denied.error.code is ErrorCode.UNAUTHENTICATED
    assert database.read_bytes() == before_bytes

    wrong_session_grant = _grant(
        "task.ack_events", command_id=command.command_id, target=task_id
    )
    denied = core.execute(command, wrong_session_grant, now=NOW)
    assert not denied.ok and denied.error is not None
    assert denied.error.code is ErrorCode.PERMISSION_DENIED
    assert database.read_bytes() == before_bytes

    applied = core.execute(command, full_grant, now=NOW)

    assert applied.ok and applied.result is not None
    assert applied.result["acked_through_seq"] == 0
    assert applied.extensions["live_voice.command"]["disposition"] == "applied"
    assert _consumer_rows(database)[0][0:5] == (
        _scope().subject_id,
        _scope().project_id,
        task_id,
        "text",
        0,
    )
    assert executor.dispatches == []
    assert executor.adjustments == []


@pytest.mark.parametrize(
    "failpoint_name",
    (
        "executor_terminal.after_source_fact",
        "executor_terminal.after_attempt",
        "executor_terminal.after_attempt_event",
        "executor_terminal.after_task_event",
        "executor_terminal.after_task_terminal",
        "executor_terminal.after_task_result",
        "executor_terminal.after_outbox_settlement",
    ),
)
def test_completed_terminal_chain_failpoints_roll_back_the_entire_fact_group(
    tmp_path: Path,
    failpoint_name: str,
) -> None:
    """Catches unread observing any half-settled completed terminal authority."""

    database = tmp_path / f"terminal-atomic-{failpoint_name.rsplit('.', 1)[-1]}.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(
        setup,
        tmp_path,
        suffix=f"-terminal-{failpoint_name.rsplit('.', 1)[-1]}",
    )
    item = setup.claim_outbox(f"worker-{failpoint_name}")
    assert item is not None
    artifact_path = tmp_path / f"{item.attempt_id}-result.txt"
    artifact_bytes = b"immutable terminal artifact\n"
    artifact_path.write_bytes(artifact_bytes)
    artifact = TaskResultArtifact(
        relative_path=artifact_path.name,
        sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    observations = _observations(
        item,
        outcome=TerminalOutcome.COMPLETED,
        result_text="immutable completed result",
        result_artifacts=(artifact,),
    )

    def failpoint(name: str) -> None:
        if name == failpoint_name:
            raise RuntimeError(f"injected {name}")

    store = SqliteTaskStore(database, failpoint=failpoint)
    before_counts = store.counts()
    before_authority = _nonconsumption_authority(database)
    before_bytes = database.read_bytes()

    with pytest.raises(RuntimeError, match="injected executor_terminal"):
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=observations,
        )

    assert store.counts() == before_counts
    assert _nonconsumption_authority(database) == before_authority
    assert _consumer_rows(database) == []
    assert database.read_bytes() == before_bytes
    assert artifact_path.read_bytes() == artifact_bytes
    unread = store.unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    )
    assert unread.head_seq == 0
    assert [event.seq for event in unread.events] == [0]
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.NOT_READY,
        None,
        "TASK_RESULT_NOT_READY",
    )
    SqliteTaskStore(database)


def test_terminal_result_stays_retained_across_pre_and_post_ack_restarts(
    tmp_path: Path,
) -> None:
    """Catches ACK deleting terminal events/results or coupling record read to files."""

    database = tmp_path / "terminal-ack-restart.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-terminal-ack-restart")
    item = store.claim_outbox("terminal-ack-restart-worker")
    assert item is not None
    artifact_path = tmp_path / "terminal-ack-result.txt"
    artifact_bytes = b"retained TaskResult authority\n"
    artifact_path.write_bytes(artifact_bytes)
    artifact = TaskResultArtifact(
        relative_path=artifact_path.name,
        sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(
            item,
            outcome=TerminalOutcome.COMPLETED,
            result_text="retained completed result",
            result_artifacts=(artifact,),
        ),
    )
    events = store.events(task_id, _scope())
    terminal = events[-1]
    assert terminal.event_type == "task.terminal"
    assert terminal.outcome == TerminalOutcome.COMPLETED.value
    availability, record, reason = store.task_result(task_id, _scope())
    assert availability is TaskResultAvailability.AVAILABLE
    assert record is not None and reason == "TASK_RESULT_AVAILABLE"

    before_ack_restart = SqliteTaskStore(database)
    unread_before = before_ack_restart.unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    )
    assert unread_before.watermark == -1
    assert [event.seq for event in unread_before.events] == list(
        range(terminal.seq + 1)
    )
    stable_authority = _nonconsumption_authority(database)
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=terminal.seq,
        acked_event_id=terminal.event_id,
        expected_event_head=terminal.seq,
        command_id="command-terminal-ack-restart",
    )
    applied = before_ack_restart.ack_events(command, observed_at=NOW)
    assert applied.ok
    assert _nonconsumption_authority(database) == stable_authority

    artifact_path.unlink()
    after_ack_restart = SqliteTaskStore(database)
    unread_after = after_ack_restart.unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    )
    assert unread_after.watermark == terminal.seq
    assert unread_after.acked_event_id == terminal.event_id
    assert unread_after.events == ()
    assert after_ack_restart.events(task_id, _scope()) == events
    assert after_ack_restart.task_result(task_id, _scope()) == (
        TaskResultAvailability.AVAILABLE,
        record,
        "TASK_RESULT_AVAILABLE",
    )


@pytest.mark.parametrize("corruption", ("consumer", "negative_binding"))
def test_ack_corruption_fails_closed_on_reopen_without_repair_writes(
    tmp_path: Path,
    corruption: str,
) -> None:
    """Catches startup accepting or silently repairing forged consumption truth."""

    database = tmp_path / f"ack-corrupt-{corruption}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-ack-corrupt-{corruption}")
    event = store.events(task_id, _scope())[0]
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=(event.event_id if corruption == "consumer" else "missing"),
        expected_event_head=0,
        command_id=f"command-ack-corrupt-{corruption}",
    )
    result = store.ack_events(command, observed_at=NOW)
    assert result.ok is (corruption == "consumer")
    with sqlite3.connect(database) as connection:
        if corruption == "consumer":
            connection.execute(
                "UPDATE task_event_consumption SET updated_at=?",
                ("2026-08-05T12:00:09Z",),
            )
        else:
            connection.execute(
                """UPDATE commands SET fingerprint=?
                   WHERE command_type='task.ack_events'""",
                (b"{}",),
            )
        connection.commit()
    before_reopen_bytes = database.read_bytes()
    before_authority = _nonconsumption_authority(database)

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert corrupt.value.code is ErrorCode.INTERNAL
    assert database.read_bytes() == before_reopen_bytes
    assert _nonconsumption_authority(database) == before_authority
