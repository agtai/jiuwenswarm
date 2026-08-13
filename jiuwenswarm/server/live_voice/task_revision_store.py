# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""SQLite saga authority for the separately flagged S8.5 task revision.

The sidecar schema cohosts the formal P3alpha Store database so predecessor
fencing, successor attempt creation, TaskEvent append, and dispatch outbox write
can commit in one SQLite transaction.  Constructing ``SqliteTaskStore`` alone
does not create or activate this extension.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ScopeRef,
    TerminalOutcome,
)

from .formal_task_models import (
    ExecutorDeliveryResult,
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
    PersistentTaskRecord,
    utc_now,
)
from .task_revision import (
    RevisionApplicationState,
    RevisionFenceAck,
    RevisionFenceRequest,
    TaskRevisionAuthority,
    TaskRevisionCommand,
    TaskRevisionConstraints,
    TaskRevisionExecutionAck,
    TaskRevisionGrant,
    TaskRevisionOperation,
    TaskRevisionPlan,
    TaskRevisionRecord,
    TaskRevisionTargetSnapshot,
    TaskRevisionViolation,
    plan_task_revision,
)
from .task_store import SqliteTaskStore, _json_dump, _json_load, _scope_key


_EXTENSION_SCHEMA_VERSION = 2
_EXTENSION_COLUMNS = {
    "s85_revision_metadata": ("key", "value"),
    "s85_task_revisions": (
        "task_id",
        "task_revision",
        "predecessor_revision",
        "attempt_id",
        "scope_key",
        "base_instruction",
        "additive_facts_json",
        "constraints_json",
        "origin_commit_id",
        "command_id",
        "created_at",
    ),
    "s85_revision_commands": (
        "scope_key",
        "command_id",
        "fingerprint",
        "operation",
        "task_id",
        "predecessor_revision",
        "successor_revision",
        "predecessor_attempt_id",
        "application_state",
        "command_json",
        "plan_json",
        "receipt_json",
        "fence_outbox_id",
        "created_at",
        "updated_at",
    ),
    "s85_revision_outbox": (
        "outbox_id",
        "scope_key",
        "command_id",
        "task_id",
        "predecessor_revision",
        "predecessor_attempt_id",
        "executor_id",
        "executor_ref",
        "state",
        "delivery_count",
        "claimed_by",
        "claim_token",
        "last_error",
        "created_at",
        "updated_at",
    ),
    "s85_revision_fence_acks": (
        "scope_key",
        "command_id",
        "ack_json",
        "created_at",
    ),
    "s85_revision_dispatch_outbox": (
        "outbox_id",
        "scope_key",
        "command_id",
        "task_id",
        "attempt_id",
        "payload_json",
        "state",
        "delivery_count",
        "claimed_by",
        "claim_token",
        "last_error",
        "created_at",
        "updated_at",
    ),
    "s85_revision_execution_acks": (
        "scope_key",
        "task_id",
        "task_revision",
        "attempt_id",
        "executor_ref",
        "ack_json",
        "created_at",
    ),
}
_EXTENSION_PRIMARY_KEYS = {
    "s85_revision_metadata": ("key",),
    "s85_task_revisions": ("task_id", "task_revision"),
    "s85_revision_commands": ("scope_key", "command_id"),
    "s85_revision_outbox": ("outbox_id",),
    "s85_revision_fence_acks": ("scope_key", "command_id"),
    "s85_revision_dispatch_outbox": ("outbox_id",),
    "s85_revision_execution_acks": ("task_id", "task_revision"),
}
_EXTENSION_NAMED_INDEXES = {
    "idx_s85_one_fence_per_task": (
        "s85_revision_commands",
        ("task_id",),
        True,
        True,
    ),
    "idx_s85_revision_outbox_pending": (
        "s85_revision_outbox",
        ("state", "created_at", "outbox_id"),
        False,
        False,
    ),
    "idx_s85_dispatch_pending": (
        "s85_revision_dispatch_outbox",
        ("state", "created_at", "outbox_id"),
        False,
        False,
    ),
}


class RevisionOutboxState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DELIVERED = "delivered"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TaskRevisionReceipt:
    command_id: str
    task_id: str
    application_state: RevisionApplicationState
    predecessor_revision: int
    successor_revision: int
    predecessor_attempt_id: str
    successor_attempt_id: str | None
    fence_outbox_id: str
    dispatch_outbox_id: str | None = None
    replayed: bool = False

    def __post_init__(self) -> None:
        required_text = (
            self.command_id,
            self.task_id,
            self.predecessor_attempt_id,
            self.fence_outbox_id,
        )
        applied = self.application_state is RevisionApplicationState.APPLIED
        if (
            any(type(value) is not str or not value.strip() for value in required_text)
            or type(self.application_state) is not RevisionApplicationState
            or type(self.predecessor_revision) is not int
            or self.predecessor_revision < 1
            or type(self.successor_revision) is not int
            or self.successor_revision != self.predecessor_revision + 1
            or type(self.replayed) is not bool
            or applied
            != (
                type(self.successor_attempt_id) is str
                and bool(self.successor_attempt_id.strip())
                and type(self.dispatch_outbox_id) is str
                and bool(self.dispatch_outbox_id.strip())
            )
            or (
                not applied
                and (
                    self.successor_attempt_id is not None
                    or self.dispatch_outbox_id is not None
                )
            )
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "task revision receipt contains invalid authority facts",
                ErrorCode.INTERNAL,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "task_id": self.task_id,
            "application_state": self.application_state.value,
            "predecessor_revision": self.predecessor_revision,
            "successor_revision": self.successor_revision,
            "predecessor_attempt_id": self.predecessor_attempt_id,
            "successor_attempt_id": self.successor_attempt_id,
            "fence_outbox_id": self.fence_outbox_id,
            "dispatch_outbox_id": self.dispatch_outbox_id,
            "replayed": self.replayed,
        }

    @classmethod
    def from_dict(cls, payload: object) -> TaskRevisionReceipt:
        expected = {
            "command_id",
            "task_id",
            "application_state",
            "predecessor_revision",
            "successor_revision",
            "predecessor_attempt_id",
            "successor_attempt_id",
            "fence_outbox_id",
            "dispatch_outbox_id",
            "replayed",
        }
        if type(payload) is not dict or set(payload) != expected:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "task revision receipt is malformed",
                ErrorCode.INTERNAL,
            )
        try:
            return cls(
                command_id=payload["command_id"],  # type: ignore[arg-type]
                task_id=payload["task_id"],  # type: ignore[arg-type]
                application_state=RevisionApplicationState(
                    payload["application_state"]
                ),
                predecessor_revision=payload["predecessor_revision"],  # type: ignore[arg-type]
                successor_revision=payload["successor_revision"],  # type: ignore[arg-type]
                predecessor_attempt_id=payload["predecessor_attempt_id"],  # type: ignore[arg-type]
                successor_attempt_id=payload["successor_attempt_id"],  # type: ignore[arg-type]
                fence_outbox_id=payload["fence_outbox_id"],  # type: ignore[arg-type]
                dispatch_outbox_id=payload["dispatch_outbox_id"],  # type: ignore[arg-type]
                replayed=payload["replayed"],  # type: ignore[arg-type]
            )
        except (TypeError, ValueError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "task revision receipt contains invalid facts",
                ErrorCode.INTERNAL,
            ) from error


@dataclass(frozen=True, slots=True)
class ClaimedRevisionFence:
    outbox_id: str
    claim_token: str
    request: RevisionFenceRequest
    scope: ScopeRef
    executor_id: str
    executor_ref: str
    delivery_count: int


@dataclass(frozen=True, slots=True)
class ClaimedRevisionDispatch:
    item: PersistentOutboxItem


@dataclass(frozen=True, slots=True)
class TaskRevisionTruth:
    task: PersistentTaskRecord
    attempt: PersistentAttemptRecord
    current_revision: TaskRevisionRecord
    revisions: tuple[TaskRevisionRecord, ...]
    pending_receipt: TaskRevisionReceipt | None
    cleanup_ack: RevisionFenceAck | None
    execution_ack: TaskRevisionExecutionAck | None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task.task_id,
            "task_state": self.task.state.value,
            "outcome": None if self.task.outcome is None else self.task.outcome.value,
            "current_revision": self.current_revision.task_revision,
            "current_attempt_id": self.attempt.attempt_id,
            "attempt_number": self.attempt.attempt_number,
            "revision_history": [record.to_dict() for record in self.revisions],
            "pending_command": (
                None if self.pending_receipt is None else self.pending_receipt.to_dict()
            ),
            "cleanup": (
                None
                if self.cleanup_ack is None
                else {
                    "command_id": self.cleanup_ack.command_id,
                    "predecessor_attempt_id": self.cleanup_ack.predecessor_attempt_id,
                    "cleanup_id": self.cleanup_ack.cleanup_id,
                    "checkout_identity": self.cleanup_ack.checkout_identity,
                    "unapplied_changes_discarded": (
                        self.cleanup_ack.unapplied_changes_discarded
                    ),
                    "acknowledged_at": self.cleanup_ack.acknowledged_at,
                }
            ),
            "execution": (
                None if self.execution_ack is None else self.execution_ack.to_dict()
            ),
        }


class SqliteTaskRevisionStore:
    """Task-Core-owned S8.5 revision ledger and fence-to-successor saga."""

    def __init__(
        self,
        task_store: SqliteTaskStore,
        *,
        failpoint: Callable[[str], None] | None = None,
    ) -> None:
        if type(task_store) is not SqliteTaskStore:
            raise TypeError("task_store must be an exact SqliteTaskStore")
        self.task_store = task_store
        self.database_path = Path(task_store.database_path)
        self._failpoint = failpoint
        self._initialize()
        self.task_store.register_s8_5_revision_extension()

    def _initialize(self) -> None:
        with self.task_store._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_revision_metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL)
                """
            )

            version = connection.execute(
                "SELECT value FROM s85_revision_metadata WHERE key='schema_version'"
            ).fetchone()
            if version is None:
                connection.execute(
                    """
                    INSERT INTO s85_revision_metadata(key, value)
                    VALUES('schema_version', ?)
                    """,
                    (str(_EXTENSION_SCHEMA_VERSION),),
                )
            elif version["value"] == "1":
                # The isolated incubator briefly carried the pre-verifier
                # schema.  Upgrade only that exact known version in the same
                # transaction; every unknown/partial shape still fails closed
                # in the complete schema verification below.
                connection.execute(
                    """
                    UPDATE s85_revision_metadata SET value=?
                    WHERE key='schema_version' AND value='1'
                    """,
                    (str(_EXTENSION_SCHEMA_VERSION),),
                )
            elif version["value"] != str(_EXTENSION_SCHEMA_VERSION):
                raise FormalTaskViolation(
                    "TASK_REVISION_SCHEMA_UNSUPPORTED",
                    "S8.5 task revision schema version is unsupported",
                    ErrorCode.UNSUPPORTED,
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_task_revisions (
                    task_id TEXT NOT NULL,
                    task_revision INTEGER NOT NULL CHECK(task_revision >= 1),
                    predecessor_revision INTEGER,
                    attempt_id TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    base_instruction TEXT NOT NULL,
                    additive_facts_json TEXT NOT NULL,
                    constraints_json TEXT NOT NULL,
                    origin_commit_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, task_revision),
                    UNIQUE(attempt_id))
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_revision_commands (
                    scope_key TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    fingerprint BLOB NOT NULL,
                    operation TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    predecessor_revision INTEGER NOT NULL,
                    successor_revision INTEGER NOT NULL,
                    predecessor_attempt_id TEXT NOT NULL,
                    application_state TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    fence_outbox_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(scope_key, command_id))
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_s85_one_fence_per_task
                ON s85_revision_commands(task_id)
                WHERE application_state IN ('fencing', 'unknown')
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_revision_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    scope_key TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    predecessor_revision INTEGER NOT NULL,
                    predecessor_attempt_id TEXT NOT NULL,
                    executor_id TEXT NOT NULL,
                    executor_ref TEXT NOT NULL,
                    state TEXT NOT NULL,
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    claimed_by TEXT,
                    claim_token TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(scope_key, command_id))
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_s85_revision_outbox_pending
                ON s85_revision_outbox(state, created_at, outbox_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_revision_fence_acks (
                    scope_key TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    ack_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(scope_key, command_id))
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_revision_dispatch_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    scope_key TEXT NOT NULL,
                    command_id TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    delivery_count INTEGER NOT NULL DEFAULT 0,
                    claimed_by TEXT,
                    claim_token TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_s85_dispatch_pending
                ON s85_revision_dispatch_outbox(state, created_at, outbox_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS s85_revision_execution_acks (
                    scope_key TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_revision INTEGER NOT NULL CHECK(task_revision >= 1),
                    attempt_id TEXT NOT NULL UNIQUE,
                    executor_ref TEXT NOT NULL,
                    ack_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, task_revision))
                """
            )
            self._verify_schema(connection)

    def _hit(self, name: str) -> None:
        if self._failpoint is not None:
            self._failpoint(name)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE 's85_%'
                """
            ).fetchall()
        }
        if tables != set(_EXTENSION_COLUMNS):
            raise FormalTaskViolation(
                "TASK_REVISION_SCHEMA_UNSUPPORTED",
                "S8.5 task revision schema tables are incomplete or unknown",
                ErrorCode.UNSUPPORTED,
            )
        for table, expected_columns in _EXTENSION_COLUMNS.items():
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
            if tuple(row["name"] for row in rows) != expected_columns:
                raise FormalTaskViolation(
                    "TASK_REVISION_SCHEMA_UNSUPPORTED",
                    f"S8.5 task revision table {table} has unsupported columns",
                    ErrorCode.UNSUPPORTED,
                )
            primary_key = tuple(
                row["name"]
                for row in sorted(rows, key=lambda item: item["pk"])
                if row["pk"]
            )
            if primary_key != _EXTENSION_PRIMARY_KEYS[table]:
                raise FormalTaskViolation(
                    "TASK_REVISION_SCHEMA_UNSUPPORTED",
                    f"S8.5 task revision table {table} has an unsupported key",
                    ErrorCode.UNSUPPORTED,
                )
            for row in rows:
                expected_type = (
                    "BLOB"
                    if row["name"] == "fingerprint"
                    else "INTEGER"
                    if row["name"]
                    in {
                        "task_revision",
                        "predecessor_revision",
                        "successor_revision",
                        "delivery_count",
                    }
                    else "TEXT"
                )
                if row["type"].upper() != expected_type:
                    raise FormalTaskViolation(
                        "TASK_REVISION_SCHEMA_UNSUPPORTED",
                        f"S8.5 task revision table {table} has unsupported types",
                        ErrorCode.UNSUPPORTED,
                    )
        for name, (table, columns, unique, partial) in _EXTENSION_NAMED_INDEXES.items():
            indexes = {
                row["name"]: row
                for row in connection.execute(f"PRAGMA index_list({table})").fetchall()
            }
            index = indexes.get(name)
            actual_columns = (
                ()
                if index is None
                else tuple(
                    row["name"]
                    for row in connection.execute(f"PRAGMA index_info({name})")
                )
            )
            if (
                index is None
                or bool(index["unique"]) is not unique
                or bool(index["partial"]) is not partial
                or actual_columns != columns
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_SCHEMA_UNSUPPORTED",
                    f"S8.5 task revision index {name} is unsupported",
                    ErrorCode.UNSUPPORTED,
                )
            if name == "idx_s85_one_fence_per_task":
                sql_row = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                    (name,),
                ).fetchone()
                normalized_sql = (
                    ""
                    if sql_row is None or type(sql_row["sql"]) is not str
                    else "".join(sql_row["sql"].lower().split())
                )
                if (
                    "whereapplication_statein('fencing','unknown')"
                    not in normalized_sql
                ):
                    raise FormalTaskViolation(
                        "TASK_REVISION_SCHEMA_UNSUPPORTED",
                        "S8.5 unresolved-revision ownership index is unsupported",
                        ErrorCode.UNSUPPORTED,
                    )
        metadata = connection.execute(
            "SELECT key, value FROM s85_revision_metadata ORDER BY key"
        ).fetchall()
        if tuple((row["key"], row["value"]) for row in metadata) != (
            ("schema_version", str(_EXTENSION_SCHEMA_VERSION)),
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_SCHEMA_UNSUPPORTED",
                "S8.5 task revision metadata is unsupported",
                ErrorCode.UNSUPPORTED,
            )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "S8.5 task revision Store failed its integrity check",
                ErrorCode.INTERNAL,
            )

    @staticmethod
    def _translate(error: TaskRevisionViolation) -> FormalTaskViolation:
        return FormalTaskViolation(error.reason, str(error), error.code)

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> TaskRevisionRecord:
        facts = _json_load(row["additive_facts_json"])
        if type(facts) is not list:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision facts are malformed",
                ErrorCode.INTERNAL,
            )
        try:
            return TaskRevisionRecord(
                task_id=row["task_id"],
                task_revision=int(row["task_revision"]),
                predecessor_revision=(
                    None
                    if row["predecessor_revision"] is None
                    else int(row["predecessor_revision"])
                ),
                attempt_id=row["attempt_id"],
                base_instruction=row["base_instruction"],
                additive_facts=tuple(facts),
                constraints=TaskRevisionConstraints.from_dict(
                    _json_load(row["constraints_json"])
                ),
                origin_commit_id=row["origin_commit_id"],
                created_by_command_id=row["command_id"],
            )
        except TaskRevisionViolation as error:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision record is invalid",
                ErrorCode.INTERNAL,
            ) from error

    @staticmethod
    def _plan_from_json(value: str) -> TaskRevisionPlan:
        payload = _json_load(value)
        if type(payload) is not dict or set(payload) != {
            "command_id",
            "operation",
            "task_id",
            "predecessor_revision",
            "successor_revision",
            "predecessor_attempt_id",
            "additive_facts",
            "constraints",
            "effective_instruction",
            "application_state",
        }:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision plan is malformed",
                ErrorCode.INTERNAL,
            )
        facts = payload["additive_facts"]
        if type(facts) is not list:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision plan facts are malformed",
                ErrorCode.INTERNAL,
            )
        try:
            return TaskRevisionPlan(
                command_id=payload["command_id"],  # type: ignore[arg-type]
                operation=TaskRevisionOperation(payload["operation"]),
                task_id=payload["task_id"],  # type: ignore[arg-type]
                predecessor_revision=payload["predecessor_revision"],  # type: ignore[arg-type]
                successor_revision=payload["successor_revision"],  # type: ignore[arg-type]
                predecessor_attempt_id=payload["predecessor_attempt_id"],  # type: ignore[arg-type]
                additive_facts=tuple(facts),
                constraints=TaskRevisionConstraints.from_dict(payload["constraints"]),
                effective_instruction=payload["effective_instruction"],  # type: ignore[arg-type]
                application_state=RevisionApplicationState(
                    payload["application_state"]
                ),
            )
        except (TaskRevisionViolation, TypeError, ValueError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision plan contains invalid facts",
                ErrorCode.INTERNAL,
            ) from error

    @staticmethod
    def _ack_from_json(value: str) -> RevisionFenceAck:
        payload = _json_load(value)
        if type(payload) is not dict:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision cleanup ACK is malformed",
                ErrorCode.INTERNAL,
            )
        try:
            return RevisionFenceAck(**payload)  # type: ignore[arg-type]
        except (TaskRevisionViolation, TypeError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision cleanup ACK is invalid",
                ErrorCode.INTERNAL,
            ) from error

    @staticmethod
    def _execution_ack_from_json(value: str) -> TaskRevisionExecutionAck:
        try:
            return TaskRevisionExecutionAck.from_dict(_json_load(value))
        except (TaskRevisionViolation, TypeError, ValueError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "stored revision execution ACK is invalid",
                ErrorCode.INTERNAL,
            ) from error

    def request_revision(
        self,
        command: TaskRevisionCommand,
        grant: TaskRevisionGrant,
        *,
        initial_constraints: TaskRevisionConstraints,
        observed_at: str | None = None,
    ) -> TaskRevisionReceipt:
        now = observed_at or utc_now()
        scope_key = _scope_key(command.scope)
        fingerprint = command.fingerprint()
        with self.task_store._transaction() as connection:
            existing = connection.execute(
                """
                SELECT fingerprint, receipt_json FROM s85_revision_commands
                WHERE scope_key=? AND command_id=?
                """,
                (scope_key, command.command_id),
            ).fetchone()
            if existing is not None:
                if existing["fingerprint"] != fingerprint:
                    raise FormalTaskViolation(
                        "IDEMPOTENCY_CONFLICT",
                        "revision command_id cannot change its meaning",
                        ErrorCode.CONFLICT,
                    )
                receipt = TaskRevisionReceipt.from_dict(
                    _json_load(existing["receipt_json"])
                )
                return replace(receipt, replayed=True)
            collision = connection.execute(
                """
                SELECT 1 FROM commands WHERE scope_key=? AND command_id=?
                """,
                (scope_key, command.command_id),
            ).fetchone()
            if collision is not None:
                raise FormalTaskViolation(
                    "IDEMPOTENCY_CONFLICT",
                    "command_id is already bound to a formal task command",
                    ErrorCode.CONFLICT,
                )
            task = self.task_store._require_task_row(
                connection, command.task_id, command.scope
            )
            self.task_store._verify_durable_lineage(connection, task)
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (task["attempt_id"],),
            ).fetchone()
            if attempt is None or attempt["task_id"] != command.task_id:
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "current task attempt is unavailable",
                    ErrorCode.INTERNAL,
                )
            if task["state"] not in {
                FormalTaskState.RUNNING.value,
                FormalTaskState.BLOCKED.value,
                FormalTaskState.DECISION_REQUIRED.value,
            }:
                raise FormalTaskViolation(
                    "TASK_REVISION_NOT_RUNNING",
                    "S8.5 revision requires a live background attempt",
                    ErrorCode.CONFLICT,
                )
            if bool(task["cancel_requested"]) or attempt["executor_ref"] is None:
                raise FormalTaskViolation(
                    "TASK_REVISION_EXECUTOR_NOT_BOUND",
                    "revision requires one uncancelled Executor-bound attempt",
                    ErrorCode.CONFLICT,
                )
            latest = connection.execute(
                """
                SELECT * FROM s85_task_revisions
                WHERE task_id=? ORDER BY task_revision DESC LIMIT 1
                """,
                (command.task_id,),
            ).fetchone()
            if latest is None:
                if int(attempt["attempt_number"]) != 1:
                    raise FormalTaskViolation(
                        "TASK_REVISION_RETRY_MIXING_UNSUPPORTED",
                        "the S8.5 showcase revises only the original task attempt",
                        ErrorCode.UNSUPPORTED,
                    )
                spec = FormalTaskSpec.from_dict(_json_load(task["spec_json"]))
                initial = TaskRevisionRecord(
                    task_id=command.task_id,
                    task_revision=1,
                    predecessor_revision=None,
                    attempt_id=task["attempt_id"],
                    base_instruction=spec.instruction,
                    additive_facts=(),
                    constraints=initial_constraints,
                    origin_commit_id=(
                        spec.origin.commit_id or f"structured:{command.task_id}"
                    ),
                    created_by_command_id=f"initial:{command.task_id}",
                )
                self._insert_revision(
                    connection,
                    initial,
                    scope_key=scope_key,
                    created_at=now,
                )
                self._hit("revision.request.after_initial_revision")
                current = initial
            else:
                current = self._revision_from_row(latest)
            pending = connection.execute(
                """
                SELECT command_id FROM s85_revision_commands
                WHERE task_id=? AND application_state IN (?, ?) LIMIT 1
                """,
                (
                    command.task_id,
                    RevisionApplicationState.FENCING.value,
                    RevisionApplicationState.UNKNOWN.value,
                ),
            ).fetchone()
            authority = TaskRevisionAuthority(
                task_id=command.task_id,
                scope=command.scope,
                task_revision=current.task_revision,
                attempt_id=task["attempt_id"],
                task_state=task["state"],
                base_instruction=current.base_instruction,
                additive_facts=current.additive_facts,
                constraints=current.constraints,
                pending_command_id=(None if pending is None else pending["command_id"]),
            )
            try:
                plan = plan_task_revision(
                    command,
                    grant,
                    authority,
                    feature_enabled=True,
                    now=now,
                )
            except TaskRevisionViolation as error:
                raise self._translate(error) from error
            outbox_id = f"revision-fence-{uuid.uuid4().hex}"
            receipt = TaskRevisionReceipt(
                command_id=command.command_id,
                task_id=command.task_id,
                application_state=RevisionApplicationState.FENCING,
                predecessor_revision=plan.predecessor_revision,
                successor_revision=plan.successor_revision,
                predecessor_attempt_id=plan.predecessor_attempt_id,
                successor_attempt_id=None,
                fence_outbox_id=outbox_id,
            )
            connection.execute(
                """
                INSERT INTO s85_revision_commands(
                    scope_key, command_id, fingerprint, operation, task_id,
                    predecessor_revision, successor_revision,
                    predecessor_attempt_id, application_state, command_json,
                    plan_json, receipt_json, fence_outbox_id, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_key,
                    command.command_id,
                    fingerprint,
                    command.operation.value,
                    command.task_id,
                    plan.predecessor_revision,
                    plan.successor_revision,
                    plan.predecessor_attempt_id,
                    receipt.application_state.value,
                    _json_dump(command.to_dict()),
                    _json_dump(plan.to_dict()),
                    _json_dump(receipt.to_dict()),
                    outbox_id,
                    now,
                    now,
                ),
            )
            self._hit("revision.request.after_command")
            connection.execute(
                """
                INSERT INTO s85_revision_outbox(
                    outbox_id, scope_key, command_id, task_id,
                    predecessor_revision, predecessor_attempt_id,
                    executor_id, executor_ref, state, delivery_count,
                    claimed_by, claim_token, last_error, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?, ?)
                """,
                (
                    outbox_id,
                    scope_key,
                    command.command_id,
                    command.task_id,
                    plan.predecessor_revision,
                    plan.predecessor_attempt_id,
                    attempt["executor_id"],
                    attempt["executor_ref"],
                    RevisionOutboxState.PENDING.value,
                    now,
                    now,
                ),
            )
            self._hit("revision.request.after_fence_outbox")
            self.task_store._append_event(
                connection,
                task,
                event_type="task.revision_requested",
                state=task["state"],
                outcome=None,
                producer="task_core.revision",
                source_event_id=None,
                causation_id=command.command_id,
                occurred_at=now,
                details={
                    "command_id": command.command_id,
                    "operation": command.operation.value,
                    "predecessor_revision": plan.predecessor_revision,
                    "successor_revision": plan.successor_revision,
                    "predecessor_attempt_id": plan.predecessor_attempt_id,
                },
            )
            self._hit("revision.request.after_requested_event")
            return receipt

    def read_target(self, task_id: str, scope: ScopeRef) -> TaskRevisionTargetSnapshot:
        """Read the current revision target without allocating revision state."""

        with self.task_store._reader() as connection:
            connection.execute("BEGIN")
            task = self.task_store._require_task_row(connection, task_id, scope)
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (task["attempt_id"],)
            ).fetchone()
            if attempt is None or attempt["task_id"] != task_id:
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "revision target attempt is unavailable",
                    ErrorCode.INTERNAL,
                )
            latest = connection.execute(
                """
                SELECT task_revision, attempt_id FROM s85_task_revisions
                WHERE task_id=? AND scope_key=?
                ORDER BY task_revision DESC LIMIT 1
                """,
                (task_id, _scope_key(scope)),
            ).fetchone()
            task_revision = 1 if latest is None else int(latest["task_revision"])
            if latest is not None and latest["attempt_id"] != task["attempt_id"]:
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "revision target disagrees with the current attempt",
                    ErrorCode.INTERNAL,
                )
            pending = connection.execute(
                """
                SELECT command_id FROM s85_revision_commands
                WHERE task_id=? AND application_state IN (?, ?) LIMIT 1
                """,
                (
                    task_id,
                    RevisionApplicationState.FENCING.value,
                    RevisionApplicationState.UNKNOWN.value,
                ),
            ).fetchone()
            return TaskRevisionTargetSnapshot(
                task_id=task_id,
                scope=scope,
                task_revision=task_revision,
                attempt_id=task["attempt_id"],
                attempt_number=int(attempt["attempt_number"]),
                task_state=task["state"],
                pending_command_id=None if pending is None else pending["command_id"],
            )

    @staticmethod
    def _insert_revision(
        connection: sqlite3.Connection,
        record: TaskRevisionRecord,
        *,
        scope_key: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO s85_task_revisions(
                task_id, task_revision, predecessor_revision, attempt_id,
                scope_key, base_instruction, additive_facts_json,
                constraints_json, origin_commit_id, command_id, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id,
                record.task_revision,
                record.predecessor_revision,
                record.attempt_id,
                scope_key,
                record.base_instruction,
                _json_dump(list(record.additive_facts)),
                _json_dump(record.constraints.to_dict()),
                record.origin_commit_id,
                record.created_by_command_id,
                created_at,
            ),
        )

    def claim_fence(self, worker_id: str) -> ClaimedRevisionFence | None:
        if type(worker_id) is not str or not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        token = uuid.uuid4().hex
        now = utc_now()
        with self.task_store._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM s85_revision_outbox WHERE state=?
                ORDER BY created_at, outbox_id LIMIT 1
                """,
                (RevisionOutboxState.PENDING.value,),
            ).fetchone()
            if row is None:
                return None
            changed = connection.execute(
                """
                UPDATE s85_revision_outbox
                SET state=?, delivery_count=delivery_count+1, claimed_by=?,
                    claim_token=?, updated_at=?
                WHERE outbox_id=? AND state=?
                """,
                (
                    RevisionOutboxState.CLAIMED.value,
                    worker_id,
                    token,
                    now,
                    row["outbox_id"],
                    RevisionOutboxState.PENDING.value,
                ),
            ).rowcount
            if changed != 1:
                return None
            claimed = ClaimedRevisionFence(
                outbox_id=row["outbox_id"],
                claim_token=token,
                request=RevisionFenceRequest(
                    command_id=row["command_id"],
                    task_id=row["task_id"],
                    predecessor_revision=int(row["predecessor_revision"]),
                    predecessor_attempt_id=row["predecessor_attempt_id"],
                ),
                scope=ScopeRef.from_dict(_json_load(row["scope_key"])),
                executor_id=row["executor_id"],
                executor_ref=row["executor_ref"],
                delivery_count=int(row["delivery_count"]) + 1,
            )
            command_row = self._require_claimed_command(connection, claimed)
            try:
                command = TaskRevisionCommand.from_dict(
                    _json_load(command_row["command_json"])
                )
                plan = self._plan_from_json(command_row["plan_json"])
                receipt = TaskRevisionReceipt.from_dict(
                    _json_load(command_row["receipt_json"])
                )
            except (TaskRevisionViolation, TypeError, ValueError) as error:
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "revision fence command ledger is malformed",
                    ErrorCode.INTERNAL,
                ) from error
            task = self.task_store._require_task_row(
                connection, claimed.request.task_id, claimed.scope
            )
            self.task_store._verify_durable_lineage(connection, task)
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (claimed.request.predecessor_attempt_id,),
            ).fetchone()
            if (
                command_row["fingerprint"] != command.fingerprint()
                or command.scope != claimed.scope
                or command.command_id != claimed.request.command_id
                or command.task_id != claimed.request.task_id
                or command.expected_task_revision
                != claimed.request.predecessor_revision
                or command.expected_attempt_id != claimed.request.predecessor_attempt_id
                or plan.command_id != command.command_id
                or plan.task_id != command.task_id
                or plan.predecessor_revision != command.expected_task_revision
                or plan.predecessor_attempt_id != command.expected_attempt_id
                or receipt.command_id != command.command_id
                or receipt.task_id != command.task_id
                or receipt.application_state is not RevisionApplicationState.FENCING
                or receipt.fence_outbox_id != claimed.outbox_id
                or task["attempt_id"] != claimed.request.predecessor_attempt_id
                or attempt is None
                or attempt["task_id"] != claimed.request.task_id
                or attempt["executor_id"] != claimed.executor_id
                or attempt["executor_ref"] != claimed.executor_ref
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_OUTBOX_BINDING_MISMATCH",
                    "revision fence is not bound to one exact command and attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if bool(task["cancel_requested"]) or task["state"] == (
                FormalTaskState.TERMINAL.value
            ):
                rejected = replace(
                    receipt,
                    application_state=RevisionApplicationState.REJECTED,
                )
                connection.execute(
                    """
                    UPDATE s85_revision_commands
                    SET application_state=?, receipt_json=?, updated_at=?
                    WHERE scope_key=? AND command_id=?
                    """,
                    (
                        rejected.application_state.value,
                        _json_dump(rejected.to_dict()),
                        now,
                        _scope_key(claimed.scope),
                        claimed.request.command_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE s85_revision_outbox
                    SET state=?, claimed_by=NULL, claim_token=NULL,
                        last_error=?, updated_at=? WHERE outbox_id=?
                    """,
                    (
                        RevisionOutboxState.DELIVERED.value,
                        "TASK_REVISION_CANCEL_RACE",
                        now,
                        claimed.outbox_id,
                    ),
                )
                return None
            if task["state"] not in {
                FormalTaskState.RUNNING.value,
                FormalTaskState.BLOCKED.value,
                FormalTaskState.DECISION_REQUIRED.value,
            }:
                raise FormalTaskViolation(
                    "TASK_REVISION_PRECONDITION_STALE",
                    "revision predecessor is no longer a live task",
                    ErrorCode.STALE,
                )
            return claimed

    def release_fence(self, item: ClaimedRevisionFence, error: str) -> bool:
        with self.task_store._transaction() as connection:
            return (
                connection.execute(
                    """
                    UPDATE s85_revision_outbox
                    SET state=?, claimed_by=NULL, claim_token=NULL,
                        last_error=?, updated_at=?
                    WHERE outbox_id=? AND state=? AND claim_token=?
                    """,
                    (
                        RevisionOutboxState.PENDING.value,
                        error[:1_000],
                        utc_now(),
                        item.outbox_id,
                        RevisionOutboxState.CLAIMED.value,
                        item.claim_token,
                    ),
                ).rowcount
                == 1
            )

    def mark_fence_unknown(
        self, item: ClaimedRevisionFence, *, reason: str
    ) -> TaskRevisionReceipt:
        now = utc_now()
        with self.task_store._transaction() as connection:
            command_row = self._require_claimed_command(connection, item)
            prior = TaskRevisionReceipt.from_dict(
                _json_load(command_row["receipt_json"])
            )
            receipt = replace(
                prior,
                application_state=RevisionApplicationState.UNKNOWN,
            )
            connection.execute(
                """
                UPDATE s85_revision_commands
                SET application_state=?, receipt_json=?, updated_at=?
                WHERE scope_key=? AND command_id=?
                """,
                (
                    receipt.application_state.value,
                    _json_dump(receipt.to_dict()),
                    now,
                    _scope_key(item.scope),
                    item.request.command_id,
                ),
            )
            connection.execute(
                """
                UPDATE s85_revision_outbox
                SET state=?, claimed_by=NULL, claim_token=NULL,
                    last_error=?, updated_at=? WHERE outbox_id=?
                """,
                (
                    RevisionOutboxState.UNKNOWN.value,
                    reason[:1_000],
                    now,
                    item.outbox_id,
                ),
            )
            return receipt

    def complete_fence(
        self,
        item: ClaimedRevisionFence,
        ack: RevisionFenceAck,
    ) -> TaskRevisionReceipt:
        now = ack.acknowledged_at
        scope_key = _scope_key(item.scope)
        with self.task_store._transaction() as connection:
            command_row = self._require_claimed_command(connection, item)
            if (
                ack.command_id != item.request.command_id
                or ack.task_id != item.request.task_id
                or ack.predecessor_revision != item.request.predecessor_revision
                or ack.predecessor_attempt_id != item.request.predecessor_attempt_id
                or ack.executor_id != item.executor_id
                or ack.executor_ref != item.executor_ref
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_FENCE_ACK_MISMATCH",
                    "cleanup ACK does not bind the claimed predecessor",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if not ack.unapplied_changes_discarded:
                raise FormalTaskViolation(
                    "TASK_REVISION_CLEANUP_UNPROVEN",
                    "successor requires proof that predecessor changes were discarded",
                    ErrorCode.RESULT_UNKNOWN,
                )
            task = self.task_store._require_task_row(
                connection, item.request.task_id, item.scope
            )
            self.task_store._verify_durable_lineage(connection, task)
            if task["attempt_id"] != item.request.predecessor_attempt_id:
                raise FormalTaskViolation(
                    "TASK_REVISION_PRECONDITION_STALE",
                    "task current attempt changed before cleanup ACK",
                    ErrorCode.STALE,
                )
            if bool(task["cancel_requested"]) or task["state"] == (
                FormalTaskState.TERMINAL.value
            ):
                prior = TaskRevisionReceipt.from_dict(
                    _json_load(command_row["receipt_json"])
                )
                rejected = replace(
                    prior,
                    application_state=RevisionApplicationState.REJECTED,
                )
                connection.execute(
                    """
                    UPDATE s85_revision_commands
                    SET application_state=?, receipt_json=?, updated_at=?
                    WHERE scope_key=? AND command_id=?
                    """,
                    (
                        rejected.application_state.value,
                        _json_dump(rejected.to_dict()),
                        now,
                        scope_key,
                        item.request.command_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE s85_revision_outbox
                    SET state=?, claimed_by=NULL, claim_token=NULL,
                        last_error=?, updated_at=? WHERE outbox_id=?
                    """,
                    (
                        RevisionOutboxState.DELIVERED.value,
                        "TASK_REVISION_CANCEL_RACE",
                        now,
                        item.outbox_id,
                    ),
                )
                return rejected
            predecessor = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (item.request.predecessor_attempt_id,),
            ).fetchone()
            if (
                predecessor is None
                or predecessor["task_id"] != item.request.task_id
                or predecessor["executor_id"] != ack.executor_id
                or predecessor["executor_ref"] != ack.executor_ref
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_FENCE_ACK_MISMATCH",
                    "cleanup ACK does not bind the authoritative attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            attempt_number = int(predecessor["attempt_number"])
            plan = self._plan_from_json(command_row["plan_json"])
            if (
                plan.task_id != task["task_id"]
                or plan.predecessor_revision != item.request.predecessor_revision
                or plan.predecessor_attempt_id != predecessor["attempt_id"]
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "stored plan does not bind the claimed predecessor",
                    ErrorCode.INTERNAL,
                )
            predecessor_revision_row = connection.execute(
                """
                SELECT * FROM s85_task_revisions
                WHERE task_id=? AND task_revision=?
                """,
                (task["task_id"], plan.predecessor_revision),
            ).fetchone()
            if predecessor_revision_row is None:
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "revision plan predecessor is missing",
                    ErrorCode.INTERNAL,
                )
            predecessor_revision = self._revision_from_row(predecessor_revision_row)
            fenced_terminal = self._read_fenced_terminal_observation(
                connection,
                task=task,
                predecessor=predecessor,
            )
            if fenced_terminal is not None:
                assert fenced_terminal.attempt_outcome is not None
                previous_outcome = fenced_terminal.attempt_outcome.value
                connection.execute(
                    """
                    UPDATE attempts SET state=?, outcome=?, updated_at=?
                    WHERE attempt_id=?
                    """,
                    (
                        FormalAttemptState.TERMINAL.value,
                        previous_outcome,
                        now,
                        predecessor["attempt_id"],
                    ),
                )
                self._append_fenced_terminal_observation(
                    connection,
                    task=task,
                    observation=fenced_terminal,
                )
                task = self.task_store._require_task_row(
                    connection, item.request.task_id, item.scope
                )
            elif predecessor["state"] != FormalAttemptState.TERMINAL.value:
                previous_outcome = TerminalOutcome.INTERRUPTED.value
                connection.execute(
                    """
                    UPDATE attempts SET state=?, outcome=?, updated_at=?
                    WHERE attempt_id=?
                    """,
                    (
                        FormalAttemptState.TERMINAL.value,
                        TerminalOutcome.INTERRUPTED.value,
                        now,
                        predecessor["attempt_id"],
                    ),
                )
                self.task_store._append_event(
                    connection,
                    task,
                    event_type="attempt.terminal",
                    state=FormalAttemptState.TERMINAL.value,
                    outcome=TerminalOutcome.INTERRUPTED.value,
                    producer="task_core.revision",
                    source_event_id=None,
                    causation_id=ack.cleanup_id,
                    occurred_at=now,
                    details={
                        "reason": "TASK_REVISION_PREDECESSOR_FENCED",
                        "command_id": ack.command_id,
                        "task_revision": plan.predecessor_revision,
                    },
                )
                task = self.task_store._require_task_row(
                    connection, item.request.task_id, item.scope
                )
            else:
                previous_outcome = predecessor["outcome"]
            self._hit("revision.complete.after_predecessor")
            spec = FormalTaskSpec.from_dict(_json_load(task["spec_json"]))
            successor_spec = replace(spec, instruction=plan.effective_instruction)
            successor_attempt_id = f"attempt-{uuid.uuid4().hex}"
            dispatch_outbox_id = f"revision-dispatch-{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, task_id, attempt_number, executor_id, executor_ref,
                    state, outcome, source_seq, updated_at
                ) VALUES(?, ?, ?, ?, NULL, ?, NULL, -1, ?)
                """,
                (
                    successor_attempt_id,
                    task["task_id"],
                    attempt_number + 1,
                    successor_spec.executor_id,
                    FormalAttemptState.ACCEPTED.value,
                    now,
                ),
            )
            self._hit("revision.complete.after_successor_attempt")
            connection.execute(
                """
                UPDATE tasks SET spec_json=?, state=?, outcome=NULL, attempt_id=?,
                    cancel_requested=0, dispatch_fenced=0, updated_at=?,
                    reconciliation_state=NULL, reconciliation_reason=NULL
                WHERE task_id=?
                """,
                (
                    _json_dump(successor_spec.to_dict()),
                    FormalTaskState.ACCEPTED.value,
                    successor_attempt_id,
                    now,
                    task["task_id"],
                ),
            )
            self._hit("revision.complete.after_task_pointer")
            current_task = self.task_store._require_task_row(
                connection, item.request.task_id, item.scope
            )
            self.task_store._append_event(
                connection,
                current_task,
                event_type="task.revision_applied",
                state=FormalTaskState.ACCEPTED.value,
                outcome=None,
                producer="task_core",
                source_event_id=None,
                causation_id=ack.command_id,
                occurred_at=now,
                details={
                    "command_id": ack.command_id,
                    "predecessor_attempt_id": ack.predecessor_attempt_id,
                    "predecessor_revision": ack.predecessor_revision,
                    "previous_outcome": previous_outcome,
                    "task_revision": plan.successor_revision,
                    "attempt_number": attempt_number + 1,
                    "cleanup_id": ack.cleanup_id,
                },
            )
            self._hit("revision.complete.after_boundary_event")
            connection.execute(
                """
                INSERT INTO s85_revision_dispatch_outbox(
                    outbox_id, scope_key, command_id, task_id, attempt_id,
                    payload_json, state, delivery_count, claimed_by, claim_token,
                    last_error, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?, ?)
                """,
                (
                    dispatch_outbox_id,
                    scope_key,
                    ack.command_id,
                    task["task_id"],
                    successor_attempt_id,
                    _json_dump(
                        {
                            "scope": item.scope.to_dict(),
                            "spec": successor_spec.to_dict(),
                        }
                    ),
                    OutboxState.PENDING.value,
                    now,
                    now,
                ),
            )
            self._hit("revision.complete.after_dispatch_outbox")
            revision = TaskRevisionRecord(
                task_id=task["task_id"],
                task_revision=plan.successor_revision,
                predecessor_revision=plan.predecessor_revision,
                attempt_id=successor_attempt_id,
                base_instruction=predecessor_revision.base_instruction,
                additive_facts=plan.additive_facts,
                constraints=plan.constraints,
                origin_commit_id=TaskRevisionCommand.from_dict(
                    _json_load(command_row["command_json"])
                ).origin_commit_id,
                created_by_command_id=ack.command_id,
            )
            self._insert_revision(
                connection, revision, scope_key=scope_key, created_at=now
            )
            self._hit("revision.complete.after_successor_revision")
            prior = TaskRevisionReceipt.from_dict(
                _json_load(command_row["receipt_json"])
            )
            receipt = replace(
                prior,
                application_state=RevisionApplicationState.APPLIED,
                successor_attempt_id=successor_attempt_id,
                dispatch_outbox_id=dispatch_outbox_id,
            )
            ack_payload = {
                "command_id": ack.command_id,
                "task_id": ack.task_id,
                "predecessor_revision": ack.predecessor_revision,
                "predecessor_attempt_id": ack.predecessor_attempt_id,
                "executor_id": ack.executor_id,
                "executor_ref": ack.executor_ref,
                "cleanup_id": ack.cleanup_id,
                "checkout_identity": ack.checkout_identity,
                "unapplied_changes_discarded": ack.unapplied_changes_discarded,
                "acknowledged_at": ack.acknowledged_at,
            }
            connection.execute(
                """
                INSERT INTO s85_revision_fence_acks(
                    scope_key, command_id, ack_json, created_at
                ) VALUES(?, ?, ?, ?)
                """,
                (scope_key, ack.command_id, _json_dump(ack_payload), now),
            )
            self._hit("revision.complete.after_cleanup_ack")
            connection.execute(
                """
                UPDATE s85_revision_commands
                SET application_state=?, receipt_json=?, updated_at=?
                WHERE scope_key=? AND command_id=?
                """,
                (
                    receipt.application_state.value,
                    _json_dump(receipt.to_dict()),
                    now,
                    scope_key,
                    ack.command_id,
                ),
            )
            self._hit("revision.complete.after_command")
            connection.execute(
                """
                UPDATE s85_revision_outbox
                SET state=?, claimed_by=NULL, claim_token=NULL, last_error=NULL,
                    updated_at=? WHERE outbox_id=?
                """,
                (
                    RevisionOutboxState.DELIVERED.value,
                    now,
                    item.outbox_id,
                ),
            )
            self._hit("revision.complete.after_fence_outbox")
            return receipt

    @staticmethod
    def _read_fenced_terminal_observation(
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        predecessor: sqlite3.Row,
    ) -> ExecutorObservation | None:
        """Return the exact quarantined terminal fact, if one was observed."""

        source = connection.execute(
            """
            SELECT source_event_id, canonical FROM executor_events
            WHERE attempt_id=? AND source_seq=?
            """,
            (predecessor["attempt_id"], predecessor["source_seq"]),
        ).fetchone()
        if source is None:
            return None
        payload = _json_load(source["canonical"])
        expected_fields = {
            "resolution",
            "executor_id",
            "executor_ref",
            "task_id",
            "attempt_id",
            "source_event_id",
            "source_seq",
            "attempt_state",
            "attempt_outcome",
            "occurred_at",
            "raw_status",
            "summary",
            "error",
        }
        try:
            if type(payload) is not dict or set(payload) != expected_fields:
                raise ValueError("non-canonical Executor observation")
            outcome = payload["attempt_outcome"]
            observation = ExecutorObservation(
                resolution=ExecutorResolution(payload["resolution"]),
                executor_id=payload["executor_id"],
                executor_ref=payload["executor_ref"],
                task_id=payload["task_id"],
                attempt_id=payload["attempt_id"],
                source_event_id=payload["source_event_id"],
                source_seq=payload["source_seq"],
                attempt_state=FormalAttemptState(payload["attempt_state"]),
                attempt_outcome=(None if outcome is None else TerminalOutcome(outcome)),
                occurred_at=payload["occurred_at"],
                raw_status=payload["raw_status"],
                summary=payload["summary"],
                error=payload["error"],
            )
        except (FormalTaskViolation, TypeError, ValueError) as error:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "fenced predecessor Executor fact is malformed",
                ErrorCode.INTERNAL,
            ) from error
        if (
            observation.resolution is not ExecutorResolution.KNOWN
            or observation.task_id != task["task_id"]
            or observation.attempt_id != predecessor["attempt_id"]
            or observation.executor_id != predecessor["executor_id"]
            or observation.executor_ref != predecessor["executor_ref"]
            or observation.source_event_id != source["source_event_id"]
            or observation.source_seq != predecessor["source_seq"]
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "fenced predecessor Executor fact does not bind its attempt",
                ErrorCode.INTERNAL,
            )
        return (
            observation
            if observation.attempt_state is FormalAttemptState.TERMINAL
            else None
        )

    def _append_fenced_terminal_observation(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        observation: ExecutorObservation,
    ) -> None:
        """Materialize a quarantined terminal fact inside the revision commit.

        While a fence is pending, the base Store records the Executor fact but
        deliberately does not append a TaskEvent or change current Task truth.
        Once cleanup succeeds, the predecessor is no longer the current
        attempt, so its exact terminal diagnostic can safely join durable
        lineage immediately before the successor boundary.
        """

        if (
            observation.attempt_state is not FormalAttemptState.TERMINAL
            or observation.attempt_outcome is None
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "fenced predecessor terminal fact is not terminal",
                ErrorCode.INTERNAL,
            )
        existing = connection.execute(
            """
            SELECT * FROM task_events
            WHERE task_id=? AND attempt_id=? AND event_type='attempt.terminal'
            """,
            (task["task_id"], observation.attempt_id),
        ).fetchall()
        if existing:
            if (
                len(existing) != 1
                or existing[0]["state"] != FormalAttemptState.TERMINAL.value
                or existing[0]["outcome"] != observation.attempt_outcome.value
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "predecessor terminal event disagrees with its attempt",
                    ErrorCode.INTERNAL,
                )
            return
        self.task_store._append_event(
            connection,
            task,
            event_type="attempt.terminal",
            state=FormalAttemptState.TERMINAL.value,
            outcome=observation.attempt_outcome.value,
            producer=observation.executor_id,
            source_event_id=observation.source_event_id,
            causation_id=observation.source_event_id,
            occurred_at=observation.occurred_at,
            details={
                "raw_status": observation.raw_status,
                "summary": observation.summary,
                "error": observation.error,
            },
        )

    @staticmethod
    def _dispatch_item(
        row: sqlite3.Row,
        *,
        state: OutboxState = OutboxState.CLAIMED,
        claim_token: str | None,
    ) -> PersistentOutboxItem:
        payload = _json_load(row["payload_json"])
        if type(payload) is not dict or set(payload) != {"scope", "spec"}:
            raise FormalTaskViolation(
                "TASK_REVISION_STORE_CORRUPT",
                "revision dispatch payload is malformed",
                ErrorCode.INTERNAL,
            )
        scope = ScopeRef.from_dict(payload["scope"])
        spec = FormalTaskSpec.from_dict(payload["spec"])
        if spec.context.scope != scope:
            raise FormalTaskViolation(
                "TASK_REVISION_DISPATCH_BINDING_MISMATCH",
                "revision dispatch scope and spec disagree",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        return PersistentOutboxItem(
            outbox_id=row["outbox_id"],
            kind=OutboxKind.ATTEMPT_DISPATCH,
            task_id=row["task_id"],
            attempt_id=row["attempt_id"],
            command_id=row["command_id"],
            scope=scope,
            spec=spec,
            executor_ref=None,
            source_seq=-1,
            state=state,
            delivery_count=int(row["delivery_count"]),
            claim_token=claim_token,
        )

    def claim_successor_dispatch(
        self, worker_id: str
    ) -> ClaimedRevisionDispatch | None:
        if type(worker_id) is not str or not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        token = uuid.uuid4().hex
        now = utc_now()
        with self.task_store._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM s85_revision_dispatch_outbox WHERE state=?
                ORDER BY created_at, outbox_id LIMIT 1
                """,
                (OutboxState.PENDING.value,),
            ).fetchone()
            if row is None:
                return None
            item = self._dispatch_item(row, claim_token=token)
            task = self.task_store._require_task_row(
                connection, item.task_id, item.scope
            )
            self.task_store._verify_durable_lineage(connection, task)
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (item.attempt_id,),
            ).fetchone()
            if (
                task["attempt_id"] != item.attempt_id
                or task["state"] != FormalTaskState.ACCEPTED.value
                or bool(task["cancel_requested"])
                or attempt is None
                or attempt["task_id"] != item.task_id
                or attempt["executor_id"] != item.spec.executor_id
                or attempt["executor_ref"] is not None
                or attempt["state"] != FormalAttemptState.ACCEPTED.value
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_DISPATCH_BINDING_MISMATCH",
                    "revision successor dispatch is not the exact accepted attempt",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            changed = connection.execute(
                """
                UPDATE s85_revision_dispatch_outbox
                SET state=?, delivery_count=delivery_count+1,
                    claimed_by=?, claim_token=?, updated_at=?
                WHERE outbox_id=? AND state=?
                """,
                (
                    OutboxState.CLAIMED.value,
                    worker_id,
                    token,
                    now,
                    row["outbox_id"],
                    OutboxState.PENDING.value,
                ),
            ).rowcount
            if changed != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM s85_revision_dispatch_outbox WHERE outbox_id=?",
                (row["outbox_id"],),
            ).fetchone()
            assert claimed is not None
            return ClaimedRevisionDispatch(
                self._dispatch_item(claimed, claim_token=token)
            )

    def release_successor_dispatch(
        self, claimed: ClaimedRevisionDispatch, *, error: str
    ) -> bool:
        item = claimed.item
        with self.task_store._transaction() as connection:
            return (
                connection.execute(
                    """
                    UPDATE s85_revision_dispatch_outbox
                    SET state=?, claimed_by=NULL, claim_token=NULL,
                        last_error=?, updated_at=?
                    WHERE outbox_id=? AND state=? AND claim_token=?
                    """,
                    (
                        OutboxState.PENDING.value,
                        error[:1_000],
                        utc_now(),
                        item.outbox_id,
                        OutboxState.CLAIMED.value,
                        item.claim_token,
                    ),
                ).rowcount
                == 1
            )

    def complete_successor_dispatch(
        self,
        claimed: ClaimedRevisionDispatch,
        delivery: ExecutorDeliveryResult,
    ) -> None:
        item = claimed.item
        with self.task_store._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM s85_revision_dispatch_outbox WHERE outbox_id=?",
                (item.outbox_id,),
            ).fetchone()
            if (
                row is None
                or row["state"] != OutboxState.CLAIMED.value
                or row["claim_token"] != item.claim_token
                or row["task_id"] != item.task_id
                or row["attempt_id"] != item.attempt_id
                or row["command_id"] != item.command_id
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_DISPATCH_CLAIM_LOST",
                    "only the exact claimed successor dispatch can complete",
                    ErrorCode.CONFLICT,
                )
            task = self.task_store._require_task_row(
                connection, item.task_id, item.scope
            )
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (item.attempt_id,),
            ).fetchone()
            if (
                task["attempt_id"] != item.attempt_id
                or attempt is None
                or attempt["task_id"] != item.task_id
                or attempt["executor_id"] != item.spec.executor_id
                or attempt["executor_ref"] not in {None, delivery.executor_ref}
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_DISPATCH_BINDING_MISMATCH",
                    "Executor delivery does not bind the current successor",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if any(
                observation.executor_ref != delivery.executor_ref
                or observation.task_id != item.task_id
                or observation.attempt_id != item.attempt_id
                or observation.executor_id != item.spec.executor_id
                for observation in delivery.observations
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_DISPATCH_BINDING_MISMATCH",
                    "successor observations do not bind one Executor delivery",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            connection.execute(
                "UPDATE attempts SET executor_ref=?, updated_at=? WHERE attempt_id=?",
                (delivery.executor_ref, utc_now(), item.attempt_id),
            )
            for observation in delivery.observations:
                self.task_store._apply_observation(connection, observation)
            connection.execute(
                """
                UPDATE s85_revision_dispatch_outbox
                SET state=?, claimed_by=NULL, claim_token=NULL, last_error=NULL,
                    updated_at=? WHERE outbox_id=?
                """,
                (OutboxState.DELIVERED.value, utc_now(), item.outbox_id),
            )

    def pending_execution_items(
        self, *, limit: int = 1
    ) -> tuple[PersistentOutboxItem, ...]:
        """Read durable dispatched successors that still need verifier ACKs.

        Verification itself is read-only and the resulting ACK insert is
        idempotent.  Keeping this queue derivable from the delivered dispatch
        ledger makes a process restart resume verification without another
        mutable queue or a client-supplied attempt identity.
        """

        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("limit must be between 1 and 32")
        with self.task_store._reader() as connection:
            connection.execute("BEGIN")
            self._verify_schema(connection)
            rows = connection.execute(
                """
                SELECT d.*
                FROM s85_revision_dispatch_outbox AS d
                JOIN s85_task_revisions AS r
                  ON r.task_id=d.task_id AND r.attempt_id=d.attempt_id
                LEFT JOIN s85_revision_execution_acks AS a
                  ON a.task_id=r.task_id AND a.task_revision=r.task_revision
                WHERE d.state=? AND a.task_id IS NULL
                ORDER BY d.created_at, d.outbox_id
                LIMIT ?
                """,
                (OutboxState.DELIVERED.value, limit),
            ).fetchall()
            return tuple(
                self._dispatch_item(
                    row,
                    state=OutboxState.DELIVERED,
                    claim_token=None,
                )
                for row in rows
            )

    def record_execution_ack(
        self,
        scope: ScopeRef,
        ack: TaskRevisionExecutionAck,
        *,
        observed_at: str | None = None,
    ) -> TaskRevisionExecutionAck:
        """Persist one exact successor result without rewriting Task outcome."""

        if type(ack) is not TaskRevisionExecutionAck:
            raise TypeError("ack must be an exact TaskRevisionExecutionAck")
        now = observed_at or utc_now()
        scope_key = _scope_key(scope)
        payload = _json_dump(ack.to_dict())
        with self.task_store._transaction() as connection:
            self._verify_schema(connection)
            task = self.task_store._require_task_row(connection, ack.task_id, scope)
            self.task_store._verify_durable_lineage(connection, task)
            revision_row = connection.execute(
                """
                SELECT * FROM s85_task_revisions
                WHERE task_id=? AND task_revision=? AND scope_key=?
                """,
                (ack.task_id, ack.task_revision, scope_key),
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (ack.attempt_id,),
            ).fetchone()
            cleanup_row = connection.execute(
                """
                SELECT ack_json FROM s85_revision_fence_acks
                WHERE scope_key=? AND command_id=(
                    SELECT command_id FROM s85_task_revisions
                    WHERE task_id=? AND task_revision=?)
                """,
                (scope_key, ack.task_id, ack.task_revision),
            ).fetchone()
            if (
                revision_row is None
                or revision_row["attempt_id"] != ack.attempt_id
                or task["attempt_id"] != ack.attempt_id
                or attempt is None
                or attempt["task_id"] != ack.task_id
                or attempt["executor_ref"] != ack.executor_ref
                or attempt["state"] != FormalAttemptState.TERMINAL.value
                or cleanup_row is None
                or self._ack_from_json(cleanup_row["ack_json"]).checkout_identity
                != ack.fixture_identity
                or ack.execution_ack
                != (attempt["outcome"] == TerminalOutcome.COMPLETED.value)
                or ack.verified_success
                and (
                    task["state"] != FormalTaskState.TERMINAL.value
                    or task["outcome"] != TerminalOutcome.COMPLETED.value
                )
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_EXECUTION_ACK_MISMATCH",
                    "execution ACK does not bind current terminal revision truth",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            existing = connection.execute(
                """
                SELECT ack_json FROM s85_revision_execution_acks
                WHERE task_id=? AND task_revision=?
                """,
                (ack.task_id, ack.task_revision),
            ).fetchone()
            if existing is not None:
                prior = self._execution_ack_from_json(existing["ack_json"])
                if prior != ack:
                    raise FormalTaskViolation(
                        "TASK_REVISION_EXECUTION_ACK_CONFLICT",
                        "one revision cannot change its execution result",
                        ErrorCode.CONFLICT,
                    )
                return prior
            connection.execute(
                """
                INSERT INTO s85_revision_execution_acks(
                    scope_key, task_id, task_revision, attempt_id, executor_ref,
                    ack_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_key,
                    ack.task_id,
                    ack.task_revision,
                    ack.attempt_id,
                    ack.executor_ref,
                    payload,
                    now,
                ),
            )
            self._hit("revision.execution.after_ack")
            self.task_store._append_event(
                connection,
                task,
                event_type="task.revision_execution_recorded",
                state=task["state"],
                outcome=task["outcome"],
                producer="task_core.revision_verifier",
                source_event_id=None,
                causation_id=ack.attempt_id,
                occurred_at=now,
                details={
                    "task_revision": ack.task_revision,
                    "attempt_id": ack.attempt_id,
                    "execution_ack": ack.execution_ack,
                    "changed_path_count": len(ack.changed_paths),
                    "diff_summary": ack.diff_summary,
                    "verifier_id": ack.verifier.verifier_id,
                    "verifier_result": ack.verifier.result.value,
                    "cleanup_state": ack.cleanup_state,
                    "forbidden_side_effect_count": (ack.forbidden_side_effect_count),
                    "verified_success": ack.verified_success,
                },
            )
            return ack

    @staticmethod
    def _require_claimed_command(
        connection: sqlite3.Connection, item: ClaimedRevisionFence
    ) -> sqlite3.Row:
        outbox = connection.execute(
            "SELECT * FROM s85_revision_outbox WHERE outbox_id=?",
            (item.outbox_id,),
        ).fetchone()
        if (
            outbox is None
            or outbox["state"] != RevisionOutboxState.CLAIMED.value
            or outbox["claim_token"] != item.claim_token
            or outbox["scope_key"] != _scope_key(item.scope)
            or outbox["command_id"] != item.request.command_id
            or outbox["task_id"] != item.request.task_id
            or outbox["predecessor_attempt_id"] != item.request.predecessor_attempt_id
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_OUTBOX_CLAIM_LOST",
                "only the exact claimed revision fence can complete",
                ErrorCode.CONFLICT,
            )
        command = connection.execute(
            """
            SELECT * FROM s85_revision_commands
            WHERE scope_key=? AND command_id=?
            """,
            (_scope_key(item.scope), item.request.command_id),
        ).fetchone()
        if (
            command is None
            or command["application_state"] != RevisionApplicationState.FENCING.value
            or command["task_id"] != item.request.task_id
            or command["predecessor_revision"] != item.request.predecessor_revision
            or command["predecessor_attempt_id"] != item.request.predecessor_attempt_id
        ):
            raise FormalTaskViolation(
                "TASK_REVISION_OUTBOX_BINDING_MISMATCH",
                "revision command and fence outbox do not share one predecessor",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        return command

    def truth(self, task_id: str, scope: ScopeRef) -> TaskRevisionTruth:
        with self.task_store._reader() as connection:
            connection.execute("BEGIN")
            self._verify_schema(connection)
            task_row = self.task_store._require_task_row(connection, task_id, scope)
            self.task_store._verify_durable_lineage(connection, task_row)
            attempt_row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (task_row["attempt_id"],),
            ).fetchone()
            revision_rows = connection.execute(
                """
                SELECT * FROM s85_task_revisions
                WHERE task_id=? AND scope_key=? ORDER BY task_revision
                """,
                (task_id, _scope_key(scope)),
            ).fetchall()
            if attempt_row is None or not revision_rows:
                raise FormalTaskViolation(
                    "TASK_REVISION_TRUTH_UNAVAILABLE",
                    "task has no initialized S8.5 revision truth",
                    ErrorCode.NOT_FOUND,
                )
            revisions = tuple(self._revision_from_row(row) for row in revision_rows)
            if (
                tuple(record.task_revision for record in revisions)
                != tuple(range(1, len(revisions) + 1))
                or len(revisions) > 2
                or revisions[-1].attempt_id != task_row["attempt_id"]
            ):
                raise FormalTaskViolation(
                    "TASK_REVISION_STORE_CORRUPT",
                    "current task attempt disagrees with contiguous revision lineage",
                    ErrorCode.INTERNAL,
                )
            pending_row = connection.execute(
                """
                SELECT receipt_json FROM s85_revision_commands
                WHERE task_id=? AND application_state IN (?, ?)
                ORDER BY created_at DESC LIMIT 1
                """,
                (
                    task_id,
                    RevisionApplicationState.FENCING.value,
                    RevisionApplicationState.UNKNOWN.value,
                ),
            ).fetchone()
            pending = (
                None
                if pending_row is None
                else TaskRevisionReceipt.from_dict(
                    _json_load(pending_row["receipt_json"])
                )
            )
            ack_row = connection.execute(
                """
                SELECT ack_json FROM s85_revision_fence_acks
                WHERE scope_key=? AND command_id=(
                    SELECT command_id FROM s85_task_revisions
                    WHERE task_id=? ORDER BY task_revision DESC LIMIT 1)
                """,
                (_scope_key(scope), task_id),
            ).fetchone()
            execution_row = connection.execute(
                """
                SELECT ack_json FROM s85_revision_execution_acks
                WHERE scope_key=? AND task_id=? AND task_revision=?
                """,
                (_scope_key(scope), task_id, revisions[-1].task_revision),
            ).fetchone()
            return TaskRevisionTruth(
                task=self.task_store._task_from_row(task_row),
                attempt=self.task_store._attempt_from_row(attempt_row),
                current_revision=revisions[-1],
                revisions=revisions,
                pending_receipt=pending,
                cleanup_ack=(
                    None
                    if ack_row is None
                    else self._ack_from_json(ack_row["ack_json"])
                ),
                execution_ack=(
                    None
                    if execution_row is None
                    else self._execution_ack_from_json(execution_row["ack_json"])
                ),
            )


__all__ = [
    "ClaimedRevisionDispatch",
    "ClaimedRevisionFence",
    "RevisionOutboxState",
    "SqliteTaskRevisionStore",
    "TaskRevisionReceipt",
    "TaskRevisionTruth",
]
