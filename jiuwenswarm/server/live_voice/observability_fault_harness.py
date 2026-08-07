# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Bounded, payload-free fault exporter for Live Voice observability tests.

The harness is an injected exporter callback, not an exporter backend, product
registration, route-fact issuer, retry owner, or business authority.  It retains
only a fixed number of content-free attempt facts.  The existing observability
exporter buffer continues to own worker, timeout, backpressure, and close truth.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Final, Literal, TypeAlias

from jiuwenswarm.server.live_voice.observability import (
    LiveVoiceMetric,
    LiveVoiceObservation,
)
from jiuwenswarm.server.live_voice.observability_exporter import ExportRecord


MAX_OBSERVABILITY_FAULT_STEPS: Final = 16


class ObservabilityFaultAction(StrEnum):
    """Closed fault script vocabulary."""

    DELIVER = "deliver"
    RAISE = "raise"
    STALL = "stall"


class ObservabilityFaultOutcome(StrEnum):
    """Closed, content-free attempt outcome vocabulary."""

    STALLED = "stalled"
    DELIVERED = "delivered"
    RAISED = "raised"
    CANCELLED = "cancelled"


class ObservabilityFaultHarnessState(StrEnum):
    """Current leaf state; this is not exporter-worker lifecycle truth."""

    DISABLED = "disabled"
    READY = "ready"
    STALLED = "stalled"
    EXHAUSTED = "exhausted"


ObservabilityFaultRecordKind: TypeAlias = Literal["observation", "metric"]


class ObservabilityFaultHarnessError(RuntimeError):
    """Base class for stable, injected harness outcomes."""


class InjectedObservabilityExportError(ObservabilityFaultHarnessError):
    """One scripted exporter callback failure."""


class ObservabilityFaultScriptExhaustedError(ObservabilityFaultHarnessError):
    """The bounded script has no remaining attempt slot."""


@dataclass(frozen=True, slots=True)
class ObservabilityFaultAttemptSnapshot:
    """Payload-free identity and state for one attempted export."""

    attempt_id: str
    record_kind: ObservabilityFaultRecordKind
    action: ObservabilityFaultAction
    outcome: ObservabilityFaultOutcome


@dataclass(frozen=True, slots=True)
class ObservabilityFaultHarnessSnapshot:
    """Only closed vocabulary, counters, and harness-issued IDs."""

    enabled: bool
    state: ObservabilityFaultHarnessState
    script_capacity: int
    configured_steps: int
    consumed_steps: int
    retained_attempts: int
    active_stalls: int
    delivered_attempts: int
    raised_attempts: int
    cancelled_attempts: int
    rejected_invalid_records: int
    rejected_exhausted: int
    attempts: tuple[ObservabilityFaultAttemptSnapshot, ...]
    business_result_changed: bool = False
    lifecycle_authority_exercised: bool = False
    cancel_authority_exercised: bool = False
    success_authority_exercised: bool = False

    def __post_init__(self) -> None:
        if any(
            (
                self.business_result_changed,
                self.lifecycle_authority_exercised,
                self.cancel_authority_exercised,
                self.success_authority_exercised,
            )
        ):
            raise ValueError("observability fault harness has no business authority")


@dataclass(slots=True)
class _Attempt:
    attempt_id: str
    record_kind: ObservabilityFaultRecordKind
    action: ObservabilityFaultAction
    outcome: ObservabilityFaultOutcome

    def snapshot(self) -> ObservabilityFaultAttemptSnapshot:
        return ObservabilityFaultAttemptSnapshot(
            attempt_id=self.attempt_id,
            record_kind=self.record_kind,
            action=self.action,
            outcome=self.outcome,
        )


@dataclass(slots=True)
class _StallControl:
    event: asyncio.Event
    resolution: Literal["release", "cancel"] | None = None


class DisabledObservabilityFaultHarness:
    """Singleton feature-off value with no exporter callback or resources."""

    __slots__ = ()
    enabled = False
    exporter = None

    def snapshot(self) -> ObservabilityFaultHarnessSnapshot:
        return ObservabilityFaultHarnessSnapshot(
            enabled=False,
            state=ObservabilityFaultHarnessState.DISABLED,
            script_capacity=MAX_OBSERVABILITY_FAULT_STEPS,
            configured_steps=0,
            consumed_steps=0,
            retained_attempts=0,
            active_stalls=0,
            delivered_attempts=0,
            raised_attempts=0,
            cancelled_attempts=0,
            rejected_invalid_records=0,
            rejected_exhausted=0,
            attempts=(),
        )


class LiveVoiceObservabilityFaultHarness:
    """Async fault callback with a fixed, non-evicting attempt ledger.

    No record payload or product identity is retained.  A scripted step is used
    exactly once and is never retried by this leaf.  Cancelling a callback or a
    waiter changes only its content-free attempt outcome; the attempt remains in
    the ledger until the harness itself is discarded.
    """

    __slots__ = (
        "_attempts",
        "_lock",
        "_next_step",
        "_rejected_exhausted",
        "_rejected_invalid_records",
        "_script",
        "_stalls",
    )
    enabled = True

    def __init__(
        self,
        script: tuple[ObservabilityFaultAction, ...],
        *,
        _construction_token: object,
    ) -> None:
        if _construction_token is not _CONSTRUCTION_TOKEN:
            raise ValueError("use create_observability_fault_harness")
        self._script = script
        self._lock = Lock()
        self._attempts: list[_Attempt] = []
        self._stalls: dict[str, _StallControl] = {}
        self._next_step = 0
        self._rejected_invalid_records = 0
        self._rejected_exhausted = 0

    @property
    def exporter(self) -> LiveVoiceObservabilityFaultHarness:
        """Return the native async callable expected by the product Adapter."""

        return self

    async def __call__(self, record: ExportRecord) -> None:
        record_kind = self._record_kind(record)
        if record_kind is None:
            with self._lock:
                self._rejected_invalid_records += 1
            raise TypeError("fault harness accepts only exact observability records")

        with self._lock:
            if self._next_step >= len(self._script):
                self._rejected_exhausted += 1
                raise ObservabilityFaultScriptExhaustedError(
                    "observability fault script is exhausted"
                )
            step_index = self._next_step
            self._next_step += 1
            action = self._script[step_index]
            attempt = _Attempt(
                attempt_id=f"xobs-fault-attempt-{step_index:02d}",
                record_kind=record_kind,
                action=action,
                outcome=(
                    ObservabilityFaultOutcome.STALLED
                    if action is ObservabilityFaultAction.STALL
                    else (
                        ObservabilityFaultOutcome.RAISED
                        if action is ObservabilityFaultAction.RAISE
                        else ObservabilityFaultOutcome.DELIVERED
                    )
                ),
            )
            self._attempts.append(attempt)
            if action is ObservabilityFaultAction.STALL:
                control = _StallControl(event=asyncio.Event())
                self._stalls[attempt.attempt_id] = control
            else:
                control = None

        if action is ObservabilityFaultAction.DELIVER:
            return
        if action is ObservabilityFaultAction.RAISE:
            raise InjectedObservabilityExportError(
                "observability export failure was injected"
            )

        assert control is not None
        try:
            await control.event.wait()
        except asyncio.CancelledError:
            self._finish_attempt(
                attempt.attempt_id, ObservabilityFaultOutcome.CANCELLED
            )
            raise
        with self._lock:
            resolution = control.resolution
        if resolution == "release":
            self._finish_attempt(
                attempt.attempt_id, ObservabilityFaultOutcome.DELIVERED
            )
            return
        self._finish_attempt(attempt.attempt_id, ObservabilityFaultOutcome.CANCELLED)
        raise asyncio.CancelledError

    def release_stall(self, attempt_id: str) -> bool:
        """Explicitly allow one retained stalled callback to return."""

        return self._resolve_stall(attempt_id, "release")

    def cancel_stall(self, attempt_id: str) -> bool:
        """Explicitly cancel one retained stalled callback without business cancel."""

        return self._resolve_stall(attempt_id, "cancel")

    def snapshot(self) -> ObservabilityFaultHarnessSnapshot:
        with self._lock:
            attempts = tuple(attempt.snapshot() for attempt in self._attempts)
            active_stalls = len(self._stalls)
            next_step = self._next_step
            rejected_invalid_records = self._rejected_invalid_records
            rejected_exhausted = self._rejected_exhausted
        if active_stalls:
            state = ObservabilityFaultHarnessState.STALLED
        elif next_step >= len(self._script):
            state = ObservabilityFaultHarnessState.EXHAUSTED
        else:
            state = ObservabilityFaultHarnessState.READY
        return ObservabilityFaultHarnessSnapshot(
            enabled=True,
            state=state,
            script_capacity=MAX_OBSERVABILITY_FAULT_STEPS,
            configured_steps=len(self._script),
            consumed_steps=next_step,
            retained_attempts=len(attempts),
            active_stalls=active_stalls,
            delivered_attempts=sum(
                attempt.outcome is ObservabilityFaultOutcome.DELIVERED
                for attempt in attempts
            ),
            raised_attempts=sum(
                attempt.outcome is ObservabilityFaultOutcome.RAISED
                for attempt in attempts
            ),
            cancelled_attempts=sum(
                attempt.outcome is ObservabilityFaultOutcome.CANCELLED
                for attempt in attempts
            ),
            rejected_invalid_records=rejected_invalid_records,
            rejected_exhausted=rejected_exhausted,
            attempts=attempts,
        )

    @staticmethod
    def _record_kind(record: object) -> ObservabilityFaultRecordKind | None:
        if type(record) is LiveVoiceObservation:
            return "observation"
        if type(record) is LiveVoiceMetric:
            return "metric"
        return None

    def _resolve_stall(
        self,
        attempt_id: str,
        resolution: Literal["release", "cancel"],
    ) -> bool:
        if type(attempt_id) is not str or not attempt_id:
            return False
        with self._lock:
            control = self._stalls.get(attempt_id)
            if control is None or control.resolution is not None:
                return False
            control.resolution = resolution
            event = control.event
        event.set()
        return True

    def _finish_attempt(
        self,
        attempt_id: str,
        outcome: ObservabilityFaultOutcome,
    ) -> None:
        with self._lock:
            for attempt in self._attempts:
                if attempt.attempt_id == attempt_id:
                    attempt.outcome = outcome
                    break
            self._stalls.pop(attempt_id, None)


_CONSTRUCTION_TOKEN = object()
_DISABLED_HARNESS = DisabledObservabilityFaultHarness()


def create_observability_fault_harness(
    *,
    enabled: bool = False,
    script: object = (),
) -> DisabledObservabilityFaultHarness | LiveVoiceObservabilityFaultHarness:
    """Create the leaf without inspecting injected input when feature-off."""

    if enabled is not True:
        return _DISABLED_HARNESS
    if type(script) is not tuple:
        raise TypeError("fault script must be an exact tuple")
    if not script or len(script) > MAX_OBSERVABILITY_FAULT_STEPS:
        raise ValueError(
            "fault script must contain between one and sixteen fixed steps"
        )
    if any(type(step) is not ObservabilityFaultAction for step in script):
        raise TypeError("fault script must contain ObservabilityFaultAction values")
    return LiveVoiceObservabilityFaultHarness(
        script,
        _construction_token=_CONSTRUCTION_TOKEN,
    )


__all__ = [
    "MAX_OBSERVABILITY_FAULT_STEPS",
    "DisabledObservabilityFaultHarness",
    "InjectedObservabilityExportError",
    "LiveVoiceObservabilityFaultHarness",
    "ObservabilityFaultAction",
    "ObservabilityFaultAttemptSnapshot",
    "ObservabilityFaultHarnessError",
    "ObservabilityFaultHarnessSnapshot",
    "ObservabilityFaultHarnessState",
    "ObservabilityFaultOutcome",
    "ObservabilityFaultRecordKind",
    "ObservabilityFaultScriptExhaustedError",
    "create_observability_fault_harness",
]
