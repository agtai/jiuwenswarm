# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CONTRACT_VERSION,
    Assurance,
    CommandEnvelope,
    ErrorCode,
    InputCommitState,
    QueryEnvelope,
    ScopeRef,
    TerminalOutcome,
    TurnCommit,
    TurnCommitLedger,
    WorkProgressEventV2,
    canonical_json_bytes,
)
from jiuwenswarm.server.live_voice.formal_task_models import (
    ExecutorDeliveryResult,
    ExecutorObservation,
    ExecutorResolution,
    ExecutorRetryReadiness,
    FormalAttemptState,
    FormalTaskState,
    FormalTaskViolation,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskEvent,
    PersistentTaskRecord,
    ReconciliationState,
    ResolvedTaskContext,
    TaskAuthorizationGrant,
    TaskAdjustmentDeliveryResult,
    TaskAdjustmentSettlement,
    TaskAdjustmentState,
    TaskEventAuthoritySnapshot,
    TaskMutationDisposition,
    TaskResultArtifact,
    TaskResultAvailability,
    TaskResultRecord,
    TaskRetryAuthoritySnapshot,
    TaskRetryProductRequestFingerprint,
    utc_now,
)
from jiuwenswarm.server.live_voice.persistent_task_core import (
    PersistentTaskCore,
    project_task_event,
)
from jiuwenswarm.server.live_voice.project_code_executor import (
    FORMAL_PROJECT_EXECUTOR_ID,
)
from jiuwenswarm.server.live_voice.task_store import SqliteTaskStore
from jiuwenswarm.server.live_voice.voice_task_policy import (
    FormalTaskPolicyAdapter,
    FormalTaskPolicyInput,
)

NOW = "2026-08-05T12:00:00Z"
EXPIRY = "2026-08-05T13:00:00Z"


def test_task_event_authority_snapshot_is_publicly_exported() -> None:
    from jiuwenswarm.server.live_voice import formal_task_models

    assert "TaskEventAuthoritySnapshot" in formal_task_models.__all__
    assert formal_task_models.TaskEventAuthoritySnapshot is TaskEventAuthoritySnapshot


def _scope() -> ScopeRef:
    return ScopeRef("user-1", "project-1", "session-1", Assurance.AUTHENTICATED)


def _grant(
    operation: str,
    *,
    command_id: str | None,
    target: str | None,
) -> TaskAuthorizationGrant:
    return TaskAuthorizationGrant(
        principal_id="user-1",
        scope=_scope(),
        operation=operation,
        command_id=command_id,
        target_task_id=target,
        allowed_capabilities=frozenset({operation}),
        confirmation_id="confirm-1" if command_id is not None else None,
        confirmed=command_id is not None,
        expires_at=EXPIRY,
    )


def _context(project: Path) -> ResolvedTaskContext:
    return ResolvedTaskContext(
        source="gateway.project_registry",
        stable_id="project-1",
        uri=project.resolve().as_uri(),
        revision_kind="version",
        revision_value="a77516a0",
        scope=_scope(),
        permissions=("task.execute", "project.write"),
        expires_at=EXPIRY,
        redaction_policy_id="live_voice.project.v1",
    )


def _create(
    project: Path,
    *,
    instruction: str = "Change one project file.",
    identity_suffix: str = "",
):
    command_id = f"command-create{identity_suffix}"
    commit_id = f"commit-1{identity_suffix}"
    turn_id = f"turn-1{identity_suffix}"
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="voice",
        operation="task.create",
        request_id=f"request-create{identity_suffix}",
        command_id=command_id,
        issued_at=NOW,
        scope=_scope(),
        correlation_id=f"correlation-1{identity_suffix}",
        authorization=_grant("task.create", command_id=command_id, target=None),
        interaction_id=f"interaction-1{identity_suffix}",
        turn_id=turn_id,
        commit_id=commit_id,
        name="Formal project task",
        instruction=instruction,
        context=_context(project),
        attributes={
            "model_identity": "default#0",
            "model_config_version": "catalog-v1",
        },
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
    )
    commits = TurnCommitLedger()
    commits.accept(
        TurnCommit.from_dict(
            {
                "contract_version": CONTRACT_VERSION,
                "commit_id": commit_id,
                "turn_id": turn_id,
                "interaction_id": f"interaction-1{identity_suffix}",
                "text": instruction,
                "hypothesis_provenance": {"provider": "test"},
                "scope": _scope().to_dict(),
                "context_refs": [],
                "committed_at": NOW,
            }
        )
    )
    return FormalTaskPolicyAdapter(commits).map(intent)


def _cancel(task_id: str):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.cancel",
        request_id="request-cancel",
        command_id="command-cancel",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant(
            "task.cancel", command_id="command-cancel", target=task_id
        ),
        task_id=task_id,
        destructive=True,
        confirmed=True,
        confirmation_id="confirm-1",
    )
    return FormalTaskPolicyAdapter().map(intent)


def _adjust(
    task_id: str,
    adjustment: str,
    *,
    command_id: str = "command-adjust",
    request_id: str = "request-adjust",
) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
    base = _cancel(task_id)
    payload = base.envelope.to_dict()
    payload.update(
        {
            "request_id": request_id,
            "command_id": command_id,
            "command_type": "task.adjust",
            "required_capabilities": ["task.adjust"],
            "payload": {"adjustment": adjustment},
        }
    )
    return (
        CommandEnvelope.from_dict(payload),
        _grant("task.adjust", command_id=command_id, target=task_id),
    )


def _retry(
    task_id: str,
    previous_attempt_id: str,
    previous_outcome: TerminalOutcome,
    attempt_number: int,
    *,
    command_id: str | None = None,
    correlation_id: str = "correlation-1",
) -> tuple[CommandEnvelope, TaskAuthorizationGrant]:
    retry_command_id = command_id or f"command-retry-{attempt_number}"
    product_request = _retry_product_request_fingerprint(
        command_id=retry_command_id,
        task_id=task_id,
        correlation_id=correlation_id,
    )
    command = CommandEnvelope.from_dict(
        {
            "contract_version": CONTRACT_VERSION,
            "request_id": f"request-retry-{attempt_number}",
            "command_id": retry_command_id,
            "command_type": "task.retry",
            "issued_at": NOW,
            "scope": _scope().to_dict(),
            "correlation_id": correlation_id,
            "causation_id": None,
            "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
            "target_ref": {"kind": "task", "id": task_id},
            "context_refs": [],
            "required_capabilities": ["task.retry"],
            "payload": {
                "previous_attempt_id": previous_attempt_id,
                "previous_outcome": previous_outcome.value,
                "attempt_number": attempt_number,
            },
            "extensions": product_request.to_extensions(),
        }
    )
    return command, _grant("task.retry", command_id=retry_command_id, target=task_id)


def _retry_product_request_fingerprint(
    *,
    command_id: str,
    task_id: str,
    issued_at: str = NOW,
    correlation_id: str = "correlation-1",
    causation_id: str | None = None,
    confirmation_id: str = "confirm-1",
) -> TaskRetryProductRequestFingerprint:
    """Model the product ledger facts; never include request_id or server facts."""

    product_owned_facts = {
        "operation": "task.retry",
        "scope": _scope().to_dict(),
        "command_id": command_id,
        "task_id": task_id,
        "issued_at": issued_at,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "origin": {"kind": "structured", "turn_id": None, "commit_id": None},
        "confirmation_id": confirmation_id,
    }
    assert "request_id" not in product_owned_facts
    assert "payload" not in product_owned_facts
    assert "context" not in product_owned_facts
    return TaskRetryProductRequestFingerprint(
        hashlib.sha256(canonical_json_bytes(product_owned_facts)).hexdigest()
    )


def _status(task_id: str):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.status",
        request_id="request-status",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.status", command_id=None, target=task_id),
        task_id=task_id,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _events(task_id: str, after_seq: int):
    intent = FormalTaskPolicyInput(
        state=InputCommitState.COMMITTED,
        source="structured",
        operation="task.events",
        request_id="request-events",
        issued_at=NOW,
        scope=_scope(),
        correlation_id="correlation-1",
        authorization=_grant("task.events", command_id=None, target=task_id),
        task_id=task_id,
        after_seq=after_seq,
    )
    return FormalTaskPolicyAdapter().map(intent)


def _observations(
    item: PersistentOutboxItem,
    *,
    outcome: TerminalOutcome | None = None,
    result_text: str | None = None,
    result_artifacts: tuple[TaskResultArtifact, ...] = (),
) -> tuple[ExecutorObservation, ...]:
    target_seq = 2 if outcome is not None else 1
    states = (
        (FormalAttemptState.ACCEPTED, None),
        (FormalAttemptState.RUNNING, None),
        (FormalAttemptState.TERMINAL, outcome),
    )
    result = []
    for seq in range(item.source_seq + 1, target_seq + 1):
        state, state_outcome = states[seq]
        result.append(
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=FORMAL_PROJECT_EXECUTOR_ID,
                executor_ref=f"legacy:{item.attempt_id}",
                task_id=item.task_id,
                attempt_id=item.attempt_id,
                source_event_id=f"legacy:{item.attempt_id}:{seq}",
                source_seq=seq,
                attempt_state=state,
                attempt_outcome=state_outcome,
                occurred_at=utc_now(),
                raw_status=("success" if outcome else "running"),
                result_text=(
                    result_text if state is FormalAttemptState.TERMINAL else None
                ),
                result_artifacts=(
                    result_artifacts if state is FormalAttemptState.TERMINAL else ()
                ),
            )
        )
    return tuple(result)


def _downgrade_fixture_to_v1(database: Path) -> None:
    """Rebuild only the v1 attempts table to exercise the real v2 migrator."""

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """CREATE TABLE attempts_v1 (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE
                    REFERENCES tasks(task_id) ON DELETE CASCADE,
                executor_id TEXT NOT NULL, executor_ref TEXT,
                state TEXT NOT NULL, outcome TEXT,
                source_seq INTEGER NOT NULL DEFAULT -1,
                updated_at TEXT NOT NULL)"""
        )
        connection.execute(
            """INSERT INTO attempts_v1(
                attempt_id, task_id, executor_id, executor_ref, state,
                outcome, source_seq, updated_at)
                SELECT attempt_id, task_id, executor_id, executor_ref, state,
                       outcome, source_seq, updated_at FROM attempts"""
        )
        connection.execute("DROP TABLE attempts")
        connection.execute("ALTER TABLE attempts_v1 RENAME TO attempts")
        connection.execute("DROP TABLE task_results")
        connection.execute("DROP TABLE current_background_tasks")
        connection.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
        connection.commit()


def _database_dump(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


def test_v1_schema_migrates_atomically_and_preserves_active_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    result = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert result.ok and result.result is not None
    task_id = str(result.result["task_id"])
    attempt_id = str(result.result["attempt_id"])
    before = store.counts()
    _downgrade_fixture_to_v1(database)

    reopened = SqliteTaskStore(database)

    assert reopened.counts() == before
    assert reopened.get_task(task_id, _scope()).attempt_id == attempt_id
    assert reopened.get_attempt(attempt_id).attempt_number == 1
    assert (
        reopened.get_current_background_task(_scope(), session_id=_scope().session_id)
        is None
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("3",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
        assert "attempt_number" in columns
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("lifecycle", ["terminal", "claimed"])
def test_v1_schema_migration_preserves_terminal_or_claimed_state_across_reopen(
    tmp_path: Path, lifecycle: str
) -> None:
    database = tmp_path / f"migration-{lifecycle}.sqlite"
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
    attempt_id = str(created.result["attempt_id"])
    item = store.claim_outbox(f"migration-{lifecycle}")
    assert item is not None
    if lifecycle == "terminal":
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{attempt_id}",
            observations=_observations(item, outcome=TerminalOutcome.COMPLETED),
        )
    before_counts = store.counts()
    before_task = store.get_task(task_id, _scope())
    before_attempt = store.get_attempt(attempt_id)
    with sqlite3.connect(database) as connection:
        before_outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
    _downgrade_fixture_to_v1(database)

    migrated = SqliteTaskStore(database)
    reopened = SqliteTaskStore(database)

    assert migrated.counts() == before_counts
    assert reopened.counts() == before_counts
    assert reopened.get_task(task_id, _scope()) == before_task
    migrated_attempt = reopened.get_attempt(attempt_id)
    assert migrated_attempt == before_attempt
    assert migrated_attempt.attempt_number == 1
    with sqlite3.connect(database) as connection:
        after_outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert after_outbox == before_outbox


@pytest.mark.parametrize(
    "failpoint",
    [
        "migration.v1_to_v2.before_create",
        "migration.v1_to_v2.after_create",
        "migration.v1_to_v2.after_copy",
        "migration.v1_to_v2.after_drop",
        "migration.v1_to_v2.after_rename",
        "migration.v1_to_v2.before_metadata",
    ],
)
def test_v1_schema_migration_failpoints_restore_exact_v1(
    tmp_path: Path, failpoint: str
) -> None:
    database = tmp_path / f"{failpoint}.sqlite"
    SqliteTaskStore(database)
    _downgrade_fixture_to_v1(database)

    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match=failpoint):
        SqliteTaskStore(database, failpoint=fail)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("1",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
        assert "attempt_number" not in columns
        assert "attempts_v2" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def test_fresh_schema_bootstrap_failure_leaves_no_partial_ddl(tmp_path: Path) -> None:
    database = tmp_path / "bootstrap-fail.sqlite"

    def fail(name: str) -> None:
        if name == "initialize.bootstrap.before_metadata":
            raise RuntimeError(name)

    with pytest.raises(RuntimeError, match="initialize.bootstrap.before_metadata"):
        SqliteTaskStore(database, failpoint=fail)

    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            == []
        )
    reopened = SqliteTaskStore(database)
    assert reopened.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }


def test_unknown_schema_is_rejected_without_ddl(tmp_path: Path) -> None:
    database = tmp_path / "unknown.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', '99')"
        )
        connection.execute("CREATE TABLE sentinel(value TEXT)")
        connection.execute("INSERT INTO sentinel(value) VALUES('unchanged')")
        connection.commit()
    before = database.read_bytes()

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM sentinel").fetchall() == [
            ("unchanged",)
        ]
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        } == {"metadata", "sentinel"}


def test_initialize_rollback_failure_preserves_stable_schema_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "rollback-failure.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', '2')"
        )
        connection.commit()
    before = database.read_bytes()
    real_connect = sqlite3.connect

    class RollbackFailingConnection(sqlite3.Connection):
        def rollback(self) -> None:
            raise sqlite3.OperationalError("injected rollback failure")

    def connect_with_rollback_failure(*args: object, **kwargs: object) -> object:
        kwargs["factory"] = RollbackFailingConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect_with_rollback_failure)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert rejected.value.code is ErrorCode.UNSUPPORTED
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "metadata_only",
        "missing_table",
        "missing_attempt_number",
        "fake_owned_table",
        "missing_required_index",
        "missing_attempt_bound",
    ],
)
def test_supported_schema_versions_require_complete_authoritative_shape(
    tmp_path: Path, damage: str
) -> None:
    database = tmp_path / f"schema-{damage}.sqlite"
    if damage == "metadata_only":
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', '2')"
            )
            connection.commit()
    else:
        SqliteTaskStore(database)
        if damage == "missing_attempt_number":
            _downgrade_fixture_to_v1(database)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE metadata SET value='2' WHERE key='schema_version'"
                )
                connection.commit()
        else:
            with sqlite3.connect(database) as connection:
                connection.execute("PRAGMA foreign_keys=OFF")
                if damage == "missing_table":
                    connection.execute("DROP TABLE commands")
                elif damage == "fake_owned_table":
                    connection.execute("DROP TABLE outbox")
                    connection.execute("CREATE TABLE outbox(fake TEXT)")
                elif damage == "missing_required_index":
                    connection.execute("DROP INDEX idx_tasks_scope")
                else:
                    connection.execute(
                        """CREATE TABLE attempts_without_bound (
                            attempt_id TEXT PRIMARY KEY,
                            task_id TEXT NOT NULL REFERENCES tasks(task_id)
                                ON DELETE CASCADE,
                            attempt_number INTEGER NOT NULL,
                            executor_id TEXT NOT NULL, executor_ref TEXT,
                            state TEXT NOT NULL, outcome TEXT,
                            source_seq INTEGER NOT NULL DEFAULT -1,
                            updated_at TEXT NOT NULL,
                            UNIQUE(task_id, attempt_number))"""
                    )
                    connection.execute("DROP TABLE attempts")
                    connection.execute(
                        "ALTER TABLE attempts_without_bound RENAME TO attempts"
                    )
                connection.commit()
    before = _database_dump(database)

    with pytest.raises(FormalTaskViolation) as rejected:
        SqliteTaskStore(database)

    assert rejected.value.reason == "TASK_STORE_SCHEMA_UNSUPPORTED"
    assert _database_dump(database) == before


def test_fresh_task_schema_coexists_with_unrelated_component_tables(
    tmp_path: Path,
) -> None:
    database = tmp_path / "shared-components.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE p3_confirmations(confirmation_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO p3_confirmations(confirmation_id) VALUES('confirmation-1')"
        )
        connection.commit()

    store = SqliteTaskStore(database)

    assert store.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT confirmation_id FROM p3_confirmations"
        ).fetchall() == [("confirmation-1",)]
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("3",)


def test_concurrent_initializers_converge_on_schema_v3(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.sqlite"

    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = tuple(pool.map(lambda _index: SqliteTaskStore(database), range(2)))

    assert all(store.counts()["attempts"] == 0 for store in stores)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() == ("3",)


def test_current_background_create_is_one_atomic_winner_and_replays_exactly(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current-race.sqlite"
    invocations = (
        _create(tmp_path, identity_suffix="-a"),
        _create(tmp_path, identity_suffix="-b"),
    )

    def submit(index: int):
        invocation = invocations[index]
        return PersistentTaskCore(SqliteTaskStore(database), _Executor()).execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
            current_background_session_id=_scope().session_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(submit, range(2)))

    accepted = [result for result in results if result.ok]
    rejected = [result for result in results if not result.ok]
    assert len(accepted) == len(rejected) == 1
    assert rejected[0].error is not None
    assert rejected[0].error.reason == "CURRENT_BACKGROUND_TASK_ACTIVE"
    store = SqliteTaskStore(database)
    assert store.counts() == {
        "commands": 1,
        "tasks": 1,
        "attempts": 1,
        "task_events": 1,
        "executor_events": 0,
        "outbox": 1,
    }
    current = store.get_current_background_task(
        _scope(), session_id=_scope().session_id
    )
    assert current is not None
    assert accepted[0].result is not None
    assert current.task_id == accepted[0].result["task_id"]

    winner = results.index(accepted[0])
    assert submit(winner) == accepted[0]
    assert store.counts()["tasks"] == 1


@pytest.mark.asyncio
async def test_adjustment_admission_replay_conflict_and_final_event_are_v3(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    create = _create(tmp_path)
    created = core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    assert await core.drain_outbox_once(worker_id="dispatch") is True
    task_id = str(created.result["task_id"])
    command, grant = _adjust(task_id, "Move the museum visit to 09:30.")

    admitted = core.execute(
        command,
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    replay = core.execute(
        replace(command, request_id="request-adjust-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert admitted.ok and admitted.result is not None
    assert admitted.result["adjustment_state"] == "pending"
    assert replay.ok and replay.result == admitted.result
    conflict, conflict_grant = _adjust(
        task_id,
        "Delete the itinerary.",
        command_id=command.command_id,
        request_id="request-adjust-conflict",
    )
    rejected_conflict = core.execute(
        conflict,
        conflict_grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert not rejected_conflict.ok
    assert rejected_conflict.error is not None
    assert rejected_conflict.error.reason == "IDEMPOTENCY_CONFLICT"

    requested = [
        event
        for event in store.events(task_id, _scope(), after_seq=-1)
        if event.event_type == "task.adjust_requested"
    ]
    assert len(requested) == 1
    assert dict(requested[0].details) == {"command_id": command.command_id}
    assert "09:30" not in json.dumps(requested[0].to_dict())

    assert await core.drain_outbox_once(worker_id="adjust") is True
    final = core.execute(
        replace(command, request_id="request-adjust-final-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert final.ok and final.result is not None
    assert final.result["adjustment_state"] == "applied"
    assert final.result["reason"] is None
    adjustment_events = [
        event
        for event in store.events(task_id, _scope(), after_seq=-1)
        if event.event_type.startswith("task.adjust_")
    ]
    assert [event.event_type for event in adjustment_events] == [
        "task.adjust_requested",
        "task.adjust_applied",
    ]
    assert all(
        event.producer == "task_core.control"
        and event.causation_id == command.command_id
        and "09:30" not in json.dumps(event.to_dict())
        for event in adjustment_events
    )
    assert executor.adjustments == [command.command_id]
    assert executor.adjustment_settlements == [
        TaskAdjustmentSettlement(TaskAdjustmentState.APPLIED, False)
    ]
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()[0]
            == "3"
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "task_adjustments" not in tables

    artifact_path = tmp_path / "adjusted-final.txt"
    artifact_path.write_text("museum at 09:30\n", encoding="utf-8")
    artifact = TaskResultArtifact(
        relative_path="adjusted-final.txt",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    attempt = store.get_attempt(str(created.result["attempt_id"]))
    assert attempt.executor_ref is not None
    store.apply_observations(
        (
            ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=attempt.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task_id,
                attempt_id=attempt.attempt_id,
                source_event_id="executor-adjusted-terminal",
                source_seq=2,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.COMPLETED,
                occurred_at=utc_now(),
                raw_status="completed",
                result_text="museum at 09:30",
                result_artifacts=(artifact,),
            ),
        )
    )
    events = store.events(task_id, _scope(), after_seq=-1)
    event_types = [event.event_type for event in events]
    assert event_types.index("task.adjust_applied") < event_types.index("task.terminal")
    availability, result, _reason = store.task_result(task_id, _scope())
    assert availability is TaskResultAvailability.AVAILABLE
    assert result is not None and result.result_text == "museum at 09:30"


@pytest.mark.parametrize("malformed_mode", ["result", "raised"])
@pytest.mark.asyncio
async def test_malformed_executor_adjustment_reason_is_canonicalized_before_store(
    tmp_path: Path,
    malformed_mode: str,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    create = _create(tmp_path)
    created = core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    assert await core.drain_outbox_once(worker_id="dispatch") is True
    task_id = str(created.result["task_id"])
    command, grant = _adjust(task_id, "Move the museum visit to 09:30.")
    admitted = core.execute(
        command,
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert admitted.ok
    executor.adjustment_state = TaskAdjustmentState.REJECTED
    if malformed_mode == "result":
        executor.adjustment_reason = "not applicable"
    else:
        executor.adjustment_error = FormalTaskViolation(
            "not applicable",
            "custom Executor returned malformed authority evidence",
            ErrorCode.PROTOCOL_VIOLATION,
        )

    assert await core.drain_outbox_once(worker_id="malformed-adjust") is True

    events = [
        event
        for event in store.events(task_id, _scope(), after_seq=-1)
        if event.event_type.startswith("task.adjust_")
    ]
    assert [event.event_type for event in events] == [
        "task.adjust_requested",
        "task.adjust_rejected",
    ]
    assert dict(events[-1].details) == {
        "command_id": command.command_id,
        "reason": "TASK_ADJUSTMENT_RESULT_INVALID",
    }
    assert "not applicable" not in json.dumps([event.to_dict() for event in events])
    assert executor.adjustment_settlements == [
        TaskAdjustmentSettlement(TaskAdjustmentState.REJECTED, False)
    ]
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            "SELECT state, last_error FROM outbox WHERE command_id=?",
            (command.command_id,),
        ).fetchone()
    assert outbox == ("delivered", "TASK_ADJUSTMENT_RESULT_INVALID")


@pytest.mark.asyncio
async def test_terminal_fence_rejects_pending_adjustment_without_executor_effect(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    create = _create(tmp_path)
    created = core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    await core.drain_outbox_once(worker_id="dispatch")
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    command, grant = _adjust(task_id, "Add an unsafe late change.")
    admitted = core.execute(
        command,
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert admitted.ok
    attempt = store.get_attempt(attempt_id)
    artifact_path = tmp_path / "final.txt"
    artifact_path.write_text("immutable\n", encoding="utf-8")
    artifact = TaskResultArtifact(
        relative_path="final.txt",
        sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
    )
    terminal = ExecutorObservation(
        resolution=ExecutorResolution.KNOWN,
        executor_id=attempt.executor_id,
        executor_ref=attempt.executor_ref,
        task_id=task_id,
        attempt_id=attempt_id,
        source_event_id="executor-terminal",
        source_seq=2,
        attempt_state=FormalAttemptState.TERMINAL,
        attempt_outcome=TerminalOutcome.COMPLETED,
        occurred_at=utc_now(),
        raw_status="completed",
        result_text="immutable result",
        result_artifacts=(artifact,),
    )
    store.apply_observations((terminal,))

    replay = core.execute(
        replace(command, request_id="request-terminal-replay"),
        grant,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert replay.ok and replay.result is not None
    assert replay.result["adjustment_state"] == "rejected"
    assert replay.result["reason"] == "TASK_TERMINAL_BEFORE_ADJUSTMENT"
    events = store.events(task_id, _scope(), after_seq=-1)
    types = [event.event_type for event in events]
    assert types.index("task.adjust_rejected") < types.index("task.terminal")
    assert executor.adjustments == []
    result_state, result, _reason = store.task_result(task_id, _scope())
    assert result_state is TaskResultAvailability.AVAILABLE
    assert result is not None and result.result_text == "immutable result"


@pytest.mark.asyncio
async def test_two_store_connections_serialize_same_and_distinct_adjustments(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    first_store = SqliteTaskStore(database)
    executor = _Executor()
    first_core = PersistentTaskCore(first_store, executor)
    create = _create(tmp_path)
    created = first_core.execute(
        create.envelope,
        create.authorization,
        context=create.context,
        now=NOW,
        current_background_session_id="session-1",
    )
    assert created.ok and created.result is not None
    dispatch = first_store.claim_outbox("dispatch")
    assert dispatch is not None
    first_store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch),
    )
    second_store = SqliteTaskStore(database)
    second_core = PersistentTaskCore(second_store, executor)
    task_id = str(created.result["task_id"])
    same_command, same_grant = _adjust(task_id, "Keep lunch vegetarian.")

    def submit_same(core: PersistentTaskCore, request_id: str):
        return core.execute(
            replace(same_command, request_id=request_id),
            same_grant,
            now=NOW,
            current_background_session_id="session-1",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        same_results = tuple(
            pool.map(
                lambda args: submit_same(*args),
                ((first_core, "same-a"), (second_core, "same-b")),
            )
        )
    assert all(result.ok for result in same_results)
    same_events = [
        event
        for event in first_store.events(task_id, _scope(), after_seq=-1)
        if event.event_type == "task.adjust_requested"
    ]
    assert len(same_events) == 1

    command_a, grant_a = _adjust(
        task_id,
        "Add a morning walk.",
        command_id="command-adjust-a",
        request_id="distinct-a",
    )
    command_b, grant_b = _adjust(
        task_id,
        "Move dinner later.",
        command_id="command-adjust-b",
        request_id="distinct-b",
    )

    def submit_distinct(args):
        core, command, grant = args
        return core.execute(
            command,
            grant,
            now=NOW,
            current_background_session_id="session-1",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        distinct = tuple(
            pool.map(
                submit_distinct,
                ((first_core, command_a, grant_a), (second_core, command_b, grant_b)),
            )
        )
    assert all(result.ok for result in distinct)
    requested = [
        event
        for event in first_store.events(task_id, _scope(), after_seq=-1)
        if event.event_type == "task.adjust_requested"
    ]
    assert [event.seq for event in requested] == sorted(
        event.seq for event in requested
    )
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT e.seq, o.command_id FROM outbox AS o
            JOIN task_events AS e
              ON e.task_id=o.task_id AND e.attempt_id=o.attempt_id
             AND e.event_type='task.adjust_requested'
             AND e.causation_id=o.command_id
            WHERE o.kind='attempt.adjust' ORDER BY e.seq
            """
        ).fetchall()
    assert [row[0] for row in rows] == [event.seq for event in requested]
    authoritative_command_order = [row[1] for row in rows]
    for index, expected_command_id in enumerate(authoritative_command_order):
        item = first_store.claim_outbox(f"adjust-order-{index}")
        assert item is not None and item.command_id == expected_command_id
        delivery = await executor.adjust(item)
        settlement = first_store.complete_adjustment_outbox(item, delivery)
        await executor.settle_adjustment(item, settlement)
    assert executor.adjustments == authoritative_command_order


def test_task_result_is_three_state_immutable_and_revalidates_artifact(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "result.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.NOT_READY,
        None,
        "TASK_RESULT_NOT_READY",
    )

    artifact_path = tmp_path / "itinerary.md"
    artifact_bytes = "第二天最早的固定安排是 08:30 早餐。\n".encode()
    artifact_path.write_bytes(artifact_bytes)
    artifact = TaskResultArtifact(
        relative_path="itinerary.md",
        sha256=hashlib.sha256(artifact_bytes).hexdigest(),
    )
    item = store.claim_outbox("result-worker")
    assert item is not None
    observations = _observations(
        item,
        outcome=TerminalOutcome.COMPLETED,
        result_text="三天行程已完成；第二天 08:30 安排早餐。",
        result_artifacts=(artifact,),
    )
    with pytest.raises(FormalTaskViolation) as missing_artifact:
        replace(observations[-1], result_artifacts=())
    assert missing_artifact.value.reason == "INVALID_TASK_RESULT_STATE"
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )

    availability, record, reason = store.task_result(task_id, _scope())
    assert availability is TaskResultAvailability.AVAILABLE
    assert reason == "TASK_RESULT_AVAILABLE"
    assert record is not None and record.artifacts == (artifact,)
    assert store.apply_observations(observations).events == ()
    with pytest.raises(FormalTaskViolation, match="Executor event identity"):
        store.apply_observations(
            (replace(observations[-1], result_text="conflicting result"),)
        )
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            1,
        )

    artifact_path.write_text("tampered", encoding="utf-8")
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.UNAVAILABLE,
        None,
        "TASK_RESULT_ARTIFACT_INVALID",
    )


def test_nul_executor_result_is_rejected_before_any_terminal_store_write(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "nul-result.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
        current_background_session_id=_scope().session_id,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    item = store.claim_outbox("nul-result-worker")
    assert item is not None
    observations = _observations(
        item,
        outcome=TerminalOutcome.COMPLETED,
        result_text="safe result",
        result_artifacts=(
            TaskResultArtifact(relative_path="itinerary.md", sha256="a" * 64),
        ),
    )
    object.__setattr__(observations[-1], "result_text", "unsafe\x00result")

    with pytest.raises(FormalTaskViolation) as invalid:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=observations,
        )
    assert invalid.value.reason == "INVALID_TASK_RESULT_TEXT"
    task = store.get_task(task_id, _scope())
    assert task is not None
    assert task.state is FormalTaskState.ACCEPTED
    assert task.outcome is None
    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.NOT_READY,
        None,
        "TASK_RESULT_NOT_READY",
    )
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_results").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM task_events WHERE event_type='task.terminal'"
        ).fetchone() == (0,)


def test_task_result_record_rejects_nul_and_canonicalizes_utc_offset() -> None:
    artifact = TaskResultArtifact(
        relative_path="itinerary.md",
        sha256="a" * 64,
    )
    with pytest.raises(FormalTaskViolation) as invalid_text:
        TaskResultRecord(
            task_id="task-1",
            attempt_id="attempt-1",
            source_event_id="source-1",
            result_text="unsafe\x00result",
            artifacts=(artifact,),
            completed_at="2030-01-01T08:00:00+08:00",
        )
    assert invalid_text.value.reason == "INVALID_TASK_RESULT_TEXT"

    with pytest.raises(FormalTaskViolation) as invalid_identity:
        TaskResultRecord(
            task_id="task-1",
            attempt_id="attempt-1",
            source_event_id="source\x00id",
            result_text="safe result",
            artifacts=(artifact,),
            completed_at="2030-01-01T00:00:00Z",
        )
    assert invalid_identity.value.reason == "INVALID_TASK_RESULT_IDENTITY"

    record = TaskResultRecord(
        task_id="task-1",
        attempt_id="attempt-1",
        source_event_id="source-1",
        result_text="safe result",
        artifacts=(artifact,),
        completed_at="2030-01-01T08:00:00+08:00",
    )
    assert record.completed_at == "2030-01-01T00:00:00Z"

    astral = TaskResultRecord(
        task_id="😀" * 256,
        attempt_id="attempt-astral",
        source_event_id="source-astral",
        result_text="😀" * 20_000,
        artifacts=(
            TaskResultArtifact(
                relative_path=f"{'😀' * 300}.md",
                sha256="b" * 64,
            ),
        ),
        completed_at="2030-01-01T00:00:00Z",
    )
    assert len(astral.result_text) == 20_000

    with pytest.raises(FormalTaskViolation) as oversized_identity:
        replace(record, task_id="😀" * 257)
    assert oversized_identity.value.reason == "INVALID_TASK_RESULT_IDENTITY"


def _terminal_task(
    tmp_path: Path,
    *,
    outcome: TerminalOutcome = TerminalOutcome.COMPLETED,
) -> tuple[SqliteTaskStore, _Executor, PersistentTaskCore, str, str]:
    store = SqliteTaskStore(tmp_path / "retry.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    item = store.claim_outbox("terminal-fixture")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item, outcome=outcome),
    )
    return store, executor, core, item.task_id, item.attempt_id


@pytest.mark.parametrize(
    ("outcome", "reason"),
    (
        (TerminalOutcome.CANCELLED, "TASK_CANCELLED"),
        (TerminalOutcome.FAILED, "TASK_FAILED"),
        (TerminalOutcome.INTERRUPTED, "TASK_INTERRUPTED"),
    ),
)
def test_terminal_noncompleted_task_result_is_stably_unavailable(
    tmp_path: Path,
    outcome: TerminalOutcome,
    reason: str,
) -> None:
    store, _executor, _core, task_id, _attempt_id = _terminal_task(
        tmp_path,
        outcome=outcome,
    )

    assert store.task_result(task_id, _scope()) == (
        TaskResultAvailability.UNAVAILABLE,
        None,
        reason,
    )


def test_retry_a_to_b_is_atomic_and_preserves_exact_history(tmp_path: Path) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    context_b = replace(_context(tmp_path), revision_value="clean-revision-b")

    result = core.execute(retry, grant, context=context_b, now=NOW)

    assert result.ok and result.result is not None
    assert result.result["previous_attempt_id"] == attempt_a
    assert result.result["attempt_number"] == 2
    assert result.result["applied"] is True
    attempt_b = str(result.result["attempt_id"])
    assert attempt_b != attempt_a
    assert store.get_attempt(attempt_a).to_dict()["outcome"] == "completed"
    assert store.get_attempt(attempt_a).attempt_number == 1
    assert store.get_attempt(attempt_b).attempt_number == 2
    task = store.get_task(task_id, _scope())
    assert task.attempt_id == attempt_b
    assert task.state is FormalTaskState.ACCEPTED
    assert task.spec.context.revision_value == "clean-revision-b"
    assert executor.retry_readiness_calls == [attempt_a]
    history = store.events(task_id, _scope())
    boundary = history[-1]
    assert boundary.event_type == "task.retry_accepted"
    assert boundary.attempt_id == attempt_b
    assert dict(boundary.details) == {
        "command_id": retry.command_id,
        "retry_of_attempt_id": attempt_a,
        "previous_outcome": "completed",
        "attempt_number": 2,
    }
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=20)
    assert snapshot.start_seq == boundary.seq
    assert snapshot.events == (boundary,)


def test_retry_preserves_stable_task_and_project_identity_with_zero_effects(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    before = store.counts()

    wrong_project = core.execute(
        retry,
        grant,
        context=replace(
            _context(tmp_path),
            stable_id="project-other",
            revision_value="clean-revision-b",
        ),
        now=NOW,
    )

    assert not wrong_project.ok and wrong_project.error is not None
    assert wrong_project.error.reason == "TASK_RETRY_CONTEXT_IDENTITY_MISMATCH"
    assert store.counts() == before
    assert executor.retry_readiness_calls == []

    authority = store.read_retry_authority(retry)
    assert isinstance(authority, TaskRetryAuthoritySnapshot)
    with pytest.raises(FormalTaskViolation) as replaced_spec:
        store.retry(
            retry,
            replace(authority.task.spec, instruction="replacement instruction"),
            authority,
            observed_at=NOW,
        )

    assert replaced_spec.value.reason == "TASK_RETRY_SPEC_MISMATCH"
    assert store.counts() == before


def test_retry_rejects_foreign_correlation_before_readiness_and_preserves_lineage(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        correlation_id="correlation-foreign",
    )
    before = store.counts()
    before_dump = _database_dump(store.database_path)
    before_bytes = store.database_path.read_bytes()

    rejected = core.execute(
        retry,
        grant,
        context=replace(_context(tmp_path), revision_value="clean-revision-b"),
        now=NOW,
    )

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_RETRY_PRECONDITION_STALE"
    assert rejected.error.code is ErrorCode.STALE
    assert store.counts() == before
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes
    assert executor.retry_readiness_calls == []
    assert executor.dispatches == []
    assert executor.cancels == []
    authority = core.read_current_retry_authority(scope=_scope(), task_id=task_id)
    assert authority.task.correlation_id == "correlation-1"
    assert authority.precondition.previous_attempt_id == attempt_a


@pytest.mark.parametrize(
    "corruption",
    ["wrong_task", "wrong_ordinal", "nonterminal", "outcome_mismatch"],
)
def test_retry_event_authority_requires_exact_durable_predecessor(
    tmp_path: Path, corruption: str
) -> None:
    store, _executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    database = store.database_path

    if corruption == "wrong_task":
        foreign_invocation = _create(tmp_path, identity_suffix="-foreign-lineage")
        foreign = core.execute(
            foreign_invocation.envelope,
            foreign_invocation.authorization,
            context=foreign_invocation.context,
            now=NOW,
        )
        assert foreign.ok and foreign.result is not None
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                """
                SELECT details_json FROM task_events
                WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
                """,
                (task_id, attempt_b),
            ).fetchone()
            assert row is not None
            details = json.loads(row[0])
            details["retry_of_attempt_id"] = str(foreign.result["attempt_id"])
            connection.execute(
                """
                UPDATE task_events SET details_json=?
                WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
                """,
                (json.dumps(details, sort_keys=True), task_id, attempt_b),
            )
    else:
        with sqlite3.connect(database) as connection:
            if corruption == "wrong_ordinal":
                connection.execute(
                    "UPDATE attempts SET attempt_number=3 WHERE attempt_id=?",
                    (attempt_a,),
                )
            elif corruption == "nonterminal":
                connection.execute(
                    """
                    UPDATE attempts SET state='running', outcome=NULL
                    WHERE attempt_id=?
                    """,
                    (attempt_a,),
                )
            else:
                connection.execute(
                    "UPDATE attempts SET outcome='cancelled' WHERE attempt_id=?",
                    (attempt_a,),
                )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as rejected:
        store.event_authority_snapshot(task_id, _scope(), max_events=20)

    assert rejected.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before


def test_retry_exact_replay_skips_readiness_and_conflict_has_zero_effects(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    context = replace(_context(tmp_path), revision_value="clean-revision-b")
    first = core.execute(retry, grant, context=context, now=NOW)
    assert first.ok and first.result is not None
    before = store.counts()
    calls = list(executor.retry_readiness_calls)

    replay = core.execute(retry, grant, context=context, now=NOW)
    conflicting_retry, conflicting_grant = _retry(
        task_id,
        "different-attempt",
        TerminalOutcome.COMPLETED,
        2,
        command_id=retry.command_id,
    )
    conflict = core.execute(
        conflicting_retry,
        conflicting_grant,
        context=replace(context, revision_value="different-clean-revision"),
        now=NOW,
    )
    correlation_conflict, correlation_grant = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        command_id=retry.command_id,
        correlation_id="correlation-foreign",
    )
    correlation_rejected = core.execute(
        correlation_conflict,
        correlation_grant,
        context=context,
        now=NOW,
    )

    assert replay.ok and replay.result == first.result
    assert not conflict.ok and conflict.error is not None
    assert conflict.error.reason == "IDEMPOTENCY_CONFLICT"
    assert not correlation_rejected.ok and correlation_rejected.error is not None
    assert correlation_rejected.error.reason == "IDEMPOTENCY_CONFLICT"
    assert store.counts() == before
    assert executor.retry_readiness_calls == calls


def test_concurrent_exact_retry_across_store_instances_has_one_successor(
    tmp_path: Path,
) -> None:
    store, executor_a, core_a, task_id, attempt_a = _terminal_task(tmp_path)
    store_b = SqliteTaskStore(store.database_path)
    executor_b = _Executor()
    core_b = PersistentTaskCore(store_b, executor_b)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    context = replace(_context(tmp_path), revision_value="clean-revision-b")
    before = store.counts()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = tuple(
            pool.submit(core.execute, retry, grant, context=context, now=NOW)
            for core in (core_a, core_b)
        )
        results = tuple(future.result() for future in futures)

    assert all(result.ok and result.result is not None for result in results)
    assert results[0].result == results[1].result
    assert results[0].result is not None
    successor_id = str(results[0].result["attempt_id"])
    after = store.counts()
    assert after == {
        **before,
        "commands": before["commands"] + 1,
        "attempts": before["attempts"] + 1,
        "task_events": before["task_events"] + 1,
        "outbox": before["outbox"] + 1,
    }
    assert store.get_task(task_id, _scope()).attempt_id == successor_id
    assert [
        event
        for event in store.events(task_id, _scope())
        if event.event_type == "task.retry_accepted"
    ][0].attempt_id == successor_id
    assert sum(
        attempt_id == attempt_a
        for attempt_id in (
            *executor_a.retry_readiness_calls,
            *executor_b.retry_readiness_calls,
        )
    ) in {1, 2}


def test_concurrent_distinct_retries_from_same_epoch_apply_one_and_stale_one(
    tmp_path: Path,
) -> None:
    store, _executor_a, core_a, task_id, attempt_a = _terminal_task(tmp_path)
    core_b = PersistentTaskCore(SqliteTaskStore(store.database_path), _Executor())
    retry_a, grant_a = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        command_id="command-retry-left",
    )
    retry_b, grant_b = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        command_id="command-retry-right",
    )
    context = replace(_context(tmp_path), revision_value="clean-revision-b")
    before = store.counts()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(core_a.execute, retry_a, grant_a, context=context, now=NOW),
            pool.submit(core_b.execute, retry_b, grant_b, context=context, now=NOW),
        )
        results = tuple(future.result() for future in futures)

    successes = tuple(result for result in results if result.ok)
    failures = tuple(result for result in results if not result.ok)
    assert len(successes) == len(failures) == 1
    assert failures[0].error is not None
    assert failures[0].error.reason == "TASK_RETRY_PRECONDITION_STALE"
    after = store.counts()
    assert after == {
        **before,
        "commands": before["commands"] + 1,
        "attempts": before["attempts"] + 1,
        "task_events": before["task_events"] + 1,
        "outbox": before["outbox"] + 1,
    }
    boundaries = tuple(
        event
        for event in store.events(task_id, _scope())
        if event.event_type == "task.retry_accepted"
    )
    assert len(boundaries) == 1
    assert store.get_task(task_id, _scope()).attempt_id == boundaries[0].attempt_id


def test_retry_a_to_b_to_c_then_old_retry_replay_and_fourth_rejection(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b, grant_b = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    context_b = replace(_context(tmp_path), revision_value="clean-revision-b")
    result_b = core.execute(retry_b, grant_b, context=context_b, now=NOW)
    assert result_b.ok and result_b.result is not None
    attempt_b = str(result_b.result["attempt_id"])
    item_b = store.claim_outbox("terminal-b")
    assert item_b is not None and item_b.attempt_id == attempt_b
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(item_b, outcome=TerminalOutcome.CANCELLED),
    )
    retry_c, grant_c = _retry(task_id, attempt_b, TerminalOutcome.CANCELLED, 3)
    context_c = replace(_context(tmp_path), revision_value="clean-revision-c")
    result_c = core.execute(retry_c, grant_c, context=context_c, now=NOW)
    assert result_c.ok and result_c.result is not None
    attempt_c = str(result_c.result["attempt_id"])
    item_c = store.claim_outbox("terminal-c")
    assert item_c is not None and item_c.attempt_id == attempt_c
    store.complete_outbox(
        item_c,
        executor_ref=f"legacy:{attempt_c}",
        observations=_observations(item_c, outcome=TerminalOutcome.COMPLETED),
    )
    before = store.counts()
    readiness_calls = list(executor.retry_readiness_calls)

    replay_b = core.execute(retry_b, grant_b, context=None, now=NOW)
    fourth, fourth_grant = _retry(
        task_id,
        attempt_c,
        TerminalOutcome.COMPLETED,
        3,
        command_id="command-retry-fourth",
    )
    rejected = core.execute(fourth, fourth_grant, context=context_c, now=NOW)

    assert replay_b.ok and replay_b.result == result_b.result
    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_RETRY_LIMIT_EXCEEDED"
    assert store.counts() == before
    assert executor.retry_readiness_calls == readiness_calls
    history = store.events(task_id, _scope())
    boundaries = [
        event for event in history if event.event_type == "task.retry_accepted"
    ]
    assert [event.attempt_id for event in boundaries] == [attempt_b, attempt_c]
    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=20)
    assert snapshot.start_seq == boundaries[-1].seq
    assert all(event.attempt_id == attempt_c for event in snapshot.events)
    page_a = store.events(task_id, _scope(), after_seq=-1)
    page_b = store.events(task_id, _scope(), after_seq=boundaries[0].seq - 1)
    page_c = store.events(task_id, _scope(), after_seq=boundaries[1].seq - 1)
    assert page_a == history
    assert page_b[0] == boundaries[0]
    assert page_c[0] == boundaries[1]
    assert store.events(
        task_id,
        _scope(),
        after_seq=boundaries[0].seq - 1,
        attempt_id=attempt_b,
    ) == tuple(event for event in history if event.attempt_id == attempt_b)


def test_current_retry_authority_derives_server_payload_without_side_effects(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    before_dump = _database_dump(store.database_path)
    before_bytes = store.database_path.read_bytes()

    authority = core.read_current_retry_authority(
        scope=_scope(),
        task_id=task_id,
    )

    assert authority.task.task_id == task_id
    assert authority.attempt.attempt_id == attempt_a
    assert authority.precondition.to_dict() == {
        "previous_attempt_id": attempt_a,
        "previous_outcome": TerminalOutcome.COMPLETED.value,
        "attempt_number": 2,
    }
    assert executor.retry_readiness_calls == []
    assert executor.dispatches == []
    assert executor.cancels == []
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes
    request_asserted = ScopeRef(
        "user-1",
        "project-1",
        "session-1",
        Assurance.REQUEST_ASSERTED,
    )
    with pytest.raises(FormalTaskViolation) as rejected:
        core.read_current_retry_authority(
            scope=request_asserted,
            task_id=task_id,
        )
    assert rejected.value.reason == "TASK_RETRY_AUTHORITY_FACTS_INVALID"
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes


def test_retry_requires_one_product_request_fingerprint_before_readiness(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    before_dump = _database_dump(store.database_path)
    before_bytes = store.database_path.read_bytes()

    cases = (
        ({}, "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_REQUIRED"),
        (
            {**retry.extensions, "product.unbound": {"fact": "changed"}},
            "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_REQUIRED",
        ),
        (
            {
                next(iter(retry.extensions)): {
                    "sha256": "NOT-A-CANONICAL-SHA256",
                }
            },
            "TASK_RETRY_PRODUCT_REQUEST_FINGERPRINT_INVALID",
        ),
    )
    for extensions, reason in cases:
        raw = retry.to_dict()
        raw["extensions"] = extensions
        invalid = CommandEnvelope.from_dict(raw)
        result = core.execute(invalid, grant, context=_context(tmp_path), now=NOW)
        assert not result.ok and result.error is not None
        assert result.error.reason == reason

    assert executor.retry_readiness_calls == []
    assert executor.dispatches == []
    assert executor.cancels == []
    assert _database_dump(store.database_path) == before_dump
    assert store.database_path.read_bytes() == before_bytes


def test_durable_applied_retry_replay_survives_new_process_without_command(
    tmp_path: Path,
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b_command_id = "command-retry-2"
    retry_b, grant_b = _retry(
        task_id,
        attempt_a,
        TerminalOutcome.COMPLETED,
        2,
        command_id=retry_b_command_id,
    )
    context_b = replace(_context(tmp_path), revision_value="clean-revision-b")
    result_b = core.execute(retry_b, grant_b, context=context_b, now=NOW)
    assert result_b.ok and result_b.result is not None
    item_b = store.claim_outbox("replay-b")
    assert item_b is not None
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{item_b.attempt_id}",
        observations=_observations(item_b, outcome=TerminalOutcome.CANCELLED),
    )
    retry_c, grant_c = _retry(task_id, item_b.attempt_id, TerminalOutcome.CANCELLED, 3)
    context_c = replace(_context(tmp_path), revision_value="clean-revision-c")
    result_c = core.execute(retry_c, grant_c, context=context_c, now=NOW)
    assert result_c.ok
    database = store.database_path
    product_request = _retry_product_request_fingerprint(
        command_id=retry_b_command_id,
        task_id=task_id,
    )
    del retry_b, grant_b, retry_c, grant_c, core, executor, store

    reopened = SqliteTaskStore(database)
    restarted_executor = _Executor()
    restarted_core = PersistentTaskCore(reopened, restarted_executor)
    before_dump = _database_dump(database)
    before_bytes = database.read_bytes()

    replay = restarted_core.read_applied_retry_replay(
        scope=_scope(),
        command_id=retry_b_command_id,
        task_id=task_id,
        product_request=product_request,
    )

    assert replay is not None
    assert replay.original_command.command_id == retry_b_command_id
    assert replay.original_command.payload == {
        "previous_attempt_id": attempt_a,
        "previous_outcome": TerminalOutcome.COMPLETED.value,
        "attempt_number": 2,
    }
    assert replay.original_result == result_b
    assert replay.precondition.previous_attempt_id == attempt_a
    assert replay.precondition.attempt_number == 2
    assert replay.resulting_spec.context.revision_value == "clean-revision-b"
    assert reopened.get_task(task_id, _scope()).spec.context.revision_value == (
        "clean-revision-c"
    )
    assert _database_dump(database) == before_dump
    assert database.read_bytes() == before_bytes
    assert restarted_executor.retry_readiness_calls == []
    assert restarted_executor.dispatches == []
    assert restarted_executor.cancels == []

    assert (
        restarted_core.read_applied_retry_replay(
            scope=_scope(),
            command_id="command-retry-absent",
            task_id=task_id,
            product_request=_retry_product_request_fingerprint(
                command_id="command-retry-absent",
                task_id=task_id,
            ),
        )
        is None
    )
    conflict = _retry_product_request_fingerprint(
        command_id=retry_b_command_id,
        task_id=task_id,
        correlation_id="changed-correlation",
    )
    with pytest.raises(FormalTaskViolation) as rejected:
        restarted_core.read_applied_retry_replay(
            scope=_scope(),
            command_id=retry_b_command_id,
            task_id=task_id,
            product_request=conflict,
        )
    assert rejected.value.reason == "IDEMPOTENCY_CONFLICT"
    assert _database_dump(database) == before_dump
    assert database.read_bytes() == before_bytes
    assert restarted_executor.retry_readiness_calls == []
    assert restarted_executor.dispatches == []
    assert restarted_executor.cancels == []


@pytest.mark.parametrize(
    "corruption",
    [
        "future_ordinal",
        "orphan_attempt",
        "foreign_event",
        "duplicate_create_boundary",
        "missing_create_command",
        "missing_create_dispatch",
    ],
)
def test_retry_read_authority_rejects_incomplete_full_lineage_before_readiness(
    tmp_path: Path, corruption: str
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    database = store.database_path
    if corruption == "foreign_event":
        foreign = _create(tmp_path, identity_suffix="-lineage-foreign")
        foreign_result = core.execute(
            foreign.envelope,
            foreign.authorization,
            context=foreign.context,
            now=NOW,
        )
        assert foreign_result.ok and foreign_result.result is not None
        foreign_attempt = str(foreign_result.result["attempt_id"])
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        if corruption == "future_ordinal":
            connection.execute(
                "UPDATE attempts SET attempt_number=2 WHERE attempt_id=?",
                (attempt_a,),
            )
        elif corruption == "orphan_attempt":
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, task_id, attempt_number, executor_id,
                    executor_ref, state, outcome, source_seq, updated_at)
                SELECT 'attempt-orphan', task_id, 2, executor_id, NULL,
                    'accepted', NULL, -1, updated_at
                FROM attempts WHERE attempt_id=?
                """,
                (attempt_a,),
            )
        elif corruption == "foreign_event":
            connection.execute(
                """
                UPDATE task_events SET attempt_id=?
                WHERE task_id=? AND seq=1
                """,
                (foreign_attempt, task_id),
            )
        elif corruption == "duplicate_create_boundary":
            connection.execute(
                """
                UPDATE task_events SET event_type='task.accepted',
                    state='accepted', outcome=NULL, producer='task_core',
                    source_event_id=NULL, details_json=?
                WHERE task_id=? AND seq=1
                """,
                (json.dumps({"command_id": "command-create"}), task_id),
            )
        elif corruption == "missing_create_command":
            connection.execute("DELETE FROM commands WHERE command_id='command-create'")
        else:
            connection.execute(
                """
                DELETE FROM outbox WHERE task_id=? AND attempt_id=?
                    AND kind='attempt.dispatch'
                """,
                (task_id, attempt_a),
            )
        connection.commit()
    before = _database_dump(database)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)

    rejected = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_STORE_CORRUPT"
    assert executor.retry_readiness_calls == []
    assert _database_dump(database) == before


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_retry_boundary",
        "duplicate_retry_boundary",
        "missing_retry_command",
        "wrong_retry_result",
        "wrong_retry_dispatch_command",
    ],
)
def test_next_retry_rejects_corrupt_prior_retry_ledger_with_zero_effects(
    tmp_path: Path, corruption: str
) -> None:
    store, executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry_b, grant_b = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    result_b = core.execute(retry_b, grant_b, context=_context(tmp_path), now=NOW)
    assert result_b.ok and result_b.result is not None
    attempt_b = str(result_b.result["attempt_id"])
    item_b = store.claim_outbox("prior-retry-ledger")
    assert item_b is not None
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(item_b, outcome=TerminalOutcome.CANCELLED),
    )
    with sqlite3.connect(store.database_path) as connection:
        boundary = connection.execute(
            """
            SELECT seq, details_json FROM task_events
            WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
            """,
            (task_id, attempt_b),
        ).fetchone()
        assert boundary is not None
        if corruption == "missing_retry_boundary":
            connection.execute(
                """
                UPDATE task_events SET event_type='task.running'
                WHERE task_id=? AND seq=?
                """,
                (task_id, boundary[0]),
            )
        elif corruption == "duplicate_retry_boundary":
            connection.execute(
                """
                UPDATE task_events SET event_type='task.retry_accepted',
                    state='accepted', outcome=NULL, producer='task_core',
                    source_event_id=NULL, causation_id=?, details_json=?
                WHERE task_id=? AND seq=?
                """,
                (
                    retry_b.command_id,
                    boundary[1],
                    task_id,
                    int(boundary[0]) + 1,
                ),
            )
        elif corruption == "missing_retry_command":
            connection.execute(
                "DELETE FROM commands WHERE command_id=?",
                (retry_b.command_id,),
            )
        elif corruption == "wrong_retry_result":
            row = connection.execute(
                "SELECT result_json FROM commands WHERE command_id=?",
                (retry_b.command_id,),
            ).fetchone()
            assert row is not None
            payload = json.loads(row[0])
            payload["result"]["attempt_id"] = "attempt-foreign-result"
            connection.execute(
                "UPDATE commands SET result_json=? WHERE command_id=?",
                (json.dumps(payload, sort_keys=True), retry_b.command_id),
            )
        else:
            connection.execute(
                """
                UPDATE outbox SET command_id='command-create'
                WHERE task_id=? AND attempt_id=? AND kind='attempt.dispatch'
                """,
                (task_id, attempt_b),
            )
        connection.commit()
    before = _database_dump(store.database_path)
    calls = list(executor.retry_readiness_calls)
    retry_c, grant_c = _retry(task_id, attempt_b, TerminalOutcome.CANCELLED, 3)

    rejected = core.execute(retry_c, grant_c, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == "TASK_STORE_CORRUPT"
    assert executor.retry_readiness_calls == calls
    assert _database_dump(store.database_path) == before


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (TerminalOutcome.FAILED, "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"),
        (TerminalOutcome.INTERRUPTED, "TASK_RETRY_OUTCOME_NOT_ELIGIBLE"),
    ],
)
def test_retry_ineligible_terminal_outcome_has_zero_effects(
    tmp_path: Path, outcome: TerminalOutcome, reason: str
) -> None:
    store, executor, core, task_id, attempt_id = _terminal_task(
        tmp_path, outcome=outcome
    )
    # The strict command contract permits only eligible outcomes; use an eligible
    # asserted value and prove that Store authority still rejects actual truth.
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.COMPLETED, 2)
    before = store.counts()

    result = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not result.ok and result.error is not None
    assert result.error.reason == reason
    assert store.counts() == before
    assert executor.retry_readiness_calls == []


def test_retry_requires_terminal_and_executor_readiness_with_zero_effects(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "retry-guards.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.COMPLETED, 2)
    before = store.counts()

    nonterminal = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not nonterminal.ok and nonterminal.error is not None
    assert nonterminal.error.reason == "TASK_RETRY_REQUIRES_TERMINAL"
    assert store.counts() == before

    item = store.claim_outbox("terminal-fixture")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item, outcome=TerminalOutcome.COMPLETED),
    )
    executor.retry_ready = False
    before = store.counts()
    pending = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert not pending.ok and pending.error is not None
    assert pending.error.reason == "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
    assert pending.error.message == "Executor predecessor cleanup is not retry-ready"
    assert store.counts() == before
    executor.retry_ready = True
    executor.retry_readiness_error = FormalTaskViolation(
        "PRIVATE_EXECUTOR_ERROR",
        "credential-like private detail",
        ErrorCode.INTERNAL,
    )
    failed_readiness = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert not failed_readiness.ok and failed_readiness.error is not None
    assert failed_readiness.error.reason == "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
    assert failed_readiness.error.message == "Executor retry-readiness is unavailable"
    assert "private" not in failed_readiness.error.message
    assert store.counts() == before

    class GetterFailureExecutor(_Executor):
        @property
        def retry_readiness(self) -> object:
            raise RuntimeError("private getter detail")

    getter_failure = PersistentTaskCore(store, GetterFailureExecutor()).execute(
        retry, grant, context=_context(tmp_path), now=NOW
    )
    assert not getter_failure.ok and getter_failure.error is not None
    assert getter_failure.error.reason == "TASK_RETRY_EXECUTOR_CLEANUP_PENDING"
    assert getter_failure.error.message == "Executor retry-readiness is unavailable"
    assert "private" not in getter_failure.error.message
    assert store.counts() == before


@pytest.mark.parametrize(
    ("unsettled_owner", "reason"),
    [
        ("outbox", "TASK_RETRY_OUTBOX_PENDING"),
        ("reconciliation", "TASK_RETRY_RECONCILIATION_PENDING"),
    ],
)
def test_retry_requires_settled_durable_ownership_with_zero_effects(
    tmp_path: Path,
    unsettled_owner: str,
    reason: str,
) -> None:
    store, executor, core, task_id, attempt_id = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_id, TerminalOutcome.COMPLETED, 2)
    with sqlite3.connect(store.database_path) as connection:
        if unsettled_owner == "outbox":
            connection.execute(
                "UPDATE outbox SET state='pending' WHERE attempt_id=?",
                (attempt_id,),
            )
        else:
            connection.execute(
                """
                UPDATE tasks SET reconciliation_state='pending',
                    reconciliation_reason='cleanup_pending' WHERE task_id=?
                """,
                (task_id,),
            )
        connection.commit()
        before = tuple(connection.iterdump())

    rejected = core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert not rejected.ok and rejected.error is not None
    assert rejected.error.reason == reason
    assert executor.retry_readiness_calls == []
    with sqlite3.connect(store.database_path) as connection:
        assert tuple(connection.iterdump()) == before


def test_old_attempt_facts_are_explicitly_superseded_after_retry(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "stale-observation.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    item_a = store.claim_outbox("terminal-a")
    assert item_a is not None
    observations_a = _observations(item_a, outcome=TerminalOutcome.COMPLETED)
    store.complete_outbox(
        item_a,
        executor_ref=f"legacy:{item_a.attempt_id}",
        observations=observations_a,
    )
    retry, grant = _retry(
        item_a.task_id, item_a.attempt_id, TerminalOutcome.COMPLETED, 2
    )
    applied = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert applied.ok
    before = store.counts()

    duplicate = store.apply_observations(observations_a)
    assert duplicate.disposition is TaskMutationDisposition.SUPERSEDED
    assert store.counts() == before
    late = replace(
        observations_a[-1],
        source_event_id=f"late:{item_a.attempt_id}",
        source_seq=3,
    )
    stale = store.apply_observations((late,))

    assert stale.disposition is TaskMutationDisposition.SUPERSEDED
    assert stale.attempt.attempt_id == item_a.attempt_id
    assert stale.events == ()
    assert store.counts() == before


def test_old_attempt_outbox_and_reconciliation_callbacks_have_zero_effects(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "stale-callbacks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    item_a = store.claim_outbox("terminal-a")
    assert item_a is not None
    store.complete_outbox(
        item_a,
        executor_ref=f"legacy:{item_a.attempt_id}",
        observations=_observations(item_a, outcome=TerminalOutcome.COMPLETED),
    )
    retry, grant = _retry(
        item_a.task_id, item_a.attempt_id, TerminalOutcome.COMPLETED, 2
    )
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    before_counts = store.counts()
    before_task = store.get_task(item_a.task_id, _scope())
    before_history = store.events(item_a.task_id, _scope())
    with sqlite3.connect(store.database_path) as connection:
        before_outboxes = connection.execute(
            """
            SELECT outbox_id, state, delivery_count, claimed_by, claim_token
            FROM outbox ORDER BY outbox_id
            """
        ).fetchall()

    superseded_operations = (
        lambda: store.mark_reconciliation_pending(
            item_a.task_id, item_a.attempt_id, "late pending"
        ),
        lambda: store.mark_reconciliation_resolved(
            item_a.task_id, item_a.attempt_id, "late resolved"
        ),
        lambda: store.resolve_lost_attempt(
            item_a.task_id, item_a.attempt_id, "late lost"
        ),
    )
    for operation in superseded_operations:
        receipt = operation()
        assert receipt.disposition is TaskMutationDisposition.SUPERSEDED
        assert receipt.attempt.attempt_id == item_a.attempt_id
        assert receipt.events == ()
    with pytest.raises(FormalTaskViolation) as stale_release:
        store.release_outbox(item_a, "late release")
    assert stale_release.value.reason == "TASK_ATTEMPT_STALE"
    assert stale_release.value.code is ErrorCode.STALE
    with pytest.raises(FormalTaskViolation) as lost_claim:
        store.complete_outbox(
            item_a,
            executor_ref=f"legacy:{item_a.attempt_id}",
            observations=_observations(item_a),
        )
    assert lost_claim.value.reason == "OUTBOX_CLAIM_LOST"

    assert store.counts() == before_counts
    assert store.get_task(item_a.task_id, _scope()) == before_task
    assert store.get_task(item_a.task_id, _scope()).attempt_id == attempt_b
    assert store.events(item_a.task_id, _scope()) == before_history
    assert store.get_attempt(item_a.attempt_id).outcome is TerminalOutcome.COMPLETED
    with sqlite3.connect(store.database_path) as connection:
        after_outboxes = connection.execute(
            """
            SELECT outbox_id, state, delivery_count, claimed_by, claim_token
            FROM outbox ORDER BY outbox_id
            """
        ).fetchall()
    assert after_outboxes == before_outboxes


def test_cancel_after_retry_targets_only_current_attempt(tmp_path: Path) -> None:
    store, _executor, core, task_id, attempt_a = _terminal_task(tmp_path)
    retry, grant = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    attempt_b = str(retried.result["attempt_id"])
    before_a = store.get_attempt(attempt_a)

    cancel = _cancel(task_id)
    cancelled = core.execute(cancel.envelope, cancel.authorization, now=NOW)

    assert cancelled.ok and cancelled.result is not None
    assert cancelled.result["attempt_id"] == attempt_b
    assert cancelled.result["state"] == FormalTaskState.TERMINAL.value
    assert store.get_attempt(attempt_a) == before_a
    assert store.get_attempt(attempt_a).outcome is TerminalOutcome.COMPLETED
    assert store.get_attempt(attempt_b).outcome is TerminalOutcome.CANCELLED
    current = store.get_task(task_id, _scope())
    assert current.attempt_id == attempt_b
    assert current.outcome is TerminalOutcome.CANCELLED
    assert all(
        event.attempt_id == attempt_b
        for event in store.events(
            task_id,
            _scope(),
            after_seq=-1,
            attempt_id=attempt_b,
        )
    )


@pytest.mark.parametrize(
    "failpoint",
    [
        "retry.before_ids",
        "retry.after_attempt",
        "retry.after_event",
        "retry.after_outbox",
        "retry.after_command",
        "retry.after_task",
    ],
)
def test_retry_failpoints_leave_exact_predecessor_unchanged(
    tmp_path: Path, failpoint: str
) -> None:
    enabled = False

    def fail(name: str) -> None:
        if enabled and name == failpoint:
            raise RuntimeError(name)

    store = SqliteTaskStore(tmp_path / f"{failpoint}.sqlite", failpoint=fail)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    item = store.claim_outbox("terminal-fixture")
    assert item is not None
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=_observations(item, outcome=TerminalOutcome.COMPLETED),
    )
    retry, grant = _retry(item.task_id, item.attempt_id, TerminalOutcome.COMPLETED, 2)
    before_counts = store.counts()
    before_task = store.get_task(item.task_id, _scope())
    before_events = store.events(item.task_id, _scope())
    enabled = True

    with pytest.raises(RuntimeError, match=failpoint):
        core.execute(retry, grant, context=_context(tmp_path), now=NOW)

    assert store.counts() == before_counts
    assert store.get_task(item.task_id, _scope()) == before_task
    assert store.events(item.task_id, _scope()) == before_events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "missing_boundary",
        "duplicate_boundary",
        "boundary_details",
        "boundary_state",
        "boundary_not_segment_start",
        "predecessor_outcome",
        "predecessor_number",
    ],
)
async def test_corrupt_retry_dispatch_lineage_fails_before_claim_or_executor(
    tmp_path: Path, corruption: str
) -> None:
    database = tmp_path / f"retry-lineage-{corruption}.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    attempt_a = str(created.result["attempt_id"])
    dispatch_a = store.claim_outbox("terminal-a")
    assert dispatch_a is not None
    store.complete_outbox(
        dispatch_a,
        executor_ref=f"legacy:{attempt_a}",
        observations=_observations(dispatch_a, outcome=TerminalOutcome.COMPLETED),
    )
    retry, grant = _retry(dispatch_a.task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    retried = core.execute(retry, grant, context=_context(tmp_path), now=NOW)
    assert retried.ok and retried.result is not None
    retry_outbox_id = str(retried.result["outbox_id"])
    attempt_b = str(retried.result["attempt_id"])

    with sqlite3.connect(database) as connection:
        if corruption == "missing_boundary":
            connection.execute(
                "DELETE FROM task_events WHERE event_type='task.retry_accepted'"
            )
        elif corruption == "duplicate_boundary":
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, seq, event_id, attempt_id, scope_json, event_type,
                    state, outcome, producer, source_event_id, causation_id,
                    correlation_id, occurred_at, details_json
                )
                SELECT task_id, seq + 100, event_id || '-duplicate', attempt_id,
                       scope_json, event_type, state, outcome, producer,
                       source_event_id, causation_id, correlation_id,
                       occurred_at, details_json
                FROM task_events WHERE event_type='task.retry_accepted'
                """
            )
        elif corruption == "boundary_details":
            row = connection.execute(
                """
                SELECT details_json FROM task_events
                WHERE event_type='task.retry_accepted'
                """
            ).fetchone()
            assert row is not None
            details = json.loads(row[0])
            details["retry_of_attempt_id"] = "attempt-foreign"
            connection.execute(
                """
                UPDATE task_events SET details_json=?
                WHERE event_type='task.retry_accepted'
                """,
                (json.dumps(details, sort_keys=True),),
            )
        elif corruption == "boundary_state":
            connection.execute(
                """
                UPDATE task_events SET state='running'
                WHERE event_type='task.retry_accepted'
                """
            )
        elif corruption == "boundary_not_segment_start":
            connection.execute(
                "UPDATE task_events SET attempt_id=? WHERE task_id=? AND seq=0",
                (attempt_b, dispatch_a.task_id),
            )
        elif corruption == "predecessor_outcome":
            connection.execute(
                "UPDATE attempts SET outcome='cancelled' WHERE attempt_id=?",
                (attempt_a,),
            )
        else:
            connection.execute(
                "UPDATE attempts SET attempt_number=3 WHERE attempt_id=?",
                (attempt_a,),
            )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="retry-worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (retry_outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert store.get_task(dispatch_a.task_id, _scope()).attempt_id == attempt_b
    assert executor.dispatches == []
    assert executor.cancels == []


class _Executor:
    executor_id = FORMAL_PROJECT_EXECUTOR_ID

    def __init__(self) -> None:
        self.dispatches: list[str] = []
        self.cancels: list[str] = []
        self.adjustments: list[str] = []
        self.adjustment_state = TaskAdjustmentState.APPLIED
        self.adjustment_reason: str | None = None
        self.adjustment_error: FormalTaskViolation | None = None
        self.adjustment_settlements: list[TaskAdjustmentSettlement] = []
        self.fail_dispatches = 0
        self.status_resolution: ExecutorResolution | None = None
        self.retry_ready = True
        self.retry_readiness_error: Exception | None = None
        self.retry_readiness_calls: list[str] = []

    def retry_readiness(
        self, task: PersistentTaskRecord, attempt: PersistentAttemptRecord
    ) -> ExecutorRetryReadiness:
        self.retry_readiness_calls.append(attempt.attempt_id)
        if self.retry_readiness_error is not None:
            raise self.retry_readiness_error
        assert attempt.outcome is not None
        return ExecutorRetryReadiness(
            task_id=task.task_id,
            previous_attempt_id=attempt.attempt_id,
            previous_outcome=attempt.outcome,
            previous_attempt_number=attempt.attempt_number,
            ready=self.retry_ready,
            reason=("cleanup_complete" if self.retry_ready else "cleanup_pending"),
        )

    async def dispatch(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.dispatches.append(item.attempt_id)
        if self.fail_dispatches:
            self.fail_dispatches -= 1
            raise RuntimeError("transient delivery failure")
        return ExecutorDeliveryResult(f"legacy:{item.attempt_id}", _observations(item))

    async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
        self.cancels.append(item.attempt_id)
        return ExecutorDeliveryResult(
            f"legacy:{item.attempt_id}",
            _observations(item, outcome=TerminalOutcome.CANCELLED),
        )

    async def adjust(self, item: PersistentOutboxItem) -> TaskAdjustmentDeliveryResult:
        self.adjustments.append(item.command_id)
        assert item.executor_ref is not None
        if self.adjustment_error is not None:
            raise self.adjustment_error
        return TaskAdjustmentDeliveryResult(
            item.executor_ref,
            item.command_id,
            self.adjustment_state,
            self.adjustment_reason,
        )

    async def settle_adjustment(
        self,
        _item: PersistentOutboxItem,
        settlement: TaskAdjustmentSettlement,
    ) -> None:
        self.adjustment_settlements.append(settlement)

    async def status(
        self,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> ExecutorDeliveryResult | ExecutorObservation:
        if self.status_resolution is None:
            return ExecutorDeliveryResult(attempt.executor_ref or "", ())
        return ExecutorObservation(
            resolution=self.status_resolution,
            executor_id=self.executor_id,
            executor_ref=attempt.executor_ref,
            task_id=task.task_id,
            attempt_id=attempt.attempt_id,
            source_event_id=None,
            source_seq=None,
            attempt_state=None,
            attempt_outcome=None,
            occurred_at=utc_now(),
            raw_status=None,
            error=f"STATUS_{self.status_resolution.value.upper()}",
        )


@pytest.mark.parametrize(
    "failpoint",
    [
        "create.before_ids",
        "create.after_task",
        "create.after_event",
        "create.after_outbox",
        "create.after_command",
    ],
)
def test_create_is_atomic_at_every_persistence_boundary(
    tmp_path: Path, failpoint: str
) -> None:
    def fail(name: str) -> None:
        if name == failpoint:
            raise RuntimeError(name)

    store = SqliteTaskStore(tmp_path / f"{failpoint}.sqlite", failpoint=fail)
    invocation = _create(tmp_path)

    with pytest.raises(RuntimeError, match=failpoint):
        PersistentTaskCore(store, _Executor()).execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )

    assert store.counts() == {
        "commands": 0,
        "tasks": 0,
        "attempts": 0,
        "task_events": 0,
        "executor_events": 0,
        "outbox": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failpoint",
    [
        "cancel.after_snapshot",
        "cancel.after_request_event",
        "cancel.after_outbox_or_terminal",
        "cancel.after_command",
    ],
)
async def test_active_cancel_is_atomic_at_every_persistence_boundary(
    tmp_path: Path, failpoint: str
) -> None:
    enabled = False

    def fail(name: str) -> None:
        if enabled and name == failpoint:
            raise RuntimeError(name)

    store = SqliteTaskStore(tmp_path / f"{failpoint}.sqlite", failpoint=fail)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    persisted = store.get_task(str(created.result["task_id"]), _scope())
    assert persisted.spec.origin.to_dict() == {
        "kind": "committed_turn",
        "turn_id": "turn-1",
        "commit_id": "commit-1",
    }
    await core.drain_outbox()
    task_id = str(created.result["task_id"])
    before_counts = store.counts()
    before_task = store.get_task(task_id, _scope())
    before_events = store.events(task_id, _scope())
    enabled = True
    cancel = _cancel(task_id)

    with pytest.raises(RuntimeError, match=failpoint):
        core.execute(cancel.envelope, cancel.authorization, now=NOW)

    assert store.counts() == before_counts
    assert store.get_task(task_id, _scope()) == before_task
    assert store.events(task_id, _scope()) == before_events
    assert executor.cancels == []


def test_same_create_is_idempotent_across_store_instances_and_threads(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    stores = (SqliteTaskStore(database), SqliteTaskStore(database))
    invocation = _create(tmp_path)

    def execute(index: int):
        return PersistentTaskCore(stores[index], _Executor()).execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, (0, 1)))

    assert all(result.ok for result in results)
    assert results[0].result == results[1].result
    assert stores[0].counts() == {
        "commands": 1,
        "tasks": 1,
        "attempts": 1,
        "task_events": 1,
        "executor_events": 0,
        "outbox": 1,
    }


def test_missing_authorization_and_conflicting_replay_have_zero_new_effects(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)

    denied = core.execute(
        invocation.envelope, None, context=invocation.context, now=NOW
    )
    assert not denied.ok
    assert denied.error is not None
    assert denied.error.reason == "FORMAL_TASK_AUTHORIZATION_REQUIRED"
    assert sum(store.counts().values()) == 0

    accepted = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    before = store.counts()
    conflict = _create(tmp_path, instruction="Different intent under same command id.")
    rejected = core.execute(
        conflict.envelope,
        conflict.authorization,
        context=conflict.context,
        now=NOW,
    )

    assert accepted.ok
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.reason == "IDEMPOTENCY_CONFLICT"
    assert store.counts() == before
    assert executor.dispatches == []


def test_direct_command_cannot_omit_operation_capability(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    raw = invocation.envelope.to_dict()
    raw["required_capabilities"] = []
    weakened = CommandEnvelope.from_dict(raw)

    rejected = core.execute(
        weakened,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )

    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.reason == "FORMAL_TASK_CAPABILITY_MISMATCH"
    assert sum(store.counts().values()) == 0


def test_direct_envelopes_reject_noncanonical_target_and_hidden_payload(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    raw_create = invocation.envelope.to_dict()
    raw_create["target_ref"] = {"kind": "task", "id": "create:other-command"}
    wrong_target = CommandEnvelope.from_dict(raw_create)

    rejected_create = core.execute(
        wrong_target,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert not rejected_create.ok
    assert rejected_create.error is not None
    assert rejected_create.error.reason == "FORMAL_TASK_TARGET_MISMATCH"
    assert sum(store.counts().values()) == 0

    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before = store.counts()

    status = _status(task_id)
    raw_status = status.envelope.to_dict()
    raw_status["payload"] = {"repair": True}
    rejected_query = core.query(
        QueryEnvelope.from_dict(raw_status), status.authorization, now=NOW
    )
    assert not rejected_query.ok
    assert rejected_query.error is not None
    assert rejected_query.error.reason == "INVALID_FORMAL_TASK_PAYLOAD"

    assert store.counts() == before
    assert store.get_task(task_id, _scope()).cancel_requested is False


@pytest.mark.parametrize(
    ("context_change", "reason"),
    [
        ({"redacted": True}, "TASK_CONTEXT_REDACTED"),
        (
            {"revision_kind": "unversioned", "revision_value": None},
            "UNVERSIONED_DESTRUCTIVE_CONTEXT",
        ),
        ({"expires_at": "2026-08-05T11:59:59Z"}, "TASK_CONTEXT_EXPIRED"),
    ],
)
def test_unsafe_context_is_rejected_before_persistence(
    tmp_path: Path,
    context_change: dict[str, object],
    reason: str,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    context = replace(invocation.context, **context_change)

    rejected = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=context,
        now=NOW,
    )

    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.reason == reason
    assert sum(store.counts().values()) == 0


@pytest.mark.asyncio
async def test_outbox_retries_the_same_attempt_and_read_query_is_side_effect_free(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    executor.fail_dispatches = 1
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None

    with pytest.raises(RuntimeError, match="transient"):
        await core.drain_outbox_once(worker_id="worker-1")
    assert await core.drain_outbox_once(worker_id="worker-2") is True
    assert executor.dispatches == [
        created.result["attempt_id"],
        created.result["attempt_id"],
    ]

    before = store.counts()
    status = _status(str(created.result["task_id"]))
    result = core.query(status.envelope, status.authorization, now=NOW)
    assert result.ok
    assert store.counts() == before


@pytest.mark.asyncio
async def test_released_outbox_does_not_starve_another_pending_task(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    executor.fail_dispatches = 1
    core = PersistentTaskCore(store, executor)
    first = _create(tmp_path, identity_suffix="-first")
    second = _create(tmp_path, identity_suffix="-second")
    first_result = core.execute(
        first.envelope,
        first.authorization,
        context=first.context,
        now=NOW,
    )
    second_result = core.execute(
        second.envelope,
        second.authorization,
        context=second.context,
        now=NOW,
    )
    assert first_result.ok and second_result.ok

    with pytest.raises(RuntimeError, match="transient"):
        await core.drain_outbox_once(worker_id="worker-1")
    failed_attempt = executor.dispatches[0]

    assert await core.drain_outbox_once(worker_id="worker-2") is True
    assert executor.dispatches[1] != failed_attempt
    assert await core.drain_outbox_once(worker_id="worker-3") is True
    assert executor.dispatches[2] == failed_attempt


def test_executor_duplicate_is_noop_and_conflicting_duplicate_is_rejected(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    item = store.claim_outbox("worker")
    assert item is not None
    observations = _observations(item)
    store.complete_outbox(
        item,
        executor_ref=f"legacy:{item.attempt_id}",
        observations=observations,
    )
    before = store.counts()

    store.apply_observations(observations)
    assert store.counts() == before

    conflict = replace(observations[0], summary="different canonical fact")
    with pytest.raises(FormalTaskViolation) as raised:
        store.apply_observations((conflict,))
    assert raised.value.reason == "EXECUTOR_EVENT_ID_CONFLICT"
    assert store.counts() == before


def test_wrong_executor_binding_and_sequence_gap_leave_state_unchanged(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    item = store.claim_outbox("worker")
    assert item is not None
    before = store.counts()
    valid = _observations(item)[0]

    with pytest.raises(FormalTaskViolation) as wrong_binding:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=(replace(valid, executor_id="foreign-executor"),),
        )
    assert wrong_binding.value.reason == "EXECUTOR_OBSERVATION_BINDING_MISMATCH"
    assert store.counts() == before

    with pytest.raises(FormalTaskViolation) as gap:
        store.complete_outbox(
            item,
            executor_ref=f"legacy:{item.attempt_id}",
            observations=(replace(valid, source_seq=1),),
        )
    assert gap.value.reason == "EXECUTOR_EVENT_SEQUENCE_GAP"
    assert store.counts() == before


@pytest.mark.asyncio
async def test_cancel_before_dispatch_fences_executor_with_zero_external_calls(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    cancel = _cancel(str(created.result["task_id"]))

    cancelled = core.execute(cancel.envelope, cancel.authorization, now=NOW)

    assert cancelled.ok
    assert await core.drain_outbox() == 0
    assert executor.dispatches == []
    assert executor.cancels == []
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is TerminalOutcome.CANCELLED
    assert task.dispatch_fenced is True
    events = store.events(task.task_id, _scope())
    cancel_requested = next(
        event for event in events if event.event_type == "task.cancel_requested"
    )
    assert cancel_requested.scope == _scope()
    assert cancel_requested.causation_id == "command-cancel"
    with pytest.raises(FormalTaskViolation) as raised:
        project_task_event(cancel_requested)
    assert raised.value.reason == "TASK_EVENT_NOT_PROJECTABLE"


@pytest.mark.asyncio
async def test_active_cancel_waits_for_exact_binding_then_calls_executor_once(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None

    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    cancel = _cancel(str(created.result["task_id"]))
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok
    assert store.claim_outbox("cancel-worker") is None

    delivery = await executor.dispatch(dispatch)
    store.complete_outbox(
        dispatch,
        executor_ref=delivery.executor_ref,
        observations=delivery.observations,
    )
    assert await core.drain_outbox(worker_id="cancel-worker") == 1
    assert executor.dispatches == [created.result["attempt_id"]]
    assert executor.cancels == [created.result["attempt_id"]]
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is TerminalOutcome.CANCELLED


@pytest.mark.asyncio
async def test_cancel_after_unknown_dispatch_retries_binding_before_executor_cancel(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    attempt_id = str(created.result["attempt_id"])

    uncertain = store.claim_outbox("first-dispatch")
    assert uncertain is not None
    await executor.dispatch(uncertain)
    assert store.release_outbox(uncertain, "accepted externally; result unavailable")

    cancel = _cancel(str(created.result["task_id"]))
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    assert acknowledged.result["outbox_id"] is not None
    assert store.get_task(str(created.result["task_id"]), _scope()).outcome is None

    assert await core.drain_outbox(worker_id="reconcile-dispatch") == 2
    assert executor.dispatches == [attempt_id, attempt_id]
    assert executor.cancels == [attempt_id]
    assert (
        store.get_task(str(created.result["task_id"]), _scope()).outcome
        is TerminalOutcome.CANCELLED
    )


@pytest.mark.asyncio
async def test_executor_terminal_truth_suppresses_racing_cancel_side_effect(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    cancel = _cancel(str(created.result["task_id"]))
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok

    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{dispatch.attempt_id}",
        observations=_observations(dispatch, outcome=TerminalOutcome.COMPLETED),
    )

    assert await core.drain_outbox(worker_id="cancel-worker") == 0
    assert executor.cancels == []
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is TerminalOutcome.COMPLETED


@pytest.mark.asyncio
async def test_active_cancel_delivery_rejection_preserves_lifecycle_for_reconciliation(
    tmp_path: Path,
) -> None:
    class RejectingCancelExecutor(_Executor):
        async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
            self.cancels.append(item.attempt_id)
            raise FormalTaskViolation(
                "LEGACY_EXECUTOR_ACCESS_MISMATCH",
                "cannot prove control of the original attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )

    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = RejectingCancelExecutor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    cancel = _cancel(str(created.result["task_id"]))
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok

    assert await core.drain_outbox() == 1
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is None
    assert task.reconciliation_state is ReconciliationState.PENDING
    assert task.reconciliation_reason is not None
    assert "LEGACY_EXECUTOR_ACCESS_MISMATCH" in task.reconciliation_reason


@pytest.mark.asyncio
async def test_restart_delivery_unavailable_keeps_original_outbox_and_marks_pending(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    first = PersistentTaskCore(SqliteTaskStore(database), _Executor())
    invocation = _create(tmp_path)
    created = first.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None

    unavailable_executor = _Executor()
    unavailable_executor.fail_dispatches = 1
    store = SqliteTaskStore(database)
    restarted = PersistentTaskCore(store, unavailable_executor)
    summary = await restarted.reconcile()

    assert summary["delivery_unavailable"] == 1
    task = store.get_task(str(created.result["task_id"]), _scope())
    assert task.outcome is None
    assert task.reconciliation_state is ReconciliationState.PENDING
    assert task.attempt_id == created.result["attempt_id"]
    assert store.counts()["outbox"] == 1


@pytest.mark.asyncio
async def test_restart_does_not_reclaim_a_live_cross_process_outbox_claim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    live_claim = store.claim_outbox("still-active-worker")
    assert live_claim is not None
    restart_executor = _Executor()

    summary = await PersistentTaskCore(
        SqliteTaskStore(database), restart_executor
    ).reconcile()

    assert summary["reset_claims"] == 0
    assert summary["delivered"] == 0
    assert restart_executor.dispatches == []
    assert store.claim_outbox("overlapping-worker") is None
    assert store.release_outbox(live_claim, "test cleanup") is True


@pytest.mark.asyncio
async def test_restart_reclaims_only_an_expired_claim_and_reuses_the_attempt(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    expired = store.claim_outbox("dead-worker")
    assert expired is not None
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE outbox SET claimed_at=? WHERE outbox_id=?",
            ("2000-01-01T00:00:00Z", expired.outbox_id),
        )
    restart_executor = _Executor()

    summary = await PersistentTaskCore(
        SqliteTaskStore(database), restart_executor
    ).reconcile()

    assert summary["reset_claims"] == 1
    assert summary["delivered"] == 1
    assert restart_executor.dispatches == [created.result["attempt_id"]]
    assert store.counts()["attempts"] == 1


def test_reclaimed_outbox_claim_fences_the_stale_worker_result(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    invocation = _create(tmp_path)
    created = PersistentTaskCore(store, _Executor()).execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok
    stale = store.claim_outbox("dead-worker")
    assert stale is not None
    assert store.reset_expired_outbox_claims(claimed_before="9999-01-01T00:00:00Z") == 1
    current = store.claim_outbox("replacement-worker")
    assert current is not None

    with pytest.raises(FormalTaskViolation) as raised:
        store.complete_outbox(
            stale,
            executor_ref=f"legacy:{stale.attempt_id}",
            observations=_observations(stale),
        )

    assert raised.value.reason == "OUTBOX_CLAIM_LOST"
    store.complete_outbox(
        current,
        executor_ref=f"legacy:{current.attempt_id}",
        observations=_observations(current),
    )


@pytest.mark.asyncio
async def test_lost_reconciliation_suppresses_retrying_cancel_outbox(
    tmp_path: Path,
) -> None:
    class UncertainCancelExecutor(_Executor):
        async def cancel(self, item: PersistentOutboxItem) -> ExecutorDeliveryResult:
            self.cancels.append(item.attempt_id)
            raise FormalTaskViolation(
                "EXECUTOR_CANCEL_UNAVAILABLE",
                "cancel result is unavailable",
                ErrorCode.UNAVAILABLE,
            )

    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    executor = UncertainCancelExecutor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    task_id = str(created.result["task_id"])
    cancel = _cancel(task_id)
    assert core.execute(cancel.envelope, cancel.authorization, now=NOW).ok
    executor.status_resolution = ExecutorResolution.LOST

    summary = await core.reconcile()

    assert summary["delivery_unavailable"] == 1
    assert summary["lost"] == 1
    assert await core.drain_outbox() == 0
    assert executor.cancels == [created.result["attempt_id"]]
    assert store.get_task(task_id, _scope()).outcome is TerminalOutcome.INTERRUPTED


def test_wrong_scope_query_and_wrong_grant_do_not_disclose_or_mutate(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    before = store.counts()
    task_id = str(created.result["task_id"])

    cancel = _cancel(task_id)
    wrong_grant = replace(cancel.authorization, principal_id="other-user")
    denied = core.execute(cancel.envelope, wrong_grant, now=NOW)
    assert not denied.ok
    assert denied.error is not None
    assert denied.error.reason == "FORMAL_TASK_AUTHORIZATION_DENIED"

    foreign_scope = ScopeRef(
        "other-user", "project-1", "session-1", Assurance.AUTHENTICATED
    )
    foreign_query = replace(
        _status(task_id),
        authorization=TaskAuthorizationGrant(
            principal_id="other-user",
            scope=foreign_scope,
            operation="task.status",
            command_id=None,
            target_task_id=task_id,
            allowed_capabilities=frozenset({"task.status"}),
            confirmation_id=None,
            confirmed=False,
            expires_at=EXPIRY,
        ),
    )
    raw_query = foreign_query.envelope.to_dict()
    raw_query["scope"] = foreign_scope.to_dict()
    hidden = core.query(
        QueryEnvelope.from_dict(raw_query), foreign_query.authorization, now=NOW
    )
    assert not hidden.ok
    assert hidden.error is not None
    assert hidden.error.reason == "TASK_NOT_FOUND"
    assert store.counts() == before


def test_corrupt_persisted_spec_fails_closed_without_executor_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before = store.counts()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE tasks SET spec_json=? WHERE task_id=?",
            ("not-json", task_id),
        )
    status = _status(task_id)

    result = core.query(status.envelope, status.authorization, now=NOW)

    assert not result.ok
    assert result.error is not None
    assert result.error.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert executor.dispatches == []
    assert executor.cancels == []


def test_structurally_corrupt_persisted_scope_fails_closed_without_executor_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    before = store.counts()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE tasks SET scope_json=? WHERE task_id=?",
            (
                '{"assurance":"authenticated","project_id":"project-1",'
                '"session_id":"session-1","user_id":42}',
                task_id,
            ),
        )
    status = _status(task_id)

    result = core.query(status.envelope, status.authorization, now=NOW)

    assert not result.ok
    assert result.error is not None
    assert result.error.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
async def test_corrupt_task_scope_key_cannot_disclose_or_dispatch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    secret_instruction = "PRIVATE PROJECT INSTRUCTION: rotate the internal key."
    invocation = _create(tmp_path, instruction=secret_instruction)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    foreign_scope = ScopeRef(
        "foreign-user", "foreign-project", "foreign-session", Assurance.AUTHENTICATED
    )
    foreign_scope_key = json.dumps(
        foreign_scope.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE tasks SET scope_key=? WHERE task_id=?",
            (foreign_scope_key, task_id),
        )
    before = store.counts()
    status = _status(task_id)
    raw_query = status.envelope.to_dict()
    raw_query["scope"] = foreign_scope.to_dict()
    foreign_grant = TaskAuthorizationGrant(
        principal_id="foreign-user",
        scope=foreign_scope,
        operation="task.status",
        command_id=None,
        target_task_id=task_id,
        allowed_capabilities=frozenset({"task.status"}),
        confirmation_id=None,
        confirmed=False,
        expires_at=EXPIRY,
    )

    hidden = core.query(QueryEnvelope.from_dict(raw_query), foreign_grant, now=NOW)

    assert not hidden.ok
    assert hidden.error is not None
    assert hidden.error.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in json.dumps(hidden.to_dict())
    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")
    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in str(raised.value)
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox
            """
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["scope", "executor"])
async def test_corrupt_outbox_binding_fails_before_executor_effect(
    tmp_path: Path,
    corruption: str,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT payload_json FROM outbox").fetchone()
        assert row is not None
        payload = json.loads(row[0])
        if corruption == "scope":
            payload["scope"]["project_id"] = "project-other"
        else:
            payload["spec"]["executor_id"] = "foreign-executor"
        connection.execute(
            "UPDATE outbox SET payload_json=?",
            (json.dumps(payload, sort_keys=True),),
        )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert store.get_attempt(str(created.result["attempt_id"])).executor_ref is None
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox
            """
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    [
        "cancel_to_dispatch",
        "dispatch_to_cancel",
        "dispatch_lifecycle",
        "foreign_command",
        "command_payload",
    ],
)
async def test_corrupt_outbox_command_binding_cannot_claim_or_execute(
    tmp_path: Path,
    corruption: str,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    secret_instruction = "PRIVATE PRIMARY TASK INSTRUCTION"
    invocation = _create(tmp_path, instruction=secret_instruction)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    target_outbox_id = str(created.result["outbox_id"])
    if corruption == "cancel_to_dispatch":
        held_dispatch = store.claim_outbox("held-dispatch")
        assert held_dispatch is not None
        cancel = _cancel(task_id)
        acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
        assert acknowledged.ok and acknowledged.result is not None
        target_outbox_id = str(acknowledged.result["outbox_id"])
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET kind=? WHERE outbox_id=?",
                ("attempt.dispatch", target_outbox_id),
            )
    elif corruption == "dispatch_to_cancel":
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET kind=? WHERE outbox_id=?",
                ("attempt.cancel", target_outbox_id),
            )
    elif corruption == "dispatch_lifecycle":
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE tasks SET cancel_requested=1, dispatch_fenced=1
                WHERE task_id=?
                """,
                (task_id,),
            )
    elif corruption == "foreign_command":
        other_invocation = _create(
            tmp_path,
            instruction="Different task instruction.",
            identity_suffix="-foreign-command",
        )
        other = core.execute(
            other_invocation.envelope,
            other_invocation.authorization,
            context=other_invocation.context,
            now=NOW,
        )
        assert other.ok and other.result is not None
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET state=? WHERE outbox_id=?",
                ("suppressed", str(other.result["outbox_id"])),
            )
            connection.execute(
                "UPDATE outbox SET command_id=? WHERE outbox_id=?",
                (other_invocation.envelope.command_id, target_outbox_id),
            )
    else:
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT fingerprint FROM commands WHERE command_id=?",
                (invocation.envelope.command_id,),
            ).fetchone()
            assert row is not None
            fingerprint = json.loads(row[0])
            fingerprint["command"]["payload"]["instruction"] = (
                "FOREIGN COMMAND INSTRUCTION"
            )
            connection.execute(
                "UPDATE commands SET fingerprint=? WHERE command_id=?",
                (
                    json.dumps(fingerprint, sort_keys=True).encode(),
                    invocation.envelope.command_id,
                ),
            )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in str(raised.value)
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (target_outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("durable_state", "corrupt_result_state"),
    [
        (FormalTaskState.ACCEPTED, FormalTaskState.RUNNING),
        (FormalTaskState.RUNNING, FormalTaskState.ACCEPTED),
    ],
)
async def test_corrupt_cancel_result_state_cannot_claim_or_execute(
    tmp_path: Path,
    durable_state: FormalTaskState,
    corrupt_result_state: FormalTaskState,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    secret_instruction = "PRIVATE CANCEL TARGET INSTRUCTION"
    invocation = _create(tmp_path, instruction=secret_instruction)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    if durable_state is FormalTaskState.RUNNING:
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{dispatch.attempt_id}",
            observations=_observations(dispatch),
        )
    cancel = _cancel(task_id)
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    assert acknowledged.result["state"] == durable_state.value
    cancel_outbox_id = str(acknowledged.result["outbox_id"])
    events = store.events(task_id, _scope())
    cancel_event = next(
        event for event in events if event.event_type == "task.cancel_requested"
    )
    assert cancel_event.state == durable_state.value
    assert cancel_event.causation_id == cancel.envelope.command_id
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?",
            (cancel.envelope.command_id,),
        ).fetchone()
        assert row is not None
        result = json.loads(row[0])
        result["result"]["state"] = corrupt_result_state.value
        connection.execute(
            "UPDATE commands SET result_json=? WHERE command_id=?",
            (
                json.dumps(result, sort_keys=True),
                cancel.envelope.command_id,
            ),
        )
    before = store.counts()

    if durable_state is FormalTaskState.ACCEPTED:
        with pytest.raises(FormalTaskViolation) as raised:
            store.complete_outbox(
                dispatch,
                executor_ref=f"legacy:{dispatch.attempt_id}",
                observations=_observations(dispatch),
            )
        assert store.get_attempt(dispatch.attempt_id).executor_ref is None
    else:
        with pytest.raises(FormalTaskViolation) as raised:
            await core.drain_outbox_once(worker_id="cancel-worker")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert secret_instruction not in str(raised.value)
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (cancel_outbox_id,),
        ).fetchone()
        dispatch_outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (dispatch.outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    if durable_state is FormalTaskState.ACCEPTED:
        assert dispatch_outbox == (
            "claimed",
            1,
            "dispatch-worker",
            dispatch.claim_token,
        )
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corrupt_executor_ref", [None, "legacy:other-attempt"])
async def test_corrupt_cancel_outbox_executor_ref_fails_before_executor_effect(
    tmp_path: Path,
    corrupt_executor_ref: str | None,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    store.complete_outbox(
        dispatch,
        executor_ref=f"legacy:{attempt_id}",
        observations=_observations(dispatch),
    )
    cancel = _cancel(task_id)
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    cancel_outbox_id = str(acknowledged.result["outbox_id"])
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM outbox WHERE outbox_id=?",
            (cancel_outbox_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["executor_ref"] = corrupt_executor_ref
        connection.execute(
            "UPDATE outbox SET payload_json=? WHERE outbox_id=?",
            (json.dumps(payload, sort_keys=True), cancel_outbox_id),
        )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="cancel-worker")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (cancel_outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
async def test_dispatch_completion_does_not_overwrite_corrupt_cancel_binding(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    dispatch = store.claim_outbox("dispatch-worker")
    assert dispatch is not None
    cancel = _cancel(task_id)
    acknowledged = core.execute(cancel.envelope, cancel.authorization, now=NOW)
    assert acknowledged.ok and acknowledged.result is not None
    cancel_outbox_id = str(acknowledged.result["outbox_id"])
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM outbox WHERE outbox_id=?",
            (cancel_outbox_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert payload["executor_ref"] is None
        payload["executor_ref"] = "legacy:foreign-attempt"
        connection.execute(
            "UPDATE outbox SET payload_json=? WHERE outbox_id=?",
            (json.dumps(payload, sort_keys=True), cancel_outbox_id),
        )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        store.complete_outbox(
            dispatch,
            executor_ref=f"legacy:{attempt_id}",
            observations=_observations(dispatch),
        )

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    assert store.get_attempt(attempt_id).executor_ref is None
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT outbox_id, state, delivery_count, claimed_by, claim_token,
                   payload_json
            FROM outbox ORDER BY outbox_id
            """
        ).fetchall()
    by_id = {row[0]: row for row in rows}
    assert by_id[dispatch.outbox_id][1:5] == (
        "claimed",
        1,
        "dispatch-worker",
        dispatch.claim_token,
    )
    assert by_id[cancel_outbox_id][1:5] == ("pending", 0, None, None)
    assert json.loads(by_id[cancel_outbox_id][5])["executor_ref"] == (
        "legacy:foreign-attempt"
    )
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["missing_attempt", "cross_binding"])
async def test_corrupt_outbox_canonical_binding_is_not_hidden(
    tmp_path: Path,
    corruption: str,
) -> None:
    database = tmp_path / "tasks.sqlite"
    store = SqliteTaskStore(database)
    executor = _Executor()
    core = PersistentTaskCore(store, executor)
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    task_id = str(created.result["task_id"])
    attempt_id = str(created.result["attempt_id"])
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT outbox_id FROM outbox WHERE task_id=?", (task_id,)
        ).fetchone()
        assert row is not None
        outbox_id = str(row[0])
    if corruption == "missing_attempt":
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM attempts WHERE attempt_id=?", (attempt_id,))
    else:
        other_invocation = _create(tmp_path, identity_suffix="-other")
        other = core.execute(
            other_invocation.envelope,
            other_invocation.authorization,
            context=other_invocation.context,
            now=NOW,
        )
        assert other.ok and other.result is not None
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE outbox SET state=? WHERE task_id=?",
                ("suppressed", str(other.result["task_id"])),
            )
            connection.execute(
                "UPDATE outbox SET attempt_id=? WHERE outbox_id=?",
                (str(other.result["attempt_id"]), outbox_id),
            )
    before = store.counts()

    with pytest.raises(FormalTaskViolation) as raised:
        await core.drain_outbox_once(worker_id="worker-corrupt")

    assert raised.value.reason == "TASK_STORE_CORRUPT"
    assert store.counts() == before
    with sqlite3.connect(database) as connection:
        outbox = connection.execute(
            """
            SELECT state, delivery_count, claimed_by, claimed_at, claim_token
            FROM outbox WHERE outbox_id=?
            """,
            (outbox_id,),
        ).fetchone()
    assert outbox == ("pending", 0, None, None, None)
    assert executor.dispatches == []
    assert executor.cancels == []


@pytest.mark.asyncio
async def test_task_event_projection_is_pure_and_preserves_source(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    invocation = _create(tmp_path)
    core = PersistentTaskCore(store, _Executor())
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    event = next(
        candidate
        for candidate in store.events(str(created.result["task_id"]), _scope())
        if candidate.event_type == "task.running"
    )
    before = store.counts()

    progress = project_task_event(event)

    assert progress["work_ref"] == {"kind": "task", "id": created.result["task_id"]}
    parsed = WorkProgressEventV2.from_dict(progress)
    assert parsed.source.source_work_ref == parsed.work_ref
    assert progress["source"]["event_id"] == event.event_id
    assert progress["source"]["adapter"] is None
    assert progress["urgency"] == "unknown"
    assert progress["speakability"] == "not_speakable"
    assert event.scope == _scope()
    assert event.to_dict()["scope"] == _scope().to_dict()
    assert store.counts() == before


@pytest.mark.asyncio
async def test_event_authority_snapshot_is_one_exact_contiguous_store_revision(
    tmp_path: Path,
) -> None:
    event_queries: list[str] = []

    def failpoint(name: str) -> None:
        if name == "event_authority_snapshot.before_events":
            event_queries.append(name)

    store = SqliteTaskStore(tmp_path / "authority-snapshot.sqlite", failpoint=failpoint)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    task_id = str(created.result["task_id"])

    snapshot = store.event_authority_snapshot(task_id, _scope(), max_events=64)

    assert snapshot.task.task_id == task_id
    assert snapshot.attempt.attempt_id == snapshot.task.attempt_id
    assert snapshot.cursor == snapshot.task.event_head
    assert [event.seq for event in snapshot.events] == list(range(snapshot.cursor + 1))
    assert all(event.task_id == task_id for event in snapshot.events)
    assert event_queries == ["event_authority_snapshot.before_events"]


@pytest.mark.parametrize("max_events", [0, -1, True])
def test_event_authority_snapshot_rejects_invalid_capacity(
    tmp_path: Path, max_events: int
) -> None:
    store = SqliteTaskStore(tmp_path / f"authority-invalid-{max_events}.sqlite")

    with pytest.raises(FormalTaskViolation) as raised:
        store.event_authority_snapshot("task-1", _scope(), max_events=max_events)

    assert raised.value.reason == "INVALID_TASK_EVENT_AUTHORITY_CAPACITY"
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


@pytest.mark.asyncio
async def test_event_authority_snapshot_rejects_oversize_before_event_query(
    tmp_path: Path,
) -> None:
    event_queries: list[str] = []

    def failpoint(name: str) -> None:
        if name == "event_authority_snapshot.before_events":
            event_queries.append(name)

    store = SqliteTaskStore(tmp_path / "authority-oversize.sqlite", failpoint=failpoint)
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    task_id = str(created.result["task_id"])

    with pytest.raises(FormalTaskViolation) as raised:
        store.event_authority_snapshot(task_id, _scope(), max_events=1)

    assert raised.value.reason == "TASK_EVENT_AUTHORITY_PREFIX_CAPACITY"
    assert raised.value.code is ErrorCode.UNAVAILABLE
    assert event_queries == []


def test_event_authority_snapshot_rejects_a_corrupt_head_without_partial_prefix(
    tmp_path: Path,
) -> None:
    database = tmp_path / "authority-corrupt.sqlite"
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
        connection.execute("UPDATE tasks SET event_head=1 WHERE task_id=?", (task_id,))

    with pytest.raises(FormalTaskViolation) as raised:
        store.event_authority_snapshot(task_id, _scope(), max_events=64)
    assert raised.value.reason == "TASK_STORE_CORRUPT"


@pytest.mark.asyncio
async def test_attempt_event_cannot_emit_duplicate_progress_and_event_head_is_authoritative(
    tmp_path: Path,
) -> None:
    store = SqliteTaskStore(tmp_path / "tasks.sqlite")
    core = PersistentTaskCore(store, _Executor())
    invocation = _create(tmp_path)
    created = core.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await core.drain_outbox()
    task_id = str(created.result["task_id"])
    events = store.events(task_id, _scope())
    attempt_event = next(
        event for event in events if event.event_type.startswith("attempt.")
    )

    with pytest.raises(FormalTaskViolation) as raised:
        project_task_event(attempt_event)
    assert raised.value.reason == "TASK_EVENT_NOT_PROJECTABLE"

    query = _events(task_id, after_seq=999)
    result = core.query(query.envelope, query.authorization, now=NOW)
    assert result.ok and result.result is not None
    assert result.result["task_id"] == task_id
    assert result.result["after_seq"] == 999
    assert result.result["events"] == []
    assert result.result["head_seq"] == events[-1].seq


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resolution", "terminal", "reconciliation"),
    [
        (ExecutorResolution.LOST, True, None),
        (ExecutorResolution.UNAVAILABLE, False, ReconciliationState.PENDING),
        (None, False, ReconciliationState.RESOLVED),
    ],
)
async def test_restart_reconciles_only_the_original_attempt(
    tmp_path: Path,
    resolution: ExecutorResolution | None,
    terminal: bool,
    reconciliation: ReconciliationState | None,
) -> None:
    database = tmp_path / f"tasks-{resolution}.sqlite"
    first_executor = _Executor()
    first = PersistentTaskCore(SqliteTaskStore(database), first_executor)
    invocation = _create(tmp_path)
    created = first.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await first.drain_outbox()

    restart_executor = _Executor()
    restart_executor.status_resolution = resolution
    restarted_store = SqliteTaskStore(database)
    reconciliation_events: list[tuple[object, object]] = []

    async def reconciliation_sink(event: object, attempt: object) -> None:
        reconciliation_events.append((event, attempt))

    restarted = PersistentTaskCore(
        restarted_store,
        restart_executor,
        reconciliation_event_sink=reconciliation_sink,
    )
    summary = await restarted.reconcile()

    task = restarted_store.get_task(str(created.result["task_id"]), _scope())
    assert task.attempt_id == created.result["attempt_id"]
    assert (task.outcome is TerminalOutcome.INTERRUPTED) is terminal
    assert task.reconciliation_state is reconciliation
    assert restarted_store.counts()["attempts"] == 1
    assert restart_executor.dispatches == []
    assert restart_executor.cancels == []
    assert sum(summary[key] for key in ("known", "unavailable", "lost")) == 1
    if resolution is ExecutorResolution.LOST:
        assert [event.event_type for event, _ in reconciliation_events] == [
            "attempt.terminal",
            "task.terminal",
        ]
        assert all(
            event.task_id == task.task_id
            and event.attempt_id == task.attempt_id
            and attempt.task_id == task.task_id
            and attempt.attempt_id == task.attempt_id
            for event, attempt in reconciliation_events
        )
    else:
        assert reconciliation_events == []
    await restarted.reconcile()
    assert len(reconciliation_events) == (2 if terminal else 0)


@pytest.mark.asyncio
async def test_reconciliation_publishes_frozen_predecessor_receipt_after_retry(
    tmp_path: Path,
) -> None:
    class TerminalStatusExecutor(_Executor):
        async def status(
            self,
            task: PersistentTaskRecord,
            attempt: PersistentAttemptRecord,
        ) -> ExecutorObservation:
            return ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=self.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task.task_id,
                attempt_id=attempt.attempt_id,
                source_event_id=f"status-terminal:{attempt.attempt_id}",
                source_seq=attempt.source_seq + 1,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.COMPLETED,
                occurred_at=utc_now(),
                raw_status="success",
            )

    class RetryBeforeReturnStore(SqliteTaskStore):
        after_apply: object | None = None

        def apply_observations(self, observations):  # type: ignore[no-untyped-def]
            receipt = super().apply_observations(observations)
            callback = self.after_apply
            if callback is not None:
                self.after_apply = None
                callback()  # type: ignore[operator]
            return receipt

    seed_store, _seed_executor, _seed_core, task_id, attempt_a = _terminal_task(
        tmp_path
    )
    store = RetryBeforeReturnStore(seed_store.database_path)
    executor = TerminalStatusExecutor()
    core = PersistentTaskCore(store, executor)
    retry_b, grant_b = _retry(task_id, attempt_a, TerminalOutcome.COMPLETED, 2)
    result_b = core.execute(
        retry_b,
        grant_b,
        context=replace(_context(tmp_path), revision_value="barrier-b"),
        now=NOW,
    )
    assert result_b.ok and result_b.result is not None
    attempt_b = str(result_b.result["attempt_id"])
    item_b = store.claim_outbox("barrier-b")
    assert item_b is not None
    store.complete_outbox(
        item_b,
        executor_ref=f"legacy:{attempt_b}",
        observations=_observations(item_b),
    )
    retry_c, grant_c = _retry(task_id, attempt_b, TerminalOutcome.COMPLETED, 3)

    def create_c() -> None:
        result_c = core.execute(
            retry_c,
            grant_c,
            context=replace(_context(tmp_path), revision_value="barrier-c"),
            now=NOW,
        )
        assert result_c.ok and result_c.result is not None

    store.after_apply = create_c
    published: list[tuple[PersistentTaskEvent, PersistentAttemptRecord]] = []

    async def sink(
        event: PersistentTaskEvent, attempt: PersistentAttemptRecord
    ) -> None:
        published.append((event, attempt))

    core._reconciliation_event_sink = sink

    summary = await core.reconcile()

    assert summary["known"] == 1
    assert [event.event_type for event, _ in published] == [
        "attempt.terminal",
        "task.terminal",
    ]
    assert all(
        event.attempt_id == attempt_b and attempt.attempt_id == attempt_b
        for event, attempt in published
    )
    assert all(event.event_type != "task.retry_accepted" for event, _ in published)
    assert store.get_task(task_id, _scope()).attempt_id != attempt_b


@pytest.mark.asyncio
async def test_reconciliation_counts_superseded_status_race_and_continues(
    tmp_path: Path,
) -> None:
    database = tmp_path / "reconcile-status-race.sqlite"
    store = SqliteTaskStore(database)
    seed_core = PersistentTaskCore(store, _Executor())
    for suffix in ("-race-one", "-race-two"):
        invocation = _create(tmp_path, identity_suffix=suffix)
        created = seed_core.execute(
            invocation.envelope,
            invocation.authorization,
            context=invocation.context,
            now=NOW,
        )
        assert created.ok
    await seed_core.drain_outbox()

    class AdvancingStatusExecutor(_Executor):
        def __init__(self) -> None:
            super().__init__()
            self.core: PersistentTaskCore | None = None
            self.advanced = False

        async def status(
            self,
            task: PersistentTaskRecord,
            attempt: PersistentAttemptRecord,
        ) -> ExecutorDeliveryResult | ExecutorObservation:
            if self.advanced:
                return ExecutorDeliveryResult(attempt.executor_ref or "", ())
            self.advanced = True
            terminal = ExecutorObservation(
                resolution=ExecutorResolution.KNOWN,
                executor_id=self.executor_id,
                executor_ref=attempt.executor_ref,
                task_id=task.task_id,
                attempt_id=attempt.attempt_id,
                source_event_id=f"racing-terminal:{attempt.attempt_id}",
                source_seq=attempt.source_seq + 1,
                attempt_state=FormalAttemptState.TERMINAL,
                attempt_outcome=TerminalOutcome.COMPLETED,
                occurred_at=utc_now(),
                raw_status="success",
            )
            external = SqliteTaskStore(database)
            external.apply_observations((terminal,))
            retry, grant = _retry(
                task.task_id,
                attempt.attempt_id,
                TerminalOutcome.COMPLETED,
                2,
                command_id=f"command-racing-retry:{attempt.attempt_id}",
                correlation_id=task.correlation_id,
            )
            assert self.core is not None
            retried = self.core.execute(
                retry,
                grant,
                context=replace(_context(tmp_path), revision_value="race-successor"),
                now=NOW,
            )
            assert retried.ok
            return terminal

    executor = AdvancingStatusExecutor()
    core = PersistentTaskCore(store, executor)
    executor.core = core

    summary = await core.reconcile()

    assert summary["superseded"] == 1
    assert summary["known"] == 1
    assert executor.advanced is True


@pytest.mark.asyncio
async def test_reconciliation_sink_failure_cannot_change_durable_task_truth(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sink-failure.sqlite"
    first = PersistentTaskCore(SqliteTaskStore(database), _Executor())
    invocation = _create(tmp_path)
    created = first.execute(
        invocation.envelope,
        invocation.authorization,
        context=invocation.context,
        now=NOW,
    )
    assert created.ok and created.result is not None
    await first.drain_outbox()

    async def failing_sink(_event: object, _attempt: object) -> None:
        raise RuntimeError("evidence sink unavailable")

    executor = _Executor()
    executor.status_resolution = ExecutorResolution.LOST
    store = SqliteTaskStore(database)
    restarted = PersistentTaskCore(
        store,
        executor,
        reconciliation_event_sink=failing_sink,
    )

    summary = await restarted.reconcile()

    task = store.get_task(str(created.result["task_id"]), _scope())
    assert summary["lost"] == 1
    assert task.state is FormalTaskState.TERMINAL
    assert task.outcome is TerminalOutcome.INTERRUPTED
