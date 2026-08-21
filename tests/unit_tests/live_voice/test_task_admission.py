# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    TerminalOutcome,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    AdmissionDisposition,
    AdmissionPolicy,
    AdmissionPriority,
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskState,
    FormalTaskViolation,
    OutboxState,
    PersistedExecutorSelection,
    ReconciliationState,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentState,
    TaskMutationDisposition,
)
from jiuwenswarm.server.live_voice.persistent_task_core import PersistentTaskCore
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from tests.unit_tests.live_voice.test_persistent_task_core import (
    NOW,
    _adjust,
    _cancel,
    _context,
    _create,
    _Executor,
    _observations,
    _list_tasks,
    _retry,
    _scope,
    _status,
    _successor_command,
    _task_authority_dump,
    _terminal_task,
    _wave2_command,
)


ADMISSION_COLUMNS = (
    "adapter_id",
    "capability_profile_json",
    "capability_profile_digest",
    "execution_requirements_json",
    "admission_priority",
    "admission_reason",
    "admission_attempt_count",
    "admission_next_eligible_at",
    "admission_deadline_at",
    "admission_enqueued_at",
)


@pytest.mark.parametrize(
    "policy_kwargs",
    [
        {"deadline_seconds": float("nan")},
        {"initial_backoff_seconds": float("inf")},
        {"max_backoff_seconds": float("inf")},
        {"max_attempts": True},
    ],
)
def test_admission_policy_rejects_non_finite_or_boolean_bounds(
    policy_kwargs: dict[str, object],
) -> None:
    with pytest.raises(FormalTaskViolation) as invalid:
        AdmissionPolicy(**policy_kwargs)

    assert invalid.value.reason == "INVALID_ADMISSION_POLICY"


@pytest.mark.parametrize(
    "policy_kwargs",
    [
        {"deadline_seconds": 1e308},
        {"initial_backoff_seconds": 1e-308},
        {"max_backoff_seconds": 1e308},
        {
            "initial_backoff_seconds": 1e-308,
            "max_backoff_seconds": 1e308,
        },
    ],
)
def test_admission_policy_rejects_finite_unrepresentable_durations(
    policy_kwargs: dict[str, object],
) -> None:
    """Catches finite policy values leaking timedelta or ratio overflow."""

    with pytest.raises(FormalTaskViolation) as invalid:
        AdmissionPolicy(**policy_kwargs)

    assert invalid.value.reason == "INVALID_ADMISSION_POLICY"


@pytest.mark.parametrize(
    "field_name",
    [
        "deadline_seconds",
        "initial_backoff_seconds",
        "max_backoff_seconds",
    ],
)
def test_admission_policy_normalizes_huge_integer_bounds_without_store_writes(
    tmp_path: Path,
    field_name: str,
) -> None:
    """Catches huge integers overflowing math.isfinite before normalization."""

    store = SqliteTaskStore(tmp_path / f"huge-{field_name}.sqlite")
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as invalid:
        AdmissionPolicy(**{field_name: 10**400})

    assert invalid.value.reason == "INVALID_ADMISSION_POLICY"
    assert invalid.value.code is ErrorCode.INVALID_ARGUMENT
    assert store.counts() == before


def test_admission_deadline_overflow_is_normalized_with_zero_store_effect(
    tmp_path: Path,
) -> None:
    """Catches representable duration overflowing its absolute UTC deadline."""

    store = SqliteTaskStore(tmp_path / "deadline-overflow.sqlite")
    invocation = _create(tmp_path, identity_suffix="-deadline-overflow")
    policy = AdmissionPolicy(deadline_seconds=1e12)
    before = store.counts()

    result = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=_selection(),
        admission_policy=policy,
    )

    assert not result.ok and result.error is not None
    assert result.error.reason == "INVALID_ADMISSION_POLICY"
    assert store.counts() == before


def test_falsy_nonpolicy_carriers_are_not_silently_defaulted(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "falsy-policy.sqlite")
    with pytest.raises(TypeError, match="AdmissionPolicy"):
        PersistentTaskCore(store, _Executor(), admission_policy=False)

    invocation = _create(tmp_path, identity_suffix="-falsy-policy")
    result = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=_selection(),
        admission_policy=False,
    )

    assert not result.ok and result.error is not None
    assert result.error.reason == "INVALID_ADMISSION_POLICY"
    assert store.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }


def _selection(
    *, priority: AdmissionPriority = AdmissionPriority.NORMAL
) -> PersistedExecutorSelection:
    profile = canonical_json_bytes(
        {
            "adapter_id": "direct-v1",
            "build_identity": "direct-build-2026-08-19",
            "max_live_workers": 32,
            "protocol_version": "p3-3.v1",
        }
    )
    requirements = canonical_json_bytes(
        {
            "required_capabilities": ["task.create"],
            "side_effect_class": "project_mutation",
        }
    )
    return PersistedExecutorSelection(
        adapter_id="direct-v1",
        capability_profile_json=profile,
        capability_profile_digest=hashlib.sha256(profile).hexdigest(),
        execution_requirements_json=requirements,
        admission_priority=priority,
    )


def _selected_create(
    store: SqliteTaskStore,
    tmp_path: Path,
    *,
    suffix: str,
    priority: AdmissionPriority = AdmissionPriority.NORMAL,
    observed_at: str = NOW,
    policy: AdmissionPolicy | None = None,
) -> tuple[str, str]:
    invocation = _create(tmp_path, identity_suffix=suffix)
    result = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=observed_at,
        selection=_selection(priority=priority),
        admission_policy=policy or AdmissionPolicy(),
    )
    assert result.ok and result.result is not None
    return str(result.result["task_id"]), str(result.result["attempt_id"])


def _complete_selected(store: SqliteTaskStore, item) -> None:
    assert item.selection is not None
    observations = tuple(
        replace(
            observation,
            adapter_id=item.selection.adapter_id,
            capability_profile_digest=item.selection.capability_profile_digest,
        )
        for observation in _observations(item)
    )
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )


def _reprioritize(
    task_id: str,
    attempt_id: str,
    event_head: int,
    priority: str,
    *,
    command_id: str,
):
    return _wave2_command(
        task_id,
        "task.reprioritize",
        {
            "attempt_id": attempt_id,
            "expected_event_head": event_head,
            "priority": priority,
            "reason": "Raise queued execution urgency.",
        },
        command_id=command_id,
    )


def _database_dump(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


_V6_DURABILITY_TABLES = (
    "durability_recovery_fences",
    "durability_mutator_leases",
    "durability_recoveries",
    "durability_effect_facts",
    "durability_checkpoints",
)


def _downgrade_empty_current_to_v4(database: Path) -> None:
    """Rebuild the exact empty v4 shape used by the accepted Task 2 baseline."""

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        for table in _V6_DURABILITY_TABLES:
            connection.execute(f"DROP TABLE {table}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "task_event_consumption" in tables:
            connection.execute("DROP TABLE task_event_consumption")
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        if "uq_task_events_exact" in indexes:
            connection.execute("DROP INDEX uq_task_events_exact")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
        if set(ADMISSION_COLUMNS) & columns:
            connection.execute(
                """CREATE TABLE attempts_v4 (
                    attempt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    attempt_number INTEGER NOT NULL
                        CHECK(attempt_number BETWEEN 1 AND 3),
                    executor_id TEXT NOT NULL, executor_ref TEXT,
                    state TEXT NOT NULL, outcome TEXT,
                    source_seq INTEGER NOT NULL DEFAULT -1,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, attempt_number))"""
            )
            connection.execute(
                """INSERT INTO attempts_v4(
                    attempt_id, task_id, attempt_number, executor_id,
                    executor_ref, state, outcome, source_seq, updated_at)
                   SELECT attempt_id, task_id, attempt_number, executor_id,
                          executor_ref, state, outcome, source_seq, updated_at
                   FROM attempts"""
            )
            connection.execute("DROP TABLE attempts")
            connection.execute("ALTER TABLE attempts_v4 RENAME TO attempts")
        connection.execute("UPDATE metadata SET value='4' WHERE key='schema_version'")
        connection.commit()


def test_fresh_v6_schema_has_exact_admission_consumption_and_durability_shape(
    tmp_path: Path,
) -> None:
    """Catches a current bootstrap that omits or renames owned DDL."""

    database = tmp_path / "fresh-v6.sqlite"
    SqliteTaskStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)
        attempt_columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(attempts)")
        )
        assert attempt_columns[-len(ADMISSION_COLUMNS) :] == ADMISSION_COLUMNS
        assert all(
            row[3] == 0
            for row in connection.execute("PRAGMA table_info(attempts)")
            if row[1] in ADMISSION_COLUMNS
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "task_event_consumption" in tables
        assert set(_V6_DURABILITY_TABLES) <= tables
        assert tuple(
            row[1]
            for row in connection.execute("PRAGMA table_info(task_event_consumption)")
        ) == (
            "subject_id",
            "project_id",
            "task_id",
            "presentation_class",
            "acked_through_seq",
            "acked_event_id",
            "updated_at",
        )
        fk_rows = connection.execute(
            "PRAGMA foreign_key_list(task_event_consumption)"
        ).fetchall()
        grouped = {}
        for row in fk_rows:
            grouped.setdefault(row[0], []).append(row)
        assert {
            (
                tuple(item[3] for item in sorted(rows, key=lambda value: value[1])),
                rows[0][2],
                tuple(item[4] for item in sorted(rows, key=lambda value: value[1])),
                rows[0][6].upper(),
            )
            for rows in grouped.values()
        } == {
            (
                ("task_id", "acked_through_seq", "acked_event_id"),
                "task_events",
                ("task_id", "seq", "event_id"),
                "CASCADE",
            )
        }


def test_v4_to_v6_migration_is_atomic_and_metadata_is_last(tmp_path: Path) -> None:
    """Catches a partial current-schema promotion or early metadata update."""

    database = tmp_path / "v4-to-v6.sqlite"
    SqliteTaskStore(database)
    _downgrade_empty_current_to_v4(database)

    reopened = SqliteTaskStore(database)

    assert reopened.counts()["attempts"] == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)
        assert (
            ADMISSION_COLUMNS
            == tuple(
                row[1] for row in connection.execute("PRAGMA table_info(attempts)")
            )[-len(ADMISSION_COLUMNS) :]
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "failpoint",
    [
        "migration.v4_to_v5.before_columns",
        "migration.v4_to_v5.after_columns",
        "migration.v4_to_v5.after_consumption",
        "migration.v4_to_v5.after_indexes",
        "migration.v4_to_v5.before_metadata",
    ],
)
def test_v4_to_v5_failpoints_restore_exact_v4(tmp_path: Path, failpoint: str) -> None:
    """Catches any v5 failpoint that leaks DDL outside BEGIN EXCLUSIVE."""

    database = tmp_path / f"{failpoint}.sqlite"
    SqliteTaskStore(database)
    _downgrade_empty_current_to_v4(database)
    before = _database_dump(database)

    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match=failpoint):
        SqliteTaskStore(database, failpoint=fail)

    assert _database_dump(database) == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("4",)


@pytest.mark.parametrize("damage", ["partial_columns", "missing_consumption"])
def test_v5_partial_or_mislabeled_shape_fails_closed(
    tmp_path: Path, damage: str
) -> None:
    """Catches v5 acceptance when its version label and authoritative shape differ."""

    database = tmp_path / f"v5-{damage}.sqlite"
    SqliteTaskStore(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        if damage == "missing_consumption":
            connection.execute("DROP TABLE task_event_consumption")
        else:
            connection.execute("ALTER TABLE attempts RENAME TO attempts_v5")
            connection.execute(
                """CREATE TABLE attempts (
                    attempt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    attempt_number INTEGER NOT NULL
                        CHECK(attempt_number BETWEEN 1 AND 3),
                    executor_id TEXT NOT NULL, executor_ref TEXT,
                    state TEXT NOT NULL, outcome TEXT,
                    source_seq INTEGER NOT NULL DEFAULT -1,
                    updated_at TEXT NOT NULL,
                    adapter_id TEXT,
                    UNIQUE(task_id, attempt_number))"""
            )
            connection.execute("DROP TABLE attempts_v5")
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    ("table", "fragments"),
    [
        ("attempts", ("CHECK(admission_attempt_count >= 0)",)),
        (
            "task_event_consumption",
            (
                "CHECK(presentation_class IN ('text', 'voice'))",
                "CHECK(acked_through_seq >= 0)",
            ),
        ),
    ],
)
def test_v5_mislabeled_shape_without_owned_checks_fails_closed(
    tmp_path: Path, table: str, fragments: tuple[str, ...]
) -> None:
    database = tmp_path / f"v5-missing-check-{table}.sqlite"
    SqliteTaskStore(database)
    with sqlite3.connect(database) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
        for fragment in fragments:
            assert fragment in sql
            sql = sql.replace(fragment, "")
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET sql=? WHERE type='table' AND name=?",
            (sql, table),
        )
        connection.execute("PRAGMA writable_schema=OFF")
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert _database_dump(database) == before


def test_concurrent_initializers_converge_on_schema_v6(tmp_path: Path) -> None:
    """Catches a fresh-schema race that exposes a partial current schema."""

    database = tmp_path / "concurrent-v6.sqlite"
    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = tuple(pool.map(lambda _index: SqliteTaskStore(database), range(2)))

    assert all(store.counts()["attempts"] == 0 for store in stores)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("6",)


def test_v4_legacy_attempt_migrates_with_all_ten_admission_columns_null(
    tmp_path: Path,
) -> None:
    """Catches migration that relabels historical Attempts as selected work."""

    database = tmp_path / "legacy-v4-attempt.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    attempt_id = str(created.result["attempt_id"])
    _downgrade_empty_current_to_v4(database)

    reopened = SqliteTaskStore(database)

    assert reopened.get_attempt(attempt_id).attempt_id == attempt_id
    with sqlite3.connect(database) as connection:
        columns = ", ".join(ADMISSION_COLUMNS)
        assert connection.execute(
            f"SELECT {columns} FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone() == (None,) * len(ADMISSION_COLUMNS)


def test_v5_partial_selection_group_fails_closed_on_reopen(tmp_path: Path) -> None:
    """Catches acceptance of an Attempt that is neither legacy nor selected."""

    database = tmp_path / "partial-selection.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET adapter_id='direct-v1' WHERE attempt_id=?",
            (str(created.result["attempt_id"]),),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def _selected_authority_attempt(tmp_path: Path, lineage: str) -> tuple[Path, str]:
    """Create one selected Attempt through the named immutable command lineage."""

    if lineage in {"create", "terminal"}:
        database = tmp_path / f"selected-authority-{lineage}.sqlite"
        store = SqliteTaskStore(database)
        _task_id, attempt_id = _selected_create(
            store,
            tmp_path,
            suffix=f"-selected-authority-{lineage}",
        )
        if lineage == "terminal":
            item = store.claim_outbox("selected-authority-terminal", observed_at=NOW)
            assert item is not None and item.selection is not None
            observations = tuple(
                replace(
                    observation,
                    adapter_id=item.selection.adapter_id,
                    capability_profile_digest=(
                        item.selection.capability_profile_digest
                    ),
                )
                for observation in _observations(
                    item, outcome=TerminalOutcome.CANCELLED
                )
            )
            store.complete_outbox(
                item,
                executor_ref=f"legacy:{item.attempt_id}",
                observations=observations,
            )
        return database, attempt_id

    store, _executor, core, predecessor_id, predecessor_attempt_id = _terminal_task(
        tmp_path
    )
    database = store.database_path
    selection = _selection()
    if lineage == "retry":
        command, grant = _retry(
            predecessor_id,
            predecessor_attempt_id,
            TerminalOutcome.CANCELLED,
            2,
            command_id="command-selected-authority-retry",
        )
        result = core.execute(
            command,
            grant,
            context=replace(
                _context(tmp_path), revision_value="selected-authority-retry"
            ),
            now=NOW,
            selection=selection,
            admission_policy=AdmissionPolicy(),
        )
    else:
        assert lineage == "successor"
        predecessor = store.get_task(predecessor_id, _scope())
        terminal_event = store.events(predecessor_id, _scope())[-1]
        command, grant = _successor_command(
            predecessor,
            terminal_event,
            result_sha256=None,
            command_id="command-selected-authority-successor",
        )
        result = core.execute(
            command,
            grant,
            context=replace(
                _context(tmp_path), revision_value="selected-authority-successor"
            ),
            now=NOW,
            selection=selection,
            admission_policy=AdmissionPolicy(),
        )
    assert result.ok and result.result is not None
    return database, str(result.result["attempt_id"])


@pytest.mark.parametrize("lineage", ["create", "retry", "successor", "terminal"])
def test_selected_attempt_cannot_downgrade_to_legacy_when_columns_are_cleared(
    tmp_path: Path, lineage: str
) -> None:
    """Catches immutable selected command authority reopening as legacy."""

    database, attempt_id = _selected_authority_attempt(tmp_path, lineage)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET "
            + ", ".join(f"{column}=NULL" for column in ADMISSION_COLUMNS)
            + " WHERE attempt_id=?",
            (attempt_id,),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def test_selected_attempt_partial_clear_fails_closed_on_reopen(
    tmp_path: Path,
) -> None:
    """Catches a selected row shedding one required admission authority fact."""

    database, attempt_id = _selected_authority_attempt(tmp_path, "create")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET admission_deadline_at=NULL WHERE attempt_id=?",
            (attempt_id,),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize("lineage", ["create", "retry", "successor"])
@pytest.mark.parametrize(
    "forged_enqueued_at",
    ["2026-08-05T11:59:59Z", "2026-08-05T12:00:01Z"],
)
def test_selected_enqueue_timestamp_is_bound_to_immutable_creation_authority(
    tmp_path: Path, lineage: str, forged_enqueued_at: str
) -> None:
    """Catches FIFO authority drifting earlier or later than real creation."""

    database, attempt_id = _selected_authority_attempt(tmp_path, lineage)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET admission_enqueued_at=? WHERE attempt_id=?",
            (forged_enqueued_at, attempt_id),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize("authority", ["dispatch", "boundary"])
def test_selected_enqueue_rejects_changed_creation_timestamp_authority(
    tmp_path: Path, authority: str
) -> None:
    """Catches admission FIFO trusting a dispatch or event timestamp rewrite."""

    database, attempt_id = _selected_authority_attempt(tmp_path, "create")
    with sqlite3.connect(database) as connection:
        if authority == "dispatch":
            connection.execute(
                "UPDATE outbox SET created_at=? WHERE attempt_id=? AND kind=?",
                (
                    "2026-08-05T12:00:01Z",
                    attempt_id,
                    "attempt.dispatch",
                ),
            )
        else:
            connection.execute(
                """UPDATE task_events SET occurred_at=?
                   WHERE attempt_id=? AND event_type='task.accepted'""",
                ("2026-08-05T12:00:01Z", attempt_id),
            )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    ("attempt_count", "reason", "delivery_count", "last_error"),
    [
        (0, "EXECUTOR_PROJECT_BUSY", 0, None),
        (1, None, 1, None),
        (1, "EXECUTOR_PROJECT_BUSY", 1, None),
    ],
)
def test_v5_admission_count_and_reason_must_prove_closed_delivery_history(
    tmp_path: Path,
    attempt_count: int,
    reason: str | None,
    delivery_count: int,
    last_error: str | None,
) -> None:
    """Catches semantic shapes that cannot prove original or deferred delivery."""

    database = tmp_path / f"admission-history-{attempt_count}.sqlite"
    store = SqliteTaskStore(database)
    _selected_create(store, tmp_path, suffix=f"-history-{attempt_count}")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE attempts SET admission_attempt_count=?, admission_reason=?",
            (attempt_count, reason),
        )
        connection.execute(
            "UPDATE outbox SET delivery_count=?, last_error=?",
            (delivery_count, last_error),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def test_consumption_seed_reopens_only_when_consumer_scope_matches_task(
    tmp_path: Path,
) -> None:
    """Catches a structurally legal consumer row bound to another subject/project."""

    database = tmp_path / "consumer-scope.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    with sqlite3.connect(database) as connection:
        event = connection.execute(
            "SELECT seq, event_id FROM task_events WHERE task_id=? AND seq=0",
            (task_id,),
        ).fetchone()
        assert event is not None
        connection.execute(
            """INSERT INTO task_event_consumption(
                   subject_id, project_id, task_id, presentation_class,
                   acked_through_seq, acked_event_id, updated_at)
               VALUES(?, ?, ?, 'text', ?, ?, ?)""",
            (
                _scope().subject_id,
                _scope().project_id,
                task_id,
                event[0],
                event[1],
                NOW,
            ),
        )
        connection.commit()

    assert SqliteTaskStore(database).get_task(task_id, _scope()).task_id == task_id
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE task_event_consumption SET subject_id='other-subject'"
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    ("profile", "digest", "reason"),
    [
        (
            b'{"b":2, "a":1}',
            hashlib.sha256(b'{"b":2, "a":1}').hexdigest(),
            "EXECUTOR_SELECTION_JSON_NOT_CANONICAL",
        ),
        (
            canonical_json_bytes({"adapter_id": "direct-v1"}),
            "0" * 64,
            "EXECUTOR_SELECTION_DIGEST_MISMATCH",
        ),
    ],
)
def test_executor_selection_rejects_noncanonical_or_changed_profile(
    profile: bytes, digest: str, reason: str
) -> None:
    """Catches lossy snapshots and caller-supplied digest/profile disagreement."""

    with pytest.raises(FormalTaskViolation) as rejected:
        PersistedExecutorSelection(
            adapter_id="direct-v1",
            capability_profile_json=profile,
            capability_profile_digest=digest,
            execution_requirements_json=canonical_json_bytes(
                {"side_effect_class": "project_mutation"}
            ),
            admission_priority=AdmissionPriority.NORMAL,
        )

    assert rejected.value.reason == reason


def test_executor_selection_from_values_normalizes_invalid_priority_error() -> None:
    """Catches enum constructor leakage across the Core/Store carrier boundary."""

    with pytest.raises(FormalTaskViolation) as rejected:
        PersistedExecutorSelection.from_values(
            adapter_id="direct-v1",
            capability_profile={"protocol_version": "p3-3.v1"},
            execution_requirements={"side_effect_class": "project_mutation"},
            admission_priority="critical",
        )

    assert rejected.value.reason == "INVALID_ADMISSION_PRIORITY"


def test_selected_create_persists_and_reopens_exact_canonical_bytes(
    tmp_path: Path,
) -> None:
    """Catches selection recomputation, JSON normalization drift, or deadline reset."""

    database = tmp_path / "selected-create.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    selection = _selection(priority=AdmissionPriority.HIGH)
    policy = AdmissionPolicy()

    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
        admission_policy=policy,
    )

    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    attempt = store.get_attempt(attempt_id)
    admission = store.admission_projection(task_id, _scope())
    assert attempt.selection == selection
    assert attempt.to_dict()["executor_selection"]["admission_priority"] == "high"
    assert admission.task_id == task_id
    assert admission.attempt_id == attempt_id
    assert admission.priority is AdmissionPriority.HIGH
    assert admission.reason is None
    assert admission.attempt_count == 0
    assert admission.next_eligible_at == NOW
    assert admission.deadline_at == "2026-08-05T13:00:00Z"
    assert admission.enqueued_at == NOW
    assert admission.queued is True
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            f"SELECT {', '.join(ADMISSION_COLUMNS)} FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
    assert row == (
        selection.adapter_id,
        selection.capability_profile_json.decode("utf-8"),
        selection.capability_profile_digest,
        selection.execution_requirements_json.decode("utf-8"),
        "high",
        None,
        0,
        NOW,
        "2026-08-05T13:00:00Z",
        NOW,
    )

    reopened = SqliteTaskStore(database)
    assert reopened.get_attempt(attempt_id).selection == selection
    assert reopened.admission_projection(task_id, _scope()) == admission


def test_reconciliation_scan_reopens_exact_executor_selection(tmp_path: Path) -> None:
    """Catches restart reconciliation silently dropping selected authority."""

    database = tmp_path / "selected-reconciliation-scan.sqlite"
    store = SqliteTaskStore(database)
    selection = _selection(priority=AdmissionPriority.HIGH)
    invocation = _create(tmp_path, identity_suffix="-selected-reconciliation-scan")
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(),
    )
    assert created.ok and created.result is not None

    scanned = SqliteTaskStore(database).nonterminal_attempts()

    assert len(scanned) == 1
    assert scanned[0][1].attempt_id == created.result["attempt_id"]
    assert scanned[0][1].selection == selection


@pytest.mark.parametrize(
    "damage",
    ["profile_json", "profile_blob", "profile_digest", "fractional_count"],
)
def test_selected_attempt_corruption_fails_closed_on_reopen(
    tmp_path: Path, damage: str
) -> None:
    """Catches reopening a selected Attempt under changed capability authority."""

    database = tmp_path / f"selected-{damage}.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    selection = _selection()
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(),
    )
    assert created.ok
    with sqlite3.connect(database) as connection:
        if damage == "profile_json":
            connection.execute(
                "UPDATE attempts SET capability_profile_json=?",
                ('{"adapter_id":"changed"}',),
            )
        elif damage == "profile_blob":
            connection.execute(
                "UPDATE attempts SET capability_profile_json=?",
                (sqlite3.Binary(selection.capability_profile_json),),
            )
        elif damage == "profile_digest":
            connection.execute(
                "UPDATE attempts SET capability_profile_digest=?", ("0" * 64,)
            )
        else:
            connection.execute("UPDATE attempts SET admission_attempt_count=0.5")
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def test_selected_late_callback_requires_exact_adapter_and_digest_before_writes(
    tmp_path: Path,
) -> None:
    """Catches a late callback mutating any ledger under a different selection."""

    database = tmp_path / "selected-callback.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    selection = _selection()
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(),
    )
    assert created.ok
    item = store.claim_outbox("worker-selection-binding", observed_at=NOW)
    assert item is not None
    observations = tuple(
        replace(
            observation,
            adapter_id=selection.adapter_id,
            capability_profile_digest="0" * 64,
        )
        for observation in _observations(item)
    )
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=observations,
        )

    assert rejected.value.reason == "EXECUTOR_SELECTION_MISMATCH"
    assert _database_dump(database) == before


def test_selected_adjustment_completion_rereads_exact_attempt_selection(
    tmp_path: Path,
) -> None:
    """Catches a claimed adjustment settling after its selection authority moved."""

    database = tmp_path / "selected-adjustment-completion.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path, identity_suffix="-selected-adjustment")
    selection = _selection()
    core = PersistentTaskCore(store, _Executor())
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(),
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    dispatch = store.claim_outbox("selected-adjustment-dispatch", observed_at=NOW)
    assert dispatch is not None
    _complete_selected(store, dispatch)
    command, grant = _adjust(
        task_id,
        "Apply one bounded selected adjustment.",
        command_id="command-selected-adjustment",
        request_id="request-selected-adjustment",
    )
    admitted = core.execute(command, grant, now=NOW)
    assert admitted.ok
    item = store.claim_outbox("selected-adjustment-delivery", observed_at=NOW)
    assert item is not None and item.executor_ref is not None
    assert item.selection == selection

    foreign_profile = canonical_json_bytes(
        {
            "adapter_id": "other-v1",
            "build_identity": "other-build-2026-08-20",
            "max_live_workers": 1,
            "protocol_version": "other.v1",
        }
    )
    foreign_requirements = canonical_json_bytes(
        {
            "required_capabilities": ["task.create"],
            "side_effect_class": "project_mutation",
        }
    )
    foreign = PersistedExecutorSelection(
        adapter_id="other-v1",
        capability_profile_json=foreign_profile,
        capability_profile_digest=hashlib.sha256(foreign_profile).hexdigest(),
        execution_requirements_json=foreign_requirements,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE attempts
               SET adapter_id=?, capability_profile_json=?,
                   capability_profile_digest=?, execution_requirements_json=?,
                   admission_priority=?
               WHERE attempt_id=?""",
            (
                foreign.adapter_id,
                foreign.capability_profile_json.decode("utf-8"),
                foreign.capability_profile_digest,
                foreign.execution_requirements_json.decode("utf-8"),
                foreign.admission_priority.value,
                item.attempt_id,
            ),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        store.complete_adjustment_outbox(
            item,
            TaskAdjustmentDeliveryResult(
                item.executor_ref,
                item.command_id,
                TaskAdjustmentState.APPLIED,
            ),
            observed_at=NOW,
        )

    assert rejected.value.reason == "EXECUTOR_SELECTION_MISMATCH"
    assert rejected.value.code is ErrorCode.PROTOCOL_VIOLATION
    assert _database_dump(database) == before


def test_selected_persisted_callback_binding_is_reverified_on_reopen(
    tmp_path: Path,
) -> None:
    """Catches canonical Executor history being rebound to another adapter."""

    database = tmp_path / "selected-callback-reopen.sqlite"
    store = SqliteTaskStore(database)
    _selected_create(store, tmp_path, suffix="-callback-reopen")
    item = store.claim_outbox("callback-reopen", observed_at=NOW)
    assert item is not None
    _complete_selected(store, item)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT source_event_id, canonical FROM executor_events ORDER BY source_seq"
        ).fetchone()
        assert row is not None
        payload = json.loads(row[1])
        payload["adapter_id"] = "different-adapter"
        connection.execute(
            "UPDATE executor_events SET canonical=? WHERE source_event_id=?",
            (canonical_json_bytes(payload), row[0]),
        )
        connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert _database_dump(database) == before


def test_legacy_all_null_callback_remains_compatible(tmp_path: Path) -> None:
    """Catches v5 accidentally requiring Task-3 binding facts from legacy attempts."""

    store = SqliteTaskStore(tmp_path / "legacy-callback.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    item = store.claim_outbox("worker-legacy-binding")
    assert item is not None
    observations = _observations(item)

    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )

    assert store.get_attempt(item.attempt_id).source_seq == 1


def test_retry_persists_new_selection_without_backfilling_predecessor(
    tmp_path: Path,
) -> None:
    """Catches retry reuse/backfill of the predecessor's immutable selection epoch."""

    store, _executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    command, grant = _retry(task_id, attempt_a, TerminalOutcome.CANCELLED, 2)
    selection = _selection(priority=AdmissionPriority.URGENT)

    result = core.execute(
        command,
        grant,
        context=replace(_context(tmp_path), revision_value="selected-retry-b"),
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(deadline_seconds=90),
    )

    assert result.ok and result.result is not None
    attempt_b = str(result.result["attempt_id"])
    assert store.get_attempt(attempt_a).selection is None
    assert store.get_attempt(attempt_b).selection == selection
    admission = store.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.attempt_id == attempt_b
    assert admission.deadline_at == "2026-08-05T12:01:30Z"
    reopened = SqliteTaskStore(store.database_path)
    assert reopened.get_attempt(attempt_b).selection == selection
    claimed = reopened.claim_outbox("selected-retry-reopen", observed_at=NOW)
    assert claimed is not None
    assert claimed.attempt_id == attempt_b
    assert claimed.selection == selection


def test_successor_persists_its_own_selection_without_mutating_predecessor(
    tmp_path: Path,
) -> None:
    """Catches successor selection leakage across immutable Task revisions."""

    store, _executor, core, predecessor_id, predecessor_attempt_id = _terminal_task(
        tmp_path
    )
    predecessor = store.get_task(predecessor_id, _scope())
    terminal_event = store.events(predecessor_id, _scope())[-1]
    command, grant = _successor_command(
        predecessor,
        terminal_event,
        result_sha256=None,
        command_id="command-selected-successor",
    )
    selection = _selection(priority=AdmissionPriority.LOW)

    result = core.execute(
        command,
        grant,
        context=replace(_context(tmp_path), revision_value="selected-successor"),
        now=NOW,
        selection=selection,
        admission_policy=AdmissionPolicy(deadline_seconds=30),
    )

    assert result.ok and result.result is not None
    successor_id = str(result.result["task_id"])
    successor_attempt_id = str(result.result["attempt_id"])
    assert store.get_attempt(predecessor_attempt_id).selection is None
    assert store.get_attempt(successor_attempt_id).selection == selection
    admission = store.admission_projection(successor_id, _scope())
    assert admission is not None
    assert admission.deadline_at == "2026-08-05T12:00:30Z"
    reopened = SqliteTaskStore(store.database_path)
    claimed = reopened.claim_outbox("selected-successor-reopen", observed_at=NOW)
    assert claimed is not None
    assert claimed.attempt_id == successor_attempt_id
    assert claimed.selection == selection


def test_admission_policy_defaults_and_all_four_configuration_inputs() -> None:
    assert AdmissionPolicy() == AdmissionPolicy(
        deadline_seconds=3_600,
        initial_backoff_seconds=1,
        max_backoff_seconds=60,
        max_attempts=120,
    )
    assert (
        AdmissionPolicy(
            deadline_seconds=90,
            initial_backoff_seconds=0.25,
            max_backoff_seconds=8,
            max_attempts=7,
        ).max_attempts
        == 7
    )


def test_claim_orders_selected_dispatch_by_priority_then_immutable_fifo(
    tmp_path: Path,
) -> None:
    """Catches updated-at drift or UUID order replacing priority/FIFO authority."""

    store = SqliteTaskStore(tmp_path / "priority-fifo.sqlite")
    expected_priority = []
    for suffix, priority in (
        ("-low", AdmissionPriority.LOW),
        ("-urgent", AdmissionPriority.URGENT),
        ("-normal", AdmissionPriority.NORMAL),
        ("-high", AdmissionPriority.HIGH),
    ):
        _task_id, attempt_id = _selected_create(
            store, tmp_path, suffix=suffix, priority=priority
        )
        expected_priority.append((priority, attempt_id))
    claimed = []
    for index in range(4):
        item = store.claim_outbox(f"priority-{index}", observed_at=NOW)
        assert item is not None and item.selection is not None
        claimed.append((item.selection.admission_priority, item.attempt_id))
        _complete_selected(store, item)
    assert claimed == sorted(
        expected_priority,
        key=lambda value: {
            AdmissionPriority.URGENT: 0,
            AdmissionPriority.HIGH: 1,
            AdmissionPriority.NORMAL: 2,
            AdmissionPriority.LOW: 3,
        }[value[0]],
    )

    fifo_store = SqliteTaskStore(tmp_path / "same-priority-fifo.sqlite")
    first = _selected_create(
        fifo_store,
        tmp_path,
        suffix="-fifo-a",
        observed_at="2026-08-05T12:00:00Z",
    )[1]
    second = _selected_create(
        fifo_store,
        tmp_path,
        suffix="-fifo-b",
        observed_at="2026-08-05T12:00:01Z",
    )[1]
    assert (
        fifo_store.claim_outbox(
            "fifo-first", observed_at="2026-08-05T12:00:02Z"
        ).attempt_id
        == first
    )
    first_item = fifo_store.get_attempt(first)
    assert first_item.attempt_id == first
    # The first item remains claimed; exact FIFO must not skip to a later peer.
    assert (
        fifo_store.claim_outbox(
            "fifo-second", observed_at="2026-08-05T12:00:02Z"
        ).attempt_id
        == second
    )

    deferred_store = SqliteTaskStore(tmp_path / "same-priority-deferred-fifo.sqlite")
    deferred_first = _selected_create(
        deferred_store,
        tmp_path,
        suffix="-deferred-fifo-a",
        observed_at="2026-08-05T12:00:00Z",
    )[1]
    _selected_create(
        deferred_store,
        tmp_path,
        suffix="-deferred-fifo-b",
        observed_at="2026-08-05T12:00:01Z",
    )
    deferred = deferred_store.claim_outbox(
        "deferred-fifo-first", observed_at="2026-08-05T12:00:02Z"
    )
    assert deferred is not None and deferred.attempt_id == deferred_first
    assert (
        deferred_store.defer_admission(
            deferred,
            reason="EXECUTOR_PROJECT_BUSY",
            policy=AdmissionPolicy(),
            observed_at="2026-08-05T12:00:02Z",
        )
        is AdmissionDisposition.DEFERRED
    )
    assert (
        deferred_store.claim_outbox(
            "deferred-fifo-again", observed_at="2026-08-05T12:00:03Z"
        ).attempt_id
        == deferred_first
    )


@pytest.mark.parametrize(
    "reason", ["EXECUTOR_PROJECT_BUSY", "EXECUTOR_CAPACITY_EXHAUSTED"]
)
def test_defer_admission_keeps_attempt_and_outbox_with_bounded_backoff(
    tmp_path: Path, reason: str
) -> None:
    """Catches retry allocation, delivery-count conflation, or deadline extension."""

    store = SqliteTaskStore(tmp_path / f"defer-{reason}.sqlite")
    policy = AdmissionPolicy(
        deadline_seconds=30,
        initial_backoff_seconds=1,
        max_backoff_seconds=2,
        max_attempts=5,
    )
    task_id, attempt_id = _selected_create(
        store, tmp_path, suffix=f"-{reason}", policy=policy
    )
    item = store.claim_outbox("defer-1", observed_at=NOW)
    assert item is not None

    first = store.defer_admission(item, reason=reason, policy=policy, observed_at=NOW)

    assert first is AdmissionDisposition.DEFERRED
    admission = store.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.attempt_id == attempt_id
    assert admission.attempt_count == 1
    assert admission.next_eligible_at == "2026-08-05T12:00:01Z"
    assert admission.deadline_at == "2026-08-05T12:00:30Z"
    assert admission.reason == reason
    assert (
        store.claim_outbox("too-early", observed_at="2026-08-05T12:00:00.999999Z")
        is None
    )
    item = store.claim_outbox("defer-2", observed_at="2026-08-05T12:00:01Z")
    assert item is not None
    assert item.attempt_id == attempt_id
    assert item.delivery_count == 2

    second = store.defer_admission(
        item,
        reason=reason,
        policy=policy,
        observed_at="2026-08-05T12:00:01Z",
    )

    assert second is AdmissionDisposition.DEFERRED
    admission = store.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.attempt_count == 2
    assert admission.next_eligible_at == "2026-08-05T12:00:03Z"
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT state, delivery_count, claimed_by, claim_token FROM outbox"
        ).fetchone() == ("pending", 2, None, None)
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone() == (1,)


def test_defer_near_power_of_two_never_exceeds_max_backoff(tmp_path: Path) -> None:
    """Catches floating-point saturation rounding one microsecond past the cap."""

    initial = 2996.7134700800784
    maximum = math.nextafter(math.ldexp(initial, 8), 0.0)
    assert maximum == 767158.6483405
    policy = AdmissionPolicy(
        deadline_seconds=2e6,
        initial_backoff_seconds=initial,
        max_backoff_seconds=maximum,
        max_attempts=20,
    )
    store = SqliteTaskStore(tmp_path / "near-power-of-two-backoff.sqlite")
    task_id, _attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-near-power-of-two-backoff",
        policy=policy,
    )
    observed_at = NOW

    for next_count in range(1, 10):
        item = store.claim_outbox(
            f"near-power-of-two-{next_count}", observed_at=observed_at
        )
        assert item is not None and item.delivery_count == next_count
        assert (
            store.defer_admission(
                item,
                reason="EXECUTOR_PROJECT_BUSY",
                policy=policy,
                observed_at=observed_at,
            )
            is AdmissionDisposition.DEFERRED
        )
        admission = store.admission_projection(task_id, _scope())
        assert admission is not None and admission.attempt_count == next_count
        if next_count < 9:
            observed_at = admission.next_eligible_at

    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    exact_upper_bound = (
        (observed + timedelta(seconds=maximum)).isoformat().replace("+00:00", "Z")
    )
    assert admission.next_eligible_at == exact_upper_bound
    assert datetime.fromisoformat(
        admission.next_eligible_at.replace("Z", "+00:00")
    ) - observed <= timedelta(seconds=maximum)


def test_defer_rejects_nonclosed_reason_with_zero_effects(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "defer-invalid.sqlite")
    _selected_create(store, tmp_path, suffix="-invalid-defer")
    item = store.claim_outbox("invalid-defer", observed_at=NOW)
    assert item is not None
    before = _database_dump(store.database_path)

    with pytest.raises(FormalTaskViolation) as rejected:
        store.defer_admission(
            item,
            reason="EXECUTOR_UNAVAILABLE",
            policy=AdmissionPolicy(),
            observed_at=NOW,
        )

    assert rejected.value.reason == "INVALID_ADMISSION_REASON"
    assert _database_dump(store.database_path) == before


def test_safe_budget_exhaustion_atomically_terminalizes_without_result(
    tmp_path: Path,
) -> None:
    """Catches an extra Attempt, missing terminal boundary, or false TaskResult."""

    store = SqliteTaskStore(tmp_path / "budget-timeout.sqlite")
    policy = AdmissionPolicy(
        deadline_seconds=60,
        initial_backoff_seconds=1,
        max_backoff_seconds=1,
        max_attempts=2,
    )
    task_id, attempt_id = _selected_create(
        store, tmp_path, suffix="-budget-timeout", policy=policy
    )
    first = store.claim_outbox("budget-1", observed_at=NOW)
    assert first is not None
    assert (
        store.defer_admission(
            first,
            reason="EXECUTOR_CAPACITY_EXHAUSTED",
            policy=policy,
            observed_at=NOW,
        )
        is AdmissionDisposition.DEFERRED
    )
    second = store.claim_outbox("budget-2", observed_at="2026-08-05T12:00:01Z")
    assert second is not None

    disposition = store.defer_admission(
        second,
        reason="EXECUTOR_CAPACITY_EXHAUSTED",
        policy=policy,
        observed_at="2026-08-05T12:00:01Z",
    )

    assert disposition is AdmissionDisposition.TIMED_OUT
    task = store.get_task(task_id, _scope())
    attempt = store.get_attempt(attempt_id)
    assert task.state is FormalTaskState.TERMINAL
    assert task.outcome is TerminalOutcome.FAILED
    assert attempt.state is FormalAttemptState.TERMINAL
    assert attempt.outcome is TerminalOutcome.FAILED
    events = store.events(task_id, _scope())
    assert [event.event_type for event in events] == [
        "task.accepted",
        "attempt.terminal",
        "task.terminal",
    ]
    assert events[-1].details == {"reason": "EXECUTOR_ADMISSION_TIMEOUT"}
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT state, claimed_by, claim_token FROM outbox"
        ).fetchone() == ("suppressed", None, None)
    assert (
        store.claim_outbox("budget-after", observed_at="2026-08-05T12:00:02Z") is None
    )


def test_first_closed_defer_can_safely_exhaust_configured_budget(
    tmp_path: Path,
) -> None:
    """Catches max_attempts=1 losing the current closed pre-effect proof."""

    store = SqliteTaskStore(tmp_path / "first-defer-timeout.sqlite")
    policy = AdmissionPolicy(max_attempts=1)
    task_id, attempt_id = _selected_create(
        store, tmp_path, suffix="-first-defer-timeout", policy=policy
    )
    item = store.claim_outbox("first-defer-timeout", observed_at=NOW)
    assert item is not None

    disposition = store.defer_admission(
        item,
        reason="EXECUTOR_PROJECT_BUSY",
        policy=policy,
        observed_at=NOW,
    )

    assert disposition is AdmissionDisposition.TIMED_OUT
    assert store.get_task(task_id, _scope()).outcome is TerminalOutcome.FAILED
    assert store.get_attempt(attempt_id).outcome is TerminalOutcome.FAILED
    assert [event.event_type for event in store.events(task_id, _scope())] == [
        "task.accepted",
        "attempt.terminal",
        "task.terminal",
    ]


@pytest.mark.parametrize("damage", ["delivery_gap", "missing_defer_proof"])
def test_deadline_claim_settles_only_proven_pre_effect_or_requires_manual_action(
    tmp_path: Path, damage: str
) -> None:
    """Catches Store-claim expiry being treated as Direct lease/lock proof."""

    safe = SqliteTaskStore(tmp_path / "deadline-safe.sqlite")
    safe_task, safe_attempt = _selected_create(
        safe,
        tmp_path,
        suffix="-deadline-safe",
        policy=AdmissionPolicy(deadline_seconds=2),
    )
    assert (
        safe.claim_outbox("deadline-safe", observed_at="2026-08-05T12:00:02Z") is None
    )
    assert safe.get_task(safe_task, _scope()).state is FormalTaskState.TERMINAL
    assert safe.get_attempt(safe_attempt).outcome is TerminalOutcome.FAILED

    unknown = SqliteTaskStore(tmp_path / f"deadline-unknown-{damage}.sqlite")
    unknown_task, unknown_attempt = _selected_create(
        unknown,
        tmp_path,
        suffix="-deadline-unknown",
        policy=AdmissionPolicy(deadline_seconds=2),
    )
    with sqlite3.connect(unknown.database_path) as connection:
        if damage == "missing_defer_proof":
            connection.execute(
                """UPDATE attempts SET admission_attempt_count=1,
                   admission_reason='EXECUTOR_PROJECT_BUSY'
                   WHERE attempt_id=?""",
                (unknown_attempt,),
            )
        connection.execute(
            "UPDATE outbox SET delivery_count=1 WHERE attempt_id=?",
            (unknown_attempt,),
        )
        connection.commit()

    assert (
        unknown.claim_outbox("deadline-unknown", observed_at="2026-08-05T12:00:02Z")
        is None
    )

    task = unknown.get_task(unknown_task, _scope())
    assert task.state is FormalTaskState.ACCEPTED
    assert task.outcome is None
    assert task.reconciliation_state is not None
    assert task.reconciliation_state.value == "required"
    assert task.reconciliation_reason is not None
    assert "MANUAL_ACTION_REQUIRED" in task.reconciliation_reason
    assert unknown.get_attempt(unknown_attempt).state is FormalAttemptState.ACCEPTED
    assert [event.event_type for event in unknown.events(unknown_task, _scope())] == [
        "task.accepted"
    ]
    with sqlite3.connect(unknown.database_path) as connection:
        assert connection.execute(
            "SELECT state, delivery_count FROM outbox"
        ).fetchone() == (OutboxState.SUPPRESSED.value, 1)
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )


def test_admission_timeout_suppresses_open_cancel_without_executor_or_result(
    tmp_path: Path,
) -> None:
    database = tmp_path / "timeout-open-cancel.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    task_id, _attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-timeout-open-cancel",
        policy=AdmissionPolicy(deadline_seconds=2),
    )
    dispatch = store.claim_outbox("timeout-open-cancel", observed_at=NOW)
    assert dispatch is not None
    assert (
        store.defer_admission(
            dispatch,
            reason="EXECUTOR_PROJECT_BUSY",
            policy=AdmissionPolicy(deadline_seconds=2),
            observed_at=NOW,
        )
        is AdmissionDisposition.DEFERRED
    )
    cancel = _cancel(task_id)
    accepted = core.execute(
        cancel.envelope,
        cancel.authorization,
        now="2026-08-05T12:00:00.500000Z",
    )
    assert accepted.ok and accepted.result is not None
    assert accepted.result["applied"] is False

    assert (
        store.claim_outbox("timeout-after-cancel", observed_at="2026-08-05T12:00:02Z")
        is None
    )

    assert store.get_task(task_id, _scope()).outcome is TerminalOutcome.FAILED
    assert [event.event_type for event in store.events(task_id, _scope())] == [
        "task.accepted",
        "task.cancel_requested",
        "attempt.terminal",
        "task.terminal",
    ]
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT kind, state, last_error FROM outbox ORDER BY kind"
        ).fetchall() == [
            ("attempt.cancel", "suppressed", "EXECUTOR_ADMISSION_TIMEOUT"),
            ("attempt.dispatch", "suppressed", "EXECUTOR_ADMISSION_TIMEOUT"),
        ]
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM executor_events"
        ).fetchone() == (0,)
    SqliteTaskStore(database)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["EXECUTOR_PROJECT_BUSY", "EXECUTOR_CAPACITY_EXHAUSTED"]
)
async def test_core_defers_only_explicit_direct_pre_effect_capacity(
    tmp_path: Path, reason: str
) -> None:
    """Catches closed Direct capacity facts being collapsed into generic release."""

    class CapacityExecutor(_Executor):
        async def dispatch(self, item):
            self.dispatches.append(item.attempt_id)
            raise FormalTaskViolation(
                reason, "closed pre-effect", ErrorCode.UNAVAILABLE
            )

    store = SqliteTaskStore(tmp_path / f"core-{reason}.sqlite")
    executor = CapacityExecutor()
    policy = AdmissionPolicy(initial_backoff_seconds=1, max_backoff_seconds=2)
    core = PersistentTaskCore(store, executor, admission_policy=policy)
    invocation = _create(tmp_path, identity_suffix=f"-core-{reason}")
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=_selection(),
    )
    assert created.ok and created.result is not None

    assert await core.drain_outbox_once(worker_id="core-capacity", observed_at=NOW)

    admission = store.admission_projection(str(created.result["task_id"]), _scope())
    assert admission is not None
    assert admission.attempt_count == 1
    assert admission.reason == reason
    assert admission.queued is True
    assert executor.dispatches == [created.result["attempt_id"]]
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM executor_events"
        ).fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reason", "code"),
    [
        ("EXECUTOR_UNAVAILABLE", ErrorCode.UNAVAILABLE),
        ("EXECUTOR_DISPATCH_TIMEOUT", ErrorCode.TIMEOUT),
        ("EXECUTOR_OUTCOME_UNKNOWN", ErrorCode.RESULT_UNKNOWN),
    ],
)
async def test_core_does_not_reclassify_generic_unknown_delivery_as_capacity(
    tmp_path: Path, reason: str, code: ErrorCode
) -> None:
    """Catches unknown ownership being converted into a false pre-effect defer."""

    class UnknownExecutor(_Executor):
        async def dispatch(self, item):
            self.dispatches.append(item.attempt_id)
            raise FormalTaskViolation(reason, "ownership unknown", code)

    store = SqliteTaskStore(tmp_path / f"core-{reason}.sqlite")
    executor = UnknownExecutor()
    core = PersistentTaskCore(store, executor, admission_policy=AdmissionPolicy())
    invocation = _create(tmp_path, identity_suffix=f"-core-{reason}")
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=_selection(),
    )
    assert created.ok and created.result is not None

    with pytest.raises(FormalTaskViolation) as unavailable:
        await core.drain_outbox_once(worker_id="core-unknown", observed_at=NOW)

    assert unavailable.value.reason == reason
    admission = store.admission_projection(str(created.result["task_id"]), _scope())
    assert admission is not None
    assert admission.attempt_count == 0
    assert admission.reason is None
    assert admission.reconciliation_required is True
    assert admission.manual_action == "verify_external_ownership_and_settle"
    assert (
        store.claim_outbox("core-unknown-reclaim", observed_at="2026-08-05T12:00:01Z")
        is None
    )
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT state, delivery_count FROM outbox"
        ).fetchone() == (OutboxState.SUPPRESSED.value, 1)
        assert connection.execute(
            "SELECT COUNT(*) FROM executor_events"
        ).fetchone() == (0,)
    reopened = SqliteTaskStore(store.database_path)
    reopened_admission = reopened.admission_projection(
        str(created.result["task_id"]), _scope()
    )
    assert reopened_admission is not None
    assert reopened_admission.reconciliation_required is True


@pytest.mark.asyncio
async def test_reconcile_preserves_manual_admission_reconciliation_required(
    tmp_path: Path,
) -> None:
    """Catches restart audit downgrading unknown ownership to automatic pending."""

    class UnknownExecutor(_Executor):
        async def dispatch(self, item):
            self.dispatches.append(item.attempt_id)
            raise FormalTaskViolation(
                "EXECUTOR_OUTCOME_UNKNOWN",
                "ownership unknown",
                ErrorCode.RESULT_UNKNOWN,
            )

    database = tmp_path / "reconcile-unknown.sqlite"
    store = SqliteTaskStore(database)
    executor = UnknownExecutor()
    core = PersistentTaskCore(
        store,
        executor,
        admission_policy=AdmissionPolicy(deadline_seconds=365 * 24 * 60 * 60),
    )
    invocation = _create(tmp_path, identity_suffix="-reconcile-unknown")
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        selection=_selection(),
    )
    assert created.ok and created.result is not None

    summary = await core.reconcile()

    assert summary["delivery_unavailable"] == 1
    assert executor.dispatches == [created.result["attempt_id"]]
    admission = store.admission_projection(str(created.result["task_id"]), _scope())
    assert admission is not None
    assert admission.reconciliation_required is True
    assert admission.manual_action == "verify_external_ownership_and_settle"
    assert (
        store.claim_outbox(
            "reconcile-unknown-reclaim", observed_at="2026-08-05T12:00:01Z"
        )
        is None
    )
    reopened = SqliteTaskStore(database)
    reopened_admission = reopened.admission_projection(
        str(created.result["task_id"]), _scope()
    )
    assert reopened_admission is not None
    assert reopened_admission.reconciliation_required is True


def _selected_running_required_attempt(
    tmp_path: Path, *, suffix: str
) -> tuple[Path, str, str, PersistedExecutorSelection]:
    database = tmp_path / f"selected-required{suffix}.sqlite"
    store = SqliteTaskStore(database)
    task_id, attempt_id = _selected_create(
        store, tmp_path, suffix=f"-selected-required{suffix}"
    )
    item = store.claim_outbox(f"selected-required{suffix}", observed_at=NOW)
    assert item is not None and item.selection is not None
    _complete_selected(store, item)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """UPDATE tasks SET reconciliation_state=?, reconciliation_reason=?
               WHERE task_id=?""",
            (
                ReconciliationState.REQUIRED.value,
                "EXECUTOR_ADMISSION_OWNERSHIP_UNKNOWN_MANUAL_ACTION_REQUIRED",
                task_id,
            ),
        )
        connection.commit()
    return database, task_id, attempt_id, item.selection


@pytest.mark.asyncio
async def test_selected_required_reconcile_rejects_empty_status_after_reopen(
    tmp_path: Path,
) -> None:
    """Catches executor-ref equality resolving selected work without selection proof."""

    database, task_id, _attempt_id, _selection_epoch = (
        _selected_running_required_attempt(tmp_path, suffix="-empty")
    )

    class EmptyStatusExecutor(_Executor):
        async def status(self, _task, attempt):  # type: ignore[no-untyped-def]
            return ExecutorDeliveryResult(attempt.executor_ref, ())

    store = SqliteTaskStore(database)
    executor = EmptyStatusExecutor()
    core = PersistentTaskCore(store, executor)
    before = _database_dump(database)

    summary = await core.reconcile()

    task = store.get_task(task_id, _scope())
    assert summary["known"] == 0
    assert summary["unavailable"] == 1
    assert task.reconciliation_state is ReconciliationState.REQUIRED
    assert (
        task.reconciliation_reason
        == "EXECUTOR_ADMISSION_OWNERSHIP_UNKNOWN_MANUAL_ACTION_REQUIRED"
    )
    assert _database_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    reopened = SqliteTaskStore(database).get_task(task_id, _scope())
    assert reopened.reconciliation_state is ReconciliationState.REQUIRED


def test_mark_reconciliation_resolved_cannot_downgrade_manual_required(
    tmp_path: Path,
) -> None:
    """Catches a generic automatic settlement clearing manual ownership fencing."""

    database, task_id, attempt_id, _selection_epoch = (
        _selected_running_required_attempt(tmp_path, suffix="-direct-resolved")
    )
    store = SqliteTaskStore(database)
    before = _database_dump(database)

    result = store.mark_reconciliation_resolved(
        task_id, attempt_id, "EXECUTOR_STATE_UNCHANGED"
    )

    assert result.disposition is TaskMutationDisposition.NOOP
    assert (
        store.get_task(task_id, _scope()).reconciliation_state
        is ReconciliationState.REQUIRED
    )
    assert _database_dump(database) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["missing", "wrong"])
async def test_selected_required_reconcile_rejects_unbound_status_observation(
    tmp_path: Path, binding: str
) -> None:
    """Catches selected status evidence with absent or changed profile authority."""

    database, task_id, attempt_id, selection = _selected_running_required_attempt(
        tmp_path, suffix=f"-{binding}"
    )

    class UnboundStatusExecutor(_Executor):
        async def status(self, task, attempt):  # type: ignore[no-untyped-def]
            adapter_id = None if binding == "missing" else selection.adapter_id
            digest = None if binding == "missing" else "0" * 64
            return ExecutorObservation(
                resolution=ExecutorResolution.LOST,
                executor_id=self.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task.task_id,
                attempt_id=attempt.attempt_id,
                source_event_id=None,
                source_seq=None,
                attempt_state=None,
                attempt_outcome=None,
                occurred_at=NOW,
                raw_status="lost",
                error="EXECUTOR_ATTEMPT_LOST",
                adapter_id=adapter_id,
                capability_profile_digest=digest,
            )

    store = SqliteTaskStore(database)
    executor = UnboundStatusExecutor()
    before = _database_dump(database)

    summary = await PersistentTaskCore(store, executor).reconcile()

    assert summary["known"] == 0
    assert summary["unavailable"] == 1
    task = store.get_task(task_id, _scope())
    assert task.attempt_id == attempt_id
    assert task.reconciliation_state is ReconciliationState.REQUIRED
    assert _database_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.asyncio
async def test_selected_required_reconcile_accepts_exact_selection_observation(
    tmp_path: Path,
) -> None:
    """Preserves automatic settlement when status carries exact selected authority."""

    database, task_id, _attempt_id, selection = _selected_running_required_attempt(
        tmp_path, suffix="-exact"
    )

    class ExactStatusExecutor(_Executor):
        async def status(self, task, attempt):  # type: ignore[no-untyped-def]
            return ExecutorObservation(
                resolution=ExecutorResolution.LOST,
                executor_id=self.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task.task_id,
                attempt_id=attempt.attempt_id,
                source_event_id=None,
                source_seq=None,
                attempt_state=None,
                attempt_outcome=None,
                occurred_at=NOW,
                raw_status="lost",
                error="EXECUTOR_ATTEMPT_LOST",
                adapter_id=selection.adapter_id,
                capability_profile_digest=selection.capability_profile_digest,
            )

    store = SqliteTaskStore(database)
    summary = await PersistentTaskCore(store, ExactStatusExecutor()).reconcile()

    task = store.get_task(task_id, _scope())
    assert summary["lost"] == 1
    assert task.state is FormalTaskState.TERMINAL
    assert task.outcome is TerminalOutcome.INTERRUPTED
    assert task.reconciliation_state is None


@pytest.mark.asyncio
async def test_legacy_reconcile_empty_status_remains_compatible(
    tmp_path: Path,
) -> None:
    """Catches selected proof requirements disabling legacy empty status audit."""

    database = tmp_path / "legacy-empty-status.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path, identity_suffix="-legacy-empty-status")
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    item = store.claim_outbox("legacy-empty-status", observed_at=NOW)
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item),
    )

    summary = await PersistentTaskCore(store, _Executor()).reconcile()

    task = store.get_task(str(created.result["task_id"]), _scope())
    assert summary["known"] == 1
    assert task.reconciliation_state is ReconciliationState.RESOLVED
    assert task.reconciliation_reason == "EXECUTOR_STATE_UNCHANGED"


def test_status_and_list_project_queued_without_new_canonical_state(
    tmp_path: Path,
) -> None:
    """Catches queue UX being persisted as a fake Task lifecycle state."""

    store = SqliteTaskStore(tmp_path / "queued-projection.sqlite")
    core = PersistentTaskCore(store, _Executor())
    task_id, _attempt_id = _selected_create(
        store, tmp_path, suffix="-queued-projection"
    )
    before = _database_dump(store.database_path)
    status_query = _status(task_id)
    listed_query = _list_tasks(limit=10)

    status = core.query(status_query.envelope, status_query.authorization, now=NOW)
    listed = core.query(listed_query.envelope, listed_query.authorization, now=NOW)

    assert status.ok and status.result is not None
    assert status.result["task"]["state"] == "accepted"
    assert status.result["task"]["queued"] is True
    assert status.result["admission"]["queued"] is True
    assert listed.ok and listed.result is not None
    assert listed.result["tasks"][0]["state"] == "accepted"
    assert listed.result["tasks"][0]["queued"] is True
    assert listed.result["tasks"][0]["admission"]["priority"] == "normal"
    assert _database_dump(store.database_path) == before


def test_status_projection_uses_one_snapshot_during_legal_retry(
    tmp_path: Path,
) -> None:
    """Catches terminal Attempt A being combined with queued retry Attempt B."""

    seed_store, _seed_executor, _seed_core, task_id, attempt_a = _terminal_task(
        tmp_path
    )
    database = seed_store.database_path
    retry, grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.CANCELLED,
        2,
        command_id="command-status-snapshot-retry",
    )
    external_store = SqliteTaskStore(database)
    external_core = PersistentTaskCore(external_store, _Executor())
    race_attempt: list[str] = []
    post_race_dump: list[tuple[str, ...]] = []

    def failpoint(name: str) -> None:
        if name != "task_read_snapshot.after_task" or race_attempt:
            return
        retried = external_core.execute(
            retry,
            grant,
            context=replace(_context(tmp_path), revision_value="status-snapshot-retry"),
            now=NOW,
            selection=_selection(),
            admission_policy=AdmissionPolicy(),
        )
        assert retried.ok and retried.result is not None
        race_attempt.append(str(retried.result["attempt_id"]))
        post_race_dump.append(_database_dump(database))

    executor = _Executor()
    core = PersistentTaskCore(SqliteTaskStore(database, failpoint=failpoint), executor)
    query = _status(task_id)

    status = core.query(query.envelope, query.authorization, now=NOW)

    assert race_attempt and race_attempt[0] != attempt_a
    assert status.ok and status.result is not None
    assert status.result["task"]["attempt_id"] == attempt_a
    assert status.result["task"]["state"] == "terminal"
    assert status.result["task"]["queued"] is False
    assert status.result["attempt"]["attempt_id"] == attempt_a
    assert status.result["admission"] is None
    assert external_store.get_task(task_id, _scope()).attempt_id == race_attempt[0]
    assert _database_dump(database) == post_race_dump[0]
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


@pytest.mark.parametrize("mutation", ["retry", "successor", "settlement"])
def test_list_projection_uses_one_snapshot_during_legal_mutation(
    tmp_path: Path, mutation: str
) -> None:
    """Catches a page Task being combined with post-page Attempt authority."""

    if mutation == "settlement":
        database = tmp_path / "list-snapshot-settlement.sqlite"
        seed_store = SqliteTaskStore(database)
        task_id, attempt_id = _selected_create(
            seed_store, tmp_path, suffix="-list-snapshot-settlement"
        )
        expected_state = "accepted"
        expected_queued = True
    else:
        seed_store, _executor, _core, task_id, attempt_id = _terminal_task(tmp_path)
        database = seed_store.database_path
        expected_state = "terminal"
        expected_queued = False
    external_store = SqliteTaskStore(database)
    external_core = PersistentTaskCore(external_store, _Executor())
    predecessor = external_store.get_task(task_id, _scope())
    terminal_event = external_store.events(task_id, _scope())[-1]
    race_ids: list[str] = []
    post_race_dump: list[tuple[str, ...]] = []

    def failpoint(name: str) -> None:
        if name != "list_task_read_snapshots_page.after_tasks" or race_ids:
            return
        if mutation == "retry":
            command, grant = _retry(
                task_id,
                attempt_id,
                TerminalOutcome.CANCELLED,
                2,
                command_id="command-list-snapshot-retry",
            )
            changed = external_core.execute(
                command,
                grant,
                context=replace(
                    _context(tmp_path), revision_value="list-snapshot-retry"
                ),
                now=NOW,
                selection=_selection(),
                admission_policy=AdmissionPolicy(),
            )
            assert changed.ok and changed.result is not None
            race_ids.append(str(changed.result["attempt_id"]))
        elif mutation == "successor":
            command, grant = _successor_command(
                predecessor,
                terminal_event,
                result_sha256=None,
                command_id="command-list-snapshot-successor",
            )
            changed = external_core.execute(
                command,
                grant,
                context=replace(
                    _context(tmp_path), revision_value="list-snapshot-successor"
                ),
                now=NOW,
                selection=_selection(),
                admission_policy=AdmissionPolicy(),
            )
            assert changed.ok and changed.result is not None
            race_ids.append(str(changed.result["task_id"]))
        else:
            item = external_store.claim_outbox(
                "list-snapshot-settlement", observed_at=NOW
            )
            assert item is not None and item.attempt_id == attempt_id
            _complete_selected(external_store, item)
            race_ids.append(item.attempt_id)
        post_race_dump.append(_database_dump(database))

    executor = _Executor()
    core = PersistentTaskCore(SqliteTaskStore(database, failpoint=failpoint), executor)
    query = _list_tasks(limit=10)

    listed = core.query(query.envelope, query.authorization, now=NOW)

    assert race_ids
    assert listed.ok and listed.result is not None
    assert listed.result["has_more"] is False
    assert len(listed.result["tasks"]) == 1
    task = listed.result["tasks"][0]
    assert task["task_id"] == task_id
    assert task["attempt_id"] == attempt_id
    assert task["state"] == expected_state
    assert task["queued"] is expected_queued
    if mutation == "settlement":
        assert task["admission"]["attempt_id"] == attempt_id
        assert task["admission"]["queued"] is True
        assert (
            external_store.get_task(task_id, _scope()).state is FormalTaskState.RUNNING
        )
    else:
        assert task["admission"] is None
    assert _database_dump(database) == post_race_dump[0]
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []


def test_reconciliation_projection_exposes_bounded_manual_action(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "manual-projection.sqlite")
    task_id, attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-manual-projection",
        policy=AdmissionPolicy(deadline_seconds=1),
    )
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE outbox SET delivery_count=1 WHERE attempt_id=?", (attempt_id,)
        )
        connection.commit()
    assert (
        store.claim_outbox("manual-projection", observed_at="2026-08-05T12:00:01Z")
        is None
    )

    admission = store.admission_projection(task_id, _scope())

    assert admission is not None
    assert admission.reconciliation_required is True
    assert admission.manual_action == "verify_external_ownership_and_settle"
    assert admission.queued is False


def test_reprioritize_pending_selected_attempt_is_atomic_replayable_and_reopens(
    tmp_path: Path,
) -> None:
    """Catches priority changes that reorder identity or lack durable settlement."""

    database = tmp_path / "reprioritize-applied.sqlite"
    store = SqliteTaskStore(database)
    core = PersistentTaskCore(store, _Executor())
    task_id, attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-reprioritize-applied",
        priority=AdmissionPriority.LOW,
    )
    task = store.get_task(task_id, _scope())
    before = store.claim_outbox(
        "reprioritize-inspect", observed_at="2026-08-05T11:59:59Z"
    )
    assert before is None
    with sqlite3.connect(database) as connection:
        original = connection.execute(
            "SELECT outbox_id, created_at, delivery_count FROM outbox"
        ).fetchone()
    command, authorization = _reprioritize(
        task_id,
        attempt_id,
        task.event_head,
        "urgent",
        command_id="cmd-reprioritize-applied",
    )

    applied = core.execute(command, authorization, now="2026-08-05T12:00:01Z")

    assert applied.ok and applied.result is not None
    assert applied.result == {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "state": "accepted",
        "priority": "urgent",
        "applied": True,
    }
    admission = store.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.priority is AdmissionPriority.URGENT
    events = store.events(task_id, _scope())
    assert [event.event_type for event in events][-2:] == [
        "task.reprioritize_requested",
        "task.reprioritize_applied",
    ]
    assert events[-2].details == {
        "command_id": command.command_id,
        "priority": "urgent",
    }
    assert events[-1].details == events[-2].details
    replay_command, replay_authorization = _reprioritize(
        task_id,
        attempt_id,
        task.event_head,
        "urgent",
        command_id=command.command_id,
    )
    replay_command = replace(replay_command, request_id="request-reprioritize-replay")
    replay = core.execute(
        replay_command,
        replay_authorization,
        now="2026-08-05T12:00:09Z",
    )
    assert replay.to_dict() == {
        **applied.to_dict(),
        "request_id": "request-reprioritize-replay",
    }
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT outbox_id, created_at, delivery_count FROM outbox"
            ).fetchone()
            == original
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_id=?",
            (command.command_id,),
        ).fetchone() == (1,)

    reopened = SqliteTaskStore(database)
    reopened_admission = reopened.admission_projection(task_id, _scope())
    assert reopened_admission is not None
    assert reopened_admission.priority is AdmissionPriority.URGENT
    assert len(reopened.events(task_id, _scope())) == len(events)
    claimed = reopened.claim_outbox(
        "reprioritize-after-reopen", observed_at="2026-08-05T12:00:02Z"
    )
    assert claimed is not None
    assert claimed.attempt_id == attempt_id
    assert claimed.selection is not None
    assert claimed.selection.admission_priority is AdmissionPriority.URGENT


def test_reprioritize_after_closed_pre_effect_defer_preserves_queue_identity(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "reprioritize-deferred.sqlite")
    task_id, attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-reprioritize-deferred",
        priority=AdmissionPriority.LOW,
    )
    item = store.claim_outbox("reprioritize-deferred", observed_at=NOW)
    assert item is not None
    with sqlite3.connect(store.database_path) as connection:
        original_identity = connection.execute(
            "SELECT outbox_id, created_at FROM outbox"
        ).fetchone()
    assert (
        store.defer_admission(
            item,
            reason="EXECUTOR_PROJECT_BUSY",
            policy=AdmissionPolicy(),
            observed_at=NOW,
        )
        is AdmissionDisposition.DEFERRED
    )
    task = store.get_task(task_id, _scope())
    command, authorization = _reprioritize(
        task_id,
        attempt_id,
        task.event_head,
        "high",
        command_id="cmd-reprioritize-deferred",
    )

    applied = PersistentTaskCore(store, _Executor()).execute(
        command, authorization, now="2026-08-05T12:00:00.500000Z"
    )

    assert applied.ok
    admission = store.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.priority is AdmissionPriority.HIGH
    assert admission.attempt_count == 1
    assert admission.reason == "EXECUTOR_PROJECT_BUSY"
    with sqlite3.connect(store.database_path) as connection:
        row = connection.execute(
            "SELECT outbox_id, created_at, delivery_count, state FROM outbox"
        ).fetchone()
    assert row == (*original_identity, 1, OutboxState.PENDING.value)
    SqliteTaskStore(store.database_path)


@pytest.mark.parametrize(
    ("mode", "expected_reason"),
    [
        ("claimed", "TASK_CONTROL_STATE_CONFLICT"),
        ("ownership_gap", "TASK_CONTROL_STATE_CONFLICT"),
        ("running", "TASK_CONTROL_STATE_CONFLICT"),
        ("terminal", "TASK_CONTROL_STATE_CONFLICT"),
        ("legacy", "TASK_CONTROL_STATE_CONFLICT"),
        ("reconciliation", "TASK_CONTROL_STATE_CONFLICT"),
        ("stale_attempt", "TASK_CONTROL_PRECONDITION_STALE"),
        ("stale_head", "TASK_CONTROL_PRECONDITION_STALE"),
    ],
)
def test_reprioritize_conflicts_have_zero_queue_or_executor_effects(
    tmp_path: Path,
    mode: str,
    expected_reason: str,
) -> None:
    database = tmp_path / f"reprioritize-{mode}.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    if mode == "legacy":
        invocation = _create(tmp_path, identity_suffix=f"-reprioritize-{mode}")
        created = core.execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )
        assert created.ok and created.result is not None
        task_id = str(created.result["task_id"])
        attempt_id = str(created.result["attempt_id"])
    else:
        task_id, attempt_id = _selected_create(
            store, tmp_path, suffix=f"-reprioritize-{mode}"
        )

    if mode == "claimed":
        assert store.claim_outbox("reprioritize-claimed", observed_at=NOW) is not None
    elif mode == "ownership_gap":
        claimed = store.claim_outbox("reprioritize-gap", observed_at=NOW)
        assert claimed is not None
        assert store.release_outbox(claimed, "EXECUTOR_OUTCOME_UNKNOWN")
    elif mode in {"running", "terminal"}:
        claimed = store.claim_outbox(f"reprioritize-{mode}", observed_at=NOW)
        assert claimed is not None and claimed.selection is not None
        observations = tuple(
            replace(
                observation,
                adapter_id=claimed.selection.adapter_id,
                capability_profile_digest=(claimed.selection.capability_profile_digest),
            )
            for observation in _observations(
                claimed,
                outcome=(TerminalOutcome.FAILED if mode == "terminal" else None),
            )
        )
        store.complete_outbox(
            claimed,
            executor_ref=f"legacy:{attempt_id}",
            observations=(observations if mode == "terminal" else observations[:1]),
        )
    elif mode == "reconciliation":
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET delivery_count=1 WHERE attempt_id=?",
                (attempt_id,),
            )
            connection.execute(
                "UPDATE attempts SET admission_deadline_at=? WHERE attempt_id=?",
                (NOW, attempt_id),
            )
            connection.commit()
        assert (
            store.claim_outbox(
                "reprioritize-reconciliation",
                observed_at=NOW,
            )
            is None
        )

    task = store.get_task(task_id, _scope())
    addressed_attempt = "attempt-stale" if mode == "stale_attempt" else attempt_id
    addressed_head = task.event_head + 1 if mode == "stale_head" else task.event_head
    command, authorization = _reprioritize(
        task_id,
        addressed_attempt,
        addressed_head,
        "urgent",
        command_id=f"cmd-reprioritize-{mode}",
    )
    before = _task_authority_dump(database)

    result = core.execute(command, authorization, now="2026-08-05T12:00:09Z")

    assert not result.ok and result.error is not None
    assert result.error.reason == expected_reason, result.error
    assert _task_authority_dump(database) == before
    assert executor.dispatches == []
    assert executor.cancels == []
    assert executor.adjustments == []
    SqliteTaskStore(database)


def test_reconcile_callback_requires_exact_persisted_selection_before_writes(
    tmp_path: Path,
) -> None:
    """Catches the non-outbox callback path bypassing adapter/profile binding."""

    database = tmp_path / "reconcile-selection-binding.sqlite"
    store = SqliteTaskStore(database)
    _task_id, _attempt_id = _selected_create(
        store, tmp_path, suffix="-reconcile-selection-binding"
    )
    item = store.claim_outbox("reconcile-selection-binding", observed_at=NOW)
    assert item is not None and item.selection is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=(),
    )
    observations = tuple(
        replace(
            observation,
            adapter_id="wrong-adapter",
            capability_profile_digest=item.selection.capability_profile_digest,
        )
        for observation in _observations(item)
    )
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as mismatch:
        store.apply_observations(observations)

    assert mismatch.value.reason == "EXECUTOR_SELECTION_MISMATCH"
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    "failpoint",
    [
        "admission.timeout.after_attempt",
        "admission.timeout.after_attempt_event",
        "admission.timeout.after_task_event",
        "admission.timeout.after_outbox",
    ],
)
def test_admission_timeout_failpoints_roll_back_every_authority_surface(
    tmp_path: Path,
    failpoint: str,
) -> None:
    database = tmp_path / f"{failpoint}.sqlite"
    store = SqliteTaskStore(database)
    task_id, _attempt_id = _selected_create(
        store,
        tmp_path,
        suffix=f"-{failpoint}",
        policy=AdmissionPolicy(deadline_seconds=1),
    )
    before = _database_dump(database)

    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    failing = SqliteTaskStore(database, failpoint=fail)
    with pytest.raises(RuntimeError, match=failpoint):
        failing.claim_outbox("timeout-failpoint", observed_at="2026-08-05T12:00:01Z")

    assert _database_dump(database) == before
    assert (
        SqliteTaskStore(database).get_task(task_id, _scope()).state
        is FormalTaskState.ACCEPTED
    )


def test_concurrent_deadline_claimers_commit_one_terminal_settlement(
    tmp_path: Path,
) -> None:
    database = tmp_path / "deadline-race.sqlite"
    store = SqliteTaskStore(database)
    task_id, _attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-deadline-race",
        policy=AdmissionPolicy(deadline_seconds=1),
    )
    claimers = (SqliteTaskStore(database), SqliteTaskStore(database))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda pair: pair[1].claim_outbox(
                    f"deadline-racer-{pair[0]}",
                    observed_at="2026-08-05T12:00:01Z",
                ),
                enumerate(claimers),
            )
        )

    assert results == (None, None)
    reopened = SqliteTaskStore(database)
    assert [event.event_type for event in reopened.events(task_id, _scope())] == [
        "task.accepted",
        "attempt.terminal",
        "task.terminal",
    ]
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM task_events WHERE event_type='task.terminal'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )


def test_expired_store_claim_never_proves_direct_lease_or_os_lock_release(
    tmp_path: Path,
) -> None:
    database = tmp_path / "three-fence-reset.sqlite"
    store = SqliteTaskStore(database)
    task_id, _attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-three-fence-reset",
        policy=AdmissionPolicy(deadline_seconds=2),
    )
    assert store.claim_outbox("three-fence-owner", observed_at=NOW) is not None
    assert store.reset_expired_outbox_claims(claimed_before="2026-08-05T12:00:01Z") == 1

    reset_task = store.get_task(task_id, _scope())
    reset_admission = store.admission_projection(task_id, _scope())
    assert reset_task.reconciliation_state is not None
    assert reset_task.reconciliation_state.value == "required"
    assert reset_admission is not None
    assert reset_admission.reconciliation_required is True
    assert reset_admission.manual_action == "verify_external_ownership_and_settle"
    assert (
        store.claim_outbox("three-fence-reclaimer", observed_at="2026-08-05T12:00:01Z")
        is None
    )

    task = store.get_task(task_id, _scope())
    assert task.state is FormalTaskState.ACCEPTED
    assert task.reconciliation_state is not None
    assert task.reconciliation_state.value == "required"
    assert [event.event_type for event in store.events(task_id, _scope())] == [
        "task.accepted"
    ]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )
    reopened = SqliteTaskStore(database)
    reopened_admission = reopened.admission_projection(task_id, _scope())
    assert reopened_admission is not None
    assert reopened_admission.reconciliation_required is True


@pytest.mark.parametrize(
    "failpoint",
    [
        "reprioritize.after_requested_event",
        "reprioritize.after_attempt",
        "reprioritize.after_applied_event",
        "reprioritize.after_command",
    ],
)
def test_reprioritize_failpoints_roll_back_priority_events_and_ledger(
    tmp_path: Path,
    failpoint: str,
) -> None:
    database = tmp_path / f"{failpoint}.sqlite"
    store = SqliteTaskStore(database)
    task_id, attempt_id = _selected_create(
        store,
        tmp_path,
        suffix=f"-{failpoint}",
        priority=AdmissionPriority.LOW,
    )
    task = store.get_task(task_id, _scope())
    command, _authorization = _reprioritize(
        task_id,
        attempt_id,
        task.event_head,
        "urgent",
        command_id=f"cmd-{failpoint}",
    )
    before = _database_dump(database)

    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    failing = SqliteTaskStore(database, failpoint=fail)
    with pytest.raises(RuntimeError, match=failpoint):
        failing.reprioritize(command, observed_at="2026-08-05T12:00:01Z")

    assert _database_dump(database) == before
    reopened = SqliteTaskStore(database)
    admission = reopened.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.priority is AdmissionPriority.LOW


def test_concurrent_reprioritize_commands_have_one_applied_winner(
    tmp_path: Path,
) -> None:
    database = tmp_path / "reprioritize-race.sqlite"
    store = SqliteTaskStore(database)
    task_id, attempt_id = _selected_create(
        store,
        tmp_path,
        suffix="-reprioritize-race",
        priority=AdmissionPriority.LOW,
    )
    head = store.get_task(task_id, _scope()).event_head
    commands = tuple(
        _reprioritize(
            task_id,
            attempt_id,
            head,
            priority,
            command_id=f"cmd-reprioritize-race-{priority}",
        )[0]
        for priority in ("high", "urgent")
    )
    stores = (SqliteTaskStore(database), SqliteTaskStore(database))
    before_outbox = None
    with sqlite3.connect(database) as connection:
        before_outbox = connection.execute(
            "SELECT outbox_id, created_at, delivery_count FROM outbox"
        ).fetchone()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda pair: pair[1].reprioritize(
                    commands[pair[0]], observed_at="2026-08-05T12:00:01Z"
                ),
                enumerate(stores),
            )
        )

    assert sum(result.ok for result in results) == 1
    assert {result.error.reason for result in results if result.error is not None} == {
        "TASK_CONTROL_PRECONDITION_STALE"
    }
    reopened = SqliteTaskStore(database)
    admission = reopened.admission_projection(task_id, _scope())
    assert admission is not None
    assert admission.priority.value in {"high", "urgent"}
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT outbox_id, created_at, delivery_count FROM outbox"
            ).fetchone()
            == before_outbox
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE command_type='task.reprioritize'"
        ).fetchone() == (2,)
