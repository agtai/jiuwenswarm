# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Server-owned, durable confirmation authority for P3-alpha mutations."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    ScopeRef,
    canonical_json_bytes,
)

from .formal_task_models import FormalTaskViolation
from .formal_task_models import ResolvedTaskContext
from .p3_model_resolution import ResolvedP3Model


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalTaskViolation(
            "INVALID_P3_CONFIRMATION",
            f"{field_name} must be an ISO-8601 timestamp",
            ErrorCode.INVALID_ARGUMENT,
        ) from exc
    if parsed.tzinfo is None:
        raise FormalTaskViolation(
            "INVALID_P3_CONFIRMATION",
            f"{field_name} must include a timezone",
            ErrorCode.INVALID_ARGUMENT,
        )
    return parsed.astimezone(UTC)


def _scope_key(scope: ScopeRef) -> str:
    payload = scope.to_dict()
    canonical_json_bytes(payload)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def p3_confirmation_intent_fingerprint(
    *,
    operation: str,
    command_id: str,
    target_task_id: str | None,
    context: ResolvedTaskContext | None,
    name: str | None = None,
    instruction: str | None = None,
    model: ResolvedP3Model | None = None,
) -> str:
    """Canonical server helper shared by the issuer and route verifier."""

    payload: dict[str, object] = {
        "operation": operation,
        "command_id": command_id,
        "target_task_id": target_task_id,
    }
    if operation == "task.create":
        if context is None or name is None or instruction is None or model is None:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "task.create confirmation requires exact resolved intent facts",
                ErrorCode.INVALID_ARGUMENT,
            )
        payload.update(
            {
                "context": context.to_dict(),
                "name": name,
                "instruction": instruction,
                "model_identity": model.identity,
                "model_config_version": model.config_version,
            }
        )
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class P3ConfirmationBinding:
    """Exact trusted facts a confirmation owner must bind before issuance."""

    principal_id: str
    scope: ScopeRef
    operation: str
    command_id: str
    target_task_id: str | None
    intent_fingerprint: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("principal_id", self.principal_id),
            ("operation", self.operation),
            ("command_id", self.command_id),
            ("intent_fingerprint", self.intent_fingerprint),
        ):
            if type(value) is not str or not value.strip():
                raise FormalTaskViolation(
                    "INVALID_P3_CONFIRMATION",
                    f"confirmation {field_name} must be a non-empty string",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if not isinstance(self.scope, ScopeRef):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "confirmation scope must be a ScopeRef",
                ErrorCode.INVALID_ARGUMENT,
            )
        if self.target_task_id is not None and (
            type(self.target_task_id) is not str or not self.target_task_id.strip()
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "confirmation target_task_id must be a non-empty string",
                ErrorCode.INVALID_ARGUMENT,
            )


@dataclass(frozen=True, slots=True)
class VerifiedP3Confirmation:
    confirmation_id: str
    expires_at: str
    replayed: bool


class P3ConfirmationVerifier(Protocol):
    def verify_and_consume(
        self,
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        *,
        now: str,
    ) -> VerifiedP3Confirmation: ...


class SqliteP3ConfirmationLedger:
    """Durable single-use ledger; only exact replays reuse a consumed record."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=10,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as exc:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_UNAVAILABLE",
                "formal task confirmation authority is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS p3_confirmations (
                    confirmation_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    target_task_id TEXT,
                    intent_fingerprint TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    consumed_at TEXT
                )
                """
            )
        except sqlite3.Error as exc:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_UNAVAILABLE",
                "formal task confirmation authority is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        finally:
            connection.close()

    def issue(
        self,
        binding: P3ConfirmationBinding,
        *,
        expires_at: str,
        now: str,
        confirmation_id: str | None = None,
    ) -> str:
        """Issue from a trusted server confirmation owner, never a raw route."""

        if _parse_utc(expires_at, "confirmation.expires_at") <= _parse_utc(now, "now"):
            raise FormalTaskViolation(
                "P3_CONFIRMATION_EXPIRED",
                "formal task confirmation has expired",
                ErrorCode.PERMISSION_DENIED,
            )
        identifier = confirmation_id or f"p3-confirm-{uuid.uuid4().hex}"
        if type(identifier) is not str or not identifier.strip():
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "confirmation_id must be a non-empty string",
                ErrorCode.INVALID_ARGUMENT,
            )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO p3_confirmations(
                    confirmation_id, principal_id, scope_key, operation,
                    command_id, target_task_id, intent_fingerprint,
                    expires_at, issued_at, consumed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    identifier,
                    binding.principal_id,
                    _scope_key(binding.scope),
                    binding.operation,
                    binding.command_id,
                    binding.target_task_id,
                    binding.intent_fingerprint,
                    expires_at,
                    now,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise FormalTaskViolation(
                "P3_CONFIRMATION_CONFLICT",
                "confirmation_id is already issued",
                ErrorCode.CONFLICT,
            ) from exc
        except sqlite3.Error as exc:
            connection.rollback()
            raise FormalTaskViolation(
                "P3_CONFIRMATION_UNAVAILABLE",
                "formal task confirmation authority is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        finally:
            connection.close()
        return identifier

    def verify_and_consume(
        self,
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        *,
        now: str,
    ) -> VerifiedP3Confirmation:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM p3_confirmations WHERE confirmation_id=?",
                (confirmation_id,),
            ).fetchone()
            if row is None:
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_INVALID",
                    "formal task confirmation is unavailable or invalid",
                    ErrorCode.PERMISSION_DENIED,
                )
            expected = (
                binding.principal_id,
                _scope_key(binding.scope),
                binding.operation,
                binding.command_id,
                binding.target_task_id,
                binding.intent_fingerprint,
            )
            actual = (
                row["principal_id"],
                row["scope_key"],
                row["operation"],
                row["command_id"],
                row["target_task_id"],
                row["intent_fingerprint"],
            )
            if actual != expected:
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_BINDING_MISMATCH",
                    "formal task confirmation does not bind the exact invocation",
                    ErrorCode.PERMISSION_DENIED,
                )
            if _parse_utc(row["expires_at"], "confirmation.expires_at") <= _parse_utc(
                now, "now"
            ):
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_EXPIRED",
                    "formal task confirmation has expired",
                    ErrorCode.PERMISSION_DENIED,
                )
            replayed = row["consumed_at"] is not None
            if not replayed:
                connection.execute(
                    "UPDATE p3_confirmations SET consumed_at=? WHERE confirmation_id=?",
                    (now, confirmation_id),
                )
            connection.commit()
            return VerifiedP3Confirmation(
                confirmation_id=confirmation_id,
                expires_at=row["expires_at"],
                replayed=replayed,
            )
        except FormalTaskViolation:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise FormalTaskViolation(
                "P3_CONFIRMATION_UNAVAILABLE",
                "formal task confirmation authority is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        finally:
            connection.close()


__all__ = [
    "P3ConfirmationBinding",
    "P3ConfirmationVerifier",
    "SqliteP3ConfirmationLedger",
    "VerifiedP3Confirmation",
    "p3_confirmation_intent_fingerprint",
]
