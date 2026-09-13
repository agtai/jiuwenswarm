# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Host input provenance and notification receipts extending SDK Work storage.

Work checkpoint CAS/recovery has a single SDK owner. These extra tables bind
application input and presentation facts; they cannot create execution success.
"""

from __future__ import annotations
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from openjiuwen.core.application.tasks.contracts import (
    ErrorCode,
    ScopeRef,
    canonical_json_bytes,
)
from openjiuwen.core.application.tasks.work_runtime import (
    WorkViolation as NativeWorkViolation,
)
from openjiuwen.core.application.tasks.work_store import (
    SqliteWorkStore,
    _digest,
    _scope_digest,
    verify_work_tables,
)

_SCHEMA_VERSION = 1

_SUPPRESSION_REASONS = frozenset({"speech_interrupted", "superseded"})

_APPLICATION_COLUMNS = {
    "native_work_presentation": (
        ("schema_version", "INTEGER", 0),
        ("scope_sha256", "TEXT", 1),
        ("event_id", "TEXT", 2),
        ("presented_at", "TEXT", 0),
        ("fact_sha256", "TEXT", 0),
    ),
    "native_work_suppression": (
        ("schema_version", "INTEGER", 0),
        ("scope_sha256", "TEXT", 1),
        ("event_id", "TEXT", 2),
        ("reason", "TEXT", 0),
        ("recorded_at", "TEXT", 0),
        ("fact_sha256", "TEXT", 0),
    ),
    "native_business_task_origin": (
        ("schema_version", "INTEGER", 0),
        ("scope_sha256", "TEXT", 1),
        ("task_id", "TEXT", 2),
        ("source_identity", "TEXT", 0),
        ("commit_id", "TEXT", 0),
        ("recorded_at", "TEXT", 0),
        ("fact_sha256", "TEXT", 0),
    ),
}


def _event_identity(event_id: str) -> str:
    try:
        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or len(event_id.encode("utf-8")) > 256
        ):
            raise ValueError("invalid event id")
    except (ValueError, UnicodeEncodeError) as error:
        raise NativeWorkViolation(
            "NATIVE_WORK_PRESENTATION_ID_INVALID", "invalid presentation event identity"
        ) from error
    return event_id


def _origin_identity(task_id: str, source_identity: str, commit_id: str) -> None:
    try:
        for value in (task_id, commit_id):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value.encode("utf-8")) > 256
            ):
                raise ValueError("invalid task origin identity")
        if (
            not isinstance(source_identity, str)
            or not source_identity.startswith("native-business:")
            or len(source_identity) != len("native-business:") + 64
            or any(
                c not in "0123456789abcdef"
                for c in source_identity[len("native-business:") :]
            )
        ):
            raise ValueError("invalid Native source identity")
    except (ValueError, UnicodeEncodeError) as error:
        raise NativeWorkViolation(
            "NATIVE_TASK_ORIGIN_INVALID", "invalid task creation origin data"
        ) from error


class SqliteNativeWorkJournal(SqliteWorkStore):
    """Application extensions validated atomically with the SDK checkpoints."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        max_records: int = 128,
        max_presentations: int = 4096,
        max_task_origins: int = 4096,
    ) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (max_records, max_presentations, max_task_origins)
        ):
            raise NativeWorkViolation(
                "NATIVE_WORK_JOURNAL_BOUNDS_INVALID",
                "journal bounds must be positive integers",
            )
        self._max_presentations = max_presentations
        self._max_task_origins = max_task_origins
        super().__init__(database_path, max_records=max_records)

    def _initialize_application_schema(self, connection: sqlite3.Connection) -> None:
        self._require_input_journal(connection)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS native_work_presentation (
                schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                scope_sha256 TEXT NOT NULL,
                event_id TEXT NOT NULL,
                presented_at TEXT NOT NULL,
                fact_sha256 TEXT NOT NULL,
                PRIMARY KEY(scope_sha256, event_id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS native_work_suppression (
                schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                scope_sha256 TEXT NOT NULL,
                event_id TEXT NOT NULL,
                reason TEXT NOT NULL CHECK(reason IN ('speech_interrupted', 'superseded')),
                recorded_at TEXT NOT NULL,
                fact_sha256 TEXT NOT NULL,
                PRIMARY KEY(scope_sha256, event_id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS native_business_task_origin (
                schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                scope_sha256 TEXT NOT NULL,
                task_id TEXT NOT NULL,
                source_identity TEXT NOT NULL,
                commit_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                fact_sha256 TEXT NOT NULL,
                PRIMARY KEY(scope_sha256, task_id)
            )
        """)

    def _verify_application_schema(self, connection: sqlite3.Connection) -> None:
        self._require_input_journal(connection)
        verify_work_tables(connection, _APPLICATION_COLUMNS)

    """Bounded additive tables; exact sequence CAS and no automatic replay."""

    @staticmethod
    def _require_input_journal(connection: sqlite3.Connection) -> None:
        if (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='unified_committed_inputs'"
            ).fetchone()
            is None
        ):
            raise NativeWorkViolation(
                "NATIVE_WORK_INPUT_JOURNAL_REQUIRED",
                "Native work must share the committed input journal database",
                ErrorCode.UNAVAILABLE,
            )

    def presented(self, event_id: str, scope: ScopeRef) -> bool:
        event_id, scope_sha = _event_identity(event_id), _scope_digest(scope)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_work_presentation WHERE scope_sha256=? AND event_id=?",
                (scope_sha, event_id),
            ).fetchone()
            if row is not None:
                self._verify_presentation(row)
            return row is not None

    @staticmethod
    def _verify_presentation(row: sqlite3.Row) -> None:
        try:
            observed = datetime.fromisoformat(
                row["presented_at"].replace("Z", "+00:00")
            )
            payload = {
                key: row[key]
                for key in (
                    "schema_version",
                    "scope_sha256",
                    "event_id",
                    "presented_at",
                )
            }
            if (
                row["schema_version"] != _SCHEMA_VERSION
                or observed.tzinfo is None
                or _digest(canonical_json_bytes(payload)) != row["fact_sha256"]
            ):
                raise ValueError("invalid presentation fact")
        except (ValueError, TypeError, AttributeError) as error:
            raise NativeWorkViolation(
                "NATIVE_WORK_PRESENTATION_CORRUPT",
                "presentation fact integrity failed",
                ErrorCode.UNAVAILABLE,
            ) from error

    def mark_presented(self, event_id: str, scope: ScopeRef) -> bool:
        """Record an actual ACK supplied by Main's presentation owner, once."""
        event_id, scope_sha = _event_identity(event_id), _scope_digest(scope)
        with self._connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM native_work_presentation WHERE scope_sha256=? AND event_id=?",
                (scope_sha, event_id),
            ).fetchone()
            if row is not None:
                self._verify_presentation(row)
                return False
            count = connection.execute(
                "SELECT COUNT(*) FROM native_work_presentation"
            ).fetchone()[0]
            if count >= self._max_presentations:
                raise NativeWorkViolation(
                    "NATIVE_WORK_PRESENTATION_LEDGER_FULL",
                    "bounded presentation journal is full",
                    ErrorCode.UNAVAILABLE,
                )
            now = (
                datetime.now(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            fact_sha = _digest(
                canonical_json_bytes(
                    {
                        "schema_version": _SCHEMA_VERSION,
                        "scope_sha256": scope_sha,
                        "event_id": event_id,
                        "presented_at": now,
                    }
                )
            )
            connection.execute(
                "INSERT INTO native_work_presentation VALUES(?,?,?,?,?)",
                (_SCHEMA_VERSION, scope_sha, event_id, now, fact_sha),
            )
            return True

    @staticmethod
    def _verify_suppression(row: sqlite3.Row) -> None:
        try:
            observed = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
            payload = {
                key: row[key]
                for key in (
                    "schema_version",
                    "scope_sha256",
                    "event_id",
                    "reason",
                    "recorded_at",
                )
            }
            if (
                row["schema_version"] != _SCHEMA_VERSION
                or observed.tzinfo is None
                or row["reason"] not in _SUPPRESSION_REASONS
                or _digest(canonical_json_bytes(payload)) != row["fact_sha256"]
            ):
                raise ValueError("invalid suppression fact")
        except (ValueError, TypeError, AttributeError) as error:
            raise NativeWorkViolation(
                "NATIVE_WORK_SUPPRESSION_CORRUPT",
                "suppression fact integrity failed",
                ErrorCode.UNAVAILABLE,
            ) from error

    def suppressed(self, event_id: str, scope: ScopeRef) -> bool:
        """Whether automatic delivery was stopped; this says nothing was heard."""
        event_id, scope_sha = _event_identity(event_id), _scope_digest(scope)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM native_work_suppression WHERE scope_sha256=? AND event_id=?",
                (scope_sha, event_id),
            ).fetchone()
            if row is not None:
                self._verify_suppression(row)
            return row is not None

    def mark_suppressed(self, event_id: str, scope: ScopeRef, reason: str) -> bool:
        """Record Main's exact STOP/supersession fact, never a presentation ACK."""
        event_id, scope_sha = _event_identity(event_id), _scope_digest(scope)
        if not isinstance(reason, str) or reason not in _SUPPRESSION_REASONS:
            raise NativeWorkViolation(
                "NATIVE_WORK_SUPPRESSION_REASON_INVALID",
                "unsupported delivery suppression reason",
            )
        with self._connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM native_work_suppression WHERE scope_sha256=? AND event_id=?",
                (scope_sha, event_id),
            ).fetchone()
            if row is not None:
                self._verify_suppression(row)
                if row["reason"] != reason:
                    raise NativeWorkViolation(
                        "NATIVE_WORK_SUPPRESSION_CONFLICT",
                        "suppression fact cannot change its recorded reason",
                        ErrorCode.CONFLICT,
                    )
                return False
            count = connection.execute(
                "SELECT COUNT(*) FROM native_work_suppression"
            ).fetchone()[0]
            if count >= self._max_presentations:
                raise NativeWorkViolation(
                    "NATIVE_WORK_SUPPRESSION_LEDGER_FULL",
                    "bounded suppression journal is full",
                    ErrorCode.UNAVAILABLE,
                )
            now = (
                datetime.now(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            payload = {
                "schema_version": _SCHEMA_VERSION,
                "scope_sha256": scope_sha,
                "event_id": event_id,
                "reason": reason,
                "recorded_at": now,
            }
            connection.execute(
                "INSERT INTO native_work_suppression VALUES(?,?,?,?,?,?)",
                (
                    _SCHEMA_VERSION,
                    scope_sha,
                    event_id,
                    reason,
                    now,
                    _digest(canonical_json_bytes(payload)),
                ),
            )
            return True

    @staticmethod
    def _verify_task_origin(row: sqlite3.Row) -> None:
        try:
            _origin_identity(row["task_id"], row["source_identity"], row["commit_id"])
            observed = datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
            payload = {
                key: row[key]
                for key in (
                    "schema_version",
                    "scope_sha256",
                    "task_id",
                    "source_identity",
                    "commit_id",
                    "recorded_at",
                )
            }
            if (
                row["schema_version"] != _SCHEMA_VERSION
                or observed.tzinfo is None
                or _digest(canonical_json_bytes(payload)) != row["fact_sha256"]
            ):
                raise ValueError("invalid task creation origin fact")
        except (ValueError, TypeError, AttributeError) as error:
            raise NativeWorkViolation(
                "NATIVE_TASK_ORIGIN_CORRUPT",
                "task creation origin integrity failed",
                ErrorCode.UNAVAILABLE,
            ) from error

    def recover_task_origins(self, scope: ScopeRef) -> None:
        """Repair a missing projection write from the exact durable call receipt.

        A journal commit may succeed after the separate origin write failed.
        This recovers only the association, including after process restart;
        callers must still intersect it with current authorized Task facts.
        """
        scope_sha = _scope_digest(scope)
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT request_id,voice_identity_sha256,fingerprint,
                          json_extract(result_json,'$.task_id') AS task_id,
                          json_extract(result_json,'$.native_origin') AS origin_json
                   FROM unified_committed_inputs
                   WHERE status='completed' AND request_id LIKE 'native-business:%'
                     AND json_valid(result_json)
                     AND json_extract(result_json,'$.contract_version')='live-voice.native-business.v1'
                     AND json_extract(result_json,'$.status')='dispatched'
                     AND json_extract(result_json,'$.operation') IN ('task.create','task.create_successor')
                     AND json_extract(result_json,'$.native_origin.scope_sha256')=?
                     AND json_extract(result_json,'$.task_id') NOT IN
                       (SELECT task_id FROM native_business_task_origin WHERE scope_sha256=?)
                   LIMIT ?""",
                (scope_sha, scope_sha, self._max_task_origins + 1),
            ).fetchall()
        if len(rows) > self._max_task_origins:
            raise NativeWorkViolation(
                "NATIVE_TASK_ORIGIN_LEDGER_FULL",
                "Recovery exceeds origin capacity",
                ErrorCode.UNAVAILABLE,
            )
        for row in rows:
            if (
                type(row["origin_json"]) is not str
                or len(row["origin_json"].encode("utf-8")) > 4096
            ):
                raise NativeWorkViolation(
                    "NATIVE_TASK_ORIGIN_CORRUPT",
                    "Creation receipt origin is invalid",
                    ErrorCode.UNAVAILABLE,
                )
            origin = json.loads(row["origin_json"])
            source = origin.get("source_identity")
            identity = row["voice_identity_sha256"]
            if (
                set(origin) != {"scope_sha256", "source_identity", "commit_id"}
                or source != row["request_id"]
                or source != "native-business:" + identity
                or len(identity) != 64
                or any(char not in "0123456789abcdef" for char in identity)
                or bytes(row["fingerprint"]) != bytes.fromhex(identity)
            ):
                raise NativeWorkViolation(
                    "NATIVE_TASK_ORIGIN_CORRUPT",
                    "Creation receipt identity changed",
                    ErrorCode.UNAVAILABLE,
                )
            self.record_task_origin(scope, row["task_id"], source, origin["commit_id"])

    def record_task_origin(
        self, scope: ScopeRef, task_id: str, source_identity: str, commit_id: str
    ) -> None:
        """Remember a real creation receipt; this grants no Task read authority."""
        scope_sha = _scope_digest(scope)
        _origin_identity(task_id, source_identity, commit_id)
        with self._connection(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM native_business_task_origin WHERE scope_sha256=? AND task_id=?",
                (scope_sha, task_id),
            ).fetchone()
            if row is not None:
                self._verify_task_origin(row)
                if (
                    row["source_identity"] != source_identity
                    or row["commit_id"] != commit_id
                ):
                    raise NativeWorkViolation(
                        "NATIVE_TASK_ORIGIN_CONFLICT",
                        "task creation origin cannot change",
                        ErrorCode.CONFLICT,
                    )
                return
            count = connection.execute(
                "SELECT COUNT(*) FROM native_business_task_origin"
            ).fetchone()[0]
            if count >= self._max_task_origins:
                raise NativeWorkViolation(
                    "NATIVE_TASK_ORIGIN_LEDGER_FULL",
                    "bounded task creation origin journal is full",
                    ErrorCode.UNAVAILABLE,
                )
            now = (
                datetime.now(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            payload = {
                "schema_version": _SCHEMA_VERSION,
                "scope_sha256": scope_sha,
                "task_id": task_id,
                "source_identity": source_identity,
                "commit_id": commit_id,
                "recorded_at": now,
            }
            connection.execute(
                "INSERT INTO native_business_task_origin VALUES(?,?,?,?,?,?,?)",
                (
                    _SCHEMA_VERSION,
                    scope_sha,
                    task_id,
                    source_identity,
                    commit_id,
                    now,
                    _digest(canonical_json_bytes(payload)),
                ),
            )

    def task_origins(self, scope: ScopeRef) -> tuple[str, ...]:
        """IDs to intersect with authorized Task reads; no Task state is restored."""
        scope_sha = _scope_digest(scope)
        with self._connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM native_business_task_origin"
            ).fetchone()[0]
            if count > self._max_task_origins:
                raise NativeWorkViolation(
                    "NATIVE_TASK_ORIGIN_LEDGER_FULL",
                    "retained task origins exceed configured capacity",
                    ErrorCode.UNAVAILABLE,
                )
            rows = connection.execute(
                "SELECT * FROM native_business_task_origin WHERE scope_sha256=? ORDER BY task_id",
                (scope_sha,),
            ).fetchall()
            for row in rows:
                self._verify_task_origin(row)
            return tuple(row["task_id"] for row in rows)
