# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Independent durable replay owner for committed hands-free voice input.

The journal stores digests, bounded control recovery and pre-command semantic
context. It never stores raw audio, bearer credentials or Gateway receipts.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    Assurance,
    ErrorCode,
    ScopeRef,
    canonical_json_bytes,
)

from .formal_task_models import FormalTaskViolation
from .p3_confirmation import P3_CONFIRMATION_MAX_CAPACITY, P3_CONFIRMATION_MAX_TTL


@dataclass(frozen=True, slots=True)
class UnifiedInputAdmission:
    execute: bool
    replay_result: dict[str, object] | None
    in_progress: bool = False
    semantic_binding: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class UnifiedForegroundEffectAdmission:
    execute: bool
    replay_result: dict[str, object] | None
    result_unknown: bool = False
    effect_kind: str | None = None
    recovery: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class PendingSemanticContext:
    context_id: str
    kind: str
    source_id: str
    version: int
    payload: dict[str, object]
    issued_at: float
    expires_at: float
    consumed_by: str | None


class SqliteUnifiedCommittedInputJournal:
    """Bind request and Gateway voice identities before any business effect."""

    _LEASE_SECONDS = 30.0

    @property
    def renewal_interval_seconds(self) -> float:
        """Bound renew cadence below one third of the current execution lease."""

        return max(0.001, min(10.0, self._LEASE_SECONDS / 3.0))

    _FOREGROUND_EFFECT_KINDS = frozenset({"agent_submit", "authoritative_presentation"})

    def __init__(self, database: str | os.PathLike[str]) -> None:
        self.database_path = Path(database).resolve(strict=False)
        self._execution_owner = uuid.uuid4().hex
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS unified_committed_inputs (
                    request_id TEXT PRIMARY KEY,
                    voice_identity_sha256 TEXT NOT NULL UNIQUE,
                    fingerprint BLOB NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'completed')),
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    execution_owner TEXT,
                    lease_expires_at REAL,
                    semantic_binding_json TEXT
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(unified_committed_inputs)"
                ).fetchall()
            }
            if "execution_owner" not in columns:
                connection.execute(
                    "ALTER TABLE unified_committed_inputs ADD COLUMN execution_owner TEXT"
                )
            if "lease_expires_at" not in columns:
                connection.execute(
                    "ALTER TABLE unified_committed_inputs ADD COLUMN lease_expires_at REAL"
                )
            if "semantic_binding_json" not in columns:
                connection.execute(
                    "ALTER TABLE unified_committed_inputs "
                    "ADD COLUMN semantic_binding_json TEXT"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS unified_request_bindings (
                    request_id TEXT PRIMARY KEY,
                    voice_identity_sha256 TEXT NOT NULL,
                    fingerprint BLOB NOT NULL,
                    FOREIGN KEY(voice_identity_sha256)
                        REFERENCES unified_committed_inputs(voice_identity_sha256)
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO unified_request_bindings(
                    request_id, voice_identity_sha256, fingerprint
                )
                SELECT request_id, voice_identity_sha256, fingerprint
                  FROM unified_committed_inputs
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS unified_foreground_effects (
                    voice_identity_sha256 TEXT PRIMARY KEY,
                    fingerprint BLOB NOT NULL,
                    effect_kind TEXT NOT NULL CHECK(
                        effect_kind IN (
                            'agent_submit', 'authoritative_presentation'
                        )
                    ),
                    status TEXT NOT NULL CHECK(
                        status IN ('prepared', 'completed')
                    ),
                    result_json TEXT,
                    recovery_json TEXT,
                    execution_owner TEXT NOT NULL,
                    FOREIGN KEY(voice_identity_sha256)
                        REFERENCES unified_committed_inputs(voice_identity_sha256)
                )
                """
            )
            effect_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(unified_foreground_effects)"
                ).fetchall()
            }
            if "recovery_json" not in effect_columns:
                connection.execute(
                    "ALTER TABLE unified_foreground_effects "
                    "ADD COLUMN recovery_json TEXT"
                )
            connection.execute("""
                CREATE TABLE IF NOT EXISTS semantic_pending_contexts (
                    context_id TEXT PRIMARY KEY,
                    scope_sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('proposal', 'clarification', 'confirmation')),
                    source_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version > 0),
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    consumed_by TEXT,
                    record_sha256 TEXT NOT NULL,
                    UNIQUE(scope_sha256, kind, source_id)
                )
            """)

    @staticmethod
    def _semantic_scope_key(scope: ScopeRef) -> str:
        if (
            not isinstance(scope, ScopeRef)
            or scope.assurance is not Assurance.AUTHENTICATED
            or not scope.session_id
        ):
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_SCOPE_REQUIRED",
                "semantic context requires an authenticated conversation",
                ErrorCode.PERMISSION_DENIED,
            )
        return hashlib.sha256(canonical_json_bytes(scope.to_dict())).hexdigest()

    @staticmethod
    def _semantic_time(value: float) -> float:
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_TIME_INVALID",
                "invalid context time",
                ErrorCode.INVALID_ARGUMENT,
            )
        return float(value)

    @staticmethod
    def _semantic_text(value: str) -> str:
        if (
            type(value) is not str
            or not value.strip()
            or "\x00" in value
            or len(value.encode("utf-8")) > 256
        ):
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_ID_INVALID",
                "invalid context identity",
                ErrorCode.INVALID_ARGUMENT,
            )
        return value

    @staticmethod
    def _semantic_record_digest(row: Mapping[str, object]) -> str:
        return hashlib.sha256(
            canonical_json_bytes(
                {
                    field: row[field]
                    for field in (
                        "context_id",
                        "scope_sha256",
                        "kind",
                        "source_id",
                        "version",
                        "payload_sha256",
                        "issued_at",
                        "expires_at",
                        "consumed_by",
                    )
                }
            )
        ).hexdigest()

    @staticmethod
    def _pending_context(row: sqlite3.Row) -> PendingSemanticContext:
        try:
            if (
                SqliteUnifiedCommittedInputJournal._semantic_record_digest(row)
                != row["record_sha256"]
            ):
                raise ValueError
            payload = json.loads(row["payload_json"])
            if type(payload) is not dict or len(canonical_json_bytes(payload)) > 32_768:
                raise ValueError
            if (
                hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
                != row["payload_sha256"]
            ):
                raise ValueError
            return PendingSemanticContext(
                str(row["context_id"]),
                str(row["kind"]),
                str(row["source_id"]),
                int(row["version"]),
                payload,
                float(row["issued_at"]),
                float(row["expires_at"]),
                row["consumed_by"],
            )
        except (ValueError, TypeError, KeyError) as error:
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_CORRUPT",
                "persisted semantic context failed integrity checks",
                ErrorCode.INTERNAL,
            ) from error

    def retain_semantic_context(
        self,
        *,
        scope: ScopeRef,
        kind: str,
        source_id: str,
        payload: Mapping[str, object],
        issued_at: float,
        expires_at: float,
        now: float | None = None,
    ) -> PendingSemanticContext:
        """Persist pre-command data, never a Task or an authorization receipt.

        Source and expiry are server facts. Replaying an Agent presentation or
        reconnecting cannot change payload, refresh expiry or mint another ID.
        """
        scope_key = self._semantic_scope_key(scope)
        source_id = self._semantic_text(source_id)
        issued, expires = (
            self._semantic_time(issued_at),
            self._semantic_time(expires_at),
        )
        observed = self._semantic_time(time.time() if now is None else now)
        if kind not in {"proposal", "clarification", "confirmation"} or not isinstance(
            payload, Mapping
        ):
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_INVALID",
                "invalid pre-command context",
                ErrorCode.INVALID_ARGUMENT,
            )
        encoded = canonical_json_bytes(dict(payload))
        if (
            len(encoded) > 32_768
            or not issued <= observed < expires
            or expires - issued > P3_CONFIRMATION_MAX_TTL.total_seconds()
        ):
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_BOUND_EXCEEDED",
                "context bounds or expiry rejected",
                ErrorCode.INVALID_ARGUMENT,
            )
        digest = hashlib.sha256(encoded).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM semantic_pending_contexts WHERE scope_sha256=? AND kind=? AND source_id=?",
                (scope_key, kind, source_id),
            ).fetchone()
            if existing is not None:
                record = self._pending_context(existing)
                if (
                    existing["payload_sha256"] != digest
                    or record.issued_at != issued
                    or record.expires_at != expires
                ):
                    raise FormalTaskViolation(
                        "SEMANTIC_CONTEXT_SOURCE_CONFLICT",
                        "source context cannot change",
                        ErrorCode.CONFLICT,
                    )
                return record
            # Retain expired source anchors: forgetting one would allow an old
            # Agent presentation to mint new work with a refreshed expiry. The
            # global capacity includes anchors and fails closed when full.
            count = connection.execute(
                "SELECT COUNT(*) FROM semantic_pending_contexts"
            ).fetchone()[0]
            scoped = connection.execute(
                "SELECT COUNT(*) FROM semantic_pending_contexts WHERE scope_sha256=? AND consumed_by IS NULL AND expires_at>?",
                (scope_key, observed),
            ).fetchone()[0]
            if count >= P3_CONFIRMATION_MAX_CAPACITY or scoped >= 8:
                raise FormalTaskViolation(
                    "SEMANTIC_CONTEXT_CAPACITY_EXCEEDED",
                    "bounded pending context is full",
                    ErrorCode.UNAVAILABLE,
                )
            context_id = f"semantic-{uuid.uuid4().hex}"
            record_digest = self._semantic_record_digest(
                {
                    "context_id": context_id,
                    "scope_sha256": scope_key,
                    "kind": kind,
                    "source_id": source_id,
                    "version": 1,
                    "payload_sha256": digest,
                    "issued_at": issued,
                    "expires_at": expires,
                    "consumed_by": None,
                }
            )
            connection.execute(
                "INSERT INTO semantic_pending_contexts VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, NULL, ?)",
                (
                    context_id,
                    scope_key,
                    kind,
                    source_id,
                    encoded.decode("utf-8"),
                    digest,
                    issued,
                    expires,
                    record_digest,
                ),
            )
            row = connection.execute(
                "SELECT * FROM semantic_pending_contexts WHERE context_id=?",
                (context_id,),
            ).fetchone()
            assert row is not None
            return self._pending_context(row)

    def read_semantic_contexts(
        self,
        *,
        scope: ScopeRef,
        now: float | None = None,
    ) -> tuple[PendingSemanticContext, ...]:
        scope_key = self._semantic_scope_key(scope)
        observed = self._semantic_time(time.time() if now is None else now)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM semantic_pending_contexts WHERE scope_sha256=? AND consumed_by IS NULL AND issued_at<=? AND expires_at>? "
                "ORDER BY issued_at, context_id LIMIT 9",
                (scope_key, observed, observed),
            ).fetchall()
        if len(rows) > 8:
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_CORRUPT",
                "pending context bound exceeded",
                ErrorCode.INTERNAL,
            )
        return tuple(self._pending_context(row) for row in rows)

    def consume_semantic_context(
        self,
        *,
        scope: ScopeRef,
        context_id: str,
        version: int,
        commit_sha256: str,
        now: float | None = None,
    ) -> PendingSemanticContext:
        """Single-input CAS; not confirmation or permission to execute a Task."""
        scope_key = self._semantic_scope_key(scope)
        context_id = self._semantic_text(context_id)
        observed = self._semantic_time(time.time() if now is None else now)
        if (
            type(version) is not int
            or version < 1
            or type(commit_sha256) is not str
            or len(commit_sha256) != 64
            or any(c not in "0123456789abcdef" for c in commit_sha256)
        ):
            raise FormalTaskViolation(
                "SEMANTIC_CONTEXT_CONSUMPTION_INVALID",
                "invalid context consumption",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM semantic_pending_contexts WHERE context_id=? AND scope_sha256=? AND version=?",
                (context_id, scope_key, version),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "SEMANTIC_CONTEXT_UNAVAILABLE",
                    "exact pending context unavailable",
                    ErrorCode.CONFLICT,
                )
            record = self._pending_context(row)
            if record.consumed_by == commit_sha256:
                return record
            if (
                record.consumed_by is not None
                or not record.issued_at <= observed < record.expires_at
            ):
                raise FormalTaskViolation(
                    "SEMANTIC_CONTEXT_STALE",
                    "context expired or already consumed",
                    ErrorCode.CONFLICT,
                )
            connection.execute(
                "UPDATE semantic_pending_contexts SET consumed_by=?, record_sha256=? "
                "WHERE context_id=? AND consumed_by IS NULL",
                (
                    commit_sha256,
                    self._semantic_record_digest(
                        {
                            **dict(row),
                            "consumed_by": commit_sha256,
                        }
                    ),
                    context_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM semantic_pending_contexts WHERE context_id=?",
                (context_id,),
            ).fetchone()
            assert row is not None
            return self._pending_context(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @staticmethod
    def _validate_identity(
        request_id: str,
        voice_identity_sha256: str,
        fingerprint: bytes,
    ) -> None:
        if not request_id or len(request_id) > 256:
            raise FormalTaskViolation(
                "INVALID_UNIFIED_REQUEST_ID",
                "unified request identity is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            len(voice_identity_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in voice_identity_sha256
            )
            or type(fingerprint) is not bytes
            or len(fingerprint) != 32
        ):
            raise FormalTaskViolation(
                "INVALID_UNIFIED_VOICE_IDENTITY",
                "unified voice identity is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )

    @staticmethod
    def _validate_voice_binding(
        voice_identity_sha256: str,
        fingerprint: bytes,
    ) -> None:
        if (
            type(voice_identity_sha256) is not str
            or len(voice_identity_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in voice_identity_sha256
            )
            or type(fingerprint) is not bytes
            or len(fingerprint) != 32
        ):
            raise FormalTaskViolation(
                "INVALID_UNIFIED_VOICE_IDENTITY",
                "unified voice identity is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )

    @staticmethod
    def _decode_result(row: sqlite3.Row) -> dict[str, object]:
        value = row["result_json"]
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError) as exc:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_JOURNAL_CORRUPT",
                "unified committed-input result is invalid",
                ErrorCode.INTERNAL,
            ) from exc
        if not isinstance(payload, dict):
            raise FormalTaskViolation(
                "UNIFIED_INPUT_JOURNAL_CORRUPT",
                "unified committed-input result is invalid",
                ErrorCode.INTERNAL,
            )
        return payload

    @staticmethod
    def _decode_recovery(row: sqlite3.Row) -> dict[str, object] | None:
        value = row["recovery_json"]
        if value is None:
            return None
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError) as exc:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_JOURNAL_CORRUPT",
                "unified foreground-effect recovery is invalid",
                ErrorCode.INTERNAL,
            ) from exc
        if not isinstance(payload, dict):
            raise FormalTaskViolation(
                "UNIFIED_INPUT_JOURNAL_CORRUPT",
                "unified foreground-effect recovery is invalid",
                ErrorCode.INTERNAL,
            )
        return payload

    @staticmethod
    def _decode_semantic_binding(row: sqlite3.Row) -> dict[str, object] | None:
        value = row["semantic_binding_json"]
        if value is None:
            return None
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError) as exc:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_JOURNAL_CORRUPT",
                "unified semantic target binding is invalid",
                ErrorCode.INTERNAL,
            ) from exc
        if not isinstance(payload, dict):
            raise FormalTaskViolation(
                "UNIFIED_INPUT_JOURNAL_CORRUPT",
                "unified semantic target binding is invalid",
                ErrorCode.INTERNAL,
            )
        return payload

    def admit(
        self,
        *,
        request_id: str,
        voice_identity_sha256: str,
        fingerprint: bytes,
        created_at: str,
        semantic_binding: Mapping[str, object] | None = None,
    ) -> UnifiedInputAdmission:
        self._validate_identity(request_id, voice_identity_sha256, fingerprint)
        semantic_json = (
            None
            if semantic_binding is None
            else json.dumps(
                dict(semantic_binding),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        if semantic_json is not None and len(semantic_json.encode("utf-8")) > 16_384:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_SEMANTIC_BINDING_TOO_LARGE",
                "unified semantic target binding exceeds its closed bound",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            request_binding = connection.execute(
                "SELECT * FROM unified_request_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()
            voice_row = connection.execute(
                """
                SELECT * FROM unified_committed_inputs
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if request_binding is not None and (
                bytes(request_binding["fingerprint"]) != fingerprint
                or str(request_binding["voice_identity_sha256"])
                != voice_identity_sha256
            ):
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_ID_CONFLICT",
                    "request or voice identity was reused with different content",
                    ErrorCode.CONFLICT,
                )
            if voice_row is not None and bytes(voice_row["fingerprint"]) != fingerprint:
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_ID_CONFLICT",
                    "request or voice identity was reused with different content",
                    ErrorCode.CONFLICT,
                )
            if voice_row is not None:
                if request_binding is None:
                    connection.execute(
                        """
                        INSERT INTO unified_request_bindings(
                            request_id, voice_identity_sha256, fingerprint
                        ) VALUES(?, ?, ?)
                        """,
                        (request_id, voice_identity_sha256, fingerprint),
                    )
                if voice_row["status"] == "completed":
                    return UnifiedInputAdmission(
                        False,
                        self._decode_result(voice_row),
                        semantic_binding=self._decode_semantic_binding(voice_row),
                    )
                lease_expires_at = voice_row["lease_expires_at"]
                now = time.time()
                if (
                    not isinstance(lease_expires_at, (int, float))
                    or float(lease_expires_at) <= now
                ):
                    connection.execute(
                        """
                        UPDATE unified_committed_inputs
                           SET execution_owner=?, lease_expires_at=?
                         WHERE voice_identity_sha256=? AND status='pending'
                        """,
                        (
                            self._execution_owner,
                            now + self._LEASE_SECONDS,
                            voice_identity_sha256,
                        ),
                    )
                    return UnifiedInputAdmission(
                        True,
                        None,
                        semantic_binding=self._decode_semantic_binding(voice_row),
                    )
                return UnifiedInputAdmission(
                    False,
                    None,
                    in_progress=True,
                    semantic_binding=self._decode_semantic_binding(voice_row),
                )
            now = time.time()
            connection.execute(
                """
                INSERT INTO unified_committed_inputs(
                    request_id, voice_identity_sha256, fingerprint, status,
                    result_json, created_at, completed_at, execution_owner,
                    lease_expires_at, semantic_binding_json
                ) VALUES(?, ?, ?, 'pending', NULL, ?, NULL, ?, ?, ?)
                """,
                (
                    request_id,
                    voice_identity_sha256,
                    fingerprint,
                    created_at,
                    self._execution_owner,
                    now + self._LEASE_SECONDS,
                    semantic_json,
                ),
            )
            connection.execute(
                """
                INSERT INTO unified_request_bindings(
                    request_id, voice_identity_sha256, fingerprint
                ) VALUES(?, ?, ?)
                """,
                (request_id, voice_identity_sha256, fingerprint),
            )
        return UnifiedInputAdmission(
            True,
            None,
            semantic_binding=(
                None if semantic_binding is None else dict(semantic_binding)
            ),
        )

    def renew(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
    ) -> None:
        """Keep the one admitted execution lease while its business work runs."""

        with self._connect() as connection:
            updated = connection.execute(
                """
                UPDATE unified_committed_inputs
                   SET lease_expires_at=?
                 WHERE voice_identity_sha256=? AND fingerprint=?
                   AND status='pending' AND execution_owner=?
                """,
                (
                    time.time() + self._LEASE_SECONDS,
                    voice_identity_sha256,
                    fingerprint,
                    self._execution_owner,
                ),
            ).rowcount
        if updated != 1:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_EXECUTION_LEASE_LOST",
                "unified committed-input execution lease is no longer authoritative",
                ErrorCode.CONFLICT,
            )

    def bind_semantic(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        semantic_binding: Mapping[str, object],
    ) -> dict[str, object]:
        """Freeze data once, after admission and before any protected effect.

        This operation does not validate a speech source, mint an origin grant,
        or authorize a Task. Only the still-live execution owner can bind; an
        exact retry is harmless, but cannot replace a previous interpretation.
        """

        try:
            encoded = json.dumps(
                dict(semantic_binding),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (ValueError, TypeError, RecursionError) as error:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_SEMANTIC_BINDING_INVALID",
                "semantic binding must be bounded JSON data",
                ErrorCode.INVALID_ARGUMENT,
            ) from error
        if len(encoded.encode("utf-8")) > 131_072:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_SEMANTIC_BINDING_TOO_LARGE",
                "semantic binding exceeds its closed bound",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM unified_committed_inputs WHERE voice_identity_sha256=?",
                (voice_identity_sha256,),
            ).fetchone()
            if (
                row is None
                or bytes(row["fingerprint"]) != fingerprint
                or row["status"] != "pending"
                or row["execution_owner"] != self._execution_owner
                or not isinstance(row["lease_expires_at"], (int, float))
                or row["lease_expires_at"] <= time.time()
            ):
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_EXECUTION_LEASE_LOST",
                    "semantic binding requires the exact live execution lease",
                    ErrorCode.CONFLICT,
                )
            retained = self._decode_semantic_binding(row)
            value = json.loads(encoded)
            if retained is not None and retained != value:
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_SEMANTIC_BINDING_CONFLICT",
                    "an admitted input cannot change its frozen interpretation",
                    ErrorCode.CONFLICT,
                )
            if retained is None:
                connection.execute(
                    "UPDATE unified_committed_inputs SET semantic_binding_json=? "
                    "WHERE voice_identity_sha256=?",
                    (encoded, voice_identity_sha256),
                )
            return value

    def wait_for_completion(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        timeout_seconds: float = 30.0,
    ) -> dict[str, object] | None:
        """Wait boundedly for another owner and return only its durable result."""

        deadline = time.monotonic() + max(0.0, min(timeout_seconds, 30.0))
        while True:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM unified_committed_inputs
                    WHERE voice_identity_sha256=?
                    """,
                    (voice_identity_sha256,),
                ).fetchone()
            if row is None or bytes(row["fingerprint"]) != fingerprint:
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_ADMISSION_MISSING",
                    "unified replay has no exact durable admission",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if row["status"] == "completed":
                return self._decode_result(row)
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def read_foreground_effect(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
    ) -> UnifiedForegroundEffectAdmission | None:
        """Recover a sealed effect or fence an indeterminate external effect.

        A prepared presentation row is never taken over because publication
        may already have happened.  An Agent row that contains only the strict
        pre-dispatch marker is different: the synchronous P2 handoff proves no
        Agent/Tool task could run, so an expired lease owner may rebuild it.
        """

        self._validate_voice_binding(voice_identity_sha256, fingerprint)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM unified_foreground_effects
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
        if row is None:
            return None
        if bytes(row["fingerprint"]) != fingerprint:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_ID_CONFLICT",
                "voice identity cannot change committed content",
                ErrorCode.CONFLICT,
            )
        if row["status"] == "completed" or row["result_json"] is not None:
            return UnifiedForegroundEffectAdmission(
                False,
                self._decode_result(row),
                effect_kind=str(row["effect_kind"]),
                recovery=self._decode_recovery(row),
            )
        if row["recovery_json"] is not None and row["effect_kind"] == "agent_submit":
            # Agent submission has a strict synchronous handoff: no event-loop
            # yield is permitted between the local Harness/Bridge commit and
            # promotion of the exact accepted result.  If only this
            # pre-dispatch marker survived, the old process could not have run
            # Agent/Tool work; a lease successor may safely rebuild it.
            return None
        if row["recovery_json"] is not None:
            # Presentation publication is not transactionally coupled to this
            # SQLite journal, so a recovered owner must fail closed instead of
            # publishing it twice.
            return UnifiedForegroundEffectAdmission(
                False,
                None,
                result_unknown=True,
                effect_kind=str(row["effect_kind"]),
                recovery=self._decode_recovery(row),
            )
        # No checkpoint proves the external effect could not have started, so
        # the recovered input-lease owner may safely rebuild it.
        return None

    def admit_foreground_effect(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        effect_kind: str,
    ) -> UnifiedForegroundEffectAdmission:
        """Persist a no-takeover fence before one external foreground effect."""

        self._validate_voice_binding(voice_identity_sha256, fingerprint)
        if effect_kind not in self._FOREGROUND_EFFECT_KINDS:
            raise FormalTaskViolation(
                "INVALID_UNIFIED_FOREGROUND_EFFECT",
                "unified foreground effect kind is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT fingerprint, status, execution_owner, lease_expires_at
                  FROM unified_committed_inputs
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if (
                parent is None
                or bytes(parent["fingerprint"]) != fingerprint
                or parent["status"] != "pending"
                or parent["execution_owner"] != self._execution_owner
                or not isinstance(parent["lease_expires_at"], (int, float))
                or float(parent["lease_expires_at"]) <= time.time()
            ):
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_EXECUTION_LEASE_LOST",
                    "foreground effect lost its exact unified execution lease",
                    ErrorCode.CONFLICT,
                )
            row = connection.execute(
                """
                SELECT * FROM unified_foreground_effects
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if row is not None:
                if (
                    bytes(row["fingerprint"]) != fingerprint
                    or row["effect_kind"] != effect_kind
                ):
                    raise FormalTaskViolation(
                        "UNIFIED_FOREGROUND_EFFECT_CONFLICT",
                        "unified foreground effect identity is immutable",
                        ErrorCode.CONFLICT,
                    )
                if row["status"] == "completed":
                    return UnifiedForegroundEffectAdmission(
                        False,
                        self._decode_result(row),
                        effect_kind=effect_kind,
                        recovery=self._decode_recovery(row),
                    )
                if row["result_json"] is not None:
                    return UnifiedForegroundEffectAdmission(
                        False,
                        self._decode_result(row),
                        effect_kind=effect_kind,
                        recovery=self._decode_recovery(row),
                    )
                if row["recovery_json"] is not None and effect_kind != "agent_submit":
                    return UnifiedForegroundEffectAdmission(
                        False,
                        None,
                        result_unknown=True,
                        effect_kind=effect_kind,
                        recovery=self._decode_recovery(row),
                    )
                if effect_kind == "agent_submit":
                    connection.execute(
                        """
                        UPDATE unified_foreground_effects
                           SET execution_owner=?, recovery_json=NULL
                         WHERE voice_identity_sha256=? AND status='prepared'
                        """,
                        (self._execution_owner, voice_identity_sha256),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE unified_foreground_effects
                           SET execution_owner=?
                         WHERE voice_identity_sha256=? AND status='prepared'
                        """,
                        (self._execution_owner, voice_identity_sha256),
                    )
                return UnifiedForegroundEffectAdmission(
                    True,
                    None,
                    effect_kind=effect_kind,
                )
            connection.execute(
                """
                INSERT INTO unified_foreground_effects(
                    voice_identity_sha256, fingerprint, effect_kind, status,
                    result_json, recovery_json, execution_owner
                ) VALUES(?, ?, ?, 'prepared', NULL, NULL, ?)
                """,
                (
                    voice_identity_sha256,
                    fingerprint,
                    effect_kind,
                    self._execution_owner,
                ),
            )
        return UnifiedForegroundEffectAdmission(
            True,
            None,
            effect_kind=effect_kind,
        )

    def checkpoint_foreground_effect_result(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        effect_kind: str,
        result: Mapping[str, object],
    ) -> dict[str, object]:
        """Promote an owned pre-dispatch marker to a replayable outcome.

        The Agent owner calls this immediately after the existing P2 facade has
        accepted the deterministic request.  It closes the normal
        dispatch-to-journal window.  A failed promotion is synchronously
        rolled back before Agent/Tool work starts; a process that leaves only
        the pre-dispatch marker is therefore safe for one recovered dispatch.
        """

        self._validate_voice_binding(voice_identity_sha256, fingerprint)
        if effect_kind != "agent_submit":
            raise FormalTaskViolation(
                "INVALID_UNIFIED_FOREGROUND_EFFECT",
                "only Agent submit outcomes use foreground-result promotion",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not isinstance(result, Mapping):
            raise TypeError("unified foreground effect result must be a mapping")
        encoded = json.dumps(
            dict(result), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        if len(encoded.encode("utf-8")) > 262_144:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_RESULT_TOO_LARGE",
                "unified foreground effect result exceeds its closed bound",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT fingerprint, status, execution_owner, lease_expires_at
                  FROM unified_committed_inputs
                 WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            row = connection.execute(
                """
                SELECT * FROM unified_foreground_effects
                 WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if (
                parent is None
                or bytes(parent["fingerprint"]) != fingerprint
                or parent["status"] != "pending"
                or parent["execution_owner"] != self._execution_owner
                or not isinstance(parent["lease_expires_at"], (int, float))
                or float(parent["lease_expires_at"]) <= time.time()
                or row is None
                or bytes(row["fingerprint"]) != fingerprint
                or row["effect_kind"] != effect_kind
                or row["status"] != "prepared"
                or row["execution_owner"] != self._execution_owner
                or row["recovery_json"] is None
            ):
                raise FormalTaskViolation(
                    "UNIFIED_FOREGROUND_EFFECT_MISSING",
                    "Agent outcome promotion lost its exact prepared owner",
                    ErrorCode.CONFLICT,
                )
            if row["result_json"] is not None:
                existing = self._decode_result(row)
                if (
                    json.dumps(
                        existing,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    != encoded
                ):
                    raise FormalTaskViolation(
                        "UNIFIED_FOREGROUND_EFFECT_CONFLICT",
                        "unified foreground effect outcome is immutable",
                        ErrorCode.CONFLICT,
                    )
                return existing
            connection.execute(
                """
                UPDATE unified_foreground_effects
                   SET result_json=?
                 WHERE voice_identity_sha256=? AND status='prepared'
                   AND execution_owner=? AND result_json IS NULL
                """,
                (encoded, voice_identity_sha256, self._execution_owner),
            )
        return dict(result)

    def checkpoint_foreground_effect(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        effect_kind: str,
        result: Mapping[str, object] | None,
        recovery: Mapping[str, object],
    ) -> None:
        """Persist deterministic recovery facts before effect publication."""

        self._validate_voice_binding(voice_identity_sha256, fingerprint)
        if effect_kind not in self._FOREGROUND_EFFECT_KINDS:
            raise FormalTaskViolation(
                "INVALID_UNIFIED_FOREGROUND_EFFECT",
                "unified foreground effect kind is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )
        if result is not None and not isinstance(result, Mapping):
            raise TypeError("unified foreground effect checkpoint result is invalid")
        if not isinstance(recovery, Mapping):
            raise TypeError("unified foreground effect checkpoint is invalid")
        result_json = (
            None
            if result is None
            else json.dumps(
                dict(result),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        recovery_json = json.dumps(
            dict(recovery), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        if (
            result_json is not None and len(result_json.encode("utf-8")) > 262_144
        ) or len(recovery_json.encode("utf-8")) > 65_536:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_RESULT_TOO_LARGE",
                "unified foreground effect checkpoint exceeds its closed bound",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT fingerprint, status, execution_owner, lease_expires_at
                  FROM unified_committed_inputs
                 WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            row = connection.execute(
                """
                SELECT * FROM unified_foreground_effects
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if (
                parent is None
                or bytes(parent["fingerprint"]) != fingerprint
                or parent["status"] != "pending"
                or parent["execution_owner"] != self._execution_owner
                or not isinstance(parent["lease_expires_at"], (int, float))
                or float(parent["lease_expires_at"]) <= time.time()
                or row is None
                or bytes(row["fingerprint"]) != fingerprint
                or row["effect_kind"] != effect_kind
                or row["status"] != "prepared"
                or row["execution_owner"] != self._execution_owner
            ):
                raise FormalTaskViolation(
                    "UNIFIED_FOREGROUND_EFFECT_MISSING",
                    "foreground effect checkpoint lost its exact owner",
                    ErrorCode.CONFLICT,
                )
            if row["result_json"] is not None or row["recovery_json"] is not None:
                if (
                    row["result_json"] != result_json
                    or str(row["recovery_json"]) != recovery_json
                ):
                    raise FormalTaskViolation(
                        "UNIFIED_FOREGROUND_EFFECT_CONFLICT",
                        "unified foreground effect checkpoint is immutable",
                        ErrorCode.CONFLICT,
                    )
                return
            connection.execute(
                """
                UPDATE unified_foreground_effects
                   SET result_json=?, recovery_json=?
                 WHERE voice_identity_sha256=? AND status='prepared'
                   AND execution_owner=?
                """,
                (
                    result_json,
                    recovery_json,
                    voice_identity_sha256,
                    self._execution_owner,
                ),
            )

    def claim_foreground_effect_recovery(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
    ) -> UnifiedForegroundEffectAdmission:
        """Claim one checkpointed presentation under the recovered input lease."""

        self._validate_voice_binding(voice_identity_sha256, fingerprint)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT fingerprint, status, execution_owner, lease_expires_at
                  FROM unified_committed_inputs
                 WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            row = connection.execute(
                """
                SELECT * FROM unified_foreground_effects
                 WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if (
                parent is None
                or bytes(parent["fingerprint"]) != fingerprint
                or parent["status"] != "pending"
                or parent["execution_owner"] != self._execution_owner
                or not isinstance(parent["lease_expires_at"], (int, float))
                or float(parent["lease_expires_at"]) <= time.time()
                or row is None
                or bytes(row["fingerprint"]) != fingerprint
                or row["effect_kind"] != "authoritative_presentation"
                or row["result_json"] is None
                or row["recovery_json"] is None
            ):
                raise FormalTaskViolation(
                    "UNIFIED_FOREGROUND_EFFECT_MISSING",
                    "recoverable foreground presentation is unavailable",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            connection.execute(
                """
                UPDATE unified_foreground_effects SET execution_owner=?
                 WHERE voice_identity_sha256=?
                """,
                (self._execution_owner, voice_identity_sha256),
            )
            return UnifiedForegroundEffectAdmission(
                False,
                self._decode_result(row),
                effect_kind="authoritative_presentation",
                recovery=self._decode_recovery(row),
            )

    def complete_foreground_effect(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        effect_kind: str,
        result: Mapping[str, object],
    ) -> dict[str, object]:
        """Seal the exact control outcome immediately after the effect call."""

        self._validate_voice_binding(voice_identity_sha256, fingerprint)
        if effect_kind not in self._FOREGROUND_EFFECT_KINDS:
            raise FormalTaskViolation(
                "INVALID_UNIFIED_FOREGROUND_EFFECT",
                "unified foreground effect kind is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not isinstance(result, Mapping):
            raise TypeError("unified foreground effect result must be a mapping")
        encoded = json.dumps(
            dict(result), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        if len(encoded.encode("utf-8")) > 262_144:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_RESULT_TOO_LARGE",
                "unified foreground effect result exceeds its closed bound",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            parent = connection.execute(
                """
                SELECT fingerprint, status, execution_owner, lease_expires_at
                  FROM unified_committed_inputs
                 WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            row = connection.execute(
                """
                SELECT * FROM unified_foreground_effects
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if (
                parent is None
                or bytes(parent["fingerprint"]) != fingerprint
                or parent["status"] != "pending"
                or parent["execution_owner"] != self._execution_owner
                or not isinstance(parent["lease_expires_at"], (int, float))
                or float(parent["lease_expires_at"]) <= time.time()
                or row is None
                or bytes(row["fingerprint"]) != fingerprint
                or row["effect_kind"] != effect_kind
            ):
                raise FormalTaskViolation(
                    "UNIFIED_FOREGROUND_EFFECT_MISSING",
                    "unified foreground effect has no exact prepared identity",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if row["status"] == "completed":
                existing = self._decode_result(row)
                if (
                    json.dumps(
                        existing,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    != encoded
                ):
                    raise FormalTaskViolation(
                        "UNIFIED_FOREGROUND_EFFECT_CONFLICT",
                        "unified foreground effect outcome is immutable",
                        ErrorCode.CONFLICT,
                    )
                return existing
            if row["execution_owner"] != self._execution_owner:
                raise FormalTaskViolation(
                    "UNIFIED_FOREGROUND_EFFECT_RESULT_UNKNOWN",
                    "unified foreground effect cannot be taken over after process loss",
                    ErrorCode.RESULT_UNKNOWN,
                )
            if effect_kind == "authoritative_presentation" and (
                row["result_json"] is None or row["recovery_json"] is None
            ):
                raise FormalTaskViolation(
                    "UNIFIED_FOREGROUND_EFFECT_CHECKPOINT_MISSING",
                    "authoritative presentation was not durably checkpointed",
                    ErrorCode.RESULT_UNKNOWN,
                )
            if row["result_json"] is not None:
                existing = self._decode_result(row)
                if (
                    json.dumps(
                        existing,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    != encoded
                ):
                    raise FormalTaskViolation(
                        "UNIFIED_FOREGROUND_EFFECT_CONFLICT",
                        "unified foreground effect outcome is immutable",
                        ErrorCode.CONFLICT,
                    )
            connection.execute(
                """
                UPDATE unified_foreground_effects
                   SET status='completed', result_json=?
                 WHERE voice_identity_sha256=? AND status='prepared'
                   AND execution_owner=?
                """,
                (encoded, voice_identity_sha256, self._execution_owner),
            )
        return dict(result)

    def complete(
        self,
        *,
        voice_identity_sha256: str,
        fingerprint: bytes,
        result: Mapping[str, object],
        completed_at: str,
    ) -> dict[str, object]:
        if not isinstance(result, Mapping):
            raise TypeError("unified result must be a mapping")
        encoded = json.dumps(
            dict(result), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        if len(encoded.encode("utf-8")) > 262_144:
            raise FormalTaskViolation(
                "UNIFIED_INPUT_RESULT_TOO_LARGE",
                "unified control result exceeds its closed bound",
                ErrorCode.PROTOCOL_VIOLATION,
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM unified_committed_inputs
                WHERE voice_identity_sha256=?
                """,
                (voice_identity_sha256,),
            ).fetchone()
            if row is None or bytes(row["fingerprint"]) != fingerprint:
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_ADMISSION_MISSING",
                    "unified result has no exact durable admission",
                    ErrorCode.PROTOCOL_VIOLATION,
                )
            if row["status"] == "completed":
                existing = self._decode_result(row)
                if (
                    json.dumps(
                        existing,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    != encoded
                ):
                    raise FormalTaskViolation(
                        "UNIFIED_INPUT_RESULT_CONFLICT",
                        "unified input cannot complete with different control facts",
                        ErrorCode.CONFLICT,
                    )
                return existing
            if row["execution_owner"] != self._execution_owner:
                raise FormalTaskViolation(
                    "UNIFIED_INPUT_EXECUTION_LEASE_LOST",
                    "unified committed-input completion lost its execution lease",
                    ErrorCode.CONFLICT,
                )
            connection.execute(
                """
                UPDATE unified_committed_inputs
                   SET status='completed', result_json=?, completed_at=?,
                       lease_expires_at=NULL
                 WHERE voice_identity_sha256=? AND status='pending'
                   AND execution_owner=?
                """,
                (
                    encoded,
                    completed_at,
                    voice_identity_sha256,
                    self._execution_owner,
                ),
            )
        return dict(result)


__all__ = [
    "SqliteUnifiedCommittedInputJournal",
    "UnifiedForegroundEffectAdmission",
    "UnifiedInputAdmission",
]
