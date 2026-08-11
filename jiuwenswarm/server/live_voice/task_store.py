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
    AppliedTaskRetryReplay,
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
    TaskEventAuthoritySnapshot,
    TaskMutationDisposition,
    TaskMutationResult,
    TaskRetryAuthoritySnapshot,
    TaskRetryPrecondition,
    TaskRetryProductRequestFingerprint,
    utc_now,
)

_SCHEMA_VERSION = 2
_TASK_STORE_TABLES = frozenset(
    {
        "metadata",
        "commands",
        "tasks",
        "attempts",
        "task_events",
        "executor_events",
        "outbox",
    }
)
_TASK_STORE_COLUMNS = {
    "metadata": ("key", "value"),
    "commands": (
        "command_id",
        "fingerprint",
        "command_type",
        "scope_key",
        "result_json",
        "created_at",
    ),
    "tasks": (
        "task_id",
        "scope_key",
        "scope_json",
        "spec_json",
        "state",
        "outcome",
        "attempt_id",
        "correlation_id",
        "cancel_requested",
        "dispatch_fenced",
        "event_head",
        "reconciliation_state",
        "reconciliation_reason",
        "created_at",
        "updated_at",
    ),
    "attempts": (
        "attempt_id",
        "task_id",
        "attempt_number",
        "executor_id",
        "executor_ref",
        "state",
        "outcome",
        "source_seq",
        "updated_at",
    ),
    "task_events": (
        "task_id",
        "seq",
        "event_id",
        "attempt_id",
        "scope_json",
        "event_type",
        "state",
        "outcome",
        "producer",
        "source_event_id",
        "causation_id",
        "correlation_id",
        "occurred_at",
        "details_json",
    ),
    "executor_events": (
        "source_event_id",
        "attempt_id",
        "source_seq",
        "canonical",
    ),
    "outbox": (
        "outbox_id",
        "kind",
        "task_id",
        "attempt_id",
        "command_id",
        "payload_json",
        "state",
        "delivery_count",
        "claimed_by",
        "claimed_at",
        "claim_token",
        "last_error",
        "created_at",
        "updated_at",
    ),
}
_TASK_STORE_NOT_NULL = {
    "metadata": frozenset({"value"}),
    "commands": frozenset(_TASK_STORE_COLUMNS["commands"]),
    "tasks": frozenset(
        {
            "scope_key",
            "scope_json",
            "spec_json",
            "state",
            "attempt_id",
            "correlation_id",
            "cancel_requested",
            "dispatch_fenced",
            "event_head",
            "created_at",
            "updated_at",
        }
    ),
    "attempts": frozenset(
        {
            "task_id",
            "attempt_number",
            "executor_id",
            "state",
            "source_seq",
            "updated_at",
        }
    ),
    "task_events": frozenset(
        {
            "task_id",
            "seq",
            "event_id",
            "attempt_id",
            "scope_json",
            "event_type",
            "state",
            "producer",
            "causation_id",
            "correlation_id",
            "occurred_at",
            "details_json",
        }
    ),
    "executor_events": frozenset({"attempt_id", "source_seq", "canonical"}),
    "outbox": frozenset(
        {
            "kind",
            "task_id",
            "attempt_id",
            "command_id",
            "payload_json",
            "state",
            "delivery_count",
            "created_at",
            "updated_at",
        }
    ),
}
_TASK_STORE_PRIMARY_KEYS = {
    "metadata": ("key",),
    "commands": ("scope_key", "command_id"),
    "tasks": ("task_id",),
    "attempts": ("attempt_id",),
    "task_events": ("task_id", "seq"),
    "executor_events": ("source_event_id",),
    "outbox": ("outbox_id",),
}
_TASK_STORE_INTEGER_COLUMNS = frozenset(
    {
        ("tasks", "cancel_requested"),
        ("tasks", "dispatch_fenced"),
        ("tasks", "event_head"),
        ("attempts", "attempt_number"),
        ("attempts", "source_seq"),
        ("task_events", "seq"),
        ("executor_events", "source_seq"),
        ("outbox", "delivery_count"),
    }
)
_TASK_STORE_BLOB_COLUMNS = frozenset(
    {("commands", "fingerprint"), ("executor_events", "canonical")}
)
_TASK_STORE_DEFAULTS = {
    ("tasks", "cancel_requested"): "0",
    ("tasks", "dispatch_fenced"): "0",
    ("attempts", "source_seq"): "-1",
    ("outbox", "delivery_count"): "0",
}
_TASK_STORE_NAMED_INDEXES = {
    "idx_tasks_scope": ("tasks", ("scope_key", "task_id")),
    "idx_tasks_state": ("tasks", ("state", "task_id")),
    "idx_outbox_pending": ("outbox", ("state", "created_at", "outbox_id")),
}
_TASK_STORE_UNIQUE_KEYS_V2 = {
    "metadata": frozenset({("key",)}),
    "commands": frozenset({("scope_key", "command_id")}),
    "tasks": frozenset({("task_id",), ("attempt_id",)}),
    "attempts": frozenset({("attempt_id",), ("task_id", "attempt_number")}),
    "task_events": frozenset({("task_id", "seq"), ("event_id",)}),
    "executor_events": frozenset({("source_event_id",), ("attempt_id", "source_seq")}),
    "outbox": frozenset({("outbox_id",)}),
}
_TASK_STORE_FOREIGN_KEYS = {
    "metadata": frozenset(),
    "commands": frozenset(),
    "tasks": frozenset(),
    "attempts": frozenset({("task_id", "tasks", "task_id", "CASCADE")}),
    "task_events": frozenset({("task_id", "tasks", "task_id", "CASCADE")}),
    "executor_events": frozenset({("attempt_id", "attempts", "attempt_id", "CASCADE")}),
    "outbox": frozenset(
        {
            ("task_id", "tasks", "task_id", "CASCADE"),
            ("attempt_id", "attempts", "attempt_id", "CASCADE"),
        }
    ),
}
_StoredRecordT = TypeVar("_StoredRecordT")
_OUTBOX_BINDING_SELECT = """
    SELECT o.*, a.attempt_id AS canonical_attempt_id,
           a.task_id AS attempt_task_id,
           a.executor_ref AS bound_executor_ref,
           a.attempt_number AS bound_attempt_number,
           a.source_seq AS bound_source_seq,
           a.executor_id AS bound_executor_id,
           a.state AS bound_attempt_state,
           a.outcome AS bound_attempt_outcome,
           pa.attempt_id AS predecessor_attempt_id,
           pa.task_id AS predecessor_task_id,
           pa.attempt_number AS predecessor_attempt_number,
           pa.state AS predecessor_attempt_state,
           pa.outcome AS predecessor_attempt_outcome,
           t.task_id AS canonical_task_id,
           t.attempt_id AS task_attempt_id,
           t.scope_key AS task_scope_key,
           t.scope_json AS task_scope_json,
           t.spec_json AS task_spec_json,
           t.state AS bound_task_state,
           t.outcome AS bound_task_outcome,
           t.correlation_id AS task_correlation_id,
           t.event_head AS task_event_head,
           t.cancel_requested AS task_cancel_requested,
           t.dispatch_fenced AS task_dispatch_fenced,
           c.command_id AS canonical_command_id,
           c.command_type AS bound_command_type,
           c.scope_key AS command_scope_key,
           c.fingerprint AS command_fingerprint,
           c.result_json AS command_result_json,
           ce.event_id AS cancel_event_id,
           ce.task_id AS cancel_event_task_id,
           ce.attempt_id AS cancel_event_attempt_id,
           ce.scope_json AS cancel_event_scope_json,
           ce.event_type AS cancel_event_type,
           ce.state AS cancel_event_state,
           ce.outcome AS cancel_event_outcome,
           ce.producer AS cancel_event_producer,
           ce.source_event_id AS cancel_event_source_event_id,
           ce.causation_id AS cancel_event_causation_id,
           ce.correlation_id AS cancel_event_correlation_id,
           ce.occurred_at AS cancel_event_occurred_at,
           ce.details_json AS cancel_event_details_json,
           ce.seq AS cancel_event_seq,
           re.event_id AS retry_event_id,
           re.task_id AS retry_event_task_id,
           re.attempt_id AS retry_event_attempt_id,
           re.scope_json AS retry_event_scope_json,
           re.event_type AS retry_event_type,
           re.state AS retry_event_state,
           re.outcome AS retry_event_outcome,
           re.producer AS retry_event_producer,
           re.source_event_id AS retry_event_source_event_id,
           re.causation_id AS retry_event_causation_id,
           re.correlation_id AS retry_event_correlation_id,
           re.occurred_at AS retry_event_occurred_at,
           re.details_json AS retry_event_details_json,
           re.seq AS retry_event_seq,
           (
             SELECT COUNT(*) FROM task_events AS ce_count
             WHERE ce_count.task_id=o.task_id
               AND ce_count.attempt_id=o.attempt_id
               AND ce_count.event_type='task.cancel_requested'
               AND ce_count.causation_id=o.command_id
           ) AS cancel_event_count
           ,(
             SELECT COUNT(*) FROM task_events AS re_count
             WHERE re_count.task_id=o.task_id
               AND re_count.attempt_id=o.attempt_id
               AND re_count.event_type='task.retry_accepted'
               AND re_count.causation_id=o.command_id
           ) AS retry_event_count
           ,(
             SELECT MIN(re_start.seq) FROM task_events AS re_start
             WHERE re_start.task_id=o.task_id
               AND re_start.attempt_id=o.attempt_id
           ) AS retry_segment_start_seq
    FROM outbox AS o
    LEFT JOIN attempts AS a ON a.attempt_id=o.attempt_id
    LEFT JOIN attempts AS pa
      ON pa.task_id=o.task_id AND pa.attempt_number=a.attempt_number-1
    LEFT JOIN tasks AS t ON t.task_id=o.task_id
    LEFT JOIN commands AS c
      ON c.command_id=o.command_id AND c.scope_key=t.scope_key
    LEFT JOIN task_events AS ce
      ON ce.task_id=o.task_id
     AND ce.attempt_id=o.attempt_id
     AND ce.event_type='task.cancel_requested'
     AND ce.causation_id=o.command_id
    LEFT JOIN task_events AS re
      ON re.task_id=o.task_id
     AND re.attempt_id=o.attempt_id
     AND re.event_type='task.retry_accepted'
     AND re.causation_id=o.command_id
"""


def _json_dump(value: object) -> str:
    canonical_json_bytes(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(value: str | bytes) -> object:
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
    except FormalTaskViolation as error:
        if error.reason == "TASK_STORE_CORRUPT":
            raise
        raise FormalTaskViolation(
            "TASK_STORE_CORRUPT",
            f"formal Task Store contains an invalid {record_kind} record",
            ErrorCode.INTERNAL,
        ) from error
    except (ContractViolation, KeyError, OverflowError, TypeError, ValueError) as error:
        raise FormalTaskViolation(
            "TASK_STORE_CORRUPT",
            f"formal Task Store contains an invalid {record_kind} record",
            ErrorCode.INTERNAL,
        ) from error


def _task_binding_from_row(row: sqlite3.Row) -> tuple[ScopeRef, FormalTaskSpec]:
    def load() -> tuple[ScopeRef, FormalTaskSpec]:
        scope = ScopeRef.from_dict(_json_load(row["scope_json"]))
        spec = FormalTaskSpec.from_dict(_json_load(row["spec_json"]))
        if row["scope_key"] != _scope_key(scope) or spec.context.scope != scope:
            raise FormalTaskViolation(
                "TASK_SCOPE_BINDING_MISMATCH",
                "task scope key or context does not match its canonical scope",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        return scope, spec

    return _stored_record("task", load)


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

    def _connect(self, *, foreign_keys: bool = True) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=10,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute(
                f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}"
            )
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
        connection = self._connect(foreign_keys=False)
        try:
            connection.execute("BEGIN EXCLUSIVE")
            tables = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchall()
            }
            task_store_tables = tables & _TASK_STORE_TABLES
            if not task_store_tables:
                self._create_schema_v2(connection)
                self._verify_schema_structure(connection, version=2)
                self._verify_database(connection)
                self._hit("initialize.bootstrap.before_metadata")
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    (str(_SCHEMA_VERSION),),
                )
            else:
                if "metadata" not in task_store_tables:
                    raise FormalTaskViolation(
                        "TASK_STORE_SCHEMA_UNSUPPORTED",
                        "formal task Store has tables but no schema authority",
                        ErrorCode.UNSUPPORTED,
                    )
                self._verify_metadata_schema(connection)
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()
                if row is None:
                    raise FormalTaskViolation(
                        "TASK_STORE_SCHEMA_UNSUPPORTED",
                        "formal task Store schema version is unavailable",
                        ErrorCode.UNSUPPORTED,
                    )
                try:
                    version = int(row["value"])
                except (TypeError, ValueError) as error:
                    raise FormalTaskViolation(
                        "TASK_STORE_SCHEMA_UNSUPPORTED",
                        "formal task Store schema version is unsupported",
                        ErrorCode.UNSUPPORTED,
                    ) from error
                if version == 1:
                    self._verify_schema_structure(connection, version=1)
                    self._migrate_v1_to_v2(connection)
                elif version == _SCHEMA_VERSION:
                    self._verify_schema_structure(connection, version=2)
                    self._verify_database(connection)
                else:
                    raise FormalTaskViolation(
                        "TASK_STORE_SCHEMA_UNSUPPORTED",
                        "formal task Store schema version is unsupported",
                        ErrorCode.UNSUPPORTED,
                    )
            connection.commit()
        except sqlite3.Error as exc:
            try:
                connection.rollback()
            except BaseException:  # noqa: BLE001 -- preserve the stable primary error
                pass
            raise FormalTaskViolation(
                "TASK_STORE_UNAVAILABLE",
                "formal Task Store schema cannot be initialized",
                ErrorCode.UNAVAILABLE,
            ) from exc
        except BaseException:
            try:
                connection.rollback()
            except BaseException:  # noqa: BLE001 -- rollback cannot replace authority truth
                pass
            raise
        finally:
            connection.close()

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

    @staticmethod
    def _schema_unsupported(message: str) -> FormalTaskViolation:
        return FormalTaskViolation(
            "TASK_STORE_SCHEMA_UNSUPPORTED",
            message,
            ErrorCode.UNSUPPORTED,
        )

    @classmethod
    def _verify_metadata_schema(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(metadata)").fetchall()
        if tuple(row["name"] for row in rows) != _TASK_STORE_COLUMNS["metadata"]:
            raise cls._schema_unsupported(
                "formal task Store metadata schema is unsupported"
            )
        if tuple(row["type"].upper() for row in rows) != ("TEXT", "TEXT"):
            raise cls._schema_unsupported(
                "formal task Store metadata schema is unsupported"
            )
        if {row["name"] for row in rows if bool(row["notnull"])} != (
            _TASK_STORE_NOT_NULL["metadata"]
        ):
            raise cls._schema_unsupported(
                "formal task Store metadata schema is unsupported"
            )
        primary_key = tuple(
            row["name"]
            for row in sorted(rows, key=lambda item: item["pk"])
            if row["pk"]
        )
        if primary_key != _TASK_STORE_PRIMARY_KEYS["metadata"]:
            raise cls._schema_unsupported(
                "formal task Store metadata schema is unsupported"
            )

    @classmethod
    def _verify_schema_structure(
        cls, connection: sqlite3.Connection, *, version: int
    ) -> None:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        }
        if not _TASK_STORE_TABLES.issubset(tables):
            raise cls._schema_unsupported(
                "formal task Store schema is missing required tables"
            )

        unique_keys = dict(_TASK_STORE_UNIQUE_KEYS_V2)
        if version == 1:
            unique_keys["attempts"] = frozenset({("attempt_id",), ("task_id",)})
        for table in sorted(_TASK_STORE_TABLES):
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
            expected_columns = _TASK_STORE_COLUMNS[table]
            if version == 1 and table == "attempts":
                expected_columns = tuple(
                    column for column in expected_columns if column != "attempt_number"
                )
            if tuple(row["name"] for row in rows) != expected_columns:
                raise cls._schema_unsupported(
                    f"formal task Store {table} columns are unsupported"
                )
            for row in rows:
                column = row["name"]
                expected_type = (
                    "INTEGER"
                    if (table, column) in _TASK_STORE_INTEGER_COLUMNS
                    else "BLOB"
                    if (table, column) in _TASK_STORE_BLOB_COLUMNS
                    else "TEXT"
                )
                if row["type"].upper() != expected_type:
                    raise cls._schema_unsupported(
                        f"formal task Store {table} column types are unsupported"
                    )
                expected_default = _TASK_STORE_DEFAULTS.get((table, column))
                actual_default = row["dflt_value"]
                if actual_default != expected_default:
                    raise cls._schema_unsupported(
                        f"formal task Store {table} defaults are unsupported"
                    )
            expected_not_null = _TASK_STORE_NOT_NULL[table]
            if version == 1 and table == "attempts":
                expected_not_null = expected_not_null - {"attempt_number"}
            if {
                row["name"] for row in rows if bool(row["notnull"])
            } != expected_not_null:
                raise cls._schema_unsupported(
                    f"formal task Store {table} nullability is unsupported"
                )
            primary_key = tuple(
                row["name"]
                for row in sorted(rows, key=lambda item: item["pk"])
                if row["pk"]
            )
            if primary_key != _TASK_STORE_PRIMARY_KEYS[table]:
                raise cls._schema_unsupported(
                    f"formal task Store {table} primary key is unsupported"
                )

            actual_unique_keys: set[tuple[str, ...]] = set()
            for index in connection.execute(f"PRAGMA index_list({table})").fetchall():
                if not bool(index["unique"]):
                    continue
                columns = tuple(
                    row["name"]
                    for row in connection.execute(
                        f"PRAGMA index_info({index['name']})"
                    ).fetchall()
                )
                actual_unique_keys.add(columns)
            if actual_unique_keys != unique_keys[table]:
                raise cls._schema_unsupported(
                    f"formal task Store {table} uniqueness is unsupported"
                )

            actual_foreign_keys = frozenset(
                (
                    row["from"],
                    row["table"],
                    row["to"],
                    row["on_delete"].upper(),
                )
                for row in connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
            )
            if actual_foreign_keys != _TASK_STORE_FOREIGN_KEYS[table]:
                raise cls._schema_unsupported(
                    f"formal task Store {table} foreign keys are unsupported"
                )

        for index_name, (table, expected_columns) in _TASK_STORE_NAMED_INDEXES.items():
            indexes = {
                row["name"]: row
                for row in connection.execute(f"PRAGMA index_list({table})").fetchall()
            }
            index = indexes.get(index_name)
            if index is None or bool(index["unique"]) or bool(index["partial"]):
                raise cls._schema_unsupported(
                    f"formal task Store index {index_name} is unsupported"
                )
            columns = tuple(
                row["name"]
                for row in connection.execute(
                    f"PRAGMA index_info({index_name})"
                ).fetchall()
            )
            if columns != expected_columns:
                raise cls._schema_unsupported(
                    f"formal task Store index {index_name} is unsupported"
                )

        if version == 2:
            attempt_sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='attempts'"
            ).fetchone()
            attempt_sql = "" if attempt_sql_row is None else attempt_sql_row["sql"]
            normalized = "".join(str(attempt_sql).upper().split())
            if "CHECK(ATTEMPT_NUMBERBETWEEN1AND3)" not in normalized:
                raise cls._schema_unsupported(
                    "formal task Store attempt bounds are unsupported"
                )

    @staticmethod
    def _create_schema_v2(connection: sqlite3.Connection) -> None:
        statements = (
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
            """CREATE TABLE commands (
                command_id TEXT NOT NULL, fingerprint BLOB NOT NULL,
                command_type TEXT NOT NULL, scope_key TEXT NOT NULL,
                result_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(scope_key, command_id))""",
            """CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY, scope_key TEXT NOT NULL,
                scope_json TEXT NOT NULL, spec_json TEXT NOT NULL,
                state TEXT NOT NULL, outcome TEXT,
                attempt_id TEXT NOT NULL UNIQUE, correlation_id TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                dispatch_fenced INTEGER NOT NULL DEFAULT 0,
                event_head INTEGER NOT NULL, reconciliation_state TEXT,
                reconciliation_reason TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)""",
            "CREATE INDEX idx_tasks_scope ON tasks(scope_key, task_id)",
            "CREATE INDEX idx_tasks_state ON tasks(state, task_id)",
            """CREATE TABLE attempts (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
                executor_id TEXT NOT NULL, executor_ref TEXT,
                state TEXT NOT NULL, outcome TEXT,
                source_seq INTEGER NOT NULL DEFAULT -1, updated_at TEXT NOT NULL,
                UNIQUE(task_id, attempt_number))""",
            """CREATE TABLE task_events (
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                seq INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
                attempt_id TEXT NOT NULL, scope_json TEXT NOT NULL,
                event_type TEXT NOT NULL, state TEXT NOT NULL, outcome TEXT,
                producer TEXT NOT NULL, source_event_id TEXT,
                causation_id TEXT NOT NULL, correlation_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL, details_json TEXT NOT NULL,
                PRIMARY KEY(task_id, seq))""",
            """CREATE TABLE executor_events (
                source_event_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
                source_seq INTEGER NOT NULL, canonical BLOB NOT NULL,
                UNIQUE(attempt_id, source_seq))""",
            """CREATE TABLE outbox (
                outbox_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL, task_id TEXT NOT NULL
                    REFERENCES tasks(task_id) ON DELETE CASCADE,
                attempt_id TEXT NOT NULL
                    REFERENCES attempts(attempt_id) ON DELETE CASCADE,
                command_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                state TEXT NOT NULL, delivery_count INTEGER NOT NULL DEFAULT 0,
                claimed_by TEXT, claimed_at TEXT, claim_token TEXT,
                last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            "CREATE INDEX idx_outbox_pending ON outbox(state, created_at, outbox_id)",
        )
        for statement in statements:
            connection.execute(statement)

    def _migrate_v1_to_v2(self, connection: sqlite3.Connection) -> None:
        self._hit("migration.v1_to_v2.before_create")
        connection.execute(
            """CREATE TABLE attempts_v2 (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
                executor_id TEXT NOT NULL, executor_ref TEXT,
                state TEXT NOT NULL, outcome TEXT,
                source_seq INTEGER NOT NULL DEFAULT -1, updated_at TEXT NOT NULL,
                UNIQUE(task_id, attempt_number))"""
        )
        self._hit("migration.v1_to_v2.after_create")
        connection.execute(
            """INSERT INTO attempts_v2(
                attempt_id, task_id, attempt_number, executor_id, executor_ref,
                state, outcome, source_seq, updated_at)
                SELECT attempt_id, task_id, 1, executor_id, executor_ref,
                       state, outcome, source_seq, updated_at FROM attempts"""
        )
        self._hit("migration.v1_to_v2.after_copy")
        connection.execute("DROP TABLE attempts")
        self._hit("migration.v1_to_v2.after_drop")
        connection.execute("ALTER TABLE attempts_v2 RENAME TO attempts")
        self._hit("migration.v1_to_v2.after_rename")
        self._verify_schema_structure(connection, version=2)
        self._verify_database(connection)
        self._hit("migration.v1_to_v2.before_metadata")
        changed = connection.execute(
            "UPDATE metadata SET value=? WHERE key='schema_version' AND value='1'",
            (str(_SCHEMA_VERSION),),
        ).rowcount
        if changed != 1:
            raise FormalTaskViolation(
                "TASK_STORE_SCHEMA_UNSUPPORTED",
                "formal task Store schema changed during migration",
                ErrorCode.UNSUPPORTED,
            )

    @staticmethod
    def _verify_database(connection: sqlite3.Connection) -> None:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise FormalTaskViolation(
                "TASK_STORE_CORRUPT",
                "formal Task Store failed its integrity check",
                ErrorCode.INTERNAL,
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise FormalTaskViolation(
                "TASK_STORE_CORRUPT",
                "formal Task Store failed its foreign-key check",
                ErrorCode.INTERNAL,
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
                    attempt_id, task_id, attempt_number, executor_id, executor_ref,
                    state, outcome, source_seq, updated_at
                ) VALUES(?, ?, 1, ?, NULL, ?, NULL, -1, ?)
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
                WHERE task_id=? AND attempt_id=? AND kind=?
                ORDER BY created_at, outbox_id LIMIT 1
                """,
                (
                    task_id,
                    task["attempt_id"],
                    OutboxKind.ATTEMPT_DISPATCH.value,
                ),
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

    @staticmethod
    def _retry_fingerprint(command: CommandEnvelope) -> bytes:
        return command.fingerprint()

    def read_retry_authority(
        self,
        command: CommandEnvelope,
    ) -> ResultEnvelope | TaskRetryAuthoritySnapshot:
        """Return exact replay or one side-effect-free retry admission snapshot."""

        fingerprint = self._retry_fingerprint(command)
        with self._reader() as connection:
            connection.execute("BEGIN")
            replay = self._verified_retry_replay(connection, command, fingerprint)
            if replay is not None:
                return replay
            return self._retry_authority_from_connection(connection, command)

    def read_current_retry_authority(
        self,
        *,
        scope: ScopeRef,
        task_id: str,
    ) -> TaskRetryAuthoritySnapshot:
        """Derive the current retry payload without accepting client lineage."""

        if (
            not isinstance(scope, ScopeRef)
            or scope.assurance.value != "authenticated"
            or type(task_id) is not str
            or not task_id.strip()
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_AUTHORITY_FACTS_INVALID",
                "retry authority requires an authenticated scope and exact task id",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._reader() as connection:
            connection.execute("BEGIN")
            task, attempt = self._retry_state_from_connection(
                connection,
                scope=scope,
                task_id=task_id,
            )
            return self._current_retry_authority_from_state(
                connection,
                task=task,
                attempt=attempt,
            )

    def read_applied_retry_replay(
        self,
        *,
        scope: ScopeRef,
        command_id: str,
        task_id: str,
        product_request: TaskRetryProductRequestFingerprint,
    ) -> AppliedTaskRetryReplay | None:
        """Resolve an applied retry from product-owned identity only.

        The original canonical command, including its server-derived predecessor
        payload, is reconstructed from the durable ledger.  Callers never submit
        that payload back to the Store to prove an applied replay.
        """

        if (
            not isinstance(scope, ScopeRef)
            or scope.assurance.value != "authenticated"
            or type(command_id) is not str
            or not command_id.strip()
            or type(task_id) is not str
            or not task_id.strip()
            or type(product_request) is not TaskRetryProductRequestFingerprint
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_REPLAY_FACTS_INVALID",
                "applied retry lookup requires exact authenticated product facts",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._reader() as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT * FROM commands WHERE scope_key=? AND command_id=?
                """,
                (_scope_key(scope), command_id),
            ).fetchone()
            if row is None:
                return None
            original_command, original_result, resolved_spec = (
                self._command_ledger_from_row(row)
            )
            if (
                row["command_type"] != "task.retry"
                or original_command.command_type != "task.retry"
                or original_command.command_id != command_id
                or original_command.scope != scope
                or original_command.target_ref.kind.value != "task"
                or original_command.target_ref.id != task_id
            ):
                raise FormalTaskViolation(
                    "IDEMPOTENCY_CONFLICT",
                    "command_id is already bound to different task facts",
                    ErrorCode.CONFLICT,
                )
            try:
                stored_product_request = (
                    TaskRetryProductRequestFingerprint.from_extensions(
                        original_command.extensions
                    )
                )
            except FormalTaskViolation as error:
                raise self._corrupt(
                    "applied retry command lacks its product request identity"
                ) from error
            if stored_product_request != product_request:
                raise FormalTaskViolation(
                    "IDEMPOTENCY_CONFLICT",
                    "command_id is already bound to different product request facts",
                    ErrorCode.CONFLICT,
                )
            task_row = self._require_task_row(connection, task_id, scope)
            self._verify_durable_lineage(connection, task_row)
            if resolved_spec is not None:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "retry command ledger contains create-only specification facts",
                    ErrorCode.INTERNAL,
                )
            result = original_result.result
            if result is None or result.get("task_id") != task_id:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "retry command result does not bind the requested task",
                    ErrorCode.INTERNAL,
                )
            attempt_id = result.get("attempt_id")
            if type(attempt_id) is not str:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "retry command result has no successor attempt",
                    ErrorCode.INTERNAL,
                )
            outbox_row = connection.execute(
                """
                SELECT payload_json FROM outbox
                WHERE outbox_id=? AND task_id=? AND attempt_id=? AND command_id=?
                  AND kind=?
                """,
                (
                    result.get("outbox_id"),
                    task_id,
                    attempt_id,
                    command_id,
                    OutboxKind.ATTEMPT_DISPATCH.value,
                ),
            ).fetchone()
            if outbox_row is None:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "retry command is missing its durable dispatch",
                    ErrorCode.INTERNAL,
                )
            payload = self._outbox_payload(outbox_row["payload_json"])
            precondition = TaskRetryPrecondition.from_payload(original_command.payload)
            return AppliedTaskRetryReplay(
                original_command=original_command,
                original_result=original_result,
                precondition=precondition,
                resulting_spec=payload[1],
            )

    def retry(
        self,
        command: CommandEnvelope,
        spec: FormalTaskSpec,
        authority: TaskRetryAuthoritySnapshot,
        *,
        observed_at: str,
    ) -> ResultEnvelope:
        """Atomically create one bounded successor attempt after exact re-CAS."""

        fingerprint = self._retry_fingerprint(command)
        scope_key = _scope_key(command.scope)
        with self._transaction() as connection:
            replay = self._verified_retry_replay(connection, command, fingerprint)
            if replay is not None:
                return replay
            current = self._retry_authority_from_connection(connection, command)
            if current != authority:
                raise FormalTaskViolation(
                    "TASK_RETRY_PRECONDITION_STALE",
                    "task retry authority changed before it could be applied",
                    ErrorCode.STALE,
                )
            prior_spec = current.task.spec
            if (
                spec.name,
                spec.instruction,
                spec.origin,
                spec.executor_id,
                spec.required_capabilities,
                spec.side_effect_class,
                spec.attributes,
            ) != (
                prior_spec.name,
                prior_spec.instruction,
                prior_spec.origin,
                prior_spec.executor_id,
                prior_spec.required_capabilities,
                prior_spec.side_effect_class,
                prior_spec.attributes,
            ):
                raise FormalTaskViolation(
                    "TASK_RETRY_SPEC_MISMATCH",
                    "task.retry cannot replace the stable task specification",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if (
                spec.context.source,
                spec.context.stable_id,
                spec.context.uri,
                spec.context.scope,
            ) != (
                prior_spec.context.source,
                prior_spec.context.stable_id,
                prior_spec.context.uri,
                prior_spec.context.scope,
            ):
                raise FormalTaskViolation(
                    "TASK_RETRY_CONTEXT_IDENTITY_MISMATCH",
                    "retry context must preserve the task's stable project identity",
                    ErrorCode.PERMISSION_DENIED,
                )
            self._hit("retry.before_ids")
            attempt_id = f"attempt-{uuid.uuid4().hex}"
            outbox_id = f"outbox-{uuid.uuid4().hex}"
            event_id = f"event-{uuid.uuid4().hex}"
            precondition = current.precondition
            task = current.task
            next_seq = task.event_head + 1
            now = observed_at
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, task_id, attempt_number, executor_id, executor_ref,
                    state, outcome, source_seq, updated_at
                ) VALUES(?, ?, ?, ?, NULL, ?, NULL, -1, ?)
                """,
                (
                    attempt_id,
                    task.task_id,
                    precondition.attempt_number,
                    spec.executor_id,
                    FormalAttemptState.ACCEPTED.value,
                    now,
                ),
            )
            self._hit("retry.after_attempt")
            self._insert_event(
                connection,
                event_id=event_id,
                task_id=task.task_id,
                attempt_id=attempt_id,
                scope=task.scope,
                seq=next_seq,
                event_type="task.retry_accepted",
                state=FormalTaskState.ACCEPTED.value,
                outcome=None,
                producer="task_core",
                source_event_id=None,
                causation_id=command.command_id,
                correlation_id=task.correlation_id,
                occurred_at=now,
                details={
                    "command_id": command.command_id,
                    "retry_of_attempt_id": precondition.previous_attempt_id,
                    "previous_outcome": precondition.previous_outcome.value,
                    "attempt_number": precondition.attempt_number,
                },
            )
            self._hit("retry.after_event")
            self._insert_outbox(
                connection,
                outbox_id=outbox_id,
                kind=OutboxKind.ATTEMPT_DISPATCH,
                task_id=task.task_id,
                attempt_id=attempt_id,
                command_id=command.command_id,
                scope=task.scope,
                spec=spec,
                now=now,
            )
            self._hit("retry.after_outbox")
            result = ResultEnvelope.success(
                owner=command,
                result={
                    "task_id": task.task_id,
                    "previous_attempt_id": precondition.previous_attempt_id,
                    "attempt_id": attempt_id,
                    "attempt_number": precondition.attempt_number,
                    "applied": True,
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
            self._hit("retry.after_command")
            changed = connection.execute(
                """
                UPDATE tasks SET spec_json=?, state=?, outcome=NULL,
                    attempt_id=?, cancel_requested=0, dispatch_fenced=0,
                    event_head=?, reconciliation_state=NULL,
                    reconciliation_reason=NULL, updated_at=?
                WHERE task_id=? AND attempt_id=? AND state=? AND outcome=?
                  AND event_head=?
                """,
                (
                    _json_dump(spec.to_dict()),
                    FormalTaskState.ACCEPTED.value,
                    attempt_id,
                    next_seq,
                    now,
                    task.task_id,
                    precondition.previous_attempt_id,
                    FormalTaskState.TERMINAL.value,
                    precondition.previous_outcome.value,
                    task.event_head,
                ),
            ).rowcount
            if changed != 1:
                raise FormalTaskViolation(
                    "TASK_RETRY_PRECONDITION_STALE",
                    "task retry predecessor changed before commit",
                    ErrorCode.STALE,
                )
            self._hit("retry.after_task")
            return result

    def _retry_authority_from_connection(
        self, connection: sqlite3.Connection, command: CommandEnvelope
    ) -> TaskRetryAuthoritySnapshot:
        if command.command_type != "task.retry":
            raise FormalTaskViolation(
                "INVALID_FORMAL_TASK_OPERATION",
                "retry authority requires task.retry",
                ErrorCode.INVALID_ARGUMENT,
            )
        TaskRetryProductRequestFingerprint.from_extensions(command.extensions)
        precondition = TaskRetryPrecondition.from_payload(command.payload)
        task, attempt = self._retry_state_from_connection(
            connection,
            scope=command.scope,
            task_id=command.target_ref.id,
        )
        if command.correlation_id != task.correlation_id:
            raise FormalTaskViolation(
                "TASK_RETRY_PRECONDITION_STALE",
                "task.retry correlation does not match the authoritative task",
                ErrorCode.STALE,
            )
        if (
            task.state is FormalTaskState.TERMINAL
            and attempt.state is FormalAttemptState.TERMINAL
            and attempt.attempt_number >= 3
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_LIMIT_EXCEEDED",
                "formal task permits at most three total attempts",
                ErrorCode.CONFLICT,
            )
        if (
            precondition.previous_attempt_id != attempt.attempt_id
            or precondition.attempt_number != attempt.attempt_number + 1
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_PRECONDITION_STALE",
                "task.retry lineage does not match the current attempt epoch",
                ErrorCode.STALE,
            )
        authority = self._current_retry_authority_from_state(
            connection,
            task=task,
            attempt=attempt,
        )
        if precondition != authority.precondition:
            raise FormalTaskViolation(
                "TASK_RETRY_PRECONDITION_STALE",
                "task.retry lineage does not match the current terminal attempt",
                ErrorCode.STALE,
            )
        return authority

    def _retry_state_from_connection(
        self,
        connection: sqlite3.Connection,
        *,
        scope: ScopeRef,
        task_id: str,
    ) -> tuple[PersistentTaskRecord, PersistentAttemptRecord]:
        task_row = self._require_task_row(connection, task_id, scope)
        self._verify_durable_lineage(connection, task_row)
        task = self._task_from_row(task_row)
        attempt_row = connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (task.attempt_id,)
        ).fetchone()
        if attempt_row is None:
            raise FormalTaskViolation(
                "TASK_STORE_CORRUPT",
                "formal Task Store is missing the current attempt",
                ErrorCode.INTERNAL,
            )
        return task, self._attempt_from_row(attempt_row)

    def _current_retry_authority_from_state(
        self,
        connection: sqlite3.Connection,
        *,
        task: PersistentTaskRecord,
        attempt: PersistentAttemptRecord,
    ) -> TaskRetryAuthoritySnapshot:
        if (
            task.state is FormalTaskState.TERMINAL
            and attempt.state is FormalAttemptState.TERMINAL
            and attempt.attempt_number >= 3
        ):
            raise FormalTaskViolation(
                "TASK_RETRY_LIMIT_EXCEEDED",
                "formal task permits at most three total attempts",
                ErrorCode.CONFLICT,
            )
        if task.state is not FormalTaskState.TERMINAL:
            raise FormalTaskViolation(
                "TASK_RETRY_REQUIRES_TERMINAL",
                "task.retry requires a terminal current attempt",
                ErrorCode.CONFLICT,
            )
        if attempt.state is not FormalAttemptState.TERMINAL:
            raise FormalTaskViolation(
                "TASK_STORE_CORRUPT",
                "terminal task does not have a terminal current attempt",
                ErrorCode.INTERNAL,
            )
        if task.outcome != attempt.outcome:
            raise FormalTaskViolation(
                "TASK_STORE_CORRUPT",
                "task and attempt terminal outcomes disagree",
                ErrorCode.INTERNAL,
            )
        if task.outcome not in {
            TerminalOutcome.CANCELLED,
            TerminalOutcome.COMPLETED,
        }:
            raise FormalTaskViolation(
                "TASK_RETRY_OUTCOME_NOT_ELIGIBLE",
                "only cancelled or completed attempts can be retried",
                ErrorCode.CONFLICT,
            )
        expected = TaskRetryPrecondition(
            previous_attempt_id=attempt.attempt_id,
            previous_outcome=task.outcome,
            attempt_number=attempt.attempt_number + 1,
        )
        unsettled = connection.execute(
            """
            SELECT 1 FROM outbox
            WHERE task_id=? AND attempt_id=? AND state IN (?, ?)
            LIMIT 1
            """,
            (
                task.task_id,
                attempt.attempt_id,
                OutboxState.PENDING.value,
                OutboxState.CLAIMED.value,
            ),
        ).fetchone()
        if unsettled is not None:
            raise FormalTaskViolation(
                "TASK_RETRY_OUTBOX_PENDING",
                "predecessor delivery ownership is not settled",
                ErrorCode.UNAVAILABLE,
            )
        if task.reconciliation_state not in {None, ReconciliationState.RESOLVED}:
            raise FormalTaskViolation(
                "TASK_RETRY_RECONCILIATION_PENDING",
                "predecessor reconciliation ownership is not settled",
                ErrorCode.UNAVAILABLE,
            )
        return TaskRetryAuthoritySnapshot(task, attempt, expected)

    @staticmethod
    def _corrupt(message: str) -> FormalTaskViolation:
        return FormalTaskViolation(
            "TASK_STORE_CORRUPT",
            message,
            ErrorCode.INTERNAL,
        )

    @classmethod
    def _command_ledger_from_row(
        cls, row: sqlite3.Row
    ) -> tuple[CommandEnvelope, ResultEnvelope, FormalTaskSpec | None]:
        def load() -> tuple[CommandEnvelope, ResultEnvelope, FormalTaskSpec | None]:
            result = ResultEnvelope.from_dict(_json_load(row["result_json"]))
            if not result.ok or result.command_id != row["command_id"]:
                raise cls._corrupt(
                    "formal Task command ledger contains a non-canonical result"
                )
            fingerprint_payload = _json_load(row["fingerprint"])
            resolved_spec: FormalTaskSpec | None = None
            if row["command_type"] == "task.create":
                if type(fingerprint_payload) is not dict or set(
                    fingerprint_payload
                ) != {"command", "resolved_spec"}:
                    raise cls._corrupt(
                        "task.create ledger fingerprint is not canonical"
                    )
                command_payload = fingerprint_payload["command"]
                resolved_spec = FormalTaskSpec.from_dict(
                    fingerprint_payload["resolved_spec"]
                )
            elif row["command_type"] == "task.retry":
                command_payload = fingerprint_payload
            else:
                raise cls._corrupt("attempt lineage references a non-admission command")
            if type(command_payload) is not dict or "request_id" in command_payload:
                raise cls._corrupt("formal Task command fingerprint is not canonical")
            canonical_command = dict(command_payload)
            canonical_command["request_id"] = result.request_id
            command = CommandEnvelope.from_dict(canonical_command)
            if (
                command.command_id != row["command_id"]
                or command.command_type != row["command_type"]
                or _scope_key(command.scope) != row["scope_key"]
            ):
                raise cls._corrupt("formal Task command ledger binding is inconsistent")
            expected_fingerprint = (
                canonical_json_bytes(
                    {
                        "command": json.loads(command.fingerprint()),
                        "resolved_spec": resolved_spec.to_dict(),
                    }
                )
                if resolved_spec is not None
                else command.fingerprint()
            )
            if expected_fingerprint != row["fingerprint"]:
                raise cls._corrupt(
                    "formal Task command ledger fingerprint is inconsistent"
                )
            return command, result, resolved_spec

        return _stored_record("command ledger", load)

    @classmethod
    def _outbox_payload(
        cls, payload_json: str | bytes
    ) -> tuple[ScopeRef, FormalTaskSpec, str | None]:
        def load() -> tuple[ScopeRef, FormalTaskSpec, str | None]:
            payload = _json_load(payload_json)
            if type(payload) is not dict or set(payload) != {
                "scope",
                "spec",
                "executor_ref",
            }:
                raise cls._corrupt("formal Task dispatch payload is not canonical")
            scope = ScopeRef.from_dict(payload["scope"])
            spec = FormalTaskSpec.from_dict(payload["spec"])
            executor_ref = payload["executor_ref"]
            if executor_ref is not None and type(executor_ref) is not str:
                raise cls._corrupt("formal Task dispatch executor_ref is invalid")
            if spec.context.scope != scope:
                raise cls._corrupt("formal Task dispatch context does not match scope")
            return scope, spec, executor_ref

        return _stored_record("outbox", load)

    @classmethod
    def _verify_durable_lineage(
        cls, connection: sqlite3.Connection, task_row: sqlite3.Row
    ) -> None:
        """Prove every attempt epoch from create through the current pointer."""

        try:
            task = cls._task_from_row(task_row)
            attempt_rows = connection.execute(
                """
                SELECT * FROM attempts WHERE task_id=?
                ORDER BY attempt_number, attempt_id
                """,
                (task.task_id,),
            ).fetchall()
            attempts = tuple(cls._attempt_from_row(row) for row in attempt_rows)
            if (
                not attempts
                or tuple(item.attempt_number for item in attempts)
                != tuple(range(1, len(attempts) + 1))
                or attempts[-1].attempt_id != task.attempt_id
                or len(attempts) > 3
            ):
                raise cls._corrupt(
                    "formal Task attempt ordinals are not one contiguous lineage"
                )
            attempts_by_id = {item.attempt_id: item for item in attempts}
            if len(attempts_by_id) != len(attempts):
                raise cls._corrupt("formal Task attempt lineage contains duplicates")

            event_rows = connection.execute(
                "SELECT * FROM task_events WHERE task_id=? ORDER BY seq",
                (task.task_id,),
            ).fetchall()
            events = tuple(cls._event_from_row(row) for row in event_rows)
            if len(events) != task.event_head + 1 or tuple(
                event.seq for event in events
            ) != tuple(range(task.event_head + 1)):
                raise cls._corrupt(
                    "formal Task event history is not one contiguous prefix"
                )
            for event in events:
                if (
                    event.task_id != task.task_id
                    or event.scope != task.scope
                    or event.correlation_id != task.correlation_id
                    or event.attempt_id not in attempts_by_id
                ):
                    raise cls._corrupt(
                        "formal Task event history crosses its durable authority"
                    )

            ordinal_stream = tuple(
                attempts_by_id[event.attempt_id].attempt_number for event in events
            )
            if ordinal_stream != tuple(sorted(ordinal_stream)):
                raise cls._corrupt(
                    "formal Task attempt segments are not monotonically ordered"
                )
            accepted_events = tuple(
                event for event in events if event.event_type == "task.accepted"
            )
            retry_events = tuple(
                event for event in events if event.event_type == "task.retry_accepted"
            )
            if len(accepted_events) != 1 or len(retry_events) != len(attempts) - 1:
                raise cls._corrupt(
                    "formal Task admission boundaries are incomplete or duplicated"
                )

            dispatch_specs: dict[int, FormalTaskSpec] = {}
            for ordinal, attempt in enumerate(attempts, 1):
                segment = tuple(
                    event for event in events if event.attempt_id == attempt.attempt_id
                )
                if not segment:
                    raise cls._corrupt(
                        "formal Task attempt has no durable event segment"
                    )
                boundary = segment[0]
                expected_boundary = (
                    "task.accepted" if ordinal == 1 else "task.retry_accepted"
                )
                if boundary.event_type != expected_boundary:
                    raise cls._corrupt(
                        "formal Task attempt segment lacks its admission boundary"
                    )
                if any(
                    event.event_type in {"task.accepted", "task.retry_accepted"}
                    for event in segment[1:]
                ):
                    raise cls._corrupt(
                        "formal Task attempt segment has duplicate admission boundaries"
                    )
                command_id = boundary.details.get("command_id")
                if (
                    type(command_id) is not str
                    or boundary.causation_id != command_id
                    or boundary.state != FormalTaskState.ACCEPTED.value
                    or boundary.outcome is not None
                    or boundary.producer != "task_core"
                    or boundary.source_event_id is not None
                ):
                    raise cls._corrupt(
                        "formal Task admission boundary is not canonical"
                    )
                command_rows = connection.execute(
                    """
                    SELECT * FROM commands WHERE scope_key=? AND command_id=?
                    """,
                    (_scope_key(task.scope), command_id),
                ).fetchall()
                dispatch_rows = connection.execute(
                    """
                    SELECT * FROM outbox
                    WHERE task_id=? AND attempt_id=? AND kind=?
                    """,
                    (
                        task.task_id,
                        attempt.attempt_id,
                        OutboxKind.ATTEMPT_DISPATCH.value,
                    ),
                ).fetchall()
                if len(command_rows) != 1 or len(dispatch_rows) != 1:
                    raise cls._corrupt(
                        "formal Task admission lacks one exact ledger and dispatch"
                    )
                command, result, resolved_spec = cls._command_ledger_from_row(
                    command_rows[0]
                )
                outbox_row = dispatch_rows[0]
                scope, dispatch_spec, executor_ref = cls._outbox_payload(
                    outbox_row["payload_json"]
                )
                try:
                    outbox_state = OutboxState(outbox_row["state"])
                    delivery_count = int(outbox_row["delivery_count"])
                except (TypeError, ValueError) as error:
                    raise cls._corrupt(
                        "formal Task dispatch lifecycle is invalid"
                    ) from error
                result_value = result.result
                if (
                    scope != task.scope
                    or dispatch_spec.executor_id != attempt.executor_id
                    or executor_ref is not None
                    or outbox_row["command_id"] != command_id
                    or delivery_count < 0
                    or (
                        outbox_state is OutboxState.CLAIMED
                        and (
                            outbox_row["claimed_by"] is None
                            or outbox_row["claimed_at"] is None
                            or outbox_row["claim_token"] is None
                        )
                    )
                    or (
                        outbox_state is not OutboxState.CLAIMED
                        and (
                            outbox_row["claimed_by"] is not None
                            or outbox_row["claimed_at"] is not None
                            or outbox_row["claim_token"] is not None
                        )
                    )
                    or command.scope != task.scope
                    or command.correlation_id != task.correlation_id
                    or command.required_capabilities != (command.command_type,)
                    or result_value is None
                    or result_value.get("task_id") != task.task_id
                    or result_value.get("attempt_id") != attempt.attempt_id
                    or result_value.get("outbox_id") != outbox_row["outbox_id"]
                    or result_value.get("state") != FormalTaskState.ACCEPTED.value
                ):
                    raise cls._corrupt(
                        "formal Task admission ledger does not bind its successor"
                    )
                dispatch_specs[ordinal] = dispatch_spec

                if ordinal == 1:
                    if (
                        boundary.seq != 0
                        or set(boundary.details) != {"command_id"}
                        or command.command_type != "task.create"
                        or command.target_ref.id != f"create:{command_id}"
                        or set(result_value)
                        != {
                            "task_id",
                            "attempt_id",
                            "state",
                            "outbox_id",
                        }
                        or resolved_spec != dispatch_spec
                        or resolved_spec is None
                        or resolved_spec.origin != command.origin
                        or resolved_spec.required_capabilities
                        != command.required_capabilities
                    ):
                        raise cls._corrupt(
                            "initial formal Task admission is not canonical"
                        )
                else:
                    predecessor = attempts[ordinal - 2]
                    unsettled_predecessor = connection.execute(
                        """
                        SELECT 1 FROM outbox
                        WHERE task_id=? AND attempt_id=? AND state IN (?, ?)
                        LIMIT 1
                        """,
                        (
                            task.task_id,
                            predecessor.attempt_id,
                            OutboxState.PENDING.value,
                            OutboxState.CLAIMED.value,
                        ),
                    ).fetchone()
                    if (
                        set(boundary.details)
                        != {
                            "command_id",
                            "retry_of_attempt_id",
                            "previous_outcome",
                            "attempt_number",
                        }
                        or command.command_type != "task.retry"
                        or command.target_ref.id != task.task_id
                        or resolved_spec is not None
                    ):
                        raise cls._corrupt(
                            "formal Task retry admission is not canonical"
                        )
                    prior_spec = dispatch_specs[ordinal - 1]
                    if (
                        dispatch_spec.name,
                        dispatch_spec.instruction,
                        dispatch_spec.origin,
                        dispatch_spec.executor_id,
                        dispatch_spec.required_capabilities,
                        dispatch_spec.side_effect_class,
                        dispatch_spec.attributes,
                    ) != (
                        prior_spec.name,
                        prior_spec.instruction,
                        prior_spec.origin,
                        prior_spec.executor_id,
                        prior_spec.required_capabilities,
                        prior_spec.side_effect_class,
                        prior_spec.attributes,
                    ) or (
                        dispatch_spec.context.source,
                        dispatch_spec.context.stable_id,
                        dispatch_spec.context.uri,
                        dispatch_spec.context.scope,
                    ) != (
                        prior_spec.context.source,
                        prior_spec.context.stable_id,
                        prior_spec.context.uri,
                        prior_spec.context.scope,
                    ):
                        raise cls._corrupt(
                            "formal Task retry changed stable specification identity"
                        )
                    TaskRetryProductRequestFingerprint.from_extensions(
                        command.extensions
                    )
                    precondition = TaskRetryPrecondition.from_payload(command.payload)
                    if (
                        boundary.details.get("retry_of_attempt_id")
                        != predecessor.attempt_id
                        or boundary.details.get("previous_outcome")
                        != (
                            None
                            if predecessor.outcome is None
                            else predecessor.outcome.value
                        )
                        or boundary.details.get("attempt_number") != ordinal
                        or precondition.previous_attempt_id != predecessor.attempt_id
                        or precondition.previous_outcome != predecessor.outcome
                        or precondition.attempt_number != ordinal
                        or predecessor.state is not FormalAttemptState.TERMINAL
                        or predecessor.outcome
                        not in {
                            TerminalOutcome.CANCELLED,
                            TerminalOutcome.COMPLETED,
                        }
                        or unsettled_predecessor is not None
                        or set(result_value)
                        != {
                            "task_id",
                            "previous_attempt_id",
                            "attempt_id",
                            "attempt_number",
                            "applied",
                            "state",
                            "outbox_id",
                        }
                        or result_value.get("previous_attempt_id")
                        != predecessor.attempt_id
                        or result_value.get("attempt_number") != ordinal
                        or result_value.get("applied") is not True
                    ):
                        raise cls._corrupt(
                            "formal Task retry lineage does not bind its predecessor"
                        )
                    predecessor_segment = tuple(
                        event
                        for event in events
                        if event.attempt_id == predecessor.attempt_id
                    )
                    terminal_events = tuple(
                        event
                        for event in predecessor_segment
                        if event.event_type == "task.terminal"
                    )
                    attempt_terminal_events = tuple(
                        event
                        for event in predecessor_segment
                        if event.event_type == "attempt.terminal"
                    )
                    if (
                        len(terminal_events) != 1
                        or len(attempt_terminal_events) != 1
                        or terminal_events[0].state != FormalTaskState.TERMINAL.value
                        or terminal_events[0].outcome != predecessor.outcome.value
                        or attempt_terminal_events[0].state
                        != FormalAttemptState.TERMINAL.value
                        or attempt_terminal_events[0].outcome
                        != predecessor.outcome.value
                    ):
                        raise cls._corrupt(
                            "formal Task retry predecessor lacks exact terminal truth"
                        )

                attempt_events = tuple(
                    event
                    for event in segment
                    if event.event_type.startswith("attempt.")
                )
                if attempt_events and (
                    attempt_events[-1].state != attempt.state.value
                    or attempt_events[-1].outcome
                    != (None if attempt.outcome is None else attempt.outcome.value)
                ):
                    raise cls._corrupt(
                        "formal Task attempt row disagrees with its event history"
                    )

            current_task_events = tuple(
                event
                for event in events
                if event.attempt_id == task.attempt_id
                and event.event_type
                in {
                    "task.accepted",
                    "task.retry_accepted",
                    "task.running",
                    "task.blocked",
                    "task.decision_required",
                    "task.terminal",
                }
            )
            if (
                not current_task_events
                or current_task_events[-1].state != task.state.value
                or current_task_events[-1].outcome
                != (None if task.outcome is None else task.outcome.value)
                or dispatch_specs[len(attempts)] != task.spec
            ):
                raise cls._corrupt(
                    "formal Task current pointer disagrees with its durable lineage"
                )
        except FormalTaskViolation as error:
            if error.reason == "TASK_STORE_CORRUPT":
                raise
            raise cls._corrupt(
                "formal Task durable attempt lineage is invalid"
            ) from error
        except (ContractViolation, KeyError, TypeError, ValueError) as error:
            raise cls._corrupt(
                "formal Task durable attempt lineage is invalid"
            ) from error

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

    def _verified_retry_replay(
        self,
        connection: sqlite3.Connection,
        command: CommandEnvelope,
        fingerprint: bytes,
    ) -> ResultEnvelope | None:
        replay = self._command_replay(connection, command, fingerprint)
        if replay is None:
            return None
        task_row = self._require_task_row(
            connection, command.target_ref.id, command.scope
        )
        self._verify_durable_lineage(connection, task_row)
        result = replay.result
        if result is None or result.get("task_id") != command.target_ref.id:
            raise self._corrupt("applied retry result does not bind its durable task")
        boundary = connection.execute(
            """
            SELECT 1 FROM task_events
            WHERE task_id=? AND attempt_id=? AND event_type='task.retry_accepted'
              AND causation_id=?
            """,
            (
                command.target_ref.id,
                result.get("attempt_id"),
                command.command_id,
            ),
        ).fetchall()
        if len(boundary) != 1:
            raise self._corrupt("applied retry result lacks one exact durable boundary")
        return replay

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
            candidates = connection.execute(
                _OUTBOX_BINDING_SELECT
                + """
                  WHERE o.state=?
                  ORDER BY o.updated_at, o.created_at, o.outbox_id
                """,
                (OutboxState.PENDING.value,),
            )
            row = None
            for candidate in candidates:
                item = self._outbox_from_row(candidate)
                if (
                    item.kind is OutboxKind.ATTEMPT_DISPATCH
                    or item.executor_ref is not None
                ):
                    row = candidate
                    break
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
                _OUTBOX_BINDING_SELECT + " WHERE o.outbox_id=?",
                (row["outbox_id"],),
            ).fetchone()
            if claimed is None:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "claimed formal Task outbox record vanished during reload",
                    ErrorCode.INTERNAL,
                )
            return self._outbox_from_row(claimed)

    def release_outbox(self, item: PersistentOutboxItem, error: str) -> bool:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT task_id, attempt_id FROM outbox WHERE outbox_id=?",
                (item.outbox_id,),
            ).fetchone()
            if (
                row is None
                or row["task_id"] != item.task_id
                or row["attempt_id"] != item.attempt_id
            ):
                raise FormalTaskViolation(
                    "OUTBOX_BINDING_MISMATCH",
                    "released outbox identity does not match its stored delivery",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            task = self._require_task_row_by_id(connection, item.task_id)
            if task["attempt_id"] != item.attempt_id:
                raise FormalTaskViolation(
                    "TASK_ATTEMPT_STALE",
                    "outbox release targets an old task attempt",
                    ErrorCode.STALE,
                )
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
            if task["attempt_id"] != item.attempt_id:
                raise FormalTaskViolation(
                    "TASK_ATTEMPT_STALE",
                    "outbox rejection targets an old task attempt",
                    ErrorCode.STALE,
                )
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
            task = self._require_task_row_by_id(connection, item.task_id)
            if task["attempt_id"] != item.attempt_id:
                raise FormalTaskViolation(
                    "TASK_ATTEMPT_STALE",
                    "outbox completion targets an old task attempt",
                    ErrorCode.STALE,
                )
            if attempt["executor_ref"] not in {None, executor_ref}:
                raise FormalTaskViolation(
                    "EXECUTOR_REFERENCE_CONFLICT",
                    "attempt cannot change its executor reference",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            now = utc_now()
            if item.kind is OutboxKind.ATTEMPT_DISPATCH:
                pending_cancels = connection.execute(
                    _OUTBOX_BINDING_SELECT
                    + " WHERE o.attempt_id=? AND o.kind=? AND o.state=?",
                    (
                        item.attempt_id,
                        OutboxKind.ATTEMPT_CANCEL.value,
                        OutboxState.PENDING.value,
                    ),
                ).fetchall()
                for cancel_row in pending_cancels:
                    cancel_item = self._outbox_from_row(cancel_row)
                    payload = {
                        "scope": cancel_item.scope.to_dict(),
                        "spec": cancel_item.spec.to_dict(),
                        "executor_ref": executor_ref,
                    }
                    changed = connection.execute(
                        """
                        UPDATE outbox SET payload_json=?, updated_at=?
                        WHERE outbox_id=? AND state=?
                        """,
                        (
                            _json_dump(payload),
                            now,
                            cancel_item.outbox_id,
                            OutboxState.PENDING.value,
                        ),
                    ).rowcount
                    if changed != 1:
                        raise FormalTaskViolation(
                            "TASK_STORE_CORRUPT",
                            "pending cancel outbox changed during Executor binding",
                            ErrorCode.INTERNAL,
                        )
            connection.execute(
                "UPDATE attempts SET executor_ref=?, updated_at=? WHERE attempt_id=?",
                (executor_ref, now, item.attempt_id),
            )
            for observation in observations:
                self._apply_observation(connection, observation)
            connection.execute(
                """
                UPDATE outbox SET state=?, claimed_by=NULL, claimed_at=NULL,
                    claim_token=NULL, last_error=NULL, updated_at=? WHERE outbox_id=?
                """,
                (OutboxState.DELIVERED.value, now, item.outbox_id),
            )

    def apply_observations(
        self, observations: tuple[ExecutorObservation, ...]
    ) -> TaskMutationResult:
        if not observations:
            raise FormalTaskViolation(
                "EXECUTOR_OBSERVATIONS_REQUIRED",
                "observation mutation requires at least one Executor fact",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._transaction() as connection:
            first = observations[0]
            for observation in observations:
                if (
                    observation.resolution is not ExecutorResolution.KNOWN
                    or observation.source_event_id is None
                    or observation.source_seq is None
                    or observation.attempt_state is None
                ):
                    raise FormalTaskViolation(
                        "EXECUTOR_EVENT_INCOMPLETE",
                        "known Executor mutation requires complete lifecycle facts",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                existing = connection.execute(
                    "SELECT canonical FROM executor_events WHERE source_event_id=?",
                    (observation.source_event_id,),
                ).fetchone()
                if existing is not None and existing[
                    "canonical"
                ] != canonical_json_bytes(observation.canonical_dict()):
                    raise FormalTaskViolation(
                        "EXECUTOR_EVENT_ID_CONFLICT",
                        "Executor event identity was reused with different facts",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
            if any(
                observation.task_id != first.task_id
                or observation.attempt_id != first.attempt_id
                or observation.executor_id != first.executor_id
                or observation.executor_ref != first.executor_ref
                for observation in observations
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_OBSERVATION_BINDING_MISMATCH",
                    "one observation mutation must bind one exact attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (first.attempt_id,)
            ).fetchone()
            if (
                attempt is None
                or attempt["task_id"] != first.task_id
                or attempt["executor_id"] != first.executor_id
                or attempt["executor_ref"] != first.executor_ref
            ):
                raise FormalTaskViolation(
                    "EXECUTOR_OBSERVATION_BINDING_MISMATCH",
                    "Executor observation does not bind the exact attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            task = self._require_task_row_by_id(connection, first.task_id)
            if task["attempt_id"] != first.attempt_id:
                return self._mutation_result(
                    connection,
                    attempt,
                    TaskMutationDisposition.SUPERSEDED,
                )
            appended: list[PersistentTaskEvent] = []
            for observation in observations:
                appended.extend(self._apply_observation(connection, observation))
            frozen_attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (first.attempt_id,)
            ).fetchone()
            assert frozen_attempt is not None
            return self._mutation_result(
                connection,
                frozen_attempt,
                (
                    TaskMutationDisposition.APPLIED
                    if appended
                    else TaskMutationDisposition.NOOP
                ),
                events=tuple(appended),
            )

    def _apply_observation(
        self, connection: sqlite3.Connection, observation: ExecutorObservation
    ) -> tuple[PersistentTaskEvent, ...]:
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
            return ()
        task = self._require_task_row_by_id(connection, observation.task_id)
        if task["attempt_id"] != observation.attempt_id:
            raise FormalTaskViolation(
                "TASK_ATTEMPT_STALE",
                "Executor observation targets an old task attempt",
                ErrorCode.STALE,
            )
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
        appended = [
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
        ]
        task = self._require_task_row_by_id(connection, observation.task_id)
        task_state = FormalTaskState(task["state"])
        if (
            target is FormalAttemptState.RUNNING
            and task_state is FormalTaskState.ACCEPTED
        ):
            appended.append(
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
            )
        elif target is FormalAttemptState.TERMINAL:
            assert observation.attempt_outcome is not None
            if task_state is FormalTaskState.TERMINAL:
                raise FormalTaskViolation(
                    "TASK_TERMINAL_CONFLICT",
                    "terminal task cannot accept a new Executor outcome",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            appended.append(
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
        return tuple(appended)

    @classmethod
    def _mutation_result(
        cls,
        connection: sqlite3.Connection,
        attempt_row: sqlite3.Row,
        disposition: TaskMutationDisposition,
        *,
        events: tuple[PersistentTaskEvent, ...] = (),
    ) -> TaskMutationResult:
        boundary = connection.execute(
            """
            SELECT MAX(seq) AS through_seq FROM task_events
            WHERE task_id=? AND attempt_id=?
            """,
            (attempt_row["task_id"], attempt_row["attempt_id"]),
        ).fetchone()
        if boundary is None or boundary["through_seq"] is None:
            raise cls._corrupt(
                "formal Task mutation target has no durable event segment"
            )
        return TaskMutationResult(
            disposition=disposition,
            task_id=attempt_row["task_id"],
            attempt=cls._attempt_from_row(attempt_row),
            through_seq=int(boundary["through_seq"]),
            events=events,
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
        self,
        task_id: str,
        attempt_id: str,
        reason: str,
        *,
        in_progress: bool = False,
    ) -> TaskMutationResult:
        state = (
            ReconciliationState.IN_PROGRESS
            if in_progress
            else ReconciliationState.PENDING
        )
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
            if task["attempt_id"] != attempt_id:
                return self._mutation_result(
                    connection,
                    attempt,
                    TaskMutationDisposition.SUPERSEDED,
                )
            if task["state"] == FormalTaskState.TERMINAL.value:
                return self._mutation_result(
                    connection, attempt, TaskMutationDisposition.NOOP
                )
            if (
                task["reconciliation_state"] == state.value
                and task["reconciliation_reason"] == reason
            ):
                return self._mutation_result(
                    connection, attempt, TaskMutationDisposition.NOOP
                )
            connection.execute(
                """
                UPDATE tasks SET reconciliation_state=?, reconciliation_reason=?,
                    updated_at=? WHERE task_id=?
                """,
                (state.value, reason, utc_now(), task_id),
            )
            return self._mutation_result(
                connection, attempt, TaskMutationDisposition.APPLIED
            )

    def mark_reconciliation_resolved(
        self, task_id: str, attempt_id: str, reason: str
    ) -> TaskMutationResult:
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
            if task["attempt_id"] != attempt_id:
                return self._mutation_result(
                    connection,
                    attempt,
                    TaskMutationDisposition.SUPERSEDED,
                )
            if task["state"] == FormalTaskState.TERMINAL.value:
                return self._mutation_result(
                    connection, attempt, TaskMutationDisposition.NOOP
                )
            if (
                task["reconciliation_state"] == ReconciliationState.RESOLVED.value
                and task["reconciliation_reason"] == reason
            ):
                return self._mutation_result(
                    connection, attempt, TaskMutationDisposition.NOOP
                )
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
            return self._mutation_result(
                connection, attempt, TaskMutationDisposition.APPLIED
            )

    def resolve_lost_attempt(
        self, task_id: str, attempt_id: str, reason: str
    ) -> TaskMutationResult:
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
            if task["attempt_id"] != attempt_id:
                return self._mutation_result(
                    connection,
                    attempt,
                    TaskMutationDisposition.SUPERSEDED,
                )
            if task["state"] == FormalTaskState.TERMINAL.value:
                return self._mutation_result(
                    connection, attempt, TaskMutationDisposition.NOOP
                )
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
            appended = [
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
            ]
            appended.append(
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
            frozen_attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            assert frozen_attempt is not None
            return self._mutation_result(
                connection,
                frozen_attempt,
                TaskMutationDisposition.APPLIED,
                events=tuple(appended),
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
        self,
        task_id: str,
        scope: ScopeRef,
        *,
        after_seq: int = -1,
        attempt_id: str | None = None,
    ) -> tuple[PersistentTaskEvent, ...]:
        if type(after_seq) is not int or after_seq < -1:
            raise FormalTaskViolation(
                "INVALID_EVENT_CURSOR",
                "after_seq must be an integer at least -1",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._reader() as connection:
            self._require_task_row(connection, task_id, scope)
            if attempt_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM task_events WHERE task_id=? AND seq>?
                    ORDER BY seq
                    """,
                    (task_id, after_seq),
                ).fetchall()
            else:
                attempt_row = connection.execute(
                    "SELECT task_id FROM attempts WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                if attempt_row is None or attempt_row["task_id"] != task_id:
                    raise FormalTaskViolation(
                        "TASK_ATTEMPT_STALE",
                        "event segment attempt does not belong to the task",
                        ErrorCode.STALE,
                    )
                rows = connection.execute(
                    """
                    SELECT * FROM task_events
                    WHERE task_id=? AND attempt_id=? AND seq>?
                    ORDER BY seq
                    """,
                    (task_id, attempt_id, after_seq),
                ).fetchall()
            return tuple(self._event_from_row(row) for row in rows)

    def event_authority_snapshot(
        self, task_id: str, scope: ScopeRef, *, max_events: int
    ) -> TaskEventAuthoritySnapshot:
        """Read task, attempt, and the exact durable prefix in one SQLite snapshot."""

        if type(max_events) is not int or max_events <= 0:
            raise FormalTaskViolation(
                "INVALID_TASK_EVENT_AUTHORITY_CAPACITY",
                "TaskEvent authority capacity must be a positive integer",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._reader() as connection:
            # The explicit read transaction pins every following SELECT to one
            # WAL snapshot. Concurrent appends are recovered later from cursor;
            # they can neither leak into nor create a hole inside this prefix.
            connection.execute("BEGIN")
            task_row = self._require_task_row(connection, task_id, scope)
            self._verify_durable_lineage(connection, task_row)
            task = self._task_from_row(task_row)
            attempt_row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (task.attempt_id,)
            ).fetchone()
            if attempt_row is None:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "formal Task Store is missing the bound attempt",
                    ErrorCode.INTERNAL,
                )
            attempt = self._attempt_from_row(attempt_row)
            boundary_row = connection.execute(
                """
                SELECT MIN(seq) AS start_seq FROM task_events
                WHERE task_id=? AND attempt_id=?
                """,
                (task.task_id, task.attempt_id),
            ).fetchone()
            if boundary_row is None or boundary_row["start_seq"] is None:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "formal Task Store is missing the current attempt segment",
                    ErrorCode.INTERNAL,
                )
            start_seq = int(boundary_row["start_seq"])
            if task.event_head - start_seq + 1 > max_events:
                raise FormalTaskViolation(
                    "TASK_EVENT_AUTHORITY_PREFIX_CAPACITY",
                    "TaskEvent authority segment exceeds the declared reader capacity",
                    ErrorCode.UNAVAILABLE,
                )
            self._hit("event_authority_snapshot.before_events")
            event_rows = connection.execute(
                """
                SELECT * FROM task_events
                WHERE task_id=? AND attempt_id=? AND seq>=? AND seq<=?
                ORDER BY seq
                """,
                (task.task_id, task.attempt_id, start_seq, task.event_head),
            ).fetchall()
            events = tuple(self._event_from_row(row) for row in event_rows)
            if attempt.attempt_number > 1:
                if not events or events[0].event_type != "task.retry_accepted":
                    raise FormalTaskViolation(
                        "TASK_STORE_CORRUPT",
                        "current retry segment lacks its durable authority boundary",
                        ErrorCode.INTERNAL,
                    )
                boundary = events[0]
                retry_of_attempt_id = boundary.details.get("retry_of_attempt_id")
                previous_outcome = boundary.details.get("previous_outcome")
                predecessor_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?",
                    (retry_of_attempt_id,),
                ).fetchone()
                if (
                    predecessor_row is None
                    or predecessor_row["task_id"] != task.task_id
                    or int(predecessor_row["attempt_number"])
                    != attempt.attempt_number - 1
                    or predecessor_row["state"] != FormalAttemptState.TERMINAL.value
                    or predecessor_row["outcome"] != previous_outcome
                    or previous_outcome
                    not in {
                        TerminalOutcome.CANCELLED.value,
                        TerminalOutcome.COMPLETED.value,
                    }
                ):
                    raise FormalTaskViolation(
                        "TASK_STORE_CORRUPT",
                        "retry authority boundary does not match its durable predecessor",
                        ErrorCode.INTERNAL,
                    )
            return TaskEventAuthoritySnapshot(
                task=task,
                attempt=attempt,
                events=events,
                cursor=task.event_head,
                start_seq=start_seq,
            )

    def nonterminal_attempts(
        self,
    ) -> tuple[tuple[PersistentTaskRecord, PersistentAttemptRecord], ...]:
        with self._reader() as connection:
            rows = connection.execute(
                """
                SELECT t.*, a.attempt_id AS a_attempt_id, a.task_id AS a_task_id,
                    a.executor_id AS a_executor_id, a.executor_ref AS a_executor_ref,
                    a.attempt_number AS a_attempt_number,
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
                    int(row["a_attempt_number"]),
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
        _task_binding_from_row(row)
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
        _task_binding_from_row(row)
        return row

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> PersistentTaskRecord:
        def load() -> PersistentTaskRecord:
            reconciliation_state = row["reconciliation_state"]
            scope, spec = _task_binding_from_row(row)
            return PersistentTaskRecord(
                task_id=row["task_id"],
                scope=scope,
                spec=spec,
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
                int(row["attempt_number"]),
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
            if type(payload) is not dict or set(payload) != {
                "scope",
                "spec",
                "executor_ref",
            }:
                raise FormalTaskViolation(
                    "TASK_STORE_CORRUPT",
                    "formal Task Store contains an invalid outbox payload",
                    ErrorCode.INTERNAL,
                )
            row_keys = set(row.keys())
            kind = OutboxKind(row["kind"])
            scope = ScopeRef.from_dict(payload["scope"])
            spec = FormalTaskSpec.from_dict(payload["spec"])
            if spec.context.scope != scope:
                raise FormalTaskViolation(
                    "OUTBOX_BINDING_MISMATCH",
                    "outbox context does not match its stored scope",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if {
                "canonical_attempt_id",
                "attempt_task_id",
                "bound_executor_id",
                "bound_attempt_number",
                "canonical_task_id",
                "task_attempt_id",
                "task_scope_key",
                "task_scope_json",
                "task_spec_json",
                "bound_attempt_state",
                "bound_attempt_outcome",
                "predecessor_attempt_id",
                "predecessor_task_id",
                "predecessor_attempt_number",
                "predecessor_attempt_state",
                "predecessor_attempt_outcome",
                "bound_task_state",
                "bound_task_outcome",
                "task_correlation_id",
                "task_event_head",
                "task_cancel_requested",
                "task_dispatch_fenced",
                "canonical_command_id",
                "bound_command_type",
                "command_scope_key",
                "command_fingerprint",
                "command_result_json",
                "cancel_event_id",
                "cancel_event_task_id",
                "cancel_event_attempt_id",
                "cancel_event_scope_json",
                "cancel_event_type",
                "cancel_event_state",
                "cancel_event_outcome",
                "cancel_event_producer",
                "cancel_event_source_event_id",
                "cancel_event_causation_id",
                "cancel_event_correlation_id",
                "cancel_event_occurred_at",
                "cancel_event_details_json",
                "cancel_event_seq",
                "cancel_event_count",
                "retry_event_id",
                "retry_event_task_id",
                "retry_event_attempt_id",
                "retry_event_scope_json",
                "retry_event_type",
                "retry_event_state",
                "retry_event_outcome",
                "retry_event_producer",
                "retry_event_source_event_id",
                "retry_event_causation_id",
                "retry_event_correlation_id",
                "retry_event_occurred_at",
                "retry_event_details_json",
                "retry_event_seq",
                "retry_event_count",
                "retry_segment_start_seq",
            }.issubset(row_keys):
                if (
                    row["canonical_attempt_id"] is None
                    or row["canonical_task_id"] is None
                    or row["canonical_command_id"] is None
                    or row["attempt_task_id"] != row["task_id"]
                    or row["task_attempt_id"] != row["attempt_id"]
                ):
                    raise FormalTaskViolation(
                        "OUTBOX_BINDING_MISMATCH",
                        "outbox task and attempt do not have an exact canonical binding",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                task_scope = ScopeRef.from_dict(_json_load(row["task_scope_json"]))
                task_spec = FormalTaskSpec.from_dict(_json_load(row["task_spec_json"]))
                if (
                    scope != task_scope
                    or row["task_scope_key"] != _scope_key(task_scope)
                    or spec != task_spec
                    or row["bound_executor_id"] != spec.executor_id
                    or payload["executor_ref"] != row["bound_executor_ref"]
                ):
                    raise FormalTaskViolation(
                        "OUTBOX_BINDING_MISMATCH",
                        "outbox scope or Executor does not match its canonical binding",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                stored_fingerprint = _json_load(row["command_fingerprint"])
                if (
                    kind is OutboxKind.ATTEMPT_DISPATCH
                    and row["bound_command_type"] == "task.create"
                ):
                    if type(stored_fingerprint) is not dict or set(
                        stored_fingerprint
                    ) != {"command", "resolved_spec"}:
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "dispatch outbox lacks its exact create command binding",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    command_payload = stored_fingerprint["command"]
                    resolved_spec = FormalTaskSpec.from_dict(
                        stored_fingerprint["resolved_spec"]
                    )
                    if resolved_spec != spec:
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "dispatch command does not bind the resolved task spec",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                else:
                    command_payload = stored_fingerprint
                if type(command_payload) is not dict or "request_id" in command_payload:
                    raise FormalTaskViolation(
                        "OUTBOX_COMMAND_BINDING_MISMATCH",
                        "outbox command fingerprint is invalid",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                command = CommandEnvelope.from_dict(
                    {"request_id": "task-store-validation", **command_payload}
                )
                result = ResultEnvelope.from_dict(
                    _json_load(row["command_result_json"])
                )
                expected_command_type = (
                    row["bound_command_type"]
                    if kind is OutboxKind.ATTEMPT_DISPATCH
                    else "task.cancel"
                )
                if (
                    expected_command_type not in {"task.create", "task.retry"}
                    and kind is OutboxKind.ATTEMPT_DISPATCH
                ) or (
                    row["bound_command_type"] != expected_command_type
                    or row["command_scope_key"] != row["task_scope_key"]
                    or command.command_id != row["command_id"]
                    or command.command_type != expected_command_type
                    or command.scope != scope
                    or tuple(command.required_capabilities) != (expected_command_type,)
                    or not result.ok
                    or result.command_id != row["command_id"]
                ):
                    raise FormalTaskViolation(
                        "OUTBOX_COMMAND_BINDING_MISMATCH",
                        "outbox does not match its canonical command ledger entry",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                command_result = result.result
                if (
                    kind is OutboxKind.ATTEMPT_DISPATCH
                    and expected_command_type == "task.create"
                ):
                    expected_payload = {
                        "name": spec.name,
                        "instruction": spec.instruction,
                        "executor_id": spec.executor_id,
                        "side_effect_class": spec.side_effect_class,
                        "attributes": dict(spec.attributes),
                    }
                    if (
                        command.target_ref.id != f"create:{row['command_id']}"
                        or command.payload not in ({}, expected_payload)
                        or command.origin != spec.origin
                        or type(command_result) is not dict
                        or set(command_result)
                        != {"task_id", "attempt_id", "state", "outbox_id"}
                        or command_result["task_id"] != row["task_id"]
                        or command_result["attempt_id"] != row["attempt_id"]
                        or command_result["state"] != FormalTaskState.ACCEPTED.value
                        or command_result["outbox_id"] != row["outbox_id"]
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "dispatch outbox does not match its create command facts",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                elif (
                    kind is OutboxKind.ATTEMPT_DISPATCH
                    and expected_command_type == "task.retry"
                ):
                    TaskRetryProductRequestFingerprint.from_extensions(
                        command.extensions
                    )
                    expected_number = int(row["bound_attempt_number"])
                    if (
                        command.target_ref.id != row["task_id"]
                        or command.payload.get("attempt_number") != expected_number
                        or type(command_result) is not dict
                        or set(command_result)
                        != {
                            "task_id",
                            "previous_attempt_id",
                            "attempt_id",
                            "attempt_number",
                            "applied",
                            "state",
                            "outbox_id",
                        }
                        or command_result["task_id"] != row["task_id"]
                        or command_result["previous_attempt_id"]
                        != command.payload.get("previous_attempt_id")
                        or command_result["attempt_id"] != row["attempt_id"]
                        or command_result["attempt_number"] != expected_number
                        or command_result["applied"] is not True
                        or command_result["state"] != FormalTaskState.ACCEPTED.value
                        or command_result["outbox_id"] != row["outbox_id"]
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "dispatch outbox does not match its retry command facts",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    if (
                        int(row["retry_event_count"]) != 1
                        or type(row["retry_event_id"]) is not str
                        or not row["retry_event_id"].strip()
                        or row["retry_segment_start_seq"] is None
                        or row["predecessor_attempt_id"] is None
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "retry dispatch lacks one exact durable lineage boundary",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    retry_event_scope = ScopeRef.from_dict(
                        _json_load(row["retry_event_scope_json"])
                    )
                    retry_event_details = _json_load(row["retry_event_details_json"])
                    retry_event_state = FormalTaskState(row["retry_event_state"])
                    retry_event_seq = int(row["retry_event_seq"])
                    predecessor_state = FormalAttemptState(
                        row["predecessor_attempt_state"]
                    )
                    expected_previous_attempt_id = command.payload.get(
                        "previous_attempt_id"
                    )
                    expected_previous_outcome = command.payload.get("previous_outcome")
                    if (
                        expected_number not in {2, 3}
                        or row["predecessor_attempt_id"] != expected_previous_attempt_id
                        or row["predecessor_attempt_id"]
                        != command_result["previous_attempt_id"]
                        or row["predecessor_task_id"] != row["task_id"]
                        or int(row["predecessor_attempt_number"]) != expected_number - 1
                        or predecessor_state is not FormalAttemptState.TERMINAL
                        or row["predecessor_attempt_outcome"]
                        != expected_previous_outcome
                        or expected_previous_outcome
                        not in {
                            TerminalOutcome.CANCELLED.value,
                            TerminalOutcome.COMPLETED.value,
                        }
                        or row["retry_event_task_id"] != row["task_id"]
                        or row["retry_event_attempt_id"] != row["attempt_id"]
                        or retry_event_scope != scope
                        or row["retry_event_type"] != "task.retry_accepted"
                        or retry_event_state is not FormalTaskState.ACCEPTED
                        or row["retry_event_outcome"] is not None
                        or row["retry_event_producer"] != "task_core"
                        or row["retry_event_source_event_id"] is not None
                        or row["retry_event_causation_id"] != row["command_id"]
                        or row["retry_event_correlation_id"]
                        != row["task_correlation_id"]
                        or row["retry_event_occurred_at"] != result.observed_at
                        or retry_event_details
                        != {
                            "command_id": row["command_id"],
                            "retry_of_attempt_id": expected_previous_attempt_id,
                            "previous_outcome": expected_previous_outcome,
                            "attempt_number": expected_number,
                        }
                        or retry_event_seq < 1
                        or retry_event_seq != int(row["retry_segment_start_seq"])
                        or retry_event_seq > int(row["task_event_head"])
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "retry dispatch does not match its durable lineage boundary",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                elif (
                    command.target_ref.id != row["task_id"]
                    or command.payload
                    or type(command_result) is not dict
                    or set(command_result)
                    != {
                        "task_id",
                        "attempt_id",
                        "cancel_acknowledged",
                        "applied",
                        "state",
                        "outbox_id",
                    }
                    or command_result["task_id"] != row["task_id"]
                    or command_result["attempt_id"] != row["attempt_id"]
                    or command_result["cancel_acknowledged"] is not True
                    or command_result["applied"] is not True
                    or command_result["outbox_id"] != row["outbox_id"]
                ):
                    raise FormalTaskViolation(
                        "OUTBOX_COMMAND_BINDING_MISMATCH",
                        "cancel outbox does not match its cancel command facts",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                if kind is OutboxKind.ATTEMPT_CANCEL:
                    if (
                        int(row["cancel_event_count"]) != 1
                        or type(row["cancel_event_id"]) is not str
                        or not row["cancel_event_id"].strip()
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "cancel outbox lacks one exact durable request event",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                    cancel_event_scope = ScopeRef.from_dict(
                        _json_load(row["cancel_event_scope_json"])
                    )
                    cancel_event_details = _json_load(row["cancel_event_details_json"])
                    cancel_event_state = FormalTaskState(row["cancel_event_state"])
                    cancel_event_seq = int(row["cancel_event_seq"])
                    if (
                        row["cancel_event_task_id"] != row["task_id"]
                        or row["cancel_event_attempt_id"] != row["attempt_id"]
                        or cancel_event_scope != scope
                        or row["cancel_event_type"] != "task.cancel_requested"
                        or cancel_event_state
                        not in {FormalTaskState.ACCEPTED, FormalTaskState.RUNNING}
                        or command_result["state"] != cancel_event_state.value
                        or row["cancel_event_outcome"] is not None
                        or row["cancel_event_producer"] != "task_core.control"
                        or row["cancel_event_source_event_id"] is not None
                        or row["cancel_event_causation_id"] != row["command_id"]
                        or row["cancel_event_correlation_id"]
                        != row["task_correlation_id"]
                        or row["cancel_event_occurred_at"] != result.observed_at
                        or cancel_event_details != {"command_id": row["command_id"]}
                        or cancel_event_seq < 1
                        or cancel_event_seq > int(row["task_event_head"])
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_COMMAND_BINDING_MISMATCH",
                            "cancel result does not match its durable request event",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                task_state = FormalTaskState(row["bound_task_state"])
                attempt_state = FormalAttemptState(row["bound_attempt_state"])
                cancel_requested = row["task_cancel_requested"]
                dispatch_fenced = row["task_dispatch_fenced"]
                if (
                    cancel_requested not in {0, 1}
                    or dispatch_fenced not in {0, 1}
                    or task_state is FormalTaskState.TERMINAL
                    or row["bound_task_outcome"] is not None
                    or attempt_state is FormalAttemptState.TERMINAL
                    or row["bound_attempt_outcome"] is not None
                ):
                    raise FormalTaskViolation(
                        "OUTBOX_LIFECYCLE_MISMATCH",
                        "pending outbox does not match a deliverable task lifecycle",
                        ErrorCode.PROTOCOL_VIOLATION,
                    )
                if kind is OutboxKind.ATTEMPT_DISPATCH:
                    if (
                        task_state is not FormalTaskState.ACCEPTED
                        or attempt_state is not FormalAttemptState.ACCEPTED
                        or row["bound_executor_ref"] is not None
                        or bool(cancel_requested) != bool(dispatch_fenced)
                        or (bool(cancel_requested) and int(row["delivery_count"]) == 0)
                    ):
                        raise FormalTaskViolation(
                            "OUTBOX_LIFECYCLE_MISMATCH",
                            "dispatch outbox does not match its task lifecycle",
                            ErrorCode.PROTOCOL_VIOLATION,
                        )
                elif (
                    not bool(cancel_requested)
                    or not bool(dispatch_fenced)
                    or (task_state is FormalTaskState.ACCEPTED)
                    != (attempt_state is FormalAttemptState.ACCEPTED)
                    or (task_state is FormalTaskState.RUNNING)
                    != (attempt_state is FormalAttemptState.RUNNING)
                ):
                    raise FormalTaskViolation(
                        "OUTBOX_LIFECYCLE_MISMATCH",
                        "cancel outbox lacks its durable cancellation lifecycle",
                        ErrorCode.PROTOCOL_VIOLATION,
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
                scope,
                spec,
                payload["executor_ref"],
                source_seq,
                OutboxState(row["state"]),
                int(row["delivery_count"]),
                row["claim_token"],
            )

        return _stored_record("outbox", load)


__all__ = ["SqliteTaskStore"]
