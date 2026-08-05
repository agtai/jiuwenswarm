# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SQLite authority for formal P3-alpha command/task/event/attempt state."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    CommandEnvelope,
    ContractViolation,
    ErrorCode,
    ResultEnvelope,
    ScopeRef,
    TerminalOutcome,
    canonical_json_bytes,
)

from .formal_task_models import (
    ExecutorObservation,
    ExecutorResolution,
    FormalAttemptState,
    FormalTaskSpec,
    FormalTaskState,
    FormalTaskViolation,
    OutboxKind,
    OutboxState,
    PersistentAttemptRecord,
    PersistentOutboxItem,
    PersistentTaskEvent,
    PersistentTaskRecord,
    ReconciliationState,
    utc_now,
)

_SCHEMA_VERSION = 1
_StoredRecordT = TypeVar("_StoredRecordT")


def _json_dump(value: object) -> str:
    canonical_json_bytes(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(value: str) -> object:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as error:
        raise FormalTaskViolation(
            "TASK_STORE_CORRUPT",
            "formal Task Store contains malformed JSON",
            ErrorCode.INTERNAL,
        ) from error


def _scope_key(scope: ScopeRef) -> str:
    return _json_dump(scope.to_dict())


def _stored_record(
    record_kind: str, loader: Callable[[], _StoredRecordT]
) -> _StoredRecordT:
    try:
        return loader()
    except FormalTaskViolation:
        raise
    except (ContractViolation, KeyError, OverflowError, TypeError, ValueError) as error:
        raise FormalTaskViolation(
            "TASK_STORE_CORRUPT",
            f"formal Task Store contains an invalid {record_kind} record",
            ErrorCode.INTERNAL,
        ) from error


class SqliteTaskStore:
    """Cross-process transactional Store; the legacy schedule JSON is not read."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        failpoint: Callable[[str], None] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._failpoint = failpoint
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=10,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as exc:
            if connection is not None:
                connection.close()
            raise FormalTaskViolation(
                "TASK_STORE_UNAVAILABLE",
                "formal Task Store is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            try:
                connection.rollback()
            finally:
                raise FormalTaskViolation(
                    "TASK_STORE_UNAVAILABLE",
                    "formal Task Store transaction is unavailable",
                    ErrorCode.UNAVAILABLE,
                ) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        except sqlite3.Error as exc:
            raise FormalTaskViolation(
                "TASK_STORE_UNAVAILABLE",
                "formal Task Store read is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        finally:
            connection.close()

    def _initialize(self) -> None:
        journal_connection = self._connect()
        try:
            journal_connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error as exc:
            raise FormalTaskViolation(
                "TASK_STORE_UNAVAILABLE",
                "formal Task Store journal cannot be initialized",
                ErrorCode.UNAVAILABLE,
            ) from exc
        finally:
            journal_connection.close()
        with self._transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT NOT NULL,
                    fingerprint BLOB NOT NULL,
                    command_type TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(scope_key, command_id)
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    scope_key TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    outcome TEXT,
                    attempt_id TEXT NOT NULL UNIQUE,
                    correlation_id TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    dispatch_fenced INTEGER NOT NULL DEFAULT 0,
                    event_head INTEGER NOT NULL,
                    reconciliation_state TEXT,
                    reconciliation_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_scope ON tasks(scope_key, task_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state, task_id);

                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
                    executor_id TEXT NOT NULL,
                    executor_ref TEXT,
                    state TEXT NOT NULL,
                    outcome TEXT,
                    source_seq INTEGER NOT NULL DEFAULT -1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    attempt_id TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    outcome TEXT,
                    producer TEXT NOT NULL,
                    source_event_id TEXT,
                    causation_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    PRIMARY KEY(task_id, seq)
                );

                CREATE TABLE IF NOT EXISTS executor_events (
                    source_event_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
                    source_seq INTEGER NOT NULL,
                    canonical BLOB NOT NULL,
                    UNIQUE(attempt_id, source_seq)
                );

                CREATE TABLE IF NOT EXISTS outbox (
                    outbox_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
                    command_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    claimed_by TEXT,
                    claimed_at TEXT,
                    claim_token TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_outbox_pending
                    ON outbox(state, created_at, outbox_id);
                """
            )
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    (str(_SCHEMA_VERSION),),
                )
            elif int(row["value"]) != _SCHEMA_VERSION:
                raise FormalTaskViolation(
                    "TASK_STORE_SCHEMA_UNSUPPORTED",
                    "formal task Store schema version is unsupported",
                    ErrorCode.UNSUPPORTED,
                )

    def _hit(self, name: str) -> None:
        if self._failpoint is not None:
            self._failpoint(name)

    def create(
        self,
        command: CommandEnvelope,
        spec: FormalTaskSpec,
        *,
        observed_at: str,
    ) -> ResultEnvelope:
        fingerprint = canonical_json_bytes(
            {
                "command": json.loads(command.fingerprint()),
                "resolved_spec": spec.to_dict(),
            }
        )
        scope_key = _scope_key(command.scope)
        with self._transaction() as connection:
            replay = self._command_replay(connection, command, fingerprint)
            if replay is not None:
                return replay
            self._hit("create.before_ids")
            task_id = f"task-{uuid.uuid4().hex}"
            attempt_id = f"attempt-{uuid.uuid4().hex}"
            outbox_id = f"outbox-{uuid.uuid4().hex}"
            event_id = f"event-{uuid.uuid4().hex}"
            now = observed_at
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, scope_key, scope_json, spec_json, state, outcome,
                    attempt_id, correlation_id, event_head, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, NULL, ?, ?, 0, ?, ?)
                """,
                (
                    task_id,
                    scope_key,
                    _json_dump(command.scope.to_dict()),
                    _json_dump(spec.to_dict()),
                    FormalTaskState.ACCEPTED.value,
                    attempt_id,
                    command.correlation_id,
                    now,
                    now,
                ),
            )
            self._hit("create.after_task")
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, task_id, executor_id, executor_ref,
                    state, outcome, source_seq, updated_at
                ) VALUES(?, ?, ?, NULL, ?, NULL, -1, ?)
                """,
                (
                    attempt_id,
                    task_id,
                    spec.executor_id,
                    FormalAttemptState.ACCEPTED.value,
                    now,
                ),
            )
            self._insert_event(
                connection,
                event_id=event_id,
                task_id=task_id,
                attempt_id=attempt_id,
                scope=command.scope,
                seq=0,
                event_type="task.accepted",
                state=FormalTaskState.ACCEPTED.value,
                outcome=None,
                producer="task_core",
                source_event_id=None,
                causation_id=command.command_id,
                correlation_id=command.correlation_id,
                occurred_at=now,
                details={"command_id": command.command_id},
            )
            self._hit("create.after_event")
            self._insert_outbox(
                connection,
                outbox_id=outbox_id,
                kind=OutboxKind.ATTEMPT_DISPATCH,
                task_id=task_id,
                attempt_id=attempt_id,
                command_id=command.command_id,
                scope=command.scope,
                spec=spec,
                now=now,
            )
            self._hit("create.after_outbox")
            result = ResultEnvelope.success(
                owner=command,
                result={
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "state": FormalTaskState.ACCEPTED.value,
                    "outbox_id": outbox_id,
                },
                observed_at=observed_at,
                extensions={"live_voice.store": {"durability": "sqlite_outbox"}},
            )
            self._insert_command(
                connection,
                command,
                fingerprint,
                scope_key,
                result,
                observed_at,
            )
            self._hit("create.after_command")
            return result

    def cancel(
        self,
        command: CommandEnvelope,
        *,
        observed_at: str,
    ) -> ResultEnvelope:
        fingerprint = command.fingerprint()
        scope_key = _scope_key(command.scope)
        task_id = command.target_ref.id
        with self._transaction() as connection:
            replay = self._command_replay(connection, command, fingerprint)
            if replay is not None:
                return replay
            task = self._require_task_row(connection, task_id, command.scope)
            if task["state"] == FormalTaskState.TERMINAL.value:
                raise FormalTaskViolation(
                    "TASK_ALREADY_TERMINAL",
                    "terminal tasks cannot accept cancellation",
                    ErrorCode.CONFLICT,
                )
            if bool(task["cancel_requested"]):
                result = ResultEnvelope.success(
                    owner=command,
                    result={
                        "task_id": task_id,
                        "attempt_id": task["attempt_id"],
                        "cancel_acknowledged": True,
                        "applied": False,
                        "state": task["state"],
                    },
                    observed_at=observed_at,
                )
                self._insert_command(
                    connection,
                    command,
                    fingerprint,
                    scope_key,
                    result,
                    observed_at,
                )
                return result

            dispatch = connection.execute(
                """
                SELECT * FROM outbox
                WHERE task_id=? AND kind=?
                ORDER BY created_at, outbox_id LIMIT 1
                """,
                (task_id, OutboxKind.ATTEMPT_DISPATCH.value),
            ).fetchone()
            if dispatch is None:
                raise FormalTaskViolation(
                    "TASK_DISPATCH_RECORD_MISSING",
                    "task has no durable dispatch record",
                    ErrorCode.INTERNAL,
                )
            now = observed_at
            connection.execute(
                """
                UPDATE tasks SET cancel_requested=1, dispatch_fenced=1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self._hit("cancel.after_snapshot")
            self._append_event(
                connection,
                task,
                event_type="task.cancel_requested",
                state=task["state"],
                outcome=task["outcome"],
                producer="task_core.control",
                source_event_id=None,
                causation_id=command.command_id,
                occurred_at=now,
                details={"command_id": command.command_id},
            )
            self._hit("cancel.after_request_event")
            task = self._require_task_row(connection, task_id, command.scope)
            terminal_before_dispatch = (
                dispatch["state"] == OutboxState.PENDING.value
                and int(dispatch["delivery_count"]) == 0
            )
            cancel_outbox_id: str | None = None
            if terminal_before_dispatch:
                connection.execute(
                    """
                    UPDATE outbox SET state=?, updated_at=?
                    WHERE outbox_id=? AND state=?
                    """,
                    (
                        OutboxState.SUPPRESSED.value,
                        now,
                        dispatch["outbox_id"],
                        OutboxState.PENDING.value,
                    ),
                )
                connection.execute(
                    """
                    UPDATE attempts SET state=?, outcome=?, updated_at=?
                    WHERE attempt_id=?
                    """,
                    (
                        FormalAttemptState.TERMINAL.value,
                        TerminalOutcome.CANCELLED.value,
                        now,
                        task["attempt_id"],
                    ),
                )
                self._append_event(
                    connection,
                    task,
                    event_type="attempt.terminal",
                    state=FormalAttemptState.TERMINAL.value,
                    outcome=TerminalOutcome.CANCELLED.value,
                    producer="task_core.reconciliation",
                    source_event_id=None,
                    causation_id=command.command_id,
                    occurred_at=now,
                    details={"reason": "CANCELLED_BEFORE_DISPATCH"},
                )
                task = self._require_task_row(connection, task_id, command.scope)
                self._append_event(
                    connection,
                    task,
                    event_type="task.terminal",
                    state=FormalTaskState.TERMINAL.value,
                    outcome=TerminalOutcome.CANCELLED.value,
                    producer="task_core",
                    source_event_id=None,
                    causation_id=command.command_id,
                    occurred_at=now,
                    details={"reason": "CANCELLED_BEFORE_DISPATCH"},
                    update_task=True,
                )
            else:
                cancel_outbox_id = f"outbox-{uuid.uuid4().hex}"
                self._insert_outbox(
                    connection,
                    outbox_id=cancel_outbox_id,
                    kind=OutboxKind.ATTEMPT_CANCEL,
                    task_id=task_id,
                    attempt_id=task["attempt_id"],
                    command_id=command.command_id,
                    scope=command.scope,
                    spec=FormalTaskSpec.from_dict(_json_load(task["spec_json"])),
                    now=now,
                    executor_ref=connection.execute(
                        "SELECT executor_ref FROM attempts WHERE attempt_id=?",
                        (task["attempt_id"],),
                    ).fetchone()["executor_ref"],
                )
            self._hit("cancel.after_outbox_or_terminal")
            result = ResultEnvelope.success(
                owner=command,
                result={
                    "task_id": task_id,
                    "attempt_id": task["attempt_id"],
                    "cancel_acknowledged": True,
                    "applied": True,
                    "state": (
                        FormalTaskState.TERMINAL.value
                        if terminal_before_dispatch
                        else task["state"]
                    ),
                    "outbox_id": cancel_outbox_id,
                },
                observed_at=observed_at,
            )
            self._insert_command(
                connection,
                command,
                fingerprint,
                scope_key,
                result,
                observed_at,
            )
            self._hit("cancel.after_command")
            return result

    def _command_replay(
        self,
        connection: sqlite3.Connection,
        command: CommandEnvelope,
        fingerprint: bytes,
    ) -> ResultEnvelope | None:
        row = connection.execute(
            """
            SELECT fingerprint, result_json FROM commands
            WHERE scope_key=? AND command_id=?
            """,
            (_scope_key(command.scope), command.command_id),
        ).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise FormalTaskViolation(
                "IDEMPOTENCY_CONFLICT",
                "command_id is already bound to different task facts",
                ErrorCode.CONFLICT,
            )
        try:
            result = ResultEnvelope.from_dict(_json_load(row["result_json"]))
        except ContractViolation as error:
            raise FormalTaskViolation(
                "TASK_STORE_CORRUPT",
                "formal Task Store contains an invalid command result",
                ErrorCode.INTERNAL,
            ) from error
        return result.for_request(command.request_id)

    @staticmethod
    def _insert_command(
        connection: sqlite3.Connection,
        command: CommandEnvelope,
        fingerprint: bytes,
        scope_key: str,
        result: ResultEnvelope,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO commands(
                command_id, fingerprint, command_type, scope_key,
                result_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                command.command_id,
                fingerprint,
                command.command_type,
                scope_key,
                _json_dump(result.to_dict()),
                created_at,
            ),
        )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        event_id: str,
        task_id: str,
        attempt_id: str,
        scope: ScopeRef,
        seq: int,
        event_type: str,
        state: str,
        outcome: str | None,
        producer: str,
        source_event_id: str | None,
        causation_id: str,
        correlation_id: str,
        occurred_at: str,
        details: dict[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_events(
                task_id, seq, event_id, attempt_id, scope_json, event_type, state, outcome,
                producer, source_event_id, causation_id, correlation_id,
                occurred_at, details_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                seq,
                event_id,
                attempt_id,
                _json_dump(scope.to_dict()),
                event_type,
                state,
                outcome,
                producer,
                source_event_id,
                causation_id,
                correlation_id,
                occurred_at,
                _json_dump(details),
            ),
        )

    @staticmethod
    def _insert_outbox(
        connection: sqlite3.Connection,
        *,
        outbox_id: str,
        kind: OutboxKind,
        task_id: str,
        attempt_id: str,
        command_id: str,
        scope: ScopeRef,
        spec: FormalTaskSpec,
        now: str,
        executor_ref: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO outbox(
                outbox_id, kind, task_id, attempt_id, command_id, payload_json,
                state, delivery_count, claimed_by, claimed_at, claim_token, last_error,
                created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                outbox_id,
                kind.value,
                task_id,
                attempt_id,
                command_id,
                _json_dump(
                    {
                        "scope": scope.to_dict(),
                        "spec": spec.to_dict(),
                        "executor_ref": executor_ref,
                    }
                ),
                OutboxState.PENDING.value,
                now,
                now,
            ),
        )

    def claim_outbox(self, worker_id: str) -> PersistentOutboxItem | None:
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        now = utc_now()
        claim_token = uuid.uuid4().hex
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT o.*, a.executor_ref AS bound_executor_ref,
                       a.source_seq AS bound_source_seq
                FROM outbox AS o
                JOIN attempts AS a ON a.attempt_id=o.attempt_id
                WHERE o.state=?
                  AND (
                    o.kind=?
                    OR (o.kind=? AND a.executor_ref IS NOT NULL)
                  )
                ORDER BY o.updated_at, o.created_at, o.outbox_id LIMIT 1
                """,
                (
                    OutboxState.PENDING.value,
                    OutboxKind.ATTEMPT_DISPATCH.value,
                    OutboxKind.ATTEMPT_CANCEL.value,
                ),
            ).fetchone()
            if row is None:
                return None
            changed = connection.execute(
                """
                UPDATE outbox
                SET state=?, delivery_count=delivery_count+1,
                    claimed_by=?, claimed_at=?, claim_token=?, updated_at=?
                WHERE outbox_id=? AND state=?
                """,
                (
                    OutboxState.CLAIMED.value,
                    worker_id,
                    now,
                    claim_token,
                    now,
                    row["outbox_id"],
                    OutboxState.PENDING.value,
                ),
            ).rowcount
            if changed != 1:
                return None
            claimed = connection.execute(
                """
                SELECT o.*, a.executor_ref AS bound_executor_ref,
                       a.source_seq AS bound_source_seq
                FROM outbox AS o
                JOIN attempts AS a ON a.attempt_id=o.attempt_id
                WHERE o.outbox_id=?
                """,
                (row["outbox_id"],),
            ).fetchone()
            return self._outbox_from_row(claimed)

    def release_outbox(self, item: PersistentOutboxItem, error: str) -> bool:
        with self._transaction() as connection:
            return (
                connection.execute(
                    """
                UPDATE outbox SET state=?, claimed_by=NULL, claimed_at=NULL,
                    claim_token=NULL, last_error=?, updated_at=?
                WHERE outbox_id=? AND state=? AND claim_token=?
                """,
                    (
                        OutboxState.PENDING.value,
                        error[:1000],
                        utc_now(),
                        item.outbox_id,
                        OutboxState.CLAIMED.value,
                        item.claim_token,
                    ),
                ).rowcount
                == 1
            )

    def reject_outbox(
        self, item: PersistentOutboxItem, error: FormalTaskViolation
    ) -> None:
        """Terminally reject a non-retriable delivery without inventing an Executor fact."""

        now = utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE outbox_id=?", (item.outbox_id,)
            ).fetchone()
            if (
                row is None
                or row["state"] != OutboxState.CLAIMED.value
                or item.claim_token is None
                or row["claim_token"] != item.claim_token
            ):
                raise FormalTaskViolation(
                    "OUTBOX_CLAIM_LOST",
                    "only the claimed outbox item can be rejected",
                    ErrorCode.CONFLICT,
                )
            if (
                row["task_id"] != item.task_id
                or row["attempt_id"] != item.attempt_id
                or row["kind"] != item.kind.value
            ):
                raise FormalTaskViolation(
                    "OUTBOX_BINDING_MISMATCH",
                    "claimed outbox identity does not match its stored delivery",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            task = self._require_task_row_by_id(connection, item.task_id)
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (item.attempt_id,)
            ).fetchone()
            if attempt is None or attempt["task_id"] != item.task_id:
                raise FormalTaskViolation(
                    "ATTEMPT_SCOPE_MISMATCH",
                    "rejected delivery does not belong to the formal task",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            terminal_dispatch_rejection = (
                item.kind is OutboxKind.ATTEMPT_DISPATCH
                and task["state"] != FormalTaskState.TERMINAL.value
            )
            if terminal_dispatch_rejection:
                connection.execute(
                    """
                    UPDATE attempts SET state=?, outcome=?, updated_at=?
                    WHERE attempt_id=?
                    """,
                    (
                        FormalAttemptState.TERMINAL.value,
                        TerminalOutcome.FAILED.value,
                        now,
                        item.attempt_id,
                    ),
                )
                details = {"reason": error.reason, "error": str(error)}
                self._append_event(
                    connection,
                    task,
                    event_type="attempt.terminal",
                    state=FormalAttemptState.TERMINAL.value,
                    outcome=TerminalOutcome.FAILED.value,
                    producer="task_core.delivery",
                    source_event_id=None,
                    causation_id=item.outbox_id,
                    occurred_at=now,
                    details=details,
                )
                self._append_event(
                    connection,
                    self._require_task_row_by_id(connection, item.task_id),
                    event_type="task.terminal",
                    state=FormalTaskState.TERMINAL.value,
                    outcome=TerminalOutcome.FAILED.value,
                    producer="task_core.delivery",
                    source_event_id=None,
                    causation_id=item.outbox_id,
                    occurred_at=now,
                    details=details,
                    update_task=True,
                )
            elif task["state"] != FormalTaskState.TERMINAL.value:
                connection.execute(
                    """
                    UPDATE tasks SET reconciliation_state=?, reconciliation_reason=?,
                        updated_at=? WHERE task_id=?
                    """,
                    (
                        ReconciliationState.PENDING.value,
                        f"{error.reason}: {error}"[:1000],
                        now,
                        item.task_id,
                    ),
                )
            connection.execute(
                """
                UPDATE outbox SET state=?, claimed_by=NULL, claimed_at=NULL,
                    claim_token=NULL, last_error=?, updated_at=? WHERE outbox_id=?
                """,
                (
                    OutboxState.SUPPRESSED.value,
                    f"{error.reason}: {error}"[:1000],
                    now,
                    item.outbox_id,
                ),
            )
            if terminal_dispatch_rejection:
                connection.execute(
                    """
                    UPDATE outbox SET state=?, last_error=?, updated_at=?
                    WHERE task_id=? AND state=? AND outbox_id<>?
                    """,
                    (
                        OutboxState.SUPPRESSED.value,
                        "TASK_TERMINAL_BEFORE_DELIVERY",
                        now,
                        item.task_id,
                        OutboxState.PENDING.value,
                        item.outbox_id,
                    ),
                )

    def complete_outbox(
        self,
        item: PersistentOutboxItem,
        *,
        executor_ref: str,
        observations: tuple[ExecutorObservation, ...],
    ) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE outbox_id=?", (item.outbox_id,)
            ).fetchone()
            if (
                row is None
                or row["state"] != OutboxState.CLAIMED.value
                or item.claim_token is None
                or row["claim_token"] != item.claim_token
            ):
                raise FormalTaskViolation(
                    "OUTBOX_CLAIM_LOST",
                    "claimed outbox item is no longer deliverable",
                    ErrorCode.CONFLICT,
                )
            if (
                row["task_id"] != item.task_id
                or row["attempt_id"] != item.attempt_id
                or row["kind"] != item.kind.value
            ):
                raise FormalTaskViolation(
                    "OUTBOX_BINDING_MISMATCH",
                    "claimed outbox identity does not match its stored delivery",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (item.attempt_id,)
            ).fetchone()
            if attempt is None or attempt["executor_id"] != item.spec.executor_id:
                raise FormalTaskViolation(
                    "EXECUTOR_BINDING_MISMATCH",
                    "outbox executor does not match the stored attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if attempt["executor_ref"] not in {None, executor_ref}:
                raise FormalTaskViolation(
                    "EXECUTOR_REFERENCE_CONFLICT",
                    "attempt cannot change its executor reference",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            connection.execute(
                "UPDATE attempts SET executor_ref=?, updated_at=? WHERE attempt_id=?",
                (executor_ref, utc_now(), item.attempt_id),
            )
            for observation in observations:
                self._apply_observation(connection, observation)
            connection.execute(
                """
                UPDATE outbox SET state=?, claimed_by=NULL, claimed_at=NULL,
                    claim_token=NULL, last_error=NULL, updated_at=? WHERE outbox_id=?
                """,
                (OutboxState.DELIVERED.value, utc_now(), item.outbox_id),
            )

    def apply_observations(self, observations: tuple[ExecutorObservation, ...]) -> None:
        with self._transaction() as connection:
            for observation in observations:
                self._apply_observation(connection, observation)

    def _apply_observation(
        self, connection: sqlite3.Connection, observation: ExecutorObservation
    ) -> None:
        if observation.resolution is not ExecutorResolution.KNOWN:
            raise FormalTaskViolation(
                "EXECUTOR_FACT_NOT_KNOWN",
                "only known Executor observations can change lifecycle state",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            observation.source_event_id is None
            or observation.source_seq is None
            or observation.attempt_state is None
        ):
            raise FormalTaskViolation(
                "EXECUTOR_EVENT_INCOMPLETE",
                "known Executor observation lacks event identity or state",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        attempt = connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (observation.attempt_id,)
        ).fetchone()
        if (
            attempt is None
            or attempt["task_id"] != observation.task_id
            or attempt["executor_id"] != observation.executor_id
            or attempt["executor_ref"] != observation.executor_ref
        ):
            raise FormalTaskViolation(
                "EXECUTOR_OBSERVATION_BINDING_MISMATCH",
                "Executor observation does not bind the exact attempt",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        canonical = canonical_json_bytes(observation.canonical_dict())
        existing = connection.execute(
            "SELECT canonical FROM executor_events WHERE source_event_id=?",
            (observation.source_event_id,),
        ).fetchone()
        if existing is not None:
            if existing["canonical"] != canonical:
                raise FormalTaskViolation(
                    "EXECUTOR_EVENT_ID_CONFLICT",
                    "Executor event identity was reused with different facts",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            return
        expected_source_seq = int(attempt["source_seq"]) + 1
        if observation.source_seq != expected_source_seq:
            raise FormalTaskViolation(
                "EXECUTOR_EVENT_SEQUENCE_GAP",
                f"expected Executor sequence {expected_source_seq}",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        connection.execute(
            """
            INSERT INTO executor_events(source_event_id, attempt_id, source_seq, canonical)
            VALUES(?, ?, ?, ?)
            """,
            (
                observation.source_event_id,
                observation.attempt_id,
                observation.source_seq,
                canonical,
            ),
        )
        current = FormalAttemptState(attempt["state"])
        target = observation.attempt_state
        if target is current:
            if target is not FormalAttemptState.ACCEPTED:
                raise FormalTaskViolation(
                    "EXECUTOR_TRANSITION_REPEATED",
                    "non-initial Executor lifecycle state cannot be re-emitted",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
        elif (
            current is FormalAttemptState.ACCEPTED
            and target is FormalAttemptState.RUNNING
        ) or (
            current is FormalAttemptState.RUNNING
            and target is FormalAttemptState.TERMINAL
        ):
            pass
        else:
            raise FormalTaskViolation(
                "INVALID_EXECUTOR_TRANSITION",
                f"Executor attempt cannot transition {current.value} -> {target.value}",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        if target is FormalAttemptState.TERMINAL:
            if observation.attempt_outcome is None:
                raise FormalTaskViolation(
                    "TERMINAL_OUTCOME_REQUIRED",
                    "terminal Executor observation requires an outcome",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
        elif observation.attempt_outcome is not None:
            raise FormalTaskViolation(
                "NONTERMINAL_OUTCOME_FORBIDDEN",
                "nonterminal Executor observation cannot carry an outcome",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        connection.execute(
            """
            UPDATE attempts SET state=?, outcome=?, source_seq=?, updated_at=?
            WHERE attempt_id=?
            """,
            (
                target.value,
                (
                    None
                    if observation.attempt_outcome is None
                    else observation.attempt_outcome.value
                ),
                observation.source_seq,
                observation.occurred_at,
                observation.attempt_id,
            ),
        )
        task = self._require_task_row_by_id(connection, observation.task_id)
        details = {
            "raw_status": observation.raw_status,
            "summary": observation.summary,
            "error": observation.error,
        }
        self._append_event(
            connection,
            task,
            event_type=f"attempt.{target.value}",
            state=target.value,
            outcome=(
                None
                if observation.attempt_outcome is None
                else observation.attempt_outcome.value
            ),
            producer=observation.executor_id,
            source_event_id=observation.source_event_id,
            causation_id=observation.source_event_id,
            occurred_at=observation.occurred_at,
            details=details,
        )
        task = self._require_task_row_by_id(connection, observation.task_id)
        task_state = FormalTaskState(task["state"])
        if (
            target is FormalAttemptState.RUNNING
            and task_state is FormalTaskState.ACCEPTED
        ):
            self._append_event(
                connection,
                task,
                event_type="task.running",
                state=FormalTaskState.RUNNING.value,
                outcome=None,
                producer="task_core",
                source_event_id=observation.source_event_id,
                causation_id=observation.source_event_id,
                occurred_at=observation.occurred_at,
                details=details,
                update_task=True,
            )
        elif target is FormalAttemptState.TERMINAL:
            assert observation.attempt_outcome is not None
            if task_state is FormalTaskState.TERMINAL:
                raise FormalTaskViolation(
                    "TASK_TERMINAL_CONFLICT",
                    "terminal task cannot accept a new Executor outcome",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            self._append_event(
                connection,
                self._require_task_row_by_id(connection, observation.task_id),
                event_type="task.terminal",
                state=FormalTaskState.TERMINAL.value,
                outcome=observation.attempt_outcome.value,
                producer="task_core",
                source_event_id=observation.source_event_id,
                causation_id=observation.source_event_id,
                occurred_at=observation.occurred_at,
                details=details,
                update_task=True,
            )
            connection.execute(
                """
                UPDATE outbox SET state=?, last_error=?, updated_at=?
                WHERE task_id=? AND kind=? AND state=?
                """,
                (
                    OutboxState.SUPPRESSED.value,
                    "TASK_TERMINAL_BEFORE_CANCELLATION_DELIVERY",
                    observation.occurred_at,
                    observation.task_id,
                    OutboxKind.ATTEMPT_CANCEL.value,
                    OutboxState.PENDING.value,
                ),
            )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        task: sqlite3.Row,
        *,
        event_type: str,
        state: str,
        outcome: str | None,
        producer: str,
        source_event_id: str | None,
        causation_id: str,
        occurred_at: str,
        details: Mapping[str, object],
        update_task: bool = False,
    ) -> PersistentTaskEvent:
        event_details = dict(details)
        seq = int(task["event_head"]) + 1
        event_id = f"event-{uuid.uuid4().hex}"
        self._insert_event(
            connection,
            event_id=event_id,
            task_id=task["task_id"],
            attempt_id=task["attempt_id"],
            scope=ScopeRef.from_dict(_json_load(task["scope_json"])),
            seq=seq,
            event_type=event_type,
            state=state,
            outcome=outcome,
            producer=producer,
            source_event_id=source_event_id,
            causation_id=causation_id,
            correlation_id=task["correlation_id"],
            occurred_at=occurred_at,
            details=event_details,
        )
        if update_task:
            connection.execute(
                """
                UPDATE tasks SET state=?, outcome=?, event_head=?, updated_at=?,
                    reconciliation_state=NULL, reconciliation_reason=NULL
                WHERE task_id=?
                """,
                (state, outcome, seq, occurred_at, task["task_id"]),
            )
        else:
            connection.execute(
                "UPDATE tasks SET event_head=?, updated_at=? WHERE task_id=?",
                (seq, occurred_at, task["task_id"]),
            )
        return PersistentTaskEvent(
            event_id=event_id,
            task_id=task["task_id"],
            attempt_id=task["attempt_id"],
            scope=ScopeRef.from_dict(_json_load(task["scope_json"])),
            seq=seq,
            event_type=event_type,
            state=state,
            outcome=outcome,
            producer=producer,
            source_event_id=source_event_id,
            causation_id=causation_id,
            correlation_id=task["correlation_id"],
            occurred_at=occurred_at,
            details=event_details,
        )

    def reset_expired_outbox_claims(self, *, claimed_before: str) -> int:
        with self._transaction() as connection:
            return connection.execute(
                """
                UPDATE outbox SET state=?, claimed_by=NULL, claimed_at=NULL,
                    claim_token=NULL, updated_at=?
                WHERE state=? AND claimed_at IS NOT NULL AND claimed_at<=?
                """,
                (
                    OutboxState.PENDING.value,
                    utc_now(),
                    OutboxState.CLAIMED.value,
                    claimed_before,
                ),
            ).rowcount

    def mark_reconciliation_pending(
        self, task_id: str, reason: str, *, in_progress: bool = False
    ) -> None:
        state = (
            ReconciliationState.IN_PROGRESS
            if in_progress
            else ReconciliationState.PENDING
        )
        with self._transaction() as connection:
            task = self._require_task_row_by_id(connection, task_id)
            if task["state"] == FormalTaskState.TERMINAL.value:
                return
            connection.execute(
                """
                UPDATE tasks SET reconciliation_state=?, reconciliation_reason=?,
                    updated_at=? WHERE task_id=?
                """,
                (state.value, reason, utc_now(), task_id),
            )

    def mark_reconciliation_resolved(self, task_id: str, reason: str) -> None:
        with self._transaction() as connection:
            task = self._require_task_row_by_id(connection, task_id)
            if task["state"] == FormalTaskState.TERMINAL.value:
                return
            connection.execute(
                """
                UPDATE tasks SET reconciliation_state=?, reconciliation_reason=?,
                    updated_at=? WHERE task_id=?
                """,
                (
                    ReconciliationState.RESOLVED.value,
                    reason,
                    utc_now(),
                    task_id,
                ),
            )

    def resolve_lost_attempt(self, task_id: str, attempt_id: str, reason: str) -> None:
        now = utc_now()
        with self._transaction() as connection:
            task = self._require_task_row_by_id(connection, task_id)
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if attempt is None or attempt["task_id"] != task_id:
                raise FormalTaskViolation(
                    "ATTEMPT_SCOPE_MISMATCH",
                    "reconciliation attempt does not belong to task",
                    ErrorCode.PERMISSION_DENIED,
                )
            if task["state"] == FormalTaskState.TERMINAL.value:
                return
            connection.execute(
                """
                UPDATE attempts SET state=?, outcome=?, updated_at=?
                WHERE attempt_id=?
                """,
                (
                    FormalAttemptState.TERMINAL.value,
                    TerminalOutcome.INTERRUPTED.value,
                    now,
                    attempt_id,
                ),
            )
            self._append_event(
                connection,
                task,
                event_type="attempt.terminal",
                state=FormalAttemptState.TERMINAL.value,
                outcome=TerminalOutcome.INTERRUPTED.value,
                producer="task_core.reconciliation",
                source_event_id=None,
                causation_id=f"reconciliation:{attempt_id}",
                occurred_at=now,
                details={"reason": reason},
            )
            self._append_event(
                connection,
                self._require_task_row_by_id(connection, task_id),
                event_type="task.terminal",
                state=FormalTaskState.TERMINAL.value,
                outcome=TerminalOutcome.INTERRUPTED.value,
                producer="task_core.reconciliation",
                source_event_id=None,
                causation_id=f"reconciliation:{attempt_id}",
                occurred_at=now,
                details={"reason": reason},
                update_task=True,
            )
            connection.execute(
                """
                UPDATE outbox SET state=?, last_error=?, updated_at=?
                WHERE task_id=? AND state=?
                """,
                (
                    OutboxState.SUPPRESSED.value,
                    "EXECUTOR_ATTEMPT_LOST",
                    now,
                    task_id,
                    OutboxState.PENDING.value,
                ),
            )

    def get_task(self, task_id: str, scope: ScopeRef) -> PersistentTaskRecord:
        with self._reader() as connection:
            return self._task_from_row(
                self._require_task_row(connection, task_id, scope)
            )

    def list_tasks(self, scope: ScopeRef) -> tuple[PersistentTaskRecord, ...]:
        with self._reader() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE scope_key=? ORDER BY created_at, task_id",
                (_scope_key(scope),),
            ).fetchall()
            return tuple(self._task_from_row(row) for row in rows)

    def get_attempt(self, attempt_id: str) -> PersistentAttemptRecord:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "ATTEMPT_NOT_FOUND",
                    "attempt is unavailable",
                    ErrorCode.NOT_FOUND,
                )
            return self._attempt_from_row(row)

    def events(
        self, task_id: str, scope: ScopeRef, *, after_seq: int = -1
    ) -> tuple[PersistentTaskEvent, ...]:
        if type(after_seq) is not int or after_seq < -1:
            raise FormalTaskViolation(
                "INVALID_EVENT_CURSOR",
                "after_seq must be an integer at least -1",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._reader() as connection:
            self._require_task_row(connection, task_id, scope)
            rows = connection.execute(
                """
                SELECT * FROM task_events WHERE task_id=? AND seq>?
                ORDER BY seq
                """,
                (task_id, after_seq),
            ).fetchall()
            return tuple(self._event_from_row(row) for row in rows)

    def nonterminal_attempts(
        self,
    ) -> tuple[tuple[PersistentTaskRecord, PersistentAttemptRecord], ...]:
        with self._reader() as connection:
            rows = connection.execute(
                """
                SELECT t.*, a.attempt_id AS a_attempt_id, a.task_id AS a_task_id,
                    a.executor_id AS a_executor_id, a.executor_ref AS a_executor_ref,
                    a.state AS a_state, a.outcome AS a_outcome,
                    a.source_seq AS a_source_seq, a.updated_at AS a_updated_at
                FROM tasks t JOIN attempts a ON a.attempt_id=t.attempt_id
                WHERE t.state<>? ORDER BY t.created_at, t.task_id
                """,
                (FormalTaskState.TERMINAL.value,),
            ).fetchall()
            result = []
            for row in rows:
                attempt = PersistentAttemptRecord(
                    row["a_attempt_id"],
                    row["a_task_id"],
                    row["a_executor_id"],
                    row["a_executor_ref"],
                    FormalAttemptState(row["a_state"]),
                    (
                        None
                        if row["a_outcome"] is None
                        else TerminalOutcome(row["a_outcome"])
                    ),
                    int(row["a_source_seq"]),
                )
                result.append((self._task_from_row(row), attempt))
            return tuple(result)

    def counts(self) -> dict[str, int]:
        with self._reader() as connection:
            return {
                table: int(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in (
                    "commands",
                    "tasks",
                    "attempts",
                    "task_events",
                    "executor_events",
                    "outbox",
                )
            }

    @staticmethod
    def _require_task_row(
        connection: sqlite3.Connection, task_id: str, scope: ScopeRef
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM tasks WHERE task_id=? AND scope_key=?",
            (task_id, _scope_key(scope)),
        ).fetchone()
        if row is None:
            raise FormalTaskViolation(
                "TASK_NOT_FOUND",
                "task is unavailable in the authorized scope",
                ErrorCode.NOT_FOUND,
            )
        return row

    @staticmethod
    def _require_task_row_by_id(
        connection: sqlite3.Connection, task_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise FormalTaskViolation(
                "TASK_NOT_FOUND", "task is unavailable", ErrorCode.NOT_FOUND
            )
        return row

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> PersistentTaskRecord:
        def load() -> PersistentTaskRecord:
            reconciliation_state = row["reconciliation_state"]
            return PersistentTaskRecord(
                task_id=row["task_id"],
                scope=ScopeRef.from_dict(_json_load(row["scope_json"])),
                spec=FormalTaskSpec.from_dict(_json_load(row["spec_json"])),
                state=FormalTaskState(row["state"]),
                attempt_id=row["attempt_id"],
                correlation_id=row["correlation_id"],
                cancel_requested=bool(row["cancel_requested"]),
                dispatch_fenced=bool(row["dispatch_fenced"]),
                outcome=(
                    None if row["outcome"] is None else TerminalOutcome(row["outcome"])
                ),
                reconciliation_state=(
                    None
                    if reconciliation_state is None
                    else ReconciliationState(reconciliation_state)
                ),
                reconciliation_reason=row["reconciliation_reason"],
                event_head=int(row["event_head"]),
            )

        return _stored_record("task", load)

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> PersistentAttemptRecord:
        return _stored_record(
            "attempt",
            lambda: PersistentAttemptRecord(
                row["attempt_id"],
                row["task_id"],
                row["executor_id"],
                row["executor_ref"],
                FormalAttemptState(row["state"]),
                None if row["outcome"] is None else TerminalOutcome(row["outcome"]),
                int(row["source_seq"]),
            ),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> PersistentTaskEvent:
        def load() -> PersistentTaskEvent:
            details = _json_load(row["details_json"])
            if type(details) is not dict:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "formal Task Store contains invalid event details",
                    ErrorCode.INTERNAL,
                )
            return PersistentTaskEvent(
                event_id=row["event_id"],
                task_id=row["task_id"],
                attempt_id=row["attempt_id"],
                scope=ScopeRef.from_dict(_json_load(row["scope_json"])),
                seq=int(row["seq"]),
                event_type=row["event_type"],
                state=row["state"],
                outcome=row["outcome"],
                producer=row["producer"],
                source_event_id=row["source_event_id"],
                causation_id=row["causation_id"],
                correlation_id=row["correlation_id"],
                occurred_at=row["occurred_at"],
                details=details,
            )

        return _stored_record("event", load)

    @staticmethod
    def _outbox_from_row(row: sqlite3.Row) -> PersistentOutboxItem:
        def load() -> PersistentOutboxItem:
            payload = _json_load(row["payload_json"])
            if type(payload) is not dict:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "formal Task Store contains an invalid outbox payload",
                    ErrorCode.INTERNAL,
                )
            row_keys = set(row.keys())
            executor_ref = (
                row["bound_executor_ref"]
                if "bound_executor_ref" in row_keys
                else payload["executor_ref"]
            )
            source_seq = (
                int(row["bound_source_seq"]) if "bound_source_seq" in row_keys else -1
            )
            return PersistentOutboxItem(
                row["outbox_id"],
                OutboxKind(row["kind"]),
                row["task_id"],
                row["attempt_id"],
                row["command_id"],
                ScopeRef.from_dict(payload["scope"]),
                FormalTaskSpec.from_dict(payload["spec"]),
                executor_ref,
                source_seq,
                OutboxState(row["state"]),
                int(row["delivery_count"]),
                row["claim_token"],
            )

        return _stored_record("outbox", load)


__all__ = ["SqliteTaskStore"]
