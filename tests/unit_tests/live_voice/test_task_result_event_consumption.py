# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
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


def _create_task_at(
    store: SqliteTaskStore,
    tmp_path: Path,
    *,
    suffix: str,
    now: str,
) -> str:
    invocation = _create(tmp_path, identity_suffix=suffix)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=now,
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


def _command_result_json(database: Path, command_id: str) -> dict[str, object]:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (command_id,),
        ).fetchone()
    assert row is not None
    value = json.loads(row[0])
    assert type(value) is dict
    return value


def _replace_command_result_json(
    database: Path,
    command_id: str,
    value: dict[str, object],
) -> None:
    with sqlite3.connect(database) as connection:
        updated = connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                command_id,
            ),
        ).rowcount
        assert updated == 1
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


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


def _after(timestamp: str, *, seconds: int = 1) -> str:
    parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    return (parsed + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


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
    ack_time = _after(events[1].occurred_at)

    result = store.ack_events(command, observed_at=ack_time)

    assert result.ok and result.result is not None
    assert {
        field: result.result[field]
        for field in (
            "task_id",
            "presentation_class",
            "acked_through_seq",
            "acked_event_id",
            "advanced",
        )
    } == {
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
            ack_time,
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
    first_time = _after(events[-1].occurred_at)
    lower_time = _after(first_time)
    equal_time = _after(first_time, seconds=2)
    higher_time = _after(first_time, seconds=3)
    first_result = store.ack_events(first, observed_at=first_time)
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
    lower_result = store.ack_events(lower, observed_at=lower_time)
    assert lower_result.ok and lower_result.result is not None
    assert {
        field: lower_result.result[field]
        for field in (
            "task_id",
            "presentation_class",
            "acked_through_seq",
            "acked_event_id",
            "advanced",
        )
    } == {
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
    equal_result = store.ack_events(equal, observed_at=equal_time)
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
    higher_result = store.ack_events(higher, observed_at=higher_time)
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
            higher_time,
        )
    ]
    assert _nonconsumption_authority(database) == stable_authority
    commands_after_higher = store.counts()["commands"]
    before_replay_bytes = database.read_bytes()

    replay = store.ack_events(
        replace(higher, request_id="request-command-ack-higher-replay"),
        observed_at=_after(higher_time),
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
        store.ack_events(changed, observed_at=_after(higher_time, seconds=2))
    assert conflict.value.reason == "IDEMPOTENCY_CONFLICT"
    assert database.read_bytes() == before_conflict_bytes
    assert _consumer_rows(database)[0][4:6] == (3, events[3].event_id)


def test_runtime_ack_results_form_a_closed_history_chain_across_noops(
    tmp_path: Path,
) -> None:
    """Catches a successful ACK omitting or skipping its predecessor digest."""

    database = tmp_path / "ack-history-chain.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-history-chain")
    item = store.claim_outbox("ack-history-chain-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    observed = _after(events[-1].occurred_at)
    first, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-history-first",
    )
    lower, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=events[0].event_id,
        expected_event_head=3,
        command_id="command-ack-history-lower",
    )
    equal, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-history-equal",
    )

    first_result = store.ack_events(first, observed_at=observed)
    lower_result = store.ack_events(lower, observed_at=_after(observed))
    equal_result = store.ack_events(equal, observed_at=_after(observed, seconds=2))

    assert first_result.result is not None
    first_history = first_result.result["consumption_history"]
    assert first_history["version"] == 1
    assert first_history["origin"] == "runtime_v1"
    assert first_history["previous"] == {
        "acked_through_seq": -1,
        "acked_event_id": None,
        "updated_at": None,
        "history_sha256": None,
    }
    assert first_history["current"] == {
        "acked_through_seq": 1,
        "acked_event_id": events[1].event_id,
        "updated_at": observed,
        "history_sha256": first_history["current"]["history_sha256"],
    }
    first_digest = first_history["current"]["history_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", first_digest) is not None

    assert lower_result.result is not None
    lower_history = lower_result.result["consumption_history"]
    assert lower_history["origin"] == "runtime_v1"
    assert lower_history["previous"] == first_history["current"]
    assert lower_history["current"]["acked_through_seq"] == 1
    assert lower_history["current"]["acked_event_id"] == events[1].event_id
    assert lower_history["current"]["updated_at"] == observed
    lower_digest = lower_history["current"]["history_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", lower_digest) is not None
    assert lower_digest != first_digest

    assert equal_result.result is not None
    equal_history = equal_result.result["consumption_history"]
    assert equal_history["origin"] == "runtime_v1"
    assert equal_history["previous"] == lower_history["current"]
    assert equal_history["current"]["acked_through_seq"] == 1
    assert equal_history["current"]["acked_event_id"] == events[1].event_id
    assert equal_history["current"]["updated_at"] == observed
    assert equal_history["current"]["history_sha256"] != lower_digest
    assert SqliteTaskStore(database).unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    ).watermark == 1


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
    committed_time = _after(event.occurred_at)
    committed = store.ack_events(command, observed_at=committed_time)
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
        observed_at=_after(committed_time),
    )

    assert page.watermark == 0
    assert page.acked_event_id == event.event_id
    assert page.events == ()
    assert replay == committed.for_request("request-command-ack-reopen-2")
    assert database.read_bytes() == before_bytes


def test_task4_consumer_seed_accepts_a_first_noop_ack_and_reopens(
    tmp_path: Path,
) -> None:
    """Catches the first Task5 command invalidating the closed Task4 seed."""

    database = tmp_path / "ack-task4-seed.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-task4-seed")
    events = store.events(task_id, _scope())
    assert [(event.seq, event.event_type, event.occurred_at) for event in events] == [
        (0, "task.accepted", NOW)
    ]
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
                0,
                events[0].event_id,
                events[0].occurred_at,
            ),
        )
        connection.commit()
    reopened = SqliteTaskStore(database)
    equal, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=events[0].event_id,
        expected_event_head=0,
        command_id="command-ack-task4-seed-equal",
    )

    result = reopened.ack_events(
        equal,
        observed_at="2026-08-05T12:00:01Z",
    )

    assert result.ok and result.result is not None
    assert {
        field: result.result[field]
        for field in (
            "task_id",
            "presentation_class",
            "acked_through_seq",
            "acked_event_id",
            "advanced",
        )
    } == {
        "task_id": task_id,
        "presentation_class": "text",
        "acked_through_seq": 0,
        "acked_event_id": events[0].event_id,
        "advanced": False,
    }
    assert _consumer_rows(database)[0][4:] == (
        0,
        events[0].event_id,
        events[0].occurred_at,
    )
    assert SqliteTaskStore(database).unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    ).watermark == 0


def test_unowned_consumer_outside_legacy_seed_v1_shape_is_corrupt(
    tmp_path: Path,
) -> None:
    """Catches a later retained event being promoted into a broader raw seed."""

    database = tmp_path / "ack-unowned-noninitial-seed.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-unowned-noninitial-seed")
    item = store.claim_outbox("ack-unowned-noninitial-seed-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    accepted = events[0]
    event = events[1]
    assert event.event_type == "attempt.accepted"
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
                event.seq,
                event.event_id,
                accepted.occurred_at,
            ),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


def test_runtime_first_seq_one_cannot_be_relabelled_by_seed_timestamp(
    tmp_path: Path,
) -> None:
    """Catches a runtime ACK being relabelled by changing only its timestamp."""

    database = tmp_path / "ack-runtime-seq-one-seed-time.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-runtime-seq-one-seed-time")
    accepted = store.events(task_id, _scope())[0]
    item = store.claim_outbox("ack-runtime-seq-one-seed-time-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    first, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-runtime-seq-one-seed-time",
    )
    assert store.ack_events(
        first,
        observed_at=_after(events[-1].occurred_at),
    ).ok
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE task_event_consumption SET updated_at=?",
            (accepted.occurred_at,),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


def test_deleted_superseded_runtime_ack_breaks_history_and_id_stays_owned(
    tmp_path: Path,
) -> None:
    """Catches deleting an earlier ACK and reusing its ID in another class."""

    database = tmp_path / "ack-runtime-superseded-deleted.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-runtime-superseded-deleted")
    item = store.claim_outbox("ack-runtime-superseded-deleted-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    first, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-runtime-superseded-deleted",
    )
    higher, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-runtime-superseded-higher",
    )
    assert store.ack_events(
        first,
        observed_at=_after(events[-1].occurred_at),
    ).ok
    assert store.ack_events(
        higher,
        observed_at=_after(events[-1].occurred_at, seconds=2),
    ).ok
    with sqlite3.connect(database) as connection:
        deleted = connection.execute(
            "DELETE FROM commands WHERE command_id=?",
            (first.command_id,),
        ).rowcount
        assert deleted == 1
        connection.commit()
    changed, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id=first.command_id,
    )
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database).ack_events(
            changed,
            observed_at=_after(events[-1].occurred_at, seconds=3),
        )

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes
    assert _consumer_rows(database)[0][3:6] == (
        "text",
        3,
        events[3].event_id,
    )


@pytest.mark.parametrize(
    "deleted_label",
    ("lower", "equal"),
)
def test_deleting_applied_noop_ack_breaks_the_history_chain(
    tmp_path: Path,
    deleted_label: str,
) -> None:
    """Catches deletion of an applied ACK whose watermark was a no-op."""

    database = tmp_path / f"ack-history-delete-{deleted_label}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-ack-history-delete-{deleted_label}")
    item = store.claim_outbox(f"ack-history-delete-{deleted_label}-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    observed = _after(events[-1].occurred_at)
    commands: dict[str, CommandEnvelope] = {}
    for label, seq in (("first", 1), ("lower", 0), ("equal", 1), ("higher", 3)):
        command, _grant_unused = _ack_command(
            task_id,
            presentation_class="text",
            acked_through_seq=seq,
            acked_event_id=events[seq].event_id,
            expected_event_head=3,
            command_id=f"command-ack-history-delete-{deleted_label}-{label}",
        )
        commands[label] = command
    for index, label in enumerate(("first", "lower", "equal", "higher")):
        assert store.ack_events(
            commands[label],
            observed_at=_after(observed, seconds=index),
        ).ok
    with sqlite3.connect(database) as connection:
        deleted = connection.execute(
            "DELETE FROM commands WHERE command_id=?",
            (commands[deleted_label].command_id,),
        ).rowcount
        assert deleted == 1
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


def test_reordering_two_applied_noop_acks_breaks_the_history_chain(
    tmp_path: Path,
) -> None:
    """Catches command-row order changes that preserve the final watermark."""

    database = tmp_path / "ack-history-reorder-noops.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-history-reorder-noops")
    item = store.claim_outbox("ack-history-reorder-noops-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    observed = _after(events[-1].occurred_at)
    commands: list[CommandEnvelope] = []
    for label, seq in (("first", 1), ("lower", 0), ("equal", 1)):
        command, _grant_unused = _ack_command(
            task_id,
            presentation_class="text",
            acked_through_seq=seq,
            acked_event_id=events[seq].event_id,
            expected_event_head=3,
            command_id=f"command-ack-history-reorder-{label}",
        )
        commands.append(command)
    for index, command in enumerate(commands):
        assert store.ack_events(
            command,
            observed_at=_after(observed, seconds=index),
        ).ok
    with sqlite3.connect(database) as connection:
        max_rowid = connection.execute(
            "SELECT MAX(rowid) FROM commands"
        ).fetchone()[0]
        connection.execute(
            "UPDATE commands SET rowid=? WHERE command_id=?",
            (max_rowid + 1, commands[1].command_id),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


@pytest.mark.parametrize(
    ("field_path", "replacement"),
    (
        (("version",), 2),
        (("origin",), "legacy_seed_v1"),
        (("previous", "acked_through_seq"), 99),
        (("previous", "acked_event_id"), "event-forged"),
        (("previous", "updated_at"), NOW),
        (("previous", "history_sha256"), "0" * 64),
        (("current", "acked_through_seq"), 99),
        (("current", "acked_event_id"), "event-forged"),
        (("current", "updated_at"), NOW),
        (("current", "history_sha256"), "f" * 64),
    ),
)
def test_ack_history_result_tamper_is_corrupt(
    tmp_path: Path,
    field_path: tuple[str, ...],
    replacement: object,
) -> None:
    """Catches any stored predecessor, origin, state, or digest substitution."""

    label = "-".join(field_path)
    database = tmp_path / f"ack-history-result-tamper-{label}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix=f"-ack-history-tamper-{label}")
    event = store.events(task_id, _scope())[0]
    first, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-history-tamper-{label}-first",
    )
    second, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-history-tamper-{label}-second",
    )
    assert store.ack_events(
        first,
        observed_at=_after(event.occurred_at),
    ).ok
    assert store.ack_events(
        second,
        observed_at=_after(event.occurred_at, seconds=2),
    ).ok
    result_json = _command_result_json(database, second.command_id)
    result = result_json["result"]
    assert type(result) is dict
    history = result["consumption_history"]
    assert type(history) is dict
    target = history
    for field in field_path[:-1]:
        target = target[field]
        assert type(target) is dict
    target[field_path[-1]] = replacement
    _replace_command_result_json(database, second.command_id, result_json)
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


def test_legacy_seed_anchor_survives_noop_and_multiple_higher_acks(
    tmp_path: Path,
) -> None:
    """Catches an adopted seed losing provenance after its watermark advances."""

    database = tmp_path / "ack-seed-noop-then-higher.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-seed-noop-then-higher")
    accepted = store.events(task_id, _scope())[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'voice', 0, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                accepted.event_id,
                accepted.occurred_at,
            ),
        )
        connection.commit()
    adopted = SqliteTaskStore(database)
    equal, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=accepted.event_id,
        expected_event_head=0,
        command_id="command-ack-seed-adopt-equal",
    )
    equal_result = adopted.ack_events(equal, observed_at=_after(accepted.occurred_at))
    assert equal_result.ok and equal_result.result is not None
    assert equal_result.result["advanced"] is False

    item = adopted.claim_outbox("ack-seed-noop-then-higher-worker")
    assert item is not None
    adopted.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = adopted.events(task_id, _scope())
    first_higher, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-seed-first-higher",
    )
    first_time = _after(events[-1].occurred_at)
    first_result = adopted.ack_events(first_higher, observed_at=first_time)
    assert first_result.ok and first_result.result is not None
    assert first_result.result["advanced"] is True
    assert _consumer_rows(database)[0][4:] == (
        1,
        events[1].event_id,
        accepted.occurred_at,
    )

    final_higher, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-seed-final-higher",
    )
    final_result = adopted.ack_events(
        final_higher,
        observed_at=_after(first_time),
    )
    assert final_result.ok and final_result.result is not None
    assert final_result.result["advanced"] is True
    assert _consumer_rows(database)[0][4:] == (
        3,
        events[3].event_id,
        accepted.occurred_at,
    )

    for label, seq in (("lower", 1), ("equal", 3)):
        noop, _grant_unused = _ack_command(
            task_id,
            presentation_class="voice",
            acked_through_seq=seq,
            acked_event_id=events[seq].event_id,
            expected_event_head=3,
            command_id=f"command-ack-seed-final-{label}",
        )
        noop_result = adopted.ack_events(
            noop,
            observed_at=_after(first_time, seconds=2 if label == "lower" else 3),
        )
        assert noop_result.ok and noop_result.result is not None
        assert noop_result.result["advanced"] is False
        assert _consumer_rows(database)[0][4:] == (
            3,
            events[3].event_id,
            accepted.occurred_at,
        )

    reopened = SqliteTaskStore(database)
    before_replay_bytes = database.read_bytes()
    replay = reopened.ack_events(
        replace(final_higher, request_id="request-ack-seed-final-higher-replay"),
        observed_at=_after(first_time, seconds=4),
    )
    assert replay == final_result.for_request(
        "request-ack-seed-final-higher-replay"
    )
    assert database.read_bytes() == before_replay_bytes


def test_legacy_seed_direct_higher_is_replayable_stale_without_advancing(
    tmp_path: Path,
) -> None:
    """Catches a raw seed advancing before its exact adoption handshake."""

    database = tmp_path / "ack-seed-direct-higher-stale.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-seed-direct-higher-stale")
    accepted = store.events(task_id, _scope())[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'text', 0, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                accepted.event_id,
                accepted.occurred_at,
            ),
        )
        connection.commit()
    store = SqliteTaskStore(database)
    item = store.claim_outbox("ack-seed-direct-higher-stale-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    direct, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-seed-direct-higher-stale",
    )
    before_consumer = _consumer_rows(database)
    before_authority = _nonconsumption_authority(database)
    rejected = store.ack_events(
        direct,
        observed_at=_after(events[-1].occurred_at),
    )
    after_rejection_bytes = database.read_bytes()

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_ACK_PRECONDITION_STALE"
    assert rejected.error.code is ErrorCode.STALE
    assert _consumer_rows(database) == before_consumer
    assert _nonconsumption_authority(database) == before_authority
    reopened = SqliteTaskStore(database)
    replay = reopened.ack_events(
        replace(direct, request_id="request-ack-seed-direct-higher-replay"),
        observed_at=_after(events[-1].occurred_at, seconds=2),
    )
    assert replay == rejected.for_request("request-ack-seed-direct-higher-replay")
    assert database.read_bytes() == after_rejection_bytes

    changed, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id=direct.command_id,
    )
    with pytest.raises(FormalTaskViolation) as conflict:
        reopened.ack_events(
            changed,
            observed_at=_after(events[-1].occurred_at, seconds=3),
        )
    assert conflict.value.reason == "IDEMPOTENCY_CONFLICT"
    assert database.read_bytes() == after_rejection_bytes

    adoption, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=accepted.event_id,
        expected_event_head=3,
        command_id="command-ack-seed-after-direct-stale-adoption",
    )
    adopted = reopened.ack_events(
        adoption,
        observed_at=_after(events[-1].occurred_at, seconds=4),
    )
    assert adopted.ok and adopted.result is not None
    assert adopted.result["advanced"] is False
    assert adopted.result["consumption_history"]["origin"] == "legacy_seed_v1"
    higher, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-seed-after-direct-stale-higher",
    )
    advanced = reopened.ack_events(
        higher,
        observed_at=_after(events[-1].occurred_at, seconds=5),
    )
    assert advanced.ok and advanced.result is not None
    assert advanced.result["advanced"] is True
    assert _consumer_rows(database)[0][4:] == (
        3,
        events[3].event_id,
        accepted.occurred_at,
    )
    after_higher = SqliteTaskStore(database)
    before_replays = database.read_bytes()
    assert after_higher.ack_events(
        replace(direct, request_id="request-ack-seed-direct-stale-late-replay"),
        observed_at=_after(events[-1].occurred_at, seconds=6),
    ) == rejected.for_request("request-ack-seed-direct-stale-late-replay")
    assert after_higher.ack_events(
        replace(higher, request_id="request-ack-seed-higher-replay"),
        observed_at=_after(events[-1].occurred_at, seconds=7),
    ) == advanced.for_request("request-ack-seed-higher-replay")
    assert database.read_bytes() == before_replays


def test_adopted_legacy_seed_two_store_higher_race_keeps_anchor(
    tmp_path: Path,
) -> None:
    """Catches concurrent advancement replacing an adopted seed's anchor."""

    database = tmp_path / "ack-seed-direct-higher-race.sqlite"
    setup = SqliteTaskStore(database)
    task_id = _create_task(setup, tmp_path, suffix="-ack-seed-direct-higher-race")
    accepted = setup.events(task_id, _scope())[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'text', 0, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                accepted.event_id,
                accepted.occurred_at,
            ),
        )
        connection.commit()
    setup = SqliteTaskStore(database)
    adoption, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=accepted.event_id,
        expected_event_head=0,
        command_id="command-ack-seed-race-adoption",
    )
    adopted = setup.ack_events(
        adoption,
        observed_at=_after(accepted.occurred_at),
    )
    assert adopted.ok and adopted.result is not None
    assert adopted.result["advanced"] is False
    item = setup.claim_outbox("ack-seed-direct-higher-race-worker")
    assert item is not None
    setup.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = setup.events(task_id, _scope())
    lower, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=1,
        acked_event_id=events[1].event_id,
        expected_event_head=3,
        command_id="command-ack-seed-race-lower",
    )
    higher, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-seed-race-higher",
    )
    lower_store = SqliteTaskStore(database)
    higher_store = SqliteTaskStore(database)
    barrier = Barrier(2)

    def apply(
        store: SqliteTaskStore,
        command: CommandEnvelope,
        observed_at: str,
    ):
        barrier.wait(timeout=10)
        return store.ack_events(command, observed_at=observed_at)

    with ThreadPoolExecutor(max_workers=2) as pool:
        lower_future = pool.submit(
            apply,
            lower_store,
            lower,
            _after(events[-1].occurred_at),
        )
        higher_future = pool.submit(
            apply,
            higher_store,
            higher,
            _after(events[-1].occurred_at, seconds=2),
        )
        lower_result = lower_future.result(timeout=20)
        higher_result = higher_future.result(timeout=20)

    assert lower_result.ok and higher_result.ok
    assert _consumer_rows(database)[0][4:] == (
        3,
        events[3].event_id,
        accepted.occurred_at,
    )
    assert SqliteTaskStore(database).unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    ).watermark == 3


def test_runtime_first_ack_result_flip_remains_corrupt_after_a_higher_ack(
    tmp_path: Path,
) -> None:
    """Catches later runtime state laundering a forged first-ACK disposition."""

    database = tmp_path / "ack-runtime-result-flip-then-higher.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-runtime-flip-higher")
    accepted = store.events(task_id, _scope())[0]
    first, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=accepted.event_id,
        expected_event_head=0,
        command_id="command-ack-runtime-flip-higher-first",
    )
    assert store.ack_events(first, observed_at=_after(accepted.occurred_at)).ok
    item = store.claim_outbox("ack-runtime-flip-higher-worker")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )
    events = store.events(task_id, _scope())
    higher, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=3,
        acked_event_id=events[3].event_id,
        expected_event_head=3,
        command_id="command-ack-runtime-flip-higher-final",
    )
    assert store.ack_events(
        higher,
        observed_at=_after(events[-1].occurred_at),
    ).ok
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (first.command_id,),
        ).fetchone()
        assert row is not None
        result_json = json.loads(row[0])
        result_json["result"]["advanced"] = False
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (
                json.dumps(
                    result_json,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                first.command_id,
            ),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


def test_runtime_first_ack_result_cannot_self_declare_a_legacy_seed(
    tmp_path: Path,
) -> None:
    """Catches flipping advanced=true into a mutable legacy-seed claim."""

    database = tmp_path / "ack-runtime-result-flip.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-runtime-result-flip")
    event = store.events(task_id, _scope())[0]
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id="command-ack-runtime-result-flip",
    )
    applied = store.ack_events(
        command,
        observed_at="2026-08-05T12:00:01Z",
    )
    assert applied.ok and applied.result is not None
    assert applied.result["advanced"] is True
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
        assert row is not None
        result_json = json.loads(row[0])
        result_json["result"]["advanced"] = False
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (
                json.dumps(
                    result_json,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                command.command_id,
            ),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


def test_deleted_runtime_ack_cannot_reopen_or_reuse_its_id_for_other_class(
    tmp_path: Path,
) -> None:
    """Catches command deletion relabeling runtime authority as a raw seed."""

    database = tmp_path / "ack-runtime-command-deleted.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-runtime-command-deleted")
    event = store.events(task_id, _scope())[0]
    original, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id="command-ack-runtime-deleted",
    )
    assert store.ack_events(
        original,
        observed_at="2026-08-05T12:00:01Z",
    ).ok
    with sqlite3.connect(database) as connection:
        deleted = connection.execute(
            "DELETE FROM commands WHERE command_id=?",
            (original.command_id,),
        ).rowcount
        assert deleted == 1
        connection.commit()
    changed, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=original.command_id,
    )
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database).ack_events(
            changed,
            observed_at="2026-08-05T12:00:02Z",
        )

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes
    assert _consumer_rows(database) == [
        (
            _scope().subject_id,
            _scope().project_id,
            task_id,
            "text",
            0,
            event.event_id,
            "2026-08-05T12:00:01Z",
        )
    ]


@pytest.mark.parametrize(
    "updated_at",
    (
        "not-a-timestamp",
        "2026-08-05 12:00:00Z",
        "2026-08-05T14:00:00+02:00",
    ),
)
def test_unowned_legacy_seed_requires_canonical_accepted_event_timestamp(
    tmp_path: Path,
    updated_at: str,
) -> None:
    """Catches invalid or alternate-offset time self-authorizing a raw seed."""

    database = tmp_path / f"ack-seed-invalid-time-{updated_at[:4]}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-seed-invalid-time")
    event = store.events(task_id, _scope())[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'text', 0, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                event.event_id,
                updated_at,
            ),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


@pytest.mark.parametrize(
    "tampered_at",
    ("2026-08-05T11:59:59Z", "2026-08-05T12:00:02Z"),
)
def test_adopted_legacy_seed_timestamp_is_immutable(
    tmp_path: Path,
    tampered_at: str,
) -> None:
    """Catches a valid ISO timestamp replacing the immutable seed anchor."""

    database = tmp_path / f"ack-seed-time-tamper-{tampered_at[-3:-1]}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-seed-time-tamper")
    event = store.events(task_id, _scope())[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'voice', 0, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                event.event_id,
                event.occurred_at,
            ),
        )
        connection.commit()
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-seed-time-tamper-{tampered_at}",
    )
    adopted = SqliteTaskStore(database).ack_events(
        command,
        observed_at="2026-08-05T12:00:01Z",
    )
    assert adopted.ok and adopted.result is not None
    assert adopted.result["advanced"] is False
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE task_event_consumption SET updated_at=?",
            (tampered_at,),
        )
        connection.commit()
    before_reopen_bytes = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteTaskStore(database)

    assert corrupt.value.reason == "TASK_STORE_CORRUPT"
    assert database.read_bytes() == before_reopen_bytes


@pytest.mark.parametrize(
    ("event_at", "observed_at"),
    (
        (
            "2026-08-05T12:00:00.000000001Z",
            "2026-08-05T12:00:00.000000002Z",
        ),
        (
            "2026-08-05T12:00:00.1234567Z",
            "2026-08-05T12:00:00.1234568Z",
        ),
        (
            "2026-08-05T12:00:00.12345678Z",
            "2026-08-05T12:00:00.12345679Z",
        ),
        (
            "2026-08-05T12:00:00.123456789Z",
            "2026-08-05T12:00:00.123456790Z",
        ),
        (
            "2026-08-05T12:00:00.999999999Z",
            "2026-08-05T12:00:01Z",
        ),
    ),
)
def test_runtime_ack_preserves_contract_nanoseconds_when_ordering_event_time(
    tmp_path: Path,
    event_at: str,
    observed_at: str,
) -> None:
    """Catches seventh-to-ninth fractional digits collapsing to microseconds."""

    label = event_at.split(".")[-1].removesuffix("Z")
    database = tmp_path / f"ack-nanosecond-positive-{label}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task_at(
        store,
        tmp_path,
        suffix=f"-ack-nanosecond-positive-{label}",
        now=event_at,
    )
    event = store.events(task_id, _scope())[0]
    assert event.occurred_at == event_at
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-nanosecond-positive-{label}",
    )

    applied = store.ack_events(command, observed_at=observed_at)

    assert applied.ok and applied.result is not None
    assert applied.result["advanced"] is True
    assert applied.result["consumption_history"]["current"]["updated_at"] == (
        observed_at
    )
    assert _consumer_rows(database)[0][4:] == (
        0,
        event.event_id,
        observed_at,
    )
    assert SqliteTaskStore(database).unread_events_page(
        task_id,
        _scope(),
        presentation_class="text",
        limit=500,
    ).watermark == 0


def test_legacy_seed_adoption_preserves_nanosecond_ordering(tmp_path: Path) -> None:
    """Catches a +1ns seed adoption being collapsed into an equal timestamp."""

    event_at = "2026-08-05T12:00:00.000000001Z"
    observed_at = "2026-08-05T12:00:00.000000002Z"
    database = tmp_path / "ack-seed-nanosecond-adoption.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task_at(
        store,
        tmp_path,
        suffix="-ack-seed-nanosecond-adoption",
        now=event_at,
    )
    event = store.events(task_id, _scope())[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'voice', 0, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                event.event_id,
                event_at,
            ),
        )
        connection.commit()
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="voice",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id="command-ack-seed-nanosecond-adoption",
    )

    adopted = SqliteTaskStore(database).ack_events(
        command,
        observed_at=observed_at,
    )

    assert adopted.ok and adopted.result is not None
    history = adopted.result["consumption_history"]
    assert history["origin"] == "legacy_seed_v1"
    assert history["previous"]["updated_at"] == event_at
    assert history["current"]["updated_at"] == event_at
    assert history["previous"]["history_sha256"] is None
    assert SqliteTaskStore(database).unread_events_page(
        task_id,
        _scope(),
        presentation_class="voice",
        limit=500,
    ).watermark == 0


@pytest.mark.parametrize(
    "observed_at",
    (
        "2026-08-05T12:00:00.000000001Z",
        "2026-08-05T12:00:00.000000000Z",
    ),
)
def test_nanosecond_equal_or_earlier_ack_is_durable_stale_and_zero_consumer(
    tmp_path: Path,
    observed_at: str,
) -> None:
    """Catches equal or pre-event nanoseconds escaping the stale boundary."""

    event_at = "2026-08-05T12:00:00.000000001Z"
    database = tmp_path / f"ack-nanosecond-stale-{observed_at[-4:-1]}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task_at(
        store,
        tmp_path,
        suffix=f"-ack-nanosecond-stale-{observed_at[-4:-1]}",
        now=event_at,
    )
    event = store.events(task_id, _scope())[0]
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-nanosecond-stale-{observed_at}",
    )
    before_authority = _nonconsumption_authority(database)

    rejected = store.ack_events(command, observed_at=observed_at)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_ACK_PRECONDITION_STALE"
    assert rejected.error.code is ErrorCode.STALE
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority
    assert SqliteTaskStore(database).ack_events(
        replace(command, request_id=f"request-replay-{observed_at}"),
        observed_at="2026-08-05T12:00:01Z",
    ) == rejected.for_request(f"request-replay-{observed_at}")


@pytest.mark.parametrize(
    "observed_at",
    (
        "2026-08-05T12:00:00.1234567890Z",
        "2026-08-05T12:00:00.Z",
        "2026-08-05T14:00:00.000000002+02:00",
        "2026-02-30T12:00:00.000000002Z",
    ),
)
def test_ack_rejects_noncanonical_nanosecond_observation_before_writes(
    tmp_path: Path,
    observed_at: str,
) -> None:
    """Catches the local order parser broadening the global timestamp wire."""

    database = tmp_path / "ack-nanosecond-noncanonical.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task_at(
        store,
        tmp_path,
        suffix=f"-ack-nanosecond-noncanonical-{len(observed_at)}",
        now="2026-08-05T12:00:00.000000001Z",
    )
    event = store.events(task_id, _scope())[0]
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-nanosecond-noncanonical-{observed_at}",
    )
    before_counts = store.counts()
    before_authority = _nonconsumption_authority(database)

    with pytest.raises(FormalTaskViolation) as invalid:
        store.ack_events(command, observed_at=observed_at)

    assert invalid.value.reason == "TASK_ACK_INVALID"
    assert store.counts() == before_counts
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority


@pytest.mark.parametrize(
    "observed_at",
    (NOW, "2026-08-05T11:59:59Z"),
)
def test_runtime_ack_at_or_before_event_is_durable_stale_without_consumption(
    tmp_path: Path,
    observed_at: str,
) -> None:
    """Catches a runtime row becoming indistinguishable from a Task4 seed."""

    database = tmp_path / f"ack-temporal-stale-{observed_at[-3:-1]}.sqlite"
    store = SqliteTaskStore(database)
    task_id = _create_task(store, tmp_path, suffix="-ack-temporal-stale")
    event = store.events(task_id, _scope())[0]
    assert event.occurred_at == NOW
    command, _grant_unused = _ack_command(
        task_id,
        presentation_class="text",
        acked_through_seq=0,
        acked_event_id=event.event_id,
        expected_event_head=0,
        command_id=f"command-ack-temporal-stale-{observed_at}",
    )
    before_counts = store.counts()
    before_authority = _nonconsumption_authority(database)
    before_schema = _schema_identity(database)

    rejected = store.ack_events(command, observed_at=observed_at)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_ACK_PRECONDITION_STALE"
    assert rejected.error.code is ErrorCode.STALE
    assert store.counts() == {
        **before_counts,
        "commands": before_counts["commands"] + 1,
    }
    assert _consumer_rows(database) == []
    assert _nonconsumption_authority(database) == before_authority
    assert _schema_identity(database) == before_schema
    reopened = SqliteTaskStore(database)
    before_replay_bytes = database.read_bytes()
    replay = reopened.ack_events(
        replace(command, request_id=f"{command.request_id}-replay"),
        observed_at="2026-08-05T12:00:02Z",
    )
    assert replay == rejected.for_request(f"{command.request_id}-replay")
    assert database.read_bytes() == before_replay_bytes


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
    ack_time = _after(event.occurred_at) if decision == "applied" else NOW

    with pytest.raises(RuntimeError, match="injected ACK crash"):
        store.ack_events(command, observed_at=ack_time)

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
    lower_time = _after(events[-1].occurred_at)
    higher_time = _after(events[-1].occurred_at, seconds=2)

    def apply(
        store: SqliteTaskStore,
        command: CommandEnvelope,
        observed_at: str,
    ):
        barrier.wait(timeout=10)
        return store.ack_events(command, observed_at=observed_at)

    with ThreadPoolExecutor(max_workers=2) as pool:
        lower_future = pool.submit(apply, lower_store, lower, lower_time)
        higher_future = pool.submit(apply, higher_store, higher, higher_time)
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
            higher_time,
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
        writer.ack_events(command, observed_at=_after(events[3].occurred_at))
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

    applied = core.execute(command, full_grant, now=_after(event.occurred_at))

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
    applied = before_ack_restart.ack_events(
        command,
        observed_at=_after(terminal.occurred_at),
    )
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
    observed_at = _after(event.occurred_at) if corruption == "consumer" else NOW
    result = store.ack_events(command, observed_at=observed_at)
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
