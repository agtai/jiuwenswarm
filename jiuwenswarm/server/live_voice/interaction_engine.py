# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Capability-checked interaction engine port without lifecycle ownership."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from jiuwenswarm.common.schema.live_voice_contract_v2 import ScopeRef


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


class InteractionEnginePort:
    def __init__(self, operations: frozenset[str]) -> None:
        if not operations or any(not item.strip() for item in operations):
            raise InteractionEngineViolation(
                "INVALID_CAPABILITIES", "at least one valid operation is required"
            )
        self._operations = frozenset(operations)
        self._lock = threading.RLock()
        self._accepted: dict[str, InteractionAction] = {}

    def propose(self, action: InteractionAction) -> tuple[bool, InteractionAction]:
        if action.operation not in self._operations:
            raise InteractionEngineViolation(
                "CAPABILITY_UNSUPPORTED",
                f"operation {action.operation!r} is unsupported",
            )
        if not action.action_id.strip() or not action.interaction_id.strip():
            raise InteractionEngineViolation(
                "INVALID_ACTION_IDENTITY", "action identities must be non-empty"
            )
        with self._lock:
            existing = self._accepted.get(action.action_id)
            if existing is not None:
                if existing == action:
                    return False, existing
                raise InteractionEngineViolation(
                    "ACTION_ID_CONFLICT", "action_id cannot change its meaning"
                )
            self._accepted[action.action_id] = action
            return True, action

    def accepted(self) -> tuple[InteractionAction, ...]:
        with self._lock:
            return tuple(self._accepted.values())
