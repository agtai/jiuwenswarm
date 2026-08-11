# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Capability-checked interaction engine port without lifecycle ownership."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef


_MAX_OPERATION_COUNT = 64
_MAX_OPERATION_CHARS = 128
_MAX_OPERATION_UTF8_BYTES = 512
_MAX_IDENTITY_CHARS = 256
_MAX_IDENTITY_UTF8_BYTES = 1024
_MAX_PAYLOAD_ENTRIES = 32
_MAX_PAYLOAD_KEY_CHARS = 128
_MAX_PAYLOAD_KEY_UTF8_BYTES = 512
_MAX_PAYLOAD_VALUE_CHARS = 1024
_MAX_PAYLOAD_VALUE_UTF8_BYTES = 4096
_MAX_ACTIONS = 1024


class InteractionEngineViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class InteractionAction:
    action_id: str
    operation: str
    interaction_id: str
    scope: ScopeRef
    payload: tuple[tuple[str, str], ...] = ()


def _is_canonical_text(value: object, *, max_chars: int, max_utf8_bytes: int) -> bool:
    if (
        type(value) is not str
        or not value
        or len(value) > max_chars
        or value != value.strip()
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= max_utf8_bytes
    except UnicodeEncodeError:
        return False


def _canonical_scope(value: object) -> ScopeRef:
    if not isinstance(value, ScopeRef):
        raise InteractionEngineViolation(
            "INVALID_SCOPE", "scope must be a canonical ScopeRef"
        )
    try:
        canonical = ScopeRef.from_dict(value.to_dict())
    except Exception:
        raise InteractionEngineViolation(
            "INVALID_SCOPE", "scope must be a canonical ScopeRef"
        ) from None
    if any(
        item is not None
        and not _is_canonical_text(
            item,
            max_chars=_MAX_IDENTITY_CHARS,
            max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
        )
        for item in (
            canonical.subject_id,
            canonical.project_id,
            canonical.session_id,
        )
    ):
        raise InteractionEngineViolation(
            "INVALID_SCOPE", "scope identities must be canonical bounded strings"
        )
    return canonical


class InteractionEnginePort:
    def __init__(
        self,
        operations: frozenset[str],
        *,
        scope: ScopeRef | None = None,
        max_actions: int = 256,
    ) -> None:
        if (
            not isinstance(operations, frozenset)
            or not operations
            or len(operations) > _MAX_OPERATION_COUNT
            or any(
                not _is_canonical_text(
                    item,
                    max_chars=_MAX_OPERATION_CHARS,
                    max_utf8_bytes=_MAX_OPERATION_UTF8_BYTES,
                )
                for item in operations
            )
        ):
            raise InteractionEngineViolation(
                "INVALID_CAPABILITIES", "at least one valid operation is required"
            )
        canonical_scope = None if scope is None else _canonical_scope(scope)
        if type(max_actions) is not int or not 0 < max_actions <= _MAX_ACTIONS:
            raise InteractionEngineViolation(
                "INVALID_CAPACITY", "max_actions exceeds the bounded positive range"
            )
        self._operations = frozenset(operations)
        self._scope = canonical_scope
        self._max_actions = max_actions
        self._lock = threading.RLock()
        self._accepted: dict[str, InteractionAction] = {}

    def propose(self, action: InteractionAction) -> tuple[bool, InteractionAction]:
        if not isinstance(action, InteractionAction):
            raise InteractionEngineViolation(
                "INVALID_ACTION", "action must use the canonical InteractionAction type"
            )
        if not _is_canonical_text(
            action.operation,
            max_chars=_MAX_OPERATION_CHARS,
            max_utf8_bytes=_MAX_OPERATION_UTF8_BYTES,
        ):
            raise InteractionEngineViolation(
                "INVALID_ACTION", "action operation must be a non-empty string"
            )
        canonical_scope = _canonical_scope(action.scope)
        if self._scope is not None and canonical_scope != self._scope:
            raise InteractionEngineViolation(
                "ACTION_SCOPE_MISMATCH",
                "action scope must match the exact interaction owner scope",
            )
        if action.operation not in self._operations:
            raise InteractionEngineViolation(
                "CAPABILITY_UNSUPPORTED",
                f"operation {action.operation!r} is unsupported",
            )
        if not _is_canonical_text(
            action.action_id,
            max_chars=_MAX_IDENTITY_CHARS,
            max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
        ) or not _is_canonical_text(
            action.interaction_id,
            max_chars=_MAX_IDENTITY_CHARS,
            max_utf8_bytes=_MAX_IDENTITY_UTF8_BYTES,
        ):
            raise InteractionEngineViolation(
                "INVALID_ACTION_IDENTITY", "action identities must be non-empty"
            )
        if (
            type(action.payload) is not tuple
            or len(action.payload) > _MAX_PAYLOAD_ENTRIES
            or any(
                type(item) is not tuple
                or len(item) != 2
                or not _is_canonical_text(
                    item[0],
                    max_chars=_MAX_PAYLOAD_KEY_CHARS,
                    max_utf8_bytes=_MAX_PAYLOAD_KEY_UTF8_BYTES,
                )
                or not _is_canonical_text(
                    item[1],
                    max_chars=_MAX_PAYLOAD_VALUE_CHARS,
                    max_utf8_bytes=_MAX_PAYLOAD_VALUE_UTF8_BYTES,
                )
                for item in action.payload
            )
        ):
            raise InteractionEngineViolation(
                "INVALID_ACTION", "action payload must be an immutable string tuple"
            )
        with self._lock:
            existing = self._accepted.get(action.action_id)
            if existing is not None:
                if existing == action:
                    return False, existing
                raise InteractionEngineViolation(
                    "ACTION_ID_CONFLICT", "action_id cannot change its meaning"
                )
            if len(self._accepted) >= self._max_actions:
                raise InteractionEngineViolation(
                    "ACTION_LEDGER_FULL",
                    "bounded interaction action ledger is full",
                )
            self._accepted[action.action_id] = action
            return True, action

    def accepted(self) -> tuple[InteractionAction, ...]:
        with self._lock:
            return tuple(self._accepted.values())
