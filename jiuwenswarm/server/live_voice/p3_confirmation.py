# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Server-owned, durable confirmation authority for P3-alpha mutations."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


P3_CONFIRMATION_MAX_TTL = timedelta(minutes=2)
P3_CONFIRMATION_MAX_CAPACITY = 4_096
_P3_MUTATION_OPERATIONS = frozenset({"task.create", "task.cancel"})


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


def _validate_capacity(capacity: int) -> int:
    if (
        type(capacity) is not int
        or capacity <= 0
        or capacity > P3_CONFIRMATION_MAX_CAPACITY
    ):
        raise FormalTaskViolation(
            "INVALID_P3_CONFIRMATION_CAPACITY",
            "confirmation capacity must be between 1 and the fixed hard maximum",
            ErrorCode.INVALID_ARGUMENT,
        )
    return capacity


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


@dataclass(frozen=True, slots=True)
class P3ConfirmationOwnerContext:
    """Server-owned route facts that are never accepted as browser authority."""

    session_id: str
    correlation_id: str
    owner_generation: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("session_id", self.session_id),
            ("correlation_id", self.correlation_id),
        ):
            if type(value) is not str or not value.strip():
                raise FormalTaskViolation(
                    "INVALID_P3_CONFIRMATION_OWNER_CONTEXT",
                    f"confirmation owner {field_name} must be a non-empty string",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if type(self.owner_generation) is not int or self.owner_generation <= 0:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_OWNER_CONTEXT",
                "confirmation owner_generation must be a positive integer",
                ErrorCode.INVALID_ARGUMENT,
            )


@dataclass(frozen=True, slots=True)
class TrustedP3ConfirmationIssue:
    """Typed input assembled only after Main resolves product authority.

    This intentionally has no ``from_dict`` parser.  Browser claims must first be
    compared with server-owned authority and owner-generation state by Main.
    """

    binding: P3ConfirmationBinding
    owner: P3ConfirmationOwnerContext
    expires_at: str
    confirmation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, P3ConfirmationBinding):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "trusted confirmation binding is required",
                ErrorCode.INVALID_ARGUMENT,
            )
        if not isinstance(self.owner, P3ConfirmationOwnerContext):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_OWNER_CONTEXT",
                "trusted confirmation owner context is required",
                ErrorCode.INVALID_ARGUMENT,
            )
        _parse_utc(self.expires_at, "confirmation.expires_at")
        if type(self.confirmation_id) is not str or not self.confirmation_id.strip():
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "trusted confirmation_id must be a stable non-empty string",
                ErrorCode.INVALID_ARGUMENT,
            )


@dataclass(frozen=True, slots=True)
class IssuedP3Confirmation:
    """Issuance receipt only; it does not report mutation acceptance/completion."""

    confirmation_id: str
    expires_at: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class ValidatedP3ConfirmationForwarding:
    """Persisted owner match, not a product permit; mutation remains unconsumed."""

    confirmation_id: str
    expires_at: str
    binding: P3ConfirmationBinding
    owner: P3ConfirmationOwnerContext


class P3ConfirmationVerifier(Protocol):
    def verify_and_consume(
        self,
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        *,
        now: str,
    ) -> VerifiedP3Confirmation: ...


class SqliteP3ConfirmationLedger:
    """Bounded durable ledger; records are never evicted or overwritten."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        capacity: int = P3_CONFIRMATION_MAX_CAPACITY,
    ) -> None:
        self._capacity = _validate_capacity(capacity)
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
            connection.execute("BEGIN IMMEDIATE")
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
                    consumed_at TEXT,
                    owner_session_id TEXT,
                    owner_correlation_id TEXT,
                    owner_generation INTEGER
                )
                """
            )
            existing_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(p3_confirmations)"
                ).fetchall()
            }
            for column_name, column_type in (
                ("owner_session_id", "TEXT"),
                ("owner_correlation_id", "TEXT"),
                ("owner_generation", "INTEGER"),
            ):
                if column_name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE p3_confirmations "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
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
        """Legacy low-level issue API; product code must use the bounded owner."""

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
            if (
                connection.execute(
                    "SELECT 1 FROM p3_confirmations WHERE confirmation_id=?",
                    (identifier,),
                ).fetchone()
                is not None
            ):
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_CONFLICT",
                    "confirmation_id is already issued",
                    ErrorCode.CONFLICT,
                )
            self._require_capacity(connection)
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
        except FormalTaskViolation:
            connection.rollback()
            raise
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

    def issue_owned(
        self,
        issue: TrustedP3ConfirmationIssue,
        *,
        now: str,
    ) -> IssuedP3Confirmation:
        """Atomically issue or replay an exact server-owned confirmation."""

        identifier = issue.confirmation_id
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM p3_confirmations WHERE confirmation_id=?",
                (identifier,),
            ).fetchone()
            expected = (
                issue.binding.principal_id,
                _scope_key(issue.binding.scope),
                issue.binding.operation,
                issue.binding.command_id,
                issue.binding.target_task_id,
                issue.binding.intent_fingerprint,
                issue.expires_at,
                issue.owner.session_id,
                issue.owner.correlation_id,
                issue.owner.owner_generation,
            )
            if existing is not None:
                actual = (
                    existing["principal_id"],
                    existing["scope_key"],
                    existing["operation"],
                    existing["command_id"],
                    existing["target_task_id"],
                    existing["intent_fingerprint"],
                    existing["expires_at"],
                    existing["owner_session_id"],
                    existing["owner_correlation_id"],
                    existing["owner_generation"],
                )
                if actual != expected:
                    raise FormalTaskViolation(
                        "P3_CONFIRMATION_CONFLICT",
                        "confirmation_id is already issued for another request",
                        ErrorCode.CONFLICT,
                    )
                connection.commit()
                return IssuedP3Confirmation(
                    confirmation_id=identifier,
                    expires_at=str(existing["expires_at"]),
                    replayed=True,
                )
            self._require_capacity(connection)
            connection.execute(
                """
                INSERT INTO p3_confirmations(
                    confirmation_id, principal_id, scope_key, operation,
                    command_id, target_task_id, intent_fingerprint,
                    expires_at, issued_at, consumed_at,
                    owner_session_id, owner_correlation_id, owner_generation
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    identifier,
                    issue.binding.principal_id,
                    _scope_key(issue.binding.scope),
                    issue.binding.operation,
                    issue.binding.command_id,
                    issue.binding.target_task_id,
                    issue.binding.intent_fingerprint,
                    issue.expires_at,
                    now,
                    issue.owner.session_id,
                    issue.owner.correlation_id,
                    issue.owner.owner_generation,
                ),
            )
            connection.commit()
            return IssuedP3Confirmation(
                confirmation_id=identifier,
                expires_at=issue.expires_at,
                replayed=False,
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

    def _require_capacity(self, connection: sqlite3.Connection) -> None:
        retained = int(
            connection.execute("SELECT COUNT(*) FROM p3_confirmations").fetchone()[0]
        )
        if retained >= self._capacity:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_CAPACITY_EXCEEDED",
                "formal task confirmation ledger has reached its hard capacity",
                ErrorCode.UNAVAILABLE,
            )

    def validate_owned_for_forwarding(
        self,
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        owner: P3ConfirmationOwnerContext,
        *,
        now: str,
    ) -> ValidatedP3ConfirmationForwarding:
        """Validate exact owner/binding facts without consuming the record."""

        connection = self._connect()
        try:
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
                owner.session_id,
                owner.correlation_id,
                owner.owner_generation,
            )
            actual = (
                row["principal_id"],
                row["scope_key"],
                row["operation"],
                row["command_id"],
                row["target_task_id"],
                row["intent_fingerprint"],
                row["owner_session_id"],
                row["owner_correlation_id"],
                row["owner_generation"],
            )
            if actual != expected:
                raise FormalTaskViolation(
                    "P3_CONFIRMATION_BINDING_MISMATCH",
                    "formal task confirmation does not bind the exact owner invocation",
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
            return ValidatedP3ConfirmationForwarding(
                confirmation_id=confirmation_id,
                expires_at=str(row["expires_at"]),
                binding=binding,
                owner=owner,
            )
        except sqlite3.Error as exc:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_UNAVAILABLE",
                "formal task confirmation authority is unavailable",
                ErrorCode.UNAVAILABLE,
            ) from exc
        finally:
            connection.close()

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


class BoundedP3ConfirmationOwner:
    """Default-off trusted issuer with a fixed TTL and no background resources."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        enabled: bool = False,
        capacity: int = P3_CONFIRMATION_MAX_CAPACITY,
    ) -> None:
        if type(enabled) is not bool:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_OWNER",
                "confirmation owner enabled must be a boolean",
                ErrorCode.INVALID_ARGUMENT,
            )
        validated_capacity = _validate_capacity(capacity)
        self._enabled = enabled
        self._ledger = (
            SqliteP3ConfirmationLedger(
                database_path,
                capacity=validated_capacity,
            )
            if enabled
            else None
        )

    @property
    def raw_verifier(self) -> P3ConfirmationVerifier | None:
        """Return the low-level verifier, which is not a product permit.

        Main must first validate current server-owned context and wrap forwarding;
        injecting this verifier alone does not make a mutation route product-safe.
        """

        return self._ledger

    def issue(
        self,
        issue: TrustedP3ConfirmationIssue,
        *,
        now: str,
    ) -> IssuedP3Confirmation:
        ledger = self._require_ledger()
        if not isinstance(issue, TrustedP3ConfirmationIssue):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "trusted server confirmation issue is required",
                ErrorCode.INVALID_ARGUMENT,
            )
        self._validate_trusted_issue(issue, now=now)
        return ledger.issue_owned(issue, now=now)

    def validate_for_forwarding(
        self,
        confirmation_id: str,
        binding: P3ConfirmationBinding,
        owner: P3ConfirmationOwnerContext,
        *,
        now: str,
    ) -> ValidatedP3ConfirmationForwarding:
        """Compare stored facts with current server-owned context before forwarding.

        Main remains responsible for current-owner validation and for constructing
        the permit wrapper that guards use of ``raw_verifier``.
        """

        ledger = self._require_ledger()
        self._validate_binding_owner(binding, owner)
        return ledger.validate_owned_for_forwarding(
            confirmation_id,
            binding,
            owner,
            now=now,
        )

    def _require_ledger(self) -> SqliteP3ConfirmationLedger:
        if not self._enabled or self._ledger is None:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_ISSUER_UNAVAILABLE",
                "formal task confirmation issuer is disabled or unavailable",
                ErrorCode.UNAVAILABLE,
            )
        return self._ledger

    @staticmethod
    def _validate_trusted_issue(
        issue: TrustedP3ConfirmationIssue,
        *,
        now: str,
    ) -> None:
        BoundedP3ConfirmationOwner._validate_binding_owner(issue.binding, issue.owner)
        current = _parse_utc(now, "now")
        expires = _parse_utc(issue.expires_at, "confirmation.expires_at")
        if expires <= current:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_EXPIRED",
                "formal task confirmation has expired",
                ErrorCode.PERMISSION_DENIED,
            )
        if expires - current > P3_CONFIRMATION_MAX_TTL:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_TTL_EXCEEDED",
                "formal task confirmation exceeds the fixed maximum TTL",
                ErrorCode.INVALID_ARGUMENT,
            )

    @staticmethod
    def _validate_binding_owner(
        binding: P3ConfirmationBinding,
        owner: P3ConfirmationOwnerContext,
    ) -> None:
        if not isinstance(binding, P3ConfirmationBinding) or not isinstance(
            owner, P3ConfirmationOwnerContext
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_OWNER_CONTEXT",
                "exact trusted confirmation binding and owner context are required",
                ErrorCode.INVALID_ARGUMENT,
            )
        if binding.operation not in _P3_MUTATION_OPERATIONS:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION_OPERATION",
                "confirmation operation must be task.create or task.cancel",
                ErrorCode.INVALID_ARGUMENT,
            )
        if binding.operation == "task.create" and binding.target_task_id is not None:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "task.create confirmation must not bind a target task",
                ErrorCode.INVALID_ARGUMENT,
            )
        if binding.operation == "task.cancel" and binding.target_task_id is None:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "task.cancel confirmation must bind an exact target task",
                ErrorCode.INVALID_ARGUMENT,
            )
        if binding.principal_id != binding.scope.subject_id:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_BINDING_MISMATCH",
                "confirmation principal does not match the resolved scope",
                ErrorCode.PERMISSION_DENIED,
            )
        if binding.scope.session_id != owner.session_id:
            raise FormalTaskViolation(
                "P3_CONFIRMATION_BINDING_MISMATCH",
                "confirmation session does not match the current owner",
                ErrorCode.PERMISSION_DENIED,
            )


__all__ = [
    "BoundedP3ConfirmationOwner",
    "IssuedP3Confirmation",
    "P3_CONFIRMATION_MAX_CAPACITY",
    "P3_CONFIRMATION_MAX_TTL",
    "P3ConfirmationBinding",
    "P3ConfirmationOwnerContext",
    "P3ConfirmationVerifier",
    "SqliteP3ConfirmationLedger",
    "TrustedP3ConfirmationIssue",
    "ValidatedP3ConfirmationForwarding",
    "VerifiedP3Confirmation",
    "p3_confirmation_intent_fingerprint",
]
