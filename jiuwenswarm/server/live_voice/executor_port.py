# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Truthful deterministic executor port for P3-alpha attempts."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from enum import StrEnum

from jiuwenswarm.common.schema.live_voice_contract_v2 import TerminalOutcome

from .task_core import DispatchIntent


class ExecutorPortViolation(ValueError):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ExecutorState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class ExecutorStatus:
    task_id: str
    attempt_id: str
    state: ExecutorState
    cancel_acknowledged: bool = False
    outcome: TerminalOutcome | None = None


@dataclass(frozen=True, slots=True)
class ExecutorCapabilities:
    supports_start: bool = True
    supports_status: bool = True
    supports_cancel_ack: bool = True
    supports_terminal_outcome: bool = True
    supports_restart_recovery: bool = False


class ExecutorPort:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._attempts: dict[str, tuple[DispatchIntent, ExecutorStatus]] = {}

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities()

    def dispatch(self, intent: DispatchIntent) -> tuple[bool, ExecutorStatus]:
        with self._lock:
            existing = self._attempts.get(intent.attempt_id)
            if existing is not None:
                if existing[0] == intent:
                    return False, existing[1]
                raise ExecutorPortViolation(
                    "ATTEMPT_DELIVERY_CONFLICT",
                    "attempt_id cannot change its dispatch intent",
                )
            status = ExecutorStatus(
                intent.task_id, intent.attempt_id, ExecutorState.ACCEPTED
            )
            self._attempts[intent.attempt_id] = (intent, status)
            return True, status

    def start(self, attempt_id: str) -> ExecutorStatus:
        with self._lock:
            intent, status = self._require(attempt_id)
            if status.state is not ExecutorState.ACCEPTED:
                raise ExecutorPortViolation(
                    "INVALID_EXECUTOR_TRANSITION",
                    "only an accepted attempt can start",
                )
            updated = replace(status, state=ExecutorState.RUNNING)
            self._attempts[attempt_id] = (intent, updated)
            return updated

    def cancel(self, attempt_id: str) -> ExecutorStatus:
        with self._lock:
            intent, status = self._require(attempt_id)
            if status.state is ExecutorState.TERMINAL:
                raise ExecutorPortViolation(
                    "ATTEMPT_ALREADY_TERMINAL",
                    "terminal attempts cannot accept cancellation",
                )
            updated = replace(status, cancel_acknowledged=True)
            self._attempts[attempt_id] = (intent, updated)
            return updated

    def finish(self, attempt_id: str, outcome: TerminalOutcome) -> ExecutorStatus:
        with self._lock:
            intent, status = self._require(attempt_id)
            if status.state is not ExecutorState.RUNNING:
                raise ExecutorPortViolation(
                    "INVALID_EXECUTOR_TRANSITION",
                    "only a running attempt can finish",
                )
            updated = replace(status, state=ExecutorState.TERMINAL, outcome=outcome)
            self._attempts[attempt_id] = (intent, updated)
            return updated

    def status(self, attempt_id: str) -> ExecutorStatus | None:
        with self._lock:
            entry = self._attempts.get(attempt_id)
            return None if entry is None else entry[1]

    def _require(self, attempt_id: str) -> tuple[DispatchIntent, ExecutorStatus]:
        entry = self._attempts.get(attempt_id)
        if entry is None:
            raise ExecutorPortViolation(
                "ATTEMPT_NOT_FOUND", "unknown attempts are not running or complete"
            )
        return entry
