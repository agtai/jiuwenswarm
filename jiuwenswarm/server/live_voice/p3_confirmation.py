# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Server-owned, durable confirmation authority for P3-alpha mutations."""

from __future__ import annotations

import hashlib
import hmac
import json
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
_P3_MUTATION_OPERATIONS = frozenset(
    {"task.create", "task.adjust", "task.cancel", "task.retry"}
)
_P3_RETRY_ELIGIBLE_OUTCOMES = frozenset({"cancelled", "completed"})
_P3_REPLAY_FENCE_MARKER = "__p3_confirmation_replay_fence_v1__"


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


def _binding_digest_from_values(
    *,
    principal_id: object,
    scope_key: object,
    operation: object,
    command_id: object,
    target_task_id: object,
    intent_fingerprint: object,
) -> str:
    payload = {
        "principal_id": principal_id,
        "scope_key": scope_key,
        "operation": operation,
        "command_id": command_id,
        "target_task_id": target_task_id,
        "intent_fingerprint": intent_fingerprint,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _binding_digest(binding: P3ConfirmationBinding) -> str:
    return _binding_digest_from_values(
        principal_id=binding.principal_id,
        scope_key=_scope_key(binding.scope),
        operation=binding.operation,
        command_id=binding.command_id,
        target_task_id=binding.target_task_id,
        intent_fingerprint=binding.intent_fingerprint,
    )


def _owned_issue_digest_from_values(
    *,
    binding_digest: str,
    expires_at: object,
    owner_session_id: object,
    owner_correlation_id: object,
    owner_generation: object,
) -> str:
    payload = {
        "binding_sha256": binding_digest,
        "expires_at": expires_at,
        "owner_session_id": owner_session_id,
        "owner_correlation_id": owner_correlation_id,
        "owner_generation": owner_generation,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _owned_issue_digest(issue: TrustedP3ConfirmationIssue) -> str:
    return _owned_issue_digest_from_values(
        binding_digest=_binding_digest(issue.binding),
        expires_at=issue.expires_at,
        owner_session_id=issue.owner.session_id,
        owner_correlation_id=issue.owner.correlation_id,
        owner_generation=issue.owner.owner_generation,
    )


@dataclass(frozen=True, slots=True)
class PreparedP3RetryFacts:
    """Exact server-derived predecessor snapshot frozen into one retry confirmation.

    Every field is read from Task Store authority and the original task
    specification.  The external request contributes only ``task_id``; a client
    can neither declare a predecessor, an attempt ordinal, nor a replacement
    intent, executor, model, capability, or side-effect class.  Any change to
    these facts between issuance and consumption changes the intent
    fingerprint, so a stale or forged retry fails closed with zero effect.
    """

    previous_attempt_id: str
    previous_outcome: str
    attempt_number: int
    name: str
    instruction: str
    executor_id: str
    required_capabilities: tuple[str, ...]
    side_effect_class: str
    attributes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("previous_attempt_id", self.previous_attempt_id),
            ("name", self.name),
            ("instruction", self.instruction),
            ("executor_id", self.executor_id),
            ("side_effect_class", self.side_effect_class),
        ):
            if type(value) is not str or not value.strip():
                raise FormalTaskViolation(
                    "INVALID_P3_CONFIRMATION",
                    f"retry confirmation {field_name} must be a non-empty string",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if self.previous_outcome not in _P3_RETRY_ELIGIBLE_OUTCOMES:
            raise FormalTaskViolation(
                "TASK_RETRY_OUTCOME_NOT_ELIGIBLE",
                "only cancelled or completed attempts can be retried",
                ErrorCode.CONFLICT,
            )
        if type(self.attempt_number) is not int or self.attempt_number not in {2, 3}:
            raise FormalTaskViolation(
                "TASK_RETRY_ATTEMPT_NUMBER_INVALID",
                "task.retry attempt_number must be 2 or 3",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(self.required_capabilities) is not tuple or any(
            type(item) is not str or not item.strip()
            for item in self.required_capabilities
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "retry confirmation capabilities must be exact non-empty strings",
                ErrorCode.INVALID_ARGUMENT,
            )
        if type(self.attributes) is not tuple or any(
            type(item) is not tuple
            or len(item) != 2
            or any(type(part) is not str or not part.strip() for part in item)
            for item in self.attributes
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "retry confirmation attributes must be exact string pairs",
                ErrorCode.INVALID_ARGUMENT,
            )

    def to_fingerprint_payload(self) -> dict[str, object]:
        return {
            "previous_attempt_id": self.previous_attempt_id,
            "previous_outcome": self.previous_outcome,
            "attempt_number": self.attempt_number,
            "name": self.name,
            "instruction": self.instruction,
            "executor_id": self.executor_id,
            "required_capabilities": list(self.required_capabilities),
            "side_effect_class": self.side_effect_class,
            "attributes": [list(item) for item in self.attributes],
        }


def p3_confirmation_intent_fingerprint(
    *,
    operation: str,
    command_id: str,
    target_task_id: str | None,
    context: ResolvedTaskContext | None,
    name: str | None = None,
    instruction: str | None = None,
    model: ResolvedP3Model | None = None,
    source: str = "structured",
    interaction_id: str | None = None,
    turn_id: str | None = None,
    commit_id: str | None = None,
    retry: PreparedP3RetryFacts | None = None,
) -> str:
    """Canonical server helper shared by the issuer and route verifier."""

    if retry is not None and operation != "task.retry":
        raise FormalTaskViolation(
            "INVALID_P3_CONFIRMATION",
            "only task.retry confirmations may carry frozen retry facts",
            ErrorCode.INVALID_ARGUMENT,
        )
    payload: dict[str, object] = {
        "operation": operation,
        "command_id": command_id,
        "target_task_id": target_task_id,
        "source": source,
        "interaction_id": interaction_id,
        "turn_id": turn_id,
        "commit_id": commit_id,
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
    elif operation == "task.adjust":
        if (
            context is not None
            or target_task_id is None
            or name is not None
            or instruction is None
            or model is not None
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "task.adjust confirmation requires one exact target and adjustment",
                ErrorCode.INVALID_ARGUMENT,
            )
        payload["adjustment"] = instruction
    elif operation == "task.retry":
        if (
            context is None
            or type(retry) is not PreparedP3RetryFacts
            or target_task_id is None
            or name is not None
            or instruction is not None
            or model is not None
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "task.retry confirmation requires the exact frozen retry snapshot",
                ErrorCode.INVALID_ARGUMENT,
            )
        payload.update(
            {
                "context": context.to_dict(),
                "retry": retry.to_fingerprint_payload(),
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
    """Bounded durable ledger with live authority and compact replay fences."""

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
            self._prepare_new_admission(connection, now=now)
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
                if self._is_replay_fence(existing):
                    if not self._replay_fence_issue_matches(existing, issue):
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
            self._prepare_new_admission(connection, now=now)
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

    @staticmethod
    def _is_replay_fence(row: sqlite3.Row) -> bool:
        return (
            row["consumed_at"] is not None
            and row["principal_id"] == _P3_REPLAY_FENCE_MARKER
            and row["operation"] == _P3_REPLAY_FENCE_MARKER
        )

    @staticmethod
    def _row_binding_digest(row: sqlite3.Row) -> str:
        return _binding_digest_from_values(
            principal_id=row["principal_id"],
            scope_key=row["scope_key"],
            operation=row["operation"],
            command_id=row["command_id"],
            target_task_id=row["target_task_id"],
            intent_fingerprint=row["intent_fingerprint"],
        )

    @classmethod
    def _row_owned_issue_digest(cls, row: sqlite3.Row) -> str:
        return _owned_issue_digest_from_values(
            binding_digest=cls._row_binding_digest(row),
            expires_at=row["expires_at"],
            owner_session_id=row["owner_session_id"],
            owner_correlation_id=row["owner_correlation_id"],
            owner_generation=row["owner_generation"],
        )

    @staticmethod
    def _replay_fence_binding_matches(
        row: sqlite3.Row,
        binding: P3ConfirmationBinding,
    ) -> bool:
        stored_digest = row["scope_key"]
        return type(stored_digest) is str and hmac.compare_digest(
            stored_digest,
            _binding_digest(binding),
        )

    @staticmethod
    def _replay_fence_issue_matches(
        row: sqlite3.Row,
        issue: TrustedP3ConfirmationIssue,
    ) -> bool:
        stored_digest = row["command_id"]
        return type(stored_digest) is str and hmac.compare_digest(
            stored_digest,
            _owned_issue_digest(issue),
        )

    def _prepare_new_admission(
        self,
        connection: sqlite3.Connection,
        *,
        now: str,
    ) -> None:
        """Reclaim heavy terminal rows inside the caller's write transaction."""

        current = _parse_utc(now, "now")
        rows = connection.execute(
            "SELECT * FROM p3_confirmations ORDER BY issued_at, confirmation_id"
        ).fetchall()
        for row in rows:
            expired = (
                _parse_utc(row["expires_at"], "confirmation.expires_at") <= current
            )
            if self._is_replay_fence(row):
                continue
            if row["consumed_at"] is None and not expired:
                continue
            binding_digest = self._row_binding_digest(row)
            owned_issue_digest = self._row_owned_issue_digest(row)
            connection.execute(
                """
                UPDATE p3_confirmations
                SET principal_id=?, scope_key=?, operation=?, command_id=?,
                    target_task_id=NULL, intent_fingerprint='',
                    owner_session_id=NULL, owner_correlation_id=NULL,
                    owner_generation=NULL, consumed_at=?
                WHERE confirmation_id=?
                """,
                (
                    _P3_REPLAY_FENCE_MARKER,
                    binding_digest,
                    _P3_REPLAY_FENCE_MARKER,
                    owned_issue_digest,
                    row["consumed_at"] or now,
                    row["confirmation_id"],
                ),
            )
        replay_fences = connection.execute(
            """
            SELECT confirmation_id
            FROM p3_confirmations
            WHERE consumed_at IS NOT NULL
              AND principal_id=?
              AND operation=?
            ORDER BY consumed_at DESC, issued_at DESC, confirmation_id DESC
            """,
            (_P3_REPLAY_FENCE_MARKER, _P3_REPLAY_FENCE_MARKER),
        ).fetchall()
        for fence in replay_fences[self._capacity :]:
            connection.execute(
                "DELETE FROM p3_confirmations WHERE confirmation_id=?",
                (fence["confirmation_id"],),
            )

    def _require_capacity(self, connection: sqlite3.Connection) -> None:
        retained = int(
            connection.execute(
                "SELECT COUNT(*) FROM p3_confirmations WHERE consumed_at IS NULL"
            ).fetchone()[0]
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
            if self._is_replay_fence(row):
                issue = TrustedP3ConfirmationIssue(
                    binding=binding,
                    owner=owner,
                    expires_at=str(row["expires_at"]),
                    confirmation_id=confirmation_id,
                )
                matched = self._replay_fence_issue_matches(row, issue)
            else:
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
                matched = actual == expected
            if not matched:
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
            replay_fence = self._is_replay_fence(row)
            if replay_fence:
                matched = self._replay_fence_binding_matches(row, binding)
            else:
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
                matched = actual == expected
            if not matched:
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
            replayed = replay_fence or row["consumed_at"] is not None
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
                "confirmation operation is not a supported P3 mutation",
                ErrorCode.INVALID_ARGUMENT,
            )
        if binding.operation == "task.create" and binding.target_task_id is not None:
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                "task.create confirmation must not bind a target task",
                ErrorCode.INVALID_ARGUMENT,
            )
        if (
            binding.operation in {"task.adjust", "task.cancel", "task.retry"}
            and binding.target_task_id is None
        ):
            raise FormalTaskViolation(
                "INVALID_P3_CONFIRMATION",
                f"{binding.operation} confirmation must bind an exact target task",
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
    "PreparedP3RetryFacts",
    "SqliteP3ConfirmationLedger",
    "TrustedP3ConfirmationIssue",
    "ValidatedP3ConfirmationForwarding",
    "VerifiedP3Confirmation",
    "p3_confirmation_intent_fingerprint",
]
