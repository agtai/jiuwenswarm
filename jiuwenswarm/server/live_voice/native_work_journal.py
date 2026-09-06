# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Native work checkpoints and recovery facts in the input journal DB.

This adapter never executes work, recovers an Agent, or manufactures an ACK.
Registry supplies the existing SqliteUnifiedCommittedInputJournal.database_path;
NativeWorkRuntime converts lost process ownership to UNKNOWN on restoration.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ScopeRef,
    canonical_json_bytes,
)
from .native_work_runtime import (
    NativeWorkSnapshot,
    NativeWorkState,
    NativeWorkViolation,
)

_SCHEMA_VERSION = 1
_MAX_PAYLOAD_BYTES = 192 * 1024
_SUPPRESSION_REASONS = frozenset({"speech_interrupted", "superseded"})
_IMMUTABLE_FIELDS = (
    "scope",
    "work_id",
    "revision",
    "request_id",
    "input_id",
    "instruction",
    "model_identity",
    "model_config_version",
    "context_id",
    "foreground",
    "accepted_at",
    "supersedes_revision",
)
_COLUMNS = {
    "native_work_checkpoint": (
        ("schema_version", "INTEGER", 0),
        ("scope_sha256", "TEXT", 1),
        ("work_id", "TEXT", 2),
        ("revision", "INTEGER", 3),
        ("sequence", "INTEGER", 0),
        ("request_id", "TEXT", 0),
        ("identity_sha256", "TEXT", 0),
        ("snapshot_json", "TEXT", 0),
        ("snapshot_sha256", "TEXT", 0),
    ),
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
_TRANSITIONS = {
    NativeWorkState.ACCEPTED: frozenset(
        {
            NativeWorkState.RUNNING,
            NativeWorkState.CANCELLING,
            NativeWorkState.CANCELLED,
            NativeWorkState.SUPERSEDED,
            NativeWorkState.FAILED,
            NativeWorkState.UNKNOWN,
        }
    ),
    NativeWorkState.RUNNING: frozenset(
        {
            NativeWorkState.COMPLETED,
            NativeWorkState.CANCELLING,
            NativeWorkState.CANCELLED,
            NativeWorkState.SUPERSEDED,
            NativeWorkState.FAILED,
            NativeWorkState.UNKNOWN,
        }
    ),
    NativeWorkState.CANCELLING: frozenset(
        {NativeWorkState.CANCELLED, NativeWorkState.UNKNOWN}
    ),
    NativeWorkState.COMPLETED: frozenset(
        {NativeWorkState.SUPERSEDED, NativeWorkState.UNKNOWN}
    ),
    NativeWorkState.FAILED: frozenset(
        {NativeWorkState.SUPERSEDED, NativeWorkState.UNKNOWN}
    ),
    NativeWorkState.CANCELLED: frozenset({NativeWorkState.UNKNOWN}),
    NativeWorkState.SUPERSEDED: frozenset({NativeWorkState.UNKNOWN}),
    NativeWorkState.UNKNOWN: frozenset(),
}


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _scope_digest(scope: ScopeRef) -> str:
    if not isinstance(scope, ScopeRef):
        raise NativeWorkViolation(
            "NATIVE_WORK_JOURNAL_SCOPE_INVALID", "canonical work scope is required"
        )
    canonical = ScopeRef.from_dict(scope.to_dict())
    return _digest(canonical_json_bytes(canonical.to_dict()))


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


class SqliteNativeWorkJournal:
    """Bounded additive tables; exact sequence CAS and no automatic replay."""

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
        self.database_path = Path(database_path)
        self._max_records = max_records
        self._max_presentations = max_presentations
        self._max_task_origins = max_task_origins
        self._require_existing_database()
        with self._connection(write=True, verify=False) as connection:
            self._require_input_journal(connection)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS native_work_checkpoint (
                    schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                    scope_sha256 TEXT NOT NULL,
                    work_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision > 0),
                    sequence INTEGER NOT NULL CHECK(sequence > 0),
                    request_id TEXT NOT NULL,
                    identity_sha256 TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    PRIMARY KEY(scope_sha256, work_id, revision),
                    UNIQUE(scope_sha256, request_id)
                )
            """)
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
            self._verify_schema(connection)

    def _require_existing_database(self) -> None:
        if self.database_path.is_symlink() or not self.database_path.is_file():
            raise NativeWorkViolation(
                "NATIVE_WORK_JOURNAL_UNAVAILABLE",
                "Native work requires the existing regular input journal database",
                ErrorCode.UNAVAILABLE,
            )

    @contextmanager
    def _connection(self, *, write: bool = False, verify: bool = True):
        self._require_existing_database()
        connection = None
        try:
            connection = sqlite3.connect(
                self.database_path.absolute().as_uri() + "?mode=rw",
                uri=True,
                timeout=5.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if verify:
                self._verify_schema(connection)
            yield connection
            connection.commit()
        except (sqlite3.Error, OverflowError) as error:
            if connection is not None:
                connection.rollback()
            raise NativeWorkViolation(
                "NATIVE_WORK_JOURNAL_UNAVAILABLE",
                "Native work checkpoint transaction is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from error
        except BaseException:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

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

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        SqliteNativeWorkJournal._require_input_journal(connection)
        for table, expected in _COLUMNS.items():
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            actual = tuple(
                (str(row["name"]), str(row["type"]).upper(), int(row["pk"]))
                for row in columns
            )
            if actual != expected or any(not row["notnull"] for row in columns):
                raise NativeWorkViolation(
                    "NATIVE_WORK_JOURNAL_SCHEMA_UNSUPPORTED",
                    "Native work journal schema is unsupported",
                    ErrorCode.UNAVAILABLE,
                )
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=? LIMIT 1",
                (table,),
            ).fetchone():
                raise NativeWorkViolation(
                    "NATIVE_WORK_JOURNAL_SCHEMA_UNSUPPORTED",
                    "Native work journal triggers are unsupported",
                    ErrorCode.UNAVAILABLE,
                )

    @staticmethod
    def _encode(snapshot: NativeWorkSnapshot) -> tuple[str, str, str]:
        if not isinstance(snapshot, NativeWorkSnapshot):
            raise NativeWorkViolation(
                "NATIVE_WORK_CHECKPOINT_INVALID",
                "checkpoint requires an immutable work snapshot",
            )
        payload = snapshot.to_dict()
        encoded = canonical_json_bytes(payload)
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            raise NativeWorkViolation(
                "NATIVE_WORK_CHECKPOINT_TOO_LARGE",
                "checkpoint exceeds its closed size bound",
            )
        identity = _digest(
            canonical_json_bytes({key: payload[key] for key in _IMMUTABLE_FIELDS})
        )
        return encoded.decode("utf-8"), _digest(encoded), identity

    @classmethod
    def _decode(cls, row: sqlite3.Row) -> NativeWorkSnapshot:
        try:
            encoded = row["snapshot_json"].encode("utf-8")
            if (
                row["schema_version"] != _SCHEMA_VERSION
                or len(encoded) > _MAX_PAYLOAD_BYTES
                or _digest(encoded) != row["snapshot_sha256"]
            ):
                raise ValueError("invalid checkpoint envelope")
            snapshot = NativeWorkSnapshot.from_dict(json.loads(encoded))
            _, digest, identity = cls._encode(snapshot)
            if (
                digest != row["snapshot_sha256"]
                or identity != row["identity_sha256"]
                or _scope_digest(snapshot.scope) != row["scope_sha256"]
                or snapshot.work_id != row["work_id"]
                or snapshot.revision != row["revision"]
                or snapshot.sequence != row["sequence"]
                or snapshot.request_id != row["request_id"]
            ):
                raise ValueError("checkpoint row identity disagrees with payload")
            return snapshot
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise NativeWorkViolation(
                "NATIVE_WORK_CHECKPOINT_CORRUPT",
                "Native work checkpoint integrity failed",
                ErrorCode.UNAVAILABLE,
            ) from error

    def save(self, snapshot: NativeWorkSnapshot) -> None:
        encoded, payload_sha, identity_sha = self._encode(snapshot)
        scope_sha = _scope_digest(snapshot.scope)
        key = (scope_sha, snapshot.work_id, snapshot.revision)
        with self._connection(write=True) as connection:
            prior = connection.execute(
                "SELECT * FROM native_work_checkpoint WHERE scope_sha256=? AND work_id=? AND revision=?",
                key,
            ).fetchone()
            if prior is not None:
                previous = self._decode(prior)
                if (
                    snapshot.sequence == previous.sequence
                    and prior["snapshot_sha256"] == payload_sha
                ):
                    return
                if snapshot.sequence != previous.sequence + 1:
                    raise NativeWorkViolation(
                        "NATIVE_WORK_CHECKPOINT_SEQUENCE_CONFLICT",
                        "checkpoint must advance exactly one sequence or replay exactly",
                        ErrorCode.CONFLICT,
                    )
                if identity_sha != prior["identity_sha256"]:
                    raise NativeWorkViolation(
                        "NATIVE_WORK_CHECKPOINT_IDENTITY_CONFLICT",
                        "checkpoint cannot change admitted work identity",
                        ErrorCode.CONFLICT,
                    )
                if (
                    snapshot.state is not previous.state
                    and snapshot.state not in _TRANSITIONS[previous.state]
                ):
                    raise NativeWorkViolation(
                        "NATIVE_WORK_CHECKPOINT_STATE_CONFLICT",
                        "checkpoint cannot revive a retired work revision",
                        ErrorCode.CONFLICT,
                    )
                connection.execute(
                    "UPDATE native_work_checkpoint SET sequence=?, snapshot_json=?, snapshot_sha256=? WHERE scope_sha256=? AND work_id=? AND revision=? AND sequence=?",
                    (snapshot.sequence, encoded, payload_sha, *key, previous.sequence),
                )
                return
            if (
                snapshot.sequence != 1
                or snapshot.state is not NativeWorkState.ACCEPTED
                or snapshot.execution_settled
            ):
                raise NativeWorkViolation(
                    "NATIVE_WORK_CHECKPOINT_ADMISSION_REQUIRED",
                    "new checkpoint requires initial accepted state",
                    ErrorCode.CONFLICT,
                )
            if connection.execute(
                "SELECT 1 FROM native_work_checkpoint WHERE scope_sha256=? AND request_id=?",
                (scope_sha, snapshot.request_id),
            ).fetchone():
                raise NativeWorkViolation(
                    "NATIVE_WORK_CHECKPOINT_REQUEST_CONFLICT",
                    "request already names another work revision",
                    ErrorCode.CONFLICT,
                )
            latest = connection.execute(
                "SELECT MAX(revision) FROM native_work_checkpoint WHERE scope_sha256=? AND work_id=?",
                (scope_sha, snapshot.work_id),
            ).fetchone()[0]
            if snapshot.revision != (int(latest) + 1 if latest is not None else 1):
                raise NativeWorkViolation(
                    "NATIVE_WORK_CHECKPOINT_REVISION_CONFLICT",
                    "new revision must follow its retained predecessor",
                    ErrorCode.CONFLICT,
                )
            count = connection.execute(
                "SELECT COUNT(*) FROM native_work_checkpoint"
            ).fetchone()[0]
            if count >= self._max_records:
                raise NativeWorkViolation(
                    "NATIVE_WORK_JOURNAL_FULL",
                    "bounded work journal is full",
                    ErrorCode.UNAVAILABLE,
                )
            connection.execute(
                "INSERT INTO native_work_checkpoint VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    _SCHEMA_VERSION,
                    scope_sha,
                    snapshot.work_id,
                    snapshot.revision,
                    snapshot.sequence,
                    snapshot.request_id,
                    identity_sha,
                    encoded,
                    payload_sha,
                ),
            )

    def restore(self) -> tuple[NativeWorkSnapshot, ...]:
        with self._connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM native_work_checkpoint"
            ).fetchone()[0]
            if count > self._max_records:
                raise NativeWorkViolation(
                    "NATIVE_WORK_JOURNAL_FULL",
                    "retained work exceeds configured capacity",
                    ErrorCode.UNAVAILABLE,
                )
            if connection.execute(
                "SELECT 1 FROM native_work_checkpoint WHERE length(CAST(snapshot_json AS BLOB)) > ? LIMIT 1",
                (_MAX_PAYLOAD_BYTES,),
            ).fetchone():
                raise NativeWorkViolation(
                    "NATIVE_WORK_CHECKPOINT_CORRUPT",
                    "retained checkpoint exceeds its size bound",
                    ErrorCode.UNAVAILABLE,
                )
            return tuple(
                self._decode(row)
                for row in connection.execute(
                    "SELECT * FROM native_work_checkpoint ORDER BY scope_sha256, work_id, revision"
                ).fetchall()
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
